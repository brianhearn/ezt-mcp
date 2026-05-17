#!/usr/bin/env python3
"""Build static PMTiles archives for Map Component part layers.

The first supported layer is ``us_zips``. The script reads canonical part
geometry from PostGIS, writes an MBTiles archive containing MVT tiles, then uses
the installed ``pmtiles`` CLI to convert it to a browser-deliverable PMTiles
archive.

This is intentionally an operational build script, not request-path code.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import mercantile
from mapbox_vector_tile import encode as encode_mvt
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.validation import make_valid

DEFAULT_OUTPUT = "ezt_mcp/map_component/static/tiles/parts/us_zips.pmtiles"
TILE_SIZE = 4096


@dataclass(frozen=True)
class PartLayerSpec:
    part_layer: str
    label: str
    schema: str
    table: str
    id_column: str
    source_layer: str = "parts"
    minzoom: int = 5
    maxzoom: int = 10
    bounds: tuple[float, float, float, float] = (-125.0, 24.5, -66.5, 49.5)
    srid: int = 3785


SPECS = {
    "us_zips": PartLayerSpec(
        part_layer="us_zips",
        label="US ZIP Codes",
        schema="geo",
        table="us_postal",
        id_column="zipcode",
    )
}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build part-layer PMTiles from PostGIS.")
    parser.add_argument("--part-layer", default="us_zips", choices=sorted(SPECS))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--minzoom", type=int)
    parser.add_argument("--maxzoom", type=int)
    parser.add_argument("--pmtiles-bin", default="pmtiles")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-mbtiles")
    return parser.parse_args(argv)


async def build(args: argparse.Namespace) -> dict[str, Any]:
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    if shutil.which(args.pmtiles_bin) is None:
        raise SystemExit(f"pmtiles CLI not found: {args.pmtiles_bin}")

    spec = SPECS[args.part_layer]
    minzoom = spec.minzoom if args.minzoom is None else args.minzoom
    maxzoom = spec.maxzoom if args.maxzoom is None else args.maxzoom
    if not (0 <= minzoom <= maxzoom <= 14):
        raise SystemExit("Require 0 <= minzoom <= maxzoom <= 14 for this first builder.")

    output = Path(args.output)
    if output.exists() and not args.force:
        raise SystemExit(f"Output exists; pass --force to overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    conn = await asyncpg.connect(args.database_url)
    try:
        tmpdir = Path(tempfile.mkdtemp(prefix="ezt-part-pmtiles-"))
        mbtiles = Path(args.keep_mbtiles) if args.keep_mbtiles else tmpdir / f"{spec.part_layer}.mbtiles"
        if mbtiles.exists():
            mbtiles.unlink()
        tile_stats = await write_mbtiles(conn, spec, mbtiles, minzoom=minzoom, maxzoom=maxzoom)
    finally:
        await conn.close()

    tmp_output = output.with_suffix(output.suffix + ".tmp")
    if tmp_output.exists():
        tmp_output.unlink()
    subprocess.run(
        [args.pmtiles_bin, "convert", str(mbtiles), str(tmp_output), "--force"],
        check=True,
    )
    tmp_output.replace(output)
    subprocess.run([args.pmtiles_bin, "verify", str(output)], check=True)

    return {
        "ok": True,
        "part_layer": spec.part_layer,
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "tiles_written": tile_stats["tiles_written"],
        "empty_tiles": tile_stats["empty_tiles"],
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


async def write_mbtiles(
    conn: asyncpg.Connection,
    spec: PartLayerSpec,
    mbtiles: Path,
    *,
    minzoom: int,
    maxzoom: int,
) -> dict[str, int]:
    db = sqlite3.connect(str(mbtiles))
    try:
        db.execute("create table metadata (name text, value text)")
        db.execute("create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)")
        db.execute("create unique index tile_index on tiles (zoom_level, tile_column, tile_row)")
        metadata = mbtiles_metadata(spec, minzoom=minzoom, maxzoom=maxzoom)
        db.executemany("insert into metadata(name, value) values (?, ?)", metadata.items())

        source_features = await fetch_source_features(conn, spec)
        print(f"source_features={len(source_features)}", file=sys.stderr)
        tiles_written = 0
        empty_tiles = 0
        for z in range(minzoom, maxzoom + 1):
            x0, y0 = lonlat_to_tile(spec.bounds[0], spec.bounds[3], z)
            x1, y1 = lonlat_to_tile(spec.bounds[2], spec.bounds[1], z)
            rows = []
            for x in range(max(0, x0), min((1 << z) - 1, x1) + 1):
                for y in range(max(0, y0), min((1 << z) - 1, y1) + 1):
                    mvt = encode_tile(source_features, spec, z=z, x=x, y=y)
                    if mvt:
                        # MBTiles stores TMS row numbers, not XYZ row numbers.
                        tms_y = (1 << z) - 1 - y
                        rows.append((z, x, tms_y, gzip.compress(bytes(mvt))))
                    else:
                        empty_tiles += 1
            if rows:
                db.executemany(
                    "insert into tiles(zoom_level, tile_column, tile_row, tile_data) values (?, ?, ?, ?)",
                    rows,
                )
                db.commit()
                tiles_written += len(rows)
            print(f"z={z} complete tiles_written={tiles_written}", file=sys.stderr)
        return {"tiles_written": tiles_written, "empty_tiles": empty_tiles}
    finally:
        db.close()


async def fetch_source_features(conn: asyncpg.Connection, spec: PartLayerSpec) -> list[dict[str, Any]]:
    sql = f"""
        select
          {spec.id_column}::text as part_id,
          state::text as state,
          city::text as city,
          ST_AsGeoJSON(ST_Transform(geom, 4326)) as geometry_geojson
        from {spec.schema}.{spec.table}
        where geom is not null
          and {spec.id_column} is not null
    """
    rows = await conn.fetch(sql)
    features = []
    for row in rows:
        geometry_geojson = row["geometry_geojson"]
        if not geometry_geojson:
            continue
        geom = make_valid(shape(json.loads(geometry_geojson)))
        if geom.is_empty:
            continue
        features.append(
            {
                "geometry": geom,
                "bbox": geom.bounds,
                "properties": {
                    "part_id": row["part_id"],
                    "partcode": row["part_id"],
                    "state": row["state"],
                    "city": row["city"],
                },
            }
        )
    return features


def encode_tile(
    source_features: list[dict[str, Any]],
    spec: PartLayerSpec,
    *,
    z: int,
    x: int,
    y: int,
) -> bytes | None:
    west, south, east, north = mercantile.bounds(x, y, z)
    tile_bounds = (west, south, east, north)
    tile_box = box(west, south, east, north)
    features = []
    for source in source_features:
        if not bounds_intersect(source["bbox"], tile_bounds):
            continue
        try:
            clipped = source["geometry"].intersection(tile_box)
        except Exception:
            clipped = make_valid(source["geometry"]).intersection(tile_box)
        if clipped.is_empty:
            continue
        polygonal = polygonal_geometry(clipped)
        if polygonal is None or polygonal.is_empty:
            continue
        features.append({"geometry": polygonal, "properties": source["properties"]})
    if not features:
        return None
    return encode_mvt(
        [{"name": spec.source_layer, "features": features}],
        default_options={
            "quantize_bounds": tile_bounds,
            "extents": TILE_SIZE,
            "y_coord_down": False,
        },
    )


def polygonal_geometry(geometry: Any):
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    geoms = getattr(geometry, "geoms", None)
    if not geoms:
        return None
    polygons = []
    for item in geoms:
        if isinstance(item, Polygon):
            polygons.append(item)
        elif isinstance(item, MultiPolygon):
            polygons.extend(list(item.geoms))
    if not polygons:
        return None
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def bounds_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def mbtiles_metadata(spec: PartLayerSpec, *, minzoom: int, maxzoom: int) -> dict[str, str]:
    bounds = ",".join(str(value) for value in spec.bounds)
    center_lon = (spec.bounds[0] + spec.bounds[2]) / 2
    center_lat = (spec.bounds[1] + spec.bounds[3]) / 2
    vector_layers = [
        {
            "id": spec.source_layer,
            "description": spec.label,
            "minzoom": minzoom,
            "maxzoom": maxzoom,
            "fields": {
                "part_id": "String",
                "partcode": "String",
                "state": "String",
                "city": "String",
            },
        }
    ]
    return {
        "name": spec.label,
        "description": f"{spec.label} part boundaries generated from PostGIS.",
        "version": "1",
        "type": "overlay",
        "format": "pbf",
        "bounds": bounds,
        "center": f"{center_lon},{center_lat},{minzoom}",
        "minzoom": str(minzoom),
        "maxzoom": str(maxzoom),
        "json": json.dumps({"vector_layers": vector_layers}, separators=(",", ":")),
    }


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = asyncio.run(build(args))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

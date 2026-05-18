#!/usr/bin/env python3
"""Build production PMTiles for Map Component part layers with tippecanoe.

This is the preferred operational builder for z9+ part-layer overlays. It
exports canonical PostGIS geometry to newline-delimited GeoJSON Features, uses
``tippecanoe`` to produce an MBTiles vector archive, then converts that archive
to PMTiles with the ``pmtiles`` CLI.

The builder is intentionally an operational script, not request-path code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg

DEFAULT_OUTPUT = "ezt_mcp/map_component/static/tiles/parts/us_zips.pmtiles"


@dataclass(frozen=True)
class PartLayerSpec:
    part_layer: str
    label: str
    schema: str
    table: str
    id_column: str
    source_layer: str = "parts"
    minzoom: int = 5
    maxzoom: int = 12
    bounds: tuple[float, float, float, float] = (-125.0, 24.5, -66.5, 49.5)


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
    parser = argparse.ArgumentParser(
        description="Build production part-layer PMTiles from PostGIS using tippecanoe."
    )
    parser.add_argument("--part-layer", default="us_zips", choices=sorted(SPECS))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--minzoom", type=int)
    parser.add_argument("--maxzoom", type=int)
    parser.add_argument("--tippecanoe-bin", default="tippecanoe")
    parser.add_argument("--pmtiles-bin", default="pmtiles")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-geojsonseq")
    parser.add_argument("--keep-mbtiles")
    parser.add_argument(
        "--allow-tile-dropping",
        action="store_true",
        help="Allow tippecanoe to drop/coalesce features to enforce tile limits. Off by default.",
    )
    parser.add_argument(
        "--extra-tippecanoe-arg",
        action="append",
        default=[],
        help="Additional raw argument to append to the tippecanoe invocation.",
    )
    return parser.parse_args(argv)


async def build(args: argparse.Namespace) -> dict[str, Any]:
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    if shutil.which(args.tippecanoe_bin) is None:
        raise SystemExit(f"tippecanoe CLI not found: {args.tippecanoe_bin}")
    if shutil.which(args.pmtiles_bin) is None:
        raise SystemExit(f"pmtiles CLI not found: {args.pmtiles_bin}")

    spec = SPECS[args.part_layer]
    minzoom = spec.minzoom if args.minzoom is None else args.minzoom
    maxzoom = spec.maxzoom if args.maxzoom is None else args.maxzoom
    if not (0 <= minzoom <= maxzoom <= 14):
        raise SystemExit("Require 0 <= minzoom <= maxzoom <= 14 for part-layer PMTiles.")

    output = Path(args.output)
    if output.exists() and not args.force:
        raise SystemExit(f"Output exists; pass --force to overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    tmpdir = Path(tempfile.mkdtemp(prefix="ezt-part-tippecanoe-"))
    geojsonseq = Path(args.keep_geojsonseq) if args.keep_geojsonseq else tmpdir / f"{spec.part_layer}.geojsonseq"
    mbtiles = Path(args.keep_mbtiles) if args.keep_mbtiles else tmpdir / f"{spec.part_layer}.mbtiles"
    if geojsonseq.exists():
        geojsonseq.unlink()
    if mbtiles.exists():
        mbtiles.unlink()

    conn = await asyncpg.connect(args.database_url)
    try:
        export_stats = await export_geojsonseq(conn, spec, geojsonseq)
    finally:
        await conn.close()

    run_tippecanoe(
        args,
        spec,
        geojsonseq,
        mbtiles,
        minzoom=minzoom,
        maxzoom=maxzoom,
    )

    tmp_output = output.with_suffix(output.suffix + ".tmp")
    if tmp_output.exists():
        tmp_output.unlink()
    subprocess.run(
        [args.pmtiles_bin, "convert", str(mbtiles), str(tmp_output), "--force"],
        check=True,
    )
    tmp_output.replace(output)
    verify = subprocess.run(
        [args.pmtiles_bin, "verify", str(output)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    return {
        "ok": True,
        "part_layer": spec.part_layer,
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "features_exported": export_stats["features_exported"],
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "tippecanoe": shutil.which(args.tippecanoe_bin),
        "pmtiles": shutil.which(args.pmtiles_bin),
        "verify": verify.stdout.strip().splitlines()[-5:],
    }


async def export_geojsonseq(
    conn: asyncpg.Connection, spec: PartLayerSpec, geojsonseq: Path
) -> dict[str, int]:
    sql = f"""
        select
          {spec.id_column}::text as part_id,
          state::text as state,
          city::text as city,
          ST_AsGeoJSON(ST_Transform(geom, 4326), 6) as geometry_geojson
        from {spec.schema}.{spec.table}
        where geom is not null
          and {spec.id_column} is not null
        order by {spec.id_column}::text
    """
    count = 0
    geojsonseq.parent.mkdir(parents=True, exist_ok=True)
    with geojsonseq.open("w", encoding="utf-8") as handle:
        rows = await conn.fetch(sql)
        for row in rows:
            geometry_geojson = row["geometry_geojson"]
            if not geometry_geojson:
                continue
            feature = {
                "type": "Feature",
                "properties": {
                    "part_id": row["part_id"],
                    "partcode": row["part_id"],
                    "state": row["state"],
                    "city": row["city"],
                },
                "geometry": json.loads(geometry_geojson),
            }
            handle.write(json.dumps(feature, separators=(",", ":")))
            handle.write("\n")
            count += 1
    print(f"features_exported={count} geojsonseq={geojsonseq}", file=sys.stderr)
    return {"features_exported": count}


def run_tippecanoe(
    args: argparse.Namespace,
    spec: PartLayerSpec,
    geojsonseq: Path,
    mbtiles: Path,
    *,
    minzoom: int,
    maxzoom: int,
) -> None:
    command = [
        args.tippecanoe_bin,
        "--output",
        str(mbtiles),
        "--force",
        "--layer",
        spec.source_layer,
        "--name",
        spec.label,
        "--description",
        f"{spec.label} part boundaries generated from canonical PostGIS geometry.",
        "--minimum-zoom",
        str(minzoom),
        "--maximum-zoom",
        str(maxzoom),
        "--detect-shared-borders",
        "--simplify-only-low-zooms",
        "--no-tiny-polygon-reduction-at-maximum-zoom",
        "--read-parallel",
    ]
    if not args.allow_tile_dropping:
        command.extend(["--no-feature-limit", "--no-tile-size-limit"])
    command.extend(args.extra_tippecanoe_arg)
    command.append(str(geojsonseq))

    print("running:", " ".join(command), file=sys.stderr)
    subprocess.run(command, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = asyncio.run(build(args))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

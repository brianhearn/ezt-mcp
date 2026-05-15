#!/usr/bin/env python3
"""Benchmark Direct Build with real ZIP geometries from the configured database.

This is an operator/dev script, not a unit test. It reads geography from the
configured DATABASE_URL and performs no writes unless --submit-job is added in a
future extension.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import asyncpg

from ezt_mcp.db.parts import AsyncpgPartsRepository
from ezt_mcp.territory.dissolve import DissolveOptions
from ezt_mcp.tools.direct_build import build_direct_tal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Direct Build on real ZIP geometries")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--part-layer", default="us_zips")
    parser.add_argument("--state", default="FL", help="State/province filter for query_parts")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--territories", type=int, default=10)
    parser.add_argument("--partition-threshold", type=int, default=10000)
    parser.add_argument("--target-parts-per-cluster", type=int, default=100)
    parser.add_argument("--max-clusters", type=int, default=30)
    parser.add_argument("--output", help="Optional JSON output path")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")
    if args.territories < 1:
        raise SystemExit("--territories must be >= 1")

    pool = await asyncpg.create_pool(args.database_url, min_size=1, max_size=3)
    try:
        repo = AsyncpgPartsRepository(pool)
        part_ids = await _fetch_part_ids(pool, args.part_layer, args.state, args.limit)
        t0 = time.perf_counter()
        geometries = await repo.fetch_part_geometries(args.part_layer, part_ids)
        fetch_seconds = time.perf_counter() - t0

        assignments = [
            {
                "part_id": part_id,
                "territory_path": [f"Territory {index % args.territories + 1:03d}"],
            }
            for index, part_id in enumerate(part_ids)
        ]
        request = {
            "part_layer": args.part_layer,
            "tal_label": f"Scalability {args.limit} {args.part_layer}",
            "assignments": assignments,
        }
        options = DissolveOptions(
            partition_threshold=args.partition_threshold,
            target_parts_per_cluster=args.target_parts_per_cluster,
            max_clusters=args.max_clusters,
        )
        t1 = time.perf_counter()
        result = build_direct_tal(request, geometries, dissolve_options=options)
        build_seconds = time.perf_counter() - t1

        summary: dict[str, Any] = {
            "ok": result.get("ok") is True,
            "part_layer": args.part_layer,
            "state": args.state,
            "requested_limit": args.limit,
            "part_count": len(part_ids),
            "fetched_geometry_count": len(geometries),
            "territory_count": result.get("result", {}).get("territory_count"),
            "fetch_seconds": round(fetch_seconds, 6),
            "build_seconds": round(build_seconds, 6),
            "total_seconds": round(fetch_seconds + build_seconds, 6),
            "partition_threshold": args.partition_threshold,
            "target_parts_per_cluster": args.target_parts_per_cluster,
            "max_clusters": args.max_clusters,
            "warnings": result.get("warnings", []),
        }
        print(json.dumps(summary, indent=2))
        if args.output:
            Path(args.output).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return 0
    finally:
        await pool.close()


async def _fetch_part_ids(pool: Any, part_layer: str, state: str, limit: int) -> list[str]:
    if part_layer != "us_zips":
        raise SystemExit("Current scalability script supports --part-layer us_zips only")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select zipcode::text as part_id
            from geo.us_postal
            where state = $1
            order by zipcode
            limit $2
            """,
            state,
            limit,
        )
    return [str(row["part_id"]) for row in rows]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

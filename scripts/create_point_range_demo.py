#!/usr/bin/env python3
"""Create a live Map Component demo with many point locations and range classification.

This is a visual QA/demo helper for the MC Layer-Legend point-layer path. It posts a
synthetic TS to /get-map-visualization and prints the resulting map URL plus basic
class counts.

Examples:
    EZT_MCP_API_KEY=*** python scripts/create_point_range_demo.py
    EZT_MCP_API_KEY=*** python scripts/create_point_range_demo.py --point-scale 2 --expiry-seconds 7200
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import urllib.request
from collections.abc import Sequence
from typing import Any

DEFAULT_BASE_URL = "https://expertpack.ai/mcp"

TERRITORIES = [
    ("t-nfl", "North Florida", [(-87.7, 29.5), (-81.0, 29.5), (-81.0, 31.2), (-87.7, 31.2), (-87.7, 29.5)]),
    ("t-cfl", "Central Florida", [(-83.4, 27.4), (-80.0, 27.4), (-80.0, 29.5), (-83.4, 29.5), (-83.4, 27.4)]),
    ("t-sfl", "South Florida", [(-82.4, 24.5), (-79.8, 24.5), (-79.8, 27.4), (-82.4, 27.4), (-82.4, 24.5)]),
    ("t-ga", "Georgia", [(-85.6, 31.2), (-80.8, 31.2), (-80.8, 35.0), (-85.6, 35.0), (-85.6, 31.2)]),
    ("t-al", "Alabama", [(-88.5, 30.2), (-85.0, 30.2), (-85.0, 35.0), (-88.5, 35.0), (-88.5, 30.2)]),
]

CITY_CLUSTERS = [
    ("Miami", -80.19, 25.76, 1.55, 60),
    ("Tampa", -82.46, 27.95, 1.18, 45),
    ("Orlando", -81.38, 28.54, 1.25, 45),
    ("Jacksonville", -81.66, 30.33, 0.88, 35),
    ("Tallahassee", -84.28, 30.44, 0.62, 25),
    ("Atlanta", -84.39, 33.75, 1.42, 50),
    ("Savannah", -81.09, 32.08, 0.72, 25),
    ("Birmingham", -86.80, 33.52, 0.78, 25),
    ("Mobile", -88.04, 30.69, 0.66, 20),
]

CLASS_BREAKS = [
    {"id": "rev-0-1", "label": "<$1M", "min": 0, "max": 1, "color": "#38bdf8"},
    {"id": "rev-1-3", "label": "$1M–$3M", "min": 1, "max": 3, "color": "#22c55e"},
    {"id": "rev-3-6", "label": "$3M–$6M", "min": 3, "max": 6, "color": "#facc15"},
    {"id": "rev-6-10", "label": "$6M–$10M", "min": 6, "max": 10, "color": "#fb923c"},
    {"id": "rev-10-plus", "label": "$10M+", "min": 10, "color": "#ef4444"},
]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a point-layer range-class MC demo")
    parser.add_argument("--base-url", default=os.environ.get("EZT_MCP_PUBLIC_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("EZT_MCP_API_KEY"))
    parser.add_argument("--expiry-seconds", type=int, default=7200)
    parser.add_argument("--point-scale", type=int, default=1, help="Multiplier for default 330 points")
    parser.add_argument("--seed", type=int, default=20260518)
    parser.add_argument("--user-id", default="brian-point-range-demo")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    return parser.parse_args(argv)


def build_ts(*, seed: int, point_scale: int) -> tuple[dict[str, Any], dict[str, int]]:
    rng = random.Random(seed)
    features: list[dict[str, Any]] = []
    territory_colors = ["#2563eb", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]
    for idx, (tid, label, coords) in enumerate(TERRITORIES):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "tal_id": "tal-demo-range",
                    "territory_id": tid,
                    "label": label,
                    "is_leaf": True,
                    "depth": 1,
                    "part_ids": [tid.upper()],
                    "_render_color": territory_colors[idx],
                },
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )

    class_counts = {item["label"]: 0 for item in CLASS_BREAKS}
    point_index = 1
    for city, lon, lat, demand_bias, base_count in CITY_CLUSTERS:
        for _ in range(base_count * max(1, point_scale)):
            radius = abs(rng.gauss(0.0, 0.38))
            theta = rng.random() * math.tau
            x = lon + math.cos(theta) * radius * 1.25
            y = lat + math.sin(theta) * radius * 0.85
            revenue_m = max(0.1, rng.lognormvariate(math.log(1.8 * demand_bias), 0.68))
            open_pipeline_m = max(0.0, revenue_m * rng.uniform(0.2, 1.4))
            growth_pct = rng.uniform(-8, 38) + (demand_bias - 1) * 8
            revenue_m = round(revenue_m, 2)
            _increment_class_counts(class_counts, revenue_m)
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "feature_kind": "point",
                        "point_layer": "customer_locations",
                        "point_id": f"acct-{point_index:04d}",
                        "account_name": f"{city} Account {point_index:03d}",
                        "city": city,
                        "annual_revenue_m": revenue_m,
                        "open_pipeline_m": round(open_pipeline_m, 2),
                        "growth_pct": round(growth_pct, 1),
                    },
                    "geometry": {"type": "Point", "coordinates": [round(x, 5), round(y, 5)]},
                }
            )
            point_index += 1

    ts = {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-demo-range",
            "ts_identity": {
                "ts_id": "ts-point-range-demo",
                "revision": 1,
                "content_hash": "sha256:" + "5" * 64,
                "updated_at": "2026-05-18T15:40:00Z",
            },
            "territory_alignment_layers": [
                {"tal_id": "tal-demo-range", "label": "SE demo territories", "part_layer": "us_zips"}
            ],
            "presentation": {
                "executive_review": {
                    "custom_content": {
                        "title": "Point range-classification demo",
                        "text": "Synthetic customer locations across FL/GA/AL. Point color is annual revenue range; class toggles filter points by revenue band.",
                        "items": [
                            f"{point_index - 1} point locations",
                            "5 annual-revenue classes",
                            "Use the Layer-Legend class checkboxes to test range filtering",
                        ],
                    }
                }
            },
            "point_layers": [
                {
                    "point_layer": "customer_locations",
                    "label": "Customer locations — annual revenue range",
                    "label_field": "account_name",
                    "default_visible": True,
                    "style": {"color": "#94a3b8", "size": 6, "opacity": 0.82},
                    "classification": {
                        "field": "annual_revenue_m",
                        "method": "range",
                        "unit": "USD millions",
                        "default_color": "#64748b",
                        "classes": CLASS_BREAKS,
                    },
                    "filters": [{"field": "annual_revenue_m", "op": "gte", "value": 0}],
                }
            ],
        },
        "features": features,
    }
    return ts, class_counts


def _increment_class_counts(counts: dict[str, int], value: float) -> None:
    for item in CLASS_BREAKS:
        min_value = item.get("min", float("-inf"))
        max_value = item.get("max", float("inf"))
        if value >= min_value and value < max_value:
            counts[item["label"]] += 1
            return


def create_demo(args: argparse.Namespace) -> dict[str, Any]:
    if not args.api_key:
        raise SystemExit("EZT_MCP_API_KEY or --api-key required")
    ts, class_counts = build_ts(seed=args.seed, point_scale=args.point_scale)
    body = {
        "ts": ts,
        "mode": "view",
        "active_tal_id": "tal-demo-range",
        "presentation": {"style_overrides": {"theme": "dark"}},
        "expiry_seconds": args.expiry_seconds,
        "user_id": args.user_id,
        "part_layers": ["us_zips"],
        "active_part_layer": "us_zips",
    }
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/get-map-visualization",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise SystemExit(json.dumps(payload, indent=2))
    result = payload["result"]
    return {
        "ok": True,
        "map_url": result.get("map_url"),
        "map_session_id": result.get("map_session_id"),
        "expires_at": result.get("expires_at"),
        "territory_count": len(TERRITORIES),
        "point_count": sum(class_counts.values()),
        "class_counts": class_counts,
    }


def print_human(summary: dict[str, Any]) -> None:
    print("POINT RANGE DEMO CREATED")
    print(f"map_url: {summary['map_url']}")
    print(f"expires_at: {summary['expires_at']}")
    print(f"territories: {summary['territory_count']}")
    print(f"points: {summary['point_count']}")
    print("class_counts:")
    for label, count in summary["class_counts"].items():
        print(f"  {label}: {count}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or [])
    summary = create_demo(args)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))

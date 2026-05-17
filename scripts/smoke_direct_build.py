#!/usr/bin/env python3
"""Smoke-test live HTTP Direct Build against real part geometries.

The script submits a tiny queued ``/direct-build`` job, polls it to completion,
retrieves the completed result, and asserts the pieces that prove the real
Direct Build path is healthy: PostGIS geometry fetch, hierarchy materialization,
leaf/rollup dissolve, ``geometry_summary``, TAL metadata, and optional Map
Component URL/render-payload creation.

Examples:
    EZT_MCP_API_KEY=*** python scripts/smoke_direct_build.py \
        --base-url https://expertpack.ai/mcp

    ssh root@165.245.136.51 \
        'set -a; . /opt/ezt-mcp/.env; /opt/ezt-mcp/.venv/bin/python \
         /opt/ezt-mcp/scripts/smoke_direct_build.py --base-url https://expertpack.ai/mcp'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import Any

DEFAULT_BASE_URL = "https://expertpack.ai/mcp"
DEFAULT_PART_IDS = ["32003", "32009", "32008"]
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled", "expired"}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test queued Direct Build over live HTTP."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EZT_MCP_PUBLIC_URL", DEFAULT_BASE_URL),
        help=f"EZT MCP HTTP base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("EZT_MCP_API_KEY"),
        help="Bearer API key. Defaults to EZT_MCP_API_KEY.",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--part-layer", default="us_zips")
    parser.add_argument("--part-id", dest="part_ids", action="append")
    parser.add_argument("--tal-label")
    parser.add_argument("--tal-id")
    parser.add_argument(
        "--map-visualization",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create and verify a Map Component URL from the completed TS (default: true).",
    )
    parser.add_argument(
        "--part-layer-overlay",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Request the built part layer as a Map Component PMTiles overlay (default: true).",
    )
    parser.add_argument("--user-id")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser.parse_args(argv)


def smoke(args: argparse.Namespace) -> dict[str, Any]:
    if not args.api_key:
        raise SystemExit("EZT_MCP_API_KEY or --api-key is required")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")

    base_url = str(args.base_url).rstrip("/")
    part_ids = args.part_ids or DEFAULT_PART_IDS
    stamp = int(time.time())
    tal_label = args.tal_label or f"Live Direct Build Smoke {stamp}"
    tal_id = args.tal_id or f"tal-live-direct-build-smoke-{stamp}"

    submitted = request_json(
        "POST",
        f"{base_url}/direct-build",
        api_key=args.api_key,
        body={
            "part_layer": args.part_layer,
            "tal_label": tal_label,
            "tal_id": tal_id,
            "assignments": smoke_assignments(part_ids),
        },
    )
    require_ok(submitted, "submit direct_build")
    job_ref = submitted["result"]
    job_id = job_ref["job_id"]
    status_url = absolute_status_url(base_url, job_ref)
    result_url = absolute_result_url(base_url, job_ref, job_id)

    final_status = poll_job_status(
        status_url,
        api_key=args.api_key,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
    )
    if final_status.get("status") != "completed":
        raise RuntimeError(f"Direct Build job did not complete: {json.dumps(final_status, indent=2)}")

    result_payload = request_json("GET", result_url, api_key=args.api_key, timeout=20)
    require_ok(result_payload, "fetch direct_build result")
    result = result_payload["result"]
    assertions = assert_direct_build_result(result, tal_id=tal_id, part_ids=part_ids)

    map_summary: dict[str, Any] | None = None
    if args.map_visualization:
        map_summary = create_and_verify_map_visualization(
            base_url,
            api_key=args.api_key,
            ts=result["ts"],
            tal_id=tal_id,
            user_id=args.user_id or f"direct-build-smoke-{stamp}",
            part_layers=[args.part_layer] if args.part_layer_overlay else None,
        )

    return {
        "ok": True,
        "base_url": base_url,
        "job_id": job_id,
        "job_status": final_status.get("status"),
        "job_phase": final_status.get("phase"),
        "tal_id": result.get("tal_id"),
        "part_layer": args.part_layer,
        "part_ids": part_ids,
        "territory_count": result.get("territory_count"),
        "hierarchy_summary": result.get("hierarchy_summary"),
        "geometry_summary": result.get("geometry_summary"),
        "assignment_summary": result.get("assignment_summary"),
        "tal_metadata": assertions["tal_metadata"],
        "feature_geometry_types": assertions["feature_geometry_types"],
        "feature_labels": assertions["feature_labels"],
        "map": map_summary,
        "status_url": status_url,
        "result_url": result_url,
    }


def smoke_assignments(part_ids: Sequence[str]) -> list[dict[str, Any]]:
    if len(part_ids) < 3:
        return [
            {"part_id": part_id, "territory_path": ["Smoke", f"Territory {index + 1}"]}
            for index, part_id in enumerate(part_ids)
        ]
    first, second, third, *rest = part_ids
    assignments = [
        {"part_id": first, "territory_path": ["Smoke", "Northeast Florida"]},
        {"part_id": second, "territory_path": ["Smoke", "Northeast Florida"]},
        {"part_id": third, "territory_path": ["Smoke", "North Central Florida"]},
    ]
    for index, part_id in enumerate(rest, start=4):
        assignments.append({"part_id": part_id, "territory_path": ["Smoke", f"Extra {index}"]})
    return assignments


def assert_direct_build_result(
    result: dict[str, Any], *, tal_id: str, part_ids: Sequence[str]
) -> dict[str, Any]:
    require(result.get("tal_id") == tal_id, f"unexpected tal_id: {result.get('tal_id')!r}")
    require(result.get("territory_count") == 3, f"expected 3 territories, got {result.get('territory_count')!r}")

    assignment_summary = require_dict(result.get("assignment_summary"), "assignment_summary")
    require(
        assignment_summary.get("assigned_part_count") == len(set(part_ids)),
        f"expected {len(set(part_ids))} assigned parts, got {assignment_summary.get('assigned_part_count')!r}",
    )

    hierarchy_summary = require_dict(result.get("hierarchy_summary"), "hierarchy_summary")
    require(hierarchy_summary.get("max_depth") == 1, "expected one hierarchy level below Smoke")
    require(hierarchy_summary.get("leaf_territory_count") == 2, "expected 2 leaf territories")
    require(hierarchy_summary.get("rollup_territory_count") == 1, "expected 1 rollup territory")

    geometry_summary = require_dict(result.get("geometry_summary"), "geometry_summary")
    require(geometry_summary.get("geometry_backend"), "geometry_summary.geometry_backend is required")
    require(geometry_summary.get("territory_count") == 3, "geometry_summary territory count mismatch")
    require(geometry_summary.get("leaf_territory_count") == 2, "geometry_summary leaf count mismatch")
    require(geometry_summary.get("rollup_territory_count") == 1, "geometry_summary rollup count mismatch")
    assert_bbox(geometry_summary.get("bbox"), "geometry_summary.bbox")

    ts = require_dict(result.get("ts"), "ts")
    features = ts.get("features")
    require(isinstance(features, list), "ts.features must be a list")
    tal_features = [
        feature for feature in features
        if isinstance(feature, dict)
        and isinstance(feature.get("properties"), dict)
        and feature["properties"].get("tal_id") == tal_id
    ]
    require(len(tal_features) == 3, f"expected 3 features for {tal_id}, got {len(tal_features)}")
    geometry_types = sorted(
        str(require_dict(feature.get("geometry"), "feature.geometry").get("type"))
        for feature in tal_features
    )
    require(
        set(geometry_types).issubset({"Polygon", "MultiPolygon"}),
        f"unexpected feature geometry types: {geometry_types}",
    )
    labels = sorted(
        str(require_dict(feature.get("properties"), "feature.properties").get("label"))
        for feature in tal_features
    )
    require(labels == ["North Central Florida", "Northeast Florida", "Smoke"], f"unexpected labels: {labels}")

    properties = require_dict(ts.get("properties"), "ts.properties")
    tal_metadata = tal_metadata_for(properties, tal_id)
    require(tal_metadata.get("geometry_backend") == geometry_summary.get("geometry_backend"), "TAL metadata backend mismatch")
    require(tal_metadata.get("bbox") == geometry_summary.get("bbox"), "TAL metadata bbox mismatch")

    return {
        "feature_geometry_types": geometry_types,
        "feature_labels": labels,
        "tal_metadata": tal_metadata,
    }


def tal_metadata_for(ts_properties: dict[str, Any], tal_id: str) -> dict[str, Any]:
    candidates = [
        ts_properties.get("tal_metadata"),
        ts_properties.get("tals"),
        ts_properties.get("territory_alignment_layers"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate.get(tal_id)
            if isinstance(value, dict):
                return value
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict) and item.get("tal_id") == tal_id:
                    return item
    # Current TS shape stores TAL metadata in properties.alignments.
    alignments = ts_properties.get("alignments")
    if isinstance(alignments, list):
        for item in alignments:
            if isinstance(item, dict) and item.get("tal_id") == tal_id:
                return item
    raise RuntimeError(f"TAL metadata for {tal_id} was not found in TS properties")


def create_and_verify_map_visualization(
    base_url: str,
    *,
    api_key: str,
    ts: dict[str, Any],
    tal_id: str,
    user_id: str,
    part_layers: list[str] | None = None,
) -> dict[str, Any]:
    created = request_json(
        "POST",
        f"{base_url}/get-map-visualization",
        api_key=api_key,
        body={
            "ts": ts,
            "mode": "view",
            "active_tal_id": tal_id,
            "presentation": {"style_overrides": {"theme": "dark"}},
            "expiry_seconds": 900,
            "user_id": user_id,
            **({"part_layers": part_layers, "active_part_layer": part_layers[0]} if part_layers else {}),
        },
    )
    require_ok(created, "create map visualization")
    map_result = created["result"]
    map_url = str(map_result["map_url"])
    render_payload = request_json("GET", f"{map_url.rstrip('/')}/render-payload", timeout=20)
    features = render_payload_features(render_payload)
    require(len(features) == 3, f"expected 3 render features, got {len(features)}")
    active_tal = render_payload.get("active_tal")
    if isinstance(active_tal, dict):
        require(active_tal.get("tal_id") == tal_id, "render payload active_tal.tal_id mismatch")
    else:
        require(render_payload.get("active_tal_id") == tal_id, "render payload active_tal_id mismatch")
    bounds = render_payload.get("bounds")
    if bounds is not None:
        assert_bbox(bounds, "render_payload.bounds")
    part_layer_payloads = render_payload.get("part_layers") or []
    if part_layers:
        require(part_layer_payloads, "render payload part_layers are required")
        require(
            render_payload.get("active_part_layer") == part_layers[0],
            "render payload active_part_layer mismatch",
        )
    return {
        "map_session_id": map_result.get("map_session_id"),
        "map_url": map_url,
        "expires_at": map_result.get("expires_at"),
        "render_feature_count": len(features),
        "render_bounds": bounds,
        "active_part_layer": render_payload.get("active_part_layer"),
        "part_layers": [layer.get("part_layer") for layer in part_layer_payloads],
    }


def render_payload_features(render_payload: dict[str, Any]) -> list[Any]:
    features = render_payload.get("features")
    if isinstance(features, list):
        return features
    geojson = render_payload.get("geojson")
    if isinstance(geojson, dict) and isinstance(geojson.get("features"), list):
        return geojson["features"]
    ts = render_payload.get("ts")
    if isinstance(ts, dict) and isinstance(ts.get("features"), list):
        return ts["features"]
    raise RuntimeError("render payload features must be a list")


def request_json(
    method: str,
    url: str,
    *,
    api_key: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed HTTP {exc.code}: {raw}") from exc


def require_ok(payload: dict[str, Any], label: str) -> None:
    if payload.get("ok") is not True:
        raise RuntimeError(f"{label} failed: {json.dumps(payload, indent=2)}")


def absolute_status_url(base_url: str, job_ref: dict[str, Any]) -> str:
    raw = job_ref.get("status_url") or f"/jobs/{job_ref['job_id']}/status"
    return absolute_url(base_url, str(raw))


def absolute_result_url(base_url: str, job_ref: dict[str, Any], job_id: str) -> str:
    raw = job_ref.get("result_url") or f"/jobs/{job_id}/result"
    return absolute_url(base_url, str(raw))


def absolute_url(base_url: str, raw: str) -> str:
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("ezt://"):
        parsed = urllib.parse.urlparse(raw)
        return f"{base_url}/{parsed.netloc}{parsed.path}"
    return f"{base_url}{raw if raw.startswith('/') else '/' + raw}"


def poll_job_status(
    status_url: str,
    *,
    api_key: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_status = request_json("GET", status_url, api_key=api_key, timeout=10)
        if str(last_status.get("status") or "") in TERMINAL_JOB_STATUSES:
            return last_status
        time.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Job did not reach a terminal status within {timeout_seconds}s; "
        f"last_status={last_status}"
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def assert_bbox(value: Any, label: str) -> None:
    require(isinstance(value, list), f"{label} must be a list")
    require(len(value) == 4, f"{label} must contain 4 numbers")
    for item in value:
        require(isinstance(item, int | float), f"{label} must contain only numbers")


def print_human(summary: dict[str, Any]) -> None:
    print("PASS Direct Build smoke")
    print(f"job_id={summary['job_id']} status={summary['job_status']} phase={summary['job_phase']}")
    print(f"tal_id={summary['tal_id']}")
    print(f"part_layer={summary['part_layer']} part_ids={summary['part_ids']}")
    print(f"territory_count={summary['territory_count']}")
    print(f"hierarchy_summary={summary['hierarchy_summary']}")
    print(f"geometry_summary={summary['geometry_summary']}")
    print(f"feature_geometry_types={summary['feature_geometry_types']}")
    print(f"feature_labels={summary['feature_labels']}")
    if summary.get("map"):
        print(f"map_session_id={summary['map']['map_session_id']}")
        print(f"map_render_feature_count={summary['map']['render_feature_count']}")
        print(f"map_active_part_layer={summary['map']['active_part_layer']}")
        print(f"map_part_layers={summary['map']['part_layers']}")
        print(f"map_url={summary['map']['map_url']}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = smoke(args)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

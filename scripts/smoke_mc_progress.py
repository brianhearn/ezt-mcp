#!/usr/bin/env python3
"""Smoke-test MC-linked queued territory-build progress over live HTTP/SSE.

The script creates a short-lived Map Component session, opens its Server-Sent
Events stream, submits a create_territory_from_parts job with the map_session_id,
polls the durable job to completion, and verifies the MC stream receives progress
including a final done event.

Examples:
    EZT_MCP_API_KEY=*** python scripts/smoke_mc_progress.py \
        --base-url https://expertpack.ai/mcp

    ssh root@165.245.136.51 \
        'set -a; . /opt/ezt-mcp/.env; /opt/ezt-mcp/.venv/bin/python \
         /opt/ezt-mcp/scripts/smoke_mc_progress.py --base-url https://expertpack.ai/mcp'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

DEFAULT_BASE_URL = "https://expertpack.ai/mcp"
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled", "expired"}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test MC progress events from a queued create_territory_from_parts job."
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
    parser.add_argument("--territory-name")
    parser.add_argument("--user-id")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser.parse_args(argv)


async def smoke(args: argparse.Namespace) -> dict[str, Any]:
    if not args.api_key:
        raise SystemExit("EZT_MCP_API_KEY or --api-key is required")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")

    base_url = str(args.base_url).rstrip("/")
    part_ids = args.part_ids or ["32301", "32303", "32304"]
    stamp = int(time.time())
    territory_name = args.territory_name or f"Progress Smoke {stamp}"
    user_id = args.user_id or f"progress-smoke-{stamp}"

    created = request_json(
        "POST",
        f"{base_url}/get-map-visualization",
        api_key=args.api_key,
        body={
            "ts": synthetic_ts(),
            "mode": "view",
            "active_tal_id": "tal-progress-smoke-base",
            "presentation": {"style_overrides": {"theme": "dark"}},
            "expiry_seconds": 600,
            "user_id": user_id,
        },
    )
    require_ok(created, "create map visualization")
    map_result = created["result"]
    map_session_id = map_result["map_session_id"]
    map_url = map_result["map_url"]

    reader = asyncio.create_task(
        read_sse_until_done(
            f"{map_url.rstrip('/')}/events",
            map_session_id=map_session_id,
            timeout_seconds=args.timeout,
        )
    )
    # Give the event stream a brief chance to subscribe before the job starts.
    await asyncio.sleep(0.5)

    submitted = request_json(
        "POST",
        f"{base_url}/create-territory-from-parts",
        api_key=args.api_key,
        body={
            "part_layer": args.part_layer,
            "part_ids": part_ids,
            "territory_name": territory_name,
            "territory_path": ["Smoke", "Progress"],
            "conflict_policy": "move_from_existing",
            "map_session_id": map_session_id,
        },
    )
    require_ok(submitted, "submit create_territory_from_parts")
    job_ref = submitted["result"]
    job_id = job_ref["job_id"]
    status_url = absolute_status_url(base_url, job_ref)

    final_status = await poll_job_status(
        status_url,
        api_key=args.api_key,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
    )
    events = await reader

    progress_events = [event for event in events if event.get("type") == "progress"]
    progress_states = [str(event.get("state") or "") for event in progress_events]
    progress_percents = [event.get("percent") for event in progress_events]
    saw_done = any(event.get("state") == "done" for event in progress_events)
    completed = final_status.get("status") == "completed"
    ok = completed and saw_done

    return {
        "ok": ok,
        "base_url": base_url,
        "map_session_id": map_session_id,
        "map_url": map_url,
        "job_id": job_id,
        "job_status": final_status.get("status"),
        "job_phase": final_status.get("phase"),
        "progress_states": progress_states,
        "progress_percents": progress_percents,
        "saw_done_event": saw_done,
        "final_status": final_status,
        "events": events,
    }


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
    if str(raw).startswith("http://") or str(raw).startswith("https://"):
        return str(raw)
    return f"{base_url}{str(raw) if str(raw).startswith('/') else '/' + str(raw)}"


async def poll_job_status(
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
        await asyncio.sleep(poll_interval_seconds)
    raise TimeoutError(
        f"Job did not reach a terminal status within {timeout_seconds}s; "
        f"last_status={last_status}"
    )


async def read_sse_until_done(
    url: str,
    *,
    map_session_id: str,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    proc = await asyncio.create_subprocess_exec(
        "curl",
        "-N",
        "-s",
        "--max-time",
        str(timeout_seconds),
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    events: list[dict[str, Any]] = []
    event_name: str | None = None
    data_lines: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    assert proc.stdout is not None

    try:
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=max(0.1, deadline - time.monotonic())
                )
            except asyncio.TimeoutError:
                break
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                if data_lines:
                    event = parse_sse_event(event_name, data_lines)
                    events.append(event)
                    if (
                        event.get("type") == "progress"
                        and event.get("map_session_id") == map_session_id
                        and event.get("state") == "done"
                    ):
                        break
                event_name = None
                data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    return events


def parse_sse_event(event_name: str | None, data_lines: list[str]) -> dict[str, Any]:
    text = "\n".join(data_lines)
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            payload = {"data": payload}
    except json.JSONDecodeError:
        payload = {"raw": text}
    payload["_event"] = event_name
    return payload


def synthetic_ts() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-progress-smoke-base",
            "ts_identity": {
                "ts_id": "ts-progress-smoke",
                "revision": 1,
                "content_hash": "sha256:" + "7" * 64,
                "updated_at": "2026-05-16T12:00:00Z",
            },
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "tal_id": "tal-progress-smoke-base",
                    "territory_id": "baseline",
                    "label": "Baseline",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-84.6, 30.2],
                            [-83.7, 30.2],
                            [-83.7, 30.7],
                            [-84.6, 30.7],
                            [-84.6, 30.2],
                        ]
                    ],
                },
            }
        ],
    }


def print_human(summary: dict[str, Any]) -> None:
    status = "PASS" if summary["ok"] else "FAIL"
    print(f"{status} MC progress smoke")
    print(f"map_session_id={summary['map_session_id']}")
    print(f"job_id={summary['job_id']} status={summary['job_status']} phase={summary['job_phase']}")
    print(f"progress_states={summary['progress_states']}")
    print(f"progress_percents={summary['progress_percents']}")
    print(f"saw_done_event={summary['saw_done_event']}")
    print(f"map_url={summary['map_url']}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = asyncio.run(smoke(args))
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_human(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

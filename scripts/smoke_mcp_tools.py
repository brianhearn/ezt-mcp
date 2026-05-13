#!/usr/bin/env python3
"""Smoke-test EZT MCP tool discovery/calls over Streamable HTTP.

Examples:
    EZT_MCP_API_KEY=... python scripts/smoke_mcp_tools.py \
        --url https://expertpack.ai/mcp/ --query-parts

    python scripts/smoke_mcp_tools.py --url http://127.0.0.1:8100/ --map-visualization
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEFAULT_URL = "https://expertpack.ai/mcp/"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test EZT MCP tools")
    parser.add_argument(
        "--url",
        default=os.environ.get("EZT_MCP_URL", DEFAULT_URL),
        help=f"MCP Streamable HTTP URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("EZT_MCP_API_KEY"),
        help="Bearer API key. Defaults to EZT_MCP_API_KEY.",
    )
    parser.add_argument(
        "--query-parts",
        action="store_true",
        help="Call query_parts with a small default us_zips/state_abbr=FL query.",
    )
    parser.add_argument(
        "--map-visualization",
        action="store_true",
        help="Call get_map_visualization with a tiny synthetic TS.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON summary instead of human text.",
    )
    return parser.parse_args(argv)


async def smoke(
    url: str,
    api_key: str | None,
    *,
    call_query_parts: bool,
    call_map_visualization: bool,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    async with streamablehttp_client(url, headers=headers) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            calls: dict[str, Any] = {}
            if call_query_parts:
                result = await session.call_tool(
                    "query_parts",
                    {
                        "part_layer": "us_zips",
                        "filter": {"state_abbr": "FL"},
                        "max_results": 3,
                    },
                )
                calls["query_parts"] = _tool_result(result)
            if call_map_visualization:
                result = await session.call_tool(
                    "get_map_visualization",
                    {
                        "ts": _synthetic_ts(),
                        "mode": "view",
                        "active_tal_id": "tal-smoke",
                        "expiry_seconds": 300,
                    },
                )
                calls["get_map_visualization"] = _tool_result(result)

    return {
        "url": url,
        "server": {
            "name": init.serverInfo.name,
            "protocol_version": init.protocolVersion,
        },
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "has_output_schema": tool.outputSchema is not None,
            }
            for tool in tools.tools
        ],
        "calls": calls,
    }


def _tool_result(result: Any) -> dict[str, Any]:
    return {
        "is_error": result.isError,
        "structured_content": result.structuredContent,
        "content_texts": [getattr(content, "text", str(content)) for content in result.content],
    }


def _synthetic_ts() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-smoke",
            "ts_identity": {
                "ts_id": "ts-smoke",
                "revision": 1,
                "content_hash": "sha256:" + "3" * 64,
                "updated_at": "2026-05-13T20:00:00Z",
            },
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "tal_id": "tal-smoke",
                    "territory_id": "north",
                    "label": "North",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-84, 30], [-83, 30], [-83, 31], [-84, 31], [-84, 30]]],
                },
            }
        ],
    }


def print_human(summary: dict[str, Any]) -> None:
    server = summary["server"]
    print(f"INITIALIZED {server['name']} protocol={server['protocol_version']}")
    print(f"TOOLS {len(summary['tools'])}")
    for tool in summary["tools"]:
        print(
            "TOOL "
            f"{tool['name']} | output_schema={tool['has_output_schema']} | "
            f"{tool.get('description') or ''}"
        )
    for name, result in summary["calls"].items():
        print(f"CALL {name} is_error={result['is_error']}")
        structured = result.get("structured_content")
        if structured is not None:
            print(json.dumps(structured, indent=2)[:1600])
        for text in result.get("content_texts") or []:
            print(text[:1600])


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = anyio.run(
        lambda: smoke(
            args.url,
            args.api_key,
            call_query_parts=args.query_parts,
            call_map_visualization=args.map_visualization,
        )
    )
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

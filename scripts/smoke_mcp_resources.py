#!/usr/bin/env python3
"""Smoke-test EZT MCP resource discovery over Streamable HTTP.

Examples:
    EZT_MCP_API_KEY=... python scripts/smoke_mcp_resources.py \
        --url https://expertpack.ai/mcp/

    python scripts/smoke_mcp_resources.py --url http://127.0.0.1:8100/ --api-key dev-test-key
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
DEFAULT_DETAIL_RESOURCE = "ezt://part-layers/us_zips"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test EZT MCP resources")
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
        "--detail-resource",
        default=os.environ.get("EZT_MCP_DETAIL_RESOURCE", DEFAULT_DETAIL_RESOURCE),
        help=f"Detail resource to read (default: {DEFAULT_DETAIL_RESOURCE})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON summary instead of human text.",
    )
    return parser.parse_args(argv)


async def smoke(url: str, api_key: str | None, detail_resource: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    async with streamablehttp_client(url, headers=headers) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            list_result = await session.read_resource("ezt://part-layers")
            detail_result = await session.read_resource(detail_resource)

    return {
        "url": url,
        "server": {
            "name": init.serverInfo.name,
            "protocol_version": init.protocolVersion,
        },
        "resources": [
            {
                "uri": str(resource.uri),
                "name": resource.name,
                "description": resource.description,
            }
            for resource in resources.resources
        ],
        "resource_templates": [
            {
                "uri_template": template.uriTemplate,
                "name": template.name,
                "description": template.description,
            }
            for template in templates.resourceTemplates
        ],
        "reads": {
            "ezt://part-layers": _content_texts(list_result.contents),
            detail_resource: _content_texts(detail_result.contents),
        },
    }


def _content_texts(contents: Sequence[Any]) -> list[str]:
    return [getattr(content, "text", str(content)) for content in contents]


def print_human(summary: dict[str, Any]) -> None:
    server = summary["server"]
    print(f"INITIALIZED {server['name']} protocol={server['protocol_version']}")
    print(f"RESOURCES {len(summary['resources'])}")
    for resource in summary["resources"]:
        print(
            "RESOURCE "
            f"{resource['uri']} | {resource.get('name') or ''} | "
            f"{resource.get('description') or ''}"
        )
    print(f"TEMPLATES {len(summary['resource_templates'])}")
    for template in summary["resource_templates"]:
        print(
            "TEMPLATE "
            f"{template['uri_template']} | {template.get('name') or ''} | "
            f"{template.get('description') or ''}"
        )
    for uri, texts in summary["reads"].items():
        print(f"READ {uri} contents={len(texts)}")
        for text in texts:
            print(text[:1200])


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = anyio.run(smoke, args.url, args.api_key, args.detail_resource)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

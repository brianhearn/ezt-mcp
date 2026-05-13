from __future__ import annotations

import asyncio

from ezt_mcp.resources.part_layers import UnknownPartLayerError, assert_no_forbidden_public_fields
from ezt_mcp.tools.query_parts import (
    QueryPartsRequest,
    decode_page_token,
    encode_page_token,
    query_parts_tool,
)


class FakePartsRepo:
    def __init__(self):
        self.requests = []

    async def query_parts(self, request: QueryPartsRequest):
        self.requests.append(request)
        if request.part_layer == "moon_craters":
            raise UnknownPartLayerError(request.part_layer)
        return {
            "parts": [
                {
                    "part_id": "32301",
                    "attributes": {
                        "state_abbr": "FL",
                        "county_name": "Leon",
                        "population": 28000,
                    },
                }
            ],
            "total_count": 1,
            "part_layer": request.part_layer,
            "warnings": [],
        }


def test_query_parts_filter_payload_returns_safe_tool_envelope():
    repo = FakePartsRepo()
    payload = asyncio.run(
        query_parts_tool(
            repo,
            {"part_layer": "us_zips", "filter": {"state_abbr": "FL"}, "max_results": 50},
        )
    )

    assert payload["ok"] is True
    assert payload["result"]["parts"][0]["part_id"] == "32301"
    assert repo.requests[0].filter == {"state_abbr": "FL"}
    assert repo.requests[0].max_results == 50
    assert_no_forbidden_public_fields(payload)


def test_query_parts_part_ids_payload():
    repo = FakePartsRepo()
    payload = asyncio.run(
        query_parts_tool(repo, {"part_layer": "us_zips", "part_ids": ["32301", "32303"]})
    )

    assert payload["ok"] is True
    assert repo.requests[0].part_ids == ["32301", "32303"]


def test_query_parts_rejects_filter_and_part_ids_together():
    payload = asyncio.run(
        query_parts_tool(
            FakePartsRepo(),
            {"part_layer": "us_zips", "filter": {"state_abbr": "FL"}, "part_ids": ["32301"]},
        )
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_REQUEST"


def test_query_parts_unknown_part_layer_maps_to_error_envelope():
    payload = asyncio.run(
        query_parts_tool(FakePartsRepo(), {"part_layer": "moon_craters", "part_ids": ["A1"]})
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNKNOWN_PART_LAYER"
    assert payload["error"]["details"] == {"part_layer": "moon_craters"}


def test_page_token_round_trip_and_layer_guard():
    token = encode_page_token(part_layer="us_zips", offset=100)

    assert decode_page_token(token, part_layer="us_zips") == 100

    payload = asyncio.run(
        query_parts_tool(
            FakePartsRepo(),
            {"part_layer": "us_counties", "part_ids": ["12073"], "page_token": token},
        )
    )
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_PAGE_TOKEN"

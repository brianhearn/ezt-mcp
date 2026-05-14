from __future__ import annotations

from shapely.geometry import Polygon, mapping

import pytest

from ezt_mcp.map_component.sessions import (
    InMemoryMapSessionStore,
    MapVisualizationError,
    build_render_payload,
)


def square_feature(tal_id: str, territory_id: str, label: str, x: float, y: float):
    polygon = Polygon([(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)])
    return {
        "type": "Feature",
        "properties": {
            "tal_id": tal_id,
            "territory_id": territory_id,
            "label": label,
            "is_leaf": True,
            "part_ids": [territory_id.upper()],
        },
        "geometry": mapping(polygon),
    }


def sample_ts():
    return {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-current",
            "ts_identity": {
                "ts_id": "ts-demo",
                "revision": 3,
                "content_hash": "sha256:" + "1" * 64,
                "updated_at": "2026-05-13T18:30:00Z",
            },
            "territory_alignment_layers": [
                {"tal_id": "tal-current", "label": "Current Territories"}
            ],
        },
        "features": [
            square_feature("tal-current", "t-west", "West", -100, 35),
            square_feature("tal-current", "t-east", "East", -90, 36),
            square_feature("tal-other", "t-other", "Other", -80, 36),
        ],
    }


def test_build_render_payload_filters_active_tal_and_bounds():
    payload = build_render_payload(
        sample_ts(),
        active_tal_id="tal-current",
        mode="view",
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["active_tal"] == {
        "tal_id": "tal-current",
        "label": "Current Territories",
        "territory_count": 2,
    }
    assert payload["bounds"] == [-100.0, 35.0, -89.0, 37.0]
    assert len(payload["geojson"]["features"]) == 2
    assert payload["geojson"]["features"][0]["properties"]["_render_color"]
    assert payload["geojson"]["features"][0]["properties"]["part_ids"] == '["T-WEST"]'
    assert payload["basemap"]["url"] == "https://expertpack.ai/mcp/assets/tiles/us-basemap.pmtiles"


def test_build_render_payload_applies_presentation_template_and_overrides():
    ts = sample_ts()
    ts["properties"]["presentation"] = {
        "views": {
            "qa_verification": {
                "title": "QA From TS",
                "panel": {
                    "summary_items": [{"label": "Source", "value": "TS"}]
                },
            }
        }
    }

    payload = build_render_payload(
        ts,
        active_tal_id="tal-current",
        mode="view",
        presentation={
            "view_name": "qa_verification",
            "style_overrides": {
                "debug_panel": False,
                "panel": {
                    "summary_items": [{"label": "Override", "value": "Request"}]
                },
            },
        },
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["presentation"]["view_name"] == "qa_verification"
    assert payload["presentation"]["panel_template"] == "qa_verification"
    assert payload["presentation"]["title"] == "QA From TS"
    assert payload["presentation"]["debug_panel"] is False
    assert payload["presentation"]["panel"]["summary_items"] == [
        {"label": "Override", "value": "Request"}
    ]


def test_build_render_payload_defaults_select_mode_to_selection_template():
    payload = build_render_payload(
        sample_ts(),
        active_tal_id="tal-current",
        mode="select",
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["presentation"]["panel_template"] == "selection"
    assert payload["presentation"]["debug_panel"] is False


def test_session_store_returns_new_tab_response_and_validates_token():
    store = InMemoryMapSessionStore()
    session = store.create_session(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "expiry_seconds": 900,
        },
        public_base_url="https://expertpack.ai/mcp",
    )

    result = session.response_result(public_base_url="https://expertpack.ai/mcp")

    assert result["map_url"].startswith("https://expertpack.ai/mcp/maps/session/")
    assert result["presentation"] == {
        "preferred_open": "new_tab",
        "embed_status": "experimental",
        "open_in_new_tab_recommended": True,
    }
    assert result["session_exists"] is False
    assert result["active_tal_summary"]["territory_count"] == 2
    assert store.get_session(session.map_session_id, session.token) is session


def test_session_store_rejects_truncated_unicode_token_without_type_error():
    store = InMemoryMapSessionStore()
    session = store.create_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
    )

    with pytest.raises(MapVisualizationError) as exc:
        store.get_session(session.map_session_id, "abc…def")

    assert exc.value.code == "INVALID_TS_HANDLE"

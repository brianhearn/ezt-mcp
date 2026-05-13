from __future__ import annotations

from shapely.geometry import Polygon, mapping

from ezt_mcp.map_component.sessions import InMemoryMapSessionStore
from ezt_mcp.server import AppState, _create_map_visualization_tool_result


def _feature(tal_id: str, territory_id: str):
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    return {
        "type": "Feature",
        "properties": {"tal_id": tal_id, "territory_id": territory_id, "label": territory_id},
        "geometry": mapping(polygon),
    }


def _ts():
    return {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": "tal-a",
            "ts_identity": {
                "ts_id": "ts-demo",
                "revision": 1,
                "content_hash": "sha256:" + "2" * 64,
                "updated_at": "2026-05-13T20:00:00Z",
            },
        },
        "features": [_feature("tal-a", "north")],
    }


def test_create_map_visualization_tool_result_returns_schema_shape_with_path_token():
    state = AppState()
    state.map_sessions = InMemoryMapSessionStore()

    payload = _create_map_visualization_tool_result(
        state,
        {"ts": _ts(), "mode": "view"},
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["ok"] is True
    result = payload["result"]
    assert result["session_exists"] is False
    assert result["map_url"].startswith("https://expertpack.ai/mcp/maps/session/")
    assert "?token=" not in result["map_url"]
    assert result["active_tal_summary"]["tal_id"] == "tal-a"


def test_create_map_visualization_tool_result_maps_errors_to_envelope():
    state = AppState()

    payload = _create_map_visualization_tool_result(
        state,
        {"mode": "view"},
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_TS"

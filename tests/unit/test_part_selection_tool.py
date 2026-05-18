from __future__ import annotations

from ezt_mcp.server import AppState, _request_part_selection_tool_result
from tests.unit.test_map_visualization import sample_ts


def test_request_part_selection_creates_task_and_points_session_to_task_resource():
    state = AppState()

    payload = _request_part_selection_tool_result(
        state,
        {
            "ts": sample_ts(),
            "mode": "select",
            "active_tal_id": "tal-current",
            "user_id": "monica",
        },
        part_layer="us_zips",
        purpose="build_territory",
        prompt="Select ZIPs for North Florida.",
        public_base_url="https://expertpack.ai/mcp",
    )

    assert payload["ok"] is True
    result = payload["result"]
    assert result["status"] == "awaiting_user_selection"
    assert result["purpose"] == "build_territory"
    assert result["part_layer"] == "us_zips"
    assert result["selection_resource_uri"].startswith("ezt://part-selections/psel_")

    state_payload = state.map_sessions.get_state(result["map_session_id"])
    assert state_payload["mode"] == "select"
    assert state_payload["active_selection_task_id"] == result["selection_task_id"]
    session = state.map_sessions.get_session(result["map_session_id"])
    assert session.render_payload["active_part_layer"] == "us_zips"
    assert session.render_payload["part_layers"][0]["part_layer"] == "us_zips"


def test_request_part_selection_reuses_persistent_user_session():
    state = AppState()
    first = _request_part_selection_tool_result(
        state,
        {"ts": sample_ts(), "mode": "select", "user_id": "monica"},
        part_layer="us_zips",
        purpose="return_list",
        prompt=None,
        public_base_url="https://expertpack.ai/mcp",
    )
    second = _request_part_selection_tool_result(
        state,
        {"ts": sample_ts(), "mode": "select", "user_id": "monica"},
        part_layer="us_zips",
        purpose="analyze",
        prompt=None,
        public_base_url="https://expertpack.ai/mcp",
    )

    assert second["ok"] is True
    assert second["result"]["session_exists"] is True
    assert second["result"]["map_session_id"] == first["result"]["map_session_id"]
    assert second["result"]["selection_task_id"] != first["result"]["selection_task_id"]

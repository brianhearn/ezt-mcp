from __future__ import annotations

from starlette.testclient import TestClient

from ezt_mcp.config import ServerConfig
from ezt_mcp.jobs import CustomerContext
from ezt_mcp.server import _request_part_selection_tool_result, build_app
from tests.unit.test_map_visualization import sample_ts


def test_map_commit_updates_first_class_part_selection_task():
    app = build_app(ServerConfig(map_visualization={"public_base_url": "https://expertpack.ai/mcp"}))
    state = app.state.ezt_state
    requested = _request_part_selection_tool_result(
        state,
        {"ts": sample_ts(), "mode": "select", "user_id": "monica"},
        part_layer="us_zips",
        purpose="return_list",
        prompt="Pick ZIPs.",
        public_base_url="https://expertpack.ai/mcp",
    )
    result = requested["result"]
    session = state.map_sessions.get_session(result["map_session_id"])

    with TestClient(app) as client:
        response = client.post(
            f"/maps/session/{session.map_session_id}/{session.token}/selection",
            json={
                "part_layer": "us_zips",
                "part_ids": ["32301", "32301", "32303"],
                "selection_method": "box",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["selection_task_id"] == result["selection_task_id"]
    assert payload["part_selection"]["status"] == "committed"
    assert payload["part_selection"]["selection"]["part_ids"] == ["32301", "32303"]

    task = state.part_selections.get(
        CustomerContext(customer_id="00000000-0000-0000-0000-000000000001"),
        result["selection_task_id"],
    )
    assert task.resource()["status"] == "committed"

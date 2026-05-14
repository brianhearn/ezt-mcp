from __future__ import annotations

from starlette.testclient import TestClient

from ezt_mcp.config import ServerConfig
from ezt_mcp.server import build_app
from tests.unit.test_map_visualization import sample_ts


def test_browser_route_switches_active_tal_and_render_payload():
    app = build_app(ServerConfig(map_visualization={"public_base_url": "https://expertpack.ai/mcp"}))
    state = app.state.ezt_state
    created = state.map_sessions.create_or_update_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )
    session = created.session

    with TestClient(app) as client:
        response = client.post(
            f"/maps/session/{session.map_session_id}/{session.token}/active-tal",
            json={"active_tal_id": "tal-other"},
        )
        payload_response = client.get(
            f"/maps/session/{session.map_session_id}/{session.token}/render-payload"
        )

    assert response.status_code == 200
    assert response.json()["result"]["active_tal_id"] == "tal-other"
    assert payload_response.status_code == 200
    payload = payload_response.json()
    assert payload["active_tal"]["tal_id"] == "tal-other"
    assert payload["available_tals"] == [
        {
            "tal_id": "tal-current",
            "tal_label": "Current Territories",
            "territory_count": 2,
            "is_active": False,
            "render_role": "reference",
        },
        {
            "tal_id": "tal-other",
            "territory_count": 1,
            "is_active": True,
            "render_role": "active",
        },
    ]

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


def test_render_payload_route_includes_point_layer_contract_for_browser():
    ts = sample_ts()
    ts["properties"]["point_layers"] = [
        {
            "point_layer": "accounts",
            "label": "Accounts",
            "style": {"color": "#ff7a00"},
            "classification": {
                "field": "segment",
                "classes": [{"value": "A", "label": "A", "color": "#00d4aa"}],
            },
        }
    ]
    ts["features"].append(
        {
            "type": "Feature",
            "properties": {
                "feature_kind": "point",
                "point_layer": "accounts",
                "account_id": "acct-1",
                "segment": "A",
            },
            "geometry": {"type": "Point", "coordinates": [-95, 36]},
        }
    )
    app = build_app(ServerConfig(map_visualization={"public_base_url": "https://expertpack.ai/mcp"}))
    state = app.state.ezt_state
    created = state.map_sessions.create_or_update_session(
        {"ts": ts, "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )
    session = created.session

    with TestClient(app) as client:
        response = client.get(f"/maps/session/{session.map_session_id}/{session.token}/render-payload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["point_layers"][0]["point_layer"] == "accounts"
    assert payload["point_layers"][0]["classification"]["classes"][0]["label"] == "A"
    assert payload["point_geojson"]["features"][0]["properties"]["account_id"] == "acct-1"

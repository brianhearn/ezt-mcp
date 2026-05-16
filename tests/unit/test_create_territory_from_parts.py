from __future__ import annotations

import time

from tests.fixtures.synthetic_geometry import grid_square_geometries
from starlette.testclient import TestClient

from ezt_mcp.config import ServerConfig
from ezt_mcp.server import build_app


class FakePartsRepository:
    async def fetch_part_geometries(self, part_layer: str, part_ids: list[str]):
        return grid_square_geometries(part_ids, as_geojson=True)


def test_create_territory_from_parts_http_submits_and_completes_direct_build_job():
    app = build_app(ServerConfig())
    app.state.ezt_state.parts_repo = FakePartsRepository()

    with TestClient(app) as client:
        response = client.post(
            "/create-territory-from-parts",
            json={
                "part_layer": "us_zips",
                "part_ids": ["32301", "32303", "32301"],
                "territory_name": "North Florida",
                "territory_path": ["East", "Southeast"],
                "tal_id": "tal-selected-north-florida",
                "conflict_policy": "move_from_existing",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        job_id = payload["result"]["job_id"]
        assert payload["result"]["tool_name"] == "create_territory_from_parts"

        status_payload = _wait_for_job(client, job_id)
        assert status_payload["status"] == "completed"

        result_response = client.get(f"/jobs/{job_id}/result")
        assert result_response.status_code == 200
        result = result_response.json()
        assert result["ok"] is True
        assert result["result"]["territory_count"] == 3
        assert result["result"]["tal_id"] == "tal-selected-north-florida"


def _wait_for_job(client: TestClient, job_id: str, *, timeout_seconds: float = 2.0):
    deadline = time.monotonic() + timeout_seconds
    last_payload = None
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}/status")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] in {"completed", "failed", "cancelled", "expired"}:
            return last_payload
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish; last status: {last_payload}")

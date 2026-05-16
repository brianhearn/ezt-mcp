from __future__ import annotations

import time

from tests.fixtures.synthetic_geometry import grid_square_geometries
from starlette.testclient import TestClient

from ezt_mcp.config import ServerConfig
from ezt_mcp.server import build_app


class FakePartsRepository:
    async def fetch_part_geometries(self, part_layer: str, part_ids: list[str]):
        return grid_square_geometries(part_ids, as_geojson=True)


def test_direct_build_http_submits_job_and_result_resource_returns_payload():
    app = build_app(ServerConfig())
    app.state.ezt_state.parts_repo = FakePartsRepository()

    with TestClient(app) as client:
        response = client.post(
            "/direct-build",
            json={
                "part_layer": "us_zips",
                "tal_label": "Test TAL",
                "assignments": [
                    {"part_id": "A", "territory_path": ["North"]},
                    {"part_id": "B", "territory_path": ["South"]},
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        job_id = payload["result"]["job_id"]

        status_payload = _wait_for_job(client, job_id)
        assert status_payload["status"] == "completed"

        result_response = client.get(f"/jobs/{job_id}/result")
        assert result_response.status_code == 200
        result = result_response.json()
        assert result["ok"] is True
        assert result["result"]["territory_count"] == 2


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

from __future__ import annotations

from starlette.testclient import TestClient

from ezt_mcp.config import ServerConfig
from ezt_mcp.jobs import CustomerContext
from ezt_mcp.server import build_app


def test_http_job_status_result_cancel_routes_use_dev_job_context_without_db():
    app = build_app(ServerConfig())
    repo = app.state.ezt_state.jobs_repo
    context = CustomerContext(customer_id="00000000-0000-0000-0000-000000000001")
    job = repo.submit(context, tool_name="direct_build")

    with TestClient(app) as client:
        status_response = client.get(f"/jobs/{job.job_id}/status")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "queued"

        result_response = client.get(f"/jobs/{job.job_id}/result")
        assert result_response.status_code == 409
        assert result_response.json()["error"]["code"] == "INVALID_JOB_STATE"

        cancel_response = client.post(f"/jobs/{job.job_id}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["result"]["status"] == "cancelled"

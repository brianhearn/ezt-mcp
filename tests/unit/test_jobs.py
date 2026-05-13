from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ezt_mcp.jobs import (
    CustomerContext,
    InMemoryJobRepository,
    InvalidJobTransitionError,
    JobAccessError,
    submission_response,
)


def test_submit_returns_schema_compatible_job_reference():
    repo = InMemoryJobRepository()
    context = CustomerContext(customer_id="cust-a", key_id="key-a")
    now = datetime(2026, 5, 13, 20, 0, tzinfo=UTC)

    job = repo.submit(context, tool_name="direct_build", now=now)
    payload = submission_response(job)

    assert payload["ok"] is True
    result = payload["result"]
    assert result["job_id"].startswith("job_")
    assert result["tool_name"] == "direct_build"
    assert result["status"] == "queued"
    assert result["phase"] == "queued"
    assert result["status_resource_uri"] == f"ezt://jobs/{job.job_id}/status"
    assert result["result_resource_uri"] == f"ezt://jobs/{job.job_id}/result"
    assert result["poll_interval_ms"] == 2000
    assert result["created_at"] == "2026-05-13T20:00:00Z"


def test_customer_isolation_blocks_cross_customer_status_and_result():
    repo = InMemoryJobRepository()
    cust_a = CustomerContext(customer_id="cust-a")
    cust_b = CustomerContext(customer_id="cust-b")
    job = repo.submit(cust_a, tool_name="direct_build")

    with pytest.raises(JobAccessError):
        repo.get(cust_b, job.job_id)

    repo.complete(cust_a, job.job_id, result={"ok": True, "result": {"value": 1}})
    with pytest.raises(JobAccessError):
        repo.get(cust_b, job.job_id).result_resource()


def test_progress_is_monotonic_and_status_resource_is_safe_summary():
    repo = InMemoryJobRepository()
    context = CustomerContext(customer_id="cust-a")
    job = repo.submit(context, tool_name="direct_build")

    repo.update_progress(
        context,
        job.job_id,
        status="running",
        phase="fetching_part_geometries",
        progress=20,
        total=100,
        counts={"part_count": 42},
    )
    repo.update_progress(context, job.job_id, progress=10)
    status = repo.get(context, job.job_id).status_resource()

    assert status["status"] == "running"
    assert status["phase"] == "fetching_part_geometries"
    assert status["progress"] == 20
    assert status["counts"] == {"part_count": 42}
    assert "result" not in status


def test_awaiting_user_selection_reference_includes_required_input():
    repo = InMemoryJobRepository()
    context = CustomerContext(customer_id="cust-a")

    job = repo.submit(
        context,
        tool_name="direct_build",
        status="awaiting_user_selection",
        phase="awaiting_map_selection",
        required_input={
            "type": "map_selection",
            "part_layer": "us_zips",
            "context_tal_id": "tal-current",
        },
    )

    reference = job.reference()
    assert reference["status"] == "awaiting_user_selection"
    assert reference["required_input"] == {
        "type": "map_selection",
        "part_layer": "us_zips",
        "context_tal_id": "tal-current",
    }


def test_result_only_available_after_completion_and_terminal_update_blocked():
    repo = InMemoryJobRepository()
    context = CustomerContext(customer_id="cust-a")
    job = repo.submit(context, tool_name="direct_build")

    with pytest.raises(InvalidJobTransitionError):
        job.result_resource()

    repo.complete(context, job.job_id, result={"ok": True, "result": {"ts_handle": "ts_1"}})
    assert repo.get(context, job.job_id).result_resource() == {
        "ok": True,
        "result": {"ts_handle": "ts_1"},
    }

    with pytest.raises(InvalidJobTransitionError):
        repo.update_progress(context, job.job_id, phase="should_not_happen")


def test_job_expires_on_access_after_ttl():
    repo = InMemoryJobRepository()
    context = CustomerContext(customer_id="cust-a")
    now = datetime(2026, 5, 13, 20, 0, tzinfo=UTC)
    job = repo.submit(context, tool_name="direct_build", ttl_seconds=60, now=now)

    expired = repo.get(context, job.job_id, now=now + timedelta(seconds=61))

    assert expired.status == "expired"
    assert expired.status_resource()["status"] == "expired"


def test_cancel_marks_terminal_cancelled():
    repo = InMemoryJobRepository()
    context = CustomerContext(customer_id="cust-a")
    job = repo.submit(context, tool_name="direct_build")

    cancelled = repo.cancel(context, job.job_id)

    assert cancelled.status == "cancelled"
    assert cancelled.cancel_requested is True
    assert cancelled.status_resource()["phase"] == "cancelled"

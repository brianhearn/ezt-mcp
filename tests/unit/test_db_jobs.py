from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from ezt_mcp.db.jobs import AsyncpgJobRepository
from ezt_mcp.jobs import CustomerContext, InvalidJobTransitionError, JobAccessError


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConn:
    def __init__(self):
        self.jobs = {}
        self.events = []
        self.results = {}
        self.exec_calls = []

    def transaction(self):
        return FakeTransaction()

    async def execute(self, sql, *args):
        self.exec_calls.append((sql, args))
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert into transient.jobs"):
            job_id = args[0]
            self.jobs[job_id] = {
                "job_id": job_id,
                "customer_id": UUID(args[1]),
                "key_id": UUID(args[2]) if args[2] else None,
                "tool_name": args[3],
                "status": args[4],
                "phase": args[5],
                "status_message": args[6],
                "progress": 0,
                "total": None,
                "poll_interval_ms": args[7],
                "request_summary": __import__("json").loads(args[8]),
                "result_summary": {},
                "result_handle": None,
                "error": None,
                "cancel_requested": False,
                "started_at": None,
                "completed_at": None,
                "created_at": args[9],
                "last_progress_at": args[9],
                "expires_at": args[10],
            }
        elif normalized.startswith("insert into transient.job_events"):
            self.events.append(args)
        elif normalized.startswith("insert into transient.job_results"):
            self.results[args[0]] = {
                "result_handle": args[0],
                "job_id": args[1],
                "customer_id": UUID(args[2]),
                "payload_compressed": args[3],
            }
        elif normalized.startswith("update transient.jobs"):
            job = self.jobs[args[0]]
            if "set status = $3, phase = $4" in normalized:
                job.update(
                    {
                        "status": args[2],
                        "phase": args[3],
                        "progress": args[4],
                        "total": args[5],
                        "status_message": args[6],
                        "result_summary": __import__("json").loads(args[7]),
                        "started_at": args[8],
                        "last_progress_at": args[9],
                    }
                )
            elif "set status = 'completed'" in normalized:
                job.update(
                    {
                        "status": "completed",
                        "phase": "completed",
                        "progress": job["total"] if job["total"] is not None else max(job["progress"], 1),
                        "status_message": "Completed.",
                        "result_summary": __import__("json").loads(args[2]),
                        "result_handle": args[3],
                        "completed_at": args[4],
                        "last_progress_at": args[4],
                    }
                )
            elif "set status = 'expired'" in normalized:
                job.update({"status": "expired", "phase": "expired", "completed_at": args[2], "last_progress_at": args[2]})
            elif "set status = 'failed'" in normalized:
                job.update({"status": "failed", "phase": "failed", "error": __import__("json").loads(args[2]), "completed_at": args[3], "last_progress_at": args[3]})
            elif "set cancel_requested = true" in normalized:
                job.update({"cancel_requested": True, "status": "cancelled", "phase": "cancelled", "status_message": "Cancelled.", "completed_at": args[2], "last_progress_at": args[2]})
        return "OK"

    async def fetchrow(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if "from transient.jobs" in normalized:
            job = self.jobs.get(args[0])
            if job is None or str(job["customer_id"]) != args[1]:
                return None
            return dict(job)
        if "from transient.job_results" in normalized:
            result = self.results.get(args[0])
            if result and result["job_id"] == args[1] and str(result["customer_id"]) == args[2]:
                return result
            return None
        return None

    async def fetchval(self, sql, *args):
        if "from transient.job_events" in sql:
            return len([event for event in self.events if event[1] == args[0] and event[2] == args[1]]) + 1
        return None


def _repo():
    conn = FakeConn()
    return AsyncpgJobRepository(FakePool(conn)), conn


def test_asyncpg_job_repo_submit_and_progress_and_result_roundtrip():
    repo, conn = _repo()
    context = CustomerContext(
        customer_id="11111111-1111-1111-1111-111111111111",
        key_id="22222222-2222-2222-2222-222222222222",
    )
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)

    job = asyncio.run(repo.submit(context, tool_name="direct_build", now=now))
    assert job.status == "queued"
    assert len(conn.events) == 1

    updated = asyncio.run(
        repo.update_progress(
            context,
            job.job_id,
            status="running",
            phase="fetching_part_geometries",
            progress=20,
            total=100,
            counts={"part_count": 3},
            now=now + timedelta(seconds=1),
        )
    )
    assert updated.status == "running"
    assert updated.progress == 20
    assert updated.counts == {"part_count": 3}

    completed = asyncio.run(
        repo.complete(
            context,
            job.job_id,
            result={"ok": True, "result": {"ts_handle": "ts_1"}},
            now=now + timedelta(seconds=2),
        )
    )
    assert completed.status == "completed"
    result = asyncio.run(repo.result_resource(context, job.job_id))
    assert result == {"ok": True, "result": {"ts_handle": "ts_1"}}


def test_asyncpg_job_repo_customer_isolation_and_terminal_guard():
    repo, _conn = _repo()
    cust_a = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    cust_b = CustomerContext(customer_id="33333333-3333-3333-3333-333333333333")
    job = asyncio.run(repo.submit(cust_a, tool_name="direct_build"))

    with pytest.raises(JobAccessError):
        asyncio.run(repo.get(cust_b, job.job_id))

    asyncio.run(repo.cancel(cust_a, job.job_id))
    with pytest.raises(InvalidJobTransitionError):
        asyncio.run(repo.update_progress(cust_a, job.job_id, phase="too_late"))


def test_asyncpg_job_repo_expiry_on_access():
    repo, _conn = _repo()
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)
    job = asyncio.run(repo.submit(context, tool_name="direct_build", ttl_seconds=60, now=now))

    expired = asyncio.run(repo.get(context, job.job_id, now=now + timedelta(seconds=61)))

    assert expired.status == "expired"

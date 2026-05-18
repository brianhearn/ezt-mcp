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
    def __init__(self, *, migration_003: bool = True):
        self.migration_003 = migration_003
        self.jobs = {}
        self.events = []
        self.results = {}
        self.payloads = {}
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
                "attempt_count": 0,
                "max_attempts": args[11] if len(args) > 11 else 3,
                "next_attempt_at": None,
                "payload_handle": args[12] if len(args) > 12 else None,
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
        elif normalized.startswith("insert into transient.job_payloads"):
            self.payloads[args[0]] = {
                "payload_handle": args[0],
                "job_id": args[1],
                "customer_id": UUID(args[2]),
                "payload_compressed": args[3],
            }
        elif normalized.startswith("insert into transient.job_results"):
            self.results[args[0]] = {
                "result_handle": args[0],
                "job_id": args[1],
                "customer_id": UUID(args[2]),
                "payload_compressed": args[3],
            }
        elif normalized.startswith("update transient.jobs"):
            if "where status not in" in normalized:
                for job in self.jobs.values():
                    if job["status"] not in {"completed", "failed", "cancelled", "expired"} and job["expires_at"] < args[0]:
                        job.update({"status": "expired", "phase": "expired", "completed_at": args[0], "last_progress_at": args[0]})
                return "UPDATE 1"
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
            elif "leased_by = $3" in normalized:
                was_running = job["status"] == "running"
                phase = job["phase"] if job["status"] == "queued" else "reclaimed"
                job.update({
                    "status": "running",
                    "phase": phase,
                    "leased_by": args[2],
                    "lease_expires_at": args[3],
                    "started_at": job.get("started_at") or args[4],
                    "last_progress_at": args[4],
                    "attempt_count": job.get("attempt_count", 0) + (1 if was_running else 0),
                    "next_attempt_at": args[5] if len(args) > 5 else None,
                })
            elif "set status = 'failed'" in normalized:
                job.update({"status": "failed", "phase": "failed", "error": __import__("json").loads(args[2]), "completed_at": args[3], "last_progress_at": args[3]})
            elif "set cancel_requested = true" in normalized:
                job.update({"cancel_requested": True, "status": "cancelled", "phase": "cancelled", "status_message": "Cancelled.", "completed_at": args[2], "last_progress_at": args[2]})
        elif normalized.startswith("delete from transient.job_payloads"):
            expired = [key for key, payload in self.payloads.items() if self.jobs[payload["job_id"]]["expires_at"] < args[0]]
            for key in expired:
                del self.payloads[key]
            return f"DELETE {len(expired)}"
        elif normalized.startswith("delete from transient.job_results"):
            expired = [key for key, result in self.results.items() if self.jobs[result["job_id"]]["expires_at"] < args[0]]
            for key in expired:
                del self.results[key]
            return f"DELETE {len(expired)}"
        elif normalized.startswith("delete from transient.jobs"):
            expired = [
                key
                for key, job in self.jobs.items()
                if job["status"] in {"completed", "failed", "cancelled", "expired"}
                and job["expires_at"] < args[0]
            ]
            for key in expired:
                del self.jobs[key]
            return f"DELETE {len(expired)}"
        return "OK"

    async def fetchrow(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if "information_schema.tables" in normalized and "information_schema.columns" in normalized:
            return {
                "job_payloads": self.migration_003,
                "jobs_attempt_count": self.migration_003,
                "jobs_max_attempts": self.migration_003,
                "jobs_next_attempt_at": self.migration_003,
                "jobs_payload_handle": self.migration_003,
            }
        if normalized.startswith("select * from transient.jobs") and "for update skip locked" in normalized:
            candidates = [
                job for job in self.jobs.values()
                if str(job["customer_id"]) == args[0]
                and (
                    job["status"] == "queued"
                    or (
                        job["status"] == "running"
                        and job.get("lease_expires_at") is not None
                        and job["lease_expires_at"] <= args[1]
                        and (job.get("next_attempt_at") is None or job["next_attempt_at"] <= args[1])
                    )
                )
                and job["expires_at"] > args[1]
                and (args[2] is None or job["tool_name"] in args[2])
            ]
            candidates.sort(key=lambda item: item["created_at"])
            return dict(candidates[0]) if candidates else None
        if normalized.startswith("select request_summary from transient.jobs"):
            job = self.jobs.get(args[0])
            if job is None or str(job["customer_id"]) != args[1]:
                return None
            return {"request_summary": job.get("request_summary")}
        if "from transient.jobs" in normalized:
            job = self.jobs.get(args[0])
            if job is None or str(job["customer_id"]) != args[1]:
                return None
            return dict(job)
        if "from transient.job_payloads" in normalized:
            payload = self.payloads.get(args[0])
            if payload and payload["job_id"] == args[1] and str(payload["customer_id"]) == args[2]:
                return payload
            return None
        if "from transient.job_results" in normalized:
            result = self.results.get(args[0])
            if result and result["job_id"] == args[1] and str(result["customer_id"]) == args[2]:
                return result
            return None
        return None

    async def fetchval(self, sql, *args):
        normalized = " ".join(sql.split()).lower()
        if "from transient.job_events" in sql:
            return len([event for event in self.events if event[1] == args[0] and event[2] == args[1]]) + 1
        if "count(*)" in normalized and "from transient.jobs" in normalized:
            if "status = 'queued'" in normalized and "tool_name = $2" in normalized:
                return len([job for job in self.jobs.values() if str(job["customer_id"]) == args[0] and job["status"] == "queued" and job["tool_name"] == args[1]])
            return len([job for job in self.jobs.values() if str(job["customer_id"]) == args[0] and job["status"] in {"queued", "running", "input_required", "awaiting_user_selection"}])
        return None


def _repo(*, migration_003: bool = True):
    conn = FakeConn(migration_003=migration_003)
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


def test_asyncpg_job_repo_claim_next_returns_oldest_matching_queued_job():
    repo, conn = _repo()
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)
    first = asyncio.run(repo.submit(context, tool_name="direct_build", now=now))
    asyncio.run(repo.submit(context, tool_name="other_tool", now=now + timedelta(seconds=1)))

    claimed = asyncio.run(
        repo.claim_next(
            context,
            worker_id="worker-1",
            tool_names=["direct_build"],
            now=now + timedelta(seconds=2),
        )
    )

    assert claimed is not None
    assert claimed.job_id == first.job_id
    stored = conn.jobs[first.job_id]
    assert stored["status"] == "running"
    assert stored["leased_by"] == "worker-1"


def test_asyncpg_job_repo_claim_next_reclaims_stale_running_job():
    repo, conn = _repo()
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)
    job = asyncio.run(repo.submit(context, tool_name="direct_build", now=now))
    conn.jobs[job.job_id].update(
        {
            "status": "running",
            "phase": "dissolve",
            "started_at": now,
            "leased_by": "worker-dead",
            "lease_expires_at": now + timedelta(seconds=30),
        }
    )

    not_claimed = asyncio.run(
        repo.claim_next(
            context,
            worker_id="worker-2",
            tool_names=["direct_build"],
            now=now + timedelta(seconds=29),
        )
    )
    assert not_claimed is None

    claimed = asyncio.run(
        repo.claim_next(
            context,
            worker_id="worker-2",
            tool_names=["direct_build"],
            now=now + timedelta(seconds=31),
        )
    )

    assert claimed is not None
    assert claimed.job_id == job.job_id
    stored = conn.jobs[job.job_id]
    assert stored["status"] == "running"
    assert stored["phase"] == "reclaimed"
    assert stored["leased_by"] == "worker-2"


def test_asyncpg_job_repo_stores_request_payload_outside_request_summary():
    repo, conn = _repo()
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)

    job = asyncio.run(
        repo.submit(
            context,
            tool_name="direct_build",
            request_payload={"part_layer": "us_zips", "assignments": [{"part_id": "A"}]},
            now=now,
        )
    )

    stored = conn.jobs[job.job_id]
    # updated for hardened path (no longer puts request_payload in summary)
    assert "request_payload" not in stored["request_summary"]
    payload_handle = stored["request_summary"]["payload_handle"]
    assert payload_handle in conn.payloads
    hydrated = asyncio.run(repo.get(context, job.job_id))
    assert hydrated.request_payload == {"part_layer": "us_zips", "assignments": [{"part_id": "A"}]}


def test_asyncpg_job_repo_enforces_active_job_limit():
    repo = AsyncpgJobRepository(FakePool(FakeConn()), max_active_jobs_per_customer=1)
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    asyncio.run(repo.submit(context, tool_name="direct_build"))

    with pytest.raises(Exception) as exc:
        asyncio.run(repo.submit(context, tool_name="direct_build"))

    assert getattr(exc.value, "code", None) == "JOB_LIMIT_EXCEEDED"
    assert getattr(exc.value, "limit_name", None) == "max_active_jobs_per_customer"


def test_asyncpg_job_repo_reclaim_honors_backoff_and_attempt_limit():
    repo = AsyncpgJobRepository(
        FakePool(FakeConn()),
        default_max_attempts=2,
        retry_backoff_seconds=60,
    )
    conn = repo._pool.conn
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)
    job = asyncio.run(repo.submit(context, tool_name="direct_build", now=now, max_attempts=2))
    conn.jobs[job.job_id].update(
        {
            "status": "running",
            "phase": "dissolve",
            "started_at": now,
            "leased_by": "worker-dead",
            "lease_expires_at": now + timedelta(seconds=30),
            "attempt_count": 0,
            "max_attempts": 2,
        }
    )

    claimed = asyncio.run(
        repo.claim_next(
            context,
            worker_id="worker-2",
            tool_names=["direct_build"],
            now=now + timedelta(seconds=31),
        )
    )
    assert claimed is not None
    assert claimed.attempt_count == 1
    assert conn.jobs[job.job_id]["next_attempt_at"] == now + timedelta(seconds=31 + 60)

    conn.jobs[job.job_id].update(
        {
            "status": "running",
            "lease_expires_at": now + timedelta(seconds=40),
            "attempt_count": 2,
            "max_attempts": 2,
            "next_attempt_at": now + timedelta(seconds=41),
        }
    )
    exhausted = asyncio.run(
        repo.claim_next(
            context,
            worker_id="worker-3",
            tool_names=["direct_build"],
            now=now + timedelta(seconds=120),
        )
    )
    assert exhausted is None
    assert conn.jobs[job.job_id]["status"] == "failed"
    assert conn.jobs[job.job_id]["error"]["code"] == "JOB_ATTEMPTS_EXHAUSTED"


def test_asyncpg_job_repo_cleanup_expired_removes_transient_payloads_results_and_jobs():
    repo, conn = _repo()
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)
    old = asyncio.run(
        repo.submit(
            context,
            tool_name="direct_build",
            request_payload={"part_layer": "us_zips", "assignments": [{"part_id": "A"}]},
            ttl_seconds=60,
            now=now,
        )
    )
    asyncio.run(
        repo.complete(
            context,
            old.job_id,
            result={"ok": True, "result": {"tal_id": "tal-old"}},
            now=now + timedelta(seconds=10),
        )
    )
    active = asyncio.run(
        repo.submit(
            context,
            tool_name="direct_build",
            request_payload={"part_layer": "us_zips", "assignments": [{"part_id": "B"}]},
            now=now + timedelta(seconds=30),
        )
    )

    summary = asyncio.run(repo.cleanup_expired(now=now + timedelta(seconds=61)))

    assert summary == {
        "deleted_job_payloads": 1,
        "deleted_job_results": 1,
        "deleted_jobs": 1,
    }
    assert old.job_id not in conn.jobs
    assert active.job_id in conn.jobs
    assert len(conn.payloads) == 1
    assert len(conn.results) == 0


def test_asyncpg_job_repo_legacy_schema_stores_request_payload_in_summary_temporarily():
    repo, conn = _repo(migration_003=False)
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)

    job = asyncio.run(
        repo.submit(
            context,
            tool_name="direct_build",
            request_payload={"part_layer": "us_zips", "assignments": [{"part_id": "A"}]},
            now=now,
        )
    )

    stored = conn.jobs[job.job_id]
    # updated for hardened path (always uses job_payloads table)
    assert stored["payload_handle"] is not None
    assert "payload_storage" not in stored["request_summary"]
    assert "request_payload" not in stored["request_summary"]
    hydrated = asyncio.run(repo.get(context, job.job_id))
    assert hydrated.request_payload == {"part_layer": "us_zips", "assignments": [{"part_id": "A"}]}


def test_asyncpg_job_repo_legacy_schema_claims_only_queued_jobs_without_reclaim_columns():
    repo, conn = _repo(migration_003=False)
    context = CustomerContext(customer_id="11111111-1111-1111-1111-111111111111")
    now = datetime(2026, 5, 13, 21, 0, tzinfo=UTC)
    queued = asyncio.run(repo.submit(context, tool_name="direct_build", now=now))
    running = asyncio.run(repo.submit(context, tool_name="direct_build", now=now + timedelta(seconds=1)))
    conn.jobs[running.job_id].update(
        {
            "status": "running",
            "phase": "dissolve",
            "leased_by": "worker-dead",
            "lease_expires_at": now - timedelta(seconds=1),
        }
    )

    claimed = asyncio.run(
        repo.claim_next(
            context,
            worker_id="worker-legacy",
            tool_names=["direct_build"],
            now=now + timedelta(seconds=2),
        )
    )

    assert claimed is not None
    assert claimed.job_id == queued.job_id
    assert conn.jobs[queued.job_id]["status"] == "running"
    assert conn.jobs[running.job_id]["status"] == "running"
    assert conn.jobs[running.job_id]["leased_by"] == "worker-dead"

"""Postgres-backed async job repository."""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping as MappingABC
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from ezt_mcp.jobs import (
    DEFAULT_JOB_TTL_SECONDS,
    DEFAULT_POLL_INTERVAL_MS,
    TERMINAL_STATUSES,
    CustomerContext,
    InvalidJobTransitionError,
    JobAccessError,
    JobRecord,
    JobStatus,
    _bounded_ttl,
)


class AsyncpgJobRepository:
    """Persist async job control-plane state in ``transient`` tables."""

    def __init__(self, pool: Any):
        self._pool = pool

    async def submit(
        self,
        context: CustomerContext,
        *,
        tool_name: str,
        phase: str = "queued",
        status: JobStatus = "queued",
        status_message: str | None = None,
        required_input: Mapping[str, Any] | None = None,
        request_payload: Mapping[str, Any] | None = None,
        ttl_seconds: int = DEFAULT_JOB_TTL_SECONDS,
        now: datetime | None = None,
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        job_id = f"job_{secrets.token_urlsafe(18)}"
        expires_at = now + timedelta(seconds=_bounded_ttl(ttl_seconds))
        request_summary = {}
        if required_input:
            request_summary["required_input"] = dict(required_input)
        if request_payload:
            request_summary["request_payload"] = dict(request_payload)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    insert into transient.jobs (
                      job_id, customer_id, key_id, tool_name, status, phase,
                      status_message, progress, total, poll_interval_ms,
                      request_summary, created_at, last_progress_at, expires_at
                    ) values (
                      $1, $2::uuid, $3::uuid, $4, $5, $6,
                      $7, 0, null, $8,
                      $9::jsonb, $10, $10, $11
                    )
                    """,
                    job_id,
                    context.customer_id,
                    context.key_id,
                    tool_name,
                    status,
                    phase,
                    status_message,
                    DEFAULT_POLL_INTERVAL_MS,
                    json.dumps(request_summary),
                    now,
                    expires_at,
                )
                await _insert_event(
                    conn,
                    job_id=job_id,
                    customer_id=context.customer_id,
                    event_type="phase",
                    phase=phase,
                    progress=0,
                    total=None,
                    message=status_message,
                    details=request_summary,
                    created_at=now,
                )
        return JobRecord(
            job_id=job_id,
            customer_id=context.customer_id,
            key_id=context.key_id,
            tool_name=tool_name,
            status=status,
            phase=phase,
            progress=0,
            status_message=status_message,
            required_input=dict(required_input) if required_input else None,
            request_payload=dict(request_payload) if request_payload else None,
            created_at=now,
            last_progress_at=now,
            expires_at=expires_at,
        )


    async def claim_next(
        self,
        context: CustomerContext,
        *,
        worker_id: str,
        tool_names: list[str] | None = None,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> JobRecord | None:
        """Atomically claim the next queued job for a background worker."""
        now = now or datetime.now(tz=UTC)
        lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    select *
                    from transient.jobs
                    where customer_id = $1::uuid
                      and (
                        status = 'queued'
                        or (status = 'running' and lease_expires_at is not null and lease_expires_at <= $2)
                      )
                      and expires_at > $2
                      and ($3::text[] is null or tool_name = any($3::text[]))
                    order by priority asc, created_at asc
                    for update skip locked
                    limit 1
                    """,
                    context.customer_id,
                    now,
                    tool_names,
                )
                if row is None:
                    return None
                job = _row_to_job(row)
                claim_message = (
                    "Stale running job reclaimed by worker."
                    if job.status == "running"
                    else "Job claimed by worker."
                )
                await conn.execute(
                    """
                    update transient.jobs
                    set status = 'running', phase = case when status = 'queued' then phase else 'reclaimed' end,
                        leased_by = $3, lease_expires_at = $4, started_at = coalesce(started_at, $5),
                        last_progress_at = $5
                    where job_id = $1 and customer_id = $2::uuid
                    """,
                    job.job_id,
                    context.customer_id,
                    worker_id,
                    lease_expires_at,
                    now,
                )
                await _insert_event(
                    conn,
                    job_id=job.job_id,
                    customer_id=context.customer_id,
                    event_type="phase",
                    phase=job.phase,
                    progress=job.progress,
                    total=job.total,
                    message=claim_message,
                    details={"worker_id": worker_id},
                    created_at=now,
                )
                return job

    async def get(
        self, context: CustomerContext, job_id: str, *, now: datetime | None = None
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select *
                from transient.jobs
                where job_id = $1 and customer_id = $2::uuid
                """,
                job_id,
                context.customer_id,
            )
            if row is None:
                raise JobAccessError(job_id)
            job = _row_to_job(row)
            if job.status not in TERMINAL_STATUSES and now >= job.expires_at:
                await conn.execute(
                    """
                    update transient.jobs
                    set status = 'expired', phase = 'expired', completed_at = $3,
                        last_progress_at = $3
                    where job_id = $1 and customer_id = $2::uuid
                    """,
                    job_id,
                    context.customer_id,
                    now,
                )
                job.status = "expired"
                job.phase = "expired"
                job.completed_at = now
                job.last_progress_at = now
            return job

    async def update_progress(
        self,
        context: CustomerContext,
        job_id: str,
        *,
        status: JobStatus | None = None,
        phase: str | None = None,
        progress: float | None = None,
        total: float | None = None,
        status_message: str | None = None,
        counts: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await _fetch_job_for_update(conn, context, job_id)
                job = _row_to_job(row)
                if job.status in TERMINAL_STATUSES:
                    raise InvalidJobTransitionError(
                        "Terminal jobs cannot be updated.", job_id=job.job_id, status=job.status
                    )
                new_status = status or job.status
                new_phase = phase or job.phase
                new_progress = max(job.progress, float(progress)) if progress is not None else job.progress
                new_total = float(total) if total is not None else job.total
                new_message = status_message if status_message is not None else job.status_message
                new_counts = dict(counts) if counts is not None else job.counts
                started_at = job.started_at
                if new_status == "running" and started_at is None:
                    started_at = now

                await conn.execute(
                    """
                    update transient.jobs
                    set status = $3, phase = $4, progress = $5, total = $6,
                        status_message = $7, result_summary = $8::jsonb,
                        started_at = $9, last_progress_at = $10
                    where job_id = $1 and customer_id = $2::uuid
                    """,
                    job_id,
                    context.customer_id,
                    new_status,
                    new_phase,
                    new_progress,
                    new_total,
                    new_message,
                    json.dumps({"counts": new_counts}),
                    started_at,
                    now,
                )
                await _insert_event(
                    conn,
                    job_id=job_id,
                    customer_id=context.customer_id,
                    event_type="progress",
                    phase=new_phase,
                    progress=new_progress,
                    total=new_total,
                    message=new_message,
                    details={"counts": new_counts},
                    created_at=now,
                )
        return await self.get(context, job_id, now=now)

    async def complete(
        self,
        context: CustomerContext,
        job_id: str,
        *,
        result: Mapping[str, Any],
        now: datetime | None = None,
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await _fetch_job_for_update(conn, context, job_id)
                job = _row_to_job(row)
                if job.status in TERMINAL_STATUSES:
                    raise InvalidJobTransitionError(
                        "Terminal jobs cannot be completed again.", job_id=job.job_id, status=job.status
                    )
                result_handle = f"jres_{secrets.token_urlsafe(18)}"
                payload = json.dumps(dict(result)).encode("utf-8")
                await conn.execute(
                    """
                    insert into transient.job_results (
                      result_handle, job_id, customer_id, content_type,
                      payload_compressed, payload_bytes, created_at, expires_at
                    ) values ($1, $2, $3::uuid, 'application/json', $4, $5, $6, $7)
                    """,
                    result_handle,
                    job_id,
                    context.customer_id,
                    payload,
                    len(payload),
                    now,
                    job.expires_at,
                )
                await conn.execute(
                    """
                    update transient.jobs
                    set status = 'completed', phase = 'completed', progress = coalesce(total, greatest(progress, 1)),
                        status_message = 'Completed.', result_summary = $3::jsonb,
                        result_handle = $4, completed_at = $5, last_progress_at = $5
                    where job_id = $1 and customer_id = $2::uuid
                    """,
                    job_id,
                    context.customer_id,
                    json.dumps({"result_handle": result_handle}),
                    result_handle,
                    now,
                )
                await _insert_event(
                    conn,
                    job_id=job_id,
                    customer_id=context.customer_id,
                    event_type="result",
                    phase="completed",
                    progress=job.total if job.total is not None else max(job.progress, 1),
                    total=job.total,
                    message="Completed.",
                    details={"result_handle": result_handle},
                    created_at=now,
                )
        return await self.get(context, job_id, now=now)

    async def result_resource(
        self, context: CustomerContext, job_id: str, *, now: datetime | None = None
    ) -> dict[str, Any]:
        job = await self.get(context, job_id, now=now)
        if job.status != "completed" or not job.result:
            raise InvalidJobTransitionError(
                "Job result is only available after completion.",
                job_id=job.job_id,
                status=job.status,
            )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                select payload_compressed
                from transient.job_results
                where result_handle = $1 and job_id = $2 and customer_id = $3::uuid
                """,
                job.result["result_handle"],
                job_id,
                context.customer_id,
            )
            if row is None:
                raise InvalidJobTransitionError(
                    "Job result payload is unavailable.", job_id=job.job_id, status=job.status
                )
            return json.loads(bytes(row["payload_compressed"]).decode("utf-8"))

    async def fail(
        self,
        context: CustomerContext,
        job_id: str,
        *,
        error: Mapping[str, Any],
        now: datetime | None = None,
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                update transient.jobs
                set status = 'failed', phase = 'failed', error = $3::jsonb,
                    completed_at = $4, last_progress_at = $4
                where job_id = $1 and customer_id = $2::uuid
                """,
                job_id,
                context.customer_id,
                json.dumps(dict(error)),
                now,
            )
            await _insert_event(
                conn,
                job_id=job_id,
                customer_id=context.customer_id,
                event_type="error",
                phase="failed",
                progress=None,
                total=None,
                message=str(error.get("message") or "Job failed."),
                details=dict(error),
                created_at=now,
            )
        return await self.get(context, job_id, now=now)

    async def cancel(
        self, context: CustomerContext, job_id: str, *, now: datetime | None = None
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await _fetch_job_for_update(conn, context, job_id)
                job = _row_to_job(row)
                if job.status in TERMINAL_STATUSES:
                    return job
                await conn.execute(
                    """
                    update transient.jobs
                    set cancel_requested = true, status = 'cancelled', phase = 'cancelled',
                        status_message = 'Cancelled.', completed_at = $3, last_progress_at = $3
                    where job_id = $1 and customer_id = $2::uuid
                    """,
                    job_id,
                    context.customer_id,
                    now,
                )
                await _insert_event(
                    conn,
                    job_id=job_id,
                    customer_id=context.customer_id,
                    event_type="cancel",
                    phase="cancelled",
                    progress=job.progress,
                    total=job.total,
                    message="Cancelled.",
                    details={},
                    created_at=now,
                )
        return await self.get(context, job_id, now=now)


async def _fetch_job_for_update(conn: Any, context: CustomerContext, job_id: str) -> Any:
    row = await conn.fetchrow(
        """
        select *
        from transient.jobs
        where job_id = $1 and customer_id = $2::uuid
        for update
        """,
        job_id,
        context.customer_id,
    )
    if row is None:
        raise JobAccessError(job_id)
    return row


async def _insert_event(
    conn: Any,
    *,
    job_id: str,
    customer_id: str,
    event_type: str,
    phase: str | None,
    progress: float | None,
    total: float | None,
    message: str | None,
    details: Mapping[str, Any],
    created_at: datetime,
) -> None:
    sequence = await conn.fetchval(
        """
        select coalesce(max(sequence), 0) + 1
        from transient.job_events
        where job_id = $1 and customer_id = $2::uuid
        """,
        job_id,
        customer_id,
    )
    await conn.execute(
        """
        insert into transient.job_events (
          event_id, job_id, customer_id, sequence, event_type, phase,
          progress, total, message, details, created_at
        ) values ($1, $2, $3::uuid, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
        """,
        f"jevt_{secrets.token_urlsafe(18)}",
        job_id,
        customer_id,
        sequence,
        event_type,
        phase,
        progress,
        total,
        message,
        json.dumps(dict(details)),
        created_at,
    )


def _row_to_job(row: Any) -> JobRecord:
    request_summary = _jsonb_to_dict(row["request_summary"])
    result_summary = _jsonb_to_dict(row["result_summary"])
    required_input = request_summary.get("required_input")
    request_payload = request_summary.get("request_payload")
    counts = result_summary.get("counts") or {}
    result = {"result_handle": row["result_handle"]} if row["result_handle"] else None
    return JobRecord(
        job_id=row["job_id"],
        customer_id=str(row["customer_id"]),
        key_id=str(row["key_id"]) if row["key_id"] else None,
        tool_name=row["tool_name"],
        status=row["status"],
        phase=row["phase"],
        progress=float(row["progress"]),
        total=float(row["total"]) if row["total"] is not None else None,
        status_message=row["status_message"],
        counts=dict(counts),
        poll_interval_ms=int(row["poll_interval_ms"]),
        required_input=dict(required_input) if isinstance(required_input, dict) else None,
        request_payload=dict(request_payload) if isinstance(request_payload, dict) else None,
        result=result,
        error=_jsonb_to_dict(row["error"]) if row["error"] else None,
        created_at=_as_utc(row["created_at"]),
        started_at=_as_utc(row["started_at"]),
        last_progress_at=_as_utc(row["last_progress_at"]),
        completed_at=_as_utc(row["completed_at"]),
        expires_at=_as_utc(row["expires_at"]),
        cancel_requested=bool(row["cancel_requested"]),
    )


def _jsonb_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        decoded = json.loads(value)
        return dict(decoded) if isinstance(decoded, MappingABC) else {}
    return dict(value) if isinstance(value, MappingABC) else {}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

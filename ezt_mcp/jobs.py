"""Async job control-plane primitives.

This module is intentionally storage-agnostic at the public API boundary. The
initial implementation uses an in-memory repository for unit-testable control
plane semantics; Postgres-backed persistence can replace it without changing the
MCP job resource contract.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Mapping

JobStatus = Literal[
    "queued",
    "running",
    "input_required",
    "awaiting_user_selection",
    "completed",
    "failed",
    "cancelled",
    "expired",
]

TERMINAL_STATUSES: set[str] = {"completed", "failed", "cancelled", "expired"}
DEFAULT_JOB_TTL_SECONDS = 3600
DEFAULT_POLL_INTERVAL_MS = 2000


class JobAccessError(PermissionError):
    """Raised when a caller cannot access a job."""

    def __init__(self, job_id: str):
        super().__init__("Job was not found for this customer.")
        self.job_id = job_id
        self.code = "UNKNOWN_JOB"


class InvalidJobTransitionError(ValueError):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, message: str, *, job_id: str, status: str):
        super().__init__(message)
        self.job_id = job_id
        self.status = status
        self.code = "INVALID_JOB_STATE"


class JobLimitExceededError(RuntimeError):
    """Raised when a customer exceeds configured transient job limits."""

    def __init__(self, message: str, *, limit_name: str, limit: int, current: int):
        super().__init__(message)
        self.limit_name = limit_name
        self.limit = limit
        self.current = current
        self.code = "JOB_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class CustomerContext:
    """Authenticated customer/key context used for job isolation checks."""

    customer_id: str
    key_id: str | None = None


@dataclass
class JobRecord:
    """Short-lived async job record."""

    job_id: str
    customer_id: str
    tool_name: str
    status: JobStatus
    phase: str
    progress: float
    created_at: datetime
    last_progress_at: datetime
    expires_at: datetime
    key_id: str | None = None
    total: float | None = None
    status_message: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
    required_input: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    request_payload: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancel_requested: bool = False
    attempt_count: int = 0
    max_attempts: int = 3
    leased_by: str | None = None
    lease_expires_at: datetime | None = None
    next_attempt_at: datetime | None = None

    def reference(self) -> dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "total": self.total,
            "status_message": self.status_message,
            "status_resource_uri": f"ezt://jobs/{self.job_id}/status",
            "result_resource_uri": f"ezt://jobs/{self.job_id}/result",
            "cancel_resource_uri": f"ezt://jobs/{self.job_id}/cancel",
            "poll_interval_ms": self.poll_interval_ms,
            "created_at": _isoformat_z(self.created_at),
            "expires_at": _isoformat_z(self.expires_at),
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
        }
        if self.required_input:
            payload["required_input"] = self.required_input
        return _drop_none(payload)

    def status_resource(self, *, now: datetime | None = None) -> dict[str, Any]:
        status = self._effective_status(now=now)
        payload = {
            "job_id": self.job_id,
            "tool_name": self.tool_name,
            "status": status,
            "phase": self.phase,
            "progress": self.progress,
            "total": self.total,
            "status_message": self.status_message,
            "counts": self.counts,
            "poll_interval_ms": self.poll_interval_ms,
            "result_resource_uri": f"ezt://jobs/{self.job_id}/result",
            "error": self.error,
            "created_at": _isoformat_z(self.created_at),
            "started_at": _isoformat_z(self.started_at),
            "last_progress_at": _isoformat_z(self.last_progress_at),
            "completed_at": _isoformat_z(self.completed_at),
            "expires_at": _isoformat_z(self.expires_at),
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "leased_by": self.leased_by,
            "lease_expires_at": _isoformat_z(self.lease_expires_at),
            "next_attempt_at": _isoformat_z(self.next_attempt_at),
        }
        if self.required_input:
            payload["required_input"] = self.required_input
        return _drop_none(payload)

    def result_resource(self, *, now: datetime | None = None) -> dict[str, Any]:
        status = self._effective_status(now=now)
        if status != "completed":
            raise InvalidJobTransitionError(
                "Job result is only available after completion.",
                job_id=self.job_id,
                status=status,
            )
        return self.result or {}

    def _effective_status(self, *, now: datetime | None = None) -> JobStatus:
        now = now or datetime.now(tz=UTC)
        if self.status not in TERMINAL_STATUSES and now >= self.expires_at:
            return "expired"
        return self.status


class InMemoryJobRepository:
    """Customer-scoped in-memory job repository for the v1 skeleton."""

    def __init__(
        self,
        *,
        max_queued_jobs_per_customer: int = 100,
        max_active_jobs_per_customer: int = 20,
        default_max_attempts: int = 3,
    ):
        self._jobs: dict[str, JobRecord] = {}
        self.max_queued_jobs_per_customer = max(1, int(max_queued_jobs_per_customer))
        self.max_active_jobs_per_customer = max(1, int(max_active_jobs_per_customer))
        self.default_max_attempts = max(1, int(default_max_attempts))

    def submit(
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
        max_attempts: int | None = None,
        now: datetime | None = None,
    ) -> JobRecord:
        now = now or datetime.now(tz=UTC)
        self._enforce_customer_limits(context, tool_name=tool_name)
        job = JobRecord(
            job_id=f"job_{secrets.token_urlsafe(18)}",
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
            expires_at=now + timedelta(seconds=_bounded_ttl(ttl_seconds)),
            max_attempts=max(1, int(max_attempts or self.default_max_attempts)),
        )
        self._jobs[job.job_id] = job
        return job

    def _enforce_customer_limits(self, context: CustomerContext, *, tool_name: str) -> None:
        active_count = sum(
            1
            for job in self._jobs.values()
            if job.customer_id == context.customer_id and job.status not in TERMINAL_STATUSES
        )
        if active_count >= self.max_active_jobs_per_customer:
            raise JobLimitExceededError(
                "Customer has too many active jobs.",
                limit_name="max_active_jobs_per_customer",
                limit=self.max_active_jobs_per_customer,
                current=active_count,
            )
        queued_count = sum(
            1
            for job in self._jobs.values()
            if job.customer_id == context.customer_id
            and job.status == "queued"
            and job.tool_name == tool_name
        )
        if queued_count >= self.max_queued_jobs_per_customer:
            raise JobLimitExceededError(
                "Customer has too many queued jobs for this tool.",
                limit_name="max_queued_jobs_per_customer",
                limit=self.max_queued_jobs_per_customer,
                current=queued_count,
            )

    def get(self, context: CustomerContext, job_id: str, *, now: datetime | None = None) -> JobRecord:
        job = self._jobs.get(job_id)
        if job is None or job.customer_id != context.customer_id:
            raise JobAccessError(job_id)
        effective = job._effective_status(now=now)
        if effective == "expired" and job.status != "expired":
            job.status = "expired"
            job.phase = "expired"
            job.completed_at = now or datetime.now(tz=UTC)
            job.last_progress_at = job.completed_at
        return job

    def update_progress(
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
        job = self.get(context, job_id, now=now)
        if job.status in TERMINAL_STATUSES:
            raise InvalidJobTransitionError(
                "Terminal jobs cannot be updated.", job_id=job.job_id, status=job.status
            )
        now = now or datetime.now(tz=UTC)
        if status is not None:
            job.status = status
            if status == "running" and job.started_at is None:
                job.started_at = now
        if phase is not None:
            job.phase = phase
        if progress is not None:
            job.progress = max(job.progress, float(progress))
        if total is not None:
            job.total = float(total)
        if status_message is not None:
            job.status_message = status_message
        if counts is not None:
            job.counts = dict(counts)
        job.last_progress_at = now
        return job

    def complete(
        self,
        context: CustomerContext,
        job_id: str,
        *,
        result: Mapping[str, Any],
        now: datetime | None = None,
    ) -> JobRecord:
        job = self.get(context, job_id, now=now)
        if job.status in TERMINAL_STATUSES:
            raise InvalidJobTransitionError(
                "Terminal jobs cannot be completed again.", job_id=job.job_id, status=job.status
            )
        now = now or datetime.now(tz=UTC)
        job.status = "completed"
        job.phase = "completed"
        job.progress = job.total if job.total is not None else max(job.progress, 1)
        job.status_message = "Completed."
        job.result = dict(result)
        job.completed_at = now
        job.last_progress_at = now
        return job

    def fail(
        self,
        context: CustomerContext,
        job_id: str,
        *,
        error: Mapping[str, Any],
        now: datetime | None = None,
    ) -> JobRecord:
        job = self.get(context, job_id, now=now)
        if job.status in TERMINAL_STATUSES:
            raise InvalidJobTransitionError(
                "Terminal jobs cannot be failed again.", job_id=job.job_id, status=job.status
            )
        now = now or datetime.now(tz=UTC)
        job.status = "failed"
        job.phase = "failed"
        job.error = dict(error)
        job.completed_at = now
        job.last_progress_at = now
        return job

    def cancel(self, context: CustomerContext, job_id: str, *, now: datetime | None = None) -> JobRecord:
        job = self.get(context, job_id, now=now)
        now = now or datetime.now(tz=UTC)
        if job.status in TERMINAL_STATUSES:
            return job
        job.cancel_requested = True
        job.status = "cancelled"
        job.phase = "cancelled"
        job.status_message = "Cancelled."
        job.completed_at = now
        job.last_progress_at = now
        return job


def submission_response(job: JobRecord) -> dict[str, Any]:
    """Return a schema-compatible successful job submission envelope."""
    return {"ok": True, "result": job.reference()}


def _bounded_ttl(value: Any) -> int:
    try:
        seconds = int(value or DEFAULT_JOB_TTL_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_JOB_TTL_SECONDS
    return max(60, min(seconds, 86400))


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _isoformat_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

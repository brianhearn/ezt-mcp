"""Background job worker loop for queued EZT MCP jobs."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from ezt_mcp.jobs import CustomerContext, TERMINAL_STATUSES
from ezt_mcp.territory.dissolve import DissolveOptions
from ezt_mcp.tools.direct_build_job import run_direct_build_job

logger = logging.getLogger(__name__)

ProgressPublisher = Callable[[str, str, str, int | None], Any]


class JobWorker:
    """Claim queued jobs from the shared job repository and execute them."""

    def __init__(
        self,
        *,
        context: CustomerContext,
        jobs_repo: Any,
        parts_repo: Any,
        dissolve_options: DissolveOptions | None = None,
        progress_publisher: ProgressPublisher | None = None,
        poll_interval_seconds: float = 0.25,
        cleanup_interval_seconds: float = 3600.0,
        worker_id: str | None = None,
    ) -> None:
        self.context = context
        self.jobs_repo = jobs_repo
        self.parts_repo = parts_repo
        self.dissolve_options = dissolve_options
        self.progress_publisher = progress_publisher
        self.poll_interval_seconds = poll_interval_seconds
        self.cleanup_interval_seconds = max(60.0, float(cleanup_interval_seconds))
        self.worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._next_cleanup_at = datetime.now(tz=UTC)
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        logger.info("EZT MCP job worker started", extra={"worker_id": self.worker_id})
        while not self._stopping.is_set():
            try:
                await self._cleanup_expired_if_due()
                job = await self._claim_next()
                if job is None:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self.poll_interval_seconds
                    )
                    continue
                await self._run_job(job)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("EZT MCP job worker loop error")
                await asyncio.sleep(self.poll_interval_seconds)
        logger.info("EZT MCP job worker stopped", extra={"worker_id": self.worker_id})

    async def _cleanup_expired_if_due(self) -> None:
        if not hasattr(self.jobs_repo, "cleanup_expired"):
            return
        now = datetime.now(tz=UTC)
        if now < self._next_cleanup_at:
            return
        self._next_cleanup_at = now + timedelta(seconds=self.cleanup_interval_seconds)
        try:
            summary = await _maybe_await(self.jobs_repo.cleanup_expired(now=now))
            logger.info(
                "EZT MCP expired transient job cleanup complete",
                extra={"worker_id": self.worker_id, "cleanup_summary": summary},
            )
        except Exception:  # noqa: BLE001
            logger.exception("EZT MCP expired transient job cleanup failed")

    async def _claim_next(self) -> Any | None:
        if hasattr(self.jobs_repo, "claim_next"):
            return await _maybe_await(
                self.jobs_repo.claim_next(
                    self.context,
                    worker_id=self.worker_id,
                    tool_names=["direct_build", "create_territory_from_parts"],
                )
            )

        # In-memory fallback for dev/tests: claim the first queued job in process.
        jobs = getattr(self.jobs_repo, "_jobs", {})
        for job in list(jobs.values()):
            if job.customer_id == self.context.customer_id and job.status == "queued":
                return job
        return None

    async def _run_job(self, job: Any) -> None:
        if getattr(job, "status", None) in TERMINAL_STATUSES:
            return
        request = getattr(job, "request_payload", None)
        if not isinstance(request, Mapping):
            await _maybe_await(
                self.jobs_repo.fail(
                    self.context,
                    job.job_id,
                    error={
                        "code": "INVALID_JOB_PAYLOAD",
                        "message": "Queued job is missing its request payload.",
                        "details": {"job_id": job.job_id, "tool_name": getattr(job, "tool_name", None)},
                        "retryable": False,
                        "user_action_required": False,
                    },
                )
            )
            return

        tool_name = getattr(job, "tool_name", "")
        if tool_name not in {"direct_build", "create_territory_from_parts"}:
            await _maybe_await(
                self.jobs_repo.fail(
                    self.context,
                    job.job_id,
                    error={
                        "code": "UNSUPPORTED_JOB_TOOL",
                        "message": f"No worker is registered for tool {tool_name}.",
                        "details": {"tool_name": tool_name},
                        "retryable": False,
                        "user_action_required": False,
                    },
                )
            )
            return

        await run_direct_build_job(
            context=self.context,
            job_id=job.job_id,
            request=request,
            parts_repo=self.parts_repo,
            jobs_repo=self.jobs_repo,
            dissolve_options=self.dissolve_options,
            progress_publisher=self.progress_publisher,
        )


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value

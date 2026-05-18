"""Async Direct Build job runner."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from collections.abc import Callable
from typing import Any, Protocol

from ezt_mcp.jobs import CustomerContext, InvalidJobTransitionError
from ezt_mcp.observability import timed_async_operation
from ezt_mcp.resources.part_layers import UnknownPartLayerError
from ezt_mcp.territory.dissolve import (
    DissolveOptions,
    DissolveValidationError,
    GeometryDissolveBackend,
)
from ezt_mcp.territory.hierarchy import HierarchyValidationError
from ezt_mcp.tools.direct_build import build_direct_tal
from ezt_mcp.tools.query_parts import QueryPartsError

logger = logging.getLogger(__name__)


class DirectBuildPartsRepository(Protocol):
    """Small repository contract needed by the Direct Build worker."""

    async def fetch_part_geometries(
        self,
        part_layer: str,
        part_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Return GeoJSON geometries keyed by public part ID."""


class DirectBuildJobRepository(Protocol):
    """Job repository methods used by the Direct Build worker."""

    def update_progress(self, context: CustomerContext, job_id: str, **kwargs: Any) -> Any: ...

    def complete(self, context: CustomerContext, job_id: str, **kwargs: Any) -> Any: ...

    def fail(self, context: CustomerContext, job_id: str, **kwargs: Any) -> Any: ...

    def get(self, context: CustomerContext, job_id: str, **kwargs: Any) -> Any: ...


async def run_direct_build_job(
    *,
    context: CustomerContext,
    job_id: str,
    request: Mapping[str, Any],
    parts_repo: DirectBuildPartsRepository,
    jobs_repo: DirectBuildJobRepository,
    backend: GeometryDissolveBackend | None = None,
    dissolve_options: DissolveOptions | None = None,
    progress_publisher: Callable[[str, str, str, int | None, str | None], Any] | None = None,
) -> dict[str, Any]:
    """Run Direct Build and persist progress/result into the job repository.

    The server submits this coroutine as a background task so MCP clients get an
    immediate job reference and poll ``ezt://jobs/{job_id}/status`` plus
    ``ezt://jobs/{job_id}/result`` for completion.
    """
    part_layer = str(request.get("part_layer") or "").strip()
    assignments = list(request.get("assignments") or [])
    part_ids = _assignment_part_ids(assignments)
    map_session_id = str(request.get("map_session_id") or "").strip()

    async with timed_async_operation(
        logger,
        "tools.direct_build.job",
        job_id=job_id,
        part_layer=part_layer,
        assignment_count=len(assignments),
        unique_part_count=len(part_ids),
    ):
        try:
            await _checkpoint_not_cancelled(
                jobs_repo,
                context,
                job_id,
                map_session_id=map_session_id,
                progress_publisher=progress_publisher,
            )
            await _publish_progress(
                progress_publisher, map_session_id, "running", "Fetching part geometries.", 10, job_id
            )
            await _maybe_await(
                jobs_repo.update_progress(
                    context,
                    job_id,
                    status="running",
                    phase="fetch_part_geometries",
                    progress=10,
                    total=100,
                    status_message="Fetching part geometries.",
                    counts={"assignment_count": len(assignments), "unique_part_count": len(part_ids)},
                )
            )
            await _checkpoint_not_cancelled(
                jobs_repo,
                context,
                job_id,
                map_session_id=map_session_id,
                progress_publisher=progress_publisher,
            )

            async with timed_async_operation(
                logger,
                "tools.direct_build.fetch_part_geometries",
                job_id=job_id,
                part_layer=part_layer,
                requested_part_count=len(part_ids),
            ):
                part_geometries = await _fetch_part_geometries_cooperatively(
                    parts_repo,
                    part_layer,
                    part_ids,
                    jobs_repo=jobs_repo,
                    context=context,
                    job_id=job_id,
                    map_session_id=map_session_id,
                    progress_publisher=progress_publisher,
                )

            await _checkpoint_not_cancelled(
                jobs_repo,
                context,
                job_id,
                map_session_id=map_session_id,
                progress_publisher=progress_publisher,
            )
            await _publish_progress(
                progress_publisher, map_session_id, "running", "Dissolving territory geometries.", 45, job_id
            )
            await _maybe_await(
                jobs_repo.update_progress(
                    context,
                    job_id,
                    phase="dissolve",
                    progress=45,
                    status_message="Dissolving territory geometries.",
                    counts={
                        "assignment_count": len(assignments),
                        "unique_part_count": len(part_ids),
                        "fetched_geometry_count": len(part_geometries),
                    },
                )
            )
            await _checkpoint_not_cancelled(
                jobs_repo,
                context,
                job_id,
                map_session_id=map_session_id,
                progress_publisher=progress_publisher,
            )

            result_payload = build_direct_tal(
                request,
                part_geometries,
                backend=backend,
                dissolve_options=dissolve_options,
            )

            await _checkpoint_not_cancelled(
                jobs_repo,
                context,
                job_id,
                map_session_id=map_session_id,
                progress_publisher=progress_publisher,
            )
            await _publish_progress(
                progress_publisher, map_session_id, "running", "Serializing Territory Solution result.", 90, job_id
            )
            await _maybe_await(
                jobs_repo.update_progress(
                    context,
                    job_id,
                    phase="serialize_result",
                    progress=90,
                    status_message="Serializing Territory Solution result.",
                    counts={
                        "assignment_count": len(assignments),
                        "unique_part_count": len(part_ids),
                        "fetched_geometry_count": len(part_geometries),
                        "territory_count": result_payload.get("result", {}).get("territory_count"),
                    },
                )
            )
            await _checkpoint_not_cancelled(
                jobs_repo,
                context,
                job_id,
                map_session_id=map_session_id,
                progress_publisher=progress_publisher,
            )
            await _maybe_await(jobs_repo.complete(context, job_id, result=result_payload))
            await _publish_progress(
                progress_publisher, map_session_id, "done", "Territory build complete.", 100, job_id
            )
            return result_payload
        except JobCancelledError as exc:
            await _publish_progress(
                progress_publisher, map_session_id, "cancelled", str(exc), None, job_id
            )
            return {"ok": False, "error": exc.to_error()}
        except InvalidJobTransitionError as exc:
            if exc.status == "cancelled":
                cancelled = JobCancelledError(job_id)
                await _publish_progress(
                    progress_publisher, map_session_id, "cancelled", str(cancelled), None, job_id
                )
                return {"ok": False, "error": cancelled.to_error()}
            raise
        except (HierarchyValidationError, DissolveValidationError, QueryPartsError, ValueError) as exc:
            error = _structured_error(exc)
            await _fail_if_not_terminal(jobs_repo, context, job_id, error=error)
            await _publish_progress(progress_publisher, map_session_id, "error", str(error.get("message") or "Territory build failed."), None, job_id)
            return {"ok": False, "error": error}
        except UnknownPartLayerError as exc:
            error = {
                "code": exc.code,
                "message": str(exc),
                "details": {"part_layer": exc.part_layer},
                "retryable": False,
                "user_action_required": True,
            }
            await _fail_if_not_terminal(jobs_repo, context, job_id, error=error)
            await _publish_progress(progress_publisher, map_session_id, "error", str(error.get("message") or "Territory build failed."), None, job_id)
            return {"ok": False, "error": error}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Direct Build job failed")
            error = {
                "code": "DIRECT_BUILD_FAILED",
                "message": "Direct Build failed unexpectedly.",
                "details": {"exception_type": exc.__class__.__name__},
                "retryable": False,
                "user_action_required": False,
            }
            await _fail_if_not_terminal(jobs_repo, context, job_id, error=error)
            await _publish_progress(progress_publisher, map_session_id, "error", error["message"], None, job_id)
            return {"ok": False, "error": error}


async def _publish_progress(
    publisher: Callable[[str, str, str, int | None, str | None], Any] | None,
    map_session_id: str,
    state: str,
    message: str,
    percent: int | None,
    job_id: str | None = None,
) -> None:
    if not publisher or not map_session_id:
        return
    try:
        await _maybe_await(publisher(map_session_id, state, message, percent, job_id))
    except Exception:  # noqa: BLE001
        logger.debug("Map progress publish failed", exc_info=True)


class JobCancelledError(RuntimeError):
    """Raised at cooperative cancellation checkpoints."""

    code = "JOB_CANCELLED"

    def __init__(self, job_id: str):
        super().__init__(f"Direct Build job {job_id} was cancelled.")
        self.job_id = job_id

    def to_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": {"job_id": self.job_id},
            "retryable": False,
            "user_action_required": False,
        }


async def _fetch_part_geometries_cooperatively(
    parts_repo: DirectBuildPartsRepository,
    part_layer: str,
    part_ids: list[str],
    *,
    jobs_repo: DirectBuildJobRepository,
    context: CustomerContext,
    job_id: str,
    map_session_id: str,
    progress_publisher: Callable[[str, str, str, int | None, str | None], Any] | None,
) -> dict[str, dict[str, Any]]:
    chunk_size = 500
    if len(part_ids) <= chunk_size:
        return await parts_repo.fetch_part_geometries(part_layer, part_ids)

    merged: dict[str, dict[str, Any]] = {}
    total = len(part_ids)
    for offset in range(0, total, chunk_size):
        await _checkpoint_not_cancelled(
            jobs_repo,
            context,
            job_id,
            map_session_id=map_session_id,
            progress_publisher=progress_publisher,
        )
        chunk = part_ids[offset : offset + chunk_size]
        merged.update(await parts_repo.fetch_part_geometries(part_layer, chunk))
        fetched = min(offset + len(chunk), total)
        percent = 10 + int(25 * fetched / max(total, 1))
        message = f"Fetching part geometries ({fetched}/{total})."
        await _publish_progress(progress_publisher, map_session_id, "running", message, percent, job_id)
        await _maybe_await(
            jobs_repo.update_progress(
                context,
                job_id,
                status="running",
                phase="fetch_part_geometries",
                progress=percent,
                total=100,
                status_message=message,
                counts={"unique_part_count": total, "fetched_geometry_count": len(merged)},
            )
        )
    return merged


async def _checkpoint_not_cancelled(
    jobs_repo: DirectBuildJobRepository,
    context: CustomerContext,
    job_id: str,
    *,
    map_session_id: str,
    progress_publisher: Callable[[str, str, str, int | None, str | None], Any] | None,
) -> None:
    job = await _maybe_await(jobs_repo.get(context, job_id))
    if getattr(job, "cancel_requested", False) or getattr(job, "status", None) == "cancelled":
        await _publish_progress(
            progress_publisher, map_session_id, "cancelled", "Territory build cancelled.", None, job_id
        )
        raise JobCancelledError(job_id)


async def _fail_if_not_terminal(
    jobs_repo: DirectBuildJobRepository,
    context: CustomerContext,
    job_id: str,
    *,
    error: dict[str, Any],
) -> None:
    try:
        await _maybe_await(jobs_repo.fail(context, job_id, error=error))
    except InvalidJobTransitionError as exc:
        if exc.status == "cancelled":
            return
        raise


def _assignment_part_ids(assignments: list[Any]) -> list[str]:
    part_ids: list[str] = []
    for assignment in assignments:
        if isinstance(assignment, Mapping):
            part_id = str(assignment.get("part_id") or "").strip()
            if part_id:
                part_ids.append(part_id)
    return list(dict.fromkeys(part_ids))


def _structured_error(exc: Exception) -> dict[str, Any]:
    if hasattr(exc, "to_error"):
        return exc.to_error()  # type: ignore[no-any-return]
    return {
        "code": getattr(exc, "code", "INVALID_REQUEST"),
        "message": str(exc),
        "details": getattr(exc, "details", {}),
        "retryable": False,
        "user_action_required": True,
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value

"""Async Direct Build job runner."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from ezt_mcp.jobs import CustomerContext
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
) -> dict[str, Any]:
    """Run Direct Build and persist progress/result into the job repository.

    The server submits this coroutine as a background task so MCP clients get an
    immediate job reference and poll ``ezt://jobs/{job_id}/status`` plus
    ``ezt://jobs/{job_id}/result`` for completion.
    """
    part_layer = str(request.get("part_layer") or "").strip()
    assignments = list(request.get("assignments") or [])
    part_ids = _assignment_part_ids(assignments)

    async with timed_async_operation(
        logger,
        "tools.direct_build.job",
        job_id=job_id,
        part_layer=part_layer,
        assignment_count=len(assignments),
        unique_part_count=len(part_ids),
    ):
        try:
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
            _raise_if_cancelled(await _maybe_await(jobs_repo.get(context, job_id)), job_id=job_id)

            async with timed_async_operation(
                logger,
                "tools.direct_build.fetch_part_geometries",
                job_id=job_id,
                part_layer=part_layer,
                requested_part_count=len(part_ids),
            ):
                part_geometries = await parts_repo.fetch_part_geometries(part_layer, part_ids)

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
            _raise_if_cancelled(await _maybe_await(jobs_repo.get(context, job_id)), job_id=job_id)

            result_payload = build_direct_tal(
                request,
                part_geometries,
                backend=backend,
                dissolve_options=dissolve_options,
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
            await _maybe_await(jobs_repo.complete(context, job_id, result=result_payload))
            return result_payload
        except (HierarchyValidationError, DissolveValidationError, QueryPartsError, ValueError) as exc:
            error = _structured_error(exc)
            await _maybe_await(jobs_repo.fail(context, job_id, error=error))
            return {"ok": False, "error": error}
        except UnknownPartLayerError as exc:
            error = {
                "code": exc.code,
                "message": str(exc),
                "details": {"part_layer": exc.part_layer},
                "retryable": False,
                "user_action_required": True,
            }
            await _maybe_await(jobs_repo.fail(context, job_id, error=error))
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
            await _maybe_await(jobs_repo.fail(context, job_id, error=error))
            return {"ok": False, "error": error}


def _assignment_part_ids(assignments: list[Any]) -> list[str]:
    part_ids: list[str] = []
    for assignment in assignments:
        if isinstance(assignment, Mapping):
            part_id = str(assignment.get("part_id") or "").strip()
            if part_id:
                part_ids.append(part_id)
    return list(dict.fromkeys(part_ids))


def _raise_if_cancelled(job: Any, *, job_id: str) -> None:
    if getattr(job, "cancel_requested", False) or getattr(job, "status", None) == "cancelled":
        raise ValueError(f"Direct Build job {job_id} was cancelled.")


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

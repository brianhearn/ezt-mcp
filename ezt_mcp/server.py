"""FastMCP/Starlette server setup for EZT MCP."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

import asyncpg
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .map_component.routes import MapVisualizationRoutes
from .map_component.sessions import InMemoryMapSessionStore, MapVisualizationError
from datetime import UTC, datetime

from .auth import APIKeyAuth
from .config import ServerConfig
from .db.jobs import AsyncpgJobRepository
from .db.map_sessions import AsyncpgMapSessionStore
from .db.part_layers import AsyncpgPartLayerRepository
from .db.parts import AsyncpgPartsRepository
from .observability import RequestTimingMiddleware, timed_async_operation
from .jobs import (
    CustomerContext,
    InMemoryJobRepository,
    InvalidJobTransitionError,
    JobAccessError,
    JobLimitExceededError,
    submission_response,
)
from .part_selection import (
    InMemoryPartSelectionRepository,
    InvalidPartSelectionError,
    PartSelectionAccessError,
)
from .resources.part_layers import (
    UnknownPartLayerError,
    assert_no_forbidden_public_fields,
    get_part_layer_resource,
    list_part_layers_resource,
)
from .territory.dissolve import DissolveOptions
from .tools.query_parts import query_parts_tool
from .workers import JobWorker

logger = logging.getLogger(__name__)


class AppState:
    """Mutable runtime state attached to the Starlette app."""

    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None
        self.part_layers_repo: AsyncpgPartLayerRepository | None = None
        self.parts_repo: AsyncpgPartsRepository | None = None
        self.jobs_repo: AsyncpgJobRepository | InMemoryJobRepository = InMemoryJobRepository()
        self.part_selections = InMemoryPartSelectionRepository()
        self.map_sessions = InMemoryMapSessionStore()
        self.job_worker: JobWorker | None = None
        self.job_worker_task: asyncio.Task[Any] | None = None


def create_mcp_server(state: AppState, *, public_base_url: str):
    """Create the FastMCP server and register EZT resources."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.server import TransportSecuritySettings

    mcp = FastMCP(
        name="ezt-mcp",
        instructions=(
            "EasyTerritory MCP server. Use resources such as ezt://part-layers "
            "to discover available geography before calling territory tools."
        ),
        streamable_http_path="/",
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                "expertpack.ai",
                "www.expertpack.ai",
                "127.0.0.1:8100",
                "localhost:8100",
            ],
            allowed_origins=[
                "https://expertpack.ai",
                "https://www.expertpack.ai",
            ],
        ),
    )

    @mcp.resource("ezt://part-layers")
    async def part_layers() -> str:
        """Available canonical part layers for territory construction."""
        async with timed_async_operation(logger, "mcp.resource.part_layers.list"):
            repo = _require_repo(state)
            payload = await list_part_layers_resource(repo)
            assert_no_forbidden_public_fields(payload)
            return json.dumps(payload, indent=2)

    @mcp.resource("ezt://part-layers/{part_layer}")
    async def part_layer_detail(part_layer: str) -> str:
        """Detailed metadata for one canonical part layer."""
        async with timed_async_operation(
            logger, "mcp.resource.part_layers.detail", part_layer=part_layer
        ):
            repo = _require_repo(state)
            try:
                payload = await get_part_layer_resource(repo, part_layer)
            except UnknownPartLayerError as exc:
                return json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": exc.code,
                            "message": str(exc),
                            "details": {"part_layer": exc.part_layer},
                            "retryable": False,
                            "user_action_required": True,
                        },
                    },
                    indent=2,
                )
            assert_no_forbidden_public_fields(payload)
            return json.dumps(payload, indent=2)

    @mcp.resource("ezt://jobs/{job_id}/status")
    async def job_status(job_id: str) -> str:
        """Authoritative async job status for the authenticated customer."""
        async with timed_async_operation(logger, "mcp.resource.jobs.status", job_id=job_id):
            try:
                job = await _maybe_await(
                    _require_jobs_repo(state).get(_default_customer_context(), job_id)
                )
            except JobAccessError as exc:
                return json.dumps(_job_error_payload(exc.code, str(exc), job_id=job_id), indent=2)
            return json.dumps(job.status_resource(), indent=2)

    @mcp.resource("ezt://jobs/{job_id}/result")
    async def job_result(job_id: str) -> str:
        """Terminal async job result for the authenticated customer."""
        async with timed_async_operation(logger, "mcp.resource.jobs.result", job_id=job_id):
            try:
                repo = _require_jobs_repo(state)
                if hasattr(repo, "result_resource"):
                    result = await _maybe_await(
                        repo.result_resource(_default_customer_context(), job_id)
                    )
                else:
                    job = await _maybe_await(repo.get(_default_customer_context(), job_id))
                    result = job.result_resource()
            except JobAccessError as exc:
                return json.dumps(_job_error_payload(exc.code, str(exc), job_id=job_id), indent=2)
            except InvalidJobTransitionError as exc:
                return json.dumps(
                    _job_error_payload(exc.code, str(exc), job_id=job_id, status=exc.status),
                    indent=2,
                )
            return json.dumps(result, indent=2)

    @mcp.resource("ezt://part-selections/{selection_task_id}")
    async def part_selection(selection_task_id: str) -> str:
        """Committed output or current status for a first-class part-selection task."""
        async with timed_async_operation(
            logger, "mcp.resource.part_selections.detail", selection_task_id=selection_task_id
        ):
            try:
                task = state.part_selections.get(_default_customer_context(), selection_task_id)
            except PartSelectionAccessError as exc:
                return json.dumps(
                    _selection_error_payload(exc.code, str(exc), selection_task_id=selection_task_id),
                    indent=2,
                )
            return json.dumps(task.resource(), indent=2)

    @mcp.resource("ezt://map-sessions/{map_session_id}/state")
    async def map_session_state(map_session_id: str) -> str:
        """Current Map Component session state."""
        async with timed_async_operation(
            logger, "mcp.resource.map_sessions.state", map_session_id=map_session_id
        ):
            try:
                return json.dumps(
                    await _maybe_await(state.map_sessions.get_state(map_session_id)), indent=2
                )
            except MapVisualizationError as exc:
                return json.dumps({"ok": False, "error": exc.to_error()}, indent=2)

    @mcp.resource("ezt://map-sessions/{map_session_id}/selection")
    async def map_session_selection(map_session_id: str) -> str:
        """Committed Map Component selection, when available."""
        async with timed_async_operation(
            logger, "mcp.resource.map_sessions.selection", map_session_id=map_session_id
        ):
            try:
                return json.dumps(
                    await _maybe_await(state.map_sessions.get_selection(map_session_id)), indent=2
                )
            except MapVisualizationError as exc:
                return json.dumps({"ok": False, "error": exc.to_error()}, indent=2)

    @mcp.tool(
        name="get_map_visualization",
        description=(
            "Create a short-lived browser-safe Map Component URL for a TS/TAL. "
            "The URL token is carried in the path; no MCP API key or geometry is returned in the tool payload."
        ),
        structured_output=True,
    )
    async def get_map_visualization(
        ts: dict[str, Any],
        mode: str = "view",
        active_tal_id: str | None = None,
        presentation: dict[str, Any] | None = None,
        expiry_seconds: int | None = None,
        interaction_flags: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a browser-safe map visualization URL for a TS/TAL."""
        request: dict[str, Any] = {"ts": ts, "mode": mode}
        if active_tal_id is not None:
            request["active_tal_id"] = active_tal_id
        if presentation is not None:
            request["presentation"] = presentation
        if expiry_seconds is not None:
            request["expiry_seconds"] = expiry_seconds
        if interaction_flags is not None:
            request["interaction_flags"] = interaction_flags
        async with timed_async_operation(logger, "mcp.tool.get_map_visualization"):
            return await _create_map_visualization_tool_result_async(
                state,
                request,
                public_base_url=public_base_url,
            )

    @mcp.tool(
        name="query_parts",
        description=(
            "Query part metadata by attribute filter or explicit part IDs. "
            "Returns part_id plus generic attributes only; geometry is never returned."
        ),
        structured_output=True,
    )
    async def query_parts(
        part_layer: str,
        filter: dict[str, Any] | None = None,
        part_ids: list[str] | None = None,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Find parts by filter predicate or explicit ID list."""
        payload: dict[str, Any] = {"part_layer": part_layer, "max_results": max_results}
        if filter is not None:
            payload["filter"] = filter
        if part_ids is not None:
            payload["part_ids"] = part_ids
        if page_token is not None:
            payload["page_token"] = page_token
        async with timed_async_operation(logger, "mcp.tool.query_parts"):
            return await query_parts_tool(_require_parts_repo(state), payload)

    @mcp.tool(
        name="direct_build",
        description=(
            "Submit and run a Direct Build job from part assignments to a Territory Solution. "
            "The job fetches part geometry server-side and returns the completed result through job resources."
        ),
        structured_output=True,
    )
    async def direct_build(
        part_layer: str,
        tal_label: str,
        assignments: list[dict[str, Any]],
        ts: dict[str, Any] | None = None,
        ts_handle: str | None = None,
        expected_revision: int | None = None,
        repair_policy: str = "default",
        map_session_id: str | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "part_layer": part_layer,
            "tal_label": tal_label,
            "assignments": assignments,
            "repair_policy": repair_policy,
        }
        if ts is not None:
            request["ts"] = ts
        if ts_handle is not None:
            request["ts_handle"] = ts_handle
        if expected_revision is not None:
            request["expected_revision"] = expected_revision
        if map_session_id is not None:
            request["map_session_id"] = map_session_id
        async with timed_async_operation(logger, "mcp.tool.direct_build"):
            return await _submit_and_run_direct_build(state, request)

    @mcp.tool(
        name="request_part_selection",
        description=(
            "Create a first-class human part-selection task, open/reuse the user's "
            "Map Component in select mode, and return a selection resource URI."
        ),
        structured_output=True,
    )
    async def request_part_selection(
        part_layer: str,
        purpose: str = "generic",
        prompt: str | None = None,
        ts: dict[str, Any] | None = None,
        active_tal_id: str | None = None,
        user_id: str | None = None,
        expiry_seconds: int | None = None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "mode": "select",
            "user_id": user_id or "default-user",
            "expiry_seconds": expiry_seconds,
        }
        if ts is not None:
            request["ts"] = ts
        if active_tal_id is not None:
            request["active_tal_id"] = active_tal_id
        async with timed_async_operation(logger, "mcp.tool.request_part_selection"):
            return await _request_part_selection_tool_result_async(
                state,
                request,
                part_layer=part_layer,
                purpose=purpose,
                prompt=prompt,
                public_base_url=public_base_url,
            )

    @mcp.tool(
        name="get_part_selection",
        description="Return the status or committed selected part IDs for a part-selection task.",
        structured_output=True,
    )
    async def get_part_selection(selection_task_id: str) -> dict[str, Any]:
        async with timed_async_operation(
            logger, "mcp.tool.get_part_selection", selection_task_id=selection_task_id
        ):
            try:
                task = state.part_selections.get(_default_customer_context(), selection_task_id)
            except PartSelectionAccessError as exc:
                return _selection_error_payload(exc.code, str(exc), selection_task_id=selection_task_id)
            return {"ok": True, "result": task.resource()}

    @mcp.tool(
        name="create_territory_from_parts",
        description=(
            "Create/update one territory from explicit part IDs by submitting a queued "
            "Direct Build-backed mutation job. The Map Component only supplies selected parts."
        ),
        structured_output=True,
    )
    async def create_territory_from_parts(
        part_layer: str,
        part_ids: list[str],
        territory_name: str,
        territory_path: list[str] | None = None,
        tal_id: str | None = None,
        conflict_policy: str | None = None,
        ts: dict[str, Any] | None = None,
        map_session_id: str | None = None,
    ) -> dict[str, Any]:
        async with timed_async_operation(logger, "mcp.tool.create_territory_from_parts"):
            if not part_ids or not all(isinstance(item, str) and item for item in part_ids):
                return _selection_error_payload(
                    "INVALID_REQUEST", "create_territory_from_parts requires non-empty part_ids."
                )
            request = _create_territory_direct_build_request(
                part_layer=part_layer,
                part_ids=part_ids,
                territory_name=territory_name,
                territory_path=territory_path,
                tal_id=tal_id,
                conflict_policy=conflict_policy,
                ts=ts,
                map_session_id=map_session_id,
            )
            return await _submit_and_run_direct_build(
                state, request, tool_name="create_territory_from_parts"
            )

    @mcp.tool(
        name="cancel_job",
        description="Cooperatively cancel an async EZT MCP job for the authenticated customer.",
        structured_output=True,
    )
    async def cancel_job(job_id: str) -> dict[str, Any]:
        async with timed_async_operation(logger, "mcp.tool.cancel_job", job_id=job_id):
            try:
                job = await _maybe_await(
                    _require_jobs_repo(state).cancel(_default_customer_context(), job_id)
                )
            except JobAccessError as exc:
                return _job_error_payload(exc.code, str(exc), job_id=job_id)
            return {"ok": True, "result": job.status_resource()}

    @mcp.tool(
        name="set_map_state",
        description=(
            "Update deterministic Map Component session state, such as mode, "
            "active TAL, and pending job reference. "
            "Selection-driven job advancement is intentionally handled separately."
        ),
        structured_output=True,
    )
    async def set_map_state(
        map_session_id: str,
        mode: str | None = None,
        active_tal_id: str | None = None,
        pending_job_reference: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with timed_async_operation(
            logger, "mcp.tool.set_map_state", map_session_id=map_session_id
        ):
            try:
                result = await _maybe_await(
                    state.map_sessions.set_state(
                        map_session_id,
                        mode=mode,
                        active_tal_id=active_tal_id,
                        pending_job_reference=pending_job_reference,
                    )
                )
            except MapVisualizationError as exc:
                return {"ok": False, "error": exc.to_error()}
            return {"ok": True, "result": result}

    @mcp.tool(
        name="get_map_selection",
        description="Return the committed selection for a Map Component session, if one exists.",
        structured_output=True,
    )
    async def get_map_selection(map_session_id: str) -> dict[str, Any]:
        async with timed_async_operation(
            logger, "mcp.tool.get_map_selection", map_session_id=map_session_id
        ):
            try:
                selection = await _maybe_await(state.map_sessions.get_selection(map_session_id))
            except MapVisualizationError as exc:
                return {"ok": False, "error": exc.to_error()}
            return {"ok": True, "result": selection}

    return mcp


def build_app(config: ServerConfig) -> Starlette:
    """Build the Starlette ASGI app with health/debug routes and MCP mount."""
    state = AppState()
    auth = APIKeyAuth(config.auth.api_keys)
    mcp = create_mcp_server(state, public_base_url=config.map_visualization.public_base_url)
    mcp_app = mcp.streamable_http_app()
    map_routes = MapVisualizationRoutes(
        state.map_sessions,
        public_base_url=config.map_visualization.public_base_url,
        on_selection_committed=lambda selection: _commit_part_selection_from_map(state, selection),
    )
    dissolve_options = DissolveOptions(
        simplify_tolerance=config.dissolve.simplify_tolerance,
        overview_simplify_tolerance=config.dissolve.overview_simplify_tolerance,
        partition_threshold=config.dissolve.partition_threshold,
        target_parts_per_cluster=config.dissolve.target_parts_per_cluster,
        max_clusters=config.dissolve.max_clusters,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        database_url = config.database_url
        if database_url:
            async with timed_async_operation(logger, "startup.db_pool.open"):
                state.pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
                state.part_layers_repo = AsyncpgPartLayerRepository(state.pool)
                state.parts_repo = AsyncpgPartsRepository(state.pool)
                if await _transient_jobs_available(state.pool):
                    state.jobs_repo = AsyncpgJobRepository(
                        state.pool,
                        max_queued_jobs_per_customer=config.jobs.max_queued_jobs_per_customer,
                        max_active_jobs_per_customer=config.jobs.max_active_jobs_per_customer,
                        default_max_attempts=config.jobs.max_attempts,
                        retry_backoff_seconds=config.jobs.retry_backoff_seconds,
                    )
                else:
                    logger.warning(
                        "transient.jobs migration is not available; "
                        "async job resources will use the in-memory dev repository"
                    )
                if await _transient_map_sessions_available(state.pool):
                    state.map_sessions = AsyncpgMapSessionStore(state.pool)
                    map_routes.store = state.map_sessions
                else:
                    logger.warning(
                        "transient.map_sessions migration is not available; "
                        "map sessions will use the in-memory dev repository"
                    )
        else:
            logger.warning("DATABASE_URL not configured; DB-backed resources will be unavailable")

        if state.parts_repo is not None:
            state.job_worker = JobWorker(
                context=_default_customer_context(),
                jobs_repo=state.jobs_repo,
                parts_repo=state.parts_repo,
                dissolve_options=dissolve_options,
                progress_publisher=lambda map_session_id, event_state, message, percent: _publish_map_progress(
                    state, map_session_id, event_state, message, percent
                ),
            )
            state.job_worker_task = asyncio.create_task(state.job_worker.run())

        async with mcp.session_manager.run():
            try:
                yield
            finally:
                if state.job_worker is not None:
                    state.job_worker.stop()
                if state.job_worker_task is not None:
                    state.job_worker_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await state.job_worker_task

        if state.pool is not None:
            async with timed_async_operation(logger, "shutdown.db_pool.close"):
                await state.pool.close()

    async def health(request: Request) -> JSONResponse:
        db: dict[str, Any] = {"configured": bool(config.database_url), "connected": False}
        if state.pool is not None:
            try:
                async with timed_async_operation(logger, "health.db_probe"):
                    async with state.pool.acquire() as conn:
                        value = await conn.fetchval("select 1")
                    db["connected"] = value == 1
            except Exception as exc:  # noqa: BLE001
                db["error"] = exc.__class__.__name__
        return JSONResponse(
            {
                "status": "healthy" if db.get("connected") or not db["configured"] else "degraded",
                "service": "ezt-mcp",
                "auth_enabled": auth.enabled,
                "database": db,
            }
        )

    async def part_layers_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        async with timed_async_operation(logger, "http.part_layers.list"):
            repo = _require_repo(state)
            payload = await list_part_layers_resource(repo)
            assert_no_forbidden_public_fields(payload)
            return JSONResponse(payload)

    async def part_layer_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        part_layer = request.path_params["part_layer"]
        async with timed_async_operation(logger, "http.part_layers.detail", part_layer=part_layer):
            repo = _require_repo(state)
            try:
                payload = await get_part_layer_resource(repo, part_layer)
            except UnknownPartLayerError as exc:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": {
                            "code": exc.code,
                            "message": str(exc),
                            "details": {"part_layer": exc.part_layer},
                            "retryable": False,
                            "user_action_required": True,
                        },
                    },
                    status_code=404,
                )
            assert_no_forbidden_public_fields(payload)
            return JSONResponse(payload)

    async def query_parts_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        async with timed_async_operation(logger, "http.query_parts"):
            payload = await query_parts_tool(_require_parts_repo(state), body)
            status_code = 200 if payload.get("ok") is True else _status_for_tool_error(payload)
            return JSONResponse(payload, status_code=status_code)

    async def set_map_progress_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        async with timed_async_operation(logger, "http.set_map_progress"):
            payload = _set_map_progress(state, body)
            status_code = 200 if payload.get("ok") is True else 400
            return JSONResponse(payload, status_code=status_code)

    async def direct_build_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        async with timed_async_operation(logger, "http.direct_build"):
            payload = await _submit_and_run_direct_build(
                state,
                body,
                dissolve_options=dissolve_options,
            )
            status_code = 200 if payload.get("ok") is True else _status_for_tool_error(payload)
            return JSONResponse(payload, status_code=status_code)

    async def create_territory_from_parts_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        async with timed_async_operation(logger, "http.create_territory_from_parts"):
            try:
                direct_request = _create_territory_direct_build_request(
                    part_layer=str(body.get("part_layer") or ""),
                    part_ids=list(body.get("part_ids") or []),
                    territory_name=str(body.get("territory_name") or ""),
                    territory_path=body.get("territory_path"),
                    tal_id=body.get("tal_id"),
                    conflict_policy=body.get("conflict_policy"),
                    ts=body.get("ts") if isinstance(body.get("ts"), dict) else None,
                    map_session_id=body.get("map_session_id"),
                )
            except ValueError as exc:
                payload = _selection_error_payload("INVALID_REQUEST", str(exc))
                return JSONResponse(payload, status_code=400)
            payload = await _submit_and_run_direct_build(
                state,
                direct_request,
                tool_name="create_territory_from_parts",
                dissolve_options=dissolve_options,
            )
            status_code = 200 if payload.get("ok") is True else _status_for_tool_error(payload)
            return JSONResponse(payload, status_code=status_code)

    async def job_status_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        job_id = request.path_params["job_id"]
        async with timed_async_operation(logger, "http.jobs.status", job_id=job_id):
            try:
                job = await _maybe_await(
                    _require_jobs_repo(state).get(_default_customer_context(), job_id)
                )
            except JobAccessError as exc:
                return JSONResponse(
                    _job_error_payload(exc.code, str(exc), job_id=job_id), status_code=404
                )
            return JSONResponse(job.status_resource())

    async def job_result_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        job_id = request.path_params["job_id"]
        async with timed_async_operation(logger, "http.jobs.result", job_id=job_id):
            try:
                repo = _require_jobs_repo(state)
                if hasattr(repo, "result_resource"):
                    result = await _maybe_await(
                        repo.result_resource(_default_customer_context(), job_id)
                    )
                else:
                    job = await _maybe_await(repo.get(_default_customer_context(), job_id))
                    result = job.result_resource()
            except JobAccessError as exc:
                return JSONResponse(
                    _job_error_payload(exc.code, str(exc), job_id=job_id), status_code=404
                )
            except InvalidJobTransitionError as exc:
                return JSONResponse(
                    _job_error_payload(exc.code, str(exc), job_id=job_id, status=exc.status),
                    status_code=409,
                )
            return JSONResponse(result)

    async def cancel_job_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        job_id = request.path_params["job_id"]
        async with timed_async_operation(logger, "http.jobs.cancel", job_id=job_id):
            try:
                job = await _maybe_await(
                    _require_jobs_repo(state).cancel(_default_customer_context(), job_id)
                )
            except JobAccessError as exc:
                return JSONResponse(
                    _job_error_payload(exc.code, str(exc), job_id=job_id), status_code=404
                )
            return JSONResponse({"ok": True, "result": job.status_resource()})

    routes = [
        Route("/health", health),
        Route("/part-layers", part_layers_http),
        Route("/part-layers/{part_layer}", part_layer_http),
        Route("/query-parts", query_parts_http, methods=["POST"]),
        Route("/direct-build", direct_build_http, methods=["POST"]),
        Route("/create-territory-from-parts", create_territory_from_parts_http, methods=["POST"]),
        Route("/jobs/{job_id}/status", job_status_http),
        Route("/jobs/{job_id}/result", job_result_http),
        Route("/jobs/{job_id}/cancel", cancel_job_http, methods=["POST"]),
        Route("/get-map-visualization", map_routes.create_visualization, methods=["POST"]),
        Route("/set-map-progress", set_map_progress_http, methods=["POST"]),
        Route("/maps/session/{map_session_id}/{token}", map_routes.viewer),
        Route("/maps/session/{map_session_id}/{token}/render-payload", map_routes.render_payload),
        Route("/maps/session/{map_session_id}/{token}/state", map_routes.state),
        Route(
            "/maps/session/{map_session_id}/{token}/active-tal",
            map_routes.set_active_tal,
            methods=["POST"],
        ),
        Route("/maps/session/{map_session_id}/{token}/events", map_routes.events),
        Route(
            "/maps/session/{map_session_id}/{token}/selection",
            map_routes.commit_selection,
            methods=["POST"],
        ),
        Route("/maps/session/{map_session_id}", map_routes.viewer),
        Route("/maps/session/{map_session_id}/render-payload", map_routes.render_payload),
        Route("/maps/session/{map_session_id}/state", map_routes.state),
        Route(
            "/maps/session/{map_session_id}/active-tal",
            map_routes.set_active_tal,
            methods=["POST"],
        ),
        Route("/maps/session/{map_session_id}/events", map_routes.events),
        Route("/static/{asset_name}", map_routes.static_asset),
        Route("/assets/tiles/us-basemap.pmtiles", map_routes.pmtiles_asset),
        Route("/assets/tiles/parts/{part_layer}.pmtiles", map_routes.part_pmtiles_asset),
        Mount("/", app=mcp_app),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.ezt_state = state
    app.add_middleware(RequestTimingMiddleware)
    return app


def _require_repo(state: AppState) -> AsyncpgPartLayerRepository:
    if state.part_layers_repo is None:
        raise RuntimeError("Database repository is not configured")
    return state.part_layers_repo


def _require_parts_repo(state: AppState) -> AsyncpgPartsRepository:
    if state.parts_repo is None:
        raise RuntimeError("Database repository is not configured")
    return state.parts_repo


def _create_map_visualization_tool_result(
    state: AppState, request: dict[str, Any], *, public_base_url: str
) -> dict[str, Any]:
    try:
        created = state.map_sessions.create_or_update_session(
            request,
            public_base_url=public_base_url,
            user_id=str(request.get("user_id") or "default-user"),
        )
    except MapVisualizationError as exc:
        return {"ok": False, "error": exc.to_error()}
    return _map_visualization_payload(created, public_base_url=public_base_url)


async def _create_map_visualization_tool_result_async(
    state: AppState, request: dict[str, Any], *, public_base_url: str
) -> dict[str, Any]:
    try:
        created = await _maybe_await(
            state.map_sessions.create_or_update_session(
                request,
                public_base_url=public_base_url,
                user_id=str(request.get("user_id") or "default-user"),
            )
        )
    except MapVisualizationError as exc:
        return {"ok": False, "error": exc.to_error()}
    return _map_visualization_payload(created, public_base_url=public_base_url)


def _map_visualization_payload(created: Any, *, public_base_url: str) -> dict[str, Any]:
    return {
        "ok": True,
        "result": created.session.response_result(
            public_base_url=public_base_url,
            session_exists=created.session_exists,
        ),
    }




async def _request_part_selection_tool_result_async(
    state: AppState,
    request: dict[str, Any],
    *,
    part_layer: str,
    purpose: str,
    prompt: str | None,
    public_base_url: str,
) -> dict[str, Any]:
    try:
        map_result = await _create_map_visualization_tool_result_async(
            state, request, public_base_url=public_base_url
        )
        if map_result.get("ok") is not True:
            return map_result
        map_payload = map_result["result"]
        task = state.part_selections.create(
            _default_customer_context(),
            user_id=str(request.get("user_id") or "default-user"),
            part_layer=part_layer,
            purpose=purpose,
            prompt=prompt,
            map_session_id=map_payload["map_session_id"],
            map_url=map_payload["map_url"],
            active_tal_id=(map_payload.get("active_tal_summary") or {}).get("tal_id"),
            ts_identity=map_payload.get("ts_identity"),
        )
        await _maybe_await(
            state.map_sessions.set_active_selection_task(
                map_payload["map_session_id"], task.selection_task_id
            )
        )
    except (MapVisualizationError, InvalidPartSelectionError) as exc:
        return {"ok": False, "error": exc.to_error()}
    return {
        "ok": True,
        "result": {
            **map_payload,
            "selection_task_id": task.selection_task_id,
            "selection_resource_uri": f"ezt://part-selections/{task.selection_task_id}",
            "part_selection": task.resource(),
        },
    }

def _commit_part_selection_from_map(
    state: AppState, selection: dict[str, Any]
) -> dict[str, Any] | None:
    selection_task_id = selection.get("selection_task_id")
    if not isinstance(selection_task_id, str) or not selection_task_id:
        return None
    try:
        task = state.part_selections.commit(
            _default_customer_context(), selection_task_id, selection
        )
    except (PartSelectionAccessError, InvalidPartSelectionError) as exc:
        if isinstance(exc, PartSelectionAccessError):
            return _selection_error_payload(
                exc.code, str(exc), selection_task_id=selection_task_id
            )
        return _selection_error_payload(exc.code, str(exc), **exc.details)
    state.map_sessions.publish_event(
        task.map_session_id,
        {
            "type": "part_selection_committed",
            "map_session_id": task.map_session_id,
            "selection_task_id": task.selection_task_id,
            "selection_resource_uri": task.selection_resource_uri,
            "created_at": task.resource().get("committed_at"),
        },
    )
    return task.resource()


async def _submit_and_run_direct_build(
    state: AppState,
    request: dict[str, Any],
    *,
    tool_name: str = "direct_build",
    dissolve_options: DissolveOptions | None = None,
) -> dict[str, Any]:
    try:
        repo = _require_jobs_repo(state)
        _require_parts_repo(state)
        context = _default_customer_context()
        message = (
            "Create Territory from Parts job accepted and queued."
            if tool_name == "create_territory_from_parts"
            else "Direct Build job accepted and queued."
        )
        job = await _maybe_await(
            repo.submit(
                context,
                tool_name=tool_name,
                phase="queued",
                status="queued",
                status_message=message,
                request_payload=request,
            )
        )
        # A startup JobWorker claims queued jobs from shared transient storage.
        # This keeps submissions durable across request completion and avoids
        # process-local per-request asyncio.create_task execution.
        return submission_response(job)
    except JobLimitExceededError as exc:
        return _job_error_payload(
            exc.code,
            str(exc),
            limit_name=exc.limit_name,
            limit=exc.limit,
            current=exc.current,
        )
    except RuntimeError as exc:
        return _job_error_payload("UNSUPPORTED_OPERATION", str(exc))




def _create_territory_direct_build_request(
    *,
    part_layer: str,
    part_ids: list[str],
    territory_name: str,
    territory_path: list[str] | None,
    tal_id: str | None,
    conflict_policy: str | None,
    ts: dict[str, Any] | None,
    map_session_id: str | None,
) -> dict[str, Any]:
    unique_part_ids = list(
        dict.fromkeys(str(part_id).strip() for part_id in part_ids if str(part_id).strip())
    )
    clean_name = str(territory_name or "").strip()
    if not clean_name:
        raise ValueError("territory_name is required")
    path = [str(item).strip() for item in (territory_path or []) if str(item).strip()]
    if not path or path[-1] != clean_name:
        path.append(clean_name)
    request: dict[str, Any] = {
        "part_layer": part_layer,
        "tal_label": clean_name,
        "assignments": [
            {"part_id": part_id, "territory_path": path}
            for part_id in unique_part_ids
        ],
        "repair_policy": "default",
        "source_tool": "create_territory_from_parts",
        "conflict_policy": conflict_policy or "reject",
    }
    if ts is not None:
        request["ts"] = ts
    if tal_id:
        request["requested_tal_id"] = tal_id
    if map_session_id:
        request["map_session_id"] = map_session_id
    return request

def _request_part_selection_tool_result(
    state: AppState,
    request: dict[str, Any],
    *,
    part_layer: str,
    purpose: str,
    prompt: str | None,
    public_base_url: str,
) -> dict[str, Any]:
    try:
        map_result = _create_map_visualization_tool_result(
            state, request, public_base_url=public_base_url
        )
        if map_result.get("ok") is not True:
            return map_result
        map_payload = map_result["result"]
        task = state.part_selections.create(
            _default_customer_context(),
            user_id=str(request.get("user_id") or "default-user"),
            part_layer=part_layer,
            purpose=purpose,
            prompt=prompt,
            map_session_id=map_payload["map_session_id"],
            map_url=map_payload["map_url"],
            active_tal_id=(map_payload.get("active_tal_summary") or {}).get("tal_id"),
            ts_identity=map_payload.get("ts_identity"),
            ttl_seconds=int(request.get("expiry_seconds") or 3600),
        )
        state.map_sessions.set_active_selection_task(
            task.map_session_id, task.selection_task_id
        )
    except (MapVisualizationError, InvalidPartSelectionError) as exc:
        if isinstance(exc, MapVisualizationError):
            return {"ok": False, "error": exc.to_error()}
        return _selection_error_payload(exc.code, str(exc), **exc.details)
    return {
        "ok": True,
        "result": task.reference(session_exists=bool(map_payload.get("session_exists"))),
    }


def _require_jobs_repo(state: AppState):
    return state.jobs_repo


async def _transient_jobs_available(pool: asyncpg.Pool) -> bool:
    try:
        async with pool.acquire() as conn:
            value = await conn.fetchval("select to_regclass($1)", "transient.jobs")
    except Exception as exc:  # noqa: BLE001
        logger.warning("transient.jobs migration probe failed: %s", exc.__class__.__name__)
        return False
    return value is not None


async def _transient_map_sessions_available(pool: asyncpg.Pool) -> bool:
    try:
        async with pool.acquire() as conn:
            value = await conn.fetchval("select to_regclass($1)", "transient.map_sessions")
    except Exception as exc:  # noqa: BLE001
        logger.warning("transient.map_sessions migration probe failed: %s", exc.__class__.__name__)
        return False
    return value is not None


def _default_customer_context() -> CustomerContext:
    # Temporary dev/test customer context until auth exposes customer_id/key_id.
    return CustomerContext(customer_id="00000000-0000-0000-0000-000000000001")


def _publish_map_progress(
    state: AppState, map_session_id: str, event_state: str, message: str, percent: int | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "map_session_id": map_session_id,
        "state": event_state,
        "message": message,
    }
    if percent is not None:
        payload["percent"] = percent
    return _set_map_progress(state, payload)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _job_error_payload(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": {key: value for key, value in details.items() if value is not None},
            "retryable": False,
            "user_action_required": code == "UNKNOWN_JOB",
        },
    }


def _selection_error_payload(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": {key: value for key, value in details.items() if value is not None},
            "retryable": False,
            "user_action_required": code in {"UNKNOWN_SELECTION_TASK", "INVALID_REQUEST"},
        },
    }


def _status_for_tool_error(payload: dict[str, Any]) -> int:
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code in {"INVALID_REQUEST", "INVALID_PAGE_TOKEN", "UNSUPPORTED_FILTER"}:
        return 400
    if code in {"UNKNOWN_PART_LAYER", "UNKNOWN_PART_ID"}:
        return 404
    if code == "JOB_LIMIT_EXCEEDED":
        return 429
    if code == "UNSUPPORTED_OPERATION":
        return 501
    return 500


def _unauthorized_if_needed(request: Request, auth: APIKeyAuth) -> JSONResponse | None:
    if auth.authenticate(request.headers.get("Authorization", "")):
        return None
    return JSONResponse({"error": "Unauthorized"}, status_code=401)


def _set_map_progress(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        map_session_id = payload.get("map_session_id")
        if not map_session_id or not isinstance(map_session_id, str):
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "map_session_id is required",
                },
            }
        state_val = payload.get("state")
        if state_val not in {"running", "done", "error", "idle"}:
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_PROGRESS_STATE",
                    "message": f"Invalid state: {state_val}. Must be one of running, done, error, idle.",
                },
            }
        percent = payload.get("percent")
        if percent is not None:
            if not isinstance(percent, int) or not (0 <= percent <= 100):
                return {
                    "ok": False,
                    "error": {
                        "code": "INVALID_PROGRESS_PERCENT",
                        "message": "percent must be integer between 0 and 100 if provided",
                    },
                }
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            return {
                "ok": False,
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "message is required",
                },
            }

        event = {
            "type": "progress",
            "map_session_id": map_session_id,
            "state": state_val,
            "message": message,
            "percent": percent,
            "created_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        }
        state.map_sessions.publish_event(map_session_id, event)
        return {
            "ok": True,
            "map_session_id": map_session_id,
            "state": state_val,
            "message": message,
        }
    except MapVisualizationError as exc:
        return {"ok": False, "error": exc.to_error()}
    except Exception as exc:  # noqa: BLE001
        logger.exception("set_map_progress failed")
        return {
            "ok": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(exc),
            },
        }

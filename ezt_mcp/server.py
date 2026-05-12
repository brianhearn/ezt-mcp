"""FastMCP/Starlette server setup for EZT MCP."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .auth import APIKeyAuth
from .config import ServerConfig
from .db.part_layers import AsyncpgPartLayerRepository
from .resources.part_layers import (
    UnknownPartLayerError,
    assert_no_forbidden_public_fields,
    get_part_layer_resource,
    list_part_layers_resource,
)

logger = logging.getLogger(__name__)


class AppState:
    """Mutable runtime state attached to the Starlette app."""

    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None
        self.part_layers_repo: AsyncpgPartLayerRepository | None = None


def create_mcp_server(state: AppState):
    """Create the FastMCP server and register EZT resources."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="ezt-mcp",
        instructions=(
            "EasyTerritory MCP server. Use resources such as ezt://part-layers "
            "to discover available geography before calling territory tools."
        ),
        stateless_http=True,
    )

    @mcp.resource("ezt://part-layers")
    async def part_layers() -> str:
        """Available canonical part layers for territory construction."""
        repo = _require_repo(state)
        payload = await list_part_layers_resource(repo)
        assert_no_forbidden_public_fields(payload)
        return json.dumps(payload, indent=2)

    @mcp.resource("ezt://part-layers/{part_layer}")
    async def part_layer_detail(part_layer: str) -> str:
        """Detailed metadata for one canonical part layer."""
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

    return mcp


def build_app(config: ServerConfig) -> Starlette:
    """Build the Starlette ASGI app with health/debug routes and MCP mount."""
    state = AppState()
    auth = APIKeyAuth(config.auth.api_keys)
    mcp = create_mcp_server(state)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: Starlette):
        database_url = config.database_url
        if database_url:
            logger.info("Opening PostgreSQL pool")
            state.pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
            state.part_layers_repo = AsyncpgPartLayerRepository(state.pool)
        else:
            logger.warning("DATABASE_URL not configured; DB-backed resources will be unavailable")

        async with mcp.session_manager.run():
            yield

        if state.pool is not None:
            await state.pool.close()

    async def health(request: Request) -> JSONResponse:
        db: dict[str, Any] = {"configured": bool(config.database_url), "connected": False}
        if state.pool is not None:
            try:
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
        repo = _require_repo(state)
        payload = await list_part_layers_resource(repo)
        assert_no_forbidden_public_fields(payload)
        return JSONResponse(payload)

    async def part_layer_http(request: Request) -> JSONResponse:
        unauthorized = _unauthorized_if_needed(request, auth)
        if unauthorized is not None:
            return unauthorized
        repo = _require_repo(state)
        part_layer = request.path_params["part_layer"]
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

    routes = [
        Route("/health", health),
        Route("/part-layers", part_layers_http),
        Route("/part-layers/{part_layer}", part_layer_http),
        Mount("/", app=mcp_app),
    ]
    return Starlette(routes=routes, lifespan=lifespan)


def _require_repo(state: AppState) -> AsyncpgPartLayerRepository:
    if state.part_layers_repo is None:
        raise RuntimeError("Database repository is not configured")
    return state.part_layers_repo


def _unauthorized_if_needed(request: Request, auth: APIKeyAuth) -> JSONResponse | None:
    if auth.authenticate(request.headers.get("Authorization", "")):
        return None
    return JSONResponse({"error": "Unauthorized"}, status_code=401)

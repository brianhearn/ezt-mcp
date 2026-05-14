"""Starlette routes for read-only Map Component visualization."""

from __future__ import annotations

import asyncio
import json
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Mapping

from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)

from .sessions import InMemoryMapSessionStore, MapVisualizationError


class MapVisualizationRoutes:
    """HTTP handlers for dev/test map visualization sessions."""

    def __init__(
        self,
        store: InMemoryMapSessionStore,
        *,
        public_base_url: str,
        on_selection_committed: Callable[[Mapping[str, Any]], dict[str, Any] | None] | None = None,
    ):
        self.store = store
        self.public_base_url = public_base_url.rstrip("/")
        self.on_selection_committed = on_selection_committed

    async def create_visualization(self, request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, Mapping):
            return _error_response(
                MapVisualizationError("INVALID_TS", "Request body must be a JSON object."),
                status_code=400,
            )
        try:
            created = self.store.create_or_update_session(
                body,
                public_base_url=self.public_base_url,
                user_id=_user_id_from_request(request, body),
            )
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))
        return JSONResponse(
            {
                "ok": True,
                "result": created.session.response_result(
                    public_base_url=self.public_base_url,
                    session_exists=created.session_exists,
                ),
            }
        )

    async def viewer(self, request: Request) -> HTMLResponse:
        try:
            self._session_from_request(request)
        except MapVisualizationError as exc:
            return HTMLResponse(_error_html(str(exc)), status_code=_status_for_error(exc))
        html = _static_text("viewer.html").replace("__PUBLIC_BASE_URL__", self.public_base_url)
        return HTMLResponse(html)

    async def render_payload(self, request: Request) -> JSONResponse:
        try:
            session = self._session_from_request(request)
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))
        payload: dict[str, Any] = dict(session.render_payload)
        payload["map_session_id"] = session.map_session_id
        payload["expires_at"] = session.expires_at.isoformat().replace("+00:00", "Z")
        return JSONResponse(payload)

    async def state(self, request: Request) -> JSONResponse:
        try:
            session = self._session_from_request(request)
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))
        return JSONResponse(session.state_payload())

    async def set_active_tal(self, request: Request) -> JSONResponse:
        try:
            session = self._session_from_request(request)
            body = await request.json()
            if not isinstance(body, Mapping):
                raise MapVisualizationError("INVALID_TS", "Request body must be a JSON object.")
            active_tal_id = body.get("active_tal_id")
            if not isinstance(active_tal_id, str) or not active_tal_id.strip():
                raise MapVisualizationError(
                    "UNKNOWN_TAL_ID",
                    "active_tal_id is required to switch the active TAL.",
                )
            state = self.store.set_state(
                session.map_session_id,
                active_tal_id=active_tal_id,
            )
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))
        return JSONResponse({"ok": True, "result": state})

    async def events(self, request: Request) -> StreamingResponse:
        try:
            session = self._session_from_request(request)
            queue = self.store.subscribe(session.map_session_id)
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))

        async def event_stream():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                        yield _sse_event(event)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                self.store.unsubscribe(session.map_session_id, queue)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def commit_selection(self, request: Request) -> JSONResponse:
        try:
            session = self._session_from_request(request)
            body = await request.json()
            if not isinstance(body, Mapping):
                raise MapVisualizationError(
                    "INVALID_SELECTION", "Request body must be a JSON object."
                )
            selection = self.store.commit_selection(session.map_session_id, body)
            part_selection = None
            if self.on_selection_committed is not None:
                part_selection = self.on_selection_committed(selection)
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))
        payload = {"ok": True, "result": selection}
        if part_selection is not None:
            payload["part_selection"] = part_selection
        return JSONResponse(payload)

    async def static_asset(self, request: Request) -> Response:
        asset_name = request.path_params["asset_name"]
        asset_map = {
            "map-viewer-css": ("map-viewer.css", "text/css"),
            "map-viewer-js": ("map-viewer.js", "application/javascript"),
        }
        if asset_name not in asset_map:
            return Response("Not found", status_code=404)
        file_name, media_type = asset_map[asset_name]
        return Response(
            _static_text(file_name),
            media_type=media_type,
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    async def pmtiles_asset(self, request: Request) -> Response:
        tile_path = _static_path("tiles/us-basemap.pmtiles")
        if not tile_path.exists():
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "UNSUPPORTED_OPERATION",
                        "message": "US basemap PMTiles is not installed on this dev server yet.",
                        "details": {
                            "expected_path": "/assets/tiles/us-basemap.pmtiles",
                            "next_step": (
                                "Install a US-only PMTiles basemap or configure static tile hosting."
                            ),
                        },
                        "retryable": False,
                        "user_action_required": True,
                    },
                },
                status_code=404,
            )
        return FileResponse(
            tile_path,
            media_type="application/octet-stream",
            filename="us-basemap.pmtiles",
        )

    def _session_from_request(self, request: Request):
        token = request.path_params.get("token") or request.query_params.get("token", "")
        session_id = request.path_params["map_session_id"]
        return self.store.get_session(session_id, token)


def _user_id_from_request(request: Request, body: Mapping[str, Any] | None = None) -> str | None:
    if body and isinstance(body.get("user_id"), str):
        return body["user_id"]
    return request.headers.get("X-EZT-User-Id") or request.headers.get("X-User-Id")


def _sse_event(event: Mapping[str, Any]) -> str:
    event_type = str(event.get("type") or "message")
    data = json.dumps(dict(event), separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


def _static_text(asset_name: str) -> str:
    return _static_path(asset_name).read_text(encoding="utf-8")


def _static_path(asset_name: str) -> Path:
    root = resources.files("ezt_mcp.map_component.static")
    return Path(str(root.joinpath(asset_name)))


def _error_response(exc: MapVisualizationError, *, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": exc.to_error()}, status_code=status_code)


def _status_for_error(exc: MapVisualizationError) -> int:
    if exc.code in {"INVALID_TS", "INVALID_SELECTION", "UNSUPPORTED_OPERATION", "AMBIGUOUS_TAL"}:
        return 400
    if exc.code in {"INVALID_TS_HANDLE", "UNKNOWN_TAL_ID"}:
        return 404
    return 500


def _error_html(message: str) -> str:
    return f"""
<!doctype html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>Map unavailable</title></head>
  <body style=\"font-family: sans-serif; background:#101418; color:#f6f8fb; padding:24px\">
    <h1>Map unavailable</h1>
    <p>{json.dumps(message)}</p>
  </body>
</html>
"""

"""Starlette routes for read-only Map Component visualization."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .sessions import InMemoryMapSessionStore, MapVisualizationError


class MapVisualizationRoutes:
    """HTTP handlers for dev/test map visualization sessions."""

    def __init__(self, store: InMemoryMapSessionStore, *, public_base_url: str):
        self.store = store
        self.public_base_url = public_base_url.rstrip("/")

    async def create_visualization(self, request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, Mapping):
            return _error_response(
                MapVisualizationError("INVALID_TS", "Request body must be a JSON object."),
                status_code=400,
            )
        try:
            session = self.store.create_session(body, public_base_url=self.public_base_url)
        except MapVisualizationError as exc:
            return _error_response(exc, status_code=_status_for_error(exc))
        return JSONResponse(
            {
                "ok": True,
                "result": session.response_result(public_base_url=self.public_base_url),
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

    async def static_asset(self, request: Request) -> Response:
        asset_name = request.path_params["asset_name"]
        if asset_name not in {"map-viewer.css", "map-viewer.js"}:
            return Response("Not found", status_code=404)
        content = _static_text(asset_name)
        media_type = "text/css" if asset_name.endswith(".css") else "application/javascript"
        return Response(content, media_type=media_type)

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
        token = request.query_params.get("token", "")
        session_id = request.path_params["map_session_id"]
        return self.store.get_session(session_id, token)


def _static_text(asset_name: str) -> str:
    return _static_path(asset_name).read_text(encoding="utf-8")


def _static_path(asset_name: str) -> Path:
    root = resources.files("ezt_mcp.map_component.static")
    return Path(str(root.joinpath(asset_name)))


def _error_response(exc: MapVisualizationError, *, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": exc.to_error()}, status_code=status_code)


def _status_for_error(exc: MapVisualizationError) -> int:
    if exc.code in {"INVALID_TS", "UNSUPPORTED_OPERATION", "AMBIGUOUS_TAL"}:
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

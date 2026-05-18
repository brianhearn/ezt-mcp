"""Short-lived map visualization sessions for the Map Component."""

from __future__ import annotations

import asyncio
import copy
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from shapely.geometry import shape

from .part_layers import resolve_part_layer_tiles

DEFAULT_SESSION_TTL_SECONDS = 3600
DEFAULT_USER_ID = "default-user"


class MapVisualizationError(ValueError):
    """Structured map visualization request/session failure."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "retryable": False,
            "user_action_required": True,
        }


@dataclass
class MapVisualizationSession:
    """One browser-safe map visualization session."""

    map_session_id: str
    token: str
    mode: str
    active_tal_id: str
    active_tal_label: str | None
    ts_identity: dict[str, Any]
    render_payload: dict[str, Any]
    ts: dict[str, Any]
    presentation: dict[str, Any]
    public_base_url: str
    created_at: datetime
    expires_at: datetime
    state_resource_uri: str
    user_id: str = DEFAULT_USER_ID
    theme: str = "dark"
    selection_resource_uri: str | None = None
    pending_job_reference: dict[str, Any] | None = None
    committed_selection: dict[str, Any] | None = None
    active_selection_task_id: str | None = None
    updated_at: datetime | None = None

    @property
    def territory_count(self) -> int:
        return len(self.render_payload.get("geojson", {}).get("features", []))

    def response_result(
        self, *, public_base_url: str, session_exists: bool = False
    ) -> dict[str, Any]:
        map_url = (
            f"{public_base_url.rstrip('/')}/maps/session/"
            f"{self.map_session_id}/{self.token}"
        )
        result = {
            "map_session_id": self.map_session_id,
            "map_url": map_url,
            "state_resource_uri": self.state_resource_uri,
            "expires_at": _isoformat_z(self.expires_at),
            "ts_identity": self.ts_identity,
            "active_tal_summary": {
                "tal_id": self.active_tal_id,
                "tal_label": self.active_tal_label,
                "mode": self.mode,
                "territory_count": self.territory_count,
            },
            "session_exists": session_exists,
            "presentation": {
                "preferred_open": "new_tab",
                "embed_status": "experimental",
                "open_in_new_tab_recommended": True,
            },
        }
        if self.selection_resource_uri:
            result["selection_resource_uri"] = self.selection_resource_uri
        return result

    def state_payload(self) -> dict[str, Any]:
        return _drop_none(
            {
                "map_session_id": self.map_session_id,
                "user_id": self.user_id,
                "mode": self.mode,
                "status": "active" if datetime.now(tz=UTC) < self.expires_at else "expired",
                "active_tal_id": self.active_tal_id,
                "active_tal_label": self.active_tal_label,
                "available_tals": self.render_payload.get("available_tals"),
                "territory_count": self.territory_count,
                "ts_identity": self.ts_identity,
                "pending_job_reference": self.pending_job_reference,
                "committed_selection": self.committed_selection,
                "active_selection_task_id": self.active_selection_task_id,
                "created_at": _isoformat_z(self.created_at),
                "updated_at": _isoformat_z(self.updated_at),
                "expires_at": _isoformat_z(self.expires_at),
            }
        )

    def refresh_from_request(
        self,
        request: Mapping[str, Any],
        *,
        public_base_url: str,
        now: datetime,
    ) -> None:
        mode = _validated_mode(request.get("mode") or self.mode)
        ts = request.get("ts")
        if not isinstance(ts, Mapping):
            raise MapVisualizationError(
                "INVALID_TS",
                "A full TS payload is required until TS handle resolution is implemented.",
            )
        req_presentation = (
            request.get("presentation")
            if isinstance(request.get("presentation"), Mapping)
            else {}
        )
        theme = _resolved_theme(req_presentation, fallback=self.theme)
        render_payload = build_render_payload(
            copy.deepcopy(dict(ts)),
            active_tal_id=request.get("active_tal_id"),
            mode=mode,
            presentation=req_presentation,
            public_base_url=public_base_url,
            theme=theme,
            part_layers=request.get("part_layers"),
            active_part_layer=request.get("active_part_layer"),
        )
        ttl_seconds = _bounded_ttl(request.get("expiry_seconds"))
        previous_mode = self.mode
        self.mode = mode
        self.theme = theme
        self.active_tal_id = render_payload["active_tal"]["tal_id"]
        self.active_tal_label = render_payload["active_tal"].get("label")
        self.ts_identity = render_payload["ts_identity"]
        self.render_payload = render_payload
        self.ts = copy.deepcopy(dict(ts))
        self.presentation = dict(req_presentation)
        self.public_base_url = public_base_url
        self.expires_at = now + timedelta(seconds=ttl_seconds)
        self.updated_at = now
        self.selection_resource_uri = (
            f"ezt://map-sessions/{self.map_session_id}/selection" if mode == "select" else None
        )
        if previous_mode != mode:
            self.committed_selection = None
            if mode != "select":
                self.active_selection_task_id = None


@dataclass
class _SessionWithExistence:
    session: MapVisualizationSession
    session_exists: bool


@dataclass
class InMemoryMapSessionStore:
    """Process-local map session store for the dev/test visualization loop.

    The store enforces one active browser session per user in-process. Production
    will move this to the transient DB, but the public contract and MC event flow
    are intentionally represented here first.
    """

    _sessions: dict[str, MapVisualizationSession] = field(default_factory=dict)
    _session_by_user: dict[str, str] = field(default_factory=dict)
    _event_queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = field(default_factory=dict)

    def create_session(
        self,
        request: Mapping[str, Any],
        *,
        public_base_url: str,
        user_id: str | None = None,
        now: datetime | None = None,
    ) -> MapVisualizationSession:
        return self.create_or_update_session(
            request,
            public_base_url=public_base_url,
            user_id=user_id,
            now=now,
        ).session

    def create_or_update_session(
        self,
        request: Mapping[str, Any],
        *,
        public_base_url: str,
        user_id: str | None = None,
        now: datetime | None = None,
    ) -> _SessionWithExistence:
        now = now or datetime.now(tz=UTC)
        user_id = _normal_user_id(user_id)
        existing = self._active_session_for_user(user_id, now=now)
        if existing is not None:
            previous_mode = existing.mode
            existing.refresh_from_request(request, public_base_url=public_base_url, now=now)
            self.publish_event(
                existing.map_session_id,
                {
                    "type": "tal_updated",
                    "map_session_id": existing.map_session_id,
                    "active_tal_id": existing.active_tal_id,
                    "ts_identity": existing.ts_identity,
                    "created_at": _isoformat_z(now),
                },
            )
            if previous_mode != existing.mode:
                self.publish_event(
                    existing.map_session_id,
                    {
                        "type": "mode_changed",
                        "map_session_id": existing.map_session_id,
                        "mode": existing.mode,
                        "created_at": _isoformat_z(now),
                    },
                )
            return _SessionWithExistence(existing, True)

        mode = _validated_mode(request.get("mode") or "view")
        ts = request.get("ts")
        if not isinstance(ts, Mapping):
            raise MapVisualizationError(
                "INVALID_TS",
                "A full TS payload is required until TS handle resolution is implemented.",
            )
        ts_copy = copy.deepcopy(dict(ts))
        req_presentation = (
            request.get("presentation")
            if isinstance(request.get("presentation"), Mapping)
            else {}
        )
        theme = _resolved_theme(req_presentation)
        render_payload = build_render_payload(
            ts_copy,
            active_tal_id=request.get("active_tal_id"),
            mode=mode,
            presentation=req_presentation,
            public_base_url=public_base_url,
            theme=theme,
            part_layers=request.get("part_layers"),
            active_part_layer=request.get("active_part_layer"),
        )
        ttl_seconds = _bounded_ttl(request.get("expiry_seconds"))
        map_session_id = f"msess_{secrets.token_urlsafe(16)}"
        # Keep the browser token short enough that chat/control UIs do not
        # redact it with an ellipsis when sharing a dev/test map URL. 9 random
        # bytes is ~72 bits of entropy, acceptable for this short-lived viewer
        # token while the durable production token model is still being built.
        token = secrets.token_urlsafe(9)
        selection_uri = None
        if mode == "select":
            selection_uri = f"ezt://map-sessions/{map_session_id}/selection"
        session = MapVisualizationSession(
            map_session_id=map_session_id,
            token=token,
            mode=mode,
            theme=theme,
            active_tal_id=render_payload["active_tal"]["tal_id"],
            active_tal_label=render_payload["active_tal"].get("label"),
            ts_identity=render_payload["ts_identity"],
            render_payload=render_payload,
            ts=ts_copy,
            presentation=dict(req_presentation),
            public_base_url=public_base_url,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            state_resource_uri=f"ezt://map-sessions/{map_session_id}/state",
            selection_resource_uri=selection_uri,
            user_id=user_id,
        )
        self._sessions[map_session_id] = session
        self._session_by_user[user_id] = map_session_id
        self.publish_event(
            map_session_id,
            {
                "type": "session_created",
                "map_session_id": map_session_id,
                "mode": mode,
                "active_tal_id": session.active_tal_id,
                "created_at": _isoformat_z(now),
            },
        )
        return _SessionWithExistence(session, False)

    def get_session(self, map_session_id: str, token: str | None = None) -> MapVisualizationSession:
        session = self._sessions.get(map_session_id)
        if session is None:
            raise MapVisualizationError(
                "INVALID_TS_HANDLE",
                "Map visualization session was not found or the token is invalid.",
            )
        if token is not None and not _safe_token_equal(session.token, token):
            raise MapVisualizationError(
                "INVALID_TS_HANDLE",
                "Map visualization session was not found or the token is invalid.",
            )
        if datetime.now(tz=UTC) >= session.expires_at:
            self._sessions.pop(map_session_id, None)
            self._session_by_user.pop(session.user_id, None)
            self.publish_event(
                map_session_id,
                {
                    "type": "session_expired",
                    "map_session_id": map_session_id,
                    "created_at": _isoformat_z(datetime.now(tz=UTC)),
                },
            )
            raise MapVisualizationError(
                "INVALID_TS_HANDLE",
                "Map visualization session has expired.",
                {"map_session_id": map_session_id},
            )
        return session

    def get_state(self, map_session_id: str) -> dict[str, Any]:
        return self.get_session(map_session_id).state_payload()

    def set_state(
        self,
        map_session_id: str,
        *,
        mode: str | None = None,
        active_tal_id: str | None = None,
        pending_job_reference: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(tz=UTC)
        session = self.get_session(map_session_id)
        previous_mode = session.mode
        previous_tal = session.active_tal_id
        if mode is not None:
            session.mode = _validated_mode(mode)
            session.render_payload["mode"] = session.mode
            session.selection_resource_uri = (
                f"ezt://map-sessions/{session.map_session_id}/selection"
                if session.mode == "select"
                else None
            )
        if active_tal_id is not None:
            self._set_active_tal(session, active_tal_id)
        if pending_job_reference is not None:
            session.pending_job_reference = dict(pending_job_reference)
        session.updated_at = now
        if previous_tal != session.active_tal_id:
            self.publish_event(
                map_session_id,
                {
                    "type": "tal_updated",
                    "map_session_id": map_session_id,
                    "active_tal_id": session.active_tal_id,
                    "ts_identity": session.ts_identity,
                    "created_at": _isoformat_z(now),
                },
            )
        if previous_mode != session.mode:
            self.publish_event(
                map_session_id,
                {
                    "type": "mode_changed",
                    "map_session_id": map_session_id,
                    "mode": session.mode,
                    "created_at": _isoformat_z(now),
                },
            )
        if previous_mode == session.mode and previous_tal == session.active_tal_id:
            self.publish_event(
                map_session_id,
                {
                    "type": "state_updated",
                    "map_session_id": map_session_id,
                    "state": session.state_payload(),
                    "created_at": _isoformat_z(now),
                },
            )
        return session.state_payload()

    def set_active_selection_task(
        self,
        map_session_id: str,
        selection_task_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(tz=UTC)
        session = self.get_session(map_session_id)
        session.active_selection_task_id = selection_task_id
        session.mode = "select"
        session.render_payload["mode"] = "select"
        session.selection_resource_uri = f"ezt://part-selections/{selection_task_id}"
        session.updated_at = now
        self.publish_event(
            map_session_id,
            {
                "type": "selection_prompt",
                "map_session_id": map_session_id,
                "selection_task_id": selection_task_id,
                "selection_resource_uri": session.selection_resource_uri,
                "created_at": _isoformat_z(now),
            },
        )
        return session.state_payload()

    def commit_selection(
        self,
        map_session_id: str,
        selection: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(tz=UTC)
        session = self.get_session(map_session_id)
        if session.mode != "select":
            raise MapVisualizationError(
                "UNSUPPORTED_OPERATION",
                "Selections can only be committed while the map session is in select mode.",
                {"map_session_id": map_session_id, "mode": session.mode},
            )
        part_ids = selection.get("part_ids")
        if not isinstance(part_ids, list) or not all(
            isinstance(item, str) and item for item in part_ids
        ):
            raise MapVisualizationError(
                "INVALID_SELECTION",
                "Selection commit requires a non-empty part_ids array of strings.",
            )
        payload = {
            "type": "map_selection",
            "part_layer": selection.get("part_layer"),
            "part_ids": list(dict.fromkeys(part_ids)),
            "committed_at": _isoformat_z(now),
            "job_id": selection.get("job_id"),
            "selection_task_id": selection.get("selection_task_id") or session.active_selection_task_id,
            "selection_method": selection.get("selection_method"),
        }
        session.committed_selection = _drop_none(payload)
        session.updated_at = now
        self.publish_event(
            map_session_id,
            {
                "type": "selection_committed",
                "map_session_id": map_session_id,
                "selection": session.committed_selection,
                "created_at": _isoformat_z(now),
            },
        )
        return session.committed_selection

    def get_selection(self, map_session_id: str) -> dict[str, Any]:
        session = self.get_session(map_session_id)
        if session.committed_selection is None:
            raise MapVisualizationError(
                "INVALID_TS_HANDLE",
                "No committed selection is available for this map session yet.",
                {"map_session_id": map_session_id},
            )
        return session.committed_selection

    def subscribe(self, map_session_id: str) -> asyncio.Queue[dict[str, Any]]:
        # Validate session id but do not require browser token for server-side MCP/SSE wiring.
        session = self.get_session(map_session_id)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._event_queues.setdefault(map_session_id, set()).add(queue)
        queue.put_nowait(
            {
                "type": "connected",
                "map_session_id": map_session_id,
                "state": session.state_payload(),
                "created_at": _isoformat_z(datetime.now(tz=UTC)),
            }
        )
        return queue

    def unsubscribe(self, map_session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        queues = self._event_queues.get(map_session_id)
        if not queues:
            return
        queues.discard(queue)
        if not queues:
            self._event_queues.pop(map_session_id, None)

    def publish_event(self, map_session_id: str, event: Mapping[str, Any]) -> None:
        queues = list(self._event_queues.get(map_session_id, set()))
        for queue in queues:
            try:
                queue.put_nowait(dict(event))
            except asyncio.QueueFull:
                # Drop stale clients rather than blocking server-side tool work.
                self.unsubscribe(map_session_id, queue)

    def _set_active_tal(self, session: MapVisualizationSession, active_tal_id: str) -> None:
        requested_tal = str(active_tal_id or "").strip()
        if not requested_tal:
            raise MapVisualizationError(
                "UNKNOWN_TAL_ID",
                "active_tal_id is required to switch the active TAL.",
            )
        render_payload = build_render_payload(
            copy.deepcopy(session.ts),
            active_tal_id=requested_tal,
            mode=session.mode,
            presentation=session.presentation,
            public_base_url=session.public_base_url,
            theme=session.theme,
        )
        session.active_tal_id = render_payload["active_tal"]["tal_id"]
        session.active_tal_label = render_payload["active_tal"].get("label")
        session.ts_identity = render_payload["ts_identity"]
        session.render_payload = render_payload

    def _active_session_for_user(
        self, user_id: str, *, now: datetime
    ) -> MapVisualizationSession | None:
        session_id = self._session_by_user.get(user_id)
        if not session_id:
            return None
        session = self._sessions.get(session_id)
        if session is None or now >= session.expires_at:
            self._session_by_user.pop(user_id, None)
            if session is not None:
                self._sessions.pop(session_id, None)
            return None
        return session


def build_render_payload(
    ts: Mapping[str, Any],
    *,
    active_tal_id: Any = None,
    mode: str = "view",
    presentation: Mapping[str, Any] | None = None,
    public_base_url: str = "",
    theme: str = "dark",
    part_layers: Any = None,
    active_part_layer: Any = None,
) -> dict[str, Any]:
    """Extract the active TAL as a browser render payload."""
    if ts.get("type") != "FeatureCollection" or not isinstance(ts.get("features"), list):
        raise MapVisualizationError(
            "INVALID_TS",
            "TS must be a GeoJSON FeatureCollection with a features array.",
        )
    properties = ts.get("properties") if isinstance(ts.get("properties"), Mapping) else {}
    requested_tal = str(active_tal_id or properties.get("active_tal_id") or "").strip()
    if not requested_tal:
        requested_tal = _single_tal_id(ts)
    if not requested_tal:
        raise MapVisualizationError(
            "AMBIGUOUS_TAL",
            "active_tal_id is required when no single TAL can be inferred from the TS.",
        )

    point_features = [feature for feature in ts["features"] if _is_point_feature(feature)]

    active_features = [
        feature
        for feature in ts["features"]
        if isinstance(feature, Mapping)
        and isinstance(feature.get("properties"), Mapping)
        and not _is_point_feature(feature)
        and feature["properties"].get("tal_id") == requested_tal
        and feature.get("geometry")
    ]
    if not active_features:
        raise MapVisualizationError(
            "UNKNOWN_TAL_ID",
            "No territory features were found for the requested TAL.",
            {"active_tal_id": requested_tal},
        )

    reference_features = [
        feature
        for feature in ts["features"]
        if isinstance(feature, Mapping)
        and isinstance(feature.get("properties"), Mapping)
        and not _is_point_feature(feature)
        and feature["properties"].get("tal_id") != requested_tal
        and feature.get("geometry")
    ]

    presentation_payload = _presentation_payload(
        ts_properties=properties,
        request_presentation=presentation or {},
        view_name=_view_name(presentation, mode=mode),
        mode=mode,
    )
    sorted_active_features = sorted(
        active_features,
        key=lambda feature: _render_priority(feature),
        reverse=True,
    )
    clean_active_features = [
        _feature_for_render(feature, index, role="active")
        for index, feature in enumerate(sorted_active_features)
    ]
    clean_reference_features = [
        _feature_for_render(feature, index, role="reference")
        for index, feature in enumerate(reference_features)
    ]
    clean_point_features = [
        _point_feature_for_render(feature, index)
        for index, feature in enumerate(point_features)
    ]
    bounds = _feature_collection_bounds(
        clean_active_features + clean_reference_features + clean_point_features
    )
    tal_label = _tal_label(properties, requested_tal)
    default_part_layer = _tal_part_layer(properties, requested_tal)
    part_layer_tiles, resolved_active_part_layer = resolve_part_layer_tiles(
        part_layers if part_layers is not None else properties.get("part_layers"),
        public_base_url=public_base_url,
        active_part_layer=active_part_layer or properties.get("active_part_layer"),
        default_part_layer=default_part_layer,
    )
    return {
        "map_session_id": None,
        "mode": mode,
        "theme": theme,
        "basemap": {
            "type": "pmtiles",
            "url": f"{public_base_url.rstrip('/')}/assets/tiles/us-basemap.pmtiles",
        },
        "ts_identity": _ts_identity(properties),
        "active_tal": {
            "tal_id": requested_tal,
            "label": tal_label,
            "territory_count": len(clean_active_features),
        },
        "available_tals": _available_tal_summaries(
            properties,
            clean_active_features + clean_reference_features,
            active_tal_id=requested_tal,
        ),
        "reference_tals": _reference_tal_summaries(
            properties,
            clean_reference_features,
            active_tal_id=requested_tal,
        ),
        "part_layers": part_layer_tiles,
        "active_part_layer": resolved_active_part_layer,
        "point_layers": _point_layer_summaries(properties, clean_point_features),
        "bounds": bounds,
        "presentation": presentation_payload,
        "geojson": {
            "type": "FeatureCollection",
            "features": clean_active_features,
        },
        "reference_geojson": {
            "type": "FeatureCollection",
            "features": clean_reference_features,
        },
        "point_geojson": {
            "type": "FeatureCollection",
            "features": clean_point_features,
        },
    }


DEFAULT_CHROME_LABELS: dict[str, str] = {
    "active_alignment_label": "Active alignment",
    "active_alignment_aria": "Active territory alignment",
    "reference_alignments_legend": "Other alignments (dimmed)",
    "switching_active_alignment_status": "Switching active alignment…",
    "active_alignment_updated_status": "Active alignment updated.",
    "loaded_multi_alignment_status": "Loaded. Use Active alignment to switch layers.",
}


PRESENTATION_TEMPLATES: dict[str, dict[str, Any]] = {
    "qa_verification": {
        "view_name": "qa_verification",
        "panel_template": "qa_verification",
        "show_panel": True,
        "show_legend": True,
        "debug_panel": True,
        "title": "Territory QA Verification",
        "subtitle": "Review generated geometry, counts, and map-render diagnostics.",
        "chrome_labels": DEFAULT_CHROME_LABELS,
    },
    "executive_review": {
        "view_name": "executive_review",
        "panel_template": "executive_review",
        "show_panel": True,
        "show_legend": True,
        "debug_panel": False,
        "title": "Territory Review",
        "subtitle": "Executive summary of the active territory alignment.",
        "chrome_labels": DEFAULT_CHROME_LABELS,
    },
    "selection": {
        "view_name": "selection",
        "panel_template": "selection",
        "show_panel": True,
        "show_legend": True,
        "debug_panel": False,
        "title": "Select Geography",
        "subtitle": "Choose parts on the map, then commit the selection.",
        "chrome_labels": DEFAULT_CHROME_LABELS,
    },
}


def _presentation_payload(
    *,
    ts_properties: Mapping[str, Any],
    request_presentation: Mapping[str, Any],
    view_name: str,
    mode: str,
) -> dict[str, Any]:
    template = copy.deepcopy(PRESENTATION_TEMPLATES.get(view_name, {}))
    if not template:
        template = copy.deepcopy(
            PRESENTATION_TEMPLATES["selection" if mode == "select" else "executive_review"]
        )
        template["view_name"] = view_name
    ts_view = _ts_presentation_view(ts_properties, view_name)
    overrides = request_presentation.get("style_overrides")
    if not isinstance(overrides, Mapping):
        overrides = {}
    merged = _deep_merge(template, ts_view)
    merged = _deep_merge(merged, dict(overrides))
    merged["view_name"] = view_name
    merged["style_overrides"] = dict(overrides)
    return merged


def _view_name(presentation: Mapping[str, Any] | None, *, mode: str) -> str:
    if isinstance(presentation, Mapping) and isinstance(presentation.get("view_name"), str):
        view_name = presentation["view_name"].strip()
        if view_name:
            return view_name
    return "selection" if mode == "select" else "executive_review"


def _ts_presentation_view(ts_properties: Mapping[str, Any], view_name: str) -> dict[str, Any]:
    presentation = ts_properties.get("presentation")
    if not isinstance(presentation, Mapping):
        return {}
    views = presentation.get("views")
    if isinstance(views, Mapping) and isinstance(views.get(view_name), Mapping):
        return dict(views[view_name])
    if isinstance(presentation.get(view_name), Mapping):
        return dict(presentation[view_name])
    return {}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _available_tal_summaries(
    ts_properties: Mapping[str, Any],
    features: list[Mapping[str, Any]],
    *,
    active_tal_id: str,
) -> list[dict[str, Any]]:
    counts = _tal_feature_counts(features)
    metadata = _tal_metadata(ts_properties)
    tal_ids = sorted(set(metadata) | set(counts))
    return [
        _drop_none(
            {
                "tal_id": tal_id,
                "tal_label": metadata.get(tal_id) or _tal_label(ts_properties, tal_id),
                "territory_count": counts.get(tal_id, 0),
                "is_active": tal_id == active_tal_id,
                "render_role": "active" if tal_id == active_tal_id else "reference",
            }
        )
        for tal_id in tal_ids
    ]


def _reference_tal_summaries(
    ts_properties: Mapping[str, Any],
    features: list[Mapping[str, Any]],
    *,
    active_tal_id: str,
) -> list[dict[str, Any]]:
    return [
        _drop_none(
            {
                "tal_id": item["tal_id"],
                "tal_label": item.get("tal_label"),
                "territory_count": item["territory_count"],
                "render_role": "reference",
            }
        )
        for item in _available_tal_summaries(
            ts_properties,
            features,
            active_tal_id=active_tal_id,
        )
        if item["tal_id"] != active_tal_id
    ]


def _is_point_feature(feature: Any) -> bool:
    if not isinstance(feature, Mapping) or not feature.get("geometry"):
        return False
    properties = (
        feature.get("properties") if isinstance(feature.get("properties"), Mapping) else {}
    )
    if properties.get("feature_kind") == "point" or properties.get("point_layer") is not None:
        return True
    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), Mapping) else {}
    return geometry.get("type") in {"Point", "MultiPoint"} and properties.get("tal_id") is None


def _point_feature_for_render(feature: Mapping[str, Any], index: int) -> dict[str, Any]:
    properties = dict(feature.get("properties") or {})
    properties.setdefault("feature_kind", "point")
    properties.setdefault("point_layer", "points")
    properties.setdefault(
        "_render_id",
        properties.get("point_id") or properties.get("account_id") or f"point-{index}",
    )
    properties.setdefault("_render_color", _palette_color(index))
    properties.setdefault(
        "_render_label",
        properties.get("label")
        or properties.get("name")
        or properties.get("account_name")
        or properties.get("point_id"),
    )
    return {
        "type": "Feature",
        "properties": _json_safe_properties(properties),
        "geometry": feature.get("geometry"),
    }


def _point_layer_summaries(
    ts_properties: Mapping[str, Any],
    point_features: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for feature in point_features:
        properties = (
            feature.get("properties") if isinstance(feature.get("properties"), Mapping) else {}
        )
        layer_id = str(properties.get("point_layer") or "points")
        counts[layer_id] = counts.get(layer_id, 0) + 1

    metadata: dict[str, dict[str, Any]] = {}
    layers = ts_properties.get("point_layers")
    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, Mapping):
                continue
            raw_id = (
                layer.get("point_layer")
                or layer.get("layer_id")
                or layer.get("id")
                or layer.get("name")
            )
            if raw_id is None:
                continue
            layer_id = str(raw_id)
            metadata[layer_id] = copy.deepcopy(dict(layer))

    layer_ids = list(metadata) + [layer_id for layer_id in counts if layer_id not in metadata]
    summaries: list[dict[str, Any]] = []
    for index, layer_id in enumerate(layer_ids):
        layer = metadata.get(layer_id, {})
        style = layer.get("style") if isinstance(layer.get("style"), Mapping) else {}
        classification = (
            layer.get("classification")
            if isinstance(layer.get("classification"), Mapping)
            else None
        )
        filters = (
            layer.get("filters")
            if isinstance(layer.get("filters"), list)
            else layer.get("filter")
        )
        summaries.append(
            _drop_none(
                {
                    "point_layer": layer_id,
                    "label": str(layer.get("label") or layer.get("title") or layer_id),
                    "feature_count": counts.get(layer_id, 0),
                    "default_visible": bool(
                        layer.get("default_visible", layer.get("visible", True))
                    ),
                    "minzoom": layer.get("minzoom"),
                    "maxzoom": layer.get("maxzoom"),
                    "search_fields": (
                        layer.get("search_fields")
                        if isinstance(layer.get("search_fields"), list)
                        else None
                    ),
                    "label_field": layer.get("label_field"),
                    "style": _drop_none(
                        {
                            "color": (
                                style.get("color")
                                or style.get("fill_color")
                                or style.get("stroke_color")
                                or _palette_color(index)
                            ),
                            "size": style.get("size"),
                            "opacity": style.get("opacity"),
                            "shape": style.get("shape"),
                        }
                    ),
                    "classification": (
                        copy.deepcopy(dict(classification)) if classification else None
                    ),
                    "filters": copy.deepcopy(filters) if filters else None,
                }
            )
        )
    return summaries


def _tal_feature_counts(features: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for feature in features:
        raw_properties = feature.get("properties")
        properties = raw_properties if isinstance(raw_properties, Mapping) else {}
        tal_id = properties.get("tal_id")
        if tal_id is not None:
            counts[str(tal_id)] = counts.get(str(tal_id), 0) + 1
    return counts


def _tal_metadata(ts_properties: Mapping[str, Any]) -> dict[str, str | None]:
    metadata: dict[str, str | None] = {}
    layers = ts_properties.get("territory_alignment_layers")
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, Mapping) and layer.get("tal_id") is not None:
                label = layer.get("label")
                metadata[str(layer["tal_id"])] = str(label) if label is not None else None
    return metadata


def _render_priority(feature: Mapping[str, Any]) -> tuple[int, int]:
    properties = feature.get("properties") if isinstance(feature.get("properties"), Mapping) else {}
    is_leaf = properties.get("is_leaf")
    if isinstance(is_leaf, str):
        leaf_rank = 1 if is_leaf.lower() == "true" else 0
    else:
        leaf_rank = 1 if is_leaf is True else 0
    try:
        depth = int(properties.get("depth") or 0)
    except (TypeError, ValueError):
        depth = 0
    return (leaf_rank, depth)


def _feature_for_render(
    feature: Mapping[str, Any],
    index: int,
    *,
    role: str = "active",
) -> dict[str, Any]:
    properties = dict(feature.get("properties") or {})
    properties.setdefault("_render_color", _palette_color(index))
    properties.setdefault(
        "_render_label",
        properties.get("label") or properties.get("territory_id"),
    )
    leaf_rank, depth = _render_priority(feature)
    properties.setdefault("_render_label_priority", (0 if leaf_rank else 100) + depth)
    properties["_render_tal_role"] = role
    return {
        "type": "Feature",
        "properties": _json_safe_properties(properties),
        "geometry": feature.get("geometry"),
    }


def _json_safe_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            safe[key] = value
        elif isinstance(value, (list, tuple, dict)):
            safe[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
        else:
            safe[key] = str(value)
    return safe


def _feature_collection_bounds(features: list[Mapping[str, Any]]) -> list[float]:
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for feature in features:
        geom = shape(feature["geometry"])
        bx0, by0, bx1, by1 = geom.bounds
        minx = min(minx, bx0)
        miny = min(miny, by0)
        maxx = max(maxx, bx1)
        maxy = max(maxy, by1)
    return [float(minx), float(miny), float(maxx), float(maxy)]


def _single_tal_id(ts: Mapping[str, Any]) -> str | None:
    tal_ids = {
        feature.get("properties", {}).get("tal_id")
        for feature in ts.get("features", [])
        if isinstance(feature, Mapping) and isinstance(feature.get("properties"), Mapping)
    }
    tal_ids.discard(None)
    return str(next(iter(tal_ids))) if len(tal_ids) == 1 else None


def _tal_part_layer(properties: Mapping[str, Any], tal_id: str) -> str | None:
    layers = properties.get("territory_alignment_layers")
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, Mapping) and layer.get("tal_id") == tal_id:
                part_layer = layer.get("part_layer")
                return str(part_layer) if part_layer is not None else None
    return None


def _tal_label(properties: Mapping[str, Any], tal_id: str) -> str | None:
    layers = properties.get("territory_alignment_layers")
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, Mapping) and layer.get("tal_id") == tal_id:
                label = layer.get("label")
                return str(label) if label is not None else None
    return None


def _ts_identity(properties: Mapping[str, Any]) -> dict[str, Any]:
    identity = (
        properties.get("ts_identity")
        if isinstance(properties.get("ts_identity"), Mapping)
        else {}
    )
    return {
        "ts_id": str(identity.get("ts_id") or properties.get("ts_id") or "ts-inline"),
        "revision": int(identity.get("revision") or properties.get("revision") or 1),
        "content_hash": str(identity.get("content_hash") or "sha256:" + "0" * 64),
        "updated_at": str(
            identity.get("updated_at")
            or datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
        ),
    }


def _palette_color(index: int) -> str:
    palette = ["#2F80ED", "#27AE60", "#F2994A", "#9B51E0", "#EB5757", "#56CCF2"]
    return palette[index % len(palette)]


def _bounded_ttl(value: Any) -> int:
    try:
        seconds = int(value or DEFAULT_SESSION_TTL_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_SESSION_TTL_SECONDS
    return max(60, min(seconds, 86400))


def _validated_mode(value: Any) -> str:
    mode = str(value or "view")
    if mode not in {"view", "select"}:
        raise MapVisualizationError(
            "UNSUPPORTED_OPERATION",
            "get_map_visualization mode must be 'view' or 'select'.",
            {"mode": mode},
        )
    return mode


def _normal_user_id(value: str | None) -> str:
    user_id = str(value or DEFAULT_USER_ID).strip()
    return user_id or DEFAULT_USER_ID


def _safe_token_equal(actual: str, supplied: str) -> bool:
    return secrets.compare_digest(actual.encode("utf-8"), str(supplied).encode("utf-8"))


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _resolved_theme(presentation: Mapping[str, Any], *, fallback: str = "dark") -> str:
    """Extract and validate the theme from presentation.style_overrides.theme."""
    overrides = presentation.get("style_overrides") if isinstance(presentation, Mapping) else None
    if isinstance(overrides, Mapping):
        raw = overrides.get("theme")
        if raw in ("dark", "light"):
            return raw
    return fallback


def _isoformat_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

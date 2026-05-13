"""Short-lived map visualization sessions for the Map Component."""

from __future__ import annotations

import copy
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from shapely.geometry import shape

DEFAULT_SESSION_TTL_SECONDS = 3600


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


@dataclass(frozen=True)
class MapVisualizationSession:
    """One browser-safe map visualization session."""

    map_session_id: str
    token: str
    mode: str
    active_tal_id: str
    active_tal_label: str | None
    ts_identity: dict[str, Any]
    render_payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    state_resource_uri: str
    selection_resource_uri: str | None = None

    @property
    def territory_count(self) -> int:
        return len(self.render_payload.get("geojson", {}).get("features", []))

    def response_result(self, *, public_base_url: str) -> dict[str, Any]:
        map_url = (
            f"{public_base_url.rstrip('/')}/maps/session/"
            f"{self.map_session_id}?token={self.token}"
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
        return {
            "map_session_id": self.map_session_id,
            "mode": self.mode,
            "status": "active" if datetime.now(tz=UTC) < self.expires_at else "expired",
            "active_tal_id": self.active_tal_id,
            "active_tal_label": self.active_tal_label,
            "territory_count": self.territory_count,
            "ts_identity": self.ts_identity,
            "created_at": _isoformat_z(self.created_at),
            "expires_at": _isoformat_z(self.expires_at),
        }


@dataclass
class InMemoryMapSessionStore:
    """Process-local map session store for the dev/test visualization loop.

    This is intentionally short-lived and will be replaced by the transient DB
    store when async job/session infrastructure lands.
    """

    _sessions: dict[str, MapVisualizationSession] = field(default_factory=dict)

    def create_session(
        self,
        request: Mapping[str, Any],
        *,
        public_base_url: str,
        now: datetime | None = None,
    ) -> MapVisualizationSession:
        now = now or datetime.now(tz=UTC)
        mode = str(request.get("mode") or "view")
        if mode not in {"view", "select"}:
            raise MapVisualizationError(
                "UNSUPPORTED_OPERATION",
                "get_map_visualization mode must be 'view' or 'select'.",
                {"mode": mode},
            )
        ts = request.get("ts")
        if not isinstance(ts, Mapping):
            raise MapVisualizationError(
                "INVALID_TS",
                "A full TS payload is required until TS handle resolution is implemented.",
            )
        ts_copy = copy.deepcopy(dict(ts))
        render_payload = build_render_payload(
            ts_copy,
            active_tal_id=request.get("active_tal_id"),
            mode=mode,
            presentation=(
                request.get("presentation") if isinstance(request.get("presentation"), Mapping) else {}
            ),
            public_base_url=public_base_url,
        )
        ttl_seconds = _bounded_ttl(request.get("expiry_seconds"))
        map_session_id = f"msess_{secrets.token_urlsafe(16)}"
        token = secrets.token_urlsafe(32)
        selection_uri = None
        if mode == "select":
            selection_uri = f"ezt://map-sessions/{map_session_id}/selection"
        session = MapVisualizationSession(
            map_session_id=map_session_id,
            token=token,
            mode=mode,
            active_tal_id=render_payload["active_tal"]["tal_id"],
            active_tal_label=render_payload["active_tal"].get("label"),
            ts_identity=render_payload["ts_identity"],
            render_payload=render_payload,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            state_resource_uri=f"ezt://map-sessions/{map_session_id}/state",
            selection_resource_uri=selection_uri,
        )
        self._sessions[map_session_id] = session
        return session

    def get_session(self, map_session_id: str, token: str) -> MapVisualizationSession:
        session = self._sessions.get(map_session_id)
        if session is None or not _safe_token_equal(session.token, token):
            raise MapVisualizationError(
                "INVALID_TS_HANDLE",
                "Map visualization session was not found or the token is invalid.",
            )
        if datetime.now(tz=UTC) >= session.expires_at:
            self._sessions.pop(map_session_id, None)
            raise MapVisualizationError(
                "INVALID_TS_HANDLE",
                "Map visualization session has expired.",
                {"map_session_id": map_session_id},
            )
        return session


def build_render_payload(
    ts: Mapping[str, Any],
    *,
    active_tal_id: Any = None,
    mode: str = "view",
    presentation: Mapping[str, Any] | None = None,
    public_base_url: str = "",
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

    features = [
        feature
        for feature in ts["features"]
        if isinstance(feature, Mapping)
        and isinstance(feature.get("properties"), Mapping)
        and feature["properties"].get("tal_id") == requested_tal
        and feature.get("geometry")
    ]
    if not features:
        raise MapVisualizationError(
            "UNKNOWN_TAL_ID",
            "No territory features were found for the requested TAL.",
            {"active_tal_id": requested_tal},
        )

    clean_features = [_feature_for_render(feature, index) for index, feature in enumerate(features)]
    bounds = _feature_collection_bounds(clean_features)
    tal_label = _tal_label(properties, requested_tal)
    return {
        "map_session_id": None,
        "mode": mode,
        "basemap": {
            "type": "pmtiles",
            "url": f"{public_base_url.rstrip('/')}/assets/tiles/us-basemap.pmtiles",
        },
        "ts_identity": _ts_identity(properties),
        "active_tal": {
            "tal_id": requested_tal,
            "label": tal_label,
            "territory_count": len(clean_features),
        },
        "bounds": bounds,
        "presentation": dict(presentation or {}),
        "geojson": {
            "type": "FeatureCollection",
            "features": clean_features,
        },
    }


def _feature_for_render(feature: Mapping[str, Any], index: int) -> dict[str, Any]:
    properties = dict(feature.get("properties") or {})
    properties.setdefault("_render_color", _palette_color(index))
    properties.setdefault(
        "_render_label",
        properties.get("label") or properties.get("territory_id"),
    )
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": feature.get("geometry"),
    }


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
        feature["properties"].get("tal_id")
        for feature in ts.get("features", [])
        if isinstance(feature, Mapping) and isinstance(feature.get("properties"), Mapping)
    }
    tal_ids = {str(tal_id) for tal_id in tal_ids if tal_id}
    return next(iter(tal_ids)) if len(tal_ids) == 1 else None


def _tal_label(properties: Mapping[str, Any], tal_id: str) -> str | None:
    layers = properties.get("territory_alignment_layers")
    if isinstance(layers, list):
        for layer in layers:
            if isinstance(layer, Mapping) and layer.get("tal_id") == tal_id:
                label = layer.get("label")
                return str(label) if label else None
    return None


def _ts_identity(properties: Mapping[str, Any]) -> dict[str, Any]:
    identity = properties.get("ts_identity")
    if isinstance(identity, Mapping):
        return dict(identity)
    return {
        "ts_id": str(properties.get("ts_id") or "ts-visualization"),
        "revision": int(properties.get("revision") or 0),
        "content_hash": str(
            properties.get("content_hash")
            or "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        ),
        "updated_at": str(properties.get("updated_at") or _isoformat_z(datetime.now(tz=UTC))),
    }


def _safe_token_equal(expected: str, actual: str) -> bool:
    if not actual or not actual.isascii():
        return False
    return secrets.compare_digest(expected, actual)


def _bounded_ttl(value: Any) -> int:
    try:
        seconds = int(value or DEFAULT_SESSION_TTL_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_SESSION_TTL_SECONDS
    return max(60, min(seconds, 86400))


def _palette_color(index: int) -> str:
    palette = [
        "#2F80ED",
        "#27AE60",
        "#F2994A",
        "#9B51E0",
        "#EB5757",
        "#00A3A3",
        "#F2C94C",
        "#56CCF2",
    ]
    return palette[index % len(palette)]


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

"""Direct Build orchestration.

This module wires the deterministic hierarchy and dissolve kernels into the
smallest useful Direct Build pipeline. It deliberately keeps TS persistence,
cache handles, and database-backed part lookup out of this layer for now; those
will sit around this core once the server tool is exposed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any, Mapping

from ezt_mcp.observability import timed_operation
from ezt_mcp.territory.dissolve import (
    DissolveOptions,
    GeometryDissolveBackend,
    dissolve_hierarchy_geometries,
)
from ezt_mcp.territory.hierarchy import materialize_assignment_tree

logger = logging.getLogger(__name__)


def build_direct_tal(
    request: Mapping[str, Any],
    part_geometries: Mapping[str, Any],
    *,
    backend: GeometryDissolveBackend | None = None,
    dissolve_options: DissolveOptions | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a Direct Build TAL to a TS and return a success payload.

    ``request`` follows ``schemas/direct_build.schema.json`` at the orchestration
    boundary. ``part_geometries`` is the already-fetched part geometry map keyed
    by public part ID. The DB-backed fetch/validation layer will call into this
    function after resolving ``part_layer``.
    """
    assignments = list(request.get("assignments") or [])
    part_layer = _required_string(request, "part_layer")
    tal_label = _required_string(request, "tal_label")
    tal_id = _resolve_tal_id(request, tal_label)
    timestamp = now or datetime.now(tz=UTC)

    with timed_operation(
        logger,
        "tools.direct_build",
        tal_id=tal_id,
        part_layer=part_layer,
        assignment_count=len(assignments),
    ):
        with timed_operation(logger, "tools.direct_build.materialize", tal_id=tal_id):
            hierarchy = materialize_assignment_tree(assignments, tal_id=tal_id)

        with timed_operation(
            logger,
            "tools.direct_build.dissolve",
            tal_id=tal_id,
            part_geometry_count=len(part_geometries),
        ):
            dissolved = dissolve_hierarchy_geometries(
                hierarchy,
                part_geometries,
                backend=backend,
                options=dissolve_options,
            )

        ts = _append_tal_to_ts(
            request.get("ts"),
            tal_id=tal_id,
            tal_label=tal_label,
            part_layer=part_layer,
            dissolved=dissolved,
            updated_at=timestamp,
        )
        ts_identity = _ts_identity(ts, previous_identity=_incoming_identity(request), now=timestamp)
        ts.setdefault("properties", {})["ts_identity"] = ts_identity

        warnings = [warning.to_dict() for warning in hierarchy.warnings]
        if hierarchy.rollup_nodes:
            warnings.append(
                {
                    "code": "ROLLUP_TERRITORIES_CREATED",
                    "message": "Created hierarchy rollup territories from territory_path values.",
                }
            )

        return {
            "ok": True,
            "result": {
                "ts": ts,
                "ts_identity": ts_identity,
                "tal_id": tal_id,
                "territory_count": len(dissolved.territories),
                "assignment_summary": {
                    "assigned_part_count": len(
                        {part_id for node in hierarchy.leaf_nodes for part_id in node.part_ids}
                    ),
                    "unassigned_part_count": 0,
                },
                "hierarchy_summary": hierarchy.summary(),
                "geometry_summary": dissolved.summary(),
                "repair_summary": {
                    "holes_filled": 0,
                    "contiguity_repairs": 0,
                    "changed_part_ids": [],
                },
                "invalid_parts": [],
            },
            "warnings": warnings,
        }


def _append_tal_to_ts(
    source_ts: Any,
    *,
    tal_id: str,
    tal_label: str,
    part_layer: str,
    dissolved: Any,
    updated_at: datetime,
) -> dict[str, Any]:
    ts = copy.deepcopy(source_ts) if isinstance(source_ts, Mapping) else None
    if not ts:
        ts = {"type": "FeatureCollection", "features": [], "properties": {}}
    if ts.get("type") != "FeatureCollection":
        raise ValueError("ts must be a GeoJSON FeatureCollection")

    ts.setdefault("features", [])
    ts.setdefault("properties", {})
    features = [territory.to_geojson_feature() for territory in dissolved.territories]
    ts["features"].extend(features)

    tal_metadata = {
        "tal_id": tal_id,
        "label": tal_label,
        "part_layer": part_layer,
        "max_depth": max((territory.depth for territory in dissolved.territories), default=0),
        "territory_count": len(dissolved.territories),
        "geometry_backend": dissolved.backend,
        "bbox": list(dissolved.bbox) if dissolved.bbox is not None else None,
        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
    }
    properties = ts["properties"]
    properties.setdefault("territory_alignment_layers", [])
    properties["territory_alignment_layers"].append(tal_metadata)
    properties["active_tal_id"] = tal_id
    return ts


def _ts_identity(
    ts: Mapping[str, Any],
    *,
    previous_identity: Mapping[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    ts_id = str((previous_identity or {}).get("ts_id") or "ts-direct-build")
    revision = int((previous_identity or {}).get("revision") or 0) + 1
    return {
        "ts_id": ts_id,
        "revision": revision,
        "content_hash": _content_hash(ts),
        "updated_at": now.isoformat().replace("+00:00", "Z"),
    }


def _content_hash(ts: Mapping[str, Any]) -> str:
    canonical_ts = copy.deepcopy(dict(ts))
    properties = canonical_ts.setdefault("properties", {})
    properties.pop("ts_identity", None)
    encoded = json.dumps(canonical_ts, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _incoming_identity(request: Mapping[str, Any]) -> Mapping[str, Any] | None:
    ts = request.get("ts")
    if isinstance(ts, Mapping):
        properties = ts.get("properties")
        if isinstance(properties, Mapping):
            identity = properties.get("ts_identity")
            if isinstance(identity, Mapping):
                return identity
    return None


def _required_string(request: Mapping[str, Any], key: str) -> str:
    value = request.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"{key} is required")
    return str(value).strip()


def _resolve_tal_id(request: Mapping[str, Any], tal_label: str) -> str:
    requested_tal_id = str(request.get("tal_id") or request.get("requested_tal_id") or "").strip()
    if not requested_tal_id:
        return _stable_tal_id(tal_label)
    _validate_tal_id(requested_tal_id)
    _validate_tal_id_available(request.get("ts"), requested_tal_id)
    return requested_tal_id


def _validate_tal_id(tal_id: str) -> None:
    if len(tal_id) > 128:
        raise ValueError("tal_id must be 128 characters or fewer")
    if not all(character.isalnum() or character in {"-", "_"} for character in tal_id):
        raise ValueError("tal_id may contain only letters, numbers, hyphen, and underscore")


def _validate_tal_id_available(source_ts: Any, tal_id: str) -> None:
    if not isinstance(source_ts, Mapping):
        return
    properties = source_ts.get("properties")
    existing_tal_ids: set[str] = set()
    if isinstance(properties, Mapping):
        for layer in properties.get("territory_alignment_layers") or []:
            if isinstance(layer, Mapping) and layer.get("tal_id") is not None:
                existing_tal_ids.add(str(layer["tal_id"]))
        if properties.get("active_tal_id") is not None:
            existing_tal_ids.add(str(properties["active_tal_id"]))
    for feature in source_ts.get("features") or []:
        if isinstance(feature, Mapping):
            feature_properties = feature.get("properties")
            if isinstance(feature_properties, Mapping) and feature_properties.get("tal_id") is not None:
                existing_tal_ids.add(str(feature_properties["tal_id"]))
    if tal_id in existing_tal_ids:
        raise ValueError(f"tal_id already exists in the source TS: {tal_id}")


def _stable_tal_id(label: str) -> str:
    slug = "".join(character if character.isalnum() else "-" for character in label.casefold())
    slug = "-".join(part for part in slug.split("-") if part)
    return f"tal-{slug or 'direct-build'}"

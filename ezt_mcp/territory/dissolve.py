"""Geometry dissolve kernels for territory hierarchies.

The public functions in this module intentionally hide the concrete geometry
engine behind a tiny backend boundary. V1 uses Shapely in-process for small and
medium Direct Build requests; the call sites should not care if a future version
switches large dissolves to PostGIS ``ST_UnaryUnion``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from ezt_mcp.observability import timed_operation
from ezt_mcp.territory.hierarchy import TerritoryHierarchy, TerritoryNode

logger = logging.getLogger(__name__)


class DissolveValidationError(ValueError):
    """Structured validation failure for geometry dissolve."""

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


class GeometryDissolveBackend(Protocol):
    """Backend contract for territory geometry unions."""

    name: str

    def union(
        self,
        geometries: Sequence[BaseGeometry],
        *,
        operation: str,
        context: Mapping[str, Any] | None = None,
    ) -> BaseGeometry:
        """Union geometries and return a valid polygonal geometry."""


@dataclass(frozen=True)
class TerritoryGeometry:
    """Dissolved geometry and agent-friendly properties for one territory node."""

    territory_id: str
    label: str
    tal_id: str
    depth: int
    parent_territory_id: str | None
    is_leaf: bool
    part_ids: tuple[str, ...]
    geometry: BaseGeometry
    geometry_simple: BaseGeometry
    bbox: tuple[float, float, float, float]

    def properties(self) -> dict[str, Any]:
        return {
            "territory_id": self.territory_id,
            "label": self.label,
            "tal_id": self.tal_id,
            "depth": self.depth,
            "parent_territory_id": self.parent_territory_id,
            "is_leaf": self.is_leaf,
            "part_ids": list(self.part_ids),
            "bbox": list(self.bbox),
        }

    def to_geojson_feature(self, *, simplified: bool = False) -> dict[str, Any]:
        geometry = self.geometry_simple if simplified else self.geometry
        return {
            "type": "Feature",
            "properties": self.properties(),
            "geometry": mapping(geometry),
        }


@dataclass(frozen=True)
class DissolvedHierarchy:
    """Geometry results for all materialized hierarchy nodes."""

    tal_id: str
    territories: tuple[TerritoryGeometry, ...]
    backend: str

    @property
    def leaf_territories(self) -> tuple[TerritoryGeometry, ...]:
        return tuple(territory for territory in self.territories if territory.is_leaf)

    @property
    def rollup_territories(self) -> tuple[TerritoryGeometry, ...]:
        return tuple(territory for territory in self.territories if not territory.is_leaf)

    def to_feature_collection(self, *, simplified: bool = False) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "properties": {
                "tal_id": self.tal_id,
                "territory_count": len(self.territories),
                "leaf_territory_count": len(self.leaf_territories),
                "rollup_territory_count": len(self.rollup_territories),
                "geometry_backend": self.backend,
                "simplified": simplified,
            },
            "features": [
                territory.to_geojson_feature(simplified=simplified)
                for territory in self.territories
            ],
        }


@dataclass(frozen=True)
class ShapelyGeometryDissolveBackend:
    """In-process Shapely dissolve backend.

    This mirrors the proven EasyTerritoryAI pattern at a smaller abstraction
    level: validate before union, use unary union, then validate again. Spatial
    partitioning can be added inside this backend later without changing Direct
    Build orchestration.
    """

    name: str = "shapely"

    def union(
        self,
        geometries: Sequence[BaseGeometry],
        *,
        operation: str,
        context: Mapping[str, Any] | None = None,
    ) -> BaseGeometry:
        fields = {"geometry_count": len(geometries), "backend": self.name, **dict(context or {})}
        with timed_operation(logger, f"territory.dissolve.{operation}", **fields):
            cleaned = [_repair_polygonal_geometry(geometry) for geometry in geometries]
            cleaned = [geometry for geometry in cleaned if not geometry.is_empty]
            if not cleaned:
                raise DissolveValidationError(
                    "EMPTY_GEOMETRY",
                    "No non-empty polygon geometries were available to dissolve.",
                    dict(context or {}),
                )
            return _repair_polygonal_geometry(unary_union(cleaned))


def dissolve_hierarchy_geometries(
    hierarchy: TerritoryHierarchy,
    part_geometries: Mapping[str, BaseGeometry | Mapping[str, Any]],
    *,
    backend: GeometryDissolveBackend | None = None,
    simplify_tolerance: float = 0.0,
    overview_simplify_tolerance: float = 0.0,
) -> DissolvedHierarchy:
    """Dissolve leaf and rollup territory geometries for a hierarchy.

    ``part_geometries`` is keyed by public ``part_id`` and may contain either
    Shapely geometries or GeoJSON geometry dictionaries. Missing assigned parts
    are rejected before any union work starts so Direct Build can return a clear
    validation error.
    """
    backend = backend or ShapelyGeometryDissolveBackend()
    normalized_parts = _normalize_part_geometries(part_geometries)
    _validate_leaf_part_coverage(hierarchy, normalized_parts)

    with timed_operation(
        logger,
        "territory.dissolve.hierarchy",
        tal_id=hierarchy.tal_id,
        node_count=len(hierarchy.nodes),
        leaf_count=len(hierarchy.leaf_nodes),
        rollup_count=len(hierarchy.rollup_nodes),
        part_geometry_count=len(normalized_parts),
        backend=backend.name,
    ):
        by_node_id: dict[str, TerritoryGeometry] = {}

        for node in hierarchy.leaf_nodes:
            territory = _dissolve_leaf_node(
                node,
                hierarchy=hierarchy,
                part_geometries=normalized_parts,
                backend=backend,
                simplify_tolerance=simplify_tolerance,
                overview_simplify_tolerance=overview_simplify_tolerance,
            )
            by_node_id[territory.territory_id] = territory

        rollup_nodes = sorted(
            hierarchy.rollup_nodes,
            key=lambda candidate: candidate.depth,
            reverse=True,
        )
        for node in rollup_nodes:
            territory = _dissolve_rollup_node(
                node,
                hierarchy=hierarchy,
                dissolved_by_node_id=by_node_id,
                backend=backend,
                simplify_tolerance=simplify_tolerance,
                overview_simplify_tolerance=overview_simplify_tolerance,
            )
            by_node_id[territory.territory_id] = territory

        ordered = tuple(by_node_id[_required_territory_id(node)] for node in hierarchy.nodes)
        return DissolvedHierarchy(
            tal_id=hierarchy.tal_id,
            territories=ordered,
            backend=backend.name,
        )


def _dissolve_leaf_node(
    node: TerritoryNode,
    *,
    hierarchy: TerritoryHierarchy,
    part_geometries: Mapping[str, BaseGeometry],
    backend: GeometryDissolveBackend,
    simplify_tolerance: float,
    overview_simplify_tolerance: float,
) -> TerritoryGeometry:
    territory_id = _required_territory_id(node)
    part_ids = tuple(sorted(node.part_ids))
    geometry = backend.union(
        [part_geometries[part_id] for part_id in part_ids],
        operation="leaf",
        context={
            "tal_id": hierarchy.tal_id,
            "territory_id": territory_id,
            "part_count": len(part_ids),
        },
    )
    return _territory_geometry_from_node(
        node,
        hierarchy=hierarchy,
        part_ids=part_ids,
        geometry=geometry,
        simplify_tolerance=simplify_tolerance,
        overview_simplify_tolerance=overview_simplify_tolerance,
    )


def _dissolve_rollup_node(
    node: TerritoryNode,
    *,
    hierarchy: TerritoryHierarchy,
    dissolved_by_node_id: Mapping[str, TerritoryGeometry],
    backend: GeometryDissolveBackend,
    simplify_tolerance: float,
    overview_simplify_tolerance: float,
) -> TerritoryGeometry:
    territory_id = _required_territory_id(node)
    child_geometries = [
        dissolved_by_node_id[_required_territory_id(child)].geometry
        for child in node.children.values()
    ]
    geometry = backend.union(
        child_geometries,
        operation="rollup",
        context={
            "tal_id": hierarchy.tal_id,
            "territory_id": territory_id,
            "child_count": len(child_geometries),
            "depth": node.depth,
        },
    )
    return _territory_geometry_from_node(
        node,
        hierarchy=hierarchy,
        part_ids=(),
        geometry=geometry,
        simplify_tolerance=simplify_tolerance,
        overview_simplify_tolerance=overview_simplify_tolerance,
    )


def _territory_geometry_from_node(
    node: TerritoryNode,
    *,
    hierarchy: TerritoryHierarchy,
    part_ids: tuple[str, ...],
    geometry: BaseGeometry,
    simplify_tolerance: float,
    overview_simplify_tolerance: float,
) -> TerritoryGeometry:
    repaired = _repair_polygonal_geometry(geometry)
    if simplify_tolerance > 0:
        repaired = _repair_polygonal_geometry(
            repaired.simplify(simplify_tolerance, preserve_topology=True)
        )
    geometry_simple = repaired
    if overview_simplify_tolerance > 0:
        geometry_simple = _repair_polygonal_geometry(
            repaired.simplify(overview_simplify_tolerance, preserve_topology=True)
        )
    return TerritoryGeometry(
        territory_id=_required_territory_id(node),
        label=node.label,
        tal_id=hierarchy.tal_id,
        depth=node.depth,
        parent_territory_id=node.parent_territory_id,
        is_leaf=node.is_leaf,
        part_ids=part_ids,
        geometry=repaired,
        geometry_simple=geometry_simple,
        bbox=tuple(float(value) for value in repaired.bounds),
    )


def _normalize_part_geometries(
    part_geometries: Mapping[str, BaseGeometry | Mapping[str, Any]],
) -> dict[str, BaseGeometry]:
    normalized: dict[str, BaseGeometry] = {}
    for part_id, geometry in part_geometries.items():
        public_part_id = str(part_id).strip()
        if not public_part_id:
            raise DissolveValidationError(
                "INVALID_PART_GEOMETRY",
                "Part geometry mapping contains an empty part_id.",
            )
        normalized[public_part_id] = _coerce_geometry(geometry, part_id=public_part_id)
    return normalized


def _coerce_geometry(geometry: BaseGeometry | Mapping[str, Any], *, part_id: str) -> BaseGeometry:
    if isinstance(geometry, BaseGeometry):
        return _repair_polygonal_geometry(geometry)
    if isinstance(geometry, Mapping):
        try:
            return _repair_polygonal_geometry(shape(geometry))
        except Exception as exc:  # pragma: no cover - shapely error types vary
            raise DissolveValidationError(
                "INVALID_PART_GEOMETRY",
                f"Part {part_id!r} has invalid GeoJSON geometry.",
                {"part_id": part_id, "exception_type": exc.__class__.__name__},
            ) from exc
    raise DissolveValidationError(
        "INVALID_PART_GEOMETRY",
        f"Part {part_id!r} has unsupported geometry type.",
        {"part_id": part_id, "python_type": type(geometry).__name__},
    )


def _validate_leaf_part_coverage(
    hierarchy: TerritoryHierarchy,
    part_geometries: Mapping[str, BaseGeometry],
) -> None:
    required_part_ids = sorted(
        {part_id for node in hierarchy.leaf_nodes for part_id in node.part_ids}
    )
    missing = [part_id for part_id in required_part_ids if part_id not in part_geometries]
    if missing:
        raise DissolveValidationError(
            "UNKNOWN_PART_ID",
            "One or more assigned parts were not found in the selected part layer.",
            {
                "tal_id": hierarchy.tal_id,
                "missing_part_ids": missing,
                "missing_count": len(missing),
            },
        )


def _repair_polygonal_geometry(geometry: BaseGeometry) -> BaseGeometry:
    repaired = make_valid(geometry) if not geometry.is_valid else geometry
    if repaired.is_empty:
        return repaired

    polygons = [geom for geom in _iter_polygonal_parts(repaired) if not geom.is_empty]
    if not polygons:
        raise DissolveValidationError(
            "INVALID_PART_GEOMETRY",
            "Geometry repair did not produce polygonal output.",
            {"geometry_type": repaired.geom_type},
        )
    return MultiPolygon(polygons)


def _iter_polygonal_parts(geometry: BaseGeometry) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        yield from geometry.geoms
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _iter_polygonal_parts(part)


def _required_territory_id(node: TerritoryNode) -> str:
    if node.territory_id is None:  # pragma: no cover - hierarchy assigns IDs
        raise RuntimeError("territory_id has not been assigned")
    return node.territory_id

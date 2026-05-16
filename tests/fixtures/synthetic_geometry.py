"""Synthetic polygon fixtures for Direct Build and dissolve tests.

The fixtures intentionally use tiny axis-aligned squares so expected areas,
bounds, and rollup unions are obvious without depending on production geography.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from shapely.geometry import Polygon


def square(x: float, y: float, size: float = 1.0) -> Polygon:
    """Return a deterministic square polygon anchored at ``(x, y)``."""
    return Polygon(
        [
            (x, y),
            (x + size, y),
            (x + size, y + size),
            (x, y + size),
        ]
    )


def grid_square_geometries(
    part_ids: Iterable[str],
    *,
    columns: int = 10,
    size: float = 1.0,
    gap: float = 0.0,
    as_geojson: bool = False,
) -> dict[str, Polygon | dict[str, Any]]:
    """Return part geometries laid out in a deterministic row-major grid."""
    geometries: dict[str, Polygon | dict[str, Any]] = {}
    stride = size + gap
    for index, part_id in enumerate(part_ids):
        x = (index % columns) * stride
        y = (index // columns) * stride
        geometry = square(x, y, size=size)
        geometries[str(part_id)] = geometry.__geo_interface__ if as_geojson else geometry
    return geometries


class SyntheticPartsRepository:
    """Async repository test double for Direct Build jobs.

    It records each fetch call and returns only requested IDs that exist in the
    supplied geometry mapping, mirroring the production repository's missing-ID
    behavior before the dissolve layer raises ``UNKNOWN_PART_ID``.
    """

    def __init__(self, geometries: Mapping[str, Any]):
        self.geometries = dict(geometries)
        self.calls: list[tuple[str, list[str]]] = []

    async def fetch_part_geometries(self, part_layer: str, part_ids: list[str]) -> dict[str, Any]:
        self.calls.append((part_layer, list(part_ids)))
        return {
            part_id: self.geometries[part_id]
            for part_id in part_ids
            if part_id in self.geometries
        }

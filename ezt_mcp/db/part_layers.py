"""PostGIS-backed part-layer metadata repository."""

from __future__ import annotations

from typing import Any

from ezt_mcp.resources.part_layers import PartLayerMetadata


PART_LAYER_PUBLIC_COLUMNS = """
  part_layer,
  label,
  description,
  country_codes,
  admin_levels,
  geometry_type,
  srid,
  id_format,
  example_part_ids,
  part_count,
  capabilities,
  data_version,
  updated_at
"""


class AsyncpgPartLayerRepository:
    """Read safe part-layer metadata from ``geo.part_layers``.

    ``pool`` is expected to be an ``asyncpg.Pool`` or compatible object.
    """

    def __init__(self, pool: Any):
        self._pool = pool

    async def list_active_part_layers(self) -> list[PartLayerMetadata]:
        query = f"""
        select {PART_LAYER_PUBLIC_COLUMNS}
        from geo.part_layers
        where is_active = true
        order by country_codes, admin_levels, part_layer
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [PartLayerMetadata.from_record(dict(row)) for row in rows]

    async def get_part_layer(self, part_layer: str) -> PartLayerMetadata | None:
        query = f"""
        select {PART_LAYER_PUBLIC_COLUMNS}
        from geo.part_layers
        where is_active = true and part_layer = $1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, part_layer)
        if row is None:
            return None
        return PartLayerMetadata.from_record(dict(row))

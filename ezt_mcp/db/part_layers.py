"""PostGIS-backed part-layer metadata repository."""

from __future__ import annotations

from typing import Any

from ezt_mcp.resources.part_layers import DEFAULT_CAPABILITIES, PartLayerMetadata


class AsyncpgPartLayerRepository:
    """Read safe part-layer metadata from PostGIS.

    ``pool`` is expected to be an ``asyncpg.Pool`` or compatible object.

    The preferred future path is the metadata registry table ``geo.part_layers``.
    The current staging database predates that table and contains concrete
    curated geography tables only, so this repository includes a compatibility
    fallback that derives metadata from those known tables.
    """

    def __init__(self, pool: Any):
        self._pool = pool

    async def list_active_part_layers(self) -> list[PartLayerMetadata]:
        async with self._pool.acquire() as conn:
            if await _has_part_layers_registry(conn):
                rows = await conn.fetch(_REGISTRY_LIST_SQL)
                return [PartLayerMetadata.from_record(dict(row)) for row in rows]
            return await _list_staging_part_layers(conn)

    async def get_part_layer(self, part_layer: str) -> PartLayerMetadata | None:
        async with self._pool.acquire() as conn:
            if await _has_part_layers_registry(conn):
                row = await conn.fetchrow(_REGISTRY_GET_SQL, part_layer)
                if row is None:
                    return None
                return PartLayerMetadata.from_record(dict(row))
            layers = await _list_staging_part_layers(conn)
        for layer in layers:
            if layer.part_layer == part_layer:
                return layer
        return None


_REGISTRY_COLUMNS = """
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

_REGISTRY_LIST_SQL = f"""
select {_REGISTRY_COLUMNS}
from geo.part_layers
where is_active = true
order by country_codes, admin_levels, part_layer
"""

_REGISTRY_GET_SQL = f"""
select {_REGISTRY_COLUMNS}
from geo.part_layers
where is_active = true and part_layer = $1
"""


async def _has_part_layers_registry(conn: Any) -> bool:
    return bool(
        await conn.fetchval(
            """
            select exists (
              select 1
              from information_schema.tables
              where table_schema = 'geo' and table_name = 'part_layers'
            )
            """
        )
    )


async def _list_staging_part_layers(conn: Any) -> list[PartLayerMetadata]:
    """Derive layer metadata from the current staging ``geo`` tables."""
    table_names = set(
        await conn.fetch(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'geo'
            """
        )
    )
    # asyncpg Records do not hash as strings; normalize defensively for fake tests too.
    normalized_table_names = {
        row["table_name"] if hasattr(row, "keys") else row[0] for row in table_names
    }

    layers: list[PartLayerMetadata] = []

    if "us_postal" in normalized_table_names:
        count = await conn.fetchval("select count(*) from geo.us_postal")
        examples = await conn.fetch(
            """
            select zipcode
            from geo.us_postal
            where zipcode is not null
            order by zipcode
            limit 3
            """
        )
        layers.append(
            PartLayerMetadata(
                part_layer="us_zips",
                label="US ZIP Codes",
                description="United States ZIP Code polygons for territory construction.",
                country_codes=["US"],
                admin_levels=["postal"],
                geometry_type="MultiPolygon",
                srid=4326,
                part_count=count,
                id_format="5-digit ZIP Code string",
                example_part_ids=[row["zipcode"] for row in examples],
                capabilities=DEFAULT_CAPABILITIES.copy(),
                data_version="staging",
                updated_at="2026-05-08T00:00:00Z",
                aliases=["ZIP", "ZIP Code", "postal code"],
                source_name="EasyTerritory staging geo.us_postal",
                source_vintage="staging",
                id_format_notes="IDs are strings. Preserve leading zeroes.",
            )
        )

    if "us_county" in normalized_table_names:
        count = await conn.fetchval("select count(*) from geo.us_county")
        examples = await conn.fetch(
            """
            select fips
            from geo.us_county
            where fips is not null
            order by fips
            limit 3
            """
        )
        layers.append(
            PartLayerMetadata(
                part_layer="us_counties",
                label="US Counties",
                description="United States county polygons for territory construction.",
                country_codes=["US"],
                admin_levels=["county"],
                geometry_type="MultiPolygon",
                srid=4326,
                part_count=count,
                id_format="County FIPS string",
                example_part_ids=[row["fips"] for row in examples],
                capabilities=DEFAULT_CAPABILITIES.copy(),
                data_version="staging",
                updated_at="2026-05-08T00:00:00Z",
                aliases=["county", "counties", "FIPS"],
                source_name="EasyTerritory staging geo.us_county",
                source_vintage="staging",
                id_format_notes="IDs are county FIPS strings. Preserve leading zeroes.",
            )
        )

    if "ca_postal" in normalized_table_names:
        count = await conn.fetchval("select count(*) from geo.ca_postal")
        examples = await conn.fetch(
            """
            select postalcode
            from geo.ca_postal
            where postalcode is not null
            order by postalcode
            limit 3
            """
        )
        layers.append(
            PartLayerMetadata(
                part_layer="ca_fsa",
                label="Canada FSAs",
                description="Canadian Forward Sortation Area polygons for territory construction.",
                country_codes=["CA"],
                admin_levels=["postal"],
                geometry_type="MultiPolygon",
                srid=4326,
                part_count=count,
                id_format="3-character Forward Sortation Area string",
                example_part_ids=[row["postalcode"] for row in examples],
                capabilities=DEFAULT_CAPABILITIES.copy(),
                data_version="staging",
                updated_at="2026-05-08T00:00:00Z",
                aliases=["FSA", "Canadian postal", "Canada postal"],
                source_name="EasyTerritory staging geo.ca_postal",
                source_vintage="staging",
                id_format_notes="IDs are 3-character FSA strings, e.g. A0A.",
            )
        )

    return layers

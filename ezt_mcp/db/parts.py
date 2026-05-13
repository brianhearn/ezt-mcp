"""PostGIS-backed part query repository."""

from __future__ import annotations

from typing import Any

from ezt_mcp.resources.part_layers import UnknownPartLayerError
from ezt_mcp.tools.query_parts import QueryPartsError, QueryPartsRequest, encode_page_token


class AsyncpgPartsRepository:
    """Query safe part attributes from known geography tables.

    The repository intentionally uses a closed mapping of public part-layer IDs to
    internal tables/ID columns. Caller-supplied values are only passed as bind
    parameters, never interpolated into SQL. Geometry columns are excluded from
    public payloads and SELECT lists.
    """

    def __init__(self, pool: Any):
        self._pool = pool

    async def query_parts(self, request: QueryPartsRequest) -> dict[str, Any]:
        spec = _LAYER_SPECS.get(request.part_layer)
        if spec is None:
            raise UnknownPartLayerError(request.part_layer)

        async with self._pool.acquire() as conn:
            columns = await _safe_columns(conn, spec)
            if request.part_ids is not None:
                rows = await _query_by_part_ids(conn, spec, columns, request)
                total_count = await _count_by_part_ids(conn, spec, request.part_ids)
            else:
                rows = await _query_by_filter(conn, spec, columns, request)
                total_count = await _count_by_filter(conn, spec, columns, request.filter or {})

        parts = [_row_to_part(row, spec) for row in rows]
        result: dict[str, Any] = {
            "parts": parts,
            "total_count": total_count,
            "part_layer": request.part_layer,
            "warnings": [],
        }
        next_offset = request.offset + len(parts)
        if next_offset < total_count:
            result["next_page_token"] = encode_page_token(
                part_layer=request.part_layer, offset=next_offset
            )
        return result


_LAYER_SPECS: dict[str, dict[str, Any]] = {
    "us_zips": {
        "schema": "geo",
        "table_name": "us_postal",
        "table": "geo.us_postal",
        "id_column": "zipcode",
        "filter_aliases": {
            "state_abbr": ["state_abbr", "state", "stusps"],
            "county_name": ["county_name", "county", "countyname", "name"],
            "population": ["population", "pop", "total_population"],
        },
        "order_column": "zipcode",
    },
    "us_counties": {
        "schema": "geo",
        "table_name": "us_county",
        "table": "geo.us_county",
        "id_column": "fips",
        "filter_aliases": {
            "state_abbr": ["state_abbr", "state", "stusps"],
            "county_name": ["county_name", "county", "countyname", "name"],
            "population": ["population", "pop", "total_population"],
        },
        "order_column": "fips",
    },
    "ca_fsa": {
        "schema": "geo",
        "table_name": "ca_postal",
        "table": "geo.ca_postal",
        "id_column": "postalcode",
        "filter_aliases": {
            "state_abbr": ["province_abbr", "province", "prov", "state_abbr"],
            "county_name": ["city_name", "city", "municipality", "name"],
            "population": ["population", "pop", "total_population"],
        },
        "order_column": "postalcode",
    },
}

_GEOMETRY_COLUMN_NAMES = {"geom", "geometry", "geog", "geography", "wkb_geometry", "shape"}
_GEOMETRY_DATA_TYPES = {"USER-DEFINED"}


async def _safe_columns(conn: Any, spec: dict[str, Any]) -> list[str]:
    rows = await conn.fetch(
        """
        select column_name, data_type, udt_name
        from information_schema.columns
        where table_schema = $1 and table_name = $2
        order by ordinal_position
        """,
        spec["schema"],
        spec["table_name"],
    )
    columns: list[str] = []
    for row in rows:
        column_name = row["column_name"]
        data_type = row.get("data_type") if hasattr(row, "get") else row["data_type"]
        udt_name = row.get("udt_name") if hasattr(row, "get") else row["udt_name"]
        lowered = str(column_name).lower()
        if lowered in _GEOMETRY_COLUMN_NAMES:
            continue
        if data_type in _GEOMETRY_DATA_TYPES and str(udt_name).lower() in {"geometry", "geography"}:
            continue
        columns.append(str(column_name))

    if spec["id_column"] not in columns:
        raise QueryPartsError(
            "UNSUPPORTED_OPERATION",
            "Part layer table is missing its configured public ID column.",
            details={"part_layer": _public_layer_for_spec(spec)},
            user_action_required=False,
        )
    return columns


async def _query_by_part_ids(
    conn: Any, spec: dict[str, Any], columns: list[str], request: QueryPartsRequest
):
    sql = f"""
        select {_select_clause(columns)}
        from {spec["table"]}
        where {spec["id_column"]} = any($1::text[])
        order by {spec["order_column"]}
        limit $2 offset $3
    """
    return await conn.fetch(sql, request.part_ids, request.max_results, request.offset)


async def _count_by_part_ids(conn: Any, spec: dict[str, Any], part_ids: list[str]) -> int:
    sql = f"""
        select count(*)
        from {spec["table"]}
        where {spec["id_column"]} = any($1::text[])
    """
    return int(await conn.fetchval(sql, part_ids) or 0)


async def _query_by_filter(
    conn: Any, spec: dict[str, Any], columns: list[str], request: QueryPartsRequest
):
    where_sql, params = _build_filter_where(spec, columns, request.filter or {})
    params.extend([request.max_results, request.offset])
    limit_idx = len(params) - 1
    offset_idx = len(params)
    sql = f"""
        select {_select_clause(columns)}
        from {spec["table"]}
        {where_sql}
        order by {spec["order_column"]}
        limit ${limit_idx} offset ${offset_idx}
    """
    return await conn.fetch(sql, *params)


async def _count_by_filter(
    conn: Any, spec: dict[str, Any], columns: list[str], filter_payload: dict[str, Any]
) -> int:
    where_sql, params = _build_filter_where(spec, columns, filter_payload)
    sql = f"""
        select count(*)
        from {spec["table"]}
        {where_sql}
    """
    return int(await conn.fetchval(sql, *params) or 0)


def _build_filter_where(
    spec: dict[str, Any], columns: list[str], filter_payload: dict[str, Any]
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for key, value in filter_payload.items():
        if key == "part_layer":
            continue
        column = _resolve_filter_column(spec, columns, key)
        if column is None:
            raise QueryPartsError(
                "UNSUPPORTED_FILTER",
                f"Unsupported filter field for {key!r}.",
                details={"field": key, "supported_fields": sorted(spec["filter_aliases"])},
            )
        if isinstance(value, list):
            if not value:
                raise QueryPartsError(
                    "INVALID_REQUEST",
                    "Filter array values must not be empty.",
                    details={"field": key},
                )
            params.append(value)
            clauses.append(f"{column} = any(${len(params)}::text[])")
        elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
            params.append(value)
            if isinstance(value, (int, float)):
                clauses.append(f"{column} = ${len(params)}")
            else:
                clauses.append(f"{column} = ${len(params)}::text")
        else:
            raise QueryPartsError(
                "INVALID_REQUEST",
                "Filter values must be strings, numbers, or arrays.",
                details={"field": key},
            )
    if not clauses:
        raise QueryPartsError(
            "INVALID_REQUEST",
            "filter must include at least one supported predicate.",
            details={"field": "filter"},
        )
    return "where " + " and ".join(clauses), params


def _resolve_filter_column(spec: dict[str, Any], columns: list[str], key: str) -> str | None:
    column_set = set(columns)
    if key in column_set:
        return key
    for candidate in spec["filter_aliases"].get(key, []):
        if candidate in column_set:
            return candidate
    return None


def _select_clause(columns: list[str]) -> str:
    return ", ".join(columns)


def _row_to_part(row: Any, spec: dict[str, Any]) -> dict[str, Any]:
    record = dict(row)
    part_id = str(record.pop(spec["id_column"]))
    attributes = {key: value for key, value in record.items() if value is not None}
    return {"part_id": part_id, "attributes": attributes}


def _public_layer_for_spec(spec: dict[str, Any]) -> str:
    for part_layer, candidate in _LAYER_SPECS.items():
        if candidate is spec:
            return part_layer
    return "unknown"

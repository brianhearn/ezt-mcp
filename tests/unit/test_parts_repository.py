from __future__ import annotations

import asyncio

import pytest

from ezt_mcp.db.parts import AsyncpgPartsRepository
from ezt_mcp.tools.query_parts import QueryPartsError, QueryPartsRequest


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


class FakeConn:
    def __init__(self):
        self.fetch_calls = []
        self.fetchval_calls = []

    async def fetch(self, sql, *args):
        self.fetch_calls.append((sql, args))
        if "information_schema.columns" in sql:
            return [
                {"column_name": "zipcode", "data_type": "text", "udt_name": "text"},
                {"column_name": "state_abbr", "data_type": "text", "udt_name": "text"},
                {"column_name": "county_name", "data_type": "text", "udt_name": "text"},
                {"column_name": "population", "data_type": "integer", "udt_name": "int4"},
                {"column_name": "geom", "data_type": "USER-DEFINED", "udt_name": "geometry"},
            ]
        if "from geo.us_postal" in sql:
            return [
                {
                    "zipcode": "32301",
                    "state_abbr": "FL",
                    "county_name": "Leon",
                    "population": 28000,
                }
            ]
        return []

    async def fetchval(self, sql, *args):
        self.fetchval_calls.append((sql, args))
        return 1


def test_parts_repository_filter_query_uses_known_table_mapping_and_no_geometry():
    conn = FakeConn()
    repo = AsyncpgPartsRepository(FakePool(conn))

    result = asyncio.run(
        repo.query_parts(
            QueryPartsRequest(part_layer="us_zips", filter={"state_abbr": "FL"}, max_results=50)
        )
    )

    assert result["part_layer"] == "us_zips"
    assert result["total_count"] == 1
    assert result["parts"] == [
        {
            "part_id": "32301",
            "attributes": {"state_abbr": "FL", "county_name": "Leon", "population": 28000},
        }
    ]
    fetch_sql, fetch_args = conn.fetch_calls[1]
    assert "from geo.us_postal" in fetch_sql
    assert "geom" not in fetch_sql.lower()
    assert fetch_args == ("FL", 50, 0)


def test_parts_repository_id_list_query_uses_bind_parameters():
    conn = FakeConn()
    repo = AsyncpgPartsRepository(FakePool(conn))

    asyncio.run(
        repo.query_parts(
            QueryPartsRequest(part_layer="us_zips", part_ids=["32301", "32303"], max_results=100)
        )
    )

    fetch_sql, fetch_args = conn.fetch_calls[1]
    assert "where zipcode = any($1::text[])" in fetch_sql
    assert fetch_args == (["32301", "32303"], 100, 0)


def test_parts_repository_rejects_unsupported_filter_field():
    repo = AsyncpgPartsRepository(FakePool(FakeConn()))

    with pytest.raises(QueryPartsError) as exc:
        asyncio.run(
            repo.query_parts(
                QueryPartsRequest(part_layer="us_zips", filter={"table_name": "geo.us_postal"})
            )
        )

    assert exc.value.code == "UNSUPPORTED_FILTER"

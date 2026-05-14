from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import Polygon

from ezt_mcp.jobs import CustomerContext, InMemoryJobRepository
from ezt_mcp.resources.part_layers import UnknownPartLayerError
from ezt_mcp.tools.direct_build_job import run_direct_build_job


class FakePartsRepository:
    def __init__(self, geometries: dict[str, Any]):
        self.geometries = geometries
        self.calls = []

    async def fetch_part_geometries(self, part_layer: str, part_ids: list[str]):
        self.calls.append((part_layer, part_ids))
        return {part_id: self.geometries[part_id] for part_id in part_ids if part_id in self.geometries}


def square(x: float, y: float, size: float = 1.0) -> Polygon:
    return Polygon(
        [
            (x, y),
            (x + size, y),
            (x + size, y + size),
            (x, y + size),
        ]
    )


def test_run_direct_build_job_fetches_geometries_and_completes_job():
    context = CustomerContext(customer_id="cust-1")
    jobs = InMemoryJobRepository()
    now = datetime.now(tz=UTC) + timedelta(seconds=5)
    job = jobs.submit(context, tool_name="direct_build", now=now)
    parts = FakePartsRepository({"A": square(0, 0), "B": square(1, 0)})
    request = {
        "part_layer": "us_zips",
        "tal_label": "Test TAL",
        "assignments": [
            {"part_id": "A", "territory_path": ["North"]},
            {"part_id": "A", "territory_path": ["North"]},
            {"part_id": "B", "territory_path": ["South"]},
        ],
    }

    result = asyncio.run(
        run_direct_build_job(
            context=context,
            job_id=job.job_id,
            request=request,
            parts_repo=parts,
            jobs_repo=jobs,
        )
    )

    assert result["ok"] is True
    assert parts.calls == [("us_zips", ["A", "B"])]
    completed = jobs.get(context, job.job_id)
    assert completed.status == "completed"
    assert completed.result == result
    assert completed.counts["territory_count"] == 2


def test_run_direct_build_job_fails_with_structured_error_for_unknown_part_layer():
    class UnknownLayerPartsRepository:
        async def fetch_part_geometries(self, part_layer: str, part_ids: list[str]):
            raise UnknownPartLayerError(part_layer)

    context = CustomerContext(customer_id="cust-1")
    jobs = InMemoryJobRepository()
    job = jobs.submit(context, tool_name="direct_build")
    request = {
        "part_layer": "bogus",
        "tal_label": "Test TAL",
        "assignments": [{"part_id": "A", "territory_path": ["North"]}],
    }

    result = asyncio.run(
        run_direct_build_job(
            context=context,
            job_id=job.job_id,
            request=request,
            parts_repo=UnknownLayerPartsRepository(),
            jobs_repo=jobs,
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_PART_LAYER"
    assert jobs.get(context, job.job_id).status == "failed"


def test_run_direct_build_job_fails_with_structured_error_when_geometry_missing():
    context = CustomerContext(customer_id="cust-1")
    jobs = InMemoryJobRepository()
    job = jobs.submit(context, tool_name="direct_build")
    parts = FakePartsRepository({"A": square(0, 0)})
    request = {
        "part_layer": "us_zips",
        "tal_label": "Test TAL",
        "assignments": [
            {"part_id": "A", "territory_path": ["North"]},
            {"part_id": "B", "territory_path": ["South"]},
        ],
    }

    result = asyncio.run(
        run_direct_build_job(
            context=context,
            job_id=job.job_id,
            request=request,
            parts_repo=parts,
            jobs_repo=jobs,
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_PART_ID"
    failed = jobs.get(context, job.job_id)
    assert failed.status == "failed"
    assert failed.error["code"] == "UNKNOWN_PART_ID"

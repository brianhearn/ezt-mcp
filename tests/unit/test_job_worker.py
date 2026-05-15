from __future__ import annotations

import asyncio

from shapely.geometry import Polygon

from ezt_mcp.jobs import CustomerContext, InMemoryJobRepository
from ezt_mcp.workers import JobWorker


class FakePartsRepository:
    async def fetch_part_geometries(self, part_layer: str, part_ids: list[str]):
        return {part_id: square(index, 0).__geo_interface__ for index, part_id in enumerate(part_ids)}


def square(x: float, y: float, size: float = 1.0) -> Polygon:
    return Polygon([(x, y), (x + size, y), (x + size, y + size), (x, y + size)])


def test_job_worker_claims_queued_payload_and_publishes_progress():
    context = CustomerContext(customer_id="cust-1")
    repo = InMemoryJobRepository()
    job = repo.submit(
        context,
        tool_name="direct_build",
        request_payload={
            "part_layer": "us_zips",
            "tal_label": "Worker TAL",
            "assignments": [
                {"part_id": "A", "territory_path": ["North"]},
                {"part_id": "B", "territory_path": ["South"]},
            ],
            "map_session_id": "msess_1",
        },
    )
    events = []

    async def run_once():
        worker = JobWorker(
            context=context,
            jobs_repo=repo,
            parts_repo=FakePartsRepository(),
            progress_publisher=lambda *args: events.append(args),
        )
        claimed = await worker._claim_next()
        assert claimed.job_id == job.job_id
        await worker._run_job(claimed)

    asyncio.run(run_once())

    completed = repo.get(context, job.job_id)
    assert completed.status == "completed"
    assert completed.result["ok"] is True
    assert [event[1] for event in events] == ["running", "running", "running", "done"]

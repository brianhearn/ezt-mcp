from __future__ import annotations

import pytest

from ezt_mcp.jobs import CustomerContext
from ezt_mcp.part_selection import (
    InMemoryPartSelectionRepository,
    InvalidPartSelectionError,
    PartSelectionAccessError,
)


CONTEXT = CustomerContext(customer_id="00000000-0000-0000-0000-000000000001")


def test_part_selection_task_reference_and_resource_before_commit():
    repo = InMemoryPartSelectionRepository()

    task = repo.create(
        CONTEXT,
        user_id="monica",
        part_layer="us_zips",
        purpose="build_territory",
        prompt="Select ZIPs for North Florida.",
        map_session_id="msess_1",
        map_url="https://expertpack.ai/mcp/maps/session/msess_1/token",
        active_tal_id="tal-current",
        ts_identity={"ts_id": "ts-demo", "revision": 1},
    )

    reference = task.reference(session_exists=True)
    assert reference["status"] == "awaiting_user_selection"
    assert reference["selection_resource_uri"] == f"ezt://part-selections/{task.selection_task_id}"
    assert reference["session_exists"] is True

    resource = repo.get(CONTEXT, task.selection_task_id).resource()
    assert resource["status"] == "awaiting_user_selection"
    assert "selection" not in resource


def test_part_selection_commit_dedupes_parts_and_preserves_awareness_metadata():
    repo = InMemoryPartSelectionRepository()
    task = repo.create(
        CONTEXT,
        user_id="monica",
        part_layer="us_zips",
        purpose="return_list",
        map_session_id="msess_1",
        map_url="https://expertpack.ai/mcp/maps/session/msess_1/token",
    )

    committed = repo.commit(
        CONTEXT,
        task.selection_task_id,
        {
            "part_layer": "us_zips",
            "part_ids": ["32301", "32301", "32303"],
            "selection_method": "mixed",
        },
    )

    resource = committed.resource()
    assert resource["status"] == "committed"
    assert resource["selection"]["type"] == "part_selection"
    assert resource["selection"]["purpose"] == "return_list"
    assert resource["selection"]["part_ids"] == ["32301", "32303"]
    assert resource["selection"]["selection_method"] == "mixed"


def test_part_selection_is_customer_scoped_and_validates_layer_on_commit():
    repo = InMemoryPartSelectionRepository()
    task = repo.create(
        CONTEXT,
        user_id="monica",
        part_layer="us_zips",
        purpose="generic",
        map_session_id="msess_1",
        map_url="https://expertpack.ai/mcp/maps/session/msess_1/token",
    )

    with pytest.raises(PartSelectionAccessError):
        repo.get(CustomerContext(customer_id="other"), task.selection_task_id)

    with pytest.raises(InvalidPartSelectionError) as exc:
        repo.commit(
            CONTEXT,
            task.selection_task_id,
            {"part_layer": "us_counties", "part_ids": ["12073"]},
        )
    assert exc.value.code == "INVALID_SELECTION"

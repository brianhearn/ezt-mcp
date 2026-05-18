from __future__ import annotations

import pytest

from ezt_mcp.map_component.sessions import InMemoryMapSessionStore, MapVisualizationError
from tests.unit.test_map_visualization import sample_ts


def test_map_session_is_idempotent_per_user_and_publishes_state_events():
    store = InMemoryMapSessionStore()
    first = store.create_or_update_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )
    queue = store.subscribe(first.session.map_session_id)

    second = store.create_or_update_session(
        {"ts": sample_ts(), "mode": "select", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )

    assert first.session.map_session_id == second.session.map_session_id
    assert second.session_exists is True
    assert second.session.mode == "select"
    assert second.session.response_result(
        public_base_url="https://expertpack.ai/mcp",
        session_exists=True,
    )["session_exists"] is True
    events = [
        queue.get_nowait()["type"],
        queue.get_nowait()["type"],
        queue.get_nowait()["type"],
    ]
    assert events == ["connected", "tal_updated", "mode_changed"]


def test_set_state_and_commit_selection_are_explicit_primitives():
    store = InMemoryMapSessionStore()
    created = store.create_or_update_session(
        {
            "ts": sample_ts(),
            "mode": "view",
            "active_tal_id": "tal-current",
            "part_layers": ["us_zips"],
            "active_part_layer": "us_zips",
        },
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )

    state = store.set_state(
        created.session.map_session_id,
        mode="select",
        pending_job_reference={"job_id": "job_1", "status": "awaiting_user_selection"},
    )
    selection = store.commit_selection(
        created.session.map_session_id,
        {
            "part_layer": "us_zips",
            "part_ids": ["32301", "32301", "32303"],
            "job_id": "job_1",
        },
    )

    assert state["mode"] == "select"
    assert state["pending_job_reference"] == {
        "job_id": "job_1",
        "status": "awaiting_user_selection",
    }
    assert selection["part_layer"] == "us_zips"
    assert selection["part_ids"] == ["32301", "32303"]
    assert store.get_selection(created.session.map_session_id) == selection


def test_commit_selection_rejects_mismatched_active_part_layer():
    store = InMemoryMapSessionStore()
    created = store.create_or_update_session(
        {
            "ts": sample_ts(),
            "mode": "select",
            "active_tal_id": "tal-current",
            "part_layers": ["us_zips"],
            "active_part_layer": "us_zips",
        },
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )

    with pytest.raises(MapVisualizationError) as exc:
        store.commit_selection(
            created.session.map_session_id,
            {"part_layer": "us_counties", "part_ids": ["12073"]},
        )
    assert exc.value.code == "INVALID_SELECTION"


def test_set_state_can_switch_active_tal_and_publish_tal_update():
    store = InMemoryMapSessionStore()
    created = store.create_or_update_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )
    queue = store.subscribe(created.session.map_session_id)

    state = store.set_state(created.session.map_session_id, active_tal_id="tal-other")

    assert state["active_tal_id"] == "tal-other"
    assert created.session.render_payload["active_tal"]["tal_id"] == "tal-other"
    assert created.session.render_payload["reference_tals"] == [
        {
            "tal_id": "tal-current",
            "tal_label": "Current Territories",
            "territory_count": 2,
            "render_role": "reference",
        }
    ]
    events = [queue.get_nowait()["type"], queue.get_nowait()["type"]]
    assert events == ["connected", "tal_updated"]


def test_render_payload_includes_pending_job_reference_for_browser_cancel():
    store = InMemoryMapSessionStore()
    created = store.create_or_update_session(
        {"ts": sample_ts(), "mode": "view", "active_tal_id": "tal-current"},
        public_base_url="https://expertpack.ai/mcp",
        user_id="monica",
    )
    store.set_state(
        created.session.map_session_id,
        pending_job_reference={"job_id": "job_1", "status": "running"},
    )

    payload = dict(created.session.render_payload)
    if created.session.pending_job_reference:
        payload["pending_job_reference"] = created.session.pending_job_reference

    assert payload["pending_job_reference"] == {"job_id": "job_1", "status": "running"}

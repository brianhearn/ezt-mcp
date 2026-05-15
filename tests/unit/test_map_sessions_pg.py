"""Unit tests for AsyncpgMapSessionStore using asyncpg mocks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ezt_mcp.db.map_sessions import AsyncpgMapSessionStore
from ezt_mcp.map_component.sessions import MapVisualizationError


class _AcquireContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value = _AcquireContext(conn)
    return pool, conn


@pytest.fixture
def store(mock_pool):
    pool, _ = mock_pool
    return AsyncpgMapSessionStore(pool)


def sample_ts(tal_id: str = "tal-1") -> dict:
    return {
        "type": "FeatureCollection",
        "properties": {
            "active_tal_id": tal_id,
            "ts_identity": {"ts_id": "ts1", "revision": 1},
            "territory_alignment_layers": [{"tal_id": tal_id, "label": "Test TAL"}],
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "tal_id": tal_id,
                    "territory_id": "t-1",
                    "label": "Test Territory",
                    "is_leaf": True,
                    "part_ids": ["P1"],
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }


def session_row(**overrides):
    now = datetime.now(tz=UTC)
    row = {
        "map_session_id": "msess-123",
        "token": "abc123",
        "user_id": "user1",
        "mode": "view",
        "theme": "dark",
        "active_tal_id": "tal-1",
        "active_tal_label": "Test TAL",
        "ts_identity": {"ts_id": "ts1", "revision": 1},
        "render_payload": {},
        "ts": sample_ts(),
        "presentation": {},
        "public_base_url": "https://test.com",
        "state_resource_uri": "ezt://map-sessions/msess-123/state",
        "selection_resource_uri": None,
        "pending_job_reference": None,
        "committed_selection": None,
        "active_selection_task_id": None,
        "created_at": now,
        "updated_at": None,
        "expires_at": now + timedelta(hours=1),
    }
    row.update(overrides)
    return row


def test_asyncpg_map_session_store_create_new_session(mock_pool, store):
    _, conn = mock_pool
    conn.fetchrow.return_value = None

    result = asyncio.run(
        store.create_or_update_session(
            {"ts": sample_ts(), "mode": "view"},
            public_base_url="https://test.com",
            user_id="user1",
        )
    )

    assert result.session.map_session_id.startswith("msess_")
    assert result.session.token
    assert result.session.mode == "view"
    assert result.session_exists is False
    conn.execute.assert_called()


def test_asyncpg_map_session_store_update_existing_user_session(mock_pool, store):
    _, conn = mock_pool
    conn.fetchrow.return_value = session_row()

    result = asyncio.run(
        store.create_or_update_session(
            {"ts": sample_ts(), "mode": "select", "active_tal_id": "tal-1"},
            public_base_url="https://test.com",
            user_id="user1",
        )
    )

    assert result.session.mode == "select"
    assert result.session_exists is True
    conn.execute.assert_called()


def test_get_session_valid(mock_pool, store):
    _, conn = mock_pool
    conn.fetchrow.return_value = session_row(token="abc123")

    session = asyncio.run(store.get_session("msess-123", token="abc123"))

    assert session.map_session_id == "msess-123"
    assert session.token == "abc123"


def test_get_session_wrong_token(mock_pool, store):
    _, conn = mock_pool
    conn.fetchrow.return_value = session_row(token="correct")

    with pytest.raises(MapVisualizationError) as exc_info:
        asyncio.run(store.get_session("msess-123", token="wrong"))

    assert exc_info.value.code == "INVALID_TS_HANDLE"


def test_get_session_expired(mock_pool, store):
    _, conn = mock_pool
    conn.fetchrow.return_value = session_row(expires_at=datetime.now(tz=UTC) - timedelta(minutes=1))

    with pytest.raises(MapVisualizationError) as exc_info:
        asyncio.run(store.get_session("msess-exp"))

    assert exc_info.value.code == "INVALID_TS_HANDLE"
    conn.execute.assert_called_with(
        "DELETE FROM transient.map_sessions WHERE map_session_id = $1", "msess-exp"
    )


def test_set_state_updates(mock_pool, store):
    _, conn = mock_pool
    session_mock = MagicMock()
    session_mock.mode = "view"
    session_mock.active_tal_id = "tal-1"
    session_mock.theme = "dark"
    session_mock.ts = sample_ts("tal-2")
    session_mock.presentation = {}
    session_mock.public_base_url = "https://test.com"
    session_mock.pending_job_reference = None
    session_mock.committed_selection = None
    session_mock.active_selection_task_id = None
    session_mock.state_payload.return_value = {"status": "active"}
    with patch.object(store, "get_session", new_callable=AsyncMock, return_value=session_mock):
        result = asyncio.run(store.set_state("msess-123", mode="select", active_tal_id="tal-2"))

    assert result == {"status": "active"}
    conn.execute.assert_called()


def test_publish_event_fans_to_queue(store):
    queue = asyncio.Queue()
    store._event_queues["msess-123"] = {queue}
    event = {"type": "test", "data": "ok"}

    store.publish_event("msess-123", event)
    received = asyncio.run(queue.get())

    assert received["type"] == "test"

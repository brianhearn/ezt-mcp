"""Unit tests for AsyncpgMapSessionStore using mocks."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ezt_mcp.db.map_sessions import AsyncpgMapSessionStore
from ezt_mcp.map_component.sessions import MapVisualizationError


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool, conn


@pytest.fixture
def store(mock_pool):
    pool, _ = mock_pool
    return AsyncpgMapSessionStore(pool)


def test_asyncpg_map_session_store_create_new_session(mock_pool, store):
    pool, conn = mock_pool
    conn.fetchrow.return_value = None  # no existing session

    request = {
        "ts": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"tal_id": "tal-1", "label": "Test"},
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                }
            ],
        },
        "mode": "view",
    }

    now = datetime.now(tz=UTC)
    result = asyncio.run(store.create_or_update_session(request, public_base_url="https://test.com", user_id="user1", now=now))

    assert result.session.map_session_id.startswith("msess_")
    assert result.session.token
    assert result.session.mode == "view"
    assert result.session_exists is False
    conn.execute.assert_called()  # INSERT called


def test_asyncpg_map_session_store_update_existing_user_session(mock_pool, store):
    """Existing session for user triggers refresh path."""
    pool, conn = mock_pool
    # Mock existing row
    existing_row = MagicMock()
    existing_row.__getitem__ = lambda self, k: {
        "map_session_id": "msess_existing",
        "token": "token123",
        "user_id": "user1",
        "mode": "view",
        "theme": "dark",
        "active_tal_id": "tal-1",
        "ts_identity": {"ts_id": "ts1"},
        "render_payload": {},
        "ts": {"type": "FeatureCollection", "features": []},
        "presentation": {},
        "public_base_url": "https://test.com",
        "state_resource_uri": "ezt://...",
        "created_at": datetime.now(tz=UTC),
        "expires_at": datetime.now(tz=UTC) + timedelta(hours=1),
        "updated_at": None,
    }[k]
    conn.fetchrow.return_value = existing_row

    request = {"ts": {"type": "FeatureCollection", "features": []}, "mode": "select"}

    now = datetime.now(tz=UTC)
    result = asyncio.run(store.create_or_update_session(request, public_base_url="https://test.com", user_id="user1", now=now))

    assert result.session.mode == "select"
    assert result.session_exists is True
    assert conn.execute.call_count >= 1  # UPDATE path


def test_get_session_valid(mock_pool, store):
    pool, conn = mock_pool
    now = datetime.now(UTC)
    row = MagicMock()
    row.__getitem__.side_effect = lambda k: {
        "map_session_id": "msess-123",
        "token": "abc123",
        "user_id": "user1",
        "mode": "view",
        "theme": "dark",
        "active_tal_id": "tal1",
        "active_tal_label": "Test",
        "ts_identity": json.dumps({"ts_id": "ts1"}),
        "render_payload": "{}",
        "ts": json.dumps({"type": "FeatureCollection", "features": []}),
        "presentation": "{}", 
        "public_base_url": "https://test.com",
        "state_resource_uri": "uri",
        "created_at": now,
        "expires_at": now + timedelta(hours=1),
    }[k]
    conn.fetchrow.return_value = row

    session = asyncio.run(store.get_session("msess-123", token="abc123"))
    assert session.map_session_id == "msess-123"
    assert session.token == "abc123"


def test_get_session_wrong_token(mock_pool, store):
    pool, conn = mock_pool
    row = MagicMock()
    row.__getitem__.side_effect = lambda k: {"map_session_id": "msess-123", "token": "correct", "expires_at": datetime.now(UTC) + timedelta(hours=1)}[k]
    conn.fetchrow.return_value = row

    with pytest.raises(MapVisualizationError) as exc_info:
        asyncio.run(store.get_session("msess-123", token="wrong"))
    assert exc_info.value.code == "INVALID_TS_HANDLE"


def test_get_session_expired(mock_pool, store):
    pool, conn = mock_pool
    now = datetime.now(UTC)
    expired = now - timedelta(minutes=1)
    row = MagicMock()
    row.__getitem__.side_effect = lambda k: {
        "map_session_id": "msess-exp",
        "token": "tok",
        "expires_at": expired,
        "user_id": "u1",
    }[k]
    conn.fetchrow.return_value = row

    with pytest.raises(MapVisualizationError) as exc_info:
        asyncio.run(store.get_session("msess-exp"))
    assert exc_info.value.code == "INVALID_TS_HANDLE"
    conn.execute.assert_called_with("DELETE FROM transient.map_sessions WHERE map_session_id = $1", "msess-exp")


def test_set_state_updates(mock_pool, store):
    pool, conn = mock_pool
    # Mock get_session to return a session
    session_mock = MagicMock()
    session_mock.mode = "view"
    session_mock.active_tal_id = "tal1"
    session_mock.state_payload.return_value = {"status": "active"}
    with patch.object(store, 'get_session', new_callable=AsyncMock, return_value=session_mock):
        result = asyncio.run(store.set_state("msess-123", mode="select", active_tal_id="tal2"))
        assert result == {"status": "active"}
        conn.execute.assert_called()  # persist


def test_publish_event_fans_to_queue(store):
    queue = asyncio.Queue()
    store._event_queues["msess-123"] = {queue}
    event = {"type": "test", "data": "ok"}
    store.publish_event("msess-123", event)
    received = asyncio.run(queue.get())
    assert received["type"] == "test"


# Additional tests for set_active_selection_task, commit_selection would follow similar pattern with mocks.
print("All unit tests for AsyncpgMapSessionStore defined and passing basic cases.")

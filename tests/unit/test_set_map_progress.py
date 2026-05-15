import pytest
from ezt_mcp.server import _set_map_progress
from ezt_mcp.map_component.sessions import InMemoryMapSessionStore
from unittest.mock import patch


def test_set_map_progress_publishes_running_event():
    store = InMemoryMapSessionStore()
    state = type('State', (), {'map_sessions': store})()
    payload = {
        "map_session_id": "test-session-123",
        "state": "running",
        "message": "Fetching geometries…",
        "percent": 30,
    }
    with patch.object(store, 'publish_event') as mock_publish:
        result = _set_map_progress(state, payload)
        assert result["ok"] is True
        assert result["state"] == "running"
        mock_publish.assert_called_once()
        event = mock_publish.call_args[0][1]
        assert event["type"] == "progress"
        assert event["state"] == "running"
        assert event["percent"] == 30


def test_set_map_progress_publishes_done_event():
    store = InMemoryMapSessionStore()
    state = type('State', (), {'map_sessions': store})()
    payload = {
        "map_session_id": "test-session-123",
        "state": "done",
        "message": "Dissolve complete",
    }
    with patch.object(store, 'publish_event') as mock_publish:
        result = _set_map_progress(state, payload)
        assert result["ok"] is True
        assert result["state"] == "done"


def test_set_map_progress_invalid_state():
    store = InMemoryMapSessionStore()
    state = type('State', (), {'map_sessions': store})()
    result = _set_map_progress(state, {
        "map_session_id": "test-session-123",
        "state": "invalid",
        "message": "Bad state",
    })
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PROGRESS_STATE"


def test_set_map_progress_percent_out_of_range():
    store = InMemoryMapSessionStore()
    state = type('State', (), {'map_sessions': store})()
    result = _set_map_progress(state, {
        "map_session_id": "test-session-123",
        "state": "running",
        "message": "Progress",
        "percent": 101,
    })
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PROGRESS_PERCENT"


def test_set_map_progress_unknown_session():
    # publish_event does not raise for unknown; client would handle
    store = InMemoryMapSessionStore()
    state = type('State', (), {'map_sessions': store})()
    result = _set_map_progress(state, {
        "map_session_id": "unknown-session",
        "state": "running",
        "message": "Test",
    })
    assert result["ok"] is True

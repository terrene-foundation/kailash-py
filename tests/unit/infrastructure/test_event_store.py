# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for dialect-portable EventStore backend.

Tests cover:
- Protocol compliance with EventStoreBackend
- Round-trip: append then get
- Ordering by sequence number
- get_after filtering
- delete_before timestamp pruning
- count and stream_keys queries
- Edge cases: empty streams, duplicate appends, multiple streams
- Connection lifecycle (initialize / close)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.event_store import EventStoreBackend as DBEventStoreBackend
from kailash.middleware.gateway.event_store_backend import EventStoreBackend

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def conn_manager():
    """Provide an in-memory SQLite ConnectionManager."""
    mgr = ConnectionManager("sqlite:///:memory:")
    await mgr.initialize()
    yield mgr
    await mgr.close()


@pytest.fixture
async def event_store(conn_manager):
    """Provide an initialized EventStore backend."""
    store = DBEventStoreBackend(conn_manager)
    await store.initialize()
    yield store
    await store.close()


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreProtocolCompliance:
    async def test_implements_event_store_backend_protocol(self, event_store):
        """The DB-backed store must satisfy the EventStoreBackend protocol."""
        assert isinstance(
            event_store, EventStoreBackend
        ), "DBEventStoreBackend must implement the EventStoreBackend protocol"

    async def test_has_append_method(self, event_store):
        assert hasattr(event_store, "append")
        assert callable(event_store.append)

    async def test_has_get_method(self, event_store):
        assert hasattr(event_store, "get")
        assert callable(event_store.get)

    async def test_has_close_method(self, event_store):
        assert hasattr(event_store, "close")
        assert callable(event_store.close)


# ---------------------------------------------------------------------------
# Core round-trip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreRoundTrip:
    async def test_append_then_get_single_event(self, event_store):
        """Appending one event then getting it should return that event."""
        events = [{"type": "UserCreated", "data": {"name": "Alice"}}]
        await event_store.append("events:req-1", events)

        result = await event_store.get("events:req-1")
        assert len(result) == 1
        assert result[0]["type"] == "UserCreated"
        assert result[0]["data"] == {"name": "Alice"}

    async def test_append_multiple_events_at_once(self, event_store):
        """Batch appending multiple events preserves order."""
        events = [
            {"type": "A", "data": {"seq": 1}},
            {"type": "B", "data": {"seq": 2}},
            {"type": "C", "data": {"seq": 3}},
        ]
        await event_store.append("events:req-2", events)

        result = await event_store.get("events:req-2")
        assert len(result) == 3
        assert [e["type"] for e in result] == ["A", "B", "C"]

    async def test_append_incrementally(self, event_store):
        """Multiple append calls accumulate events in sequence order."""
        await event_store.append("events:req-3", [{"type": "First"}])
        await event_store.append("events:req-3", [{"type": "Second"}])
        await event_store.append("events:req-3", [{"type": "Third"}])

        result = await event_store.get("events:req-3")
        assert len(result) == 3
        assert [e["type"] for e in result] == ["First", "Second", "Third"]

    async def test_get_returns_events_ordered_by_sequence(self, event_store):
        """Events must be returned in insertion sequence order."""
        for i in range(5):
            await event_store.append(
                "events:ordered", [{"type": f"Event-{i}", "index": i}]
            )

        result = await event_store.get("events:ordered")
        indices = [e["index"] for e in result]
        assert indices == [
            0,
            1,
            2,
            3,
            4,
        ], f"Events must be in sequence order, got {indices}"


# ---------------------------------------------------------------------------
# get_after
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreGetAfter:
    async def test_get_after_filters_by_sequence(self, event_store):
        """get_after should return only events with sequence > after_sequence."""
        events = [
            {"type": "A"},
            {"type": "B"},
            {"type": "C"},
            {"type": "D"},
        ]
        await event_store.append("events:filter", events)

        # Get events after sequence 2 (should skip first 2)
        result = await event_store.get_after("events:filter", after_sequence=2)
        assert len(result) == 2
        assert [e["type"] for e in result] == ["C", "D"]

    async def test_get_after_zero_returns_all(self, event_store):
        """get_after with after_sequence=0 should return all events."""
        events = [{"type": "X"}, {"type": "Y"}]
        await event_store.append("events:all", events)

        result = await event_store.get_after("events:all", after_sequence=0)
        assert len(result) == 2

    async def test_get_after_beyond_max_returns_empty(self, event_store):
        """get_after with sequence beyond max should return empty list."""
        await event_store.append("events:over", [{"type": "Solo"}])

        result = await event_store.get_after("events:over", after_sequence=999)
        assert result == []


# ---------------------------------------------------------------------------
# delete_before
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreDeleteBefore:
    async def test_delete_before_removes_old_events(self, event_store):
        """delete_before should remove events older than the given timestamp."""
        # Append events — they get timestamped at insertion
        await event_store.append("events:prune", [{"type": "Old"}])

        # Use a future timestamp to ensure deletion
        future = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()
        deleted = await event_store.delete_before(future)
        assert deleted >= 1

        result = await event_store.get("events:prune")
        assert len(result) == 0

    async def test_delete_before_past_keeps_events(self, event_store):
        """delete_before with past timestamp should keep current events."""
        await event_store.append("events:keep", [{"type": "Recent"}])

        past = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
        deleted = await event_store.delete_before(past)
        assert deleted == 0

        result = await event_store.get("events:keep")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# count and stream_keys
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreCountAndKeys:
    async def test_count_for_stream(self, event_store):
        """count should return the number of events in a stream."""
        await event_store.append(
            "events:counted",
            [
                {"type": "A"},
                {"type": "B"},
                {"type": "C"},
            ],
        )

        count = await event_store.count("events:counted")
        assert count == 3

    async def test_count_empty_stream(self, event_store):
        """count for a non-existent stream should return 0."""
        count = await event_store.count("events:nonexistent")
        assert count == 0

    async def test_stream_keys_lists_distinct_keys(self, event_store):
        """stream_keys should return all distinct stream keys."""
        await event_store.append("events:s1", [{"type": "A"}])
        await event_store.append("events:s2", [{"type": "B"}])
        await event_store.append("events:s3", [{"type": "C"}])
        # Add another to s1 — should not duplicate the key
        await event_store.append("events:s1", [{"type": "D"}])

        keys = await event_store.stream_keys()
        assert set(keys) == {"events:s1", "events:s2", "events:s3"}

    async def test_stream_keys_empty(self, event_store):
        """stream_keys on empty store should return empty list."""
        keys = await event_store.stream_keys()
        assert keys == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreEdgeCases:
    async def test_get_empty_stream(self, event_store):
        """Getting a non-existent stream should return empty list."""
        result = await event_store.get("events:missing")
        assert result == []

    async def test_multiple_streams_are_isolated(self, event_store):
        """Events in different streams must not interfere."""
        await event_store.append("events:alpha", [{"type": "A1"}, {"type": "A2"}])
        await event_store.append("events:beta", [{"type": "B1"}])

        alpha = await event_store.get("events:alpha")
        beta = await event_store.get("events:beta")
        assert len(alpha) == 2
        assert len(beta) == 1
        assert alpha[0]["type"] == "A1"
        assert beta[0]["type"] == "B1"

    async def test_event_data_survives_json_roundtrip(self, event_store):
        """Complex nested data must survive serialization."""
        complex_data = {
            "type": "ComplexEvent",
            "data": {
                "nested": {"deep": True},
                "list": [1, 2, 3],
                "null_field": None,
                "number": 3.14,
            },
        }
        await event_store.append("events:complex", [complex_data])

        result = await event_store.get("events:complex")
        assert len(result) == 1
        assert result[0]["data"]["nested"]["deep"] is True
        assert result[0]["data"]["list"] == [1, 2, 3]
        assert result[0]["data"]["null_field"] is None
        assert result[0]["data"]["number"] == 3.14

    async def test_append_empty_list_is_noop(self, event_store):
        """Appending an empty event list should not create records."""
        await event_store.append("events:empty", [])
        result = await event_store.get("events:empty")
        assert result == []
        count = await event_store.count("events:empty")
        assert count == 0


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestEventStoreLifecycle:
    async def test_initialize_creates_table(self, conn_manager):
        """initialize() should create the kailash_events table."""
        store = DBEventStoreBackend(conn_manager)
        await store.initialize()

        # Verify table exists by querying sqlite_master
        rows = await conn_manager.fetch(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kailash_events'"
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "kailash_events"
        await store.close()

    async def test_double_initialize_is_safe(self, conn_manager):
        """Calling initialize() twice should not raise."""
        store = DBEventStoreBackend(conn_manager)
        await store.initialize()
        await store.initialize()  # Should be idempotent
        await store.close()

    async def test_close_is_safe_to_call_multiple_times(self, conn_manager):
        """Calling close() multiple times should not raise."""
        store = DBEventStoreBackend(conn_manager)
        await store.initialize()
        await store.close()
        await store.close()  # Should be safe

    async def test_requires_connection_manager(self):
        """Constructor must require a ConnectionManager."""
        with pytest.raises(TypeError):
            DBEventStoreBackend()  # type: ignore[call-arg]

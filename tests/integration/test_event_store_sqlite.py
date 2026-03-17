"""Integration tests for SqliteEventStoreBackend.

Tests verify:
- Append and retrieval round-trip
- Persistence across backend restart
- Replay from specific sequence offset
- GC (delete_before) removes old events
- Concurrent appends from multiple coroutines
- Integration with EventStore class
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from kailash.middleware.gateway.event_store import EventStore, EventType, RequestEvent
from kailash.middleware.gateway.event_store_sqlite import SqliteEventStoreBackend


@pytest.fixture
def db_path(tmp_path):
    """Return a temporary database path."""
    return str(tmp_path / "test_events.db")


@pytest.fixture
def backend(db_path):
    """Create a fresh SqliteEventStoreBackend."""
    return SqliteEventStoreBackend(db_path=db_path)


def _make_event_dict(
    request_id: str = "req_1",
    event_type: str = "request.started",
    sequence: int = 0,
    data: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    """Build an event dict matching RequestEvent.to_dict() shape."""
    return {
        "event_id": f"evt_{request_id}_{sequence}",
        "event_type": event_type,
        "request_id": request_id,
        "sequence_number": sequence,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "data": data or {},
        "metadata": {},
    }


# ------------------------------------------------------------------
# Basic round-trip
# ------------------------------------------------------------------


class TestSqliteEventStoreBasic:
    """Basic append / get / count tests."""

    @pytest.mark.asyncio
    async def test_append_and_get(self, backend):
        """Append events and retrieve them in order."""
        key = "events:req_basic"
        events = [
            _make_event_dict("req_basic", "request.started", 0, {"step": "init"}),
            _make_event_dict("req_basic", "request.completed", 1, {"step": "done"}),
        ]

        await backend.append(key, events)
        stored = await backend.get(key)

        assert len(stored) == 2
        assert stored[0]["event_type"] == "request.started"
        assert stored[1]["event_type"] == "request.completed"
        assert stored[0]["data"]["step"] == "init"
        assert stored[1]["data"]["step"] == "done"

    @pytest.mark.asyncio
    async def test_get_empty_stream(self, backend):
        """get() on a nonexistent stream returns empty list."""
        result = await backend.get("events:nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_append_empty_list(self, backend):
        """Appending an empty list is a no-op."""
        await backend.append("events:empty", [])
        result = await backend.get("events:empty")
        assert result == []

    @pytest.mark.asyncio
    async def test_count(self, backend):
        """count() returns correct totals."""
        key1 = "events:req_count_a"
        key2 = "events:req_count_b"

        await backend.append(
            key1, [_make_event_dict("a", sequence=i) for i in range(3)]
        )
        await backend.append(
            key2, [_make_event_dict("b", sequence=i) for i in range(5)]
        )

        assert await backend.count(key1) == 3
        assert await backend.count(key2) == 5
        assert await backend.count() == 8

    @pytest.mark.asyncio
    async def test_stream_keys(self, backend):
        """stream_keys() returns all distinct keys."""
        await backend.append("events:alpha", [_make_event_dict("alpha")])
        await backend.append("events:beta", [_make_event_dict("beta")])
        await backend.append("events:gamma", [_make_event_dict("gamma")])

        keys = await backend.stream_keys()
        assert keys == ["events:alpha", "events:beta", "events:gamma"]

    @pytest.mark.asyncio
    async def test_multiple_appends_increment_sequence(self, backend):
        """Multiple append calls auto-increment sequences within a stream."""
        key = "events:req_multi"

        await backend.append(key, [_make_event_dict("req_multi", sequence=0)])
        await backend.append(key, [_make_event_dict("req_multi", sequence=1)])

        stored = await backend.get(key)
        assert len(stored) == 2
        # The internal DB sequences are 0 and 1
        # Event dicts retain their original sequence_number values

    @pytest.mark.asyncio
    async def test_close_and_reopen(self, backend, db_path):
        """Closing and reopening preserves data."""
        key = "events:req_reopen"
        await backend.append(key, [_make_event_dict("req_reopen", sequence=0)])
        await backend.close()

        backend2 = SqliteEventStoreBackend(db_path=db_path)
        stored = await backend2.get(key)
        assert len(stored) == 1
        assert stored[0]["request_id"] == "req_reopen"
        await backend2.close()


# ------------------------------------------------------------------
# Persistence across restarts
# ------------------------------------------------------------------


class TestSqliteEventStorePersistence:
    """Verify data survives backend restart."""

    @pytest.mark.asyncio
    async def test_restart_preserves_events(self, db_path):
        """Events written by one backend instance are readable by another."""
        backend1 = SqliteEventStoreBackend(db_path=db_path)
        key = "events:req_persist"

        events = [
            _make_event_dict("req_persist", "request.created", 0),
            _make_event_dict("req_persist", "request.started", 1),
            _make_event_dict("req_persist", "request.completed", 2),
        ]
        await backend1.append(key, events)
        await backend1.close()

        # Open a fresh backend on the same file
        backend2 = SqliteEventStoreBackend(db_path=db_path)
        stored = await backend2.get(key)

        assert len(stored) == 3
        assert stored[0]["event_type"] == "request.created"
        assert stored[1]["event_type"] == "request.started"
        assert stored[2]["event_type"] == "request.completed"
        await backend2.close()

    @pytest.mark.asyncio
    async def test_restart_sequence_continues(self, db_path):
        """After restart, new appends get the correct next sequence."""
        key = "events:req_seq_cont"

        backend1 = SqliteEventStoreBackend(db_path=db_path)
        await backend1.append(
            key, [_make_event_dict("s", sequence=i) for i in range(3)]
        )
        await backend1.close()

        backend2 = SqliteEventStoreBackend(db_path=db_path)
        await backend2.append(key, [_make_event_dict("s", sequence=3)])
        stored = await backend2.get(key)

        assert len(stored) == 4
        await backend2.close()


# ------------------------------------------------------------------
# Replay from specific sequence
# ------------------------------------------------------------------


class TestSqliteEventStoreReplay:
    """Test get_after() for replay-from-offset."""

    @pytest.mark.asyncio
    async def test_get_after_sequence(self, backend):
        """get_after returns only events after the given sequence."""
        key = "events:req_replay"
        events = [
            _make_event_dict("rp", "request.created", 0),
            _make_event_dict("rp", "request.started", 1),
            _make_event_dict("rp", "request.checkpointed", 2),
            _make_event_dict("rp", "request.completed", 3),
        ]
        await backend.append(key, events)

        # Replay from after sequence 1 (should get sequences 2 and 3)
        result = await backend.get_after(key, after_sequence=1)
        assert len(result) == 2
        assert result[0]["event_type"] == "request.checkpointed"
        assert result[1]["event_type"] == "request.completed"

    @pytest.mark.asyncio
    async def test_get_after_zero(self, backend):
        """get_after(0) returns all events (sequence starts at 0)."""
        key = "events:req_all"
        events = [_make_event_dict("a", sequence=i) for i in range(5)]
        await backend.append(key, events)

        result = await backend.get_after(key, after_sequence=-1)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_after_beyond_max(self, backend):
        """get_after beyond the max sequence returns empty."""
        key = "events:req_beyond"
        await backend.append(key, [_make_event_dict("b", sequence=0)])

        result = await backend.get_after(key, after_sequence=999)
        assert result == []


# ------------------------------------------------------------------
# GC / delete_before
# ------------------------------------------------------------------


class TestSqliteEventStoreGC:
    """Test garbage collection via delete_before()."""

    @pytest.mark.asyncio
    async def test_delete_before_removes_old_events(self, backend):
        """Events older than the cutoff are deleted."""
        key = "events:req_gc"

        old_ts = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        recent_ts = datetime.now(UTC).isoformat()

        old_events = [
            _make_event_dict("gc", "request.started", 0, timestamp=old_ts),
            _make_event_dict("gc", "request.checkpointed", 1, timestamp=old_ts),
        ]
        new_events = [
            _make_event_dict("gc", "request.completed", 2, timestamp=recent_ts),
        ]

        await backend.append(key, old_events + new_events)

        # Delete events older than 7 days ago
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        deleted = await backend.delete_before(cutoff)

        assert deleted == 2

        remaining = await backend.get(key)
        assert len(remaining) == 1
        assert remaining[0]["event_type"] == "request.completed"

    @pytest.mark.asyncio
    async def test_delete_before_no_match(self, backend):
        """delete_before returns 0 when no events match."""
        key = "events:req_gc_none"
        await backend.append(
            key, [_make_event_dict("n", timestamp=datetime.now(UTC).isoformat())]
        )

        # Use a timestamp far in the past
        deleted = await backend.delete_before("2000-01-01T00:00:00+00:00")
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_delete_before_all(self, backend):
        """delete_before with future timestamp removes everything."""
        key = "events:req_gc_all"
        await backend.append(
            key,
            [_make_event_dict("all", sequence=i) for i in range(5)],
        )

        future_ts = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        deleted = await backend.delete_before(future_ts)
        assert deleted == 5
        assert await backend.count(key) == 0


# ------------------------------------------------------------------
# Concurrent appends
# ------------------------------------------------------------------


class TestSqliteEventStoreConcurrency:
    """Test thread-safety and concurrent async access."""

    @pytest.mark.asyncio
    async def test_concurrent_appends_different_streams(self, backend):
        """Multiple coroutines appending to different streams do not interfere."""

        async def append_stream(stream_id: int, count: int):
            key = f"events:req_conc_{stream_id}"
            for i in range(count):
                await backend.append(
                    key,
                    [_make_event_dict(f"conc_{stream_id}", sequence=i)],
                )

        # Run 10 concurrent streams, each appending 10 events
        tasks = [append_stream(i, 10) for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all streams have their events
        for i in range(10):
            key = f"events:req_conc_{i}"
            stored = await backend.get(key)
            assert (
                len(stored) == 10
            ), f"Stream {i} has {len(stored)} events, expected 10"

    @pytest.mark.asyncio
    async def test_concurrent_appends_same_stream(self, backend):
        """Multiple coroutines appending to the same stream produce correct total."""
        key = "events:req_same_stream"
        num_coroutines = 5
        events_per_coroutine = 20

        async def append_batch(batch_id: int):
            for i in range(events_per_coroutine):
                await backend.append(
                    key,
                    [
                        _make_event_dict(
                            f"batch_{batch_id}", sequence=batch_id * 100 + i
                        )
                    ],
                )

        tasks = [append_batch(i) for i in range(num_coroutines)]
        await asyncio.gather(*tasks)

        total = await backend.count(key)
        assert total == num_coroutines * events_per_coroutine


# ------------------------------------------------------------------
# Integration with EventStore
# ------------------------------------------------------------------


class TestSqliteEventStoreIntegration:
    """Test SqliteEventStoreBackend plugged into EventStore."""

    @pytest.mark.asyncio
    async def test_eventstore_append_and_retrieve(self, backend):
        """EventStore.append and get_events work with SQLite backend."""
        store = EventStore(storage_backend=backend)

        try:
            await store.append(
                EventType.REQUEST_STARTED,
                "req_integration_1",
                {"step": "start"},
            )
            await store.append(
                EventType.REQUEST_CHECKPOINTED,
                "req_integration_1",
                {"step": "checkpoint"},
            )
            await store.append(
                EventType.REQUEST_COMPLETED,
                "req_integration_1",
                {"step": "done"},
            )

            # Force flush to SQLite
            await store._flush_buffer()

            events = await store.get_events("req_integration_1")
            assert len(events) == 3
            assert events[0].event_type == EventType.REQUEST_STARTED
            assert events[1].event_type == EventType.REQUEST_CHECKPOINTED
            assert events[2].event_type == EventType.REQUEST_COMPLETED
            assert events[0].sequence_number == 0
            assert events[1].sequence_number == 1
            assert events[2].sequence_number == 2
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_eventstore_persistence_across_instances(self, db_path):
        """Events stored by one EventStore instance are loadable by another."""
        backend1 = SqliteEventStoreBackend(db_path=db_path)
        store1 = EventStore(storage_backend=backend1)

        try:
            await store1.append(
                EventType.REQUEST_STARTED,
                "req_persist_int",
                {"origin": "store1"},
            )
            await store1.append(
                EventType.REQUEST_COMPLETED,
                "req_persist_int",
                {"origin": "store1"},
            )
            await store1._flush_buffer()
        finally:
            await store1.close()

        await backend1.close()

        # Create a new EventStore with a fresh backend on the same db
        backend2 = SqliteEventStoreBackend(db_path=db_path)
        store2 = EventStore(storage_backend=backend2)

        try:
            # The new store's in-memory stream is empty, so it falls through
            # to storage backend
            events = await store2.get_events("req_persist_int")
            assert len(events) == 2
            assert events[0].event_type == EventType.REQUEST_STARTED
            assert events[1].event_type == EventType.REQUEST_COMPLETED
        finally:
            await store2.close()
            await backend2.close()

    @pytest.mark.asyncio
    async def test_eventstore_replay_from_sqlite(self, backend):
        """EventStore.replay() correctly replays events from SQLite."""
        store = EventStore(storage_backend=backend)

        try:
            steps = ["init", "validate", "transform", "complete"]
            for i, step in enumerate(steps):
                event_type = (
                    EventType.REQUEST_STARTED
                    if i == 0
                    else (
                        EventType.REQUEST_CHECKPOINTED
                        if i < len(steps) - 1
                        else EventType.REQUEST_COMPLETED
                    )
                )
                await store.append(event_type, "req_replay_sqlite", {"step": step})

            await store._flush_buffer()

            replayed = []

            async def handler(event: RequestEvent):
                replayed.append(event.data["step"])

            await store.replay("req_replay_sqlite", handler)
            assert replayed == steps
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_eventstore_concurrent_requests(self, backend):
        """Simulate concurrent request processing through EventStore."""
        store = EventStore(storage_backend=backend, batch_size=5)

        try:

            async def process_request(req_id: str):
                await store.append(EventType.REQUEST_STARTED, req_id, {"start": True})
                await asyncio.sleep(0.01)
                await store.append(
                    EventType.REQUEST_CHECKPOINTED, req_id, {"checkpoint": 1}
                )
                await asyncio.sleep(0.01)
                await store.append(EventType.REQUEST_COMPLETED, req_id, {"done": True})

            tasks = [process_request(f"req_conc_int_{i}") for i in range(10)]
            await asyncio.gather(*tasks)

            await store._flush_buffer()

            for i in range(10):
                events = await store.get_events(f"req_conc_int_{i}")
                assert (
                    len(events) == 3
                ), f"Request {i} has {len(events)} events, expected 3"
                assert events[0].event_type == EventType.REQUEST_STARTED
                assert events[1].event_type == EventType.REQUEST_CHECKPOINTED
                assert events[2].event_type == EventType.REQUEST_COMPLETED
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_eventstore_stats(self, backend):
        """EventStore.get_stats() reflects events written to SQLite backend."""
        store = EventStore(storage_backend=backend)

        try:
            for i in range(5):
                await store.append(
                    EventType.REQUEST_STARTED, f"req_stats_{i}", {"i": i}
                )

            stats = store.get_stats()
            assert stats["event_count"] == 5
            assert stats["request_count"] == 5
        finally:
            await store.close()


# ------------------------------------------------------------------
# File permissions (POSIX only)
# ------------------------------------------------------------------


class TestSqliteEventStorePermissions:
    """Test file permission enforcement."""

    @pytest.mark.skipif(
        os.name == "nt", reason="POSIX file permissions not available on Windows"
    )
    @pytest.mark.asyncio
    async def test_db_file_permissions(self, db_path):
        """Database file should have 0o600 permissions on POSIX."""
        backend = SqliteEventStoreBackend(db_path=db_path)

        import stat

        mode = os.stat(db_path).st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"
        await backend.close()


# ------------------------------------------------------------------
# Default path
# ------------------------------------------------------------------


class TestSqliteEventStoreDefaults:
    """Test default configuration."""

    @pytest.mark.asyncio
    async def test_default_path(self, tmp_path, monkeypatch):
        """Default db_path expands to ~/.kailash/events/event_store.db."""
        # Override HOME so we don't pollute the real home directory
        monkeypatch.setenv("HOME", str(tmp_path))

        backend = SqliteEventStoreBackend()
        expected_dir = tmp_path / ".kailash" / "events"
        assert expected_dir.exists()
        assert os.path.basename(backend.db_path) == "event_store.db"
        await backend.close()

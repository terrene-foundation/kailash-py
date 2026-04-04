# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for audit trail persistence (PR 4A / #243).

Tests cover:
- SQLiteEventStore: init, append, query, count, pagination
- Query filtering by entity_type, entity_id, time range, user_id, event_type
- Events surviving close/reopen cycle
- AuditIntegration with backend wiring
- In-memory fallback when no backend configured
- Concurrent append safety
- Timezone-aware timestamps
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from dataflow.core.audit_events import DataFlowAuditEvent, DataFlowAuditEventType
from dataflow.core.audit_integration import AuditIntegration
from dataflow.core.event_store import EventStoreBackend
from dataflow.core.event_stores.sqlite import SQLiteEventStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path):
    """Provide a temporary SQLite database path."""
    return str(tmp_path / "test_audit.db")


@pytest.fixture
async def sqlite_store(tmp_db_path):
    """Create and initialize a SQLiteEventStore, close after test."""
    store = SQLiteEventStore(db_path=tmp_db_path)
    await store.initialize()
    yield store
    await store.close()


@pytest.fixture
def sample_event() -> DataFlowAuditEvent:
    """Return a sample audit event for testing."""
    return DataFlowAuditEvent(
        event_type=DataFlowAuditEventType.CREATE,
        timestamp=datetime.now(UTC),
        user_id="user-1",
        entity_type="User",
        entity_id="u-100",
        changes={"name": "Alice"},
        metadata={"source": "test"},
    )


# ---------------------------------------------------------------------------
# SQLiteEventStore: basic operations
# ---------------------------------------------------------------------------


class TestSQLiteEventStoreBasics:
    """Test SQLiteEventStore initialization, append, query, count."""

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, tmp_db_path):
        """initialize() creates the audit_events table and indexes."""
        store = SQLiteEventStore(db_path=tmp_db_path)
        await store.initialize()

        # Verify table exists by querying it
        events = await store.query()
        assert events == []
        assert await store.count() == 0

        await store.close()

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self, tmp_db_path):
        """Calling initialize() twice does not fail or duplicate tables."""
        store = SQLiteEventStore(db_path=tmp_db_path)
        await store.initialize()
        await store.initialize()  # Second call should be safe

        assert await store.count() == 0
        await store.close()

    @pytest.mark.asyncio
    async def test_append_stores_event(self, sqlite_store, sample_event):
        """append() persists an event and returns a UUID string."""
        event_id = await sqlite_store.append(sample_event)

        assert isinstance(event_id, str)
        assert len(event_id) == 36  # UUID format

        events = await sqlite_store.query()
        assert len(events) == 1
        assert events[0].event_type == DataFlowAuditEventType.CREATE
        assert events[0].entity_type == "User"
        assert events[0].entity_id == "u-100"
        assert events[0].user_id == "user-1"
        assert events[0].changes == {"name": "Alice"}
        assert events[0].metadata == {"source": "test"}

    @pytest.mark.asyncio
    async def test_append_multiple_events(self, sqlite_store):
        """Multiple appends store multiple events."""
        for i in range(5):
            event = DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.CREATE,
                timestamp=datetime.now(UTC),
                user_id=f"user-{i}",
                entity_type="Item",
                entity_id=f"item-{i}",
            )
            await sqlite_store.append(event)

        assert await sqlite_store.count() == 5

    @pytest.mark.asyncio
    async def test_count_returns_total(self, sqlite_store, sample_event):
        """count() returns the total number of stored events."""
        assert await sqlite_store.count() == 0

        await sqlite_store.append(sample_event)
        assert await sqlite_store.count() == 1

    @pytest.mark.asyncio
    async def test_close_is_safe_to_call_twice(self, tmp_db_path):
        """close() can be called multiple times without error."""
        store = SQLiteEventStore(db_path=tmp_db_path)
        await store.initialize()
        await store.close()
        await store.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_operations_before_initialize_raise(self, tmp_db_path):
        """Calling append/query/count before initialize() raises RuntimeError."""
        store = SQLiteEventStore(db_path=tmp_db_path)

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.append(
                DataFlowAuditEvent(event_type=DataFlowAuditEventType.READ)
            )

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.query()

        with pytest.raises(RuntimeError, match="not initialized"):
            await store.count()


# ---------------------------------------------------------------------------
# SQLiteEventStore: query filtering
# ---------------------------------------------------------------------------


class TestSQLiteEventStoreFiltering:
    """Test query filtering by entity_type, entity_id, event_type, user_id, time range."""

    @pytest.fixture(autouse=True)
    async def _seed_events(self, sqlite_store):
        """Seed the store with a variety of events."""
        self.store = sqlite_store
        self.base_time = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)

        events = [
            DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.CREATE,
                timestamp=self.base_time,
                user_id="alice",
                entity_type="User",
                entity_id="u-1",
                changes={"name": "Alice"},
            ),
            DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.UPDATE,
                timestamp=self.base_time + timedelta(minutes=1),
                user_id="bob",
                entity_type="User",
                entity_id="u-1",
                changes={"name": "Alice B."},
            ),
            DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.CREATE,
                timestamp=self.base_time + timedelta(minutes=2),
                user_id="alice",
                entity_type="Product",
                entity_id="p-1",
                changes={"title": "Widget"},
            ),
            DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.DELETE,
                timestamp=self.base_time + timedelta(minutes=3),
                user_id="admin",
                entity_type="User",
                entity_id="u-2",
            ),
            DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.READ,
                timestamp=self.base_time + timedelta(minutes=4),
                user_id="alice",
                entity_type="User",
                entity_id="u-1",
            ),
        ]
        for e in events:
            await self.store.append(e)

    @pytest.mark.asyncio
    async def test_filter_by_entity_type(self):
        """Filter events by entity_type."""
        results = await self.store.query(entity_type="User")
        assert len(results) == 4
        assert all(e.entity_type == "User" for e in results)

    @pytest.mark.asyncio
    async def test_filter_by_entity_id(self):
        """Filter events by entity_id."""
        results = await self.store.query(entity_id="u-1")
        assert len(results) == 3
        assert all(e.entity_id == "u-1" for e in results)

    @pytest.mark.asyncio
    async def test_filter_by_event_type(self):
        """Filter events by event_type enum."""
        results = await self.store.query(event_type=DataFlowAuditEventType.CREATE)
        assert len(results) == 2
        assert all(e.event_type == DataFlowAuditEventType.CREATE for e in results)

    @pytest.mark.asyncio
    async def test_filter_by_user_id(self):
        """Filter events by user_id."""
        results = await self.store.query(user_id="alice")
        assert len(results) == 3
        assert all(e.user_id == "alice" for e in results)

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self):
        """Filter events by start_time and end_time."""
        start = self.base_time + timedelta(minutes=1)
        end = self.base_time + timedelta(minutes=3)
        results = await self.store.query(start_time=start, end_time=end)
        assert len(results) == 3  # minutes 1, 2, 3

    @pytest.mark.asyncio
    async def test_filter_combined(self):
        """Multiple filters are AND-combined."""
        results = await self.store.query(
            entity_type="User",
            user_id="alice",
            event_type=DataFlowAuditEventType.CREATE,
        )
        assert len(results) == 1
        assert results[0].entity_id == "u-1"

    @pytest.mark.asyncio
    async def test_count_with_filters(self):
        """count() respects filters."""
        count = await self.store.count(entity_type="User")
        assert count == 4

        count = await self.store.count(user_id="admin")
        assert count == 1

    @pytest.mark.asyncio
    async def test_query_order_is_timestamp_desc(self):
        """Events are returned newest-first."""
        results = await self.store.query()
        timestamps = [e.timestamp for e in results]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# SQLiteEventStore: pagination
# ---------------------------------------------------------------------------


class TestSQLiteEventStorePagination:
    """Test limit and offset parameters."""

    @pytest.fixture(autouse=True)
    async def _seed_events(self, sqlite_store):
        self.store = sqlite_store
        for i in range(20):
            event = DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.CREATE,
                timestamp=datetime(2026, 4, 1, 12, 0, i, tzinfo=UTC),
                entity_type="Item",
                entity_id=f"item-{i}",
            )
            await self.store.append(event)

    @pytest.mark.asyncio
    async def test_limit(self):
        """limit restricts the number of returned events."""
        results = await self.store.query(limit=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_offset(self):
        """offset skips events."""
        all_events = await self.store.query(limit=20)
        offset_events = await self.store.query(limit=5, offset=5)

        assert len(offset_events) == 5
        # Offset events should match the 6th-10th events from all_events
        assert [e.entity_id for e in offset_events] == [
            e.entity_id for e in all_events[5:10]
        ]

    @pytest.mark.asyncio
    async def test_offset_beyond_total(self):
        """offset beyond total returns empty list."""
        results = await self.store.query(offset=100)
        assert results == []

    @pytest.mark.asyncio
    async def test_default_limit_is_100(self):
        """Default limit is 100 (all 20 events returned)."""
        results = await self.store.query()
        assert len(results) == 20


# ---------------------------------------------------------------------------
# SQLiteEventStore: persistence across close/reopen
# ---------------------------------------------------------------------------


class TestSQLiteEventStorePersistence:
    """Test that events survive close and reopen."""

    @pytest.mark.asyncio
    async def test_events_survive_close_reopen(self, tmp_db_path):
        """Write events, close, reopen, and verify they are still there."""
        # Write
        store = SQLiteEventStore(db_path=tmp_db_path)
        await store.initialize()

        event = DataFlowAuditEvent(
            event_type=DataFlowAuditEventType.CREATE,
            timestamp=datetime.now(UTC),
            user_id="tester",
            entity_type="Order",
            entity_id="ord-1",
            changes={"total": 42.0},
            metadata={"env": "test"},
        )
        await store.append(event)
        assert await store.count() == 1

        # Close
        await store.close()

        # Reopen
        store2 = SQLiteEventStore(db_path=tmp_db_path)
        await store2.initialize()

        events = await store2.query()
        assert len(events) == 1
        assert events[0].entity_type == "Order"
        assert events[0].entity_id == "ord-1"
        assert events[0].changes == {"total": 42.0}
        assert events[0].metadata == {"env": "test"}
        assert events[0].user_id == "tester"

        await store2.close()


# ---------------------------------------------------------------------------
# SQLiteEventStore: concurrent appends
# ---------------------------------------------------------------------------


class TestSQLiteEventStoreConcurrency:
    """Test concurrent append safety with WAL mode."""

    @pytest.mark.asyncio
    async def test_concurrent_appends(self, sqlite_store):
        """Multiple concurrent appends all succeed."""

        async def append_event(idx: int):
            event = DataFlowAuditEvent(
                event_type=DataFlowAuditEventType.CREATE,
                timestamp=datetime.now(UTC),
                entity_type="ConcurrentItem",
                entity_id=f"c-{idx}",
            )
            await sqlite_store.append(event)

        # Run 50 concurrent appends
        await asyncio.gather(*(append_event(i) for i in range(50)))

        count = await sqlite_store.count(entity_type="ConcurrentItem")
        assert count == 50


# ---------------------------------------------------------------------------
# AuditIntegration: backend wiring
# ---------------------------------------------------------------------------


class TestAuditIntegrationWithBackend:
    """Test AuditIntegration with an EventStoreBackend attached."""

    @pytest.mark.asyncio
    async def test_log_event_persists_to_backend(self, sqlite_store):
        """log_event() stores in-memory AND schedules backend persist."""
        integration = AuditIntegration(enabled=True, backend=sqlite_store)

        event = integration.log_event(
            event_type=DataFlowAuditEventType.CREATE,
            entity_type="Widget",
            entity_id="w-1",
            user_id="tester",
            changes={"color": "red"},
        )

        assert event is not None
        assert len(integration.events) == 1

        # Give the fire-and-forget task a moment to complete
        await asyncio.sleep(0.1)

        # Verify in backend
        stored = await sqlite_store.query(entity_type="Widget")
        assert len(stored) == 1
        assert stored[0].entity_id == "w-1"

    @pytest.mark.asyncio
    async def test_get_trail_queries_backend(self, sqlite_store):
        """get_trail() queries the backend when available."""
        integration = AuditIntegration(enabled=True, backend=sqlite_store)

        # Directly append to backend (simulating prior session data)
        event = DataFlowAuditEvent(
            event_type=DataFlowAuditEventType.UPDATE,
            timestamp=datetime.now(UTC),
            entity_type="User",
            entity_id="u-42",
            changes={"email": "new@example.com"},
        )
        await sqlite_store.append(event)

        trail = await integration.get_trail("User", "u-42")
        assert len(trail) == 1
        assert trail[0].changes == {"email": "new@example.com"}

    @pytest.mark.asyncio
    async def test_query_forwards_to_backend(self, sqlite_store):
        """query() delegates to backend with all filters."""
        integration = AuditIntegration(enabled=True, backend=sqlite_store)

        event = DataFlowAuditEvent(
            event_type=DataFlowAuditEventType.DELETE,
            timestamp=datetime.now(UTC),
            user_id="admin",
            entity_type="Order",
            entity_id="ord-99",
        )
        await sqlite_store.append(event)

        results = await integration.query(
            entity_type="Order",
            user_id="admin",
        )
        assert len(results) == 1
        assert results[0].event_type == DataFlowAuditEventType.DELETE

    @pytest.mark.asyncio
    async def test_backend_property_accessible(self, sqlite_store):
        """The backend property exposes the configured store."""
        integration = AuditIntegration(enabled=True, backend=sqlite_store)
        assert integration.backend is sqlite_store


# ---------------------------------------------------------------------------
# AuditIntegration: in-memory fallback (backward compat)
# ---------------------------------------------------------------------------


class TestAuditIntegrationInMemory:
    """Test that AuditIntegration works without a backend (backward compat)."""

    def test_log_event_without_backend(self):
        """log_event() works with no backend (in-memory only)."""
        integration = AuditIntegration(enabled=True)

        event = integration.log_event(
            event_type=DataFlowAuditEventType.READ,
            entity_type="Config",
            entity_id="cfg-1",
        )

        assert event is not None
        assert len(integration.events) == 1
        assert integration.backend is None

    def test_disabled_integration_returns_none(self):
        """When disabled, log_event() returns None and stores nothing."""
        integration = AuditIntegration(enabled=False)

        event = integration.log_event(
            event_type=DataFlowAuditEventType.CREATE,
            entity_type="Ignored",
        )

        assert event is None
        assert len(integration.events) == 0

    @pytest.mark.asyncio
    async def test_query_in_memory_fallback(self):
        """query() falls back to in-memory filtering without a backend."""
        integration = AuditIntegration(enabled=True)

        integration.log_event(
            event_type=DataFlowAuditEventType.CREATE,
            entity_type="User",
            entity_id="u-1",
            user_id="alice",
        )
        integration.log_event(
            event_type=DataFlowAuditEventType.DELETE,
            entity_type="User",
            entity_id="u-2",
            user_id="bob",
        )

        results = await integration.query(user_id="alice")
        assert len(results) == 1
        assert results[0].entity_id == "u-1"

    @pytest.mark.asyncio
    async def test_get_trail_in_memory_fallback(self):
        """get_trail() filters in-memory when no backend."""
        integration = AuditIntegration(enabled=True)

        integration.log_event(
            event_type=DataFlowAuditEventType.CREATE,
            entity_type="Order",
            entity_id="ord-5",
        )
        integration.log_event(
            event_type=DataFlowAuditEventType.CREATE,
            entity_type="Product",
            entity_id="p-1",
        )

        trail = await integration.get_trail("Order", "ord-5")
        assert len(trail) == 1
        assert trail[0].entity_type == "Order"


# ---------------------------------------------------------------------------
# Timezone-aware timestamps
# ---------------------------------------------------------------------------


class TestTimezoneAwareTimestamps:
    """Test that datetime.now(UTC) timestamps work with query filters."""

    @pytest.mark.asyncio
    async def test_timezone_aware_query_params(self, sqlite_store):
        """Timezone-aware start_time/end_time work with stored events."""
        now = datetime.now(UTC)

        event = DataFlowAuditEvent(
            event_type=DataFlowAuditEventType.CREATE,
            timestamp=now,
            entity_type="Timestamped",
            entity_id="ts-1",
        )
        await sqlite_store.append(event)

        # Query with timezone-aware bounds
        results = await sqlite_store.query(
            start_time=now - timedelta(seconds=1),
            end_time=now + timedelta(seconds=1),
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_event_default_timestamp_is_utc(self):
        """DataFlowAuditEvent default timestamp uses UTC."""
        event = DataFlowAuditEvent(
            event_type=DataFlowAuditEventType.READ,
        )
        # The timestamp should be timezone-aware (UTC)
        assert event.timestamp.tzinfo is not None or event.timestamp.tzinfo == UTC


# ---------------------------------------------------------------------------
# EventStoreBackend ABC
# ---------------------------------------------------------------------------


class TestEventStoreBackendABC:
    """Test that EventStoreBackend is a proper ABC."""

    def test_cannot_instantiate_abc(self):
        """EventStoreBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            EventStoreBackend()

    def test_sqlite_is_subclass(self):
        """SQLiteEventStore is a proper subclass."""
        assert issubclass(SQLiteEventStore, EventStoreBackend)

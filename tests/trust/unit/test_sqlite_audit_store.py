# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for SqliteAuditStore (SPEC-08).

Covers:
- Table creation and schema
- Append with chain linkage validation
- Persistence across reads
- Query with AuditFilter
- Chain integrity verification (WAL mode)
- create_and_append convenience method
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
from kailash.trust.audit_store import (
    _GENESIS_HASH,
    AuditEvent,
    AuditFilter,
    ChainIntegrityError,
    SqliteAuditStore,
    _compute_event_hash,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Use a unique shared-cache URI per test to avoid cross-test interference.
_COUNTER = 0


def _unique_memory_uri() -> str:
    global _COUNTER
    _COUNTER += 1
    return f"file:audit_test_{_COUNTER}?mode=memory&cache=shared"


@pytest.fixture
async def store():
    """Provide an initialized SqliteAuditStore backed by in-memory SQLite."""
    uri = _unique_memory_uri()
    config = SQLitePoolConfig(db_path=uri, uri=True, max_read_connections=2)
    pool = AsyncSQLitePool(config)
    await pool.initialize()
    s = SqliteAuditStore(pool)
    await s.initialize()
    yield s
    await pool.close()


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


class TestSqliteAuditStoreInit:
    """SqliteAuditStore.initialize must create the table and indices."""

    @pytest.mark.asyncio
    async def test_table_exists_after_init(self, store: SqliteAuditStore):
        """Table should exist after initialize()."""
        async with store._pool.acquire_read() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (store._table_name,),
            )
            row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_idempotent_init(self, store: SqliteAuditStore):
        """Calling initialize() twice must not fail."""
        await store.initialize()  # second call

    @pytest.mark.asyncio
    async def test_invalid_table_name_rejected(self):
        """Table names with SQL injection characters must be rejected."""
        uri = _unique_memory_uri()
        config = SQLitePoolConfig(db_path=uri, uri=True)
        pool = AsyncSQLitePool(config)
        await pool.initialize()
        with pytest.raises(ValueError, match="Invalid table name"):
            SqliteAuditStore(pool, table_name="drop table; --")
        await pool.close()


# ---------------------------------------------------------------------------
# Append and persistence
# ---------------------------------------------------------------------------


class TestSqliteAppend:
    """SqliteAuditStore.append must persist events with chain validation."""

    @pytest.mark.asyncio
    async def test_append_single(self, store: SqliteAuditStore):
        prev = await store._get_last_hash()
        event = store.create_event(
            actor="agent-1",
            action="analyze",
            resource="dataset-1",
            prev_hash=prev,
        )
        await store.append(event)

        # Verify persisted
        results = await store.query(AuditFilter())
        assert len(results) == 1
        assert results[0].event_id == event.event_id

    @pytest.mark.asyncio
    async def test_append_three_events(self, store: SqliteAuditStore):
        for i in range(3):
            await store.create_and_append(
                actor=f"agent-{i}",
                action="process",
                resource=f"item-{i}",
            )
        results = await store.query(AuditFilter())
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_append_rejects_broken_chain(self, store: SqliteAuditStore):
        """Event with wrong prev_hash must be rejected."""
        await store.create_and_append(actor="a", action="first")

        wrong_prev = "f" * 64
        h = _compute_event_hash(
            event_id="bad",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="a",
            action="bad",
            resource="",
            outcome="success",
            prev_hash=wrong_prev,
            parent_anchor_id=None,
            duration_ms=None,
            metadata={},
        )
        bad_event = AuditEvent(
            event_id="bad",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="a",
            action="bad",
            resource="",
            outcome="success",
            prev_hash=wrong_prev,
            hash=h,
        )
        with pytest.raises(ChainIntegrityError):
            await store.append(bad_event)

    @pytest.mark.asyncio
    async def test_append_rejects_tampered_hash(self, store: SqliteAuditStore):
        """Event with tampered content hash must be rejected."""
        prev = await store._get_last_hash()
        tampered = AuditEvent(
            event_id="tampered",
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor="a",
            action="bad",
            resource="",
            outcome="success",
            prev_hash=prev,
            hash="0" * 64,
        )
        with pytest.raises(ChainIntegrityError):
            await store.append(tampered)


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestSqliteQuery:
    """SqliteAuditStore.query must filter correctly."""

    @pytest.mark.asyncio
    async def _populate(self, store: SqliteAuditStore):
        actors = ["alice", "bob", "alice"]
        actions = ["read", "write", "read"]
        resources = ["file-1", "file-2", "file-3"]
        outcomes = ["success", "failure", "denied"]
        for actor, action, resource, outcome in zip(
            actors, actions, resources, outcomes
        ):
            await store.create_and_append(
                actor=actor,
                action=action,
                resource=resource,
                outcome=outcome,
            )

    @pytest.mark.asyncio
    async def test_query_no_filter(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter())
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_by_actor(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(actor="alice"))
        assert len(results) == 2
        assert all(e.actor == "alice" for e in results)

    @pytest.mark.asyncio
    async def test_query_by_action(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(action="write"))
        assert len(results) == 1
        assert results[0].actor == "bob"

    @pytest.mark.asyncio
    async def test_query_by_resource(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(resource="file-2"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_outcome(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(outcome="denied"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_with_limit(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(limit=2))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_combined_filters(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(actor="alice", action="read"))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_no_match(self, store: SqliteAuditStore):
        await self._populate(store)
        results = await store.query(AuditFilter(actor="charlie"))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_query_time_range(self, store: SqliteAuditStore):
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        for i in range(5):
            ts = (base + timedelta(hours=i)).isoformat()
            prev = await store._get_last_hash()
            event = store.create_event(
                actor="agent",
                action="step",
                resource=f"r-{i}",
                timestamp=ts,
                prev_hash=prev,
            )
            await store.append(event)

        since = base + timedelta(hours=1)
        until = base + timedelta(hours=3)
        results = await store.query(AuditFilter(since=since, until=until))
        assert len(results) == 3  # hours 1, 2, 3


# ---------------------------------------------------------------------------
# Chain integrity verification
# ---------------------------------------------------------------------------


class TestSqliteVerifyChain:
    """SqliteAuditStore.verify_chain must detect integrity issues."""

    @pytest.mark.asyncio
    async def test_empty_store_valid(self, store: SqliteAuditStore):
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_single_event_valid(self, store: SqliteAuditStore):
        await store.create_and_append(actor="a", action="b")
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_multi_event_chain_valid(self, store: SqliteAuditStore):
        for i in range(10):
            await store.create_and_append(
                actor=f"agent-{i % 3}",
                action="process",
                resource=f"item-{i}",
            )
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_metadata_survives_round_trip(self, store: SqliteAuditStore):
        """Metadata must be correctly serialized and deserialized."""
        await store.create_and_append(
            actor="a",
            action="b",
            metadata={"key": "value", "nested": {"x": 1}},
        )
        results = await store.query(AuditFilter())
        assert len(results) == 1
        assert results[0].metadata["key"] == "value"
        assert results[0].metadata["nested"]["x"] == 1
        assert results[0].verify_integrity() is True

    @pytest.mark.asyncio
    async def test_duration_ms_round_trip(self, store: SqliteAuditStore):
        await store.create_and_append(
            actor="a",
            action="b",
            duration_ms=123.456,
        )
        results = await store.query(AuditFilter())
        assert results[0].duration_ms == pytest.approx(123.456)

    @pytest.mark.asyncio
    async def test_parent_anchor_id_round_trip(self, store: SqliteAuditStore):
        await store.create_and_append(
            actor="a",
            action="b",
            parent_anchor_id="parent-xyz",
        )
        results = await store.query(AuditFilter())
        assert results[0].parent_anchor_id == "parent-xyz"


# ---------------------------------------------------------------------------
# create_and_append convenience
# ---------------------------------------------------------------------------


class TestSqliteCreateAndAppend:
    """create_and_append must atomically create and persist."""

    @pytest.mark.asyncio
    async def test_create_and_append_returns_event(self, store: SqliteAuditStore):
        event = await store.create_and_append(
            actor="agent-1",
            action="analyze",
            resource="ds-1",
            outcome="success",
            duration_ms=50.0,
            metadata={"source": "test"},
        )
        assert event.actor == "agent-1"
        assert event.duration_ms == 50.0
        assert event.verify_integrity() is True

    @pytest.mark.asyncio
    async def test_create_and_append_chain(self, store: SqliteAuditStore):
        """Multiple create_and_append calls must form a valid chain."""
        for i in range(5):
            await store.create_and_append(actor="a", action="step", resource=f"r-{i}")
        assert await store.verify_chain() is True
        results = await store.query(AuditFilter())
        assert len(results) == 5


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestSqliteClose:
    """SqliteAuditStore.close is a no-op (pool lifecycle managed externally)."""

    @pytest.mark.asyncio
    async def test_close_does_not_crash(self, store: SqliteAuditStore):
        await store.close()

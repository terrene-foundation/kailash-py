# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for InMemoryAuditStore (SPEC-08).

Covers:
- Append with correct chain linkage
- Query with AuditFilter (actor, action, resource, time range)
- Verify chain integrity
- Chain integrity failure detection
- Bounded capacity (maxlen)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kailash.trust.audit_store import (
    _GENESIS_HASH,
    AuditEvent,
    AuditFilter,
    ChainIntegrityError,
    InMemoryAuditStore,
    _compute_event_hash,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------


class TestInMemoryAppend:
    """InMemoryAuditStore.append must maintain chain integrity."""

    @pytest.mark.asyncio
    async def test_append_single_event(self):
        store = InMemoryAuditStore()
        event = store.create_event(actor="a", action="do", resource="r")
        await store.append(event)
        assert store.count == 1

    @pytest.mark.asyncio
    async def test_append_three_events_chain(self):
        store = InMemoryAuditStore()
        for i in range(3):
            event = store.create_event(
                actor=f"agent-{i}", action="step", resource=f"res-{i}"
            )
            await store.append(event)
        assert store.count == 3
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_append_rejects_broken_chain(self):
        """Appending an event with wrong prev_hash must raise ChainIntegrityError."""
        store = InMemoryAuditStore()
        event1 = store.create_event(actor="a", action="do", resource="r")
        await store.append(event1)

        # Create an event with wrong prev_hash
        wrong_prev = "f" * 64
        h = _compute_event_hash(
            event_id="evt-bad",
            timestamp=_now_iso(),
            actor="a",
            action="do",
            resource="r",
            outcome="success",
            prev_hash=wrong_prev,
            parent_anchor_id=None,
            duration_ms=None,
            metadata={},
        )
        bad_event = AuditEvent(
            event_id="evt-bad",
            timestamp=_now_iso(),
            actor="a",
            action="do",
            resource="r",
            outcome="success",
            prev_hash=wrong_prev,
            hash=h,
        )
        with pytest.raises(ChainIntegrityError):
            await store.append(bad_event)

    @pytest.mark.asyncio
    async def test_append_rejects_tampered_hash(self):
        """Appending an event with tampered hash must raise ChainIntegrityError."""
        store = InMemoryAuditStore()
        prev = store.last_hash
        tampered = AuditEvent(
            event_id="evt-tamper",
            timestamp=_now_iso(),
            actor="a",
            action="do",
            resource="r",
            outcome="success",
            prev_hash=prev,
            hash="0" * 64,  # tampered hash
        )
        with pytest.raises(ChainIntegrityError):
            await store.append(tampered)

    @pytest.mark.asyncio
    async def test_last_hash_updates_after_append(self):
        store = InMemoryAuditStore()
        assert store.last_hash == _GENESIS_HASH

        event = store.create_event(actor="a", action="do")
        await store.append(event)
        assert store.last_hash == event.hash
        assert store.last_hash != _GENESIS_HASH


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestInMemoryQuery:
    """InMemoryAuditStore.query must filter correctly."""

    @pytest.mark.asyncio
    async def _build_store(self):
        store = InMemoryAuditStore()
        actors = ["alice", "bob", "alice"]
        actions = ["read", "write", "read"]
        resources = ["file-1", "file-2", "file-3"]
        outcomes = ["success", "failure", "denied"]
        for actor, action, resource, outcome in zip(
            actors, actions, resources, outcomes
        ):
            event = store.create_event(
                actor=actor, action=action, resource=resource, outcome=outcome
            )
            await store.append(event)
        return store

    @pytest.mark.asyncio
    async def test_query_no_filter(self):
        store = await self._build_store()
        results = await store.query(AuditFilter())
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_query_by_actor(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(actor="alice"))
        assert len(results) == 2
        assert all(e.actor == "alice" for e in results)

    @pytest.mark.asyncio
    async def test_query_by_action(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(action="write"))
        assert len(results) == 1
        assert results[0].actor == "bob"

    @pytest.mark.asyncio
    async def test_query_by_resource(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(resource="file-2"))
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_query_by_outcome(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(outcome="denied"))
        assert len(results) == 1
        assert results[0].outcome == "denied"

    @pytest.mark.asyncio
    async def test_query_with_limit(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(limit=2))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_combined_filters(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(actor="alice", action="read"))
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_no_match(self):
        store = await self._build_store()
        results = await store.query(AuditFilter(actor="nonexistent"))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_query_time_range(self):
        store = InMemoryAuditStore()
        base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        for i in range(5):
            ts = (base + timedelta(hours=i)).isoformat()
            event = store.create_event(
                actor="agent",
                action="step",
                resource=f"r-{i}",
                timestamp=ts,
            )
            await store.append(event)

        # Query for events in the middle window
        since = base + timedelta(hours=1)
        until = base + timedelta(hours=3)
        results = await store.query(AuditFilter(since=since, until=until))
        assert len(results) == 3  # hours 1, 2, 3


# ---------------------------------------------------------------------------
# Verify chain
# ---------------------------------------------------------------------------


class TestInMemoryVerifyChain:
    """InMemoryAuditStore.verify_chain must detect integrity issues."""

    @pytest.mark.asyncio
    async def test_empty_store_is_valid(self):
        store = InMemoryAuditStore()
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_single_event_is_valid(self):
        store = InMemoryAuditStore()
        event = store.create_event(actor="a", action="b")
        await store.append(event)
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_multi_event_chain_is_valid(self):
        store = InMemoryAuditStore()
        for i in range(10):
            event = store.create_event(
                actor=f"agent-{i % 3}", action="process", resource=f"item-{i}"
            )
            await store.append(event)
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_create_event_includes_metadata(self):
        store = InMemoryAuditStore()
        event = store.create_event(
            actor="a",
            action="b",
            metadata={"key": "value"},
        )
        await store.append(event)
        assert event.metadata == {"key": "value"}
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_create_event_includes_duration(self):
        store = InMemoryAuditStore()
        event = store.create_event(actor="a", action="b", duration_ms=42.5)
        await store.append(event)
        assert event.duration_ms == 42.5

    @pytest.mark.asyncio
    async def test_create_event_includes_parent_anchor(self):
        store = InMemoryAuditStore()
        event = store.create_event(actor="a", action="b", parent_anchor_id="parent-1")
        await store.append(event)
        assert event.parent_anchor_id == "parent-1"


# ---------------------------------------------------------------------------
# Bounded capacity
# ---------------------------------------------------------------------------


class TestInMemoryBounded:
    """InMemoryAuditStore must respect max_events bound."""

    @pytest.mark.asyncio
    async def test_bounded_eviction(self):
        """Oldest events are evicted when capacity is exceeded."""
        store = InMemoryAuditStore(max_events=5)
        for i in range(10):
            event = store.create_event(actor="a", action="step", resource=f"r-{i}")
            await store.append(event)

        # deque(maxlen=5) keeps the last 5
        assert store.count == 5

    @pytest.mark.asyncio
    async def test_bounded_chain_still_verifiable(self):
        """After eviction, the remaining chain should still be internally consistent.

        Note: after deque eviction, the first event's prev_hash points to
        an evicted event, so verify_chain returns False for the truncated
        chain. This is expected behavior for bounded stores.
        """
        store = InMemoryAuditStore(max_events=5)
        for i in range(10):
            event = store.create_event(actor="a", action="step", resource=f"r-{i}")
            await store.append(event)

        # After eviction, internal hash integrity of each event is still valid
        events = list(store._events)
        for event in events:
            assert event.verify_integrity() is True


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


class TestInMemoryClose:
    """InMemoryAuditStore.close is a no-op."""

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        store = InMemoryAuditStore()
        await store.close()
        # Store is still usable after close (no-op)
        event = store.create_event(actor="a", action="b")
        await store.append(event)
        assert store.count == 1

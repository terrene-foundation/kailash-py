# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M3: DeadLetterStore — bounded ring buffer for undeliverable messages.

Tests cover:
- record() and count()
- Ring buffer eviction (oldest evicted when at capacity)
- recent(limit) returns newest first
- drain_for(instance_id) removes and returns matching entries
- Edge cases: empty store, drain non-existent instance
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kaizen.l3.messaging.dead_letters import DeadLetterReason, DeadLetterStore
from kaizen.l3.messaging.types import (
    DelegationPayload,
    MessageEnvelope,
)


def _envelope(
    to_inst: str = "child-001",
    from_inst: str = "parent-001",
) -> MessageEnvelope:
    """Helper to create a test envelope."""
    return MessageEnvelope(
        from_instance=from_inst,
        to_instance=to_inst,
        payload=DelegationPayload(task_description="test"),
    )


class TestDeadLetterReason:
    """Test DeadLetterReason enum variants."""

    def test_all_variants_exist(self):
        assert DeadLetterReason.EXPIRED
        assert DeadLetterReason.RECIPIENT_TERMINATED
        assert DeadLetterReason.RECIPIENT_NOT_FOUND
        assert DeadLetterReason.SENDER_NOT_FOUND
        assert DeadLetterReason.COMMUNICATION_BLOCKED
        assert DeadLetterReason.CHANNEL_CLOSED
        assert DeadLetterReason.CHANNEL_FULL

    def test_variant_count(self):
        assert len(DeadLetterReason) == 7

    def test_str_backed(self):
        """Enum values are strings (EATP convention)."""
        assert isinstance(DeadLetterReason.EXPIRED.value, str)


class TestDeadLetterStoreConstruction:
    """Test store construction."""

    def test_default_capacity(self):
        store = DeadLetterStore()
        assert store.count() == 0

    def test_custom_capacity(self):
        store = DeadLetterStore(max_capacity=5)
        assert store.count() == 0

    def test_capacity_must_be_positive(self):
        with pytest.raises(ValueError, match="max_capacity"):
            DeadLetterStore(max_capacity=0)
        with pytest.raises(ValueError, match="max_capacity"):
            DeadLetterStore(max_capacity=-1)


class TestDeadLetterStoreRecord:
    """Test recording dead letters."""

    def test_record_increments_count(self):
        store = DeadLetterStore(max_capacity=100)
        store.record(_envelope(), DeadLetterReason.EXPIRED)
        assert store.count() == 1
        store.record(_envelope(), DeadLetterReason.CHANNEL_CLOSED)
        assert store.count() == 2

    def test_record_stores_envelope_and_reason(self):
        store = DeadLetterStore(max_capacity=100)
        env = _envelope(to_inst="target-001")
        store.record(env, DeadLetterReason.RECIPIENT_TERMINATED)
        entries = store.recent(1)
        assert len(entries) == 1
        assert entries[0][0].message_id == env.message_id
        assert entries[0][1] == DeadLetterReason.RECIPIENT_TERMINATED

    def test_record_stores_timestamp(self):
        store = DeadLetterStore(max_capacity=100)
        before = datetime.now(UTC)
        store.record(_envelope(), DeadLetterReason.EXPIRED)
        after = datetime.now(UTC)
        entries = store.recent(1)
        assert before <= entries[0][2] <= after


class TestDeadLetterStoreEviction:
    """Test ring buffer eviction semantics."""

    def test_oldest_evicted_when_at_capacity(self):
        store = DeadLetterStore(max_capacity=3)
        envs = []
        for i in range(5):
            env = _envelope(to_inst=f"child-{i}")
            envs.append(env)
            store.record(env, DeadLetterReason.EXPIRED)
        assert store.count() == 3
        # Should have the 3 most recent (child-2, child-3, child-4)
        entries = store.recent(10)
        to_instances = [e[0].to_instance for e in entries]
        assert "child-0" not in to_instances
        assert "child-1" not in to_instances
        assert "child-4" in to_instances
        assert "child-3" in to_instances
        assert "child-2" in to_instances

    def test_capacity_1_keeps_only_latest(self):
        store = DeadLetterStore(max_capacity=1)
        first = _envelope(to_inst="first")
        second = _envelope(to_inst="second")
        store.record(first, DeadLetterReason.EXPIRED)
        store.record(second, DeadLetterReason.CHANNEL_CLOSED)
        assert store.count() == 1
        entries = store.recent(10)
        assert entries[0][0].to_instance == "second"


class TestDeadLetterStoreRecent:
    """Test recent() retrieval."""

    def test_recent_returns_newest_first(self):
        store = DeadLetterStore(max_capacity=100)
        for i in range(5):
            store.record(_envelope(to_inst=f"child-{i}"), DeadLetterReason.EXPIRED)
        entries = store.recent(5)
        # Newest first = child-4, child-3, child-2, child-1, child-0
        assert entries[0][0].to_instance == "child-4"
        assert entries[4][0].to_instance == "child-0"

    def test_recent_with_limit(self):
        store = DeadLetterStore(max_capacity=100)
        for i in range(10):
            store.record(_envelope(to_inst=f"child-{i}"), DeadLetterReason.EXPIRED)
        entries = store.recent(3)
        assert len(entries) == 3
        assert entries[0][0].to_instance == "child-9"

    def test_recent_on_empty_store(self):
        store = DeadLetterStore(max_capacity=100)
        entries = store.recent(5)
        assert entries == []

    def test_recent_limit_exceeds_count(self):
        store = DeadLetterStore(max_capacity=100)
        store.record(_envelope(), DeadLetterReason.EXPIRED)
        entries = store.recent(100)
        assert len(entries) == 1


class TestDeadLetterStoreDrainFor:
    """Test drain_for() — remove and return entries for a specific instance."""

    def test_drain_for_removes_matching_entries(self):
        store = DeadLetterStore(max_capacity=100)
        env1 = _envelope(to_inst="target")
        env2 = _envelope(to_inst="other")
        env3 = _envelope(to_inst="target")
        store.record(env1, DeadLetterReason.EXPIRED)
        store.record(env2, DeadLetterReason.EXPIRED)
        store.record(env3, DeadLetterReason.CHANNEL_CLOSED)

        drained = store.drain_for("target")
        assert len(drained) == 2
        assert store.count() == 1  # Only "other" remains

    def test_drain_for_returns_matching_entries(self):
        store = DeadLetterStore(max_capacity=100)
        env = _envelope(to_inst="target")
        store.record(env, DeadLetterReason.RECIPIENT_NOT_FOUND)
        drained = store.drain_for("target")
        assert len(drained) == 1
        assert drained[0][0].message_id == env.message_id
        assert drained[0][1] == DeadLetterReason.RECIPIENT_NOT_FOUND

    def test_drain_for_nonexistent_instance(self):
        store = DeadLetterStore(max_capacity=100)
        store.record(_envelope(to_inst="other"), DeadLetterReason.EXPIRED)
        drained = store.drain_for("nonexistent")
        assert drained == []
        assert store.count() == 1  # Nothing removed

    def test_drain_for_empty_store(self):
        store = DeadLetterStore(max_capacity=100)
        drained = store.drain_for("any")
        assert drained == []

    def test_drain_for_preserves_reason_and_timestamp(self):
        store = DeadLetterStore(max_capacity=100)
        env = _envelope(to_inst="target")
        store.record(env, DeadLetterReason.COMMUNICATION_BLOCKED)
        drained = store.drain_for("target")
        assert drained[0][1] == DeadLetterReason.COMMUNICATION_BLOCKED
        assert isinstance(drained[0][2], datetime)

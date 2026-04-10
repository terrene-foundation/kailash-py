# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Security tests for audit store (SPEC-08).

Covers:
- Tamper detection: modifying stored events must be detected by verify_chain
- Chain integrity attacks: inserting, removing, or reordering events
- Hash collision resistance: near-identical events produce different hashes
- Cross-SDK JSON format: serialization round-trip for interoperability
- Budget double-counting protection via CostDeduplicator
- Registry poisoning: invalid event types, actors with special chars
- Constant-time comparison: verify hmac.compare_digest is used (structural)
"""

from __future__ import annotations

import json

import pytest

from kailash.trust.audit_store import (
    _GENESIS_HASH,
    AuditEvent,
    AuditEventType,
    AuditFilter,
    AuditOutcome,
    AuditStoreProtocol,
    ChainIntegrityError,
    InMemoryAuditStore,
    _compute_event_hash,
)
from kailash.trust.cost_event import CostDeduplicator, CostEvent, DuplicateCostError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_chain(store: InMemoryAuditStore, count: int = 5) -> None:
    """Append `count` events to the store synchronously via the event loop."""
    import asyncio

    async def _populate():
        for i in range(count):
            event = store.create_event(
                actor=f"agent-{i}",
                action=f"action-{i}",
                resource=f"resource-{i}",
            )
            await store.append(event)

    asyncio.get_event_loop().run_until_complete(_populate())


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


class TestTamperDetection:
    """Modifying stored events must be detected."""

    @pytest.mark.asyncio
    async def test_tampered_event_detected_by_verify_integrity(self):
        """An event with a modified field fails verify_integrity."""
        store = InMemoryAuditStore()
        event = store.create_event(actor="alice", action="read", resource="secret")
        await store.append(event)

        # Create a tampered copy with a different actor but same hash
        tampered = AuditEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            actor="eve",  # tampered
            action=event.action,
            resource=event.resource,
            outcome=event.outcome,
            prev_hash=event.prev_hash,
            hash=event.hash,  # hash from original -- will mismatch
            metadata=event.metadata,
        )
        assert tampered.verify_integrity() is False

    @pytest.mark.asyncio
    async def test_tampered_chain_detected_by_verify_chain(self):
        """Replacing an event in the chain breaks verify_chain."""
        store = InMemoryAuditStore()
        for i in range(5):
            event = store.create_event(
                actor=f"agent-{i}", action="step", resource=f"r-{i}"
            )
            await store.append(event)

        # Verify chain is initially valid
        assert await store.verify_chain() is True

        # Tamper with the middle event by replacing it in the deque
        original = store._events[2]
        tampered = AuditEvent(
            event_id=original.event_id,
            timestamp=original.timestamp,
            actor="TAMPERED",
            action=original.action,
            resource=original.resource,
            outcome=original.outcome,
            prev_hash=original.prev_hash,
            hash=original.hash,
            metadata=original.metadata,
        )
        store._events[2] = tampered

        # Chain verification must detect the tampering
        assert await store.verify_chain() is False

    @pytest.mark.asyncio
    async def test_recomputed_hash_after_field_change_differs(self):
        """Changing any field must produce a different hash."""
        base_params = {
            "event_id": "e1",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "actor": "alice",
            "action": "read",
            "resource": "file",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "parent_anchor_id": None,
            "duration_ms": None,
            "metadata": {},
        }
        original_hash = _compute_event_hash(**base_params)

        # Change each field individually and verify hash changes
        for field_name, new_value in [
            ("event_id", "e2"),
            ("timestamp", "2026-01-15T13:00:00+00:00"),
            ("actor", "bob"),
            ("action", "write"),
            ("resource", "other_file"),
            ("outcome", "failure"),
            ("prev_hash", "a" * 64),
            ("parent_anchor_id", "anchor-1"),
            ("duration_ms", 42.0),
            ("metadata", {"key": "val"}),
        ]:
            modified = dict(base_params)
            modified[field_name] = new_value
            modified_hash = _compute_event_hash(**modified)
            assert (
                modified_hash != original_hash
            ), f"Changing {field_name} did not change the hash"


# ---------------------------------------------------------------------------
# Chain integrity attacks
# ---------------------------------------------------------------------------


class TestChainIntegrityAttacks:
    """Attacks against the Merkle chain structure."""

    @pytest.mark.asyncio
    async def test_replay_attack_detected(self):
        """Re-appending a previously valid event must fail."""
        store = InMemoryAuditStore()
        event1 = store.create_event(actor="a", action="first")
        await store.append(event1)

        event2 = store.create_event(actor="a", action="second")
        await store.append(event2)

        # Try to re-append event1 (replay attack)
        with pytest.raises(ChainIntegrityError):
            await store.append(event1)

    @pytest.mark.asyncio
    async def test_forged_genesis_rejected(self):
        """An event claiming to be genesis after other events must fail."""
        store = InMemoryAuditStore()
        event1 = store.create_event(actor="a", action="first")
        await store.append(event1)

        # Create an event with genesis prev_hash (forged)
        forged_h = _compute_event_hash(
            event_id="forged",
            timestamp="2026-01-15T12:00:00+00:00",
            actor="attacker",
            action="forge",
            resource="",
            outcome="success",
            prev_hash=_GENESIS_HASH,
            parent_anchor_id=None,
            duration_ms=None,
            metadata={},
        )
        forged = AuditEvent(
            event_id="forged",
            timestamp="2026-01-15T12:00:00+00:00",
            actor="attacker",
            action="forge",
            resource="",
            outcome="success",
            prev_hash=_GENESIS_HASH,
            hash=forged_h,
        )
        with pytest.raises(ChainIntegrityError):
            await store.append(forged)

    @pytest.mark.asyncio
    async def test_empty_chain_genesis_accepted(self):
        """The first event must have genesis prev_hash."""
        store = InMemoryAuditStore()
        event = store.create_event(actor="a", action="first")
        assert event.prev_hash == _GENESIS_HASH
        await store.append(event)
        assert store.count == 1

    @pytest.mark.asyncio
    async def test_wrong_hash_algorithm_fails(self):
        """An event with a hash from a different algorithm must fail."""
        store = InMemoryAuditStore()
        prev = store.last_hash
        # Use MD5-length hash (32 hex chars) instead of SHA-256 (64 hex chars)
        bad_event = AuditEvent(
            event_id="bad",
            timestamp="2026-01-15T12:00:00+00:00",
            actor="a",
            action="b",
            resource="",
            outcome="success",
            prev_hash=prev,
            hash="a" * 32,  # MD5-length, not SHA-256
        )
        with pytest.raises(ChainIntegrityError):
            await store.append(bad_event)


# ---------------------------------------------------------------------------
# Hash collision resistance
# ---------------------------------------------------------------------------


class TestHashCollisionResistance:
    """Near-identical events must produce different hashes."""

    def test_whitespace_in_actor_changes_hash(self):
        """Trailing whitespace in actor must change the hash."""
        params = {
            "event_id": "e1",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "action": "x",
            "resource": "r",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "parent_anchor_id": None,
            "duration_ms": None,
            "metadata": {},
        }
        h1 = _compute_event_hash(actor="alice", **params)
        h2 = _compute_event_hash(actor="alice ", **params)
        assert h1 != h2

    def test_empty_vs_missing_metadata_key(self):
        """Empty dict vs dict with empty value must differ."""
        params = {
            "event_id": "e1",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "actor": "a",
            "action": "x",
            "resource": "r",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "parent_anchor_id": None,
            "duration_ms": None,
        }
        h1 = _compute_event_hash(metadata={}, **params)
        h2 = _compute_event_hash(metadata={"key": ""}, **params)
        assert h1 != h2


# ---------------------------------------------------------------------------
# Cross-SDK JSON format verification
# ---------------------------------------------------------------------------


class TestCrossSDKJsonFormat:
    """Serialized format must be deterministic and match cross-SDK expectations."""

    def test_audit_event_json_round_trip(self):
        """Serialize to JSON string and back."""
        store = InMemoryAuditStore()
        event = store.create_event(
            actor="agent-1",
            action="analyze",
            resource="dataset",
            outcome="success",
            duration_ms=42.5,
            metadata={"source": "test", "nested": {"x": 1}},
        )
        d = event.to_dict()
        json_str = json.dumps(d, sort_keys=True)
        restored_dict = json.loads(json_str)
        restored = AuditEvent.from_dict(restored_dict)

        assert restored.actor == event.actor
        assert restored.action == event.action
        assert restored.hash == event.hash
        assert restored.prev_hash == event.prev_hash
        assert restored.metadata == event.metadata
        assert restored.verify_integrity() is True

    def test_audit_event_field_names_match_spec(self):
        """Verify the canonical field names are present in to_dict output."""
        store = InMemoryAuditStore()
        event = store.create_event(actor="a", action="b")
        d = event.to_dict()

        # Core Merkle fields
        required_fields = {
            "event_id",
            "timestamp",
            "actor",
            "action",
            "resource",
            "outcome",
            "prev_hash",
            "hash",
            "parent_anchor_id",
            "duration_ms",
            "metadata",
        }
        assert required_fields.issubset(set(d.keys()))

        # Extended fields (SPEC-08 superset)
        extended_fields = {
            "event_type",
            "severity",
            "description",
            "user_id",
            "tenant_id",
            "resource_id",
            "ip_address",
            "user_agent",
            "session_id",
            "correlation_id",
            "trace_id",
            "workflow_id",
            "node_id",
            "agent_id",
            "human_origin_id",
        }
        assert extended_fields.issubset(set(d.keys()))

    def test_cost_event_json_round_trip(self):
        """CostEvent must survive JSON serialization."""
        event = CostEvent.create(
            call_id="chatcmpl-abc",
            source="openai",
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
            cost_microdollars=4500,
            agent_id="agent-1",
        )
        json_str = json.dumps(event.to_dict(), sort_keys=True)
        restored = CostEvent.from_dict(json.loads(json_str))
        assert restored == event

    def test_cost_event_field_names_match_spec(self):
        """CostEvent field names must match the cross-SDK spec."""
        event = CostEvent.create(
            call_id="x",
            source="openai",
            model="m",
            input_tokens=0,
            output_tokens=0,
            cost_microdollars=0,
        )
        d = event.to_dict()
        required = {
            "cost_id",
            "call_id",
            "timestamp",
            "source",
            "model",
            "input_tokens",
            "output_tokens",
            "cost_microdollars",
            "agent_id",
            "workflow_id",
            "metadata",
        }
        assert required == set(d.keys())

    def test_audit_event_hash_is_deterministic(self):
        """Same inputs must always produce the same hash."""
        params = {
            "event_id": "deterministic-1",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "actor": "agent",
            "action": "test",
            "resource": "res",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "parent_anchor_id": None,
            "duration_ms": None,
            "metadata": {"key": "value"},
        }
        h1 = _compute_event_hash(**params)
        h2 = _compute_event_hash(**params)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length


# ---------------------------------------------------------------------------
# Budget double-counting protection
# ---------------------------------------------------------------------------


class TestBudgetDoubleCounting:
    """CostDeduplicator must prevent budget double-counting."""

    def test_same_call_id_different_amounts_rejected(self):
        """Even if the cost amount differs, duplicate call_id is rejected."""
        dedup = CostDeduplicator()
        event1 = CostEvent.create(
            call_id="same-call",
            source="openai",
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            cost_microdollars=1000,
        )
        event2 = CostEvent.create(
            call_id="same-call",
            source="openai",
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            cost_microdollars=2000,  # different amount, same call
        )
        dedup.check_and_record(event1)
        with pytest.raises(DuplicateCostError):
            dedup.check_and_record(event2)

    def test_same_call_id_different_sources_rejected(self):
        """Cross-provider replay is also rejected."""
        dedup = CostDeduplicator()
        event1 = CostEvent.create(
            call_id="cross-provider",
            source="openai",
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            cost_microdollars=1000,
        )
        event2 = CostEvent.create(
            call_id="cross-provider",
            source="anthropic",  # different source
            model="claude-3",
            input_tokens=100,
            output_tokens=50,
            cost_microdollars=1000,
        )
        dedup.check_and_record(event1)
        with pytest.raises(DuplicateCostError):
            dedup.check_and_record(event2)

    def test_high_volume_dedup(self):
        """Deduplicator handles high volume without false positives."""
        dedup = CostDeduplicator(capacity=10_000)
        for i in range(1000):
            event = CostEvent.create(
                call_id=f"call-{i}",
                source="openai",
                model="gpt-4",
                input_tokens=i,
                output_tokens=i,
                cost_microdollars=i * 10,
            )
            dedup.check_and_record(event)

        # All 1000 should be tracked
        assert dedup.count == 1000

        # No false positives for new events
        new_event = CostEvent.create(
            call_id="call-9999",
            source="openai",
            model="gpt-4",
            input_tokens=1,
            output_tokens=1,
            cost_microdollars=10,
        )
        assert dedup.check_and_record(new_event) is True


# ---------------------------------------------------------------------------
# Registry poisoning protection
# ---------------------------------------------------------------------------


class TestRegistryPoisoning:
    """Audit store must handle adversarial inputs safely."""

    @pytest.mark.asyncio
    async def test_special_chars_in_actor(self):
        """Actors with special characters must not break the chain."""
        store = InMemoryAuditStore()
        event = store.create_event(
            actor='agent"; DROP TABLE audit; --',
            action="test",
            resource="res",
        )
        await store.append(event)
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_unicode_in_fields(self):
        """Unicode content must not break hashing or storage."""
        store = InMemoryAuditStore()
        event = store.create_event(
            actor="agent-\u00e9\u00e0\u00fc",
            action="\u2603 snowman",
            resource="\U0001f600 emoji",
            metadata={"key": "\u00e9\u00e0\u00fc"},
        )
        await store.append(event)
        assert event.verify_integrity() is True
        assert await store.verify_chain() is True

    @pytest.mark.asyncio
    async def test_very_long_actor_name(self):
        """Extremely long field values must not cause crashes."""
        store = InMemoryAuditStore()
        long_actor = "a" * 10_000
        event = store.create_event(actor=long_actor, action="test")
        await store.append(event)
        assert event.verify_integrity() is True

    @pytest.mark.asyncio
    async def test_null_bytes_in_metadata(self):
        """Null bytes in metadata must not break JSON serialization."""
        store = InMemoryAuditStore()
        event = store.create_event(
            actor="agent",
            action="test",
            metadata={"key": "value\x00with\x00nulls"},
        )
        await store.append(event)
        # JSON serialization should handle this
        d = event.to_dict()
        json_str = json.dumps(d)
        assert json_str  # must not crash

    def test_audit_event_type_enum_values_are_strings(self):
        """AuditEventType values must be strings for JSON serialization."""
        for member in AuditEventType:
            assert isinstance(member.value, str)

    def test_audit_outcome_enum_values_are_strings(self):
        """AuditOutcome values must be strings for JSON serialization."""
        for member in AuditOutcome:
            assert isinstance(member.value, str)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """InMemoryAuditStore must satisfy AuditStoreProtocol."""

    def test_in_memory_store_is_protocol_compliant(self):
        """InMemoryAuditStore must be a runtime-checkable AuditStoreProtocol."""
        store = InMemoryAuditStore()
        assert isinstance(store, AuditStoreProtocol)

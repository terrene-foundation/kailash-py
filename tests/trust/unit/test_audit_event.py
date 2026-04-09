# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for AuditEvent canonical dataclass (SPEC-08).

Covers:
- Frozen immutability
- Serialization round-trip (to_dict / from_dict)
- Hash integrity verification
- Hash chain linkage
"""

from __future__ import annotations

import copy

import pytest

from kailash.trust.audit_store import (
    _GENESIS_HASH,
    AuditEvent,
    AuditFilter,
    AuditQueryError,
    AuditStoreError,
    ChainIntegrityError,
    _compute_event_hash,
)

# ---------------------------------------------------------------------------
# AuditEvent construction and frozen semantics
# ---------------------------------------------------------------------------


class TestAuditEventFrozen:
    """AuditEvent must be immutable (frozen=True)."""

    def _make_event(self, **overrides):
        defaults = {
            "event_id": "evt-001",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "actor": "agent-1",
            "action": "analyze_data",
            "resource": "dataset-42",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "hash": "",  # will be set below
        }
        defaults.update(overrides)
        if not defaults["hash"]:
            defaults["hash"] = _compute_event_hash(
                event_id=defaults["event_id"],
                timestamp=defaults["timestamp"],
                actor=defaults["actor"],
                action=defaults["action"],
                resource=defaults["resource"],
                outcome=defaults["outcome"],
                prev_hash=defaults["prev_hash"],
                parent_anchor_id=defaults.get("parent_anchor_id"),
                duration_ms=defaults.get("duration_ms"),
                metadata=defaults.get("metadata", {}),
            )
        return AuditEvent(**defaults)

    def test_frozen_cannot_set_attribute(self):
        event = self._make_event()
        with pytest.raises(AttributeError):
            event.actor = "someone-else"  # type: ignore[misc]

    def test_frozen_cannot_delete_attribute(self):
        event = self._make_event()
        with pytest.raises(AttributeError):
            del event.actor  # type: ignore[misc]

    def test_all_fields_accessible(self):
        event = self._make_event(
            parent_anchor_id="parent-1",
            duration_ms=42.5,
            metadata={"key": "value"},
        )
        assert event.event_id == "evt-001"
        assert event.actor == "agent-1"
        assert event.action == "analyze_data"
        assert event.resource == "dataset-42"
        assert event.outcome == "success"
        assert event.parent_anchor_id == "parent-1"
        assert event.duration_ms == 42.5
        assert event.metadata == {"key": "value"}

    def test_default_optional_fields(self):
        event = self._make_event()
        assert event.parent_anchor_id is None
        assert event.duration_ms is None
        assert event.metadata == {}


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestAuditEventSerialization:
    """to_dict / from_dict must round-trip cleanly."""

    def _make_event(self, **overrides):
        defaults = {
            "event_id": "evt-rt-001",
            "timestamp": "2026-01-15T12:00:00+00:00",
            "actor": "agent-1",
            "action": "read_data",
            "resource": "file-abc",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "parent_anchor_id": "parent-x",
            "duration_ms": 150.0,
            "metadata": {"source": "test"},
        }
        defaults.update(overrides)
        defaults["hash"] = _compute_event_hash(
            event_id=defaults["event_id"],
            timestamp=defaults["timestamp"],
            actor=defaults["actor"],
            action=defaults["action"],
            resource=defaults["resource"],
            outcome=defaults["outcome"],
            prev_hash=defaults["prev_hash"],
            parent_anchor_id=defaults.get("parent_anchor_id"),
            duration_ms=defaults.get("duration_ms"),
            metadata=defaults.get("metadata", {}),
        )
        return AuditEvent(**defaults)

    def test_round_trip(self):
        event = self._make_event()
        d = event.to_dict()
        restored = AuditEvent.from_dict(d)
        assert restored == event

    def test_to_dict_types(self):
        event = self._make_event()
        d = event.to_dict()
        assert isinstance(d["event_id"], str)
        assert isinstance(d["timestamp"], str)
        assert isinstance(d["metadata"], dict)
        assert d["parent_anchor_id"] == "parent-x"
        assert d["duration_ms"] == 150.0

    def test_from_dict_missing_optional(self):
        """from_dict should handle missing optional fields gracefully."""
        d = {
            "event_id": "evt-min",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "actor": "a",
            "action": "b",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "hash": "abc",
        }
        event = AuditEvent.from_dict(d)
        assert event.resource == ""
        assert event.parent_anchor_id is None
        assert event.duration_ms is None
        assert event.metadata == {}


# ---------------------------------------------------------------------------
# Hash integrity
# ---------------------------------------------------------------------------


class TestAuditEventHashIntegrity:
    """verify_integrity must detect content tampering."""

    def _make_valid_event(self):
        eid = "evt-hash-001"
        ts = "2026-01-15T12:00:00+00:00"
        actor = "agent-1"
        action = "verify_test"
        resource = "res-1"
        outcome = "success"
        prev = _GENESIS_HASH
        meta = {"test": True}

        h = _compute_event_hash(
            event_id=eid,
            timestamp=ts,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            prev_hash=prev,
            parent_anchor_id=None,
            duration_ms=None,
            metadata=meta,
        )
        return AuditEvent(
            event_id=eid,
            timestamp=ts,
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            prev_hash=prev,
            hash=h,
            metadata=meta,
        )

    def test_valid_event_passes_integrity(self):
        event = self._make_valid_event()
        assert event.verify_integrity() is True

    def test_tampered_hash_fails_integrity(self):
        event = self._make_valid_event()
        # Create a new event with a tampered hash
        tampered = AuditEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            actor=event.actor,
            action=event.action,
            resource=event.resource,
            outcome=event.outcome,
            prev_hash=event.prev_hash,
            hash="0" * 64,  # wrong hash
            metadata=event.metadata,
        )
        assert tampered.verify_integrity() is False

    def test_different_content_different_hash(self):
        h1 = _compute_event_hash(
            event_id="e1",
            timestamp="2026-01-01T00:00:00+00:00",
            actor="a",
            action="x",
            resource="r",
            outcome="success",
            prev_hash=_GENESIS_HASH,
            parent_anchor_id=None,
            duration_ms=None,
            metadata={},
        )
        h2 = _compute_event_hash(
            event_id="e1",
            timestamp="2026-01-01T00:00:00+00:00",
            actor="a",
            action="y",  # different action
            resource="r",
            outcome="success",
            prev_hash=_GENESIS_HASH,
            parent_anchor_id=None,
            duration_ms=None,
            metadata={},
        )
        assert h1 != h2

    def test_hash_includes_metadata(self):
        """Metadata changes must produce different hashes."""
        base = {
            "event_id": "e1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "actor": "a",
            "action": "x",
            "resource": "r",
            "outcome": "success",
            "prev_hash": _GENESIS_HASH,
            "parent_anchor_id": None,
            "duration_ms": None,
        }
        h1 = _compute_event_hash(**base, metadata={"a": 1})
        h2 = _compute_event_hash(**base, metadata={"a": 2})
        assert h1 != h2


# ---------------------------------------------------------------------------
# Hash chain linkage
# ---------------------------------------------------------------------------


class TestAuditEventChainLinkage:
    """Events must correctly chain via prev_hash."""

    def test_chain_of_three(self):
        """Build a 3-event chain and verify linkage."""
        events = []
        prev = _GENESIS_HASH

        for i in range(3):
            eid = f"evt-chain-{i}"
            ts = f"2026-01-15T12:0{i}:00+00:00"
            h = _compute_event_hash(
                event_id=eid,
                timestamp=ts,
                actor="agent",
                action="step",
                resource=f"res-{i}",
                outcome="success",
                prev_hash=prev,
                parent_anchor_id=None,
                duration_ms=None,
                metadata={},
            )
            event = AuditEvent(
                event_id=eid,
                timestamp=ts,
                actor="agent",
                action="step",
                resource=f"res-{i}",
                outcome="success",
                prev_hash=prev,
                hash=h,
            )
            assert event.verify_integrity()
            events.append(event)
            prev = h

        # Verify linkage
        assert events[0].prev_hash == _GENESIS_HASH
        assert events[1].prev_hash == events[0].hash
        assert events[2].prev_hash == events[1].hash


# ---------------------------------------------------------------------------
# AuditFilter
# ---------------------------------------------------------------------------


class TestAuditFilter:
    """AuditFilter dataclass tests."""

    def test_default_values(self):
        f = AuditFilter()
        assert f.actor is None
        assert f.action is None
        assert f.resource is None
        assert f.outcome is None
        assert f.since is None
        assert f.until is None
        assert f.limit == 100

    def test_to_dict(self):
        from datetime import datetime, timezone

        f = AuditFilter(actor="a", limit=50)
        d = f.to_dict()
        assert d["actor"] == "a"
        assert d["limit"] == 50
        assert d["since"] is None


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class TestErrorTypes:
    """Error types must inherit from TrustError/AuditStoreError."""

    def test_audit_store_error_inherits_trust_error(self):
        from kailash.trust.exceptions import TrustError

        err = AuditStoreError("test")
        assert isinstance(err, TrustError)

    def test_chain_integrity_error(self):
        err = ChainIntegrityError("broken chain", sequence=5)
        assert isinstance(err, AuditStoreError)
        assert err.sequence == 5
        assert "broken chain" in str(err)

    def test_audit_query_error(self):
        err = AuditQueryError("query failed", filter_info={"actor": "x"})
        assert isinstance(err, AuditStoreError)
        assert err.filter_info == {"actor": "x"}

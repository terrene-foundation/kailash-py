# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for kaizen_agents.audit.trail — EATP Audit Trail.

Tier 1: Unit tests. No external dependencies. Tests audit record creation,
hash chain integrity, bounded collection, query by agent, and export.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import pytest

from kaizen_agents.audit.trail import AuditRecord, AuditTrail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_envelope(limit: float = 10.0) -> dict[str, Any]:
    """Create a minimal envelope dict for testing."""
    return {
        "financial": {"limit": limit},
        "operational": {"allowed": [], "blocked": []},
        "temporal": {},
        "data_access": {"ceiling": "internal", "scopes": []},
        "communication": {"recipients": [], "channels": []},
    }


# ---------------------------------------------------------------------------
# Test: Genesis record
# ---------------------------------------------------------------------------


class TestGenesisRecord:
    """record_genesis should create the first record in the trail."""

    def test_genesis_record_created_correctly(self) -> None:
        """Genesis record should have correct type, agent_id, and envelope in details."""
        trail = AuditTrail()
        envelope = _make_envelope(limit=50.0)

        record = trail.record_genesis(agent_id="agent-root", envelope=envelope)

        assert isinstance(record, AuditRecord)
        assert record.record_type == "genesis"
        assert record.agent_id == "agent-root"
        assert record.parent_id is None
        assert record.details["envelope"] == envelope
        assert record.action == "genesis"
        assert isinstance(record.timestamp, datetime)
        assert record.record_id  # non-empty UUID string

    def test_genesis_record_has_genesis_prev_hash(self) -> None:
        """The first record's prev_hash should be 'genesis'."""
        trail = AuditTrail()
        record = trail.record_genesis(agent_id="agent-root", envelope=_make_envelope())

        assert record.prev_hash == "genesis"

    def test_genesis_record_hash_is_non_empty(self) -> None:
        """The genesis record should have a non-empty record_hash."""
        trail = AuditTrail()
        record = trail.record_genesis(agent_id="agent-root", envelope=_make_envelope())

        assert record.record_hash
        assert len(record.record_hash) == 64  # sha256 hex digest length


# ---------------------------------------------------------------------------
# Test: Delegation record
# ---------------------------------------------------------------------------


class TestDelegationRecord:
    """record_delegation should link parent to child with envelope."""

    def test_delegation_record_links_parent_child(self) -> None:
        """Delegation record should capture parent_id, child agent_id, and envelope."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="parent-001", envelope=_make_envelope())
        child_envelope = _make_envelope(limit=5.0)

        record = trail.record_delegation(
            parent_id="parent-001",
            child_id="child-001",
            envelope=child_envelope,
        )

        assert record.record_type == "delegation"
        assert record.agent_id == "child-001"
        assert record.parent_id == "parent-001"
        assert record.details["envelope"] == child_envelope
        assert record.action == "delegation"

    def test_delegation_record_chains_to_genesis(self) -> None:
        """Delegation record's prev_hash should equal the genesis record's hash."""
        trail = AuditTrail()
        genesis = trail.record_genesis(agent_id="parent-001", envelope=_make_envelope())

        delegation = trail.record_delegation(
            parent_id="parent-001",
            child_id="child-001",
            envelope=_make_envelope(),
        )

        assert delegation.prev_hash == genesis.record_hash


# ---------------------------------------------------------------------------
# Test: Termination record
# ---------------------------------------------------------------------------


class TestTerminationRecord:
    """record_termination should record agent termination with budget consumed."""

    def test_termination_record_with_budget_consumed(self) -> None:
        """Termination record should capture reason and budget consumed."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="agent-001", envelope=_make_envelope())
        budget = {"financial_spent": 4.50, "actions_executed": 12}

        record = trail.record_termination(
            agent_id="agent-001",
            reason="budget_exhausted",
            budget_consumed=budget,
        )

        assert record.record_type == "termination"
        assert record.agent_id == "agent-001"
        assert record.action == "termination"
        assert record.details["reason"] == "budget_exhausted"
        assert record.details["budget_consumed"] == budget


# ---------------------------------------------------------------------------
# Test: Action record
# ---------------------------------------------------------------------------


class TestActionRecord:
    """record_action should record governance-relevant actions."""

    def test_action_record_for_tool_call(self) -> None:
        """Action record should capture action name and details."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="agent-001", envelope=_make_envelope())
        details = {"tool": "web_search", "query": "Kailash SDK docs"}

        record = trail.record_action(
            agent_id="agent-001",
            action="tool_call",
            details=details,
        )

        assert record.record_type == "action"
        assert record.agent_id == "agent-001"
        assert record.action == "tool_call"
        assert record.details == details


# ---------------------------------------------------------------------------
# Test: Held event record
# ---------------------------------------------------------------------------


class TestHeldRecord:
    """record_held should record held events."""

    def test_held_record_captures_node_and_reason(self) -> None:
        """Held record should capture the node_id and reason for the hold."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="agent-001", envelope=_make_envelope())

        record = trail.record_held(
            agent_id="agent-001",
            node_id="node-abc",
            reason="budget_threshold_exceeded",
        )

        assert record.record_type == "held"
        assert record.agent_id == "agent-001"
        assert record.action == "held"
        assert record.details["node_id"] == "node-abc"
        assert record.details["reason"] == "budget_threshold_exceeded"


# ---------------------------------------------------------------------------
# Test: Modification record
# ---------------------------------------------------------------------------


class TestModificationRecord:
    """record_modification should record plan modifications."""

    def test_modification_record_captures_modification_dict(self) -> None:
        """Modification record should store the modification details."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="agent-001", envelope=_make_envelope())
        modification = {
            "type": "add_node",
            "node_id": "node-new",
            "reason": "recovery after failure",
        }

        record = trail.record_modification(
            agent_id="agent-001",
            modification=modification,
        )

        assert record.record_type == "modification"
        assert record.agent_id == "agent-001"
        assert record.action == "modification"
        assert record.details["modification"] == modification


# ---------------------------------------------------------------------------
# Test: Hash chain integrity
# ---------------------------------------------------------------------------


class TestHashChainIntegrity:
    """verify_chain should validate hash chain from genesis to latest."""

    def test_verify_chain_returns_true_for_valid_chain(self) -> None:
        """A trail with multiple records should have a valid hash chain."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="root", envelope=_make_envelope())
        trail.record_delegation(parent_id="root", child_id="child-1", envelope=_make_envelope())
        trail.record_action(agent_id="child-1", action="search", details={"q": "test"})
        trail.record_termination(
            agent_id="child-1", reason="completed", budget_consumed={"cost": 1.0}
        )

        assert trail.verify_chain() is True

    def test_verify_chain_detects_tampering(self) -> None:
        """Modifying a record's data should cause verify_chain to return False."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="root", envelope=_make_envelope())
        trail.record_action(agent_id="root", action="search", details={"q": "test"})
        trail.record_action(agent_id="root", action="write", details={"file": "x.py"})

        # Tamper with the middle record by replacing it with a modified copy.
        # AuditRecord is frozen, so we create a new one with altered action.
        tampered = AuditRecord(
            record_id=trail._records[1].record_id,
            record_type=trail._records[1].record_type,
            timestamp=trail._records[1].timestamp,
            agent_id=trail._records[1].agent_id,
            parent_id=trail._records[1].parent_id,
            action="TAMPERED_ACTION",
            details=trail._records[1].details,
            prev_hash=trail._records[1].prev_hash,
            record_hash=trail._records[1].record_hash,  # hash no longer matches
        )
        trail._records[1] = tampered

        assert trail.verify_chain() is False

    def test_verify_chain_empty_trail_returns_true(self) -> None:
        """An empty trail should be considered valid."""
        trail = AuditTrail()
        assert trail.verify_chain() is True

    def test_verify_chain_single_record(self) -> None:
        """A trail with a single record should be valid."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="root", envelope=_make_envelope())
        assert trail.verify_chain() is True


# ---------------------------------------------------------------------------
# Test: Bounded collection
# ---------------------------------------------------------------------------


class TestBoundedCollection:
    """The trail should enforce maxlen and evict oldest records."""

    def test_bounded_collection_evicts_oldest(self) -> None:
        """Adding 10001 records to a maxlen=10000 trail should evict the first."""
        trail = AuditTrail(maxlen=100)  # Use smaller value for speed
        trail.record_genesis(agent_id="root", envelope=_make_envelope())

        # Add 100 more records (101 total, but maxlen=100)
        for i in range(100):
            trail.record_action(agent_id="root", action=f"action-{i}", details={"i": i})

        assert len(trail._records) == 100
        # The genesis record should have been evicted
        assert trail._records[0].record_type != "genesis" or trail._records[0].action != "genesis"

    def test_default_maxlen_is_10000(self) -> None:
        """Default maxlen should be 10000 per trust-plane-security rules."""
        trail = AuditTrail()
        assert trail._records.maxlen == 10000


# ---------------------------------------------------------------------------
# Test: Query by agent
# ---------------------------------------------------------------------------


class TestQueryByAgent:
    """query_by_agent should return records filtered by agent_id."""

    def test_query_returns_correct_records(self) -> None:
        """Querying for an agent should return only that agent's records."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="agent-A", envelope=_make_envelope())
        trail.record_delegation(parent_id="agent-A", child_id="agent-B", envelope=_make_envelope())
        trail.record_action(agent_id="agent-A", action="search", details={})
        trail.record_action(agent_id="agent-B", action="write", details={})
        trail.record_termination(agent_id="agent-B", reason="completed", budget_consumed={})

        a_records = trail.query_by_agent("agent-A")
        b_records = trail.query_by_agent("agent-B")

        assert len(a_records) == 2  # genesis + action
        assert all(r.agent_id == "agent-A" for r in a_records)

        assert len(b_records) == 3  # delegation + action + termination
        assert all(r.agent_id == "agent-B" for r in b_records)

    def test_query_nonexistent_agent_returns_empty(self) -> None:
        """Querying for an agent with no records should return empty list."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="agent-A", envelope=_make_envelope())

        result = trail.query_by_agent("nonexistent")

        assert result == []


# ---------------------------------------------------------------------------
# Test: Multiple agents filter correctly
# ---------------------------------------------------------------------------


class TestMultipleAgents:
    """With multiple agents, query should filter correctly."""

    def test_multiple_agents_query_filters_correctly(self) -> None:
        """Each agent's query should return only their records, not others'."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="supervisor", envelope=_make_envelope())

        # Create three child agents
        for i in range(3):
            trail.record_delegation(
                parent_id="supervisor",
                child_id=f"worker-{i}",
                envelope=_make_envelope(),
            )
            trail.record_action(
                agent_id=f"worker-{i}",
                action="execute",
                details={"task": f"task-{i}"},
            )

        supervisor_records = trail.query_by_agent("supervisor")
        assert len(supervisor_records) == 1  # genesis only

        for i in range(3):
            worker_records = trail.query_by_agent(f"worker-{i}")
            assert len(worker_records) == 2  # delegation + action
            assert all(r.agent_id == f"worker-{i}" for r in worker_records)


# ---------------------------------------------------------------------------
# Test: Export to dict list
# ---------------------------------------------------------------------------


class TestExportToList:
    """to_list should export all records as dicts."""

    def test_export_to_dict_list(self) -> None:
        """Exported list should contain dict representations of all records."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="root", envelope=_make_envelope())
        trail.record_action(agent_id="root", action="test", details={"key": "value"})

        exported = trail.to_list()

        assert isinstance(exported, list)
        assert len(exported) == 2

        for item in exported:
            assert isinstance(item, dict)
            assert "record_id" in item
            assert "record_type" in item
            assert "timestamp" in item
            assert "agent_id" in item
            assert "parent_id" in item
            assert "action" in item
            assert "details" in item
            assert "prev_hash" in item
            assert "record_hash" in item

    def test_export_preserves_data(self) -> None:
        """Exported dicts should contain the actual data from the records."""
        trail = AuditTrail()
        envelope = _make_envelope(limit=99.0)
        trail.record_genesis(agent_id="root", envelope=envelope)

        exported = trail.to_list()

        assert exported[0]["record_type"] == "genesis"
        assert exported[0]["agent_id"] == "root"
        assert exported[0]["details"]["envelope"]["financial"]["limit"] == 99.0

    def test_export_timestamp_is_iso_format(self) -> None:
        """Exported timestamps should be ISO format strings."""
        trail = AuditTrail()
        trail.record_genesis(agent_id="root", envelope=_make_envelope())

        exported = trail.to_list()

        # Should be a parseable ISO timestamp string
        ts = exported[0]["timestamp"]
        assert isinstance(ts, str)
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None  # should be timezone-aware

    def test_export_empty_trail_returns_empty_list(self) -> None:
        """Exporting an empty trail should return an empty list."""
        trail = AuditTrail()
        assert trail.to_list() == []

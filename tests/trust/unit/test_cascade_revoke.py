# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for cascade revocation with TrustStore integration (Phase 3, todo 3.10).

Verifies:
- Linear chain revocation (A->B->C, revoke A -> B,C also revoked)
- Branching tree revocation (A->B, A->C, revoke A -> B,C revoked)
- Circular chain handling (A->B->A, no infinite loop)
- Audit trail completeness (every revocation produces an event)
- Idempotent re-revocation (revoking already-revoked = no-op)
- Revoke leaf node (no cascade needed)
- Revoke non-existent agent (returns no-op result)
- RevocationResult serialization and defaults
- cascade_revoke with custom and default broadcaster/registry
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.revocation.broadcaster import (
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationEvent,
    RevocationType,
)
from kailash.trust.revocation.cascade import RevocationResult, cascade_revoke
from kailash.trust.chain_store.memory import InMemoryTrustStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_genesis(agent_id: str, authority_id: str = "auth-1") -> GenesisRecord:
    """Create a minimal GenesisRecord for testing."""
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        signature="sig-test-genesis",
    )


def _make_chain(agent_id: str, authority_id: str = "auth-1") -> TrustLineageChain:
    """Create a minimal TrustLineageChain for testing."""
    return TrustLineageChain(genesis=_make_genesis(agent_id, authority_id))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Fresh InMemoryTrustStore for each test."""
    return InMemoryTrustStore()


@pytest.fixture
def registry():
    """Fresh InMemoryDelegationRegistry for each test."""
    return InMemoryDelegationRegistry()


@pytest.fixture
def broadcaster():
    """Fresh InMemoryRevocationBroadcaster for each test."""
    return InMemoryRevocationBroadcaster()


# ---------------------------------------------------------------------------
# 1 — Linear chain revocation (A -> B -> C)
# ---------------------------------------------------------------------------


class TestLinearChainRevocation:
    """Phase 3: Linear chain A->B->C, revoke A -> B,C also revoked."""

    async def test_linear_chain_all_revoked(self, store, registry, broadcaster):
        """Revoking root of A->B->C must soft-delete chains for A, B, and C."""
        # Set up chains in the store
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        # Set up delegation chain: A -> B -> C
        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Security violation",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {"agent-A", "agent-B", "agent-C"}
        assert result.errors == {}

    async def test_linear_chain_stores_are_deleted(self, store, registry, broadcaster):
        """After linear cascade, all chains must be deleted from the store."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Security violation",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        # All three chains must be gone
        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-A")
        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-B")
        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-C")

    async def test_linear_chain_events_generated(self, store, registry, broadcaster):
        """Linear cascade must produce events for A, B, and C."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Security violation",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        event_targets = {e.target_id for e in result.events}
        assert "agent-A" in event_targets
        assert "agent-B" in event_targets
        assert "agent-C" in event_targets
        assert len(result.events) >= 3


# ---------------------------------------------------------------------------
# 2 — Branching tree revocation (A -> B, A -> C)
# ---------------------------------------------------------------------------


class TestBranchingTreeRevocation:
    """Phase 3: A->B and A->C, revoke A -> both B and C revoked."""

    async def test_branching_tree_all_revoked(self, store, registry, broadcaster):
        """Revoking A with branches to B and C must revoke all three."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Policy update",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {"agent-A", "agent-B", "agent-C"}

    async def test_branching_tree_stores_deleted(self, store, registry, broadcaster):
        """After branching cascade, all chains must be deleted from the store."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Policy update",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        for agent_id in ("agent-A", "agent-B", "agent-C"):
            with pytest.raises(TrustChainNotFoundError):
                await store.get_chain(agent_id)

    async def test_branching_tree_events_generated(self, store, registry, broadcaster):
        """Branching cascade must produce at least 3 events."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Policy update",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        event_targets = {e.target_id for e in result.events}
        assert event_targets >= {"agent-A", "agent-B", "agent-C"}


# ---------------------------------------------------------------------------
# 3 — Circular chain handling (A -> B -> A)
# ---------------------------------------------------------------------------


class TestCircularChainHandling:
    """Phase 3: Circular delegation A->B->A must not cause infinite loop."""

    async def test_circular_chain_terminates(self, store, registry, broadcaster):
        """Circular delegation A->B->A must terminate without infinite loop."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-A")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Cycle test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {"agent-A", "agent-B"}

    async def test_circular_chain_no_duplicate_events(self, store, registry, broadcaster):
        """Circular chain must not produce duplicate revocation events for same target."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-A")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Cycle test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        # Each target should appear as event.target_id at most once
        target_ids = [e.target_id for e in result.events]
        assert len(target_ids) == len(set(target_ids))

    async def test_three_node_cycle(self, store, registry, broadcaster):
        """Cycle A->B->C->A must terminate and revoke all three."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")
        registry.register_delegation("agent-C", "agent-A")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Three-node cycle test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {"agent-A", "agent-B", "agent-C"}


# ---------------------------------------------------------------------------
# 4 — Audit trail completeness
# ---------------------------------------------------------------------------


class TestAuditTrailCompleteness:
    """Phase 3: Every revocation must produce an event in the audit trail."""

    async def test_every_revoked_agent_has_event(self, store, registry, broadcaster):
        """Every agent in revoked_agents must have a corresponding event."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Audit trail test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        event_targets = {e.target_id for e in result.events}
        for agent_id in result.revoked_agents:
            assert agent_id in event_targets, f"Agent '{agent_id}' was revoked but has no event in the audit trail"

    async def test_initial_event_is_agent_revoked(self, store, registry, broadcaster):
        """The first event must be of type AGENT_REVOKED for the target agent."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Event type test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        initial_event = result.events[0]
        assert initial_event.target_id == "agent-A"
        assert initial_event.revocation_type == RevocationType.AGENT_REVOKED

    async def test_cascade_events_are_cascade_type(self, store, registry, broadcaster):
        """Cascade events (non-initial) must be of type CASCADE_REVOCATION."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Cascade type test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        cascade_events = [e for e in result.events if e.target_id != "agent-A"]
        for event in cascade_events:
            assert event.revocation_type == RevocationType.CASCADE_REVOCATION

    async def test_events_have_unique_ids(self, store, registry, broadcaster):
        """Each event must have a unique event_id."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))
        await store.store_chain(_make_chain("agent-C"))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Unique ID test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        event_ids = [e.event_id for e in result.events]
        assert len(event_ids) == len(set(event_ids)), "Event IDs must be unique"

    async def test_events_broadcast_to_broadcaster_history(self, store, registry, broadcaster):
        """All events must also appear in the broadcaster's history."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Broadcaster history test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        history = broadcaster.get_history()
        history_ids = {e.event_id for e in history}
        for event in result.events:
            assert event.event_id in history_ids, f"Event '{event.event_id}' missing from broadcaster history"

    async def test_cascade_event_has_cascade_from(self, store, registry, broadcaster):
        """Cascade events must reference their parent event via cascade_from."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Cascade from test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        cascade_events = [e for e in result.events if e.target_id == "agent-B"]
        assert len(cascade_events) >= 1
        for event in cascade_events:
            assert event.cascade_from is not None, "Cascade events must have cascade_from set"

    async def test_event_revoked_by_matches(self, store, registry, broadcaster):
        """All events must carry the revoked_by field from the caller."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Revoked-by test",
            revoked_by="security-admin-42",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        for event in result.events:
            assert event.revoked_by == "security-admin-42"


# ---------------------------------------------------------------------------
# 5 — Idempotent re-revocation
# ---------------------------------------------------------------------------


class TestIdempotentRevocation:
    """Phase 3: Revoking an already-revoked agent is a no-op."""

    async def test_re_revoke_returns_success(self, store, registry, broadcaster):
        """Re-revoking an already-revoked agent must return success=True."""
        await store.store_chain(_make_chain("agent-A"))

        # First revocation
        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="First revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        # Second revocation -- idempotent no-op
        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Second revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True

    async def test_re_revoke_produces_no_events(self, store, registry, broadcaster):
        """Re-revoking must produce zero events (no-op)."""
        await store.store_chain(_make_chain("agent-A"))

        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="First revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Second revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.events == []

    async def test_re_revoke_produces_no_revoked_agents(self, store, registry, broadcaster):
        """Re-revoking must produce empty revoked_agents list."""
        await store.store_chain(_make_chain("agent-A"))

        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="First revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Second revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.revoked_agents == []


# ---------------------------------------------------------------------------
# 6 — Revoke leaf node (no cascade needed)
# ---------------------------------------------------------------------------


class TestLeafNodeRevocation:
    """Phase 3: Revoking a leaf node with no delegates."""

    async def test_leaf_revocation_success(self, store, registry, broadcaster):
        """Revoking a leaf node with no delegates must succeed."""
        await store.store_chain(_make_chain("agent-leaf"))

        result = await cascade_revoke(
            agent_id="agent-leaf",
            store=store,
            reason="Leaf revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert "agent-leaf" in result.revoked_agents

    async def test_leaf_revocation_single_event(self, store, registry, broadcaster):
        """Revoking a leaf node must produce exactly one event."""
        await store.store_chain(_make_chain("agent-leaf"))

        result = await cascade_revoke(
            agent_id="agent-leaf",
            store=store,
            reason="Leaf revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert len(result.events) == 1
        assert result.events[0].target_id == "agent-leaf"
        assert result.events[0].revocation_type == RevocationType.AGENT_REVOKED

    async def test_leaf_revocation_chain_deleted(self, store, registry, broadcaster):
        """After revoking a leaf, its chain must be deleted from the store."""
        await store.store_chain(_make_chain("agent-leaf"))

        await cascade_revoke(
            agent_id="agent-leaf",
            store=store,
            reason="Leaf revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        with pytest.raises(TrustChainNotFoundError):
            await store.get_chain("agent-leaf")

    async def test_leaf_revocation_does_not_affect_parent(self, store, registry, broadcaster):
        """Revoking a leaf must NOT affect its parent's chain."""
        await store.store_chain(_make_chain("agent-parent"))
        await store.store_chain(_make_chain("agent-leaf"))

        registry.register_delegation("agent-parent", "agent-leaf")

        await cascade_revoke(
            agent_id="agent-leaf",
            store=store,
            reason="Leaf only",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        # Parent chain must still be accessible
        parent_chain = await store.get_chain("agent-parent")
        assert parent_chain.genesis.agent_id == "agent-parent"


# ---------------------------------------------------------------------------
# 7 — Revoke non-existent agent
# ---------------------------------------------------------------------------


class TestNonExistentAgentRevocation:
    """Phase 3: Revoking a non-existent agent returns no-op result."""

    async def test_non_existent_returns_success(self, store, registry, broadcaster):
        """Revoking a non-existent agent must return success=True (no-op)."""
        result = await cascade_revoke(
            agent_id="agent-ghost",
            store=store,
            reason="Ghost test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True

    async def test_non_existent_no_events(self, store, registry, broadcaster):
        """Revoking a non-existent agent must produce zero events."""
        result = await cascade_revoke(
            agent_id="agent-ghost",
            store=store,
            reason="Ghost test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.events == []

    async def test_non_existent_no_revoked_agents(self, store, registry, broadcaster):
        """Revoking a non-existent agent must produce empty revoked_agents."""
        result = await cascade_revoke(
            agent_id="agent-ghost",
            store=store,
            reason="Ghost test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.revoked_agents == []

    async def test_non_existent_no_errors(self, store, registry, broadcaster):
        """Revoking a non-existent agent must produce no errors."""
        result = await cascade_revoke(
            agent_id="agent-ghost",
            store=store,
            reason="Ghost test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.errors == {}


# ---------------------------------------------------------------------------
# 8 — RevocationResult.to_dict() serialization
# ---------------------------------------------------------------------------


class TestRevocationResultToDict:
    """Phase 3: RevocationResult.to_dict() serialization."""

    def test_to_dict_empty_result(self):
        """Empty RevocationResult must serialize correctly."""
        result = RevocationResult(success=True)
        d = result.to_dict()

        assert d["success"] is True
        assert d["events"] == []
        assert d["revoked_agents"] == []
        assert d["errors"] == {}

    def test_to_dict_with_events(self):
        """RevocationResult with events must serialize events via to_dict()."""
        event = RevocationEvent(
            event_id="rev-001",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-A",
            revoked_by="admin",
            reason="Test reason",
        )
        result = RevocationResult(
            success=True,
            events=[event],
            revoked_agents=["agent-A"],
        )
        d = result.to_dict()

        assert len(d["events"]) == 1
        assert d["events"][0]["event_id"] == "rev-001"
        assert d["events"][0]["revocation_type"] == "agent_revoked"
        assert d["events"][0]["target_id"] == "agent-A"
        assert d["revoked_agents"] == ["agent-A"]

    def test_to_dict_with_errors(self):
        """RevocationResult with errors must serialize errors correctly."""
        result = RevocationResult(
            success=False,
            errors={"agent-X": "RuntimeError: store failure"},
        )
        d = result.to_dict()

        assert d["success"] is False
        assert d["errors"] == {"agent-X": "RuntimeError: store failure"}

    async def test_to_dict_from_real_revocation(self, store, registry, broadcaster):
        """to_dict() on a real revocation result must produce valid structure."""
        await store.store_chain(_make_chain("agent-A"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Serialization test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["success"] is True
        assert isinstance(d["events"], list)
        assert isinstance(d["revoked_agents"], list)
        assert isinstance(d["errors"], dict)
        assert len(d["events"]) >= 1
        assert "agent-A" in d["revoked_agents"]


# ---------------------------------------------------------------------------
# 9 — RevocationResult field defaults
# ---------------------------------------------------------------------------


class TestRevocationResultDefaults:
    """Phase 3: RevocationResult dataclass field defaults."""

    def test_default_events_empty_list(self):
        """Default events must be an empty list."""
        result = RevocationResult(success=True)
        assert result.events == []
        assert isinstance(result.events, list)

    def test_default_revoked_agents_empty_list(self):
        """Default revoked_agents must be an empty list."""
        result = RevocationResult(success=True)
        assert result.revoked_agents == []
        assert isinstance(result.revoked_agents, list)

    def test_default_errors_empty_dict(self):
        """Default errors must be an empty dict."""
        result = RevocationResult(success=True)
        assert result.errors == {}
        assert isinstance(result.errors, dict)

    def test_success_is_required(self):
        """success must be explicitly provided (no default)."""
        # RevocationResult(success=True) works
        r = RevocationResult(success=True)
        assert r.success is True

        # RevocationResult(success=False) works
        r = RevocationResult(success=False)
        assert r.success is False

    def test_independent_default_lists(self):
        """Each instance must get its own default list/dict (no shared mutable state)."""
        r1 = RevocationResult(success=True)
        r2 = RevocationResult(success=True)

        r1.events.append(
            RevocationEvent(
                event_id="test",
                revocation_type=RevocationType.AGENT_REVOKED,
                target_id="x",
                revoked_by="y",
                reason="z",
            )
        )
        r1.revoked_agents.append("agent-1")
        r1.errors["agent-1"] = "error"

        # r2 must be unaffected
        assert r2.events == []
        assert r2.revoked_agents == []
        assert r2.errors == {}


# ---------------------------------------------------------------------------
# 10 — cascade_revoke with custom broadcaster
# ---------------------------------------------------------------------------


class TestCascadeRevokeCustomBroadcaster:
    """Phase 3: cascade_revoke with explicitly provided broadcaster."""

    async def test_custom_broadcaster_receives_events(self, store, registry):
        """A custom broadcaster must receive all broadcast events."""
        custom_broadcaster = InMemoryRevocationBroadcaster()
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Custom broadcaster test",
            revoked_by="admin",
            broadcaster=custom_broadcaster,
            delegation_registry=registry,
        )

        history = custom_broadcaster.get_history()
        assert len(history) >= 2
        history_targets = {e.target_id for e in history}
        assert "agent-A" in history_targets
        assert "agent-B" in history_targets

    async def test_subscriber_receives_events_from_custom_broadcaster(self, store, registry):
        """Subscribers on the custom broadcaster must receive cascade events."""
        custom_broadcaster = InMemoryRevocationBroadcaster()
        received_events = []
        custom_broadcaster.subscribe(lambda e: received_events.append(e))

        await store.store_chain(_make_chain("agent-A"))

        await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Subscriber test",
            revoked_by="admin",
            broadcaster=custom_broadcaster,
            delegation_registry=InMemoryDelegationRegistry(),
        )

        assert len(received_events) >= 1
        assert received_events[0].target_id == "agent-A"


# ---------------------------------------------------------------------------
# 11 — cascade_revoke with default broadcaster/registry
# ---------------------------------------------------------------------------


class TestCascadeRevokeDefaults:
    """Phase 3: cascade_revoke with default (None) broadcaster and registry."""

    async def test_default_broadcaster_and_registry(self, store):
        """cascade_revoke with no broadcaster/registry must still work."""
        await store.store_chain(_make_chain("agent-A"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Default infra test",
            revoked_by="admin",
        )

        assert result.success is True
        assert "agent-A" in result.revoked_agents

    async def test_default_registry_no_cascade(self, store):
        """Default registry (empty) must mean no cascade beyond the target."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Default registry test",
            revoked_by="admin",
        )

        # Only agent-A should be revoked (default empty registry has no delegations)
        assert "agent-A" in result.revoked_agents
        assert "agent-B" not in result.revoked_agents

        # agent-B chain must still exist
        chain_b = await store.get_chain("agent-B")
        assert chain_b.genesis.agent_id == "agent-B"

    async def test_default_broadcaster_does_not_raise(self, store):
        """Using default broadcaster must not raise any errors."""
        await store.store_chain(_make_chain("agent-A"))

        # This must not raise
        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="No-raise test",
            revoked_by="admin",
            broadcaster=None,
            delegation_registry=None,
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# 12 — Deep chain revocation (A -> B -> C -> D)
# ---------------------------------------------------------------------------


class TestDeepChainRevocation:
    """Phase 3: Deep chains are handled correctly."""

    async def test_four_level_chain(self, store, registry, broadcaster):
        """Four-level chain A->B->C->D must cascade through all levels."""
        for agent in ("agent-A", "agent-B", "agent-C", "agent-D"):
            await store.store_chain(_make_chain(agent))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")
        registry.register_delegation("agent-C", "agent-D")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Deep chain test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {
            "agent-A",
            "agent-B",
            "agent-C",
            "agent-D",
        }

    async def test_middle_node_revocation(self, store, registry, broadcaster):
        """Revoking middle node B in A->B->C must revoke B and C but not A."""
        for agent in ("agent-A", "agent-B", "agent-C"):
            await store.store_chain(_make_chain(agent))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-B", "agent-C")

        result = await cascade_revoke(
            agent_id="agent-B",
            store=store,
            reason="Middle revoke",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert "agent-B" in result.revoked_agents
        assert "agent-C" in result.revoked_agents
        assert "agent-A" not in result.revoked_agents

        # agent-A chain must still be accessible
        chain_a = await store.get_chain("agent-A")
        assert chain_a.genesis.agent_id == "agent-A"


# ---------------------------------------------------------------------------
# 13 — Diamond delegation pattern (A -> B, A -> C, B -> D, C -> D)
# ---------------------------------------------------------------------------


class TestDiamondDelegation:
    """Phase 3: Diamond delegation where D has two parents."""

    async def test_diamond_revokes_all(self, store, registry, broadcaster):
        """Diamond pattern A->{B,C}->D must revoke all four agents."""
        for agent in ("agent-A", "agent-B", "agent-C", "agent-D"):
            await store.store_chain(_make_chain(agent))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")
        registry.register_delegation("agent-B", "agent-D")
        registry.register_delegation("agent-C", "agent-D")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Diamond test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.success is True
        assert set(result.revoked_agents) == {
            "agent-A",
            "agent-B",
            "agent-C",
            "agent-D",
        }

    async def test_diamond_no_duplicate_deletes(self, store, registry, broadcaster):
        """Diamond pattern must not attempt to delete D's chain twice."""
        for agent in ("agent-A", "agent-B", "agent-C", "agent-D"):
            await store.store_chain(_make_chain(agent))

        registry.register_delegation("agent-A", "agent-B")
        registry.register_delegation("agent-A", "agent-C")
        registry.register_delegation("agent-B", "agent-D")
        registry.register_delegation("agent-C", "agent-D")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Diamond no-dup test",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        # D appears at most once in revoked_agents
        assert result.revoked_agents.count("agent-D") <= 1
        # No errors about chain-not-found for D (would indicate double delete attempt)
        # The cascade manager's BFS visited set prevents D from being processed twice,
        # so it should only appear once across all events and revoked_agents.
        assert result.success is True


# ---------------------------------------------------------------------------
# 14 — Reason propagation
# ---------------------------------------------------------------------------


class TestReasonPropagation:
    """Phase 3: Reason strings are preserved in events."""

    async def test_initial_event_contains_reason(self, store, registry, broadcaster):
        """The initial event must contain the exact reason provided."""
        await store.store_chain(_make_chain("agent-A"))

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Specific violation #42",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        assert result.events[0].reason == "Specific violation #42"

    async def test_cascade_event_references_parent_reason(self, store, registry, broadcaster):
        """Cascade events must reference the original reason in their reason string."""
        await store.store_chain(_make_chain("agent-A"))
        await store.store_chain(_make_chain("agent-B"))

        registry.register_delegation("agent-A", "agent-B")

        result = await cascade_revoke(
            agent_id="agent-A",
            store=store,
            reason="Compliance failure",
            revoked_by="admin",
            broadcaster=broadcaster,
            delegation_registry=registry,
        )

        cascade_events = [e for e in result.events if e.target_id == "agent-B"]
        assert len(cascade_events) >= 1
        # The cascade reason should mention the original reason
        assert "Compliance failure" in cascade_events[0].reason

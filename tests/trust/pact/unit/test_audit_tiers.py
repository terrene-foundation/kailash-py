# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PACT N4 Audit Durability Tiers (PACT-08).

Covers:
- TieredAuditDispatcher tier routing based on VerificationLevel
- AUTO_APPROVED -> ephemeral only (Tier 1)
- HELD/BLOCKED -> synchronous durable write (Tier 3)
- FLAGGED -> buffered, persisted on flush_session() (Tier 2)
- flush_session() clears buffer and returns count
- No dispatcher -> backward compat in GovernanceEngine
- Anchor-to-event conversion
"""

from __future__ import annotations

import asyncio

import pytest
from kailash.trust.audit_store import InMemoryAuditStore
from kailash.trust.pact.audit import AuditAnchor, AuditChain, TieredAuditDispatcher
from kailash.trust.pact.config import VerificationLevel

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def ephemeral() -> AuditChain:
    """Fresh ephemeral audit chain."""
    return AuditChain(chain_id="test-chain")


@pytest.fixture()
def durable() -> InMemoryAuditStore:
    """Fresh in-memory durable store."""
    return InMemoryAuditStore()


@pytest.fixture()
def dispatcher(
    ephemeral: AuditChain, durable: InMemoryAuditStore
) -> TieredAuditDispatcher:
    """Dispatcher with both ephemeral and durable stores."""
    return TieredAuditDispatcher(ephemeral=ephemeral, durable=durable)


@pytest.fixture()
def ephemeral_only_dispatcher(ephemeral: AuditChain) -> TieredAuditDispatcher:
    """Dispatcher with ephemeral chain only (no durable store)."""
    return TieredAuditDispatcher(ephemeral=ephemeral, durable=None)


def _make_anchor(
    *,
    action: str = "test_action",
    agent_id: str = "agent-1",
    level: VerificationLevel = VerificationLevel.AUTO_APPROVED,
) -> AuditAnchor:
    """Helper to create a sealed AuditAnchor."""
    anchor = AuditAnchor(
        agent_id=agent_id,
        action=action,
        verification_level=level,
        result="success",
        metadata={"detail": "test"},
    )
    anchor.seal()
    return anchor


# ===========================================================================
# Tier 1: AUTO_APPROVED -> ephemeral only
# ===========================================================================


class TestTier1AutoApproved:
    """AUTO_APPROVED actions go to ephemeral chain only."""

    def test_auto_approved_writes_to_ephemeral(
        self,
        dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
        durable: InMemoryAuditStore,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.AUTO_APPROVED)
        dispatcher.dispatch(anchor, VerificationLevel.AUTO_APPROVED)

        assert ephemeral.length == 1
        assert durable.count == 0

    def test_auto_approved_not_buffered(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.AUTO_APPROVED)
        dispatcher.dispatch(anchor, VerificationLevel.AUTO_APPROVED)

        assert dispatcher.session_buffer_size == 0

    def test_auto_approved_ephemeral_only_mode(
        self,
        ephemeral_only_dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.AUTO_APPROVED)
        ephemeral_only_dispatcher.dispatch(anchor, VerificationLevel.AUTO_APPROVED)

        assert ephemeral.length == 1


# ===========================================================================
# Tier 3: HELD/BLOCKED -> synchronous durable write
# ===========================================================================


class TestTier3HeldBlocked:
    """HELD and BLOCKED actions write to both ephemeral and durable stores."""

    def test_held_writes_to_ephemeral(
        self,
        dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
    ) -> None:
        anchor = _make_anchor(action="held_action", level=VerificationLevel.HELD)
        dispatcher.dispatch(anchor, VerificationLevel.HELD)

        assert ephemeral.length == 1
        assert ephemeral.anchors[0].action == "held_action"

    def test_held_writes_to_durable(
        self,
        dispatcher: TieredAuditDispatcher,
        durable: InMemoryAuditStore,
    ) -> None:
        anchor = _make_anchor(action="held_action", level=VerificationLevel.HELD)
        dispatcher.dispatch(anchor, VerificationLevel.HELD)

        assert durable.count == 1

    def test_blocked_writes_to_ephemeral(
        self,
        dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
    ) -> None:
        anchor = _make_anchor(action="blocked_action", level=VerificationLevel.BLOCKED)
        dispatcher.dispatch(anchor, VerificationLevel.BLOCKED)

        assert ephemeral.length == 1
        assert ephemeral.anchors[0].action == "blocked_action"

    def test_blocked_writes_to_durable(
        self,
        dispatcher: TieredAuditDispatcher,
        durable: InMemoryAuditStore,
    ) -> None:
        anchor = _make_anchor(action="blocked_action", level=VerificationLevel.BLOCKED)
        dispatcher.dispatch(anchor, VerificationLevel.BLOCKED)

        assert durable.count == 1

    def test_held_not_buffered(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.HELD)
        dispatcher.dispatch(anchor, VerificationLevel.HELD)

        assert dispatcher.session_buffer_size == 0

    def test_blocked_not_buffered(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.BLOCKED)
        dispatcher.dispatch(anchor, VerificationLevel.BLOCKED)

        assert dispatcher.session_buffer_size == 0

    def test_held_ephemeral_only_mode(
        self,
        ephemeral_only_dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
    ) -> None:
        """When no durable store, HELD still writes to ephemeral."""
        anchor = _make_anchor(level=VerificationLevel.HELD)
        ephemeral_only_dispatcher.dispatch(anchor, VerificationLevel.HELD)

        assert ephemeral.length == 1


# ===========================================================================
# Tier 2: FLAGGED -> buffered, persisted on flush_session()
# ===========================================================================


class TestTier2Flagged:
    """FLAGGED actions are buffered and flushed to durable store on demand."""

    def test_flagged_writes_to_ephemeral(
        self,
        dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
    ) -> None:
        anchor = _make_anchor(action="flagged_action", level=VerificationLevel.FLAGGED)
        dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        assert ephemeral.length == 1
        assert ephemeral.anchors[0].action == "flagged_action"

    def test_flagged_not_immediately_durable(
        self,
        dispatcher: TieredAuditDispatcher,
        durable: InMemoryAuditStore,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.FLAGGED)
        dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        assert durable.count == 0

    def test_flagged_buffered(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.FLAGGED)
        dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        assert dispatcher.session_buffer_size == 1

    def test_flagged_multiple_buffered(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        for i in range(5):
            anchor = _make_anchor(
                action=f"flagged_{i}", level=VerificationLevel.FLAGGED
            )
            dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        assert dispatcher.session_buffer_size == 5

    def test_flush_persists_to_durable(
        self,
        dispatcher: TieredAuditDispatcher,
        durable: InMemoryAuditStore,
    ) -> None:
        for i in range(3):
            anchor = _make_anchor(
                action=f"flagged_{i}", level=VerificationLevel.FLAGGED
            )
            dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        flushed = dispatcher.flush_session()

        assert flushed == 3
        assert durable.count == 3

    def test_flush_clears_buffer(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        anchor = _make_anchor(level=VerificationLevel.FLAGGED)
        dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        dispatcher.flush_session()

        assert dispatcher.session_buffer_size == 0

    def test_flush_empty_returns_zero(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        flushed = dispatcher.flush_session()

        assert flushed == 0

    def test_flush_without_durable_clears_buffer(
        self,
        ephemeral_only_dispatcher: TieredAuditDispatcher,
    ) -> None:
        """Buffer clears even without durable store (no memory leak)."""
        anchor = _make_anchor(level=VerificationLevel.FLAGGED)
        ephemeral_only_dispatcher.dispatch(anchor, VerificationLevel.FLAGGED)

        assert ephemeral_only_dispatcher.session_buffer_size == 1

        flushed = ephemeral_only_dispatcher.flush_session()

        assert flushed == 0
        assert ephemeral_only_dispatcher.session_buffer_size == 0


# ===========================================================================
# Anchor-to-event conversion
# ===========================================================================


class TestAnchorToEvent:
    """Verify AuditAnchor -> AuditEvent conversion."""

    def test_conversion_maps_fields(
        self,
        dispatcher: TieredAuditDispatcher,
        durable: InMemoryAuditStore,
    ) -> None:
        anchor = AuditAnchor(
            agent_id="test-agent",
            action="deploy",
            verification_level=VerificationLevel.HELD,
            envelope_id="env-123",
            result="denied",
            metadata={"reason": "over budget"},
        )
        anchor.seal()

        dispatcher.dispatch(anchor, VerificationLevel.HELD)

        assert durable.count == 1
        # Access the event through the internal deque
        event = durable._events[0]
        assert event.actor == "test-agent"
        assert event.action == "deploy"
        assert event.resource == "env-123"
        assert event.outcome == "denied"
        assert event.metadata["reason"] == "over budget"
        assert event.metadata["verification_level"] == "HELD"
        assert "pact_anchor_id" in event.metadata

    def test_conversion_without_durable_raises(
        self,
        ephemeral_only_dispatcher: TieredAuditDispatcher,
    ) -> None:
        with pytest.raises(RuntimeError, match="without a durable store"):
            anchor = _make_anchor()
            ephemeral_only_dispatcher._anchor_to_event(anchor)


# ===========================================================================
# GovernanceEngine backward compatibility
# ===========================================================================


class TestGovernanceEngineBackwardCompat:
    """GovernanceEngine without dispatcher uses legacy audit path."""

    def test_no_dispatcher_uses_direct_append(self) -> None:
        """Without audit_dispatcher, _emit_audit uses the legacy AuditChain path."""
        from kailash.trust.pact.engine import GovernanceEngine
        from pact.examples.university.org import create_university_org

        compiled, _org_def = create_university_org()
        chain = AuditChain(chain_id="compat-chain")
        engine = GovernanceEngine(compiled, audit_chain=chain)

        # Verify no dispatcher is set
        assert engine.audit_dispatcher is None

        # Emit directly -- should go through legacy path
        engine._emit_audit("test_action", {"key": "value"})

        assert chain.length == 1
        assert chain.anchors[0].action == "test_action"

    def test_with_dispatcher_routes_through_tiers(self) -> None:
        """With audit_dispatcher, _emit_audit routes to the dispatcher."""
        from kailash.trust.pact.engine import GovernanceEngine
        from pact.examples.university.org import create_university_org

        compiled, _org_def = create_university_org()
        ephemeral_chain = AuditChain(chain_id="tier-chain")
        durable_store = InMemoryAuditStore()
        tiered = TieredAuditDispatcher(ephemeral=ephemeral_chain, durable=durable_store)
        engine = GovernanceEngine(compiled, audit_dispatcher=tiered)

        assert engine.audit_dispatcher is tiered

        # Emit with HELD level -- should write to both
        engine._emit_audit(
            "held_action",
            {"key": "value"},
            verification_level=VerificationLevel.HELD,
        )

        assert ephemeral_chain.length == 1
        assert durable_store.count == 1

    def test_dispatcher_auto_approved_ephemeral_only(self) -> None:
        """AUTO_APPROVED through engine._emit_audit stays ephemeral-only."""
        from kailash.trust.pact.engine import GovernanceEngine
        from pact.examples.university.org import create_university_org

        compiled, _org_def = create_university_org()
        ephemeral_chain = AuditChain(chain_id="tier-chain")
        durable_store = InMemoryAuditStore()
        tiered = TieredAuditDispatcher(ephemeral=ephemeral_chain, durable=durable_store)
        engine = GovernanceEngine(compiled, audit_dispatcher=tiered)

        engine._emit_audit("auto_action", {"key": "value"})

        assert ephemeral_chain.length == 1
        assert durable_store.count == 0


# ===========================================================================
# Properties and edge cases
# ===========================================================================


class TestDispatcherProperties:
    """Dispatcher property accessors and edge cases."""

    def test_ephemeral_property(
        self,
        dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
    ) -> None:
        assert dispatcher.ephemeral is ephemeral

    def test_session_buffer_starts_empty(
        self,
        dispatcher: TieredAuditDispatcher,
    ) -> None:
        assert dispatcher.session_buffer_size == 0

    def test_mixed_tiers_in_sequence(
        self,
        dispatcher: TieredAuditDispatcher,
        ephemeral: AuditChain,
        durable: InMemoryAuditStore,
    ) -> None:
        """Dispatch a mix of all tiers and verify correct routing."""
        # Tier 1
        dispatcher.dispatch(
            _make_anchor(action="auto", level=VerificationLevel.AUTO_APPROVED),
            VerificationLevel.AUTO_APPROVED,
        )
        # Tier 2
        dispatcher.dispatch(
            _make_anchor(action="flagged", level=VerificationLevel.FLAGGED),
            VerificationLevel.FLAGGED,
        )
        # Tier 3
        dispatcher.dispatch(
            _make_anchor(action="held", level=VerificationLevel.HELD),
            VerificationLevel.HELD,
        )
        # Tier 3
        dispatcher.dispatch(
            _make_anchor(action="blocked", level=VerificationLevel.BLOCKED),
            VerificationLevel.BLOCKED,
        )

        # All 4 should be in ephemeral
        assert ephemeral.length == 4
        # HELD + BLOCKED = 2 in durable (synchronous)
        assert durable.count == 2
        # FLAGGED = 1 in buffer
        assert dispatcher.session_buffer_size == 1

        # Flush the FLAGGED anchor
        flushed = dispatcher.flush_session()
        assert flushed == 1
        assert durable.count == 3
        assert dispatcher.session_buffer_size == 0

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for EnvelopeEnforcer.

Covers:
- INV-3: Non-bypassable enforcement
- check_action() -> record_action() sequence
- Delegation to tracker for depletable dimensions
- Non-depletable dimension callback
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


def _make_envelope(
    financial_limit: float = 1000.0,
    temporal_limit_seconds: float = 3600.0,
    action_limit: int = 100,
) -> dict:
    return {
        "financial_limit": financial_limit,
        "temporal_limit_seconds": temporal_limit_seconds,
        "action_limit": action_limit,
    }


def _make_gradient(**overrides):
    from kaizen.l3.envelope.types import PlanGradient

    defaults = {
        "budget_flag_threshold": 0.80,
        "budget_hold_threshold": 0.95,
    }
    defaults.update(overrides)
    return PlanGradient(**defaults)


class TestEnvelopeEnforcerConstruction:
    """Enforcer requires all components."""

    def test_requires_tracker(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer

        with pytest.raises((TypeError, ValueError)):
            EnvelopeEnforcer(tracker=None)  # type: ignore[arg-type]

    def test_construction_with_tracker(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)
        assert enforcer.tracker is tracker


class TestNonBypassable:
    """INV-3: Non-bypassable enforcement."""

    def test_no_disable_method(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        assert not hasattr(enforcer, "disable")
        assert not hasattr(enforcer, "bypass")
        assert not hasattr(enforcer, "skip")
        assert not hasattr(enforcer, "pause")

    def test_no_enable_toggle(self):
        """No enabled/disabled flag."""
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        assert not hasattr(enforcer, "enabled")
        assert not hasattr(enforcer, "_enabled")
        assert not hasattr(enforcer, "active")


class TestCheckAction:
    """check_action() — pre-execution verdict."""

    @pytest.mark.asyncio
    async def test_check_action_approved(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="web_search",
            estimated_cost=50.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 50.0},
        )
        verdict = await enforcer.check_action(ctx)
        assert verdict.is_approved is True

    @pytest.mark.asyncio
    async def test_check_action_blocked_when_over_budget(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(
            envelope=_make_envelope(financial_limit=100.0),
            gradient=_make_gradient(),
        )
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="expensive_tool",
            estimated_cost=200.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 200.0},
        )
        verdict = await enforcer.check_action(ctx)
        assert verdict.tag == "BLOCKED"

    @pytest.mark.asyncio
    async def test_check_action_does_not_record_cost(self):
        """check_action is advisory — no cost recorded."""
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="tool",
            estimated_cost=500.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 500.0},
        )
        await enforcer.check_action(ctx)

        remaining = await tracker.remaining()
        assert remaining.financial_remaining == 1000.0  # Unchanged


class TestRecordAction:
    """record_action() — post-execution recording."""

    @pytest.mark.asyncio
    async def test_record_action_after_check(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="web_search",
            estimated_cost=50.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 50.0},
        )
        check_verdict = await enforcer.check_action(ctx)
        assert check_verdict.is_approved

        record_verdict = await enforcer.record_action(ctx, actual_cost=45.0)
        # Cost actually recorded
        remaining = await tracker.remaining()
        assert remaining.financial_remaining == pytest.approx(955.0)

    @pytest.mark.asyncio
    async def test_record_action_rejects_without_check(self):
        """Must call check_action first."""
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.errors import EnforcerError
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="unapproved_tool",
            estimated_cost=50.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 50.0},
        )
        with pytest.raises(EnforcerError, match="ActionNotApproved"):
            await enforcer.record_action(ctx, actual_cost=50.0)

    @pytest.mark.asyncio
    async def test_record_action_rejects_nan_cost(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.errors import EnforcerError
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="tool",
            estimated_cost=50.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 50.0},
        )
        await enforcer.check_action(ctx)

        with pytest.raises(EnforcerError, match="InvalidContext"):
            await enforcer.record_action(ctx, actual_cost=float("nan"))

    @pytest.mark.asyncio
    async def test_record_action_rejects_negative_cost(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.errors import EnforcerError
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        ctx = EnforcementContext(
            action="tool",
            estimated_cost=50.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 50.0},
        )
        await enforcer.check_action(ctx)

        with pytest.raises(EnforcerError, match="InvalidContext"):
            await enforcer.record_action(ctx, actual_cost=-10.0)


class TestEnforcerWithStrictCallback:
    """Non-depletable dimension enforcement via callback."""

    @pytest.mark.asyncio
    async def test_strict_check_blocks_action(self):
        """A strict_check callback that returns False blocks the action."""
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())

        def block_everything(ctx: EnforcementContext) -> str | None:
            """Return a dimension name to indicate a block, or None to pass."""
            return "data_access"

        enforcer = EnvelopeEnforcer(tracker=tracker, strict_check=block_everything)

        ctx = EnforcementContext(
            action="blocked_tool",
            estimated_cost=10.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 10.0},
        )
        verdict = await enforcer.check_action(ctx)
        assert verdict.tag == "BLOCKED"
        assert verdict.dimension == "data_access"

    @pytest.mark.asyncio
    async def test_strict_check_passes(self):
        """A strict_check callback that returns None allows the action."""
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker
        from kaizen.l3.envelope.types import EnforcementContext

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())

        def allow_everything(ctx: EnforcementContext) -> str | None:
            return None

        enforcer = EnvelopeEnforcer(tracker=tracker, strict_check=allow_everything)

        ctx = EnforcementContext(
            action="allowed_tool",
            estimated_cost=10.0,
            agent_instance_id="agent-001",
            dimension_costs={"financial": 10.0},
        )
        verdict = await enforcer.check_action(ctx)
        assert verdict.is_approved


class TestEnforcerTrackerAccess:
    """Read-only tracker access."""

    @pytest.mark.asyncio
    async def test_tracker_property_is_read_only_reference(self):
        from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
        from kaizen.l3.envelope.tracker import EnvelopeTracker

        tracker = EnvelopeTracker(envelope=_make_envelope(), gradient=_make_gradient())
        enforcer = EnvelopeEnforcer(tracker=tracker)

        # Can read tracker
        remaining = await enforcer.tracker.remaining()
        assert remaining.financial_remaining == 1000.0

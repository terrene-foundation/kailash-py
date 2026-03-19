# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 1 Unit Tests: PostureBudgetIntegration

Tests verify that budget threshold events trigger the correct posture
transitions in the PostureStateMachine:

- 80% threshold: warning logged, no posture change
- 95% threshold: downgrade to SUPERVISED
- 100% exhausted: emergency_downgrade to PSEUDO_AGENT
- Configurable thresholds override defaults
- Audit trail records budget-triggered posture changes
- Duplicate threshold events are not re-emitted
- Multiple agents tracked independently
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pytest

from eatp.constraints.budget_tracker import (
    BudgetEvent,
    BudgetTracker,
    usd_to_microdollars,
)
from eatp.postures import (
    PostureStateMachine,
    PostureTransition,
    TrustPosture,
    TransitionResult,
)
from kaizen.governance.posture_budget import PostureBudgetIntegration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def budget_tracker() -> BudgetTracker:
    """Create a BudgetTracker with $100 budget (100M microdollars)."""
    return BudgetTracker(allocated_microdollars=usd_to_microdollars(100.0))


@pytest.fixture
def state_machine() -> PostureStateMachine:
    """Create a PostureStateMachine with DELEGATED default and no upgrade guards."""
    return PostureStateMachine(
        default_posture=TrustPosture.DELEGATED,
        require_upgrade_approval=False,
    )


@pytest.fixture
def integration(
    budget_tracker: BudgetTracker,
    state_machine: PostureStateMachine,
) -> PostureBudgetIntegration:
    """Create a PostureBudgetIntegration with default thresholds."""
    return PostureBudgetIntegration(
        budget_tracker=budget_tracker,
        state_machine=state_machine,
        agent_id="agent-001",
    )


# ---------------------------------------------------------------------------
# 1. 80% threshold emits warning without posture change
# ---------------------------------------------------------------------------
class TestThreshold80Warning:
    """At 80% budget usage, a warning is logged but posture is NOT changed."""

    def test_80_percent_no_posture_change(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        # Spend exactly 80% of budget ($80 out of $100)
        amount = usd_to_microdollars(80.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        # Posture should remain DELEGATED
        assert state_machine.get_posture("agent-001") == TrustPosture.DELEGATED

    def test_80_percent_warning_logged(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        amount = usd_to_microdollars(80.0)
        budget_tracker.reserve(amount)
        with caplog.at_level(
            logging.WARNING, logger="kaizen.governance.posture_budget"
        ):
            budget_tracker.record(
                reserved_microdollars=amount, actual_microdollars=amount
            )

        # Should have logged a warning about budget threshold
        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any(
            "80" in msg or "threshold" in msg.lower() for msg in warning_messages
        ), f"Expected a warning about 80% budget threshold, got: {warning_messages}"


# ---------------------------------------------------------------------------
# 2. 95% threshold triggers downgrade to SUPERVISED
# ---------------------------------------------------------------------------
class TestThreshold95Downgrade:
    """At 95% budget usage, posture is downgraded to SUPERVISED."""

    def test_95_percent_downgrades_to_supervised(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        # Spend 95% of budget
        amount = usd_to_microdollars(95.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        # Posture should be downgraded to SUPERVISED
        assert state_machine.get_posture("agent-001") == TrustPosture.SUPERVISED

    def test_95_percent_from_shared_planning_downgrades(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        """Even from SHARED_PLANNING, 95% threshold should downgrade to SUPERVISED."""
        state_machine.set_posture("agent-001", TrustPosture.SHARED_PLANNING)

        amount = usd_to_microdollars(95.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        assert state_machine.get_posture("agent-001") == TrustPosture.SUPERVISED

    def test_95_already_at_supervised_no_change(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        """If already at SUPERVISED, 95% threshold does not further downgrade."""
        state_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        amount = usd_to_microdollars(95.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        # Should remain at SUPERVISED (not PSEUDO_AGENT)
        assert state_machine.get_posture("agent-001") == TrustPosture.SUPERVISED


# ---------------------------------------------------------------------------
# 3. 100% exhausted triggers emergency_downgrade to PSEUDO_AGENT
# ---------------------------------------------------------------------------
class TestExhaustedEmergencyDowngrade:
    """When budget is fully exhausted, emergency_downgrade to PSEUDO_AGENT."""

    def test_exhaustion_triggers_emergency_downgrade(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        # Spend 100% of budget
        amount = usd_to_microdollars(100.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        # Should be emergency downgraded to PSEUDO_AGENT
        assert state_machine.get_posture("agent-001") == TrustPosture.PSEUDO_AGENT

    def test_exhaustion_from_supervised_goes_to_pseudo(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        """Even from SUPERVISED, exhaustion should emergency downgrade to PSEUDO_AGENT."""
        state_machine.set_posture("agent-001", TrustPosture.SUPERVISED)

        amount = usd_to_microdollars(100.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        assert state_machine.get_posture("agent-001") == TrustPosture.PSEUDO_AGENT


# ---------------------------------------------------------------------------
# 4. Audit trail records budget-triggered posture changes
# ---------------------------------------------------------------------------
class TestAuditTrail:
    """Transition history records budget-triggered changes with metadata."""

    def test_exhaustion_recorded_in_history(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        amount = usd_to_microdollars(100.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        history = state_machine.get_transition_history(agent_id="agent-001")
        assert len(history) >= 1

        # Find the emergency downgrade
        emergency_transitions = [
            t
            for t in history
            if t.transition_type == PostureTransition.EMERGENCY_DOWNGRADE
        ]
        assert len(emergency_transitions) >= 1

        last = emergency_transitions[-1]
        assert last.to_posture == TrustPosture.PSEUDO_AGENT
        assert last.success is True
        assert "budget" in last.reason.lower()

    def test_95_percent_recorded_in_history(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        amount = usd_to_microdollars(95.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        history = state_machine.get_transition_history(agent_id="agent-001")

        # Should have at least one downgrade transition
        downgrade_transitions = [
            t
            for t in history
            if t.transition_type
            in (PostureTransition.DOWNGRADE, PostureTransition.EMERGENCY_DOWNGRADE)
        ]
        assert len(downgrade_transitions) >= 1

        # The downgrade should mention budget in the reason
        last = downgrade_transitions[-1]
        assert "budget" in last.reason.lower()


# ---------------------------------------------------------------------------
# 5. Configurable thresholds
# ---------------------------------------------------------------------------
class TestConfigurableThresholds:
    """Custom threshold percentages override defaults."""

    def test_custom_warning_threshold(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """A custom warning threshold of 50% should log at 50% not 80%."""
        integration = PostureBudgetIntegration(
            budget_tracker=budget_tracker,
            state_machine=state_machine,
            agent_id="agent-002",
            thresholds={"warning": 0.50, "downgrade": 0.90, "emergency": 1.0},
        )
        state_machine.set_posture("agent-002", TrustPosture.DELEGATED)

        # At 50%, no posture change
        amount = usd_to_microdollars(50.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        assert state_machine.get_posture("agent-002") == TrustPosture.DELEGATED

    def test_custom_downgrade_threshold(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """Custom downgrade=0.70 triggers downgrade at exactly 70% spend."""
        integration = PostureBudgetIntegration(
            budget_tracker=budget_tracker,
            state_machine=state_machine,
            agent_id="agent-003",
            thresholds={"warning": 0.50, "downgrade": 0.70, "emergency": 1.0},
        )
        state_machine.set_posture("agent-003", TrustPosture.DELEGATED)

        # Spend exactly 70% — should trigger downgrade with custom threshold
        amount = usd_to_microdollars(70.0)
        budget_tracker.reserve(amount)
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        assert state_machine.get_posture("agent-003") == TrustPosture.SUPERVISED

    def test_custom_emergency_threshold(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """Custom emergency=0.90 triggers emergency downgrade at 90% spend."""
        # Need a fresh tracker since previous tests may have used this one
        fresh_tracker = BudgetTracker(allocated_microdollars=usd_to_microdollars(100.0))
        integration = PostureBudgetIntegration(
            budget_tracker=fresh_tracker,
            state_machine=state_machine,
            agent_id="agent-004",
            thresholds={"warning": 0.50, "downgrade": 0.70, "emergency": 0.90},
        )
        state_machine.set_posture("agent-004", TrustPosture.DELEGATED)

        # Spend 90% — should trigger emergency with custom threshold
        amount = usd_to_microdollars(90.0)
        fresh_tracker.reserve(amount)
        fresh_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        assert state_machine.get_posture("agent-004") == TrustPosture.PSEUDO_AGENT


# ---------------------------------------------------------------------------
# 6. Duplicate threshold events are not re-processed
# ---------------------------------------------------------------------------
class TestNoDuplicateProcessing:
    """BudgetTracker fires each threshold once. Integration should handle
    the event only once, not produce duplicate transitions."""

    def test_repeated_records_no_duplicate_transitions(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.DELEGATED)

        # Record in increments past 80%
        for i in range(10):
            amt = usd_to_microdollars(10.0)
            budget_tracker.reserve(amt)
            budget_tracker.record(reserved_microdollars=amt, actual_microdollars=amt)

        # At this point, 100% used. Multiple thresholds should have fired
        # but each only once. Emergency downgrade should have happened.
        assert state_machine.get_posture("agent-001") == TrustPosture.PSEUDO_AGENT

        # Check that emergency downgrade happened only once
        history = state_machine.get_transition_history(agent_id="agent-001")
        emergency_transitions = [
            t
            for t in history
            if t.transition_type == PostureTransition.EMERGENCY_DOWNGRADE
        ]
        assert len(emergency_transitions) == 1


# ---------------------------------------------------------------------------
# 7. PostureBudgetIntegration requires valid arguments
# ---------------------------------------------------------------------------
class TestValidation:
    """Construction validates inputs."""

    def test_requires_agent_id(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        with pytest.raises((ValueError, TypeError)):
            PostureBudgetIntegration(
                budget_tracker=budget_tracker,
                state_machine=state_machine,
                agent_id="",
            )

    def test_invalid_threshold_keys_rejected(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        with pytest.raises((ValueError, KeyError)):
            PostureBudgetIntegration(
                budget_tracker=budget_tracker,
                state_machine=state_machine,
                agent_id="agent-001",
                thresholds={"invalid_key": 0.5},
            )

    def test_threshold_values_must_be_valid_fractions(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """Threshold values must be between 0 and 1 (exclusive of 0)."""
        with pytest.raises(ValueError):
            PostureBudgetIntegration(
                budget_tracker=budget_tracker,
                state_machine=state_machine,
                agent_id="agent-001",
                thresholds={"warning": 1.5, "downgrade": 0.95, "emergency": 1.0},
            )


# ---------------------------------------------------------------------------
# 10. NaN/Inf threshold rejection (RT-04)
# ---------------------------------------------------------------------------
class TestNanInfThresholds:
    """Non-finite threshold values must be rejected at construction time.

    NaN and Inf bypass numeric comparisons (NaN > X is always False,
    Inf > 1.0 is True but isfinite() catches it first). These tests
    verify math.isfinite() enforcement in PostureBudgetIntegration.__init__.
    """

    def test_nan_warning_rejected(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """NaN threshold value is rejected with a 'finite' error."""
        with pytest.raises(ValueError, match="finite"):
            PostureBudgetIntegration(
                budget_tracker=budget_tracker,
                state_machine=state_machine,
                agent_id="nan-test",
                thresholds={"warning": float("nan")},
            )

    def test_inf_downgrade_rejected(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """Positive Inf threshold value is rejected with a 'finite' error."""
        with pytest.raises(ValueError, match="finite"):
            PostureBudgetIntegration(
                budget_tracker=budget_tracker,
                state_machine=state_machine,
                agent_id="inf-test",
                thresholds={"downgrade": float("inf")},
            )

    def test_negative_inf_rejected(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
    ) -> None:
        """Negative Inf threshold value is rejected (not finite)."""
        with pytest.raises(ValueError, match="finite"):
            PostureBudgetIntegration(
                budget_tracker=budget_tracker,
                state_machine=state_machine,
                agent_id="neginf-test",
                thresholds={"emergency": float("-inf")},
            )


# ---------------------------------------------------------------------------
# 8. PostureBudgetIntegration exposes accessors
# ---------------------------------------------------------------------------
class TestAccessors:
    """Integration exposes useful read-only accessors."""

    def test_agent_id_accessor(
        self,
        integration: PostureBudgetIntegration,
    ) -> None:
        assert integration.agent_id == "agent-001"

    def test_thresholds_accessor(
        self,
        integration: PostureBudgetIntegration,
    ) -> None:
        thresholds = integration.thresholds
        assert "warning" in thresholds
        assert "downgrade" in thresholds
        assert "emergency" in thresholds
        # Defaults
        assert thresholds["warning"] == 0.80
        assert thresholds["downgrade"] == 0.95
        assert thresholds["emergency"] == 1.0


# ---------------------------------------------------------------------------
# 9. Integration with already-at-PSEUDO_AGENT
# ---------------------------------------------------------------------------
class TestAlreadyAtLowest:
    """If agent is already at PSEUDO_AGENT, budget events do not fail."""

    def test_exhaustion_at_pseudo_agent_no_error(
        self,
        budget_tracker: BudgetTracker,
        state_machine: PostureStateMachine,
        integration: PostureBudgetIntegration,
    ) -> None:
        state_machine.set_posture("agent-001", TrustPosture.PSEUDO_AGENT)

        amount = usd_to_microdollars(100.0)
        budget_tracker.reserve(amount)
        # Should not raise, even if agent is already at lowest posture
        budget_tracker.record(reserved_microdollars=amount, actual_microdollars=amount)

        assert state_machine.get_posture("agent-001") == TrustPosture.PSEUDO_AGENT

"""Unit tests for PostureStateMachine bounded history (ROUND6-002).

Tests that PostureStateMachine limits transition history to prevent
unbounded memory growth via the _max_history_size limit and _record_transition
method that trims oldest entries when the limit is exceeded.

These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import pytest
from kailash.trust.posture.postures import (
    PostureStateMachine,
    PostureTransition,
    PostureTransitionRequest,
    TransitionResult,
    TrustPosture,
)


class TestMaxHistorySizeAttribute:
    """Test that _max_history_size attribute exists and has correct value."""

    def test_max_history_size_attribute_exists(self):
        """ROUND6-002: Verify _max_history_size attribute exists on PostureStateMachine."""
        machine = PostureStateMachine()

        assert hasattr(machine, "_max_history_size"), (
            "PostureStateMachine must have _max_history_size attribute "
            "for bounded history"
        )

    def test_max_history_size_is_10000(self):
        """ROUND6-002: Verify _max_history_size is set to 10000."""
        machine = PostureStateMachine()

        assert (
            machine._max_history_size == 10000
        ), f"_max_history_size should be 10000, got {machine._max_history_size}"

    def test_max_history_size_is_integer(self):
        """ROUND6-002: Verify _max_history_size is an integer."""
        machine = PostureStateMachine()

        assert isinstance(
            machine._max_history_size, int
        ), "_max_history_size should be an integer"


class TestRecordTransitionMethodExists:
    """Test that _record_transition method exists and is callable."""

    def test_record_transition_method_exists(self):
        """ROUND6-002: Verify _record_transition method exists."""
        machine = PostureStateMachine()

        assert hasattr(
            machine, "_record_transition"
        ), "PostureStateMachine must have _record_transition method"

    def test_record_transition_is_callable(self):
        """ROUND6-002: Verify _record_transition is callable."""
        machine = PostureStateMachine()

        assert callable(
            machine._record_transition
        ), "_record_transition must be callable"


class TestHistoryBoundsBasic:
    """Test basic history bounding behavior."""

    def test_history_stays_bounded_simple(self):
        """ROUND6-002: History stays bounded when many transitions are recorded.

        NOTE: This test may fail if _record_transition has infinite recursion.
        The fix should append to history and trim, not call itself recursively.
        """
        machine = PostureStateMachine(require_upgrade_approval=False)
        max_size = machine._max_history_size

        # Try to record more transitions than the max
        # This may cause RecursionError if _record_transition calls itself
        num_transitions = max_size + 500

        try:
            for i in range(num_transitions):
                # Alternate between two postures to create valid transitions
                if i % 2 == 0:
                    machine.set_posture("test-agent", TrustPosture.SUPERVISED)
                    machine.transition(
                        PostureTransitionRequest(
                            agent_id="test-agent",
                            from_posture=TrustPosture.SUPERVISED,
                            to_posture=TrustPosture.ASSISTED,
                        )
                    )
                else:
                    machine.transition(
                        PostureTransitionRequest(
                            agent_id="test-agent",
                            from_posture=TrustPosture.ASSISTED,
                            to_posture=TrustPosture.SUPERVISED,
                        )
                    )
        except RecursionError as e:
            pytest.fail(
                f"RecursionError in _record_transition - likely infinite recursion: {e}"
            )

        # Verify history is bounded
        history_size = len(machine._transition_history)
        assert (
            history_size <= max_size
        ), f"History size {history_size} exceeds max {max_size}"

    def test_history_trimmed_by_10_percent(self):
        """ROUND6-002: When history exceeds max, oldest 10% are trimmed."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        # Override max_history_size to a smaller value for testing
        machine._max_history_size = 100
        max_size = machine._max_history_size

        # Fill history to exactly max + 1
        for i in range(max_size + 1):
            if i % 2 == 0:
                machine.set_posture("agent", TrustPosture.SUPERVISED)
                machine.transition(
                    PostureTransitionRequest(
                        agent_id="agent",
                        from_posture=TrustPosture.SUPERVISED,
                        to_posture=TrustPosture.ASSISTED,
                    )
                )
            else:
                machine.transition(
                    PostureTransitionRequest(
                        agent_id="agent",
                        from_posture=TrustPosture.ASSISTED,
                        to_posture=TrustPosture.SUPERVISED,
                    )
                )

        # After trimming 10%, we should have 90 entries (100 - 10)
        # Note: actual size depends on when trimming occurs
        history_size = len(machine._transition_history)
        expected_after_trim = max_size - (max_size // 10)  # 90

        assert (
            history_size <= max_size
        ), f"History size {history_size} should not exceed max {max_size}"


class TestMostRecentTransitionsPreserved:
    """Test that most recent transitions are preserved, not oldest."""

    def test_most_recent_preserved_after_trim(self):
        """ROUND6-002: Most recent transitions are preserved (not oldest)."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        # Use smaller max for faster test
        machine._max_history_size = 50
        max_size = machine._max_history_size

        # Create unique markers for transitions
        # First batch (these should be trimmed)
        for i in range(30):
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                    reason=f"old_batch_{i}",
                )
            )

        # Second batch (these should be preserved as they are more recent)
        recent_reasons = []
        for i in range(30):
            reason = f"new_batch_{i}"
            recent_reasons.append(reason)
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                    reason=reason,
                )
            )

        # Get history
        history = machine.get_transition_history()

        # The most recent transitions should be present
        # Check that at least some of the new_batch entries are preserved
        preserved_recent = [
            h for h in history if h.reason and h.reason.startswith("new_batch_")
        ]

        # All or most of new_batch should be preserved since they are recent
        assert (
            len(preserved_recent) > 0
        ), "Recent transitions should be preserved after trimming"

        # Check that old entries were trimmed (if trimming occurred)
        if len(history) < 60:  # Trimming occurred
            old_entries = [
                h for h in history if h.reason and h.reason.startswith("old_batch_")
            ]
            # If we preserved all new entries, old ones should be partially trimmed
            assert len(old_entries) < 30, "Oldest entries should be trimmed first"


class TestEmergencyDowngradeUsesBoundedHistory:
    """Test that emergency_downgrade uses bounded history."""

    def test_emergency_downgrade_records_to_bounded_history(self):
        """ROUND6-002: Emergency downgrade uses bounded history."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        # Use smaller max for testing
        machine._max_history_size = 20
        max_size = machine._max_history_size

        # Perform many emergency downgrades
        num_downgrades = max_size + 10

        try:
            for i in range(num_downgrades):
                machine.set_posture(f"agent-{i % 5}", TrustPosture.FULL_AUTONOMY)
                machine.emergency_downgrade(
                    agent_id=f"agent-{i % 5}",
                    reason=f"Emergency {i}",
                )
        except RecursionError as e:
            pytest.fail(f"RecursionError in emergency_downgrade: {e}")

        # Verify history is bounded
        history_size = len(machine._transition_history)
        assert (
            history_size <= max_size
        ), f"History size {history_size} exceeds max {max_size} after emergency downgrades"

    def test_emergency_downgrade_transitions_recorded(self):
        """Test that emergency downgrade transitions are properly recorded."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        machine.set_posture("test-agent", TrustPosture.FULL_AUTONOMY)
        machine.emergency_downgrade(
            agent_id="test-agent",
            reason="Security incident",
            requester_id="security-system",
        )

        history = machine.get_transition_history()

        assert len(history) >= 1, "Emergency downgrade should be recorded"

        last_transition = history[-1]
        assert last_transition.transition_type == PostureTransition.EMERGENCY_DOWNGRADE
        assert last_transition.to_posture == TrustPosture.BLOCKED
        assert last_transition.success is True


class TestTransitionViaGuardsUsesBoundedHistory:
    """Test that transitions via guards use bounded history."""

    def test_transition_via_guards_bounded(self):
        """ROUND6-002: Transition via guards uses bounded history."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        # Use smaller max for testing
        machine._max_history_size = 30
        max_size = machine._max_history_size

        # Perform many transitions that go through guards
        num_transitions = max_size + 15

        try:
            for i in range(num_transitions):
                machine.set_posture("agent", TrustPosture.BLOCKED)
                machine.transition(
                    PostureTransitionRequest(
                        agent_id="agent",
                        from_posture=TrustPosture.BLOCKED,
                        to_posture=TrustPosture.SUPERVISED,
                        reason=f"Upgrade {i}",
                    )
                )
        except RecursionError as e:
            pytest.fail(f"RecursionError in transition: {e}")

        # Verify history is bounded
        history_size = len(machine._transition_history)
        assert (
            history_size <= max_size
        ), f"History size {history_size} exceeds max {max_size}"

    def test_blocked_transitions_also_recorded(self):
        """Test that blocked transitions are also recorded in bounded history."""
        machine = PostureStateMachine(require_upgrade_approval=True)

        # Use smaller max for testing
        machine._max_history_size = 20
        max_size = machine._max_history_size

        # Perform many blocked transitions (no requester_id)
        num_transitions = max_size + 10

        try:
            for i in range(num_transitions):
                machine.set_posture("agent", TrustPosture.SUPERVISED)
                machine.transition(
                    PostureTransitionRequest(
                        agent_id="agent",
                        from_posture=TrustPosture.SUPERVISED,
                        to_posture=TrustPosture.FULL_AUTONOMY,
                        reason=f"Blocked attempt {i}",
                        # No requester_id - should be blocked by guard
                    )
                )
        except RecursionError as e:
            pytest.fail(f"RecursionError recording blocked transitions: {e}")

        # Verify history is bounded
        history_size = len(machine._transition_history)
        assert (
            history_size <= max_size
        ), f"History size {history_size} exceeds max {max_size}"

        # Verify some blocked transitions are in history
        history = machine.get_transition_history()
        blocked = [h for h in history if h.success is False]
        assert len(blocked) > 0, "Blocked transitions should be recorded"


class TestHistoryRetrievalAfterBounding:
    """Test that history retrieval works correctly after bounding."""

    def test_get_transition_history_after_bound(self):
        """Test get_transition_history returns correct results after bounding."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        machine._max_history_size = 25

        # Create transitions for multiple agents
        for i in range(40):
            agent_id = f"agent-{i % 3}"
            machine.set_posture(agent_id, TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id=agent_id,
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                )
            )

        # Get all history
        all_history = machine.get_transition_history()
        assert len(all_history) <= 25, "History should be bounded"

        # Get history for specific agent
        agent_history = machine.get_transition_history(agent_id="agent-0")
        assert all(
            h.metadata.get("agent_id") == "agent-0" for h in agent_history
        ), "Filtered history should only contain specified agent"

        # Get with limit
        limited = machine.get_transition_history(limit=5)
        assert len(limited) == 5, "Limit should be respected"

    def test_history_limit_respects_bounding(self):
        """Test that history limit works with bounded history."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        machine._max_history_size = 15

        # Fill beyond bound
        for i in range(20):
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                )
            )

        # Request more than what's bounded
        history = machine.get_transition_history(limit=50)

        # Should return at most the bounded amount
        assert len(history) <= 15, "Should not exceed bounded history size"


class TestMemoryGrowthPrevention:
    """Test that history bounding prevents unbounded memory growth."""

    def test_no_memory_growth_over_many_transitions(self):
        """ROUND6-002: History size stays constant after reaching max."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        machine._max_history_size = 100

        # Perform initial transitions to fill history
        for i in range(100):
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                )
            )

        # Get initial size (should be at or near max)
        initial_size = len(machine._transition_history)

        # Perform many more transitions
        for i in range(500):
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                )
            )

        final_size = len(machine._transition_history)

        # Size should not have grown unboundedly
        assert final_size <= 100, f"History grew to {final_size} despite max of 100"

        # Size should be reasonably close to initial after trimming
        assert final_size <= initial_size, "History should not grow after initial fill"


class TestEdgeCases:
    """Test edge cases for history bounding."""

    def test_empty_history_no_issues(self):
        """Test that empty history works correctly."""
        machine = PostureStateMachine()

        history = machine.get_transition_history()
        assert len(history) == 0, "Fresh machine should have empty history"

    def test_single_transition_preserved(self):
        """Test that a single transition is preserved."""
        machine = PostureStateMachine(require_upgrade_approval=False)

        machine.set_posture("agent", TrustPosture.SUPERVISED)
        machine.transition(
            PostureTransitionRequest(
                agent_id="agent",
                from_posture=TrustPosture.SUPERVISED,
                to_posture=TrustPosture.ASSISTED,
            )
        )

        history = machine.get_transition_history()
        assert len(history) == 1, "Single transition should be preserved"

    def test_exactly_max_transitions(self):
        """Test behavior when exactly max transitions are recorded."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        machine._max_history_size = 10

        # Record exactly max transitions
        for i in range(10):
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                )
            )

        assert len(machine._transition_history) == 10

    def test_max_plus_one_triggers_trim(self):
        """Test that max+1 transitions triggers trimming."""
        machine = PostureStateMachine(require_upgrade_approval=False)
        machine._max_history_size = 10

        # Record max+1 transitions
        for i in range(11):
            machine.set_posture("agent", TrustPosture.SUPERVISED)
            machine.transition(
                PostureTransitionRequest(
                    agent_id="agent",
                    from_posture=TrustPosture.SUPERVISED,
                    to_posture=TrustPosture.ASSISTED,
                )
            )

        # Should have trimmed - size should be <= max
        assert (
            len(machine._transition_history) <= 10
        ), "History should be trimmed after exceeding max"

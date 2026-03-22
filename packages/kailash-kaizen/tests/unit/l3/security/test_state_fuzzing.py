# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""M6-05: State machine fuzzing tests for L3 lifecycle and plan state machines.

Exhaustively tests ALL invalid state transitions for:
1. AgentLifecycleState (6-state machine: Pending, Running, Waiting, Completed, Failed, Terminated)
2. PlanNodeState (6-state machine: PENDING, READY, RUNNING, COMPLETED, FAILED, SKIPPED)
3. PlanState (7-state machine: DRAFT, VALIDATED, EXECUTING, COMPLETED, FAILED, SUSPENDED, CANCELLED)

Every invalid transition must raise the appropriate error. Terminal states
must have zero valid outgoing transitions.

Red team milestone: M6-05 (state machine integrity).
"""

from __future__ import annotations

import pytest

from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    InvalidStateTransitionError,
    TerminationReason,
    WaitReason,
    _StateTag,
    validate_transition,
)
from kaizen.l3.plan.types import (
    Plan,
    PlanEdge,
    PlanNode,
    PlanNodeOutput,
    PlanNodeState,
    PlanState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All AgentLifecycleState variants for exhaustive testing
_ALL_LIFECYCLE_STATES: list[AgentLifecycleState] = [
    AgentLifecycleState.pending(),
    AgentLifecycleState.running(),
    AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE),
    AgentLifecycleState.completed(result={"ok": True}),
    AgentLifecycleState.failed(error="test error"),
    AgentLifecycleState.terminated(TerminationReason.EXPLICIT_TERMINATION),
]

# Valid transitions for AgentLifecycleState (from source code)
_VALID_LIFECYCLE_TRANSITIONS: dict[_StateTag, frozenset[_StateTag]] = {
    _StateTag.PENDING: frozenset({_StateTag.RUNNING, _StateTag.TERMINATED}),
    _StateTag.RUNNING: frozenset(
        {_StateTag.WAITING, _StateTag.COMPLETED, _StateTag.FAILED, _StateTag.TERMINATED}
    ),
    _StateTag.WAITING: frozenset({_StateTag.RUNNING, _StateTag.TERMINATED}),
    _StateTag.COMPLETED: frozenset(),
    _StateTag.FAILED: frozenset(),
    _StateTag.TERMINATED: frozenset(),
}


def _make_plan_node(
    node_id: str = "node-1",
    state: PlanNodeState = PlanNodeState.PENDING,
) -> PlanNode:
    return PlanNode(
        node_id=node_id,
        agent_spec_id="spec-1",
        input_mapping={},
        state=state,
        instance_id=None,
        optional=False,
        retry_count=0,
        output=None,
        error=None,
    )


def _make_plan(state: PlanState = PlanState.DRAFT) -> Plan:
    return Plan(
        plan_id="plan-1",
        name="test-plan",
        envelope={"financial_limit": 1000.0},
        gradient={},
        nodes={},
        edges=[],
        state=state,
    )


# ===========================================================================
# 1. AgentLifecycleState: exhaustive invalid transition tests
# ===========================================================================


class TestAgentLifecycleStateInvalidTransitions:
    """Every invalid state transition in the 6-state lifecycle machine
    must raise InvalidStateTransitionError."""

    # --- Terminal states: NO outgoing transitions ---

    @pytest.mark.parametrize(
        "to_state",
        _ALL_LIFECYCLE_STATES,
        ids=[s.tag.value for s in _ALL_LIFECYCLE_STATES],
    )
    def test_completed_has_no_outgoing_transitions(
        self, to_state: AgentLifecycleState
    ) -> None:
        """Completed is terminal -- cannot transition to any state."""
        from_state = AgentLifecycleState.completed(result="done")
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    @pytest.mark.parametrize(
        "to_state",
        _ALL_LIFECYCLE_STATES,
        ids=[s.tag.value for s in _ALL_LIFECYCLE_STATES],
    )
    def test_failed_has_no_outgoing_transitions(
        self, to_state: AgentLifecycleState
    ) -> None:
        """Failed is terminal -- cannot transition to any state."""
        from_state = AgentLifecycleState.failed(error="crash")
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    @pytest.mark.parametrize(
        "to_state",
        _ALL_LIFECYCLE_STATES,
        ids=[s.tag.value for s in _ALL_LIFECYCLE_STATES],
    )
    def test_terminated_has_no_outgoing_transitions(
        self, to_state: AgentLifecycleState
    ) -> None:
        """Terminated is terminal -- cannot transition to any state."""
        from_state = AgentLifecycleState.terminated(
            TerminationReason.EXPLICIT_TERMINATION
        )
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    # --- Pending: only Running and Terminated are valid ---

    def test_pending_to_waiting_is_invalid(self) -> None:
        from_state = AgentLifecycleState.pending()
        to_state = AgentLifecycleState.waiting(WaitReason.HUMAN_APPROVAL)
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_pending_to_completed_is_invalid(self) -> None:
        from_state = AgentLifecycleState.pending()
        to_state = AgentLifecycleState.completed()
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_pending_to_failed_is_invalid(self) -> None:
        from_state = AgentLifecycleState.pending()
        to_state = AgentLifecycleState.failed(error="early fail")
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_pending_to_pending_is_invalid(self) -> None:
        """Self-transition from Pending is not in the valid set."""
        from_state = AgentLifecycleState.pending()
        to_state = AgentLifecycleState.pending()
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    # --- Waiting: only Running and Terminated are valid ---

    def test_waiting_to_waiting_is_invalid(self) -> None:
        """Cannot re-enter Waiting from Waiting."""
        from_state = AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        to_state = AgentLifecycleState.waiting(WaitReason.HUMAN_APPROVAL)
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_waiting_to_completed_is_invalid(self) -> None:
        from_state = AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        to_state = AgentLifecycleState.completed()
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_waiting_to_failed_is_invalid(self) -> None:
        from_state = AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        to_state = AgentLifecycleState.failed(error="timeout")
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_waiting_to_pending_is_invalid(self) -> None:
        from_state = AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        to_state = AgentLifecycleState.pending()
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    # --- Running: Pending is invalid (cannot go back) ---

    def test_running_to_pending_is_invalid(self) -> None:
        """Cannot revert from Running to Pending."""
        from_state = AgentLifecycleState.running()
        to_state = AgentLifecycleState.pending()
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    def test_running_to_running_is_invalid(self) -> None:
        """Self-transition from Running is not in the valid set."""
        from_state = AgentLifecycleState.running()
        to_state = AgentLifecycleState.running()
        with pytest.raises(InvalidStateTransitionError):
            validate_transition(from_state, to_state)

    # --- Valid transitions (positive cases) ---

    def test_pending_to_running_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.pending(),
            AgentLifecycleState.running(),
        )

    def test_pending_to_terminated_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.pending(),
            AgentLifecycleState.terminated(TerminationReason.TIMEOUT),
        )

    def test_running_to_waiting_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.running(),
            AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE),
        )

    def test_running_to_completed_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.running(),
            AgentLifecycleState.completed(),
        )

    def test_running_to_failed_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.running(),
            AgentLifecycleState.failed(error="oops"),
        )

    def test_running_to_terminated_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.running(),
            AgentLifecycleState.terminated(TerminationReason.BUDGET_EXHAUSTED),
        )

    def test_waiting_to_running_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.waiting(WaitReason.HUMAN_APPROVAL),
            AgentLifecycleState.running(),
        )

    def test_waiting_to_terminated_is_valid(self) -> None:
        validate_transition(
            AgentLifecycleState.waiting(WaitReason.RESOURCE_AVAILABILITY),
            AgentLifecycleState.terminated(TerminationReason.PARENT_TERMINATED),
        )


class TestAgentInstanceTransition:
    """Test that AgentInstance.transition_to() enforces the same rules."""

    def test_instance_blocks_invalid_transition(self) -> None:
        instance = AgentInstance()
        assert instance.state.tag == _StateTag.PENDING
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.completed())

    def test_instance_allows_valid_transition(self) -> None:
        instance = AgentInstance()
        instance.transition_to(AgentLifecycleState.running())
        assert instance.state.tag == _StateTag.RUNNING

    def test_terminal_state_property(self) -> None:
        instance = AgentInstance()
        assert not instance.is_terminal
        instance.transition_to(AgentLifecycleState.running())
        assert not instance.is_terminal
        instance.transition_to(AgentLifecycleState.completed())
        assert instance.is_terminal


# ===========================================================================
# 2. PlanNodeState: exhaustive invalid transition tests
# ===========================================================================


class TestPlanNodeStateInvalidTransitions:
    """Every invalid PlanNodeState transition must raise ValueError."""

    # --- Terminal states: COMPLETED and SKIPPED have no outgoing ---

    @pytest.mark.parametrize("target", list(PlanNodeState))
    def test_completed_has_no_outgoing_transitions(self, target: PlanNodeState) -> None:
        node = _make_plan_node(state=PlanNodeState.COMPLETED)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(target)

    @pytest.mark.parametrize("target", list(PlanNodeState))
    def test_skipped_has_no_outgoing_transitions(self, target: PlanNodeState) -> None:
        node = _make_plan_node(state=PlanNodeState.SKIPPED)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(target)

    # --- PENDING: only READY and SKIPPED are valid ---

    def test_pending_to_running_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.PENDING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.RUNNING)

    def test_pending_to_completed_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.PENDING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.COMPLETED)

    def test_pending_to_failed_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.PENDING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.FAILED)

    def test_pending_to_pending_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.PENDING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.PENDING)

    # --- READY: only RUNNING and SKIPPED are valid ---

    def test_ready_to_pending_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.READY)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.PENDING)

    def test_ready_to_completed_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.READY)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.COMPLETED)

    def test_ready_to_failed_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.READY)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.FAILED)

    def test_ready_to_ready_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.READY)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.READY)

    # --- RUNNING: only COMPLETED and FAILED are valid ---

    def test_running_to_pending_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.RUNNING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.PENDING)

    def test_running_to_ready_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.RUNNING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.READY)

    def test_running_to_running_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.RUNNING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.RUNNING)

    def test_running_to_skipped_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.RUNNING)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.SKIPPED)

    # --- FAILED: only RUNNING (retry) and SKIPPED are valid ---

    def test_failed_to_pending_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.FAILED)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.PENDING)

    def test_failed_to_ready_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.FAILED)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.READY)

    def test_failed_to_completed_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.FAILED)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.COMPLETED)

    def test_failed_to_failed_is_invalid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.FAILED)
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.FAILED)

    # --- Valid transitions (positive cases) ---

    def test_pending_to_ready_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.PENDING)
        node.transition_to(PlanNodeState.READY)
        assert node.state == PlanNodeState.READY

    def test_pending_to_skipped_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.PENDING)
        node.transition_to(PlanNodeState.SKIPPED)
        assert node.state == PlanNodeState.SKIPPED

    def test_ready_to_running_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.READY)
        node.transition_to(PlanNodeState.RUNNING)
        assert node.state == PlanNodeState.RUNNING

    def test_ready_to_skipped_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.READY)
        node.transition_to(PlanNodeState.SKIPPED)
        assert node.state == PlanNodeState.SKIPPED

    def test_running_to_completed_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.RUNNING)
        node.transition_to(PlanNodeState.COMPLETED)
        assert node.state == PlanNodeState.COMPLETED

    def test_running_to_failed_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.RUNNING)
        node.transition_to(PlanNodeState.FAILED)
        assert node.state == PlanNodeState.FAILED

    def test_failed_to_running_retry_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.FAILED)
        node.transition_to(PlanNodeState.RUNNING)
        assert node.state == PlanNodeState.RUNNING

    def test_failed_to_skipped_is_valid(self) -> None:
        node = _make_plan_node(state=PlanNodeState.FAILED)
        node.transition_to(PlanNodeState.SKIPPED)
        assert node.state == PlanNodeState.SKIPPED


# ===========================================================================
# 3. PlanState: exhaustive invalid transition tests
# ===========================================================================


class TestPlanStateInvalidTransitions:
    """Every invalid PlanState transition must raise ValueError."""

    # --- Terminal states: COMPLETED, FAILED, CANCELLED have no outgoing ---

    @pytest.mark.parametrize("target", list(PlanState))
    def test_completed_has_no_outgoing_transitions(self, target: PlanState) -> None:
        plan = _make_plan(state=PlanState.COMPLETED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(target)

    @pytest.mark.parametrize("target", list(PlanState))
    def test_failed_has_no_outgoing_transitions(self, target: PlanState) -> None:
        plan = _make_plan(state=PlanState.FAILED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(target)

    @pytest.mark.parametrize("target", list(PlanState))
    def test_cancelled_has_no_outgoing_transitions(self, target: PlanState) -> None:
        plan = _make_plan(state=PlanState.CANCELLED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(target)

    # --- DRAFT: only VALIDATED and DRAFT (self) are valid ---

    def test_draft_to_executing_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.DRAFT)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.EXECUTING)

    def test_draft_to_completed_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.DRAFT)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.COMPLETED)

    def test_draft_to_failed_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.DRAFT)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.FAILED)

    def test_draft_to_suspended_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.DRAFT)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.SUSPENDED)

    def test_draft_to_cancelled_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.DRAFT)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.CANCELLED)

    # --- VALIDATED: only EXECUTING and DRAFT are valid ---

    def test_validated_to_completed_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.VALIDATED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.COMPLETED)

    def test_validated_to_failed_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.VALIDATED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.FAILED)

    def test_validated_to_suspended_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.VALIDATED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.SUSPENDED)

    def test_validated_to_cancelled_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.VALIDATED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.CANCELLED)

    def test_validated_to_validated_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.VALIDATED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.VALIDATED)

    # --- EXECUTING: DRAFT, VALIDATED are invalid ---

    def test_executing_to_draft_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.DRAFT)

    def test_executing_to_validated_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.VALIDATED)

    def test_executing_to_executing_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.EXECUTING)

    # --- SUSPENDED: only EXECUTING and CANCELLED are valid ---

    def test_suspended_to_draft_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.DRAFT)

    def test_suspended_to_validated_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.VALIDATED)

    def test_suspended_to_completed_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.COMPLETED)

    def test_suspended_to_failed_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.FAILED)

    def test_suspended_to_suspended_is_invalid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        with pytest.raises(ValueError, match="Invalid plan state transition"):
            plan.transition_to(PlanState.SUSPENDED)

    # --- Valid transitions (positive cases) ---

    def test_draft_to_validated_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.DRAFT)
        plan.transition_to(PlanState.VALIDATED)
        assert plan.state == PlanState.VALIDATED

    def test_draft_to_draft_is_valid(self) -> None:
        """Self-transition: re-editing a draft."""
        plan = _make_plan(state=PlanState.DRAFT)
        plan.transition_to(PlanState.DRAFT)
        assert plan.state == PlanState.DRAFT

    def test_validated_to_executing_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.VALIDATED)
        plan.transition_to(PlanState.EXECUTING)
        assert plan.state == PlanState.EXECUTING

    def test_validated_to_draft_is_valid(self) -> None:
        """Modification after validation returns to draft."""
        plan = _make_plan(state=PlanState.VALIDATED)
        plan.transition_to(PlanState.DRAFT)
        assert plan.state == PlanState.DRAFT

    def test_executing_to_completed_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.COMPLETED)
        assert plan.state == PlanState.COMPLETED

    def test_executing_to_failed_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.FAILED)
        assert plan.state == PlanState.FAILED

    def test_executing_to_suspended_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.SUSPENDED)
        assert plan.state == PlanState.SUSPENDED

    def test_executing_to_cancelled_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.CANCELLED)
        assert plan.state == PlanState.CANCELLED

    def test_suspended_to_executing_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        plan.transition_to(PlanState.EXECUTING)
        assert plan.state == PlanState.EXECUTING

    def test_suspended_to_cancelled_is_valid(self) -> None:
        plan = _make_plan(state=PlanState.SUSPENDED)
        plan.transition_to(PlanState.CANCELLED)
        assert plan.state == PlanState.CANCELLED


# ===========================================================================
# 4. Exhaustive matrix: verify every (from, to) pair is covered
# ===========================================================================


class TestExhaustiveTransitionMatrix:
    """Verify that every possible (from_state, to_state) pair is tested
    and matches the declared transition tables exactly."""

    def test_lifecycle_transition_completeness(self) -> None:
        """For every (from_tag, to_tag) pair in the 6x6 matrix,
        verify the transition table is consistent."""
        all_tags = list(_StateTag)
        for from_tag in all_tags:
            valid_targets = _VALID_LIFECYCLE_TRANSITIONS[from_tag]
            for to_tag in all_tags:
                from_state = _make_lifecycle_state(from_tag)
                to_state = _make_lifecycle_state(to_tag)
                if to_tag in valid_targets:
                    # Should not raise
                    validate_transition(from_state, to_state)
                else:
                    # Should raise
                    with pytest.raises(InvalidStateTransitionError):
                        validate_transition(from_state, to_state)

    def test_node_transition_completeness(self) -> None:
        """For every (from_state, to_state) pair in the PlanNodeState matrix,
        verify the transition table is consistent."""
        from kaizen.l3.plan.types import _NODE_TRANSITIONS

        all_states = list(PlanNodeState)
        for from_state in all_states:
            valid_targets = _NODE_TRANSITIONS[from_state]
            for to_state in all_states:
                node = _make_plan_node(state=from_state)
                if to_state in valid_targets:
                    node.transition_to(to_state)
                    assert node.state == to_state
                else:
                    with pytest.raises(
                        ValueError, match="Invalid node state transition"
                    ):
                        node.transition_to(to_state)

    def test_plan_transition_completeness(self) -> None:
        """For every (from_state, to_state) pair in the PlanState matrix,
        verify the transition table is consistent."""
        from kaizen.l3.plan.types import _PLAN_TRANSITIONS

        all_states = list(PlanState)
        for from_state in all_states:
            valid_targets = _PLAN_TRANSITIONS[from_state]
            for to_state in all_states:
                plan = _make_plan(state=from_state)
                if to_state in valid_targets:
                    plan.transition_to(to_state)
                    assert plan.state == to_state
                else:
                    with pytest.raises(
                        ValueError, match="Invalid plan state transition"
                    ):
                        plan.transition_to(to_state)


def _make_lifecycle_state(tag: _StateTag) -> AgentLifecycleState:
    """Create a representative AgentLifecycleState for a given tag."""
    if tag == _StateTag.PENDING:
        return AgentLifecycleState.pending()
    elif tag == _StateTag.RUNNING:
        return AgentLifecycleState.running()
    elif tag == _StateTag.WAITING:
        return AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
    elif tag == _StateTag.COMPLETED:
        return AgentLifecycleState.completed()
    elif tag == _StateTag.FAILED:
        return AgentLifecycleState.failed(error="test")
    elif tag == _StateTag.TERMINATED:
        return AgentLifecycleState.terminated(TerminationReason.EXPLICIT_TERMINATION)
    raise ValueError(f"Unknown tag: {tag}")


# ===========================================================================
# 5. Terminal state immutability
# ===========================================================================


class TestTerminalStateImmutability:
    """Terminal states are frozen dataclasses -- they cannot be mutated."""

    def test_completed_state_is_frozen(self) -> None:
        state = AgentLifecycleState.completed(result="done")
        with pytest.raises(AttributeError):
            state.tag = _StateTag.RUNNING  # type: ignore[misc]

    def test_failed_state_is_frozen(self) -> None:
        state = AgentLifecycleState.failed(error="crash")
        with pytest.raises(AttributeError):
            state.tag = _StateTag.RUNNING  # type: ignore[misc]

    def test_terminated_state_is_frozen(self) -> None:
        state = AgentLifecycleState.terminated(TerminationReason.TIMEOUT)
        with pytest.raises(AttributeError):
            state.tag = _StateTag.RUNNING  # type: ignore[misc]

    def test_plan_node_state_change_via_field_bypass_blocked(self) -> None:
        """PlanNode is NOT frozen (mutable entity), but transition_to()
        is the only safe mutation path."""
        node = _make_plan_node(state=PlanNodeState.COMPLETED)
        # Direct field assignment bypasses validation -- this is "allowed"
        # structurally but transition_to() is the enforced contract.
        # The security property is that transition_to() rejects invalid transitions.
        with pytest.raises(ValueError, match="Invalid node state transition"):
            node.transition_to(PlanNodeState.RUNNING)

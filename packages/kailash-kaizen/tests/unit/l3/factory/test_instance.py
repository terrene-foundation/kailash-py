# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M0-04: AgentInstance lifecycle state machine (B5)."""

import pytest

from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    InvalidStateTransitionError,
    TerminationReason,
    WaitReason,
)


class TestAgentLifecycleState:
    """Test lifecycle state construction and properties."""

    def test_pending_state(self):
        state = AgentLifecycleState.pending()
        assert state.name == "pending"
        assert not state.is_terminal

    def test_running_state(self):
        state = AgentLifecycleState.running()
        assert state.name == "running"
        assert not state.is_terminal

    def test_waiting_state(self):
        state = AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE, "msg-123")
        assert state.name == "waiting"
        assert state.wait_reason == WaitReason.DELEGATION_RESPONSE
        assert state.wait_context == "msg-123"
        assert not state.is_terminal

    def test_completed_state_is_terminal(self):
        state = AgentLifecycleState.completed(result={"status": "done"})
        assert state.name == "completed"
        assert state.is_terminal
        assert state.result == {"status": "done"}

    def test_failed_state_is_terminal(self):
        state = AgentLifecycleState.failed("out of memory")
        assert state.name == "failed"
        assert state.is_terminal
        assert state.error == "out of memory"

    def test_terminated_state_is_terminal(self):
        state = AgentLifecycleState.terminated(
            TerminationReason.BUDGET_EXHAUSTED, "financial limit reached"
        )
        assert state.name == "terminated"
        assert state.is_terminal
        assert state.termination_reason == TerminationReason.BUDGET_EXHAUSTED

    def test_to_dict_round_trip(self):
        state = AgentLifecycleState.waiting(WaitReason.CLARIFICATION_PENDING, "msg-456")
        d = state.to_dict()
        assert d["tag"] == "waiting"
        assert d["wait_reason"] == "clarification_pending"
        assert d["wait_context"] == "msg-456"


class TestWaitReason:
    """Test WaitReason enum (including F-03 additions)."""

    def test_all_five_variants(self):
        assert len(WaitReason) == 5
        assert WaitReason.DELEGATION_RESPONSE.value == "delegation_response"
        assert WaitReason.HUMAN_APPROVAL.value == "human_approval"
        assert WaitReason.RESOURCE_AVAILABILITY.value == "resource_availability"
        assert WaitReason.CLARIFICATION_PENDING.value == "clarification_pending"
        assert WaitReason.ESCALATION_PENDING.value == "escalation_pending"


class TestTerminationReason:
    """Test TerminationReason enum."""

    def test_all_five_variants(self):
        assert len(TerminationReason) == 5
        assert TerminationReason.PARENT_TERMINATED.value == "parent_terminated"
        assert TerminationReason.ENVELOPE_VIOLATION.value == "envelope_violation"
        assert TerminationReason.TIMEOUT.value == "timeout"
        assert TerminationReason.BUDGET_EXHAUSTED.value == "budget_exhausted"
        assert TerminationReason.EXPLICIT_TERMINATION.value == "explicit_termination"


class TestStateTransitions:
    """Test valid and invalid state transitions."""

    # --- Valid transitions ---

    def test_pending_to_running(self):
        instance = AgentInstance(spec_id="test")
        assert instance.state.name == "pending"
        instance.transition_to(AgentLifecycleState.running())
        assert instance.state.name == "running"

    def test_pending_to_terminated(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(
            AgentLifecycleState.terminated(TerminationReason.EXPLICIT_TERMINATION)
        )
        assert instance.is_terminal

    def test_running_to_waiting(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(
            AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        )
        assert instance.state.name == "waiting"

    def test_running_to_completed(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(AgentLifecycleState.completed({"result": "ok"}))
        assert instance.is_terminal

    def test_running_to_failed(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(AgentLifecycleState.failed("crash"))
        assert instance.is_terminal

    def test_running_to_terminated(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(
            AgentLifecycleState.terminated(TerminationReason.TIMEOUT)
        )
        assert instance.is_terminal

    def test_waiting_to_running(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(AgentLifecycleState.waiting(WaitReason.HUMAN_APPROVAL))
        instance.transition_to(AgentLifecycleState.running())
        assert instance.state.name == "running"

    def test_waiting_to_terminated(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(
            AgentLifecycleState.waiting(WaitReason.RESOURCE_AVAILABILITY)
        )
        instance.transition_to(
            AgentLifecycleState.terminated(TerminationReason.PARENT_TERMINATED)
        )
        assert instance.is_terminal

    # --- Invalid transitions ---

    def test_pending_to_completed_invalid(self):
        instance = AgentInstance(spec_id="test")
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.completed())

    def test_pending_to_failed_invalid(self):
        instance = AgentInstance(spec_id="test")
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.failed("err"))

    def test_pending_to_waiting_invalid(self):
        instance = AgentInstance(spec_id="test")
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(
                AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
            )

    def test_completed_to_running_invalid(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(AgentLifecycleState.completed())
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.running())

    def test_failed_to_running_invalid(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(AgentLifecycleState.failed("err"))
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.running())

    def test_terminated_to_running_invalid(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(
            AgentLifecycleState.terminated(TerminationReason.TIMEOUT)
        )
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.running())

    def test_waiting_to_completed_invalid(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(
            AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        )
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.completed())

    def test_waiting_to_failed_invalid(self):
        instance = AgentInstance(spec_id="test")
        instance.transition_to(AgentLifecycleState.running())
        instance.transition_to(
            AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE)
        )
        with pytest.raises(InvalidStateTransitionError):
            instance.transition_to(AgentLifecycleState.failed("err"))


class TestAgentInstance:
    """Test AgentInstance entity."""

    def test_default_construction(self):
        instance = AgentInstance(spec_id="code-reviewer")
        assert instance.instance_id  # UUID generated
        assert instance.spec_id == "code-reviewer"
        assert instance.parent_id is None
        assert instance.state.name == "pending"
        assert instance.envelope is None
        assert instance.created_at is not None

    def test_with_parent(self):
        instance = AgentInstance(spec_id="worker", parent_id="parent-001")
        assert instance.parent_id == "parent-001"

    def test_multiple_instances_same_spec(self):
        """AC-3: Multiple instances can reference same spec."""
        i1 = AgentInstance(spec_id="analyzer")
        i2 = AgentInstance(spec_id="analyzer")
        assert i1.instance_id != i2.instance_id
        assert i1.spec_id == i2.spec_id

    def test_to_dict(self):
        instance = AgentInstance(spec_id="test", parent_id="p-001")
        d = instance.to_dict()
        assert d["spec_id"] == "test"
        assert d["parent_id"] == "p-001"
        assert d["state"]["tag"] == "pending"
        assert "instance_id" in d
        assert "created_at" in d

    def test_is_terminal_reflects_state(self):
        instance = AgentInstance(spec_id="test")
        assert not instance.is_terminal
        instance.transition_to(AgentLifecycleState.running())
        assert not instance.is_terminal
        instance.transition_to(AgentLifecycleState.completed())
        assert instance.is_terminal

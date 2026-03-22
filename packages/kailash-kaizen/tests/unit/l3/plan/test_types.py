# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Plan DAG type definitions.

Covers:
- PlanEdge, PlanNodeOutput frozen value types
- EdgeType enum members
- PlanNodeState, PlanState enums with valid/invalid transitions
- PlanNode mutable entity construction and state transitions
- Plan construction, state transitions, and to_dict/from_dict round-trip
- PlanEvent variants and construction
- PlanModification variants
- PlanGradient reuse from envelope.types
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest


# ---------------------------------------------------------------------------
# EdgeType tests
# ---------------------------------------------------------------------------


class TestEdgeType:
    """EdgeType enum: 3 members."""

    def test_members_exist(self):
        from kaizen.l3.plan.types import EdgeType

        assert hasattr(EdgeType, "DATA_DEPENDENCY")
        assert hasattr(EdgeType, "COMPLETION_DEPENDENCY")
        assert hasattr(EdgeType, "CO_START")

    def test_is_str_enum(self):
        from kaizen.l3.plan.types import EdgeType

        assert isinstance(EdgeType.DATA_DEPENDENCY, str)


# ---------------------------------------------------------------------------
# PlanEdge tests
# ---------------------------------------------------------------------------


class TestPlanEdge:
    """PlanEdge: frozen value type."""

    def test_construction(self):
        from kaizen.l3.plan.types import EdgeType, PlanEdge

        edge = PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY)
        assert edge.from_node == "a"
        assert edge.to_node == "b"
        assert edge.edge_type == EdgeType.DATA_DEPENDENCY

    def test_frozen(self):
        from kaizen.l3.plan.types import EdgeType, PlanEdge

        edge = PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY)
        with pytest.raises(AttributeError):
            edge.from_node = "c"  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.plan.types import EdgeType, PlanEdge

        edge = PlanEdge(
            from_node="a", to_node="b", edge_type=EdgeType.COMPLETION_DEPENDENCY
        )
        d = edge.to_dict()
        restored = PlanEdge.from_dict(d)
        assert restored == edge

    def test_self_edge_construction_allowed(self):
        """PlanEdge itself does not reject self-edges; that is validator's job."""
        from kaizen.l3.plan.types import EdgeType, PlanEdge

        edge = PlanEdge(from_node="a", to_node="a", edge_type=EdgeType.DATA_DEPENDENCY)
        assert edge.from_node == edge.to_node


# ---------------------------------------------------------------------------
# PlanNodeOutput tests
# ---------------------------------------------------------------------------


class TestPlanNodeOutput:
    """PlanNodeOutput: frozen reference to predecessor output."""

    def test_construction(self):
        from kaizen.l3.plan.types import PlanNodeOutput

        out = PlanNodeOutput(source_node="node_a", output_key="result")
        assert out.source_node == "node_a"
        assert out.output_key == "result"

    def test_frozen(self):
        from kaizen.l3.plan.types import PlanNodeOutput

        out = PlanNodeOutput(source_node="node_a", output_key="result")
        with pytest.raises(AttributeError):
            out.source_node = "node_b"  # type: ignore[misc]

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.plan.types import PlanNodeOutput

        out = PlanNodeOutput(source_node="node_a", output_key="result")
        d = out.to_dict()
        restored = PlanNodeOutput.from_dict(d)
        assert restored == out


# ---------------------------------------------------------------------------
# PlanNodeState tests
# ---------------------------------------------------------------------------


class TestPlanNodeState:
    """PlanNodeState enum: 6 members."""

    def test_members_exist(self):
        from kaizen.l3.plan.types import PlanNodeState

        assert hasattr(PlanNodeState, "PENDING")
        assert hasattr(PlanNodeState, "READY")
        assert hasattr(PlanNodeState, "RUNNING")
        assert hasattr(PlanNodeState, "COMPLETED")
        assert hasattr(PlanNodeState, "FAILED")
        assert hasattr(PlanNodeState, "SKIPPED")

    def test_is_str_enum(self):
        from kaizen.l3.plan.types import PlanNodeState

        assert isinstance(PlanNodeState.PENDING, str)


# ---------------------------------------------------------------------------
# PlanState tests
# ---------------------------------------------------------------------------


class TestPlanState:
    """PlanState enum: 7 members with validated transitions."""

    def test_members_exist(self):
        from kaizen.l3.plan.types import PlanState

        assert hasattr(PlanState, "DRAFT")
        assert hasattr(PlanState, "VALIDATED")
        assert hasattr(PlanState, "EXECUTING")
        assert hasattr(PlanState, "COMPLETED")
        assert hasattr(PlanState, "FAILED")
        assert hasattr(PlanState, "SUSPENDED")
        assert hasattr(PlanState, "CANCELLED")

    def test_terminal_states(self):
        from kaizen.l3.plan.types import PlanState

        terminals = {PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED}
        for state in terminals:
            assert state in terminals


# ---------------------------------------------------------------------------
# PlanNode tests
# ---------------------------------------------------------------------------


class TestPlanNode:
    """PlanNode: mutable entity with state transitions."""

    def _make_node(self, **overrides):
        from kaizen.l3.plan.types import PlanNode, PlanNodeState

        defaults = dict(
            node_id="node_1",
            agent_spec_id="spec_research",
            input_mapping={},
            state=PlanNodeState.PENDING,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
        )
        defaults.update(overrides)
        return PlanNode(**defaults)

    def test_construction(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node()
        assert node.node_id == "node_1"
        assert node.agent_spec_id == "spec_research"
        assert node.state == PlanNodeState.PENDING
        assert node.optional is False
        assert node.retry_count == 0

    def test_mutable_state(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node()
        node.state = PlanNodeState.READY
        assert node.state == PlanNodeState.READY

    def test_transition_pending_to_ready(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.PENDING)
        node.transition_to(PlanNodeState.READY)
        assert node.state == PlanNodeState.READY

    def test_transition_ready_to_running(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.READY)
        node.transition_to(PlanNodeState.RUNNING)
        assert node.state == PlanNodeState.RUNNING

    def test_transition_running_to_completed(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.RUNNING)
        node.transition_to(PlanNodeState.COMPLETED)
        assert node.state == PlanNodeState.COMPLETED

    def test_transition_running_to_failed(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.RUNNING)
        node.transition_to(PlanNodeState.FAILED)
        assert node.state == PlanNodeState.FAILED

    def test_transition_failed_to_running_retry(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.FAILED)
        node.transition_to(PlanNodeState.RUNNING)
        assert node.state == PlanNodeState.RUNNING

    def test_transition_pending_to_skipped(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.PENDING)
        node.transition_to(PlanNodeState.SKIPPED)
        assert node.state == PlanNodeState.SKIPPED

    def test_transition_failed_to_skipped(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.FAILED)
        node.transition_to(PlanNodeState.SKIPPED)
        assert node.state == PlanNodeState.SKIPPED

    def test_invalid_transition_completed_to_running(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.COMPLETED)
        with pytest.raises(ValueError, match="Invalid.*transition"):
            node.transition_to(PlanNodeState.RUNNING)

    def test_invalid_transition_skipped_to_running(self):
        from kaizen.l3.plan.types import PlanNodeState

        node = self._make_node(state=PlanNodeState.SKIPPED)
        with pytest.raises(ValueError, match="Invalid.*transition"):
            node.transition_to(PlanNodeState.RUNNING)

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.plan.types import PlanNode, PlanNodeOutput, PlanNodeState

        node = self._make_node(
            input_mapping={
                "data": PlanNodeOutput(source_node="node_0", output_key="result")
            }
        )
        d = node.to_dict()
        restored = PlanNode.from_dict(d)
        assert restored.node_id == node.node_id
        assert restored.agent_spec_id == node.agent_spec_id
        assert restored.state == node.state
        assert "data" in restored.input_mapping


# ---------------------------------------------------------------------------
# Plan tests
# ---------------------------------------------------------------------------


class TestPlan:
    """Plan: mutable entity with state transitions."""

    def _make_plan(self, **overrides):
        from kaizen.l3.plan.types import Plan, PlanState

        defaults = dict(
            plan_id="plan_001",
            name="test plan",
            envelope={"financial": {"max_cost": 100.0}},
            gradient={},
            nodes={},
            edges=[],
            state=PlanState.DRAFT,
        )
        defaults.update(overrides)
        return Plan(**defaults)

    def test_construction(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan()
        assert plan.plan_id == "plan_001"
        assert plan.state == PlanState.DRAFT
        assert plan.created_at is not None
        assert plan.modified_at is not None

    def test_transition_draft_to_validated(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.DRAFT)
        plan.transition_to(PlanState.VALIDATED)
        assert plan.state == PlanState.VALIDATED

    def test_transition_validated_to_executing(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.VALIDATED)
        plan.transition_to(PlanState.EXECUTING)
        assert plan.state == PlanState.EXECUTING

    def test_transition_executing_to_completed(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.COMPLETED)
        assert plan.state == PlanState.COMPLETED

    def test_transition_executing_to_failed(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.FAILED)
        assert plan.state == PlanState.FAILED

    def test_transition_executing_to_suspended(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.SUSPENDED)
        assert plan.state == PlanState.SUSPENDED

    def test_transition_executing_to_cancelled(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.EXECUTING)
        plan.transition_to(PlanState.CANCELLED)
        assert plan.state == PlanState.CANCELLED

    def test_transition_suspended_to_executing(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.SUSPENDED)
        plan.transition_to(PlanState.EXECUTING)
        assert plan.state == PlanState.EXECUTING

    def test_transition_suspended_to_cancelled(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.SUSPENDED)
        plan.transition_to(PlanState.CANCELLED)
        assert plan.state == PlanState.CANCELLED

    def test_transition_validated_to_draft_on_modification(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.VALIDATED)
        plan.transition_to(PlanState.DRAFT)
        assert plan.state == PlanState.DRAFT

    def test_invalid_transition_completed_to_executing(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.COMPLETED)
        with pytest.raises(ValueError, match="Invalid.*transition"):
            plan.transition_to(PlanState.EXECUTING)

    def test_invalid_transition_failed_to_executing(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.FAILED)
        with pytest.raises(ValueError, match="Invalid.*transition"):
            plan.transition_to(PlanState.EXECUTING)

    def test_invalid_transition_cancelled_to_executing(self):
        from kaizen.l3.plan.types import PlanState

        plan = self._make_plan(state=PlanState.CANCELLED)
        with pytest.raises(ValueError, match="Invalid.*transition"):
            plan.transition_to(PlanState.EXECUTING)

    def test_to_dict_from_dict_roundtrip(self):
        from kaizen.l3.plan.types import (
            EdgeType,
            Plan,
            PlanEdge,
            PlanNode,
            PlanNodeState,
            PlanState,
        )

        node = PlanNode(
            node_id="n1",
            agent_spec_id="spec_1",
            input_mapping={},
            state=PlanNodeState.PENDING,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
        )
        edge = PlanEdge(
            from_node="n1", to_node="n2", edge_type=EdgeType.DATA_DEPENDENCY
        )
        plan = self._make_plan(
            nodes={"n1": node},
            edges=[edge],
        )
        d = plan.to_dict()
        restored = Plan.from_dict(d)
        assert restored.plan_id == plan.plan_id
        assert restored.name == plan.name
        assert "n1" in restored.nodes
        assert len(restored.edges) == 1


# ---------------------------------------------------------------------------
# PlanEvent tests
# ---------------------------------------------------------------------------


class TestPlanEvent:
    """PlanEvent variants."""

    def test_node_ready(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_ready("n1")
        assert evt.tag == "NodeReady"
        assert evt.node_id == "n1"

    def test_node_started(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_started("n1", instance_id="inst_1")
        assert evt.tag == "NodeStarted"
        assert evt.node_id == "n1"
        assert evt.details["instance_id"] == "inst_1"

    def test_node_completed(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_completed("n1", output={"result": 42})
        assert evt.tag == "NodeCompleted"
        assert evt.details["output"] == {"result": 42}

    def test_node_failed(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_failed("n1", error="timeout", retryable=True)
        assert evt.tag == "NodeFailed"
        assert evt.details["error"] == "timeout"
        assert evt.details["retryable"] is True

    def test_node_retrying(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_retrying("n1", attempt=2, max_attempts=3)
        assert evt.tag == "NodeRetrying"
        assert evt.details["attempt"] == 2

    def test_node_held(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_held("n1", reason="retry exhausted", zone="HELD")
        assert evt.tag == "NodeHeld"

    def test_node_blocked(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_blocked("n1", dimension="financial", detail="over budget")
        assert evt.tag == "NodeBlocked"

    def test_node_skipped(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_skipped("n1", reason="optional failure")
        assert evt.tag == "NodeSkipped"

    def test_node_flagged(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.node_flagged("n1", reason="budget warning")
        assert evt.tag == "NodeFlagged"

    def test_plan_completed(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.plan_completed(results={"n1": {"result": 42}})
        assert evt.tag == "PlanCompleted"

    def test_plan_failed(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.plan_failed(failed_nodes=["n1"], reason="unrecoverable")
        assert evt.tag == "PlanFailed"
        assert evt.details["failed_nodes"] == ["n1"]

    def test_plan_suspended(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.plan_suspended()
        assert evt.tag == "PlanSuspended"

    def test_plan_resumed(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.plan_resumed()
        assert evt.tag == "PlanResumed"

    def test_plan_cancelled(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.plan_cancelled()
        assert evt.tag == "PlanCancelled"

    def test_envelope_warning(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.envelope_warning(
            node_id="n1", dimension="financial", usage_pct=0.85, zone="FLAGGED"
        )
        assert evt.tag == "EnvelopeWarning"
        assert evt.details["usage_pct"] == 0.85

    def test_modification_applied(self):
        from kaizen.l3.plan.types import PlanEvent

        evt = PlanEvent.modification_applied(modification={"type": "AddNode"})
        assert evt.tag == "ModificationApplied"


# ---------------------------------------------------------------------------
# PlanModification tests
# ---------------------------------------------------------------------------


class TestPlanModification:
    """PlanModification discriminated union variants."""

    def test_add_node(self):
        from kaizen.l3.plan.types import PlanModification, PlanNode, PlanNodeState

        node = PlanNode(
            node_id="new_node",
            agent_spec_id="spec_new",
            input_mapping={},
            state=PlanNodeState.PENDING,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
        )
        mod = PlanModification.add_node(node=node, edges=[])
        assert mod.tag == "AddNode"
        assert mod.details["node"].node_id == "new_node"

    def test_remove_node(self):
        from kaizen.l3.plan.types import PlanModification

        mod = PlanModification.remove_node(node_id="n1")
        assert mod.tag == "RemoveNode"
        assert mod.details["node_id"] == "n1"

    def test_replace_node(self):
        from kaizen.l3.plan.types import PlanModification, PlanNode, PlanNodeState

        new_node = PlanNode(
            node_id="replacement",
            agent_spec_id="spec_better",
            input_mapping={},
            state=PlanNodeState.PENDING,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
        )
        mod = PlanModification.replace_node(old_node_id="n1", new_node=new_node)
        assert mod.tag == "ReplaceNode"

    def test_add_edge(self):
        from kaizen.l3.plan.types import EdgeType, PlanEdge, PlanModification

        edge = PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY)
        mod = PlanModification.add_edge(edge=edge)
        assert mod.tag == "AddEdge"

    def test_remove_edge(self):
        from kaizen.l3.plan.types import PlanModification

        mod = PlanModification.remove_edge(from_node="a", to_node="b")
        assert mod.tag == "RemoveEdge"

    def test_update_spec(self):
        from kaizen.l3.plan.types import PlanModification

        mod = PlanModification.update_spec(node_id="n1", new_spec_id="spec_v2")
        assert mod.tag == "UpdateSpec"

    def test_skip_node(self):
        from kaizen.l3.plan.types import PlanModification

        mod = PlanModification.skip_node(node_id="n1", reason="not needed")
        assert mod.tag == "SkipNode"
        assert mod.details["reason"] == "not needed"

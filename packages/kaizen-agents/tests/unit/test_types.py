"""
Unit tests for kaizen_agents.types — verify type construction and validation.

These tests verify that all local type definitions correctly construct,
validate constraints, and implement discriminated union factory methods.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from kaizen_agents.types import (
    AgentInstance,
    AgentSpec,
    AgentState,
    AgentStateData,
    ClarificationPayload,
    CompletionPayload,
    ConstraintEnvelope,
    make_envelope,
    DelegationPayload,
    DimensionGradient,
    EdgeType,
    EscalationPayload,
    EscalationSeverity,
    GradientZone,
    L3Message,
    L3MessageType,
    MemoryConfig,
    Plan,
    PlanEdge,
    PlanEvent,
    PlanEventType,
    PlanGradient,
    PlanModification,
    PlanModificationType,
    PlanNode,
    PlanNodeOutput,
    PlanNodeState,
    PlanState,
    Priority,
    ResourceSnapshot,
    StatusPayload,
    SystemPayload,
    SystemSubtype,
    TerminationReason,
    WaitReason,
)


# ---------------------------------------------------------------------------
# GradientZone ordering
# ---------------------------------------------------------------------------


class TestGradientZone:
    def test_ordering_blocked_is_highest(self) -> None:
        assert GradientZone.BLOCKED > GradientZone.HELD
        assert GradientZone.HELD > GradientZone.FLAGGED
        assert GradientZone.FLAGGED > GradientZone.AUTO_APPROVED

    def test_ordering_auto_approved_is_lowest(self) -> None:
        assert not (GradientZone.AUTO_APPROVED > GradientZone.FLAGGED)

    def test_ge_same_zone(self) -> None:
        assert GradientZone.HELD >= GradientZone.HELD

    def test_ordering_returns_not_implemented_for_non_zone(self) -> None:
        result = GradientZone.HELD.__gt__("not_a_zone")
        assert result is NotImplemented

    def test_ge_returns_not_implemented_for_non_zone(self) -> None:
        result = GradientZone.HELD.__ge__("not_a_zone")
        assert result is NotImplemented


# ---------------------------------------------------------------------------
# DimensionGradient validation
# ---------------------------------------------------------------------------


class TestDimensionGradient:
    def test_valid_construction(self) -> None:
        dg = DimensionGradient(flag_threshold=0.7, hold_threshold=0.9)
        assert dg.flag_threshold == 0.7
        assert dg.hold_threshold == 0.9

    def test_default_values(self) -> None:
        dg = DimensionGradient()
        assert dg.flag_threshold == 0.80
        assert dg.hold_threshold == 0.95

    def test_invalid_flag_exceeds_hold_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid thresholds"):
            DimensionGradient(flag_threshold=0.95, hold_threshold=0.80)

    def test_equal_thresholds_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid thresholds"):
            DimensionGradient(flag_threshold=0.80, hold_threshold=0.80)

    def test_negative_flag_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid thresholds"):
            DimensionGradient(flag_threshold=-0.1, hold_threshold=0.5)

    def test_hold_exceeds_one_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid thresholds"):
            DimensionGradient(flag_threshold=0.5, hold_threshold=1.1)


# ---------------------------------------------------------------------------
# PlanGradient validation
# ---------------------------------------------------------------------------


class TestPlanGradient:
    def test_default_construction(self) -> None:
        pg = PlanGradient()
        assert pg.retry_budget == 2
        assert pg.after_retry_exhaustion == GradientZone.HELD
        assert pg.budget_flag_threshold == 0.80
        assert pg.budget_hold_threshold == 0.95

    def test_negative_retry_budget_raises(self) -> None:
        with pytest.raises(ValueError, match="retry_budget must be >= 0"):
            PlanGradient(retry_budget=-1)

    def test_invalid_after_retry_exhaustion_raises(self) -> None:
        with pytest.raises(ValueError, match="after_retry_exhaustion must be HELD or BLOCKED"):
            PlanGradient(after_retry_exhaustion=GradientZone.FLAGGED)

    def test_optional_node_failure_blocked_raises(self) -> None:
        with pytest.raises(ValueError, match="optional_node_failure cannot be BLOCKED"):
            PlanGradient(optional_node_failure=GradientZone.BLOCKED)

    def test_invalid_budget_thresholds_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid budget thresholds"):
            PlanGradient(budget_flag_threshold=0.95, budget_hold_threshold=0.80)

    def test_zero_resolution_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="resolution_timeout must be positive"):
            PlanGradient(resolution_timeout=timedelta(seconds=0))

    def test_custom_dimension_thresholds(self) -> None:
        pg = PlanGradient(
            dimension_thresholds={
                "financial": DimensionGradient(flag_threshold=0.6, hold_threshold=0.8)
            }
        )
        assert "financial" in pg.dimension_thresholds
        assert pg.dimension_thresholds["financial"].flag_threshold == 0.6


# ---------------------------------------------------------------------------
# ConstraintEnvelope
# ---------------------------------------------------------------------------


class TestConstraintEnvelope:
    def test_default_construction(self) -> None:
        ce = make_envelope()
        assert ce.financial is not None
        assert ce.financial.max_spend_usd == 1.0
        assert ce.operational.allowed_actions == []
        assert ce.operational.blocked_actions == []

    def test_custom_financial(self) -> None:
        ce = make_envelope(financial={"limit": 100.0})
        assert ce.financial is not None
        assert ce.financial.max_spend_usd == 100.0

    def test_custom_operational(self) -> None:
        ce = make_envelope(operational={"allowed": ["read", "write"], "blocked": ["delete"]})
        assert "read" in ce.operational.allowed_actions
        assert "delete" in ce.operational.blocked_actions


# ---------------------------------------------------------------------------
# Agent types
# ---------------------------------------------------------------------------


class TestAgentState:
    def test_terminal_states(self) -> None:
        assert AgentState.COMPLETED.is_terminal is True
        assert AgentState.FAILED.is_terminal is True
        assert AgentState.TERMINATED.is_terminal is True

    def test_non_terminal_states(self) -> None:
        assert AgentState.PENDING.is_terminal is False
        assert AgentState.RUNNING.is_terminal is False
        assert AgentState.WAITING.is_terminal is False


class TestAgentSpec:
    def test_minimal_construction(self) -> None:
        spec = AgentSpec(
            spec_id="test-001",
            name="Test Agent",
            description="A test agent.",
        )
        assert spec.spec_id == "test-001"
        assert spec.name == "Test Agent"
        assert spec.capabilities == []
        assert spec.tool_ids == []
        assert spec.max_lifetime is None
        assert spec.max_children is None
        assert spec.max_depth is None

    def test_full_construction(self) -> None:
        spec = AgentSpec(
            spec_id="full-001",
            name="Full Agent",
            description="An agent with all fields set.",
            capabilities=["code-review", "testing"],
            tool_ids=["file_read", "code_search"],
            envelope=make_envelope(financial={"limit": 5.0}),
            memory_config=MemoryConfig(session=True, shared=True, persistent=False),
            max_lifetime=timedelta(hours=1),
            max_children=10,
            max_depth=3,
            required_context_keys=["project_root"],
            produced_context_keys=["review_result"],
            metadata={"team": "backend"},
        )
        assert len(spec.capabilities) == 2
        assert spec.max_depth == 3
        assert spec.envelope.financial.max_spend_usd == 5.0
        assert spec.memory_config.shared is True

    def test_default_memory_config(self) -> None:
        spec = AgentSpec(spec_id="mem-001", name="M", description="D")
        assert spec.memory_config.session is True
        assert spec.memory_config.shared is False
        assert spec.memory_config.persistent is False


class TestAgentInstance:
    def test_default_construction(self) -> None:
        inst = AgentInstance()
        assert inst.state == AgentState.PENDING
        assert inst.parent_id is None
        assert inst.instance_id  # non-empty UUID string

    def test_instance_id_is_unique(self) -> None:
        inst1 = AgentInstance()
        inst2 = AgentInstance()
        assert inst1.instance_id != inst2.instance_id

    def test_custom_construction(self) -> None:
        inst = AgentInstance(
            instance_id="custom-id",
            spec_id="spec-001",
            parent_id="parent-001",
            state=AgentState.RUNNING,
        )
        assert inst.instance_id == "custom-id"
        assert inst.spec_id == "spec-001"
        assert inst.parent_id == "parent-001"
        assert inst.state == AgentState.RUNNING


# ---------------------------------------------------------------------------
# Plan DAG types
# ---------------------------------------------------------------------------


class TestPlanState:
    def test_terminal_states(self) -> None:
        assert PlanState.COMPLETED.is_terminal is True
        assert PlanState.FAILED.is_terminal is True
        assert PlanState.CANCELLED.is_terminal is True

    def test_non_terminal_states(self) -> None:
        assert PlanState.DRAFT.is_terminal is False
        assert PlanState.VALIDATED.is_terminal is False
        assert PlanState.EXECUTING.is_terminal is False
        assert PlanState.SUSPENDED.is_terminal is False


class TestPlanNodeState:
    def test_terminal_states(self) -> None:
        assert PlanNodeState.COMPLETED.is_terminal is True
        assert PlanNodeState.FAILED.is_terminal is True
        assert PlanNodeState.SKIPPED.is_terminal is True

    def test_non_terminal_states(self) -> None:
        assert PlanNodeState.PENDING.is_terminal is False
        assert PlanNodeState.READY.is_terminal is False
        assert PlanNodeState.RUNNING.is_terminal is False


class TestPlanNode:
    def test_construction(self) -> None:
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        node = PlanNode(node_id="n1", agent_spec=spec)
        assert node.node_id == "n1"
        assert node.state == PlanNodeState.PENDING
        assert node.instance_id is None
        assert node.optional is False
        assert node.retry_count == 0

    def test_input_mapping(self) -> None:
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        node = PlanNode(
            node_id="n2",
            agent_spec=spec,
            input_mapping={"data": PlanNodeOutput(source_node="n1", output_key="result")},
        )
        assert "data" in node.input_mapping
        assert node.input_mapping["data"].source_node == "n1"


class TestPlanEdge:
    def test_data_dependency(self) -> None:
        edge = PlanEdge(from_node="a", to_node="b", edge_type=EdgeType.DATA_DEPENDENCY)
        assert edge.from_node == "a"
        assert edge.to_node == "b"
        assert edge.edge_type == EdgeType.DATA_DEPENDENCY

    def test_default_edge_type(self) -> None:
        edge = PlanEdge(from_node="a", to_node="b")
        assert edge.edge_type == EdgeType.DATA_DEPENDENCY


class TestPlan:
    def test_default_construction(self) -> None:
        plan = Plan()
        assert plan.state == PlanState.DRAFT
        assert plan.nodes == {}
        assert plan.edges == []
        assert plan.plan_id  # non-empty

    def test_plan_with_nodes_and_edges(self) -> None:
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        plan = Plan(
            name="Test Plan",
            nodes={
                "a": PlanNode(node_id="a", agent_spec=spec),
                "b": PlanNode(node_id="b", agent_spec=spec),
            },
            edges=[PlanEdge(from_node="a", to_node="b")],
        )
        assert len(plan.nodes) == 2
        assert len(plan.edges) == 1


# ---------------------------------------------------------------------------
# PlanModification factory methods
# ---------------------------------------------------------------------------


class TestPlanModification:
    def test_add_node(self) -> None:
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        node = PlanNode(node_id="n1", agent_spec=spec)
        mod = PlanModification.add_node(node)
        assert mod.modification_type == PlanModificationType.ADD_NODE
        assert mod.node is node
        assert mod.edges == []

    def test_add_node_with_edges(self) -> None:
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        node = PlanNode(node_id="n2", agent_spec=spec)
        edge = PlanEdge(from_node="n1", to_node="n2")
        mod = PlanModification.add_node(node, edges=[edge])
        assert len(mod.edges) == 1

    def test_remove_node(self) -> None:
        mod = PlanModification.remove_node("n1")
        assert mod.modification_type == PlanModificationType.REMOVE_NODE
        assert mod.node_id == "n1"

    def test_replace_node(self) -> None:
        spec = AgentSpec(spec_id="s2", name="N2", description="D2")
        node = PlanNode(node_id="n2", agent_spec=spec)
        mod = PlanModification.replace_node("n1", node)
        assert mod.modification_type == PlanModificationType.REPLACE_NODE
        assert mod.old_node_id == "n1"
        assert mod.new_node is node

    def test_add_edge(self) -> None:
        edge = PlanEdge(from_node="a", to_node="b")
        mod = PlanModification.add_edge(edge)
        assert mod.modification_type == PlanModificationType.ADD_EDGE
        assert mod.edge is edge

    def test_remove_edge(self) -> None:
        mod = PlanModification.remove_edge("a", "b")
        assert mod.modification_type == PlanModificationType.REMOVE_EDGE
        assert mod.from_node == "a"
        assert mod.to_node == "b"

    def test_update_spec(self) -> None:
        spec = AgentSpec(spec_id="s2", name="N2", description="D2")
        mod = PlanModification.update_spec("n1", spec)
        assert mod.modification_type == PlanModificationType.UPDATE_SPEC
        assert mod.node_id == "n1"
        assert mod.new_spec is spec

    def test_skip_node(self) -> None:
        mod = PlanModification.skip_node("n1", "Not needed")
        assert mod.modification_type == PlanModificationType.SKIP_NODE
        assert mod.node_id == "n1"
        assert mod.reason == "Not needed"


# ---------------------------------------------------------------------------
# PlanEvent
# ---------------------------------------------------------------------------


class TestPlanEvent:
    def test_node_ready_event(self) -> None:
        event = PlanEvent(event_type=PlanEventType.NODE_READY, node_id="n1")
        assert event.event_type == PlanEventType.NODE_READY
        assert event.node_id == "n1"
        assert event.timestamp is not None

    def test_plan_completed_event(self) -> None:
        event = PlanEvent(
            event_type=PlanEventType.PLAN_COMPLETED,
            results={"n1": {"status": "ok"}},
        )
        assert event.results is not None
        assert "n1" in event.results

    def test_envelope_warning_event(self) -> None:
        event = PlanEvent(
            event_type=PlanEventType.ENVELOPE_WARNING,
            node_id="n1",
            dimension="financial",
            usage_pct=0.85,
            zone=GradientZone.FLAGGED,
        )
        assert event.dimension == "financial"
        assert event.usage_pct == 0.85
        assert event.zone == GradientZone.FLAGGED


# ---------------------------------------------------------------------------
# L3 Message variants
# ---------------------------------------------------------------------------


class TestL3Message:
    def test_create_delegation(self) -> None:
        payload = DelegationPayload(
            task_description="Review the PR",
            priority=Priority.HIGH,
        )
        msg = L3Message.create_delegation("parent-1", "child-1", payload)
        assert msg.message_type == L3MessageType.DELEGATION
        assert msg.delegation is payload
        assert msg.from_instance == "parent-1"
        assert msg.to_instance == "child-1"

    def test_create_status(self) -> None:
        payload = StatusPayload(
            phase="analyzing",
            progress_pct=0.5,
            resource_usage=ResourceSnapshot(financial_spent=1.25, actions_executed=10),
        )
        msg = L3Message.create_status("child-1", "parent-1", payload)
        assert msg.message_type == L3MessageType.STATUS
        assert msg.status is payload
        assert msg.status.progress_pct == 0.5

    def test_create_clarification(self) -> None:
        payload = ClarificationPayload(
            question="Which branch should I target?",
            options=["main", "develop"],
            blocking=True,
            is_response=False,
        )
        msg = L3Message.create_clarification("child-1", "parent-1", payload)
        assert msg.message_type == L3MessageType.CLARIFICATION
        assert msg.clarification.blocking is True
        assert len(msg.clarification.options) == 2

    def test_create_completion(self) -> None:
        payload = CompletionPayload(
            result={"files_reviewed": 3, "issues_found": 1},
            success=True,
            context_updates={"review_status": "done"},
            resource_consumed=ResourceSnapshot(financial_spent=2.0),
        )
        msg = L3Message.create_completion("child-1", "parent-1", payload)
        assert msg.message_type == L3MessageType.COMPLETION
        assert msg.completion.success is True
        assert msg.completion.result["files_reviewed"] == 3

    def test_create_escalation(self) -> None:
        payload = EscalationPayload(
            severity=EscalationSeverity.CRITICAL,
            problem_description="Rate limit exceeded",
            attempted_mitigations=["Waited 60s", "Reduced batch size"],
            violating_dimension="operational",
        )
        msg = L3Message.create_escalation("child-1", "parent-1", payload)
        assert msg.message_type == L3MessageType.ESCALATION
        assert msg.escalation.severity == EscalationSeverity.CRITICAL
        assert len(msg.escalation.attempted_mitigations) == 2

    def test_create_system(self) -> None:
        payload = SystemPayload(
            subtype=SystemSubtype.TERMINATION_NOTICE,
            reason="Parent terminated",
        )
        msg = L3Message.create_system("system", "child-1", payload)
        assert msg.message_type == L3MessageType.SYSTEM
        assert msg.system.subtype == SystemSubtype.TERMINATION_NOTICE

    def test_message_id_is_unique(self) -> None:
        p = StatusPayload(phase="test")
        msg1 = L3Message.create_status("a", "b", p)
        msg2 = L3Message.create_status("a", "b", p)
        assert msg1.message_id != msg2.message_id

    def test_correlation_id(self) -> None:
        payload = ClarificationPayload(
            question="Answer to your question",
            blocking=False,
            is_response=True,
        )
        original_id = str(uuid.uuid4())
        msg = L3Message.create_clarification(
            "parent-1", "child-1", payload, correlation_id=original_id
        )
        assert msg.correlation_id == original_id


# ---------------------------------------------------------------------------
# Enums — basic coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_wait_reason_values(self) -> None:
        assert WaitReason.DELEGATION_RESPONSE.value == "delegation_response"
        assert WaitReason.HUMAN_APPROVAL.value == "human_approval"
        assert WaitReason.RESOURCE_AVAILABILITY.value == "resource_availability"

    def test_termination_reason_values(self) -> None:
        assert TerminationReason.PARENT_TERMINATED.value == "parent_terminated"
        assert TerminationReason.TIMEOUT.value == "timeout"

    def test_edge_type_values(self) -> None:
        assert EdgeType.DATA_DEPENDENCY.value == "data_dependency"
        assert EdgeType.COMPLETION_DEPENDENCY.value == "completion_dependency"
        assert EdgeType.CO_START.value == "co_start"

    def test_priority_values(self) -> None:
        assert Priority.LOW.value == 0
        assert Priority.NORMAL.value == 1
        assert Priority.HIGH.value == 2
        assert Priority.CRITICAL.value == 3

    def test_escalation_severity(self) -> None:
        assert EscalationSeverity.WARNING.value == "warning"
        assert EscalationSeverity.CRITICAL.value == "critical"
        assert EscalationSeverity.BUDGET_ALERT.value == "budget_alert"


# ---------------------------------------------------------------------------
# AgentStateData
# ---------------------------------------------------------------------------


class TestAgentStateData:
    def test_default_all_none(self) -> None:
        data = AgentStateData()
        assert data.reason is None
        assert data.result is None
        assert data.error is None
        assert data.wait_reason is None

    def test_with_termination_info(self) -> None:
        data = AgentStateData(
            termination_reason=TerminationReason.ENVELOPE_VIOLATION,
            dimension="financial",
            detail="Exceeded $10.00 limit",
        )
        assert data.termination_reason == TerminationReason.ENVELOPE_VIOLATION
        assert data.dimension == "financial"

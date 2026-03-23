"""
Unit tests for kaizen_agents.monitor -- PlanMonitor.

Uses mocked LLM and mocked execute_node callback (Tier 1 -- unit tests
may mock external services). Tests the full L3 orchestration loop including
decompose -> design -> compose -> execute -> monitor -> recover.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.monitor import PlanMonitor, PlanResult
from kaizen_agents.orchestration.planner.designer import SpawnDecision
from kaizen_agents.orchestration.recovery.diagnoser import FailureCategory
from kaizen_agents.orchestration.recovery.recomposer import RecoveryStrategy
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    GradientZone,
    Plan,
    PlanEdge,
    PlanEventType,
    PlanGradient,
    PlanModification,
    PlanNode,
    PlanNodeState,
    PlanState,
)


# ---------------------------------------------------------------------------
# Helpers -- mock LLM client and agent specs
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_responses: list[dict[str, Any]] | None = None) -> LLMClient:
    """Create a mock LLMClient with optional sequenced structured responses.

    If structured_responses is provided, each call to complete_structured
    returns the next response in the list. If not provided, returns a
    default empty dict.
    """
    mock = MagicMock(spec=LLMClient)
    if structured_responses:
        mock.complete_structured.side_effect = list(structured_responses)
    else:
        mock.complete_structured.return_value = {}
    return mock


def _make_agent_spec(
    name: str = "test-agent",
    description: str = "A test agent",
    capabilities: list[str] | None = None,
    tool_ids: list[str] | None = None,
) -> AgentSpec:
    """Create an AgentSpec with sensible defaults for testing."""
    return AgentSpec(
        spec_id=f"spec-{name}",
        name=name,
        description=description,
        capabilities=capabilities or [],
        tool_ids=tool_ids or [],
    )


def _make_single_node_plan(
    optional: bool = False,
    budget_limit: float = 10.0,
) -> Plan:
    """Build a plan with a single node -- the simplest possible plan."""
    spec = _make_agent_spec(name="solo-agent", description="The only agent")
    node = PlanNode(
        node_id="node-0",
        agent_spec=spec,
        state=PlanNodeState.PENDING,
        optional=optional,
    )
    return Plan(
        plan_id="single-node-plan",
        name="Single Node Plan",
        nodes={"node-0": node},
        edges=[],
        state=PlanState.VALIDATED,
        envelope=ConstraintEnvelope(financial={"limit": budget_limit}),
        gradient=PlanGradient(retry_budget=2),
    )


def _make_three_node_linear_plan(
    budget_limit: float = 10.0,
) -> Plan:
    """Build a three-node linear plan: node-0 -> node-1 -> node-2.

    All nodes are required (not optional). Each produces output consumed
    by the next.
    """
    specs = [
        _make_agent_spec(name="gather", description="Gather data"),
        _make_agent_spec(name="analyze", description="Analyze data"),
        _make_agent_spec(name="report", description="Generate report"),
    ]
    nodes = {
        f"node-{i}": PlanNode(
            node_id=f"node-{i}",
            agent_spec=specs[i],
            state=PlanNodeState.PENDING,
        )
        for i in range(3)
    }
    edges = [
        PlanEdge(from_node="node-0", to_node="node-1", edge_type=EdgeType.DATA_DEPENDENCY),
        PlanEdge(from_node="node-1", to_node="node-2", edge_type=EdgeType.DATA_DEPENDENCY),
    ]
    return Plan(
        plan_id="three-node-plan",
        name="Three Node Linear Plan",
        nodes=nodes,
        edges=edges,
        state=PlanState.VALIDATED,
        envelope=ConstraintEnvelope(financial={"limit": budget_limit}),
        gradient=PlanGradient(retry_budget=2),
    )


def _make_diamond_plan(
    budget_limit: float = 10.0,
) -> Plan:
    """Build a diamond plan: node-0 -> (node-1, node-2) -> node-3.

    node-1 and node-2 can execute in parallel. node-3 depends on both.
    """
    specs = [
        _make_agent_spec(name="start", description="Starting point"),
        _make_agent_spec(name="branch-a", description="Branch A"),
        _make_agent_spec(name="branch-b", description="Branch B"),
        _make_agent_spec(name="merge", description="Merge results"),
    ]
    nodes = {
        f"node-{i}": PlanNode(
            node_id=f"node-{i}",
            agent_spec=specs[i],
            state=PlanNodeState.PENDING,
        )
        for i in range(4)
    }
    edges = [
        PlanEdge(from_node="node-0", to_node="node-1", edge_type=EdgeType.DATA_DEPENDENCY),
        PlanEdge(from_node="node-0", to_node="node-2", edge_type=EdgeType.DATA_DEPENDENCY),
        PlanEdge(from_node="node-1", to_node="node-3", edge_type=EdgeType.DATA_DEPENDENCY),
        PlanEdge(from_node="node-2", to_node="node-3", edge_type=EdgeType.DATA_DEPENDENCY),
    ]
    return Plan(
        plan_id="diamond-plan",
        name="Diamond Plan",
        nodes=nodes,
        edges=edges,
        state=PlanState.VALIDATED,
        envelope=ConstraintEnvelope(financial={"limit": budget_limit}),
        gradient=PlanGradient(retry_budget=2),
    )


# ---------------------------------------------------------------------------
# PlanResult dataclass
# ---------------------------------------------------------------------------


class TestPlanResult:
    def test_construction(self) -> None:
        plan = _make_single_node_plan()
        pr = PlanResult(
            plan=plan,
            results={"node-0": "output"},
            events=[],
            modifications_applied=[],
            total_cost=0.5,
            success=True,
        )
        assert pr.success is True
        assert pr.total_cost == 0.5
        assert pr.results == {"node-0": "output"}

    def test_defaults(self) -> None:
        plan = _make_single_node_plan()
        pr = PlanResult(plan=plan)
        assert pr.results == {}
        assert pr.events == []
        assert pr.modifications_applied == []
        assert pr.total_cost == 0.0
        assert pr.success is False


# ---------------------------------------------------------------------------
# PlanMonitor.run_plan -- single-node plan succeeds
# ---------------------------------------------------------------------------


class TestSingleNodePlanSuccess:
    @pytest.mark.asyncio
    async def test_single_node_success(self) -> None:
        """A single-node plan where execution succeeds produces a successful PlanResult."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()

        async def execute_success(spec: AgentSpec, inputs: dict) -> dict:
            return {"result": "task completed", "cost": 0.05}

        result = await monitor.run_plan(plan=plan, execute_node=execute_success)

        assert result.success is True
        assert result.results.get("node-0") == "task completed"
        assert result.total_cost == pytest.approx(0.05)
        assert plan.state == PlanState.COMPLETED

        # Check events include start, completed, plan_completed
        event_types = [e.event_type for e in result.events]
        assert PlanEventType.NODE_STARTED in event_types
        assert PlanEventType.NODE_COMPLETED in event_types
        assert PlanEventType.PLAN_COMPLETED in event_types

    @pytest.mark.asyncio
    async def test_single_node_with_no_cost(self) -> None:
        """A node that does not report cost still succeeds; cost stays at zero."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()

        async def execute_no_cost(spec: AgentSpec, inputs: dict) -> dict:
            return {"result": "done"}

        result = await monitor.run_plan(plan=plan, execute_node=execute_no_cost)

        assert result.success is True
        assert result.total_cost == 0.0


# ---------------------------------------------------------------------------
# PlanMonitor.run_plan -- multi-node plan with dependencies executes in order
# ---------------------------------------------------------------------------


class TestMultiNodePlanDependencyOrder:
    @pytest.mark.asyncio
    async def test_linear_plan_executes_in_order(self) -> None:
        """A three-node linear plan executes nodes in dependency order."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()
        execution_order: list[str] = []

        async def execute_tracking(spec: AgentSpec, inputs: dict) -> dict:
            execution_order.append(spec.name)
            return {"result": f"output-from-{spec.name}", "cost": 0.01}

        result = await monitor.run_plan(plan=plan, execute_node=execute_tracking)

        assert result.success is True
        assert len(result.results) == 3
        # Execution must respect dependency order
        assert execution_order == ["gather", "analyze", "report"]

    @pytest.mark.asyncio
    async def test_diamond_plan_respects_merge_point(self) -> None:
        """A diamond plan runs parallel branches before the merge node."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_diamond_plan()
        execution_order: list[str] = []

        async def execute_tracking(spec: AgentSpec, inputs: dict) -> dict:
            execution_order.append(spec.name)
            return {"result": f"output-from-{spec.name}", "cost": 0.01}

        result = await monitor.run_plan(plan=plan, execute_node=execute_tracking)

        assert result.success is True
        assert len(result.results) == 4

        # start must be first; merge must be last
        assert execution_order[0] == "start"
        assert execution_order[-1] == "merge"
        # branch-a and branch-b must both appear before merge
        assert "branch-a" in execution_order[1:-1]
        assert "branch-b" in execution_order[1:-1]

    @pytest.mark.asyncio
    async def test_cumulative_cost_tracking(self) -> None:
        """Costs from all nodes accumulate in total_cost."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()

        async def execute_with_cost(spec: AgentSpec, inputs: dict) -> dict:
            return {"result": "ok", "cost": 0.10}

        result = await monitor.run_plan(plan=plan, execute_node=execute_with_cost)

        assert result.success is True
        assert result.total_cost == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# PlanMonitor.run_plan -- node failure triggers diagnosis and recomposition
# ---------------------------------------------------------------------------


class TestNodeFailureRecovery:
    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self) -> None:
        """A transient failure within retry budget gets auto-retried."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        call_count = 0

        async def execute_fail_then_succeed(spec: AgentSpec, inputs: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": "Transient network timeout", "cost": 0.01}
            return {"result": "success on retry", "cost": 0.01}

        result = await monitor.run_plan(plan=plan, execute_node=execute_fail_then_succeed)

        assert result.success is True
        assert call_count == 2
        assert result.results.get("node-0") == "success on retry"

        # Should have a RETRYING event
        event_types = [e.event_type for e in result.events]
        assert PlanEventType.NODE_RETRYING in event_types

    @pytest.mark.asyncio
    async def test_held_event_triggers_diagnosis_and_recomposition(self) -> None:
        """When retries are exhausted, the monitor diagnoses and recomposes.

        Mock the diagnoser to return a SKIP-able diagnosis and the recomposer
        to return a SKIP recovery. Since the node is optional, skip succeeds.
        """
        # The LLM will be called by:
        #   1. FailureDiagnoser.diagnose (structured output)
        #   2. Recomposer.recompose (structured output)
        diagnosis_response = {
            "root_cause": "API endpoint permanently moved",
            "category": "permanent",
            "recoverable": False,
            "suggested_actions": ["Skip this optional step"],
            "confidence": 0.9,
        }
        recovery_response = {
            "strategy": "skip",
            "rationale": "Node is optional; skipping to continue plan",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": "Optional analysis not critical",
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(
            retry_budget=0,
            optional_node_failure=GradientZone.HELD,  # Force held so recovery runs
        )
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan(optional=True)

        async def execute_fail(spec: AgentSpec, inputs: dict) -> dict:
            return {"error": "API endpoint permanently moved"}

        result = await monitor.run_plan(plan=plan, execute_node=execute_fail)

        # The optional node was skipped via recovery, so plan succeeds
        assert result.success is True
        assert len(result.modifications_applied) > 0

        event_types = [e.event_type for e in result.events]
        assert PlanEventType.NODE_HELD in event_types
        assert PlanEventType.MODIFICATION_APPLIED in event_types

    @pytest.mark.asyncio
    async def test_recovery_with_replace_strategy(self) -> None:
        """When the recomposer selects REPLACE, the failed node is replaced
        and the replacement node can execute."""
        diagnosis_response = {
            "root_cause": "Agent lacks required capability",
            "category": "configuration",
            "recoverable": True,
            "suggested_actions": ["Replace with better-equipped agent"],
            "confidence": 0.85,
        }
        recovery_response = {
            "strategy": "replace",
            "rationale": "Replacing with an agent that has the correct tools",
            "replacement_spec": {
                "name": "replacement-agent",
                "description": "Agent with correct capabilities",
                "capabilities": ["correct-capability"],
                "tool_ids": ["correct-tool"],
            },
            "alternative_nodes": None,
            "skip_reason": None,
        }
        # Diagnoser + Recomposer = 2 LLM calls for first failure.
        # After replace, the new node runs and we need no more LLM calls.
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=0)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        call_count = 0

        async def execute_fail_then_succeed(spec: AgentSpec, inputs: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if spec.name == "solo-agent":
                return {"error": "Missing capability"}
            return {"result": "replacement succeeded", "cost": 0.02}

        result = await monitor.run_plan(plan=plan, execute_node=execute_fail_then_succeed)

        assert result.success is True
        assert len(result.modifications_applied) > 0

    @pytest.mark.asyncio
    async def test_recovery_with_retry_strategy(self) -> None:
        """When the recomposer selects RETRY, the held node is reset to READY."""
        diagnosis_response = {
            "root_cause": "Transient rate limit",
            "category": "transient",
            "recoverable": True,
            "suggested_actions": ["Retry the operation"],
            "confidence": 0.95,
        }
        recovery_response = {
            "strategy": "retry",
            "rationale": "Transient failure, retry should succeed",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": None,
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=0)  # 0 retries so it goes to HELD
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        call_count = 0

        async def execute_fail_then_succeed(spec: AgentSpec, inputs: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": "Rate limit exceeded"}
            return {"result": "success after recovery retry", "cost": 0.01}

        result = await monitor.run_plan(plan=plan, execute_node=execute_fail_then_succeed)

        assert result.success is True
        assert call_count == 2


# ---------------------------------------------------------------------------
# PlanMonitor.run_plan -- budget exhaustion triggers held event
# ---------------------------------------------------------------------------


class TestBudgetExhaustion:
    @pytest.mark.asyncio
    async def test_budget_flag_threshold_emits_warning(self) -> None:
        """When cost exceeds the flag threshold, an ENVELOPE_WARNING is emitted
        but execution continues."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 1.0})
        gradient = PlanGradient(
            retry_budget=0,
            budget_flag_threshold=0.50,
            budget_hold_threshold=0.95,
        )
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan(budget_limit=1.0)
        plan.gradient = gradient

        async def execute_expensive(spec: AgentSpec, inputs: dict) -> dict:
            return {"result": "ok", "cost": 0.30}

        result = await monitor.run_plan(plan=plan, execute_node=execute_expensive)

        assert result.success is True
        event_types = [e.event_type for e in result.events]
        # After the first node costs 0.30 (30%), the second starts at 0.30 which is
        # below flag (50%). After second node, total is 0.60 (60%) which is above flag.
        # Third node should see a flag warning.
        assert PlanEventType.ENVELOPE_WARNING in event_types

    @pytest.mark.asyncio
    async def test_budget_hold_threshold_triggers_held(self) -> None:
        """When cost reaches the hold threshold, nodes get held."""
        # Diagnoser + Recomposer responses for held budget event
        diagnosis_response = {
            "root_cause": "Budget nearly exhausted",
            "category": "resource",
            "recoverable": False,
            "suggested_actions": ["Abort remaining tasks"],
            "confidence": 0.9,
        }
        recovery_response = {
            "strategy": "abort",
            "rationale": "Budget too low to continue",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": None,
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 1.0})
        gradient = PlanGradient(
            retry_budget=0,
            budget_flag_threshold=0.50,
            budget_hold_threshold=0.90,
        )
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan(budget_limit=1.0)
        plan.gradient = gradient

        async def execute_very_expensive(spec: AgentSpec, inputs: dict) -> dict:
            return {"result": "ok", "cost": 0.50}

        result = await monitor.run_plan(plan=plan, execute_node=execute_very_expensive)

        # After first node: 0.50 (50% of 1.0) -> second node starts.
        # After second node: 1.00 (100%) -> third node should be held (above hold threshold 90%).
        # Recovery aborts -> plan fails because the third node is required.
        event_types = [e.event_type for e in result.events]
        assert PlanEventType.NODE_HELD in event_types or PlanEventType.NODE_BLOCKED in event_types


# ---------------------------------------------------------------------------
# PlanMonitor.run_plan -- all nodes fail -> PlanResult.success = False
# ---------------------------------------------------------------------------


class TestAllNodesFail:
    @pytest.mark.asyncio
    async def test_all_nodes_fail_plan_fails(self) -> None:
        """When all required nodes fail and recovery aborts, the plan fails."""
        diagnosis_response = {
            "root_cause": "Fundamental inability to complete the task",
            "category": "permanent",
            "recoverable": False,
            "suggested_actions": [],
            "confidence": 0.9,
        }
        recovery_response = {
            "strategy": "abort",
            "rationale": "Unrecoverable failure",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": None,
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=0)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()

        async def execute_always_fail(spec: AgentSpec, inputs: dict) -> dict:
            return {"error": "Permanent failure"}

        result = await monitor.run_plan(plan=plan, execute_node=execute_always_fail)

        assert result.success is False
        assert plan.state == PlanState.FAILED

        event_types = [e.event_type for e in result.events]
        assert PlanEventType.PLAN_FAILED in event_types

    @pytest.mark.asyncio
    async def test_cascade_failure_to_downstream(self) -> None:
        """When a required node fails and recovery aborts, downstream nodes
        are cascaded to FAILED."""
        diagnosis_response = {
            "root_cause": "Cannot analyze without data",
            "category": "permanent",
            "recoverable": False,
            "suggested_actions": [],
            "confidence": 0.9,
        }
        recovery_response = {
            "strategy": "abort",
            "rationale": "Unrecoverable",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": None,
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=0)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()
        call_count = 0

        async def execute_first_fails(spec: AgentSpec, inputs: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if spec.name == "gather":
                return {"error": "Data source unavailable"}
            return {"result": "ok"}

        result = await monitor.run_plan(plan=plan, execute_node=execute_first_fails)

        assert result.success is False
        # Only the first node should have been called
        assert call_count == 1
        # Downstream nodes should be FAILED via cascade
        assert plan.nodes["node-1"].state == PlanNodeState.FAILED
        assert plan.nodes["node-2"].state == PlanNodeState.FAILED

    @pytest.mark.asyncio
    async def test_multiple_retries_then_fail(self) -> None:
        """A node that fails repeatedly exhausts its retry budget then gets held,
        and if recovery aborts, the plan fails."""
        diagnosis_response = {
            "root_cause": "Persistent service outage",
            "category": "permanent",
            "recoverable": False,
            "suggested_actions": [],
            "confidence": 0.9,
        }
        recovery_response = {
            "strategy": "abort",
            "rationale": "Service permanently down",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": None,
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        call_count = 0

        async def execute_always_fail(spec: AgentSpec, inputs: dict) -> dict:
            nonlocal call_count
            call_count += 1
            return {"error": "Service unavailable"}

        result = await monitor.run_plan(plan=plan, execute_node=execute_always_fail)

        assert result.success is False
        # 1 initial call + 2 retries + 0 more (held -> abort) = 3 calls
        assert call_count == 3

        event_types = [e.event_type for e in result.events]
        assert PlanEventType.NODE_RETRYING in event_types
        assert PlanEventType.NODE_HELD in event_types


# ---------------------------------------------------------------------------
# PlanMonitor.run_plan -- optional node failures
# ---------------------------------------------------------------------------


class TestOptionalNodeFailures:
    @pytest.mark.asyncio
    async def test_optional_node_failure_is_flagged_and_skipped(self) -> None:
        """An optional node that fails with retries exhausted gets flagged
        and the plan continues."""
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(
            retry_budget=0,
            optional_node_failure=GradientZone.FLAGGED,
        )
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan(optional=True)

        async def execute_fail(spec: AgentSpec, inputs: dict) -> dict:
            return {"error": "Optional step failed"}

        result = await monitor.run_plan(plan=plan, execute_node=execute_fail)

        # Optional node failed and was flagged/skipped, plan still succeeds
        assert result.success is True
        event_types = [e.event_type for e in result.events]
        assert PlanEventType.NODE_FLAGGED in event_types


# ---------------------------------------------------------------------------
# PlanMonitor -- internal helper tests
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_evaluate_plan_success_all_completed(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        plan.nodes["node-0"].state = PlanNodeState.COMPLETED

        assert monitor._evaluate_plan_success(plan) is True

    def test_evaluate_plan_success_required_node_failed(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        plan.nodes["node-0"].state = PlanNodeState.FAILED

        assert monitor._evaluate_plan_success(plan) is False

    def test_evaluate_plan_success_optional_node_failed_ok(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan(optional=True)
        plan.nodes["node-0"].state = PlanNodeState.FAILED

        # Optional nodes are excluded from the success check entirely.
        # A failed optional node does not block plan success -- it is optional.
        assert monitor._evaluate_plan_success(plan) is True

    def test_evaluate_plan_success_optional_node_skipped_ok(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan(optional=True)
        plan.nodes["node-0"].state = PlanNodeState.SKIPPED

        assert monitor._evaluate_plan_success(plan) is True

    def test_classify_failure_with_retries_remaining(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient(retry_budget=2)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        node = plan.nodes["node-0"]
        node.retry_count = 0

        assert monitor._classify_failure(plan, node) == GradientZone.AUTO_APPROVED

    def test_classify_failure_retries_exhausted_required(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient(retry_budget=2, after_retry_exhaustion=GradientZone.HELD)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        plan.gradient = gradient
        node = plan.nodes["node-0"]
        node.retry_count = 2

        assert monitor._classify_failure(plan, node) == GradientZone.HELD

    def test_classify_failure_retries_exhausted_optional(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient(
            retry_budget=1,
            optional_node_failure=GradientZone.FLAGGED,
        )
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan(optional=True)
        plan.gradient = gradient
        node = plan.nodes["node-0"]
        node.retry_count = 1
        node.optional = True

        assert monitor._classify_failure(plan, node) == GradientZone.FLAGGED

    def test_check_budget_auto_approved(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.95)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        assert monitor._check_budget(1.0) == GradientZone.AUTO_APPROVED

    def test_check_budget_flagged(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.95)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        assert monitor._check_budget(8.5) == GradientZone.FLAGGED

    def test_check_budget_held(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.95)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        assert monitor._check_budget(9.6) == GradientZone.HELD

    def test_check_budget_blocked(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(budget_flag_threshold=0.80, budget_hold_threshold=0.95)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        assert monitor._check_budget(10.0) == GradientZone.BLOCKED

    def test_resolve_inputs_from_dict_output(self) -> None:
        from kaizen_agents.types import PlanNodeOutput

        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        spec = _make_agent_spec()
        node = PlanNode(
            node_id="consumer",
            agent_spec=spec,
            input_mapping={
                "input_data": PlanNodeOutput(source_node="producer", output_key="data"),
            },
        )
        node_outputs = {"producer": {"data": "hello", "extra": "world"}}

        resolved = monitor._resolve_inputs(node, node_outputs)
        assert resolved == {"input_data": "hello"}

    def test_resolve_inputs_from_non_dict_output(self) -> None:
        from kaizen_agents.types import PlanNodeOutput

        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        spec = _make_agent_spec()
        node = PlanNode(
            node_id="consumer",
            agent_spec=spec,
            input_mapping={
                "input_data": PlanNodeOutput(source_node="producer", output_key="data"),
            },
        )
        node_outputs = {"producer": "raw string output"}

        resolved = monitor._resolve_inputs(node, node_outputs)
        assert resolved == {"input_data": "raw string output"}

    def test_resolve_inputs_missing_source(self) -> None:
        from kaizen_agents.types import PlanNodeOutput

        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        spec = _make_agent_spec()
        node = PlanNode(
            node_id="consumer",
            agent_spec=spec,
            input_mapping={
                "input_data": PlanNodeOutput(source_node="missing", output_key="data"),
            },
        )
        node_outputs = {}

        resolved = monitor._resolve_inputs(node, node_outputs)
        assert resolved == {"input_data": None}


# ---------------------------------------------------------------------------
# PlanMonitor -- apply_modification
# ---------------------------------------------------------------------------


class TestApplyModification:
    def test_add_node(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        new_spec = _make_agent_spec(name="new-agent")
        new_node = PlanNode(node_id="node-new", agent_spec=new_spec)
        new_edge = PlanEdge(from_node="node-0", to_node="node-new")
        mod = PlanModification.add_node(new_node, [new_edge])

        monitor._apply_modification(plan, mod)

        assert "node-new" in plan.nodes
        assert any(e.to_node == "node-new" for e in plan.edges)

    def test_remove_node(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()
        mod = PlanModification.remove_node("node-1")

        monitor._apply_modification(plan, mod)

        assert "node-1" not in plan.nodes
        # Edges involving node-1 should be removed
        for edge in plan.edges:
            assert edge.from_node != "node-1"
            assert edge.to_node != "node-1"

    def test_replace_node(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()
        new_spec = _make_agent_spec(name="replacement")
        new_node = PlanNode(node_id="node-replacement", agent_spec=new_spec)
        mod = PlanModification.replace_node("node-1", new_node)

        monitor._apply_modification(plan, mod)

        assert "node-1" not in plan.nodes
        assert "node-replacement" in plan.nodes
        # Edges should be rewired
        assert any(e.from_node == "node-0" and e.to_node == "node-replacement" for e in plan.edges)
        assert any(e.from_node == "node-replacement" and e.to_node == "node-2" for e in plan.edges)

    def test_skip_node(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        mod = PlanModification.skip_node("node-0", "Not needed")

        monitor._apply_modification(plan, mod)

        assert plan.nodes["node-0"].state == PlanNodeState.SKIPPED

    def test_update_spec(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()
        new_spec = _make_agent_spec(name="updated-agent", description="Updated description")
        mod = PlanModification.update_spec("node-0", new_spec)

        monitor._apply_modification(plan, mod)

        assert plan.nodes["node-0"].agent_spec.name == "updated-agent"


# ---------------------------------------------------------------------------
# PlanMonitor -- terminate_downstream
# ---------------------------------------------------------------------------


class TestTerminateDownstream:
    def test_cascade_marks_pending_as_failed(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()
        # Mark node-0 as failed
        plan.nodes["node-0"].state = PlanNodeState.FAILED

        monitor._terminate_downstream(plan, "node-0")

        assert plan.nodes["node-1"].state == PlanNodeState.FAILED
        assert plan.nodes["node-2"].state == PlanNodeState.FAILED

    def test_cascade_does_not_affect_completed_nodes(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_three_node_linear_plan()
        plan.nodes["node-0"].state = PlanNodeState.COMPLETED
        plan.nodes["node-1"].state = PlanNodeState.FAILED

        monitor._terminate_downstream(plan, "node-1")

        # node-0 was already completed, should not change
        assert plan.nodes["node-0"].state == PlanNodeState.COMPLETED
        # node-2 was pending, should be cascaded
        assert plan.nodes["node-2"].state == PlanNodeState.FAILED

    def test_cascade_in_diamond_plan(self) -> None:
        mock_llm = _make_mock_llm()
        envelope = ConstraintEnvelope()
        gradient = PlanGradient()
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_diamond_plan()
        plan.nodes["node-0"].state = PlanNodeState.COMPLETED
        plan.nodes["node-1"].state = PlanNodeState.FAILED

        monitor._terminate_downstream(plan, "node-1")

        # node-3 depends on both node-1 and node-2, but since node-1 failed
        # and cascades to node-3, node-3 should be FAILED
        assert plan.nodes["node-3"].state == PlanNodeState.FAILED
        # node-2 is not downstream of node-1 -- should remain PENDING
        assert plan.nodes["node-2"].state == PlanNodeState.PENDING


# ---------------------------------------------------------------------------
# PlanMonitor -- exception handling in execute_node
# ---------------------------------------------------------------------------


class TestExecuteNodeExceptions:
    @pytest.mark.asyncio
    async def test_exception_in_callback_treated_as_error(self) -> None:
        """If execute_node raises an exception, it is caught and treated
        as a node error."""
        diagnosis_response = {
            "root_cause": "Callback threw exception",
            "category": "permanent",
            "recoverable": False,
            "suggested_actions": [],
            "confidence": 0.9,
        }
        recovery_response = {
            "strategy": "abort",
            "rationale": "Cannot recover from exception",
            "replacement_spec": None,
            "alternative_nodes": None,
            "skip_reason": None,
        }
        mock_llm = _make_mock_llm([diagnosis_response, recovery_response])
        envelope = ConstraintEnvelope(financial={"limit": 10.0})
        gradient = PlanGradient(retry_budget=0)
        monitor = PlanMonitor(llm=mock_llm, envelope=envelope, gradient=gradient)

        plan = _make_single_node_plan()

        async def execute_raise(spec: AgentSpec, inputs: dict) -> dict:
            raise RuntimeError("Connection refused")

        result = await monitor.run_plan(plan=plan, execute_node=execute_raise)

        assert result.success is False
        # The error should have been caught and processed through the gradient
        assert plan.nodes["node-0"].error is not None
        assert "Connection refused" in plan.nodes["node-0"].error

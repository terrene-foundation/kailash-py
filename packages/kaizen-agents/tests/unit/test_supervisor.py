# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for GovernedSupervisor — the progressive-disclosure entry point."""

from __future__ import annotations

from typing import Any

import pytest

from kaizen_agents.governance.cost_model import CostModel
from kaizen_agents.supervisor import GovernedSupervisor, SupervisorResult
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    Plan,
    PlanEdge,
    PlanGradient,
    PlanNode,
    PlanNodeOutput,
)


# ---------------------------------------------------------------------------
# Test executors (mock LLM via callback)
# ---------------------------------------------------------------------------


async def success_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that always succeeds with a cost."""
    return {"result": f"output:{spec.name}", "cost": 0.50}


async def cheap_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor with minimal cost."""
    return {"result": f"done:{spec.name}", "cost": 0.01}


async def failing_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that always fails."""
    raise RuntimeError("node execution failed")


async def mixed_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that fails on specific nodes."""
    if spec.name == "fail-task":
        raise RuntimeError("deliberate failure")
    return {"result": f"ok:{spec.name}", "cost": 0.10}


# ---------------------------------------------------------------------------
# Layer 1: Simple API
# ---------------------------------------------------------------------------


class TestGovernedSupervisorLayer1:
    """Test the simplest entry point: model + budget."""

    @pytest.mark.asyncio
    async def test_dry_run(self) -> None:
        """Default executor returns dry-run result."""
        supervisor = GovernedSupervisor(model="test-model", budget_usd=5.0)
        result = await supervisor.run("Analyze codebase")
        assert result.success is True
        assert "task-0" in result.results
        assert result.budget_consumed == 0.0

    @pytest.mark.asyncio
    async def test_single_node_success(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=10.0)
        result = await supervisor.run("Do something", execute_node=success_executor)
        assert result.success is True
        assert result.budget_consumed == 0.50
        assert len(result.audit_trail) >= 2  # genesis + action

    @pytest.mark.asyncio
    async def test_single_node_failure(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=10.0)
        result = await supervisor.run("Do something", execute_node=failing_executor)
        assert result.success is False
        assert len(result.events) >= 2  # started + failed

    @pytest.mark.asyncio
    async def test_audit_trail_populated(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=10.0)
        result = await supervisor.run("Task", execute_node=cheap_executor)
        assert len(result.audit_trail) >= 2
        # Genesis record
        genesis = result.audit_trail[0]
        assert genesis["record_type"] == "genesis"

    @pytest.mark.asyncio
    async def test_budget_tracking(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=5.0)
        result = await supervisor.run("Task", execute_node=success_executor)
        assert result.budget_consumed == 0.50
        assert result.budget_allocated == 5.0


# ---------------------------------------------------------------------------
# Layer 2: Configured API
# ---------------------------------------------------------------------------


class TestGovernedSupervisorLayer2:
    """Test configured options: tools, clearance, thresholds."""

    def test_default_deny_tools(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.tools == []

    def test_explicit_tools(self) -> None:
        supervisor = GovernedSupervisor(tools=["read_file", "grep"])
        assert supervisor.tools == ["read_file", "grep"]

    def test_clearance_mapping(self) -> None:
        from kaizen_agents.governance.clearance import DataClassification

        supervisor = GovernedSupervisor(data_clearance="confidential")
        assert supervisor.clearance_level == DataClassification.CONFIDENTIAL

    def test_invalid_clearance_rejected(self) -> None:
        with pytest.raises(ValueError, match="data_clearance"):
            GovernedSupervisor(data_clearance="ultra_secret")

    def test_envelope_reflects_config(self) -> None:
        supervisor = GovernedSupervisor(
            budget_usd=50.0,
            tools=["read", "write"],
            timeout_seconds=600.0,
        )
        assert supervisor.envelope.financial is not None
        assert supervisor.envelope.financial.max_spend_usd == 50.0
        assert supervisor.envelope.operational.allowed_actions == ["read", "write"]

    @pytest.mark.asyncio
    async def test_budget_warning_event(self) -> None:
        supervisor = GovernedSupervisor(budget_usd=1.0, warning_threshold=0.50)
        result = await supervisor.run("Task", execute_node=success_executor)
        # cost=0.50, budget=1.0 → 50% utilization, matches 0.50 threshold
        warning_events = [e for e in result.events if e.event_type.value == "envelope_warning"]
        assert len(warning_events) >= 1

    def test_nan_budget_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            GovernedSupervisor(budget_usd=float("nan"))

    def test_negative_budget_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            GovernedSupervisor(budget_usd=-10.0)

    def test_zero_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            GovernedSupervisor(timeout_seconds=0.0)


# ---------------------------------------------------------------------------
# Layer 3: Direct access to governance subsystems
# ---------------------------------------------------------------------------


class TestGovernedSupervisorLayer3:
    """Test direct access to governance subsystems."""

    def test_audit_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.audit is not None

    def test_accountability_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.accountability is not None

    def test_budget_tracker_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        snap = supervisor.budget.get_snapshot("root")
        assert snap is not None
        assert snap.allocated == 1.0  # default budget

    def test_cascade_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.cascade is not None

    def test_clearance_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.clearance is not None

    def test_dereliction_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.dereliction is not None

    def test_bypass_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.bypass_manager is not None

    def test_vacancy_accessible(self) -> None:
        supervisor = GovernedSupervisor()
        assert supervisor.vacancy is not None


# ---------------------------------------------------------------------------
# Multi-node plans (run_plan)
# ---------------------------------------------------------------------------


class TestGovernedSupervisorMultiNode:
    """Test execution of multi-node pre-built plans."""

    @pytest.mark.asyncio
    async def test_three_node_linear_plan(self) -> None:
        """Integration test: 3-node linear plan completes successfully."""
        supervisor = GovernedSupervisor(budget_usd=10.0)

        # Build a 3-node linear plan: A → B → C
        spec_a = AgentSpec(spec_id="a", name="research", description="Research the topic")
        spec_b = AgentSpec(spec_id="b", name="analyze", description="Analyze findings")
        spec_c = AgentSpec(spec_id="c", name="report", description="Write report")

        plan = Plan(
            name="3-node-test",
            nodes={
                "A": PlanNode(node_id="A", agent_spec=spec_a),
                "B": PlanNode(
                    node_id="B",
                    agent_spec=spec_b,
                    input_mapping={"findings": PlanNodeOutput("A", "result")},
                ),
                "C": PlanNode(
                    node_id="C",
                    agent_spec=spec_c,
                    input_mapping={"analysis": PlanNodeOutput("B", "result")},
                ),
            },
            edges=[
                PlanEdge(from_node="A", to_node="B"),
                PlanEdge(from_node="B", to_node="C"),
            ],
        )

        result = await supervisor.run_plan(plan, execute_node=cheap_executor)
        assert result.success is True
        assert len(result.results) == 3
        assert result.budget_consumed == pytest.approx(0.03)  # 3 × 0.01

    @pytest.mark.asyncio
    async def test_fan_out_plan(self) -> None:
        """Fan-out: one root, two parallel children, one join."""
        supervisor = GovernedSupervisor(budget_usd=10.0)

        spec = AgentSpec(spec_id="s", name="task", description="task")
        plan = Plan(
            name="fan-out",
            nodes={
                "root": PlanNode(node_id="root", agent_spec=spec),
                "left": PlanNode(node_id="left", agent_spec=spec),
                "right": PlanNode(node_id="right", agent_spec=spec),
                "join": PlanNode(node_id="join", agent_spec=spec),
            },
            edges=[
                PlanEdge(from_node="root", to_node="left"),
                PlanEdge(from_node="root", to_node="right"),
                PlanEdge(from_node="left", to_node="join"),
                PlanEdge(from_node="right", to_node="join"),
            ],
        )

        result = await supervisor.run_plan(plan, execute_node=cheap_executor)
        assert result.success is True
        assert len(result.results) == 4

    @pytest.mark.asyncio
    async def test_partial_failure(self) -> None:
        """One node fails in a 3-node plan → overall failure."""
        supervisor = GovernedSupervisor(budget_usd=10.0)

        plan = Plan(
            name="partial-fail",
            nodes={
                "ok": PlanNode(
                    node_id="ok",
                    agent_spec=AgentSpec(spec_id="ok", name="ok-task", description="ok"),
                ),
                "fail": PlanNode(
                    node_id="fail",
                    agent_spec=AgentSpec(spec_id="f", name="fail-task", description="fail"),
                ),
            },
            edges=[],
        )

        result = await supervisor.run_plan(plan, execute_node=mixed_executor)
        assert result.success is False
        # "ok" completed, "fail" failed
        assert "ok" in result.results
        assert "fail" not in result.results

    @pytest.mark.asyncio
    async def test_optional_node_failure_still_succeeds(self) -> None:
        """Optional node failure doesn't block overall success."""
        supervisor = GovernedSupervisor(budget_usd=10.0)

        plan = Plan(
            name="optional-fail",
            nodes={
                "required": PlanNode(
                    node_id="required",
                    agent_spec=AgentSpec(spec_id="r", name="ok-task", description="r"),
                ),
                "optional": PlanNode(
                    node_id="optional",
                    agent_spec=AgentSpec(spec_id="o", name="fail-task", description="o"),
                    optional=True,
                ),
            },
            edges=[],
        )

        result = await supervisor.run_plan(plan, execute_node=mixed_executor)
        assert result.success is True  # only required nodes matter


# ---------------------------------------------------------------------------
# CostModel integration with GovernedSupervisor
# ---------------------------------------------------------------------------


async def token_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that returns token counts but no explicit cost."""
    return {
        "result": f"output:{spec.name}",
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "model": "claude-sonnet-4-6",
    }


async def token_executor_with_cost(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that returns both explicit cost and token counts."""
    return {
        "result": f"output:{spec.name}",
        "cost": 0.99,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
    }


class TestGovernedSupervisorCostModel:
    """Test CostModel integration with GovernedSupervisor."""

    @pytest.mark.asyncio
    async def test_cost_model_computes_from_tokens(self) -> None:
        """When executor returns tokens but no cost, cost_model computes it."""
        cost_model = CostModel()
        supervisor = GovernedSupervisor(budget_usd=10.0, cost_model=cost_model)
        result = await supervisor.run("Task", execute_node=token_executor)
        assert result.success is True
        # claude-sonnet-4-6: (1000 * 3.0 + 500 * 15.0) / 1_000_000
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert result.budget_consumed == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_explicit_cost_takes_precedence(self) -> None:
        """When executor returns both cost and tokens, explicit cost wins."""
        cost_model = CostModel()
        supervisor = GovernedSupervisor(budget_usd=10.0, cost_model=cost_model)
        result = await supervisor.run("Task", execute_node=token_executor_with_cost)
        assert result.success is True
        assert result.budget_consumed == pytest.approx(0.99)

    @pytest.mark.asyncio
    async def test_no_cost_model_ignores_tokens(self) -> None:
        """Without cost_model, token counts are ignored and cost is 0."""
        supervisor = GovernedSupervisor(budget_usd=10.0)
        result = await supervisor.run("Task", execute_node=token_executor)
        assert result.success is True
        assert result.budget_consumed == 0.0

    def test_cost_model_property_accessible(self) -> None:
        """cost_model property returns the configured model."""
        cm = CostModel()
        supervisor = GovernedSupervisor(cost_model=cm)
        assert supervisor.cost_model is cm

    def test_cost_model_property_none_by_default(self) -> None:
        """cost_model property returns None when not configured."""
        supervisor = GovernedSupervisor()
        assert supervisor.cost_model is None

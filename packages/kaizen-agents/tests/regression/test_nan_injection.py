# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for NaN/Inf injection vulnerabilities in PlanMonitor.

Red team finding CC4: NaN costs bypass budget checks because NaN >= threshold
evaluates to False, allowing NaN to reach AUTO_APPROVED. Additionally,
NaN + anything = NaN permanently poisons the cost accumulator.

These tests MUST fail without the fix and pass with it.

See: trust-plane-security.md Rule 3 (math.isfinite on all numeric fields)
See: zero-tolerance.md Rule 1 (pre-existing failures must be fixed)
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from kaizen_agents.orchestration.monitor import PlanMonitor
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    make_envelope,
    GradientZone,
    Plan,
    PlanGradient,
    PlanNode,
    PlanNodeState,
    PlanState,
)


def _make_plan(budget_limit: float = 10.0) -> Plan:
    """Create a simple single-node plan for testing."""
    return Plan(
        plan_id="test-plan",
        name="NaN Test Plan",
        envelope=make_envelope(financial={"limit": budget_limit}),
        gradient=PlanGradient(),
        nodes={
            "node-1": PlanNode(
                node_id="node-1",
                agent_spec=AgentSpec(
                    spec_id="test-spec",
                    name="Test Agent",
                    description="Test agent for NaN testing",
                ),
                state=PlanNodeState.PENDING,
            ),
        },
        edges=[],
        state=PlanState.VALIDATED,
    )


def _make_monitor(
    envelope: ConstraintEnvelope | None = None,
) -> PlanMonitor:
    """Create a PlanMonitor with mocked LLM client."""
    llm = AsyncMock()
    return PlanMonitor(
        llm=llm,
        envelope=envelope or make_envelope(financial={"limit": 10.0}),
        gradient=PlanGradient(),
    )


# ---------------------------------------------------------------------------
# _check_budget NaN/Inf tests
# ---------------------------------------------------------------------------


class TestCheckBudgetNaN:
    """Verify _check_budget fails closed on NaN/Inf/negative inputs."""

    def test_nan_cost_returns_blocked(self) -> None:
        """NaN cost MUST be BLOCKED, not AUTO_APPROVED."""
        monitor = _make_monitor()
        result = monitor._check_budget(float("nan"))
        assert result == GradientZone.BLOCKED

    def test_inf_cost_returns_blocked(self) -> None:
        """Inf cost MUST be BLOCKED."""
        monitor = _make_monitor()
        result = monitor._check_budget(float("inf"))
        assert result == GradientZone.BLOCKED

    def test_negative_inf_cost_returns_blocked(self) -> None:
        """-Inf cost MUST be BLOCKED."""
        monitor = _make_monitor()
        result = monitor._check_budget(float("-inf"))
        assert result == GradientZone.BLOCKED

    def test_negative_cost_returns_blocked(self) -> None:
        """Negative cost MUST be BLOCKED."""
        monitor = _make_monitor()
        result = monitor._check_budget(-1.0)
        assert result == GradientZone.BLOCKED

    def test_zero_cost_returns_auto_approved(self) -> None:
        """Zero cost is valid — AUTO_APPROVED."""
        monitor = _make_monitor()
        result = monitor._check_budget(0.0)
        assert result == GradientZone.AUTO_APPROVED

    def test_normal_cost_under_threshold(self) -> None:
        """Normal cost under flag threshold is AUTO_APPROVED."""
        monitor = _make_monitor()
        result = monitor._check_budget(5.0)  # 50% of 10.0 budget
        assert result == GradientZone.AUTO_APPROVED

    def test_nan_budget_limit_rejected_at_construction(self) -> None:
        """NaN budget limit MUST be rejected at ConstraintEnvelope construction."""
        with pytest.raises((ValueError,)):
            make_envelope(financial={"limit": float("nan")})

    def test_negative_budget_limit_rejected_at_construction(self) -> None:
        """Negative budget limit MUST be rejected at construction (Pydantic ge=0)."""
        with pytest.raises((ValueError,)):
            make_envelope(financial={"limit": -10.0})

    def test_inf_budget_limit_rejected_at_construction(self) -> None:
        """Inf budget limit MUST be rejected at ConstraintEnvelope construction."""
        with pytest.raises((ValueError,)):
            make_envelope(financial={"limit": float("inf")})


# ---------------------------------------------------------------------------
# Cost accumulation poisoning tests
# ---------------------------------------------------------------------------


class TestCostAccumulationPoisoning:
    """Verify NaN costs do not poison the total_cost accumulator."""

    @pytest.mark.asyncio
    async def test_nan_cost_in_output_blocks_node(self) -> None:
        """A node returning NaN cost MUST be BLOCKED, not accumulated."""
        plan = _make_plan()
        monitor = _make_monitor()

        async def execute_node(spec: AgentSpec, ctx: dict) -> dict:
            return {"result": "ok", "cost": float("nan")}

        result = await monitor.run_plan(plan, execute_node)

        # The node should be FAILED (blocked due to invalid cost)
        node = plan.nodes["node-1"]
        assert node.state == PlanNodeState.FAILED
        assert "Invalid cost value" in (node.error or "")

        # total_cost MUST NOT be NaN
        assert math.isfinite(result.total_cost)

    @pytest.mark.asyncio
    async def test_inf_cost_in_output_blocks_node(self) -> None:
        """A node returning Inf cost MUST be BLOCKED."""
        plan = _make_plan()
        monitor = _make_monitor()

        async def execute_node(spec: AgentSpec, ctx: dict) -> dict:
            return {"result": "ok", "cost": float("inf")}

        result = await monitor.run_plan(plan, execute_node)

        node = plan.nodes["node-1"]
        assert node.state == PlanNodeState.FAILED
        assert math.isfinite(result.total_cost)

    @pytest.mark.asyncio
    async def test_negative_cost_in_output_blocks_node(self) -> None:
        """A node returning negative cost MUST be BLOCKED."""
        plan = _make_plan()
        monitor = _make_monitor()

        async def execute_node(spec: AgentSpec, ctx: dict) -> dict:
            return {"result": "ok", "cost": -5.0}

        result = await monitor.run_plan(plan, execute_node)

        node = plan.nodes["node-1"]
        assert node.state == PlanNodeState.FAILED
        assert math.isfinite(result.total_cost)

    @pytest.mark.asyncio
    async def test_valid_cost_accumulates_correctly(self) -> None:
        """Valid costs should still accumulate normally."""
        plan = _make_plan(budget_limit=100.0)
        monitor = _make_monitor(envelope=make_envelope(financial={"limit": 100.0}))

        async def execute_node(spec: AgentSpec, ctx: dict) -> dict:
            return {"result": "ok", "cost": 0.50}

        result = await monitor.run_plan(plan, execute_node)

        assert result.total_cost == pytest.approx(0.50)
        assert math.isfinite(result.total_cost)

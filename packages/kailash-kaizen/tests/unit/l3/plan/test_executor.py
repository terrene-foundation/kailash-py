# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PlanExecutor.

Covers:
- Linear plan execution (A -> B -> C)
- Diamond plan execution (fan-out, fan-in)
- Retry on retryable failure (G2)
- Retry exhaustion -> held (G3)
- Optional node failure -> flagged/skipped (G4)
- Required node failure -> held (G5)
- Envelope violation -> blocked (G8)
- Suspend / resume / cancel operations
- Node readiness for DATA_DEPENDENCY, COMPLETION_DEPENDENCY, CO_START
"""

from __future__ import annotations

from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(node_id, agent_spec_id="spec_1", input_mapping=None, optional=False):
    from kaizen.l3.plan.types import PlanNode, PlanNodeState

    return PlanNode(
        node_id=node_id,
        agent_spec_id=agent_spec_id,
        input_mapping=input_mapping or {},
        state=PlanNodeState.PENDING,
        instance_id=None,
        optional=optional,
        retry_count=0,
        output=None,
        error=None,
    )


def _make_edge(from_node, to_node, edge_type=None):
    from kaizen.l3.plan.types import EdgeType, PlanEdge

    return PlanEdge(
        from_node=from_node,
        to_node=to_node,
        edge_type=edge_type or EdgeType.DATA_DEPENDENCY,
    )


def _make_plan(nodes, edges, envelope=None, gradient=None, state=None):
    from kaizen.l3.plan.types import Plan, PlanState

    return Plan(
        plan_id="test_plan",
        name="Test Plan",
        envelope=envelope or {"financial": {"max_cost": 100.0}},
        gradient=gradient or {},
        nodes={n.node_id: n for n in nodes},
        edges=edges,
        state=state or PlanState.VALIDATED,
    )


class SuccessCallback:
    """Callback that always succeeds with a fixed output."""

    def __init__(self, output: Any = None):
        self._output = output or {"result": "ok"}

    def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        return {"output": self._output, "error": None, "retryable": False}


class FailCallback:
    """Callback that always fails."""

    def __init__(self, error: str = "failed", retryable: bool = False):
        self._error = error
        self._retryable = retryable

    def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        return {"output": None, "error": self._error, "retryable": self._retryable}


class ConditionalCallback:
    """Callback that fails N times then succeeds."""

    def __init__(
        self, fail_count: int = 1, error: str = "transient", retryable: bool = True
    ):
        self._fail_count = fail_count
        self._calls: dict[str, int] = {}
        self._error = error
        self._retryable = retryable

    def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        count = self._calls.get(node_id, 0)
        self._calls[node_id] = count + 1
        if count < self._fail_count:
            return {"output": None, "error": self._error, "retryable": self._retryable}
        return {"output": {"result": "recovered"}, "error": None, "retryable": False}


class EnvelopeViolationCallback:
    """Callback that signals an envelope violation."""

    def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        return {
            "output": None,
            "error": "envelope_violation",
            "retryable": False,
            "envelope_violation": True,
        }


# ---------------------------------------------------------------------------
# Linear plan tests
# ---------------------------------------------------------------------------


class TestLinearPlanExecution:
    """Execute a simple A -> B -> C linear plan."""

    def test_linear_plan_all_succeed(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        n3 = _make_node("n3")
        plan = _make_plan(
            [n1, n2, n3],
            [_make_edge("n1", "n2"), _make_edge("n2", "n3")],
        )

        executor = PlanExecutor(node_callback=SuccessCallback())
        events = executor.execute(plan)

        assert plan.state == PlanState.COMPLETED
        assert plan.nodes["n1"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n2"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n3"].state == PlanNodeState.COMPLETED

        # Should have at least: 3x NodeReady + 3x NodeStarted + 3x NodeCompleted + PlanCompleted
        tags = [e.tag for e in events]
        assert tags.count("NodeReady") == 3
        assert tags.count("NodeStarted") == 3
        assert tags.count("NodeCompleted") == 3
        assert "PlanCompleted" in tags


# ---------------------------------------------------------------------------
# Diamond plan tests
# ---------------------------------------------------------------------------


class TestDiamondPlanExecution:
    """Execute a diamond: A -> B, A -> C, B -> D, C -> D."""

    def test_diamond_plan_all_succeed(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        nodes = [_make_node(f"n{i}") for i in range(1, 5)]
        edges = [
            _make_edge("n1", "n2"),
            _make_edge("n1", "n3"),
            _make_edge("n2", "n4"),
            _make_edge("n3", "n4"),
        ]
        plan = _make_plan(nodes, edges)

        executor = PlanExecutor(node_callback=SuccessCallback())
        events = executor.execute(plan)

        assert plan.state == PlanState.COMPLETED
        for n in plan.nodes.values():
            assert n.state == PlanNodeState.COMPLETED


# ---------------------------------------------------------------------------
# Retry tests (G2, G3)
# ---------------------------------------------------------------------------


class TestRetryBehavior:
    """Gradient rules G2 (retry) and G3 (retry exhausted)."""

    def test_retryable_failure_succeeds_on_retry(self):
        """G2: retryable error with retries left -> retry -> success."""
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        n1 = _make_node("n1")
        plan = _make_plan([n1], [], gradient={"retry_budget": 2})

        # Fail once then succeed
        executor = PlanExecutor(node_callback=ConditionalCallback(fail_count=1))
        events = executor.execute(plan)

        assert plan.state == PlanState.COMPLETED
        assert plan.nodes["n1"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n1"].retry_count == 1

        tags = [e.tag for e in events]
        assert "NodeRetrying" in tags

    def test_retry_budget_exhausted_holds(self):
        """G3: retries exhausted -> held (default gradient)."""
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        n1 = _make_node("n1")
        plan = _make_plan(
            [n1],
            [],
            gradient={"retry_budget": 1, "after_retry_exhaustion": "held"},
        )

        # Always fail with retryable error
        executor = PlanExecutor(
            node_callback=FailCallback(error="always fails", retryable=True)
        )
        events = executor.execute(plan)

        # Plan should be suspended/not completed since node is held
        assert plan.nodes["n1"].state == PlanNodeState.FAILED
        tags = [e.tag for e in events]
        assert "NodeHeld" in tags


# ---------------------------------------------------------------------------
# Optional node failure tests (G4)
# ---------------------------------------------------------------------------


class TestOptionalNodeFailure:
    """Gradient rule G4: optional node non-retryable failure."""

    def test_optional_node_failure_flagged_and_skipped(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        n1 = _make_node("n1", optional=True)
        plan = _make_plan(
            [n1],
            [],
            gradient={"optional_node_failure": "flagged"},
        )

        executor = PlanExecutor(
            node_callback=FailCallback(error="not retryable", retryable=False)
        )
        events = executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.SKIPPED
        tags = [e.tag for e in events]
        assert "NodeFlagged" in tags or "NodeSkipped" in tags


# ---------------------------------------------------------------------------
# Required node failure tests (G5)
# ---------------------------------------------------------------------------


class TestRequiredNodeFailure:
    """Gradient rule G5: required node non-retryable failure -> held."""

    def test_required_node_failure_held(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState

        n1 = _make_node("n1", optional=False)
        plan = _make_plan([n1], [])

        executor = PlanExecutor(
            node_callback=FailCallback(error="fatal", retryable=False)
        )
        events = executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.FAILED
        tags = [e.tag for e in events]
        assert "NodeHeld" in tags


# ---------------------------------------------------------------------------
# Envelope violation tests (G8)
# ---------------------------------------------------------------------------


class TestEnvelopeViolation:
    """Gradient rule G8: envelope violation -> always blocked."""

    def test_envelope_violation_blocks_node(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        executor = PlanExecutor(node_callback=EnvelopeViolationCallback())
        events = executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.FAILED
        tags = [e.tag for e in events]
        assert "NodeBlocked" in tags

        # Downstream n2 should be skipped due to upstream blocked
        assert plan.nodes["n2"].state == PlanNodeState.SKIPPED


# ---------------------------------------------------------------------------
# Suspend / Resume / Cancel tests
# ---------------------------------------------------------------------------


class TestSuspendResumeCancel:
    """PlanExecutor suspend, resume, cancel operations."""

    def test_suspend_executing_plan(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanState

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        executor = PlanExecutor(node_callback=SuccessCallback())
        # Set plan to executing state manually
        plan.state = PlanState.EXECUTING
        events = executor.suspend(plan)

        assert plan.state == PlanState.SUSPENDED
        tags = [e.tag for e in events]
        assert "PlanSuspended" in tags

    def test_suspend_non_executing_raises(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanState

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        executor = PlanExecutor(node_callback=SuccessCallback())

        with pytest.raises(ExecutionError, match="[Ee]xecuting"):
            executor.suspend(plan)

    def test_resume_suspended_plan(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanState

        plan = _make_plan([_make_node("n1")], [])
        plan.state = PlanState.SUSPENDED

        executor = PlanExecutor(node_callback=SuccessCallback())
        events = executor.resume(plan)

        assert plan.state == PlanState.EXECUTING
        tags = [e.tag for e in events]
        assert "PlanResumed" in tags

    def test_resume_non_suspended_raises(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanState

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        executor = PlanExecutor(node_callback=SuccessCallback())

        with pytest.raises(ExecutionError, match="[Ss]uspended"):
            executor.resume(plan)

    def test_cancel_executing_plan(self):
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanNodeState, PlanState

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])
        plan.state = PlanState.EXECUTING

        executor = PlanExecutor(node_callback=SuccessCallback())
        events = executor.cancel(plan)

        assert plan.state == PlanState.CANCELLED
        for node in plan.nodes.values():
            assert node.state == PlanNodeState.SKIPPED
        tags = [e.tag for e in events]
        assert "PlanCancelled" in tags

    def test_cancel_terminal_raises(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanState

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        plan.state = PlanState.COMPLETED
        executor = PlanExecutor(node_callback=SuccessCallback())

        with pytest.raises(ExecutionError, match="terminal"):
            executor.cancel(plan)


# ---------------------------------------------------------------------------
# Node readiness edge type tests
# ---------------------------------------------------------------------------


class TestNodeReadiness:
    """Node readiness semantics for different edge types."""

    def test_completion_dependency_ready_on_failure(self):
        """COMPLETION_DEPENDENCY: to is ready when from reaches terminal (even failed)."""
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import EdgeType, PlanNodeState, PlanState

        n1 = _make_node("n1")
        n2 = _make_node("n2")  # cleanup node
        edge = _make_edge("n1", "n2", EdgeType.COMPLETION_DEPENDENCY)
        plan = _make_plan([n1, n2], [edge])

        call_count = {"n1": 0, "n2": 0}

        def callback(node_id, spec_id):
            call_count[node_id] = call_count.get(node_id, 0) + 1
            if node_id == "n1":
                return {"output": None, "error": "fail", "retryable": False}
            return {"output": {"cleaned": True}, "error": None, "retryable": False}

        executor = PlanExecutor(node_callback=callback)
        events = executor.execute(plan)

        # n2 should have been executed despite n1 failing
        assert call_count["n2"] >= 1

    def test_co_start_does_not_block(self):
        """CO_START: advisory -- does not block to if from hasn't started."""
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import EdgeType, PlanNodeState, PlanState

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        edge = _make_edge("n1", "n2", EdgeType.CO_START)
        plan = _make_plan([n1, n2], [edge])

        executor = PlanExecutor(node_callback=SuccessCallback())
        events = executor.execute(plan)

        assert plan.state == PlanState.COMPLETED
        assert plan.nodes["n1"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n2"].state == PlanNodeState.COMPLETED


# ---------------------------------------------------------------------------
# Precondition tests
# ---------------------------------------------------------------------------


class TestExecutePreconditions:
    """PlanExecutor.execute precondition checks."""

    def test_execute_requires_validated_state(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import PlanExecutor
        from kaizen.l3.plan.types import PlanState

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        plan.state = PlanState.DRAFT
        executor = PlanExecutor(node_callback=SuccessCallback())

        with pytest.raises(ExecutionError, match="[Vv]alidated"):
            executor.execute(plan)

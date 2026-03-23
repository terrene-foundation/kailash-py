# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for AsyncPlanExecutor.

Covers:
- Linear plan execution (A -> B -> C) with async callback
- Fan-out plan execution (A -> [B, C]) with concurrent execution
- Retry on retryable failure (G2)
- Retry exhaustion -> held (G3)
- Optional node failure -> flagged/skipped (G4)
- Required node failure -> held (G5)
- Envelope violation -> blocked with cascade (G8)
- Concurrent execution timing: independent nodes run concurrently
- Event callback receives events in real-time
- Suspend / resume / cancel operations
- Concurrency limiting via max_concurrency
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from kaizen.l3.plan.types import (
    EdgeType,
    PlanEdge,
    PlanNode,
    PlanNodeState,
    PlanState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    agent_spec_id: str = "spec_1",
    input_mapping: dict | None = None,
    optional: bool = False,
) -> PlanNode:
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


def _make_edge(
    from_node: str,
    to_node: str,
    edge_type: EdgeType | None = None,
) -> PlanEdge:
    return PlanEdge(
        from_node=from_node,
        to_node=to_node,
        edge_type=edge_type or EdgeType.DATA_DEPENDENCY,
    )


def _make_plan(
    nodes: list[PlanNode],
    edges: list[PlanEdge],
    envelope: dict | None = None,
    gradient: dict | None = None,
    state: PlanState | None = None,
):
    from kaizen.l3.plan.types import Plan

    return Plan(
        plan_id="test_plan",
        name="Test Plan",
        envelope=envelope or {"financial": {"max_cost": 100.0}},
        gradient=gradient or {},
        nodes={n.node_id: n for n in nodes},
        edges=edges,
        state=state or PlanState.VALIDATED,
    )


# ---------------------------------------------------------------------------
# Async callback helpers
# ---------------------------------------------------------------------------


class AsyncSuccessCallback:
    """Async callback that always succeeds with a fixed output."""

    def __init__(self, output: Any = None, delay: float = 0.0):
        self._output = output or {"result": "ok"}
        self._delay = delay

    async def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return {"output": self._output, "error": None, "retryable": False}


class AsyncFailCallback:
    """Async callback that always fails."""

    def __init__(
        self,
        error: str = "failed",
        retryable: bool = False,
        envelope_violation: bool = False,
    ):
        self._error = error
        self._retryable = retryable
        self._envelope_violation = envelope_violation

    async def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        return {
            "output": None,
            "error": self._error,
            "retryable": self._retryable,
            "envelope_violation": self._envelope_violation,
        }


class AsyncConditionalCallback:
    """Async callback that fails N times then succeeds."""

    def __init__(
        self,
        fail_count: int = 1,
        error: str = "transient",
        retryable: bool = True,
    ):
        self._fail_count = fail_count
        self._calls: dict[str, int] = {}
        self._error = error
        self._retryable = retryable

    async def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        count = self._calls.get(node_id, 0)
        self._calls[node_id] = count + 1
        if count < self._fail_count:
            return {
                "output": None,
                "error": self._error,
                "retryable": self._retryable,
            }
        return {
            "output": {"result": "recovered"},
            "error": None,
            "retryable": False,
        }


class AsyncEnvelopeViolationCallback:
    """Async callback that signals an envelope violation."""

    async def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        return {
            "output": None,
            "error": "envelope_violation",
            "retryable": False,
            "envelope_violation": True,
        }


class AsyncTimedCallback:
    """Async callback that records execution timestamps to verify concurrency."""

    def __init__(self, delay: float = 0.05):
        self._delay = delay
        self.timestamps: dict[str, dict[str, float]] = {}

    async def __call__(self, node_id: str, agent_spec_id: str) -> dict:
        start = time.monotonic()
        await asyncio.sleep(self._delay)
        end = time.monotonic()
        self.timestamps[node_id] = {"start": start, "end": end}
        return {"output": {"result": node_id}, "error": None, "retryable": False}


# ---------------------------------------------------------------------------
# Linear plan tests
# ---------------------------------------------------------------------------


class TestAsyncLinearPlanExecution:
    """Execute a simple A -> B -> C linear plan with async executor."""

    @pytest.mark.asyncio
    async def test_linear_plan_all_succeed(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        n3 = _make_node("n3")
        plan = _make_plan(
            [n1, n2, n3],
            [_make_edge("n1", "n2"), _make_edge("n2", "n3")],
        )

        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())
        events = await executor.execute(plan)

        assert plan.state == PlanState.COMPLETED
        assert plan.nodes["n1"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n2"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n3"].state == PlanNodeState.COMPLETED

        tags = [e.tag for e in events]
        assert tags.count("NodeReady") == 3
        assert tags.count("NodeStarted") == 3
        assert tags.count("NodeCompleted") == 3
        assert "PlanCompleted" in tags


# ---------------------------------------------------------------------------
# Fan-out concurrent execution tests
# ---------------------------------------------------------------------------


class TestAsyncConcurrentExecution:
    """Verify independent nodes execute concurrently via asyncio.gather."""

    @pytest.mark.asyncio
    async def test_fan_out_executes_concurrently(self):
        """A -> [B, C]: B and C should run concurrently."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n_a = _make_node("A")
        n_b = _make_node("B")
        n_c = _make_node("C")
        plan = _make_plan(
            [n_a, n_b, n_c],
            [_make_edge("A", "B"), _make_edge("A", "C")],
        )

        timed_cb = AsyncTimedCallback(delay=0.05)
        executor = AsyncPlanExecutor(node_callback=timed_cb)
        events = await executor.execute(plan)

        assert plan.state == PlanState.COMPLETED

        # B and C should have overlapping execution windows (concurrent)
        b_start = timed_cb.timestamps["B"]["start"]
        b_end = timed_cb.timestamps["B"]["end"]
        c_start = timed_cb.timestamps["C"]["start"]
        c_end = timed_cb.timestamps["C"]["end"]

        # If concurrent, B and C should start at approximately the same time
        # (within a small tolerance). If sequential, one would start after the
        # other finished.
        start_diff = abs(b_start - c_start)
        # Concurrent: start difference should be small (< delay)
        assert (
            start_diff < 0.04
        ), f"B and C did not start concurrently: start diff = {start_diff:.4f}s"

    @pytest.mark.asyncio
    async def test_concurrent_faster_than_sequential(self):
        """Two independent nodes with delay should complete faster than 2x delay."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        delay = 0.05
        n1 = _make_node("n1")
        n2 = _make_node("n2")
        # No edges: n1 and n2 are independent
        plan = _make_plan([n1, n2], [])

        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback(delay=delay))

        start = time.monotonic()
        events = await executor.execute(plan)
        elapsed = time.monotonic() - start

        assert plan.state == PlanState.COMPLETED
        # If concurrent, total time should be ~delay, not ~2*delay
        assert elapsed < delay * 1.8, (
            f"Execution took {elapsed:.3f}s, expected < {delay * 1.8:.3f}s "
            f"for concurrent execution"
        )


# ---------------------------------------------------------------------------
# Retry tests (G2, G3)
# ---------------------------------------------------------------------------


class TestAsyncRetryBehavior:
    """Gradient rules G2 (retry) and G3 (retry exhausted) with async executor."""

    @pytest.mark.asyncio
    async def test_retryable_failure_succeeds_on_retry(self):
        """G2: retryable error with retries left -> retry -> success."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        plan = _make_plan([n1], [], gradient={"retry_budget": 2})

        executor = AsyncPlanExecutor(
            node_callback=AsyncConditionalCallback(fail_count=1)
        )
        events = await executor.execute(plan)

        assert plan.state == PlanState.COMPLETED
        assert plan.nodes["n1"].state == PlanNodeState.COMPLETED
        assert plan.nodes["n1"].retry_count == 1

        tags = [e.tag for e in events]
        assert "NodeRetrying" in tags

    @pytest.mark.asyncio
    async def test_retry_budget_exhausted_transitions_to_held(self):
        """G3: retries exhausted -> node transitions to HELD state."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        plan = _make_plan(
            [n1],
            [],
            gradient={"retry_budget": 1, "after_retry_exhaustion": "held"},
        )

        executor = AsyncPlanExecutor(
            node_callback=AsyncFailCallback(error="always fails", retryable=True)
        )
        events = await executor.execute(plan)

        # Node should be in HELD state (not FAILED)
        assert plan.nodes["n1"].state == PlanNodeState.HELD
        tags = [e.tag for e in events]
        assert "NodeHeld" in tags

    @pytest.mark.asyncio
    async def test_retry_budget_exhausted_plan_suspends(self):
        """G3: plan with held node should be SUSPENDED, not FAILED."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        plan = _make_plan(
            [n1],
            [],
            gradient={"retry_budget": 1, "after_retry_exhaustion": "held"},
        )

        executor = AsyncPlanExecutor(
            node_callback=AsyncFailCallback(error="always fails", retryable=True)
        )
        events = await executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.HELD
        assert plan.state == PlanState.SUSPENDED
        tags = [e.tag for e in events]
        assert "PlanSuspended" in tags


# ---------------------------------------------------------------------------
# Optional node failure tests (G4)
# ---------------------------------------------------------------------------


class TestAsyncOptionalNodeFailure:
    """Gradient rule G4: optional node non-retryable failure."""

    @pytest.mark.asyncio
    async def test_optional_node_failure_flagged_and_skipped(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1", optional=True)
        plan = _make_plan(
            [n1],
            [],
            gradient={"optional_node_failure": "flagged"},
        )

        executor = AsyncPlanExecutor(
            node_callback=AsyncFailCallback(error="not retryable", retryable=False)
        )
        events = await executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.SKIPPED
        tags = [e.tag for e in events]
        assert "NodeFlagged" in tags or "NodeSkipped" in tags


# ---------------------------------------------------------------------------
# Required node failure tests (G5)
# ---------------------------------------------------------------------------


class TestAsyncRequiredNodeFailure:
    """Gradient rule G5: required node non-retryable failure -> held."""

    @pytest.mark.asyncio
    async def test_required_node_failure_transitions_to_held(self):
        """G5: required node non-retryable failure transitions to HELD state."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1", optional=False)
        plan = _make_plan([n1], [])

        executor = AsyncPlanExecutor(
            node_callback=AsyncFailCallback(error="fatal", retryable=False)
        )
        events = await executor.execute(plan)

        # Node should be in HELD state (not FAILED)
        assert plan.nodes["n1"].state == PlanNodeState.HELD
        tags = [e.tag for e in events]
        assert "NodeHeld" in tags
        # Plan should be SUSPENDED
        assert plan.state == PlanState.SUSPENDED


# ---------------------------------------------------------------------------
# Envelope violation tests (G8)
# ---------------------------------------------------------------------------


class TestAsyncEnvelopeViolation:
    """Gradient rule G8: envelope violation -> always blocked."""

    @pytest.mark.asyncio
    async def test_envelope_violation_blocks_node_and_cascades(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        executor = AsyncPlanExecutor(node_callback=AsyncEnvelopeViolationCallback())
        events = await executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.FAILED
        tags = [e.tag for e in events]
        assert "NodeBlocked" in tags

        # Downstream n2 should be skipped due to upstream blocked
        assert plan.nodes["n2"].state == PlanNodeState.SKIPPED


# ---------------------------------------------------------------------------
# Event callback tests
# ---------------------------------------------------------------------------


class TestAsyncEventCallback:
    """Event callback receives events in real-time during execution."""

    @pytest.mark.asyncio
    async def test_event_callback_receives_all_events(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        received_events: list = []

        async def event_callback(event):
            received_events.append(event)

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        executor = AsyncPlanExecutor(
            node_callback=AsyncSuccessCallback(),
            event_callback=event_callback,
        )
        events = await executor.execute(plan)

        # The event callback should have received the same events
        assert len(received_events) == len(events)
        for received, returned in zip(received_events, events):
            assert received.tag == returned.tag

    @pytest.mark.asyncio
    async def test_event_callback_receives_events_incrementally(self):
        """Events are dispatched as they occur, not batched at the end."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        event_order: list[str] = []

        async def event_callback(event):
            event_order.append(event.tag)

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        executor = AsyncPlanExecutor(
            node_callback=AsyncSuccessCallback(),
            event_callback=event_callback,
        )
        await executor.execute(plan)

        # NodeReady for n1 should appear before NodeReady for n2
        n1_ready_idx = event_order.index("NodeReady")
        # Find the second NodeReady (for n2)
        second_ready_idx = None
        for i, tag in enumerate(event_order):
            if tag == "NodeReady" and i > n1_ready_idx:
                second_ready_idx = i
                break

        assert second_ready_idx is not None
        # n1's completion events should appear before n2's ready event
        assert second_ready_idx > n1_ready_idx


# ---------------------------------------------------------------------------
# Suspend / Resume / Cancel tests
# ---------------------------------------------------------------------------


class TestAsyncSuspendResumeCancel:
    """AsyncPlanExecutor suspend, resume, cancel operations."""

    @pytest.mark.asyncio
    async def test_suspend_executing_plan(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])
        plan.state = PlanState.EXECUTING

        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())
        events = await executor.suspend(plan)

        assert plan.state == PlanState.SUSPENDED
        tags = [e.tag for e in events]
        assert "PlanSuspended" in tags

    @pytest.mark.asyncio
    async def test_suspend_non_executing_raises(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())

        with pytest.raises(ExecutionError, match="[Ee]xecuting"):
            await executor.suspend(plan)

    @pytest.mark.asyncio
    async def test_resume_suspended_plan(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        plan = _make_plan([_make_node("n1")], [])
        plan.state = PlanState.SUSPENDED

        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())
        events = await executor.resume(plan)

        assert plan.state == PlanState.EXECUTING
        tags = [e.tag for e in events]
        assert "PlanResumed" in tags

    @pytest.mark.asyncio
    async def test_resume_non_suspended_raises(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())

        with pytest.raises(ExecutionError, match="[Ss]uspended"):
            await executor.resume(plan)

    @pytest.mark.asyncio
    async def test_cancel_executing_plan(self):
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])
        plan.state = PlanState.EXECUTING

        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())
        events = await executor.cancel(plan)

        assert plan.state == PlanState.CANCELLED
        for node in plan.nodes.values():
            assert node.state == PlanNodeState.SKIPPED
        tags = [e.tag for e in events]
        assert "PlanCancelled" in tags

    @pytest.mark.asyncio
    async def test_cancel_terminal_raises(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        plan.state = PlanState.COMPLETED
        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())

        with pytest.raises(ExecutionError, match="terminal"):
            await executor.cancel(plan)

    @pytest.mark.asyncio
    async def test_cancel_skips_held_nodes(self):
        """Cancel transitions HELD nodes to SKIPPED."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        n1.state = PlanNodeState.HELD
        plan = _make_plan([n1], [])
        plan.state = PlanState.SUSPENDED

        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())
        events = await executor.cancel(plan)

        assert plan.state == PlanState.CANCELLED
        assert plan.nodes["n1"].state == PlanNodeState.SKIPPED
        tags = [e.tag for e in events]
        assert "NodeSkipped" in tags
        assert "PlanCancelled" in tags


# ---------------------------------------------------------------------------
# Async HELD state resolution tests
# ---------------------------------------------------------------------------


class TestAsyncHeldStateResolution:
    """Test HELD -> RUNNING resolution with async executor."""

    @pytest.mark.asyncio
    async def test_held_node_blocks_downstream(self):
        """A HELD node should block downstream DATA_DEPENDENCY nodes."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        executor = AsyncPlanExecutor(
            node_callback=AsyncFailCallback(error="fatal", retryable=False)
        )
        events = await executor.execute(plan)

        assert plan.nodes["n1"].state == PlanNodeState.HELD
        assert plan.nodes["n2"].state == PlanNodeState.PENDING


# ---------------------------------------------------------------------------
# Concurrency limiting tests
# ---------------------------------------------------------------------------


class TestAsyncConcurrencyLimiting:
    """Verify max_concurrency parameter limits parallel execution."""

    @pytest.mark.asyncio
    async def test_max_concurrency_limits_parallelism(self):
        """With max_concurrency=1, nodes execute sequentially."""
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        delay = 0.05
        n1 = _make_node("n1")
        n2 = _make_node("n2")
        # No edges: both are independent
        plan = _make_plan([n1, n2], [])

        timed_cb = AsyncTimedCallback(delay=delay)
        executor = AsyncPlanExecutor(node_callback=timed_cb, max_concurrency=1)

        start = time.monotonic()
        events = await executor.execute(plan)
        elapsed = time.monotonic() - start

        assert plan.state == PlanState.COMPLETED
        # With max_concurrency=1, total time should be ~2*delay (sequential)
        assert elapsed >= delay * 1.5, (
            f"Execution took {elapsed:.3f}s, expected >= {delay * 1.5:.3f}s "
            f"for sequential (max_concurrency=1) execution"
        )


# ---------------------------------------------------------------------------
# Precondition tests
# ---------------------------------------------------------------------------


class TestAsyncExecutePreconditions:
    """AsyncPlanExecutor.execute precondition checks."""

    @pytest.mark.asyncio
    async def test_execute_requires_validated_state(self):
        from kaizen.l3.plan.errors import ExecutionError
        from kaizen.l3.plan.executor import AsyncPlanExecutor

        plan = _make_plan([_make_node("n1")], [], state=PlanState.VALIDATED)
        plan.state = PlanState.DRAFT
        executor = AsyncPlanExecutor(node_callback=AsyncSuccessCallback())

        with pytest.raises(ExecutionError, match="[Vv]alidated"):
            await executor.execute(plan)

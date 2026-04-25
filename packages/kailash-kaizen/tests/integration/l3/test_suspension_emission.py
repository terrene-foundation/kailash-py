# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for L3 executor SuspensionRecord emission.

Issue #598 — drives each of the 5 PACT N3 trigger conditions
end-to-end through the L3 PlanExecutor / AsyncPlanExecutor and
asserts that ``plan.suspension`` carries the correct variant.

These are Tier 2 integration tests — no mocking of the framework
hot path. The agent ``node_callback`` is a thin in-process function
(no LLM, no network) because the L3 executor's contract is purely
synchronous-callback / async-callback driven; "real infrastructure"
for L3 means the real executor running over real Plan dataclasses.
"""

from __future__ import annotations

from typing import Any

import pytest

from kaizen.l3.plan.executor import AsyncPlanExecutor, PlanExecutor
from kaizen.l3.plan.suspension import (
    BudgetExceededReason,
    CircuitBreakerTrippedReason,
    EnvelopeViolationReason,
    ExplicitCancellationReason,
    HumanApprovalGateReason,
    SuspensionRecord,
)
from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
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
    optional: bool = False,
) -> PlanNode:
    return PlanNode(
        node_id=node_id,
        agent_spec_id=agent_spec_id,
        input_mapping={},
        state=PlanNodeState.PENDING,
        instance_id=None,
        optional=optional,
        retry_count=0,
        output=None,
        error=None,
    )


def _make_edge(from_node: str, to_node: str) -> PlanEdge:
    return PlanEdge(
        from_node=from_node,
        to_node=to_node,
        edge_type=EdgeType.DATA_DEPENDENCY,
    )


def _make_plan(
    nodes: list[PlanNode],
    edges: list[PlanEdge] | None = None,
    gradient: dict[str, Any] | None = None,
) -> Plan:
    return Plan(
        plan_id="test-plan-598",
        name="suspension emission test",
        envelope={"financial": {"max_cost": 100.0}},
        gradient=gradient or {},
        nodes={n.node_id: n for n in nodes},
        edges=edges or [],
        state=PlanState.VALIDATED,
    )


# ---------------------------------------------------------------------------
# Trigger 1: HumanApprovalGate
# ---------------------------------------------------------------------------


def test_sync_human_approval_gate_on_required_node_held():
    """G5: required node fails non-retryable -> HELD -> SuspensionRecord.

    The terminal-state path attaches a HumanApprovalGateReason because
    the execution loop exits with a HELD node.
    """
    plan = _make_plan(
        [_make_node("required_n")],
        gradient={"retry_budget": 0},  # no retries; first failure -> HELD
    )

    def callback(node_id: str, agent_spec_id: str) -> dict:
        return {"output": None, "error": "boom", "retryable": False}

    executor = PlanExecutor(callback)
    events = executor.execute(plan)

    # Plan ended in SUSPENDED with at least one HELD node
    assert plan.state == PlanState.SUSPENDED
    assert any(n.state == PlanNodeState.HELD for n in plan.nodes.values())

    # SuspensionRecord attached with HumanApprovalGate variant
    assert plan.suspension is not None
    assert isinstance(plan.suspension, SuspensionRecord)
    assert isinstance(plan.suspension.reason, HumanApprovalGateReason)
    assert plan.suspension.reason.held_node == "required_n"
    # The held node's error is captured in the reason
    assert "boom" in plan.suspension.reason.reason


def test_sync_human_approval_gate_picks_lexicographic_first():
    """When multiple HELD nodes, the lex-first node id wins (deterministic
    cross-SDK comparison)."""
    plan = _make_plan(
        [_make_node("z_held"), _make_node("a_held")],
        gradient={"retry_budget": 0},
    )

    def callback(node_id: str, agent_spec_id: str) -> dict:
        return {"output": None, "error": "fail", "retryable": False}

    executor = PlanExecutor(callback)
    executor.execute(plan)

    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, HumanApprovalGateReason)
    assert plan.suspension.reason.held_node == "a_held"


# ---------------------------------------------------------------------------
# Trigger 2: CircuitBreakerTripped
# ---------------------------------------------------------------------------


def test_sync_circuit_breaker_tripped():
    """suspend_for_circuit_breaker attaches the right variant."""
    plan = _make_plan([_make_node("n1")])
    plan.state = PlanState.EXECUTING

    executor = PlanExecutor(lambda nid, sid: {"output": None, "error": None})
    events = executor.suspend_for_circuit_breaker(
        plan,
        breaker_id="openai-rate-limit",
        triggering_node="n1",
    )

    assert plan.state == PlanState.SUSPENDED
    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, CircuitBreakerTrippedReason)
    assert plan.suspension.reason.breaker_id == "openai-rate-limit"
    assert plan.suspension.reason.triggering_node == "n1"


@pytest.mark.asyncio
async def test_async_circuit_breaker_tripped():
    plan = _make_plan([_make_node("n1")])
    plan.state = PlanState.EXECUTING

    async def callback(nid, sid):
        return {"output": None, "error": None}

    executor = AsyncPlanExecutor(callback)
    await executor.suspend_for_circuit_breaker(
        plan,
        breaker_id="anthropic-quota",
        triggering_node="n1",
    )

    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, CircuitBreakerTrippedReason)
    assert plan.suspension.reason.breaker_id == "anthropic-quota"


# ---------------------------------------------------------------------------
# Trigger 3: BudgetExceeded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_budget_exceeded_via_blocked_verdict():
    """Async executor with enforcer: BLOCKED verdict whose requested >
    available is classified as BudgetExceeded."""
    from kaizen.l3.envelope.types import Verdict

    plan = _make_plan(
        [_make_node("expensive_node")],
        gradient={"retry_budget": 0},
    )

    class StubEnforcer:
        async def check_action(self, ctx):
            return Verdict(
                tag="BLOCKED",
                dimension="financial",
                detail="budget exceeded",
                requested=150.0,
                available=100.0,
            )

    async def callback(nid, sid):
        # Should never be reached because BLOCKED short-circuits
        return {"output": None, "error": None}

    executor = AsyncPlanExecutor(callback, enforcer=StubEnforcer())
    await executor.execute(plan)

    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, BudgetExceededReason)
    assert plan.suspension.reason.dimension == "financial"
    assert plan.suspension.reason.usage_pct == pytest.approx(1.5)
    assert plan.suspension.reason.triggering_node == "expensive_node"


# ---------------------------------------------------------------------------
# Trigger 4: EnvelopeViolation
# ---------------------------------------------------------------------------


def test_sync_envelope_violation_via_callback_result():
    """Sync executor: callback returns envelope_violation=True ->
    EnvelopeViolation SuspensionRecord."""
    plan = _make_plan(
        [_make_node("classified_read")],
        gradient={"retry_budget": 0},
    )

    def callback(node_id: str, agent_spec_id: str) -> dict:
        return {
            "output": None,
            "error": "clearance level mismatch",
            "retryable": False,
            "envelope_violation": True,
        }

    executor = PlanExecutor(callback)
    executor.execute(plan)

    # The execution path: envelope_violation -> NodeBlocked -> cascade.
    # No HELD nodes, so terminal-state does NOT overwrite with
    # HumanApprovalGate.
    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, EnvelopeViolationReason)
    assert plan.suspension.reason.detail == "clearance level mismatch"
    assert plan.suspension.reason.triggering_node == "classified_read"


@pytest.mark.asyncio
async def test_async_envelope_violation_via_blocked_verdict_no_overflow():
    """Async executor with enforcer: BLOCKED verdict without numeric
    overflow is classified as EnvelopeViolation."""
    from kaizen.l3.envelope.types import Verdict

    plan = _make_plan(
        [_make_node("classified_read")],
        gradient={"retry_budget": 0},
    )

    class StubEnforcer:
        async def check_action(self, ctx):
            # No requested/available numerics -> structural violation
            return Verdict(
                tag="BLOCKED",
                dimension="data_access",
                detail="clearance fail",
            )

    async def callback(nid, sid):
        return {"output": None, "error": None}

    executor = AsyncPlanExecutor(callback, enforcer=StubEnforcer())
    await executor.execute(plan)

    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, EnvelopeViolationReason)
    assert plan.suspension.reason.detail == "clearance fail"


# ---------------------------------------------------------------------------
# Trigger 5: ExplicitCancellation
# ---------------------------------------------------------------------------


def test_sync_explicit_cancellation_attaches_record():
    plan = _make_plan([_make_node("n1"), _make_node("n2")])
    plan.state = PlanState.EXECUTING

    executor = PlanExecutor(lambda nid, sid: {"output": None, "error": None})
    executor.cancel(
        plan,
        reason="user pressed stop",
        resume_hint="resume after data-quality review",
    )

    assert plan.state == PlanState.CANCELLED
    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, ExplicitCancellationReason)
    assert plan.suspension.reason.reason == "user pressed stop"
    assert plan.suspension.reason.resume_hint == "resume after data-quality review"
    # All nodes were skipped; pending_nodes captured pre-cancel
    assert plan.suspension.pending_nodes == ["n1", "n2"]


@pytest.mark.asyncio
async def test_async_explicit_cancellation_attaches_record():
    plan = _make_plan([_make_node("n1")])
    plan.state = PlanState.EXECUTING

    async def callback(nid, sid):
        return {"output": None, "error": None}

    executor = AsyncPlanExecutor(callback)
    await executor.cancel(
        plan,
        reason="quota exhausted",
        resume_hint="next billing cycle",
    )

    assert plan.suspension is not None
    assert isinstance(plan.suspension.reason, ExplicitCancellationReason)
    assert plan.suspension.reason.reason == "quota exhausted"


# ---------------------------------------------------------------------------
# resume() clears the record
# ---------------------------------------------------------------------------


def test_sync_resume_clears_suspension():
    plan = _make_plan([_make_node("n1")])
    plan.state = PlanState.EXECUTING

    executor = PlanExecutor(lambda nid, sid: {"output": None, "error": None})
    executor.suspend(
        plan,
        reason=ExplicitCancellationReason(
            reason="pause", resume_hint="resume immediately"
        ),
    )
    assert plan.suspension is not None

    executor.resume(plan)
    assert plan.suspension is None
    assert plan.state == PlanState.EXECUTING


@pytest.mark.asyncio
async def test_async_resume_clears_suspension():
    plan = _make_plan([_make_node("n1")])
    plan.state = PlanState.EXECUTING

    async def callback(nid, sid):
        return {"output": None, "error": None}

    executor = AsyncPlanExecutor(callback)
    await executor.suspend(
        plan,
        reason=CircuitBreakerTrippedReason(breaker_id="openai", triggering_node="n1"),
    )
    assert plan.suspension is not None

    await executor.resume(plan)
    assert plan.suspension is None


# ---------------------------------------------------------------------------
# Suspension survives Plan.to_dict / from_dict round-trip
#
# This is the cross-SDK wire test: a Python plan in the SUSPENDED state
# round-trips through dict and the SuspensionRecord is reconstructed.
# A Rust subscriber reading the dict MUST see the same field shapes.
# ---------------------------------------------------------------------------


def test_plan_dict_roundtrip_preserves_suspension():
    plan = _make_plan([_make_node("n1"), _make_node("n2")])
    plan.state = PlanState.EXECUTING

    executor = PlanExecutor(lambda nid, sid: {"output": None, "error": None})
    executor.cancel(plan, reason="audit", resume_hint="rerun next quarter")

    # Round-trip
    d = plan.to_dict()
    plan2 = Plan.from_dict(d)

    assert plan2.suspension is not None
    assert isinstance(plan2.suspension.reason, ExplicitCancellationReason)
    assert plan2.suspension.reason.reason == "audit"
    # Pre-cancel snapshot preserved
    assert sorted(plan2.suspension.pending_nodes) == ["n1", "n2"]

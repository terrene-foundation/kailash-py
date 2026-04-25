# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for kaizen.l3.plan.suspension.

Issue #598 — PlanSuspension parity (5-variant SuspensionReason)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kaizen.l3.plan.suspension import (
    BudgetExceededReason,
    CircuitBreakerTrippedReason,
    EnvelopeViolationReason,
    ExplicitCancellationReason,
    HumanApprovalGateReason,
    SuspensionRecord,
    suspension_reason_from_dict,
    suspension_reason_label,
    suspension_reason_to_dict,
)
from kaizen.l3.plan.types import (
    Plan,
    PlanNode,
    PlanNodeState,
    PlanState,
)


# ---------------------------------------------------------------------------
# Variant construction
# ---------------------------------------------------------------------------


def test_human_approval_gate_construction():
    r = HumanApprovalGateReason(held_node="n7", reason="manual review")
    assert r.kind == "human_approval_gate"
    assert r.held_node == "n7"
    assert r.reason == "manual review"


def test_circuit_breaker_tripped_construction():
    r = CircuitBreakerTrippedReason(
        breaker_id="openai-rate-limit",
        triggering_node="rag_query",
    )
    assert r.kind == "circuit_breaker_tripped"
    assert r.breaker_id == "openai-rate-limit"
    assert r.triggering_node == "rag_query"


def test_budget_exceeded_construction():
    r = BudgetExceededReason(
        dimension="financial",
        usage_pct=0.95,
        triggering_node="expensive_agent",
    )
    assert r.kind == "budget_exceeded"
    assert r.dimension == "financial"
    assert r.usage_pct == 0.95
    assert r.triggering_node == "expensive_agent"


def test_envelope_violation_construction():
    r = EnvelopeViolationReason(
        dimension="data_access",
        detail="clearance level mismatch",
        triggering_node="classified_doc_read",
    )
    assert r.kind == "envelope_violation"
    assert r.dimension == "data_access"
    assert r.detail == "clearance level mismatch"
    assert r.triggering_node == "classified_doc_read"


def test_explicit_cancellation_construction():
    r = ExplicitCancellationReason(
        reason="caller-initiated",
        resume_hint="resume after human review of dataset",
    )
    assert r.kind == "explicit_cancellation"
    assert r.reason == "caller-initiated"
    assert r.resume_hint == "resume after human review of dataset"


def test_variants_are_frozen():
    """Frozen dataclass blocks mutation — important for the audit trail."""
    r = HumanApprovalGateReason(held_node="n1", reason="x")
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        r.held_node = "n2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def test_label_matches_kind_for_all_5_variants():
    """Cross-SDK metric cardinality stability — labels must equal kind."""
    cases = [
        (
            HumanApprovalGateReason(held_node="n", reason="r"),
            "human_approval_gate",
        ),
        (
            CircuitBreakerTrippedReason(breaker_id="b", triggering_node="n"),
            "circuit_breaker_tripped",
        ),
        (
            BudgetExceededReason(dimension="d", usage_pct=0.9, triggering_node="n"),
            "budget_exceeded",
        ),
        (
            EnvelopeViolationReason(dimension="d", detail="x", triggering_node="n"),
            "envelope_violation",
        ),
        (
            ExplicitCancellationReason(reason="r", resume_hint="h"),
            "explicit_cancellation",
        ),
    ]
    for reason, expected_label in cases:
        assert suspension_reason_label(reason) == expected_label


# ---------------------------------------------------------------------------
# Wire-format round-trip
# ---------------------------------------------------------------------------


def test_human_approval_gate_round_trip():
    r = HumanApprovalGateReason(held_node="n7", reason="manual review")
    d = suspension_reason_to_dict(r)
    assert d == {
        "kind": "human_approval_gate",
        "held_node": "n7",
        "reason": "manual review",
    }
    r2 = suspension_reason_from_dict(d)
    assert r2 == r


def test_circuit_breaker_round_trip():
    r = CircuitBreakerTrippedReason(breaker_id="b", triggering_node="n")
    d = suspension_reason_to_dict(r)
    assert d == {
        "kind": "circuit_breaker_tripped",
        "breaker_id": "b",
        "triggering_node": "n",
    }
    r2 = suspension_reason_from_dict(d)
    assert r2 == r


def test_budget_exceeded_round_trip():
    r = BudgetExceededReason(dimension="financial", usage_pct=0.92, triggering_node="n")
    d = suspension_reason_to_dict(r)
    assert d == {
        "kind": "budget_exceeded",
        "dimension": "financial",
        "usage_pct": 0.92,
        "triggering_node": "n",
    }
    r2 = suspension_reason_from_dict(d)
    assert r2 == r


def test_envelope_violation_round_trip():
    r = EnvelopeViolationReason(
        dimension="data_access", detail="clearance fail", triggering_node="n"
    )
    d = suspension_reason_to_dict(r)
    assert d == {
        "kind": "envelope_violation",
        "dimension": "data_access",
        "detail": "clearance fail",
        "triggering_node": "n",
    }
    r2 = suspension_reason_from_dict(d)
    assert r2 == r


def test_explicit_cancellation_round_trip():
    r = ExplicitCancellationReason(reason="r", resume_hint="h")
    d = suspension_reason_to_dict(r)
    assert d == {
        "kind": "explicit_cancellation",
        "reason": "r",
        "resume_hint": "h",
    }
    r2 = suspension_reason_from_dict(d)
    assert r2 == r


def test_from_dict_rejects_missing_kind():
    with pytest.raises(ValueError, match="missing required 'kind'"):
        suspension_reason_from_dict({"held_node": "n", "reason": "r"})


def test_from_dict_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown SuspensionReason kind"):
        suspension_reason_from_dict({"kind": "made_up_variant"})


def test_from_dict_rejects_missing_required_field():
    # human_approval_gate variant requires held_node + reason
    with pytest.raises(KeyError):
        suspension_reason_from_dict({"kind": "human_approval_gate"})


# ---------------------------------------------------------------------------
# SuspensionRecord
# ---------------------------------------------------------------------------


def _make_plan_with_states(
    state_map: dict[str, PlanNodeState],
) -> Plan:
    """Build a Plan with nodes in the given states."""
    nodes: dict[str, PlanNode] = {}
    for node_id, state in state_map.items():
        nodes[node_id] = PlanNode(
            node_id=node_id,
            agent_spec_id="dummy",
            input_mapping={},
            state=state,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
        )
    return Plan(
        plan_id="p1",
        name="test",
        envelope={},
        gradient={},
        nodes=nodes,
        edges=[],
        state=PlanState.EXECUTING,
    )


def test_record_from_plan_partitions_node_states():
    plan = _make_plan_with_states(
        {
            "n_running1": PlanNodeState.RUNNING,
            "n_running2": PlanNodeState.RUNNING,
            "n_ready": PlanNodeState.READY,
            "n_pending": PlanNodeState.PENDING,
            "n_completed": PlanNodeState.COMPLETED,
            "n_failed": PlanNodeState.FAILED,
        }
    )
    reason = HumanApprovalGateReason(held_node="x", reason="y")
    record = SuspensionRecord.from_plan(reason, plan)
    assert record.running_nodes == ["n_running1", "n_running2"]
    assert record.ready_nodes == ["n_ready"]
    assert record.pending_nodes == ["n_pending"]


def test_record_lists_are_sorted_for_cross_sdk_stability():
    plan = _make_plan_with_states(
        {
            "z_run": PlanNodeState.RUNNING,
            "a_run": PlanNodeState.RUNNING,
            "m_run": PlanNodeState.RUNNING,
        }
    )
    record = SuspensionRecord.from_plan(
        ExplicitCancellationReason(reason="r", resume_hint="h"),
        plan,
    )
    assert record.running_nodes == ["a_run", "m_run", "z_run"]


def test_record_default_suspended_at_is_utc():
    plan = _make_plan_with_states({"n": PlanNodeState.PENDING})
    record = SuspensionRecord.from_plan(
        ExplicitCancellationReason(reason="r", resume_hint="h"),
        plan,
    )
    assert record.suspended_at.tzinfo is not None
    assert record.suspended_at.utcoffset().total_seconds() == 0


def test_record_with_resume_context_returns_copy():
    plan = _make_plan_with_states({"n": PlanNodeState.PENDING})
    record = SuspensionRecord.from_plan(
        ExplicitCancellationReason(reason="r", resume_hint="h"),
        plan,
    )
    record2 = record.with_resume_context({"retry": 3})
    assert record2.resume_context == {"retry": 3}
    assert record.resume_context is None  # original untouched
    assert record2.reason == record.reason
    assert record2.suspended_at == record.suspended_at


def test_record_to_dict_has_iso_suspended_at():
    plan = _make_plan_with_states({"n": PlanNodeState.PENDING})
    fixed = datetime(2026, 4, 25, 10, 30, 0, tzinfo=UTC)
    record = SuspensionRecord(
        reason=ExplicitCancellationReason(reason="r", resume_hint="h"),
        suspended_at=fixed,
        running_nodes=[],
        ready_nodes=[],
        pending_nodes=["n"],
        resume_context=None,
    )
    d = record.to_dict()
    assert d["suspended_at"] == "2026-04-25T10:30:00+00:00"
    assert d["pending_nodes"] == ["n"]
    assert d["reason"]["kind"] == "explicit_cancellation"


def test_record_round_trip_through_dict():
    plan = _make_plan_with_states(
        {"a": PlanNodeState.RUNNING, "b": PlanNodeState.PENDING}
    )
    record = SuspensionRecord.from_plan(
        BudgetExceededReason(
            dimension="financial", usage_pct=0.95, triggering_node="a"
        ),
        plan,
        resume_context={"agent_state": "awaiting_quota_lift"},
    )
    d = record.to_dict()
    record2 = SuspensionRecord.from_dict(d)
    assert record2.reason == record.reason
    assert record2.suspended_at == record.suspended_at
    assert record2.running_nodes == record.running_nodes
    assert record2.ready_nodes == record.ready_nodes
    assert record2.pending_nodes == record.pending_nodes
    assert record2.resume_context == record.resume_context


# ---------------------------------------------------------------------------
# Plan.suspension field
# ---------------------------------------------------------------------------


def test_plan_suspension_defaults_to_none():
    plan = _make_plan_with_states({"n": PlanNodeState.PENDING})
    assert plan.suspension is None


def test_plan_to_dict_round_trips_suspension():
    plan = _make_plan_with_states({"n": PlanNodeState.PENDING})
    plan.suspension = SuspensionRecord(
        reason=ExplicitCancellationReason(reason="r", resume_hint="h"),
        suspended_at=datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC),
        running_nodes=[],
        ready_nodes=[],
        pending_nodes=["n"],
        resume_context=None,
    )
    d = plan.to_dict()
    assert d["suspension"] is not None
    assert d["suspension"]["reason"]["kind"] == "explicit_cancellation"

    plan2 = Plan.from_dict(d)
    assert plan2.suspension is not None
    assert plan2.suspension.reason == plan.suspension.reason
    assert plan2.suspension.pending_nodes == ["n"]


def test_plan_to_dict_with_no_suspension_field():
    plan = _make_plan_with_states({"n": PlanNodeState.PENDING})
    d = plan.to_dict()
    assert d["suspension"] is None
    plan2 = Plan.from_dict(d)
    assert plan2.suspension is None


# ---------------------------------------------------------------------------
# Cross-SDK parity vectors
#
# These vectors are the canonical wire-format payloads. The sister Rust
# SDK (kailash-rs/crates/kailash-kaizen/src/l3/core/plan/types.rs) MUST
# produce the same shapes for the same logical inputs (modulo the
# suspended_at timestamp). Any field-name drift between SDKs MUST land
# in a single coordinated PR; this test is the structural contract.
# ---------------------------------------------------------------------------


CROSS_SDK_VECTORS = [
    # (description, wire_payload, expected_python_record_attrs)
    (
        "human_approval_gate canonical",
        {
            "kind": "human_approval_gate",
            "held_node": "n7",
            "reason": "manual review",
        },
        ("HumanApprovalGateReason", "n7", "manual review"),
    ),
    (
        "circuit_breaker_tripped canonical",
        {
            "kind": "circuit_breaker_tripped",
            "breaker_id": "openai-rate-limit",
            "triggering_node": "rag_query",
        },
        ("CircuitBreakerTrippedReason", "openai-rate-limit", "rag_query"),
    ),
    (
        "budget_exceeded canonical",
        {
            "kind": "budget_exceeded",
            "dimension": "financial",
            "usage_pct": 0.95,
            "triggering_node": "expensive_agent",
        },
        ("BudgetExceededReason", "financial", 0.95, "expensive_agent"),
    ),
    (
        "envelope_violation canonical (Python-only today, Rust follow-up)",
        {
            "kind": "envelope_violation",
            "dimension": "data_access",
            "detail": "clearance level mismatch",
            "triggering_node": "classified_doc_read",
        },
        ("EnvelopeViolationReason", "data_access", "clearance level mismatch"),
    ),
    (
        "explicit_cancellation canonical",
        {
            "kind": "explicit_cancellation",
            "reason": "caller-initiated",
            "resume_hint": "resume after human review of dataset",
        },
        (
            "ExplicitCancellationReason",
            "caller-initiated",
            "resume after human review of dataset",
        ),
    ),
]


@pytest.mark.parametrize("description,payload,expected_attrs", CROSS_SDK_VECTORS)
def test_cross_sdk_parity_vector(
    description: str,
    payload: dict,
    expected_attrs: tuple,
):
    """Each canonical wire payload deserializes to the right variant."""
    reason = suspension_reason_from_dict(payload)
    assert type(reason).__name__ == expected_attrs[0], (
        f"{description}: kind {payload['kind']!r} did NOT deserialize to "
        f"{expected_attrs[0]} (got {type(reason).__name__})"
    )
    # Round-trip back to dict — bytes-stable
    assert suspension_reason_to_dict(reason) == payload, (
        f"{description}: round-trip lost data; before={payload!r} "
        f"after={suspension_reason_to_dict(reason)!r}"
    )


def test_cross_sdk_full_record_vector():
    """A complete SuspensionRecord wire-format vector round-trips."""
    payload = {
        "reason": {
            "kind": "human_approval_gate",
            "held_node": "approval_node",
            "reason": "ML model output requires expert review",
        },
        "suspended_at": "2026-04-25T12:34:56+00:00",
        "running_nodes": ["a", "b"],
        "ready_nodes": ["c"],
        "pending_nodes": ["d", "e"],
        "resume_context": {"reviewer_id": "alice@example.com"},
    }
    record = SuspensionRecord.from_dict(payload)
    assert isinstance(record.reason, HumanApprovalGateReason)
    assert record.reason.held_node == "approval_node"
    assert record.suspended_at == datetime(2026, 4, 25, 12, 34, 56, tzinfo=UTC)
    assert record.running_nodes == ["a", "b"]
    assert record.ready_nodes == ["c"]
    assert record.pending_nodes == ["d", "e"]
    assert record.resume_context == {"reviewer_id": "alice@example.com"}
    # Round-trip
    assert record.to_dict() == payload

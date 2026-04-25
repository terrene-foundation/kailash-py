# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Plan suspension types — PACT N3 (resumable plan suspension).

PACT Normative Requirement N3 mandates that any plan which suspends
execution MUST be resumable from the exact suspension point. This module
provides the wire-level types that capture WHY a plan suspended and the
execution frontier needed to resume.

Cross-SDK parity reference:
``/Users/esperie/repos/loom/kailash-rs/crates/kailash-kaizen/src/l3/core/plan/types.rs``
lines 267-396 (``SuspensionReason`` + ``SuspensionRecord``). Field
shapes, tag spelling, and label strings MUST match the Rust contract for
a serialized SuspensionRecord round-tripped between SDKs to compare
equal modulo the timestamp.

Per issue #598, the Python SDK implements **five** suspension variants:

1. ``HumanApprovalGate`` — a node entered the Held gradient zone and an
   approver must act before it can proceed.
2. ``CircuitBreakerTripped`` — a downstream dependency circuit broke and
   execution paused while the breaker cools down.
3. ``BudgetExceeded`` — an envelope dimension hit its configured
   threshold (default 90%) and planning must decide whether to continue,
   re-plan, or escalate.
4. ``EnvelopeViolation`` — an envelope check returned BLOCKED for a
   reason other than budget threshold (clearance, classification,
   dimension policy). Distinct from ``BudgetExceeded`` because remediation
   differs (re-plan vs. escalate-and-cancel).
5. ``ExplicitCancellation`` — caller requested a graceful pause with a
   resume hint.

Spec reference: PACT envelope governance + EATP D6 cross-SDK semantic
parity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Union

__all__ = [
    "BudgetExceededReason",
    "CircuitBreakerTrippedReason",
    "EnvelopeViolationReason",
    "ExplicitCancellationReason",
    "HumanApprovalGateReason",
    "SuspensionReason",
    "SuspensionRecord",
    "suspension_reason_label",
    "suspension_reason_to_dict",
    "suspension_reason_from_dict",
]


# ---------------------------------------------------------------------------
# SuspensionReason variants
#
# Each variant is a frozen dataclass with a Literal ``kind`` discriminator.
# The Union type alias ``SuspensionReason`` ties them together as a tagged
# union. Serialization uses ``suspension_reason_to_dict`` /
# ``suspension_reason_from_dict`` which match the Rust serde contract
# ``#[serde(tag = "kind", rename_all = "snake_case")]``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HumanApprovalGateReason:
    """Human approval required (Held gradient zone).

    Mirrors Rust ``SuspensionReason::HumanApprovalGate { held_node, reason }``.
    """

    held_node: str
    reason: str
    kind: Literal["human_approval_gate"] = "human_approval_gate"


@dataclass(frozen=True)
class CircuitBreakerTrippedReason:
    """Circuit breaker for a tool, agent, or downstream service tripped.

    Mirrors Rust ``SuspensionReason::CircuitBreakerTripped { breaker_id,
    triggering_node }``.
    """

    breaker_id: str
    triggering_node: str
    kind: Literal["circuit_breaker_tripped"] = "circuit_breaker_tripped"


@dataclass(frozen=True)
class BudgetExceededReason:
    """Budget exceeded on one or more envelope dimensions.

    Mirrors Rust ``SuspensionReason::BudgetExceeded { dimension,
    usage_pct, triggering_node }``.

    ``usage_pct`` is on the 0.0..=1.0 scale (NOT 0..=100).
    """

    dimension: str
    usage_pct: float
    triggering_node: str
    kind: Literal["budget_exceeded"] = "budget_exceeded"


@dataclass(frozen=True)
class EnvelopeViolationReason:
    """Envelope check returned BLOCKED for a non-budget reason.

    Distinct from :class:`BudgetExceededReason`: this variant covers
    clearance failures, classification mismatches, dimension policy
    violations, and any other envelope-rejected execution where the cause
    is structural rather than threshold-driven. The L3 EnvelopeEnforcer
    emits this when a verdict tags BLOCKED with a non-budget dimension.

    Per issue #598, this is the Python-SDK 5th variant. The Rust SDK has
    four variants today; cross-SDK parity for ``EnvelopeViolation`` is
    tracked in the sibling kailash-rs issue. When Rust adds the variant,
    the wire-format ``kind`` tag MUST remain ``envelope_violation``.
    """

    dimension: str
    detail: str
    triggering_node: str
    kind: Literal["envelope_violation"] = "envelope_violation"


@dataclass(frozen=True)
class ExplicitCancellationReason:
    """Explicit cancellation with a resume hint.

    Mirrors Rust ``SuspensionReason::ExplicitCancellation { reason,
    resume_hint }``.
    """

    reason: str
    resume_hint: str
    kind: Literal["explicit_cancellation"] = "explicit_cancellation"


# Type alias for the tagged union. Callers MUST use isinstance to
# discriminate the variant rather than inspecting ``.kind`` (the kind
# string is a wire-format detail; isinstance is the structural form).
SuspensionReason = Union[
    HumanApprovalGateReason,
    CircuitBreakerTrippedReason,
    BudgetExceededReason,
    EnvelopeViolationReason,
    ExplicitCancellationReason,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_VARIANT_BY_KIND: dict[str, type] = {
    "human_approval_gate": HumanApprovalGateReason,
    "circuit_breaker_tripped": CircuitBreakerTrippedReason,
    "budget_exceeded": BudgetExceededReason,
    "envelope_violation": EnvelopeViolationReason,
    "explicit_cancellation": ExplicitCancellationReason,
}


def suspension_reason_label(reason: SuspensionReason) -> str:
    """Return the snake_case label for metrics / logs.

    Mirrors Rust ``SuspensionReason::label()`` so cross-SDK metric
    cardinality matches.
    """
    return reason.kind


def suspension_reason_to_dict(reason: SuspensionReason) -> dict[str, Any]:
    """Serialize a SuspensionReason to the cross-SDK wire format.

    Output shape matches the Rust serde contract
    ``#[serde(tag = "kind", rename_all = "snake_case")]``: a single
    flat object with a ``kind`` field plus the variant's data fields.

    Example::

        >>> r = HumanApprovalGateReason(held_node="n7", reason="manual review")
        >>> suspension_reason_to_dict(r)
        {'kind': 'human_approval_gate', 'held_node': 'n7', 'reason': 'manual review'}
    """
    if isinstance(reason, HumanApprovalGateReason):
        return {
            "kind": "human_approval_gate",
            "held_node": reason.held_node,
            "reason": reason.reason,
        }
    if isinstance(reason, CircuitBreakerTrippedReason):
        return {
            "kind": "circuit_breaker_tripped",
            "breaker_id": reason.breaker_id,
            "triggering_node": reason.triggering_node,
        }
    if isinstance(reason, BudgetExceededReason):
        return {
            "kind": "budget_exceeded",
            "dimension": reason.dimension,
            "usage_pct": reason.usage_pct,
            "triggering_node": reason.triggering_node,
        }
    if isinstance(reason, EnvelopeViolationReason):
        return {
            "kind": "envelope_violation",
            "dimension": reason.dimension,
            "detail": reason.detail,
            "triggering_node": reason.triggering_node,
        }
    if isinstance(reason, ExplicitCancellationReason):
        return {
            "kind": "explicit_cancellation",
            "reason": reason.reason,
            "resume_hint": reason.resume_hint,
        }
    raise TypeError(f"unknown SuspensionReason variant: {type(reason).__name__!r}")


def suspension_reason_from_dict(data: dict[str, Any]) -> SuspensionReason:
    """Deserialize a SuspensionReason from the cross-SDK wire format.

    Raises:
        ValueError: If ``kind`` is missing or not a known variant.
        TypeError: If a required field for the variant is missing.
    """
    if "kind" not in data:
        raise ValueError(
            "SuspensionReason payload missing required 'kind' discriminator"
        )
    kind = data["kind"]
    if kind == "human_approval_gate":
        return HumanApprovalGateReason(
            held_node=data["held_node"],
            reason=data["reason"],
        )
    if kind == "circuit_breaker_tripped":
        return CircuitBreakerTrippedReason(
            breaker_id=data["breaker_id"],
            triggering_node=data["triggering_node"],
        )
    if kind == "budget_exceeded":
        return BudgetExceededReason(
            dimension=data["dimension"],
            usage_pct=float(data["usage_pct"]),
            triggering_node=data["triggering_node"],
        )
    if kind == "envelope_violation":
        return EnvelopeViolationReason(
            dimension=data["dimension"],
            detail=data["detail"],
            triggering_node=data["triggering_node"],
        )
    if kind == "explicit_cancellation":
        return ExplicitCancellationReason(
            reason=data["reason"],
            resume_hint=data["resume_hint"],
        )
    raise ValueError(
        f"unknown SuspensionReason kind: {kind!r}; "
        f"expected one of {sorted(_VARIANT_BY_KIND)}"
    )


# ---------------------------------------------------------------------------
# SuspensionRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuspensionRecord:
    """Full suspension record captured when a plan enters Suspended state.

    Mirrors Rust ``SuspensionRecord`` (kailash-rs
    crates/kailash-kaizen/src/l3/core/plan/types.rs:340-396).

    Frozen: a SuspensionRecord captures the suspension snapshot and MUST
    NOT be mutated. Resume callers construct a fresh Plan state from the
    record's frontier; the record itself is discarded only when
    ``Plan.transition_to(Executing)`` succeeds (resume path) or
    ``Plan.transition_to(Cancelled)`` (cancel-from-suspended).

    Attributes:
        reason: Why the plan was suspended (tagged-union variant).
        suspended_at: Timestamp at which suspension was recorded
            (timezone-aware UTC; defaults to ``datetime.now(UTC)``).
        running_nodes: Nodes that were ``Running`` at suspension time.
            On resume these nodes retain their state and the executor
            will not re-spawn them. Sorted lexicographically for
            deterministic comparison across SDKs.
        ready_nodes: Nodes that were ``Ready`` at suspension time. These
            are the first candidates for re-scheduling on resume.
        pending_nodes: Nodes that were ``Pending`` at suspension time.
            Their gating relationships are preserved; they become Ready
            once their predecessors complete.
        resume_context: Opaque serialized context that re-entry callers
            may use to reconstitute extra state (e.g. conversation
            history, retry counter, external workflow id). Deserialized
            by the caller.
    """

    reason: SuspensionReason
    suspended_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    running_nodes: list[str] = field(default_factory=list)
    ready_nodes: list[str] = field(default_factory=list)
    pending_nodes: list[str] = field(default_factory=list)
    resume_context: Any | None = None

    @classmethod
    def from_plan(
        cls,
        reason: SuspensionReason,
        plan: Any,  # Plan; typed Any to avoid circular import
        *,
        resume_context: Any | None = None,
    ) -> SuspensionRecord:
        """Construct a record from the reason and plan-node snapshot.

        Mirrors Rust ``SuspensionRecord::new(reason, plan)``: enumerates
        node states, partitions into running/ready/pending lists, sorts
        each list lexicographically for cross-SDK comparison stability.

        Args:
            reason: Tagged-union variant identifying why the plan
                suspended.
            plan: A :class:`kaizen.l3.plan.types.Plan` instance.
                Typed ``Any`` to avoid a circular import; the function
                only requires ``plan.nodes`` (a mapping of node_id to a
                node with a ``.state`` attribute) and the
                :class:`PlanNodeState` enum values RUNNING / READY /
                PENDING.
            resume_context: Optional opaque payload that resume callers
                may use to reconstitute side-state.
        """
        # Local import to avoid cycle: types.py imports nothing from
        # suspension.py at module load; suspension.py defers its
        # PlanNodeState lookup to runtime.
        from kaizen.l3.plan.types import PlanNodeState

        running: list[str] = []
        ready: list[str] = []
        pending: list[str] = []
        for node_id, node in plan.nodes.items():
            if node.state == PlanNodeState.RUNNING:
                running.append(node_id)
            elif node.state == PlanNodeState.READY:
                ready.append(node_id)
            elif node.state == PlanNodeState.PENDING:
                pending.append(node_id)
        running.sort()
        ready.sort()
        pending.sort()
        return cls(
            reason=reason,
            suspended_at=datetime.now(UTC),
            running_nodes=running,
            ready_nodes=ready,
            pending_nodes=pending,
            resume_context=resume_context,
        )

    def with_resume_context(self, ctx: Any) -> SuspensionRecord:
        """Return a copy with ``resume_context`` set.

        Frozen-dataclass-friendly builder; mirrors Rust
        ``SuspensionRecord::with_resume_context``.
        """
        return SuspensionRecord(
            reason=self.reason,
            suspended_at=self.suspended_at,
            running_nodes=list(self.running_nodes),
            ready_nodes=list(self.ready_nodes),
            pending_nodes=list(self.pending_nodes),
            resume_context=ctx,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the cross-SDK JSON-compatible wire format."""
        return {
            "reason": suspension_reason_to_dict(self.reason),
            "suspended_at": self.suspended_at.isoformat(),
            "running_nodes": list(self.running_nodes),
            "ready_nodes": list(self.ready_nodes),
            "pending_nodes": list(self.pending_nodes),
            "resume_context": self.resume_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SuspensionRecord:
        """Deserialize from the cross-SDK JSON-compatible wire format."""
        suspended_at_raw = data.get("suspended_at")
        if isinstance(suspended_at_raw, datetime):
            suspended_at = suspended_at_raw
        elif isinstance(suspended_at_raw, str):
            suspended_at = datetime.fromisoformat(suspended_at_raw)
        else:
            suspended_at = datetime.now(UTC)
        return cls(
            reason=suspension_reason_from_dict(data["reason"]),
            suspended_at=suspended_at,
            running_nodes=list(data.get("running_nodes", [])),
            ready_nodes=list(data.get("ready_nodes", [])),
            pending_nodes=list(data.get("pending_nodes", [])),
            resume_context=data.get("resume_context"),
        )

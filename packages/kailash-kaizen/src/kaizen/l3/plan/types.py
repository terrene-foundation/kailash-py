# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Plan DAG type definitions.

All value types are frozen dataclasses per AD-L3-15.
Mutable entity types (PlanNode, Plan) use regular dataclasses with
validated state transitions.

Spec reference: workspaces/kaizen-l3/briefs/05-plan-dag.md Sections 2-3.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    "EdgeType",
    "Plan",
    "PlanEdge",
    "PlanEvent",
    "PlanModification",
    "PlanNode",
    "PlanNodeId",
    "PlanNodeOutput",
    "PlanNodeState",
    "PlanState",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

PlanNodeId = str


# ---------------------------------------------------------------------------
# EdgeType
# ---------------------------------------------------------------------------


class EdgeType(str, Enum):
    """Directed dependency between two plan nodes.

    DATA_DEPENDENCY: to cannot start until from completes successfully.
    COMPLETION_DEPENDENCY: to cannot start until from reaches terminal state.
    CO_START: to starts when from starts (advisory, soft coordination).
    """

    DATA_DEPENDENCY = "DATA_DEPENDENCY"
    COMPLETION_DEPENDENCY = "COMPLETION_DEPENDENCY"
    CO_START = "CO_START"


# ---------------------------------------------------------------------------
# PlanEdge (frozen value type)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanEdge:
    """A directed dependency edge between two plan nodes.

    Frozen per AD-L3-15. Self-edges are structurally representable
    but rejected by PlanValidator.
    """

    from_node: str
    to_node: str
    edge_type: EdgeType

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "edge_type": self.edge_type.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanEdge:
        return cls(
            from_node=data["from_node"],
            to_node=data["to_node"],
            edge_type=EdgeType(data["edge_type"]),
        )


# ---------------------------------------------------------------------------
# PlanNodeOutput (frozen value type)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanNodeOutput:
    """Reference to a specific output from another node.

    Frozen per AD-L3-15.
    """

    source_node: str
    output_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_node": self.source_node,
            "output_key": self.output_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanNodeOutput:
        return cls(
            source_node=data["source_node"],
            output_key=data["output_key"],
        )


# ---------------------------------------------------------------------------
# PlanNodeState
# ---------------------------------------------------------------------------


class PlanNodeState(str, Enum):
    """State of a single plan node.

    PENDING -> READY -> RUNNING -> COMPLETED
                                -> FAILED -> RUNNING (retry)
                                          -> SKIPPED
                                -> HELD   -> RUNNING (resolved, retry)
                                          -> FAILED  (resolution timeout)
                                          -> SKIPPED (skip held node)
    PENDING -> SKIPPED
    """

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    HELD = "HELD"


# Valid state transitions for PlanNodeState
_NODE_TRANSITIONS: dict[PlanNodeState, set[PlanNodeState]] = {
    PlanNodeState.PENDING: {PlanNodeState.READY, PlanNodeState.SKIPPED},
    PlanNodeState.READY: {PlanNodeState.RUNNING, PlanNodeState.SKIPPED},
    PlanNodeState.RUNNING: {
        PlanNodeState.COMPLETED,
        PlanNodeState.FAILED,
        PlanNodeState.HELD,
    },
    PlanNodeState.COMPLETED: set(),  # terminal
    PlanNodeState.FAILED: {
        PlanNodeState.RUNNING,
        PlanNodeState.SKIPPED,
        PlanNodeState.HELD,
    },  # retry, skip, or hold for resolution
    PlanNodeState.SKIPPED: set(),  # terminal
    PlanNodeState.HELD: {
        PlanNodeState.RUNNING,  # resolved, retry
        PlanNodeState.FAILED,  # resolution timeout
        PlanNodeState.SKIPPED,  # skip held node
    },
}


# ---------------------------------------------------------------------------
# PlanState
# ---------------------------------------------------------------------------


class PlanState(str, Enum):
    """State of the overall plan.

    Draft -> Validated -> Executing -> Completed/Failed/Suspended/Cancelled
    Validated -> Draft (on modification)
    Suspended -> Executing (resume) / Cancelled
    """

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


# Valid state transitions for PlanState
_PLAN_TRANSITIONS: dict[PlanState, set[PlanState]] = {
    PlanState.DRAFT: {PlanState.VALIDATED, PlanState.DRAFT},
    PlanState.VALIDATED: {PlanState.EXECUTING, PlanState.DRAFT},
    PlanState.EXECUTING: {
        PlanState.COMPLETED,
        PlanState.FAILED,
        PlanState.SUSPENDED,
        PlanState.CANCELLED,
    },
    PlanState.COMPLETED: set(),  # terminal
    PlanState.FAILED: set(),  # terminal
    PlanState.SUSPENDED: {PlanState.EXECUTING, PlanState.CANCELLED},
    PlanState.CANCELLED: set(),  # terminal
}


# ---------------------------------------------------------------------------
# PlanNode (mutable entity)
# ---------------------------------------------------------------------------


@dataclass
class PlanNode:
    """A single task within the plan, mapped to an AgentSpec.

    Mutable entity: state, instance_id, retry_count, output, error
    change during execution.
    """

    node_id: str
    agent_spec_id: str
    input_mapping: dict[str, PlanNodeOutput]
    state: PlanNodeState
    instance_id: str | None
    optional: bool
    retry_count: int
    output: Any
    error: str | None
    envelope: dict[str, Any] = field(default_factory=dict)

    def transition_to(self, new_state: PlanNodeState) -> None:
        """Validate and apply a state transition.

        Raises:
            ValueError: If the transition is not allowed.
        """
        allowed = _NODE_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid node state transition: {self.state.value} -> {new_state.value}. "
                f"Allowed transitions from {self.state.value}: "
                f"{sorted(s.value for s in allowed) if allowed else 'none (terminal state)'}"
            )
        self.state = new_state

    @property
    def is_terminal(self) -> bool:
        """True if this node is in a terminal state.

        HELD is NOT terminal — it indicates the node needs external
        resolution before it can proceed or be skipped.
        """
        return self.state in {
            PlanNodeState.COMPLETED,
            PlanNodeState.FAILED,
            PlanNodeState.SKIPPED,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "agent_spec_id": self.agent_spec_id,
            "input_mapping": {k: v.to_dict() for k, v in self.input_mapping.items()},
            "state": self.state.value,
            "instance_id": self.instance_id,
            "optional": self.optional,
            "retry_count": self.retry_count,
            "output": self.output,
            "error": self.error,
            "envelope": self.envelope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanNode:
        return cls(
            node_id=data["node_id"],
            agent_spec_id=data["agent_spec_id"],
            input_mapping={
                k: PlanNodeOutput.from_dict(v)
                for k, v in data.get("input_mapping", {}).items()
            },
            state=PlanNodeState(data["state"]),
            instance_id=data.get("instance_id"),
            optional=data.get("optional", False),
            retry_count=data.get("retry_count", 0),
            output=data.get("output"),
            error=data.get("error"),
            envelope=data.get("envelope", {}),
        )


# ---------------------------------------------------------------------------
# Plan (mutable entity)
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    """A directed acyclic graph of agent tasks with dependency edges.

    The plan is the unit of L3 execution.
    """

    plan_id: str
    name: str
    envelope: dict[str, Any]
    gradient: dict[str, Any]
    nodes: dict[str, PlanNode]
    edges: list[PlanEdge]
    state: PlanState
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def transition_to(self, new_state: PlanState) -> None:
        """Validate and apply a plan state transition.

        Raises:
            ValueError: If the transition is not allowed.
        """
        allowed = _PLAN_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid plan state transition: {self.state.value} -> {new_state.value}. "
                f"Allowed transitions from {self.state.value}: "
                f"{sorted(s.value for s in allowed) if allowed else 'none (terminal state)'}"
            )
        self.state = new_state
        self.modified_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "envelope": self.envelope,
            "gradient": self.gradient,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        return cls(
            plan_id=data["plan_id"],
            name=data["name"],
            envelope=data.get("envelope", {}),
            gradient=data.get("gradient", {}),
            nodes={k: PlanNode.from_dict(v) for k, v in data.get("nodes", {}).items()},
            edges=[PlanEdge.from_dict(e) for e in data.get("edges", [])],
            state=PlanState(data["state"]),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if isinstance(data.get("created_at"), str)
                else data.get("created_at", datetime.now(UTC))
            ),
            modified_at=(
                datetime.fromisoformat(data["modified_at"])
                if isinstance(data.get("modified_at"), str)
                else data.get("modified_at", datetime.now(UTC))
            ),
        )


# ---------------------------------------------------------------------------
# PlanEvent (discriminated union via tag)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanEvent:
    """Event emitted during plan execution.

    Discriminated union: the `tag` field identifies the variant,
    and `node_id` + `details` carry variant-specific data.
    """

    tag: str
    node_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    # --- Factory methods for all 16 event variants ---

    @classmethod
    def node_ready(cls, node_id: str) -> PlanEvent:
        return cls(tag="NodeReady", node_id=node_id)

    @classmethod
    def node_started(cls, node_id: str, instance_id: str) -> PlanEvent:
        return cls(
            tag="NodeStarted",
            node_id=node_id,
            details={"instance_id": instance_id},
        )

    @classmethod
    def node_completed(cls, node_id: str, output: Any) -> PlanEvent:
        return cls(
            tag="NodeCompleted",
            node_id=node_id,
            details={"output": output},
        )

    @classmethod
    def node_failed(cls, node_id: str, error: str, retryable: bool) -> PlanEvent:
        return cls(
            tag="NodeFailed",
            node_id=node_id,
            details={"error": error, "retryable": retryable},
        )

    @classmethod
    def node_retrying(cls, node_id: str, attempt: int, max_attempts: int) -> PlanEvent:
        return cls(
            tag="NodeRetrying",
            node_id=node_id,
            details={"attempt": attempt, "max_attempts": max_attempts},
        )

    @classmethod
    def node_held(cls, node_id: str, reason: str, zone: str) -> PlanEvent:
        return cls(
            tag="NodeHeld",
            node_id=node_id,
            details={"reason": reason, "zone": zone},
        )

    @classmethod
    def node_blocked(cls, node_id: str, dimension: str, detail: str) -> PlanEvent:
        return cls(
            tag="NodeBlocked",
            node_id=node_id,
            details={"dimension": dimension, "detail": detail},
        )

    @classmethod
    def node_skipped(cls, node_id: str, reason: str) -> PlanEvent:
        return cls(
            tag="NodeSkipped",
            node_id=node_id,
            details={"reason": reason},
        )

    @classmethod
    def node_flagged(cls, node_id: str, reason: str) -> PlanEvent:
        return cls(
            tag="NodeFlagged",
            node_id=node_id,
            details={"reason": reason},
        )

    @classmethod
    def plan_completed(cls, results: dict[str, Any]) -> PlanEvent:
        return cls(tag="PlanCompleted", details={"results": results})

    @classmethod
    def plan_failed(cls, failed_nodes: list[str], reason: str) -> PlanEvent:
        return cls(
            tag="PlanFailed",
            details={"failed_nodes": failed_nodes, "reason": reason},
        )

    @classmethod
    def plan_suspended(cls) -> PlanEvent:
        return cls(tag="PlanSuspended")

    @classmethod
    def plan_resumed(cls) -> PlanEvent:
        return cls(tag="PlanResumed")

    @classmethod
    def plan_cancelled(cls) -> PlanEvent:
        return cls(tag="PlanCancelled")

    @classmethod
    def envelope_warning(
        cls,
        node_id: str,
        dimension: str,
        usage_pct: float,
        zone: str,
    ) -> PlanEvent:
        return cls(
            tag="EnvelopeWarning",
            node_id=node_id,
            details={
                "dimension": dimension,
                "usage_pct": usage_pct,
                "zone": zone,
            },
        )

    @classmethod
    def modification_applied(cls, modification: dict[str, Any]) -> PlanEvent:
        return cls(
            tag="ModificationApplied",
            details={"modification": modification},
        )


# ---------------------------------------------------------------------------
# PlanModification (discriminated union via tag)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanModification:
    """Typed mutation for runtime plan changes.

    Discriminated union: the `tag` field identifies the variant,
    and `details` carries variant-specific data.
    """

    tag: str
    details: dict[str, Any] = field(default_factory=dict)

    # --- Factory methods for all 7 modification variants ---

    @classmethod
    def add_node(cls, node: PlanNode, edges: list[PlanEdge]) -> PlanModification:
        return cls(tag="AddNode", details={"node": node, "edges": edges})

    @classmethod
    def remove_node(cls, node_id: str) -> PlanModification:
        return cls(tag="RemoveNode", details={"node_id": node_id})

    @classmethod
    def replace_node(cls, old_node_id: str, new_node: PlanNode) -> PlanModification:
        return cls(
            tag="ReplaceNode",
            details={"old_node_id": old_node_id, "new_node": new_node},
        )

    @classmethod
    def add_edge(cls, edge: PlanEdge) -> PlanModification:
        return cls(tag="AddEdge", details={"edge": edge})

    @classmethod
    def remove_edge(cls, from_node: str, to_node: str) -> PlanModification:
        return cls(
            tag="RemoveEdge",
            details={"from_node": from_node, "to_node": to_node},
        )

    @classmethod
    def update_spec(cls, node_id: str, new_spec_id: str) -> PlanModification:
        return cls(
            tag="UpdateSpec",
            details={"node_id": node_id, "new_spec_id": new_spec_id},
        )

    @classmethod
    def skip_node(cls, node_id: str, reason: str) -> PlanModification:
        return cls(
            tag="SkipNode",
            details={"node_id": node_id, "reason": reason},
        )

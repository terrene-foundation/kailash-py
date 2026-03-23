"""
Local type definitions matching L3 SDK specs.

These types mirror the spec definitions from:
- M1-01: EnvelopeTracker (ConstraintEnvelope, PlanGradient, GradientZone)
- M1-03: Inter-Agent Messaging (L3Message variants)
- M1-04: AgentFactory (AgentSpec, AgentInstance, AgentState)
- M1-05: Plan DAG (Plan, PlanNode, PlanEdge, PlanState, PlanNodeState)

When the SDK teams deliver real implementations, these local types will be
replaced by imports from kailash-enterprise. All orchestration code programs
against these interfaces, so the swap is a single import change per file.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Envelope & Gradient (from spec 01 — EnvelopeTracker)
# ---------------------------------------------------------------------------


class GradientZone(Enum):
    """Verification gradient zone. Ordering: BLOCKED > HELD > FLAGGED > AUTO_APPROVED."""

    AUTO_APPROVED = "auto_approved"
    FLAGGED = "flagged"
    HELD = "held"
    BLOCKED = "blocked"

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, GradientZone):
            return NotImplemented
        order = {
            GradientZone.AUTO_APPROVED: 0,
            GradientZone.FLAGGED: 1,
            GradientZone.HELD: 2,
            GradientZone.BLOCKED: 3,
        }
        return order[self] > order[other]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, GradientZone):
            return NotImplemented
        return self == other or self > other


@dataclass
class DimensionGradient:
    """Per-dimension gradient thresholds overriding global budget thresholds."""

    flag_threshold: float = 0.80
    hold_threshold: float = 0.95

    def __post_init__(self) -> None:
        if not (0.0 <= self.flag_threshold < self.hold_threshold <= 1.0):
            raise ValueError(
                f"Invalid thresholds: flag={self.flag_threshold}, hold={self.hold_threshold}. "
                "Must satisfy 0.0 <= flag < hold <= 1.0"
            )


@dataclass
class PlanGradient:
    """Verification gradient configuration for plan execution.

    Set by the supervisor via the PACT envelope. Determines how failures,
    retries, and budget consumption are classified into gradient zones.
    """

    retry_budget: int = 2
    after_retry_exhaustion: GradientZone = GradientZone.HELD
    resolution_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=300))
    optional_node_failure: GradientZone = GradientZone.FLAGGED
    budget_flag_threshold: float = 0.80
    budget_hold_threshold: float = 0.95
    dimension_thresholds: dict[str, DimensionGradient] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.retry_budget < 0:
            raise ValueError(f"retry_budget must be >= 0, got {self.retry_budget}")
        if self.resolution_timeout.total_seconds() <= 0:
            raise ValueError("resolution_timeout must be positive")
        if self.after_retry_exhaustion not in (GradientZone.HELD, GradientZone.BLOCKED):
            raise ValueError(
                f"after_retry_exhaustion must be HELD or BLOCKED, "
                f"got {self.after_retry_exhaustion}"
            )
        if self.optional_node_failure == GradientZone.BLOCKED:
            raise ValueError("optional_node_failure cannot be BLOCKED; use a required node instead")
        if not (0.0 <= self.budget_flag_threshold < self.budget_hold_threshold <= 1.0):
            raise ValueError(
                f"Invalid budget thresholds: flag={self.budget_flag_threshold}, "
                f"hold={self.budget_hold_threshold}. Must satisfy 0 <= flag < hold <= 1.0"
            )


@dataclass(frozen=True)
class ConstraintEnvelope:
    """Simplified five-dimension constraint envelope per PACT spec.

    Frozen to prevent field reassignment after creation. The dimension dicts
    remain mutable for incremental construction (e.g., designer.py adjusts
    financial["limit"] after creation). This is a deliberate trade-off:
    frozen=True prevents wholesale field replacement while allowing dict
    mutation for the builder pattern.

    NaN/Inf validation: __post_init__ rejects non-finite values in known
    numeric fields (financial.limit, temporal.limit_seconds) to prevent
    governance bypass via NaN injection.

    Dimensions:
        financial: {"limit": float} -- monetary budget cap (default $1.00)
        operational: {"allowed": list[str], "blocked": list[str]} -- action allowlists/blocklists
        temporal: {"window_start": str, "window_end": str, "blackouts": list[str]}
        data_access: {"ceiling": str, "scopes": list[str]} -- data classification ceiling + scopes
        communication: {"recipients": list[str], "channels": list[str]} -- who/how to communicate
    """

    financial: dict[str, Any] = field(default_factory=lambda: {"limit": 1.0})
    operational: dict[str, Any] = field(default_factory=lambda: {"allowed": [], "blocked": []})
    temporal: dict[str, Any] = field(default_factory=dict)
    data_access: dict[str, Any] = field(
        default_factory=lambda: {"ceiling": "internal", "scopes": []}
    )
    communication: dict[str, Any] = field(
        default_factory=lambda: {"recipients": [], "channels": []}
    )

    def __post_init__(self) -> None:
        """Validate numeric fields in dimension dicts are finite."""
        import math

        limit = self.financial.get("limit")
        if (
            limit is not None
            and isinstance(limit, (int, float))
            and not math.isfinite(float(limit))
        ):
            raise ValueError(f"financial.limit must be finite, got {limit}")

        temporal_limit = self.temporal.get("limit_seconds")
        if (
            temporal_limit is not None
            and isinstance(temporal_limit, (int, float))
            and not math.isfinite(float(temporal_limit))
        ):
            raise ValueError(f"temporal.limit_seconds must be finite, got {temporal_limit}")


# ---------------------------------------------------------------------------
# Agent types (from spec 04 — AgentFactory)
# ---------------------------------------------------------------------------


class WaitReason(Enum):
    """Why an agent is in the Waiting state."""

    DELEGATION_RESPONSE = "delegation_response"
    HUMAN_APPROVAL = "human_approval"
    RESOURCE_AVAILABILITY = "resource_availability"


class TerminationReason(Enum):
    """Why an agent was forcibly terminated."""

    PARENT_TERMINATED = "parent_terminated"
    ENVELOPE_VIOLATION = "envelope_violation"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXPLICIT_TERMINATION = "explicit_termination"


@dataclass
class AgentStateData:
    """Payload data for agent state variants that carry additional information."""

    reason: str | None = None
    result: Any | None = None
    error: str | None = None
    wait_reason: WaitReason | None = None
    termination_reason: TerminationReason | None = None
    dimension: str | None = None
    detail: str | None = None
    by: str | None = None


class AgentState(Enum):
    """Lifecycle states for an agent instance."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"

    @property
    def is_terminal(self) -> bool:
        """Whether this state is a terminal state (no transitions out)."""
        return self in (AgentState.COMPLETED, AgentState.FAILED, AgentState.TERMINATED)


@dataclass
class MemoryConfig:
    """Configuration for memory backends attached to an agent instance."""

    session: bool = True
    shared: bool = False
    persistent: bool = False
    shared_namespace: str | None = None


@dataclass
class AgentSpec:
    """Blueprint for instantiating an agent at runtime.

    A value type that can be reused to spawn multiple instances. Contains
    everything needed except the LLM connection.
    """

    spec_id: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    envelope: ConstraintEnvelope = field(default_factory=ConstraintEnvelope)
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    max_lifetime: timedelta | None = None
    max_children: int | None = None
    max_depth: int | None = None
    required_context_keys: list[str] = field(default_factory=list)
    produced_context_keys: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentInstance:
    """A running agent entity with lifecycle tracking.

    Created by the factory at spawn time; uniquely identified and linked
    to its parent in the delegation hierarchy.
    """

    instance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    spec_id: str = ""
    parent_id: str | None = None
    state: AgentState = AgentState.PENDING
    state_data: AgentStateData = field(default_factory=AgentStateData)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active_envelope: ConstraintEnvelope = field(default_factory=ConstraintEnvelope)


# ---------------------------------------------------------------------------
# Plan DAG types (from spec 05 — Plan DAG)
# ---------------------------------------------------------------------------


class EdgeType(Enum):
    """Type of dependency between plan nodes."""

    DATA_DEPENDENCY = "data_dependency"
    COMPLETION_DEPENDENCY = "completion_dependency"
    CO_START = "co_start"


class PlanState(Enum):
    """Lifecycle state of a Plan."""

    DRAFT = "draft"
    VALIDATED = "validated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether this state is a terminal state."""
        return self in (PlanState.COMPLETED, PlanState.FAILED, PlanState.CANCELLED)


class PlanNodeState(Enum):
    """Lifecycle state of a single plan node."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    HELD = "held"

    @property
    def is_terminal(self) -> bool:
        """Whether this node state is terminal. HELD is NOT terminal."""
        return self in (PlanNodeState.COMPLETED, PlanNodeState.FAILED, PlanNodeState.SKIPPED)


@dataclass
class PlanNodeOutput:
    """Reference to a specific output from another node."""

    source_node: str
    output_key: str


@dataclass
class PlanNode:
    """A single task within the plan, mapped to an AgentSpec."""

    node_id: str
    agent_spec: AgentSpec
    input_mapping: dict[str, PlanNodeOutput] = field(default_factory=dict)
    state: PlanNodeState = PlanNodeState.PENDING
    instance_id: str | None = None
    optional: bool = False
    retry_count: int = 0
    output: Any | None = None
    error: str | None = None


@dataclass
class PlanEdge:
    """A directed dependency between two plan nodes."""

    from_node: str
    to_node: str
    edge_type: EdgeType = EdgeType.DATA_DEPENDENCY


@dataclass
class Plan:
    """A directed acyclic graph of agent tasks with dependency edges."""

    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    envelope: ConstraintEnvelope = field(default_factory=ConstraintEnvelope)
    gradient: PlanGradient = field(default_factory=PlanGradient)
    nodes: dict[str, PlanNode] = field(default_factory=dict)
    edges: list[PlanEdge] = field(default_factory=list)
    state: PlanState = PlanState.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    modified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Plan Modifications — discriminated union (from spec 05)
# ---------------------------------------------------------------------------


class PlanModificationType(Enum):
    """Types of plan modifications."""

    ADD_NODE = "add_node"
    REMOVE_NODE = "remove_node"
    REPLACE_NODE = "replace_node"
    ADD_EDGE = "add_edge"
    REMOVE_EDGE = "remove_edge"
    UPDATE_SPEC = "update_spec"
    SKIP_NODE = "skip_node"


@dataclass
class PlanModification:
    """A typed mutation that preserves audit trail.

    Uses a type tag + optional fields pattern to represent a discriminated union
    in Python dataclasses. Only the fields relevant to the modification type
    are populated.
    """

    modification_type: PlanModificationType
    node: PlanNode | None = None
    edges: list[PlanEdge] | None = None
    node_id: str | None = None
    old_node_id: str | None = None
    new_node: PlanNode | None = None
    edge: PlanEdge | None = None
    from_node: str | None = None
    to_node: str | None = None
    new_spec: AgentSpec | None = None
    reason: str | None = None

    @staticmethod
    def add_node(node: PlanNode, edges: list[PlanEdge] | None = None) -> PlanModification:
        """Create an AddNode modification."""
        return PlanModification(
            modification_type=PlanModificationType.ADD_NODE,
            node=node,
            edges=edges or [],
        )

    @staticmethod
    def remove_node(node_id: str) -> PlanModification:
        """Create a RemoveNode modification."""
        return PlanModification(
            modification_type=PlanModificationType.REMOVE_NODE,
            node_id=node_id,
        )

    @staticmethod
    def replace_node(old_node_id: str, new_node: PlanNode) -> PlanModification:
        """Create a ReplaceNode modification."""
        return PlanModification(
            modification_type=PlanModificationType.REPLACE_NODE,
            old_node_id=old_node_id,
            new_node=new_node,
        )

    @staticmethod
    def add_edge(edge: PlanEdge) -> PlanModification:
        """Create an AddEdge modification."""
        return PlanModification(
            modification_type=PlanModificationType.ADD_EDGE,
            edge=edge,
        )

    @staticmethod
    def remove_edge(from_node: str, to_node: str) -> PlanModification:
        """Create a RemoveEdge modification."""
        return PlanModification(
            modification_type=PlanModificationType.REMOVE_EDGE,
            from_node=from_node,
            to_node=to_node,
        )

    @staticmethod
    def update_spec(node_id: str, new_spec: AgentSpec) -> PlanModification:
        """Create an UpdateSpec modification."""
        return PlanModification(
            modification_type=PlanModificationType.UPDATE_SPEC,
            node_id=node_id,
            new_spec=new_spec,
        )

    @staticmethod
    def skip_node(node_id: str, reason: str) -> PlanModification:
        """Create a SkipNode modification."""
        return PlanModification(
            modification_type=PlanModificationType.SKIP_NODE,
            node_id=node_id,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# Plan Events — discriminated union (from spec 05)
# ---------------------------------------------------------------------------


class PlanEventType(Enum):
    """Types of events emitted during plan execution."""

    NODE_READY = "node_ready"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_RETRYING = "node_retrying"
    NODE_HELD = "node_held"
    NODE_BLOCKED = "node_blocked"
    NODE_SKIPPED = "node_skipped"
    NODE_FLAGGED = "node_flagged"
    PLAN_COMPLETED = "plan_completed"
    PLAN_FAILED = "plan_failed"
    PLAN_SUSPENDED = "plan_suspended"
    PLAN_RESUMED = "plan_resumed"
    PLAN_CANCELLED = "plan_cancelled"
    ENVELOPE_WARNING = "envelope_warning"
    MODIFICATION_APPLIED = "modification_applied"


@dataclass
class PlanEvent:
    """An event emitted during plan execution.

    Uses a type tag + optional fields pattern. Only the fields relevant to
    the event type are populated.
    """

    event_type: PlanEventType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    node_id: str | None = None
    instance_id: str | None = None
    output: Any | None = None
    error: str | None = None
    retryable: bool | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    reason: str | None = None
    zone: GradientZone | None = None
    dimension: str | None = None
    usage_pct: float | None = None
    results: dict[str, Any] | None = None
    failed_nodes: list[str] | None = None
    modification: PlanModification | None = None


# ---------------------------------------------------------------------------
# L3 Message variants (from spec 03 — Inter-Agent Messaging)
# ---------------------------------------------------------------------------


class Priority(Enum):
    """Execution priority for L3 messages."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EscalationSeverity(Enum):
    """Severity levels for escalation messages."""

    WARNING = "warning"
    BLOCKED = "blocked"
    BUDGET_ALERT = "budget_alert"
    CRITICAL = "critical"


@dataclass
class ResourceSnapshot:
    """Current cumulative resource consumption snapshot."""

    financial_spent: float = 0.0
    actions_executed: int = 0
    elapsed_seconds: float = 0.0
    messages_sent: int = 0


class L3MessageType(Enum):
    """L3 message type discriminator."""

    DELEGATION = "delegation"
    STATUS = "status"
    CLARIFICATION = "clarification"
    COMPLETION = "completion"
    ESCALATION = "escalation"
    SYSTEM = "system"


@dataclass
class DelegationPayload:
    """Parent assigns a task to a child."""

    task_description: str
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    envelope: ConstraintEnvelope = field(default_factory=ConstraintEnvelope)
    deadline: datetime | None = None
    priority: Priority = Priority.NORMAL


@dataclass
class StatusPayload:
    """Child reports progress to parent."""

    phase: str
    resource_usage: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    progress_pct: float | None = None


@dataclass
class ClarificationPayload:
    """Child asks parent a question, or parent responds."""

    question: str
    blocking: bool = False
    is_response: bool = False
    options: list[str] | None = None


@dataclass
class CompletionPayload:
    """Child reports task completion with results."""

    result: Any = None
    success: bool = True
    context_updates: dict[str, Any] = field(default_factory=dict)
    resource_consumed: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    error_detail: str | None = None


@dataclass
class EscalationPayload:
    """Child escalates a problem it cannot resolve within its envelope."""

    severity: EscalationSeverity
    problem_description: str
    attempted_mitigations: list[str] = field(default_factory=list)
    suggested_action: str | None = None
    violating_dimension: str | None = None


class SystemSubtype(Enum):
    """Subtypes for system-level messages."""

    TERMINATION_NOTICE = "termination_notice"
    ENVELOPE_VIOLATION = "envelope_violation"
    HEARTBEAT_REQUEST = "heartbeat_request"
    HEARTBEAT_RESPONSE = "heartbeat_response"
    CHANNEL_CLOSING = "channel_closing"


@dataclass
class SystemPayload:
    """Infrastructure-level system message."""

    subtype: SystemSubtype
    reason: str | None = None
    dimension: str | None = None
    detail: str | None = None
    instance_id: str | None = None


@dataclass
class L3Message:
    """An L3 inter-agent message with typed payload.

    The message_type discriminator determines which payload field is populated.
    """

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_instance: str = ""
    to_instance: str = ""
    message_type: L3MessageType = L3MessageType.STATUS
    correlation_id: str | None = None
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ttl: timedelta | None = None

    # Payload — exactly one is populated based on message_type
    delegation: DelegationPayload | None = None
    status: StatusPayload | None = None
    clarification: ClarificationPayload | None = None
    completion: CompletionPayload | None = None
    escalation: EscalationPayload | None = None
    system: SystemPayload | None = None

    @staticmethod
    def create_delegation(
        from_instance: str,
        to_instance: str,
        payload: DelegationPayload,
        correlation_id: str | None = None,
    ) -> L3Message:
        """Create a Delegation message."""
        return L3Message(
            from_instance=from_instance,
            to_instance=to_instance,
            message_type=L3MessageType.DELEGATION,
            correlation_id=correlation_id,
            delegation=payload,
        )

    @staticmethod
    def create_status(
        from_instance: str,
        to_instance: str,
        payload: StatusPayload,
        correlation_id: str | None = None,
    ) -> L3Message:
        """Create a Status message."""
        return L3Message(
            from_instance=from_instance,
            to_instance=to_instance,
            message_type=L3MessageType.STATUS,
            correlation_id=correlation_id,
            status=payload,
        )

    @staticmethod
    def create_clarification(
        from_instance: str,
        to_instance: str,
        payload: ClarificationPayload,
        correlation_id: str | None = None,
    ) -> L3Message:
        """Create a Clarification message."""
        return L3Message(
            from_instance=from_instance,
            to_instance=to_instance,
            message_type=L3MessageType.CLARIFICATION,
            correlation_id=correlation_id,
            clarification=payload,
        )

    @staticmethod
    def create_completion(
        from_instance: str,
        to_instance: str,
        payload: CompletionPayload,
        correlation_id: str | None = None,
    ) -> L3Message:
        """Create a Completion message."""
        return L3Message(
            from_instance=from_instance,
            to_instance=to_instance,
            message_type=L3MessageType.COMPLETION,
            correlation_id=correlation_id,
            completion=payload,
        )

    @staticmethod
    def create_escalation(
        from_instance: str,
        to_instance: str,
        payload: EscalationPayload,
        correlation_id: str | None = None,
    ) -> L3Message:
        """Create an Escalation message."""
        return L3Message(
            from_instance=from_instance,
            to_instance=to_instance,
            message_type=L3MessageType.ESCALATION,
            correlation_id=correlation_id,
            escalation=payload,
        )

    @staticmethod
    def create_system(
        from_instance: str,
        to_instance: str,
        payload: SystemPayload,
    ) -> L3Message:
        """Create a System message."""
        return L3Message(
            from_instance=from_instance,
            to_instance=to_instance,
            message_type=L3MessageType.SYSTEM,
            system=payload,
        )

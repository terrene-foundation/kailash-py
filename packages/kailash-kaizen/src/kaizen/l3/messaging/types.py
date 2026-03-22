# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 message types — typed payloads for inter-agent communication.

Extends the existing MessageType with L3 variants per Brief 03 (corrected
by F-02 to use Brief 03's 6 variants, not Brief 00's original 4).

All payload types are frozen dataclasses per AD-L3-15 (value types).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    "ClarificationPayload",
    "CompletionPayload",
    "DelegationPayload",
    "EscalationPayload",
    "EscalationSeverity",
    "MessageEnvelope",
    "MessageType",
    "Priority",
    "ResourceSnapshot",
    "StatusPayload",
    "SystemPayload",
    "SystemSubtype",
]


# ---------------------------------------------------------------------------
# MessageType Enum (L0-L2 + L3 variants)
# ---------------------------------------------------------------------------


class MessageType(str, Enum):
    """Message type for inter-agent communication.

    L0-L2 variants (existing):
        TASK_REQUEST, TASK_RESPONSE, STATUS_UPDATE,
        CAPABILITY_QUERY, CAPABILITY_RESPONSE, ERROR

    L3 variants (new — per Brief 03):
        DELEGATION, STATUS, CLARIFICATION, COMPLETION,
        ESCALATION, SYSTEM

    Forward-compatibility contract: consumers MUST handle unknown variants
    with a default/fallback. New variants may be added in future versions.
    """

    # L0-L2 variants
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    STATUS_UPDATE = "status_update"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"
    ERROR = "error"

    # L3 variants
    DELEGATION = "delegation"
    STATUS = "status"
    CLARIFICATION = "clarification"
    COMPLETION = "completion"
    ESCALATION = "escalation"
    SYSTEM = "system"


class Priority(int, Enum):
    """Execution priority for L3 messages."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EscalationSeverity(str, Enum):
    """Severity levels for escalation payloads."""

    BLOCKED = "blocked"
    WARNING = "warning"
    BUDGET_ALERT = "budget_alert"
    CRITICAL = "critical"


class SystemSubtype(str, Enum):
    """Subtypes for system payloads."""

    TERMINATION_NOTICE = "termination_notice"
    ENVELOPE_VIOLATION = "envelope_violation"
    HEARTBEAT_REQUEST = "heartbeat_request"
    HEARTBEAT_RESPONSE = "heartbeat_response"
    CHANNEL_CLOSING = "channel_closing"


# ---------------------------------------------------------------------------
# Resource Snapshot (shared by Status and Completion payloads)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceSnapshot:
    """Current cumulative resource consumption."""

    financial_spent: float = 0.0
    actions_executed: int = 0
    elapsed_seconds: float = 0.0
    messages_sent: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "financial_spent": self.financial_spent,
            "actions_executed": self.actions_executed,
            "elapsed_seconds": self.elapsed_seconds,
            "messages_sent": self.messages_sent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceSnapshot:
        return cls(
            financial_spent=float(data.get("financial_spent", 0.0)),
            actions_executed=int(data.get("actions_executed", 0)),
            elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
            messages_sent=int(data.get("messages_sent", 0)),
        )


# ---------------------------------------------------------------------------
# L3 Typed Payloads (frozen value types per AD-L3-15)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DelegationPayload:
    """Parent assigns a task to a child."""

    task_description: str
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    envelope: Any = None  # ConstraintEnvelopeConfig
    deadline: datetime | None = None
    priority: Priority = Priority.NORMAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.DELEGATION.value,
            "task_description": self.task_description,
            "context_snapshot": self.context_snapshot,
            "envelope": (
                self.envelope.to_dict()  # type: ignore[union-attr]
                if self.envelope is not None and hasattr(self.envelope, "to_dict")
                else self.envelope
            ),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "priority": self.priority.value,
        }


@dataclass(frozen=True)
class StatusPayload:
    """Child reports progress to parent."""

    phase: str
    resource_usage: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    progress_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.STATUS.value,
            "phase": self.phase,
            "resource_usage": self.resource_usage.to_dict(),
            "progress_pct": self.progress_pct,
        }


@dataclass(frozen=True)
class ClarificationPayload:
    """Child asks parent a question, or parent responds."""

    question: str
    blocking: bool = True
    is_response: bool = False
    options: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.CLARIFICATION.value,
            "question": self.question,
            "blocking": self.blocking,
            "is_response": self.is_response,
            "options": self.options,
        }


@dataclass(frozen=True)
class CompletionPayload:
    """Child reports task completion."""

    result: Any = None
    success: bool = True
    context_updates: dict[str, Any] = field(default_factory=dict)
    resource_consumed: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.COMPLETION.value,
            "result": self.result,
            "success": self.success,
            "context_updates": self.context_updates,
            "resource_consumed": self.resource_consumed.to_dict(),
            "error_detail": self.error_detail,
        }


@dataclass(frozen=True)
class EscalationPayload:
    """Child escalates a problem it cannot resolve."""

    severity: EscalationSeverity
    problem_description: str
    attempted_mitigations: list[str] = field(default_factory=list)
    suggested_action: str | None = None
    violating_dimension: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.ESCALATION.value,
            "severity": self.severity.value,
            "problem_description": self.problem_description,
            "attempted_mitigations": self.attempted_mitigations,
            "suggested_action": self.suggested_action,
            "violating_dimension": self.violating_dimension,
        }


@dataclass(frozen=True)
class SystemPayload:
    """Infrastructure-level messages not initiated by LLM decision-making."""

    subtype: SystemSubtype
    reason: str = ""
    dimension: str = ""
    detail: str = ""
    instance_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": MessageType.SYSTEM.value,
            "subtype": self.subtype.value,
            "reason": self.reason,
            "dimension": self.dimension,
            "detail": self.detail,
            "instance_id": self.instance_id,
        }


# Payload union type for type hints
L3Payload = (
    DelegationPayload
    | StatusPayload
    | ClarificationPayload
    | CompletionPayload
    | EscalationPayload
    | SystemPayload
)


# ---------------------------------------------------------------------------
# Message Envelope (transport wrapper)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MessageEnvelope:
    """Transport wrapper for L3 messages.

    Every L3 message is wrapped in a MessageEnvelope for routing.
    """

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_instance: str = ""
    to_instance: str = ""
    payload: L3Payload | None = None
    correlation_id: str | None = None
    sent_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ttl_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # P6

    @property
    def message_type(self) -> MessageType | None:
        """Infer message type from payload."""
        if isinstance(self.payload, DelegationPayload):
            return MessageType.DELEGATION
        elif isinstance(self.payload, StatusPayload):
            return MessageType.STATUS
        elif isinstance(self.payload, ClarificationPayload):
            return MessageType.CLARIFICATION
        elif isinstance(self.payload, CompletionPayload):
            return MessageType.COMPLETION
        elif isinstance(self.payload, EscalationPayload):
            return MessageType.ESCALATION
        elif isinstance(self.payload, SystemPayload):
            return MessageType.SYSTEM
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from_instance": self.from_instance,
            "to_instance": self.to_instance,
            "payload": self.payload.to_dict() if self.payload else None,
            "correlation_id": self.correlation_id,
            "sent_at": self.sent_at.isoformat(),
            "ttl_seconds": self.ttl_seconds,
            "metadata": self.metadata,
        }

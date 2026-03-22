# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Agent instance and lifecycle state machine.

Implements the AgentInstance entity type and the 6-state lifecycle machine
with validated transitions per Brief 04, Section 2.2-2.5.

State machine:
    Pending -> Running, Terminated
    Running -> Waiting, Completed, Failed, Terminated
    Waiting -> Running, Terminated
    Terminal states (no transitions out): Completed, Failed, Terminated
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    "AgentInstance",
    "AgentLifecycleState",
    "InvalidStateTransitionError",
    "TerminationReason",
    "WaitReason",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WaitReason(str, Enum):
    """Why an agent is in the Waiting state."""

    DELEGATION_RESPONSE = "delegation_response"
    HUMAN_APPROVAL = "human_approval"
    RESOURCE_AVAILABILITY = "resource_availability"
    CLARIFICATION_PENDING = "clarification_pending"  # AD-L3-11 / F-03
    ESCALATION_PENDING = "escalation_pending"  # AD-L3-11 / F-03


class TerminationReason(str, Enum):
    """Why an agent was forcibly terminated."""

    PARENT_TERMINATED = "parent_terminated"
    ENVELOPE_VIOLATION = "envelope_violation"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXPLICIT_TERMINATION = "explicit_termination"


# ---------------------------------------------------------------------------
# Lifecycle State (discriminated union via tagged dataclasses)
# ---------------------------------------------------------------------------


class _StateTag(str, Enum):
    """Internal tag for AgentLifecycleState discrimination."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass(frozen=True)
class AgentLifecycleState:
    """Lifecycle state for an agent instance.

    Uses a tag + optional payload pattern instead of separate subclasses.
    Terminal states: COMPLETED, FAILED, TERMINATED.
    """

    tag: _StateTag
    wait_reason: WaitReason | None = None
    wait_context: str | None = None  # message_id or hold_id as string
    result: Any = None  # JSON value for Completed
    error: str | None = None  # for Failed
    termination_reason: TerminationReason | None = None  # for Terminated
    termination_detail: str | None = None

    @property
    def is_terminal(self) -> bool:
        """True if this is a terminal state (no transitions out)."""
        return self.tag in (_StateTag.COMPLETED, _StateTag.FAILED, _StateTag.TERMINATED)

    @property
    def name(self) -> str:
        """Human-readable state name."""
        return self.tag.value

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {"tag": self.tag.value}
        if self.wait_reason is not None:
            d["wait_reason"] = self.wait_reason.value
        if self.wait_context is not None:
            d["wait_context"] = self.wait_context
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        if self.termination_reason is not None:
            d["termination_reason"] = self.termination_reason.value
        if self.termination_detail is not None:
            d["termination_detail"] = self.termination_detail
        return d

    # --- Factory methods ---

    @classmethod
    def pending(cls) -> AgentLifecycleState:
        return cls(tag=_StateTag.PENDING)

    @classmethod
    def running(cls) -> AgentLifecycleState:
        return cls(tag=_StateTag.RUNNING)

    @classmethod
    def waiting(
        cls, reason: WaitReason, context: str | None = None
    ) -> AgentLifecycleState:
        return cls(tag=_StateTag.WAITING, wait_reason=reason, wait_context=context)

    @classmethod
    def completed(cls, result: Any = None) -> AgentLifecycleState:
        return cls(tag=_StateTag.COMPLETED, result=result)

    @classmethod
    def failed(cls, error: str) -> AgentLifecycleState:
        return cls(tag=_StateTag.FAILED, error=error)

    @classmethod
    def terminated(
        cls, reason: TerminationReason, detail: str | None = None
    ) -> AgentLifecycleState:
        return cls(
            tag=_StateTag.TERMINATED,
            termination_reason=reason,
            termination_detail=detail,
        )


# ---------------------------------------------------------------------------
# Valid Transitions
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[_StateTag, frozenset[_StateTag]] = {
    _StateTag.PENDING: frozenset({_StateTag.RUNNING, _StateTag.TERMINATED}),
    _StateTag.RUNNING: frozenset(
        {_StateTag.WAITING, _StateTag.COMPLETED, _StateTag.FAILED, _StateTag.TERMINATED}
    ),
    _StateTag.WAITING: frozenset({_StateTag.RUNNING, _StateTag.TERMINATED}),
    # Terminal states: no transitions out
    _StateTag.COMPLETED: frozenset(),
    _StateTag.FAILED: frozenset(),
    _StateTag.TERMINATED: frozenset(),
}


class InvalidStateTransitionError(ValueError):
    """Raised when an invalid state transition is attempted."""

    def __init__(
        self, from_state: AgentLifecycleState, to_state: AgentLifecycleState
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition: {from_state.tag.value} -> {to_state.tag.value}. "
            f"Valid transitions from {from_state.tag.value}: "
            f"{sorted(t.value for t in _VALID_TRANSITIONS[from_state.tag])}"
        )


def validate_transition(
    from_state: AgentLifecycleState, to_state: AgentLifecycleState
) -> None:
    """Validate a state transition. Raises InvalidStateTransitionError if invalid."""
    if to_state.tag not in _VALID_TRANSITIONS[from_state.tag]:
        raise InvalidStateTransitionError(from_state, to_state)


# ---------------------------------------------------------------------------
# AgentInstance (mutable entity type — behind asyncio.Lock per AD-L3-04)
# ---------------------------------------------------------------------------


@dataclass
class AgentInstance:
    """A running agent entity with lifecycle tracking.

    Created by AgentFactory at spawn time. Each instance is uniquely
    identified and linked to its parent in the delegation hierarchy.

    This is a mutable entity type (not frozen) per AD-L3-15. Mutations
    are protected by asyncio.Lock in the AgentInstanceRegistry.
    """

    instance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    spec_id: str = ""
    parent_id: str | None = None  # None only for root agent
    state: AgentLifecycleState = field(default_factory=AgentLifecycleState.pending)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    envelope: Any = (
        None  # ConstraintEnvelopeConfig, typed as Any to avoid circular imports
    )

    def transition_to(self, new_state: AgentLifecycleState) -> None:
        """Transition to a new lifecycle state.

        Args:
            new_state: The target state.

        Raises:
            InvalidStateTransitionError: If the transition is not valid.
        """
        validate_transition(self.state, new_state)
        self.state = new_state

    @property
    def is_terminal(self) -> bool:
        """True if the instance is in a terminal state."""
        return self.state.is_terminal

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "instance_id": self.instance_id,
            "spec_id": self.spec_id,
            "parent_id": self.parent_id,
            "state": self.state.to_dict(),
            "created_at": self.created_at.isoformat(),
            "envelope": (
                self.envelope.to_dict()  # type: ignore[union-attr]
                if self.envelope is not None and hasattr(self.envelope, "to_dict")
                else self.envelope
            ),
        }

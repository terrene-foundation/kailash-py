"""
Core types for the State Persistence System.

Defines agent state, checkpoint metadata, and state snapshots.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


@dataclass
class AgentState:
    """
    Complete agent state at a checkpoint.

    Captures all information needed to resume agent execution from this point.
    """

    # Identification
    checkpoint_id: str = field(default_factory=lambda: f"ckpt_{uuid.uuid4().hex[:12]}")
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    step_number: int = 0

    # Conversation state
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    memory_contents: dict[str, Any] = field(default_factory=dict)

    # Execution state
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    completed_actions: list[dict[str, Any]] = field(default_factory=list)

    # Permission state (from TODO-160)
    budget_spent_usd: float = 0.0
    approval_history: list[dict[str, Any]] = field(default_factory=list)

    # Tool state
    tool_usage_counts: dict[str, int] = field(default_factory=dict)
    tool_results_cache: dict[str, Any] = field(default_factory=dict)

    # Specialist state (from ADR-013)
    active_specialists: list[str] = field(default_factory=list)
    specialist_invocations: list[dict[str, Any]] = field(default_factory=list)

    # Workflow state (Kailash SDK)
    workflow_run_id: str | None = None
    workflow_state: dict[str, Any] = field(default_factory=dict)

    # Control protocol state (from ADR-011)
    control_protocol_state: dict[str, Any] = field(default_factory=dict)

    # Hook contexts (from ADR-014)
    registered_hooks: list[dict[str, Any]] = field(default_factory=list)
    hook_event_history: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    parent_checkpoint_id: str | None = None  # For forking
    status: Literal["running", "completed", "failed", "interrupted"] = "running"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert state to dictionary for serialization.

        Returns:
            Dictionary representation of agent state
        """
        result = {}
        for field_name, field_type in self.__annotations__.items():
            value = getattr(self, field_name)

            # Convert datetime to ISO format
            if isinstance(value, datetime):
                result[field_name] = value.isoformat()
            else:
                result[field_name] = value

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        """
        Create AgentState from dictionary.

        Args:
            data: Dictionary representation of state

        Returns:
            AgentState instance
        """
        # Convert ISO timestamp back to datetime
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        return cls(**data)


@dataclass
class CheckpointMetadata:
    """
    Lightweight metadata for checkpoint listing.

    Used for efficient checkpoint discovery without loading full state.
    """

    checkpoint_id: str
    agent_id: str
    timestamp: datetime
    step_number: int
    status: str
    size_bytes: int
    parent_checkpoint_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary"""
        return {
            "checkpoint_id": self.checkpoint_id,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "step_number": self.step_number,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "parent_checkpoint_id": self.parent_checkpoint_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointMetadata":
        """Create metadata from dictionary"""
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])

        return cls(**data)


@dataclass
class StateSnapshot:
    """
    Immutable snapshot of agent state at a point in time.

    Used for debugging and state inspection without modifying checkpoints.
    """

    state: AgentState
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot_reason: str = "manual"

    def get_summary(self) -> dict[str, Any]:
        """Get human-readable summary of snapshot"""
        return {
            "checkpoint_id": self.state.checkpoint_id,
            "agent_id": self.state.agent_id,
            "step_number": self.state.step_number,
            "status": self.state.status,
            "conversation_turns": len(self.state.conversation_history),
            "pending_actions": len(self.state.pending_actions),
            "completed_actions": len(self.state.completed_actions),
            "budget_spent_usd": self.state.budget_spent_usd,
            "snapshot_reason": self.snapshot_reason,
            "created_at": self.created_at.isoformat(),
        }


# Export all public types
__all__ = [
    "AgentState",
    "CheckpointMetadata",
    "StateSnapshot",
]

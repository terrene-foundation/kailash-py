"""Session state models for Enterprise-App integration.

Defines the state models for tracking agent execution sessions.

See: TODO-204 Enterprise-App Streaming Integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionStatus(Enum):
    """Status of a session."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class ToolInvocation:
    """Record of a tool invocation during session."""

    tool_name: str
    tool_call_id: str
    input: Dict[str, Any]
    output: Any = None
    error: Optional[str] = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ended_at: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolInvocation":
        """Create from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            tool_call_id=data["tool_call_id"],
            input=data["input"],
            output=data.get("output"),
            error=data.get("error"),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            ended_at=data.get("ended_at"),
            duration_ms=data.get("duration_ms", 0),
        )


@dataclass
class SubagentCall:
    """Record of a subagent call during session."""

    subagent_id: str
    subagent_name: str
    task: str
    parent_agent_id: str
    trust_chain_id: str
    capabilities: List[str] = field(default_factory=list)
    model: Optional[str] = None
    status: str = "running"  # running, completed, error, timeout
    output: Optional[str] = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ended_at: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "subagent_id": self.subagent_id,
            "subagent_name": self.subagent_name,
            "task": self.task,
            "parent_agent_id": self.parent_agent_id,
            "trust_chain_id": self.trust_chain_id,
            "capabilities": self.capabilities,
            "model": self.model,
            "status": self.status,
            "output": self.output,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentCall":
        """Create from dictionary."""
        return cls(
            subagent_id=data["subagent_id"],
            subagent_name=data["subagent_name"],
            task=data["task"],
            parent_agent_id=data["parent_agent_id"],
            trust_chain_id=data["trust_chain_id"],
            capabilities=data.get("capabilities", []),
            model=data.get("model"),
            status=data.get("status", "running"),
            output=data.get("output"),
            tokens_used=data.get("tokens_used", 0),
            cost_usd=data.get("cost_usd", 0.0),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            ended_at=data.get("ended_at"),
            duration_ms=data.get("duration_ms", 0),
        )


@dataclass
class Message:
    """A message in the conversation history."""

    role: str  # user, assistant, system
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SessionState:
    """Complete state of an execution session.

    Tracks all state needed for:
    - Session resume/pause
    - Cost attribution
    - Audit trail
    - Progress visualization

    Example:
        >>> state = SessionState(
        ...     session_id="session-123",
        ...     agent_id="agent-001",
        ...     trust_chain_id="chain-abc",
        ... )
        >>> state.add_message(Message(role="user", content="Hello"))
        >>> state.tokens_used = 100
    """

    session_id: str
    agent_id: str
    trust_chain_id: str

    # Status and timing
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_activity_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ended_at: Optional[str] = None

    # Conversation history
    messages: List[Message] = field(default_factory=list)

    # Tool and subagent tracking
    tool_invocations: List[ToolInvocation] = field(default_factory=list)
    subagent_calls: List[SubagentCall] = field(default_factory=list)

    # Metrics
    tokens_used: int = 0
    cost_usd: float = 0.0
    cycles_used: int = 0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    agent_name: Optional[str] = None
    task: Optional[str] = None

    @property
    def cost_usd_cents(self) -> int:
        """Get cost in cents for API compatibility."""
        return int(self.cost_usd * 100)

    @property
    def duration_ms(self) -> int:
        """Calculate session duration in milliseconds."""
        start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        if self.ended_at:
            end = datetime.fromisoformat(self.ended_at.replace("Z", "+00:00"))
        else:
            end = datetime.now(timezone.utc)
        return int((end - start).total_seconds() * 1000)

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation history."""
        self.messages.append(message)
        self.last_activity_at = datetime.now(timezone.utc).isoformat()

    def add_tool_invocation(self, invocation: ToolInvocation) -> None:
        """Add a tool invocation record."""
        self.tool_invocations.append(invocation)
        self.last_activity_at = datetime.now(timezone.utc).isoformat()

    def add_subagent_call(self, call: SubagentCall) -> None:
        """Add a subagent call record."""
        self.subagent_calls.append(call)
        self.last_activity_at = datetime.now(timezone.utc).isoformat()

    def update_metrics(
        self,
        tokens_added: int = 0,
        cost_added_usd: float = 0.0,
        cycles_added: int = 0,
    ) -> None:
        """Update session metrics."""
        self.tokens_used += tokens_added
        self.cost_usd += cost_added_usd
        self.cycles_used += cycles_added
        self.last_activity_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state to dictionary."""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "trust_chain_id": self.trust_chain_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "ended_at": self.ended_at,
            "messages": [m.to_dict() for m in self.messages],
            "tool_invocations": [t.to_dict() for t in self.tool_invocations],
            "subagent_calls": [s.to_dict() for s in self.subagent_calls],
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "cost_usd_cents": self.cost_usd_cents,
            "cycles_used": self.cycles_used,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "agent_name": self.agent_name,
            "task": self.task,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Create session state from dictionary."""
        state = cls(
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            trust_chain_id=data["trust_chain_id"],
            status=SessionStatus(data.get("status", "active")),
            started_at=data.get("started_at", datetime.now(timezone.utc).isoformat()),
            last_activity_at=data.get(
                "last_activity_at", datetime.now(timezone.utc).isoformat()
            ),
            ended_at=data.get("ended_at"),
            tokens_used=data.get("tokens_used", 0),
            cost_usd=data.get("cost_usd", 0.0),
            cycles_used=data.get("cycles_used", 0),
            metadata=data.get("metadata", {}),
            agent_name=data.get("agent_name"),
            task=data.get("task"),
        )

        # Restore messages
        for msg_data in data.get("messages", []):
            state.messages.append(Message.from_dict(msg_data))

        # Restore tool invocations
        for tool_data in data.get("tool_invocations", []):
            state.tool_invocations.append(ToolInvocation.from_dict(tool_data))

        # Restore subagent calls
        for subagent_data in data.get("subagent_calls", []):
            state.subagent_calls.append(SubagentCall.from_dict(subagent_data))

        return state


@dataclass
class SessionSummary:
    """Summary of a completed session.

    Returned when a session ends, containing totals and key metrics.
    """

    session_id: str
    agent_id: str
    status: SessionStatus
    started_at: str
    ended_at: str
    duration_ms: int

    # Totals
    total_tokens: int
    total_cost_usd: float
    total_cost_cents: int
    total_cycles: int
    total_messages: int
    total_tool_calls: int
    total_subagent_calls: int

    # Key results
    final_output: Optional[str] = None
    error_message: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize summary to dictionary."""
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_cost_cents": self.total_cost_cents,
            "total_cycles": self.total_cycles,
            "total_messages": self.total_messages,
            "total_tool_calls": self.total_tool_calls,
            "total_subagent_calls": self.total_subagent_calls,
            "final_output": self.final_output,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_session_state(
        cls,
        state: SessionState,
        final_output: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> "SessionSummary":
        """Create summary from session state."""
        return cls(
            session_id=state.session_id,
            agent_id=state.agent_id,
            status=state.status,
            started_at=state.started_at,
            ended_at=state.ended_at or datetime.now(timezone.utc).isoformat(),
            duration_ms=state.duration_ms,
            total_tokens=state.tokens_used,
            total_cost_usd=state.cost_usd,
            total_cost_cents=state.cost_usd_cents,
            total_cycles=state.cycles_used,
            total_messages=len(state.messages),
            total_tool_calls=len(state.tool_invocations),
            total_subagent_calls=len(state.subagent_calls),
            final_output=final_output,
            error_message=error_message,
            metadata=state.metadata,
        )


__all__ = [
    "SessionStatus",
    "Message",
    "ToolInvocation",
    "SubagentCall",
    "SessionState",
    "SessionSummary",
]

"""Execution event types for autonomous agent runtime.

Defines event types emitted during autonomous execution including
subagent spawning, cost tracking, and execution milestones.

Provides the 10 core event types required for Enterprise-App integration:
- started, thinking, message, tool_use, tool_result
- subagent_spawn, cost_update, progress, completed, error

See: ADR-013 Specialist System, TODO-203 Task/Skill Tools, TODO-204 Enterprise-App Streaming
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(Enum):
    """Types of execution events.

    Core Enterprise-App events (10 types):
    - STARTED: Execution begins
    - THINKING: Agent reasoning
    - MESSAGE: Agent response
    - TOOL_USE: Before tool execution
    - TOOL_RESULT: After tool execution
    - SUBAGENT_SPAWN: When delegation occurs
    - COST_UPDATE: After each LLM call
    - PROGRESS: During execution steps
    - COMPLETED: Execution ends
    - ERROR: On failure

    Additional internal events:
    - SUBAGENT_COMPLETE, SUBAGENT_ERROR: Subagent lifecycle
    - SKILL_INVOKE, SKILL_COMPLETE: Skill invocation
    - CYCLE_START, CYCLE_COMPLETE: Cycle tracking
    - TOOL_START, TOOL_COMPLETE, TOOL_ERROR: Detailed tool tracking
    - THOUGHT: Structured reasoning step
    """

    # === Enterprise-App Core Events (10) ===
    STARTED = "started"
    THINKING = "thinking"
    MESSAGE = "message"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    SUBAGENT_SPAWN = "subagent_spawn"
    COST_UPDATE = "cost_update"
    PROGRESS = "progress"
    COMPLETED = "completed"
    ERROR = "error"

    # === Additional Internal Events ===
    # Subagent lifecycle
    SUBAGENT_COMPLETE = "subagent_complete"
    SUBAGENT_ERROR = "subagent_error"

    # Skill invocation
    SKILL_INVOKE = "skill_invoke"
    SKILL_COMPLETE = "skill_complete"

    # Execution milestones (legacy aliases)
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    CYCLE_START = "cycle_start"
    CYCLE_COMPLETE = "cycle_complete"

    # Detailed tool execution
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    TOOL_ERROR = "tool_error"

    # Structured thinking step
    THOUGHT = "thought"


@dataclass
class ExecutionEvent:
    """Base class for execution events.

    All events share common metadata for tracking and correlation.
    """

    session_id: str
    event_type: EventType = field(default=EventType.EXECUTION_START)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class SubagentSpawnEvent(ExecutionEvent):
    """Event emitted when a subagent is spawned.

    This is the critical event for Enterprise-App integration, enabling:
    - Progress visualization (TaskGraph)
    - Cost attribution
    - Trust chain propagation
    - Audit trail

    Example:
        >>> event = SubagentSpawnEvent(
        ...     session_id="session-123",
        ...     subagent_id="subagent-456",
        ...     subagent_name="code-reviewer",
        ...     task="Review the authentication module",
        ...     parent_agent_id="agent-001",
        ...     trust_chain_id="chain-789",
        ...     capabilities=["Read", "Glob", "Grep"],
        ... )
    """

    subagent_id: str = ""
    subagent_name: str = ""
    task: str = ""
    parent_agent_id: str = ""
    trust_chain_id: str = ""
    capabilities: List[str] = field(default_factory=list)
    model: Optional[str] = None
    max_turns: Optional[int] = None
    run_in_background: bool = False

    def __post_init__(self):
        self.event_type = EventType.SUBAGENT_SPAWN

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "subagent_id": self.subagent_id,
                "subagent_name": self.subagent_name,
                "task": self.task,
                "parent_agent_id": self.parent_agent_id,
                "trust_chain_id": self.trust_chain_id,
                "capabilities": self.capabilities,
                "model": self.model,
                "max_turns": self.max_turns,
                "run_in_background": self.run_in_background,
            }
        )
        return data


@dataclass
class SubagentCompleteEvent(ExecutionEvent):
    """Event emitted when a subagent completes execution."""

    subagent_id: str = ""
    parent_agent_id: str = ""
    status: str = "completed"  # completed, error, interrupted, timeout
    output: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    cycles_used: int = 0
    duration_ms: int = 0
    error_message: Optional[str] = None

    def __post_init__(self):
        self.event_type = EventType.SUBAGENT_COMPLETE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "subagent_id": self.subagent_id,
                "parent_agent_id": self.parent_agent_id,
                "status": self.status,
                "output": self.output,
                "tokens_used": self.tokens_used,
                "cost_usd": self.cost_usd,
                "cycles_used": self.cycles_used,
                "duration_ms": self.duration_ms,
                "error_message": self.error_message,
            }
        )
        return data


@dataclass
class SkillInvokeEvent(ExecutionEvent):
    """Event emitted when a skill is invoked."""

    skill_name: str = ""
    skill_description: str = ""
    agent_id: str = ""
    args: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = EventType.SKILL_INVOKE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "skill_name": self.skill_name,
                "skill_description": self.skill_description,
                "agent_id": self.agent_id,
                "args": self.args,
            }
        )
        return data


@dataclass
class SkillCompleteEvent(ExecutionEvent):
    """Event emitted when a skill invocation completes."""

    skill_name: str = ""
    agent_id: str = ""
    success: bool = True
    content_loaded: bool = False
    content_size: int = 0
    additional_files_count: int = 0
    error_message: Optional[str] = None

    def __post_init__(self):
        self.event_type = EventType.SKILL_COMPLETE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "skill_name": self.skill_name,
                "agent_id": self.agent_id,
                "success": self.success,
                "content_loaded": self.content_loaded,
                "content_size": self.content_size,
                "additional_files_count": self.additional_files_count,
                "error_message": self.error_message,
            }
        )
        return data


@dataclass
class CostUpdateEvent(ExecutionEvent):
    """Event emitted when cost tracking is updated."""

    agent_id: str = ""
    tokens_added: int = 0
    cost_added_usd: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    def __post_init__(self):
        self.event_type = EventType.COST_UPDATE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "agent_id": self.agent_id,
                "tokens_added": self.tokens_added,
                "cost_added_usd": self.cost_added_usd,
                "total_tokens": self.total_tokens,
                "total_cost_usd": self.total_cost_usd,
            }
        )
        return data


# ============================================================================
# Enterprise-App Core Event Types (TODO-204)
# ============================================================================


@dataclass
class StartedEvent(ExecutionEvent):
    """Event emitted when execution begins.

    Enterprise-App uses this to initialize the execution UI.

    Example:
        >>> event = StartedEvent(
        ...     session_id="session-123",
        ...     execution_id="exec-456",
        ...     agent_id="agent-001",
        ...     agent_name="Financial Analyst",
        ... )
    """

    execution_id: str = ""
    agent_id: str = ""
    agent_name: str = ""
    trust_chain_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.STARTED

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "trust_chain_id": self.trust_chain_id,
            }
        )
        return data


@dataclass
class ThinkingEvent(ExecutionEvent):
    """Event emitted during agent reasoning.

    Used to show the agent's thought process in the UI.

    Example:
        >>> event = ThinkingEvent(
        ...     session_id="session-123",
        ...     content="Let me analyze the data structure...",
        ... )
    """

    content: str = ""
    execution_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.THINKING

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "content": self.content,
                "execution_id": self.execution_id,
            }
        )
        return data


@dataclass
class MessageEvent(ExecutionEvent):
    """Event emitted when agent produces a response.

    Represents a message in the conversation.

    Example:
        >>> event = MessageEvent(
        ...     session_id="session-123",
        ...     role="assistant",
        ...     content="Based on my analysis, I recommend...",
        ... )
    """

    role: str = "assistant"  # assistant, user, system
    content: str = ""
    execution_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.MESSAGE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "role": self.role,
                "content": self.content,
                "execution_id": self.execution_id,
            }
        )
        return data


@dataclass
class ToolUseEvent(ExecutionEvent):
    """Event emitted before tool execution.

    Used to show which tool is being invoked and with what input.

    Example:
        >>> event = ToolUseEvent(
        ...     session_id="session-123",
        ...     tool="read_file",
        ...     input={"path": "/data/report.txt"},
        ... )
    """

    tool: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    execution_id: str = ""
    tool_call_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.TOOL_USE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "tool": self.tool,
                "input": self.input,
                "execution_id": self.execution_id,
                "tool_call_id": self.tool_call_id,
            }
        )
        return data


@dataclass
class ToolResultEvent(ExecutionEvent):
    """Event emitted after tool execution.

    Contains the tool's output or error.

    Example:
        >>> event = ToolResultEvent(
        ...     session_id="session-123",
        ...     tool="read_file",
        ...     output="File contents here...",
        ...     error=None,
        ... )
    """

    tool: str = ""
    output: Any = None
    error: Optional[str] = None
    execution_id: str = ""
    tool_call_id: str = ""
    duration_ms: int = 0

    def __post_init__(self):
        self.event_type = EventType.TOOL_RESULT

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "tool": self.tool,
                "output": self.output,
                "error": self.error,
                "execution_id": self.execution_id,
                "tool_call_id": self.tool_call_id,
                "duration_ms": self.duration_ms,
            }
        )
        return data


@dataclass
class ProgressEvent(ExecutionEvent):
    """Event emitted during execution steps.

    Used to show progress in the UI.

    Example:
        >>> event = ProgressEvent(
        ...     session_id="session-123",
        ...     percentage=50,
        ...     step="Analyzing data",
        ...     details="Processing file 5 of 10",
        ... )
    """

    percentage: int = 0  # 0-100
    step: str = ""
    details: str = ""
    execution_id: str = ""

    def __post_init__(self):
        self.event_type = EventType.PROGRESS

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "percentage": self.percentage,
                "step": self.step,
                "details": self.details,
                "execution_id": self.execution_id,
            }
        )
        return data


@dataclass
class CompletedEvent(ExecutionEvent):
    """Event emitted when execution ends successfully.

    Contains final metrics for the execution.

    Example:
        >>> event = CompletedEvent(
        ...     session_id="session-123",
        ...     execution_id="exec-456",
        ...     total_tokens=1500,
        ...     total_cost_cents=45,
        ... )
    """

    execution_id: str = ""
    total_tokens: int = 0
    total_cost_cents: int = 0
    total_cost_usd: float = 0.0
    duration_ms: int = 0
    cycles_used: int = 0
    tools_used: int = 0
    subagents_spawned: int = 0

    def __post_init__(self):
        self.event_type = EventType.COMPLETED

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "total_tokens": self.total_tokens,
                "total_cost_cents": self.total_cost_cents,
                "total_cost_usd": self.total_cost_usd,
                "duration_ms": self.duration_ms,
                "cycles_used": self.cycles_used,
                "tools_used": self.tools_used,
                "subagents_spawned": self.subagents_spawned,
            }
        )
        return data


@dataclass
class ErrorEvent(ExecutionEvent):
    """Event emitted on execution failure.

    Contains error details for debugging.

    Example:
        >>> event = ErrorEvent(
        ...     session_id="session-123",
        ...     execution_id="exec-456",
        ...     message="API rate limit exceeded",
        ...     error_type="RateLimitError",
        ... )
    """

    execution_id: str = ""
    message: str = ""
    error_type: str = ""
    stack_trace: Optional[str] = None
    recoverable: bool = False

    def __post_init__(self):
        self.event_type = EventType.ERROR

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        data = super().to_dict()
        data.update(
            {
                "execution_id": self.execution_id,
                "message": self.message,
                "error_type": self.error_type,
                "stack_trace": self.stack_trace,
                "recoverable": self.recoverable,
            }
        )
        return data


__all__ = [
    # Core enum and base
    "EventType",
    "ExecutionEvent",
    # Enterprise-App Core Events (TODO-204)
    "StartedEvent",
    "ThinkingEvent",
    "MessageEvent",
    "ToolUseEvent",
    "ToolResultEvent",
    "ProgressEvent",
    "CompletedEvent",
    "ErrorEvent",
    # Subagent events (TODO-203)
    "SubagentSpawnEvent",
    "SubagentCompleteEvent",
    # Skill events (TODO-203)
    "SkillInvokeEvent",
    "SkillCompleteEvent",
    # Cost tracking
    "CostUpdateEvent",
]

"""
Execution Context and Result Types for Runtime Abstraction Layer

Provides normalized types for inputs (ExecutionContext) and outputs (ExecutionResult)
that work across all autonomous agent runtimes.

These types enable runtime-agnostic code while preserving runtime-specific capabilities
through the metadata field.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionStatus(Enum):
    """Status of an autonomous agent execution.

    Used to indicate how and why an execution completed, enabling
    appropriate handling of different termination conditions.
    """

    COMPLETE = "complete"
    """Task finished successfully with expected output."""

    INTERRUPTED = "interrupted"
    """User or system interrupted the execution."""

    ERROR = "error"
    """Execution error occurred (tool failure, validation error, etc.)."""

    MAX_CYCLES = "max_cycles"
    """Cycle/iteration limit reached without completion."""

    BUDGET_EXCEEDED = "budget_exceeded"
    """Token or cost budget exceeded."""

    TIMEOUT = "timeout"
    """Time limit reached."""

    PENDING = "pending"
    """Execution is still in progress (for streaming/async)."""


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation during execution.

    Captures the complete lifecycle of a tool call including timing,
    result, and any errors that occurred.

    Attributes:
        name: Tool name as invoked
        arguments: Arguments passed to the tool
        result: Tool output (if successful)
        status: "executed", "denied", "error", or "pending"
        duration_ms: Execution time in milliseconds
        error: Error message if status is "error"
        timestamp: When the tool was called
    """

    name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    status: str = "pending"
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCallRecord":
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            name=data["name"],
            arguments=data.get("arguments", {}),
            result=data.get("result"),
            status=data.get("status", "pending"),
            duration_ms=data.get("duration_ms"),
            error=data.get("error"),
            timestamp=timestamp,
        )


@dataclass
class ExecutionContext:
    """Normalized input context for autonomous agent execution.

    Provides a unified interface for specifying tasks, tools, constraints,
    and preferences that works across all runtime adapters.

    The context is designed to be serializable for persistence and
    transmission between services.

    Attributes:
        task: The task or instruction for the agent
        session_id: Unique identifier for this execution session
        tools: List of tool definitions in Kaizen format
        memory_context: Pre-loaded memory or context for the agent
        system_prompt: System-level instructions (if runtime supports)
        conversation_history: Prior conversation messages
        max_cycles: Maximum Think-Act-Observe-Decide cycles
        max_tokens: Maximum tokens for completion
        budget_usd: Maximum cost in USD
        timeout_seconds: Maximum execution time
        permission_mode: "auto", "confirm_all", "deny_dangerous"
        pre_approved_tools: List of pre-approved tool names
        preferred_model: Preferred model identifier
        preferred_runtime: Preferred runtime name
        metadata: Extension point for runtime-specific data
    """

    task: str
    session_id: str = ""
    tools: List[Dict[str, Any]] = field(default_factory=list)
    memory_context: Optional[str] = None
    system_prompt: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    max_cycles: int = 50
    max_tokens: Optional[int] = None
    budget_usd: Optional[float] = None
    timeout_seconds: Optional[float] = None
    permission_mode: str = "auto"
    pre_approved_tools: List[str] = field(default_factory=list)
    preferred_model: Optional[str] = None
    preferred_runtime: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.session_id:
            import uuid

            self.session_id = str(uuid.uuid4())

    def has_budget_constraints(self) -> bool:
        """Check if any budget constraints are set."""
        return any(
            [
                self.max_tokens is not None,
                self.budget_usd is not None,
                self.timeout_seconds is not None,
            ]
        )

    def has_tool_requirements(self) -> bool:
        """Check if specific tools are required."""
        return len(self.tools) > 0

    def requires_capability(self, capability: str) -> bool:
        """Check if context requires a specific capability.

        Analyzes the context to determine if a capability is needed.
        """
        capability_lower = capability.lower()

        # Check tools for capability hints
        for tool in self.tools:
            tool_name = tool.get("name", "").lower()
            if capability_lower in tool_name:
                return True

        # Check task for capability keywords
        task_lower = self.task.lower()

        capability_keywords = {
            "vision": ["image", "screenshot", "picture", "photo", "visual"],
            "audio": ["audio", "sound", "voice", "speech", "listen"],
            "web_access": ["fetch", "download", "url", "http", "website"],
            "file_access": ["read", "write", "file", "directory", "folder"],
            "code_execution": ["run", "execute", "bash", "command", "script"],
        }

        if capability_lower in capability_keywords:
            return any(kw in task_lower for kw in capability_keywords[capability_lower])

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task": self.task,
            "session_id": self.session_id,
            "tools": self.tools,
            "memory_context": self.memory_context,
            "system_prompt": self.system_prompt,
            "conversation_history": self.conversation_history,
            "max_cycles": self.max_cycles,
            "max_tokens": self.max_tokens,
            "budget_usd": self.budget_usd,
            "timeout_seconds": self.timeout_seconds,
            "permission_mode": self.permission_mode,
            "pre_approved_tools": self.pre_approved_tools,
            "preferred_model": self.preferred_model,
            "preferred_runtime": self.preferred_runtime,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionContext":
        """Create from dictionary."""
        return cls(
            task=data["task"],
            session_id=data.get("session_id", ""),
            tools=data.get("tools", []),
            memory_context=data.get("memory_context"),
            system_prompt=data.get("system_prompt"),
            conversation_history=data.get("conversation_history", []),
            max_cycles=data.get("max_cycles", 50),
            max_tokens=data.get("max_tokens"),
            budget_usd=data.get("budget_usd"),
            timeout_seconds=data.get("timeout_seconds"),
            permission_mode=data.get("permission_mode", "auto"),
            pre_approved_tools=data.get("pre_approved_tools", []),
            preferred_model=data.get("preferred_model"),
            preferred_runtime=data.get("preferred_runtime"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ExecutionResult:
    """Normalized output from autonomous agent execution.

    Provides a unified result format that works across all runtime adapters,
    capturing the output, status, resource usage, and execution details.

    Attributes:
        output: The final output/response from the agent
        status: Execution status (complete, error, interrupted, etc.)
        tool_calls: List of tool invocations during execution
        tokens_used: Total tokens consumed
        cost_usd: Total cost in USD
        cycles_used: Number of Think-Act-Observe-Decide cycles
        duration_ms: Total execution time in milliseconds
        runtime_name: Name of the runtime that executed
        model_used: Model identifier used for execution
        session_id: Session identifier
        error_message: Error details if status is ERROR
        error_type: Type/category of error
        metadata: Extension point for runtime-specific data
    """

    output: str
    status: ExecutionStatus
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    cycles_used: int = 0
    duration_ms: Optional[float] = None
    runtime_name: str = ""
    model_used: str = ""
    session_id: str = ""
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """Check if execution completed successfully."""
        return self.status == ExecutionStatus.COMPLETE

    @property
    def is_error(self) -> bool:
        """Check if execution ended in error."""
        return self.status == ExecutionStatus.ERROR

    def get_successful_tool_calls(self) -> List[ToolCallRecord]:
        """Get only successfully executed tool calls."""
        return [tc for tc in self.tool_calls if tc.status == "executed"]

    def get_failed_tool_calls(self) -> List[ToolCallRecord]:
        """Get tool calls that failed or were denied."""
        return [tc for tc in self.tool_calls if tc.status in ("error", "denied")]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "output": self.output,
            "status": self.status.value,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "cycles_used": self.cycles_used,
            "duration_ms": self.duration_ms,
            "runtime_name": self.runtime_name,
            "model_used": self.model_used,
            "session_id": self.session_id,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionResult":
        """Create from dictionary."""
        status = data.get("status", "error")
        if isinstance(status, str):
            status = ExecutionStatus(status)

        tool_calls = [
            ToolCallRecord.from_dict(tc) if isinstance(tc, dict) else tc
            for tc in data.get("tool_calls", [])
        ]

        return cls(
            output=data.get("output", ""),
            status=status,
            tool_calls=tool_calls,
            tokens_used=data.get("tokens_used"),
            cost_usd=data.get("cost_usd"),
            cycles_used=data.get("cycles_used", 0),
            duration_ms=data.get("duration_ms"),
            runtime_name=data.get("runtime_name", ""),
            model_used=data.get("model_used", ""),
            session_id=data.get("session_id", ""),
            error_message=data.get("error_message"),
            error_type=data.get("error_type"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_error(
        cls,
        error: Exception,
        runtime_name: str = "",
        session_id: str = "",
        duration_ms: Optional[float] = None,
    ) -> "ExecutionResult":
        """Create an error result from an exception."""
        return cls(
            output="",
            status=ExecutionStatus.ERROR,
            runtime_name=runtime_name,
            session_id=session_id,
            duration_ms=duration_ms,
            error_message=str(error),
            error_type=type(error).__name__,
        )

    @classmethod
    def from_success(
        cls,
        output: str,
        runtime_name: str = "",
        model_used: str = "",
        session_id: str = "",
        **kwargs,
    ) -> "ExecutionResult":
        """Create a successful result."""
        return cls(
            output=output,
            status=ExecutionStatus.COMPLETE,
            runtime_name=runtime_name,
            model_used=model_used,
            session_id=session_id,
            **kwargs,
        )

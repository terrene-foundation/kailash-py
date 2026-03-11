"""
AgentResult - Structured result from agent execution

This module provides the AgentResult dataclass that captures
all execution details including output, tool calls, costs, and metrics.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ResultStatus(str, Enum):
    """Status of agent execution result."""

    SUCCESS = "success"
    """Execution completed successfully."""

    ERROR = "error"
    """Execution failed with an error."""

    TIMEOUT = "timeout"
    """Execution timed out."""

    INTERRUPTED = "interrupted"
    """Execution was interrupted by user."""

    PARTIAL = "partial"
    """Execution partially completed (useful for streaming)."""

    PENDING = "pending"
    """Execution is pending or in progress."""


@dataclass
class ToolCallRecord:
    """
    Record of a single tool call during execution.

    Captures tool name, arguments, result, timing, and any errors.
    """

    name: str
    """Tool name that was called."""

    arguments: Dict[str, Any] = field(default_factory=dict)
    """Arguments passed to the tool."""

    result: Any = None
    """Result returned by the tool."""

    error: Optional[str] = None
    """Error message if the tool call failed."""

    duration_ms: int = 0
    """Duration of the tool call in milliseconds."""

    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    """ISO timestamp when the tool was called."""

    cycle: int = 0
    """TAOD cycle number when this tool was called."""

    @property
    def succeeded(self) -> bool:
        """Whether the tool call succeeded."""
        return self.error is None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result if not callable(self.result) else str(self.result),
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "cycle": self.cycle,
            "succeeded": self.succeeded,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCallRecord":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            arguments=data.get("arguments", {}),
            result=data.get("result"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            cycle=data.get("cycle", 0),
        )

    def __str__(self) -> str:
        status = "✓" if self.succeeded else "✗"
        return f"[{status}] {self.name}({json.dumps(self.arguments)[:50]}...)"


@dataclass
class AgentResult:
    """
    Comprehensive result from agent execution.

    Contains the primary output, execution status, tool history,
    token usage, cost, timing, and metadata.

    Examples:
        # Basic usage
        result = agent.run("What is IRP?")
        print(result.text)

        # Check status
        if result.succeeded:
            print(f"Success in {result.duration_ms}ms")

        # Examine tool calls
        for tool_call in result.tool_calls:
            print(f"{tool_call.name}: {tool_call.succeeded}")

        # Check cost
        print(f"Cost: ${result.cost:.4f}")
    """

    # Primary output
    text: str = ""
    """Primary text output from the agent."""

    status: ResultStatus = ResultStatus.SUCCESS
    """Execution status."""

    # Execution history
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    """History of tool calls made during execution."""

    # Token usage
    tokens: Dict[str, int] = field(
        default_factory=lambda: {
            "input": 0,
            "output": 0,
            "total": 0,
        }
    )
    """Token usage breakdown."""

    # Cost tracking
    cost: float = 0.0
    """Estimated cost in USD."""

    # Execution metrics
    cycles: int = 0
    """Number of TAOD cycles (autonomous mode)."""

    turns: int = 0
    """Number of conversation turns."""

    duration_ms: int = 0
    """Total execution duration in milliseconds."""

    # Session info
    session_id: str = ""
    """Session identifier."""

    run_id: str = ""
    """Unique run identifier."""

    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    """ISO timestamp when execution started."""

    completed_at: str = ""
    """ISO timestamp when execution completed."""

    # Error details
    error: Optional[str] = None
    """Error message if execution failed."""

    error_type: Optional[str] = None
    """Error type/class if execution failed."""

    # Model info
    model_used: str = ""
    """Model that generated the response."""

    provider_used: str = ""
    """Provider that handled the request."""

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional execution metadata."""

    # === Convenience Properties ===

    @property
    def succeeded(self) -> bool:
        """Whether the execution succeeded."""
        return self.status == ResultStatus.SUCCESS

    @property
    def failed(self) -> bool:
        """Whether the execution failed."""
        return self.status in (ResultStatus.ERROR, ResultStatus.TIMEOUT)

    @property
    def was_interrupted(self) -> bool:
        """Whether the execution was interrupted."""
        return self.status == ResultStatus.INTERRUPTED

    @property
    def is_pending(self) -> bool:
        """Whether the execution is still pending."""
        return self.status == ResultStatus.PENDING

    @property
    def tool_call_count(self) -> int:
        """Number of tool calls made."""
        return len(self.tool_calls)

    @property
    def successful_tool_calls(self) -> List[ToolCallRecord]:
        """Tool calls that succeeded."""
        return [tc for tc in self.tool_calls if tc.succeeded]

    @property
    def failed_tool_calls(self) -> List[ToolCallRecord]:
        """Tool calls that failed."""
        return [tc for tc in self.tool_calls if not tc.succeeded]

    @property
    def input_tokens(self) -> int:
        """Input tokens used."""
        return self.tokens.get("input", 0)

    @property
    def output_tokens(self) -> int:
        """Output tokens used."""
        return self.tokens.get("output", 0)

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.tokens.get("total", 0) or (self.input_tokens + self.output_tokens)

    @property
    def duration_seconds(self) -> float:
        """Execution duration in seconds."""
        return self.duration_ms / 1000.0

    # === Tool Call Helpers ===

    def get_tool_calls_by_name(self, name: str) -> List[ToolCallRecord]:
        """
        Get all tool calls with a specific name.

        Args:
            name: Tool name to filter by

        Returns:
            List of matching tool call records
        """
        return [tc for tc in self.tool_calls if tc.name.lower() == name.lower()]

    def get_last_tool_call(self) -> Optional[ToolCallRecord]:
        """
        Get the most recent tool call.

        Returns:
            Last tool call record or None if no tool calls
        """
        return self.tool_calls[-1] if self.tool_calls else None

    def get_tool_results(self, name: Optional[str] = None) -> List[Any]:
        """
        Get results from tool calls.

        Args:
            name: Optional tool name to filter by

        Returns:
            List of tool results
        """
        calls = self.get_tool_calls_by_name(name) if name else self.tool_calls
        return [tc.result for tc in calls if tc.succeeded]

    # === Serialization ===

    def to_dict(self) -> dict:
        """
        Serialize result to a dictionary.

        Returns:
            Dictionary representation of the result
        """
        return {
            "text": self.text,
            "status": self.status.value,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tokens": self.tokens,
            "cost": self.cost,
            "cycles": self.cycles,
            "turns": self.turns,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "error_type": self.error_type,
            "model_used": self.model_used,
            "provider_used": self.provider_used,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """
        Serialize result to JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentResult":
        """
        Create result from a dictionary.

        Args:
            data: Dictionary with result data

        Returns:
            AgentResult instance
        """
        return cls(
            text=data.get("text", ""),
            status=ResultStatus(data.get("status", "success")),
            tool_calls=[
                ToolCallRecord.from_dict(tc) for tc in data.get("tool_calls", [])
            ],
            tokens=data.get("tokens", {"input": 0, "output": 0, "total": 0}),
            cost=data.get("cost", 0.0),
            cycles=data.get("cycles", 0),
            turns=data.get("turns", 0),
            duration_ms=data.get("duration_ms", 0),
            session_id=data.get("session_id", ""),
            run_id=data.get("run_id", ""),
            started_at=data.get("started_at", datetime.utcnow().isoformat()),
            completed_at=data.get("completed_at", ""),
            error=data.get("error"),
            error_type=data.get("error_type"),
            model_used=data.get("model_used", ""),
            provider_used=data.get("provider_used", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AgentResult":
        """
        Create result from JSON string.

        Args:
            json_str: JSON string

        Returns:
            AgentResult instance
        """
        return cls.from_dict(json.loads(json_str))

    # === Factory Methods ===

    @classmethod
    def success(
        cls,
        text: str,
        **kwargs,
    ) -> "AgentResult":
        """
        Create a successful result.

        Args:
            text: Output text
            **kwargs: Additional result fields

        Returns:
            AgentResult with SUCCESS status
        """
        return cls(
            text=text,
            status=ResultStatus.SUCCESS,
            completed_at=datetime.utcnow().isoformat(),
            **kwargs,
        )

    @classmethod
    def from_error(
        cls,
        error_message: str,
        error_type: str = "Error",
        **kwargs,
    ) -> "AgentResult":
        """
        Create an error result.

        Args:
            error_message: Error description
            error_type: Error class/type
            **kwargs: Additional result fields

        Returns:
            AgentResult with ERROR status
        """
        return cls(
            text="",
            status=ResultStatus.ERROR,
            error=error_message,
            error_type=error_type,
            completed_at=datetime.utcnow().isoformat(),
            **kwargs,
        )

    @classmethod
    def timeout(
        cls,
        partial_text: str = "",
        **kwargs,
    ) -> "AgentResult":
        """
        Create a timeout result.

        Args:
            partial_text: Any partial output before timeout
            **kwargs: Additional result fields

        Returns:
            AgentResult with TIMEOUT status
        """
        return cls(
            text=partial_text,
            status=ResultStatus.TIMEOUT,
            error="Execution timed out",
            error_type="TimeoutError",
            completed_at=datetime.utcnow().isoformat(),
            **kwargs,
        )

    @classmethod
    def interrupted(
        cls,
        partial_text: str = "",
        **kwargs,
    ) -> "AgentResult":
        """
        Create an interrupted result.

        Args:
            partial_text: Any partial output before interruption
            **kwargs: Additional result fields

        Returns:
            AgentResult with INTERRUPTED status
        """
        return cls(
            text=partial_text,
            status=ResultStatus.INTERRUPTED,
            completed_at=datetime.utcnow().isoformat(),
            **kwargs,
        )

    def __str__(self) -> str:
        """Human-readable result summary."""
        status_emoji = {
            ResultStatus.SUCCESS: "✓",
            ResultStatus.ERROR: "✗",
            ResultStatus.TIMEOUT: "⏱",
            ResultStatus.INTERRUPTED: "⚡",
            ResultStatus.PARTIAL: "…",
            ResultStatus.PENDING: "⋯",
        }
        emoji = status_emoji.get(self.status, "?")

        preview = self.text[:100] + "..." if len(self.text) > 100 else self.text
        return (
            f"[{emoji}] AgentResult("
            f"status={self.status.value}, "
            f"tokens={self.total_tokens}, "
            f"tools={self.tool_call_count}, "
            f"cost=${self.cost:.4f}, "
            f"text={repr(preview)})"
        )

    def __repr__(self) -> str:
        return self.__str__()

"""
LocalKaizenAdapter Core Types

Defines the core types for the native autonomous agent implementation:
- AutonomousPhase: Think-Act-Observe-Decide loop phases
- AutonomousConfig: Configuration for autonomous execution
- ExecutionState: Complete execution state for checkpointing
- PlanningStrategy: Available planning strategies
- PermissionMode: Tool permission modes
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AutonomousPhase(Enum):
    """Phases of the Think-Act-Observe-Decide loop.

    The TAOD loop is the core execution pattern for autonomous agents:
    - THINK: Reason about the task, call LLM to decide next action
    - ACT: Execute pending tool calls
    - OBSERVE: Process tool results, update working memory
    - DECIDE: Check completion conditions, determine if done
    """

    THINK = "think"
    ACT = "act"
    OBSERVE = "observe"
    DECIDE = "decide"


class PlanningStrategy(Enum):
    """Planning strategies for autonomous execution.

    - REACT: Simple step-by-step reasoning (default)
    - PEV: Plan-Execute-Verify cycle
    - TREE_OF_THOUGHTS: Multi-path exploration (experimental)
    """

    REACT = "react"
    PEV = "pev"
    TREE_OF_THOUGHTS = "tree_of_thoughts"


class PermissionMode(Enum):
    """Tool permission modes.

    Controls when user approval is required for tool execution:
    - AUTO: Auto-approve safe tools, auto-deny dangerous ones
    - CONFIRM_ALL: Require approval for all tools
    - CONFIRM_DANGEROUS: Require approval only for dangerous tools
    - DENY_ALL: Deny all tool executions (read-only mode)
    """

    AUTO = "auto"
    CONFIRM_ALL = "confirm_all"
    CONFIRM_DANGEROUS = "confirm_dangerous"
    DENY_ALL = "deny_all"


@dataclass
class AutonomousConfig:
    """Configuration for autonomous agent execution.

    Controls LLM settings, execution limits, checkpointing behavior,
    memory integration, planning strategy, and tool permissions.

    Example:
        >>> config = AutonomousConfig(
        ...     model="gpt-4o",
        ...     max_cycles=100,
        ...     budget_limit_usd=1.0,
        ...     planning_strategy=PlanningStrategy.PEV,
        ... )
    """

    # LLM settings
    llm_provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7

    # Execution limits
    max_cycles: int = 50
    budget_limit_usd: Optional[float] = None
    timeout_seconds: Optional[float] = None

    # Checkpointing
    checkpoint_frequency: int = 10
    checkpoint_on_interrupt: bool = True
    resume_from_checkpoint: Optional[str] = None

    # Memory
    enable_learning: bool = False
    memory_backend: Optional[str] = None

    # Planning
    planning_strategy: PlanningStrategy = PlanningStrategy.REACT

    # Permissions
    permission_mode: PermissionMode = PermissionMode.CONFIRM_DANGEROUS

    # Tools
    tools: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate()

    def _validate(self):
        """Validate configuration values with helpful error messages."""
        # Temperature validation
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature must be between 0.0 and 2.0, got {self.temperature}"
            )

        # Max cycles validation
        if self.max_cycles < 1:
            raise ValueError(f"max_cycles must be at least 1, got {self.max_cycles}")

        # Budget validation
        if self.budget_limit_usd is not None and self.budget_limit_usd <= 0:
            raise ValueError(
                f"budget_limit_usd must be positive, got {self.budget_limit_usd}"
            )

        # Timeout validation
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError(
                f"timeout_seconds must be positive, got {self.timeout_seconds}"
            )

        # Checkpoint frequency validation
        if self.checkpoint_frequency < 1:
            raise ValueError(
                f"checkpoint_frequency must be at least 1, got {self.checkpoint_frequency}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to dictionary.

        Returns:
            Dictionary with all configuration values
        """
        return {
            "llm_provider": self.llm_provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_cycles": self.max_cycles,
            "budget_limit_usd": self.budget_limit_usd,
            "timeout_seconds": self.timeout_seconds,
            "checkpoint_frequency": self.checkpoint_frequency,
            "checkpoint_on_interrupt": self.checkpoint_on_interrupt,
            "resume_from_checkpoint": self.resume_from_checkpoint,
            "enable_learning": self.enable_learning,
            "memory_backend": self.memory_backend,
            "planning_strategy": self.planning_strategy.value,
            "permission_mode": self.permission_mode.value,
            "tools": self.tools,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomousConfig":
        """Deserialize configuration from dictionary.

        Args:
            data: Dictionary with configuration values

        Returns:
            AutonomousConfig instance
        """
        # Convert enum strings back to enums
        if "planning_strategy" in data and isinstance(data["planning_strategy"], str):
            data = dict(data)
            data["planning_strategy"] = PlanningStrategy(data["planning_strategy"])

        if "permission_mode" in data and isinstance(data["permission_mode"], str):
            data = dict(data)
            data["permission_mode"] = PermissionMode(data["permission_mode"])

        return cls(**data)


@dataclass
class ExecutionState:
    """Complete execution state for autonomous agent.

    Tracks all aspects of execution for checkpointing and resume:
    - Task and session identification
    - Current cycle and phase
    - Conversation history
    - Plan and progress (if using planning)
    - Pending and completed tool calls
    - Working memory and learned patterns
    - Budget tracking (tokens and cost)
    - Execution status and result

    This state is serializable for checkpoint/restore operations.

    Example:
        >>> state = ExecutionState(task="List files in /tmp")
        >>> state.add_message({"role": "user", "content": "List files in /tmp"})
        >>> state.advance_cycle()
        >>> state.complete(result="Files: file1.txt, file2.txt")
    """

    # Core identification
    task: str
    session_id: str = field(default_factory=lambda: f"session_{uuid.uuid4().hex[:12]}")

    # Execution tracking
    current_cycle: int = 0
    phase: AutonomousPhase = AutonomousPhase.THINK

    # Conversation state
    messages: List[Dict[str, Any]] = field(default_factory=list)

    # Plan state (if using planning strategy)
    plan: List[str] = field(default_factory=list)
    plan_index: int = 0

    # Tool execution state
    pending_tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # Memory state
    working_memory: Dict[str, Any] = field(default_factory=dict)
    learned_patterns: List[str] = field(default_factory=list)

    # Budget tracking
    tokens_used: int = 0
    cost_usd: float = 0.0

    # Execution status
    status: str = "running"  # running, completed, interrupted, error
    result: Optional[str] = None
    error: Optional[str] = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_complete(self) -> bool:
        """Check if execution is complete (success, error, or interrupted)."""
        return self.status in ("completed", "error", "interrupted")

    @property
    def is_success(self) -> bool:
        """Check if execution completed successfully."""
        return self.status == "completed"

    @property
    def is_error(self) -> bool:
        """Check if execution ended with error."""
        return self.status == "error"

    def advance_cycle(self) -> None:
        """Advance to next cycle."""
        self.current_cycle += 1
        self.updated_at = datetime.utcnow()

    def set_phase(self, phase: AutonomousPhase) -> None:
        """Set current execution phase."""
        self.phase = phase
        self.updated_at = datetime.utcnow()

    def add_message(self, message: Dict[str, Any]) -> None:
        """Add a message to conversation history."""
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

    def add_tool_call(self, tool_call: Dict[str, Any]) -> None:
        """Add a pending tool call."""
        self.pending_tool_calls.append(tool_call)
        self.updated_at = datetime.utcnow()

    def add_tool_result(self, result: Dict[str, Any]) -> None:
        """Add a tool execution result."""
        self.tool_results.append(result)
        self.updated_at = datetime.utcnow()

    def clear_pending_tool_calls(self) -> None:
        """Clear all pending tool calls."""
        self.pending_tool_calls = []
        self.updated_at = datetime.utcnow()

    def update_budget(self, tokens: int, cost: float) -> None:
        """Update token and cost tracking.

        Args:
            tokens: Number of tokens to add
            cost: Cost in USD to add
        """
        self.tokens_used += tokens
        self.cost_usd += cost
        self.updated_at = datetime.utcnow()

    def complete(self, result: str) -> None:
        """Mark execution as completed successfully.

        Args:
            result: Final result text
        """
        self.status = "completed"
        self.result = result
        self.updated_at = datetime.utcnow()

    def fail(self, error: str) -> None:
        """Mark execution as failed with error.

        Args:
            error: Error message
        """
        self.status = "error"
        self.error = error
        self.updated_at = datetime.utcnow()

    def interrupt(self) -> None:
        """Mark execution as interrupted."""
        self.status = "interrupted"
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary for checkpointing.

        Returns:
            Dictionary with all state values
        """
        return {
            "task": self.task,
            "session_id": self.session_id,
            "current_cycle": self.current_cycle,
            "phase": self.phase.value,
            "messages": self.messages,
            "plan": self.plan,
            "plan_index": self.plan_index,
            "pending_tool_calls": self.pending_tool_calls,
            "tool_results": self.tool_results,
            "working_memory": self.working_memory,
            "learned_patterns": self.learned_patterns,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionState":
        """Deserialize state from dictionary.

        Args:
            data: Dictionary with state values

        Returns:
            ExecutionState instance
        """
        # Convert phase string to enum
        data = dict(data)
        if "phase" in data and isinstance(data["phase"], str):
            data["phase"] = AutonomousPhase(data["phase"])

        # Convert datetime strings
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        return cls(**data)

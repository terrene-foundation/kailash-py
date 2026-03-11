"""
Core types for the Hooks System.

Defines event types, contexts, and results for hook execution.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookEvent(Enum):
    """Lifecycle events where hooks can be triggered"""

    # Tool execution lifecycle
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"

    # Agent execution lifecycle
    PRE_AGENT_LOOP = "pre_agent_loop"
    POST_AGENT_LOOP = "post_agent_loop"

    # Specialist invocation lifecycle
    PRE_SPECIALIST_INVOKE = "pre_specialist_invoke"
    POST_SPECIALIST_INVOKE = "post_specialist_invoke"

    # Permission system integration
    PRE_PERMISSION_CHECK = "pre_permission_check"
    POST_PERMISSION_CHECK = "post_permission_check"

    # State persistence integration
    PRE_CHECKPOINT_SAVE = "pre_checkpoint_save"
    POST_CHECKPOINT_SAVE = "post_checkpoint_save"

    # Interrupt handling integration (TODO-169 Day 4)
    PRE_INTERRUPT = "pre_interrupt"
    POST_INTERRUPT = "post_interrupt"

    # Planning lifecycle
    PRE_PLAN_GENERATION = "pre_plan_generation"
    POST_PLAN_GENERATION = "post_plan_generation"

    # Memory lifecycle
    PRE_MEMORY_SAVE = "pre_memory_save"
    POST_MEMORY_SAVE = "post_memory_save"
    PRE_MEMORY_LOAD = "pre_memory_load"
    POST_MEMORY_LOAD = "post_memory_load"


class HookPriority(Enum):
    """Priority levels for hook execution order"""

    CRITICAL = 0  # Execute first (logging, auditing)
    HIGH = 1  # Execute early (metrics, monitoring)
    NORMAL = 2  # Default priority (most hooks)
    LOW = 3  # Execute last (cleanup, notifications)


@dataclass
class HookContext:
    """Context passed to hook handlers"""

    event_type: HookEvent
    agent_id: str
    timestamp: float
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None

    def __post_init__(self):
        """Ensure timestamp is set"""
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class HookResult:
    """Result returned by hook handler"""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def __post_init__(self):
        """Validate result"""
        if not self.success and self.error is None:
            raise ValueError("Unsuccessful hook result must include error message")


# Export all public types
__all__ = [
    "HookEvent",
    "HookPriority",
    "HookContext",
    "HookResult",
]

"""
Agent execution system for the Kaizen framework.

This module provides structured output parsing, pattern-specific execution
logic for signature-based programming, and execution event types for
autonomous agent runtime.
"""

from .events import (  # Core enum and base; Enterprise-App Core Events (TODO-204); Subagent events (TODO-203); Skill events (TODO-203); Cost tracking
    CompletedEvent,
    CostUpdateEvent,
    ErrorEvent,
    EventType,
    ExecutionEvent,
    MessageEvent,
    ProgressEvent,
    SkillCompleteEvent,
    SkillInvokeEvent,
    StartedEvent,
    SubagentCompleteEvent,
    SubagentSpawnEvent,
    ThinkingEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from .parser import OutputParser, ResponseParser, StructuredOutputParser
from .patterns import ChainOfThoughtExecutor, PatternExecutor, ReActExecutor
from .streaming_executor import ExecutionMetrics, StreamingExecutor, format_sse
from .subagent_result import SkillResult, SubagentResult

__all__ = [
    # Output parsing
    "OutputParser",
    "ResponseParser",
    "StructuredOutputParser",
    # Pattern execution
    "PatternExecutor",
    "ChainOfThoughtExecutor",
    "ReActExecutor",
    # Streaming execution (TODO-204)
    "StreamingExecutor",
    "ExecutionMetrics",
    "format_sse",
    # Execution events - Core enum and base
    "EventType",
    "ExecutionEvent",
    # Execution events - Enterprise-App Core Events (TODO-204)
    "StartedEvent",
    "ThinkingEvent",
    "MessageEvent",
    "ToolUseEvent",
    "ToolResultEvent",
    "ProgressEvent",
    "CompletedEvent",
    "ErrorEvent",
    # Execution events - Subagent (TODO-203)
    "SubagentSpawnEvent",
    "SubagentCompleteEvent",
    # Execution events - Skill (TODO-203)
    "SkillInvokeEvent",
    "SkillCompleteEvent",
    # Execution events - Cost
    "CostUpdateEvent",
    # Result types (TODO-203)
    "SubagentResult",
    "SkillResult",
]

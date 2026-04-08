# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Typed event system for Kaizen agent wrappers.

Provides frozen event dataclasses that ``StreamingAgent.run_stream()`` yields.
Consumers pattern-match on event type::

    async for event in streaming_agent.run_stream(prompt="analyse this"):
        match event:
            case TextDelta(text=t):
                print(t, end="")
            case ToolCallStart(name=n):
                show_spinner(n)
            case ToolCallEnd(name=n, result=r):
                hide_spinner(n)
            case TurnComplete(text=t):
                render_final(t)
            case BudgetExhausted():
                warn_user()
            case ErrorEvent(error=e):
                handle_error(e)
            case StreamBufferOverflow(dropped_count=n):
                log_warning(n)

All events inherit from :class:`StreamEvent` which carries an
``event_type`` discriminator and a monotonic ``timestamp``.

Events are ``@dataclass(frozen=True)`` for immutability.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "StreamEvent",
    "TextDelta",
    "ToolCallStart",
    "ToolCallEnd",
    "TurnComplete",
    "BudgetExhausted",
    "ErrorEvent",
    "StreamBufferOverflow",
    "StreamTimeoutError",
]


@dataclass(frozen=True)
class StreamEvent:
    """Base class for all streaming events.

    Attributes:
        event_type: Discriminator string for pattern matching.
        timestamp: Monotonic timestamp (``time.monotonic()``) when the
            event was created.
    """

    event_type: str = ""
    timestamp: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class TextDelta(StreamEvent):
    """Incremental text fragment from the model.

    Attributes:
        text: The new text fragment (delta only, not accumulated).
    """

    event_type: str = field(default="text_delta", init=False)
    text: str = ""


@dataclass(frozen=True)
class ToolCallStart(StreamEvent):
    """A tool call has begun streaming.

    Attributes:
        call_id: The tool call ID assigned by the model.
        name: The tool function name.
    """

    event_type: str = field(default="tool_call_start", init=False)
    call_id: str = ""
    name: str = ""


@dataclass(frozen=True)
class ToolCallEnd(StreamEvent):
    """A tool call has completed execution.

    Attributes:
        call_id: The tool call ID.
        name: The tool function name.
        result: The tool's string result.
        error: Error message if the tool failed, empty string otherwise.
    """

    event_type: str = field(default="tool_call_end", init=False)
    call_id: str = ""
    name: str = ""
    result: str = ""
    error: str = ""


@dataclass(frozen=True)
class TurnComplete(StreamEvent):
    """The model has finished responding (no more tool calls).

    Attributes:
        text: The complete accumulated text for this turn.
        usage: Token usage dict (prompt_tokens, completion_tokens, total_tokens).
        structured: Optional structured output (parsed JSON, dataclass, etc.).
        iterations: Number of TAOD loop iterations that occurred in this turn.
    """

    event_type: str = field(default="turn_complete", init=False)
    text: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    structured: Any = None
    iterations: int = 0


@dataclass(frozen=True)
class BudgetExhausted(StreamEvent):
    """Budget has been exhausted; the agent is stopping.

    Attributes:
        budget_usd: The total budget that was set.
        consumed_usd: The amount consumed before exhaustion.
    """

    event_type: str = field(default="budget_exhausted", init=False)
    budget_usd: float = 0.0
    consumed_usd: float = 0.0


@dataclass(frozen=True)
class ErrorEvent(StreamEvent):
    """An error occurred during execution.

    Attributes:
        error: Human-readable error description.
        details: Structured error details for programmatic consumption.
    """

    event_type: str = field(default="error", init=False)
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamBufferOverflow(StreamEvent):
    """Events were dropped because the stream buffer was full.

    Attributes:
        dropped_count: Number of events that were dropped.
        oldest_timestamp: Timestamp of the oldest dropped event.
    """

    event_type: str = field(default="stream_buffer_overflow", init=False)
    dropped_count: int = 0
    oldest_timestamp: float = 0.0


class StreamTimeoutError(RuntimeError):
    """Raised when a streaming operation exceeds its timeout."""

    pass

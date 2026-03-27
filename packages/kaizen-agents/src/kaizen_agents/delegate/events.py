# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Typed event system for the Delegate.

Provides structured event dataclasses that the ``Delegate.run()`` async
generator yields.  Consumers pattern-match on event type rather than
parsing raw strings::

    async for event in delegate.run("analyse this codebase"):
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

All events inherit from :class:`DelegateEvent` which carries an
``event_type`` discriminator and a monotonic ``timestamp``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DelegateEvent",
    "TextDelta",
    "ToolCallStart",
    "ToolCallEnd",
    "TurnComplete",
    "BudgetExhausted",
    "ErrorEvent",
]


@dataclass
class DelegateEvent:
    """Base class for all Delegate events.

    Attributes:
        event_type: Discriminator string for pattern matching.
        timestamp: Monotonic timestamp (``time.monotonic()``) when the
            event was created.
    """

    event_type: str = ""
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class TextDelta(DelegateEvent):
    """Incremental text fragment from the model.

    Attributes:
        text: The new text fragment (delta only, not accumulated).
    """

    event_type: str = field(default="text_delta", init=False)
    text: str = ""


@dataclass
class ToolCallStart(DelegateEvent):
    """A tool call has begun streaming.

    Attributes:
        call_id: The tool call ID assigned by the model.
        name: The tool function name.
    """

    event_type: str = field(default="tool_call_start", init=False)
    call_id: str = ""
    name: str = ""


@dataclass
class ToolCallEnd(DelegateEvent):
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


@dataclass
class TurnComplete(DelegateEvent):
    """The model has finished responding (no more tool calls).

    Attributes:
        text: The complete accumulated text for this turn.
        usage: Token usage dict (prompt_tokens, completion_tokens, total_tokens).
    """

    event_type: str = field(default="turn_complete", init=False)
    text: str = ""
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class BudgetExhausted(DelegateEvent):
    """Budget has been exhausted; the Delegate is stopping.

    Attributes:
        budget_usd: The total budget that was set.
        consumed_usd: The amount consumed before exhaustion.
    """

    event_type: str = field(default="budget_exhausted", init=False)
    budget_usd: float = 0.0
    consumed_usd: float = 0.0


@dataclass
class ErrorEvent(DelegateEvent):
    """An error occurred during execution.

    Attributes:
        error: Human-readable error description.
        details: Structured error details for programmatic consumption.
    """

    event_type: str = field(default="error", init=False)
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

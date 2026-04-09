# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unified data types shared across all providers.

These types define the lingua franca for messages, responses, token usage,
and streaming events so that consumers never depend on provider-specific
data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Union

# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

#: Flexible message content: either a plain string or a list of content blocks
#: (text, image, audio, etc.)
MessageContent = Union[str, List[Dict[str, Any]]]

#: A single conversation message in OpenAI-compatible format.
Message = Dict[str, Union[str, MessageContent]]


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    """Token consumption for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool/function call emitted by the model."""

    id: str
    type: str = "function"
    function_name: str = ""
    function_arguments: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function_name,
                "arguments": self.function_arguments,
            },
        }


# ---------------------------------------------------------------------------
# Chat response
# ---------------------------------------------------------------------------


@dataclass
class ChatResponse:
    """Standardised response from any LLM provider.

    This mirrors the dict format already used throughout the monolith so
    migration is a data-preserving rename.
    """

    id: str = ""
    content: str | None = ""
    role: str = "assistant"
    model: str = ""
    created: Any = None
    tool_calls: list[Any] = field(default_factory=list)
    finish_reason: str | None = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to the legacy dict format expected by consumers."""
        return {
            "id": self.id,
            "content": self.content,
            "role": self.role,
            "model": self.model,
            "created": self.created,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Streaming events
# ---------------------------------------------------------------------------


@dataclass
class StreamEvent:
    """A single event emitted during a streaming LLM response.

    Attributes:
        event_type: One of ``"text_delta"``, ``"tool_call_start"``,
            ``"tool_call_delta"``, ``"tool_call_end"``, ``"done"``.
        content: Accumulated text content so far (for ``text_delta`` events).
        tool_calls: Accumulated tool calls so far (for ``done`` events,
            in OpenAI-compatible format for consistency across providers).
        finish_reason: Model finish reason (set on ``"done"``).
        model: Model identifier from the response.
        usage: Token usage dict (set on ``"done"``).
        delta_text: The new text fragment in this specific event (only the
            incremental piece, not the accumulated total).
    """

    event_type: str
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    delta_text: str = ""

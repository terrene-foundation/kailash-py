# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""StreamingChatAdapter protocol and StreamEvent dataclass.

Defines the uniform interface that all LLM provider adapters implement.
The Delegate's AgentLoop uses this protocol exclusively -- it never imports
a provider SDK directly.

Stream events use a simple string-tagged dataclass rather than a union type
so that new event kinds can be added without breaking existing consumers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stream event
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


# ---------------------------------------------------------------------------
# Adapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StreamingChatAdapter(Protocol):
    """Protocol for LLM provider adapters.

    Implementors provide ``stream_chat()`` which yields ``StreamEvent``
    objects as the model generates its response.  The AgentLoop consumes
    these events to drive incremental rendering, tool calling, and
    conversation management.

    All tool calls are normalised to OpenAI-compatible format (dict with
    ``id``, ``type``, ``function.name``, ``function.arguments``) regardless
    of the underlying provider.
    """

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream a chat completion.

        Parameters
        ----------
        messages:
            Conversation messages in OpenAI-compatible format
            (``[{"role": ..., "content": ...}, ...]``).
        tools:
            Optional tool definitions in OpenAI function-calling format.
        model:
            Override the adapter's default model for this call.
        temperature:
            Override the adapter's default temperature.
        max_tokens:
            Override the adapter's default max tokens.
        **kwargs:
            Provider-specific options.

        Yields
        ------
        StreamEvent instances in chronological order, always ending with
        a ``"done"`` event.
        """
        ...  # pragma: no cover
        # The yield statement is needed so that the type-checker recognises
        # this as an AsyncGenerator, not a plain coroutine.
        yield StreamEvent(event_type="done")  # type: ignore[misc]  # pragma: no cover

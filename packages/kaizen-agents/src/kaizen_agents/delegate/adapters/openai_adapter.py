# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""OpenAI streaming chat adapter.

Wraps the ``openai`` SDK's ``AsyncOpenAI`` client behind the
:class:`StreamingChatAdapter` protocol.  Existing stream-processing logic
from ``openai_stream.py`` is reused via delegation.

Lazy-imports the ``openai`` package so that users of other providers do not
need it installed.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncGenerator

from kaizen_agents.delegate.adapters.protocol import StreamEvent

logger = logging.getLogger(__name__)

# Prefixes that require max_completion_tokens instead of max_tokens
# and do not support custom temperature (GPT-5, reasoning models).
_NEW_API_PREFIXES = ("o1", "o3", "gpt-5")


class OpenAIStreamAdapter:
    """Adapter for OpenAI and OpenAI-compatible API endpoints.

    Parameters
    ----------
    api_key:
        OpenAI API key.  Falls back to ``OPENAI_API_KEY`` env var.
    base_url:
        Optional base URL override (for proxies or compatible APIs).
    default_model:
        Model to use when none is supplied per-call.
    default_temperature:
        Default sampling temperature.
    default_max_tokens:
        Default max token limit.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "",
        default_temperature: float = 0.4,
        default_max_tokens: int = 16384,
    ) -> None:
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No OpenAI API key found.  Set OPENAI_API_KEY in your .env file "
                "or pass api_key explicitly."
            )

        self._default_model = default_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

        # Lazy import
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "The openai package is required for OpenAI adapters.  "
                "Install it with: pip install openai"
            ) from exc

        import httpx

        client_kwargs: dict[str, Any] = {
            "api_key": resolved_key,
            "timeout": httpx.Timeout(connect=10, read=120, write=30, pool=10),
        }
        resolved_base = base_url or os.environ.get("OPENAI_BASE_URL")
        if resolved_base:
            client_kwargs["base_url"] = resolved_base
        self._client = AsyncOpenAI(**client_kwargs)

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
        """Stream a chat completion via the OpenAI API.

        Yields :class:`StreamEvent` instances as tokens arrive.
        """
        resolved_model = model or self._default_model
        resolved_temp = temperature if temperature is not None else self._default_temperature
        resolved_max = max_tokens if max_tokens is not None else self._default_max_tokens

        is_new_api = any(resolved_model.startswith(p) for p in _NEW_API_PREFIXES)

        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if not is_new_api:
            request_kwargs["temperature"] = resolved_temp

        if is_new_api:
            request_kwargs["max_completion_tokens"] = resolved_max
        else:
            request_kwargs["max_tokens"] = resolved_max

        if tools:
            request_kwargs["tools"] = tools
            request_kwargs["tool_choice"] = "auto"

        # Merge any extra provider-specific kwargs
        request_kwargs.update(kwargs)

        stream = await self._client.chat.completions.create(**request_kwargs)

        # Accumulate state
        content = ""
        tool_accumulators: dict[int, dict[str, Any]] = {}
        resp_model = ""
        usage: dict[str, int] = {}
        finish_reason: str | None = None

        async for chunk in stream:
            if not chunk.choices:
                # Usage-only chunk (sent at end by some models)
                if chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                continue

            if chunk.model:
                resp_model = chunk.model

            choice = chunk.choices[0]
            delta = choice.delta

            # Text content
            if delta.content:
                content += delta.content
                yield StreamEvent(
                    event_type="text_delta",
                    content=content,
                    delta_text=delta.content,
                    model=resp_model,
                )

            # Tool calls (streamed as deltas)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index

                    if idx not in tool_accumulators:
                        acc = {
                            "id": tc_delta.id or "",
                            "type": tc_delta.type or "function",
                            "function": {
                                "name": (tc_delta.function.name if tc_delta.function else "") or "",
                                "arguments": (tc_delta.function.arguments if tc_delta.function else "") or "",
                            },
                        }
                        tool_accumulators[idx] = acc
                        yield StreamEvent(
                            event_type="tool_call_start",
                            content=content,
                            model=resp_model,
                        )
                    else:
                        acc = tool_accumulators[idx]
                        if tc_delta.function and tc_delta.function.arguments:
                            acc["function"]["arguments"] += tc_delta.function.arguments
                        yield StreamEvent(
                            event_type="tool_call_delta",
                            content=content,
                            model=resp_model,
                        )

            # Finish reason
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        # Finalise tool calls in index order
        final_tool_calls: list[dict[str, Any]] = []
        for idx in sorted(tool_accumulators.keys()):
            final_tool_calls.append(tool_accumulators[idx])

        # Emit tool_call_end events
        for _ in final_tool_calls:
            yield StreamEvent(
                event_type="tool_call_end",
                content=content,
                model=resp_model,
            )

        yield StreamEvent(
            event_type="done",
            content=content,
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            model=resp_model,
            usage=usage,
        )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Ollama local model streaming chat adapter.

Implements the :class:`StreamingChatAdapter` protocol for local Ollama models.
Uses ``httpx`` for async HTTP streaming against Ollama's ``/api/chat`` endpoint
(already a dependency of the ``openai`` package).

No additional SDK install is required -- httpx is always available.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncGenerator

from kaizen_agents.delegate.adapters.protocol import StreamEvent

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaStreamAdapter:
    """Adapter for local Ollama models via HTTP streaming.

    Uses the ``/api/chat`` endpoint which supports streaming JSON lines.

    Parameters
    ----------
    base_url:
        Ollama base URL.  Falls back to ``OLLAMA_BASE_URL`` env var or
        ``http://localhost:11434``.
    default_model:
        Model to use when none is supplied per-call.
    default_temperature:
        Default sampling temperature.
    default_max_tokens:
        Default max token limit (``num_predict`` in Ollama).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        default_model: str = "",
        default_temperature: float = 0.4,
        default_max_tokens: int = 16384,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or _DEFAULT_OLLAMA_BASE_URL
        ).rstrip("/")
        self._default_model = default_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

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
        """Stream a chat completion from a local Ollama instance.

        Yields :class:`StreamEvent` instances as tokens arrive.
        """
        import httpx

        resolved_model = model or self._default_model
        resolved_temp = temperature if temperature is not None else self._default_temperature
        resolved_max = max_tokens if max_tokens is not None else self._default_max_tokens

        # Convert messages: Ollama supports a subset of OpenAI format
        # (role/content pairs).  System, user, assistant are supported natively.
        # Tool results become assistant messages with tool content.
        ollama_messages = _convert_messages_for_ollama(messages)

        request_body: dict[str, Any] = {
            "model": resolved_model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": resolved_temp,
                "num_predict": resolved_max,
            },
        }

        if tools:
            request_body["tools"] = tools

        request_body.update(kwargs)

        url = f"{self._base_url}/api/chat"

        # Accumulate state
        content = ""
        tool_calls: list[dict[str, Any]] = []
        resp_model = resolved_model
        usage: dict[str, int] = {}
        finish_reason: str | None = None

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10)) as client:
            async with client.stream("POST", url, json=request_body) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise ConnectionError(
                        f"Ollama returned status {response.status_code}: "
                        f"{body.decode('utf-8', errors='replace')[:500]}"
                    )

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse Ollama stream line: %s", line[:200])
                        continue

                    # Model name
                    if "model" in data:
                        resp_model = data["model"]

                    # Text delta from message.content
                    msg = data.get("message", {})
                    delta_text = msg.get("content", "")
                    if delta_text:
                        content += delta_text
                        yield StreamEvent(
                            event_type="text_delta",
                            content=content,
                            delta_text=delta_text,
                            model=resp_model,
                        )

                    # Tool calls (Ollama returns them in message.tool_calls)
                    raw_tool_calls = msg.get("tool_calls", [])
                    for tc in raw_tool_calls:
                        func = tc.get("function", {})
                        tc_dict = {
                            "id": f"call_ollama_{len(tool_calls)}",
                            "type": "function",
                            "function": {
                                "name": func.get("name", ""),
                                "arguments": json.dumps(func.get("arguments", {})),
                            },
                        }
                        tool_calls.append(tc_dict)
                        yield StreamEvent(
                            event_type="tool_call_start",
                            content=content,
                            model=resp_model,
                        )
                        yield StreamEvent(
                            event_type="tool_call_end",
                            content=content,
                            model=resp_model,
                        )

                    # Done indicator
                    if data.get("done", False):
                        # Extract usage from the final message
                        usage = {
                            "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
                            "completion_tokens": data.get("eval_count", 0) or 0,
                            "total_tokens": (
                                (data.get("prompt_eval_count", 0) or 0)
                                + (data.get("eval_count", 0) or 0)
                            ),
                        }
                        if tool_calls:
                            finish_reason = "tool_calls"
                        else:
                            finish_reason = "stop"

        yield StreamEvent(
            event_type="done",
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=resp_model,
            usage=usage,
        )


def _convert_messages_for_ollama(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert OpenAI-format messages for Ollama's /api/chat.

    Ollama supports system/user/assistant/tool roles natively.
    Tool messages are passed through mostly unchanged; Ollama expects
    the same structure as OpenAI for tool results.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "")
        if role in ("system", "user", "assistant", "tool"):
            converted: dict[str, Any] = {"role": role, "content": msg.get("content", "")}
            # Pass through tool_calls for assistant messages
            if role == "assistant" and "tool_calls" in msg:
                converted["tool_calls"] = msg["tool_calls"]
            result.append(converted)
    return result

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
import uuid
from collections.abc import AsyncGenerator
from typing import Any

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
        default_max_tokens: int = 4096,
    ) -> None:
        self._base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL") or _DEFAULT_OLLAMA_BASE_URL
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
        resolved_temp = (
            temperature if temperature is not None else self._default_temperature
        )
        resolved_max = (
            max_tokens if max_tokens is not None else self._default_max_tokens
        )

        # Convert messages: Ollama supports a subset of OpenAI format
        # (role/content pairs).  System, user, assistant are supported natively.
        # Tool results become assistant messages with tool content.
        ollama_messages = _convert_messages_for_ollama(messages)

        # Ollama does not support streaming when tools are provided;
        # disable stream to get a single JSON response with tool_calls.
        use_stream = not bool(tools)

        request_body: dict[str, Any] = {
            "model": resolved_model,
            "messages": ollama_messages,
            "stream": use_stream,
            "options": {
                "temperature": resolved_temp,
                "num_predict": resolved_max,
            },
        }

        if tools:
            request_body["tools"] = tools

        # Merge permitted kwargs into request body. Only known Ollama API
        # keys are allowed to prevent callers from overwriting model/messages/
        # stream/tools (request smuggling, gh#367b security hardening).
        _ALLOWED_KWARGS = {"options", "format", "keep_alive", "template"}
        for k, v in kwargs.items():
            if k not in _ALLOWED_KWARGS:
                continue
            if k == "options" and isinstance(v, dict):
                request_body.setdefault("options", {}).update(v)
            else:
                request_body[k] = v

        url = f"{self._base_url}/api/chat"

        # Accumulate state
        content = ""
        tool_calls: list[dict[str, Any]] = []
        resp_model = resolved_model
        usage: dict[str, int] = {}
        finish_reason: str | None = None

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=120, write=30, pool=10)
        ) as client:
            if not use_stream:
                # Non-streaming path: tools are present, Ollama returns a
                # single JSON object instead of newline-delimited chunks.
                resp = await client.post(url, json=request_body)
                if resp.status_code != 200:
                    logger.warning(
                        "ollama.non_streaming_error",
                        extra={"status": resp.status_code, "body": resp.text[:500]},
                    )
                    raise ConnectionError(f"Ollama returned status {resp.status_code}")
                data = resp.json()

                if "model" in data:
                    resp_model = data["model"]

                msg = data.get("message", {})
                text = msg.get("content", "")
                if text:
                    content = text
                    yield StreamEvent(
                        event_type="text_delta",
                        content=content,
                        delta_text=text,
                        model=resp_model,
                    )

                raw_tool_calls = msg.get("tool_calls", [])
                for tc in raw_tool_calls:
                    func = tc.get("function", {})
                    tc_dict = {
                        "id": f"call_ollama_{uuid.uuid4().hex[:12]}",
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

                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
                    "completion_tokens": data.get("eval_count", 0) or 0,
                    "total_tokens": (
                        (data.get("prompt_eval_count", 0) or 0)
                        + (data.get("eval_count", 0) or 0)
                    ),
                }
                finish_reason = "tool_calls" if tool_calls else "stop"
            else:
                # Streaming path: read newline-delimited JSON chunks.
                async with client.stream("POST", url, json=request_body) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning(
                            "ollama.streaming_error",
                            extra={
                                "status": response.status_code,
                                "body": body.decode("utf-8", errors="replace")[:500],
                            },
                        )
                        raise ConnectionError(
                            f"Ollama returned status {response.status_code}"
                        )

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse Ollama stream line: %r", line[:200]
                            )
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
                                "id": f"call_ollama_{uuid.uuid4().hex[:12]}",
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
                            finish_reason = "tool_calls" if tool_calls else "stop"

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
            converted: dict[str, Any] = {
                "role": role,
                "content": msg.get("content", ""),
            }
            # Pass through tool_calls for assistant messages, deserialising
            # arguments from JSON strings back to dicts (Ollama expects dicts).
            if role == "assistant" and "tool_calls" in msg:
                converted_tcs = []
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    converted_tcs.append(
                        {
                            "type": tc.get("type", "function"),
                            "function": {
                                "name": func.get("name", ""),
                                "arguments": args,
                            },
                        }
                    )
                converted["tool_calls"] = converted_tcs
            # Preserve tool_call_id and name for tool-role messages so
            # Ollama can correlate tool results with the originating call.
            if role == "tool":
                if "tool_call_id" in msg:
                    converted["tool_call_id"] = msg["tool_call_id"]
                if "name" in msg:
                    converted["name"] = msg["name"]
            result.append(converted)
    return result

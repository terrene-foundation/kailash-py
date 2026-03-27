# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Anthropic Claude streaming chat adapter.

Implements the :class:`StreamingChatAdapter` protocol using the native
``anthropic`` Python SDK.  Maps Anthropic's ``content_block_start``,
``content_block_delta``, and ``content_block_stop`` events to the unified
``StreamEvent`` format.

Tool-use blocks are normalised to OpenAI-compatible tool call dicts for
downstream compatibility with the AgentLoop's tool execution pipeline.

Lazy-imports the ``anthropic`` package so that users of other providers
do not need it installed.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, AsyncGenerator

from kaizen_agents.delegate.adapters.protocol import StreamEvent

logger = logging.getLogger(__name__)


def _convert_messages_for_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Separate system prompt from messages and convert to Anthropic format.

    OpenAI format puts the system message in the messages list.  Anthropic
    expects it as a top-level ``system`` parameter, and uses separate
    ``tool_result`` blocks instead of ``role: "tool"`` messages.

    Returns (system_prompt, anthropic_messages).
    """
    system_prompt = ""
    anthropic_msgs: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_prompt = msg.get("content", "")

        elif role == "user":
            anthropic_msgs.append({"role": "user", "content": msg["content"]})

        elif role == "assistant":
            content_blocks: list[dict[str, Any]] = []
            text = msg.get("content", "")
            if text:
                content_blocks.append({"type": "text", "text": text})
            # Convert OpenAI tool_calls to Anthropic tool_use blocks
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", str(uuid.uuid4())),
                    "name": func.get("name", ""),
                    "input": args,
                })
            if content_blocks:
                anthropic_msgs.append({"role": "assistant", "content": content_blocks})
            else:
                anthropic_msgs.append({"role": "assistant", "content": text or ""})

        elif role == "tool":
            # Anthropic expects tool results as user messages with tool_result blocks
            anthropic_msgs.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }],
            })

    return system_prompt, anthropic_msgs


def _convert_tools_for_anthropic(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert OpenAI-format tool definitions to Anthropic format.

    OpenAI: ``{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}``
    Anthropic: ``{"name": ..., "description": ..., "input_schema": ...}``
    """
    if not tools:
        return []

    anthropic_tools: list[dict[str, Any]] = []
    for tool in tools:
        func = tool.get("function", {})
        anthropic_tools.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


class AnthropicStreamAdapter:
    """Adapter for Anthropic Claude models via the native anthropic SDK.

    Parameters
    ----------
    api_key:
        Anthropic API key.  Falls back to ``ANTHROPIC_API_KEY`` env var.
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
        default_model: str = "",
        default_temperature: float = 0.4,
        default_max_tokens: int = 16384,
    ) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "No Anthropic API key found.  Set ANTHROPIC_API_KEY in your .env "
                "file or pass api_key explicitly."
            )

        self._default_model = default_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "The anthropic package is required for Anthropic adapters.  "
                "Install it with: pip install anthropic"
            ) from exc

        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)

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
        """Stream a chat completion via the Anthropic API.

        Yields :class:`StreamEvent` instances as tokens arrive.
        """
        resolved_model = model or self._default_model
        resolved_temp = temperature if temperature is not None else self._default_temperature
        resolved_max = max_tokens if max_tokens is not None else self._default_max_tokens

        system_prompt, anthropic_messages = _convert_messages_for_anthropic(messages)
        anthropic_tools = _convert_tools_for_anthropic(tools)

        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": anthropic_messages,
            "max_tokens": resolved_max,
            "temperature": resolved_temp,
        }

        if system_prompt:
            request_kwargs["system"] = system_prompt

        if anthropic_tools:
            request_kwargs["tools"] = anthropic_tools

        request_kwargs.update(kwargs)

        # Accumulate state
        content = ""
        resp_model = resolved_model
        tool_blocks: dict[int, dict[str, Any]] = {}
        current_block_idx = -1
        usage: dict[str, int] = {}
        finish_reason: str | None = None

        async with self._client.messages.stream(**request_kwargs) as stream:
            async for event in stream:
                event_type = getattr(event, "type", "")

                if event_type == "message_start":
                    msg = getattr(event, "message", None)
                    if msg:
                        resp_model = getattr(msg, "model", resolved_model)
                        msg_usage = getattr(msg, "usage", None)
                        if msg_usage:
                            usage["prompt_tokens"] = getattr(msg_usage, "input_tokens", 0)

                elif event_type == "content_block_start":
                    current_block_idx += 1
                    block = getattr(event, "content_block", None)
                    if block:
                        block_type = getattr(block, "type", "")
                        if block_type == "tool_use":
                            tool_blocks[current_block_idx] = {
                                "id": getattr(block, "id", str(uuid.uuid4())),
                                "type": "function",
                                "function": {
                                    "name": getattr(block, "name", ""),
                                    "arguments": "",
                                },
                            }
                            yield StreamEvent(
                                event_type="tool_call_start",
                                content=content,
                                model=resp_model,
                            )

                elif event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        delta_type = getattr(delta, "type", "")
                        if delta_type == "text_delta":
                            text = getattr(delta, "text", "")
                            if text:
                                content += text
                                yield StreamEvent(
                                    event_type="text_delta",
                                    content=content,
                                    delta_text=text,
                                    model=resp_model,
                                )
                        elif delta_type == "input_json_delta":
                            partial_json = getattr(delta, "partial_json", "")
                            if partial_json and current_block_idx in tool_blocks:
                                tool_blocks[current_block_idx]["function"]["arguments"] += partial_json
                                yield StreamEvent(
                                    event_type="tool_call_delta",
                                    content=content,
                                    model=resp_model,
                                )

                elif event_type == "content_block_stop":
                    if current_block_idx in tool_blocks:
                        yield StreamEvent(
                            event_type="tool_call_end",
                            content=content,
                            model=resp_model,
                        )

                elif event_type == "message_delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        stop_reason = getattr(delta, "stop_reason", None)
                        if stop_reason:
                            # Map Anthropic stop reasons to OpenAI finish reasons
                            if stop_reason == "tool_use":
                                finish_reason = "tool_calls"
                            elif stop_reason == "end_turn":
                                finish_reason = "stop"
                            else:
                                finish_reason = stop_reason
                    msg_usage = getattr(event, "usage", None)
                    if msg_usage:
                        usage["completion_tokens"] = getattr(msg_usage, "output_tokens", 0)
                        usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)

        # Finalise tool calls
        final_tool_calls: list[dict[str, Any]] = []
        for idx in sorted(tool_blocks.keys()):
            final_tool_calls.append(tool_blocks[idx])

        yield StreamEvent(
            event_type="done",
            content=content,
            tool_calls=final_tool_calls,
            finish_reason=finish_reason,
            model=resp_model,
            usage=usage,
        )

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Google Gemini streaming chat adapter.

Implements the :class:`StreamingChatAdapter` protocol using the
``google.generativeai`` SDK.  Converts between OpenAI-format messages and
Gemini's native content format.

Lazy-imports the ``google-generativeai`` package so that users of other
providers do not need it installed.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, AsyncGenerator

from kaizen_agents.delegate.adapters.protocol import StreamEvent

logger = logging.getLogger(__name__)


def _convert_messages_for_gemini(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert OpenAI-format messages to Gemini content format.

    Returns (system_instruction, gemini_contents).

    Gemini uses ``user``/``model`` roles and ``parts`` instead of
    ``content`` strings.  Tool results are ``function_response`` parts.
    """
    system_instruction = ""
    contents: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_instruction = msg.get("content", "")

        elif role == "user":
            contents.append({
                "role": "user",
                "parts": [{"text": msg.get("content", "")}],
            })

        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            text = msg.get("content", "")
            if text:
                parts.append({"text": text})
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
                parts.append({
                    "function_call": {
                        "name": func.get("name", ""),
                        "args": args,
                    }
                })
            if parts:
                contents.append({"role": "model", "parts": parts})

        elif role == "tool":
            contents.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": msg.get("name", ""),
                        "response": {"result": msg.get("content", "")},
                    }
                }],
            })

    return system_instruction, contents


def _convert_tools_for_gemini(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Convert OpenAI-format tool defs to Gemini function_declarations.

    Gemini expects tools as:
    ``[{"function_declarations": [{"name": ..., "description": ..., "parameters": ...}]}]``
    """
    if not tools:
        return None

    declarations: list[dict[str, Any]] = []
    for tool in tools:
        func = tool.get("function", {})
        declarations.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "parameters": func.get("parameters", {"type": "object", "properties": {}}),
        })

    return [{"function_declarations": declarations}]


class GoogleStreamAdapter:
    """Adapter for Google Gemini models via the google-generativeai SDK.

    Parameters
    ----------
    api_key:
        Google API key.  Falls back to ``GOOGLE_API_KEY`` or
        ``GEMINI_API_KEY`` env vars.
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
        resolved_key = (
            api_key
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        if not resolved_key:
            raise ValueError(
                "No Google API key found.  Set GOOGLE_API_KEY or GEMINI_API_KEY "
                "in your .env file or pass api_key explicitly."
            )

        self._default_model = default_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "The google-generativeai package is required for Google adapters.  "
                "Install it with: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=resolved_key)
        self._genai = genai

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
        """Stream a chat completion via the Gemini API.

        Yields :class:`StreamEvent` instances as tokens arrive.
        """
        resolved_model = model or self._default_model
        resolved_temp = temperature if temperature is not None else self._default_temperature
        resolved_max = max_tokens if max_tokens is not None else self._default_max_tokens

        system_instruction, gemini_contents = _convert_messages_for_gemini(messages)
        gemini_tools = _convert_tools_for_gemini(tools)

        generation_config = {
            "temperature": resolved_temp,
            "max_output_tokens": resolved_max,
        }

        model_kwargs: dict[str, Any] = {
            "model_name": resolved_model,
            "generation_config": generation_config,
        }
        if system_instruction:
            model_kwargs["system_instruction"] = system_instruction
        if gemini_tools:
            model_kwargs["tools"] = gemini_tools

        generative_model = self._genai.GenerativeModel(**model_kwargs)

        # Accumulate state
        content = ""
        tool_calls: list[dict[str, Any]] = []
        resp_model = resolved_model
        usage: dict[str, int] = {}
        finish_reason: str | None = None

        response = await generative_model.generate_content_async(
            gemini_contents,
            stream=True,
        )

        async for chunk in response:
            # Extract text from parts
            if chunk.parts:
                for part in chunk.parts:
                    # Text part
                    if hasattr(part, "text") and part.text:
                        content += part.text
                        yield StreamEvent(
                            event_type="text_delta",
                            content=content,
                            delta_text=part.text,
                            model=resp_model,
                        )

                    # Function call part
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        tc_dict = {
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {
                                "name": fc.name,
                                "arguments": json.dumps(dict(fc.args)) if fc.args else "{}",
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

            # Usage metadata (if available)
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                um = chunk.usage_metadata
                usage = {
                    "prompt_tokens": getattr(um, "prompt_token_count", 0) or 0,
                    "completion_tokens": getattr(um, "candidates_token_count", 0) or 0,
                    "total_tokens": getattr(um, "total_token_count", 0) or 0,
                }

        # Determine finish reason
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

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Google Gemini streaming chat adapter.

Implements the :class:`StreamingChatAdapter` protocol using the supported
``google.genai`` SDK (the ``google-genai`` package).  Converts between
OpenAI-format messages and Gemini's native content format.

Lazy-imports ``google.genai`` so that import of this module does not pull the
SDK into processes that only use other providers; the package itself is a
runtime dependency of ``kaizen-agents`` (see ``pyproject.toml``).
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
            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": msg.get("content", "")}],
                }
            )

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
                parts.append(
                    {
                        "function_call": {
                            "name": func.get("name", ""),
                            "args": args,
                        }
                    }
                )
            if parts:
                contents.append({"role": "model", "parts": parts})

        elif role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": msg.get("name", ""),
                                "response": {"result": msg.get("content", "")},
                            }
                        }
                    ],
                }
            )

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
        declarations.append(
            {
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "parameters": func.get(
                    "parameters", {"type": "object", "properties": {}}
                ),
            }
        )

    return [{"function_declarations": declarations}]


def _iter_chunk_parts(chunk: Any) -> list[Any]:
    """Yield the content parts of a ``google.genai`` streaming chunk.

    The ``google.genai`` ``GenerateContentResponse`` does not expose ``parts``
    directly (the ``google.generativeai`` SDK did); parts live under
    ``chunk.candidates[0].content.parts``. Returns an empty list for chunks
    with no candidate/content (e.g. a trailing usage-only chunk).
    """
    candidates = getattr(chunk, "candidates", None) or []
    if not candidates:
        return []
    content = getattr(candidates[0], "content", None)
    if content is None:
        return []
    return list(getattr(content, "parts", None) or [])


class GoogleStreamAdapter:
    """Adapter for Google Gemini models via the google-genai SDK.

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
        ungoverned: bool = False,
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
        self._ungoverned = ungoverned

        # #1779 governance_required posture: this adapter egresses DIRECTLY via
        # the google-genai SDK (stream_chat -> self._client...), NOT through the
        # gated four-axis kaizen.llm.LlmClient. Gate at construction, fail-closed:
        # no mock path here (always a real genai.Client), so is_mock=False; the
        # only exemption is ungoverned=True (or posture OFF). Runs BEFORE building
        # the client so a refusal wastes no transport.
        from kaizen.llm.governance_gate import enforce_governance_posture

        enforce_governance_posture(
            is_mock=False,
            ungoverned=ungoverned,
            surface="kaizen_agents.GoogleAdapter",
        )

        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise ImportError(
                "The google-genai package is required for Google adapters.  "
                "Install it with: pip install google-genai"
            ) from exc

        self._client = genai.Client(api_key=resolved_key)
        self._types = genai_types

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
        resolved_temp = (
            temperature if temperature is not None else self._default_temperature
        )
        resolved_max = (
            max_tokens if max_tokens is not None else self._default_max_tokens
        )

        system_instruction, gemini_contents = _convert_messages_for_gemini(messages)
        gemini_tools = _convert_tools_for_gemini(tools)

        config_kwargs: dict[str, Any] = {
            "temperature": resolved_temp,
            "max_output_tokens": resolved_max,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools

        config = self._types.GenerateContentConfig(**config_kwargs)

        # Accumulate state
        content = ""
        tool_calls: list[dict[str, Any]] = []
        resp_model = resolved_model
        usage: dict[str, int] = {}
        finish_reason: str | None = None

        response = await self._client.aio.models.generate_content_stream(
            model=resolved_model,
            contents=gemini_contents,
            config=config,
        )

        async for chunk in response:
            # Extract text from parts (google.genai nests parts under
            # candidates[0].content.parts; see _iter_chunk_parts).
            chunk_parts = _iter_chunk_parts(chunk)
            if chunk_parts:
                for part in chunk_parts:
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
                                "arguments": (
                                    json.dumps(dict(fc.args)) if fc.args else "{}"
                                ),
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
        finish_reason = "tool_calls" if tool_calls else "stop"

        yield StreamEvent(
            event_type="done",
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=resp_model,
            usage=usage,
        )

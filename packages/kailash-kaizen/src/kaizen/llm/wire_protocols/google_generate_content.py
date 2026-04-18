# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Google Gemini GenerateContent wire protocol shaper.

Gemini's ``/v1beta/models/{model}:generateContent`` schema uses:

* ``contents`` (list of ``{role, parts: [{text}]}``) — not ``messages``.
* Role names: ``user`` and ``model`` (no ``assistant`` or ``system``).
* ``systemInstruction`` is a top-level field with a ``parts`` list.
* ``generationConfig`` holds temperature / max_output_tokens / top_p.
* Response: ``candidates[0].content.parts[0].text``.

See https://ai.google.dev/api/generate-content for the canonical schema.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)


def _role_from_openai(role: str) -> str:
    """Map OpenAI role names to Gemini role names.

    Gemini has only two non-system roles: ``user`` and ``model``. OpenAI's
    ``assistant`` maps to ``model``. Any other role (``tool``, ``function``)
    falls through to ``user`` — Gemini's own function-calling schema uses
    ``functionResponse`` parts inside a ``user``-role turn.
    """
    if role == "assistant":
        return "model"
    if role == "model":
        return "model"
    # Default: user. Covers "user", "tool", "function", "system" (system is
    # partitioned out before this function is called).
    return "user"


def _extract_text_parts(content: Any) -> List[Dict[str, Any]]:
    """Turn a message's ``content`` field into Gemini ``parts`` list.

    OpenAI messages carry either a string or a list of content blocks;
    Gemini expects a list of ``{text}`` / ``{inlineData}`` / etc. parts.
    We pass through text blocks as ``{"text": ...}`` and leave non-text
    block types unchanged (callers may inject ``inlineData`` for vision).
    """
    if isinstance(content, str):
        return [{"text": content}]
    if isinstance(content, list):
        parts: List[Dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append({"text": block.get("text", "")})
                else:
                    parts.append(block)
            elif isinstance(block, str):
                parts.append({"text": block})
        return parts
    # Fallback: coerce to string for safety.
    return [{"text": str(content)}]


def _partition_system(
    messages: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]] | None, List[Dict[str, Any]]]:
    """Split messages into (system_parts, non_system_messages)."""
    system_parts: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            system_parts.extend(_extract_text_parts(msg.get("content", "")))
        else:
            rest.append(msg)
    return (system_parts if system_parts else None), rest


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the GenerateContent request body for Gemini.

    Note: the model name is carried in the URL path (``:generateContent``
    is appended to ``/models/{model}``), not in the body. The HTTP sender
    in Session 3+ consults ``request.model`` when building the URL; the
    payload here does NOT duplicate the field.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    system_parts, rest = _partition_system(request.messages)
    contents: List[Dict[str, Any]] = [
        {
            "role": _role_from_openai(msg.get("role", "user")),
            "parts": _extract_text_parts(msg.get("content", "")),
        }
        for msg in rest
    ]

    generation_config: Dict[str, Any] = {}
    if request.temperature is not None:
        generation_config["temperature"] = request.temperature
    if request.top_p is not None:
        generation_config["topP"] = request.top_p
    if request.max_tokens is not None:
        generation_config["maxOutputTokens"] = request.max_tokens
    if request.stop:
        generation_config["stopSequences"] = list(request.stop)

    payload: Dict[str, Any] = {"contents": contents}
    if generation_config:
        payload["generationConfig"] = generation_config
    if system_parts is not None:
        payload["systemInstruction"] = {"parts": system_parts}
    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalized view from a Gemini ``generateContent`` response.

    Response shape:

        {
          "candidates": [
            {"content": {"parts": [{"text": "..."}]}, "finishReason": "STOP"}
          ],
          "usageMetadata": {"promptTokenCount": N, "candidatesTokenCount": M}
        }
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    candidates = payload.get("candidates", []) or []
    texts: List[str] = []
    finish_reason: Any = None
    if candidates and isinstance(candidates[0], dict):
        first = candidates[0]
        finish_reason = first.get("finishReason")
        content = first.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict):
                    text_value = part.get("text")
                    if isinstance(text_value, str):
                        texts.append(text_value)

    usage = payload.get("usageMetadata", {}) or {}
    return {
        "text": "".join(texts),
        "usage": {
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        },
        "stop_reason": finish_reason,
        "model": payload.get("modelVersion"),
    }


__all__ = ["build_request_payload", "parse_response"]

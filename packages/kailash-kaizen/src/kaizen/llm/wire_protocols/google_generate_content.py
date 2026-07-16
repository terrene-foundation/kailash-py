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

import json
import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)

# OpenAI tool_choice string mode -> Gemini function_calling_config mode.
_TOOL_CHOICE_MODE = {"auto": "AUTO", "required": "ANY", "none": "NONE"}


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

    # Wave-1b completion-shaping fields (all Optional, byte-neutral when unset).
    # top_k / seed / n / frequency_penalty / presence_penalty MERGE into the
    # existing generationConfig above — never clobber temperature/top_p/max.
    if request.top_k is not None:
        generation_config["topK"] = request.top_k
    if request.seed is not None:
        generation_config["seed"] = request.seed
    if request.n is not None:
        # Gemini names OpenAI's `n` (candidate count) `candidateCount`.
        generation_config["candidateCount"] = request.n
    if request.frequency_penalty is not None:
        generation_config["frequencyPenalty"] = request.frequency_penalty
    if request.presence_penalty is not None:
        generation_config["presencePenalty"] = request.presence_penalty
    # logit_bias: Gemini's generateContent has no equivalent — DO NOT emit it.

    # response_format -> Gemini structured-output on generationConfig. Gemini
    # supports JSON mode via responseMimeType, plus an optional responseSchema.
    # ONLY force JSON mode for the JSON response types — an OpenAI
    # ``{"type": "text"}`` must NOT be coerced into JSON (Gemini defaults to
    # text, so emit nothing for it).
    if request.response_format is not None:
        rf_type = request.response_format.get("type")
        if rf_type in ("json_object", "json_schema"):
            generation_config["responseMimeType"] = "application/json"
            schema = _extract_json_schema(request.response_format)
            if schema is not None:
                generation_config["responseSchema"] = schema

    payload: Dict[str, Any] = {"contents": contents}
    if generation_config:
        payload["generationConfig"] = generation_config
    if system_parts is not None:
        payload["systemInstruction"] = {"parts": system_parts}

    # tools -> Gemini top-level `tools` with functionDeclarations, translating
    # the OpenAI function-schema form to Gemini's shape. Guard on truthiness so
    # an explicitly-set EMPTY list (`tools=[]`) emits nothing — emitting
    # `tools:[{functionDeclarations:[]}]` + a forced `toolConfig` mode:ANY would
    # be a degenerate forced-call-with-no-functions request (matches the
    # openai/anthropic empty-tools guard).
    if request.tools:
        payload["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": fn["function"]["name"],
                        "description": fn["function"].get("description", ""),
                        "parameters": fn["function"].get("parameters", {}),
                    }
                    for fn in request.tools
                ]
            }
        ]
        # tool_choice -> Gemini toolConfig.functionCallingConfig.mode. Only
        # emitted when tools are set (a mode with no tools is meaningless).
        tool_config = _tool_config_from_choice(request.tool_choice)
        if tool_config is not None:
            payload["toolConfig"] = tool_config

    return payload


def _extract_json_schema(response_format: Dict[str, Any]) -> Dict[str, Any] | None:
    """Pull a JSON schema out of an OpenAI-shaped ``response_format``.

    OpenAI carries a schema under ``{"type": "json_schema", "json_schema":
    {"schema": {...}}}``; a bare ``{"type": "json_object"}`` has none. Returns
    the schema dict (Gemini ``responseSchema``) or ``None`` when absent.
    """
    json_schema = response_format.get("json_schema")
    if isinstance(json_schema, dict):
        schema = json_schema.get("schema")
        if isinstance(schema, dict):
            return schema
    return None


def _tool_config_from_choice(tool_choice: Any) -> Dict[str, Any] | None:
    """Translate an OpenAI ``tool_choice`` to a Gemini ``tool_config``.

    OpenAI ``"auto"``/``"required"``/``"none"`` map to Gemini modes
    ``AUTO``/``ANY``/``NONE``. A forced-tool dict
    (``{"type": "function", "function": {"name": ...}}``) maps to ``ANY`` plus
    ``allowedFunctionNames``. When tools are set but ``tool_choice`` is unset,
    the default is ``ANY`` (legacy "required" semantics).
    """
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function", {})
        name = fn.get("name") if isinstance(fn, dict) else None
        config: Dict[str, Any] = {"mode": "ANY"}
        if name is not None:
            config["allowedFunctionNames"] = [name]
        return {"functionCallingConfig": config}
    if isinstance(tool_choice, str):
        mode = _TOOL_CHOICE_MODE.get(tool_choice, "ANY")
        return {"functionCallingConfig": {"mode": mode}}
    # tool_choice is None but tools are set -> default to ANY (required).
    return {"functionCallingConfig": {"mode": "ANY"}}


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
    tool_calls: List[Dict[str, Any]] = []
    finish_reason: Any = None
    if candidates and isinstance(candidates[0], dict):
        first = candidates[0]
        finish_reason = first.get("finishReason")
        content = first.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if isinstance(parts, list):
            for index, part in enumerate(parts):
                if not isinstance(part, dict):
                    continue
                text_value = part.get("text")
                if isinstance(text_value, str):
                    texts.append(text_value)
                # Gemini emits tool invocations as ``functionCall`` parts with
                # no call id; synthesize ``call_{index}`` and JSON-encode args
                # into the canonical normalized shape shared with openai/anthropic.
                function_call = part.get("functionCall")
                if isinstance(function_call, dict):
                    tool_calls.append(
                        {
                            "id": f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": function_call.get("name"),
                                "arguments": json.dumps(function_call.get("args", {})),
                            },
                        }
                    )

    usage = payload.get("usageMetadata", {}) or {}
    result: Dict[str, Any] = {
        "text": "".join(texts),
        "usage": {
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        },
        "stop_reason": finish_reason,
        "model": payload.get("modelVersion"),
    }
    # Only surface tool_calls when ≥1 functionCall part is present; a
    # tool-less response keeps the pre-#1720 parsed keys unchanged.
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

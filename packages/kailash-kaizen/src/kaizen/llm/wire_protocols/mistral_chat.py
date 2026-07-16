# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Mistral Chat Completions wire protocol shaper.

Mistral's ``/v1/chat/completions`` endpoint is OpenAI-schema-compatible
with a handful of provider-specific deltas:

* ``safe_prompt`` (bool) — Mistral-only; toggles the hosted moderation
  layer. Absent from OpenAI's schema.
* ``random_seed`` (int) — Mistral-only equivalent of OpenAI's ``seed``.
* Response shape mirrors OpenAI's ``choices[0].message.content``.

The distinct ``MistralChat`` wire tag (vs ``OpenAiChat``) lets us evolve
Mistral-specific fields without polluting the canonical OpenAI shape.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from kaizen.llm.deployment import CompletionRequest


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/v1/chat/completions`` request body for Mistral.

    Follows the OpenAI chat completion schema closely — every optional
    field is only emitted if the caller set it, so the produced payload
    is stable across Python dict-ordering changes.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    payload: Dict[str, Any] = {
        "model": request.model,
        "messages": list(request.messages),
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.stop:
        payload["stop"] = list(request.stop)
    if request.stream:
        payload["stream"] = True
    if request.user is not None:
        # Mistral does not define a top-level `user` field but accepts it
        # in the request body as a tenant-tracking hint. Emitting it keeps
        # audit trails on the provider side linked to our caller id.
        payload["user"] = request.user

    # --- #1720 Wave-1b completion-shaping emission (Mistral deltas from OpenAI) ---
    # Tool / function calling: Mistral uses the OpenAI function-schema list, so
    # `tools` passes through verbatim. Guard on truthiness so an explicitly-set
    # EMPTY list (`tools=[]`) emits nothing. `tool_choice` is meaningless without
    # tools, so it is emitted ONLY alongside a non-empty tools list (matching the
    # openai/anthropic/google adapters — the four-axis consistency contract).
    #
    # Mistral's tool_choice vocabulary differs from OpenAI's: force-a-tool is
    # "any" (NOT OpenAI's "required"). Map "required"->"any"; "auto"/"none"/"any"
    # pass through; an unknown string falls back to "any" (the tools-set forced
    # default, the same conservative choice the anthropic adapter makes). A dict
    # is a named-tool forced selection: Mistral accepts the OpenAI-shaped
    # {"type":"function","function":{"name":X}} object form, so it passes through.
    # When tools are present but tool_choice is unset, default to "any" (the
    # pinned Wave-1a legacy "force a tool"-when-tools default, in Mistral's
    # vocabulary).
    if request.tools:
        payload["tools"] = list(request.tools)
        tool_choice = request.tool_choice
        if tool_choice is None:
            payload["tool_choice"] = "any"
        elif isinstance(tool_choice, str):
            if tool_choice == "required":
                payload["tool_choice"] = "any"
            elif tool_choice in ("auto", "none", "any"):
                payload["tool_choice"] = tool_choice
            else:
                payload["tool_choice"] = "any"
        else:
            payload["tool_choice"] = tool_choice
    # Structured output: Mistral supports {"type": "json_object"} verbatim.
    # Truthiness guard so an empty ``response_format={}`` (set but degenerate —
    # no ``type``) emits nothing rather than a malformed key.
    if request.response_format:
        payload["response_format"] = request.response_format
    # Extended sampling. Mistral's seed parameter is ``random_seed`` (NOT
    # ``seed`` like OpenAI); frequency_penalty / presence_penalty / n share the
    # OpenAI names.
    if request.seed is not None:
        payload["random_seed"] = request.seed
    if request.frequency_penalty is not None:
        payload["frequency_penalty"] = request.frequency_penalty
    if request.presence_penalty is not None:
        payload["presence_penalty"] = request.presence_penalty
    if request.n is not None:
        payload["n"] = request.n
    # Deliberately OMITTED — Mistral's /v1/chat/completions does NOT support:
    #   top_k      — not exposed by the Mistral chat API (it is an
    #                Anthropic/Google/Cohere/Ollama-family field).
    #   logit_bias — no Mistral equivalent.
    # Emitting a bogus key for either would ship a feature Mistral does not have
    # (zero-tolerance: no fake capability), so nothing is written for them.
    return payload


def _normalize_tool_call(tc: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce one Mistral ``message.tool_calls`` entry into the canonical shape.

    The canonical normalized shape (shared with the openai/anthropic/google
    shards) is::

        {"id": <str>, "type": "function",
         "function": {"name": <str>, "arguments": <str: JSON-encoded>}}

    Mistral returns the OpenAI-shaped entry where ``arguments`` is already a
    JSON string. Defensively, if a Mistral response returns ``arguments`` as a
    dict/list, coerce it via ``json.dumps`` so the canonical "arguments is a
    JSON string" invariant holds. Rebuilds a plain JSON-serializable dict so no
    provider SDK object leaks into the parsed result.
    """
    function = tc.get("function")
    function = function if isinstance(function, dict) else {}
    arguments = function.get("arguments")
    if isinstance(arguments, (dict, list)):
        arguments = json.dumps(arguments)
    return {
        "id": tc.get("id"),
        "type": tc.get("type", "function"),
        "function": {
            "name": function.get("name"),
            "arguments": arguments,
        },
    }


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract normalized ``{text, usage}`` from a Mistral chat response.

    Mistral response shape matches OpenAI's:

        {
          "choices": [{"message": {"content": "..."}, "finish_reason": "..."}],
          "usage": {"prompt_tokens": N, "completion_tokens": M, "total_tokens": T}
        }
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    choices = payload.get("choices", []) or []
    text = ""
    finish_reason: Any = None
    tool_calls: Any = None
    if choices and isinstance(choices[0], dict):
        first = choices[0]
        finish_reason = first.get("finish_reason")
        message = first.get("message", {})
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                text = content
            # #1720 Wave-1b: surface tool calls. Mistral returns OpenAI-shaped
            # `message.tool_calls`; normalize each into the canonical shape
            # ([{"id", "type": "function", "function": {"name", "arguments"}}]
            # with `arguments` a JSON-encoded string), shared with the
            # openai/anthropic/google shards. Emit as plain JSON-serializable
            # dicts, only when present — so a plain text response stays
            # byte-identical to the pre-Wave-1b parsed shape.
            raw_tool_calls = message.get("tool_calls")
            if isinstance(raw_tool_calls, list) and raw_tool_calls:
                tool_calls = [
                    _normalize_tool_call(tc)
                    for tc in raw_tool_calls
                    if isinstance(tc, dict)
                ]
    usage = payload.get("usage", {}) or {}
    result: Dict[str, Any] = {
        "text": text,
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "stop_reason": finish_reason,
        "model": payload.get("model"),
    }
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

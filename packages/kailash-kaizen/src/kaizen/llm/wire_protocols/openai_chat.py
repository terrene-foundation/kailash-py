# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""OpenAI Chat Completions wire protocol shaper (#1717).

Shapes the on-the-wire request/response for OpenAI's
``POST /v1/chat/completions`` endpoint. Consumed by ``LlmClient.complete()``
via its ``WireProtocol.OpenAiChat`` dispatch path.

Every OpenAI-compatible provider (Groq, Together, Fireworks, OpenRouter,
DeepSeek, Perplexity, Azure OpenAI, LM Studio, llama.cpp, Docker Model
Runner) shares this shape — they differ only in endpoint URL + auth, not in
the request/response body — so this single shaper serves them all.

Request schema (OpenAI documented contract):

* ``model`` (str)     — required; carried in the body (NOT the URL).
* ``messages`` (list) — required; ``[{"role", "content"}, ...]`` passed
  through verbatim so multimodal / tool blocks survive.
* ``temperature`` / ``top_p`` / ``max_tokens`` / ``stop`` / ``stream`` /
  ``user`` — only emitted when the caller set them, so the produced payload
  is stable across Python dict-ordering changes. The token-limit field name is
  model-aware: OpenAI GPT-5 / o-series require ``max_completion_tokens`` (they
  400 on ``max_tokens``), while OpenAI-compatible providers keep ``max_tokens``
  (see ``_token_limit_field``).

Response schema:

    {
      "choices": [{"message": {"content": "..."}, "finish_reason": "..."}],
      "usage": {"prompt_tokens": N, "completion_tokens": M, "total_tokens": T},
      "model": "gpt-4o-..."
    }

Cross-SDK parity: this shaper's output for a fixed input is byte-identical
to its Rust counterpart's OpenAI chat payload builder.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.reasoning_filter import filter_reasoning_model_params

logger = logging.getLogger(__name__)

# OpenAI's GPT-5 family and the o-series reasoning models REJECT `max_tokens`
# with a hard HTTP 400 ("'max_tokens' is not supported with this model; use
# 'max_completion_tokens'") — verified live 2026-07-14 against `gpt-5.6-sol`.
# OpenAI-compatible third-party providers that share this wire (DeepSeek, Groq,
# Together, Fireworks, OpenRouter, Perplexity, LM Studio, llama.cpp, Ollama,
# Docker Model Runner) still use `max_tokens`. Pick the field by model family so
# both work. Match is on the resolved model id; unknown ids keep `max_tokens`.
_MAX_COMPLETION_TOKENS_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _token_limit_field(model: str) -> str:
    m = (model or "").lower()
    if any(m.startswith(p) for p in _MAX_COMPLETION_TOKENS_MODEL_PREFIXES):
        return "max_completion_tokens"
    return "max_tokens"


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/v1/chat/completions`` request body for OpenAI.

    Emits the canonical OpenAI chat shape. Optional fields are written only
    when the caller set them so callers relying on server defaults do NOT
    get a silent override.

    #1720 Wave-1b reasoning-model filter: before any sampling field is
    written to the payload, ``temperature`` / ``top_p`` / ``frequency_penalty``
    / ``presence_penalty`` are routed through
    :func:`kaizen.llm.reasoning_filter.filter_reasoning_model_params`. o1/o3
    reasoning models reject these fields outright (HTTP 400); gpt-5 requires
    ``temperature == 1.0`` and rejects the others. Every other model family
    is a byte-neutral passthrough — this shaper's output for a fixed
    non-reasoning-model input is unchanged from before this filter existed.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    payload: Dict[str, Any] = {
        "model": request.model,
        "messages": list(request.messages),
    }

    # Collect the caller-set sampling fields, THEN filter by model family —
    # insertion into `payload` still happens at each field's ORIGINAL
    # position below, so key order (and therefore JSON byte output) is
    # unchanged for every model the filter leaves untouched.
    sampling: Dict[str, Any] = {}
    if request.temperature is not None:
        sampling["temperature"] = request.temperature
    if request.top_p is not None:
        sampling["top_p"] = request.top_p
    if request.frequency_penalty is not None:
        sampling["frequency_penalty"] = request.frequency_penalty
    if request.presence_penalty is not None:
        sampling["presence_penalty"] = request.presence_penalty
    filtered_sampling = filter_reasoning_model_params(request.model, sampling)
    if filtered_sampling != sampling:
        logger.debug(
            "openai_chat.reasoning_model_params_filtered",
            extra={
                "before_keys": sorted(sampling),
                "after_keys": sorted(filtered_sampling),
            },
        )

    if "temperature" in filtered_sampling:
        payload["temperature"] = filtered_sampling["temperature"]
    if "top_p" in filtered_sampling:
        payload["top_p"] = filtered_sampling["top_p"]
    if request.max_tokens is not None:
        payload[_token_limit_field(request.model)] = request.max_tokens
    if request.stop:
        payload["stop"] = list(request.stop)
    if request.stream:
        payload["stream"] = True
    if request.user is not None:
        payload["user"] = request.user

    # --- #1720 Wave-1b completion-shaping emission (OpenAI is the canonical shape) ---
    # Tool / function calling: `tools` is already the OpenAI function-schema list,
    # emitted verbatim. Guard on truthiness so an explicitly-set EMPTY list
    # (`tools=[]`) emits nothing. `tool_choice` is meaningless without tools (a
    # forced `"required"`/named choice with no tools is an invalid request), so
    # it is emitted ONLY alongside a non-empty tools list — matching the
    # anthropic/google adapters (the four-axis consistency contract). When tools
    # are present, `tool_choice` defaults to the legacy "required" semantics (a
    # pinned Wave-1a decision) unless the caller set it explicitly.
    if request.tools:
        payload["tools"] = list(request.tools)
        payload["tool_choice"] = (
            request.tool_choice if request.tool_choice is not None else "required"
        )
    # Structured output: OpenAI-native, verbatim passthrough. Truthiness guard so
    # an empty ``response_format={}`` (set but degenerate — no ``type``) emits
    # nothing rather than a malformed key (same empty-collection discipline as
    # the tools guard).
    if request.response_format:
        payload["response_format"] = request.response_format
    # Extended sampling: each passthrough under the same key name when set.
    if request.seed is not None:
        payload["seed"] = request.seed
    # Truthiness guard: an empty ``logit_bias={}`` is a no-op — emit nothing.
    if request.logit_bias:
        payload["logit_bias"] = request.logit_bias
    # #1720 Wave-1b: frequency_penalty / presence_penalty already went through
    # the reasoning-model filter above (dropped for o1/o3/gpt-5); emit here
    # under their ORIGINAL key position so non-reasoning-model payloads keep
    # byte-identical field order.
    if "frequency_penalty" in filtered_sampling:
        payload["frequency_penalty"] = filtered_sampling["frequency_penalty"]
    if "presence_penalty" in filtered_sampling:
        payload["presence_penalty"] = filtered_sampling["presence_penalty"]
    if request.n is not None:
        payload["n"] = request.n
    # top_k: intentionally NOT emitted — the OpenAI chat completions API does not
    # support top_k (it is an Anthropic/Google/Cohere/Mistral/Ollama family field).
    return payload


def _normalize_tool_call(tc: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce one OpenAI ``message.tool_calls`` entry into the canonical shape.

    The canonical normalized shape (shared with the anthropic/google shards) is::

        {"id": <str>, "type": "function",
         "function": {"name": <str>, "arguments": <str: JSON-encoded>}}

    OpenAI already returns this shape (``arguments`` is already a JSON string),
    so this rebuilds a plain, JSON-serializable dict from the response entry —
    guaranteeing no provider SDK object leaks into the parsed result.

    Defensive: this wire also serves OpenAI-COMPATIBLE providers (Groq,
    Together, Fireworks, OpenRouter, DeepSeek, …). A non-conformant one may
    return ``arguments`` as a dict rather than a JSON string; coerce it so the
    canonical "arguments is a JSON string" invariant holds across the fleet.
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
    """Extract normalized ``{text, usage, stop_reason, model}`` from a response.

    Handles both the non-streaming ``choices[0].message.content`` shape and
    the streaming ``choices[0].delta.content`` chunk shape so this same
    parser is reusable by ``LlmClient.stream()``.
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
        # Non-stream carries `message`; a streaming chunk carries `delta`.
        message = first.get("message")
        if not isinstance(message, dict):
            message = first.get("delta", {})
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                text = content
            # #1720 Wave-1b: surface tool calls. OpenAI already returns
            # `message.tool_calls` in the canonical normalized shape
            # ([{"id", "type": "function", "function": {"name", "arguments"}}]
            # with `arguments` a JSON-encoded string), shared with the
            # anthropic/google shards. Pass through as plain JSON-serializable
            # dicts (never SDK objects), only when present.
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

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
  is stable across Python dict-ordering changes.

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

from typing import Any, Dict

from kaizen.llm.deployment import CompletionRequest


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/v1/chat/completions`` request body for OpenAI.

    Emits the canonical OpenAI chat shape. Optional fields are written only
    when the caller set them so callers relying on server defaults do NOT
    get a silent override.
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
        payload["user"] = request.user
    return payload


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
    usage = payload.get("usage", {}) or {}
    return {
        "text": text,
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "stop_reason": finish_reason,
        "model": payload.get("model"),
    }


__all__ = ["build_request_payload", "parse_response"]

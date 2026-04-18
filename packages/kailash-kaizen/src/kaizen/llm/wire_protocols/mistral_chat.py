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

from typing import Any, Dict, List

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
    return payload


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
    if choices and isinstance(choices[0], dict):
        first = choices[0]
        finish_reason = first.get("finish_reason")
        message = first.get("message", {})
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

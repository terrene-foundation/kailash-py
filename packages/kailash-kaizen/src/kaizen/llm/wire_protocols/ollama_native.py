# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Ollama Native wire protocol shaper.

Ollama's ``/api/chat`` endpoint:

* ``model`` (str) — required.
* ``messages`` (list of ``{role, content}``) — same shape as OpenAI.
* ``stream`` (bool) — defaults to True in Ollama; we pass through the
  caller's preference so the HTTP layer can choose its reader.
* ``options`` (dict) — Ollama's grab-bag for temperature, top_p,
  num_predict (== max_tokens), stop, etc.
* Response (non-stream): ``{"message": {"content": "..."}, "done": true,
  "eval_count": N, "prompt_eval_count": M}``.

Ollama uses separate keys from OpenAI (``num_predict`` not
``max_tokens``; ``stop`` is a list on the ``options`` dict). The shaper
translates on the way in and the way out so callers work with the
shared :class:`CompletionRequest` contract.

See https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion.
"""

from __future__ import annotations

from typing import Any, Dict

from kaizen.llm.deployment import CompletionRequest


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/api/chat`` request body for Ollama.

    Maps OpenAI-style fields into Ollama's ``options`` dict where the
    server expects them (``num_predict``, ``stop``, ``temperature``,
    ``top_p``). Fields the caller left unset are omitted so the Ollama
    server uses its own defaults.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    options: Dict[str, Any] = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.top_p is not None:
        options["top_p"] = request.top_p
    if request.max_tokens is not None:
        # Ollama's knob is `num_predict` (tokens-to-predict). The semantic
        # mapping is 1:1 with OpenAI's `max_tokens`.
        options["num_predict"] = request.max_tokens
    if request.stop:
        options["stop"] = list(request.stop)

    payload: Dict[str, Any] = {
        "model": request.model,
        "messages": list(request.messages),
        # Ollama defaults `stream=True` server-side; we always pass the
        # caller's explicit choice so the HTTP client can pick the correct
        # reader (streaming JSONL vs single-JSON response).
        "stream": bool(request.stream),
    }
    if options:
        payload["options"] = options
    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalized view from an Ollama ``/api/chat`` response.

    Non-streaming responses carry ``{"message": {"role", "content"},
    "done", "eval_count", "prompt_eval_count", ...}``. Streaming responses
    are JSONL lines of the same shape with ``done: false`` until the last
    chunk — this shaper handles one object at a time so the caller can
    accumulate across a stream.
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    message = payload.get("message", {}) or {}
    text = ""
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            text = content
    return {
        "text": text,
        "usage": {
            "input_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
        },
        "stop_reason": payload.get("done_reason"),
        "model": payload.get("model"),
        "done": payload.get("done", False),
    }


__all__ = ["build_request_payload", "parse_response"]

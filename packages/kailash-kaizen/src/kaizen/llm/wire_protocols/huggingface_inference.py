# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HuggingFace Inference API wire protocol shaper.

HuggingFace Inference API exposes a model-specific endpoint at
``POST /models/{model}`` (the ``model`` is in the URL path, not the body).

For text-generation models the canonical request shape is:

    {
      "inputs": "<prompt string>",
      "parameters": {
        "max_new_tokens": N,
        "temperature": T,
        "top_p": P,
        "stop": [...]
      }
    }

For chat-completion models (hosted Inference Endpoints running
``text-generation-inference`` or routed through
``huggingface_hub.InferenceClient``) the ``messages`` shape is
OpenAI-compatible. This shaper supports BOTH: callers who pass a
``messages`` list get the chat shape; callers who pass a single user
message get the classic ``inputs`` shape.

Response (text-generation): ``[{"generated_text": "..."}]``.
Response (chat): OpenAI-style ``{"choices": [{"message": {"content": ...}}]}``.

See https://huggingface.co/docs/api-inference/detailed_parameters.
"""

from __future__ import annotations

from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest


def _flatten_messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    """Render a chat-style message list as a single prompt string.

    Used when the caller submits multi-turn messages against a classic
    text-generation endpoint. Uses the common convention:
    ``[SYSTEM] ... [USER] ... [ASSISTANT] ...``. Chat-aware models that
    speak the OpenAI schema use the ``messages`` path instead — see
    ``build_request_payload`` below.
    """
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "user").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            # Flatten typed blocks, keep only text.
            text_blocks: List[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_blocks.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_blocks.append(block)
            content = "".join(text_blocks)
        parts.append(f"[{role}] {content}")
    parts.append("[ASSISTANT] ")
    return "\n".join(parts)


def build_request_payload(
    request: CompletionRequest, *, use_chat_schema: bool = False
) -> Dict[str, Any]:
    """Build the HuggingFace Inference request body.

    By default emits the classic ``{inputs, parameters}`` shape. When
    ``use_chat_schema=True`` (for Inference Endpoints / TGI servers that
    speak OpenAI chat), emits an OpenAI-style body with ``model`` +
    ``messages``.

    Note on URL routing: the classic endpoint puts the model name in the
    URL path (``/models/{model}``) and does NOT repeat it in the body.
    The chat schema does carry ``model``. The HTTP sender in Session 3+
    consults ``request.model`` for URL construction; this function does
    not produce the URL itself.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    if use_chat_schema:
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
        return payload

    # Classic text-generation schema.
    parameters: Dict[str, Any] = {}
    if request.temperature is not None:
        parameters["temperature"] = request.temperature
    if request.top_p is not None:
        parameters["top_p"] = request.top_p
    if request.max_tokens is not None:
        parameters["max_new_tokens"] = request.max_tokens
    if request.stop:
        parameters["stop"] = list(request.stop)

    body: Dict[str, Any] = {"inputs": _flatten_messages_to_prompt(request.messages)}
    if parameters:
        body["parameters"] = parameters
    return body


def parse_response(payload: Any) -> Dict[str, Any]:
    """Extract normalized view from a HuggingFace Inference response.

    Two shapes are supported:

    * Classic text-generation — a list of ``{"generated_text": "..."}``.
    * Chat schema (TGI OpenAI-compatible) — ``{"choices": [{"message":
      {"content": "..."}}]}``.

    The shaper detects which shape arrived and normalizes to
    ``{text, usage, stop_reason, model}``.
    """
    if isinstance(payload, list):
        texts: List[str] = []
        for entry in payload:
            if isinstance(entry, dict):
                generated = entry.get("generated_text")
                if isinstance(generated, str):
                    texts.append(generated)
        return {
            "text": "".join(texts),
            "usage": {"input_tokens": None, "output_tokens": None},
            "stop_reason": None,
            "model": None,
        }

    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict or list payload")

    # Chat-schema branch.
    if "choices" in payload:
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

    # Single-object text-generation response (rare but documented).
    generated = payload.get("generated_text")
    if isinstance(generated, str):
        return {
            "text": generated,
            "usage": {"input_tokens": None, "output_tokens": None},
            "stop_reason": None,
            "model": None,
        }

    raise ValueError(
        "huggingface_inference.parse_response could not interpret payload: "
        "expected list[generated_text], chat `choices`, or single "
        "`generated_text` object"
    )


__all__ = ["build_request_payload", "parse_response"]

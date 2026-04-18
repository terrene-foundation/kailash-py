# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cohere Chat wire protocol shaper.

Cohere's ``/v1/chat`` schema differs from OpenAI:

* ``message`` (str) holds the current user turn.
* ``chat_history`` (list of ``{role: USER|CHATBOT, message: str}``) carries
  prior turns — Cohere uses uppercase ``USER`` / ``CHATBOT``, not
  ``user`` / ``assistant``.
* ``preamble`` (str) is the optional system prompt.
* ``max_tokens`` / ``temperature`` / ``p`` live at the top level.
* Response: ``text`` at the top level; ``meta.billed_units.{input,output}_tokens``.

See https://docs.cohere.com/reference/chat.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)


def _cohere_role(role: str) -> str:
    """Map OpenAI role names to Cohere chat roles (``USER`` / ``CHATBOT``)."""
    if role == "assistant":
        return "CHATBOT"
    return "USER"


def _content_to_str(content: Any) -> str:
    """Flatten a message's ``content`` into a plain string.

    Cohere's chat_history entries take a single string per turn; content
    blocks (vision) are not supported on this endpoint, so we concatenate
    any text blocks and drop non-text blocks with a debug log.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
            else:
                logger.debug(
                    "cohere_generate.non_text_block_dropped",
                    extra={"block_type": type(block).__name__},
                )
        return "".join(parts)
    return str(content)


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/v1/chat`` request body for Cohere.

    Extracts the last user message as ``message``, maps every earlier
    non-system message into ``chat_history``, and promotes system messages
    to ``preamble``. If there is no trailing user message the request is
    rejected (Cohere requires a current user turn).
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    preamble_parts: List[str] = []
    history: List[Dict[str, str]] = []
    current_message: str | None = None

    for msg in request.messages:
        role = msg.get("role", "user")
        content_str = _content_to_str(msg.get("content", ""))
        if role == "system":
            preamble_parts.append(content_str)
        else:
            history.append({"role": _cohere_role(role), "message": content_str})

    # The trailing user message is the "current" turn; pop it off the
    # history into the `message` field.
    if history and history[-1]["role"] == "USER":
        current_message = history.pop()["message"]

    if current_message is None:
        raise ValueError(
            "cohere_generate.build_request_payload requires a trailing user "
            "message (Cohere's chat API uses the last user turn as `message`)"
        )

    payload: Dict[str, Any] = {
        "model": request.model,
        "message": current_message,
    }
    if history:
        payload["chat_history"] = history
    if preamble_parts:
        payload["preamble"] = "\n".join(preamble_parts)
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["p"] = request.top_p
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.stop:
        payload["stop_sequences"] = list(request.stop)
    if request.stream:
        payload["stream"] = True
    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalized view from a Cohere chat response."""
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    text_value = payload.get("text")
    if not isinstance(text_value, str):
        text_value = ""
    meta = payload.get("meta", {}) or {}
    billed_units = meta.get("billed_units", {}) if isinstance(meta, dict) else {}
    return {
        "text": text_value,
        "usage": {
            "input_tokens": (
                billed_units.get("input_tokens")
                if isinstance(billed_units, dict)
                else None
            ),
            "output_tokens": (
                billed_units.get("output_tokens")
                if isinstance(billed_units, dict)
                else None
            ),
        },
        "stop_reason": payload.get("finish_reason"),
        "model": payload.get("model"),
    }


__all__ = ["build_request_payload", "parse_response"]

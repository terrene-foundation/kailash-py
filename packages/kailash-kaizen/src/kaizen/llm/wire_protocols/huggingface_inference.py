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

import json
import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)


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
            # Flatten typed blocks, keep only text. Non-text blocks (e.g.
            # image_url / image content sent against a text-only classic
            # text-generation endpoint) are dropped — previously silently,
            # now logged at WARNING so the drop is observable rather than a
            # silent content loss (zero-tolerance Rule 3 / observability
            # Rule 7 — a warning is an error the framework chose to keep
            # running through).
            text_blocks: List[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_blocks.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_blocks.append(block)
                else:
                    block_type = (
                        block.get("type")
                        if isinstance(block, dict)
                        else type(block).__name__
                    )
                    logger.warning(
                        "huggingface_inference.non_text_block_dropped",
                        extra={"block_type": block_type},
                    )
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

        # --- #1720 Wave-1b completion-shaping emission (chat-schema path ONLY) ---
        # TGI / Inference Endpoints running the OpenAI-compatible chat schema
        # accept the OpenAI `tools` + `tool_choice` shape verbatim. Guard on
        # truthiness so an explicitly-set EMPTY list (`tools=[]`) emits
        # nothing (matches the openai/anthropic/google/mistral/cohere
        # adapters — the four-axis consistency contract). `tool_choice` is
        # meaningless without tools, so it is emitted ONLY alongside a
        # non-empty tools list.
        #
        # TGI's tool-calling support is grammar-constrained-decoding-based
        # and MODEL-DEPENDENT — not every hosted model/deployment reliably
        # honours a FORCED tool selection. CONSERVATIVELY default the unset
        # case to `"auto"` (let the model decide whether to call a tool)
        # rather than the OpenAI-family Wave-1a legacy `"required"` default
        # (openai_chat / anthropic_messages / google_generate_content) — a
        # forced-tool default that a TGI deployment without full grammar
        # support could reject outright. An explicit caller-set tool_choice
        # (including `"required"`) still passes through verbatim; this only
        # changes the conservative UNSET default.
        if request.tools:
            payload["tools"] = list(request.tools)
            payload["tool_choice"] = (
                request.tool_choice if request.tool_choice is not None else "auto"
            )
        return payload

    # Classic text-generation schema: NO tools concept. TGI's classic
    # `{inputs, parameters}` text-generation endpoint has no OpenAI-shaped
    # tool-calling surface — no documented `tools`/`tool_choice` keys.
    # Emitting them here would advertise a capability the endpoint does not
    # have (zero-tolerance Rule 2: no fake capability), so `request.tools` /
    # `request.tool_choice` are deliberately OMITTED on this path even when
    # set. Callers that need tool calling against a TGI-backed model MUST
    # use `use_chat_schema=True` (TGI / Inference Endpoints), which DOES
    # emit them above.
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


def _normalize_tool_call(tc: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Coerce one chat-schema ``message.tool_calls`` entry into the canonical
    shape shared with the openai/anthropic/google/mistral/cohere shards::

        {"id": <str>, "type": "function",
         "function": {"name": <str>, "arguments": <str: JSON-encoded>}}

    TGI's OpenAI-compatible chat endpoint is expected to return an
    OpenAI-shaped entry (``arguments`` already a JSON string, ``id`` set);
    defensively, if a deployment omits ``id`` or returns ``arguments`` as a
    dict/list, synthesize ``call_{index}`` and ``json.dumps`` the arguments
    so the canonical invariants hold regardless of deployment conformance.
    Rebuilds a plain JSON-serializable dict so no provider SDK object leaks
    into the parsed result.
    """
    function = tc.get("function")
    function = function if isinstance(function, dict) else {}
    arguments = function.get("arguments")
    if isinstance(arguments, (dict, list)):
        arguments = json.dumps(arguments)
    tc_id = tc.get("id")
    if not isinstance(tc_id, str) or not tc_id:
        tc_id = f"call_{index}"
    return {
        "id": tc_id,
        "type": tc.get("type", "function"),
        "function": {
            "name": function.get("name"),
            "arguments": arguments,
        },
    }


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
        tool_calls: Any = None
        if choices and isinstance(choices[0], dict):
            first = choices[0]
            finish_reason = first.get("finish_reason")
            message = first.get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    text = content
                # #1720 Wave-1b: surface tool calls. TGI's OpenAI-compatible
                # chat endpoint may carry OpenAI-shaped `message.tool_calls`;
                # normalize each into the canonical shape ([{"id", "type":
                # "function", "function": {"name", "arguments"}}] with
                # `arguments` a JSON-encoded string), shared with the
                # openai/anthropic/google/mistral/cohere shards. Emit as
                # plain JSON-serializable dicts, only when present — so a
                # plain text response stays byte-identical to the
                # pre-Wave-1b parsed shape.
                raw_tool_calls = message.get("tool_calls")
                if isinstance(raw_tool_calls, list) and raw_tool_calls:
                    tool_calls = [
                        _normalize_tool_call(tc, index)
                        for index, tc in enumerate(raw_tool_calls)
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

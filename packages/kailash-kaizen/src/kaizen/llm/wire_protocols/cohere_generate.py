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

Cohere v1 diverges from OpenAI on several documented field names used by the
#1720 Wave-1b completion-shaping emission below:

* top_k is ``k`` (top_p is ``p``) — NOT ``top_k`` / ``top_p``.
* Tool schemas use ``parameter_definitions`` — a flat ``{param: {description,
  type, required}}`` map with Python-style type names — NOT the OpenAI
  function-schema. ``tool_choice`` does NOT exist on v1 ``/chat`` (forced
  ``REQUIRED`` / ``NONE`` selection arrived only in the v2 ``/chat`` API,
  which this adapter does not target) — so it is deliberately NOT emitted.
* Structured output is ``response_format={"type": "json_object"[, "schema"]}``.
* ``seed`` / ``frequency_penalty`` / ``presence_penalty`` are supported;
  ``n`` and ``logit_bias`` are NOT (deliberately omitted, never faked).

See https://docs.cohere.com/reference/chat.
"""

from __future__ import annotations

import json
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


# JSON-schema primitive ``type`` -> Cohere v1 ``parameter_definitions`` type
# name. Cohere v1 /chat tools use Python-style names ("str"/"int"/"float"/
# "bool"/"list"/"dict"), NOT JSON-schema names ("string"/"integer"/...).
_JSON_SCHEMA_TYPE_TO_COHERE = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def _cohere_param_type(json_type: Any) -> str:
    """Map a JSON-schema ``type`` to a Cohere v1 ``parameter_definitions`` type."""
    if isinstance(json_type, list):
        # JSON schema permits a union-type list; take the first non-null entry.
        for candidate in json_type:
            if candidate != "null":
                json_type = candidate
                break
    if not isinstance(json_type, str):
        return "str"
    return _JSON_SCHEMA_TYPE_TO_COHERE.get(json_type, json_type)


def _to_parameter_definitions(parameters: Any) -> Dict[str, Any]:
    """Translate an OpenAI JSON-schema ``parameters`` object into Cohere v1
    ``parameter_definitions``.

    OpenAI carries function params as a JSON-schema object
    (``{"type": "object", "properties": {...}, "required": [...]}``); Cohere
    v1's ``/chat`` tools use ``parameter_definitions`` — a flat map of
    ``{<param>: {"description", "type", "required"}}`` with Python-style type
    names. A missing / non-object ``parameters`` yields an empty map.
    """
    if not isinstance(parameters, dict):
        return {}
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return {}
    required = parameters.get("required")
    required_set = set(required) if isinstance(required, list) else set()
    definitions: Dict[str, Any] = {}
    for pname, pschema in properties.items():
        pschema = pschema if isinstance(pschema, dict) else {}
        definitions[pname] = {
            "description": pschema.get("description", ""),
            "type": _cohere_param_type(pschema.get("type")),
            "required": pname in required_set,
        }
    return definitions


def _extract_json_schema(response_format: Dict[str, Any]) -> Dict[str, Any] | None:
    """Pull a JSON schema out of an OpenAI-shaped ``response_format``.

    OpenAI carries a schema under ``{"type": "json_schema", "json_schema":
    {"schema": {...}}}``; a bare ``{"type": "json_object"}`` has none. Returns
    the schema dict (Cohere ``response_format.schema``) or ``None`` when absent.
    """
    json_schema = response_format.get("json_schema")
    if isinstance(json_schema, dict):
        schema = json_schema.get("schema")
        if isinstance(schema, dict):
            return schema
    return None


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

    # --- #1720 Wave-1b completion-shaping emission (Cohere v1 /chat schema) ---
    # This adapter targets Cohere's v1 /chat endpoint (see module docstring:
    # message / chat_history / preamble / p). The field names below are the
    # DOCUMENTED v1 names, which diverge from OpenAI (top_k is `k`; tool
    # schemas use `parameter_definitions`).
    #
    # tools: translate the OpenAI function-schema list into Cohere v1's
    # `[{name, description, parameter_definitions}]` shape. Guard on truthiness
    # so an explicitly-set EMPTY list (`tools=[]`) emits nothing (matches the
    # openai/anthropic/google empty-tools guard).
    if request.tools:
        payload["tools"] = [
            {
                "name": f["function"]["name"],
                "description": f["function"].get("description", ""),
                "parameter_definitions": _to_parameter_definitions(
                    f["function"].get("parameters", {})
                ),
            }
            for f in request.tools
        ]
        # tool_choice: Cohere's v1 /chat endpoint has NO tool_choice parameter —
        # forced/`REQUIRED`/`NONE` selection arrived only in the v2 /chat API,
        # which this adapter does NOT target. Emitting one would be a fake
        # feature the v1 API rejects/ignores, so we deliberately emit NOTHING
        # even when tools are set and tool_choice defaults to the legacy
        # "required" intent (mirrors anthropic_messages' response_format
        # omission — no fake feature). Do NOT invent a v1 tool_choice surface.

    # response_format: Cohere v1 /chat supports JSON mode via
    # `response_format={"type": "json_object"}` plus an optional `schema`. Only
    # force JSON mode for the JSON response types — an OpenAI `{"type": "text"}`
    # must NOT be coerced (v1 defaults to text, so emit nothing for it).
    # Truthiness guard so an empty `response_format={}` (no `type`) emits nothing.
    if request.response_format:
        rf_type = request.response_format.get("type")
        if rf_type in ("json_object", "json_schema"):
            cohere_rf: Dict[str, Any] = {"type": "json_object"}
            schema = _extract_json_schema(request.response_format)
            if schema is not None:
                cohere_rf["schema"] = schema
            payload["response_format"] = cohere_rf

    # Extended sampling — Cohere v1 /chat DOCUMENTED names:
    #   seed               -> `seed`               (supported)
    #   frequency_penalty  -> `frequency_penalty`  (supported)
    #   presence_penalty   -> `presence_penalty`   (supported)
    #   top_k              -> `k`  (Cohere names top_k `k`, top_p `p`)
    if request.seed is not None:
        payload["seed"] = request.seed
    # frequency_penalty / presence_penalty: Cohere v1 accepts a 0.0-1.0 range vs
    # the OpenAI/Mistral -2.0..2.0 range. The adapter SHAPE-translates (field
    # name) but does NOT value-translate/clamp — consistent with every other
    # field (temperature ranges also differ across providers and are passed
    # through unclamped); silently rescaling a caller's value would be a
    # surprising per-field special case. An out-of-range value is the caller's
    # to reconcile, not the wire adapter's to mutate.
    if request.frequency_penalty is not None:
        payload["frequency_penalty"] = request.frequency_penalty
    if request.presence_penalty is not None:
        payload["presence_penalty"] = request.presence_penalty
    if request.top_k is not None:
        payload["k"] = request.top_k
    # UNSUPPORTED by Cohere v1 /chat — deliberately NOT emitted (no fake feature):
    #   n          — v1 /chat has no multi-generation `n`/`num_generations` param.
    #   logit_bias — v1 /chat exposes no token-bias control.
    # (the shared CompletionRequest carries them for OpenAI-family wires only.)

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

    # #1720 Wave-1b: normalize Cohere v1 tool calls. The v1 /chat response
    # carries `tool_calls` as `[{"name", "parameters": {...}}]` with NO per-call
    # id — synthesize `call_{index}` (matching the google shard, which likewise
    # has no native id) and json.dumps the parameters dict into the canonical
    # `arguments` JSON STRING shared with openai/anthropic/google:
    #   {"id", "type": "function", "function": {"name", "arguments": <JSON str>}}
    tool_calls: List[Dict[str, Any]] = []
    raw_tool_calls = payload.get("tool_calls")
    if isinstance(raw_tool_calls, list):
        for index, tc in enumerate(raw_tool_calls):
            if not isinstance(tc, dict):
                continue
            tool_calls.append(
                {
                    "id": f"call_{index}",
                    "type": "function",
                    "function": {
                        "name": tc.get("name"),
                        "arguments": json.dumps(tc.get("parameters", {})),
                    },
                }
            )

    result: Dict[str, Any] = {
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
    # Only surface tool_calls when ≥1 was present, so a plain text response
    # stays byte-identical to the pre-Wave-1b parsed shape.
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

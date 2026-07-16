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

import json
import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import _content_parts

logger = logging.getLogger(__name__)


def _extract_json_schema(response_format: Dict[str, Any]) -> Dict[str, Any] | None:
    """Pull a JSON schema out of an OpenAI-shaped ``response_format``.

    OpenAI carries a schema under ``{"type": "json_schema", "json_schema":
    {"schema": {...}}}``; a bare ``{"type": "json_object"}`` has none. Returns
    the schema dict (Ollama accepts it directly as the ``format`` value) or
    ``None`` when absent.
    """
    json_schema = response_format.get("json_schema")
    if isinstance(json_schema, dict):
        schema = json_schema.get("schema")
        if isinstance(schema, dict):
            return schema
    return None


def _translate_message_to_ollama(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Translate one OpenAI-shaped message into Ollama-native's shape.

    Ollama's ``/api/chat`` message is ``{role, content: <str>, images:
    [<base64>, ...]}`` — image parts live in a SEPARATE per-message field
    as bare base64 strings, NOT inline in ``content`` (#1720 Wave-1b).

    A message with NO ``image_url`` part in its content — a bare string,
    OR a content-part list containing only text/other blocks — passes
    through UNCHANGED (same object) so a text-only request stays
    byte-identical to the pre-Wave-1b output. A message WITH >=1
    ``image_url`` part has its text blocks joined into a single
    ``content`` string and its data-URI image parts moved to the
    ``images`` field.

    A remote (non-data-URI) ``image_url`` cannot be translated without a
    network fetch, which is out of scope for this pure wire shaper (see
    ``_content_parts.to_ollama_images``); it is dropped from the request
    with a WARNING log — never silently — per
    ``rules/observability.md`` Rule 7 / zero-tolerance Rule 3.
    """
    content = msg.get("content")
    if not isinstance(content, list):
        return msg
    has_image_url = any(
        isinstance(block, dict) and block.get("type") == "image_url"
        for block in content
    )
    if not has_image_url:
        return msg

    text_parts: List[str] = []
    image_parts: List[_content_parts.ImagePart] = []
    remote_url_count = 0
    dropped_block_count = 0
    for block in content:
        part = _content_parts.parse_content_part(block)
        if isinstance(part, _content_parts.TextPart):
            text_parts.append(part.text)
        elif isinstance(part, _content_parts.ImagePart):
            if part.is_data_uri:
                image_parts.append(part)
            else:
                remote_url_count += 1
        elif isinstance(block, str):
            text_parts.append(block)
        else:
            # An unrecognized/malformed block (parse_content_part returned
            # None and the block is not a bare str -- e.g. an unknown
            # `type`, or a malformed `image_url` sub-dict missing `url`) has
            # no Ollama-native slot and is dropped from `content` -- only
            # text + image blocks are representable in Ollama's message
            # shape. /redteam Round-1 (#1720 Wave-1b): this branch
            # previously fell through with NO log; counted + WARNed here,
            # never silent, per rules/observability.md Rule 7 /
            # zero-tolerance Rule 3.
            dropped_block_count += 1

    if remote_url_count:
        logger.warning(
            "ollama_native.remote_image_url_not_translated",
            extra={"count": remote_url_count},
        )
    if dropped_block_count:
        logger.warning(
            "ollama_native.content_block_dropped",
            extra={"count": dropped_block_count},
        )

    new_msg = dict(msg)
    new_msg["content"] = "".join(text_parts)
    images = _content_parts.to_ollama_images(image_parts)
    if images:
        new_msg["images"] = images
    return new_msg


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/api/chat`` request body for Ollama.

    Maps OpenAI-style fields into Ollama's ``options`` dict where the
    server expects them (``num_predict``, ``stop``, ``temperature``,
    ``top_p``). Fields the caller left unset are omitted so the Ollama
    server uses its own defaults.

    #1720 Wave-1b completion-shaping emission. Ollama's ``/api/chat`` schema
    diverges from OpenAI's, so this shaper translates each field to Ollama's
    native shape (verified against Ollama's API docs — the ``/api/chat``
    endpoint):

    * ``tools`` — Ollama accepts the SAME OpenAI function-schema list
      (``[{"type":"function","function":{...}}]``), so tools pass through
      verbatim. Guarded on truthiness (an explicit ``tools=[]`` emits nothing).
    * ``tool_choice`` — Ollama's ``/api/chat`` has NO tool_choice parameter; it
      is OMITTED (never invented — the "omit unsupported, never fake" rule).
    * ``response_format`` — Ollama uses a top-level ``format`` key, NOT
      ``response_format``. ``{"type":"json_object"}`` -> ``format:"json"``; a
      ``json_schema`` -> ``format:<schema object>`` (newer Ollama accepts a JSON
      schema directly). A ``{"type":"text"}`` (or any other type) emits nothing
      (Ollama defaults to free text).
    * Extended sampling (``seed``/``top_k``/``frequency_penalty``/
      ``presence_penalty``) lives UNDER the ``options`` object using Ollama's own
      option names, MERGED into the existing options dict (never clobbering
      temperature/top_p/num_predict/stop). ``n`` (multiple completions) and
      ``logit_bias`` have no Ollama equivalent and are OMITTED.
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

    # Wave-1b extended sampling: MERGE into the existing options dict under
    # Ollama's native option names — never clobber temperature/top_p/etc.
    if request.seed is not None:
        options["seed"] = request.seed
    if request.top_k is not None:
        options["top_k"] = request.top_k
    if request.frequency_penalty is not None:
        options["frequency_penalty"] = request.frequency_penalty
    if request.presence_penalty is not None:
        options["presence_penalty"] = request.presence_penalty
    # n: Ollama /api/chat returns a single message — no multi-completion knob.
    #    OMITTED (do NOT fabricate a request-level completion count).
    # logit_bias: Ollama has no per-token bias parameter. OMITTED.

    payload: Dict[str, Any] = {
        "model": request.model,
        # Wave-1b multimodal translation: move image_url parts OUT of
        # `content` into the per-message `images` field Ollama expects.
        "messages": [_translate_message_to_ollama(msg) for msg in request.messages],
        # Ollama defaults `stream=True` server-side; we always pass the
        # caller's explicit choice so the HTTP client can pick the correct
        # reader (streaming JSONL vs single-JSON response).
        "stream": bool(request.stream),
    }
    if options:
        payload["options"] = options

    # tools -> Ollama accepts the OpenAI function-schema list verbatim. Guard on
    # truthiness so an explicitly-set EMPTY list (`tools=[]`) emits nothing.
    if request.tools:
        payload["tools"] = list(request.tools)
    # tool_choice: Ollama's /api/chat has NO tool_choice parameter. OMITTED —
    # do NOT invent one (the four-axis "omit unsupported, never fake" rule).

    # response_format -> Ollama's top-level `format` key. json_object -> "json";
    # json_schema -> the schema object directly. Truthiness guard so an empty
    # `response_format={}` (set but degenerate — no `type`) emits nothing.
    if request.response_format:
        rf_type = request.response_format.get("type")
        if rf_type == "json_object":
            payload["format"] = "json"
        elif rf_type == "json_schema":
            schema = _extract_json_schema(request.response_format)
            payload["format"] = schema if schema is not None else "json"
        # any other type (e.g. "text") -> emit nothing; Ollama defaults to text.

    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalized view from an Ollama ``/api/chat`` response.

    Non-streaming responses carry ``{"message": {"role", "content"},
    "done", "eval_count", "prompt_eval_count", ...}``. Streaming responses
    are JSONL lines of the same shape with ``done: false`` until the last
    chunk — this shaper handles one object at a time so the caller can
    accumulate across a stream.

    #1720 Wave-1b: surface tool calls. Ollama emits ``message.tool_calls`` as
    ``[{"function": {"name": <str>, "arguments": <dict>}}]`` — with NO call id
    and ``arguments`` a DICT (unlike OpenAI's JSON-encoded string). This shaper
    normalizes to the canonical shape shared with the openai/anthropic/google
    shards (``arguments`` a JSON-encoded string, a synthesized ``call_{i}`` id),
    only when ≥1 tool call is present.
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    message = payload.get("message", {}) or {}
    text = ""
    tool_calls: list[Dict[str, Any]] = []
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            text = content
        raw_tool_calls = message.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            for index, tc in enumerate(raw_tool_calls):
                if not isinstance(tc, dict):
                    continue
                function = tc.get("function")
                function = function if isinstance(function, dict) else {}
                arguments = function.get("arguments")
                # Ollama gives arguments as a DICT; json.dumps to the canonical
                # JSON-string form. A provider that already sent a string is
                # passed through unchanged.
                if isinstance(arguments, (dict, list)):
                    arguments = json.dumps(arguments)
                # Ollama supplies no call id — carry it if a variant sent one,
                # else synthesize `call_{index}` (matches the google shard).
                call_id = tc.get("id")
                if call_id is None:
                    call_id = f"call_{index}"
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": function.get("name"),
                            "arguments": arguments,
                        },
                    }
                )
    result: Dict[str, Any] = {
        "text": text,
        "usage": {
            "input_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
        },
        "stop_reason": payload.get("done_reason"),
        "model": payload.get("model"),
        "done": payload.get("done", False),
    }
    # Only surface tool_calls when ≥1 is present; a tool-less response keeps the
    # pre-#1720 parsed keys unchanged.
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

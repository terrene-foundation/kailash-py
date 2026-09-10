# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Google Gemini GenerateContent wire protocol shaper.

Gemini's ``/v1beta/models/{model}:generateContent`` schema uses:

* ``contents`` (list of ``{role, parts: [...]}``) — not ``messages``. A part is
  ``{text}``, ``{inlineData}``/``{fileData}`` (multimodal), ``{functionCall}``
  (an assistant tool-call turn) or ``{functionResponse}`` (a tool result); a
  ``functionCall`` part may carry a sibling ``thoughtSignature`` (#2120/#2121).
* Role names: ``user`` and ``model`` (no ``assistant`` or ``system``).
* ``systemInstruction`` is a top-level field with a ``parts`` list.
* ``generationConfig`` holds temperature / max_output_tokens / top_p.
* Response: ``candidates[0].content.parts[0].text``.

See https://ai.google.dev/api/generate-content for the canonical schema.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.thought_signature import (
    THOUGHT_SIGNATURE_KEY,
    encode_thought_signature,
    thought_signature_for_rest,
)
from kaizen.llm.wire_protocols import _content_parts

logger = logging.getLogger(__name__)

# OpenAI tool_choice string mode -> Gemini function_calling_config mode.
_TOOL_CHOICE_MODE = {"auto": "AUTO", "required": "ANY", "none": "NONE"}


def _map_finish_reason(raw: Any) -> Any:
    """Value-map a Gemini ``finishReason`` onto the legacy lowercase form.

    #1720 Wave-B1a — behavior-neutral migration of the FULL legacy value-map
    from ``kaizen.providers.llm.google.GoogleGeminiProvider`` (which lowercases
    the raw Gemini reason and buckets it): ``tool``/``function`` -> ``"tool_calls"``,
    ``max``/``length`` -> ``"length"``, ``safety`` -> ``"content_filter"``, and
    every other recognised reason (``STOP`` etc.) -> ``"stop"``. Matching the
    legacy substring-on-lowercase logic exactly means a consumer testing
    ``finish_reason == "stop"`` sees the SAME value on both the legacy and the
    four-axis path (the pre-cutover divergence was the raw ``"STOP"`` casing).

    A ``None`` finishReason (no candidate / field absent) maps to ``"stop"`` —
    legacy ``GoogleGeminiProvider`` initialises ``finish_reason = "stop"`` and
    never emits ``None`` (including on the streaming path), so ``"stop"`` is the
    faithful legacy floor for an absent reason (#1720 Wave-B1 redteam LOW —
    full finish_reason parity).
    """
    if raw is None:
        return "stop"
    fr = str(raw).lower()
    if "tool" in fr or "function" in fr:
        return "tool_calls"
    if "max" in fr or "length" in fr:
        return "length"
    if "safety" in fr:
        return "content_filter"
    return "stop"


def _role_from_openai(role: str) -> str:
    """Map OpenAI role names to Gemini role names.

    Gemini has only two non-system roles: ``user`` and ``model``. OpenAI's
    ``assistant`` maps to ``model``. Any other role (``tool``, ``function``)
    falls through to ``user`` — Gemini's own function-calling schema uses
    ``functionResponse`` parts inside a ``user``-role turn.
    """
    if role == "assistant":
        return "model"
    if role == "model":
        return "model"
    # Default: user. Covers "user", "tool", "function", "system" (system is
    # partitioned out before this function is called).
    return "user"


def _extract_text_parts(content: Any) -> List[Dict[str, Any]]:
    """Turn a message's ``content`` field into Gemini ``parts`` list.

    OpenAI messages carry either a string or a list of content blocks;
    Gemini expects a list of ``{text}`` / ``{inlineData}`` / ``{fileData}``
    / etc. parts. Text blocks pass through as ``{"text": ...}``. An
    ``image_url`` block (OpenAI's canonical multimodal shape — a base64
    data-URI or a remote http(s) url) is translated via ``_content_parts``
    into Gemini's native ``inlineData`` (data-URI) / ``fileData`` (remote
    url) part (#1720 Wave-1b). Any other block type is left unchanged
    (callers may inject an already-Gemini-shaped part directly).
    """
    if isinstance(content, str):
        return [{"text": content}]
    if isinstance(content, list):
        parts: List[Dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    parts.append({"text": block.get("text", "")})
                elif block_type == "image_url":
                    part = _content_parts.parse_content_part(block)
                    if isinstance(part, _content_parts.ImagePart):
                        parts.append(_content_parts.to_gemini_part(part))
                    else:
                        parts.append(block)
                else:
                    parts.append(block)
            elif isinstance(block, str):
                parts.append({"text": block})
        return parts
    # Fallback: coerce to string for safety.
    return [{"text": str(content)}]


def _function_call_part(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Turn ONE OpenAI-shaped ``tool_calls`` entry into a Gemini part.

    Emits ``{"functionCall": {"name", "args"}}``, plus a PART-LEVEL SIBLING
    ``thoughtSignature`` when the parse stashed one (#2120/#2121) — in Gemini's
    schema the signature lives on the Part, not inside the FunctionCall.

    OpenAI carries call arguments as a JSON **string**; Gemini wants a real
    object, so the string is parsed. A malformed arguments string raises
    ``ValueError`` naming the offending tool rather than being swallowed into
    an empty ``{}`` — silently calling a function with no arguments is the
    ``zero-tolerance`` Rule 3 failure mode (the model asked for a specific
    call; dropping its arguments produces a wrong answer, not an error).
    """
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError(
            "google_generate_content: assistant tool_calls entry has no "
            f"'function' object; got {tool_call!r}"
        )
    name = function.get("name")
    if not name:
        raise ValueError(
            "google_generate_content: assistant tool_calls entry has no "
            "function name; Gemini requires a name on every functionCall part"
        )
    raw_args = function.get("arguments", "{}")
    if isinstance(raw_args, dict):
        args: Dict[str, Any] = raw_args
    elif isinstance(raw_args, str):
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(
                "google_generate_content: tool call "
                f"{name!r} has malformed JSON arguments: {exc}"
            ) from exc
        if not isinstance(args, dict):
            raise ValueError(
                f"google_generate_content: tool call {name!r} arguments must "
                f"decode to an object; got {type(args).__name__}"
            )
    else:
        raise ValueError(
            f"google_generate_content: tool call {name!r} arguments must be a "
            f"JSON string or dict; got {type(raw_args).__name__}"
        )

    part: Dict[str, Any] = {"functionCall": {"name": name, "args": args}}
    stashed = tool_call.get(THOUGHT_SIGNATURE_KEY)
    if stashed is not None:
        part["thoughtSignature"] = thought_signature_for_rest(stashed)
    return part


def _function_response_part(
    msg: Dict[str, Any], call_id_to_name: Dict[str, str]
) -> Dict[str, Any]:
    """Turn ONE OpenAI ``role="tool"`` message into a Gemini part.

    Gemini keys a ``functionResponse`` by the function NAME, but an OpenAI tool
    result carries only ``tool_call_id`` (``LLMAgentNode``'s own loop emits
    ``{"role": "tool", "tool_call_id": ..., "content": ...}`` with NO ``name``),
    so the name is resolved from the preceding assistant turn's ``tool_calls``
    via ``call_id_to_name``, falling back to an explicit ``name`` when the
    caller supplied one.

    An unresolvable name raises ``ValueError``: there is no correct Gemini
    representation for a nameless tool result, and the pre-#2121 behaviour —
    flattening it to anonymous user text — is exactly the silent failure this
    fix removes (``zero-tolerance`` Rule 3).
    """
    call_id = msg.get("tool_call_id")
    name = msg.get("name") or (call_id_to_name.get(call_id) if call_id else None)
    if not name:
        raise ValueError(
            "google_generate_content: tool result message cannot be mapped to a "
            f"Gemini functionResponse — tool_call_id={call_id!r} matches no "
            "preceding assistant tool_calls entry and the message carries no "
            "'name'. Include the assistant tool-call turn in the message "
            "history, or set 'name' on the tool result."
        )
    content = msg.get("content", "")
    # Gemini's functionResponse.response is an OBJECT. A dict result passes
    # through as-is; anything else is wrapped under "result" (the shape the
    # sibling Delegate google adapter already uses).
    response = content if isinstance(content, dict) else {"result": content}
    return {"functionResponse": {"name": name, "response": response}}


def _contents_from_messages(rest: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build Gemini ``contents`` from the non-system OpenAI messages.

    #2121: before this, EVERY non-system message became text parts only::

        contents = [{"role": ..., "parts": _extract_text_parts(msg["content"])}
                    for msg in rest]

    so an assistant turn carrying ``tool_calls`` serialised to
    ``{"role": "model", "parts": [{"text": ""}]}`` — the function call was
    DROPPED — and a tool result became plain user text rather than a
    ``functionResponse`` part. There was no error; the model simply never saw
    that a tool had been called or what it returned, which made a multi-turn
    tool loop impossible on this wire and failed SILENTLY.

    Now an assistant turn emits its text part (when non-empty) followed by one
    ``functionCall`` part per tool call, and a ``role="tool"`` message emits a
    ``functionResponse`` part inside a ``user``-role turn (Gemini's own
    function-calling schema). A message with neither tool calls nor tool role
    is shaped exactly as before — byte-identical for every tool-less request.
    """
    contents: List[Dict[str, Any]] = []
    # Resolves a tool result's function name from the assistant turn that
    # requested it; Gemini keys functionResponse by name, OpenAI by call id.
    call_id_to_name: Dict[str, str] = {}

    for msg in rest:
        role = msg.get("role", "user")
        gemini_role = _role_from_openai(role)

        if role == "tool":
            contents.append(
                {
                    "role": gemini_role,
                    "parts": [_function_response_part(msg, call_id_to_name)],
                }
            )
            continue

        tool_calls = msg.get("tool_calls")
        if role == "assistant" and tool_calls:
            parts: List[Dict[str, Any]] = []
            content = msg.get("content", "")
            # Gemini rejects an empty text part; a tool-call turn commonly has
            # content=None/"" (the model emitted only the call).
            if content:
                parts.extend(_extract_text_parts(content))
            for tool_call in tool_calls:
                parts.append(_function_call_part(tool_call))
                call_id = tool_call.get("id")
                function = tool_call.get("function")
                if call_id and isinstance(function, dict) and function.get("name"):
                    call_id_to_name[call_id] = function["name"]
            contents.append({"role": gemini_role, "parts": parts})
            continue

        contents.append(
            {
                "role": gemini_role,
                "parts": _extract_text_parts(msg.get("content", "")),
            }
        )

    return contents


def _partition_system(
    messages: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]] | None, List[Dict[str, Any]]]:
    """Split messages into (system_parts, non_system_messages)."""
    system_parts: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            system_parts.extend(_extract_text_parts(msg.get("content", "")))
        else:
            rest.append(msg)
    return (system_parts if system_parts else None), rest


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the GenerateContent request body for Gemini.

    Note: the model name is carried in the URL path (``:generateContent``
    is appended to ``/models/{model}``), not in the body. The HTTP sender
    in Session 3+ consults ``request.model`` when building the URL; the
    payload here does NOT duplicate the field.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    system_parts, rest = _partition_system(request.messages)
    # #2121: assistant tool-call turns and tool results round-trip as
    # functionCall / functionResponse parts instead of being silently flattened
    # to text. See _contents_from_messages.
    contents: List[Dict[str, Any]] = _contents_from_messages(rest)

    generation_config: Dict[str, Any] = {}
    if request.temperature is not None:
        generation_config["temperature"] = request.temperature
    if request.top_p is not None:
        generation_config["topP"] = request.top_p
    if request.max_tokens is not None:
        generation_config["maxOutputTokens"] = request.max_tokens
    if request.stop:
        generation_config["stopSequences"] = list(request.stop)

    # Wave-1b completion-shaping fields (all Optional, byte-neutral when unset).
    # top_k / seed / n / frequency_penalty / presence_penalty MERGE into the
    # existing generationConfig above — never clobber temperature/top_p/max.
    if request.top_k is not None:
        generation_config["topK"] = request.top_k
    if request.seed is not None:
        generation_config["seed"] = request.seed
    if request.n is not None:
        # Gemini names OpenAI's `n` (candidate count) `candidateCount`.
        generation_config["candidateCount"] = request.n
    if request.frequency_penalty is not None:
        generation_config["frequencyPenalty"] = request.frequency_penalty
    if request.presence_penalty is not None:
        generation_config["presencePenalty"] = request.presence_penalty
    # logit_bias: Gemini's generateContent has no equivalent — DO NOT emit it.

    # response_format -> Gemini structured-output on generationConfig. Gemini
    # supports JSON mode via responseMimeType, plus an optional responseSchema.
    # ONLY force JSON mode for the JSON response types — an OpenAI
    # ``{"type": "text"}`` must NOT be coerced into JSON (Gemini defaults to
    # text, so emit nothing for it). /redteam Round-1 (#1720 Wave-1b):
    # truthiness guard (not `is not None`) matches every sibling wire
    # (openai_chat / anthropic_messages / ollama_native / etc.) — an
    # explicitly-set EMPTY `response_format={}` emits nothing, same as an
    # unset one.
    #
    # #1819 (gh#357 legacy guard, ported to the four-axis wire): Gemini rejects
    # a request that carries BOTH responseMimeType/responseSchema AND tools
    # (functionDeclarations) with a 400. The legacy paths dropped structured
    # output when tools were present on Gemini (base_agent.py:126-134,
    # workflow_generator.py:376-380); mirror that here — suppress the
    # response_format block when tools are set, WARNing so the drop is not
    # silent (zero-tolerance Rule 3). Function-calling is used alone; the tools
    # block below still emits.
    if request.response_format and not request.tools:
        rf_type = request.response_format.get("type")
        if rf_type in ("json_object", "json_schema"):
            generation_config["responseMimeType"] = "application/json"
            schema = _extract_json_schema(request.response_format)
            if schema is not None:
                generation_config["responseSchema"] = schema
    elif (
        request.response_format
        and request.tools
        and request.response_format.get("type") in ("json_object", "json_schema")
    ):
        # Only WARN when a JSON structured-output mode was genuinely dropped;
        # response_format={"type":"text"} emits nothing structured regardless of
        # tools, so warning there would misleadingly claim a suppression.
        logger.warning(
            "google_generate_content: response_format suppressed — Gemini rejects "
            "responseMimeType/responseSchema combined with tools (gh#357/#1819); "
            "using function-calling only."
        )

    payload: Dict[str, Any] = {"contents": contents}
    if generation_config:
        payload["generationConfig"] = generation_config
    if system_parts is not None:
        payload["systemInstruction"] = {"parts": system_parts}

    # tools -> Gemini top-level `tools` with functionDeclarations, translating
    # the OpenAI function-schema form to Gemini's shape. Guard on truthiness so
    # an explicitly-set EMPTY list (`tools=[]`) emits nothing — emitting
    # `tools:[{functionDeclarations:[]}]` + a forced `toolConfig` mode:ANY would
    # be a degenerate forced-call-with-no-functions request (matches the
    # openai/anthropic empty-tools guard).
    if request.tools:
        payload["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": fn["function"]["name"],
                        "description": fn["function"].get("description", ""),
                        "parameters": fn["function"].get("parameters", {}),
                    }
                    for fn in request.tools
                ]
            }
        ]
        # tool_choice -> Gemini toolConfig.functionCallingConfig.mode. Only
        # emitted when tools are set (a mode with no tools is meaningless).
        tool_config = _tool_config_from_choice(request.tool_choice)
        if tool_config is not None:
            payload["toolConfig"] = tool_config

    return payload


def _extract_json_schema(response_format: Dict[str, Any]) -> Dict[str, Any] | None:
    """Pull a JSON schema out of an OpenAI-shaped ``response_format``.

    OpenAI carries a schema under ``{"type": "json_schema", "json_schema":
    {"schema": {...}}}``; a bare ``{"type": "json_object"}`` has none. Returns
    the schema dict (Gemini ``responseSchema``) or ``None`` when absent.
    """
    json_schema = response_format.get("json_schema")
    if isinstance(json_schema, dict):
        schema = json_schema.get("schema")
        if isinstance(schema, dict):
            return schema
    return None


def _tool_config_from_choice(tool_choice: Any) -> Dict[str, Any] | None:
    """Translate an OpenAI ``tool_choice`` to a Gemini ``tool_config``.

    OpenAI ``"auto"``/``"required"``/``"none"`` map to Gemini modes
    ``AUTO``/``ANY``/``NONE``. A forced-tool dict
    (``{"type": "function", "function": {"name": ...}}``) maps to ``ANY`` plus
    ``allowedFunctionNames``.

    #2121 — when tools are set but ``tool_choice`` is unset, the default is
    ``AUTO``, NOT ``ANY``. ``ANY`` forces a function call on EVERY turn, so the
    model can never emit the final text answer that ends an agent loop: the
    loop runs to ``max_rounds`` and returns no answer. The previous ``ANY``
    default was commented as "legacy ``required`` semantics", but that
    rationale does not hold for THIS provider — ``legacy_tool_choice_default``
    (``kaizen/llm/deployment_resolver.py``) injects a default for openai
    (``"required"``) and azure/docker (``"auto"``) ONLY; **every other legacy
    provider, google included, sent no ``tool_choice`` at all**, leaving
    Gemini's own server-side default, which is ``AUTO``. So ``ANY`` was a
    behavioural REGRESSION introduced by this wire, not inherited legacy.
    ``AUTO`` is emitted explicitly (rather than omitting ``toolConfig``) so the
    wire states its intent instead of relying on an unstated server default.
    A caller wanting forced calling passes ``tool_choice="required"``.
    """
    if isinstance(tool_choice, dict):
        fn = tool_choice.get("function", {})
        name = fn.get("name") if isinstance(fn, dict) else None
        config: Dict[str, Any] = {"mode": "ANY"}
        if name is not None:
            config["allowedFunctionNames"] = [name]
        return {"functionCallingConfig": config}
    if isinstance(tool_choice, str):
        mode = _TOOL_CHOICE_MODE.get(tool_choice, "ANY")
        return {"functionCallingConfig": {"mode": mode}}
    # tool_choice is None but tools are set -> AUTO, so the loop can terminate.
    return {"functionCallingConfig": {"mode": "AUTO"}}


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalized view from a Gemini ``generateContent`` response.

    Response shape:

        {
          "candidates": [
            {"content": {"parts": [{"text": "..."}]}, "finishReason": "STOP"}
          ],
          "usageMetadata": {"promptTokenCount": N, "candidatesTokenCount": M}
        }
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    candidates = payload.get("candidates", []) or []
    texts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    finish_reason: Any = None
    if candidates and isinstance(candidates[0], dict):
        first = candidates[0]
        finish_reason = first.get("finishReason")
        content = first.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if isinstance(parts, list):
            for index, part in enumerate(parts):
                if not isinstance(part, dict):
                    continue
                text_value = part.get("text")
                if isinstance(text_value, str):
                    texts.append(text_value)
                # Gemini emits tool invocations as ``functionCall`` parts with
                # no call id; synthesize ``call_{index}`` and JSON-encode args
                # into the canonical normalized shape shared with openai/anthropic.
                function_call = part.get("functionCall")
                if isinstance(function_call, dict):
                    entry: Dict[str, Any] = {
                        "id": f"call_{index}",
                        "type": "function",
                        "function": {
                            "name": function_call.get("name"),
                            "arguments": json.dumps(function_call.get("args", {})),
                        },
                    }
                    # #2120/#2121: stash the PART-level thoughtSignature so the
                    # replay in _function_call_part can send it back. Gemini 3.x
                    # 400s on a replayed functionCall that lacks it, which broke
                    # the second request of every tool loop. Gemini 2.5 emits
                    # none, leaving this entry byte-identical to before.
                    signature = encode_thought_signature(part.get("thoughtSignature"))
                    if signature is not None:
                        entry[THOUGHT_SIGNATURE_KEY] = signature
                    tool_calls.append(entry)

    usage = payload.get("usageMetadata", {}) or {}
    result: Dict[str, Any] = {
        "text": "".join(texts),
        "usage": {
            "input_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "total_tokens": usage.get("totalTokenCount"),
        },
        # #1720 Wave-B1a — value-map the raw Gemini finishReason onto the legacy
        # lowercase form ('STOP' -> 'stop', 'MAX_TOKENS' -> 'length', 'SAFETY' ->
        # 'content_filter', tool/function -> 'tool_calls'), behaviour-neutral with
        # kaizen.providers.llm.google. Previously emitted the raw provider value.
        "stop_reason": _map_finish_reason(finish_reason),
        "model": payload.get("modelVersion"),
    }
    # Only surface tool_calls when ≥1 functionCall part is present; a
    # tool-less response keeps the pre-#1720 parsed keys unchanged.
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

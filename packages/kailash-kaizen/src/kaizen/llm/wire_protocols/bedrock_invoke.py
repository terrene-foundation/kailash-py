# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AWS Bedrock ``InvokeModel`` wire protocol shaper (#1717).

Non-Anthropic Bedrock families (Meta Llama, Amazon Titan, Mistral, Cohere)
speak the native Bedrock ``invoke-model`` body schema rather than the
Anthropic Messages schema. Each family has a DIFFERENT native body shape, so
this shaper selects the body builder from the on-wire model-id prefix that
Bedrock's model catalogue guarantees:

* ``meta.*``   → Llama:  ``{"prompt", "max_gen_len", "temperature", "top_p"}``
* ``amazon.*`` → Titan:  ``{"inputText", "textGenerationConfig": {...}}``
* ``mistral.*``→ Mistral:``{"prompt", "max_tokens", "temperature", "top_p", "stop"}``
* ``cohere.*`` → Cohere: ``{"prompt", "max_tokens", "temperature", "p", "stop_sequences"}``

The model id is carried in the URL path (``/model/{modelId}/invoke``), NOT
the body — so ``build_request_payload`` reads ``request.model`` only to pick
the family body builder.

This is on-the-wire serialization (a dumb data endpoint), not agent
reasoning: the prefix dispatch routes on a provider-catalogue-defined model
id, exactly the structural dispatch ``rules/agent-reasoning.md`` permits.

See https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters.html.

#1720 Wave-1b tool/tool_choice emission + tool_call parsing is added
PER-FAMILY, conservatively (OMIT-DON'T-FAKE): only ``mistral.*`` has a
documented ``tools``/``tool_choice`` field on the native InvokeModel body;
``meta.*`` / ``amazon.*`` / ``cohere.*`` have none documented for the body
shapes this shaper builds, so tools are deliberately OMITTED for those
families (see the per-builder comments below for the family-specific
rationale) rather than emitting a fake/speculative key.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)

# Llama / Titan cap output at model-specific ceilings; 512 is a safe
# cross-family default when the caller did not set max_tokens.
_DEFAULT_MAX_TOKENS = 512


def _flatten_prompt(messages: List[Dict[str, Any]], family: str = "unknown") -> str:
    """Render OpenAI-style messages as a single prompt string.

    The native Bedrock (non-Anthropic) invoke schemas take a flat ``prompt``
    string, not a message array. Uses the widely-supported
    ``[ROLE] content`` convention and trails an ``[ASSISTANT]`` cue.

    ``family`` (the Bedrock family label — "meta"/"amazon"/"mistral"/"cohere")
    is used only to name the vision-unsupported family in the dropped-block
    WARN log below; it does not affect the rendered prompt.
    """
    parts: List[str] = []
    for msg in messages:
        role = str(msg.get("role", "user")).upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            text_blocks: List[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_blocks.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_blocks.append(block)
                else:
                    # #1720 Wave-1b: an image or other non-text content block
                    # cannot be represented in the flat `prompt` string these
                    # native (non-Anthropic) Bedrock families accept — none of
                    # meta./amazon./mistral./cohere. InvokeModel bodies this
                    # shaper builds support multi-modal content. Previously
                    # this was silently dropped; now it is a structured WARN
                    # (observability.md Rule 7 / zero-tolerance Rule 3 — no
                    # silent drops) naming the family as vision-unsupported.
                    dropped_type = (
                        block.get("type")
                        if isinstance(block, dict)
                        else type(block).__name__
                    )
                    logger.warning(
                        "bedrock_invoke.non_text_block_dropped",
                        extra={
                            "family": family,
                            "block_type": dropped_type,
                            "reason": "vision_unsupported",
                        },
                    )
            content = "".join(text_blocks)
        parts.append(f"[{role}] {content}")
    parts.append("[ASSISTANT] ")
    return "\n".join(parts)


def _build_llama(request: CompletionRequest, prompt: str) -> Dict[str, Any]:
    body: Dict[str, Any] = {"prompt": prompt}
    body["max_gen_len"] = (
        request.max_tokens if request.max_tokens is not None else _DEFAULT_MAX_TOKENS
    )
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.top_p is not None:
        body["top_p"] = request.top_p
    # --- #1720 Wave-1b: tools deliberately OMITTED ---
    # Bedrock's native Llama InvokeModel body has NO documented `tools` field
    # (https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-meta.html)
    # — the body is just {"prompt", "max_gen_len", "temperature", "top_p"}.
    # Llama tool-use on Bedrock is prompt-level (the caller embeds tool
    # definitions and instructions directly into the flattened prompt text);
    # there is no structured wire field to populate. Emitting a fake `tools`
    # key here would advertise a capability the InvokeModel API does not have
    # (zero-tolerance Rule 2: no fake/speculative capability).
    return body


def _build_titan(request: CompletionRequest, prompt: str) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "maxTokenCount": (
            request.max_tokens
            if request.max_tokens is not None
            else _DEFAULT_MAX_TOKENS
        )
    }
    if request.temperature is not None:
        config["temperature"] = request.temperature
    if request.top_p is not None:
        config["topP"] = request.top_p
    if request.stop:
        config["stopSequences"] = list(request.stop)
    # --- #1720 Wave-1b: tools deliberately OMITTED ---
    # Bedrock's native Titan InvokeModel body
    # (https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-text.html)
    # has NO tools / function-calling field at all — Titan text models have no
    # documented tool-use capability on Bedrock. Emitting a `tools` key would
    # be a wholly fabricated feature the model/API does not support
    # (zero-tolerance Rule 2: no fake/speculative capability).
    return {"inputText": prompt, "textGenerationConfig": config}


def _build_mistral(request: CompletionRequest, prompt: str) -> Dict[str, Any]:
    body: Dict[str, Any] = {"prompt": prompt}
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.top_p is not None:
        body["top_p"] = request.top_p
    if request.stop:
        body["stop"] = list(request.stop)

    # --- #1720 Wave-1b tool emission (Bedrock Mistral InvokeModel) ---
    # Unlike Llama/Titan/Cohere above/below, Bedrock's native InvokeModel body
    # for Mistral models (Mistral Large et al.) DOES accept the OpenAI-shaped
    # `tools` list + a `tool_choice` string/object verbatim in the request
    # body — this is the one native family with a documented structured
    # tools field. Guard on truthiness so an explicitly-set EMPTY list
    # (`tools=[]`) emits nothing (matches the sibling wire adapters).
    if request.tools:
        body["tools"] = list(request.tools)
        tool_choice = request.tool_choice
        # Mistral's Bedrock tool_choice vocabulary matches the direct Mistral
        # API (mistral_chat.py): force-a-tool is "any" (NOT OpenAI's
        # "required"). Map "required"->"any"; "auto"/"none"/"any" pass
        # through; an unknown string falls back to the safe forced default
        # "any". A dict is a named-tool forced selection and passes through
        # verbatim (Mistral accepts the OpenAI-shaped object form). When
        # tools are present but tool_choice is unset, default to "any" — the
        # pinned Wave-1a legacy "force a tool"-when-tools default, expressed
        # in Mistral's vocabulary (mirrors mistral_chat.py exactly).
        if tool_choice is None:
            body["tool_choice"] = "any"
        elif isinstance(tool_choice, str):
            if tool_choice == "required":
                body["tool_choice"] = "any"
            elif tool_choice in ("auto", "none", "any"):
                body["tool_choice"] = tool_choice
            else:
                body["tool_choice"] = "any"
        else:
            body["tool_choice"] = tool_choice
    return body


def _build_cohere(request: CompletionRequest, prompt: str) -> Dict[str, Any]:
    body: Dict[str, Any] = {"prompt": prompt}
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.top_p is not None:
        body["p"] = request.top_p
    if request.stop:
        body["stop_sequences"] = list(request.stop)
    # --- #1720 Wave-1b: tools deliberately OMITTED ---
    # This builder targets Bedrock's classic Cohere Command InvokeModel body
    # (prompt/max_tokens/temperature/p/stop_sequences — see the module
    # docstring), which has no documented `tools` field
    # (https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-cohere-command.html).
    # Cohere tool-use on Bedrock exists only for Command R / Command R+
    # models via an entirely different chat-shaped InvokeModel body
    # (`message` + `chat_history` + `tools` + `tool_results`, NOT `prompt`)
    # that this conservative, prompt-based shard does not build. Emitting a
    # `tools` key onto this prompt-based body would be silently ignored on
    # a real classic-Command model and a malformed/rejected request on a
    # Command R model — either way a fake/speculative capability, so it is
    # deliberately omitted rather than guessed (zero-tolerance Rule 2).
    return body


# Prefix → family body builder. Ordered longest-prefix-first is unnecessary
# because Bedrock prefixes are disjoint namespaces.
_FAMILY_BUILDERS: Dict[str, Callable[[CompletionRequest, str], Dict[str, Any]]] = {
    "meta.": _build_llama,
    "amazon.": _build_titan,
    "mistral.": _build_mistral,
    "cohere.": _build_cohere,
}

# Prefix → short family label, used only for the vision-unsupported log
# context in _flatten_prompt (#1720 Wave-1b) — not part of the wire payload.
_FAMILY_LABELS: Dict[str, str] = {
    "meta.": "meta",
    "amazon.": "amazon",
    "mistral.": "mistral",
    "cohere.": "cohere",
}


def _select_builder(
    model: str,
) -> tuple[str, Callable[[CompletionRequest, str], Dict[str, Any]]]:
    """Pick the family label + body builder from the on-wire model-id prefix.

    Bedrock inference-profile ids may carry a region prefix
    (``us.meta.llama3-...``); strip a leading ``<region>.`` segment before
    matching so both native ids and inference-profile ids resolve.
    """
    candidate = model
    for family_prefix, builder in _FAMILY_BUILDERS.items():
        if (
            candidate.startswith(family_prefix)
            or f".{family_prefix}" in f".{candidate}"
        ):
            return _FAMILY_LABELS[family_prefix], builder
    # Strip a single leading dotted segment (region for inference profiles)
    # and retry once.
    if "." in candidate:
        stripped = candidate.split(".", 1)[1]
        for family_prefix, builder in _FAMILY_BUILDERS.items():
            if stripped.startswith(family_prefix):
                return _FAMILY_LABELS[family_prefix], builder
    raise ValueError(
        "bedrock_invoke.build_request_payload: could not map model id to a "
        "Bedrock family (expected a meta./amazon./mistral./cohere. prefix)"
    )


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the native Bedrock ``invoke-model`` body for the model's family.

    The model id (carried in the URL, not the body) selects the family body
    builder. Raises ``ValueError`` when the id does not map to a known
    family so a misconfigured deployment fails at the shaper boundary rather
    than with an opaque Bedrock 400.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")
    family, builder = _select_builder(request.model)
    prompt = _flatten_prompt(request.messages, family=family)
    return builder(request, prompt)


def _normalize_mistral_tool_call(tc: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Coerce one Bedrock-Mistral ``outputs[0].tool_calls`` entry into the
    canonical normalized shape (shared with the openai/anthropic/google/
    mistral_chat shards)::

        {"id": <str>, "type": "function",
         "function": {"name": <str>, "arguments": <str: JSON-encoded>}}

    Bedrock's Mistral tool-call entries mirror the direct Mistral API's
    OpenAI-shaped ``{"id", "function": {"name", "arguments"}}`` form, where
    ``arguments`` is already a JSON string (see mistral_chat.py's
    ``_normalize_tool_call``). Defensively coerce a dict/list ``arguments``
    via ``json.dumps`` so the canonical "arguments is a JSON string"
    invariant holds, and synthesize ``call_{index}`` when the provider omits
    an id. Rebuilds a plain JSON-serializable dict so no provider SDK object
    leaks into the parsed result.
    """
    function = tc.get("function")
    function = function if isinstance(function, dict) else {}
    arguments = function.get("arguments")
    if isinstance(arguments, (dict, list)):
        arguments = json.dumps(arguments)
    call_id = tc.get("id")
    if not isinstance(call_id, str) or not call_id:
        call_id = f"call_{index}"
    return {
        "id": call_id,
        "type": tc.get("type", "function"),
        "function": {
            "name": function.get("name"),
            "arguments": arguments,
        },
    }


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a native Bedrock invoke response across families.

    Family response shapes:

    * Llama:   ``{"generation": "...", "prompt_token_count", "generation_token_count", "stop_reason"}``
    * Titan:   ``{"results": [{"outputText": "...", "completionReason": "..."}], "inputTextTokenCount"}``
    * Mistral: ``{"outputs": [{"text": "...", "stop_reason": "...", "tool_calls": [...]}]}``
    * Cohere:  ``{"generations": [{"text": "...", "finish_reason": "..."}]}``

    #1720 Wave-1b: Mistral's ``outputs[0].tool_calls`` (present only for the
    one native family with documented Bedrock tool support — see
    ``_build_mistral``) is normalized into the canonical ``tool_calls`` shape
    and surfaced under the ``"tool_calls"`` key ONLY when present, so a
    plain-text response stays byte-identical to the pre-Wave-1b parsed shape.
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")

    text = ""
    stop_reason: Any = None
    input_tokens: Any = None
    output_tokens: Any = None
    tool_calls: Any = None

    if "generation" in payload:  # Llama
        gen = payload.get("generation")
        if isinstance(gen, str):
            text = gen
        stop_reason = payload.get("stop_reason")
        input_tokens = payload.get("prompt_token_count")
        output_tokens = payload.get("generation_token_count")
    elif "results" in payload:  # Titan
        results = payload.get("results", []) or []
        if results and isinstance(results[0], dict):
            first = results[0]
            out = first.get("outputText")
            if isinstance(out, str):
                text = out
            stop_reason = first.get("completionReason")
            output_tokens = first.get("tokenCount")
        input_tokens = payload.get("inputTextTokenCount")
    elif "outputs" in payload:  # Mistral
        outputs = payload.get("outputs", []) or []
        if outputs and isinstance(outputs[0], dict):
            first = outputs[0]
            out = first.get("text")
            if isinstance(out, str):
                text = out
            stop_reason = first.get("stop_reason")
            # #1720 Wave-1b: surface tool calls. Bedrock's Mistral InvokeModel
            # response carries tool calls as `outputs[0].tool_calls` (a sibling
            # key to `text`/`stop_reason`, the one native family with
            # documented Bedrock tool support — see _build_mistral).
            raw_tool_calls = first.get("tool_calls")
            if isinstance(raw_tool_calls, list) and raw_tool_calls:
                tool_calls = [
                    _normalize_mistral_tool_call(tc, i)
                    for i, tc in enumerate(raw_tool_calls)
                    if isinstance(tc, dict)
                ]
    elif "generations" in payload:  # Cohere
        generations = payload.get("generations", []) or []
        if generations and isinstance(generations[0], dict):
            first = generations[0]
            out = first.get("text")
            if isinstance(out, str):
                text = out
            stop_reason = first.get("finish_reason")

    result: Dict[str, Any] = {
        "text": text,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "stop_reason": stop_reason,
        "model": None,
    }
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

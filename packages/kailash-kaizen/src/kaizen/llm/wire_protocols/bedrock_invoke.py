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
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)

# Llama / Titan cap output at model-specific ceilings; 512 is a safe
# cross-family default when the caller did not set max_tokens.
_DEFAULT_MAX_TOKENS = 512


def _flatten_prompt(messages: List[Dict[str, Any]]) -> str:
    """Render OpenAI-style messages as a single prompt string.

    The native Bedrock (non-Anthropic) invoke schemas take a flat ``prompt``
    string, not a message array. Uses the widely-supported
    ``[ROLE] content`` convention and trails an ``[ASSISTANT]`` cue.
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
    return body


# Prefix → family body builder. Ordered longest-prefix-first is unnecessary
# because Bedrock prefixes are disjoint namespaces.
_FAMILY_BUILDERS: Dict[str, Callable[[CompletionRequest, str], Dict[str, Any]]] = {
    "meta.": _build_llama,
    "amazon.": _build_titan,
    "mistral.": _build_mistral,
    "cohere.": _build_cohere,
}


def _select_builder(
    model: str,
) -> Callable[[CompletionRequest, str], Dict[str, Any]]:
    """Pick the family body builder from the on-wire model-id prefix.

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
            return builder
    # Strip a single leading dotted segment (region for inference profiles)
    # and retry once.
    if "." in candidate:
        stripped = candidate.split(".", 1)[1]
        for family_prefix, builder in _FAMILY_BUILDERS.items():
            if stripped.startswith(family_prefix):
                return builder
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
    prompt = _flatten_prompt(request.messages)
    builder = _select_builder(request.model)
    return builder(request, prompt)


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a native Bedrock invoke response across families.

    Family response shapes:

    * Llama:   ``{"generation": "...", "prompt_token_count", "generation_token_count", "stop_reason"}``
    * Titan:   ``{"results": [{"outputText": "...", "completionReason": "..."}], "inputTextTokenCount"}``
    * Mistral: ``{"outputs": [{"text": "...", "stop_reason": "..."}]}``
    * Cohere:  ``{"generations": [{"text": "...", "finish_reason": "..."}]}``
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")

    text = ""
    stop_reason: Any = None
    input_tokens: Any = None
    output_tokens: Any = None

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
    elif "generations" in payload:  # Cohere
        generations = payload.get("generations", []) or []
        if generations and isinstance(generations[0], dict):
            first = generations[0]
            out = first.get("text")
            if isinstance(out, str):
                text = out
            stop_reason = first.get("finish_reason")

    return {
        "text": text,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "stop_reason": stop_reason,
        "model": None,
    }


__all__ = ["build_request_payload", "parse_response"]

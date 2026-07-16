# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Anthropic Messages wire protocol shaper.

Anthropic's ``/v1/messages`` schema differs from OpenAI's in several ways:

* ``system`` is a top-level field, not a message with role="system".
* ``max_tokens`` is REQUIRED on every request (OpenAI treats it as optional).
* Response content is a list of ``{"type": "text", "text": "..."}`` blocks
  rather than a single string on ``choices[0].message.content``.
* ``stop_sequences`` replaces OpenAI's ``stop``.

See https://docs.anthropic.com/en/api/messages for the canonical schema.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from kaizen.llm.deployment import CompletionRequest

logger = logging.getLogger(__name__)

# Anthropic requires max_tokens; if the caller did not supply one we use
# this generous ceiling. 4096 matches the minimum across every current
# Anthropic model family (Claude Opus, Sonnet, Haiku) — chosen as the
# largest value that every model accepts without rejecting the request.
_DEFAULT_MAX_TOKENS = 4096


# Per-model temperature floors (NEW-A). Some Claude models reject
# `temperature: 0` with a hard 400 — `claude-opus-4-8` requires a minimum of
# 1.0. This is a DATA-DRIVEN table keyed on a model-id substring so the
# handling is model-aware without a magic branch: any resolved on-wire id
# containing a listed substring (direct `claude-opus-4-8`, Vertex
# `claude-opus-4-8@...`, a Bedrock inference-profile carrying the same alias)
# gets the same floor. When a request's temperature is below the floor the
# field is OMITTED (the model then applies its own default) rather than sent
# and 400'd. Extend this table as providers publish new per-model minimums.
_TEMPERATURE_MIN_BY_MODEL_SUBSTR: dict[str, float] = {
    "claude-opus-4-8": 1.0,
}


def _temperature_floor_for(model: str) -> float | None:
    """Return the temperature floor for ``model``, or ``None`` if unconstrained."""
    if not isinstance(model, str):
        return None
    for substr, floor in _TEMPERATURE_MIN_BY_MODEL_SUBSTR.items():
        if substr in model:
            return floor
    return None


def _resolve_temperature(model: str, temperature: float | None) -> float | None:
    """Apply the per-model temperature floor.

    Returns the temperature to send, or ``None`` to OMIT the field. A value
    at/above the floor passes through unchanged; a value below the floor is
    dropped so the model uses its own default instead of hard-400'ing on an
    out-of-range temperature.

    Caller note: for a floor-constrained model (e.g. ``claude-opus-4-8``) an
    explicit ``temperature=0`` is OMITTED — the request is NOT deterministic;
    the model applies its own default sampling. A hard-400 is the only
    alternative, so determinism is not achievable on these models via this arg.
    """
    if temperature is None:
        return None
    floor = _temperature_floor_for(model)
    if floor is not None and temperature < floor:
        logger.debug(
            "anthropic_messages.temperature_omitted_below_floor",
            extra={"floor": floor},
        )
        return None
    return temperature


def _partition_messages(
    messages: List[Dict[str, Any]],
) -> tuple[str | None, List[Dict[str, Any]]]:
    """Split OpenAI-style messages into (system_prompt, non_system_messages).

    Anthropic carries the system prompt as a top-level field, not in the
    message array. A request that bundles multiple system messages gets them
    joined with newlines — matching the Rust SDK's behaviour.
    """
    system_parts: List[str] = []
    rest: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content")
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_parts.append(block.get("text", ""))
        else:
            rest.append(msg)
    system = "\n".join(system_parts) if system_parts else None
    return system, rest


def build_request_payload(request: CompletionRequest) -> Dict[str, Any]:
    """Build the ``/v1/messages`` request body for Anthropic.

    Maps the shared :class:`CompletionRequest` shape to Anthropic's schema.
    The ``max_tokens`` field is always populated (Anthropic requires it);
    if the caller omitted ``max_tokens`` we supply ``_DEFAULT_MAX_TOKENS``
    and emit a structured DEBUG log so operators can spot the fallback.
    """
    if not isinstance(request, CompletionRequest):
        raise TypeError("build_request_payload expects a CompletionRequest")

    system, rest = _partition_messages(request.messages)

    max_tokens = (
        request.max_tokens if request.max_tokens is not None else _DEFAULT_MAX_TOKENS
    )
    if request.max_tokens is None:
        logger.debug(
            "anthropic_messages.max_tokens_default_applied",
            extra={"default": _DEFAULT_MAX_TOKENS},
        )

    payload: Dict[str, Any] = {
        "model": request.model,
        "messages": rest,
        "max_tokens": max_tokens,
    }
    if system is not None:
        payload["system"] = system
    temperature = _resolve_temperature(request.model, request.temperature)
    if temperature is not None:
        payload["temperature"] = temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.stop:
        payload["stop_sequences"] = list(request.stop)
    if request.stream:
        payload["stream"] = True
    if request.user is not None:
        # Anthropic accepts `metadata.user_id` for per-tenant tracking.
        payload["metadata"] = {"user_id": request.user}

    # Wave 1b — completion-shaping field translation (OpenAI shape -> Anthropic).
    #
    # tools: the shared CompletionRequest carries the OpenAI function-schema form
    # ``[{"type": "function", "function": {"name", "description", "parameters"}}]``;
    # Anthropic's ``/v1/messages`` expects ``[{"name", "description",
    # "input_schema"}]``. Translate field-by-field only when tools is set.
    if request.tools is not None:
        payload["tools"] = [
            {
                "name": f["function"]["name"],
                "description": f["function"].get("description", ""),
                "input_schema": f["function"].get("parameters", {}),
            }
            for f in request.tools
        ]
        # tool_choice is only meaningful alongside tools. Map the OpenAI values to
        # Anthropic's ``{"type": ...}`` shape:
        #   "auto"     -> {"type": "auto"}
        #   "required" -> {"type": "any"}  (Anthropic's "must call some tool")
        #   "none"     -> omit tools entirely (drop the tools we just built)
        #   forced-tool dict {"type":"function","function":{"name":X}}
        #              -> {"type": "tool", "name": X}
        #   None       -> {"type": "any"}  (legacy "required"-when-tools default)
        tool_choice = request.tool_choice
        if tool_choice is None:
            payload["tool_choice"] = {"type": "any"}
        elif isinstance(tool_choice, str):
            if tool_choice == "auto":
                payload["tool_choice"] = {"type": "auto"}
            elif tool_choice == "required":
                payload["tool_choice"] = {"type": "any"}
            elif tool_choice == "none":
                # "none" means "do not call a tool" — Anthropic expresses this by
                # not offering tools at all. Drop the tools key we just set.
                payload.pop("tools", None)
            else:
                # Unknown string — default to the tools-set "any" semantics rather
                # than emitting a shape Anthropic would reject.
                payload["tool_choice"] = {"type": "any"}
        elif isinstance(tool_choice, dict):
            # Forced-tool: {"type":"function","function":{"name":X}} -> {"type":"tool","name":X}
            forced_name = tool_choice.get("function", {}).get("name")
            if forced_name is not None:
                payload["tool_choice"] = {"type": "tool", "name": forced_name}
            else:
                payload["tool_choice"] = {"type": "any"}

    # top_k: Anthropic SUPPORTS top_k natively.
    if request.top_k is not None:
        payload["top_k"] = request.top_k

    # response_format: Anthropic has NO native json_schema / response_format param.
    # Structured output on Anthropic is achieved by forcing a tool (input_schema =
    # the desired JSON schema) — OUT OF SCOPE for this shard (a future enhancement).
    # We deliberately emit NOTHING here: inventing a bogus key would ship a feature
    # Anthropic does not support (zero-tolerance: no fake feature).
    #
    # UNSUPPORTED by Anthropic /v1/messages — deliberately NOT emitted:
    #   seed, logit_bias, frequency_penalty, presence_penalty, n
    # (the shared CompletionRequest carries them for OpenAI-family wires only;
    # emitting them here would be rejected or silently ignored by Anthropic.)

    return payload


def parse_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a normalized ``{text, usage}`` view from an Anthropic response.

    Anthropic returns ``content`` as a list of typed blocks. We concatenate
    every ``text`` block; other block types (``tool_use``, ``image``) are
    passed through on the ``raw_blocks`` field so downstream code can
    inspect them without re-parsing.
    """
    if not isinstance(payload, dict):
        raise TypeError("parse_response expects a dict payload")
    content = payload.get("content", [])
    texts: List[str] = []
    raw_blocks: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                raw_blocks.append(block)
                block_type = block.get("type")
                if block_type == "text":
                    text_value = block.get("text", "")
                    if isinstance(text_value, str):
                        texts.append(text_value)
                elif block_type == "tool_use":
                    # Normalize the Anthropic tool_use block into the CANONICAL
                    # tool-call shape shared with the openai/google wire shards:
                    #   {"id", "type": "function",
                    #    "function": {"name", "arguments": <JSON string>}}
                    # ``arguments`` MUST be a json.dumps string of the input dict.
                    tool_calls.append(
                        {
                            "id": block.get("id"),
                            "type": "function",
                            "function": {
                                "name": block.get("name"),
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }
                    )
    usage = payload.get("usage", {}) or {}
    result: Dict[str, Any] = {
        "text": "".join(texts),
        "raw_blocks": raw_blocks,
        "usage": {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        },
        "stop_reason": payload.get("stop_reason"),
        "model": payload.get("model"),
    }
    # Only surface tool_calls when at least one tool_use block was present, so a
    # plain text response stays byte-identical to the pre-Wave-1b parsed shape.
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


__all__ = ["build_request_payload", "parse_response"]

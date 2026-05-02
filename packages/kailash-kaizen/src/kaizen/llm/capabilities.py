# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Per-preset capability negotiation matrix (#763).

Spec § 4.7 calls for ``LlmDeployment.supports() -> dict[str, bool]`` exposing
the five orthogonal capability axes a caller may need to reason about before
issuing a request:

- ``tools`` — function/tool calling (OpenAI tools, Anthropic tool_use,
  Google function declarations, Bedrock Converse tool config).
- ``vision`` — image inputs in the request payload (model-dependent at the
  provider level; the matrix reports the deployment surface, not per-model).
- ``batch`` — async batch-completion lifecycle (OpenAI Batch API, Anthropic
  Message Batches, Bedrock Batch Inference).
- ``caching`` — prompt-caching opt-in (Anthropic cache-control, OpenAI
  prompt caching, Bedrock Claude prompt caching, Google context caching).
- ``audio`` — audio input/output endpoints adjacent to the chat surface
  (OpenAI Whisper/TTS, Google Gemini audio, Bedrock NA).

The matrix is **fail-closed** for unknown presets per
``rules/security.md`` § "Fail-Closed Security Defaults": any preset name
not enumerated in :data:`_PRESET_CAPABILITIES` returns
:data:`ALL_FALSE_CAPABILITIES`. This is structural rather than semantic —
adding a new preset constructor without wiring its capability row leaves the
new deployment marked uncapable until the wiring lands.

Cross-SDK parity: rows are byte-identical to kailash-rs ``CapabilityMatrix``
in ``crates/kailash-kaizen/src/llm/deployment/capabilities.rs``. Per
``rules/cross-sdk-inspection.md`` § 3a, divergence between the two SDKs
breaks downstream callers who port code between languages — the rows MUST
stay in lockstep across releases.
"""

from __future__ import annotations

from typing import Dict, Final, Mapping

# Capability axis keys — the contract surface. Adding a new axis requires a
# coordinated cross-SDK change so kailash-rs ``CapabilityMatrix`` grows the
# same field.
CAPABILITY_KEYS: Final[tuple[str, ...]] = (
    "tools",
    "vision",
    "batch",
    "caching",
    "audio",
)


def _caps(
    *,
    tools: bool = False,
    vision: bool = False,
    batch: bool = False,
    caching: bool = False,
    audio: bool = False,
) -> Dict[str, bool]:
    """Build a capability-matrix dict with all five keys present."""
    return {
        "tools": tools,
        "vision": vision,
        "batch": batch,
        "caching": caching,
        "audio": audio,
    }


# Fail-closed default: every axis is False. Returned for unknown / future
# preset names so a deployment whose capability row has not yet been wired
# is treated as uncapable until the wiring lands. NOT exported as a
# mutable dict — callers receive a fresh copy via :func:`for_preset`.
_ALL_FALSE: Final[Mapping[str, bool]] = _caps()
ALL_FALSE_CAPABILITIES: Final[Mapping[str, bool]] = _ALL_FALSE


# Per-preset capability matrix. Rows mirror kailash-rs
# ``CapabilityMatrix::for_preset`` — see file docstring for cross-SDK parity
# requirement.
#
# Notes on individual preset choices:
#
# - ``tools``: supported on every preset whose wire protocol carries a
#   tool/function-calling shape (OpenAI tools, Anthropic tool_use, Google
#   function declarations, Bedrock Converse tool config, Cohere tools,
#   Mistral tools, Ollama 0.3+).
# - ``vision``: supported by OpenAI (gpt-4o family), Anthropic (Claude 3+),
#   Google (Gemini family), Bedrock Claude / Llama-vision models, Azure
#   OpenAI (when the deployment maps to a vision-capable model), Vertex
#   (Gemini, Claude). Per-model gating is the caller's responsibility.
# - ``batch``: OpenAI Batch API and Anthropic Message Batches; Bedrock Batch
#   Inference for the bedrock_* family. Local / server presets (``ollama``,
#   ``groq``, ``cohere``, ``mistral``, ``perplexity``, ``huggingface``) do
#   not expose a batch surface adjacent to the completion endpoint.
# - ``caching``: Anthropic prompt caching (cache-control), OpenAI prompt
#   caching, Bedrock prompt caching for Claude, Google context caching.
#   Other presets do not expose caching at the completion-endpoint level.
# - ``audio``: OpenAI (Whisper / TTS / gpt-4o-audio), Google Gemini audio.
#   Anthropic, Cohere, Mistral, Bedrock, Ollama, Groq, Perplexity,
#   HuggingFace inference do not expose audio in the chat surface.
_PRESET_CAPABILITIES: Final[Mapping[str, Mapping[str, bool]]] = {
    # --- OpenAI family ---------------------------------------------------
    "openai": _caps(tools=True, vision=True, batch=True, caching=True, audio=True),
    "openai_compatible": _caps(
        tools=True, vision=True, batch=True, caching=True, audio=True
    ),
    # --- Anthropic family ------------------------------------------------
    "anthropic": _caps(tools=True, vision=True, batch=True, caching=True, audio=False),
    "anthropic_compatible": _caps(
        tools=True, vision=True, batch=True, caching=True, audio=False
    ),
    # --- Google family ---------------------------------------------------
    "google": _caps(tools=True, vision=True, batch=False, caching=True, audio=True),
    # --- Azure / Vertex (managed-cloud OpenAI / Anthropic) ---------------
    "azure_openai": _caps(
        tools=True, vision=True, batch=True, caching=True, audio=True
    ),
    "vertex_claude": _caps(
        tools=True, vision=True, batch=False, caching=True, audio=False
    ),
    "vertex_gemini": _caps(
        tools=True, vision=True, batch=False, caching=True, audio=True
    ),
    # --- Bedrock family --------------------------------------------------
    "bedrock_claude": _caps(
        tools=True, vision=True, batch=True, caching=True, audio=False
    ),
    "bedrock_llama": _caps(
        tools=True, vision=False, batch=True, caching=False, audio=False
    ),
    "bedrock_titan": _caps(
        tools=True, vision=False, batch=True, caching=False, audio=False
    ),
    "bedrock_mistral": _caps(
        tools=True, vision=False, batch=True, caching=False, audio=False
    ),
    "bedrock_cohere": _caps(
        tools=True, vision=False, batch=True, caching=False, audio=False
    ),
    # --- Local / open-weight servers -------------------------------------
    "groq": _caps(tools=True, vision=True, batch=False, caching=False, audio=False),
    "ollama": _caps(tools=True, vision=True, batch=False, caching=False, audio=False),
    # ``ollama_default`` is the alias kailash-rs ``CapabilityMatrix::for_preset``
    # accepts alongside ``"ollama"`` (see kailash-rs
    # ``crates/kailash-kaizen/src/llm/deployment/capabilities.rs:212`` —
    # ``str_eq(preset_name, "ollama") || str_eq(preset_name, "ollama_default")``).
    # Cross-SDK parity row per ``rules/cross-sdk-inspection.md`` § 3a; row is
    # byte-identical to ``"ollama"`` above.
    "ollama_default": _caps(
        tools=True, vision=True, batch=False, caching=False, audio=False
    ),
    # --- Direct providers ------------------------------------------------
    "cohere": _caps(tools=True, vision=False, batch=False, caching=False, audio=False),
    "mistral": _caps(tools=True, vision=True, batch=False, caching=False, audio=False),
    "perplexity": _caps(),  # all-false per kailash-rs row
    "huggingface": _caps(),  # all-false per kailash-rs row
}


def for_preset(preset_name: str | None) -> Dict[str, bool]:
    """Return the capability matrix dict for ``preset_name``.

    ``preset_name`` is the canonical preset literal carried on
    :class:`LlmDeployment.preset_name` — for example ``"openai"``,
    ``"anthropic"``, ``"bedrock_claude"``. Manual constructions whose
    ``preset_name`` is ``None`` and unknown / future preset names return
    :data:`ALL_FALSE_CAPABILITIES` as a fresh dict (fail-closed default).

    Returned dicts are independent copies — mutating the result does NOT
    mutate the matrix table. Callers may freely add or rename keys on
    their copy without leaking state across calls.
    """
    if preset_name is None:
        return dict(_ALL_FALSE)
    row = _PRESET_CAPABILITIES.get(preset_name)
    if row is None:
        return dict(_ALL_FALSE)
    return dict(row)


__all__ = [
    "CAPABILITY_KEYS",
    "ALL_FALSE_CAPABILITIES",
    "for_preset",
]

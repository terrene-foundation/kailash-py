# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Vertex AI model-grammar adapters: `VertexClaudeGrammar`, `VertexGeminiGrammar`.

Session 5 (S5) of #498. Resolves caller-supplied model aliases into Vertex AI
on-wire identifiers. Two families:

# `VertexClaudeGrammar`

Anthropic Claude models published to Vertex use the `@<date>` version
suffix convention rather than Bedrock's `-v1:0` suffix. Mapping table:

    claude-3-opus      -> claude-3-opus@20240229
    claude-3-sonnet    -> claude-3-sonnet@20240229
    claude-3-haiku     -> claude-3-haiku@20240307
    claude-3-5-sonnet  -> claude-3-5-sonnet@20240620
    claude-3-5-haiku   -> claude-3-5-haiku@20241022
    claude-sonnet-4-6  -> claude-sonnet-4-6@latest
    claude-opus-4-5    -> claude-opus-4-5@latest
    claude-haiku-4-5   -> claude-haiku-4-5@latest

Native passthrough: `claude-*@*` already-versioned ids are returned
unchanged (so callers can pin a specific version explicitly).

# `VertexGeminiGrammar`

Google Gemini models on Vertex retain their canonical model id; there is
no version suffix on the most-common short aliases. Mapping table:

    gemini-1.5-pro       -> gemini-1.5-pro
    gemini-1.5-flash     -> gemini-1.5-flash
    gemini-1.5-flash-8b  -> gemini-1.5-flash-8b
    gemini-2.0-flash     -> gemini-2.0-flash
    gemini-2.0-pro       -> gemini-2.0-pro
    gemini-2.5-pro       -> gemini-2.5-pro
    gemini-2.5-flash     -> gemini-2.5-flash

Native passthrough: any `gemini-*` model id passes through unchanged.

# Cross-SDK parity

The mapping tables and `grammar_kind()` labels are byte-identical to
`kailash-rs/crates/kailash-kaizen/src/llm/deployment/vertex.rs`. The
caller-model regex gate is the SAME shape as the Bedrock grammar so
log-injection defense is uniform across providers.
"""

from __future__ import annotations

import re
from typing import Dict

from kaizen.llm.errors import ModelGrammarInvalid

# Caller-model regex gate -- byte-identical to bedrock.py's gate so the
# rejection contract is uniform across every provider grammar. Rejects
# CRLF, control chars, leading whitespace, > 128 chars. Allows the chars
# actually found in Vertex model ids: letters, digits, dot, dash,
# underscore, colon, slash, at-sign (Vertex uses `@<date>` suffix).
_CALLER_MODEL_RE = re.compile(r"^[A-Za-z0-9_./:@\-]{1,128}$")


def _validate_caller_model_shared(caller_model: object) -> str:
    """Gate the caller-model string against the input regex.

    Raises `ModelGrammarInvalid` with a stable reason code on any input
    that is not a string, is empty, contains control chars, or exceeds 128
    chars. The raw model string is NOT echoed in the error -- log-injection
    defense (same pattern as bedrock + preset-name validation).

    Shared across both Vertex grammars so the rejection contract is
    byte-identical between Claude-on-Vertex and Gemini-on-Vertex.
    """
    if not isinstance(caller_model, str):
        raise ModelGrammarInvalid(reason="caller_model_not_string")
    if not _CALLER_MODEL_RE.match(caller_model):
        raise ModelGrammarInvalid(reason="caller_model_failed_regex_gate")
    return caller_model


# ---------------------------------------------------------------------------
# VertexClaudeGrammar
# ---------------------------------------------------------------------------

# Claude-on-Vertex on-wire ids use the `@<date>` suffix convention. Source
# of truth for cross-SDK parity:
# kailash-rs/crates/kailash-kaizen/src/llm/deployment/vertex.rs::VERTEX_CLAUDE_MAPPING
_VERTEX_CLAUDE_MAPPING: Dict[str, str] = {
    # Legacy Claude 3 family on Vertex
    "claude-3-opus": "claude-3-opus@20240229",
    "claude-3-sonnet": "claude-3-sonnet@20240229",
    "claude-3-haiku": "claude-3-haiku@20240307",
    "claude-3-5-sonnet": "claude-3-5-sonnet@20240620",
    "claude-3-5-haiku": "claude-3-5-haiku@20241022",
    # Current-gen Claude 4 family (no fixed date suffix on Vertex; @latest
    # picks the most recent published version).
    "claude-sonnet-4-6": "claude-sonnet-4-6@latest",
    "claude-opus-4-5": "claude-opus-4-5@latest",
    "claude-haiku-4-5": "claude-haiku-4-5@latest",
}


class VertexClaudeGrammar:
    """Grammar for Anthropic Claude models served via Vertex AI.

    Caller supplies a short alias (`claude-3-opus`) or an already-versioned
    on-wire id (`claude-3-opus@20240229`). Anything else raises
    `ModelGrammarInvalid(reason="vertex_claude_not_in_catalog")`.

    Distinct from `BedrockClaudeGrammar` because the on-wire id format
    differs: Bedrock uses `anthropic.claude-X-v1:0`, Vertex uses
    `claude-X@<date>`.
    """

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        """Translate `caller_model` into a Vertex on-wire Claude model id.

        Returns the translated id, or the input unchanged if it is already
        in `claude-*@*` shape. Raises
        `ModelGrammarInvalid(reason="vertex_claude_not_in_catalog")` if the
        input is neither a known alias nor a valid on-wire id.
        """
        validated = self._validate_caller_model(caller_model)
        # 1) Short alias
        if validated in _VERTEX_CLAUDE_MAPPING:
            return _VERTEX_CLAUDE_MAPPING[validated]
        # 2) Already-versioned passthrough -- `claude-X@<date>` or
        # `claude-X@latest`. The `@` is the discriminator; un-suffixed
        # `claude-3-opus` would have hit the alias table above.
        if validated.startswith("claude-") and "@" in validated:
            return validated
        raise ModelGrammarInvalid(reason="vertex_claude_not_in_catalog")

    def grammar_kind(self) -> str:
        """Stable label for observability / cross-SDK parity."""
        return "vertex_claude"


# ---------------------------------------------------------------------------
# VertexGeminiGrammar
# ---------------------------------------------------------------------------

# Gemini-on-Vertex on-wire ids match the canonical Gemini model name. Source
# of truth for cross-SDK parity:
# kailash-rs/crates/kailash-kaizen/src/llm/deployment/vertex.rs::VERTEX_GEMINI_MAPPING
_VERTEX_GEMINI_MAPPING: Dict[str, str] = {
    "gemini-1.5-pro": "gemini-1.5-pro",
    "gemini-1.5-flash": "gemini-1.5-flash",
    "gemini-1.5-flash-8b": "gemini-1.5-flash-8b",
    "gemini-2.0-flash": "gemini-2.0-flash",
    "gemini-2.0-pro": "gemini-2.0-pro",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
}


class VertexGeminiGrammar:
    """Grammar for Google Gemini models served via Vertex AI.

    Caller supplies a short alias (`gemini-1.5-pro`) or any `gemini-*`
    model id. Anything else raises
    `ModelGrammarInvalid(reason="vertex_gemini_not_in_catalog")`.
    """

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        validated = self._validate_caller_model(caller_model)
        # 1) Known short alias -- pass through (the mapping is identity for
        # gemini today, but a future minor-version bump may diverge).
        if validated in _VERTEX_GEMINI_MAPPING:
            return _VERTEX_GEMINI_MAPPING[validated]
        # 2) Native passthrough: any `gemini-*` model id is accepted.
        if validated.startswith("gemini-"):
            return validated
        raise ModelGrammarInvalid(reason="vertex_gemini_not_in_catalog")

    def grammar_kind(self) -> str:
        return "vertex_gemini"


__all__ = [
    "VertexClaudeGrammar",
    "VertexGeminiGrammar",
]

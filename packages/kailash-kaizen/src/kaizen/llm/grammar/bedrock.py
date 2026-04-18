# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Bedrock model-grammar adapters.

# `BedrockClaudeGrammar`

Resolves caller-supplied Claude model aliases into Bedrock on-wire
identifiers. Accepts three input shapes:

1. **Short aliases** (the common case the developer types) -- mapped via
   an explicit table to the fully-qualified Bedrock id:

       claude-3-opus      -> anthropic.claude-3-opus-20240229-v1:0
       claude-3-5-sonnet  -> anthropic.claude-3-5-sonnet-20240620-v1:0
       claude-3-haiku     -> anthropic.claude-3-haiku-20240307-v1:0
       claude-3-5-haiku   -> anthropic.claude-3-5-haiku-20241022-v1:0
       claude-sonnet-4-6  -> anthropic.claude-sonnet-4-6-v1:0
       claude-opus-4-5    -> anthropic.claude-opus-4-5-v1:0
       claude-haiku-4-5   -> anthropic.claude-haiku-4-5-v1:0

2. **Inference-profile form** -- passthrough (`<region>.anthropic.*`):

       global.anthropic.claude-sonnet-4-6
       us.anthropic.claude-opus-4-5
       eu.anthropic.claude-haiku-4-5
       ap.anthropic.*

3. **Native on-wire form** -- passthrough (`anthropic.*`):

       anthropic.claude-3-opus-20240229-v1:0
       anthropic.claude-sonnet-4-6-v1:0

Any other shape is rejected with `ModelGrammarInvalid(reason="bedrock_claude_not_in_catalog")`.

The input is first validated against a regex gate (`_CALLER_MODEL_RE`)
that rejects CRLF, control characters, leading whitespace, and anything
longer than 128 characters -- this is the log-injection defense (same
shape as `preset_name` validation in presets.py). The regex matches
Python dictionaries, dataclasses, None, etc. before any mapping lookup.

# Cross-SDK parity

The mapping table is byte-identical to
`kailash-rs/crates/kailash-kaizen/src/llm/deployment/bedrock.rs`.
The Rust variant lists only the three `claude-sonnet-4-6`,
`claude-opus-4-5`, `claude-haiku-4-5` short aliases; we additionally
ship four legacy aliases (3.x families) so existing callers that have
already typed `claude-3-opus` don't break. A Rust alignment bump is
tracked as a follow-up once both SDKs ship S4a.
"""

from __future__ import annotations

import re
from typing import Dict

from kaizen.llm.errors import ModelGrammarInvalid

# Caller-model validation regex. Rejects CRLF, control chars, leading
# whitespace, anything > 128 chars. The regex is deliberately permissive
# inside the 128-char window (dots, slashes, colons, digits, letters, "-")
# because passthrough inference-profile ids contain dots and colons.
#
# Rejects:
#   * empty string
#   * any ASCII control char (\x00-\x1f) including \r, \n, \t
#   * > 128 chars total
#   * non-string input (handled via isinstance before regex)
#
# Allows the set of chars actually found in Bedrock ids + aliases:
#   [A-Za-z0-9_./:\-]
_CALLER_MODEL_RE = re.compile(r"^[A-Za-z0-9_./:\-]{1,128}$")


# Short-alias table: alias -> on-wire Bedrock id.
# Ordered for grep: grep "claude-3" bedrock.py finds the legacy block;
# grep "claude-sonnet-4-6" finds the current-gen block.
_BEDROCK_CLAUDE_MAPPING: Dict[str, str] = {
    # Legacy Claude 3 family (deployed on Bedrock since 2024)
    "claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
    "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
    "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
    "claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "claude-3-5-haiku": "anthropic.claude-3-5-haiku-20241022-v1:0",
    # Current-gen Claude 4 family (short-alias form matches Rust SDK)
    "claude-sonnet-4-6": "anthropic.claude-sonnet-4-6-v1:0",
    "claude-opus-4-5": "anthropic.claude-opus-4-5-v1:0",
    "claude-haiku-4-5": "anthropic.claude-haiku-4-5-v1:0",
}


# Inference-profile prefixes that pass through unchanged. Matches
# kailash-rs bedrock.rs::is_passthrough_shape.
_PASSTHROUGH_PREFIXES: tuple[str, ...] = (
    "global.anthropic.",
    "us.anthropic.",
    "eu.anthropic.",
    "ap.anthropic.",
)


def _validate_caller_model_shared(caller_model: object) -> str:
    """Gate the caller-model string against the input regex.

    Raises `ModelGrammarInvalid` with a stable reason code on any
    input that is not a string, is empty, contains control chars, or
    exceeds 128 chars. The raw model string is NOT echoed in the
    error -- log-injection defense (same pattern as preset-name
    validation).

    Shared across every Bedrock family grammar so the rejection contract
    is byte-identical no matter which family the caller hits.
    """
    if not isinstance(caller_model, str):
        raise ModelGrammarInvalid(reason="caller_model_not_string")
    if not _CALLER_MODEL_RE.match(caller_model):
        raise ModelGrammarInvalid(reason="caller_model_failed_regex_gate")
    return caller_model


class BedrockClaudeGrammar:
    """Grammar for AWS Bedrock Claude model identifiers.

    Immutable + no state -- a single instance is reusable across every
    deployment that targets Bedrock Claude. The class has a `resolve()`
    method rather than being a plain function because subsequent grammars
    (Llama, Titan, ...) may carry provider-specific config (inference
    profile defaults, region-gated catalog entries) that a bare function
    cannot.
    """

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        """Translate `caller_model` into a Bedrock on-wire model id.

        Returns the translated id (or the input unchanged if it is
        already in passthrough shape). Raises
        `ModelGrammarInvalid(reason="bedrock_claude_not_in_catalog")` if
        the input is neither a known alias nor a valid passthrough shape.
        """
        validated = self._validate_caller_model(caller_model)
        # 1) Short alias
        if validated in _BEDROCK_CLAUDE_MAPPING:
            return _BEDROCK_CLAUDE_MAPPING[validated]
        # 2) Inference-profile passthrough
        for prefix in _PASSTHROUGH_PREFIXES:
            if validated.startswith(prefix):
                return validated
        # 3) Native on-wire passthrough
        if validated.startswith("anthropic."):
            return validated
        raise ModelGrammarInvalid(reason="bedrock_claude_not_in_catalog")

    def grammar_kind(self) -> str:
        """Stable label for observability / cross-SDK parity."""
        return "bedrock_claude"


# ---------------------------------------------------------------------------
# BedrockLlamaGrammar (S4b-ii)
# ---------------------------------------------------------------------------
#
# Short alias -> on-wire id mapping for the Meta Llama family on Bedrock.
# The on-wire id format is `meta.llama<major>-<minor>-<variant>-v1:0`. The
# short aliases match the caller-facing names ("llama-3.1-70b") Meta uses
# in its own docs; Bedrock prefixes them with `meta.` and reshapes dots to
# dashes. Cross-SDK parity: byte-identical to the Rust variant's mapping
# in `kailash-rs/crates/kailash-kaizen/src/llm/deployment/bedrock.rs`.

_BEDROCK_LLAMA_MAPPING: Dict[str, str] = {
    # Llama 3.0 -- original release
    "llama-3-8b": "meta.llama3-8b-instruct-v1:0",
    "llama-3-70b": "meta.llama3-70b-instruct-v1:0",
    # Llama 3.1 -- introduced 405B + improved context
    "llama-3.1-8b": "meta.llama3-1-8b-instruct-v1:0",
    "llama-3.1-70b": "meta.llama3-1-70b-instruct-v1:0",
    "llama-3.1-405b": "meta.llama3-1-405b-instruct-v1:0",
    # Llama 3.2 -- multimodal tier
    "llama-3.2-1b": "meta.llama3-2-1b-instruct-v1:0",
    "llama-3.2-3b": "meta.llama3-2-3b-instruct-v1:0",
    "llama-3.2-11b": "meta.llama3-2-11b-instruct-v1:0",
    "llama-3.2-90b": "meta.llama3-2-90b-instruct-v1:0",
    # Llama 3.3 -- current-gen (2024 release)
    "llama-3.3-70b": "meta.llama3-3-70b-instruct-v1:0",
}

# Inference-profile passthrough prefixes for Llama (region-gated profiles).
_LLAMA_PASSTHROUGH_PREFIXES: tuple[str, ...] = (
    "global.meta.",
    "us.meta.",
    "eu.meta.",
    "ap.meta.",
)


class BedrockLlamaGrammar:
    """Grammar for AWS Bedrock Meta Llama model identifiers.

    Caller supplies a short alias (`llama-3.1-70b`), an inference-profile
    id (`us.meta.llama3-1-70b-instruct-v1:0`), or a native on-wire id
    (`meta.llama3-1-70b-instruct-v1:0`). Anything else raises
    `ModelGrammarInvalid(reason="bedrock_llama_not_in_catalog")`.
    """

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        validated = self._validate_caller_model(caller_model)
        if validated in _BEDROCK_LLAMA_MAPPING:
            return _BEDROCK_LLAMA_MAPPING[validated]
        for prefix in _LLAMA_PASSTHROUGH_PREFIXES:
            if validated.startswith(prefix):
                return validated
        if validated.startswith("meta."):
            return validated
        raise ModelGrammarInvalid(reason="bedrock_llama_not_in_catalog")

    def grammar_kind(self) -> str:
        return "bedrock_llama"


# ---------------------------------------------------------------------------
# BedrockTitanGrammar (S4b-ii)
# ---------------------------------------------------------------------------
#
# Amazon Titan family on Bedrock. Titan has three model tiers: text-lite
# (small, fast), text-express (balanced), text-premier (high-capability).
# On-wire ids are `amazon.titan-text-*-v1`. There is no versioned suffix
# like Claude's `:0`; Titan models are single-stream v1 ids.

_BEDROCK_TITAN_MAPPING: Dict[str, str] = {
    "titan-text-lite": "amazon.titan-text-lite-v1",
    "titan-text-express": "amazon.titan-text-express-v1",
    "titan-text-premier": "amazon.titan-text-premier-v1:0",
    # Embeddings family (same grammar -- callers may use the text grammar
    # for embeddings since Bedrock routes by the full on-wire id).
    "titan-embed-text": "amazon.titan-embed-text-v1",
    "titan-embed-text-v2": "amazon.titan-embed-text-v2:0",
    "titan-embed-image": "amazon.titan-embed-image-v1",
}

_TITAN_PASSTHROUGH_PREFIXES: tuple[str, ...] = (
    "global.amazon.",
    "us.amazon.",
    "eu.amazon.",
    "ap.amazon.",
)


class BedrockTitanGrammar:
    """Grammar for AWS Bedrock Amazon Titan model identifiers."""

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        validated = self._validate_caller_model(caller_model)
        if validated in _BEDROCK_TITAN_MAPPING:
            return _BEDROCK_TITAN_MAPPING[validated]
        for prefix in _TITAN_PASSTHROUGH_PREFIXES:
            if validated.startswith(prefix):
                return validated
        if validated.startswith("amazon."):
            return validated
        raise ModelGrammarInvalid(reason="bedrock_titan_not_in_catalog")

    def grammar_kind(self) -> str:
        return "bedrock_titan"


# ---------------------------------------------------------------------------
# BedrockMistralGrammar (S4b-ii)
# ---------------------------------------------------------------------------
#
# Mistral family on Bedrock -- distinct wire prefix from Mistral-direct:
# Bedrock on-wire ids are `mistral.<model>-<date>-v1:0`, whereas
# Mistral-direct API uses `<model>-latest` / version strings. The grammar
# here is Bedrock-only; Mistral-direct goes through `mistral_preset`.

_BEDROCK_MISTRAL_MAPPING: Dict[str, str] = {
    "mistral-7b": "mistral.mistral-7b-instruct-v0:2",
    "mixtral-8x7b": "mistral.mixtral-8x7b-instruct-v0:1",
    "mistral-small": "mistral.mistral-small-2402-v1:0",
    "mistral-large": "mistral.mistral-large-2402-v1:0",
    "mistral-large-2407": "mistral.mistral-large-2407-v1:0",
}

_MISTRAL_BEDROCK_PASSTHROUGH_PREFIXES: tuple[str, ...] = (
    "global.mistral.",
    "us.mistral.",
    "eu.mistral.",
    "ap.mistral.",
)


class BedrockMistralGrammar:
    """Grammar for AWS Bedrock Mistral model identifiers.

    Distinct from the Mistral-direct grammar: Bedrock ships models under
    `mistral.<name>-<date>-v1:0` ids. The same short alias may resolve
    differently here than in `mistral_preset` (Mistral-direct).
    """

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        validated = self._validate_caller_model(caller_model)
        if validated in _BEDROCK_MISTRAL_MAPPING:
            return _BEDROCK_MISTRAL_MAPPING[validated]
        for prefix in _MISTRAL_BEDROCK_PASSTHROUGH_PREFIXES:
            if validated.startswith(prefix):
                return validated
        if validated.startswith("mistral."):
            return validated
        raise ModelGrammarInvalid(reason="bedrock_mistral_not_in_catalog")

    def grammar_kind(self) -> str:
        return "bedrock_mistral"


# ---------------------------------------------------------------------------
# BedrockCohereGrammar (S4b-ii)
# ---------------------------------------------------------------------------
#
# Cohere family on Bedrock. Distinct from Cohere-direct API (which uses
# `CohereGenerate` wire + different default endpoints). On-wire ids are
# `cohere.<model>-v1:0`.

_BEDROCK_COHERE_MAPPING: Dict[str, str] = {
    "cohere-command": "cohere.command-text-v14",
    "cohere-command-light": "cohere.command-light-text-v14",
    "cohere-command-r": "cohere.command-r-v1:0",
    "cohere-command-r-plus": "cohere.command-r-plus-v1:0",
    "cohere-embed-english": "cohere.embed-english-v3",
    "cohere-embed-multilingual": "cohere.embed-multilingual-v3",
}

_COHERE_BEDROCK_PASSTHROUGH_PREFIXES: tuple[str, ...] = (
    "global.cohere.",
    "us.cohere.",
    "eu.cohere.",
    "ap.cohere.",
)


class BedrockCohereGrammar:
    """Grammar for AWS Bedrock Cohere model identifiers.

    Distinct from the Cohere-direct grammar: Bedrock ships models under
    `cohere.<name>-v1:0` ids and speaks the Bedrock `AnthropicMessages` /
    `BedrockInvoke` wire depending on the caller's choice. The direct
    Cohere API uses the `CohereGenerate` wire.
    """

    __slots__ = ()

    @staticmethod
    def _validate_caller_model(caller_model: object) -> str:
        return _validate_caller_model_shared(caller_model)

    def resolve(self, caller_model: str) -> str:
        validated = self._validate_caller_model(caller_model)
        if validated in _BEDROCK_COHERE_MAPPING:
            return _BEDROCK_COHERE_MAPPING[validated]
        for prefix in _COHERE_BEDROCK_PASSTHROUGH_PREFIXES:
            if validated.startswith(prefix):
                return validated
        if validated.startswith("cohere."):
            return validated
        raise ModelGrammarInvalid(reason="bedrock_cohere_not_in_catalog")

    def grammar_kind(self) -> str:
        return "bedrock_cohere"


__all__ = [
    "BedrockClaudeGrammar",
    "BedrockLlamaGrammar",
    "BedrockTitanGrammar",
    "BedrockMistralGrammar",
    "BedrockCohereGrammar",
]

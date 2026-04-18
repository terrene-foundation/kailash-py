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
        """Gate the caller-model string against the input regex.

        Raises `ModelGrammarInvalid` with a stable reason code on any
        input that is not a string, is empty, contains control chars, or
        exceeds 128 chars. The raw model string is NOT echoed in the
        error -- log-injection defense (same pattern as preset-name
        validation).
        """
        if not isinstance(caller_model, str):
            raise ModelGrammarInvalid(reason="caller_model_not_string")
        if not _CALLER_MODEL_RE.match(caller_model):
            raise ModelGrammarInvalid(reason="caller_model_failed_regex_gate")
        return caller_model

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


__all__ = ["BedrockClaudeGrammar"]

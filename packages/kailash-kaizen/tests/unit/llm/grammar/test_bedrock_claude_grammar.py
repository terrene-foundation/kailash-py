# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `BedrockClaudeGrammar` (#498 Session 3, S4a).

Covers:

* Short-alias mapping for every Claude family (3, 3.5, 4.x)
* Inference-profile passthrough (global.*, us.*, eu.*, ap.*)
* Native on-wire passthrough (anthropic.*)
* Regex gate rejects CRLF, null, control chars, non-strings
* Unknown models raise `ModelGrammarInvalid(reason=bedrock_claude_not_in_catalog)`
* `grammar_kind()` == "bedrock_claude" (cross-SDK parity)
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.bedrock import BedrockClaudeGrammar


@pytest.fixture
def grammar() -> BedrockClaudeGrammar:
    return BedrockClaudeGrammar()


# ---------------------------------------------------------------------------
# Short-alias mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("claude-3-opus", "anthropic.claude-3-opus-20240229-v1:0"),
        ("claude-3-sonnet", "anthropic.claude-3-sonnet-20240229-v1:0"),
        ("claude-3-haiku", "anthropic.claude-3-haiku-20240307-v1:0"),
        ("claude-3-5-sonnet", "anthropic.claude-3-5-sonnet-20240620-v1:0"),
        ("claude-3-5-haiku", "anthropic.claude-3-5-haiku-20241022-v1:0"),
        ("claude-sonnet-4-6", "anthropic.claude-sonnet-4-6-v1:0"),
        ("claude-opus-4-5", "anthropic.claude-opus-4-5-v1:0"),
        ("claude-haiku-4-5", "anthropic.claude-haiku-4-5-v1:0"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: BedrockClaudeGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


def test_grammar_mapping_table_covers_every_claude_family(
    grammar: BedrockClaudeGrammar,
) -> None:
    """Brief invariant 3: mapping table covers Claude 3, 3.5 Sonnet, 3 Haiku,
    3 Opus, 3.5 Haiku.
    """
    required = {
        "claude-3-opus",
        "claude-3-5-sonnet",
        "claude-3-haiku",
        "claude-3-5-haiku",
    }
    for alias in required:
        # Resolve returns a non-empty on-wire id (never the input unchanged
        # for these canonical aliases).
        resolved = grammar.resolve(alias)
        assert resolved.startswith("anthropic.")
        assert resolved != alias


# ---------------------------------------------------------------------------
# Passthrough shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caller_model",
    [
        "global.anthropic.claude-sonnet-4-6",
        "us.anthropic.claude-opus-4-5",
        "eu.anthropic.claude-haiku-4-5",
        "ap.anthropic.claude-sonnet-4-6",
    ],
)
def test_grammar_passes_inference_profile_through_unchanged(
    grammar: BedrockClaudeGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


@pytest.mark.parametrize(
    "caller_model",
    [
        "anthropic.claude-3-opus-20240229-v1:0",
        "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "anthropic.claude-haiku-4-5-v1:0",
    ],
)
def test_grammar_passes_native_on_wire_through_unchanged(
    grammar: BedrockClaudeGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


# ---------------------------------------------------------------------------
# Regex gate -- rejects CRLF / control chars / non-strings
# ---------------------------------------------------------------------------


def test_grammar_rejects_non_string(grammar: BedrockClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(12345)  # type: ignore[arg-type]


def test_grammar_rejects_none(grammar: BedrockClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(None)  # type: ignore[arg-type]


def test_grammar_rejects_empty_string(grammar: BedrockClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("")


def test_grammar_rejects_crlf_injection(grammar: BedrockClaudeGrammar) -> None:
    """Log-injection defense: CRLF in a caller-supplied model MUST NOT pass
    the regex gate.
    """
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("claude-3-opus\r\nX-Evil: yes")


def test_grammar_rejects_null_byte(grammar: BedrockClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("claude-3-opus\x00")


def test_grammar_rejects_tab_char(grammar: BedrockClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("claude-3-opus\t")


def test_grammar_rejects_oversized_input(grammar: BedrockClaudeGrammar) -> None:
    oversized = "anthropic." + "x" * 200
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve(oversized)


# ---------------------------------------------------------------------------
# Unknown -> not-in-catalog
# ---------------------------------------------------------------------------


def test_grammar_rejects_unknown_caller_model(
    grammar: BedrockClaudeGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_claude_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_non_anthropic_passthrough(
    grammar: BedrockClaudeGrammar,
) -> None:
    """A model id that passes the regex but is not in an accepted shape
    must reject.
    """
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_claude_not_in_catalog"):
        grammar.resolve("meta.llama3-8b-instruct-v1:0")


# ---------------------------------------------------------------------------
# grammar_kind -- cross-SDK parity label
# ---------------------------------------------------------------------------


def test_grammar_kind_is_stable_literal(grammar: BedrockClaudeGrammar) -> None:
    """Rust parity: `BedrockClaudeGrammar.grammar_kind()` must byte-match."""
    assert grammar.grammar_kind() == "bedrock_claude"

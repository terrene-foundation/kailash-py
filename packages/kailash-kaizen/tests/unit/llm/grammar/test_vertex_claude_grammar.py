# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `VertexClaudeGrammar` (#498 Session 5, S5).

Covers:

* Short-alias mapping for every published Claude family on Vertex
* Already-versioned passthrough (`claude-X@<date>`)
* Regex gate rejects CRLF, null, control chars, non-strings
* Unknown models raise
  `ModelGrammarInvalid(reason=vertex_claude_not_in_catalog)`
* `grammar_kind()` == "vertex_claude" (cross-SDK parity)
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.vertex import VertexClaudeGrammar


@pytest.fixture
def grammar() -> VertexClaudeGrammar:
    return VertexClaudeGrammar()


# ---------------------------------------------------------------------------
# Short-alias mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("claude-3-opus", "claude-3-opus@20240229"),
        ("claude-3-sonnet", "claude-3-sonnet@20240229"),
        ("claude-3-haiku", "claude-3-haiku@20240307"),
        ("claude-3-5-sonnet", "claude-3-5-sonnet@20240620"),
        ("claude-3-5-haiku", "claude-3-5-haiku@20241022"),
        ("claude-sonnet-4-6", "claude-sonnet-4-6@latest"),
        ("claude-opus-4-5", "claude-opus-4-5@latest"),
        ("claude-haiku-4-5", "claude-haiku-4-5@latest"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: VertexClaudeGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


def test_grammar_short_aliases_carry_at_suffix(
    grammar: VertexClaudeGrammar,
) -> None:
    """Cross-SDK parity: every Vertex-Claude on-wire id has `@`."""
    for alias in (
        "claude-3-opus",
        "claude-3-5-sonnet",
        "claude-sonnet-4-6",
        "claude-opus-4-5",
        "claude-haiku-4-5",
    ):
        resolved = grammar.resolve(alias)
        assert "@" in resolved, f"alias {alias!r} resolved to {resolved!r}"


# ---------------------------------------------------------------------------
# Passthrough (already versioned)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caller_model",
    [
        "claude-3-opus@20240229",
        "claude-3-5-sonnet@20240620",
        "claude-haiku-4-5@latest",
        "claude-sonnet-4-6@20250101",
    ],
)
def test_grammar_passes_versioned_id_through_unchanged(
    grammar: VertexClaudeGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


# ---------------------------------------------------------------------------
# Regex gate -- rejects CRLF / control chars / non-strings
# ---------------------------------------------------------------------------


def test_grammar_rejects_non_string(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(12345)  # type: ignore[arg-type]


def test_grammar_rejects_none(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(None)  # type: ignore[arg-type]


def test_grammar_rejects_empty_string(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("")


def test_grammar_rejects_crlf_injection(grammar: VertexClaudeGrammar) -> None:
    """Log-injection defense: CRLF in caller-supplied model MUST NOT pass."""
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("claude-3-opus\r\nX-Evil: yes")


def test_grammar_rejects_null_byte(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("claude-3-opus\x00")


def test_grammar_rejects_tab_char(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("claude-3-opus\t")


def test_grammar_rejects_oversized_input(grammar: VertexClaudeGrammar) -> None:
    oversized = "claude-" + "x" * 200
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve(oversized)


# ---------------------------------------------------------------------------
# Unknown -> not-in-catalog
# ---------------------------------------------------------------------------


def test_grammar_rejects_unknown_caller_model(
    grammar: VertexClaudeGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"vertex_claude_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_unversioned_unknown_claude_alias(
    grammar: VertexClaudeGrammar,
) -> None:
    """A `claude-` prefix without `@` and not in the table must reject."""
    with pytest.raises(ModelGrammarInvalid, match=r"vertex_claude_not_in_catalog"):
        grammar.resolve("claude-99-fictional")


def test_grammar_rejects_anthropic_dot_prefix(
    grammar: VertexClaudeGrammar,
) -> None:
    """Bedrock-shape `anthropic.*` IDs must NOT pass through Vertex grammar."""
    with pytest.raises(ModelGrammarInvalid, match=r"vertex_claude_not_in_catalog"):
        grammar.resolve("anthropic.claude-3-opus-20240229-v1:0")


# ---------------------------------------------------------------------------
# grammar_kind -- cross-SDK parity label
# ---------------------------------------------------------------------------


def test_grammar_kind_is_stable_literal(grammar: VertexClaudeGrammar) -> None:
    """Rust parity: `VertexClaudeGrammar.grammar_kind()` must byte-match."""
    assert grammar.grammar_kind() == "vertex_claude"

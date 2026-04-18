# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `VertexGeminiGrammar` (#498 Session 5, S5).

Covers:

* Short-alias mapping for every published Gemini family on Vertex
* Native passthrough (`gemini-*`)
* Regex gate rejects CRLF, null, control chars, non-strings
* Unknown models raise
  `ModelGrammarInvalid(reason=vertex_gemini_not_in_catalog)`
* `grammar_kind()` == "vertex_gemini" (cross-SDK parity)
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.vertex import VertexGeminiGrammar


@pytest.fixture
def grammar() -> VertexGeminiGrammar:
    return VertexGeminiGrammar()


# ---------------------------------------------------------------------------
# Short-alias mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("gemini-1.5-pro", "gemini-1.5-pro"),
        ("gemini-1.5-flash", "gemini-1.5-flash"),
        ("gemini-1.5-flash-8b", "gemini-1.5-flash-8b"),
        ("gemini-2.0-flash", "gemini-2.0-flash"),
        ("gemini-2.0-pro", "gemini-2.0-pro"),
        ("gemini-2.5-pro", "gemini-2.5-pro"),
        ("gemini-2.5-flash", "gemini-2.5-flash"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: VertexGeminiGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


# ---------------------------------------------------------------------------
# Native passthrough
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caller_model",
    [
        "gemini-1.5-pro-001",
        "gemini-2.0-flash-exp",
        "gemini-3.0-experimental",
    ],
)
def test_grammar_passes_native_gemini_id_through_unchanged(
    grammar: VertexGeminiGrammar, caller_model: str
) -> None:
    """Any `gemini-*` prefix passes through (Vertex routes by model id)."""
    assert grammar.resolve(caller_model) == caller_model


# ---------------------------------------------------------------------------
# Regex gate -- rejects CRLF / control chars / non-strings
# ---------------------------------------------------------------------------


def test_grammar_rejects_non_string(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(12345)  # type: ignore[arg-type]


def test_grammar_rejects_none(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(None)  # type: ignore[arg-type]


def test_grammar_rejects_empty_string(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("")


def test_grammar_rejects_crlf_injection(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("gemini-1.5-pro\r\nX-Evil: yes")


def test_grammar_rejects_null_byte(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("gemini-1.5-pro\x00")


def test_grammar_rejects_oversized_input(grammar: VertexGeminiGrammar) -> None:
    oversized = "gemini-" + "x" * 200
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve(oversized)


# ---------------------------------------------------------------------------
# Unknown -> not-in-catalog
# ---------------------------------------------------------------------------


def test_grammar_rejects_unknown_caller_model(
    grammar: VertexGeminiGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"vertex_gemini_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_claude_alias(
    grammar: VertexGeminiGrammar,
) -> None:
    """Claude-family models must NOT pass through Gemini grammar."""
    with pytest.raises(ModelGrammarInvalid, match=r"vertex_gemini_not_in_catalog"):
        grammar.resolve("claude-3-opus")


# ---------------------------------------------------------------------------
# grammar_kind -- cross-SDK parity label
# ---------------------------------------------------------------------------


def test_grammar_kind_is_stable_literal(grammar: VertexGeminiGrammar) -> None:
    """Rust parity: `VertexGeminiGrammar.grammar_kind()` must byte-match."""
    assert grammar.grammar_kind() == "vertex_gemini"

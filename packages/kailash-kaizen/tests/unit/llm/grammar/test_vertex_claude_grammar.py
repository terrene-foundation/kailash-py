# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""VertexClaudeGrammar resolution tests (#498 S5)."""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.vertex import VertexClaudeGrammar


@pytest.fixture
def grammar() -> VertexClaudeGrammar:
    return VertexClaudeGrammar()


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("claude-3-opus", "claude-3-opus@20240229"),
        ("claude-3-sonnet", "claude-3-sonnet@20240229"),
        ("claude-3-haiku", "claude-3-haiku@20240307"),
        ("claude-3-5-sonnet", "claude-3-5-sonnet@20240620"),
        ("claude-3-5-haiku", "claude-3-5-haiku@20241022"),
    ],
)
def test_vertex_claude_grammar_maps_short_aliases(
    grammar: VertexClaudeGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


def test_vertex_claude_grammar_passthrough_already_versioned(
    grammar: VertexClaudeGrammar,
) -> None:
    """Callers who pin a specific version get it back unchanged."""
    versioned = "claude-3-opus@20240229"
    assert grammar.resolve(versioned) == versioned


def test_vertex_claude_grammar_rejects_unknown(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve("gpt-4")


def test_vertex_claude_grammar_rejects_empty(grammar: VertexClaudeGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve("")


def test_vertex_claude_grammar_rejects_control_chars(
    grammar: VertexClaudeGrammar,
) -> None:
    # CRLF injection attempt -- regex gate rejects.
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve("claude-3-opus\r\nX-Injected: 1")

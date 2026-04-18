# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""VertexGeminiGrammar resolution tests (#498 S5)."""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.vertex import VertexGeminiGrammar


@pytest.fixture
def grammar() -> VertexGeminiGrammar:
    return VertexGeminiGrammar()


@pytest.mark.parametrize(
    "model",
    [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-2.0-flash",
    ],
)
def test_vertex_gemini_grammar_accepts_canonical(
    grammar: VertexGeminiGrammar, model: str
) -> None:
    # Gemini models on Vertex retain their canonical id.
    assert grammar.resolve(model) == model


def test_vertex_gemini_grammar_rejects_unknown(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve("gpt-4")


def test_vertex_gemini_grammar_rejects_empty(grammar: VertexGeminiGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve("")


def test_vertex_gemini_grammar_rejects_control_chars(
    grammar: VertexGeminiGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve("gemini-1.5-pro\r\nX-Injected: 1")

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `BedrockTitanGrammar` (#498 Session 4, S4b-ii)."""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.bedrock import BedrockTitanGrammar


@pytest.fixture
def grammar() -> BedrockTitanGrammar:
    return BedrockTitanGrammar()


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("titan-text-lite", "amazon.titan-text-lite-v1"),
        ("titan-text-express", "amazon.titan-text-express-v1"),
        ("titan-text-premier", "amazon.titan-text-premier-v1:0"),
        ("titan-embed-text", "amazon.titan-embed-text-v1"),
        ("titan-embed-text-v2", "amazon.titan-embed-text-v2:0"),
        ("titan-embed-image", "amazon.titan-embed-image-v1"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: BedrockTitanGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


@pytest.mark.parametrize(
    "caller_model",
    [
        "global.amazon.titan-text-express-v1",
        "us.amazon.titan-text-premier-v1:0",
        "eu.amazon.titan-embed-text-v2:0",
        "ap.amazon.titan-text-lite-v1",
    ],
)
def test_grammar_passes_inference_profile_through_unchanged(
    grammar: BedrockTitanGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


@pytest.mark.parametrize(
    "caller_model",
    [
        "amazon.titan-text-lite-v1",
        "amazon.titan-text-express-v1",
        "amazon.titan-embed-text-v2:0",
    ],
)
def test_grammar_passes_native_on_wire_through_unchanged(
    grammar: BedrockTitanGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


def test_grammar_rejects_non_string(grammar: BedrockTitanGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(None)  # type: ignore[arg-type]


def test_grammar_rejects_crlf_injection(grammar: BedrockTitanGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("titan-text-lite\r\nEvil: yes")


def test_grammar_rejects_null_byte(grammar: BedrockTitanGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("titan-text-lite\x00")


def test_grammar_rejects_oversized_input(grammar: BedrockTitanGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("amazon." + "x" * 200)


def test_grammar_rejects_unknown_caller_model(
    grammar: BedrockTitanGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_titan_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_cross_family_on_wire_id(
    grammar: BedrockTitanGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_titan_not_in_catalog"):
        grammar.resolve("anthropic.claude-3-opus-20240229-v1:0")


def test_grammar_kind_is_stable_literal(grammar: BedrockTitanGrammar) -> None:
    assert grammar.grammar_kind() == "bedrock_titan"

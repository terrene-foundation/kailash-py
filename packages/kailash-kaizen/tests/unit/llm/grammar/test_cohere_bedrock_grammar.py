# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `BedrockCohereGrammar` (#498 Session 4, S4b-ii)."""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.bedrock import BedrockCohereGrammar


@pytest.fixture
def grammar() -> BedrockCohereGrammar:
    return BedrockCohereGrammar()


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("cohere-command", "cohere.command-text-v14"),
        ("cohere-command-light", "cohere.command-light-text-v14"),
        ("cohere-command-r", "cohere.command-r-v1:0"),
        ("cohere-command-r-plus", "cohere.command-r-plus-v1:0"),
        ("cohere-embed-english", "cohere.embed-english-v3"),
        ("cohere-embed-multilingual", "cohere.embed-multilingual-v3"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: BedrockCohereGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


@pytest.mark.parametrize(
    "caller_model",
    [
        "global.cohere.command-r-plus-v1:0",
        "us.cohere.command-r-v1:0",
        "eu.cohere.embed-english-v3",
        "ap.cohere.command-text-v14",
    ],
)
def test_grammar_passes_inference_profile_through_unchanged(
    grammar: BedrockCohereGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


@pytest.mark.parametrize(
    "caller_model",
    [
        "cohere.command-r-v1:0",
        "cohere.command-r-plus-v1:0",
        "cohere.embed-english-v3",
    ],
)
def test_grammar_passes_native_on_wire_through_unchanged(
    grammar: BedrockCohereGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


def test_grammar_rejects_non_string(grammar: BedrockCohereGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(42)  # type: ignore[arg-type]


def test_grammar_rejects_crlf_injection(grammar: BedrockCohereGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("cohere-command-r\r\nEvil: yes")


def test_grammar_rejects_null_byte(grammar: BedrockCohereGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("cohere-command-r\x00")


def test_grammar_rejects_oversized_input(grammar: BedrockCohereGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("cohere." + "x" * 200)


def test_grammar_rejects_unknown_caller_model(
    grammar: BedrockCohereGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_cohere_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_cross_family_passthrough(
    grammar: BedrockCohereGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_cohere_not_in_catalog"):
        grammar.resolve("anthropic.claude-3-opus-20240229-v1:0")


def test_grammar_kind_is_stable_literal(grammar: BedrockCohereGrammar) -> None:
    assert grammar.grammar_kind() == "bedrock_cohere"

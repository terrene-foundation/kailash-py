# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `BedrockMistralGrammar` (#498 Session 4, S4b-ii).

Distinct from Mistral-direct: Bedrock ships `mistral.*-v1:0` ids.
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.bedrock import BedrockMistralGrammar


@pytest.fixture
def grammar() -> BedrockMistralGrammar:
    return BedrockMistralGrammar()


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("mistral-7b", "mistral.mistral-7b-instruct-v0:2"),
        ("mixtral-8x7b", "mistral.mixtral-8x7b-instruct-v0:1"),
        ("mistral-small", "mistral.mistral-small-2402-v1:0"),
        ("mistral-large", "mistral.mistral-large-2402-v1:0"),
        ("mistral-large-2407", "mistral.mistral-large-2407-v1:0"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: BedrockMistralGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


@pytest.mark.parametrize(
    "caller_model",
    [
        "global.mistral.mistral-large-2402-v1:0",
        "us.mistral.mixtral-8x7b-instruct-v0:1",
        "eu.mistral.mistral-large-2407-v1:0",
        "ap.mistral.mistral-7b-instruct-v0:2",
    ],
)
def test_grammar_passes_inference_profile_through_unchanged(
    grammar: BedrockMistralGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


@pytest.mark.parametrize(
    "caller_model",
    [
        "mistral.mistral-large-2402-v1:0",
        "mistral.mixtral-8x7b-instruct-v0:1",
        "mistral.mistral-7b-instruct-v0:2",
    ],
)
def test_grammar_passes_native_on_wire_through_unchanged(
    grammar: BedrockMistralGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


def test_grammar_rejects_non_string(grammar: BedrockMistralGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve({})  # type: ignore[arg-type]


def test_grammar_rejects_crlf_injection(grammar: BedrockMistralGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("mistral-large\r\nInjected: yes")


def test_grammar_rejects_null_byte(grammar: BedrockMistralGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("mistral-large\x00")


def test_grammar_rejects_oversized_input(grammar: BedrockMistralGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("mistral." + "x" * 200)


def test_grammar_rejects_unknown_caller_model(
    grammar: BedrockMistralGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_mistral_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_cross_family_passthrough(
    grammar: BedrockMistralGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_mistral_not_in_catalog"):
        grammar.resolve("meta.llama3-1-70b-instruct-v1:0")


def test_grammar_kind_is_stable_literal(grammar: BedrockMistralGrammar) -> None:
    assert grammar.grammar_kind() == "bedrock_mistral"

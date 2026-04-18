# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AzureOpenAIGrammar unit tests (#498 S6)."""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.azure_openai import AzureOpenAIGrammar


@pytest.fixture
def grammar() -> AzureOpenAIGrammar:
    return AzureOpenAIGrammar()


@pytest.mark.parametrize(
    "deployment_name",
    [
        "gpt-4o",
        "gpt-4o-prod",
        "my_deployment_1",
        "production-model",
        "test-2025-01-15",
        "a",  # 1 char ok
        "z" * 64,  # 64 chars ok
    ],
)
def test_grammar_accepts_valid_deployment_name(
    grammar: AzureOpenAIGrammar, deployment_name: str
) -> None:
    assert grammar.resolve(deployment_name) == deployment_name


@pytest.mark.parametrize(
    "bad_name",
    [
        "",  # empty
        "z" * 65,  # too long
        "has space",  # whitespace
        "has.dot",  # dot not allowed
        "has/slash",  # slash not allowed
        "has\r\ninjection",  # CRLF
        "has\x00null",  # null byte
        "has:colon",  # colon not allowed
    ],
)
def test_grammar_rejects_invalid_deployment_name(
    grammar: AzureOpenAIGrammar, bad_name: str
) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve(bad_name)


def test_grammar_kind_stable_literal(grammar: AzureOpenAIGrammar) -> None:
    assert grammar.grammar_kind() == "azure_openai"


def test_grammar_rejects_non_string(grammar: AzureOpenAIGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid):
        grammar.resolve(12345)  # type: ignore[arg-type]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `BedrockLlamaGrammar` (#498 Session 4, S4b-ii).

Covers the same shape as `test_bedrock_claude_grammar.py`:

* Short-alias mapping for every Llama family (3.0, 3.1, 3.2, 3.3)
* Inference-profile passthrough (global.meta.*, us.meta.*, eu.meta.*, ap.meta.*)
* Native on-wire passthrough (meta.*)
* Regex gate rejects CRLF, null, control chars, non-strings, oversized
* Unknown models raise `ModelGrammarInvalid(reason=bedrock_llama_not_in_catalog)`
* `grammar_kind()` == "bedrock_llama" (cross-SDK parity)
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import ModelGrammarInvalid
from kaizen.llm.grammar.bedrock import BedrockLlamaGrammar


@pytest.fixture
def grammar() -> BedrockLlamaGrammar:
    return BedrockLlamaGrammar()


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("llama-3-8b", "meta.llama3-8b-instruct-v1:0"),
        ("llama-3-70b", "meta.llama3-70b-instruct-v1:0"),
        ("llama-3.1-8b", "meta.llama3-1-8b-instruct-v1:0"),
        ("llama-3.1-70b", "meta.llama3-1-70b-instruct-v1:0"),
        ("llama-3.1-405b", "meta.llama3-1-405b-instruct-v1:0"),
        ("llama-3.2-1b", "meta.llama3-2-1b-instruct-v1:0"),
        ("llama-3.2-3b", "meta.llama3-2-3b-instruct-v1:0"),
        ("llama-3.2-11b", "meta.llama3-2-11b-instruct-v1:0"),
        ("llama-3.2-90b", "meta.llama3-2-90b-instruct-v1:0"),
        ("llama-3.3-70b", "meta.llama3-3-70b-instruct-v1:0"),
    ],
)
def test_grammar_resolves_short_alias(
    grammar: BedrockLlamaGrammar, alias: str, expected: str
) -> None:
    assert grammar.resolve(alias) == expected


@pytest.mark.parametrize(
    "caller_model",
    [
        "global.meta.llama3-1-70b-instruct-v1:0",
        "us.meta.llama3-2-11b-instruct-v1:0",
        "eu.meta.llama3-3-70b-instruct-v1:0",
        "ap.meta.llama3-1-405b-instruct-v1:0",
    ],
)
def test_grammar_passes_inference_profile_through_unchanged(
    grammar: BedrockLlamaGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


@pytest.mark.parametrize(
    "caller_model",
    [
        "meta.llama3-8b-instruct-v1:0",
        "meta.llama3-1-70b-instruct-v1:0",
        "meta.llama3-3-70b-instruct-v1:0",
    ],
)
def test_grammar_passes_native_on_wire_through_unchanged(
    grammar: BedrockLlamaGrammar, caller_model: str
) -> None:
    assert grammar.resolve(caller_model) == caller_model


def test_grammar_rejects_non_string(grammar: BedrockLlamaGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"caller_model_not_string"):
        grammar.resolve(12345)  # type: ignore[arg-type]


def test_grammar_rejects_crlf_injection(grammar: BedrockLlamaGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("llama-3.1-70b\r\nX-Evil: yes")


def test_grammar_rejects_null_byte(grammar: BedrockLlamaGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("llama-3.1-70b\x00")


def test_grammar_rejects_oversized_input(grammar: BedrockLlamaGrammar) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"regex"):
        grammar.resolve("meta." + "x" * 200)


def test_grammar_rejects_unknown_caller_model(
    grammar: BedrockLlamaGrammar,
) -> None:
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_llama_not_in_catalog"):
        grammar.resolve("gpt-4o-mini")


def test_grammar_rejects_anthropic_passthrough_under_llama(
    grammar: BedrockLlamaGrammar,
) -> None:
    """A Claude on-wire id passed to the Llama grammar must reject --
    cross-family mixing is not a passthrough path.
    """
    with pytest.raises(ModelGrammarInvalid, match=r"bedrock_llama_not_in_catalog"):
        grammar.resolve("anthropic.claude-3-opus-20240229-v1:0")


def test_grammar_kind_is_stable_literal(grammar: BedrockLlamaGrammar) -> None:
    assert grammar.grammar_kind() == "bedrock_llama"

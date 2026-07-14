# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: OpenAI GPT-5 / o-series require `max_completion_tokens`, not
`max_tokens` (verified live 2026-07-14 — `gpt-5.6-sol` returns HTTP 400 on
`max_tokens`). OpenAI-compatible providers (DeepSeek, Groq, ...) keep
`max_tokens`. The openai_chat shaper picks the field by model family.
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import openai_chat


def _req(model: str) -> CompletionRequest:
    return CompletionRequest(
        model=model,
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=16,
    )


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5",
        "gpt-5-mini",
        "gpt-5.6-sol",
        "o1",
        "o1-mini",
        "o3",
        "o3-mini",
        "o4-mini",
    ],
)
def test_gpt5_and_o_series_emit_max_completion_tokens(model: str) -> None:
    payload = openai_chat.build_request_payload(_req(model))
    assert payload["max_completion_tokens"] == 16
    assert "max_tokens" not in payload


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "deepseek-chat",  # OpenAI-compatible provider — verified live with max_tokens
        "llama-3.1-70b",
        "mixtral-8x7b",
    ],
)
def test_gpt4_and_compatible_providers_keep_max_tokens(model: str) -> None:
    payload = openai_chat.build_request_payload(_req(model))
    assert payload["max_tokens"] == 16
    assert "max_completion_tokens" not in payload


def test_token_limit_field_selector() -> None:
    assert openai_chat._token_limit_field("gpt-5.6-sol") == "max_completion_tokens"
    assert openai_chat._token_limit_field("o1-preview") == "max_completion_tokens"
    assert openai_chat._token_limit_field("gpt-4o") == "max_tokens"
    assert openai_chat._token_limit_field("deepseek-chat") == "max_tokens"
    assert openai_chat._token_limit_field("") == "max_tokens"


def test_no_token_field_when_max_tokens_unset() -> None:
    req = CompletionRequest(model="gpt-5", messages=[{"role": "user", "content": "hi"}])
    payload = openai_chat.build_request_payload(req)
    assert "max_tokens" not in payload
    assert "max_completion_tokens" not in payload

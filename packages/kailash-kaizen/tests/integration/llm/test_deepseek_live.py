# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-3 LIVE verification of DeepSeek chat + streaming (issue #1609 AC 4).

Real API, NO mocking (per `rules/testing.md` Tier 2/3). DeepSeek is
OpenAI-compatible, so the live chat/stream path runs through the framework's
`OpenAIProvider` pointed at the DeepSeek endpoint — the same wire schema
(`WireProtocol.OpenAiChat`) the `deepseek_preset` / `LlmProvider` describe.
(`LlmClient.complete()` is still stubbed — see `test_llmclient_openai_wiring.py`
— so provider-level chat is the current live surface.)

**Key-gated skip (test-skip-discipline):** this test is SKIPPED — never faked —
when `DEEPSEEK_API_KEY` is absent. An absent credential is an "unable to
execute" skip, NOT a broken system. Both the endpoint (`base_url`) and the
model come from the framework / environment; nothing is hardcoded
(`rules/env-models.md`).
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm import LlmProvider
from kaizen.providers.llm.openai import OpenAIProvider


def _deepseek_model() -> str:
    """Resolve the DeepSeek model from env (no hardcoded model name)."""
    for var in ("DEEPSEEK_PROD_MODEL", "DEEPSEEK_MODEL"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    pytest.skip(
        "DEEPSEEK_PROD_MODEL / DEEPSEEK_MODEL not set; live DeepSeek test "
        "needs a model from .env (rules/env-models.md — no hardcoded model)."
    )


def _deepseek_credentials() -> tuple[str, str, str]:
    """Return (api_key, base_url, model) or skip when the credential is absent."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        pytest.skip(
            "DEEPSEEK_API_KEY not set; live chat + streaming verification is "
            "pending the credential (unable-to-execute skip, not a failure)."
        )
    # base_url derived from the framework provider metadata + the preset's
    # OpenAI-compatible `/v1` path prefix — not a hardcoded literal.
    base_url = LlmProvider.from_name("deepseek").base_url + "/v1"
    return api_key, base_url, _deepseek_model()


@pytest.mark.integration_llm
def test_deepseek_live_chat() -> None:
    """A real DeepSeek chat completion returns non-empty content."""
    api_key, base_url, model = _deepseek_credentials()

    provider = OpenAIProvider()
    result = provider.chat(
        [{"role": "user", "content": "Reply with exactly the word: ok"}],
        model=model,
        api_key=api_key,
        base_url=base_url,
        generation_config={"max_completion_tokens": 8, "temperature": 0.0},
    )

    assert isinstance(result, dict)
    assert result["content"], "DeepSeek returned empty chat content"
    assert result["finish_reason"] is not None
    assert result["usage"]["total_tokens"] > 0


@pytest.mark.integration_llm
@pytest.mark.asyncio
async def test_deepseek_live_streaming() -> None:
    """A real DeepSeek streaming completion emits deltas + a terminal event."""
    api_key, base_url, model = _deepseek_credentials()

    provider = OpenAIProvider(use_async=True)
    deltas: list[str] = []
    done_seen = False
    accumulated = ""

    async for event in provider.stream_chat(
        [{"role": "user", "content": "Count: one two three"}],
        model=model,
        api_key=api_key,
        base_url=base_url,
        generation_config={"max_completion_tokens": 16, "temperature": 0.0},
    ):
        if event.event_type == "text_delta":
            deltas.append(event.delta_text)
            accumulated = event.content
        elif event.event_type == "done":
            done_seen = True
            assert event.finish_reason is not None

    assert done_seen, "streaming never emitted a terminal 'done' event"
    assert any(d for d in deltas), "streaming produced no text deltas"
    assert accumulated, "streaming accumulated no content"

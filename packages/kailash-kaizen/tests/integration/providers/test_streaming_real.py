# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration tests for SPEC-02 real streaming providers.

These tests make genuine API calls to each provider's streaming endpoint
using keys read from ``.env``. When a key is absent, the corresponding
test ``pytest.skip``s — this is the standard Tier 2 pattern for optional
real-infrastructure tests (real code path, no mocks).

Environment variables consumed (never hardcoded — see rules/env-models.md):

- ``OPENAI_API_KEY`` + ``OPENAI_DEV_MODEL`` or ``DEFAULT_LLM_MODEL``
- ``ANTHROPIC_API_KEY`` + ``ANTHROPIC_DEV_MODEL``
- ``GOOGLE_API_KEY`` (or ``GEMINI_API_KEY``) + ``GOOGLE_DEV_MODEL``
- ``OLLAMA_BASE_URL`` or ``OLLAMA_HOST`` (local service) + ``OLLAMA_MODEL``

Every test asserts the real-streaming contract:

1. The call returns an async generator (not a coroutine that awaits a
   single yield).
2. At least 2 distinct ``text_delta`` events arrive — the hallmark of
   genuine per-token streaming.
3. Exactly one ``done`` event arrives at the end.
4. The accumulated text in the final ``done`` event equals the sum of
   every incremental ``delta_text``.
"""

from __future__ import annotations

import os

import pytest

from kaizen.providers.llm.anthropic import AnthropicProvider
from kaizen.providers.llm.google import GoogleGeminiProvider
from kaizen.providers.llm.ollama import OllamaProvider
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.types import StreamEvent


def _require_env(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        pytest.skip(f"{var_name} not set — skipping real streaming integration test")
    return value


async def _collect_stream_events(agen) -> list[StreamEvent]:
    events: list[StreamEvent] = []
    async for event in agen:
        events.append(event)
    return events


def _assert_real_streaming_contract(events: list[StreamEvent]) -> None:
    """Every real stream MUST satisfy these invariants."""
    text_events = [e for e in events if e.event_type == "text_delta"]
    done_events = [e for e in events if e.event_type == "done"]

    assert (
        len(text_events) >= 2
    ), f"real stream_chat must yield >=2 distinct text chunks, got {len(text_events)}"
    assert len(done_events) == 1, "expected exactly one done event"

    accumulated_from_deltas = "".join(e.delta_text for e in text_events)
    final_content = text_events[-1].content
    assert (
        accumulated_from_deltas == final_content
    ), "delta_text concatenation must equal the last content snapshot"
    assert (
        done_events[0].content == final_content
    ), "done event content must equal accumulated text"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_streaming_yields_real_chunks():
    _require_env("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_DEV_MODEL") or os.environ.get("DEFAULT_LLM_MODEL")
    if not model:
        pytest.skip("OPENAI_DEV_MODEL / DEFAULT_LLM_MODEL not set")

    provider = OpenAIProvider()
    events = await _collect_stream_events(
        provider.stream_chat(
            [
                {
                    "role": "user",
                    "content": "Count from one to ten in English, one number per line.",
                }
            ],
            model=model,
            generation_config={"max_tokens": 80, "temperature": 0.0},
        )
    )
    _assert_real_streaming_contract(events)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_streaming_yields_real_chunks():
    _require_env("ANTHROPIC_API_KEY")
    model = os.environ.get("ANTHROPIC_DEV_MODEL")
    if not model:
        pytest.skip("ANTHROPIC_DEV_MODEL not set")

    provider = AnthropicProvider()
    events = await _collect_stream_events(
        provider.stream_chat(
            [
                {
                    "role": "user",
                    "content": "Count from one to ten in English, one number per line.",
                }
            ],
            model=model,
            generation_config={"max_tokens": 80, "temperature": 0.0},
        )
    )
    _assert_real_streaming_contract(events)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_google_gemini_streaming_yields_real_chunks():
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip(
            "GOOGLE_API_KEY / GEMINI_API_KEY not set — skipping real streaming test"
        )
    model = os.environ.get("GOOGLE_DEV_MODEL")
    if not model:
        pytest.skip("GOOGLE_DEV_MODEL not set")

    provider = GoogleGeminiProvider()
    events = await _collect_stream_events(
        provider.stream_chat(
            [
                {
                    "role": "user",
                    "content": "Count from one to ten in English, one number per line.",
                }
            ],
            model=model,
            generation_config={"max_tokens": 80, "temperature": 0.0},
        )
    )
    _assert_real_streaming_contract(events)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ollama_streaming_yields_real_chunks():
    # Ollama is a local service — test runs only when the service is
    # explicitly declared via OLLAMA_BASE_URL / OLLAMA_HOST.
    host = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST")
    if not host:
        pytest.skip(
            "OLLAMA_BASE_URL / OLLAMA_HOST not set — skipping local streaming test"
        )
    model = os.environ.get("OLLAMA_MODEL")
    if not model:
        pytest.skip("OLLAMA_MODEL not set")

    provider = OllamaProvider()
    if not provider.is_available():
        pytest.skip("Ollama service not reachable — skipping local streaming test")

    events = await _collect_stream_events(
        provider.stream_chat(
            [
                {
                    "role": "user",
                    "content": "Count from one to ten in English, one number per line.",
                }
            ],
            model=model,
            generation_config={"max_tokens": 80, "temperature": 0.0},
        )
    )
    _assert_real_streaming_contract(events)

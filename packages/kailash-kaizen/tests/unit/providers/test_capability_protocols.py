# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for SPEC-02 capability protocols.

Covers:
- ``ProviderCapability`` enum taxonomy is intact.
- The 5 capability protocols are importable.
- Every concrete LLM provider exposes ``stream_chat``, ``capabilities``,
  and ``name`` as required by the :class:`StreamingProvider` contract.
- :class:`MockProvider` satisfies the :class:`StreamingProvider` protocol
  structurally and yields at least two distinct text chunks from a simple
  prompt (the real-streaming contract the StreamingAgent depends on).
- :func:`get_provider_for_model` dispatches correctly via the declared
  prefix table and raises :class:`UnknownProviderError` on unknown models.

These tests are Tier 1 — mocks permitted, no real API calls. Tier 2
integration tests (real OpenAI / Anthropic / Google streaming) live in
``tests/integration/providers/test_streaming_real.py`` and skip when the
corresponding API key is absent from ``.env``.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from kaizen.providers.base import (
    AsyncLLMProvider,
    BaseProvider,
    ProviderCapability,
    StreamingProvider,
    StructuredOutputProvider,
    ToolCallingProvider,
)
from kaizen.providers.errors import UnknownProviderError
from kaizen.providers.llm.anthropic import AnthropicProvider
from kaizen.providers.llm.azure import AzureAIFoundryProvider
from kaizen.providers.llm.docker import DockerModelRunnerProvider
from kaizen.providers.llm.google import GoogleGeminiProvider
from kaizen.providers.llm.mock import MockProvider
from kaizen.providers.llm.ollama import OllamaProvider
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.llm.perplexity import PerplexityProvider
from kaizen.providers.registry import get_provider_for_model
from kaizen.providers.types import StreamEvent

# Every LLM provider class that MUST implement StreamingProvider.
ALL_LLM_PROVIDERS = [
    OpenAIProvider,
    AnthropicProvider,
    GoogleGeminiProvider,
    OllamaProvider,
    DockerModelRunnerProvider,
    PerplexityProvider,
    AzureAIFoundryProvider,
    MockProvider,
]


class TestProviderCapabilityEnum:
    """The ProviderCapability enum exposes the SPEC-02 taxonomy."""

    def test_enum_has_required_members(self):
        required = {
            "CHAT_SYNC",
            "CHAT_ASYNC",
            "CHAT_STREAM",
            "TOOLS",
            "STRUCTURED_OUTPUT",
            "EMBEDDINGS",
            "VISION",
            "AUDIO",
            "REASONING_MODELS",
            "BYOK",
        }
        present = {m.name for m in ProviderCapability}
        missing = required - present
        assert not missing, f"ProviderCapability missing members: {missing}"


class TestCapabilityProtocols:
    """The 5 capability protocols are importable and structurally usable."""

    def test_protocols_are_importable(self):
        # The import itself is half the test — if the symbols are missing,
        # the module fails to load before we get here.
        assert BaseProvider is not None
        assert AsyncLLMProvider is not None
        assert StreamingProvider is not None
        assert ToolCallingProvider is not None
        assert StructuredOutputProvider is not None

    def test_streaming_protocol_requires_stream_chat(self):
        # Protocol inspection — the StreamingProvider protocol defines
        # ``stream_chat`` as the structural marker method.
        assert hasattr(StreamingProvider, "stream_chat")

    def test_async_llm_protocol_requires_chat_async(self):
        assert hasattr(AsyncLLMProvider, "chat_async")


class TestLLMProviderCapabilityDeclaration:
    """Every concrete LLM provider declares the SPEC-02 contract."""

    @pytest.mark.parametrize("provider_cls", ALL_LLM_PROVIDERS)
    def test_provider_has_name_property(self, provider_cls):
        p = provider_cls()
        assert (
            isinstance(p.name, str) and p.name
        ), f"{provider_cls.__name__}.name must be a non-empty str"

    @pytest.mark.parametrize("provider_cls", ALL_LLM_PROVIDERS)
    def test_provider_has_capabilities_set(self, provider_cls):
        p = provider_cls()
        caps = p.capabilities
        assert isinstance(caps, set)
        assert all(isinstance(c, ProviderCapability) for c in caps)
        assert (
            ProviderCapability.CHAT_STREAM in caps
        ), f"{provider_cls.__name__} declares CHAT_STREAM because it ships a real stream_chat"

    @pytest.mark.parametrize("provider_cls", ALL_LLM_PROVIDERS)
    def test_provider_has_async_stream_chat(self, provider_cls):
        fn = getattr(provider_cls, "stream_chat", None)
        assert fn is not None, f"{provider_cls.__name__} missing stream_chat"
        # Must be an async generator function (the Protocol contract).
        assert inspect.isasyncgenfunction(
            fn
        ), f"{provider_cls.__name__}.stream_chat must be an async generator"

    @pytest.mark.parametrize("provider_cls", ALL_LLM_PROVIDERS)
    def test_provider_structurally_satisfies_streaming_protocol(self, provider_cls):
        p = provider_cls()
        assert isinstance(
            p, StreamingProvider
        ), f"{provider_cls.__name__} does not satisfy StreamingProvider"


class TestMockProviderStreamContract:
    """MockProvider is the test-path implementation of StreamingProvider.

    It is the ONE legitimate synthetic stream in the codebase — every
    other provider iterates the real SDK response.
    """

    def test_mock_yields_multiple_distinct_chunks(self):
        async def _run():
            provider = MockProvider()
            events: list[StreamEvent] = []
            async for event in provider.stream_chat(
                [
                    {
                        "role": "user",
                        "content": "Hello world. How are you today? This should split.",
                    }
                ]
            ):
                events.append(event)
            return events

        events = asyncio.run(_run())

        text_events = [e for e in events if e.event_type == "text_delta"]
        done_events = [e for e in events if e.event_type == "done"]

        assert (
            len(text_events) >= 2
        ), f"stream_chat must yield >=2 distinct text chunks, got {len(text_events)}"
        assert len(done_events) == 1, "stream_chat must yield exactly one done event"

        # Accumulated text in the final text_delta equals the done-event content.
        assert text_events[-1].content == done_events[0].content
        # Each delta_text is non-empty and distinct (the real-streaming contract).
        deltas = [e.delta_text for e in text_events]
        assert all(d for d in deltas), "every text_delta event must carry delta_text"
        # At least 2 distinct delta strings.
        assert len(set(deltas)) >= 2

    def test_mock_done_event_carries_finish_reason_and_usage(self):
        async def _run():
            provider = MockProvider()
            events: list[StreamEvent] = []
            async for event in provider.stream_chat(
                [{"role": "user", "content": "hello"}]
            ):
                events.append(event)
            return events

        events = asyncio.run(_run())
        done = events[-1]
        assert done.event_type == "done"
        assert done.finish_reason == "stop"
        assert isinstance(done.usage, dict)


class TestRegistryModelDispatch:
    """get_provider_for_model routes by declared prefix, not by semantics."""

    @pytest.mark.parametrize(
        "model, expected_name",
        [
            ("gpt-4o", "openai"),
            ("o4-mini", "openai"),
            ("o3", "openai"),
            ("claude-3-5-sonnet-latest", "anthropic"),
            ("gemini-2.0-flash", "google"),
            ("gemini-2.5-flash", "google"),
            ("llama3.1:8b-instruct-q8_0", "ollama"),
            ("mistral-small", "ollama"),
            ("ai/llama3.2", "docker"),
            ("sonar-pro", "perplexity"),
        ],
    )
    def test_model_prefix_dispatch(self, model: str, expected_name: str):
        provider = get_provider_for_model(model)
        assert provider.name == expected_name

    def test_mock_prefix_dispatches_to_mock_slot(self):
        # The global conftest may patch the ``mock`` slot with a test-only
        # subclass (KaizenMockProvider) that does not expose the SPEC-02
        # ``name`` property. Assert the dispatch succeeds and resolves to
        # the entry registered under ``mock`` — that's the structural
        # contract; the instance's own ``name`` is the class's concern.
        provider = get_provider_for_model("mock-model")
        # Must be the class currently registered under the ``mock`` key.
        from kaizen.providers.registry import PROVIDERS

        registered = PROVIDERS["mock"]
        # PROVIDERS stores either a class or a lazy-sentinel string; for
        # ``mock`` it is always a class.
        assert isinstance(provider, registered)  # type: ignore[arg-type]

    def test_unknown_model_raises_typed_error(self):
        with pytest.raises(UnknownProviderError):
            get_provider_for_model("xyz-model-that-does-not-exist-42")

    def test_empty_model_raises_typed_error(self):
        with pytest.raises(UnknownProviderError):
            get_provider_for_model("")

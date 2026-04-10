# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for the SPEC-02 provider registry.

Covers:
- ``PROVIDERS`` dict completeness and expected entries.
- ``get_provider`` by name (happy path + unknown + capability filter).
- ``get_provider_for_model`` prefix dispatch exhaustively.
- ``get_streaming_provider`` capability gating.
- ``get_available_providers`` returns structured info for every entry.
- Backward-compat: ``kaizen.nodes.ai.ai_providers`` re-exports match
  ``kaizen.providers.registry`` exports.
"""

from __future__ import annotations

import pytest

from kaizen.providers.base import StreamingProvider
from kaizen.providers.errors import CapabilityNotSupportedError, UnknownProviderError
from kaizen.providers.registry import (
    _MODEL_PREFIX_MAP,
    PROVIDERS,
    get_available_providers,
    get_provider,
    get_provider_for_model,
    get_streaming_provider,
)


class TestProvidersDict:
    """The PROVIDERS dict contains all expected entries."""

    EXPECTED_KEYS = {
        "ollama",
        "openai",
        "anthropic",
        "cohere",
        "huggingface",
        "mock",
        "azure",
        "azure_openai",
        "azure_ai_foundry",
        "docker",
        "google",
        "gemini",
        "perplexity",
        "pplx",
    }

    def test_all_expected_keys_present(self):
        assert self.EXPECTED_KEYS <= set(PROVIDERS.keys())

    def test_gemini_aliases_to_google(self):
        assert PROVIDERS["gemini"] is PROVIDERS["google"]

    def test_pplx_aliases_to_perplexity(self):
        assert PROVIDERS["pplx"] is PROVIDERS["perplexity"]

    def test_azure_is_lazy_sentinel(self):
        # Azure uses lazy import to avoid circular dependency.
        assert PROVIDERS["azure"] == "_unified_azure"

    def test_azure_openai_is_lazy_sentinel(self):
        assert PROVIDERS["azure_openai"] == "_unified_azure"


class TestGetProvider:
    """get_provider resolves names to instances."""

    def test_openai_by_name(self):
        from kaizen.providers.llm.openai import OpenAIProvider

        p = get_provider("openai")
        assert isinstance(p, OpenAIProvider)

    def test_anthropic_by_name(self):
        from kaizen.providers.llm.anthropic import AnthropicProvider

        p = get_provider("anthropic")
        assert isinstance(p, AnthropicProvider)

    def test_mock_by_name(self):
        p = get_provider("mock")
        # The conftest may patch the mock slot with KaizenMockProvider
        # (which lacks the SPEC-02 interface). Verify the instance is at
        # least the class registered under the "mock" key.
        assert isinstance(p, PROVIDERS["mock"])

    def test_case_insensitive(self):
        p1 = get_provider("OpenAI")
        p2 = get_provider("OPENAI")
        assert type(p1) is type(p2)

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent_provider_xyz")

    def test_chat_filter_rejects_embedding_only(self):
        with pytest.raises(ValueError, match="does not support chat"):
            get_provider("cohere", provider_type="chat")

    def test_embeddings_filter_rejects_chat_only(self):
        with pytest.raises(ValueError, match="does not support embedding"):
            get_provider("anthropic", provider_type="embeddings")

    def test_invalid_provider_type_raises(self):
        with pytest.raises(ValueError, match="Invalid provider_type"):
            get_provider("openai", provider_type="vision")


class TestGetProviderForModel:
    """get_provider_for_model dispatches via prefix table."""

    @pytest.mark.parametrize(
        "model, expected",
        [
            ("gpt-4o", "openai"),
            ("gpt-3.5-turbo", "openai"),
            ("o1-preview", "openai"),
            ("o3-mini", "openai"),
            ("o4-mini", "openai"),
            ("ft:gpt-3.5-turbo:org:custom:id", "openai"),
            ("claude-3-5-sonnet-latest", "anthropic"),
            ("claude-3-opus-20240229", "anthropic"),
            ("gemini-2.0-flash", "google"),
            ("gemini-2.5-pro", "google"),
            ("llama3.1:8b", "ollama"),
            ("mistral-7b", "ollama"),
            ("mixtral-8x7b", "ollama"),
            ("qwen2.5:14b", "ollama"),
            ("phi-3", "ollama"),
            ("deepseek-r1", "ollama"),
            ("ai/llama3.2", "docker"),
            ("sonar-pro", "perplexity"),
            ("sonar-small-chat", "perplexity"),
        ],
    )
    def test_model_prefix_dispatch(self, model: str, expected: str):
        p = get_provider_for_model(model)
        assert p.name == expected, f"model={model} got name={p.name}"

    def test_mock_prefix_dispatches(self):
        """Mock prefix resolves to whatever is registered under 'mock'."""
        p = get_provider_for_model("mock-model")
        assert isinstance(p, PROVIDERS["mock"])

    def test_empty_string_raises(self):
        with pytest.raises(UnknownProviderError):
            get_provider_for_model("")

    def test_none_raises(self):
        with pytest.raises(UnknownProviderError):
            get_provider_for_model(None)  # type: ignore[arg-type]

    def test_unknown_prefix_raises_typed_error(self):
        with pytest.raises(UnknownProviderError, match="Cannot detect provider"):
            get_provider_for_model("xyz-totally-unknown-model-999")

    def test_prefix_table_has_no_duplicate_prefixes(self):
        """No two provider rows share the same prefix string."""
        all_prefixes: list[str] = []
        for prefixes, _name in _MODEL_PREFIX_MAP:
            all_prefixes.extend(prefixes)
        assert len(all_prefixes) == len(
            set(all_prefixes)
        ), "Duplicate prefix in _MODEL_PREFIX_MAP"


class TestGetStreamingProvider:
    """get_streaming_provider gates on StreamingProvider protocol."""

    def test_openai_is_streaming(self):
        p = get_streaming_provider("openai")
        assert isinstance(p, StreamingProvider)

    def test_mock_is_streaming_when_unpatched(self):
        """MockProvider satisfies StreamingProvider when not patched by conftest."""
        from kaizen.providers.llm.mock import MockProvider

        # The conftest may replace PROVIDERS["mock"] with KaizenMockProvider
        # which doesn't implement stream_chat. Test the real MockProvider directly.
        p = MockProvider()
        assert isinstance(p, StreamingProvider)

    def test_model_string_resolves_and_checks(self):
        p = get_streaming_provider("gpt-4o")
        assert isinstance(p, StreamingProvider)

    def test_non_streaming_raises_capability_error(self):
        """Embedding-only providers do not satisfy StreamingProvider."""
        with pytest.raises(
            CapabilityNotSupportedError, match="does not support streaming"
        ):
            get_streaming_provider("cohere")


class TestGetAvailableProviders:
    """get_available_providers returns structured info."""

    def test_returns_dict(self):
        result = get_available_providers()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_each_entry_has_expected_keys(self):
        result = get_available_providers()
        for name, info in result.items():
            assert "available" in info, f"{name} missing 'available'"
            assert "chat" in info, f"{name} missing 'chat'"
            assert "embeddings" in info, f"{name} missing 'embeddings'"

    def test_chat_filter_excludes_embedding_only(self):
        result = get_available_providers(provider_type="chat")
        for name, info in result.items():
            # Providers that errored out during availability check may have
            # chat=False in the error branch — only assert on non-errored.
            if "error" not in info:
                assert info.get("chat", False), f"{name} should support chat"

    def test_embeddings_filter_excludes_chat_only(self):
        result = get_available_providers(provider_type="embeddings")
        for name, info in result.items():
            if "error" not in info:
                assert info.get(
                    "embeddings", False
                ), f"{name} should support embeddings"


class TestBackwardCompatShim:
    """kaizen.nodes.ai.ai_providers re-exports match kaizen.providers.registry."""

    def test_providers_dict_is_same_object(self):
        from kaizen.nodes.ai.ai_providers import PROVIDERS as OLD_PROVIDERS

        assert OLD_PROVIDERS is PROVIDERS

    def test_get_provider_is_same_function(self):
        from kaizen.nodes.ai.ai_providers import get_provider as old_get_provider

        assert old_get_provider is get_provider

    def test_get_available_providers_is_same_function(self):
        from kaizen.nodes.ai.ai_providers import (
            get_available_providers as old_get_available,
        )

        assert old_get_available is get_available_providers

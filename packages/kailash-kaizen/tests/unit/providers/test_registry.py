# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for the SPEC-02 provider registry (post #1720 Wave-2).

The seven legacy chat providers (openai / anthropic / google / ollama / docker /
perplexity / mock) were RETIRED onto the four-axis LlmClient in #1720 Wave-2 and
their registry entries pruned. ``PROVIDERS`` now holds only the surviving
providers (``cohere`` / ``huggingface`` embedding + ``azure`` / ``azure_openai``
/ ``azure_ai_foundry`` unified-azure). Registry model-id dispatch
(``get_provider_for_model``) is RETIRED and raises for every input — model-id ->
wire dispatch lives in ``kaizen.llm.deployment_resolver``. The model-family
prefix CLASSIFICATION table stays complete in
``kaizen.providers.provider_names`` (metrics label bounding), decoupled from the
pruned registry (registry asserts ``PROVIDERS.keys() <= PROVIDER_NAMES``).

Covers the surviving registry surface:
- ``PROVIDERS`` contains the surviving entries and none of the retired ones.
- ``get_provider`` capability filtering + typed errors.
- ``get_provider_for_model`` now raises ``UnknownProviderError`` for every model
  (dispatch retired).
- ``get_streaming_provider`` capability gating (embedding-only rejection).
- ``get_available_providers`` structured info.
- Backward-compat: ``kaizen.providers`` re-exports match
  ``kaizen.providers.registry`` exports (via the deprecation shim).
"""

from __future__ import annotations

import pytest

from kaizen.providers.errors import CapabilityNotSupportedError, UnknownProviderError
from kaizen.providers.registry import (
    PROVIDERS,
    get_available_providers,
    get_provider,
    get_provider_for_model,
    get_streaming_provider,
)

# The seven chat providers retired + removed from the registry in #1720 Wave-2.
_RETIRED_CHAT_PROVIDERS = {
    "openai",
    "anthropic",
    "google",
    "gemini",
    "ollama",
    "docker",
    "perplexity",
    "pplx",
}


class TestProvidersDict:
    """The PROVIDERS dict contains the surviving entries only."""

    EXPECTED_KEYS = {
        "cohere",
        "huggingface",
        "azure",
        "azure_openai",
        "azure_ai_foundry",
    }

    def test_all_expected_keys_present(self):
        assert self.EXPECTED_KEYS <= set(PROVIDERS.keys())

    def test_retired_chat_providers_absent(self):
        """None of the seven retired chat providers remain registered."""
        assert not (_RETIRED_CHAT_PROVIDERS & set(PROVIDERS.keys()))

    def test_azure_is_lazy_sentinel(self):
        # Azure uses lazy import to avoid circular dependency.
        assert PROVIDERS["azure"] == "_unified_azure"

    def test_azure_openai_is_lazy_sentinel(self):
        assert PROVIDERS["azure_openai"] == "_unified_azure"


class TestGetProvider:
    """get_provider resolves names to instances + enforces capability filters."""

    def test_case_insensitive(self):
        p1 = get_provider("Cohere")
        p2 = get_provider("COHERE")
        assert type(p1) is type(p2)

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent_provider_xyz")

    def test_chat_filter_rejects_embedding_only(self):
        with pytest.raises(ValueError, match="does not support chat"):
            get_provider("cohere", provider_type="chat")

    def test_invalid_provider_type_raises(self):
        with pytest.raises(ValueError, match="Invalid provider_type"):
            get_provider("cohere", provider_type="vision")


class TestGetProviderForModel:
    """get_provider_for_model — RETIRED in #1720 Wave-2, raises for every input.

    Registry model-id dispatch was retired with the chat providers; model-id ->
    wire dispatch now lives in ``kaizen.llm.deployment_resolver``. The function
    is kept as a typed, named failure (not a silent ``None``) so any lingering
    caller fails loudly with a pointer to the four-axis path. The model-family
    prefix CLASSIFICATION table (``MODEL_PREFIX_MAP``, for metrics labels) lives
    in ``kaizen.providers.provider_names`` and is covered by
    ``tests/regression/test_issue_1720_b2b_name_registry.py``.
    """

    @pytest.mark.parametrize(
        "model",
        [
            "gpt-4o",
            "claude-3-5-sonnet-latest",
            "gemini-2.0-flash",
            "llama3.1:8b",
            "ai/llama3.2",
            "sonar-pro",
        ],
    )
    def test_retired_model_prefixes_now_raise(self, model: str):
        """Every model that used to dispatch to a retired chat provider now
        raises — registry model-id dispatch was retired."""
        with pytest.raises(UnknownProviderError):
            get_provider_for_model(model)

    def test_empty_string_raises(self):
        with pytest.raises(UnknownProviderError):
            get_provider_for_model("")

    def test_none_raises(self):
        with pytest.raises(UnknownProviderError):
            get_provider_for_model(None)  # type: ignore[arg-type]

    def test_unknown_prefix_raises_typed_error(self):
        with pytest.raises(UnknownProviderError, match="Cannot detect provider"):
            get_provider_for_model("xyz-totally-unknown-model-999")

    def test_dispatch_is_retired_for_a_surviving_family_prefix_too(self):
        """Even a still-classified family prefix (openai/gpt) does NOT resolve —
        the registry no longer dispatches by model id at all (the family label
        survives only for metrics, not for provider construction)."""
        with pytest.raises(UnknownProviderError, match="retired"):
            get_provider_for_model("gpt-4o")


class TestGetStreamingProvider:
    """get_streaming_provider gates on StreamingProvider protocol."""

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
    """kaizen.providers re-exports match kaizen.providers.registry.

    These accessors remain on the PEP 562 deprecation shim (Wave-C removes
    them), so importing them via the ``kaizen.providers`` barrel warns AND
    resolves the same object — both halves are asserted here.
    """

    def test_providers_dict_is_same_object(self):
        with pytest.warns(DeprecationWarning, match=r"#1720"):
            from kaizen.providers import PROVIDERS as OLD_PROVIDERS

        assert OLD_PROVIDERS is PROVIDERS

    def test_get_provider_is_same_function(self):
        with pytest.warns(DeprecationWarning, match=r"#1720"):
            from kaizen.providers import get_provider as old_get_provider

        assert old_get_provider is get_provider

    def test_get_available_providers_is_same_function(self):
        with pytest.warns(DeprecationWarning, match=r"#1720"):
            from kaizen.providers import get_available_providers as old_get_available

        assert old_get_available is get_available_providers

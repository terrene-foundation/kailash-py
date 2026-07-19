# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for the SPEC-02 provider registry (post #1820).

The seven legacy chat providers (openai / anthropic / google / ollama / docker /
perplexity / mock) were RETIRED onto the four-axis LlmClient in #1720 Wave-2.
#1820 then RETIRED the embedding-legacy providers (``cohere`` / ``huggingface``)
and the unified-azure providers (``azure`` / ``azure_openai``) and DELETED their
modules — their transports are served end-to-end by the four-axis path
(``kaizen.llm.deployment_resolver.resolve_deployment_for`` +
``LlmClient.embed`` / ``complete``), which is consulted BEFORE this registry in
every live caller. ``PROVIDERS`` now holds ONLY ``azure_ai_foundry`` — the one
KNOWN provider ``resolve_deployment_for`` declines to map (no confirmed
four-axis wire), so it stays as the registry's legacy fallback.

Registry model-id dispatch (``get_provider_for_model``) is RETIRED and raises
for every input — model-id -> wire dispatch lives in
``kaizen.llm.deployment_resolver``.

Covers the surviving registry surface:
- ``PROVIDERS`` contains ONLY ``azure_ai_foundry``; every retired name is absent.
- The four retired #1820 keys (cohere / huggingface / azure / azure_openai) now
  resolve through the four-axis ``resolve_deployment_for`` path instead.
- ``get_provider`` capability filtering + typed errors on the surviving provider.
- ``get_provider_for_model`` raises ``UnknownProviderError`` for every model.
- ``get_streaming_provider`` capability gating.
- ``get_available_providers`` structured info.
- Backward-compat: ``kaizen.providers`` re-exports the registry accessors (via
  the deprecation shim).
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment_resolver import (
    UnsupportedDeploymentProvider,
    resolve_deployment_for,
)
from kaizen.providers.errors import CapabilityNotSupportedError, UnknownProviderError
from kaizen.providers.llm.azure import AzureAIFoundryProvider
from kaizen.providers.registry import (
    PROVIDERS,
    get_available_providers,
    get_provider,
    get_provider_for_model,
    get_streaming_provider,
)

# The seven chat providers retired in #1720 Wave-2 + the four embedding-legacy /
# unified-azure providers retired in #1820 — none remain in the registry.
_RETIRED_PROVIDERS = {
    # #1720 Wave-2 chat providers
    "openai",
    "anthropic",
    "google",
    "gemini",
    "ollama",
    "docker",
    "perplexity",
    "pplx",
    # #1820 embedding-legacy + unified-azure providers (now four-axis served)
    "cohere",
    "huggingface",
    "azure",
    "azure_openai",
}

# The four #1820 keys whose transports moved to the four-axis path. Each must now
# resolve through resolve_deployment_for (NOT the registry).
_FOUR_AXIS_KEYS = ("cohere", "huggingface", "azure", "azure_openai")


# tests/conftest.py (module scope) rebinds ``PROVIDERS["mock"] = KaizenMockProvider``
# for unit tests (unless USE_REAL_PROVIDERS=true), so under the harness a spurious
# ``"mock"`` key is present. It is a harness artifact, NOT a real registry member —
# in a clean interpreter ``PROVIDERS`` is ``{"azure_ai_foundry"}`` only. Exclude it
# from the exact-contents assertion (mirrors the barrel test's
# ``_PROVIDERS_CONFTEST_PATCHED`` carve-out).
_HARNESS_INJECTED_KEYS = {"mock"}


class TestProvidersDict:
    """The PROVIDERS dict contains ONLY the surviving azure_ai_foundry entry."""

    def test_only_azure_ai_foundry_remains(self):
        assert set(PROVIDERS.keys()) - _HARNESS_INJECTED_KEYS == {"azure_ai_foundry"}

    def test_azure_ai_foundry_resolves_to_the_kept_class(self):
        assert PROVIDERS["azure_ai_foundry"] is AzureAIFoundryProvider

    def test_retired_providers_absent(self):
        """None of the retired chat / embedding / unified-azure names remain."""
        assert not (_RETIRED_PROVIDERS & set(PROVIDERS.keys()))

    def test_no_string_sentinels_remain(self):
        """The '_unified_azure' lazy-string sentinel routing was removed."""
        assert all(isinstance(v, type) for v in PROVIDERS.values())


class TestFourAxisRoutingForRetiredKeys:
    """The four #1820 keys route to the four-axis path, not the registry."""

    def test_retired_keys_not_in_registry(self):
        for key in _FOUR_AXIS_KEYS:
            assert key not in PROVIDERS
            with pytest.raises(ValueError, match="Unknown provider"):
                get_provider(key)

    def test_cohere_resolves_via_four_axis(self):
        deployment = resolve_deployment_for("cohere", "embed-english-v3.0", api_key="k")
        assert deployment is not None

    def test_huggingface_resolves_via_four_axis(self):
        deployment = resolve_deployment_for(
            "huggingface", "sentence-transformers/all-MiniLM-L6-v2", api_key="k"
        )
        assert deployment is not None

    @pytest.mark.parametrize("provider", ["azure", "azure_openai"])
    def test_azure_resolves_via_four_axis(self, provider):
        deployment = resolve_deployment_for(
            provider,
            "test-deployment",
            api_key="k",
            base_url="https://test.openai.azure.com",
        )
        assert deployment is not None

    def test_azure_ai_foundry_declines_four_axis_and_stays_registry(self):
        """azure_ai_foundry has no four-axis wire (raises), and resolves to the
        kept AzureAIFoundryProvider via the registry — the deliberate fallback."""
        with pytest.raises(UnsupportedDeploymentProvider):
            resolve_deployment_for("azure_ai_foundry", "gpt-4o")
        provider = get_provider("azure_ai_foundry")
        assert isinstance(provider, AzureAIFoundryProvider)


class TestGetProvider:
    """get_provider resolves the surviving name + enforces capability filters."""

    def test_case_insensitive(self):
        p1 = get_provider("Azure_AI_Foundry")
        p2 = get_provider("AZURE_AI_FOUNDRY")
        assert type(p1) is type(p2)

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent_provider_xyz")

    def test_chat_filter_accepts_azure_ai_foundry(self):
        # azure_ai_foundry supports both chat and embeddings; both filters pass.
        assert isinstance(
            get_provider("azure_ai_foundry", "chat"), AzureAIFoundryProvider
        )

    def test_embeddings_filter_accepts_azure_ai_foundry(self):
        assert isinstance(
            get_provider("azure_ai_foundry", "embeddings"), AzureAIFoundryProvider
        )

    def test_invalid_provider_type_raises(self):
        with pytest.raises(ValueError, match="Invalid provider_type"):
            get_provider("azure_ai_foundry", provider_type="vision")


class TestGetProviderForModel:
    """get_provider_for_model — RETIRED, raises for every input.

    Registry model-id dispatch was retired with the chat providers; model-id ->
    wire dispatch now lives in ``kaizen.llm.deployment_resolver``.
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
        with pytest.raises(UnknownProviderError, match="retired"):
            get_provider_for_model("gpt-4o")


class TestGetStreamingProvider:
    """get_streaming_provider gates on the StreamingProvider protocol."""

    def test_azure_ai_foundry_is_a_streaming_provider(self):
        # AzureAIFoundryProvider declares CHAT_STREAM + implements stream_chat.
        provider = get_streaming_provider("azure_ai_foundry")
        assert isinstance(provider, AzureAIFoundryProvider)

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_streaming_provider("nonexistent_provider_xyz")


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


class TestBackwardCompatShim:
    """kaizen.providers re-exports the registry accessors (still shimmed).

    The registry accessors (``PROVIDERS`` / ``get_provider`` /
    ``get_available_providers``) remain on the PEP 562 deprecation shim; importing
    them via the ``kaizen.providers`` barrel warns AND resolves the same object.
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

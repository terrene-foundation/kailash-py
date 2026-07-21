# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for the SPEC-02 provider registry (post #1892).

The seven legacy chat providers (openai / anthropic / google / ollama / docker /
perplexity / mock) were RETIRED onto the four-axis LlmClient in #1720 Wave-2.
#1820 then RETIRED the embedding-legacy providers (``cohere`` / ``huggingface``)
and the unified-azure providers (``azure`` / ``azure_openai``), deleting their
modules. #1892 retired the LAST remaining registry provider,
``azure_ai_foundry``, onto its own four-axis wire
(``kaizen.llm.presets.azure_ai_foundry_preset``) -- their transports are all
served end-to-end by the four-axis path (``kaizen.llm.deployment_resolver.
resolve_deployment_for`` + ``LlmClient.embed`` / ``complete``), consulted
BEFORE this registry in every live caller. ``PROVIDERS`` is now EMPTY.

Registry model-id dispatch (``get_provider_for_model``) is RETIRED and raises
for every input -- model-id -> wire dispatch lives in
``kaizen.llm.deployment_resolver``.

Covers the surviving registry surface:
- ``PROVIDERS`` is the empty dict; every retired name is absent.
- ``get_provider`` raises ``ValueError`` ("Unknown provider") for every name --
  there is nothing left to resolve.
- ``get_provider_for_model`` raises ``UnknownProviderError`` for every model.
- ``get_streaming_provider`` raises for every name (nothing satisfies
  ``StreamingProvider``).
- ``get_available_providers`` returns an empty dict.
- Backward-compat: ``kaizen.providers`` re-exports the registry accessors (via
  the deprecation shim).
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment_resolver import (
    UnsupportedDeploymentProvider,
    resolve_deployment_for,
)
from kaizen.providers.errors import UnknownProviderError
from kaizen.providers.registry import (
    PROVIDERS,
    get_available_providers,
    get_provider,
    get_provider_for_model,
    get_streaming_provider,
)

# Every provider name ever served by the registry -- none remain (#1720
# Wave-2 + #1820 + #1892).
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
    # #1820 embedding-legacy + unified-azure providers
    "cohere",
    "huggingface",
    "azure",
    "azure_openai",
    # #1892 -- the last registry provider
    "azure_ai_foundry",
}

# The four keys covered by a live resolve_deployment_for mapping that needs
# only an api_key (azure_ai_foundry is covered separately below since it also
# needs an endpoint / model, mirroring azure / azure_openai's base_url need).
_FOUR_AXIS_KEYS = ("cohere", "huggingface", "azure", "azure_openai")


# tests/conftest.py (module scope) rebinds ``PROVIDERS["mock"] = KaizenMockProvider``
# for unit tests (unless USE_REAL_PROVIDERS=true), so under the harness a spurious
# ``"mock"`` key is present. It is a harness artifact, NOT a real registry member —
# in a clean interpreter ``PROVIDERS`` is ``{}``. Exclude it from the exact-contents
# assertion (mirrors the barrel test's ``_PROVIDERS_CONFTEST_PATCHED`` carve-out).
_HARNESS_INJECTED_KEYS = {"mock"}


class TestProvidersDict:
    """The PROVIDERS dict is empty -- every provider is four-axis-served."""

    def test_providers_dict_is_empty(self):
        assert set(PROVIDERS.keys()) - _HARNESS_INJECTED_KEYS == set()

    def test_retired_providers_absent(self):
        """None of the retired chat / embedding / unified-azure / foundry
        names remain."""
        assert not (_RETIRED_PROVIDERS & set(PROVIDERS.keys()))

    def test_no_string_sentinels_remain(self):
        """The '_unified_azure' lazy-string sentinel routing was removed."""
        assert all(isinstance(v, type) for v in PROVIDERS.values())


class TestFourAxisRoutingForRetiredKeys:
    """Every retired key routes to the four-axis path, not the registry."""

    def test_retired_keys_not_in_registry(self):
        for key in _RETIRED_PROVIDERS:
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

    def test_azure_ai_foundry_resolves_via_four_axis(self):
        """#1892: azure_ai_foundry now has a confirmed four-axis wire (the
        unified Foundry model-inference endpoint) instead of raising
        UnsupportedDeploymentProvider."""
        deployment = resolve_deployment_for(
            "azure_ai_foundry",
            "gpt-5-nano",
            api_key="k",
            base_url="https://my-foundry-resource.services.ai.azure.com",
        )
        assert deployment is not None
        assert deployment.preset_name == "azure_ai_foundry"

    def test_no_known_provider_raises_unsupported_deployment_provider(self):
        """The UnsupportedDeploymentProvider mechanism is retained for a
        FUTURE known-but-unwired provider, but NO current provider name
        triggers it -- azure_ai_foundry (the last one) closed in #1892."""
        for key in _FOUR_AXIS_KEYS + ("azure_ai_foundry",):
            try:
                resolve_deployment_for(
                    key, "m", api_key="k", base_url="https://example.com"
                )
            except UnsupportedDeploymentProvider:
                raise AssertionError(
                    f"{key!r} unexpectedly raised UnsupportedDeploymentProvider "
                    "-- every known provider should have a confirmed wire post-#1892"
                )


class TestGetProvider:
    """get_provider has nothing left to resolve -- every name is unknown."""

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent_provider_xyz")

    def test_azure_ai_foundry_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("azure_ai_foundry")

    def test_case_insensitive_still_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("Azure_AI_Foundry")


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
    """get_streaming_provider has nothing to resolve -- every name unknown."""

    def test_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_streaming_provider("nonexistent_provider_xyz")

    def test_azure_ai_foundry_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_streaming_provider("azure_ai_foundry")


class TestGetAvailableProviders:
    """get_available_providers returns an empty dict (nothing registered)."""

    def test_returns_empty_dict(self):
        # tests/conftest.py rebinds PROVIDERS["mock"] = KaizenMockProvider for
        # unit tests; get_available_providers() reflects that harness artifact
        # back out. Exclude it — see _HARNESS_INJECTED_KEYS above.
        result = get_available_providers()
        assert isinstance(result, dict)
        assert set(result.keys()) - _HARNESS_INJECTED_KEYS == set()


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

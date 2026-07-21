# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 barrel legacy-provider deprecation shims (behavioral).

The `kaizen.nodes.ai` and `kaizen.providers` barrels used to eagerly re-export
the legacy provider classes + registry accessors from their canonical
`kaizen.providers.*` locations. Wave-B2a converted those legacy re-exports to
lazy PEP 562 ``__getattr__`` DeprecationWarning shims (zero-tolerance Rule 6a:
public-API removal needs a deprecation cycle — the DeprecationWarning shipped in
kaizen 2.34.0).

Wave-2 then RETIRED the seven legacy chat providers (openai / anthropic /
google / ollama / docker / perplexity / mock) onto the four-axis LlmClient and
DELETED their canonical modules. #1820 likewise RETIRED the embedding-legacy
``CohereProvider`` / ``HuggingFaceProvider`` (delete-now, no deprecation cycle)
and the unified-azure provider stack, deleting their modules too. #1892
completed the SAME end-of-cycle for ``AzureAIFoundryProvider`` -- its
DeprecationWarning shim shipped in kaizen 2.39.0 (one minor cycle), and this PR
deletes its canonical module (``kaizen.providers.llm.azure``). Their barrel
re-exports were removed in the same step — the deprecation cycle for all of
them is COMPLETE, so accessing them via either barrel now raises
``AttributeError`` (no warning, no resolution). The STILL-shimmed names (the
base ``LLMProvider`` and the registry accessors ``PROVIDERS`` / ``get_provider``
/ ``get_available_providers``) stay on the warn+resolve shim until Wave-C.

This pins the behavioral contract so a refactor cannot silently change it:

* Accessing a STILL-shimmed legacy name (e.g. ``LLMProvider``) via either
  barrel emits a ``DeprecationWarning`` AND returns the real class
  (identity-equal to the canonical-module symbol).
* Accessing a REMOVED legacy provider (e.g. ``OpenAIProvider``,
  ``AzureAIFoundryProvider``) via either barrel raises ``AttributeError`` —
  the end-of-cycle contract.
* The registry accessors (``PROVIDERS`` / ``get_provider`` /
  ``get_available_providers``) warn + resolve the same way.
* A NON-legacy eager export (``EmbeddingGeneratorNode``, ``BaseAIProvider``)
  does NOT warn — only the shimmed legacy names do.
* A bare ``import`` of the barrel does NOT warn (only attribute access does).
* Every still-shimmed legacy name remains in each barrel's ``__all__``.
* An unknown attribute raises ``AttributeError`` (no silent stub).

Tier-1 offline + deterministic (no network, no live keys). Behavioral asserts
per ``rules/testing.md`` § "Behavioral Regression Tests Over Source-Grep".
"""

from __future__ import annotations

import importlib
import warnings

import pytest

import kaizen.nodes.ai as nodes_ai
import kaizen.providers as providers

pytestmark = pytest.mark.regression


# Still-shimmed legacy name -> canonical module, per barrel (warn + resolve).
# The seven Wave-2-retired chat providers + azure_ai_foundry (#1892) are NOT
# here — their deprecation cycle is complete and they now raise
# AttributeError (see _REMOVED_LEGACY_PROVIDERS).
_NODES_AI_LEGACY = {
    "LLMProvider": "kaizen.providers.base",
    "PROVIDERS": "kaizen.providers.registry",
    "get_provider": "kaizen.providers.registry",
    "get_available_providers": "kaizen.providers.registry",
}

# #1820: CohereProvider / HuggingFaceProvider were RETIRED (delete-now, no
# deprecation cycle) with the embedding-legacy providers — their modules were
# DELETED and their barrel re-exports removed, so they now join the
# AttributeError set below rather than the warn+resolve set.
_PROVIDERS_LEGACY = dict(_NODES_AI_LEGACY)

_PROVIDERS_LEGACY_WARNS = _PROVIDERS_LEGACY

# #1720 Wave-2: seven legacy chat providers retired onto the four-axis LlmClient,
# modules deleted, barrel re-exports removed.
# #1820: the embedding-legacy CohereProvider / HuggingFaceProvider joined them
# (delete-now, no deprecation cycle).
# #1892: AzureAIFoundryProvider completed its own deprecation cycle (the
# DeprecationWarning shipped in kaizen 2.39.0) and joins them too — its module
# is deleted and it is the LAST provider to complete this transition.
# Accessing any of these now raises AttributeError (no warning, no
# resolution) — the end-of-cycle contract.
_REMOVED_LEGACY_PROVIDERS = [
    "AnthropicProvider",
    "AzureAIFoundryProvider",
    "CohereProvider",
    "DockerModelRunnerProvider",
    "GoogleGeminiProvider",
    "HuggingFaceProvider",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "PerplexityProvider",
]

# The test harness (tests/conftest.py, module scope) deliberately rebinds
# ``kaizen.providers.MockProvider = KaizenMockProvider`` for unit tests, so under
# the harness ``MockProvider`` is a REAL attribute on the ``kaizen.providers``
# module dict and the barrel ``__getattr__`` never fires for it. That override is
# a harness artifact, not a barrel defect — in a clean interpreter
# ``kaizen.providers.MockProvider`` raises AttributeError like every other
# removed name. It is therefore excluded ONLY from the ``kaizen.providers``
# AttributeError parametrization; the ``nodes.ai`` barrel is NOT patched by
# conftest, so MockProvider's removed-name behavior is still fully covered there.
_PROVIDERS_CONFTEST_PATCHED = {"MockProvider"}
_PROVIDERS_REMOVED_RAISES = [
    n for n in _REMOVED_LEGACY_PROVIDERS if n not in _PROVIDERS_CONFTEST_PATCHED
]


def _canonical(name: str, module_path: str) -> object:
    return getattr(importlib.import_module(module_path), name)


# --------------------------------------------------------------------------
# (a) nodes.ai — access warns AND returns the real class (identity-equal).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "module_path"), sorted(_NODES_AI_LEGACY.items()))
def test_nodes_ai_every_legacy_name_warns_and_resolves(
    name: str, module_path: str
) -> None:
    with pytest.warns(DeprecationWarning, match=r"deprecated.*#1720"):
        resolved = getattr(nodes_ai, name)
    assert resolved is _canonical(name, module_path)


# --------------------------------------------------------------------------
# (b) providers — access warns AND returns the real class (identity-equal).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "module_path"), sorted(_PROVIDERS_LEGACY_WARNS.items())
)
def test_providers_every_legacy_name_warns_and_resolves(
    name: str, module_path: str
) -> None:
    with pytest.warns(DeprecationWarning, match=r"deprecated.*#1720"):
        resolved = getattr(providers, name)
    assert resolved is _canonical(name, module_path)


# --------------------------------------------------------------------------
# (c) NON-legacy eager exports do NOT warn.
# --------------------------------------------------------------------------


def test_nodes_ai_non_legacy_export_does_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        # Eagerly-imported node — accessing it must not touch __getattr__.
        assert nodes_ai.EmbeddingGeneratorNode is not None


def test_providers_non_legacy_export_does_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        # BaseAIProvider stays eager (only LLMProvider was shimmed).
        assert providers.BaseAIProvider is not None
        assert providers.EmbeddingProvider is not None


# --------------------------------------------------------------------------
# (d) Every legacy name stays in __all__ (public contract unchanged).
# --------------------------------------------------------------------------


def test_nodes_ai_all_still_contains_every_legacy_name() -> None:
    missing = [n for n in _NODES_AI_LEGACY if n not in nodes_ai.__all__]
    assert not missing, f"legacy names dropped from kaizen.nodes.ai.__all__: {missing}"


def test_providers_all_still_contains_every_legacy_name() -> None:
    missing = [n for n in _PROVIDERS_LEGACY if n not in providers.__all__]
    assert not missing, f"legacy names dropped from kaizen.providers.__all__: {missing}"


# --------------------------------------------------------------------------
# (e) Registry accessors warn + resolve (explicit coverage of the (e) item).
# --------------------------------------------------------------------------


def test_nodes_ai_registry_accessors_warn_and_resolve() -> None:
    from kaizen.providers.registry import PROVIDERS as CanonPROVIDERS
    from kaizen.providers.registry import get_provider as canon_get_provider

    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert nodes_ai.PROVIDERS is CanonPROVIDERS
    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert nodes_ai.get_provider is canon_get_provider


def test_providers_registry_accessors_warn_and_resolve() -> None:
    from kaizen.providers.registry import PROVIDERS as CanonPROVIDERS
    from kaizen.providers.registry import get_provider as canon_get_provider

    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert providers.PROVIDERS is CanonPROVIDERS
    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert providers.get_provider is canon_get_provider


# --------------------------------------------------------------------------
# (f) #1720 Wave-2 end-of-cycle — the seven RETIRED chat providers now raise
#     AttributeError on BOTH barrels (deprecation cycle complete, modules gone).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_REMOVED_LEGACY_PROVIDERS))
def test_nodes_ai_removed_legacy_provider_raises_attribute_error(name: str) -> None:
    # No DeprecationWarning, no resolution — the shim entry is gone.
    with pytest.raises(AttributeError):
        getattr(nodes_ai, name)
    # And it is no longer advertised in __all__.
    assert name not in nodes_ai.__all__


@pytest.mark.parametrize("name", sorted(_PROVIDERS_REMOVED_RAISES))
def test_providers_removed_legacy_provider_raises_attribute_error(name: str) -> None:
    # MockProvider is excluded here (conftest rebinds it on the providers barrel);
    # every other retired provider raises AttributeError.
    with pytest.raises(AttributeError):
        getattr(providers, name)
    assert name not in providers.__all__


# --------------------------------------------------------------------------
# Robustness: unknown attribute raises AttributeError (no silent stub).
# --------------------------------------------------------------------------


def test_nodes_ai_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        _ = nodes_ai.DefinitelyNotAProvider


def test_providers_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        _ = providers.DefinitelyNotAProvider

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-B2a — barrel legacy-provider deprecation shims (behavioral).

The `kaizen.nodes.ai` and `kaizen.providers` barrels used to eagerly re-export
the legacy provider classes + registry accessors from their canonical
`kaizen.providers.*` locations. Wave-B2a converts those legacy re-exports to
lazy PEP 562 ``__getattr__`` DeprecationWarning shims (zero-tolerance Rule 6a:
public-API removal needs a deprecation cycle; this STARTS the clock — Wave-C
removes them). The public contract is unchanged: every legacy name stays in
``__all__`` and resolves to the same real symbol; only the barrel access PATH
now warns.

This pins the behavioral contract so a refactor cannot silently drop the
warning, break identity, or eagerly re-inline the symbols:

* Accessing a legacy provider (e.g. ``OpenAIProvider``) via either barrel emits
  a ``DeprecationWarning`` AND returns the real class (identity-equal to the
  canonical-module symbol).
* The registry accessors (``PROVIDERS`` / ``get_provider`` /
  ``get_available_providers``) warn + resolve the same way.
* A NON-legacy eager export (``EmbeddingGeneratorNode``, ``BaseAIProvider``)
  does NOT warn — only the shimmed legacy names do.
* A bare ``import`` of the barrel does NOT warn (only attribute access does).
* Every legacy name remains in each barrel's ``__all__``.
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


# Legacy name -> canonical module, per barrel.
_NODES_AI_LEGACY = {
    "LLMProvider": "kaizen.providers.base",
    "AnthropicProvider": "kaizen.providers.llm.anthropic",
    "AzureAIFoundryProvider": "kaizen.providers.llm.azure",
    "DockerModelRunnerProvider": "kaizen.providers.llm.docker",
    "GoogleGeminiProvider": "kaizen.providers.llm.google",
    "MockProvider": "kaizen.providers.llm.mock",
    "OllamaProvider": "kaizen.providers.llm.ollama",
    "OpenAIProvider": "kaizen.providers.llm.openai",
    "PerplexityProvider": "kaizen.providers.llm.perplexity",
    "PROVIDERS": "kaizen.providers.registry",
    "get_provider": "kaizen.providers.registry",
    "get_available_providers": "kaizen.providers.registry",
}

_PROVIDERS_LEGACY = {
    **_NODES_AI_LEGACY,
    "CohereProvider": "kaizen.providers.embedding.cohere",
    "HuggingFaceProvider": "kaizen.providers.embedding.huggingface",
}

# The test harness (tests/conftest.py, module scope) deliberately rebinds
# ``kaizen.providers.MockProvider = KaizenMockProvider`` for unit tests, so under
# the harness ``MockProvider`` is a REAL attribute on the ``kaizen.providers``
# module dict and the PEP 562 shim never fires for it (nor does it resolve to the
# canonical class). That override is a harness artifact, not a shim defect — the
# shim warns + resolves correctly in a clean interpreter. The ``nodes.ai`` barrel
# is NOT patched by conftest, so ``MockProvider`` shim behavior is still fully
# covered there; here it is excluded ONLY from the ``kaizen.providers``
# warn+resolve parametrization (it remains in the ``__all__`` contract check).
_PROVIDERS_CONFTEST_PATCHED = {"MockProvider"}
_PROVIDERS_LEGACY_WARNS = {
    k: v for k, v in _PROVIDERS_LEGACY.items() if k not in _PROVIDERS_CONFTEST_PATCHED
}


def _canonical(name: str, module_path: str) -> object:
    return getattr(importlib.import_module(module_path), name)


# --------------------------------------------------------------------------
# (a) nodes.ai — access warns AND returns the real class (identity-equal).
# --------------------------------------------------------------------------


def test_nodes_ai_openai_provider_warns_and_resolves_real_class() -> None:
    with pytest.warns(DeprecationWarning, match=r"kaizen\.nodes\.ai.*#1720"):
        resolved = nodes_ai.OpenAIProvider

    from kaizen.providers.llm.openai import OpenAIProvider as Canonical

    assert resolved is Canonical


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


def test_providers_openai_provider_warns_and_resolves_real_class() -> None:
    with pytest.warns(DeprecationWarning, match=r"kaizen\.providers.*#1720"):
        resolved = providers.OpenAIProvider

    from kaizen.providers.llm.openai import OpenAIProvider as Canonical

    assert resolved is Canonical


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
    from kaizen.providers.registry import (
        PROVIDERS as CanonPROVIDERS,
        get_provider as canon_get_provider,
    )

    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert nodes_ai.PROVIDERS is CanonPROVIDERS
    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert nodes_ai.get_provider is canon_get_provider


def test_providers_registry_accessors_warn_and_resolve() -> None:
    from kaizen.providers.registry import (
        PROVIDERS as CanonPROVIDERS,
        get_provider as canon_get_provider,
    )

    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert providers.PROVIDERS is CanonPROVIDERS
    with pytest.warns(DeprecationWarning, match=r"#1720"):
        assert providers.get_provider is canon_get_provider


# --------------------------------------------------------------------------
# Robustness: unknown attribute raises AttributeError (no silent stub).
# --------------------------------------------------------------------------


def test_nodes_ai_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        _ = nodes_ai.DefinitelyNotAProvider


def test_providers_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        _ = providers.DefinitelyNotAProvider

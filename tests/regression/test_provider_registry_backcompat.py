# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test — `kaizen.providers.registry.get_provider(name)` back-compat.

MED-4 amendment to #498 Session 2 — invariant 3 of the S3 plan claims that
all 39 files importing from ``kaizen.providers.*`` compile and test
unchanged after the preset layer lands. Passive reliance on provider
tests staying green is not a guard against a future refactor that
re-routes the registry path.

This regression test imports ``get_provider("openai")``,
``get_provider("anthropic")``, ``get_provider("google")`` (and a few of
the others that have symbolic providers), runs at least one method call
through each, and asserts the legacy surface stays intact.

Per ``rules/testing.md`` § "Regression tests are never deleted", this
file MUST NOT be removed. If the registry API changes, this file is
updated to match — not deleted.
"""

from __future__ import annotations

import pytest

from kaizen.providers.base import BaseAIProvider
from kaizen.providers.registry import PROVIDERS, get_provider


# Minimum names every S3 / pre-S3 consumer relies on. Expanding this list
# is safe; shrinking it is a compat break.
_REQUIRED_PROVIDER_NAMES = (
    "openai",
    "anthropic",
    "google",
    "gemini",
    "ollama",
    "mock",
    "cohere",
    "huggingface",
    "docker",
    "perplexity",
    "pplx",
    "azure",
    "azure_openai",
)


@pytest.mark.parametrize("name", _REQUIRED_PROVIDER_NAMES)
def test_get_provider_returns_provider_instance(name: str) -> None:
    """Every legacy name resolves through ``get_provider`` to a provider instance.

    This is the minimum back-compat guarantee: the registry returns an
    object, not None, not an exception. The object is a subclass of
    ``BaseAIProvider`` (Kaizen's canonical provider base class).
    """
    provider = get_provider(name)
    assert provider is not None
    assert isinstance(provider, BaseAIProvider)


def test_get_provider_rejects_unknown_name() -> None:
    """Unknown names MUST raise ValueError (documented legacy behaviour)."""
    with pytest.raises(ValueError):
        get_provider("this-provider-does-not-exist-xyz")


def test_providers_table_contains_every_required_name() -> None:
    """``PROVIDERS`` dict exports every legacy name (used by introspection code)."""
    missing = set(_REQUIRED_PROVIDER_NAMES) - set(PROVIDERS)
    assert not missing, f"PROVIDERS missing legacy keys: {sorted(missing)}"


def test_get_provider_openai_capabilities() -> None:
    """OpenAI provider exposes the capability introspection API unchanged."""
    provider = get_provider("openai")
    caps = provider.get_capabilities()
    assert "chat" in caps
    assert caps["chat"] is True


def test_get_provider_anthropic_capabilities() -> None:
    """Anthropic provider exposes chat capability unchanged."""
    provider = get_provider("anthropic")
    caps = provider.get_capabilities()
    assert caps.get("chat") is True


def test_get_provider_google_capabilities() -> None:
    """Google Gemini provider exposes chat capability unchanged."""
    provider = get_provider("google")
    caps = provider.get_capabilities()
    assert caps.get("chat") is True


def test_get_provider_provider_type_chat_filter() -> None:
    """``provider_type='chat'`` still works on legacy registry surface."""
    provider = get_provider("openai", provider_type="chat")
    assert isinstance(provider, BaseAIProvider)


def test_get_provider_provider_type_invalid_raises() -> None:
    """Unknown ``provider_type`` still raises ValueError."""
    with pytest.raises(ValueError):
        get_provider("openai", provider_type="not-a-real-type")

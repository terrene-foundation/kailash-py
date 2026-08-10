# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test — the legacy `kaizen.providers.registry` surface is RETIRED.

This file used to assert the OPPOSITE: that ``get_provider("openai")`` and
twelve sibling names each returned a ``BaseAIProvider``. That contract was
deliberately retired — deprecated in kaizen 2.39.0 (#1720), removed in 2.40.0
(#1892) — and ``PROVIDERS`` is now intentionally empty. The assertions were
never swept when the removal landed, so 18 tests in this file failed against
`main` for three releases while asserting a contract the package had
deliberately abandoned.

Per ``rules/testing.md`` § "Regression tests are never deleted", the file is
UPDATED to match the new contract rather than removed — and the direction of
the guard is inverted. It now pins the REMOVAL: a silent re-population of
``PROVIDERS``, or a silent re-introduction of the legacy resolution path,
REDS this file. That is the failure mode worth guarding now, because the
legacy path is the one #1892 removed for carrying an ungoverned fallback.

WHAT REPLACED IT. Live resolution goes through ``kaizen.llm.LlmClient`` and
``kaizen.llm.deployment_resolver`` (consulted by ``llm_agent``'s provider
response path and ``embedding_generator``'s embedding path). Note the
replacement answers a DIFFERENT question and is NOT a drop-in:
``resolve_deployment_for(provider, model)`` returns ``None`` when no
deployment is configured and does NOT raise on an unrecognised provider, so
it cannot be substituted into the assertions below. Recorded explicitly
because a "did it raise?" probe against it reports success for every input,
known and unknown alike — an instrument that cannot tell the two apart.

``get_provider`` REMAINS EXPORTED (``kaizen.providers.__all__``) and remains
the extensibility mechanism for a future provider with no confirmed four-axis
wire. It is the TABLE that is empty, not the function that is gone.
"""

from __future__ import annotations

import pytest

from kaizen.providers.registry import PROVIDERS, get_provider

# The names the pre-2.40.0 registry resolved. Retained as the REMOVAL pin:
# each must now be rejected, so a silent re-population is loud.
_RETIRED_PROVIDER_NAMES = (
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


def test_providers_table_is_intentionally_empty() -> None:
    """``PROVIDERS`` is empty by design since #1892.

    Guards the removal in the load-bearing direction: if a future change
    re-populates this table, the legacy ungoverned resolution path is live
    again and this test REDS, forcing the author to justify it rather than
    letting it return silently.
    """
    assert PROVIDERS == {}, (
        f"PROVIDERS is no longer empty: {sorted(PROVIDERS)}. The legacy "
        f"registry path was removed in kaizen 2.40.0 (#1892) because it "
        f"carried an ungoverned fallback. Re-populating it re-opens that "
        f"path — if that is intended, update this test and say so in the "
        f"CHANGELOG."
    )


@pytest.mark.parametrize("name", _RETIRED_PROVIDER_NAMES)
def test_retired_provider_names_are_rejected(name: str) -> None:
    """Every retired name now raises, and the error names the empty table."""
    with pytest.raises(ValueError) as exc_info:
        get_provider(name)
    assert "Available: []" in str(exc_info.value), (
        f"get_provider({name!r}) raised, but not with the empty-registry "
        f"message: {exc_info.value}. If the registry gained entries, see "
        f"test_providers_table_is_intentionally_empty."
    )


def test_get_provider_still_rejects_unknown_name() -> None:
    """Unknown names still raise ValueError — unchanged by the emptying.

    This assertion is the one piece of the original contract that survives
    intact, and it is kept deliberately: it is what distinguishes "the
    function still validates its input" from "the function was gutted".
    """
    with pytest.raises(ValueError):
        get_provider("this-provider-does-not-exist-xyz")


def test_get_provider_remains_exported() -> None:
    """The FUNCTION is still public; only the TABLE was emptied.

    #1892 removed the legacy resolution DATA, not the extensibility
    mechanism. If ``get_provider`` itself is later removed, that IS a public
    API removal and owes the deprecation cycle `zero-tolerance.md` Rule 6a
    requires — this assertion is what makes that removal loud.
    """
    import kaizen.providers as providers

    assert "get_provider" in providers.__all__
    assert callable(providers.get_provider)

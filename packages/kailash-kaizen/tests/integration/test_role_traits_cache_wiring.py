"""Tier-2 — Trait-derivation cache returns without re-invoking LLM.

Per Issue #829 plan, derivation is cached per Kaizen instance keyed by
``role.strip().lower()``. Verifies via spy on ``BaseAgent.run`` that a second
identical-role call (including normalization variants) returns from cache.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from kaizen import Kaizen


@pytest.mark.integration
def test_cache_returns_same_traits_without_second_llm_call() -> None:
    os.environ.setdefault(
        "KAIZEN_DEFAULT_MODEL",
        os.environ.get("OPENAI_PROD_MODEL", "gpt-4o-mini"),
    )
    kaizen = Kaizen()

    # First call — populates cache (LLM hit allowed)
    a1 = kaizen.create_specialized_agent(name="r1", role="data analyst", config={})
    first_traits = a1.behavior_traits
    assert isinstance(first_traits, list) and len(first_traits) > 0

    # Second call — same normalized role; expect cache hit (no LLM invocation).
    # The patch replaces BaseAgent.run with an assertion-raising stub: if the
    # cache works, run() is never called and the stub never fires.
    with patch(
        "kaizen.core.base_agent.BaseAgent.run",
        side_effect=AssertionError("BaseAgent.run called on cache hit"),
    ):
        a2 = kaizen.create_specialized_agent(
            name="r2", role="Data Analyst", config={}  # case normalization
        )
    assert a2.behavior_traits == first_traits


@pytest.mark.integration
def test_cache_normalizes_whitespace_and_case() -> None:
    os.environ.setdefault(
        "KAIZEN_DEFAULT_MODEL",
        os.environ.get("OPENAI_PROD_MODEL", "gpt-4o-mini"),
    )
    kaizen = Kaizen()
    a1 = kaizen.create_specialized_agent(name="r1", role="research analyst", config={})
    # Same role + leading/trailing whitespace + mixed case → cache hit
    with patch(
        "kaizen.core.base_agent.BaseAgent.run",
        side_effect=AssertionError("cache should have hit"),
    ):
        a2 = kaizen.create_specialized_agent(
            name="r2", role="  Research Analyst  ", config={}
        )
    assert a2.behavior_traits == a1.behavior_traits

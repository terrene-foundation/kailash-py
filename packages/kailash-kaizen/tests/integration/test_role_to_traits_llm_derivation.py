"""Tier-2 — LLM-first trait derivation produces shape-correct output.

Per Issue #829 acceptance criteria #2 and #3, exercises the real LLM
derivation path through ``Kaizen.create_specialized_agent`` for two distinct
roles. Asserts SHAPE only (list[str], non-empty, lowercase-ish strings), not
exact content — LLM output is nondeterministic across providers and even
within a single provider over time.

Also covers Risk-1 disposition from
``workspaces/issue-829-kaizen-llm-first-traits/01-analysis/02-risks-and-edges.md``:
no API key → ``RuntimeError`` with actionable message naming both escape
hatches.
"""

from __future__ import annotations

import os

import pytest

from kaizen import Kaizen


@pytest.mark.integration
def test_llm_derivation_machine_learning_researcher() -> None:
    """Acceptance criterion #2: novel role → non-empty trait list[str]."""
    os.environ.setdefault(
        "KAIZEN_DEFAULT_MODEL",
        os.environ.get("OPENAI_PROD_MODEL", "gpt-4o-mini"),
    )
    kaizen = Kaizen()
    agent = kaizen.create_specialized_agent(
        name="ml_researcher",
        role="machine learning researcher",
        config={},
    )
    assert isinstance(agent.behavior_traits, list)
    assert 1 <= len(agent.behavior_traits) <= 10
    assert all(
        isinstance(t, str) and t.strip() for t in agent.behavior_traits
    ), f"every trait must be non-empty str: {agent.behavior_traits!r}"


@pytest.mark.integration
def test_llm_derivation_data_analyst_default_callers_unbroken() -> None:
    """Acceptance criterion #3: default-derivation callers continue to work."""
    os.environ.setdefault(
        "KAIZEN_DEFAULT_MODEL",
        os.environ.get("OPENAI_PROD_MODEL", "gpt-4o-mini"),
    )
    kaizen = Kaizen()
    agent = kaizen.create_specialized_agent(
        name="data_analyst",
        role="data analyst",
        config={},
    )
    assert isinstance(agent.behavior_traits, list)
    assert len(agent.behavior_traits) > 0
    assert all(isinstance(t, str) and t.strip() for t in agent.behavior_traits)


@pytest.mark.integration
def test_llm_unavailable_raises_actionable_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk-1: no provider env → RuntimeError naming both escape hatches."""
    monkeypatch.delenv("KAIZEN_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    kaizen = Kaizen()
    with pytest.raises(RuntimeError) as exc_info:
        kaizen.create_specialized_agent(
            name="will_fail",
            role="some role with no provider configured",
            config={},
        )
    msg = str(exc_info.value).lower()
    assert "behavior_traits" in msg
    assert "env" in msg or ".env" in msg


@pytest.mark.integration
def test_explicit_behavior_traits_skips_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User-supplied traits bypass derivation entirely — escape hatch alive.

    Verified by spying on ``Kaizen._generate_role_based_traits``: when
    ``behavior_traits`` is supplied in config, the derivation method MUST
    never be called. Model env is set so unrelated CoreAgent
    initialization (which independently checks ``KAIZEN_DEFAULT_MODEL``)
    succeeds — this test isolates the trait-derivation skip path, not
    the broader env-config path.
    """
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

    from unittest.mock import patch

    with patch.object(
        Kaizen,
        "_generate_role_based_traits",
        side_effect=AssertionError(
            "_generate_role_based_traits called despite explicit behavior_traits"
        ),
    ):
        kaizen = Kaizen()
        agent = kaizen.create_specialized_agent(
            name="explicit",
            role="any role",
            config={
                "model": "gpt-4o-mini",
                "behavior_traits": ["custom", "explicit", "skip_llm"],
            },
        )
        assert agent.behavior_traits == ["custom", "explicit", "skip_llm"]

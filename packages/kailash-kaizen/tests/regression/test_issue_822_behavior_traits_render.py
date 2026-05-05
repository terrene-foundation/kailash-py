"""Issue #822 regression — `behavior_traits` round-trip from create_specialized_agent
to rendered role-based prompt.

Prior code at framework.py:537-540 read ``agent.behavior_traits`` inside a
``hasattr(agent, "behavior_traits")`` guard. But the value was only stored in
``agent.config["behavior_traits"]`` (line 485), never as an attribute. The
hasattr was structurally always False; the trait-rendering branch was
unreachable. Fix at framework.py:495 area assigns ``agent.behavior_traits``
explicitly. This regression locks the round-trip.
"""

import threading
from typing import Iterator

import pytest

from kaizen import Kaizen

_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized() -> Iterator[None]:
    with _ENV_LOCK:
        yield


@pytest.mark.regression
def test_behavior_traits_attached_to_agent(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """create_specialized_agent with explicit traits → agent.behavior_traits is set."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen = Kaizen()
    agent = kaizen.create_specialized_agent(
        name="analyst",
        role="data analyst",
        config={"behavior_traits": ["analytical", "thorough"]},
    )
    assert hasattr(agent, "behavior_traits"), (
        "agent.behavior_traits must be set as attribute (not just config dict) "
        "so framework.py:537 hasattr guard fires"
    )
    assert agent.behavior_traits == ["analytical", "thorough"]


@pytest.mark.regression
def test_behavior_traits_render_in_prompt(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """Rendered role-based prompt MUST contain trait words from behavior_traits."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen = Kaizen()
    agent = kaizen.create_specialized_agent(
        name="analyst",
        role="data analyst",
        config={"behavior_traits": ["analytical", "thorough"]},
    )
    prompt = kaizen._generate_role_based_prompt(agent, task="analyze X")
    assert "analytical" in prompt, (
        f"trait 'analytical' missing from prompt: {prompt!r} — "
        "framework.py:537 trait-rendering branch may be unreachable"
    )
    assert "thorough" in prompt


@pytest.mark.regression
def test_behavior_traits_default_from_role(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """No explicit traits → default keyword-matched traits attached + rendered.

    NOTE: the keyword-matching default-derivation in
    `_generate_role_based_traits` violates `agent-reasoning.md` Rule 1 and is
    tracked in journal/0004 + Open Question #4 for follow-up. This test pins
    the CURRENT behavior so the trait-rendering chain remains exercised.
    """
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen = Kaizen()
    agent = kaizen.create_specialized_agent(
        name="researcher",
        role="research analyst",  # matches the keyword bucket
        config={},
    )
    assert hasattr(agent, "behavior_traits")
    assert agent.behavior_traits is not None
    # Defaults for "research"/"analyze" bucket include "analytical"
    assert any(
        t in agent.behavior_traits
        for t in ["analytical", "thorough", "evidence_based", "methodical"]
    ), f"Expected at least one default research trait in {agent.behavior_traits}"

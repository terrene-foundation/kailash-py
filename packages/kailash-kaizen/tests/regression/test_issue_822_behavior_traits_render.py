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
@pytest.mark.integration
def test_behavior_traits_default_from_role(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """No explicit traits → LLM-first derivation populates a non-empty list[str].

    Per Issue #829 fix, trait derivation goes through ``RoleToTraitsSignature``
    + ``BaseAgent.run()`` (LLM-first per ``rules/agent-reasoning.md`` Rule 1).
    LLM output is nondeterministic, so this test asserts the SHAPE of the
    derived list (per acceptance criterion #2: "assertion on shape, not exact
    contents") rather than exact-string membership in a hardcoded bucket.

    Tier-2 integration test — requires a working LLM provider (.env).
    """
    import os

    monkeypatch.setenv(
        "KAIZEN_DEFAULT_MODEL",
        os.environ.get("OPENAI_PROD_MODEL", "gpt-4o-mini"),
    )
    kaizen = Kaizen()
    agent = kaizen.create_specialized_agent(
        name="researcher",
        role="research analyst",
        config={},
    )
    assert hasattr(agent, "behavior_traits")
    assert isinstance(agent.behavior_traits, list)
    assert len(agent.behavior_traits) > 0
    assert all(
        isinstance(t, str) and t.strip() for t in agent.behavior_traits
    ), f"every trait must be a non-empty string: {agent.behavior_traits!r}"

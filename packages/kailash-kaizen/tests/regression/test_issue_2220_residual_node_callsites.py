# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2220 residual — the same defect through the OTHER doors.

#2220's primary fix closed the wrong-vendor composition at
``resolve_agent_provider``, whose only production consumer is ``AgentConfig``.
Roughly thirty other sites built an ``LLMAgentNode`` config by calling
``detect_provider_from_env()`` DIRECTLY and writing its answer into the same
dict as a ``model`` key — the identical "a credential answers the vendor
question" composition, reached through a different entry point.

Measured on this tree with the primary fix applied and BEFORE this change:

    Agent(config={"model": "llama-3.1"})._get_provider_for_config()
      -> 'openai'      with OPENAI_API_KEY exported
      -> 'anthropic'   with ANTHROPIC_API_KEY exported
      -> None          keyless

    RAGEvaluationNode(llm_judge_model="llama3.1:8b")
      -> node config  provider='openai'    model='llama3.1:8b'
      -> node config  provider='anthropic' model='llama3.1:8b'

The RAG family is the worst of these: it is RAG, so retrieved documents are
in the payload that leaves the machine.

WHY EVERY TEST HERE IS A PAIR
-----------------------------
A single-pole test cannot tell this fix apart from "resolution now always
raises". Each behaviour is pinned against its opposite:

* an unregistered model with a credential must RAISE, at every entry point
  <-> a REGISTERED model must still resolve normally with a credential set;
* an explicit ``llm_provider=`` must still win, so the fix cannot be mistaken
  for "locally-served models are now unusable" — the migration the error
  message names must actually work.

Parametrised over BOTH credentials deliberately. The defect was never
OpenAI-specific: the old fallback followed whichever key happened to exist,
so pinning only ``OPENAI_API_KEY`` would leave the bug reachable through
``ANTHROPIC_API_KEY``.

A further pole worth naming: a REGISTERED model's answer must not depend on
which credential is exported either. Before this change ``gpt-4`` resolved to
``'anthropic'`` at ``Agent._get_provider_for_config()`` when only
``ANTHROPIC_API_KEY`` was set — a registered OpenAI model dispatched to
Anthropic. That is the same root cause pointing the other way, and
``test_registered_model_is_credential_independent`` pins it.

No test here needs a live API key. The values are fake literals; resolution
reads only the PRESENCE of the variable, never its validity.
"""

from __future__ import annotations

import pytest

from kaizen.config.providers import ConfigurationError
from kaizen.core._provider_env import describe_node_provider, resolve_node_provider

pytestmark = pytest.mark.regression

# Chosen for what they demonstrate, not as configuration. Neither carries a
# registered provider prefix, and the first is a real Ollama library tag.
UNREGISTERED_LOCAL_MODEL = "llama3.1:8b"
UNREGISTERED_HOSTED_MODEL = "mistral-large"
REGISTERED_MODEL = "gpt-4"

CREDENTIALS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
UNREGISTERED = [UNREGISTERED_LOCAL_MODEL, UNREGISTERED_HOSTED_MODEL]


@pytest.fixture
def scrubbed_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A known-empty credential state each test then sets up deliberately.

    ``KAIZEN_ALLOW_KEYLESS_MOCK`` is cleared because the kaizen harness sets
    it (``tests/conftest.py``), under which resolution short-circuits to
    ``"mock"`` and every assertion below would pass while proving nothing.
    """
    for var in (
        "KAIZEN_ALLOW_KEYLESS_MOCK",
        "KAIZEN_ALLOW_REAL_LLM",
        # Cleared too: a developer with either of these exported would
        # otherwise see every fail-closed assertion below resolve happily.
        "KAIZEN_DEFAULT_PROVIDER",
        "DEFAULT_LLM_PROVIDER",
        *CREDENTIALS,
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def _assert_is_the_2220_refusal(raised: ConfigurationError, model: str) -> None:
    """Assert WHICH failure this was.

    A bare ``pytest.raises(ConfigurationError)`` would also pass if resolution
    raised for an unrelated reason, making the test green for the wrong cause.
    """
    message = str(raised)
    assert model in message, f"error must name the model it refused: {message}"
    assert "llm_provider=" in message, f"error must name the migration: {message}"


# ---------------------------------------------------------------------------
# Pole 1 — the shared predicate itself.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CREDENTIALS)
@pytest.mark.parametrize("model", UNREGISTERED)
def test_unregistered_model_with_credential_fails_closed(scrubbed_env, key, model):
    """A credential must not answer "which vendor serves this model"."""
    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    with pytest.raises(ConfigurationError) as excinfo:
        resolve_node_provider(model, component="test")
    _assert_is_the_2220_refusal(excinfo.value, model)


@pytest.mark.parametrize("key", CREDENTIALS)
def test_registered_model_still_resolves_with_a_credential_set(scrubbed_env, key):
    """The opposite pole: the fix must not be "everything now raises"."""
    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    assert resolve_node_provider(REGISTERED_MODEL, component="test") == "openai"


@pytest.mark.parametrize("key", CREDENTIALS)
def test_registered_model_is_credential_independent(scrubbed_env, key):
    """A registered model resolves by REGISTRY, never by which key exists.

    Before this change ``gpt-4`` resolved to ``'anthropic'`` at
    ``Agent._get_provider_for_config()`` when only ``ANTHROPIC_API_KEY`` was
    set — a registered OpenAI model dispatched to Anthropic.
    """
    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    assert resolve_node_provider(REGISTERED_MODEL, component="test") == "openai"


@pytest.mark.parametrize("key", CREDENTIALS)
@pytest.mark.parametrize("model", UNREGISTERED)
def test_explicit_provider_still_wins(scrubbed_env, key, model):
    """The migration the error message names must actually work.

    Without this pole the fix would read as "locally-served models are now
    unusable" rather than "say which vendor serves them".
    """
    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    assert resolve_node_provider(model, explicit="ollama", component="test") == "ollama"


@pytest.mark.parametrize("var", ["KAIZEN_DEFAULT_PROVIDER", "DEFAULT_LLM_PROVIDER"])
@pytest.mark.parametrize("model", UNREGISTERED)
def test_a_declared_provider_resolves_an_unregistered_model(scrubbed_env, var, model):
    """The migration for callers that expose no ``llm_provider`` argument.

    The RAG node constructors take their model from ``DEFAULT_LLM_MODEL`` and
    accept no provider argument, so without this there is no path at all for an
    Ollama user — the fix would read as "RAG is now unusable locally".

    This is NOT the guess #2220 removed. These two settings exist for no
    purpose other than naming a provider, so setting one is an affirmative
    statement; a credential is not. The next test pins that difference.
    """
    scrubbed_env.delenv(var, raising=False)
    scrubbed_env.setenv(var, "ollama")

    assert resolve_node_provider(model, component="test") == "ollama"


@pytest.mark.parametrize("key", CREDENTIALS)
@pytest.mark.parametrize("model", UNREGISTERED)
def test_a_credential_is_still_not_a_declaration(scrubbed_env, key, model):
    """The opposite pole of the test above — and the point of the whole fix.

    A declared provider resolves; a credential still does not. If this ever
    passes for the wrong reason the previous test would be meaningless, since
    both would resolve and nothing would distinguish configuration from an
    unrelated exported key.
    """
    scrubbed_env.delenv("KAIZEN_DEFAULT_PROVIDER", raising=False)
    scrubbed_env.delenv("DEFAULT_LLM_PROVIDER", raising=False)
    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    with pytest.raises(ConfigurationError) as excinfo:
        resolve_node_provider(model, component="test")
    _assert_is_the_2220_refusal(excinfo.value, model)


def test_a_declaration_does_not_override_a_known_model(scrubbed_env):
    """A declared default replaces the REFUSAL, never the registry.

    Checked after the registry precisely so that declaring a default for local
    work cannot silently redirect a model whose vendor is known. Without this
    pole, setting ``DEFAULT_LLM_PROVIDER=ollama`` would send ``claude-3-opus``
    to Ollama.
    """
    scrubbed_env.setenv("DEFAULT_LLM_PROVIDER", "ollama")

    assert resolve_node_provider("claude-3-opus", component="test") == "anthropic"
    assert resolve_node_provider(REGISTERED_MODEL, component="test") == "openai"


@pytest.mark.parametrize("key", CREDENTIALS)
def test_rag_node_builds_for_a_local_model_when_the_provider_is_declared(
    scrubbed_env, key
):
    """End to end: the documented migration actually works at the RAG surface."""
    from kaizen.nodes.rag.evaluation import RAGEvaluationNode

    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")
    scrubbed_env.setenv("DEFAULT_LLM_PROVIDER", "ollama")

    node = RAGEvaluationNode(name="probe", llm_judge_model=UNREGISTERED_LOCAL_MODEL)
    configs = [
        n.config
        for n in node._workflow.nodes.values()
        if getattr(n, "config", None) and "provider" in n.config
    ]
    assert configs, "expected at least one LLM node in the built workflow"
    for cfg in configs:
        assert cfg["provider"] == "ollama"
        assert cfg["model"] == UNREGISTERED_LOCAL_MODEL


def test_no_model_still_asks_the_credential_question(scrubbed_env):
    """The distinction this fix turns on, pinned explicitly.

    With NO model in hand there is no model whose vendor could be
    mis-attributed, so "which credentials exist" IS the right question and
    #1952's contract is unchanged. This pole is what stops the fix from being
    over-applied to the sites that were always correct.
    """
    scrubbed_env.setenv("OPENAI_API_KEY", "sk-fake-not-a-real-credential")
    assert resolve_node_provider(None, component="test") == "openai"

    scrubbed_env.delenv("OPENAI_API_KEY")
    scrubbed_env.setenv("ANTHROPIC_API_KEY", "sk-fake-not-a-real-credential")
    assert resolve_node_provider(None, component="test") == "anthropic"

    scrubbed_env.delenv("ANTHROPIC_API_KEY")
    assert resolve_node_provider(None, component="test") is None


# ---------------------------------------------------------------------------
# Pole 2 — the entry points the primary fix left open, end to end.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", CREDENTIALS)
@pytest.mark.parametrize("model", UNREGISTERED)
def test_agent_get_provider_for_config_fails_closed(scrubbed_env, key, model):
    """``Agent(config={"model": ...})`` — the door measured on the issue.

    Reached publicly via ``Kaizen.create_agent()`` with a dict config.
    """
    from kaizen.core.agents import Agent

    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")
    agent = Agent(agent_id="probe", config={"model": model})

    with pytest.raises(ConfigurationError) as excinfo:
        agent._get_provider_for_config()
    _assert_is_the_2220_refusal(excinfo.value, model)


@pytest.mark.parametrize("key", CREDENTIALS)
def test_agent_registered_model_still_resolves(scrubbed_env, key):
    """Opposite pole at the same entry point, credential-independent."""
    from kaizen.core.agents import Agent

    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")
    agent = Agent(agent_id="probe", config={"model": REGISTERED_MODEL})

    assert agent._get_provider_for_config() == "openai"


@pytest.mark.parametrize("key", CREDENTIALS)
@pytest.mark.parametrize("model", UNREGISTERED)
def test_agent_explicit_provider_still_wins(scrubbed_env, key, model):
    """An Ollama user's documented migration, at the Agent door."""
    from kaizen.core.agents import Agent

    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")
    agent = Agent(agent_id="probe", config={"model": model, "provider": "ollama"})

    assert agent._get_provider_for_config() == "ollama"


@pytest.mark.parametrize("key", CREDENTIALS)
def test_rag_node_fails_closed_for_a_local_model(scrubbed_env, key):
    """The RAG family — worst case, because retrieved documents are in the payload.

    ``RAGEvaluationNode`` is used because its model is a plain constructor
    kwarg, so the assertion does not depend on import-time env capture.
    """
    from kaizen.nodes.rag.evaluation import RAGEvaluationNode

    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    with pytest.raises(ConfigurationError) as excinfo:
        RAGEvaluationNode(name="probe", llm_judge_model=UNREGISTERED_LOCAL_MODEL)
    _assert_is_the_2220_refusal(excinfo.value, UNREGISTERED_LOCAL_MODEL)


@pytest.mark.parametrize("key", CREDENTIALS)
def test_rag_node_registered_model_still_builds(scrubbed_env, key):
    """Opposite pole: the RAG builders must still work for a hosted model."""
    from kaizen.nodes.rag.evaluation import RAGEvaluationNode

    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")
    node = RAGEvaluationNode(name="probe", llm_judge_model=REGISTERED_MODEL)

    configs = [
        n.config
        for n in node._workflow.nodes.values()
        if getattr(n, "config", None) and "provider" in n.config
    ]
    assert configs, "expected at least one LLM node in the built workflow"
    for cfg in configs:
        assert cfg["provider"] == "openai"
        assert cfg["model"] == REGISTERED_MODEL


# ---------------------------------------------------------------------------
# Pole 3 — the cache keys, which must mirror dispatch without ever raising.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", UNREGISTERED)
def test_cache_key_provider_never_raises_and_is_credential_independent(
    scrubbed_env, model
):
    """A cache key must not raise, and must not drift with ambient credentials.

    Keying on ``detect_provider_from_env()`` meant the key for an unregistered
    model changed with whichever credential happened to be exported, while the
    dispatch it exists to mirror no longer depends on that at all.
    """
    scrubbed_env.setenv("OPENAI_API_KEY", "sk-fake-not-a-real-credential")
    with_openai = describe_node_provider(model)

    scrubbed_env.delenv("OPENAI_API_KEY")
    scrubbed_env.setenv("ANTHROPIC_API_KEY", "sk-fake-not-a-real-credential")
    with_anthropic = describe_node_provider(model)

    assert with_openai == with_anthropic == "<unresolved>"


def test_cache_key_tracks_a_resolvable_provider(scrubbed_env):
    """Opposite pole: the key must still CHANGE when the dispatch would."""
    assert describe_node_provider(REGISTERED_MODEL) == "openai"
    assert describe_node_provider("claude-3-opus") == "anthropic"
    assert describe_node_provider(UNREGISTERED_LOCAL_MODEL, explicit="ollama") == (
        "ollama"
    )

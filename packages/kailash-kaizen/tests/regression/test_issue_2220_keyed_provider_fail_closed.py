# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2220 — provider resolution must fail closed WITH a credential present too.

#2069 made an unregistered model fail closed, but only on the KEYLESS path.
``resolve_agent_provider`` composed the registry-derived prefix table with
``detect_provider_from_env()``, whose order is ``OPENAI_API_KEY`` ->
``ANTHROPIC_API_KEY`` -> ``None``. So with a key exported — the common
developer configuration, and often exported for an unrelated tool — an
unregistered model still resolved silently to that key's vendor.

The concrete harm, and why this is not merely a mis-set default: an Ollama
user runs a LOCAL model precisely so the prompt does not leave the machine.
``AgentConfig(model="llama-3.1")`` with ``OPENAI_API_KEY`` set dispatched the
prompt — and any retrieved context in it — to OpenAI. It was billed. Nothing
warned: no log line, no exception, no diagnostic.

Ollama is not an edge case here, it is the structural one: it serves arbitrary
model names, so NO prefix can identify it and every local model name misses
the registry by construction.

WHY THESE TESTS ARE WRITTEN IN PAIRS
------------------------------------
A single-pole test cannot distinguish this fix from "the resolver now always
raises". Each behaviour below is therefore pinned against its opposite:

* keyed-unregistered must RAISE  <->  keyed-REGISTERED must still resolve;
* the keyless pole (#2069's own case) must keep raising, so a regression that
  re-opened the env fallback could not pass by making the keyed case raise
  for some unrelated reason.

The keyless column is also the discrimination control from the issue's probe:
the SAME code path demonstrably can return a loud error, so a keyed result
that differs is a real behavioural difference and not a probe artifact.

No test here depends on a live API key. The values set are fake literals; the
resolver reads only the PRESENCE of the variable, never its validity.
"""

from __future__ import annotations

import pytest

from kaizen.agent_config import AgentConfig
from kaizen.config.providers import ConfigurationError
from kaizen.core import resolve_agent_provider

pytestmark = pytest.mark.regression

# Model names chosen for what they demonstrate, not as configuration:
# an Ollama-served local model, and a non-OpenAI hosted model. Neither
# carries a registered provider prefix.
UNREGISTERED_LOCAL_MODEL = "llama-3.1"
UNREGISTERED_HOSTED_MODEL = "mistral-large"


@pytest.fixture
def scrubbed_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A known-empty credential state each test then sets up deliberately.

    ``KAIZEN_ALLOW_KEYLESS_MOCK`` is cleared because the kaizen harness sets
    it (``tests/conftest.py``), under which resolution answers ``"mock"`` and
    every assertion below would pass while proving nothing.
    """
    for var in (
        "KAIZEN_ALLOW_KEYLESS_MOCK",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# --------------------------------------------------------------------------
# Pole 1 — the #2220 defect proper: a credential must not answer the
# "which vendor serves this model" question.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"])
@pytest.mark.parametrize("model", [UNREGISTERED_LOCAL_MODEL, UNREGISTERED_HOSTED_MODEL])
def test_unregistered_model_with_credential_does_not_silently_dispatch(
    scrubbed_env, key, model
):
    """The exact shipped behaviour: key set + unknown model -> silent vendor.

    Parametrised over BOTH credentials on purpose. The defect was never
    OpenAI-specific — the fallback returns whichever vendor's key happens to
    be exported, so pinning only ``OPENAI_API_KEY`` would leave the same bug
    reachable through ``ANTHROPIC_API_KEY``.
    """
    scrubbed_env.setenv(key, "sk-fake-not-a-real-credential")

    try:
        config = AgentConfig(model=model)
    except ConfigurationError:
        return  # failing closed is the required behaviour
    pytest.fail(
        f"{model!r} with {key} set silently resolved to "
        f"{config.llm_provider!r} instead of failing closed. A credential "
        f"says which vendor the caller has an account with, never which "
        f"vendor serves this model (#2220)."
    )


def test_resolver_error_names_the_model_and_the_migration(scrubbed_env):
    """An error that does not say how to proceed just relocates the problem.

    Pins the two things a caller needs to act: WHICH model was unresolvable,
    and the exact kwarg that fixes it. Without the kwarg named, the obvious
    reading of "could not resolve a provider" is "export a key" — which is
    what the caller already did, and what caused the silent dispatch.
    """
    scrubbed_env.setenv("OPENAI_API_KEY", "sk-fake-not-a-real-credential")

    with pytest.raises(ConfigurationError) as caught:
        resolve_agent_provider(UNREGISTERED_LOCAL_MODEL, component="unit-test")

    message = str(caught.value)
    assert UNREGISTERED_LOCAL_MODEL in message
    assert "llm_provider=" in message
    assert "unit-test" in message, "the component must be named to locate the config"


def test_credential_presence_does_not_change_the_outcome(scrubbed_env):
    """Keyless and keyed must now agree for an unregistered model.

    This states the contract directly rather than by two separate examples:
    the environment is not an input to the vendor question at all, so adding
    a credential must not move the result. Before the fix these two branches
    disagreed, which IS the defect.
    """
    with pytest.raises(ConfigurationError):
        resolve_agent_provider(UNREGISTERED_LOCAL_MODEL)

    scrubbed_env.setenv("OPENAI_API_KEY", "sk-fake-not-a-real-credential")
    with pytest.raises(ConfigurationError):
        resolve_agent_provider(UNREGISTERED_LOCAL_MODEL)


# --------------------------------------------------------------------------
# Pole 2 — no-false-positive: the fix must not become "always raises".
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-4", "openai"),
        ("o1-preview", "openai"),
        ("claude-3-opus-20240229", "anthropic"),
        ("gemini-2.0-flash", "google"),
        ("deepseek-chat", "deepseek"),
    ],
)
def test_registered_models_still_resolve_with_a_credential_set(
    scrubbed_env, model, expected
):
    """Every registered prefix must keep resolving, key present or not.

    Run WITH ``OPENAI_API_KEY`` set specifically: this is the state in which
    the model-beats-environment ordering matters, so it also re-pins #2022 —
    a ``claude-*`` model must still reach anthropic and not be captured by
    the exported OpenAI key.
    """
    scrubbed_env.setenv("OPENAI_API_KEY", "sk-fake-not-a-real-credential")

    assert resolve_agent_provider(model) == expected
    assert AgentConfig(model=model).llm_provider == expected


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_explicit_provider_is_the_documented_migration_and_works(
    scrubbed_env, provider
):
    """The error tells callers to pass ``llm_provider=``; prove that path works.

    Advice that has not been executed is a hypothesis. This runs the exact
    migration the error message prescribes, for an unregistered model, with
    no credential present.
    """
    config = AgentConfig(model=UNREGISTERED_LOCAL_MODEL, llm_provider=provider)

    assert config.llm_provider == provider


# --------------------------------------------------------------------------
# Pole 3 — the #2069 keyless case must not regress, and the harness opt-in
# must survive.
# --------------------------------------------------------------------------


def test_keyless_unregistered_model_still_raises(scrubbed_env):
    """#2069's own case, re-pinned as this fix's discrimination control.

    If a future change re-opened the env fallback, this alone would not
    catch it — which is exactly why it is paired with the keyed tests above
    rather than standing in for them, as #2069's suite did.
    """
    with pytest.raises(ConfigurationError):
        resolve_agent_provider(UNREGISTERED_LOCAL_MODEL)


def test_explicit_harness_optin_still_resolves_to_mock(scrubbed_env):
    """An EXPLICIT opt-in flag is not a credential guess.

    The distinction this fix turns on: ``KAIZEN_ALLOW_KEYLESS_MOCK`` is set
    only by the kaizen harness, never by a real caller, and ``mock``
    dispatches nowhere off-machine. Removing it would break the
    deliberately-keyless unit suite (#1952) for no security gain.
    """
    scrubbed_env.setenv("KAIZEN_ALLOW_KEYLESS_MOCK", "1")

    assert resolve_agent_provider(UNREGISTERED_LOCAL_MODEL) == "mock"


def test_harness_optin_outranks_a_stray_credential(scrubbed_env):
    """Precedence deliberately changed by #2220, so pinned rather than assumed.

    The flag used to be reached only when NO key was set, so a harness with a
    stray ``OPENAI_API_KEY`` exported resolved to openai instead of mock. That
    contradicts the invariant this fix establishes — for an unregistered model
    the outcome must not depend on which credentials happen to exist — so the
    opt-in is now checked first.
    """
    scrubbed_env.setenv("KAIZEN_ALLOW_KEYLESS_MOCK", "1")
    scrubbed_env.setenv("OPENAI_API_KEY", "sk-fake-not-a-real-credential")

    assert resolve_agent_provider(UNREGISTERED_LOCAL_MODEL) == "mock"

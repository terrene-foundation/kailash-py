"""FNEW-5 regression — provider config getters use documented provider-intrinsic
default-model constants, never inline literals, and never leak the
provider-agnostic ``KAIZEN_DEFAULT_MODEL`` into a provider-specific getter.

Disposition (see ``kaizen/config/providers.py`` FNEW-5 header): the per-provider
``DEFAULT_<PROVIDER>_MODEL`` constants are NOT an ``env-models.md`` violation —
they are provider-intrinsic (the caller has already chosen the provider, so the
default carries no lock-in), env-overridable via ``KAIZEN_<PROVIDER>_MODEL``, and
deliberately NOT chained to ``KAIZEN_DEFAULT_MODEL`` (which is provider-agnostic;
chaining it would reintroduce the provider/model mismatch FNEW-4 fixed).

These tests lock four contracts:
  1. each getter resolves to its named constant when no arg / no env override;
  2. ``KAIZEN_<PROVIDER>_MODEL`` overrides the default; an explicit ``model=`` arg
     overrides both;
  3. the provider-agnostic ``KAIZEN_DEFAULT_MODEL`` does NOT leak into any
     provider-specific getter (the core anti-mismatch invariant);
  4. value pins — the stale anthropic default was refreshed to a current model,
     and embedding providers keep embedding (not chat) defaults.

Env-var isolation (rules/testing.md § Env-Var Test Isolation MUST): every test
that mutates the environment acquires the module-scope ``_ENV_LOCK`` via the
``_env_serialized`` fixture so xdist-parallel runs cannot race, and clears all
provider-affecting vars so an ambient ``.env`` cannot bleed into assertions.
"""

import threading
from typing import Iterator

import pytest

from kaizen.config import providers as P

pytestmark = pytest.mark.regression

# Module-scope env lock per rules/testing.md.
_ENV_LOCK = threading.Lock()

# Every env var that can influence a provider getter's resolved model or
# availability. Cleared before each test so ambient .env never leaks in.
_AFFECTING_VARS = (
    "KAIZEN_DEFAULT_MODEL",
    "KAIZEN_OPENAI_MODEL",
    "KAIZEN_OLLAMA_MODEL",
    "KAIZEN_AZURE_MODEL",
    "KAIZEN_DOCKER_MODEL",
    "KAIZEN_ANTHROPIC_MODEL",
    "KAIZEN_COHERE_MODEL",
    "KAIZEN_HUGGINGFACE_MODEL",
    "KAIZEN_GOOGLE_MODEL",
    "KAIZEN_PERPLEXITY_MODEL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "PERPLEXITY_API_KEY",
    "AZURE_API_KEY",
    "AZURE_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_AI_INFERENCE_API_KEY",
    "AZURE_AI_INFERENCE_ENDPOINT",
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Serialized + cleared environment; ollama/docker availability forced on."""
    with _ENV_LOCK:
        for var in _AFFECTING_VARS:
            monkeypatch.delenv(var, raising=False)
        # Local providers gate on a live-server probe, not env; force available
        # so the default-resolution path is reachable without a running server.
        monkeypatch.setattr(P, "check_ollama_available", lambda: True)
        monkeypatch.setattr(P, "check_docker_available", lambda: True)
        yield monkeypatch


# (provider label, getter, env-var name, default constant, availability env to set)
CASES = [
    (
        "openai",
        P.get_openai_config,
        "KAIZEN_OPENAI_MODEL",
        P.DEFAULT_OPENAI_MODEL,
        {"OPENAI_API_KEY": "sk-test"},
    ),
    (
        "anthropic",
        P.get_anthropic_config,
        "KAIZEN_ANTHROPIC_MODEL",
        P.DEFAULT_ANTHROPIC_MODEL,
        {"ANTHROPIC_API_KEY": "sk-ant-test"},
    ),
    (
        "cohere",
        P.get_cohere_config,
        "KAIZEN_COHERE_MODEL",
        P.DEFAULT_COHERE_MODEL,
        {"COHERE_API_KEY": "co-test"},
    ),
    (
        "huggingface",
        P.get_huggingface_config,
        "KAIZEN_HUGGINGFACE_MODEL",
        P.DEFAULT_HUGGINGFACE_MODEL,
        {},
    ),
    (
        "google",
        P.get_google_config,
        "KAIZEN_GOOGLE_MODEL",
        P.DEFAULT_GOOGLE_MODEL,
        {"GOOGLE_API_KEY": "g-test"},
    ),
    (
        "perplexity",
        P.get_perplexity_config,
        "KAIZEN_PERPLEXITY_MODEL",
        P.DEFAULT_PERPLEXITY_MODEL,
        {"PERPLEXITY_API_KEY": "pplx-test"},
    ),
    (
        "azure",
        P.get_azure_config,
        "KAIZEN_AZURE_MODEL",
        P.DEFAULT_AZURE_MODEL,
        {
            "AZURE_API_KEY": "az-test",
            "AZURE_ENDPOINT": "https://example.openai.azure.com",
        },
    ),
    ("ollama", P.get_ollama_config, "KAIZEN_OLLAMA_MODEL", P.DEFAULT_OLLAMA_MODEL, {}),
    ("docker", P.get_docker_config, "KAIZEN_DOCKER_MODEL", P.DEFAULT_DOCKER_MODEL, {}),
]
_CASE_PARAMS = [pytest.param(*c[1:], id=c[0]) for c in CASES]


@pytest.mark.parametrize("getter,env_var,default_const,avail", _CASE_PARAMS)
def test_default_resolves_to_named_constant(env, getter, env_var, default_const, avail):
    """No arg + no override → the provider's documented named constant."""
    for k, v in avail.items():
        env.setenv(k, v)
    assert getter().model == default_const


@pytest.mark.parametrize("getter,env_var,default_const,avail", _CASE_PARAMS)
def test_env_override_wins_over_default(env, getter, env_var, default_const, avail):
    """KAIZEN_<PROVIDER>_MODEL takes precedence over the intrinsic default."""
    for k, v in avail.items():
        env.setenv(k, v)
    env.setenv(env_var, "env-override-model")
    assert getter().model == "env-override-model"


@pytest.mark.parametrize("getter,env_var,default_const,avail", _CASE_PARAMS)
def test_explicit_arg_wins_over_env_and_default(
    env, getter, env_var, default_const, avail
):
    """An explicit model= arg beats both the env override and the default."""
    for k, v in avail.items():
        env.setenv(k, v)
    env.setenv(env_var, "env-override-model")
    assert getter(model="explicit-arg-model").model == "explicit-arg-model"


@pytest.mark.parametrize("getter,env_var,default_const,avail", _CASE_PARAMS)
def test_kaizen_default_model_does_not_leak_into_provider_getter(
    env, getter, env_var, default_const, avail
):
    """Core anti-mismatch invariant: the provider-agnostic KAIZEN_DEFAULT_MODEL
    MUST NOT be chained into a provider-specific getter — else a claude-* default
    would be returned under provider="openai" (the FNEW-4 mismatch class).
    """
    for k, v in avail.items():
        env.setenv(k, v)
    env.setenv("KAIZEN_DEFAULT_MODEL", "leaked-agnostic-model")
    # KAIZEN_<PROVIDER>_MODEL intentionally unset → provider default, NOT the leak.
    assert getter().model == default_const


def test_named_constant_value_pins(env):
    """Pin the constant values so any future drift is a loud, reviewable diff.

    These are the provider-intrinsic defaults; the test is the structural defense
    against silent re-inlining or accidental edits.
    """
    assert P.DEFAULT_OPENAI_MODEL == "gpt-4o-mini"
    assert P.DEFAULT_OLLAMA_MODEL == "llama3.2"
    assert P.DEFAULT_AZURE_MODEL == "gpt-4o"
    assert P.DEFAULT_DOCKER_MODEL == "ai/llama3.2"
    assert P.DEFAULT_COHERE_MODEL == "embed-english-v3.0"
    assert P.DEFAULT_HUGGINGFACE_MODEL == "sentence-transformers/all-MiniLM-L6-v2"
    assert P.DEFAULT_GOOGLE_MODEL == "gemini-2.0-flash"
    assert P.DEFAULT_PERPLEXITY_MODEL == "sonar"


def test_anthropic_default_refreshed_off_stale_dated_model(env):
    """The stale dated default (claude-3-haiku-20240307) was refreshed to the
    project-canonical current fast Claude. Guard against regressing to the
    dated model identifier.
    """
    assert P.DEFAULT_ANTHROPIC_MODEL == "claude-haiku-4-5"
    assert "20240307" not in P.DEFAULT_ANTHROPIC_MODEL
    env.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert P.get_anthropic_config().model == "claude-haiku-4-5"


def test_embedding_providers_keep_embedding_defaults(env):
    """Embedding providers MUST default to embedding models, never a chat model
    (the reason KAIZEN_DEFAULT_MODEL — a chat default — is not chained here).
    """
    env.setenv("COHERE_API_KEY", "co-test")
    assert "embed" in P.get_cohere_config().model
    assert P.get_huggingface_config().model.startswith("sentence-transformers/")


def test_vision_provider_default_is_named_constant():
    """The OpenAI vision provider's DEFAULT_MODEL is a documented named constant
    (FNEW-5 same-shard surface), pinned for drift detection.
    """
    from kaizen.providers.document.openai_vision_provider import OpenAIVisionProvider

    assert OpenAIVisionProvider.DEFAULT_MODEL == "gpt-4o-mini"

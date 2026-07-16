# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-A — unit tests for the shared provider->deployment resolver
(`kaizen.llm.deployment_resolver.resolve_deployment_for`), promoted from the
module-private `llm_agent._shadow_deployment_for`.

Covers every currently-mapped provider (api-key family + base-url family),
the credential/base_url skip paths, and the unmapped-provider skip. Azure is
covered separately in `test_deployment_resolver_azure.py` (invariant #3).

Tier 1, fully offline: api-key providers are resolved with an EXPLICIT
`api_key=` so no env is read; the env-fallback + missing-credential paths
mutate env vars and therefore serialize through a module-scope lock per
`rules/testing.md` § "Serialize Env-Var-Mutating Tests Via Module Lock".
"""

from __future__ import annotations

import logging
import threading

import pytest

from kaizen.llm import resolve_deployment_for  # exported from kaizen.llm
from kaizen.llm.deployment import LlmDeployment

# ---------------------------------------------------------------------------
# Env-var serialization — this module mutates the *_API_KEY vars the resolver
# reads as a credential fallback.
# ---------------------------------------------------------------------------

_ENV_LOCK = threading.Lock()
_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY",
    "PERPLEXITY_API_KEY",
)


@pytest.fixture
def _env_serialized(monkeypatch: pytest.MonkeyPatch):
    with _ENV_LOCK:
        for var in _ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        yield


# ---------------------------------------------------------------------------
# API-key family — every mapped provider resolves to its preset.
# ---------------------------------------------------------------------------

# (provider_name, expected_preset_name)
_API_KEY_PROVIDERS = [
    ("openai", "openai"),
    ("anthropic", "anthropic"),
    ("google", "google"),
    ("gemini", "google"),  # gemini aliases google_preset
    ("cohere", "cohere"),
    ("huggingface", "huggingface"),
    ("perplexity", "perplexity"),
    ("pplx", "perplexity"),  # pplx aliases perplexity_preset
]


@pytest.mark.parametrize("provider,expected_preset", _API_KEY_PROVIDERS)
def test_api_key_provider_resolves_to_preset(provider, expected_preset):
    dep = resolve_deployment_for(provider, "some-model", api_key="sk-explicit-key")
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == expected_preset
    assert dep.default_model == "some-model"


def test_provider_name_is_case_and_whitespace_insensitive():
    dep = resolve_deployment_for("  OpenAI  ", "m", api_key="sk-x")
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == "openai"


def test_api_key_env_fallback_when_no_explicit_key(monkeypatch, _env_serialized):
    """A provider with no explicit api_key reads its own <PROVIDER>_API_KEY env
    var (rules/env-models.md) — the legacy provider's own resolution."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    dep = resolve_deployment_for("openai", "m")
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == "openai"


def test_api_key_missing_returns_none_and_logs_skip(
    monkeypatch, _env_serialized, caplog
):
    """No explicit key AND no env var -> None (skip), DEBUG shadow_skipped
    with reason=missing_api_key."""
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for("openai", "m")
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "missing_api_key"


def test_api_key_provider_threads_base_url_override(monkeypatch, _env_serialized):
    """A base_url override is forwarded to the api-key preset factory
    (OpenAI-compatible endpoints)."""
    # localhost resolves without network (the SSRF guard runs real DNS at
    # Endpoint construction; a non-resolving public host would raise).
    dep = resolve_deployment_for(
        "openai", "m", api_key="sk-x", base_url="http://localhost:8080"
    )
    assert isinstance(dep, LlmDeployment)
    assert "localhost" in str(dep.endpoint.base_url)


# ---------------------------------------------------------------------------
# Base-url family — ollama / docker.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider,expected_preset",
    [("ollama", "ollama"), ("docker", "docker_model_runner")],
)
def test_base_url_provider_resolves_with_base_url(provider, expected_preset):
    dep = resolve_deployment_for(
        provider, "some-model", base_url="http://localhost:11434"
    )
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == expected_preset
    assert dep.default_model == "some-model"


@pytest.mark.parametrize("provider", ["ollama", "docker"])
def test_base_url_missing_returns_none_and_logs_skip(provider, caplog):
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for(provider, "m")
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "missing_base_url"


# ---------------------------------------------------------------------------
# Unmapped provider — best-effort skip.
# ---------------------------------------------------------------------------


def test_unmapped_provider_returns_none_and_logs_skip(caplog):
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for("totally-unknown-provider-xyz", "m")
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "unmapped_provider"

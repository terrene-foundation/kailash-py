# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: keyless LOCAL providers resolve without any credential (#1720).

``resolve_deployment_for("ollama", model)`` returned ``None`` -- reporting the
provider UNAVAILABLE -- while an Ollama server was running and reachable on
``localhost:11434``. ``llm_agent._provider_llm_response`` then raised
``Provider ollama is not available``, with no reason naming which precondition
had failed.

Root cause: ``ollama`` / ``docker`` sat in a ``_base_url_preset_map`` whose
resolve branch was ``if not base_url: return None``. Both are LOCAL runtimes
with ``StaticNone()`` auth: they have no credential to be missing, and a local
runtime publishes a canonical loopback endpoint, so "the caller named no
``base_url``" means "use the provider's own default" -- NOT "the provider is
unavailable". The resolver read a ``<PROVIDER>_API_KEY`` env var for the
credentialed family but read NO endpoint env var for the local family, so a
keyless provider had strictly fewer ways to resolve than a keyed one.

These tests have TEETH IN BOTH DIRECTIONS. The fix must NOT degenerate into
"everything is always available":

* keyless local providers resolve with EVERY credential env var stripped
  (``test_ollama_*`` / ``test_docker_*``); and
* a CREDENTIALED provider still resolves to ``None`` when its key is genuinely
  absent (``test_keyed_provider_still_unavailable_*``) -- the negative half
  that fails if the fix over-reaches.

Tier 1, fully offline: no deployment here performs network I/O (resolution is
a pure configuration mapping -- see ``resolve_deployment_for``'s "availability
means CONFIGURED, not REACHABLE" contract). Only ``localhost`` DNS is touched,
by the SSRF guard at ``Endpoint`` construction.
"""

from __future__ import annotations

import threading

import pytest

from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.deployment_resolver import (
    DEFAULT_DOCKER_MODEL_RUNNER_BASE_URL,
    DEFAULT_OLLAMA_BASE_URL,
    describe_unresolved_precondition,
    requires_credential,
    resolve_deployment_for,
)

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Env-var serialization -- these tests mutate the credential + endpoint env
# vars the resolver reads (`rules/testing.md` § "Serialize Env-Var-Mutating
# Tests Via Module Lock"). ONE lock domain covers the whole surface.
# ---------------------------------------------------------------------------

_ENV_LOCK = threading.Lock()

# Every credential var the resolver consults, for ANY provider. A keyless
# local provider must resolve with ALL of them absent -- that is the teeth.
_CREDENTIAL_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY",
    "PERPLEXITY_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "AZURE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_AI_FOUNDRY_API_KEY",
    "OLLAMA_API_KEY",
    "DOCKER_API_KEY",
)

_ENDPOINT_VARS = (
    "OLLAMA_BASE_URL",
    "OLLAMA_HOST",
    "DOCKER_MODEL_RUNNER_URL",
    "AZURE_ENDPOINT",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_AI_FOUNDRY_ENDPOINT",
)


@pytest.fixture
def bare_env(monkeypatch: pytest.MonkeyPatch):
    """No credential AND no endpoint env var anywhere in the environment."""
    with _ENV_LOCK:
        for var in (*_CREDENTIAL_VARS, *_ENDPOINT_VARS):
            monkeypatch.delenv(var, raising=False)
        yield monkeypatch


# ---------------------------------------------------------------------------
# Positive teeth -- keyless local providers resolve with a BARE environment.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider,expected_preset,expected_url",
    [
        ("ollama", "ollama", DEFAULT_OLLAMA_BASE_URL),
        (
            "docker",
            "docker_model_runner",
            DEFAULT_DOCKER_MODEL_RUNNER_BASE_URL,
        ),
    ],
)
def test_keyless_local_provider_resolves_with_no_credential_at_all(
    bare_env, provider: str, expected_preset: str, expected_url: str
) -> None:
    """THE REGRESSION. Every credential var stripped, no base_url passed, no
    endpoint env var set -> the provider still resolves, on its own canonical
    loopback default."""
    dep = resolve_deployment_for(provider, "some-model")

    assert dep is not None, (
        f"{provider} is a keyless local runtime and MUST resolve without any "
        f"credential; got None (the #1720 regression)"
    )
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == expected_preset
    assert dep.default_model == "some-model"
    assert str(dep.endpoint.base_url).rstrip("/") == expected_url.rstrip("/")


@pytest.mark.parametrize("provider", ["ollama", "docker"])
def test_keyless_local_provider_carries_no_auth_credential(
    bare_env, provider: str
) -> None:
    """The resolved deployment sends NO credential -- proof the provider is
    genuinely keyless rather than resolving via some fallback key."""
    from kaizen.llm.auth import StaticNone

    dep = resolve_deployment_for(provider, "some-model")
    assert dep is not None
    assert isinstance(dep.auth, StaticNone), (
        f"{provider} must authenticate with StaticNone (no credential); got "
        f"{type(dep.auth).__name__}"
    )
    # A StaticNone strategy installs no auth header at all.
    request: dict = {"headers": {}}
    dep.auth.apply(request)
    assert request["headers"] == {}


@pytest.mark.parametrize("provider", ["ollama", "docker"])
def test_requires_credential_declares_local_providers_keyless(provider: str) -> None:
    """The declarative property callers branch on, instead of testing the
    provider name against a hardcoded "ollama" literal."""
    assert requires_credential(provider) is False


@pytest.mark.parametrize(
    "provider", ["openai", "anthropic", "google", "azure", "azure_ai_foundry"]
)
def test_requires_credential_declares_keyed_providers_credentialed(
    provider: str,
) -> None:
    assert requires_credential(provider) is True


def test_requires_credential_fails_closed_for_unknown_provider() -> None:
    """An unrecognised name must NOT be assumed keyless."""
    assert requires_credential("totally-unknown-provider-xyz") is True


# ---------------------------------------------------------------------------
# Endpoint precedence -- override > env var > provider default.
# ---------------------------------------------------------------------------


def test_endpoint_env_var_overrides_provider_default(bare_env) -> None:
    """`rules/env-models.md`: the environment is the source of truth. The
    endpoint env var is the base_url analogue of <PROVIDER>_API_KEY.

    Note the `localhost` LABEL form: `url_safety.check_url` admits the
    allowlisted localhost hostname over http, but rejects a LITERAL loopback
    IP (`127.0.0.1`) at `Endpoint` construction -- so a local endpoint MUST
    be spelled `http://localhost:<port>`.
    """
    bare_env.setenv("OLLAMA_BASE_URL", "http://localhost:9999")
    dep = resolve_deployment_for("ollama", "m")
    assert dep is not None
    assert "9999" in str(dep.endpoint.base_url)


def test_per_request_base_url_overrides_env_var(bare_env) -> None:
    """A per-request override still wins over the env var (highest tier)."""
    bare_env.setenv("OLLAMA_BASE_URL", "http://localhost:9999")
    dep = resolve_deployment_for("ollama", "m", base_url="http://localhost:8123")
    assert dep is not None
    assert "8123" in str(dep.endpoint.base_url)
    assert "9999" not in str(dep.endpoint.base_url)


def test_empty_endpoint_env_var_falls_back_to_default(bare_env) -> None:
    """An empty/whitespace env var is NOT a configured endpoint."""
    bare_env.setenv("OLLAMA_BASE_URL", "   ")
    dep = resolve_deployment_for("ollama", "m")
    assert dep is not None
    assert str(dep.endpoint.base_url).rstrip("/") == DEFAULT_OLLAMA_BASE_URL


def test_ollama_default_endpoint_targets_the_native_wire_path(bare_env) -> None:
    """The canonical default must build the URL Ollama actually serves.

    The OllamaNative wire appends `/api/chat`; a base_url carrying a `/v1`
    suffix would build `/v1/api/chat`, which Ollama answers with 404.
    """
    from kaizen.llm.deployment import WireProtocol

    dep = resolve_deployment_for("ollama", "m")
    assert dep is not None
    assert dep.wire is WireProtocol.OllamaNative
    built = f"{str(dep.endpoint.base_url).rstrip('/')}{dep.endpoint.path_prefix or ''}"
    assert built.endswith("11434"), (
        f"ollama's default endpoint must be the bare native root (the wire "
        f"appends /api/chat); got {built!r}"
    )


# ---------------------------------------------------------------------------
# Negative teeth -- the fix MUST NOT make everything available.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider,env_var",
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("google", "GOOGLE_API_KEY"),
        ("cohere", "COHERE_API_KEY"),
        ("perplexity", "PERPLEXITY_API_KEY"),
    ],
)
def test_keyed_provider_still_unavailable_when_key_genuinely_absent(
    bare_env, provider: str, env_var: str
) -> None:
    """THE COUNTER-TEETH. If this passes while the positive tests also pass,
    the fix did not degenerate into "always available"."""
    assert resolve_deployment_for(provider, "m") is None, (
        f"{provider} requires {env_var}; with it absent the resolver MUST "
        f"still report unavailable"
    )


def test_keyed_provider_becomes_available_once_key_present(bare_env) -> None:
    """Same provider, same call -- only the credential differs. Proves the
    negative test above is measuring the credential, not a broken import."""
    assert resolve_deployment_for("openai", "m") is None
    bare_env.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    dep = resolve_deployment_for("openai", "m")
    assert dep is not None
    assert dep.preset_name == "openai"


def test_azure_still_unavailable_without_endpoint_and_key(bare_env) -> None:
    """Azure is NOT keyless -- a missing endpoint/key still returns None."""
    assert resolve_deployment_for("azure", "m") is None
    assert resolve_deployment_for("azure_ai_foundry", "m") is None


def test_unmapped_provider_still_unavailable(bare_env) -> None:
    assert resolve_deployment_for("totally-unknown-provider-xyz", "m") is None


# ---------------------------------------------------------------------------
# `rules/zero-tolerance.md` Rule 3 -- an unresolved provider names WHICH
# precondition failed. A bare "not available" is what made this expensive.
# ---------------------------------------------------------------------------


def test_unresolved_reason_names_the_missing_env_var(bare_env) -> None:
    reason = describe_unresolved_precondition("openai")
    assert "OPENAI_API_KEY" in reason
    assert "openai" in reason


def test_unresolved_reason_names_unknown_provider_and_lists_known(bare_env) -> None:
    reason = describe_unresolved_precondition("totally-unknown-provider-xyz")
    assert "totally-unknown-provider-xyz" in reason
    assert "ollama" in reason  # enumerates what IS supported


def test_llm_agent_error_message_names_the_precondition(bare_env) -> None:
    """The user-visible error must name the failed precondition, not just
    say "not available" (the defect that made this expensive to find)."""
    from kaizen.nodes.ai.llm_agent import LLMAgentNode

    node = LLMAgentNode()
    with pytest.raises(RuntimeError) as excinfo:
        node._provider_llm_response(
            "openai",
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            [],
            {},
        )
    message = str(excinfo.value)
    assert (
        "OPENAI_API_KEY" in message
    ), f"error must name the missing precondition; got {message!r}"

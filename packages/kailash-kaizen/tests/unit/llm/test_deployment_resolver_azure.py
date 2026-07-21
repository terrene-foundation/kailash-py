# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-A invariant #3 + #1892 — Azure mapping in the shared deployment
resolver.

`resolve_deployment_for("azure" | "azure_openai", ...)` builds an
`OpenAiChat`-wire deployment with an `AzureEntra` api-key auth strategy so
Azure gets shadowed (previously azure was unmapped -> never shadowed).

`resolve_deployment_for("azure_ai_foundry", ...)` (#1892) builds an
`OpenAiChat`-wire deployment via the unified, model-agnostic Foundry
model-inference wire (`azure_ai_foundry_preset`) -- azure_ai_foundry now has
a confirmed four-axis wire and resolves like every other credential-gated
preset (missing credential -> quiet `None`, NOT a raised error). This closes
the prior `UnsupportedDeploymentProvider` Wave-B blocker for this provider.

Tier 1, offline. Credential-resolution tests mutate AZURE_* env vars and
therefore serialize through a module-scope lock per rules/testing.md.
"""

from __future__ import annotations

import logging
import threading

import pytest

from kaizen.llm import (
    UnsupportedDeploymentProvider,
    resolve_deployment_for,
)
from kaizen.llm.deployment import LlmDeployment, WireProtocol

_ENV_LOCK = threading.Lock()
_ENV_VARS = (
    "AZURE_ENDPOINT",
    "AZURE_API_KEY",
    "AZURE_API_VERSION",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_AI_FOUNDRY_ENDPOINT",
    "AZURE_AI_FOUNDRY_API_KEY",
    "AZURE_AI_FOUNDRY_DEPLOYMENT",
    "AZURE_AI_FOUNDRY_API_VERSION",
)

_ENDPOINT = "https://myresource.openai.azure.com"
_FOUNDRY_ENDPOINT = "https://myfoundry.services.ai.azure.com"


@pytest.fixture
def _azure_env_serialized(monkeypatch: pytest.MonkeyPatch):
    with _ENV_LOCK:
        for var in _ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        yield


# ---------------------------------------------------------------------------
# azure / azure_openai -> OpenAiChat deployment with api-key auth.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["azure", "azure_openai"])
def test_azure_resolves_to_openai_chat_with_api_key_auth(provider):
    dep = resolve_deployment_for(
        provider, "my-deployment", api_key="k-secret", base_url=_ENDPOINT
    )
    assert isinstance(dep, LlmDeployment)
    assert dep.wire is WireProtocol.OpenAiChat
    assert dep.preset_name == "azure_openai"
    assert dep.default_model == "my-deployment"
    # api-key header variant (NOT Authorization: Bearer).
    assert dep.auth.auth_strategy_kind() == "azure_entra_api_key"


def test_azure_endpoint_carries_deployment_path_and_api_version():
    dep = resolve_deployment_for(
        "azure", "my-deployment", api_key="k", base_url=_ENDPOINT
    )
    assert dep.endpoint.path_prefix == "/openai/deployments/my-deployment"
    assert dep.endpoint.query_params == {"api-version": "2024-06-01"}
    assert "myresource.openai.azure.com" in str(dep.endpoint.base_url)


def test_azure_env_fallback_canonical(monkeypatch, _azure_env_serialized):
    """No explicit endpoint/api_key -> canonical AZURE_* env vars are read
    (the legacy Azure backend's own resolution)."""
    monkeypatch.setenv("AZURE_ENDPOINT", _ENDPOINT)
    monkeypatch.setenv("AZURE_API_KEY", "k-from-env")
    monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01")
    dep = resolve_deployment_for("azure", "my-deployment")
    assert isinstance(dep, LlmDeployment)
    assert dep.endpoint.query_params == {"api-version": "2025-01-01"}


def test_azure_missing_endpoint_returns_none(
    monkeypatch, _azure_env_serialized, caplog
):
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for("azure", "m", api_key="k")
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "missing_base_url"


def test_azure_missing_api_key_returns_none(monkeypatch, _azure_env_serialized, caplog):
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for("azure", "m", base_url=_ENDPOINT)
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "missing_api_key"


# ---------------------------------------------------------------------------
# azure_ai_foundry (#1892) -- confirmed four-axis wire, credential-gated like
# every other preset (NOT the prior UnsupportedDeploymentProvider blocker).
# ---------------------------------------------------------------------------


def test_azure_ai_foundry_resolves_to_openai_chat_with_api_key_auth(
    _azure_env_serialized,
):
    dep = resolve_deployment_for(
        "azure_ai_foundry", "gpt-5-nano", api_key="k-secret", base_url=_FOUNDRY_ENDPOINT
    )
    assert isinstance(dep, LlmDeployment)
    assert dep.wire is WireProtocol.OpenAiChat
    assert dep.preset_name == "azure_ai_foundry"
    assert dep.default_model == "gpt-5-nano"
    # No deployment-name-vs-family alias (#1859) -- the model IS the family.
    assert dep.canonical_model is None
    # api-key header variant (NOT Authorization: Bearer) -- same shape as
    # azure / azure_openai.
    assert dep.auth.auth_strategy_kind() == "azure_entra_api_key"


def test_azure_ai_foundry_endpoint_carries_the_unified_model_agnostic_path(
    _azure_env_serialized,
):
    dep = resolve_deployment_for(
        "azure_ai_foundry", "gpt-5-nano", api_key="k", base_url=_FOUNDRY_ENDPOINT
    )
    # Model-agnostic -- NO deployment name in the path (unlike azure_openai's
    # /openai/deployments/{deployment}).
    assert dep.endpoint.path_prefix == "/models"
    assert dep.endpoint.query_params == {"api-version": "2024-05-01-preview"}
    assert "myfoundry.services.ai.azure.com" in str(dep.endpoint.base_url)


def test_azure_ai_foundry_env_fallback_canonical(monkeypatch, _azure_env_serialized):
    """No explicit endpoint/api_key/model -> canonical AZURE_AI_FOUNDRY_* env
    vars are read."""
    monkeypatch.setenv("AZURE_AI_FOUNDRY_ENDPOINT", _FOUNDRY_ENDPOINT)
    monkeypatch.setenv("AZURE_AI_FOUNDRY_API_KEY", "k-from-env")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_DEPLOYMENT", "gpt-5-nano")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_API_VERSION", "2025-01-01-preview")
    dep = resolve_deployment_for("azure_ai_foundry", "unused-placeholder")
    assert isinstance(dep, LlmDeployment)
    assert dep.default_model == "gpt-5-nano"
    assert dep.endpoint.query_params == {"api-version": "2025-01-01-preview"}


def test_azure_ai_foundry_missing_endpoint_returns_none(
    monkeypatch, _azure_env_serialized, caplog
):
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for("azure_ai_foundry", "m", api_key="k")
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "missing_base_url"


def test_azure_ai_foundry_missing_api_key_returns_none(
    monkeypatch, _azure_env_serialized, caplog
):
    with caplog.at_level(logging.DEBUG, logger="kaizen.llm.deployment_resolver"):
        dep = resolve_deployment_for(
            "azure_ai_foundry", "m", base_url=_FOUNDRY_ENDPOINT
        )
    assert dep is None
    skipped = [r for r in caplog.records if r.message == "llm.dual_run.shadow_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "missing_api_key"


def test_azure_ai_foundry_no_longer_raises_unsupported_deployment_provider(
    _azure_env_serialized,
):
    """#1892 closes the prior Wave-B blocker: azure_ai_foundry now resolves
    (or quietly skips on missing credential) instead of raising
    UnsupportedDeploymentProvider."""
    dep = resolve_deployment_for(
        "azure_ai_foundry", "gpt-5-nano", api_key="k", base_url=_FOUNDRY_ENDPOINT
    )
    assert dep is not None
    # No known provider raises anymore -- the mechanism is retained for a
    # FUTURE provider with no confirmed wire, but the current registry is
    # empty (see kaizen.llm.deployment_resolver._UNSUPPORTED_PROVIDERS).
    from kaizen.llm.deployment_resolver import _UNSUPPORTED_PROVIDERS

    assert "azure_ai_foundry" not in _UNSUPPORTED_PROVIDERS
    assert _UNSUPPORTED_PROVIDERS == frozenset()


def test_unsupported_deployment_provider_mechanism_still_importable():
    """The typed-error mechanism itself is retained (not deleted) for a
    future known-but-unwired provider -- only azure_ai_foundry's membership
    in the unsupported set was removed."""
    assert issubclass(UnsupportedDeploymentProvider, ValueError)
    err = UnsupportedDeploymentProvider("some-future-provider")
    assert err.provider == "some-future-provider"

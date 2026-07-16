# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-A invariant #3 — Azure mapping in the shared deployment resolver.

`resolve_deployment_for("azure" | "azure_openai", ...)` builds an
`OpenAiChat`-wire deployment with an `AzureEntra` api-key auth strategy so
Azure gets shadowed (previously azure was unmapped -> never shadowed).
`azure_ai_foundry` has no confirmed four-axis wire and MUST raise a typed
`UnsupportedDeploymentProvider` (documented Wave-B blocker, NOT a silent
None-swallow per rules/zero-tolerance.md Rule 3).

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
)

_ENDPOINT = "https://myresource.openai.azure.com"


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
# azure_ai_foundry — documented Wave-B blocker, typed error (NOT None).
# ---------------------------------------------------------------------------


def test_azure_ai_foundry_raises_unsupported_not_none():
    with pytest.raises(UnsupportedDeploymentProvider) as exc:
        resolve_deployment_for("azure_ai_foundry", "some-model", api_key="k")
    assert exc.value.provider == "azure_ai_foundry"
    # It is NOT a silent None-swallow — the message names the blocker.
    assert "no confirmed" in str(exc.value)


def test_azure_ai_foundry_is_distinct_from_unmapped_none():
    """A genuinely-unknown provider returns None (best-effort skip); the
    KNOWN-but-unsupported azure_ai_foundry raises. The distinction is the
    zero-tolerance Rule 3 point: a documented blocker is loud, not silent."""
    assert resolve_deployment_for("some-unknown-xyz", "m") is None
    with pytest.raises(UnsupportedDeploymentProvider):
        resolve_deployment_for("azure_ai_foundry", "m")

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test: LlmClient.from_deployment + azure_ai_foundry preset (#1892).

Per `rules/facade-manager-detection.md` §2, this file exists at its canonical
path so absence is grep-able. Exercises the full four-axis path:
`azure_ai_foundry_preset()` / `LlmDeployment.azure_ai_foundry(...)` ->
`kaizen.llm.deployment_resolver.resolve_deployment_for("azure_ai_foundry", ...)`
-> `LlmClient.from_deployment().complete()` -> the unified Foundry
model-inference endpoint (`/models/chat/completions?api-version=...`).

Structural cases always run (offline, no network). The live case requires
real credentials (`AZURE_AI_FOUNDRY_ENDPOINT` / `AZURE_AI_FOUNDRY_API_KEY` /
`AZURE_AI_FOUNDRY_DEPLOYMENT`) and is skipped cleanly otherwise -- per
`rules/testing.md` Tier 2 policy: real infrastructure, NO mocking of the wire
layer.
"""

from __future__ import annotations

import os

import pytest

from kaizen.llm import LlmClient, LlmDeployment
from kaizen.llm.deployment import WireProtocol
from kaizen.llm.deployment_resolver import resolve_deployment_for
from kaizen.llm.presets import (
    AZURE_AI_FOUNDRY_DEFAULT_API_VERSION,
    azure_ai_foundry_preset,
)

# ---------------------------------------------------------------------------
# Structural -- always run, no network required.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_azure_ai_foundry_preset_composes_openai_chat_wire_with_api_key_auth() -> None:
    """The preset builds an OpenAiChat-wire deployment with api-key auth,
    the unified model-agnostic /models/chat/completions URL shape, and
    NO canonical_model alias (the model IS the family -- #1859 contract)."""
    dep = azure_ai_foundry_preset(
        "https://my-foundry-resource.services.ai.azure.com",
        "test-key",
        "gpt-5-nano",
    )
    assert isinstance(dep, LlmDeployment)
    assert dep.wire is WireProtocol.OpenAiChat
    assert dep.preset_name == "azure_ai_foundry"
    assert dep.default_model == "gpt-5-nano"
    assert dep.canonical_model is None
    assert dep.endpoint.path_prefix == "/models"
    assert dep.endpoint.query_params == {
        "api-version": AZURE_AI_FOUNDRY_DEFAULT_API_VERSION
    }
    # api-key header variant (NOT Authorization: Bearer) -- same shape as
    # azure_openai_preset's AzureEntra composition.
    assert dep.auth.auth_strategy_kind() == "azure_entra_api_key"


@pytest.mark.integration
def test_azure_ai_foundry_preset_composed_url_matches_the_unified_endpoint() -> None:
    """The client builds the EXACT unified model-inference URL shape
    validated live against Azure AI Foundry: {endpoint}/models/chat/
    completions?api-version=... (no deployment name in the path)."""
    dep = azure_ai_foundry_preset(
        "https://my-foundry-resource.services.ai.azure.com",
        "test-key",
        "gpt-5-nano",
    )
    client = LlmClient.from_deployment(dep)
    request = client._build_completion_request(
        [{"role": "user", "content": "hi"}],
        model=None,
        temperature=None,
        top_p=None,
        max_tokens=10,
        stop=None,
        user=None,
        stream=False,
    )
    _payload, url = client._build_completion_payload_and_url(request, stream=False)
    assert url == (
        "https://my-foundry-resource.services.ai.azure.com/models/chat/"
        f"completions?api-version={AZURE_AI_FOUNDRY_DEFAULT_API_VERSION}"
    )


@pytest.mark.integration
def test_azure_ai_foundry_classmethod_matches_module_level_preset() -> None:
    """LlmDeployment.azure_ai_foundry(...) is the classmethod call-style
    surface for the same factory (mirrors every other preset's dual form)."""
    via_classmethod = LlmDeployment.azure_ai_foundry(
        "https://my-foundry-resource.services.ai.azure.com", "test-key", "gpt-5-nano"
    )
    via_module = azure_ai_foundry_preset(
        "https://my-foundry-resource.services.ai.azure.com", "test-key", "gpt-5-nano"
    )
    assert via_classmethod.preset_name == via_module.preset_name
    assert via_classmethod.endpoint.base_url == via_module.endpoint.base_url
    assert via_classmethod.default_model == via_module.default_model


@pytest.mark.integration
def test_resolve_deployment_for_azure_ai_foundry_reads_canonical_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared resolver (`resolve_deployment_for`) resolves azure_ai_foundry
    from the canonical AZURE_AI_FOUNDRY_* env vars when no per-request
    override is supplied -- this is the SAME resolver LLMAgentNode's
    `_provider_llm_response` calls on the live path (#1892)."""
    monkeypatch.setenv(
        "AZURE_AI_FOUNDRY_ENDPOINT", "https://my-foundry-resource.services.ai.azure.com"
    )
    monkeypatch.setenv("AZURE_AI_FOUNDRY_API_KEY", "env-key")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_DEPLOYMENT", "gpt-5-nano")
    monkeypatch.setenv("AZURE_AI_FOUNDRY_API_VERSION", "2099-01-01-preview")

    dep = resolve_deployment_for("azure_ai_foundry", "unused-placeholder")
    assert dep is not None
    assert dep.preset_name == "azure_ai_foundry"
    assert dep.default_model == "gpt-5-nano"
    assert dep.endpoint.query_params == {"api-version": "2099-01-01-preview"}


@pytest.mark.integration
def test_resolve_deployment_for_azure_ai_foundry_missing_credential_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing endpoint/api-key is a quiet skip (None), matching the azure /
    azure_openai missing-credential contract -- NOT a raised error (#1892
    closes the prior UnsupportedDeploymentProvider blocker for this provider,
    so it now behaves like every other credential-gated preset)."""
    monkeypatch.delenv("AZURE_AI_FOUNDRY_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_FOUNDRY_API_KEY", raising=False)
    dep = resolve_deployment_for("azure_ai_foundry", "some-model")
    assert dep is None


# ---------------------------------------------------------------------------
# Live -- real endpoint, real credentials required. Skips cleanly otherwise.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.requires_real_llm
@pytest.mark.asyncio
async def test_azure_ai_foundry_complete_real() -> None:
    """End-to-end: LlmClient.from_deployment(azure_ai_foundry preset).complete()
    returns a real chat completion from the live Azure AI Foundry unified
    model-inference endpoint.

    Marked ``requires_real_llm`` per the root conftest's active cost-guard
    (``kailash.testing.env_cost_guard``) -- provider secrets are withheld from
    a bare test run, so this test only sees real credentials when explicitly
    opted in: ``KAIZEN_ALLOW_REAL_LLM=1 pytest -m requires_real_llm``.

    Validates the four-axis wire mechanics (four-axis config -> endpoint ->
    api-key auth -> chat round-trip) end-to-end against the real deployed
    model. The unified `/models/chat/completions` endpoint is MODEL-AGNOSTIC
    by design -- a non-OpenAI Foundry model (Llama/Mistral/Cohere) would use
    this identical wire path; this test validates the wire, not a specific
    model family.
    """
    endpoint = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT")
    api_key = os.environ.get("AZURE_AI_FOUNDRY_API_KEY")
    model = os.environ.get("AZURE_AI_FOUNDRY_DEPLOYMENT")
    if not endpoint or not api_key or not model:
        pytest.skip(
            "AZURE_AI_FOUNDRY_ENDPOINT / AZURE_AI_FOUNDRY_API_KEY / "
            "AZURE_AI_FOUNDRY_DEPLOYMENT not set; live wiring test requires "
            "real Azure AI Foundry credentials"
        )
    api_version = os.environ.get("AZURE_AI_FOUNDRY_API_VERSION")

    deployment = LlmDeployment.azure_ai_foundry(
        endpoint, api_key, model, api_version=api_version
    )
    client = LlmClient.from_deployment(deployment)

    # gpt-5-nano is a reasoning model: reasoning tokens are drawn from the
    # SAME max_completion_tokens budget, so a small budget (e.g. 16) can be
    # fully consumed by internal reasoning with zero visible output left
    # (stop_reason="length", text=""). 256 leaves headroom for reasoning +
    # a short visible answer.
    response = await client.complete(
        [{"role": "user", "content": "Say the single word: OK"}],
        max_tokens=256,
    )
    assert response["text"]
    assert isinstance(response["text"], str)
    assert response["model"]
    assert response["usage"]["total_tokens"] > 0


__all__ = []

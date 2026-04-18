# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""LlmClient.from_env() three-tier precedence tests (#498 S7)."""

from __future__ import annotations

import logging
import pytest

from kaizen.llm.client import LlmClient
from kaizen.llm.deployment import LlmDeployment
from kaizen.llm.errors import (
    InvalidUri,
    MissingCredential,
    NoKeysConfigured,
)
from kaizen.llm.from_env import (
    ENV_DEPLOYMENT_URI,
    ENV_SELECTOR,
    LEGACY_KEY_ORDER,
    SUPPORTED_SCHEMES,
    resolve_env_deployment,
)


# ---------------------------------------------------------------------------
# No-config -> NoKeysConfigured
# ---------------------------------------------------------------------------


def _clear_all_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every env var from_env() reads, so each test starts clean."""
    for var in [
        ENV_DEPLOYMENT_URI,
        ENV_SELECTOR,
        "OPENAI_API_KEY",
        "OPENAI_PROD_MODEL",
        "OPENAI_MODEL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_MODEL",
        "GEMINI_MODEL",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_RESOURCE",
        "AZURE_OPENAI_DEPLOYMENT",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_REGION",
        "BEDROCK_CLAUDE_MODEL_ID",
        "BEDROCK_MODEL",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ]:
        monkeypatch.delenv(var, raising=False)


def test_from_env_raises_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_env(monkeypatch)
    with pytest.raises(NoKeysConfigured):
        LlmClient.from_env()


# ---------------------------------------------------------------------------
# Legacy tier -- OpenAI wins when OPENAI_API_KEY is set
# ---------------------------------------------------------------------------


def test_legacy_tier_openai_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "OpenAiChat"
    assert client.deployment.default_model == "gpt-4o-mini"


def test_legacy_tier_ordering_openai_beats_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI wins when both keys are present (preserves autoselect ordering)."""
    _clear_all_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "OpenAiChat"


def test_legacy_tier_anthropic_when_no_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "AnthropicMessages"


# ---------------------------------------------------------------------------
# Selector tier -- KAILASH_LLM_PROVIDER wins over legacy
# ---------------------------------------------------------------------------


def test_selector_tier_beats_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_SELECTOR, "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")
    # Also set a legacy ANTHROPIC key -- selector still wins.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "OpenAiChat"


def test_selector_tier_unknown_preset_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_SELECTOR, "nonexistent_preset")
    with pytest.raises(NoKeysConfigured):
        LlmClient.from_env()


def test_selector_tier_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_SELECTOR, "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "AnthropicMessages"


# ---------------------------------------------------------------------------
# URI tier -- KAILASH_LLM_DEPLOYMENT wins over selector
# ---------------------------------------------------------------------------


def test_uri_tier_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://us-east-1/claude-3-opus")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "AnthropicMessages"  # Bedrock-Claude


def test_uri_tier_openai_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "openai-compat://api.groq.com/llama-3.1-70b")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = LlmClient.from_env()
    assert client.deployment.wire.name == "OpenAiChat"


def test_uri_tier_unsupported_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "foo://something/else")
    with pytest.raises(InvalidUri):
        LlmClient.from_env()


def test_uri_tier_bedrock_bad_region_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://evil.attacker.com/claude-3-opus")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")
    with pytest.raises(InvalidUri):
        LlmClient.from_env()


def test_uri_tier_missing_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://us-east-1/claude-3-opus")
    # AWS_BEARER_TOKEN_BEDROCK intentionally not set.
    with pytest.raises(MissingCredential):
        LlmClient.from_env()


# ---------------------------------------------------------------------------
# Migration-window isolation
# ---------------------------------------------------------------------------


def test_migration_warning_when_deployment_and_legacy_both_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_all_env(monkeypatch)
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://us-east-1/claude-3-opus")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")
    # Also set a legacy OPENAI_API_KEY -- coexistence triggers the warning.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")
    with caplog.at_level(logging.WARNING):
        client = LlmClient.from_env()
    # Deployment URI wins.
    assert client.deployment.wire.name == "AnthropicMessages"  # bedrock_claude
    # Warning was emitted.
    assert any(
        "legacy_and_deployment_both_configured" in rec.message for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Constants / cross-SDK parity
# ---------------------------------------------------------------------------


def test_env_var_names_stable() -> None:
    """Env var names are part of the public contract; pin them."""
    assert ENV_DEPLOYMENT_URI == "KAILASH_LLM_DEPLOYMENT"
    assert ENV_SELECTOR == "KAILASH_LLM_PROVIDER"


def test_legacy_key_order_matches_autoselect() -> None:
    """Legacy tier ordering: OpenAI > Azure > Anthropic > Google."""
    names = [v for v, _ in LEGACY_KEY_ORDER]
    assert names == [
        "OPENAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    ]


def test_supported_schemes_pinned() -> None:
    assert SUPPORTED_SCHEMES == frozenset(
        {"bedrock", "vertex", "azure", "openai-compat"}
    )


# ---------------------------------------------------------------------------
# from_deployment_sync shape
# ---------------------------------------------------------------------------


def test_from_deployment_sync_returns_same_client_shape() -> None:
    """Sync variant produces an identical client for the same deployment."""
    deployment = LlmDeployment.openai("sk-test", model="gpt-4o-mini")
    async_client = LlmClient.from_deployment(deployment)
    sync_client = LlmClient.from_deployment_sync(deployment)
    assert async_client.deployment is sync_client.deployment
    assert type(async_client) is type(sync_client)

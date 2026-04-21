# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: LlmClient.from_env() precedence matches Rust byte-for-byte.

Per ADR-0001 D7, both kailash-py and kailash-rs MUST resolve the three-tier
precedence chain in the same order with the same typed errors:

1. ``KAILASH_LLM_DEPLOYMENT`` URI     -- highest priority; strict per-scheme grammar
2. ``KAILASH_LLM_PROVIDER`` selector  -- preset name + preset-specific env keys
3. Legacy per-provider keys           -- OpenAI > Azure > Anthropic > Google
4. ``NoKeysConfigured`` typed error   -- MUST NOT silently fall back to mock

The shared JSON fixture pins the contract. This test asserts the Python
implementation matches each fixture field (env-var names, legacy key
order, URI schemes, migration-warning key, mock fallback = False) via
behavioural exercise of ``resolve_env_deployment()``.

EATP D6 compliance: when kailash-rs changes the precedence, regenerate
``fixtures/rust_from_env_precedence.json`` in the same PR.

Origin: issue #498 Session 8 (S9).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from kaizen.llm.errors import InvalidUri, NoKeysConfigured
from kaizen.llm.from_env import (
    ENV_DEPLOYMENT_URI,
    ENV_SELECTOR,
    LEGACY_KEY_ORDER,
    SUPPORTED_SCHEMES,
    resolve_env_deployment,
)


# Module-scope lock per testing.md § "Env-Var Test Isolation" -- every
# test in this file mutates process-level LLM env vars; serialize to
# prevent pytest-xdist interleaving from corrupting precedence results.
_ENV_LOCK = threading.Lock()


@pytest.fixture(autouse=True)
def env_serialized():
    """Serialize every test-body mutation of LLM env vars."""
    with _ENV_LOCK:
        yield


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    """Every test starts from a clean LLM env surface.

    Tests opt in to specific env vars via monkeypatch.setenv; delenv
    here guarantees no bleed-through from a previously-set shell.
    """
    for var in (
        ENV_DEPLOYMENT_URI,
        ENV_SELECTOR,
        "OPENAI_API_KEY",
        "OPENAI_PROD_MODEL",
        "OPENAI_MODEL",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_RESOURCE",
        "AZURE_OPENAI_DEPLOYMENT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_MODEL",
        "GEMINI_MODEL",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_REGION",
        "BEDROCK_CLAUDE_MODEL_ID",
        "BEDROCK_MODEL",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(scope="module")
def rust_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "rust_from_env_precedence.json"
    return json.loads(path.read_text())


def test_supported_schemes_match_rust(rust_fixture: dict) -> None:
    """URI scheme names are byte-identical to the Rust fixture."""
    py_schemes = set(SUPPORTED_SCHEMES)
    rust_schemes = set(rust_fixture["uri_schemes"].keys())
    assert py_schemes == rust_schemes, (
        f"URI scheme set drifted. Python: {sorted(py_schemes)}; "
        f"Rust: {sorted(rust_schemes)}. "
        f"Refresh fixtures/rust_from_env_precedence.json or patch the SDK."
    )


def test_legacy_key_order_matches_rust(rust_fixture: dict) -> None:
    """Legacy-tier precedence order (OpenAI > Azure > Anthropic > Google)."""
    py_order = [(var, preset) for var, preset in LEGACY_KEY_ORDER]
    rust_order = [
        (entry[0], entry[1])
        for entry in rust_fixture["precedence_order"][2]["key_order"]
    ]
    assert py_order == rust_order, (
        f"Legacy-key precedence drifted. Python: {py_order}; "
        f"Rust: {rust_order}. This changes which credentials win in "
        f"mixed-env processes -- must stay cross-SDK stable."
    )


def test_uri_tier_wins_over_selector(monkeypatch) -> None:
    """Tier 1 (URI) takes precedence over Tier 2 (selector).

    Behavioural: both set; the URI scheme's expected failure mode
    (missing bedrock token) fires, NOT the selector's expected failure
    mode. Proves the URI branch was taken.
    """
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://us-east-1/claude-3-opus")
    monkeypatch.setenv(ENV_SELECTOR, "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-would-resolve-selector")

    # URI tier fires; requires AWS_BEARER_TOKEN_BEDROCK, which is unset.
    # If the selector won, this would resolve openai successfully.
    from kaizen.llm.errors import MissingCredential

    with pytest.raises(MissingCredential, match="AWS_BEARER_TOKEN_BEDROCK"):
        resolve_env_deployment()


def test_selector_tier_wins_over_legacy(monkeypatch) -> None:
    """Tier 2 (selector) takes precedence over Tier 3 (legacy).

    Both ANTHROPIC selector and OPENAI_API_KEY are set; the anthropic
    path fires, not the openai path.
    """
    monkeypatch.setenv(ENV_SELECTOR, "anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy-openai")
    # Selector requires ANTHROPIC_API_KEY + ANTHROPIC_MODEL; deliberately
    # leave ANTHROPIC_MODEL unset so the selector path raises the expected
    # typed error AND we know the legacy OpenAI fallback was NOT taken.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")

    from kaizen.llm.errors import MissingCredential

    with pytest.raises(MissingCredential, match="ANTHROPIC_MODEL"):
        resolve_env_deployment()


def test_legacy_tier_used_when_no_deployment_signals(monkeypatch) -> None:
    """Tier 3 fires when URI and selector are both absent."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")

    deployment = resolve_env_deployment()
    # Legacy tier resolved to openai preset -- assert by inspecting the
    # deployment's wire protocol (OpenAiChat for openai preset).
    assert deployment.wire.value == "OpenAiChat"


def test_empty_env_raises_no_keys_configured() -> None:
    """Tier 4: every tier empty raises NoKeysConfigured, NOT silent mock."""
    with pytest.raises(NoKeysConfigured):
        resolve_env_deployment()


def test_never_fall_back_to_mock(rust_fixture: dict) -> None:
    """Cross-SDK invariant: empty env NEVER returns a mock deployment.

    Asserted directly against the Rust-fixture flag so a future "helpful"
    fallback to the mock preset is caught in the cross-SDK layer.
    """
    assert rust_fixture["never_fall_back_to_mock"] is True
    with pytest.raises(NoKeysConfigured):
        resolve_env_deployment()


def test_migration_warning_key_is_cross_sdk_stable(rust_fixture: dict) -> None:
    """The WARN key emitted when deployment + legacy coexist is frozen."""
    import inspect

    from kaizen.llm import from_env as from_env_mod

    src = inspect.getsource(from_env_mod.resolve_env_deployment)
    expected_key = rust_fixture["migration_warning_key"]
    assert expected_key in src, (
        f"Migration-warning key '{expected_key}' not found in "
        f"resolve_env_deployment source. Cross-SDK log-aggregator "
        f"dashboards filter on this exact string -- changing it breaks "
        f"every deployment's migration observability."
    )


def test_invalid_uri_scheme_rejects_typed(monkeypatch) -> None:
    """Unknown scheme in the URI tier raises InvalidUri, not NoKeysConfigured."""
    monkeypatch.setenv(ENV_DEPLOYMENT_URI, "notreal://evil.attacker.com/pwned")
    with pytest.raises(InvalidUri):
        resolve_env_deployment()

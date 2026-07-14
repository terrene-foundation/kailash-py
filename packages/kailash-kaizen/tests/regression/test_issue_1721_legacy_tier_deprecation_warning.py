# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #1721/#1720 -- legacy from_env() key-autodetect tier deprecation.

Root cause (cross-SDK, verified against both the Python and Rust SDKs):
`LlmClient.from_env()` is a three-tier resolver -- URI (`KAILASH_LLM_DEPLOYMENT`)
> preset selector (`KAILASH_LLM_PROVIDER`) > legacy per-provider-key auto-detect.
The legacy tier is a backward-compat migration layer preserving the old
`autoselect_provider()` behavior. The #1721 cross-SDK divergence (Python: 5
legacy keys incl. Azure; Rust: 10 keys, no Azure) lives ENTIRELY inside this
deprecated tier -- the canonical URI/selector surface is already cross-SDK
aligned. The fix is to DEPRECATE + retire the legacy tier, not reconcile the
two key-lists.

This is the START of the deprecation cycle (zero-tolerance.md Rule 6a):
resolving via the legacy tier ALONE (no URI, no selector) now emits a
`DeprecationWarning` + a structured `llm_client.migration.legacy_key_autodetect_
deprecated` log line naming the detected key and the canonical migration path.
Resolution behavior is UNCHANGED this release -- the legacy tier still resolves.

The pre-existing `legacy_and_deployment_both_configured` coexistence warning
(URI/selector + a legacy key both set) is untouched and MUST NOT gain the new
DeprecationWarning -- that path already resolves through the URI/selector
branch and never reaches the legacy-alone code path.
"""

from __future__ import annotations

import logging
import warnings

import pytest

from kaizen.llm.client import LlmClient
from kaizen.llm.from_env import ENV_DEPLOYMENT_URI, ENV_SELECTOR, LEGACY_KEY_ORDER


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
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_PROD_MODEL",
        "DEEPSEEK_MODEL",
    ]:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.regression
class TestIssue1721LegacyTierDeprecationWarning:
    """Regression tests for #1721/#1720: legacy from_env() tier deprecation."""

    # -- Legacy-alone resolution emits DeprecationWarning + behavior unchanged --

    def test_legacy_alone_emits_deprecation_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legacy tier resolving ALONE (no URI/selector) emits DeprecationWarning."""
        _clear_all_env(monkeypatch)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")

        with pytest.warns(DeprecationWarning, match="OPENAI_API_KEY"):
            client = LlmClient.from_env()

        # Behavior UNCHANGED this release: the legacy tier still resolves.
        assert client.deployment.wire.name == "OpenAiChat"
        assert client.deployment.default_model == "gpt-4o-mini"

    def test_legacy_alone_deprecation_message_names_canonical_migration_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Message points at KAILASH_LLM_PROVIDER=<preset> as the migration path."""
        _clear_all_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus")

        with pytest.warns(
            DeprecationWarning,
            match=r"ANTHROPIC_API_KEY.*KAILASH_LLM_PROVIDER='anthropic'",
        ):
            LlmClient.from_env()

    def test_legacy_alone_emits_structured_log_line(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A structured WARNING log line names the detected key + migration path."""
        _clear_all_env(monkeypatch)
        monkeypatch.setenv("GOOGLE_API_KEY", "gk-test")
        monkeypatch.setenv("GOOGLE_MODEL", "gemini-1.5-pro")

        with caplog.at_level(logging.WARNING):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                LlmClient.from_env()

        matching = [
            rec
            for rec in caplog.records
            if "legacy_key_autodetect_deprecated" in rec.message
        ]
        assert (
            matching
        ), "expected llm_client.migration.legacy_key_autodetect_deprecated"
        assert matching[0].legacy_env_var == "GOOGLE_API_KEY"
        assert matching[0].suggested_selector == "google"
        assert matching[0].canonical_selector_var == ENV_SELECTOR
        assert matching[0].canonical_uri_var == ENV_DEPLOYMENT_URI

    @pytest.mark.parametrize("legacy_var,preset", LEGACY_KEY_ORDER)
    def test_every_legacy_key_emits_warning_naming_its_preset(
        self, monkeypatch: pytest.MonkeyPatch, legacy_var: str, preset: str
    ) -> None:
        """Every one of the 5 legacy keys emits a warning naming ITS preset name."""
        _clear_all_env(monkeypatch)
        # Set the minimum env vars each legacy key's build path requires.
        if legacy_var == "OPENAI_API_KEY":
            monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
            monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")
        elif legacy_var == "AZURE_OPENAI_API_KEY":
            monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-test")
            monkeypatch.setenv("AZURE_OPENAI_RESOURCE", "myresource")
            monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "mydeployment")
        elif legacy_var == "ANTHROPIC_API_KEY":
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
            monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-opus")
        elif legacy_var == "GOOGLE_API_KEY":
            monkeypatch.setenv("GOOGLE_API_KEY", "gk-test")
            monkeypatch.setenv("GOOGLE_MODEL", "gemini-1.5-pro")
        elif legacy_var == "DEEPSEEK_API_KEY":
            monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
            monkeypatch.setenv("DEEPSEEK_PROD_MODEL", "deepseek-chat")

        with pytest.warns(
            DeprecationWarning, match=rf"{legacy_var}.*KAILASH_LLM_PROVIDER='{preset}'"
        ):
            client = LlmClient.from_env()

        # Behavior unchanged: a valid deployment is still returned.
        assert client.deployment is not None

    # -- URI / selector tiers do NOT emit the legacy-alone warning --

    def test_uri_tier_does_not_emit_legacy_deprecation_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_all_env(monkeypatch)
        monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://us-east-1/claude-3-opus")
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = LlmClient.from_env()

        dep_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "legacy per-provider-key auto-detect" in str(w.message)
        ]
        assert dep_warnings == []
        assert client.deployment.wire.name == "AnthropicMessages"

    def test_selector_tier_does_not_emit_legacy_deprecation_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_all_env(monkeypatch)
        monkeypatch.setenv(ENV_SELECTOR, "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = LlmClient.from_env()

        dep_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "legacy per-provider-key auto-detect" in str(w.message)
        ]
        assert dep_warnings == []
        assert client.deployment.wire.name == "OpenAiChat"

    def test_coexistence_path_unchanged_no_new_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """URI + legacy key both set: existing coexistence warning fires,
        the NEW legacy-alone DeprecationWarning does NOT (per spec: 'Keep the
        existing legacy_and_deployment_both_configured warning unchanged')."""
        _clear_all_env(monkeypatch)
        monkeypatch.setenv(ENV_DEPLOYMENT_URI, "bedrock://us-east-1/claude-3-opus")
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
        monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-4o-mini")

        with caplog.at_level(logging.WARNING):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                client = LlmClient.from_env()

        # Deployment (URI) tier wins -- behavior unchanged.
        assert client.deployment.wire.name == "AnthropicMessages"

        # Existing coexistence WARNING log line still fires.
        assert any(
            "legacy_and_deployment_both_configured" in rec.message
            for rec in caplog.records
        )
        # The NEW legacy-alone structured log line does NOT fire on this path.
        assert not any(
            "legacy_key_autodetect_deprecated" in rec.message for rec in caplog.records
        )
        # The NEW legacy-alone DeprecationWarning does NOT fire on this path.
        dep_warnings = [
            w
            for w in caught
            if issubclass(w.category, DeprecationWarning)
            and "legacy per-provider-key auto-detect" in str(w.message)
        ]
        assert dep_warnings == []

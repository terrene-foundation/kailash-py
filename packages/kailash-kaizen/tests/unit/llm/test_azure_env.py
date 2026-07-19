# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``kaizen.llm.azure_env.resolve_azure_env``.

The helper was relocated here from ``kaizen.nodes.ai.azure_detection`` in
#1820 when the legacy unified-azure provider stack was retired; the
four-axis Azure deployment builder (``deployment_resolver._resolve_azure_deployment``)
and the config-layer Azure helpers (``kaizen.config.providers``) are the
surviving consumers. This preserves the canonical/legacy/deprecation
coverage that used to live in ``tests/unit/nodes/ai/test_azure_detection.py``.

Tier-1 offline + deterministic (env vars only, no network).
"""

from __future__ import annotations

import warnings

from kaizen.llm.azure_env import resolve_azure_env


class TestResolveAzureEnv:
    """Unit tests for the resolve_azure_env() helper."""

    def test_returns_canonical_value(self, monkeypatch):
        """Should return the canonical env var value when set."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://canonical.openai.azure.com")

        result = resolve_azure_env("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT")
        assert result == "https://canonical.openai.azure.com"

    def test_returns_legacy_with_deprecation_warning(self, monkeypatch):
        """Should return legacy value and emit DeprecationWarning."""
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://legacy.openai.azure.com")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_azure_env("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT")

        assert result == "https://legacy.openai.azure.com"
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "AZURE_OPENAI_ENDPOINT" in str(w[0].message)
        assert "AZURE_ENDPOINT" in str(w[0].message)

    def test_canonical_takes_precedence_over_legacy(self, monkeypatch):
        """Canonical var should win when both are set, no warning emitted."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://canonical.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://legacy.openai.azure.com")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_azure_env("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT")

        assert result == "https://canonical.openai.azure.com"
        assert len(w) == 0  # No deprecation warning

    def test_returns_none_when_nothing_set(self, monkeypatch):
        """Should return None when neither canonical nor legacy is set."""
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)

        result = resolve_azure_env("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT")
        assert result is None

    def test_multiple_legacy_vars_checks_in_order(self, monkeypatch):
        """Should check legacy vars in order and warn on the first match."""
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://foundry.inference.ai.azure.com"
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_azure_env(
                "AZURE_ENDPOINT",
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_AI_INFERENCE_ENDPOINT",
            )

        assert result == "https://foundry.inference.ai.azure.com"
        assert len(w) == 1
        assert "AZURE_AI_INFERENCE_ENDPOINT" in str(w[0].message)

    def test_no_legacy_args(self, monkeypatch):
        """Should work with zero legacy arguments."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")

        result = resolve_azure_env("AZURE_ENDPOINT")
        assert result == "https://test.openai.azure.com"

    def test_no_legacy_args_returns_none(self, monkeypatch):
        """Should return None when canonical not set and no legacy provided."""
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)

        result = resolve_azure_env("AZURE_ENDPOINT")
        assert result is None

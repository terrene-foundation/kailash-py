"""Unit tests for Azure backend detection.

Tests the AzureBackendDetector class which auto-detects whether to use
Azure OpenAI Service or Azure AI Foundry based on endpoint URL patterns.

Also tests the resolve_azure_env() helper for canonical/legacy env var
resolution with deprecation warnings.
"""

import os
import warnings

import pytest

from kaizen.nodes.ai.azure_detection import (
    AZURE_AI_FOUNDRY_PATTERNS,
    AZURE_OPENAI_PATTERNS,
    AzureBackendDetector,
    resolve_azure_env,
)


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


class TestAzureBackendDetector:
    """Unit tests for Azure backend detection logic."""

    # Pattern Matching Tests - Azure OpenAI

    @pytest.mark.parametrize(
        "endpoint,expected",
        [
            ("https://my-resource.openai.azure.com", "azure_openai"),
            ("https://my-resource.openai.azure.com/", "azure_openai"),
            ("https://eastus.openai.azure.com", "azure_openai"),
            ("https://my-resource.privatelink.openai.azure.com", "azure_openai"),
            ("https://MYRESOURCE.OPENAI.AZURE.COM", "azure_openai"),
        ],
    )
    def test_detects_azure_openai_patterns(self, monkeypatch, endpoint, expected):
        """Should detect Azure OpenAI from standard endpoint patterns."""
        monkeypatch.setenv("AZURE_ENDPOINT", endpoint)
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        assert backend == expected
        assert detector.detection_source == "pattern"
        assert config["endpoint"] == endpoint

    # Pattern Matching Tests - AI Foundry

    @pytest.mark.parametrize(
        "endpoint,expected",
        [
            ("https://my-model.inference.ai.azure.com", "azure_ai_foundry"),
            ("https://my-resource.services.ai.azure.com", "azure_ai_foundry"),
            (
                "https://my-resource.services.ai.azure.com/models/gpt-4",
                "azure_ai_foundry",
            ),
        ],
    )
    def test_detects_ai_foundry_patterns(self, monkeypatch, endpoint, expected):
        """Should detect AI Foundry from standard endpoint patterns."""
        monkeypatch.setenv("AZURE_ENDPOINT", endpoint)
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        assert backend == expected
        assert detector.detection_source == "pattern"

    # Default Behavior Tests

    def test_unknown_pattern_defaults_to_openai(self, monkeypatch):
        """Should default to Azure OpenAI for unknown endpoint patterns."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://custom-proxy.company.com/azure")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        backend, _ = detector.detect()

        assert backend == "azure_openai"
        assert detector.detection_source == "default"

    def test_unknown_pattern_logs_warning(self, monkeypatch, caplog):
        """Should log warning for unknown endpoint patterns with guidance."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://custom.endpoint.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        import logging

        with caplog.at_level(logging.WARNING):
            detector = AzureBackendDetector()
            detector.detect()

        assert "Could not determine Azure backend" in caplog.text
        assert (
            "AZURE_BACKEND=openai" in caplog.text
            or "AZURE_BACKEND=foundry" in caplog.text
        )

    # Explicit Override Tests

    @pytest.mark.parametrize(
        "override,expected",
        [
            ("openai", "azure_openai"),
            ("azure_openai", "azure_openai"),
            ("azureopenai", "azure_openai"),
            ("foundry", "azure_ai_foundry"),
            ("ai_foundry", "azure_ai_foundry"),
            ("azure_ai_foundry", "azure_ai_foundry"),
            ("aifoundry", "azure_ai_foundry"),
        ],
    )
    def test_explicit_override_respected(self, monkeypatch, override, expected):
        """Should respect AZURE_BACKEND environment variable override."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://any.endpoint.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_BACKEND", override)

        detector = AzureBackendDetector()
        backend, _ = detector.detect()

        assert backend == expected
        assert detector.detection_source == "explicit"

    def test_explicit_override_invalid_raises_error(self, monkeypatch):
        """Should raise error for invalid AZURE_BACKEND value."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://any.endpoint.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_BACKEND", "invalid_backend")

        detector = AzureBackendDetector()
        with pytest.raises(ValueError, match="Invalid AZURE_BACKEND"):
            detector.detect()

    # Configuration Resolution Tests

    def test_no_config_returns_none(self, monkeypatch):
        """Should return None when no Azure configuration is available."""
        for var in [
            "AZURE_ENDPOINT",
            "AZURE_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_AI_INFERENCE_ENDPOINT",
            "AZURE_AI_INFERENCE_API_KEY",
            "AZURE_BACKEND",
        ]:
            monkeypatch.delenv(var, raising=False)

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        assert backend is None
        assert config == {}

    def test_legacy_azure_openai_vars(self, monkeypatch):
        """Should support legacy AZURE_OPENAI_* environment variables."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://legacy.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "legacy-key")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            detector = AzureBackendDetector()
            backend, config = detector.detect()

        assert backend == "azure_openai"
        assert config["endpoint"] == "https://legacy.openai.azure.com"

    def test_legacy_ai_foundry_vars(self, monkeypatch):
        """Should support legacy AZURE_AI_INFERENCE_* environment variables."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://legacy.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "legacy-key")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            detector = AzureBackendDetector()
            backend, config = detector.detect()

        assert backend == "azure_ai_foundry"
        assert config["endpoint"] == "https://legacy.inference.ai.azure.com"

    def test_canonical_takes_precedence_over_legacy(self, monkeypatch):
        """Canonical AZURE_ENDPOINT should take precedence over legacy vars."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://unified.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "unified-key")
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://legacy.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "legacy-key")

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        assert backend == "azure_openai"
        assert config["endpoint"] == "https://unified.openai.azure.com"

    def test_legacy_vars_emit_deprecation_warning(self, monkeypatch):
        """Legacy env vars should emit DeprecationWarning."""
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_API_KEY", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://legacy.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "legacy-key")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            detector = AzureBackendDetector()
            detector.detect()

        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) >= 1
        messages = [str(x.message) for x in deprecation_warnings]
        assert any("AZURE_OPENAI_ENDPOINT" in m for m in messages)

    # API Version Tests

    def test_api_version_from_canonical_env(self, monkeypatch):
        """Should read API version from canonical AZURE_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01-preview")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2025-01-01-preview"

    def test_api_version_from_legacy_env_with_warning(self, monkeypatch):
        """Should read API version from legacy var with deprecation warning."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            detector = AzureBackendDetector()
            _, config = detector.detect()

        assert config["api_version"] == "2025-04-01-preview"
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        messages = [str(x.message) for x in deprecation_warnings]
        assert any("AZURE_OPENAI_API_VERSION" in m for m in messages)

    def test_api_version_default(self, monkeypatch):
        """Should use default API version when not specified."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2024-10-21"

    # Property Tests

    def test_detected_backend_property(self, monkeypatch):
        """Should expose detected_backend property."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        detector.detect()

        assert detector.detected_backend == "azure_openai"

    def test_detection_source_property(self, monkeypatch):
        """Should expose detection_source property."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        detector.detect()

        assert detector.detection_source in ("pattern", "default", "explicit")


class TestPatternConstants:
    """Tests for pattern constant definitions."""

    def test_openai_patterns_defined(self):
        """Azure OpenAI patterns should be defined."""
        assert len(AZURE_OPENAI_PATTERNS) >= 2
        assert any("openai" in p and "azure" in p for p in AZURE_OPENAI_PATTERNS)

    def test_foundry_patterns_defined(self):
        """Azure AI Foundry patterns should be defined."""
        assert len(AZURE_AI_FOUNDRY_PATTERNS) >= 2
        assert any("inference" in p and "azure" in p for p in AZURE_AI_FOUNDRY_PATTERNS)

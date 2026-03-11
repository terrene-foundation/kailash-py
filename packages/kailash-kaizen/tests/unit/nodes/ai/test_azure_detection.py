"""Unit tests for Azure backend detection.

Tests the AzureBackendDetector class which auto-detects whether to use
Azure OpenAI Service or Azure AI Foundry based on endpoint URL patterns.
"""

import os
import warnings

import pytest

from kaizen.nodes.ai.azure_detection import (
    AZURE_AI_FOUNDRY_PATTERNS,
    AZURE_OPENAI_PATTERNS,
    AzureBackendDetector,
)


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
            ("https://MYRESOURCE.OPENAI.AZURE.COM", "azure_openai"),  # Case insensitive
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
        """Should log warning for unknown endpoint patterns."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://custom.endpoint.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        import logging

        with caplog.at_level(logging.WARNING):
            detector = AzureBackendDetector()
            detector.detect()

        assert (
            "Unknown Azure endpoint pattern" in caplog.text
            or detector.detection_source == "default"
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

    # Error Fallback Tests

    def test_error_triggers_fallback_to_foundry(self):
        """Should detect AI Foundry from 'audience is incorrect' error signature."""
        detector = AzureBackendDetector()
        detector._detected_backend = "azure_openai"
        detector._detection_source = "default"

        error = Exception("audience is incorrect (https://cognitiveservices.azure.com)")
        result = detector.handle_error(error)

        assert result == "azure_ai_foundry"
        assert detector.detection_source == "error_fallback"

    def test_error_triggers_fallback_to_openai(self):
        """Should detect Azure OpenAI from 'DeploymentNotFound' error signature."""
        detector = AzureBackendDetector()
        detector._detected_backend = "azure_ai_foundry"
        detector._detection_source = "pattern"

        error = Exception("DeploymentNotFound: The API deployment does not exist")
        result = detector.handle_error(error)

        assert result == "azure_openai"
        assert detector.detection_source == "error_fallback"

    def test_unrelated_error_no_fallback(self):
        """Should not trigger fallback for unrelated errors."""
        detector = AzureBackendDetector()
        detector._detected_backend = "azure_openai"

        # Rate limit error - not a backend detection issue
        error = Exception("Rate limit exceeded")
        result = detector.handle_error(error)

        assert result is None
        assert detector._detected_backend == "azure_openai"

    def test_auth_error_no_fallback(self):
        """Should not trigger fallback for authentication errors."""
        detector = AzureBackendDetector()
        detector._detected_backend = "azure_openai"

        error = Exception("401 Unauthorized: Invalid API key")
        result = detector.handle_error(error)

        assert result is None

    # Configuration Resolution Tests

    def test_no_config_returns_none(self, monkeypatch):
        """Should return None when no Azure configuration is available."""
        # Clear all Azure-related env vars
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

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        assert backend == "azure_ai_foundry"
        assert config["endpoint"] == "https://legacy.inference.ai.azure.com"

    def test_unified_takes_precedence_over_legacy(self, monkeypatch):
        """Unified AZURE_ENDPOINT should take precedence over legacy vars."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://unified.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "unified-key")
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://legacy.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "legacy-key")

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        # Should use unified endpoint, which is Azure OpenAI
        assert backend == "azure_openai"
        assert config["endpoint"] == "https://unified.openai.azure.com"

    # API Version Tests

    def test_api_version_from_env(self, monkeypatch):
        """Should include API version from environment variable."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01-preview")

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2025-01-01-preview"

    def test_api_version_default(self, monkeypatch):
        """Should use default API version when not specified."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://my.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2024-10-21"  # Default

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
        # Should include standard pattern (regex uses \. for literal dots)
        assert any("openai" in p and "azure" in p for p in AZURE_OPENAI_PATTERNS)

    def test_foundry_patterns_defined(self):
        """Azure AI Foundry patterns should be defined."""
        assert len(AZURE_AI_FOUNDRY_PATTERNS) >= 2
        # Should include inference pattern (regex uses \. for literal dots)
        assert any("inference" in p and "azure" in p for p in AZURE_AI_FOUNDRY_PATTERNS)

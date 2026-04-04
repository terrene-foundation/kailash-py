"""Regression: #257 — AZURE_OPENAI_API_VERSION env var not read.

azure_backends.py only read AZURE_API_VERSION, but Azure documentation
and standard tooling uses AZURE_OPENAI_API_VERSION. Users had to set
both env vars to satisfy both Kaizen and other Azure tools.

Fix: Read AZURE_OPENAI_API_VERSION first, fallback to AZURE_API_VERSION.
Applied in both azure_backends.py and azure_detection.py.
"""

import pytest

from kaizen.nodes.ai.azure_backends import AzureOpenAIBackend
from kaizen.nodes.ai.azure_detection import AzureBackendDetector


@pytest.mark.regression
class TestIssue257AzureApiVersionEnv:
    """Regression tests for #257: AZURE_OPENAI_API_VERSION support."""

    # AzureOpenAIBackend tests

    def test_backend_reads_azure_openai_api_version(self, monkeypatch):
        """Backend should prefer AZURE_OPENAI_API_VERSION."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2025-04-01-preview"

    def test_backend_falls_back_to_azure_api_version(self, monkeypatch):
        """Backend should fall back to AZURE_API_VERSION when specific var not set."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_API_VERSION", "2024-12-01")

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2024-12-01"

    def test_backend_prefers_specific_over_generic(self, monkeypatch):
        """AZURE_OPENAI_API_VERSION should take precedence over AZURE_API_VERSION."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        monkeypatch.setenv("AZURE_API_VERSION", "2024-10-21")

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2025-04-01-preview"

    def test_backend_uses_default_when_no_env_vars(self, monkeypatch):
        """Backend should use default API version when no env vars set."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2024-10-21"  # DEFAULT_API_VERSION

    # AzureBackendDetector tests

    def test_detector_config_reads_azure_openai_api_version(self, monkeypatch):
        """Detector config should prefer AZURE_OPENAI_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2025-04-01-preview"

    def test_detector_config_falls_back_to_azure_api_version(self, monkeypatch):
        """Detector config should fall back to AZURE_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_API_VERSION", "2024-12-01")

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2024-12-01"

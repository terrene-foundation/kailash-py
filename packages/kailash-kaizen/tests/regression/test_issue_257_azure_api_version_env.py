"""Regression: #257 -- AZURE_OPENAI_API_VERSION env var not read.

Azure documentation and standard tooling uses AZURE_OPENAI_API_VERSION.
The original fix read AZURE_OPENAI_API_VERSION first, falling back to
AZURE_API_VERSION.

After the M2 Azure simplification (canonical env var refactor), the
priority is now:
  1. AZURE_API_VERSION (canonical)
  2. AZURE_OPENAI_API_VERSION (legacy, emits DeprecationWarning)
  3. Default: 2024-10-21

Both vars continue to work. AZURE_OPENAI_API_VERSION now emits a
DeprecationWarning guiding users to AZURE_API_VERSION.
"""

import warnings

import pytest

from kaizen.nodes.ai.azure_backends import AzureOpenAIBackend
from kaizen.nodes.ai.azure_detection import AzureBackendDetector


@pytest.mark.regression
class TestIssue257AzureApiVersionEnv:
    """Regression tests for #257: AZURE_OPENAI_API_VERSION support."""

    # AzureOpenAIBackend tests

    def test_backend_reads_canonical_azure_api_version(self, monkeypatch):
        """Backend should prefer canonical AZURE_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-04-01-preview")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2025-04-01-preview"

    def test_backend_reads_legacy_azure_openai_api_version(self, monkeypatch):
        """Backend should still read legacy AZURE_OPENAI_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            backend = AzureOpenAIBackend()

        assert backend._api_version == "2025-04-01-preview"
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        messages = [str(x.message) for x in deprecation_warnings]
        assert any("AZURE_OPENAI_API_VERSION" in m for m in messages)

    def test_backend_falls_back_to_azure_api_version(self, monkeypatch):
        """Backend should use AZURE_API_VERSION as canonical."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_API_VERSION", "2024-12-01")

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2024-12-01"

    def test_backend_canonical_wins_over_legacy(self, monkeypatch):
        """AZURE_API_VERSION (canonical) should take precedence over AZURE_OPENAI_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2025-01-01"

    def test_backend_uses_default_when_no_env_vars(self, monkeypatch):
        """Backend should use default API version when no env vars set."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2024-10-21"  # DEFAULT_API_VERSION

    # AzureBackendDetector tests

    def test_detector_config_reads_canonical_azure_api_version(self, monkeypatch):
        """Detector config should prefer canonical AZURE_API_VERSION."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-04-01-preview")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2025-04-01-preview"

    def test_detector_config_reads_legacy_with_warning(self, monkeypatch):
        """Detector config should read legacy var with deprecation warning."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
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

    def test_detector_config_falls_back_to_azure_api_version(self, monkeypatch):
        """Detector config should use AZURE_API_VERSION as canonical."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_API_VERSION", "2024-12-01")

        detector = AzureBackendDetector()
        _, config = detector.detect()

        assert config["api_version"] == "2024-12-01"

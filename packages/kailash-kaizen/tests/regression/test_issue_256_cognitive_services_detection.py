"""Regression: #256 — Azure endpoint detection missing cognitiveservices.azure.com pattern.

Endpoints using *.cognitiveservices.azure.com (India South, other regions) without
an /openai path segment were not recognized, causing a noisy warning on every
LLM call even though the fallback to azure_openai was correct.

Fix: Added *.cognitiveservices.azure.com to AZURE_OPENAI_PATTERNS.
"""

import pytest

from kaizen.nodes.ai.azure_detection import AzureBackendDetector


@pytest.mark.regression
class TestIssue256CognitiveServicesDetection:
    """Regression tests for #256: cognitiveservices.azure.com detection."""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://myresource.cognitiveservices.azure.com",
            "https://myresource.cognitiveservices.azure.com/",
            "https://india-south-resource.cognitiveservices.azure.com",
            "https://MYRESOURCE.COGNITIVESERVICES.AZURE.COM",
        ],
    )
    def test_cognitiveservices_detected_as_azure_openai(self, monkeypatch, endpoint):
        """cognitiveservices.azure.com endpoints should be detected as azure_openai."""
        monkeypatch.setenv("AZURE_ENDPOINT", endpoint)
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        backend, config = detector.detect()

        assert backend == "azure_openai"
        assert detector.detection_source == "pattern", (
            f"Expected pattern detection, got {detector.detection_source} "
            f"(warning would fire on 'default')"
        )

    def test_cognitiveservices_with_openai_path_still_detected(self, monkeypatch):
        """Legacy cognitiveservices.azure.com/openai path should still match."""
        monkeypatch.setenv(
            "AZURE_ENDPOINT",
            "https://myresource.cognitiveservices.azure.com/openai",
        )
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        detector = AzureBackendDetector()
        backend, _ = detector.detect()

        assert backend == "azure_openai"
        assert detector.detection_source == "pattern"

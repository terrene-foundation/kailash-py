"""Regression: #257 -- AZURE_OPENAI_API_VERSION env var not read.

Azure documentation and standard tooling uses AZURE_OPENAI_API_VERSION.
The original fix read AZURE_OPENAI_API_VERSION first, falling back to
AZURE_API_VERSION.

After the M2 Azure simplification (canonical env var refactor), the
priority is now:
  1. AZURE_API_VERSION (canonical)
  2. AZURE_OPENAI_API_VERSION (legacy, emits DeprecationWarning)
  3. Default: AZURE_OPENAI_DEFAULT_API_VERSION

Both vars continue to work. AZURE_OPENAI_API_VERSION now emits a
DeprecationWarning guiding users to AZURE_API_VERSION.

#1820 MIGRATION: the legacy ``AzureOpenAIBackend`` / ``AzureBackendDetector``
this test used to assert against were RETIRED with the unified-azure provider
stack. The #257 canonical/legacy/default api-version resolution is now owned by
the four-axis Azure deployment builder
(``kaizen.llm.deployment_resolver._resolve_azure_deployment``), which resolves
the version via the shared ``kaizen.llm.azure_env.resolve_azure_env`` and stamps
it into the deployment's ``?api-version=`` query parameter. This test now pins
that behavior against the surviving four-axis surface.
"""

import warnings

import pytest

from kaizen.llm.deployment_resolver import resolve_deployment_for
from kaizen.llm.presets import AZURE_OPENAI_DEFAULT_API_VERSION

# Azure DEPLOYMENT name (a resource identifier interpolated into the request
# URL path), NOT an LLM model id — this test is offline and only builds a
# deployment object, never contacting a provider.
_DEPLOYMENT = "test-deployment"


def _resolved_api_version(monkeypatch) -> str:
    """Resolve an azure_openai four-axis deployment and return its api-version.

    Requires endpoint + api-key so the builder does not short-circuit to None.
    """
    monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    deployment = resolve_deployment_for("azure_openai", _DEPLOYMENT)
    assert deployment is not None
    return deployment.endpoint.query_params["api-version"]


@pytest.mark.regression
class TestIssue257AzureApiVersionEnv:
    """Regression tests for #257: AZURE_OPENAI_API_VERSION support (four-axis)."""

    def test_reads_canonical_azure_api_version(self, monkeypatch):
        """Four-axis builder should prefer canonical AZURE_API_VERSION."""
        monkeypatch.setenv("AZURE_API_VERSION", "2025-04-01-preview")
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

        assert _resolved_api_version(monkeypatch) == "2025-04-01-preview"

    def test_reads_legacy_azure_openai_api_version(self, monkeypatch):
        """Four-axis builder should still read legacy AZURE_OPENAI_API_VERSION."""
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resolved = _resolved_api_version(monkeypatch)

        assert resolved == "2025-04-01-preview"
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        messages = [str(x.message) for x in deprecation_warnings]
        assert any("AZURE_OPENAI_API_VERSION" in m for m in messages)

    def test_canonical_wins_over_legacy(self, monkeypatch):
        """AZURE_API_VERSION (canonical) should take precedence over legacy."""
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

        assert _resolved_api_version(monkeypatch) == "2025-01-01"

    def test_uses_default_when_no_env_vars(self, monkeypatch):
        """Four-axis builder should use the default api version when none set."""
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        assert _resolved_api_version(monkeypatch) == AZURE_OPENAI_DEFAULT_API_VERSION

"""Tests for provider registry integration with UnifiedAzureProvider."""

import pytest

from kaizen.nodes.ai.ai_providers import PROVIDERS, get_provider
from kaizen.nodes.ai.unified_azure_provider import UnifiedAzureProvider


class TestAzureProviderRegistry:
    """Tests for Azure provider registration."""

    def test_azure_key_registered(self):
        """'azure' key should be in PROVIDERS."""
        assert "azure" in PROVIDERS

    def test_azure_uses_unified_provider(self):
        """'azure' should map to UnifiedAzureProvider."""
        assert PROVIDERS["azure"] is UnifiedAzureProvider

    def test_azure_openai_alias_registered(self):
        """'azure_openai' alias should be in PROVIDERS."""
        assert "azure_openai" in PROVIDERS

    def test_azure_openai_uses_unified_provider(self):
        """'azure_openai' alias should map to UnifiedAzureProvider."""
        assert PROVIDERS["azure_openai"] is UnifiedAzureProvider

    def test_get_provider_returns_unified_azure(self, monkeypatch):
        """get_provider('azure') should return UnifiedAzureProvider instance."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = get_provider("azure")

        assert isinstance(provider, UnifiedAzureProvider)
        assert provider.is_available() is True

    def test_get_provider_azure_openai_alias(self, monkeypatch):
        """get_provider('azure_openai') should return UnifiedAzureProvider instance."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = get_provider("azure_openai")

        assert isinstance(provider, UnifiedAzureProvider)

"""Unit tests for Azure AI Foundry provider."""

import pytest
from kaizen.nodes.ai.ai_providers import AzureAIFoundryProvider


class TestAzureAIFoundryProvider:
    """Unit tests for Azure AI Foundry provider."""

    def test_is_available_with_credentials(self, monkeypatch):
        """Should return True when Azure credentials are set."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")
        provider = AzureAIFoundryProvider()
        assert provider.is_available() is True

    def test_is_available_without_endpoint(self, monkeypatch):
        """Should return False when endpoint is missing."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")
        provider = AzureAIFoundryProvider()
        # Reset cached availability
        provider._available = None
        assert provider.is_available() is False

    def test_is_available_without_api_key(self, monkeypatch):
        """Should return False when API key is missing."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        provider = AzureAIFoundryProvider()
        # Reset cached availability
        provider._available = None
        assert provider.is_available() is False

    def test_is_available_without_both(self, monkeypatch):
        """Should return False when both credentials are missing."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        provider = AzureAIFoundryProvider()
        provider._available = None
        assert provider.is_available() is False

    def test_capabilities(self):
        """Should report both chat and embeddings capabilities."""
        provider = AzureAIFoundryProvider()
        caps = provider.get_capabilities()
        assert caps["chat"] is True
        assert caps["embeddings"] is True
        assert provider.supports_chat() is True
        assert provider.supports_embeddings() is True

    def test_get_model_info_text_embedding_3_small(self):
        """Should return correct dimensions for text-embedding-3-small."""
        provider = AzureAIFoundryProvider()
        info = provider.get_model_info("text-embedding-3-small")
        assert info["dimensions"] == 1536
        assert info["max_tokens"] == 8191
        assert info["capabilities"]["variable_dimensions"] is True

    def test_get_model_info_text_embedding_3_large(self):
        """Should return correct dimensions for text-embedding-3-large."""
        provider = AzureAIFoundryProvider()
        info = provider.get_model_info("text-embedding-3-large")
        assert info["dimensions"] == 3072
        assert info["max_tokens"] == 8191

    def test_get_model_info_text_embedding_ada_002(self):
        """Should return correct dimensions for text-embedding-ada-002."""
        provider = AzureAIFoundryProvider()
        info = provider.get_model_info("text-embedding-ada-002")
        assert info["dimensions"] == 1536
        assert info["capabilities"]["variable_dimensions"] is False

    def test_get_model_info_unknown_model(self):
        """Should return default info for unknown models."""
        provider = AzureAIFoundryProvider()
        info = provider.get_model_info("unknown-model")
        assert info["dimensions"] == 1536  # Default
        assert "unknown-model" in info["description"]

    def test_use_async_initialization(self):
        """Should accept use_async parameter."""
        provider = AzureAIFoundryProvider(use_async=True)
        assert provider._use_async is True

        provider = AzureAIFoundryProvider(use_async=False)
        assert provider._use_async is False

    def test_separate_clients_initialized_to_none(self):
        """Should initialize all client references to None."""
        provider = AzureAIFoundryProvider()
        assert provider._sync_chat_client is None
        assert provider._sync_embed_client is None
        assert provider._async_chat_client is None
        assert provider._async_embed_client is None

    def test_get_endpoint_raises_without_env(self, monkeypatch):
        """Should raise RuntimeError when endpoint not set."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        provider = AzureAIFoundryProvider()
        with pytest.raises(RuntimeError, match="AZURE_AI_INFERENCE_ENDPOINT"):
            provider._get_endpoint()

    def test_get_endpoint_returns_env_value(self, monkeypatch):
        """Should return endpoint from environment variable."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://my-endpoint.azure.com"
        )
        provider = AzureAIFoundryProvider()
        assert provider._get_endpoint() == "https://my-endpoint.azure.com"

    def test_model_cache(self):
        """Should cache model info for repeated lookups."""
        provider = AzureAIFoundryProvider()

        # First call
        info1 = provider.get_model_info("text-embedding-3-small")

        # Second call should use cache
        info2 = provider.get_model_info("text-embedding-3-small")

        assert info1 is info2
        assert "text-embedding-3-small" in provider._model_cache

    def test_format_tool_calls_empty(self):
        """Should return empty list when no tool calls."""

        class MockMessage:
            tool_calls = None

        provider = AzureAIFoundryProvider()
        result = provider._format_tool_calls(MockMessage())
        assert result == []

    def test_format_tool_calls_with_data(self):
        """Should format tool calls correctly."""

        class MockFunction:
            name = "get_weather"
            arguments = '{"location": "Paris"}'

        class MockToolCall:
            id = "call_123"
            type = "function"
            function = MockFunction()

        class MockMessage:
            tool_calls = [MockToolCall()]

        provider = AzureAIFoundryProvider()
        result = provider._format_tool_calls(MockMessage())

        assert len(result) == 1
        assert result[0]["id"] == "call_123"
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "get_weather"
        assert result[0]["function"]["arguments"] == '{"location": "Paris"}'

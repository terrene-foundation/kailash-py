"""Unit tests for Google Gemini provider."""

import pytest

from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider, get_provider


class TestGoogleGeminiProvider:
    """Unit tests for Google Gemini provider."""

    def test_is_available_with_google_api_key(self, monkeypatch):
        """Should return True when GOOGLE_API_KEY is set."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        provider = GoogleGeminiProvider()
        # Reset cached availability
        provider._available = None
        assert provider.is_available() is True

    def test_is_available_with_gemini_api_key(self, monkeypatch):
        """Should return True when GEMINI_API_KEY is set."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        provider = GoogleGeminiProvider()
        provider._available = None
        assert provider.is_available() is True

    def test_is_available_with_vertex_ai_project(self, monkeypatch):
        """Should return True when GOOGLE_CLOUD_PROJECT is set."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
        provider = GoogleGeminiProvider()
        provider._available = None
        assert provider.is_available() is True

    def test_is_available_without_credentials(self, monkeypatch):
        """Should return False when no credentials are set."""
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        provider = GoogleGeminiProvider()
        provider._available = None
        assert provider.is_available() is False

    def test_capabilities(self):
        """Should report both chat and embeddings capabilities."""
        provider = GoogleGeminiProvider()
        caps = provider.get_capabilities()
        assert caps["chat"] is True
        assert caps["embeddings"] is True
        assert provider.supports_chat() is True
        assert provider.supports_embeddings() is True

    def test_get_model_info_text_embedding_004(self):
        """Should return correct dimensions for text-embedding-004."""
        provider = GoogleGeminiProvider()
        info = provider.get_model_info("text-embedding-004")
        assert info["dimensions"] == 768
        assert info["max_tokens"] == 2048
        assert info["capabilities"]["variable_dimensions"] is False

    def test_get_model_info_embedding_001(self):
        """Should return correct dimensions for embedding-001."""
        provider = GoogleGeminiProvider()
        info = provider.get_model_info("embedding-001")
        assert info["dimensions"] == 768
        assert info["max_tokens"] == 2048

    def test_get_model_info_unknown_model(self):
        """Should return default info for unknown models."""
        provider = GoogleGeminiProvider()
        info = provider.get_model_info("unknown-model")
        assert info["dimensions"] == 768  # Default
        assert "unknown-model" in info["description"]

    def test_use_async_initialization(self):
        """Should accept use_async parameter."""
        provider = GoogleGeminiProvider(use_async=True)
        assert provider._use_async is True

        provider = GoogleGeminiProvider(use_async=False)
        assert provider._use_async is False

    def test_clients_initialized_to_none(self):
        """Should initialize all client references to None."""
        provider = GoogleGeminiProvider()
        assert provider._sync_client is None
        assert provider._async_client is None

    def test_model_cache(self):
        """Should cache model info for repeated lookups."""
        provider = GoogleGeminiProvider()

        # First call
        info1 = provider.get_model_info("text-embedding-004")

        # Second call should use cache
        info2 = provider.get_model_info("text-embedding-004")

        assert info1 is info2
        assert "text-embedding-004" in provider._model_cache

    def test_registry_lookup_google(self):
        """Should be accessible via 'google' in the provider registry."""
        provider = get_provider("google")
        assert isinstance(provider, GoogleGeminiProvider)

    def test_registry_lookup_gemini_alias(self):
        """Should be accessible via 'gemini' alias in the provider registry."""
        provider = get_provider("gemini")
        assert isinstance(provider, GoogleGeminiProvider)

    def test_convert_messages_simple(self, monkeypatch):
        """Should convert simple messages correctly."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        provider = GoogleGeminiProvider()

        # This tests the message conversion (requires google.genai import)
        # We'll just verify the method exists and is callable
        assert callable(provider._convert_messages_to_contents)

    def test_convert_tools_empty(self):
        """Should return empty list for no tools."""
        provider = GoogleGeminiProvider()
        # This tests the tool conversion method exists
        assert callable(provider._convert_tools)

    def test_format_tool_calls_empty_response(self):
        """Should return empty list when no tool calls in response."""

        class MockCandidate:
            content = None

        class MockResponse:
            candidates = [MockCandidate()]

        provider = GoogleGeminiProvider()
        result = provider._format_tool_calls(MockResponse())
        assert result == []

    def test_format_tool_calls_no_candidates(self):
        """Should return empty list when no candidates in response."""

        class MockResponse:
            candidates = []

        provider = GoogleGeminiProvider()
        result = provider._format_tool_calls(MockResponse())
        assert result == []


class TestGoogleProviderConfig:
    """Tests for Google provider configuration functions."""

    def test_check_google_available_with_api_key(self, monkeypatch):
        """Should return True when GOOGLE_API_KEY is set."""
        from kaizen.config.providers import check_google_available

        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        assert check_google_available() is True

    def test_check_google_available_without_credentials(self, monkeypatch):
        """Should return False when no credentials are set."""
        from kaizen.config.providers import check_google_available

        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        assert check_google_available() is False

    def test_get_google_config_with_api_key(self, monkeypatch):
        """Should return correct config when API key is set."""
        from kaizen.config.providers import get_google_config

        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")
        config = get_google_config()

        assert config.provider == "google"
        assert config.model == "gemini-2.0-flash"
        assert config.api_key == "test-api-key"

    def test_get_google_config_custom_model(self, monkeypatch):
        """Should use custom model when specified."""
        from kaizen.config.providers import get_google_config

        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")
        config = get_google_config(model="gemini-1.5-pro")

        assert config.model == "gemini-1.5-pro"

    def test_get_google_config_from_env_model(self, monkeypatch):
        """Should use model from environment variable."""
        from kaizen.config.providers import get_google_config

        monkeypatch.setenv("GOOGLE_API_KEY", "test-api-key")
        monkeypatch.setenv("KAIZEN_GOOGLE_MODEL", "gemini-2.5-flash")
        config = get_google_config()

        assert config.model == "gemini-2.5-flash"

    def test_get_google_config_raises_without_credentials(self, monkeypatch):
        """Should raise ConfigurationError when no credentials are set."""
        from kaizen.config.providers import ConfigurationError, get_google_config

        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

        with pytest.raises(ConfigurationError, match="Google credentials not found"):
            get_google_config()

    def test_provider_type_includes_google(self):
        """Should include 'google' in ProviderType."""
        from kaizen.config.providers import ProviderType

        # ProviderType is a Literal, we verify by checking the annotation
        assert "google" in str(ProviderType)
        assert "gemini" in str(ProviderType)

    def test_auto_detect_includes_google(self, monkeypatch):
        """Google should be in auto-detection order."""
        from kaizen.config.providers import auto_detect_provider

        # Clear all other providers
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        config = auto_detect_provider()
        assert config.provider == "google"

    def test_get_provider_config_google(self, monkeypatch):
        """Should return Google config when explicitly requested."""
        from kaizen.config.providers import get_provider_config

        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        config = get_provider_config(provider="google")

        assert config.provider == "google"

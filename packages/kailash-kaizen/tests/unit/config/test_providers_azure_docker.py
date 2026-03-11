"""Unit tests for Azure and Docker config functions in providers.py."""

from unittest.mock import MagicMock, patch

import pytest

from kaizen.config.providers import (
    ConfigurationError,
    auto_detect_provider,
    check_anthropic_available,
    check_azure_available,
    check_cohere_available,
    check_docker_available,
    check_huggingface_available,
    get_anthropic_config,
    get_azure_config,
    get_cohere_config,
    get_docker_config,
    get_huggingface_config,
    get_mock_config,
    get_provider_config,
)


class TestCheckAzureAvailable:
    """Tests for check_azure_available function."""

    def test_returns_true_with_both_credentials(self, monkeypatch):
        """Should return True when both env vars set."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")
        assert check_azure_available() is True

    def test_returns_false_missing_endpoint(self, monkeypatch):
        """Should return False when endpoint missing."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")
        assert check_azure_available() is False

    def test_returns_false_missing_api_key(self, monkeypatch):
        """Should return False when API key missing."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        assert check_azure_available() is False

    def test_returns_false_both_missing(self, monkeypatch):
        """Should return False when both missing."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        assert check_azure_available() is False


class TestCheckDockerAvailable:
    """Tests for check_docker_available function."""

    def test_returns_false_when_not_running(self):
        """Should return False when Docker Model Runner not running."""
        # Without mocking, connection will fail
        assert check_docker_available() is False

    @patch("urllib.request.urlopen")
    def test_returns_true_when_running(self, mock_urlopen):
        """Should return True when Docker Model Runner accessible."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response
        assert check_docker_available() is True

    @patch("urllib.request.urlopen")
    def test_uses_custom_url(self, mock_urlopen, monkeypatch):
        """Should use custom URL from environment."""
        monkeypatch.setenv("DOCKER_MODEL_RUNNER_URL", "http://custom:9999/v1")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        check_docker_available()

        # Verify the custom URL was used
        call_args = mock_urlopen.call_args
        assert "custom:9999" in call_args[0][0]


class TestCheckOtherProviders:
    """Tests for other provider availability checks."""

    def test_check_anthropic_with_key(self, monkeypatch):
        """Should return True when API key set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        assert check_anthropic_available() is True

    def test_check_anthropic_without_key(self, monkeypatch):
        """Should return False when API key missing."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert check_anthropic_available() is False

    def test_check_cohere_with_key(self, monkeypatch):
        """Should return True when API key set."""
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        assert check_cohere_available() is True

    def test_check_cohere_without_key(self, monkeypatch):
        """Should return False when API key missing."""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        assert check_cohere_available() is False


class TestGetAzureConfig:
    """Tests for get_azure_config function."""

    def test_success_with_credentials(self, monkeypatch):
        """Should return valid config when credentials set."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        config = get_azure_config()
        assert config.provider == "azure"
        assert config.api_key == "test-key"
        assert config.base_url == "https://test.azure.com"
        assert config.model == "gpt-4o"  # Default model

    def test_custom_model(self, monkeypatch):
        """Should use custom model when specified."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        config = get_azure_config(model="gpt-4-turbo")
        assert config.model == "gpt-4-turbo"

    def test_model_from_env(self, monkeypatch):
        """Should use model from environment variable."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")
        monkeypatch.setenv("KAIZEN_AZURE_MODEL", "llama-3.1-70b")

        config = get_azure_config()
        assert config.model == "llama-3.1-70b"

    def test_raises_without_credentials(self, monkeypatch):
        """Should raise ConfigurationError when credentials missing."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="Azure AI Foundry not configured"):
            get_azure_config()


class TestGetDockerConfig:
    """Tests for get_docker_config function."""

    @patch("kaizen.config.providers.check_docker_available", return_value=True)
    def test_success_when_running(self, mock_check):
        """Should return valid config when Docker running."""
        config = get_docker_config()
        assert config.provider == "docker"
        assert config.model == "ai/llama3.2"
        assert "12434" in config.base_url

    @patch("kaizen.config.providers.check_docker_available", return_value=True)
    def test_custom_model(self, mock_check):
        """Should use custom model when specified."""
        config = get_docker_config(model="ai/qwen3")
        assert config.model == "ai/qwen3"

    @patch("kaizen.config.providers.check_docker_available", return_value=True)
    def test_model_from_env(self, mock_check, monkeypatch):
        """Should use model from environment variable."""
        monkeypatch.setenv("KAIZEN_DOCKER_MODEL", "ai/gemma3")
        config = get_docker_config()
        assert config.model == "ai/gemma3"

    def test_raises_when_not_running(self):
        """Should raise ConfigurationError when Docker not running."""
        with pytest.raises(
            ConfigurationError, match="Docker Model Runner not available"
        ):
            get_docker_config()


class TestGetOtherConfigs:
    """Tests for other provider config functions."""

    def test_get_anthropic_config_success(self, monkeypatch):
        """Should return valid config when API key set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        config = get_anthropic_config()
        assert config.provider == "anthropic"
        assert config.api_key == "test-key"
        assert "claude" in config.model

    def test_get_anthropic_config_raises(self, monkeypatch):
        """Should raise when API key missing."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="Anthropic API key"):
            get_anthropic_config()

    def test_get_cohere_config_success(self, monkeypatch):
        """Should return valid config when API key set."""
        monkeypatch.setenv("COHERE_API_KEY", "test-key")
        config = get_cohere_config()
        assert config.provider == "cohere"
        assert config.api_key == "test-key"

    def test_get_cohere_config_raises(self, monkeypatch):
        """Should raise when API key missing."""
        monkeypatch.delenv("COHERE_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="Cohere API key"):
            get_cohere_config()

    def test_get_huggingface_config(self):
        """Should return valid config (no key required for local)."""
        config = get_huggingface_config()
        assert config.provider == "huggingface"
        assert "sentence-transformers" in config.model

    def test_get_mock_config(self):
        """Should return mock config."""
        config = get_mock_config()
        assert config.provider == "mock"
        assert config.model == "mock-model"
        assert config.timeout == 1
        assert config.max_retries == 0


class TestGetProviderConfig:
    """Tests for get_provider_config function."""

    def test_azure_provider(self, monkeypatch):
        """Should return Azure config when specified."""
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        config = get_provider_config(provider="azure")
        assert config.provider == "azure"

    @patch("kaizen.config.providers.check_docker_available", return_value=True)
    def test_docker_provider(self, mock_check):
        """Should return Docker config when specified."""
        config = get_provider_config(provider="docker")
        assert config.provider == "docker"

    def test_mock_provider(self):
        """Should return mock config when specified."""
        config = get_provider_config(provider="mock")
        assert config.provider == "mock"

    def test_auto_detect_fallback(self, monkeypatch):
        """Should auto-detect when provider not specified."""
        # Set up OpenAI to be available
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = get_provider_config()
        assert config.provider == "openai"


class TestAutoDetectProvider:
    """Tests for auto_detect_provider function."""

    def test_prefers_explicit_override(self, monkeypatch):
        """Should use KAIZEN_DEFAULT_PROVIDER when set."""
        monkeypatch.setenv("KAIZEN_DEFAULT_PROVIDER", "mock")

        config = auto_detect_provider()
        assert config.provider == "mock"

    def test_detection_order_openai_first(self, monkeypatch):
        """Should detect OpenAI first when available."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        config = auto_detect_provider()
        assert config.provider == "openai"

    def test_detection_order_azure_second(self, monkeypatch):
        """Should detect Azure second when OpenAI not available."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("AZURE_AI_INFERENCE_ENDPOINT", "https://test.azure.com")
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        config = auto_detect_provider()
        assert config.provider == "azure"

    def test_detection_order_anthropic_third(self, monkeypatch):
        """Should detect Anthropic third when others not available."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        config = auto_detect_provider()
        assert config.provider == "anthropic"

    @patch("kaizen.config.providers.check_ollama_available", return_value=False)
    @patch("kaizen.config.providers.check_docker_available", return_value=False)
    def test_raises_when_none_available(self, mock_docker, mock_ollama, monkeypatch):
        """Should raise when no providers available."""
        # Clear all provider env vars
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="No LLM provider available"):
            auto_detect_provider()

    def test_preferred_provider_used_first(self, monkeypatch):
        """Should try preferred provider first."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        config = auto_detect_provider(preferred="anthropic")
        assert config.provider == "anthropic"

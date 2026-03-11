"""Unit tests for UnifiedAzureProvider.

Tests the intelligent unified Azure provider that automatically selects
between Azure OpenAI Service and Azure AI Foundry based on endpoint detection
and feature requirements.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.nodes.ai.azure_capabilities import (
    FeatureDegradationWarning,
    FeatureNotSupportedError,
)
from kaizen.nodes.ai.unified_azure_provider import UnifiedAzureProvider


class TestUnifiedAzureProviderAvailability:
    """Tests for provider availability checks."""

    def test_is_available_with_azure_openai_config(self, monkeypatch):
        """Should be available when Azure OpenAI is configured."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        assert provider.is_available() is True

    def test_is_available_with_ai_foundry_config(self, monkeypatch):
        """Should be available when AI Foundry is configured."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.inference.ai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        assert provider.is_available() is True

    def test_not_available_without_config(self, monkeypatch):
        """Should not be available without any Azure configuration."""
        # Clear all Azure env vars
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

        provider = UnifiedAzureProvider()
        assert provider.is_available() is False


class TestUnifiedAzureProviderBackendDetection:
    """Tests for automatic backend detection."""

    def test_detects_azure_openai_from_endpoint(self, monkeypatch):
        """Should detect Azure OpenAI from endpoint pattern."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        backend_type = provider.get_detected_backend()

        assert backend_type == "azure_openai"

    def test_detects_ai_foundry_from_endpoint(self, monkeypatch):
        """Should detect AI Foundry from endpoint pattern."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.inference.ai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        backend_type = provider.get_detected_backend()

        assert backend_type == "azure_ai_foundry"

    def test_respects_explicit_backend_override(self, monkeypatch):
        """Should respect AZURE_BACKEND override."""
        # Even with OpenAI endpoint pattern, explicit override should win
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_BACKEND", "foundry")

        provider = UnifiedAzureProvider()
        backend_type = provider.get_detected_backend()

        assert backend_type == "azure_ai_foundry"

    def test_defaults_to_azure_openai_for_unknown_patterns(self, monkeypatch):
        """Should default to Azure OpenAI for unknown endpoint patterns."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://custom-proxy.company.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        backend_type = provider.get_detected_backend()

        assert backend_type == "azure_openai"


class TestUnifiedAzureProviderCapabilities:
    """Tests for capability checking."""

    def test_get_capabilities_returns_dict(self, monkeypatch):
        """Should return capabilities dictionary."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        caps = provider.get_capabilities()

        assert isinstance(caps, dict)
        assert "chat" in caps
        assert "embeddings" in caps

    def test_supports_audio_on_azure_openai(self, monkeypatch):
        """Azure OpenAI should support audio input."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        caps = provider.get_capabilities()

        assert caps.get("audio_input") is True

    def test_no_audio_on_ai_foundry(self, monkeypatch):
        """AI Foundry should not support audio input."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.inference.ai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        caps = provider.get_capabilities()

        assert caps.get("audio_input") is False

    def test_supports_method(self, monkeypatch):
        """Should have supports() method for feature checking."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()

        assert provider.supports("chat") is True
        assert provider.supports("embeddings") is True


class TestUnifiedAzureProviderChat:
    """Tests for chat operations."""

    @patch("openai.AzureOpenAI")
    def test_chat_uses_detected_backend(self, mock_openai_class, monkeypatch):
        """Should use the detected backend for chat."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "test-id"
        mock_response.model = "gpt-4o"
        mock_response.created = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = UnifiedAzureProvider()
        result = provider.chat([{"role": "user", "content": "Hi"}], model="gpt-4o")

        assert result["content"] == "Hello!"
        assert result["metadata"]["provider"] == "azure_openai"

    @patch("openai.AzureOpenAI")
    def test_chat_filters_temperature_for_reasoning_models(
        self, mock_openai_class, monkeypatch
    ):
        """Should filter temperature for o1/o3/GPT-5 models."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Thought result"
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "test-id"
        mock_response.model = "o1-preview"
        mock_response.created = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = UnifiedAzureProvider()
        result = provider.chat(
            [{"role": "user", "content": "Think about this"}],
            model="o1-preview",
            generation_config={"temperature": 0.7},
        )

        # Verify temperature was filtered
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "temperature" not in call_kwargs

    @patch("openai.AzureOpenAI")
    def test_chat_passes_response_format(self, mock_openai_class, monkeypatch):
        """Should pass response_format for structured output."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"name": "test"}'
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "test-id"
        mock_response.model = "gpt-4o"
        mock_response.created = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        }

        provider = UnifiedAzureProvider()
        result = provider.chat(
            [{"role": "user", "content": "Extract name"}],
            model="gpt-4o",
            generation_config={"response_format": response_format},
        )

        # Verify response_format was passed
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "response_format" in call_kwargs


class TestUnifiedAzureProviderFeatureGaps:
    """Tests for feature gap handling."""

    def test_raises_error_for_audio_on_ai_foundry(self, monkeypatch):
        """Should raise error when using audio on AI Foundry."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.inference.ai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()

        with pytest.raises(FeatureNotSupportedError) as exc:
            provider.check_feature("audio_input")

        assert exc.value.feature == "audio_input"
        assert "Azure OpenAI" in str(exc.value)

    def test_raises_error_for_reasoning_models_on_ai_foundry(self, monkeypatch):
        """Should raise error when using reasoning models on AI Foundry."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.inference.ai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()

        with pytest.raises(FeatureNotSupportedError) as exc:
            provider.check_model_requirements("o1-preview")

        assert "reasoning" in exc.value.feature.lower()

    def test_raises_error_for_llama_on_azure_openai(self, monkeypatch):
        """Should raise error when using Llama on Azure OpenAI."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()

        with pytest.raises(FeatureNotSupportedError) as exc:
            provider.check_model_requirements("llama-3.1-8b")

        assert "AI Foundry" in str(exc.value)


class TestUnifiedAzureProviderProviderInfo:
    """Tests for provider information methods."""

    def test_get_backend_type(self, monkeypatch):
        """Should return detected backend type."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        assert provider.get_detected_backend() == "azure_openai"

    def test_get_detection_source(self, monkeypatch):
        """Should return detection source."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        source = provider.get_detection_source()

        assert source in ("pattern", "default", "explicit", "error_fallback")

    def test_supports_chat(self, monkeypatch):
        """Should indicate chat support."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        assert provider.supports_chat() is True

    def test_supports_embeddings(self, monkeypatch):
        """Should indicate embeddings support."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        provider = UnifiedAzureProvider()
        assert provider.supports_embeddings() is True


class TestUnifiedAzureProviderErrorHandling:
    """Tests for error-based backend correction."""

    @patch("openai.AzureOpenAI")
    def test_error_triggers_backend_switch(self, mock_openai_class, monkeypatch):
        """Should switch backends on specific error signatures."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://custom.proxy.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        # First call fails with audience error (indicates AI Foundry)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception(
            "audience is incorrect (https://cognitiveservices.azure.com)"
        )
        mock_openai_class.return_value = mock_client

        provider = UnifiedAzureProvider()

        # Should switch to AI Foundry based on error
        new_backend = provider.handle_error(
            Exception("audience is incorrect (https://cognitiveservices.azure.com)")
        )

        assert new_backend == "azure_ai_foundry"
        assert provider.get_detection_source() == "error_fallback"

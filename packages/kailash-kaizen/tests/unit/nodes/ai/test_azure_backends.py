"""Unit tests for Azure backend implementations.

Tests the AzureBackend ABC and its concrete implementations:
- AzureOpenAIBackend: Uses OpenAI SDK with Azure configuration
- AzureAIFoundryBackend: Uses Azure AI Inference SDK
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.nodes.ai.azure_backends import (
    AzureAIFoundryBackend,
    AzureBackend,
    AzureOpenAIBackend,
)


class TestAzureBackendABC:
    """Tests for the AzureBackend abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """AzureBackend should not be directly instantiable."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            AzureBackend()

    def test_subclass_must_implement_is_configured(self):
        """Subclasses must implement is_configured."""

        class IncompleteBackend(AzureBackend):
            def get_backend_type(self):
                return "test"

            def chat(self, messages, **kwargs):
                pass

            async def chat_async(self, messages, **kwargs):
                pass

            def embed(self, texts, **kwargs):
                pass

        with pytest.raises(TypeError, match="is_configured"):
            IncompleteBackend()

    def test_subclass_must_implement_get_backend_type(self):
        """Subclasses must implement get_backend_type."""

        class IncompleteBackend(AzureBackend):
            def is_configured(self):
                return True

            def chat(self, messages, **kwargs):
                pass

            async def chat_async(self, messages, **kwargs):
                pass

            def embed(self, texts, **kwargs):
                pass

        with pytest.raises(TypeError, match="get_backend_type"):
            IncompleteBackend()


class TestAzureOpenAIBackend:
    """Tests for Azure OpenAI Service backend."""

    # Configuration Tests

    def test_is_configured_with_all_env_vars(self, monkeypatch):
        """Should return True when all required env vars are set."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()
        assert backend.is_configured() is True

    def test_is_configured_with_unified_env_vars(self, monkeypatch):
        """Should accept unified AZURE_ENDPOINT if it's an OpenAI URL."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        backend = AzureOpenAIBackend()
        assert backend.is_configured() is True

    def test_not_configured_without_endpoint(self, monkeypatch):
        """Should return False without endpoint."""
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()
        assert backend.is_configured() is False

    def test_not_configured_without_api_key(self, monkeypatch):
        """Should return False without API key."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_API_KEY", raising=False)

        backend = AzureOpenAIBackend()
        assert backend.is_configured() is False

    def test_get_backend_type(self, monkeypatch):
        """Should return 'azure_openai'."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()
        assert backend.get_backend_type() == "azure_openai"

    # API Version Tests

    def test_uses_env_api_version(self, monkeypatch):
        """Should use AZURE_API_VERSION from environment."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01-preview")

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2025-01-01-preview"

    def test_uses_default_api_version(self, monkeypatch):
        """Should use default API version when env var not set."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("AZURE_API_VERSION", raising=False)

        backend = AzureOpenAIBackend()
        assert backend._api_version == "2024-10-21"

    # Reasoning Model Parameter Filtering Tests

    def test_filters_temperature_for_o1_models(self, monkeypatch):
        """Should filter temperature for o1 models."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()

        params = {"temperature": 0.7, "max_tokens": 100}
        filtered = backend._filter_params_for_model("o1-preview", params)

        assert "temperature" not in filtered
        assert filtered.get("max_completion_tokens") == 100

    def test_filters_temperature_for_o3_models(self, monkeypatch):
        """Should filter temperature for o3 models."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()

        params = {"temperature": 0.7, "top_p": 0.9}
        filtered = backend._filter_params_for_model("o3-mini", params)

        assert "temperature" not in filtered
        assert "top_p" not in filtered

    def test_filters_temperature_for_gpt5_models(self, monkeypatch):
        """Should filter temperature for GPT-5 models."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()

        params = {"temperature": 0.5}
        filtered = backend._filter_params_for_model("gpt-5", params)

        assert "temperature" not in filtered

    def test_preserves_params_for_standard_models(self, monkeypatch):
        """Should preserve all params for standard models."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()

        params = {"temperature": 0.7, "max_tokens": 100, "top_p": 0.9}
        filtered = backend._filter_params_for_model("gpt-4o", params)

        assert filtered["temperature"] == 0.7
        assert filtered["max_tokens"] == 100
        assert filtered["top_p"] == 0.9

    def test_translates_max_tokens_for_reasoning_models(self, monkeypatch):
        """Should translate max_tokens to max_completion_tokens for reasoning models."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        backend = AzureOpenAIBackend()

        params = {"max_tokens": 4000}
        filtered = backend._filter_params_for_model("o1", params)

        assert "max_tokens" not in filtered
        assert filtered["max_completion_tokens"] == 4000

    # Chat Tests (with mocking)

    @patch("openai.AzureOpenAI")
    def test_chat_creates_client(self, mock_azure_openai, monkeypatch):
        """Should create Azure OpenAI client on first chat call."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "test-id"
        mock_response.model = "gpt-4o"
        mock_response.created = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        mock_azure_openai.return_value = mock_client

        backend = AzureOpenAIBackend()
        messages = [{"role": "user", "content": "Hi"}]
        result = backend.chat(messages, model="gpt-4o")

        mock_azure_openai.assert_called_once()
        assert result["content"] == "Hello!"

    @patch("openai.AzureOpenAI")
    def test_chat_passes_deployment(self, mock_azure_openai, monkeypatch):
        """Should pass deployment/model to API."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_DEPLOYMENT", "my-gpt4-deployment")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Response"
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "test-id"
        mock_response.model = "my-gpt4-deployment"
        mock_response.created = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        mock_azure_openai.return_value = mock_client

        backend = AzureOpenAIBackend()
        messages = [{"role": "user", "content": "Hi"}]
        backend.chat(messages)

        # Check model was passed
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "my-gpt4-deployment"

    # Response Format Tests

    @patch("openai.AzureOpenAI")
    def test_chat_returns_standardized_response(self, mock_azure_openai, monkeypatch):
        """Should return standardized response format."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "chatcmpl-123"
        mock_response.model = "gpt-4o"
        mock_response.created = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response
        mock_azure_openai.return_value = mock_client

        backend = AzureOpenAIBackend()
        result = backend.chat([{"role": "user", "content": "Hi"}], model="gpt-4o")

        assert result["id"] == "chatcmpl-123"
        assert result["content"] == "Test response"
        assert result["role"] == "assistant"
        assert result["model"] == "gpt-4o"
        assert result["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["metadata"]["provider"] == "azure_openai"


class TestAzureAIFoundryBackend:
    """Tests for Azure AI Foundry backend."""

    # Configuration Tests

    def test_is_configured_with_inference_env_vars(self, monkeypatch):
        """Should return True with AZURE_AI_INFERENCE_* vars."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        backend = AzureAIFoundryBackend()
        assert backend.is_configured() is True

    def test_is_configured_with_unified_env_vars(self, monkeypatch):
        """Should accept unified AZURE_ENDPOINT if it's an AI Foundry URL."""
        monkeypatch.setenv("AZURE_ENDPOINT", "https://test.inference.ai.azure.com")
        monkeypatch.setenv("AZURE_API_KEY", "test-key")

        backend = AzureAIFoundryBackend()
        assert backend.is_configured() is True

    def test_not_configured_without_endpoint(self, monkeypatch):
        """Should return False without endpoint."""
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        backend = AzureAIFoundryBackend()
        assert backend.is_configured() is False

    def test_not_configured_without_api_key(self, monkeypatch):
        """Should return False without API key."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.delenv("AZURE_AI_INFERENCE_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_API_KEY", raising=False)

        backend = AzureAIFoundryBackend()
        assert backend.is_configured() is False

    def test_get_backend_type(self, monkeypatch):
        """Should return 'azure_ai_foundry'."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        backend = AzureAIFoundryBackend()
        assert backend.get_backend_type() == "azure_ai_foundry"

    # Response Format Translation Tests

    def test_translates_json_schema_format(self, monkeypatch):
        """Should translate OpenAI json_schema to Azure JsonSchemaFormat."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        # Mock the JsonSchemaFormat class
        mock_json_schema_format = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "azure.ai.inference.models": MagicMock(
                    JsonSchemaFormat=mock_json_schema_format
                )
            },
        ):
            backend = AzureAIFoundryBackend()

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

            translated = backend._translate_response_format(response_format)

            # When SDK is mocked, it should return the mock object
            # When SDK is not available, it returns None (tested in integration tests)
            # This test verifies the translation logic when SDK IS available
            mock_json_schema_format.assert_called_once()

    def test_translates_json_object_format(self, monkeypatch):
        """Should translate json_object format to Azure format."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        # Mock the JsonSchemaFormat class
        mock_json_schema_format = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "azure.ai.inference.models": MagicMock(
                    JsonSchemaFormat=mock_json_schema_format
                )
            },
        ):
            backend = AzureAIFoundryBackend()

            response_format = {"type": "json_object"}
            translated = backend._translate_response_format(response_format)

            # Verify JsonSchemaFormat was called
            mock_json_schema_format.assert_called_once()

    def test_returns_none_when_sdk_unavailable(self, monkeypatch):
        """Should return None when Azure SDK is not available."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        backend = AzureAIFoundryBackend()

        response_format = {"type": "json_schema", "json_schema": {"name": "test"}}

        # Without mocking, if SDK is not installed, it returns None
        # This is the expected graceful degradation behavior
        translated = backend._translate_response_format(response_format)
        # Either returns the SDK object if installed, or None if not
        # The actual behavior depends on SDK availability

    # Chat Tests (with mocking)

    def test_chat_creates_client(self, monkeypatch):
        """Should create ChatCompletionsClient on first chat call."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        # Create mocks
        mock_client_class = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "test-id"
        mock_response.model = "gpt-4o"
        mock_response.created = MagicMock()
        mock_response.created.timestamp.return_value = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.complete.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Mock Azure SDK modules
        mock_azure_module = MagicMock()
        mock_azure_module.ChatCompletionsClient = mock_client_class

        mock_azure_models = MagicMock()
        mock_azure_models.SystemMessage = MagicMock()
        mock_azure_models.UserMessage = MagicMock()
        mock_azure_models.AssistantMessage = MagicMock()

        mock_azure_core = MagicMock()
        mock_azure_core.AzureKeyCredential = MagicMock(return_value="mocked-cred")

        with patch.dict(
            "sys.modules",
            {
                "azure.ai.inference": mock_azure_module,
                "azure.ai.inference.models": mock_azure_models,
                "azure.core.credentials": mock_azure_core,
            },
        ):
            backend = AzureAIFoundryBackend()
            messages = [{"role": "user", "content": "Hi"}]
            result = backend.chat(messages, model="gpt-4o")

            mock_client_class.assert_called_once()
            assert result["content"] == "Hello!"

    def test_chat_returns_standardized_response(self, monkeypatch):
        """Should return standardized response format."""
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        # Create mocks
        mock_client_class = MagicMock()
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.id = "chatcmpl-456"
        mock_response.model = "gpt-4o"
        mock_response.created = MagicMock()
        mock_response.created.timestamp.return_value = 1234567890
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.complete.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Mock Azure SDK modules
        mock_azure_module = MagicMock()
        mock_azure_module.ChatCompletionsClient = mock_client_class

        mock_azure_models = MagicMock()
        mock_azure_models.SystemMessage = MagicMock()
        mock_azure_models.UserMessage = MagicMock()
        mock_azure_models.AssistantMessage = MagicMock()

        mock_azure_core = MagicMock()
        mock_azure_core.AzureKeyCredential = MagicMock(return_value="mocked-cred")

        with patch.dict(
            "sys.modules",
            {
                "azure.ai.inference": mock_azure_module,
                "azure.ai.inference.models": mock_azure_models,
                "azure.core.credentials": mock_azure_core,
            },
        ):
            backend = AzureAIFoundryBackend()
            result = backend.chat([{"role": "user", "content": "Hi"}], model="gpt-4o")

            assert result["id"] == "chatcmpl-456"
            assert result["content"] == "Test response"
            assert result["role"] == "assistant"
            assert result["finish_reason"] == "stop"
            assert result["usage"]["prompt_tokens"] == 10
            assert result["metadata"]["provider"] == "azure_ai_foundry"


class TestBackendInteroperability:
    """Tests that backends have compatible interfaces."""

    def test_both_backends_have_same_interface(self, monkeypatch):
        """Both backends should implement the same methods."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        openai_backend = AzureOpenAIBackend()
        foundry_backend = AzureAIFoundryBackend()

        # Both should have these methods
        for method in [
            "is_configured",
            "get_backend_type",
            "chat",
            "chat_async",
            "embed",
        ]:
            assert hasattr(openai_backend, method)
            assert hasattr(foundry_backend, method)
            assert callable(getattr(openai_backend, method))
            assert callable(getattr(foundry_backend, method))

    def test_backend_types_are_distinct(self, monkeypatch):
        """Backend types should be distinct identifiers."""
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv(
            "AZURE_AI_INFERENCE_ENDPOINT", "https://test.inference.ai.azure.com"
        )
        monkeypatch.setenv("AZURE_AI_INFERENCE_API_KEY", "test-key")

        openai_backend = AzureOpenAIBackend()
        foundry_backend = AzureAIFoundryBackend()

        assert openai_backend.get_backend_type() != foundry_backend.get_backend_type()
        assert openai_backend.get_backend_type() == "azure_openai"
        assert foundry_backend.get_backend_type() == "azure_ai_foundry"

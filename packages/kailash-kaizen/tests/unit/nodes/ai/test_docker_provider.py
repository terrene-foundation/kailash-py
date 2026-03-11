"""Unit tests for Docker Model Runner provider."""

from unittest.mock import MagicMock, patch

import pytest
from kaizen.nodes.ai.ai_providers import DockerModelRunnerProvider


class TestDockerModelRunnerProvider:
    """Unit tests for Docker Model Runner provider."""

    def test_default_base_url(self):
        """Should use default localhost URL."""
        provider = DockerModelRunnerProvider()
        base_url = provider._get_base_url()
        assert "localhost:12434" in base_url
        assert "/engines/llama.cpp/v1" in base_url

    def test_custom_base_url(self, monkeypatch):
        """Should use custom URL from environment."""
        custom_url = "http://custom:8080/v1"
        monkeypatch.setenv("DOCKER_MODEL_RUNNER_URL", custom_url)
        provider = DockerModelRunnerProvider()
        assert provider._get_base_url() == custom_url

    def test_container_base_url_constant(self):
        """Should have correct container URL constant."""
        assert (
            DockerModelRunnerProvider.CONTAINER_BASE_URL
            == "http://model-runner.docker.internal/engines/llama.cpp/v1"
        )

    def test_capabilities(self):
        """Should report both chat and embeddings capabilities."""
        provider = DockerModelRunnerProvider()
        caps = provider.get_capabilities()
        assert caps["chat"] is True
        assert caps["embeddings"] is True
        assert provider.supports_chat() is True
        assert provider.supports_embeddings() is True

    def test_supports_tools_qwen3(self):
        """Should indicate tool support for Qwen3 models."""
        provider = DockerModelRunnerProvider()
        assert provider.supports_tools("ai/qwen3") is True
        assert provider.supports_tools("ai/qwen3:14b") is True
        assert provider.supports_tools("ai/qwen3-instruct") is True

    def test_supports_tools_llama33(self):
        """Should indicate tool support for Llama 3.3 models."""
        provider = DockerModelRunnerProvider()
        assert provider.supports_tools("ai/llama3.3") is True
        assert provider.supports_tools("ai/llama3.3:70b") is True

    def test_supports_tools_gemma3(self):
        """Should indicate tool support for Gemma3 models."""
        provider = DockerModelRunnerProvider()
        assert provider.supports_tools("ai/gemma3") is True
        assert provider.supports_tools("ai/gemma3:2b") is True

    def test_no_tools_support_llama32(self):
        """Should indicate no tool support for Llama 3.2."""
        provider = DockerModelRunnerProvider()
        assert provider.supports_tools("ai/llama3.2") is False

    def test_no_tools_support_smollm(self):
        """Should indicate no tool support for SmolLM."""
        provider = DockerModelRunnerProvider()
        assert provider.supports_tools("ai/smollm2") is False

    def test_no_tools_support_mistral(self):
        """Should indicate no tool support for Mistral (not in list)."""
        provider = DockerModelRunnerProvider()
        assert provider.supports_tools("ai/mistral") is False

    def test_get_model_info_mxbai_embed_large(self):
        """Should return correct info for mxbai-embed-large."""
        provider = DockerModelRunnerProvider()
        info = provider.get_model_info("ai/mxbai-embed-large")
        assert info["dimensions"] == 1024
        assert info["max_tokens"] == 512
        assert "matryoshka_dimensions" in info["capabilities"]
        assert 1024 in info["capabilities"]["matryoshka_dimensions"]

    def test_get_model_info_nomic_embed_text(self):
        """Should return correct info for nomic-embed-text."""
        provider = DockerModelRunnerProvider()
        info = provider.get_model_info("ai/nomic-embed-text")
        assert info["dimensions"] == 768
        assert info["max_tokens"] == 8192

    def test_get_model_info_all_minilm(self):
        """Should return correct info for all-minilm."""
        provider = DockerModelRunnerProvider()
        info = provider.get_model_info("ai/all-minilm")
        assert info["dimensions"] == 384
        assert info["max_tokens"] == 512

    def test_get_model_info_qwen3_embedding(self):
        """Should return correct info for qwen3-embedding."""
        provider = DockerModelRunnerProvider()
        info = provider.get_model_info("ai/qwen3-embedding")
        assert info["dimensions"] == 1024

    def test_get_model_info_unknown_model(self):
        """Should return default info for unknown models."""
        provider = DockerModelRunnerProvider()
        info = provider.get_model_info("ai/unknown-model")
        assert info["dimensions"] == 1024  # Default
        assert "ai/unknown-model" in info["description"]

    def test_use_async_initialization(self):
        """Should accept use_async parameter."""
        provider = DockerModelRunnerProvider(use_async=True)
        assert provider._use_async is True

        provider = DockerModelRunnerProvider(use_async=False)
        assert provider._use_async is False

    def test_clients_initialized_to_none(self):
        """Should initialize client references to None."""
        provider = DockerModelRunnerProvider()
        assert provider._sync_client is None
        assert provider._async_client is None

    def test_is_available_when_not_running(self):
        """Should return False when Docker Model Runner not accessible."""
        provider = DockerModelRunnerProvider()
        provider._available = None  # Reset cache
        # Without mocking, should fail to connect (timeout)
        assert provider.is_available() is False

    @patch("urllib.request.urlopen")
    def test_is_available_when_running(self, mock_urlopen):
        """Should return True when Docker Model Runner is accessible."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        provider = DockerModelRunnerProvider()
        provider._available = None  # Reset cache
        assert provider.is_available() is True

    @patch("urllib.request.urlopen")
    def test_is_available_caches_result(self, mock_urlopen):
        """Should cache availability check result."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response

        provider = DockerModelRunnerProvider()
        provider._available = None

        # First call
        result1 = provider.is_available()

        # Second call should use cache
        result2 = provider.is_available()

        assert result1 is True
        assert result2 is True
        # urlopen should only be called once due to caching
        assert mock_urlopen.call_count == 1

    def test_tool_capable_models_is_frozenset(self):
        """Should use frozenset for tool capable models."""
        assert isinstance(DockerModelRunnerProvider.TOOL_CAPABLE_MODELS, frozenset)

    def test_model_cache(self):
        """Should cache model info for repeated lookups."""
        provider = DockerModelRunnerProvider()

        # First call
        info1 = provider.get_model_info("ai/mxbai-embed-large")

        # Second call should use cache
        info2 = provider.get_model_info("ai/mxbai-embed-large")

        assert info1 is info2
        assert "ai/mxbai-embed-large" in provider._model_cache

    def test_process_messages_simple(self):
        """Should process simple string messages."""
        provider = DockerModelRunnerProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        processed = provider._process_messages(messages)

        assert len(processed) == 2
        assert processed[0]["role"] == "user"
        assert processed[0]["content"] == "Hello"
        assert processed[1]["role"] == "assistant"
        assert processed[1]["content"] == "Hi there"

    def test_process_messages_complex_content(self):
        """Should extract text from complex content."""
        provider = DockerModelRunnerProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image", "path": "/some/image.jpg"},
                ],
            }
        ]
        processed = provider._process_messages(messages)

        assert len(processed) == 1
        assert processed[0]["role"] == "user"
        assert processed[0]["content"] == "What is this?"

    def test_process_messages_multiple_text_parts(self):
        """Should join multiple text parts."""
        provider = DockerModelRunnerProvider()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"},
                ],
            }
        ]
        processed = provider._process_messages(messages)

        assert processed[0]["content"] == "Part 1 Part 2"

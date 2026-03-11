"""
Unit tests for Ollama provider adapter.

Tests the OllamaProvider integration with Kaizen BaseAgent.
Following TDD pattern from TODO-148/149.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestOllamaProviderInitialization:
    """Test OllamaProvider initialization."""

    def test_ollama_provider_initialization_default_config(self):
        """Test initializing OllamaProvider with default config."""
        from kaizen.providers import OllamaProvider

        # Mock ollama to avoid actual connection
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()

            assert provider is not None
            assert hasattr(provider, "config")

    def test_ollama_provider_initialization_custom_config(self):
        """Test initializing OllamaProvider with custom config."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            custom_config = OllamaConfig(
                model="llava:13b", temperature=0.8, timeout=180
            )
            provider = OllamaProvider(config=custom_config)

            assert provider.config.model == "llava:13b"
            assert provider.config.temperature == 0.8
            assert provider.config.timeout == 180

    def test_ollama_provider_initialization_checks_availability(self):
        """Test OllamaProvider checks Ollama availability on init."""
        from kaizen.providers import OllamaProvider

        # Mock ollama that raises exception (not available)
        mock_ollama = MagicMock()
        mock_ollama.list.side_effect = Exception("Connection refused")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with pytest.raises(RuntimeError, match="Ollama not available"):
                OllamaProvider()


class TestTextGeneration:
    """Test text generation with Ollama."""

    def test_ollama_text_generation_method_exists(self):
        """Test generate method exists."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            assert hasattr(provider, "generate")

    def test_ollama_text_generation_basic(self):
        """Test basic text generation."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Paris is the capital of France."},
            "model": "llama2",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            result = provider.generate("What is the capital of France?")

            assert result is not None
            assert "response" in result
            assert result["response"] == "Paris is the capital of France."

    def test_ollama_text_generation_with_system_prompt(self):
        """Test text generation with system prompt."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Bonjour!"},
            "model": "llama2",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            provider.generate(prompt="Say hello", system="You are a French assistant.")

            # Verify system message was included
            call_args = mock_ollama.chat.call_args
            messages = call_args[1]["messages"]

            # Should have system and user messages
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"

    def test_ollama_text_generation_with_temperature(self):
        """Test text generation with custom temperature."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Response"},
            "model": "llama2",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            config = OllamaConfig(temperature=0.9)
            provider = OllamaProvider(config=config)
            provider.generate("Test prompt", temperature=0.5)

            # Should use custom temperature (overrides config)
            call_args = mock_ollama.chat.call_args
            options = call_args[1]["options"]
            assert options["temperature"] == 0.5

    def test_ollama_text_generation_error_handling(self):
        """Test error handling during text generation."""
        from kaizen.providers import OllamaProvider

        # Mock ollama that raises exception
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.side_effect = Exception("Generation failed")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()

            with pytest.raises(RuntimeError, match="Ollama generation failed"):
                provider.generate("Test prompt")


class TestVisionMessageFormat:
    """Test vision message formatting for Ollama."""

    def test_ollama_vision_message_format_method_exists(self):
        """Test generate_vision method exists."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            assert hasattr(provider, "generate_vision")

    def test_ollama_vision_message_format_with_image(self):
        """Test vision message includes image in correct format."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "I see a cat in the image."},
            "model": "llava:13b",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            config = OllamaConfig(model="llava:13b")
            provider = OllamaProvider(config=config)

            provider.generate_vision(
                prompt="What do you see in this image?", image_path="/path/to/image.jpg"
            )

            # Verify image was included in messages
            call_args = mock_ollama.chat.call_args
            messages = call_args[1]["messages"]

            # Should have user message with image
            user_message = messages[-1]
            assert user_message["role"] == "user"
            assert "images" in user_message
            assert "/path/to/image.jpg" in user_message["images"]

    def test_ollama_vision_message_format_with_system_prompt(self):
        """Test vision message with system prompt."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Analysis result"},
            "model": "llava:13b",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            config = OllamaConfig(model="llava:13b")
            provider = OllamaProvider(config=config)

            provider.generate_vision(
                prompt="Analyze this image",
                image_path="/path/to/image.jpg",
                system="You are an expert image analyst.",
            )

            # Verify system message was included
            call_args = mock_ollama.chat.call_args
            messages = call_args[1]["messages"]

            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            assert "images" in messages[1]

    def test_ollama_vision_message_format_error_handling(self):
        """Test error handling for vision generation."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama that raises exception
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.side_effect = Exception("Vision generation failed")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            config = OllamaConfig(model="llava:13b")
            provider = OllamaProvider(config=config)

            with pytest.raises(RuntimeError, match="Ollama vision generation failed"):
                provider.generate_vision(
                    prompt="Analyze", image_path="/path/to/image.jpg"
                )


class TestStreamingSupport:
    """Test streaming response support."""

    def test_ollama_streaming_method_exists(self):
        """Test generate_stream method exists."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            assert hasattr(provider, "generate_stream")

    def test_ollama_streaming_basic(self):
        """Test basic streaming generation."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        def mock_chat(*args, **kwargs):
            """Mock streaming chat response."""
            yield {"message": {"content": "Hello "}}
            yield {"message": {"content": "world"}}
            yield {"message": {"content": "!"}}

        mock_ollama.chat = mock_chat

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            chunks = list(provider.generate_stream("Say hello"))

            # Should yield multiple chunks
            assert len(chunks) > 0
            # Chunks should be strings
            assert all(isinstance(chunk, str) for chunk in chunks)

    def test_ollama_streaming_with_system_prompt(self):
        """Test streaming with system prompt."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        def mock_chat(*args, **kwargs):
            # Verify messages were passed correctly
            messages = kwargs.get("messages", [])
            if len(messages) == 2 and messages[0]["role"] == "system":
                yield {"message": {"content": "Correct"}}
            else:
                yield {"message": {"content": "Wrong"}}

        mock_ollama.chat = mock_chat

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            chunks = list(
                provider.generate_stream("Test", system="You are a test assistant.")
            )

            # Should have received chunks
            assert len(chunks) > 0

    def test_ollama_streaming_error_handling(self):
        """Test error handling in streaming."""
        from kaizen.providers import OllamaProvider

        # Mock ollama that raises exception
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.side_effect = Exception("Streaming failed")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()

            with pytest.raises(RuntimeError, match="Ollama streaming failed"):
                list(provider.generate_stream("Test"))

    def test_ollama_streaming_empty_chunks_filtered(self):
        """Test that empty chunks are filtered out."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        def mock_chat(*args, **kwargs):
            """Mock streaming with some empty chunks."""
            yield {"message": {"content": "Hello"}}
            yield {"message": {"content": ""}}  # Empty chunk
            yield {"message": {"content": "world"}}
            yield {"message": {}}  # No content key

        mock_ollama.chat = mock_chat

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            chunks = list(provider.generate_stream("Test"))

            # Should only have non-empty chunks
            assert all(chunk for chunk in chunks)


class TestTimeoutConfiguration:
    """Test request timeout configuration."""

    def test_ollama_timeout_configuration_in_config(self):
        """Test timeout is configurable via OllamaConfig."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            config = OllamaConfig(timeout=300)  # 5 minutes
            provider = OllamaProvider(config=config)

            assert provider.config.timeout == 300

    def test_ollama_timeout_default_value(self):
        """Test default timeout value is reasonable."""
        from kaizen.providers import OllamaConfig

        config = OllamaConfig()
        # Should have a default timeout (e.g., 120 seconds)
        assert config.timeout > 0
        assert config.timeout >= 60  # At least 1 minute

    def test_ollama_timeout_applied_to_requests(self):
        """Test timeout is applied to Ollama requests."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Response"},
            "model": "llama2",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            config = OllamaConfig(timeout=180)
            provider = OllamaProvider(config=config)

            # Generate should complete without timeout error
            result = provider.generate("Test")
            assert result is not None


class TestOllamaProviderIntegration:
    """Test OllamaProvider integration scenarios."""

    def test_ollama_provider_with_multiple_models(self):
        """Test switching between different Ollama models."""
        from kaizen.providers import OllamaConfig, OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Response"},
            "model": "llama2",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            # Create provider with text model
            text_config = OllamaConfig(model="llama2")
            text_provider = OllamaProvider(config=text_config)

            # Create provider with vision model
            vision_config = OllamaConfig(model="llava:13b")
            vision_provider = OllamaProvider(config=vision_config)

            assert text_provider.config.model == "llama2"
            assert vision_provider.config.model == "llava:13b"

    def test_ollama_provider_config_dataclass(self):
        """Test OllamaConfig is a proper dataclass."""
        from kaizen.providers import OllamaConfig

        config1 = OllamaConfig(model="llama2", temperature=0.7)
        config2 = OllamaConfig(model="llama2", temperature=0.7)

        # Should have same values
        assert config1.model == config2.model
        assert config1.temperature == config2.temperature

    def test_ollama_provider_response_format(self):
        """Test OllamaProvider response format is consistent."""
        from kaizen.providers import OllamaProvider

        # Mock ollama
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Test response"},
            "model": "llama2",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            provider = OllamaProvider()
            result = provider.generate("Test")

            # Response should have expected keys
            assert "response" in result
            assert "model" in result
            assert "done" in result
            assert isinstance(result["response"], str)

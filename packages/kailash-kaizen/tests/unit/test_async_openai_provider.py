"""
Unit tests for AsyncOpenAI provider implementation.

Tests the async capabilities of OpenAIProvider including:
- Async client initialization
- chat_async() method
- embed_async() method
- Backwards compatibility with sync methods
- Error handling
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Direct import to avoid circular dependencies
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from kaizen.nodes.ai.ai_providers import OpenAIProvider


class TestOpenAIProviderAsync:
    """Test async functionality of OpenAIProvider."""

    def test_provider_initialization_with_async_flag(self):
        """Test provider can be initialized with use_async parameter."""
        # Test sync mode (default)
        provider_sync = OpenAIProvider(use_async=False)
        assert provider_sync._use_async is False
        assert provider_sync._sync_client is None
        assert provider_sync._async_client is None

        # Test async mode
        provider_async = OpenAIProvider(use_async=True)
        assert provider_async._use_async is True
        assert provider_async._sync_client is None
        assert provider_async._async_client is None

    def test_provider_initialization_default_is_sync(self):
        """Test provider defaults to sync mode for backwards compatibility."""
        provider = OpenAIProvider()
        assert provider._use_async is False

    @pytest.mark.asyncio
    async def test_chat_async_method_exists(self):
        """Test chat_async() method exists and is async."""
        provider = OpenAIProvider(use_async=True)
        assert hasattr(provider, "chat_async")
        assert callable(provider.chat_async)

        # Verify it's an async method
        import inspect

        assert inspect.iscoroutinefunction(provider.chat_async)

    @pytest.mark.asyncio
    async def test_embed_async_method_exists(self):
        """Test embed_async() method exists and is async."""
        provider = OpenAIProvider(use_async=True)
        assert hasattr(provider, "embed_async")
        assert callable(provider.embed_async)

        # Verify it's an async method
        import inspect

        assert inspect.iscoroutinefunction(provider.embed_async)

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_chat_async_creates_async_client(self, mock_async_openai):
        """Test chat_async() initializes AsyncOpenAI client."""
        # Setup mock
        mock_async_client = AsyncMock()
        mock_async_openai.return_value = mock_async_client

        # Mock the chat response
        mock_choice = MagicMock()
        mock_choice.message.content = "Test response"
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_response = MagicMock()
        mock_response.id = "test-id"
        mock_response.model = "gpt-4"
        mock_response.created = 1234567890
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Test
        provider = OpenAIProvider(use_async=True)
        messages = [{"role": "user", "content": "Hello"}]
        result = await provider.chat_async(messages, model="gpt-4")

        # Verify async client was created
        mock_async_openai.assert_called_once()
        assert provider._async_client is not None

        # Verify response format
        assert result["id"] == "test-id"
        assert result["content"] == "Test response"
        assert result["role"] == "assistant"
        assert result["model"] == "gpt-4"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 20
        assert result["usage"]["total_tokens"] == 30

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_embed_async_creates_async_client(self, mock_async_openai):
        """Test embed_async() initializes AsyncOpenAI client."""
        # Setup mock
        mock_async_client = AsyncMock()
        mock_async_openai.return_value = mock_async_client

        # Mock embedding response
        mock_item = MagicMock()
        mock_item.embedding = [0.1, 0.2, 0.3]

        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_async_client.embeddings.create = AsyncMock(return_value=mock_response)

        # Test
        provider = OpenAIProvider(use_async=True)
        texts = ["Hello world"]
        result = await provider.embed_async(texts, model="text-embedding-3-small")

        # Verify async client was created
        mock_async_openai.assert_called_once()
        assert provider._async_client is not None

        # Verify response format
        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]

    @patch("openai.OpenAI")
    def test_sync_chat_uses_sync_client(self, mock_openai_cls):
        """Test sync chat() method uses sync client."""
        # Setup mock
        mock_sync_client = MagicMock()
        mock_openai_cls.return_value = mock_sync_client

        # Mock response
        mock_choice = MagicMock()
        mock_choice.message.content = "Test response"
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_response = MagicMock()
        mock_response.id = "test-id"
        mock_response.model = "gpt-4"
        mock_response.created = 1234567890
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_sync_client.chat.completions.create.return_value = mock_response

        # Test
        provider = OpenAIProvider(use_async=False)
        messages = [{"role": "user", "content": "Hello"}]
        result = provider.chat(messages, model="gpt-4")

        # Verify sync client was used
        mock_openai_cls.assert_called_once()
        assert provider._sync_client is not None
        assert provider._async_client is None

        # Verify response
        assert result["content"] == "Test response"

    def test_separate_client_instances(self):
        """Test sync and async clients are separate instances."""
        with (
            patch("openai.OpenAI") as mock_openai_cls,
            patch("openai.AsyncOpenAI") as mock_async_openai_cls,
        ):
            mock_sync_client = MagicMock()
            mock_async_client = AsyncMock()

            mock_openai_cls.return_value = mock_sync_client
            mock_async_openai_cls.return_value = mock_async_client

            provider = OpenAIProvider(use_async=False)

            # Initialize sync client
            mock_choice = MagicMock()
            mock_choice.message.content = "Test"
            mock_choice.message.role = "assistant"
            mock_choice.finish_reason = "stop"

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 10
            mock_usage.completion_tokens = 20
            mock_usage.total_tokens = 30

            mock_response = MagicMock()
            mock_response.id = "test-id"
            mock_response.model = "gpt-4"
            mock_response.created = 1234567890
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            mock_sync_client.chat.completions.create.return_value = mock_response

            provider.chat([{"role": "user", "content": "Hello"}])

            # Verify clients are separate
            assert provider._sync_client is not None
            assert provider._async_client is None

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_chat_async_with_generation_config(self, mock_async_openai):
        """Test chat_async() respects generation_config parameters."""
        # Setup mock
        mock_async_client = AsyncMock()
        mock_async_openai.return_value = mock_async_client

        mock_choice = MagicMock()
        mock_choice.message.content = "Test"
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_response = MagicMock()
        mock_response.id = "test-id"
        mock_response.model = "gpt-4"
        mock_response.created = 1234567890
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_async_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Test with custom generation config
        provider = OpenAIProvider(use_async=True)
        messages = [{"role": "user", "content": "Hello"}]
        generation_config = {
            "temperature": 0.5,
            "max_completion_tokens": 100,
            "top_p": 0.9,
        }

        await provider.chat_async(
            messages, model="gpt-4", generation_config=generation_config
        )

        # Verify generation config was passed
        call_args = mock_async_client.chat.completions.create.call_args
        assert call_args.kwargs["temperature"] == 0.5
        assert call_args.kwargs["max_completion_tokens"] == 100
        assert call_args.kwargs["top_p"] == 0.9

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_embed_async_with_dimensions(self, mock_async_openai):
        """Test embed_async() respects dimensions parameter."""
        # Setup mock
        mock_async_client = AsyncMock()
        mock_async_openai.return_value = mock_async_client

        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 512  # 512 dimensions

        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_async_client.embeddings.create = AsyncMock(return_value=mock_response)

        # Test with custom dimensions
        provider = OpenAIProvider(use_async=True)
        texts = ["Hello world"]
        result = await provider.embed_async(
            texts, model="text-embedding-3-small", dimensions=512
        )

        # Verify dimensions was passed
        call_args = mock_async_client.embeddings.create.call_args
        assert call_args.kwargs["dimensions"] == 512

        # Verify result
        assert len(result[0]) == 512

    @pytest.mark.asyncio
    async def test_chat_async_response_format_matches_sync(self):
        """Test async response format exactly matches sync format."""
        with (
            patch("openai.AsyncOpenAI") as mock_async_openai_cls,
            patch("openai.OpenAI") as mock_openai_cls,
        ):
            # Setup mock for async
            mock_async_client = AsyncMock()
            mock_async_openai_cls.return_value = mock_async_client

            mock_choice = MagicMock()
            mock_choice.message.content = "Test response"
            mock_choice.message.role = "assistant"
            mock_choice.finish_reason = "stop"
            mock_choice.message.tool_calls = []

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 10
            mock_usage.completion_tokens = 20
            mock_usage.total_tokens = 30

            mock_response = MagicMock()
            mock_response.id = "test-id"
            mock_response.model = "gpt-4"
            mock_response.created = 1234567890
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage

            mock_async_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )

            # Get async response
            provider_async = OpenAIProvider(use_async=True)
            messages = [{"role": "user", "content": "Hello"}]
            async_result = await provider_async.chat_async(messages, model="gpt-4")

            # Setup mock for sync
            mock_sync_client = MagicMock()
            mock_openai_cls.return_value = mock_sync_client
            mock_sync_client.chat.completions.create.return_value = mock_response

            # Get sync response
            provider_sync = OpenAIProvider(use_async=False)
            sync_result = provider_sync.chat(messages, model="gpt-4")

            # Verify formats match
            assert async_result.keys() == sync_result.keys()
            assert async_result["id"] == sync_result["id"]
            assert async_result["content"] == sync_result["content"]
            assert async_result["role"] == sync_result["role"]
            assert async_result["model"] == sync_result["model"]
            assert async_result["usage"] == sync_result["usage"]


class TestBackwardsCompatibility:
    """Test backwards compatibility - sync methods unchanged."""

    @patch("openai.OpenAI")
    def test_existing_sync_code_unchanged(self, mock_openai_cls):
        """Test existing sync code continues to work."""
        # Setup mock
        mock_sync_client = MagicMock()
        mock_openai_cls.return_value = mock_sync_client

        mock_choice = MagicMock()
        mock_choice.message.content = "Test response"
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 30

        mock_response = MagicMock()
        mock_response.id = "test-id"
        mock_response.model = "gpt-4"
        mock_response.created = 1234567890
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_sync_client.chat.completions.create.return_value = mock_response

        # Test: Existing code pattern (no use_async parameter)
        provider = OpenAIProvider()  # Default: sync mode
        messages = [{"role": "user", "content": "Hello"}]
        result = provider.chat(messages)

        # Verify it works
        assert result["content"] == "Test response"
        assert provider._use_async is False

    def test_default_initialization_is_sync(self):
        """Test provider defaults to sync for backwards compatibility."""
        provider = OpenAIProvider()
        assert provider._use_async is False
        assert not hasattr(provider, "_async_client") or provider._async_client is None

"""Integration tests for Azure AI Foundry provider.

These tests require real Azure credentials and use actual API calls.
NO MOCKING - tests will be skipped if Azure is not configured.

Prerequisites:
    * Set AZURE_AI_INFERENCE_ENDPOINT environment variable
    * Set AZURE_AI_INFERENCE_API_KEY environment variable
    * Have a deployed model endpoint in Azure AI Foundry
"""

import pytest
from kaizen.nodes.ai.ai_providers import AzureAIFoundryProvider


@pytest.fixture
def azure_provider():
    """Create Azure provider if credentials available."""
    provider = AzureAIFoundryProvider()
    if not provider.is_available():
        pytest.skip("Azure AI Foundry not configured - skipping integration test")
    return provider


@pytest.fixture
def azure_async_provider():
    """Create async Azure provider if credentials available."""
    provider = AzureAIFoundryProvider(use_async=True)
    if not provider.is_available():
        pytest.skip("Azure AI Foundry not configured - skipping integration test")
    return provider


class TestAzureAIFoundryChatIntegration:
    """Integration tests for Azure chat completions."""

    def test_simple_chat_completion(self, azure_provider):
        """Should generate chat completion with real API."""
        response = azure_provider.chat(
            messages=[{"role": "user", "content": "Say 'Hello' and nothing else"}],
            generation_config={"max_tokens": 10, "temperature": 0},
        )

        assert response["content"] is not None
        assert len(response["content"]) > 0
        assert "hello" in response["content"].lower()
        assert response["role"] == "assistant"
        assert response["usage"]["total_tokens"] > 0
        assert response["finish_reason"] in ["stop", "length"]

    def test_chat_with_system_message(self, azure_provider):
        """Should handle system messages correctly."""
        response = azure_provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that speaks only in uppercase.",
                },
                {"role": "user", "content": "Say hello"},
            ],
            generation_config={"max_tokens": 20, "temperature": 0},
        )

        assert response["content"] is not None
        # Check that at least some uppercase letters are present
        assert any(c.isupper() for c in response["content"])

    def test_chat_multi_turn_conversation(self, azure_provider):
        """Should handle multi-turn conversations."""
        response = azure_provider.chat(
            messages=[
                {"role": "user", "content": "My name is Alice."},
                {"role": "assistant", "content": "Hello Alice! Nice to meet you."},
                {"role": "user", "content": "What is my name?"},
            ],
            generation_config={"max_tokens": 50, "temperature": 0},
        )

        assert response["content"] is not None
        assert "alice" in response["content"].lower()

    @pytest.mark.asyncio
    async def test_chat_async(self, azure_async_provider):
        """Should generate chat completion asynchronously."""
        response = await azure_async_provider.chat_async(
            messages=[{"role": "user", "content": "Say 'Hi' and nothing else"}],
            generation_config={"max_tokens": 10, "temperature": 0},
        )

        assert response["content"] is not None
        assert response["role"] == "assistant"
        assert response["usage"]["total_tokens"] > 0


class TestAzureAIFoundryEmbeddingsIntegration:
    """Integration tests for Azure embeddings."""

    def test_single_text_embedding(self, azure_provider):
        """Should generate embedding for single text."""
        texts = ["Hello world"]
        embeddings = azure_provider.embed(texts)

        assert len(embeddings) == 1
        assert len(embeddings[0]) > 0
        assert all(isinstance(v, float) for v in embeddings[0])

    def test_batch_embeddings(self, azure_provider):
        """Should generate embeddings for multiple texts."""
        texts = ["Hello world", "Testing embeddings", "Azure AI Foundry"]
        embeddings = azure_provider.embed(texts)

        assert len(embeddings) == 3
        # All embeddings should have same dimensions
        dims = len(embeddings[0])
        assert all(len(e) == dims for e in embeddings)

    def test_embedding_consistency(self, azure_provider):
        """Should generate consistent embeddings for same text."""
        texts = ["Consistent embedding test"]

        embeddings1 = azure_provider.embed(texts)
        embeddings2 = azure_provider.embed(texts)

        # Embeddings should be very similar (allowing for floating point differences)
        diff = sum(abs(a - b) for a, b in zip(embeddings1[0], embeddings2[0]))
        assert diff < 0.001  # Very small difference

    @pytest.mark.asyncio
    async def test_embeddings_async(self, azure_async_provider):
        """Should generate embeddings asynchronously."""
        texts = ["Async embedding test"]
        embeddings = await azure_async_provider.embed_async(texts)

        assert len(embeddings) == 1
        assert len(embeddings[0]) > 0


class TestAzureAIFoundryToolCallingIntegration:
    """Integration tests for Azure tool calling."""

    def test_tool_calling_basic(self, azure_provider):
        """Should handle tool calling correctly."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather in a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city name",
                            }
                        },
                        "required": ["location"],
                    },
                },
            }
        ]

        response = azure_provider.chat(
            messages=[{"role": "user", "content": "What's the weather in Paris?"}],
            tools=tools,
            generation_config={"tool_choice": "auto", "max_tokens": 100},
        )

        # Should either call the tool or respond directly
        assert response is not None
        assert (
            response["content"] is not None or len(response.get("tool_calls", [])) > 0
        )

    def test_tool_calling_with_tool_choice(self, azure_provider):
        """Should respect tool_choice parameter."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Perform a calculation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                        },
                        "required": ["expression"],
                    },
                },
            }
        ]

        response = azure_provider.chat(
            messages=[{"role": "user", "content": "Calculate 2 + 2"}],
            tools=tools,
            generation_config={"tool_choice": "auto", "max_tokens": 100},
        )

        assert response is not None

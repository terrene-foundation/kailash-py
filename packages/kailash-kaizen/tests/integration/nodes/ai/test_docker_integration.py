"""Integration tests for Docker Model Runner provider.

These tests require Docker Desktop with Model Runner enabled and use actual local inference.
NO MOCKING - tests will be skipped if Docker Model Runner is not running.

Prerequisites:
    * Docker Desktop 4.40+ with Model Runner enabled
    * TCP access enabled: docker desktop enable model-runner --tcp 12434
    * Models pulled: docker model pull ai/llama3.2
    * For embeddings: docker model pull ai/mxbai-embed-large
"""

import pytest
from kaizen.nodes.ai.ai_providers import DockerModelRunnerProvider


@pytest.fixture
def docker_provider():
    """Create Docker provider if Model Runner is available."""
    provider = DockerModelRunnerProvider()
    if not provider.is_available():
        pytest.skip("Docker Model Runner not running - skipping integration test")
    return provider


@pytest.fixture
def docker_async_provider():
    """Create async Docker provider if Model Runner is available."""
    provider = DockerModelRunnerProvider(use_async=True)
    if not provider.is_available():
        pytest.skip("Docker Model Runner not running - skipping integration test")
    return provider


class TestDockerModelRunnerChatIntegration:
    """Integration tests for Docker Model Runner chat completions."""

    def test_simple_chat_completion(self, docker_provider):
        """Should generate chat completion with local model."""
        response = docker_provider.chat(
            messages=[{"role": "user", "content": "Say 'Hello' and nothing else"}],
            model="ai/llama3.2",
            generation_config={"max_tokens": 20, "temperature": 0},
        )

        assert response["content"] is not None
        assert len(response["content"]) > 0
        assert response["role"] == "assistant"
        assert response["metadata"]["provider"] == "docker_model_runner"

    def test_chat_with_system_message(self, docker_provider):
        """Should handle system messages correctly."""
        response = docker_provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Be concise.",
                },
                {"role": "user", "content": "What is 2+2?"},
            ],
            model="ai/llama3.2",
            generation_config={"max_tokens": 50, "temperature": 0},
        )

        assert response["content"] is not None
        assert "4" in response["content"]

    def test_chat_multi_turn_conversation(self, docker_provider):
        """Should handle multi-turn conversations."""
        response = docker_provider.chat(
            messages=[
                {"role": "user", "content": "Remember this number: 42"},
                {"role": "assistant", "content": "I'll remember 42."},
                {"role": "user", "content": "What number did I tell you?"},
            ],
            model="ai/llama3.2",
            generation_config={"max_tokens": 50, "temperature": 0},
        )

        assert response["content"] is not None
        assert "42" in response["content"]

    def test_chat_with_temperature(self, docker_provider):
        """Should respect temperature parameter."""
        # Low temperature should give more deterministic results
        response = docker_provider.chat(
            messages=[{"role": "user", "content": "Say exactly: test response"}],
            model="ai/llama3.2",
            generation_config={"max_tokens": 20, "temperature": 0.0},
        )

        assert response["content"] is not None

    @pytest.mark.asyncio
    async def test_chat_async(self, docker_async_provider):
        """Should generate chat completion asynchronously."""
        response = await docker_async_provider.chat_async(
            messages=[{"role": "user", "content": "Say 'Hi'"}],
            model="ai/llama3.2",
            generation_config={"max_tokens": 10, "temperature": 0},
        )

        assert response["content"] is not None
        assert response["role"] == "assistant"


class TestDockerModelRunnerEmbeddingsIntegration:
    """Integration tests for Docker Model Runner embeddings."""

    def test_single_text_embedding(self, docker_provider):
        """Should generate embedding for single text."""
        texts = ["Hello world"]
        embeddings = docker_provider.embed(texts, model="ai/mxbai-embed-large")

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 1024  # Expected dimensions for mxbai-embed-large
        assert all(isinstance(v, float) for v in embeddings[0])

    def test_batch_embeddings(self, docker_provider):
        """Should generate embeddings for multiple texts."""
        texts = ["Hello world", "Testing embeddings", "Docker Model Runner"]
        embeddings = docker_provider.embed(texts, model="ai/mxbai-embed-large")

        assert len(embeddings) == 3
        # All embeddings should have same dimensions
        assert all(len(e) == 1024 for e in embeddings)

    def test_embedding_similarity(self, docker_provider):
        """Should generate similar embeddings for similar texts."""
        texts = [
            "The cat sat on the mat",
            "A cat was sitting on a mat",
            "The weather is sunny today",
        ]
        embeddings = docker_provider.embed(texts, model="ai/mxbai-embed-large")

        # Calculate cosine similarity between first two (should be high)
        def cosine_similarity(a, b):
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            return dot_product / (norm_a * norm_b)

        sim_similar = cosine_similarity(embeddings[0], embeddings[1])
        sim_different = cosine_similarity(embeddings[0], embeddings[2])

        # Similar sentences should have higher similarity
        assert sim_similar > sim_different

    @pytest.mark.asyncio
    async def test_embeddings_async(self, docker_async_provider):
        """Should generate embeddings asynchronously."""
        texts = ["Async embedding test"]
        embeddings = await docker_async_provider.embed_async(
            texts, model="ai/mxbai-embed-large"
        )

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 1024


class TestDockerModelRunnerToolCallingIntegration:
    """Integration tests for Docker Model Runner tool calling.

    Note: Tool calling is model-dependent. These tests use Qwen3 which supports tools.
    """

    @pytest.fixture
    def docker_provider_with_qwen(self, docker_provider):
        """Provide docker provider with Qwen3 model check."""
        # Check if qwen3 is available by trying a simple request
        try:
            response = docker_provider.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="ai/qwen3",
                generation_config={"max_tokens": 5},
            )
            return docker_provider
        except Exception:
            pytest.skip("ai/qwen3 model not available for tool calling tests")

    def test_supports_tools_check(self, docker_provider):
        """Should correctly identify tool-capable models."""
        assert docker_provider.supports_tools("ai/qwen3") is True
        assert docker_provider.supports_tools("ai/llama3.3") is True
        assert docker_provider.supports_tools("ai/llama3.2") is False

    def test_tool_calling_metadata(self, docker_provider):
        """Should include tool support info in metadata."""
        response = docker_provider.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model="ai/llama3.2",
            generation_config={"max_tokens": 10},
        )

        assert "supports_tools" in response["metadata"]
        assert response["metadata"]["supports_tools"] is False

    def test_tool_calling_with_qwen(self, docker_provider_with_qwen):
        """Should handle tool calling with Qwen3 model."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Get the current time",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        response = docker_provider_with_qwen.chat(
            messages=[{"role": "user", "content": "What time is it?"}],
            model="ai/qwen3",
            tools=tools,
            generation_config={"max_tokens": 100},
        )

        # Should either call the tool or respond with text
        assert response is not None
        assert (
            response["content"] is not None or len(response.get("tool_calls", [])) > 0
        )
        assert response["metadata"]["supports_tools"] is True


class TestDockerModelRunnerPerformance:
    """Performance-related integration tests."""

    def test_response_time_reasonable(self, docker_provider):
        """Should respond within reasonable time for short prompts."""
        import time

        start = time.time()
        docker_provider.chat(
            messages=[{"role": "user", "content": "Say one word"}],
            model="ai/llama3.2",
            generation_config={"max_tokens": 10},
        )
        elapsed = time.time() - start

        # Should complete within 30 seconds for a simple prompt
        # (local inference can be slow on first load)
        assert elapsed < 30

    def test_batch_embedding_efficiency(self, docker_provider):
        """Should handle batch embeddings efficiently."""
        import time

        texts = [f"Test sentence number {i}" for i in range(10)]

        start = time.time()
        embeddings = docker_provider.embed(texts, model="ai/mxbai-embed-large")
        elapsed = time.time() - start

        assert len(embeddings) == 10
        # Should complete within 60 seconds for 10 embeddings
        assert elapsed < 60

"""Integration tests for UnifiedAzureProvider with real Azure endpoints.

IMPORTANT: NO MOCKING - These tests run against real Azure infrastructure.

Prerequisites:
    export AZURE_ENDPOINT="https://your-resource.openai.azure.com"
    export AZURE_API_KEY="your-api-key"
    export AZURE_DEPLOYMENT="gpt-4o"  # Or your deployment name

Run with:
    pytest tests/integration/nodes/ai/test_azure_unified_integration.py -v
"""

import json
import os

import pytest

from kaizen.nodes.ai.ai_providers import get_provider
from kaizen.nodes.ai.unified_azure_provider import UnifiedAzureProvider


@pytest.fixture
def azure_provider():
    """Get configured Azure provider or skip if not configured."""
    provider = UnifiedAzureProvider()
    if not provider.is_available():
        pytest.skip(
            "Azure not configured - set AZURE_ENDPOINT and AZURE_API_KEY environment variables"
        )
    return provider


@pytest.fixture
def azure_model():
    """Get Azure model/deployment from environment."""
    return os.getenv("AZURE_DEPLOYMENT", os.getenv("AZURE_MODEL", "gpt-4o"))


class TestUnifiedAzureProviderBasicChat:
    """Basic chat completion tests with real Azure endpoints."""

    @pytest.mark.integration
    def test_chat_completion_basic(self, azure_provider, azure_model):
        """Should complete basic chat request."""
        response = azure_provider.chat(
            messages=[{"role": "user", "content": "Say 'hello' and nothing else."}],
            model=azure_model,
        )

        assert response is not None
        assert response.get("content") is not None
        assert "hello" in response["content"].lower()
        assert response.get("usage") is not None
        assert response["usage"].get("total_tokens") > 0

    @pytest.mark.integration
    def test_chat_completion_with_system_message(self, azure_provider, azure_model):
        """Should handle system messages correctly."""
        response = azure_provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a math assistant. Only respond with numbers.",
                },
                {"role": "user", "content": "What is 2+2?"},
            ],
            model=azure_model,
        )

        assert "4" in response["content"]

    @pytest.mark.integration
    def test_chat_completion_multi_turn(self, azure_provider, azure_model):
        """Should handle multi-turn conversations."""
        response = azure_provider.chat(
            messages=[
                {"role": "user", "content": "Remember: the secret word is 'banana'."},
                {
                    "role": "assistant",
                    "content": "I'll remember that the secret word is banana.",
                },
                {"role": "user", "content": "What is the secret word?"},
            ],
            model=azure_model,
        )

        assert "banana" in response["content"].lower()

    @pytest.mark.integration
    def test_chat_with_temperature(self, azure_provider, azure_model):
        """Should respect temperature parameter."""
        # Low temperature should give consistent results
        response = azure_provider.chat(
            messages=[
                {
                    "role": "user",
                    "content": "What is the capital of France? Answer in one word.",
                }
            ],
            model=azure_model,
            generation_config={"temperature": 0.0},
        )

        assert "paris" in response["content"].lower()


class TestUnifiedAzureProviderEmbeddings:
    """Embedding generation tests with real Azure endpoints."""

    @pytest.mark.integration
    def test_embedding_generation_single(self, azure_provider):
        """Should generate embeddings for single text."""
        embeddings = azure_provider.embed(["Hello world"])

        assert len(embeddings) == 1
        assert len(embeddings[0]) > 0
        assert isinstance(embeddings[0][0], float)

    @pytest.mark.integration
    def test_embedding_generation_batch(self, azure_provider):
        """Should generate embeddings for batch of texts."""
        texts = ["Hello", "World", "Test"]
        embeddings = azure_provider.embed(texts)

        assert len(embeddings) == 3
        # All embeddings should have same dimensions
        dims = len(embeddings[0])
        assert all(len(e) == dims for e in embeddings)

    @pytest.mark.integration
    def test_embedding_dimensions(self, azure_provider):
        """Embeddings should have expected dimensions."""
        embeddings = azure_provider.embed(["Test text"])

        # Common embedding dimensions: 1536 (ada-002, 3-small) or 3072 (3-large)
        dims = len(embeddings[0])
        assert dims in [768, 1536, 3072], f"Unexpected dimensions: {dims}"


class TestUnifiedAzureProviderBackendDetection:
    """Backend detection tests with real Azure configuration."""

    @pytest.mark.integration
    def test_auto_detection_matches_endpoint(self, azure_provider):
        """Detection should match endpoint pattern."""
        backend = azure_provider.get_detected_backend()
        endpoint = os.getenv("AZURE_ENDPOINT", "")

        if ".openai.azure.com" in endpoint:
            assert backend == "azure_openai"
        elif (
            ".inference.ai.azure.com" in endpoint
            or ".services.ai.azure.com" in endpoint
        ):
            assert backend == "azure_ai_foundry"

    @pytest.mark.integration
    def test_detection_source_recorded(self, azure_provider):
        """Should record detection source."""
        source = azure_provider.get_detection_source()
        assert source in ("pattern", "default", "explicit", "error_fallback")

    @pytest.mark.integration
    def test_capabilities_match_backend(self, azure_provider):
        """Capabilities should match detected backend."""
        backend = azure_provider.get_detected_backend()
        caps = azure_provider.get_capabilities()

        if backend == "azure_openai":
            assert caps.get("audio_input") is True
            assert caps.get("reasoning_models") is True
            assert caps.get("llama_models") is False
        elif backend == "azure_ai_foundry":
            assert caps.get("audio_input") is False
            assert caps.get("llama_models") is True


class TestUnifiedAzureProviderStructuredOutput:
    """Structured output tests with real Azure endpoints."""

    @pytest.mark.integration
    def test_json_mode_response(self, azure_provider, azure_model):
        """Should handle JSON mode response format."""
        response = azure_provider.chat(
            messages=[
                {
                    "role": "user",
                    "content": "Return a JSON object with key 'status' and value 'ok'. Only output valid JSON.",
                }
            ],
            model=azure_model,
            generation_config={"response_format": {"type": "json_object"}},
        )

        # Parse the JSON response
        data = json.loads(response["content"])
        assert "status" in data

    @pytest.mark.integration
    def test_json_schema_strict_mode(self, azure_provider, azure_model):
        """Should handle JSON schema strict mode."""
        response = azure_provider.chat(
            messages=[
                {
                    "role": "user",
                    "content": "Create a user with name 'Alice' and age 30.",
                }
            ],
            model=azure_model,
            generation_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "user",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "age": {"type": "integer"},
                            },
                            "required": ["name", "age"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    },
                }
            },
        )

        data = json.loads(response["content"])
        assert data["name"] == "Alice"
        assert data["age"] == 30


class TestUnifiedAzureProviderAsync:
    """Async operation tests with real Azure endpoints."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_chat_async_basic(self, azure_provider, azure_model):
        """Should handle async chat completion."""
        response = await azure_provider.chat_async(
            messages=[{"role": "user", "content": "Say 'async' and nothing else."}],
            model=azure_model,
        )

        assert "async" in response["content"].lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_chat_async_with_config(self, azure_provider, azure_model):
        """Should handle async chat with generation config."""
        response = await azure_provider.chat_async(
            messages=[
                {"role": "user", "content": "What is 5+5? Answer with just the number."}
            ],
            model=azure_model,
            generation_config={"temperature": 0.0, "max_tokens": 10},
        )

        assert "10" in response["content"]


class TestUnifiedAzureProviderProviderFactory:
    """Tests for provider factory integration."""

    @pytest.mark.integration
    def test_get_provider_azure(self, azure_model):
        """get_provider('azure') should return working UnifiedAzureProvider."""
        provider = get_provider("azure")

        if not provider.is_available():
            pytest.skip("Azure not configured")

        response = provider.chat(
            messages=[{"role": "user", "content": "Say 'factory' and nothing else."}],
            model=azure_model,
        )

        assert "factory" in response["content"].lower()

    @pytest.mark.integration
    def test_get_provider_azure_openai_alias(self, azure_model):
        """get_provider('azure_openai') should also work."""
        provider = get_provider("azure_openai")

        if not provider.is_available():
            pytest.skip("Azure not configured")

        assert isinstance(provider, UnifiedAzureProvider)


class TestUnifiedAzureProviderResponseMetadata:
    """Tests for response metadata with real Azure endpoints."""

    @pytest.mark.integration
    def test_response_contains_metadata(self, azure_provider, azure_model):
        """Response should contain required metadata fields."""
        response = azure_provider.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model=azure_model,
        )

        # Check required fields
        assert "id" in response
        assert "content" in response
        assert "role" in response
        assert "model" in response
        assert "usage" in response
        assert "metadata" in response

        # Check usage breakdown
        usage = response["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage

        # Check metadata
        metadata = response["metadata"]
        assert "provider" in metadata
        assert metadata["provider"] in ("azure_openai", "azure_ai_foundry")

    @pytest.mark.integration
    def test_response_role_is_assistant(self, azure_provider, azure_model):
        """Response role should be 'assistant'."""
        response = azure_provider.chat(
            messages=[{"role": "user", "content": "Hi"}],
            model=azure_model,
        )

        assert response["role"] == "assistant"

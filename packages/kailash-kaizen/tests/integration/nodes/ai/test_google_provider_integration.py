"""Integration tests for Google Gemini provider using REAL API calls.

These tests require GOOGLE_API_KEY to be set and will make actual API calls.
Run with: pytest tests/integration/nodes/ai/test_google_provider_integration.py -v
"""

import base64
import os

import pytest

# Skip entire module if no Google API key
pytestmark = pytest.mark.skipif(
    not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
    reason="GOOGLE_API_KEY or GEMINI_API_KEY not set",
)


class TestGoogleGeminiProviderRealAPI:
    """Integration tests using real Google Gemini API."""

    def test_chat_simple_response(self):
        """Should generate a real chat response."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()
        assert provider.is_available(), "Provider should be available"

        messages = [
            {"role": "user", "content": "What is 2 + 2? Answer with just the number."}
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"temperature": 0, "max_tokens": 10},
        )

        # Verify response structure
        assert "id" in response
        assert "content" in response
        assert response["role"] == "assistant"
        assert response["model"] == "gemini-2.0-flash"
        assert "usage" in response
        assert response["usage"]["total_tokens"] > 0

        # Verify content contains the answer
        assert "4" in response["content"]

    def test_chat_with_system_message(self):
        """Should properly handle system messages."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {
                "role": "system",
                "content": "You are a pirate. Always respond like a pirate.",
            },
            {"role": "user", "content": "Hello!"},
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"temperature": 0.5, "max_tokens": 50},
        )

        assert response["content"] is not None
        assert len(response["content"]) > 0

    def test_chat_multi_turn_conversation(self):
        """Should handle multi-turn conversations."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {"role": "user", "content": "My name is Alice."},
            {"role": "assistant", "content": "Hello Alice! Nice to meet you."},
            {"role": "user", "content": "What is my name?"},
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"temperature": 0, "max_tokens": 20},
        )

        # Should remember the name from context
        assert "Alice" in response["content"]

    def test_embeddings_single_text(self):
        """Should generate embeddings for a single text."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        texts = ["Hello, world!"]
        embeddings = provider.embed(texts=texts, model="text-embedding-004")

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768  # Expected dimensions
        assert all(isinstance(v, float) for v in embeddings[0])

    def test_embeddings_multiple_texts(self):
        """Should generate embeddings for multiple texts."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        texts = ["Hello", "World", "How are you?"]
        embeddings = provider.embed(texts=texts, model="text-embedding-004")

        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 768

    def test_vision_with_base64_image(self):
        """Should process images via base64 encoding."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        # Create a 1x1 red pixel PNG
        red_pixel_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        )
        test_image_b64 = base64.b64encode(red_pixel_png).decode()

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What color is this 1x1 pixel image? Answer in one word.",
                    },
                    {
                        "type": "image",
                        "base64": test_image_b64,
                        "media_type": "image/png",
                    },
                ],
            }
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"temperature": 0, "max_tokens": 10},
        )

        # Should identify red color
        assert "red" in response["content"].lower()

    def test_generation_config_temperature(self):
        """Should respect temperature setting."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [{"role": "user", "content": "Say hello"}]

        # Low temperature should give consistent response
        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"temperature": 0, "max_tokens": 20},
        )

        assert response["content"] is not None

    def test_generation_config_max_tokens(self):
        """Should respect max_tokens limit."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [
            {"role": "user", "content": "Write a very long story about a dragon."}
        ]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"max_tokens": 10},
        )

        # Response should be short due to token limit
        assert response["usage"]["completion_tokens"] <= 15  # Some tolerance

    def test_finish_reason_stop(self):
        """Should return 'stop' finish reason for normal completion."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [{"role": "user", "content": "Say hello"}]

        response = provider.chat(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"max_tokens": 100},
        )

        assert response["finish_reason"] == "stop"

    def test_usage_metrics_populated(self):
        """Should populate usage metrics correctly."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [{"role": "user", "content": "Hello"}]

        response = provider.chat(messages=messages, model="gemini-2.0-flash")

        usage = response["usage"]
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0
        assert (
            usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        )


class TestGoogleGeminiAsyncRealAPI:
    """Async integration tests using real Google Gemini API."""

    @pytest.mark.asyncio
    async def test_chat_async(self):
        """Should generate chat response asynchronously."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        messages = [{"role": "user", "content": "Say 'async works'"}]

        response = await provider.chat_async(
            messages=messages,
            model="gemini-2.0-flash",
            generation_config={"temperature": 0, "max_tokens": 20},
        )

        assert (
            "async" in response["content"].lower()
            or "works" in response["content"].lower()
        )

    @pytest.mark.asyncio
    async def test_embed_async(self):
        """Should generate embeddings asynchronously."""
        from kaizen.nodes.ai.ai_providers import GoogleGeminiProvider

        provider = GoogleGeminiProvider()

        texts = ["Hello async world"]
        embeddings = await provider.embed_async(texts=texts, model="text-embedding-004")

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 768


class TestGoogleProviderViaRegistry:
    """Test accessing Google provider via the provider registry."""

    def test_get_provider_google(self):
        """Should get Google provider via registry."""
        from kaizen.nodes.ai.ai_providers import get_provider

        provider = get_provider("google")
        assert provider.is_available()

        response = provider.chat(
            messages=[{"role": "user", "content": "Say test"}],
            model="gemini-2.0-flash",
            generation_config={"max_tokens": 10},
        )
        assert response["content"] is not None

    def test_get_provider_gemini_alias(self):
        """Should get Google provider via 'gemini' alias."""
        from kaizen.nodes.ai.ai_providers import get_provider

        provider = get_provider("gemini")
        assert provider.is_available()

        response = provider.chat(
            messages=[{"role": "user", "content": "Say alias"}],
            model="gemini-2.0-flash",
            generation_config={"max_tokens": 10},
        )
        assert response["content"] is not None


class TestGoogleProviderConfigIntegration:
    """Test provider configuration with real API."""

    def test_auto_detect_finds_google(self, monkeypatch):
        """Should auto-detect Google when it's the only available provider."""
        from kaizen.config.providers import auto_detect_provider

        # Clear other providers
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_AI_INFERENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        config = auto_detect_provider()
        assert config.provider == "google"
        assert config.model == "gemini-2.0-flash"

    def test_get_google_config_real(self):
        """Should get valid Google config."""
        from kaizen.config.providers import get_google_config

        config = get_google_config()
        assert config.provider == "google"
        assert config.api_key is not None

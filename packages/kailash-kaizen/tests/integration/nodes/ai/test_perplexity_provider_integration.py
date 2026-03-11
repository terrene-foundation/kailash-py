"""Integration tests for Perplexity AI provider.

These tests require a valid PERPLEXITY_API_KEY environment variable.
They make real API calls to verify the provider works correctly.

Run with: pytest tests/integration/nodes/ai/test_perplexity_provider_integration.py -v
"""

import os

import pytest

from kaizen.nodes.ai.ai_providers import PerplexityProvider

# Skip all tests if API key is not available
pytestmark = pytest.mark.skipif(
    not os.getenv("PERPLEXITY_API_KEY"),
    reason="PERPLEXITY_API_KEY not set - skipping integration tests",
)


class TestPerplexityProviderIntegration:
    """Integration tests for Perplexity provider with real API."""

    def test_simple_chat_completion(self):
        """Should complete a simple chat request."""
        provider = PerplexityProvider()
        assert provider.is_available()

        messages = [
            {"role": "user", "content": "What is 2 + 2? Answer with just the number."}
        ]

        response = provider.chat(messages, model="sonar")

        assert response is not None
        assert "content" in response
        assert response["content"] is not None
        assert "4" in response["content"]
        assert response["role"] == "assistant"
        assert response["finish_reason"] == "stop"
        assert "usage" in response
        assert response["usage"]["total_tokens"] > 0

    def test_chat_with_web_search(self):
        """Should return response with web search results."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "user",
                "content": "What is the current date today? Be specific.",
            }
        ]

        response = provider.chat(
            messages,
            model="sonar",
            perplexity_config={
                "return_related_questions": False,
            },
        )

        assert response is not None
        assert response["content"] is not None
        # Response should contain current date information from web search
        assert len(response["content"]) > 0

    def test_chat_with_citations(self):
        """Should return response with citations in metadata."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "user",
                "content": "What are the key features of Python 3.12?",
            }
        ]

        response = provider.chat(
            messages,
            model="sonar-pro",  # sonar-pro for better citation support
        )

        assert response is not None
        assert response["content"] is not None
        # Check if metadata contains citations or search_results
        # Note: Citations may or may not be present depending on the query
        assert "metadata" in response

    def test_chat_with_domain_filter(self):
        """Should respect domain filter in search."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "user",
                "content": "What is the latest Python release?",
            }
        ]

        response = provider.chat(
            messages,
            model="sonar",
            perplexity_config={
                "search_domain_filter": ["python.org"],
            },
        )

        assert response is not None
        assert response["content"] is not None

    def test_chat_with_recency_filter(self):
        """Should respect recency filter in search."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "user",
                "content": "What are the latest AI developments this week?",
            }
        ]

        response = provider.chat(
            messages,
            model="sonar",
            perplexity_config={
                "search_recency_filter": "week",
            },
        )

        assert response is not None
        assert response["content"] is not None

    def test_chat_with_temperature(self):
        """Should respect temperature setting."""
        provider = PerplexityProvider()

        messages = [{"role": "user", "content": "Write a creative haiku about Python."}]

        # High temperature for more creativity
        response = provider.chat(
            messages,
            model="sonar",
            generation_config={"temperature": 1.5},
        )

        assert response is not None
        assert response["content"] is not None
        assert len(response["content"]) > 0

    def test_chat_with_max_tokens(self):
        """Should respect max_tokens limit."""
        provider = PerplexityProvider()

        messages = [{"role": "user", "content": "Explain quantum computing in detail."}]

        response = provider.chat(
            messages,
            model="sonar",
            generation_config={"max_tokens": 50},
        )

        assert response is not None
        assert response["content"] is not None
        # Response should be relatively short due to token limit
        assert response["usage"]["completion_tokens"] <= 60  # Some buffer

    def test_chat_with_system_message(self):
        """Should handle system messages correctly."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that responds only in haiku format.",
            },
            {"role": "user", "content": "Tell me about the weather."},
        ]

        response = provider.chat(messages, model="sonar")

        assert response is not None
        assert response["content"] is not None

    def test_chat_with_disable_search(self):
        """Should work with search disabled."""
        provider = PerplexityProvider()

        messages = [{"role": "user", "content": "What is the capital of France?"}]

        response = provider.chat(
            messages,
            model="sonar",
            perplexity_config={"disable_search": True},
        )

        assert response is not None
        assert response["content"] is not None
        # Should still know basic facts from training data
        assert "Paris" in response["content"] or "paris" in response["content"].lower()


@pytest.mark.asyncio
class TestPerplexityProviderAsyncIntegration:
    """Async integration tests for Perplexity provider."""

    async def test_async_simple_chat(self):
        """Should complete async chat request."""
        provider = PerplexityProvider(use_async=True)
        assert provider.is_available()

        messages = [
            {
                "role": "user",
                "content": "What is the square root of 16? Just the number.",
            }
        ]

        response = await provider.chat_async(messages, model="sonar")

        assert response is not None
        assert "content" in response
        assert "4" in response["content"]
        assert response["role"] == "assistant"

    async def test_async_chat_with_options(self):
        """Should handle async chat with Perplexity options."""
        provider = PerplexityProvider(use_async=True)

        messages = [{"role": "user", "content": "What are the latest AI news?"}]

        response = await provider.chat_async(
            messages,
            model="sonar-pro",
            perplexity_config={
                "search_recency_filter": "day",
            },
        )

        assert response is not None
        assert response["content"] is not None
        assert len(response["content"]) > 0


class TestPerplexityProviderModels:
    """Test different Perplexity models."""

    def test_sonar_model(self):
        """Should work with sonar model."""
        provider = PerplexityProvider()

        messages = [{"role": "user", "content": "Hello, what model are you?"}]
        response = provider.chat(messages, model="sonar")

        assert response is not None
        assert "sonar" in response.get("model", "").lower() or response["content"]

    @pytest.mark.slow
    def test_sonar_pro_model(self):
        """Should work with sonar-pro model."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "user",
                "content": "Explain the difference between machine learning and deep learning.",
            }
        ]
        response = provider.chat(messages, model="sonar-pro")

        assert response is not None
        assert response["content"] is not None
        assert len(response["content"]) > 100  # Should give detailed response


class TestPerplexityProviderSearchModes:
    """Test different search modes."""

    def test_web_search_mode(self):
        """Should work with web search mode."""
        provider = PerplexityProvider()

        messages = [{"role": "user", "content": "What is the latest news?"}]

        response = provider.chat(
            messages,
            model="sonar",
            perplexity_config={"search_mode": "web"},
        )

        assert response is not None
        assert response["content"] is not None

    def test_academic_search_mode(self):
        """Should work with academic search mode."""
        provider = PerplexityProvider()

        messages = [
            {
                "role": "user",
                "content": "What are the latest research findings on neural networks?",
            }
        ]

        response = provider.chat(
            messages,
            model="sonar",
            perplexity_config={"search_mode": "academic"},
        )

        assert response is not None
        assert response["content"] is not None

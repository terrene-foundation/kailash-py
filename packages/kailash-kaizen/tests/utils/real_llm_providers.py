"""
Real LLM Provider Fixtures for Kaizen Tests.

Provides real OpenAI and Ollama providers for integration and E2E tests.
NO MOCKING - Uses actual API calls with proper error handling.

Note: gpt-5-nano uses 'max_completion_tokens' instead of 'max_tokens'
"""

import os
from typing import Any, Dict, Optional

import httpx
import pytest
from openai import OpenAI


class RealOpenAIProvider:
    """Real OpenAI provider for testing with gpt-5-nano."""

    def __init__(self, model: str = "gpt-5-nano", api_key: Optional[str] = None):
        """Initialize OpenAI provider."""
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        self.client = OpenAI(api_key=self.api_key)
        self.is_nano_model = "nano" in model.lower() or "gpt-5" in model.lower()

    def complete(
        self, messages: list, temperature: float = 0.7, max_tokens: int = 1000, **kwargs
    ) -> Dict[str, Any]:
        """
        Complete with real OpenAI API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens (converted to max_completion_tokens for gpt-5-nano)
            **kwargs: Additional parameters

        Returns:
            Dict with response and metadata
        """
        # gpt-5-nano uses max_completion_tokens instead of max_tokens
        if self.is_nano_model:
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
            }
        else:
            request_params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

        # Add any additional kwargs
        for key, value in kwargs.items():
            if key not in request_params and key not in [
                "max_tokens",
                "max_completion_tokens",
            ]:
                request_params[key] = value

        response = self.client.chat.completions.create(**request_params)

        return {
            "content": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "finish_reason": response.choices[0].finish_reason,
        }


class RealOllamaProvider:
    """Real Ollama provider for local testing."""

    def __init__(
        self, model: str = "llama3.2:latest", base_url: str = "http://localhost:11434"
    ):
        """Initialize Ollama provider."""
        self.model = model
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = self.client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def complete(
        self, messages: list, temperature: float = 0.7, max_tokens: int = 1000, **kwargs
    ) -> Dict[str, Any]:
        """
        Complete with real Ollama API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Returns:
            Dict with response and metadata
        """
        # Convert messages to Ollama format
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

        request_data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        response = self.client.post("/api/generate", json=request_data)
        response.raise_for_status()

        data = response.json()

        return {
            "content": data.get("response", ""),
            "model": self.model,
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0)
                + data.get("eval_count", 0),
            },
            "finish_reason": "stop" if data.get("done", False) else "length",
        }

    def __del__(self):
        """Cleanup client connection."""
        try:
            self.client.close()
        except Exception:
            pass


# =============================================================================
# PYTEST FIXTURES
# =============================================================================


@pytest.fixture(scope="session")
def openai_api_key():
    """Get OpenAI API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set in environment")
    return api_key


@pytest.fixture(scope="session")
def real_openai_provider(openai_api_key):
    """
    Real OpenAI provider for integration/E2E tests.
    Uses gpt-5-nano by default.
    """
    return RealOpenAIProvider(model="gpt-5-nano", api_key=openai_api_key)


@pytest.fixture(scope="session")
def real_openai_gpt4_provider(openai_api_key):
    """Real OpenAI GPT-4 provider for advanced tests."""
    return RealOpenAIProvider(model="gpt-4", api_key=openai_api_key)


@pytest.fixture(scope="session")
def real_ollama_provider():
    """
    Real Ollama provider for local tests.
    Skips if Ollama is not available.
    """
    provider = RealOllamaProvider()
    if not provider.is_available():
        pytest.skip("Ollama not available at http://localhost:11434")
    return provider


@pytest.fixture
def llm_provider_config():
    """LLM provider configuration for tests."""
    return {
        "openai": {
            "model": "gpt-5-nano",
            "temperature": 0.1,  # Low temperature for deterministic tests
            "max_tokens": 500,
            "api_key_env": "OPENAI_API_KEY",
        },
        "ollama": {
            "model": "llama3.2:latest",
            "base_url": "http://localhost:11434",
            "temperature": 0.1,
            "max_tokens": 500,
        },
    }


@pytest.fixture
def real_llm_test_helper(real_openai_provider):
    """Helper for LLM testing with retry logic and error handling."""

    class LLMTestHelper:
        def __init__(self, provider):
            self.provider = provider

        def ask(
            self, question: str, temperature: float = 0.1, max_tokens: int = 100
        ) -> Dict[str, Any]:
            """Ask a question with retry logic."""
            messages = [{"role": "user", "content": question}]

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    return self.provider.complete(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                except Exception:
                    if attempt == max_retries - 1:
                        raise
                    # Wait and retry
                    import time

                    time.sleep(1 * (attempt + 1))

        def verify_response(
            self, response: Dict[str, Any], min_length: int = 1
        ) -> bool:
            """Verify response is valid."""
            return (
                response is not None
                and "content" in response
                and isinstance(response["content"], str)
                and len(response["content"]) >= min_length
            )

    return LLMTestHelper(real_openai_provider)


__all__ = [
    "RealOpenAIProvider",
    "RealOllamaProvider",
    "real_openai_provider",
    "real_openai_gpt4_provider",
    "real_ollama_provider",
    "llm_provider_config",
    "real_llm_test_helper",
]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Provider registry — resolve a provider name to a concrete instance.

This is infrastructure configuration branching (permitted by agent-reasoning
rules), NOT agent decision-making.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import BaseAIProvider, EmbeddingProvider, LLMProvider
from kaizen.providers.embedding.cohere import CohereProvider
from kaizen.providers.embedding.huggingface import HuggingFaceProvider
from kaizen.providers.errors import UnknownProviderError
from kaizen.providers.llm.anthropic import AnthropicProvider
from kaizen.providers.llm.azure import AzureAIFoundryProvider
from kaizen.providers.llm.docker import DockerModelRunnerProvider
from kaizen.providers.llm.google import GoogleGeminiProvider
from kaizen.providers.llm.mock import MockProvider
from kaizen.providers.llm.ollama import OllamaProvider
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.llm.perplexity import PerplexityProvider

logger = logging.getLogger(__name__)


def _get_unified_azure_provider() -> type:
    """Lazy-import UnifiedAzureProvider to avoid circular dependency.

    The UnifiedAzureProvider lives in ``kaizen.nodes.ai.unified_azure_provider``
    and inherits from the *old* monolith's ``UnifiedAIProvider``. We import it
    lazily so that the new providers package can coexist during migration.
    """
    from kaizen.nodes.ai.unified_azure_provider import UnifiedAzureProvider

    return UnifiedAzureProvider


# Provider registry mapping names to classes.
# UnifiedAzureProvider is resolved lazily via a string sentinel.
PROVIDERS: dict[str, type | str] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "cohere": CohereProvider,
    "huggingface": HuggingFaceProvider,
    "mock": MockProvider,
    "azure": "_unified_azure",
    "azure_openai": "_unified_azure",
    "azure_ai_foundry": AzureAIFoundryProvider,
    "docker": DockerModelRunnerProvider,
    "google": GoogleGeminiProvider,
    "gemini": GoogleGeminiProvider,
    "perplexity": PerplexityProvider,
    "pplx": PerplexityProvider,
}


def _resolve_provider_class(name: str) -> type:
    """Resolve a provider name to its class, handling lazy imports."""
    entry = PROVIDERS.get(name.lower())
    if entry is None:
        raise UnknownProviderError(
            f"Unknown provider: {name}. Available: {list(PROVIDERS.keys())}",
            provider_name=name,
        )
    if isinstance(entry, str) and entry == "_unified_azure":
        return _get_unified_azure_provider()
    return entry


def get_provider(
    provider_name: str,
    provider_type: str | None = None,
) -> BaseAIProvider | LLMProvider | EmbeddingProvider:
    """Get an AI provider instance by name.

    Args:
        provider_name: Name of the provider (case-insensitive).
        provider_type: Required capability — ``"chat"``, ``"embeddings"``,
            or ``None`` for any.

    Returns:
        Provider instance with the requested capabilities.

    Raises:
        ValueError: If the provider name is not recognized or doesn't
            support the requested type.
    """
    try:
        provider_class = _resolve_provider_class(provider_name)
    except UnknownProviderError:
        raise ValueError(
            f"Unknown provider: {provider_name}. Available: {list(PROVIDERS.keys())}"
        )

    provider = provider_class()

    if provider_type:
        if provider_type == "chat" and not provider.supports_chat():
            raise ValueError(
                f"Provider {provider_name} does not support chat operations"
            )
        elif provider_type == "embeddings" and not provider.supports_embeddings():
            raise ValueError(
                f"Provider {provider_name} does not support embedding operations"
            )
        elif provider_type not in ["chat", "embeddings"]:
            raise ValueError(
                f"Invalid provider_type: {provider_type}. Must be 'chat', 'embeddings', or None"
            )

    return provider


def get_available_providers(
    provider_type: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Get information about all available providers.

    Args:
        provider_type: Filter by capability — ``"chat"``, ``"embeddings"``,
            or ``None`` for all.

    Returns:
        Dict mapping provider names to their availability and capabilities.
    """
    results: dict[str, dict[str, Any]] = {}

    for name in PROVIDERS:
        try:
            provider = get_provider(name)
            capabilities = provider.get_capabilities()

            if (
                provider_type == "chat"
                and not capabilities.get("chat")
                or provider_type == "embeddings"
                and not capabilities.get("embeddings")
            ):
                continue

            results[name] = {
                "available": provider.is_available(),
                "chat": capabilities.get("chat", False),
                "embeddings": capabilities.get("embeddings", False),
                "description": (
                    provider.__class__.__doc__.split("\n")[1].strip()
                    if provider.__class__.__doc__
                    else ""
                ),
            }
        except Exception as e:
            logger.error(
                "Provider %s availability check failed: %s", name, e, exc_info=True
            )
            results[name] = {
                "available": False,
                "error": sanitize_provider_error(e, name),
                "chat": False,
                "embeddings": False,
            }

    return results

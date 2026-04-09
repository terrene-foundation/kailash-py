# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Provider registry — resolve a provider name or model name to a concrete instance.

This is infrastructure configuration branching (permitted by agent-reasoning
rules), NOT agent decision-making. The model-prefix dispatch in
:func:`get_provider_for_model` is structural string-prefix matching over a
declared provider registry — not semantic classification of user intent.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.providers.base import (
    BaseAIProvider,
    BaseProvider,
    EmbeddingProvider,
    LLMProvider,
    StreamingProvider,
)
from kaizen.providers.embedding.cohere import CohereProvider
from kaizen.providers.embedding.huggingface import HuggingFaceProvider
from kaizen.providers.errors import CapabilityNotSupportedError, UnknownProviderError
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


# SPEC-02 §3.1 — model-name prefix dispatch.
#
# This is a declared structural mapping, NOT a classification of user intent.
# Every tuple on the left is a set of model-id prefixes owned by the provider
# on the right. New providers extend this table; the function below is a
# pure prefix scan with no keyword reasoning.
_MODEL_PREFIX_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("gpt-", "o1-", "o3-", "o4-", "o1", "o3", "o4-mini", "ft:gpt"), "openai"),
    (("claude-",), "anthropic"),
    (("gemini-",), "google"),
    (
        (
            "llama",
            "mistral",
            "mixtral",
            "qwen",
            "phi-",
            "phi3",
            "phi4",
            "codellama",
            "deepseek",
        ),
        "ollama",
    ),
    (("ai/",), "docker"),
    (
        (
            "sonar",
            "sonar-",
        ),
        "perplexity",
    ),
    (("mock-", "mock"), "mock"),
)


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


def get_provider_for_model(model: str) -> BaseProvider:
    """Resolve a model id to its owning provider via structural prefix match.

    SPEC-02 §3.1. This is NOT semantic classification — it is a pure string-
    prefix scan over a declared table. Adding a new provider means extending
    ``_MODEL_PREFIX_MAP``, not teaching an LLM to recognise new prefixes.

    Args:
        model: Model identifier (e.g. ``"gpt-4o"``, ``"claude-3-opus-20240229"``,
            ``"gemini-2.5-flash"``).

    Returns:
        A provider instance whose declared prefixes match *model*.

    Raises:
        UnknownProviderError: When no declared prefix matches *model*.
    """
    if not model or not isinstance(model, str):
        raise UnknownProviderError(
            f"Cannot detect provider for model: {model!r}", provider_name=str(model)
        )

    model_lower = model.lower()
    for prefixes, provider_name in _MODEL_PREFIX_MAP:
        for prefix in prefixes:
            if model_lower.startswith(prefix.lower()):
                logger.debug(
                    "provider.resolve model=%s prefix=%s provider=%s",
                    model,
                    prefix,
                    provider_name,
                )
                return get_provider(provider_name)

    raise UnknownProviderError(
        f"Cannot detect provider for model: {model}. "
        f"Add a prefix mapping to kaizen.providers.registry._MODEL_PREFIX_MAP.",
        provider_name=model,
    )


def get_streaming_provider(name_or_model: str) -> StreamingProvider:
    """Resolve a name or model id to a provider that implements StreamingProvider.

    Tries the provider registry first; falls back to model-prefix dispatch.
    Raises :class:`CapabilityNotSupportedError` if the resolved provider does
    not satisfy the :class:`StreamingProvider` protocol (i.e. has no real
    ``stream_chat`` method).
    """
    if name_or_model.lower() in PROVIDERS:
        provider = get_provider(name_or_model)
    else:
        provider = get_provider_for_model(name_or_model)

    if not isinstance(provider, StreamingProvider):
        raise CapabilityNotSupportedError(
            f"Provider '{provider.name}' does not support streaming. "
            f"Capabilities: {provider.capabilities}",
            provider_name=getattr(provider, "name", ""),
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

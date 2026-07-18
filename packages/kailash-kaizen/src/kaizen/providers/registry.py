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
from kaizen.providers.llm.azure import AzureAIFoundryProvider
from kaizen.providers.provider_names import PROVIDER_NAMES

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
    "cohere": CohereProvider,
    "huggingface": HuggingFaceProvider,
    "azure": "_unified_azure",
    "azure_openai": "_unified_azure",
    "azure_ai_foundry": AzureAIFoundryProvider,
}


# Drift tripwire: the pure-data name registry (kaizen.providers.provider_names)
# and this name -> class dict MUST enumerate the SAME provider names. A plain
# assert over declared config data (NOT agent reasoning) — if a provider is
# added to one and not the other, fail loudly at import instead of silently
# diverging the metrics label bound (which reuses PROVIDER_NAMES) from the
# resolver's actual class map.
assert set(PROVIDERS.keys()) <= PROVIDER_NAMES, (
    "provider name drift: kaizen.providers.registry.PROVIDERS has keys not in "
    "kaizen.providers.provider_names.PROVIDER_NAMES (the metrics classification "
    f"vocabulary): {sorted(set(PROVIDERS.keys()) - PROVIDER_NAMES)}. Every "
    "registry provider MUST be a known observability family; add it to "
    "PROVIDER_NAMES. Since #1720 Wave-2 PROVIDER_NAMES is a SUPERSET (it also "
    "carries the four-axis-served families openai/anthropic/google/etc. that "
    "are no longer registry providers), so the check is subset, not equality."
)


# SPEC-02 §3.1 model-name prefix dispatch (_MODEL_PREFIX_MAP / MODEL_PREFIX_MAP)
# is the single source in kaizen.providers.provider_names, imported above. It
# is a declared structural mapping, NOT a classification of user intent.


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
    """RETIRED (#1720 Wave-2): model-id -> provider dispatch always raises.

    Model-id -> transport dispatch now lives in
    ``kaizen.llm.deployment_resolver.resolve_deployment_for`` (four-axis
    ``LlmClient``). The legacy chat providers this function used to resolve
    (openai / anthropic / google / ollama / docker / perplexity / mock) were
    deleted, and no surviving registry provider is model-id-prefix addressable
    (they resolve by explicit NAME via :func:`get_provider`). So this function
    now raises :class:`UnknownProviderError` for every input — kept as a typed,
    named failure (not a silent ``None``) so any lingering caller fails loudly
    with a pointer to the four-axis path rather than mis-resolving.

    Args:
        model: Model identifier (unused beyond the message).

    Raises:
        UnknownProviderError: Always. Migrate to
            ``kaizen.llm.LlmClient`` / ``resolve_deployment_for``.
    """
    raise UnknownProviderError(
        f"Cannot detect provider for model {model!r}: registry model-id dispatch "
        "was retired in #1720 Wave-2. Use kaizen.llm.LlmClient (model-id -> wire "
        "dispatch lives in kaizen.llm.deployment_resolver.resolve_deployment_for).",
        provider_name=str(model),
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
            # A provider is_available() check can surface an auth/connection
            # exception embedding an api_key or user:pass@ URL — sanitize the log
            # to match the already-sanitized return (return/log parity; #1720).
            logger.error(
                "Provider %s availability check failed: %s",
                name,
                sanitize_provider_error(e, name),
            )
            results[name] = {
                "available": False,
                "error": sanitize_provider_error(e, name),
                "chat": False,
                "embeddings": False,
            }

    return results

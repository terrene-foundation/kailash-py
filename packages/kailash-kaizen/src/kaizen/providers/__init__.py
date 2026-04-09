# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kaizen Provider Integrations.

Public API for the per-provider module split (SPEC-02). Import provider
classes, base types, registry helpers, cost tracking, and error types
from this package.

Legacy Ollama-specific providers (OllamaProvider from the older
``kaizen.providers.ollama_provider`` module) remain available when the
``ollama`` package is installed.
"""

# ---------------------------------------------------------------------------
# Base classes and types
# ---------------------------------------------------------------------------

from kaizen.providers.base import (
    BaseAIProvider,
    EmbeddingProvider,
    LLMProvider,
    UnifiedAIProvider,
)
from kaizen.providers.cost import CostConfig, CostTracker, ModelPricing
from kaizen.providers.embedding.cohere import CohereProvider
from kaizen.providers.embedding.huggingface import HuggingFaceProvider
from kaizen.providers.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    ModelNotFoundError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    UnknownProviderError,
)
from kaizen.providers.llm.anthropic import AnthropicProvider
from kaizen.providers.llm.azure import AzureAIFoundryProvider
from kaizen.providers.llm.docker import DockerModelRunnerProvider
from kaizen.providers.llm.google import GoogleGeminiProvider
from kaizen.providers.llm.mock import MockProvider
from kaizen.providers.llm.ollama import OllamaProvider
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.llm.perplexity import PerplexityProvider
from kaizen.providers.registry import PROVIDERS, get_available_providers, get_provider
from kaizen.providers.types import (
    ChatResponse,
    Message,
    MessageContent,
    StreamEvent,
    TokenUsage,
    ToolCall,
)

# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unified types
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Legacy Ollama-specific providers (pre-SPEC-02, optional)
# ---------------------------------------------------------------------------

OLLAMA_AVAILABLE = False
try:
    import ollama as _ollama_pkg  # noqa: F401

    OLLAMA_AVAILABLE = True
except ImportError:
    pass

__all__ = [
    # Base
    "BaseAIProvider",
    "LLMProvider",
    "EmbeddingProvider",
    "UnifiedAIProvider",
    # Types
    "Message",
    "MessageContent",
    "ChatResponse",
    "TokenUsage",
    "ToolCall",
    "StreamEvent",
    # Errors
    "ProviderError",
    "UnknownProviderError",
    "ProviderUnavailableError",
    "CapabilityNotSupportedError",
    "AuthenticationError",
    "RateLimitError",
    "ModelNotFoundError",
    # Cost
    "CostTracker",
    "CostConfig",
    "ModelPricing",
    # Providers
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleGeminiProvider",
    "OllamaProvider",
    "DockerModelRunnerProvider",
    "AzureAIFoundryProvider",
    "PerplexityProvider",
    "CohereProvider",
    "HuggingFaceProvider",
    "MockProvider",
    # Registry
    "PROVIDERS",
    "get_provider",
    "get_available_providers",
    # Legacy flag
    "OLLAMA_AVAILABLE",
]

if OLLAMA_AVAILABLE:
    from kaizen.providers.ollama_model_manager import ModelInfo, OllamaModelManager
    from kaizen.providers.ollama_provider import OllamaConfig
    from kaizen.providers.ollama_provider import OllamaProvider as LegacyOllamaProvider
    from kaizen.providers.ollama_vision_provider import (
        OllamaVisionConfig,
        OllamaVisionProvider,
    )

    __all__.extend(
        [
            "LegacyOllamaProvider",
            "OllamaConfig",
            "OllamaModelManager",
            "ModelInfo",
            "OllamaVisionProvider",
            "OllamaVisionConfig",
        ]
    )

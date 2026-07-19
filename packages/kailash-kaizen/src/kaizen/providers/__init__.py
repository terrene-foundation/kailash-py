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

import importlib
import warnings
from typing import TYPE_CHECKING

from kaizen.providers.base import (
    BaseAIProvider,
    EmbeddingProvider,
    UnifiedAIProvider,
)
from kaizen.providers.cost import CostConfig, CostTracker, ModelPricing
from kaizen.providers.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    ModelNotFoundError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    UnknownProviderError,
)
from kaizen.providers.types import (
    ChatResponse,
    Message,
    MessageContent,
    StreamEvent,
    TokenUsage,
    ToolCall,
)

# ---------------------------------------------------------------------------
# Legacy provider re-exports — deprecated (#1720; removed in Wave-C).
#
# The provider classes and registry accessors below used to be eagerly
# re-exported here from their canonical ``kaizen.providers.*`` submodules
# (SPEC-02). They are now lazy DeprecationWarning shims (PEP 562
# ``__getattr__``): attribute ACCESS warns and resolves the real symbol, while
# a bare ``import kaizen.providers`` does NOT warn. Import providers from their
# canonical modules (``kaizen.providers.llm.<mod>``,
# ``kaizen.providers.embedding.<mod>``, ``kaizen.providers.base`` for the
# ``LLMProvider`` base, ``kaizen.providers.registry`` for the accessors)
# instead.
# ---------------------------------------------------------------------------
# #1720 Wave-2: the seven legacy chat providers (openai / anthropic / google /
# ollama / docker / perplexity / mock) were RETIRED onto the four-axis LlmClient
# and their canonical modules deleted. Their barrel re-exports are removed here;
# a ``from kaizen.providers import OpenAIProvider`` now raises AttributeError
# (end of the deprecation cycle that shipped the DeprecationWarning in 2.34.0).
#
# #1820: the embedding-legacy providers (``CohereProvider`` /
# ``HuggingFaceProvider``) and the unified-azure provider stack were RETIRED and
# their canonical modules DELETED (delete-now, no deprecation cycle — their
# transports are served end-to-end by the four-axis ``LlmClient`` path). Their
# barrel re-exports are removed here too; ``from kaizen.providers import
# CohereProvider`` now raises AttributeError. The remaining shims (base
# ``LLMProvider``, the kept ``AzureAIFoundryProvider``, the registry accessors)
# stay deprecated until Wave-C.
_LEGACY_PROVIDER_MODULES: dict[str, str] = {
    "LLMProvider": "kaizen.providers.base",
    "AzureAIFoundryProvider": "kaizen.providers.llm.azure",
    "PROVIDERS": "kaizen.providers.registry",
    "get_provider": "kaizen.providers.registry",
    "get_available_providers": "kaizen.providers.registry",
}

if TYPE_CHECKING:
    # Analyzer-only imports so pyright / CodeQL py/undefined-export / Sphinx
    # autodoc still resolve the legacy names kept in ``__all__`` below.
    from kaizen.providers.base import LLMProvider
    from kaizen.providers.llm.azure import AzureAIFoundryProvider
    from kaizen.providers.registry import (
        PROVIDERS,
        get_available_providers,
        get_provider,
    )


def __getattr__(name: str) -> object:
    """Lazily resolve deprecated legacy provider re-exports (PEP 562)."""
    module_path = _LEGACY_PROVIDER_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    warnings.warn(
        f"Importing {name} from {__name__} is deprecated and will be removed "
        f"in a future release (#1720); import from {module_path} instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    module = importlib.import_module(module_path)
    return getattr(module, name)


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
    # Providers (kept — legacy chat providers retired in #1720 Wave-2; the
    # embedding-legacy + unified-azure providers retired in #1820)
    "AzureAIFoundryProvider",
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

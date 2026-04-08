"""Backward-compatibility shim for ``kaizen.nodes.ai.ai_providers``.

.. deprecated::
    This module is deprecated since the SPEC-02 provider layer split.
    Import from ``kaizen.providers`` instead::

        # Before
        from kaizen.nodes.ai.ai_providers import OpenAIProvider, get_provider

        # After
        from kaizen.providers import OpenAIProvider, get_provider

All public names are re-exported from the new ``kaizen.providers`` package
so that existing code continues to work without modification.
"""

from typing import Any, Dict, List, Union

# Note: No module-level deprecation warning here because internal modules
# (kaizen.nodes.ai.__init__, unified_azure_provider, etc.) import from this
# shim. A module-level warning would fire on every ``import kaizen``.
# The deprecation is documented in the docstring above.

# ---------------------------------------------------------------------------
# Re-export base classes
# ---------------------------------------------------------------------------

from kaizen.providers.base import (  # noqa: E402, F401
    BaseAIProvider,
    EmbeddingProvider,
    LLMProvider,
    UnifiedAIProvider,
)

# ---------------------------------------------------------------------------
# Re-export type aliases (kept as module-level names for backward compat)
# ---------------------------------------------------------------------------

from kaizen.providers.types import Message, MessageContent  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Re-export all provider implementations
# ---------------------------------------------------------------------------

from kaizen.providers.llm.openai import OpenAIProvider  # noqa: E402, F401
from kaizen.providers.llm.anthropic import AnthropicProvider  # noqa: E402, F401
from kaizen.providers.llm.ollama import OllamaProvider  # noqa: E402, F401
from kaizen.providers.llm.google import GoogleGeminiProvider  # noqa: E402, F401
from kaizen.providers.llm.mock import MockProvider  # noqa: E402, F401
from kaizen.providers.llm.azure import AzureAIFoundryProvider  # noqa: E402, F401
from kaizen.providers.llm.docker import DockerModelRunnerProvider  # noqa: E402, F401
from kaizen.providers.llm.perplexity import PerplexityProvider  # noqa: E402, F401
from kaizen.providers.embedding.cohere import CohereProvider  # noqa: E402, F401
from kaizen.providers.embedding.huggingface import (
    HuggingFaceProvider,
)  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Re-export UnifiedAzureProvider (lives in its own module, imports from base)
# ---------------------------------------------------------------------------

from kaizen.nodes.ai.unified_azure_provider import (
    UnifiedAzureProvider,
)  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Re-export registry
# ---------------------------------------------------------------------------

from kaizen.providers.registry import (  # noqa: E402, F401
    PROVIDERS,
    get_available_providers,
    get_provider,
)

# ---------------------------------------------------------------------------
# Legacy module-level objects that consumers may reference
# ---------------------------------------------------------------------------

from kaizen.nodes.ai.client_cache import BYOKClientCache  # noqa: E402, F401

_byok_cache = BYOKClientCache(max_size=128, ttl_seconds=300)

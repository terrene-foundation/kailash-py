# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Base classes and capability protocols for AI providers.

These ABCs mirror the monolith's ``BaseAIProvider``, ``LLMProvider``,
``EmbeddingProvider``, and ``UnifiedAIProvider`` hierarchy.  Every
per-provider module inherits from the appropriate class here.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, List

from kaizen.providers.types import Message

logger = logging.getLogger(__name__)


class BaseAIProvider(ABC):
    """Base class for all AI provider implementations.

    Establishes lazy initialisation, cached availability checks, and a
    capability dictionary that consumers query at runtime.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._available: bool | None = None
        self._capabilities: dict[str, bool] = {"chat": False, "embeddings": False}

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider's prerequisites are satisfied."""

    def get_capabilities(self) -> dict[str, bool]:
        return self._capabilities.copy()

    def supports_chat(self) -> bool:
        return self._capabilities.get("chat", False)

    def supports_embeddings(self) -> bool:
        return self._capabilities.get("embeddings", False)


class LLMProvider(BaseAIProvider):
    """Abstract base for providers that support LLM chat operations."""

    def __init__(self) -> None:
        super().__init__()
        self._capabilities["chat"] = True

    @abstractmethod
    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        """Generate a chat completion.

        Args:
            messages: Conversation in OpenAI message format.
            **kwargs: Provider-specific parameters (model, generation_config, etc.).

        Returns:
            Standardised response dict.
        """


class EmbeddingProvider(BaseAIProvider):
    """Abstract base for providers that support embedding generation."""

    def __init__(self) -> None:
        super().__init__()
        self._capabilities["embeddings"] = True

    @abstractmethod
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        """Generate embeddings for *texts*."""

    @abstractmethod
    def get_model_info(self, model: str) -> dict[str, Any]:
        """Return metadata about an embedding *model*."""


class UnifiedAIProvider(LLMProvider, EmbeddingProvider):
    """Base for providers supporting both chat and embeddings."""

    def __init__(self) -> None:
        super().__init__()
        self._capabilities = {"chat": True, "embeddings": True}

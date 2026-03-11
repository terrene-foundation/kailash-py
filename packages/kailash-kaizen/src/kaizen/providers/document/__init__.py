"""
Document extraction providers for multi-modal document processing.

This module provides a provider abstraction layer for document extraction
with support for multiple backends (Landing AI, OpenAI Vision, Ollama Vision).

Key Components:
- BaseDocumentProvider: Abstract base class for all providers
- LandingAIProvider: Landing AI Document Parse API (98% accuracy, bounding boxes)
- OpenAIVisionProvider: OpenAI GPT-4o-mini vision (95% accuracy, fastest)
- OllamaVisionProvider: Local Ollama vision (85% accuracy, free)
- ProviderManager: Automatic provider selection and fallback

Example:
    >>> from kaizen.providers.document import ProviderManager
    >>>
    >>> manager = ProviderManager()
    >>> result = await manager.extract("report.pdf", prefer_free=False)
    >>> print(f"Provider used: {result['provider']}")
    >>> print(f"Cost: ${result['cost']:.3f}")
"""

from kaizen.providers.document.base_provider import (
    BaseDocumentProvider,
    ExtractionResult,
    ProviderCapability,
)
from kaizen.providers.document.landing_ai_provider import LandingAIProvider
from kaizen.providers.document.ollama_vision_provider import OllamaVisionProvider
from kaizen.providers.document.openai_vision_provider import OpenAIVisionProvider
from kaizen.providers.document.provider_manager import ProviderManager

__all__ = [
    "BaseDocumentProvider",
    "ExtractionResult",
    "ProviderCapability",
    "LandingAIProvider",
    "OpenAIVisionProvider",
    "OllamaVisionProvider",
    "ProviderManager",
]

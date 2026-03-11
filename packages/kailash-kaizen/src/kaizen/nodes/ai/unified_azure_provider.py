"""Unified Azure Provider for Kaizen Framework.

This module provides an intelligent unified Azure provider that automatically
selects between Azure OpenAI Service and Azure AI Foundry based on endpoint
detection and feature requirements.

The UnifiedAzureProvider is the recommended entry point for all Azure AI
operations in Kaizen, providing:
- Automatic backend detection from endpoint URL patterns
- Feature gap handling with clear error messages
- Seamless switching between Azure OpenAI and AI Foundry
- Support for reasoning models (o1, o3, GPT-5) with automatic parameter filtering
- Structured output (json_schema) support
"""

import logging
from typing import Any, Dict, List, Optional

# Import base class from ai_providers
from .ai_providers import UnifiedAIProvider
from .azure_backends import AzureAIFoundryBackend, AzureOpenAIBackend
from .azure_capabilities import AzureCapabilityRegistry, FeatureNotSupportedError
from .azure_detection import AzureBackendDetector

logger = logging.getLogger(__name__)


class UnifiedAzureProvider(UnifiedAIProvider):
    """
    Intelligent unified Azure provider with automatic backend detection.

    This provider seamlessly handles both Azure OpenAI Service and Azure AI Foundry,
    automatically detecting the appropriate backend based on endpoint URL patterns.

    Features:
    - Automatic backend detection from endpoint URL
    - Support for explicit backend override via AZURE_BACKEND env var
    - Feature gap detection with clear error messages
    - Automatic parameter filtering for reasoning models (o1, o3, GPT-5)
    - Structured output support with api_version handling
    - Error-based backend correction for custom endpoints

    Environment Variables:
        AZURE_ENDPOINT: Unified endpoint URL (recommended)
        AZURE_API_KEY: Unified API key (recommended)
        AZURE_BACKEND: Explicit backend override ('openai' or 'foundry')
        AZURE_API_VERSION: API version (default: 2024-10-21)
        AZURE_DEPLOYMENT: Default deployment name

        Legacy (backward compatible):
        AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY
        AZURE_AI_INFERENCE_ENDPOINT, AZURE_AI_INFERENCE_API_KEY

    Examples:
        >>> # Basic usage (auto-detection)
        >>> provider = UnifiedAzureProvider()
        >>> response = provider.chat([{"role": "user", "content": "Hello"}])

        >>> # Check capabilities
        >>> if provider.supports("audio_input"):
        ...     # Use audio features
        ...     pass

        >>> # Structured output
        >>> response = provider.chat(
        ...     messages=[{"role": "user", "content": "Extract info"}],
        ...     model="gpt-4o",
        ...     generation_config={
        ...         "response_format": {
        ...             "type": "json_schema",
        ...             "json_schema": {"name": "response", "schema": {...}}
        ...         }
        ...     }
        ... )
    """

    def __init__(self, use_async: bool = False):
        """
        Initialize the unified Azure provider.

        Args:
            use_async: If True, prefer async operations for non-blocking I/O.
        """
        super().__init__()
        self._use_async = use_async
        self._detector = AzureBackendDetector()
        self._registry: Optional[AzureCapabilityRegistry] = None
        self._openai_backend: Optional[AzureOpenAIBackend] = None
        self._foundry_backend: Optional[AzureAIFoundryBackend] = None
        self._active_backend: Optional[str] = None
        self._config: Dict[str, Any] = {}

        # Perform initial detection
        self._initialize()

    def _initialize(self) -> None:
        """Perform initial backend detection and configuration."""
        self._active_backend, self._config = self._detector.detect()

        if self._active_backend:
            self._registry = AzureCapabilityRegistry(self._active_backend)
            logger.info(
                f"UnifiedAzureProvider initialized with backend: {self._active_backend} "
                f"(source: {self._detector.detection_source})"
            )

    def is_available(self) -> bool:
        """
        Check if the provider is available and properly configured.

        Returns:
            True if Azure configuration is detected and valid, False otherwise.
        """
        if self._available is not None:
            return self._available

        self._available = self._active_backend is not None
        return self._available

    def _get_backend(self):
        """
        Get the appropriate backend instance for the detected backend type.

        Returns:
            AzureOpenAIBackend or AzureAIFoundryBackend instance

        Raises:
            RuntimeError: If no backend is configured
        """
        if not self._active_backend:
            raise RuntimeError(
                "No Azure backend configured. "
                "Set AZURE_ENDPOINT and AZURE_API_KEY environment variables."
            )

        if self._active_backend == "azure_openai":
            if self._openai_backend is None:
                self._openai_backend = AzureOpenAIBackend()
            return self._openai_backend
        else:
            if self._foundry_backend is None:
                self._foundry_backend = AzureAIFoundryBackend()
            return self._foundry_backend

    def get_detected_backend(self) -> Optional[str]:
        """
        Get the currently detected backend type.

        Returns:
            "azure_openai", "azure_ai_foundry", or None if not configured
        """
        return self._active_backend

    def get_detection_source(self) -> Optional[str]:
        """
        Get how the backend was detected.

        Returns:
            "explicit", "pattern", "default", "error_fallback", or None
        """
        return self._detector.detection_source

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Get all feature capabilities for the current backend.

        Returns:
            Dictionary mapping feature names to support status.
            Includes both standard capabilities (chat, embeddings) and
            Azure-specific capabilities (audio_input, reasoning_models, etc.)
        """
        caps = super().get_capabilities().copy()

        if self._registry:
            # Add Azure-specific capabilities
            azure_caps = self._registry.get_capabilities()
            caps.update(azure_caps)

        return caps

    def supports(self, feature: str) -> bool:
        """
        Check if a feature is supported on the current backend.

        Args:
            feature: Feature name to check (e.g., "audio_input", "reasoning_models")

        Returns:
            True if supported, False otherwise
        """
        if self._registry:
            return self._registry.supports(feature)
        return False

    def check_feature(self, feature: str) -> None:
        """
        Check feature availability and raise appropriate error/warning.

        Args:
            feature: Feature name to check

        Raises:
            FeatureNotSupportedError: If feature is not supported (hard gap)

        Warns:
            FeatureDegradationWarning: If feature has degraded support
        """
        if self._registry:
            self._registry.check_feature(feature)

    def check_model_requirements(self, model: Optional[str]) -> None:
        """
        Check if a model has backend requirements.

        Args:
            model: Model name/deployment to check

        Raises:
            FeatureNotSupportedError: If model requires a different backend
        """
        if self._registry:
            self._registry.check_model_requirements(model)

    def handle_error(self, error: Exception) -> Optional[str]:
        """
        Handle an error that may indicate wrong backend detection.

        This enables automatic backend correction when the initial detection
        was incorrect (e.g., for custom domains or proxies).

        Args:
            error: The exception from a failed API call

        Returns:
            New backend type if correction was made, None otherwise
        """
        new_backend = self._detector.handle_error(error)

        if new_backend and new_backend != self._active_backend:
            logger.info(
                f"Switching backend from {self._active_backend} to {new_backend} "
                f"based on error: {str(error)[:100]}"
            )
            self._active_backend = new_backend
            self._registry = AzureCapabilityRegistry(new_backend)
            return new_backend

        return None

    def chat(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """
        Generate a chat completion using the appropriate Azure backend.

        Args:
            messages: List of messages in OpenAI format
            **kwargs: Additional parameters including:
                - model: Model/deployment name
                - generation_config: Dict with temperature, max_tokens, etc.
                - tools: List of tool definitions
                - stream: Whether to stream the response

        Returns:
            Standardized response dictionary with:
                - id: Response ID
                - content: Generated text
                - role: "assistant"
                - model: Model used
                - usage: Token usage statistics
                - metadata: {"provider": "azure_openai" or "azure_ai_foundry"}

        Raises:
            RuntimeError: If no backend is configured or API call fails
            FeatureNotSupportedError: If using unsupported features
        """
        # Check model requirements if model is specified
        model = kwargs.get("model")
        if model:
            self.check_model_requirements(model)

        backend = self._get_backend()

        try:
            return backend.chat(messages, **kwargs)
        except Exception as e:
            # Try error-based backend correction
            new_backend = self.handle_error(e)
            if new_backend:
                # Retry with corrected backend
                backend = self._get_backend()
                return backend.chat(messages, **kwargs)
            raise

    async def chat_async(self, messages: List[Dict], **kwargs) -> Dict[str, Any]:
        """
        Generate a chat completion asynchronously.

        Args:
            messages: List of messages in OpenAI format
            **kwargs: Same as chat()

        Returns:
            Same as chat()
        """
        model = kwargs.get("model")
        if model:
            self.check_model_requirements(model)

        backend = self._get_backend()

        try:
            return await backend.chat_async(messages, **kwargs)
        except Exception as e:
            new_backend = self.handle_error(e)
            if new_backend:
                backend = self._get_backend()
                return await backend.chat_async(messages, **kwargs)
            raise

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings for texts.

        Args:
            texts: List of texts to embed
            **kwargs: Additional parameters including:
                - model: Embedding model name
                - dimensions: Output dimensions (if supported)

        Returns:
            List of embedding vectors

        Raises:
            RuntimeError: If embedding call fails
        """
        backend = self._get_backend()
        return backend.embed(texts, **kwargs)

    def get_model_info(self, model: str) -> Dict[str, Any]:
        """
        Get information about a model.

        Args:
            model: Model identifier

        Returns:
            Dictionary with model information including dimensions, max_tokens, etc.
        """
        # Known embedding model dimensions
        known_models = {
            "text-embedding-3-small": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Azure OpenAI small embedding model",
                "capabilities": {"variable_dimensions": True},
            },
            "text-embedding-3-large": {
                "dimensions": 3072,
                "max_tokens": 8191,
                "description": "Azure OpenAI large embedding model",
                "capabilities": {"variable_dimensions": True},
            },
            "text-embedding-ada-002": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Azure OpenAI ada embedding model",
                "capabilities": {"variable_dimensions": False},
            },
        }

        if model in known_models:
            return known_models[model]

        return {
            "dimensions": None,
            "max_tokens": None,
            "description": f"Model: {model}",
            "capabilities": {},
        }


# Factory function for provider registration
def get_unified_azure_provider(**kwargs) -> UnifiedAzureProvider:
    """
    Factory function to create a UnifiedAzureProvider instance.

    This function is used by the provider registry.

    Args:
        **kwargs: Arguments passed to UnifiedAzureProvider

    Returns:
        UnifiedAzureProvider instance
    """
    return UnifiedAzureProvider(**kwargs)

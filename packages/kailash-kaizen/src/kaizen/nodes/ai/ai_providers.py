"""Unified AI provider implementations for LLM and embedding operations.

This module provides a unified interface for AI providers that support both
language model chat operations and text embedding generation. It reduces
redundancy by consolidating common functionality while maintaining clean
separation between LLM and embedding capabilities.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

from kaizen.nodes.ai.client_cache import BYOKClientCache
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

logger = logging.getLogger(__name__)

# Module-level BYOK client cache (shared across all providers)
_byok_cache = BYOKClientCache(max_size=128, ttl_seconds=300)

# Type definitions for flexible message content
MessageContent = Union[str, List[Dict[str, Any]]]
Message = Dict[str, Union[str, MessageContent]]


class BaseAIProvider(ABC):
    """
    Base class for all AI provider implementations.

    This abstract class defines the common interface and shared functionality
    for providers that may support LLM operations, embedding operations, or both.
    It establishes a unified pattern for provider initialization, capability
    detection, and error handling across different AI services.

    Design Philosophy:
        The BaseAIProvider follows the principle of "capability-based architecture"
        where providers declare their capabilities explicitly. This allows for
        flexible provider implementations that may support chat, embeddings, or
        both, while maintaining a consistent interface. The design promotes:
        - Single source of truth for provider availability
        - Shared client management and initialization
        - Common error handling patterns
        - Flexible support for providers with different capabilities

    Upstream Dependencies:
        - Configuration systems providing API keys and credentials
        - Environment variable loaders for secure credential management
        - Package managers ensuring required dependencies
        - Network infrastructure for API access

    Downstream Consumers:
        - LLMAgentNode: Uses chat capabilities for conversational AI
        - EmbeddingGeneratorNode: Uses embedding capabilities for vector generation
        - Provider selection logic choosing appropriate implementations
        - Error handling systems catching provider-specific exceptions

    Configuration:
        Each provider implementation handles its own configuration needs,
        typically through environment variables or explicit parameters.
        Common patterns include API keys, endpoints, and model selections.

    Implementation Details:
        - Lazy initialization of clients to avoid unnecessary connections
        - Cached availability checks to reduce repeated validation
        - Capability dictionary for runtime feature detection
        - Abstract methods enforce implementation of core functionality
        - Thread-safe design for concurrent usage

    Error Handling:
        - Provider availability checked before operations
        - Graceful degradation when providers are unavailable
        - Standardized error responses across different providers
        - Detailed error messages for debugging

    Side Effects:
        - May establish network connections to AI services
        - May consume API quotas during availability checks
        - Caches client instances for performance

    Examples:
        >>> # Provider implementation
        >>> class MyProvider(BaseAIProvider):
        ...     def __init__(self):
        ...         super().__init__()
        ...         self._capabilities = {"chat": True, "embeddings": False}
        ...
        ...     def is_available(self) -> bool:
        ...         # Check API key, dependencies, etc.
        ...         return True
        >>>
        >>> provider = MyProvider()
        >>> assert provider.supports_chat() == True
        >>> assert provider.supports_embeddings() == False
        >>> assert provider.is_available() == True
    """

    def __init__(self):
        """Initialize base provider state."""
        self._client = None
        self._available = None
        self._capabilities = {"chat": False, "embeddings": False}

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the provider is available and properly configured.

        This method should verify:
        - Required dependencies are installed
        - API keys or credentials are configured
        - Services are accessible (for local services)

        Returns:
            bool: True if the provider can be used, False otherwise
        """

    def get_capabilities(self) -> dict[str, bool]:
        """
        Get the capabilities supported by this provider.

        Returns:
            Dict[str, bool]: Dictionary indicating support for:
                - chat: LLM chat operations
                - embeddings: Text embedding generation
        """
        return self._capabilities.copy()

    def supports_chat(self) -> bool:
        """Check if this provider supports LLM chat operations."""
        return self._capabilities.get("chat", False)

    def supports_embeddings(self) -> bool:
        """Check if this provider supports embedding generation."""
        return self._capabilities.get("embeddings", False)


class LLMProvider(BaseAIProvider):
    """
    Abstract base class for providers that support LLM chat operations.

    This class extends BaseAIProvider to define the interface for language model
    providers. It ensures consistent chat operation interfaces across different
    LLM services while allowing provider-specific optimizations and features.

    Design Philosophy:
        LLMProvider standardizes the chat interface while preserving flexibility
        for provider-specific features. It follows the OpenAI message format as
        the de facto standard, enabling easy switching between providers. The
        design supports both simple completions and advanced features like
        streaming, function calling, and custom parameters.

    Upstream Dependencies:
        - BaseAIProvider: Inherits core provider functionality
        - Message formatting systems preparing chat inputs
        - Token counting utilities for cost management
        - Rate limiting systems managing API quotas

    Downstream Consumers:
        - LLMAgentNode: Primary consumer for chat operations
        - ChatAgent: Uses for conversational interactions
        - A2AAgentNode: Leverages for agent communication
        - Response processing nodes handling outputs

    Configuration:
        Provider-specific parameters are passed through kwargs, allowing:
        - Model selection (model parameter)
        - Temperature and sampling parameters
        - Token limits and stop sequences
        - Provider-specific features (tools, functions, etc.)

    Implementation Details:
        - Standardized message format: List[Dict[str, str]]
        - Messages contain 'role' and 'content' fields minimum
        - Supports system, user, and assistant roles
        - Response format standardized across providers
        - Streaming support through callbacks (implementation-specific)

    Error Handling:
        - Invalid message format validation
        - API error standardization
        - Rate limit handling with retry guidance
        - Token limit exceeded handling
        - Network error recovery strategies

    Side Effects:
        - API calls consume tokens/credits
        - May log conversations for debugging
        - Updates internal usage metrics
        - May trigger rate limiting

    Examples:
        >>> class MyLLMProvider(LLMProvider):
        ...     def is_available(self) -> bool:
        ...         return True  # Check actual availability
        ...
        ...     def chat(self, messages, **kwargs):
        ...         # Simulate LLM response
        ...         return {
        ...             "success": True,
        ...             "content": "Response to: " + messages[-1]["content"],
        ...             "model": kwargs.get("model", "default"),
        ...             "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        ...         }
        >>>
        >>> provider = MyLLMProvider()
        >>> messages = [
        ...     {"role": "system", "content": "You are helpful."},
        ...     {"role": "user", "content": "Hello!"}
        ... ]
        >>> response = provider.chat(messages, model="gpt-4")
        >>> assert response["success"] == True
        >>> assert "content" in response
    """

    def __init__(self):
        super().__init__()
        self._capabilities["chat"] = True

    @abstractmethod
    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate a chat completion using the provider's LLM.

        Args:
            messages: Conversation messages in OpenAI format
                     Can be simple: [{"role": "user", "content": "text"}]
                     Or complex: [{"role": "user", "content": [{"type": "text", "text": "..."}, {"type": "image", "path": "..."}]}]
            **kwargs: Provider-specific parameters

        Returns:
            Dict containing the standardized response
        """


class EmbeddingProvider(BaseAIProvider):
    """
    Abstract base class for providers that support embedding generation.

    This class extends BaseAIProvider to define the interface for embedding
    providers. It standardizes how text is converted to vector representations
    across different embedding services while supporting provider-specific
    optimizations and model configurations.

    Design Philosophy:
        EmbeddingProvider abstracts the complexity of different embedding models
        and services behind a simple, consistent interface. It handles batching,
        dimension management, and normalization while allowing providers to
        optimize for their specific architectures. The design supports both
        sentence and document embeddings with appropriate chunking strategies.

    Upstream Dependencies:
        - BaseAIProvider: Inherits core provider functionality
        - Text preprocessing nodes preparing embedding inputs
        - Chunking strategies for long documents
        - Tokenization utilities for size management

    Downstream Consumers:
        - EmbeddingGeneratorNode: Primary consumer for vector generation
        - Vector databases storing embeddings
        - Similarity search implementations
        - Clustering and classification systems

    Configuration:
        Provider-specific parameters include:
        - Model selection for different embedding sizes/qualities
        - Batch size limits for efficiency
        - Normalization preferences
        - Dimension specifications

    Implementation Details:
        - Batch processing for efficiency
        - Automatic text truncation/chunking for model limits
        - Vector normalization options
        - Dimension validation and consistency
        - Cache-friendly operations for repeated texts

    Error Handling:
        - Empty text handling
        - Text length validation
        - Batch size limit enforcement
        - Model availability checking
        - Dimension mismatch detection

    Side Effects:
        - API calls consume embedding quotas
        - May cache embeddings for efficiency
        - Updates usage metrics
        - May trigger rate limiting

    Examples:
        >>> class MyEmbeddingProvider(EmbeddingProvider):
        ...     def is_available(self) -> bool:
        ...         return True
        ...
        ...     def embed(self, texts, **kwargs):
        ...         # Simulate embedding generation
        ...         return [[0.1, 0.2, 0.3] for _ in texts]
        ...
        ...     def get_model_info(self):
        ...         return {
        ...             "name": "my-embedding-model",
        ...             "dimensions": 3,
        ...             "max_tokens": 512
        ...         }
        >>>
        >>> provider = MyEmbeddingProvider()
        >>> embeddings = provider.embed(["Hello", "World"])
        >>> assert len(embeddings) == 2
        >>> assert len(embeddings[0]) == 3
        >>> info = provider.get_model_info()
        >>> assert info["dimensions"] == 3
    """

    def __init__(self):
        super().__init__()
        self._capabilities["embeddings"] = True

    @abstractmethod
    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            **kwargs: Provider-specific parameters

        Returns:
            List of embedding vectors
        """

    @abstractmethod
    def get_model_info(self, model: str) -> dict[str, Any]:
        """
        Get information about a specific embedding model.

        Args:
            model: Model identifier

        Returns:
            Dict containing model information
        """


class UnifiedAIProvider(LLMProvider, EmbeddingProvider):
    """
    Abstract base class for providers that support both LLM and embedding operations.

    Providers like OpenAI and Ollama that support both capabilities should
    inherit from this class.
    """

    def __init__(self):
        super().__init__()
        self._capabilities = {"chat": True, "embeddings": True}


# ============================================================================
# Unified Provider Implementations
# ============================================================================


class OllamaProvider(UnifiedAIProvider):
    """Ollama provider for both LLM and embedding operations.

    Ollama runs models locally on your machine, supporting both chat and
    embedding operations with various open-source models.

    Prerequisites:
        * Install Ollama: https://ollama.ai
        * Pull models:
            * LLM: ``ollama pull llama3.1:8b-instruct-q8_0``
            * Embeddings: ``ollama pull snowflake-arctic-embed2``
        * Ensure Ollama service is running

    Supported LLM models:
        * llama3.1:* (various quantizations)
        * mixtral:* (various quantizations)
        * mistral:* (various quantizations)
        * qwen2.5:* (various sizes and quantizations)

    Supported embedding models:
        * snowflake-arctic-embed2 (1024 dimensions)
        * avr/sfr-embedding-mistral (4096 dimensions)
        * nomic-embed-text (768 dimensions)
        * mxbai-embed-large (1024 dimensions)
    """

    def __init__(self):
        super().__init__()
        self._model_cache = {}

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        if self._available is not None:
            return self._available

        try:
            import os

            import ollama

            # Check with environment-configured host if available
            host = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST")
            client = ollama.Client(host=host) if host else ollama.Client()

            # Check if Ollama is running
            client.list()
            self._available = True
        except Exception:
            self._available = False

        return self._available

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate a chat completion using Ollama.

        Args:
            messages: Conversation messages in OpenAI format.
            **kwargs: Additional arguments including:
                model (str): Ollama model name (default: "llama3.1:8b-instruct-q8_0")
                generation_config (dict): Generation parameters including:

                    * temperature, max_tokens, top_p, top_k, repeat_penalty
                    * seed, stop, num_ctx, num_batch, num_thread
                    * tfs_z, typical_p, mirostat, mirostat_tau, mirostat_eta
                backend_config (dict): Backend configuration including:
                    * host (str): Ollama host URL (default: from env or http://localhost:11434)
                    * port (int): Ollama port (if provided, will be appended to host)

        Returns:
            Dict containing the standardized response.
        """
        try:
            import ollama

            model = kwargs.get("model", "llama3.1:8b-instruct-q8_0")
            generation_config = kwargs.get("generation_config", {})
            backend_config = kwargs.get("backend_config", {})

            # Normalize top-level base_url kwarg into backend_config
            per_request_base_url = kwargs.get("base_url")
            if per_request_base_url and not backend_config:
                backend_config = {"base_url": per_request_base_url}

            # Configure Ollama client with custom host if provided
            if backend_config:
                host = backend_config.get("host", "localhost")
                port = backend_config.get("port")
                if port:
                    # Construct full URL if port is provided
                    host = (
                        f"http://{host}:{port}"
                        if not host.startswith("http")
                        else f"{host}:{port}"
                    )
                elif backend_config.get("base_url"):
                    host = backend_config["base_url"]
                self._client = ollama.Client(host=host)
            elif self._client is None:
                # Use default client
                import os

                host = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST")
                self._client = ollama.Client(host=host) if host else ollama.Client()

            # Map generation_config to Ollama options
            options = {
                "temperature": generation_config.get("temperature", 0.7),
                "top_p": generation_config.get("top_p", 0.9),
                "top_k": generation_config.get("top_k"),
                "repeat_penalty": generation_config.get("repeat_penalty"),
                "seed": generation_config.get("seed"),
                "stop": generation_config.get("stop"),
                "tfs_z": generation_config.get("tfs_z", 1.0),
                "num_predict": generation_config.get("max_tokens", 500),
                "num_ctx": generation_config.get("num_ctx"),
                "num_batch": generation_config.get("num_batch"),
                "num_thread": generation_config.get("num_thread"),
                "typical_p": generation_config.get("typical_p"),
                "mirostat": generation_config.get("mirostat"),
                "mirostat_tau": generation_config.get("mirostat_tau"),
                "mirostat_eta": generation_config.get("mirostat_eta"),
            }

            # Remove None values
            options = {k: v for k, v in options.items() if v is not None}

            # Process messages for vision content
            processed_messages = []

            for msg in messages:
                if isinstance(msg.get("content"), list):
                    # Complex content with potential images
                    text_parts = []
                    images = []

                    for item in msg["content"]:
                        if item["type"] == "text":
                            text_parts.append(item["text"])
                        elif item["type"] == "image":
                            # Lazy load vision utilities
                            from .vision_utils import encode_image

                            if "path" in item:
                                # For file paths, read the file directly
                                with open(item["path"], "rb") as f:
                                    images.append(f.read())
                            else:
                                # For base64, decode it to bytes
                                import base64

                                base64_data = item.get("base64", "")
                                images.append(base64.b64decode(base64_data))
                        else:
                            # Warn about unhandled content types to prevent silent failures
                            content_type = item.get("type", "unknown")
                            if content_type not in ("text", "image"):
                                import warnings

                                warnings.warn(
                                    f"Unhandled content type '{content_type}' in OllamaProvider. "
                                    f"Only 'text' and 'image' are supported. This content will be skipped.",
                                    UserWarning,
                                    stacklevel=2,
                                )

                    # Ollama expects images as part of the message
                    message_dict = {
                        "role": msg["role"],
                        "content": " ".join(text_parts),
                    }
                    if images:
                        message_dict["images"] = images

                    processed_messages.append(message_dict)
                else:
                    # Simple string content (backward compatible)
                    processed_messages.append(msg)

            # Call Ollama
            response = self._client.chat(
                model=model, messages=processed_messages, options=options
            )

            # Format response to match standard structure
            # Handle None values from Ollama response
            prompt_tokens = response.get("prompt_eval_count") or 0
            completion_tokens = response.get("eval_count") or 0

            return {
                "id": f"ollama_{hash(str(messages))}",
                "content": response["message"]["content"],
                "role": "assistant",
                "model": model,
                "created": response.get("created_at"),
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "metadata": {
                    "duration_ms": (response.get("total_duration") or 0) / 1e6,
                    "load_duration_ms": (response.get("load_duration") or 0) / 1e6,
                    "eval_duration_ms": (response.get("eval_duration") or 0) / 1e6,
                },
            }

        except ImportError:
            raise RuntimeError(
                "Ollama library not installed. Install with: pip install ollama"
            )
        except Exception as e:
            logger.error("Ollama error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Ollama"))

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings using Ollama.

        Supported kwargs:
        - model (str): Ollama model name (default: "snowflake-arctic-embed2")
        - normalize (bool): Normalize embeddings to unit length
        - backend_config (dict): Backend configuration (host, port, base_url)
        """
        try:
            import ollama

            model = kwargs.get("model", "snowflake-arctic-embed2")
            normalize = kwargs.get("normalize", False)
            backend_config = kwargs.get("backend_config", {})

            # Configure Ollama client if not already configured
            if backend_config and not hasattr(self, "_client"):
                host = backend_config.get("host", "localhost")
                port = backend_config.get("port")
                if port:
                    host = (
                        f"http://{host}:{port}"
                        if not host.startswith("http")
                        else f"{host}:{port}"
                    )
                elif backend_config.get("base_url"):
                    host = backend_config["base_url"]
                self._client = ollama.Client(host=host)
            elif not hasattr(self, "_client") or self._client is None:
                import os

                host = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST")
                self._client = ollama.Client(host=host) if host else ollama.Client()

            embeddings = []
            for text in texts:
                response = self._client.embeddings(model=model, prompt=text)
                embedding = response.get("embedding", [])

                if normalize and embedding:
                    # Normalize to unit length
                    magnitude = sum(x * x for x in embedding) ** 0.5
                    if magnitude > 0:
                        embedding = [x / magnitude for x in embedding]

                embeddings.append(embedding)

            return embeddings

        except ImportError:
            raise RuntimeError(
                "Ollama library not installed. Install with: pip install ollama"
            )
        except Exception as e:
            logger.error("Ollama embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Ollama"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about an Ollama embedding model."""
        if model in self._model_cache:
            return self._model_cache[model]

        # Known embedding model dimensions
        known_models = {
            "snowflake-arctic-embed2": {"dimensions": 1024, "max_tokens": 512},
            "avr/sfr-embedding-mistral": {"dimensions": 4096, "max_tokens": 512},
            "nomic-embed-text": {"dimensions": 768, "max_tokens": 8192},
            "mxbai-embed-large": {"dimensions": 1024, "max_tokens": 512},
        }

        if model in known_models:
            info = known_models[model].copy()
            info["description"] = f"Ollama embedding model: {model}"
            info["capabilities"] = {
                "batch_processing": True,
                "gpu_acceleration": True,
                "normalize": True,
            }
            self._model_cache[model] = info
            return info

        # Default for unknown models
        return {
            "dimensions": 1536,
            "max_tokens": 512,
            "description": f"Ollama model: {model}",
            "capabilities": {"batch_processing": True},
        }


class OpenAIProvider(UnifiedAIProvider):
    """
    OpenAI provider for both LLM and embedding operations.

    Prerequisites:
    - Set OPENAI_API_KEY environment variable
    - Install openai package: `pip install openai`

    Supported LLM models:
    - o4-mini (latest, vision support, recommended)
    - o3 (reasoning model)

    Note: This provider uses max_completion_tokens parameter compatible with
    latest OpenAI models. Older models (gpt-4, gpt-3.5-turbo) are not supported.

    Generation Config Parameters:
    - max_completion_tokens (int): Maximum tokens to generate (recommended)
    - max_tokens (int): Deprecated, use max_completion_tokens instead
    - temperature (float): Sampling temperature (0-2)
    - top_p (float): Nucleus sampling probability
    - Other standard OpenAI parameters

    Supported embedding models:
    - text-embedding-3-large (3072 dimensions, configurable)
    - text-embedding-3-small (1536 dimensions, configurable)
    - text-embedding-ada-002 (1536 dimensions, legacy)
    """

    def __init__(self, use_async: bool = False):
        """
        Initialize OpenAI provider with async support.

        Args:
            use_async: If True, uses AsyncOpenAI client for non-blocking operations.
                      If False (default), uses synchronous OpenAI client for backwards compatibility.
        """
        # Call parent __init__ which sets self._client = None
        super().__init__()
        self._use_async = use_async
        # Separate clients for sync and async to avoid conflicts
        self._sync_client = None
        self._async_client = None

    def is_available(self) -> bool:
        """Check if OpenAI is available."""
        if self._available is not None:
            return self._available

        try:
            import os

            # Check for API key
            self._available = bool(os.getenv("OPENAI_API_KEY"))
        except ImportError:
            self._available = False

        return self._available

    # Reasoning model patterns (o1, o3, GPT-5 require temperature=1.0)
    # Reasoning models that DON'T support temperature parameter at all (o1, o3)
    _REASONING_MODEL_PATTERNS = [
        r"^o1",  # o1, o1-preview, o1-mini
        r"^o3",  # o3, o3-mini
    ]

    # Models that REQUIRE temperature=1.0 (GPT-5)
    _TEMPERATURE_1_ONLY_PATTERNS = [
        r"^gpt-?5",  # gpt-5, GPT-5, gpt5
    ]

    def _is_reasoning_model(self, model: str) -> bool:
        """
        Check if model is a reasoning model (o1, o3) that doesn't support temperature.

        These models don't support temperature parameter at all.

        Args:
            model: Model name to check

        Returns:
            True if model is a reasoning model
        """
        import re

        if not model:
            return False
        model_lower = model.lower()
        for pattern in self._REASONING_MODEL_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                return True
        return False

    def _requires_temperature_1(self, model: str) -> bool:
        """
        Check if model requires temperature=1.0 (GPT-5 models).

        GPT-5 models support temperature but ONLY at 1.0.

        Args:
            model: Model name to check

        Returns:
            True if model requires temperature=1.0
        """
        import re

        if not model:
            return False
        model_lower = model.lower()
        for pattern in self._TEMPERATURE_1_ONLY_PATTERNS:
            if re.search(pattern, model_lower, re.IGNORECASE):
                return True
        return False

    def _filter_reasoning_model_params(
        self, model: str, generation_config: dict
    ) -> dict:
        """
        Filter generation parameters for reasoning models.

        Reasoning models (o1, o3, GPT-5) only support temperature=1.0
        and don't support top_p, frequency_penalty, presence_penalty.

        Args:
            model: Model name
            generation_config: Original generation config

        Returns:
            Filtered generation config
        """
        import logging

        logger = logging.getLogger(__name__)

        # Handle GPT-5 models that require temperature=1.0
        if self._requires_temperature_1(model):
            filtered = generation_config.copy()
            unsupported = {"top_p", "frequency_penalty", "presence_penalty"}

            removed = []
            for key in unsupported:
                if key in filtered:
                    removed.append(f"{key}={filtered[key]}")
                    del filtered[key]

            # Force temperature to 1.0 for GPT-5 models
            if filtered.get("temperature") != 1.0:
                if "temperature" in filtered:
                    removed.append(
                        f"temperature={filtered['temperature']} (forced to 1.0)"
                    )
                filtered["temperature"] = 1.0

            if removed:
                logger.warning(
                    f"Model {model} requires temperature=1.0. "
                    f"Adjusted parameters: {', '.join(removed)}"
                )

            return filtered

        # Handle o1/o3 reasoning models that don't support temperature at all
        if not self._is_reasoning_model(model):
            return generation_config

        filtered = generation_config.copy()
        unsupported = {"temperature", "top_p", "frequency_penalty", "presence_penalty"}

        removed = []
        for key in unsupported:
            if key in filtered:
                removed.append(f"{key}={filtered[key]}")
                del filtered[key]

        if removed:
            logger.warning(
                f"Model {model} is a reasoning model that doesn't support temperature. "
                f"Removed unsupported parameters: {', '.join(removed)}"
            )

        return filtered

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate a chat completion using OpenAI.

        Supported kwargs:
        - model (str): OpenAI model name (default: "o4-mini")
        - generation_config (dict): Generation parameters including:
            - max_completion_tokens (int): Max tokens to generate (recommended)
            - max_tokens (int): Deprecated, use max_completion_tokens
            - temperature, top_p, frequency_penalty, presence_penalty, etc.
        - tools (List[Dict]): Function/tool definitions for function calling
        """
        try:
            import openai

            model = kwargs.get("model", "o4-mini")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            # Use per-request client if overrides provided, else shared client
            if per_request_api_key or per_request_base_url:
                client_kwargs = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                client = _byok_cache.get_or_create(
                    per_request_api_key,
                    per_request_base_url,
                    factory=lambda: openai.OpenAI(**client_kwargs),
                )
            else:
                # Initialize shared sync client if needed
                if self._sync_client is None:
                    self._sync_client = openai.OpenAI()
                client = self._sync_client

            # Process messages for vision/audio content
            processed_messages = []
            for msg in messages:
                if isinstance(msg.get("content"), list):
                    # Complex content with potential images/audio
                    processed_content = []
                    for item in msg["content"]:
                        if item.get("type") == "text":
                            processed_content.append(
                                {"type": "text", "text": item.get("text", "")}
                            )
                        elif item.get("type") == "image":
                            # Lazy load vision utilities
                            from .vision_utils import (
                                encode_image,
                                get_media_type,
                                validate_image_size,
                            )

                            if "path" in item:
                                # Validate image size
                                is_valid, error_msg = validate_image_size(item["path"])
                                if not is_valid:
                                    raise ValueError(
                                        f"Image validation failed: {error_msg}"
                                    )

                                base64_image = encode_image(item["path"])
                                media_type = get_media_type(item["path"])
                            elif "base64" in item:
                                base64_image = item["base64"]
                                media_type = item.get("media_type", "image/jpeg")
                            else:
                                raise ValueError(
                                    "Image item must have either 'path' or 'base64' field"
                                )

                            processed_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{base64_image}"
                                    },
                                }
                            )
                        elif item.get("type") == "audio":
                            # Handle audio content for GPT-4o models
                            from .audio_utils import (
                                encode_audio,
                                get_audio_media_type,
                                validate_audio_size,
                            )

                            if "path" in item:
                                is_valid, error_msg = validate_audio_size(item["path"])
                                if not is_valid:
                                    raise ValueError(
                                        f"Audio validation failed: {error_msg}"
                                    )
                                base64_audio = encode_audio(item["path"])
                                media_type = get_audio_media_type(item["path"])
                            elif "base64" in item:
                                base64_audio = item["base64"]
                                media_type = item.get("media_type", "audio/mpeg")
                            elif "bytes" in item:
                                import base64

                                base64_audio = base64.b64encode(item["bytes"]).decode(
                                    "utf-8"
                                )
                                media_type = item.get("media_type", "audio/mpeg")
                            else:
                                raise ValueError(
                                    "Audio item must have 'path', 'base64', or 'bytes' field"
                                )

                            # Extract format from media type (e.g., "audio/mpeg" -> "mp3")
                            audio_format = media_type.split("/")[-1]
                            if audio_format == "mpeg":
                                audio_format = "mp3"
                            elif audio_format == "mp4":
                                audio_format = "m4a"

                            processed_content.append(
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": base64_audio,
                                        "format": audio_format,
                                    },
                                }
                            )
                        elif item.get("type") == "audio_url":
                            # Handle audio data URLs (e.g., "data:audio/mpeg;base64,...")
                            import base64

                            url = item.get("url", "")
                            if url.startswith("data:audio"):
                                # Parse data URL: "data:audio/mpeg;base64,..."
                                header, b64_data = url.split(",", 1)
                                media_type = header.replace("data:", "").split(";")[0]
                                base64_audio = b64_data

                                # Extract format from media type
                                audio_format = media_type.split("/")[-1]
                                if audio_format == "mpeg":
                                    audio_format = "mp3"
                                elif audio_format == "mp4":
                                    audio_format = "m4a"

                                processed_content.append(
                                    {
                                        "type": "input_audio",
                                        "input_audio": {
                                            "data": base64_audio,
                                            "format": audio_format,
                                        },
                                    }
                                )
                        else:
                            # Warn about unhandled content types
                            content_type = item.get("type", "unknown")
                            if content_type not in (
                                "text",
                                "image",
                                "audio",
                                "audio_url",
                            ):
                                import warnings

                                warnings.warn(
                                    f"Unhandled content type '{content_type}' in message. "
                                    "This content will be skipped. Supported types: "
                                    "text, image, audio, audio_url.",
                                    UserWarning,
                                    stacklevel=2,
                                )

                    processed_messages.append(
                        {"role": msg.get("role", "user"), "content": processed_content}
                    )
                else:
                    # Simple string content (backward compatible)
                    processed_messages.append(msg)

            # Handle max tokens parameter - support both old and new names
            # No default limit - let the model generate as many tokens as needed
            max_completion = generation_config.get(
                "max_completion_tokens"
            ) or generation_config.get("max_tokens")

            # Show deprecation warning if using old parameter
            # TODO: remove the max_tokens in the future.
            if (
                "max_tokens" in generation_config
                and "max_completion_tokens" not in generation_config
            ):
                import warnings

                warnings.warn(
                    "'max_tokens' is deprecated and will be removed in v0.5.0. "
                    "Please use 'max_completion_tokens' instead.",
                    DeprecationWarning,
                    stacklevel=3,
                )

            # FIX v0.9.6: Filter params for reasoning models (o1, o3, GPT-5)
            # These models only support temperature=1.0 and don't support top_p, etc.
            filtered_config = self._filter_reasoning_model_params(
                model, generation_config
            )

            # Prepare request
            request_params = {
                "model": model,
                "messages": processed_messages,
                "max_completion_tokens": max_completion,  # Always use new parameter
                "stop": filtered_config.get("stop"),
                "n": filtered_config.get("n", 1),
                "stream": kwargs.get("stream", False),
                "logit_bias": filtered_config.get("logit_bias"),
                "user": filtered_config.get("user"),
                "seed": filtered_config.get("seed"),
            }

            # Only add temperature/top_p params if not a reasoning model
            if not self._is_reasoning_model(model):
                request_params["temperature"] = filtered_config.get("temperature", 1.0)
                request_params["top_p"] = filtered_config.get("top_p", 1.0)
                request_params["frequency_penalty"] = filtered_config.get(
                    "frequency_penalty"
                )
                request_params["presence_penalty"] = filtered_config.get(
                    "presence_penalty"
                )

            # Handle response_format - must have valid 'type' field if provided
            response_format = filtered_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                # OpenAI requires response_format to have 'type' field
                if "type" in response_format:
                    request_params["response_format"] = response_format
                # Skip invalid/empty response_format to avoid API errors

            # Remove None values
            request_params = {k: v for k, v in request_params.items() if v is not None}

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                # Force tool usage for OpenAI when tools are provided (defaults to "required")
                # This ensures consistent tool calling behavior matching Claude Desktop's approach
                default_choice = "required" if tools and len(tools) > 0 else "auto"
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", default_choice
                )
                logger.debug(
                    "OpenAI tools: %d tools, tool_choice=%s",
                    len(tools),
                    request_params.get("tool_choice"),
                )

            # Call OpenAI (sync) — uses per-request client if overrides provided
            response = client.chat.completions.create(**request_params)

            # Format response
            choice = response.choices[0]
            return {
                "id": response.id,
                "content": choice.message.content,
                "role": choice.message.role,
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    else []
                ),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except openai.BadRequestError as e:
            # Provide helpful error message for unsupported models or parameters
            logger.error("OpenAI BadRequestError: %s", e, exc_info=True)
            if "max_tokens" in str(e):
                raise RuntimeError(
                    "This OpenAI provider requires models that support max_completion_tokens. "
                    "Please use o4-mini, o3 "
                    "Older models like gpt-4o or gpt-3.5-turbo are not supported."
                )
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))
        except Exception as e:
            logger.error("OpenAI error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    async def chat_async(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate a chat completion using OpenAI (async version).

        This async method provides non-blocking I/O for production FastAPI deployments
        and concurrent agent execution. It uses AsyncOpenAI client for true async operations.

        Supported kwargs:
        - model (str): OpenAI model name (default: "o4-mini")
        - generation_config (dict): Generation parameters including:
            - max_completion_tokens (int): Max tokens to generate (recommended)
            - max_tokens (int): Deprecated, use max_completion_tokens
            - temperature, top_p, frequency_penalty, presence_penalty, etc.
        - tools (List[Dict]): Function/tool definitions for function calling

        Returns:
            Dict containing the standardized response (same format as sync chat())

        Raises:
            RuntimeError: If AsyncOpenAI not configured or OpenAI library not installed
        """
        try:
            import openai

            model = kwargs.get("model", "o4-mini")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                from openai import AsyncOpenAI

                client_kwargs = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                async_client = AsyncOpenAI(**client_kwargs)
            else:
                # Initialize shared async client if needed
                if self._async_client is None:
                    from openai import AsyncOpenAI

                    self._async_client = AsyncOpenAI()
                async_client = self._async_client

            # Process messages for vision content (same logic as sync)
            processed_messages = []
            for msg in messages:
                if isinstance(msg.get("content"), list):
                    # Complex content with potential images
                    processed_content = []
                    for item in msg["content"]:
                        if item.get("type") == "text":
                            processed_content.append(
                                {"type": "text", "text": item.get("text", "")}
                            )
                        elif item.get("type") == "image":
                            # Lazy load vision utilities
                            from .vision_utils import (
                                encode_image,
                                get_media_type,
                                validate_image_size,
                            )

                            if "path" in item:
                                # Validate image size
                                is_valid, error_msg = validate_image_size(item["path"])
                                if not is_valid:
                                    raise ValueError(
                                        f"Image validation failed: {error_msg}"
                                    )

                                base64_image = encode_image(item["path"])
                                media_type = get_media_type(item["path"])
                            elif "base64" in item:
                                base64_image = item["base64"]
                                media_type = item.get("media_type", "image/jpeg")
                            else:
                                raise ValueError(
                                    "Image item must have either 'path' or 'base64' field"
                                )

                            processed_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{base64_image}"
                                    },
                                }
                            )

                    processed_messages.append(
                        {"role": msg.get("role", "user"), "content": processed_content}
                    )
                else:
                    # Simple string content (backward compatible)
                    processed_messages.append(msg)

            # Handle max tokens parameter - support both old and new names
            # No default limit - let the model generate as many tokens as needed
            max_completion = generation_config.get(
                "max_completion_tokens"
            ) or generation_config.get("max_tokens")

            # Show deprecation warning if using old parameter
            if (
                "max_tokens" in generation_config
                and "max_completion_tokens" not in generation_config
            ):
                import warnings

                warnings.warn(
                    "'max_tokens' is deprecated and will be removed in v0.5.0. "
                    "Please use 'max_completion_tokens' instead.",
                    DeprecationWarning,
                    stacklevel=3,
                )

            # FIX v0.9.6: Filter params for reasoning models (o1, o3, GPT-5)
            # These models only support temperature=1.0 and don't support top_p, etc.
            filtered_config = self._filter_reasoning_model_params(
                model, generation_config
            )

            # Prepare request
            request_params = {
                "model": model,
                "messages": processed_messages,
                "max_completion_tokens": max_completion,  # Always use new parameter
                "stop": filtered_config.get("stop"),
                "n": filtered_config.get("n", 1),
                "stream": kwargs.get("stream", False),
                "logit_bias": filtered_config.get("logit_bias"),
                "user": filtered_config.get("user"),
                "seed": filtered_config.get("seed"),
            }

            # Only add temperature/top_p params if not a reasoning model
            if not self._is_reasoning_model(model):
                request_params["temperature"] = filtered_config.get("temperature", 1.0)
                request_params["top_p"] = filtered_config.get("top_p", 1.0)
                request_params["frequency_penalty"] = filtered_config.get(
                    "frequency_penalty"
                )
                request_params["presence_penalty"] = filtered_config.get(
                    "presence_penalty"
                )

            # Handle response_format - must have valid 'type' field if provided
            response_format = filtered_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                # OpenAI requires response_format to have 'type' field
                if "type" in response_format:
                    request_params["response_format"] = response_format
                # Skip invalid/empty response_format to avoid API errors

            # Remove None values
            request_params = {k: v for k, v in request_params.items() if v is not None}

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                # Force tool usage for OpenAI when tools are provided (defaults to "required")
                # This ensures consistent tool calling behavior matching Claude Desktop's approach
                default_choice = "required" if tools and len(tools) > 0 else "auto"
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", default_choice
                )
                logger.debug(
                    "OpenAI async tools: %d tools, tool_choice=%s",
                    len(tools),
                    request_params.get("tool_choice"),
                )

            # Call OpenAI (async) — uses per-request client if overrides provided
            response = await async_client.chat.completions.create(**request_params)

            # Format response (same as sync)
            choice = response.choices[0]
            return {
                "id": response.id,
                "content": choice.message.content,
                "role": choice.message.role,
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    else []
                ),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except openai.BadRequestError as e:
            # Provide helpful error message for unsupported models or parameters
            logger.error("OpenAI BadRequestError: %s", e, exc_info=True)
            if "max_tokens" in str(e):
                raise RuntimeError(
                    "This OpenAI provider requires models that support max_completion_tokens. "
                    "Please use o4-mini, o3 "
                    "Older models like gpt-4o or gpt-3.5-turbo are not supported."
                )
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))
        except Exception as e:
            logger.error("OpenAI error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings using OpenAI.

        Supported kwargs:
        - model (str): OpenAI model name (default: "text-embedding-3-small")
        - dimensions (int): Desired dimensions (only for v3 models)
        - user (str): Unique user identifier for tracking
        """
        try:
            import openai

            model = kwargs.get("model", "text-embedding-3-small")
            dimensions = kwargs.get("dimensions")
            user = kwargs.get("user")

            # Initialize sync client if needed
            if self._sync_client is None:
                self._sync_client = openai.OpenAI()

            # Prepare request
            request_params = {"model": model, "input": texts}

            # Add optional parameters
            if dimensions and "embedding-3" in model:
                request_params["dimensions"] = dimensions
            if user:
                request_params["user"] = user

            # Call OpenAI (sync)
            response = self._sync_client.embeddings.create(**request_params)

            # Extract embeddings
            embeddings = [item.embedding for item in response.data]

            return embeddings

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("OpenAI embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings using OpenAI (async version).

        This async method provides non-blocking I/O for production deployments
        requiring concurrent embedding generation.

        Supported kwargs:
        - model (str): OpenAI model name (default: "text-embedding-3-small")
        - dimensions (int): Desired dimensions (only for v3 models)
        - user (str): Unique user identifier for tracking

        Returns:
            List of embedding vectors (same format as sync embed())

        Raises:
            RuntimeError: If AsyncOpenAI not configured or OpenAI library not installed
        """
        try:
            import openai

            model = kwargs.get("model", "text-embedding-3-small")
            dimensions = kwargs.get("dimensions")
            user = kwargs.get("user")

            # Initialize async client if needed
            if self._async_client is None:
                from openai import AsyncOpenAI

                self._async_client = AsyncOpenAI()

            # Prepare request
            request_params = {"model": model, "input": texts}

            # Add optional parameters
            if dimensions and "embedding-3" in model:
                request_params["dimensions"] = dimensions
            if user:
                request_params["user"] = user

            # Call OpenAI (async)
            response = await self._async_client.embeddings.create(**request_params)

            # Extract embeddings
            embeddings = [item.embedding for item in response.data]

            return embeddings

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("OpenAI embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "OpenAI"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about an OpenAI embedding model."""
        models = {
            "text-embedding-3-large": {
                "dimensions": 3072,
                "max_tokens": 8191,
                "description": "Most capable embedding model, supports dimensions",
                "capabilities": {
                    "variable_dimensions": True,
                    "min_dimensions": 256,
                    "max_dimensions": 3072,
                },
            },
            "text-embedding-3-small": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Efficient embedding model, supports dimensions",
                "capabilities": {
                    "variable_dimensions": True,
                    "min_dimensions": 256,
                    "max_dimensions": 1536,
                },
            },
            "text-embedding-ada-002": {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": "Legacy embedding model",
                "capabilities": {"variable_dimensions": False},
            },
        }

        return models.get(
            model,
            {
                "dimensions": 1536,
                "max_tokens": 8191,
                "description": f"OpenAI model: {model}",
                "capabilities": {},
            },
        )


class AnthropicProvider(LLMProvider):
    """
    Anthropic provider for Claude LLM models.

    Note: Anthropic currently only provides LLM capabilities, not embeddings.

    Prerequisites:
    - Set ANTHROPIC_API_KEY environment variable
    - Install anthropic package: `pip install anthropic`

    Supported models:
    - claude-3-opus-20240229 (Most capable, slower)
    - claude-3-sonnet-20240229 (Balanced performance)
    - claude-3-haiku-20240307 (Fastest, most affordable)
    - claude-2.1 (Previous generation)
    - claude-2.0
    - claude-instant-1.2
    """

    def is_available(self) -> bool:
        """Check if Anthropic is available."""
        if self._available is not None:
            return self._available

        try:
            import os

            # Check for API key
            self._available = bool(os.getenv("ANTHROPIC_API_KEY"))
        except ImportError:
            self._available = False

        return self._available

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate a chat completion using Anthropic."""
        try:
            import anthropic

            model = kwargs.get("model", "claude-3-sonnet-20240229")
            generation_config = kwargs.get("generation_config", {})

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                client_kwargs = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                client = _byok_cache.get_or_create(
                    per_request_api_key,
                    per_request_base_url,
                    factory=lambda: anthropic.Anthropic(**client_kwargs),
                )
            else:
                # Initialize shared client if needed
                if self._client is None:
                    self._client = anthropic.Anthropic()
                client = self._client

            # Convert messages to Anthropic format
            system_message = None
            user_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    # System messages are always text
                    system_message = (
                        msg["content"]
                        if isinstance(msg["content"], str)
                        else str(msg["content"])
                    )
                else:
                    # Process potentially complex content
                    if isinstance(msg.get("content"), list):
                        # Complex content with potential images
                        content_parts = []

                        for item in msg["content"]:
                            if item["type"] == "text":
                                content_parts.append(
                                    {"type": "text", "text": item["text"]}
                                )
                            elif item["type"] == "image":
                                # Lazy load vision utilities
                                from .vision_utils import encode_image, get_media_type

                                if "path" in item:
                                    base64_image = encode_image(item["path"])
                                    media_type = get_media_type(item["path"])
                                else:
                                    base64_image = item.get("base64", "")
                                    media_type = item.get("media_type", "image/jpeg")

                                content_parts.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": base64_image,
                                        },
                                    }
                                )
                            else:
                                # Warn about unhandled content types to prevent silent failures
                                content_type = item.get("type", "unknown")
                                if content_type not in ("text", "image"):
                                    import warnings

                                    warnings.warn(
                                        f"Unhandled content type '{content_type}' in AnthropicProvider. "
                                        f"Only 'text' and 'image' are supported. This content will be skipped.",
                                        UserWarning,
                                        stacklevel=2,
                                    )

                        user_messages.append(
                            {"role": msg["role"], "content": content_parts}
                        )
                    else:
                        # Simple string content (backward compatible)
                        user_messages.append(msg)

            # Call Anthropic - build kwargs to avoid passing None values
            create_kwargs = {
                "model": model,
                "messages": user_messages,
                "max_tokens": generation_config.get("max_tokens", 500),
                "temperature": generation_config.get("temperature", 0.7),
            }

            # Only add optional parameters if they have valid values
            if system_message is not None:
                create_kwargs["system"] = system_message
            if generation_config.get("top_p") is not None:
                create_kwargs["top_p"] = generation_config.get("top_p")
            if generation_config.get("top_k") is not None:
                create_kwargs["top_k"] = generation_config.get("top_k")
            if generation_config.get("stop_sequences") is not None:
                create_kwargs["stop_sequences"] = generation_config.get(
                    "stop_sequences"
                )
            if generation_config.get("metadata") is not None:
                create_kwargs["metadata"] = generation_config.get("metadata")

            response = client.messages.create(**create_kwargs)

            # Format response
            return {
                "id": response.id,
                "content": response.content[0].text,
                "role": "assistant",
                "model": response.model,
                "created": None,  # Anthropic doesn't provide this
                "tool_calls": [],  # Handle tool use if needed
                "finish_reason": response.stop_reason,
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens
                    + response.usage.output_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )
        except Exception as e:
            logger.error("Anthropic error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Anthropic"))

    async def chat_async(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate a chat completion using Anthropic (async version)."""
        try:
            import anthropic

            model = kwargs.get("model", "claude-3-sonnet-20240229")
            generation_config = kwargs.get("generation_config", {})

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                client_kwargs = {}
                if per_request_api_key:
                    client_kwargs["api_key"] = per_request_api_key
                if per_request_base_url:
                    client_kwargs["base_url"] = per_request_base_url
                client = anthropic.AsyncAnthropic(**client_kwargs)
            else:
                client = anthropic.AsyncAnthropic()

            # Convert messages to Anthropic format (same logic as sync)
            system_message = None
            user_messages = []

            for msg in messages:
                if msg["role"] == "system":
                    system_message = (
                        msg["content"]
                        if isinstance(msg["content"], str)
                        else str(msg["content"])
                    )
                else:
                    if isinstance(msg.get("content"), list):
                        content_parts = []
                        for item in msg["content"]:
                            if item["type"] == "text":
                                content_parts.append(
                                    {"type": "text", "text": item["text"]}
                                )
                            elif item["type"] == "image":
                                from .vision_utils import encode_image, get_media_type

                                if "path" in item:
                                    base64_image = encode_image(item["path"])
                                    media_type = get_media_type(item["path"])
                                else:
                                    base64_image = item.get("base64", "")
                                    media_type = item.get("media_type", "image/jpeg")

                                content_parts.append(
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": base64_image,
                                        },
                                    }
                                )
                        user_messages.append(
                            {"role": msg["role"], "content": content_parts}
                        )
                    else:
                        user_messages.append(msg)

            create_kwargs = {
                "model": model,
                "messages": user_messages,
                "max_tokens": generation_config.get("max_tokens", 500),
                "temperature": generation_config.get("temperature", 0.7),
            }

            if system_message is not None:
                create_kwargs["system"] = system_message
            if generation_config.get("top_p") is not None:
                create_kwargs["top_p"] = generation_config.get("top_p")
            if generation_config.get("top_k") is not None:
                create_kwargs["top_k"] = generation_config.get("top_k")
            if generation_config.get("stop_sequences") is not None:
                create_kwargs["stop_sequences"] = generation_config.get(
                    "stop_sequences"
                )

            response = await client.messages.create(**create_kwargs)

            return {
                "id": response.id,
                "content": response.content[0].text,
                "role": "assistant",
                "model": response.model,
                "created": None,
                "tool_calls": [],
                "finish_reason": response.stop_reason,
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens
                    + response.usage.output_tokens,
                },
                "metadata": {},
            }

        except ImportError:
            raise RuntimeError(
                "Anthropic library not installed. Install with: pip install anthropic"
            )
        except Exception as e:
            logger.error("Anthropic async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Anthropic"))


class CohereProvider(EmbeddingProvider):
    """
    Cohere provider for embedding operations.

    Note: This implementation focuses on embeddings. Cohere also provides
    LLM capabilities which could be added in the future.

    Prerequisites:
    - Set COHERE_API_KEY environment variable
    - Install cohere package: `pip install cohere`

    Supported embedding models:
    - embed-english-v3.0 (1024 dimensions)
    - embed-multilingual-v3.0 (1024 dimensions)
    - embed-english-light-v3.0 (384 dimensions)
    - embed-multilingual-light-v3.0 (384 dimensions)
    """

    def is_available(self) -> bool:
        """Check if Cohere is available."""
        if self._available is not None:
            return self._available

        try:
            import os

            # Check for API key
            self._available = bool(os.getenv("COHERE_API_KEY"))
        except ImportError:
            self._available = False

        return self._available

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings using Cohere."""
        try:
            import cohere

            model = kwargs.get("model", "embed-english-v3.0")
            input_type = kwargs.get("input_type", "search_document")
            truncate = kwargs.get("truncate", "END")

            # Initialize client if needed
            if self._client is None:
                self._client = cohere.Client()

            # Call Cohere
            response = self._client.embed(
                texts=texts, model=model, input_type=input_type, truncate=truncate
            )

            # Extract embeddings
            embeddings = response.embeddings

            return embeddings

        except ImportError:
            raise RuntimeError(
                "Cohere library not installed. Install with: pip install cohere"
            )
        except Exception as e:
            logger.error("Cohere embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Cohere"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about a Cohere embedding model."""
        models = {
            "embed-english-v3.0": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "English embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": ["en"],
                },
            },
            "embed-multilingual-v3.0": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "Multilingual embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": [
                        "en",
                        "es",
                        "fr",
                        "de",
                        "it",
                        "pt",
                        "ja",
                        "ko",
                        "zh",
                        "ar",
                        "hi",
                        "tr",
                    ],
                },
            },
            "embed-english-light-v3.0": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "Lightweight English embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": ["en"],
                },
            },
            "embed-multilingual-light-v3.0": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "Lightweight multilingual embedding model v3",
                "capabilities": {
                    "input_types": [
                        "search_query",
                        "search_document",
                        "classification",
                        "clustering",
                    ],
                    "languages": [
                        "en",
                        "es",
                        "fr",
                        "de",
                        "it",
                        "pt",
                        "ja",
                        "ko",
                        "zh",
                        "ar",
                        "hi",
                        "tr",
                    ],
                },
            },
        }

        return models.get(
            model,
            {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": f"Cohere embedding model: {model}",
                "capabilities": {},
            },
        )


class HuggingFaceProvider(EmbeddingProvider):
    """
    HuggingFace provider for embedding operations.

    This provider can use both the HuggingFace Inference API and local models.

    Prerequisites for API:
    - Set HUGGINGFACE_API_KEY environment variable
    - Install requests: `pip install requests`

    Prerequisites for local:
    - Install transformers: `pip install transformers torch`

    Supported embedding models:
    - sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
    - sentence-transformers/all-mpnet-base-v2 (768 dimensions)
    - BAAI/bge-large-en-v1.5 (1024 dimensions)
    - thenlper/gte-large (1024 dimensions)
    """

    def __init__(self):
        super().__init__()
        self._models = {}
        self._available_api = None
        self._available_local = None

    def is_available(self) -> bool:
        """Check if HuggingFace is available (either API or local)."""
        # Check API availability
        if self._available_api is None:
            try:
                import os

                self._available_api = bool(os.getenv("HUGGINGFACE_API_KEY"))
            except Exception:
                self._available_api = False

        # Check local availability
        if self._available_local is None:
            try:
                # Check if torch and transformers are available
                import importlib.util

                torch_spec = importlib.util.find_spec("torch")
                transformers_spec = importlib.util.find_spec("transformers")
                self._available_local = (
                    torch_spec is not None and transformers_spec is not None
                )
            except ImportError:
                self._available_local = False

        return self._available_api or self._available_local

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings using HuggingFace."""
        model = kwargs.get("model", "sentence-transformers/all-MiniLM-L6-v2")
        use_api = kwargs.get("use_api", self._available_api)
        normalize = kwargs.get("normalize", True)

        if use_api and self._available_api:
            return self._embed_api(texts, model, normalize)
        elif self._available_local:
            device = kwargs.get("device", "cpu")
            return self._embed_local(texts, model, device, normalize)
        else:
            raise RuntimeError(
                "Neither HuggingFace API nor local transformers available"
            )

    def _embed_api(
        self, texts: list[str], model: str, normalize: bool
    ) -> list[list[float]]:
        """Generate embeddings using HuggingFace Inference API."""
        try:
            import os

            import requests

            api_key = os.getenv("HUGGINGFACE_API_KEY")
            headers = {"Authorization": f"Bearer {api_key}"}

            api_url = f"https://api-inference.huggingface.co/models/{model}"

            embeddings = []
            for text in texts:
                response = requests.post(
                    api_url, headers=headers, json={"inputs": text}
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"HuggingFace API error: HTTP {response.status_code}"
                    )

                embedding = response.json()
                if isinstance(embedding, list) and isinstance(embedding[0], list):
                    embedding = embedding[0]  # Extract from nested list

                if normalize:
                    magnitude = sum(x * x for x in embedding) ** 0.5
                    if magnitude > 0:
                        embedding = [x / magnitude for x in embedding]

                embeddings.append(embedding)

            return embeddings

        except Exception as e:
            logger.error("HuggingFace API error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "HuggingFace"))

    def _embed_local(
        self, texts: list[str], model: str, device: str, normalize: bool
    ) -> list[list[float]]:
        """Generate embeddings using local HuggingFace model."""
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            # Load model if not cached
            if model not in self._models:
                tokenizer = AutoTokenizer.from_pretrained(model)
                model_obj = AutoModel.from_pretrained(model)
                model_obj.to(device)
                model_obj.eval()  # noqa: PGH001
                self._models[model] = (tokenizer, model_obj)

            tokenizer, model_obj = self._models[model]

            embeddings = []
            with torch.no_grad():
                for text in texts:
                    # Tokenize
                    inputs = tokenizer(
                        text, padding=True, truncation=True, return_tensors="pt"
                    ).to(device)

                    # Generate embeddings
                    outputs = model_obj(**inputs)

                    # Mean pooling
                    attention_mask = inputs["attention_mask"]
                    token_embeddings = outputs.last_hidden_state
                    input_mask_expanded = (
                        attention_mask.unsqueeze(-1)
                        .expand(token_embeddings.size())
                        .float()
                    )
                    embedding = torch.sum(
                        token_embeddings * input_mask_expanded, 1
                    ) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

                    # Convert to list
                    embedding = embedding.squeeze().cpu().numpy().tolist()

                    if normalize:
                        magnitude = sum(x * x for x in embedding) ** 0.5
                        if magnitude > 0:
                            embedding = [x / magnitude for x in embedding]

                    embeddings.append(embedding)

            return embeddings

        except ImportError:
            raise RuntimeError(
                "Transformers library not installed. Install with: pip install transformers torch"
            )
        except Exception as e:
            logger.error("HuggingFace local error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "HuggingFace"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about a HuggingFace embedding model."""
        models = {
            "sentence-transformers/all-MiniLM-L6-v2": {
                "dimensions": 384,
                "max_tokens": 256,
                "description": "Efficient sentence transformer model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["semantic_search", "clustering", "classification"],
                },
            },
            "sentence-transformers/all-mpnet-base-v2": {
                "dimensions": 768,
                "max_tokens": 384,
                "description": "High-quality sentence transformer model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["semantic_search", "clustering", "classification"],
                },
            },
            "BAAI/bge-large-en-v1.5": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "BAAI General Embedding model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["retrieval", "reranking", "classification"],
                },
            },
            "thenlper/gte-large": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "General Text Embeddings model",
                "capabilities": {
                    "languages": ["en"],
                    "use_cases": ["retrieval", "similarity", "clustering"],
                },
            },
        }

        return models.get(
            model,
            {
                "dimensions": 768,  # Common default
                "max_tokens": 512,
                "description": f"HuggingFace model: {model}",
                "capabilities": {},
            },
        )


class MockProvider(UnifiedAIProvider):
    """
    Mock provider for testing and development.

    This provider generates deterministic mock responses for both LLM and
    embedding operations without making actual API calls.

    Features:
    - Always available (no dependencies)
    - Generates consistent responses based on input
    - Zero latency
    - Supports both chat and embedding operations
    """

    def is_available(self) -> bool:
        """Mock provider is always available."""
        return True

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate mock LLM response with intelligent contextual patterns."""
        last_user_message = ""
        has_images = False
        full_conversation = []

        # Extract all messages for context
        for msg in messages:
            if msg.get("role") in ["user", "system", "assistant"]:
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            has_images = True
                    full_conversation.append(
                        f"{msg.get('role', 'user')}: {' '.join(text_parts)}"
                    )
                else:
                    full_conversation.append(f"{msg.get('role', 'user')}: {content}")

        # Get the last user message for primary pattern matching
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            has_images = True
                    last_user_message = " ".join(text_parts)
                else:
                    last_user_message = content
                break

        conversation_text = " ".join(full_conversation).lower()
        message_lower = last_user_message.lower()

        # Generate intelligent contextual mock response
        response_content = self._generate_contextual_response(
            message_lower, conversation_text, has_images, last_user_message
        )

        return {
            "id": f"mock_{hash(last_user_message)}",
            "content": response_content,
            "role": "assistant",
            "model": kwargs.get("model", "mock-model"),
            "created": 1701234567,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 100,  # Mock value
                "completion_tokens": len(response_content) // 4,
                "total_tokens": 0,  # Will be calculated
            },
            "metadata": {},
        }

    def _generate_contextual_response(
        self,
        message_lower: str,
        conversation_text: str,
        has_images: bool,
        original_message: str,
    ) -> str:
        """Generate contextually appropriate mock responses based on input patterns."""

        # Vision/Image responses
        if has_images:
            return "I can see the image(s) you've provided. The image contains several distinct elements that I can analyze for you. [Mock vision response with detailed observation]"

        # Mathematical and time calculation patterns
        if any(
            pattern in message_lower
            for pattern in [
                "calculate",
                "math",
                "time",
                "hour",
                "minute",
                "second",
                "duration",
            ]
        ) or any(
            op in message_lower
            for op in ["+", "-", "*", "/", "plus", "minus", "times", "divide"]
        ):
            # Specific train speed/distance problem
            if (
                "train" in conversation_text
                and "travels" in conversation_text
                and any(num in conversation_text for num in ["300", "450", "4"])
            ):
                return """Step 1: Calculate the train's speed
First, I need to find the train's speed using the given information.
Given: Distance = 300 km, Time = 4 hours
Speed = Distance ÷ Time = 300 km ÷ 4 hours = 75 km/hour

Step 2: Apply the speed to find time for new distance
Now I can use this speed to find how long it takes to travel 450 km.
Given: Speed = 75 km/hour, Distance = 450 km
Time = Distance ÷ Speed = 450 km ÷ 75 km/hour = 6 hours

Final Answer: 6 hours"""
            # Specific time calculation case: 9 - 3 hours
            elif (
                "9" in message_lower
                and "3" in message_lower
                and ("-" in message_lower or "minus" in message_lower)
            ) or (
                "time" in message_lower
                and any(num in message_lower for num in ["9", "3", "6"])
            ):
                return "Let me calculate this step by step:\n\n1. Starting with 9\n2. Subtracting 3: 9 - 3 = 6\n3. The result is 6\n\nSo the answer is 6 hours. This represents a time duration of 6 hours."
            # General mathematical operations
            elif any(
                op in message_lower
                for op in ["+", "-", "*", "/", "plus", "minus", "times", "divide"]
            ):
                return "I'll solve this mathematical problem step by step:\n\n1. First, I'll identify the operation\n2. Then apply the calculation\n3. Finally, provide the result with explanation\n\nThe calculation shows a clear mathematical relationship."
            # Time-related calculations
            elif any(
                time_word in message_lower
                for time_word in ["time", "hour", "minute", "second", "duration"]
            ):
                return "I'll help you with this time calculation. Let me work through this systematically:\n\n1. Identifying the time units involved\n2. Performing the calculation\n3. Providing the result in appropriate time format\n\nTime calculations require careful attention to units and precision."
            # General calculation requests
            else:
                return "I'll help you with this calculation. Let me work through this systematically to provide an accurate result with proper explanation of the mathematical process."

        # Chain of Thought (CoT) patterns
        if any(
            pattern in message_lower
            for pattern in [
                "step by step",
                "think through",
                "reasoning",
                "explain",
                "how do",
                "why does",
            ]
        ):
            return """Let me think through this step by step:

1. **Understanding the problem**: I need to break down the key components
2. **Analyzing the context**: Looking at the relevant factors and constraints
3. **Reasoning process**: Working through the logical connections
4. **Arriving at conclusion**: Based on the systematic analysis

This step-by-step approach ensures thorough reasoning and accurate results."""

        # ReAct (Reasoning + Acting) patterns
        if any(
            pattern in message_lower
            for pattern in [
                "plan",
                "action",
                "strategy",
                "approach",
                "implement",
                "execute",
            ]
        ):
            return """**Thought**: I need to analyze this request and determine the best approach.

**Action**: Let me break this down into actionable steps:
1. Assess the current situation
2. Identify required resources and constraints
3. Develop a systematic plan
4. Execute with monitoring

**Observation**: This approach allows for systematic problem-solving with clear action items.

**Final Action**: Proceeding with the structured implementation plan."""

        # Data analysis patterns
        if any(
            pattern in message_lower
            for pattern in ["analyze", "data", "pattern", "trend", "statistics"]
        ):
            return "Based on my analysis of the provided data, I can identify several key patterns:\n\n• **Trend Analysis**: The data shows distinct patterns over time\n• **Statistical Insights**: Key metrics indicate significant relationships\n• **Pattern Recognition**: I've identified recurring themes and anomalies\n• **Recommendations**: Based on this analysis, I suggest specific next steps"

        # Creative and generation patterns
        if any(
            pattern in message_lower
            for pattern in ["create", "generate", "write", "compose", "design", "build"]
        ):
            return "I'll help you create that. Let me approach this systematically:\n\n**Planning Phase**:\n- Understanding your requirements\n- Identifying key components needed\n\n**Creation Process**:\n- Developing the core structure\n- Adding details and refinements\n\n**Quality Assurance**:\n- Reviewing for completeness\n- Ensuring it meets your needs"

        # Question and inquiry patterns
        if "?" in message_lower or any(
            pattern in message_lower
            for pattern in ["what is", "how does", "why is", "when does", "where is"]
        ):
            return f"Regarding your question about '{original_message[:100]}...', here's a comprehensive answer:\n\nThe key points to understand are:\n• **Primary concept**: This relates to fundamental principles\n• **Practical application**: How this applies in real-world scenarios\n• **Important considerations**: Factors to keep in mind\n• **Next steps**: Recommendations for further exploration"

        # Problem-solving patterns
        if any(
            pattern in message_lower
            for pattern in ["problem", "issue", "error", "fix", "solve", "troubleshoot"]
        ):
            return "I'll help you solve this problem systematically:\n\n**Problem Analysis**:\n- Identifying the core issue\n- Understanding contributing factors\n\n**Solution Development**:\n- Exploring potential approaches\n- Evaluating pros and cons\n\n**Implementation Plan**:\n- Step-by-step resolution process\n- Monitoring and validation steps"

        # Tool calling and function patterns
        if any(
            pattern in message_lower
            for pattern in ["tool", "function", "call", "api", "service", "endpoint"]
        ):
            return "I'll help you with this tool/function call. Let me identify the appropriate tools and execute them systematically:\n\n**Tool Selection**: Identifying the best tools for this task\n**Parameter Preparation**: Setting up the required parameters\n**Execution**: Calling the tools with proper error handling\n**Result Processing**: Interpreting and formatting the results\n\nThis ensures reliable tool execution with comprehensive error handling."

        # Code and technical patterns
        if any(
            pattern in message_lower
            for pattern in ["code", "algorithm", "script", "program", "debug"]
        ):
            return "I'll help you with this technical implementation:\n\n```\n# Technical solution approach\n# 1. Understanding requirements\n# 2. Designing the solution\n# 3. Implementation details\n# 4. Testing and validation\n```\n\nThis approach ensures robust, maintainable code with proper error handling."

        # Learning and explanation patterns
        if any(
            pattern in message_lower
            for pattern in ["explain", "teach", "learn", "understand", "clarify"]
        ):
            return "Let me explain this concept clearly:\n\n**Foundation**: Starting with the basic principles\n**Key Concepts**: The essential ideas you need to understand\n**Examples**: Practical illustrations to make it concrete\n**Application**: How to use this knowledge effectively\n\nThis explanation provides a solid foundation for understanding."

        # Debate/Argument patterns - return structured JSON
        if any(
            pattern in message_lower
            for pattern in [
                "argument",
                "debate",
                "position",
                "for or against",
                "key_points",
                "evidence",
                "argue about",
                "topic to argue",
            ]
        ) or (
            "topic" in message_lower
            and ("for" in message_lower or "against" in message_lower)
        ):
            import json

            return json.dumps(
                {
                    "argument": "This is a well-reasoned argument supporting the given position with logical analysis and evidence-based conclusions.",
                    "key_points": [
                        "Point 1: Analysis of key factors",
                        "Point 2: Supporting evidence and reasoning",
                        "Point 3: Practical implications",
                    ],
                    "evidence": "Research and analysis support this position based on established principles and documented outcomes.",
                }
            )

        # Judgment/Decision patterns - return structured JSON
        if any(
            pattern in message_lower
            for pattern in ["judgment", "decision", "winner", "judge", "verdict"]
        ):
            import json

            return json.dumps(
                {
                    "decision": "for",
                    "winner": "proponent",
                    "reasoning": "After careful analysis of both arguments, the proponent presented stronger evidence and more compelling logic.",
                    "confidence": 0.85,
                }
            )

        # Rebuttal patterns - return structured JSON
        if any(
            pattern in message_lower
            for pattern in ["rebuttal", "counterpoint", "counter argument", "rebut"]
        ):
            import json

            return json.dumps(
                {
                    "rebuttal": "This rebuttal addresses the key weaknesses in the opposing argument with focused counterpoints.",
                    "counterpoints": [
                        "Counter 1: Logical flaw in premise",
                        "Counter 2: Missing evidence for claims",
                        "Counter 3: Alternative interpretation",
                    ],
                    "strength": 0.75,
                }
            )

        # Chain of thought structured output patterns
        if any(
            pattern in message_lower
            for pattern in ["step1", "step2", "step3", "final_answer", "confidence"]
        ):
            import json

            return json.dumps(
                {
                    "step1": "First, I identify and understand the problem components.",
                    "step2": "Next, I analyze the relevant factors and constraints.",
                    "step3": "Then, I develop a systematic approach to solve the problem.",
                    "step4": "I apply the method and verify intermediate results.",
                    "step5": "Finally, I synthesize the findings into a coherent answer.",
                    "final_answer": "Based on the step-by-step analysis, the answer is derived systematically.",
                    "confidence": 0.85,
                }
            )

        # Default contextual response
        if len(original_message) > 100:
            return f"I understand you're asking about '{original_message[:100]}...'. This is a complex topic that requires careful consideration of multiple factors. Let me provide a thorough response that addresses your key concerns and offers actionable insights."
        else:
            return f"I understand your request about '{original_message}'. Based on the context and requirements, I can provide a comprehensive response that addresses your specific needs with practical solutions and clear explanations."

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate mock embeddings."""
        model = kwargs.get("model", "mock-embedding")
        dimensions = kwargs.get("dimensions", 1536)
        normalize = kwargs.get("normalize", True)

        embeddings = []
        for text in texts:
            # Generate deterministic embedding based on text hash
            seed = int(hashlib.md5(f"{model}:{text}".encode()).hexdigest()[:8], 16)

            import random

            random.seed(seed)

            # Generate random vector
            embedding = [random.gauss(0, 1) for _ in range(dimensions)]

            # Normalize if requested
            if normalize:
                magnitude = sum(x * x for x in embedding) ** 0.5
                if magnitude > 0:
                    embedding = [x / magnitude for x in embedding]

            embeddings.append(embedding)

        return embeddings

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about a mock embedding model."""
        models = {
            "mock-embedding-small": {"dimensions": 384, "max_tokens": 512},
            "mock-embedding": {"dimensions": 1536, "max_tokens": 8192},
            "mock-embedding-large": {"dimensions": 3072, "max_tokens": 8192},
        }

        return models.get(
            model,
            {
                "dimensions": 1536,
                "max_tokens": 8192,
                "description": f"Mock embedding model: {model}",
                "capabilities": {"all_features": True},
            },
        )


# ============================================================================
# Azure AI Foundry Provider
# ============================================================================


class AzureAIFoundryProvider(UnifiedAIProvider):
    """
    Azure AI Foundry provider for LLM and embedding operations.

    Supports models deployed on Azure AI Foundry including:
    - Azure OpenAI (GPT-4o, GPT-4-turbo, etc.)
    - Meta Llama models
    - Mistral models
    - Cohere models

    Prerequisites:
        * Azure subscription with AI Foundry resource
        * Deployed model endpoint
        * Set AZURE_AI_INFERENCE_ENDPOINT environment variable
        * Set AZURE_AI_INFERENCE_API_KEY environment variable
          (or use Azure Identity for managed identity auth)

    Supported LLM models (depends on deployment):
        * gpt-4o, gpt-4-turbo (Azure OpenAI)
        * Llama-3.1-8B, Llama-3.1-70B (Meta)
        * Mistral-large, Mixtral-8x7B (Mistral)

    Supported embedding models:
        * text-embedding-3-small (1536 dimensions)
        * text-embedding-3-large (3072 dimensions)
    """

    def __init__(self, use_async: bool = False):
        """
        Initialize Azure AI Foundry provider.

        Args:
            use_async: If True, prefer async operations for non-blocking I/O.
        """
        super().__init__()
        self._use_async = use_async
        self._sync_chat_client = None
        self._sync_embed_client = None
        self._async_chat_client = None
        self._async_embed_client = None
        self._model_cache = {}

    def is_available(self) -> bool:
        """Check if Azure AI Foundry is configured."""
        if self._available is not None:
            return self._available

        import os

        endpoint = os.getenv("AZURE_AI_INFERENCE_ENDPOINT")
        api_key = os.getenv("AZURE_AI_INFERENCE_API_KEY")

        # Available if we have endpoint AND api_key
        self._available = bool(endpoint and api_key)
        return self._available

    def _get_credential(self):
        """Get Azure credential (API key or managed identity)."""
        import os

        from azure.core.credentials import AzureKeyCredential

        api_key = os.getenv("AZURE_AI_INFERENCE_API_KEY")
        if api_key:
            return AzureKeyCredential(api_key)

        # Fall back to DefaultAzureCredential for managed identity
        try:
            from azure.identity import DefaultAzureCredential

            return DefaultAzureCredential()
        except ImportError:
            raise RuntimeError(
                "No API key found and azure-identity not installed. "
                "Set AZURE_AI_INFERENCE_API_KEY or install azure-identity."
            )

    def _get_endpoint(self) -> str:
        """Get Azure endpoint URL."""
        import os

        endpoint = os.getenv("AZURE_AI_INFERENCE_ENDPOINT")
        if not endpoint:
            raise RuntimeError(
                "AZURE_AI_INFERENCE_ENDPOINT environment variable not set."
            )
        return endpoint

    def _convert_messages(self, messages: List[Message]) -> list:
        """Convert messages to Azure format with vision support."""
        from azure.ai.inference.models import (
            AssistantMessage,
            SystemMessage,
            UserMessage,
        )

        azure_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle complex content (vision/multi-modal)
            if isinstance(content, list):
                # Try to use Azure's content item types for vision
                try:
                    from azure.ai.inference.models import (
                        ImageContentItem,
                        ImageUrl,
                        TextContentItem,
                    )

                    content_items = []
                    for item in content:
                        if item.get("type") == "text":
                            content_items.append(
                                TextContentItem(text=item.get("text", ""))
                            )
                        elif item.get("type") == "image_url":
                            url = item.get("image_url", {}).get("url", "")
                            content_items.append(
                                ImageContentItem(image_url=ImageUrl(url=url))
                            )
                        elif item.get("type") == "image":
                            # Handle our internal image format
                            if "path" in item:
                                from .vision_utils import encode_image, get_media_type

                                base64_data = encode_image(item["path"])
                                media_type = get_media_type(item["path"])
                                url = f"data:{media_type};base64,{base64_data}"
                            elif "base64" in item:
                                media_type = item.get("media_type", "image/jpeg")
                                url = f"data:{media_type};base64,{item['base64']}"
                            else:
                                continue
                            content_items.append(
                                ImageContentItem(image_url=ImageUrl(url=url))
                            )
                        else:
                            # Warn about unhandled content types to prevent silent failures
                            content_type = item.get("type", "unknown")
                            if content_type not in ("text", "image", "image_url"):
                                import warnings

                                warnings.warn(
                                    f"Unhandled content type '{content_type}' in AzureAIFoundryProvider. "
                                    f"Only 'text', 'image', and 'image_url' are supported. This content will be skipped.",
                                    UserWarning,
                                    stacklevel=2,
                                )

                    if role == "user":
                        azure_messages.append(UserMessage(content=content_items))
                    else:
                        # For non-user roles with complex content, extract text only
                        text_content = " ".join(
                            item.get("text", "")
                            for item in content
                            if item.get("type") == "text"
                        )
                        if role == "system":
                            azure_messages.append(SystemMessage(content=text_content))
                        elif role == "assistant":
                            azure_messages.append(
                                AssistantMessage(content=text_content)
                            )

                except ImportError:
                    # Fallback: extract text only if vision types not available
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    text_content = " ".join(text_parts)
                    if role == "system":
                        azure_messages.append(SystemMessage(content=text_content))
                    elif role == "assistant":
                        azure_messages.append(AssistantMessage(content=text_content))
                    else:
                        azure_messages.append(UserMessage(content=text_content))
            else:
                # Simple string content
                if role == "system":
                    azure_messages.append(SystemMessage(content=content))
                elif role == "assistant":
                    azure_messages.append(AssistantMessage(content=content))
                else:
                    azure_messages.append(UserMessage(content=content))

        return azure_messages

    def _format_tool_calls(self, message) -> list:
        """Format tool calls from Azure response."""
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return []
        return [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate chat completion using Azure AI Foundry."""
        try:
            from azure.ai.inference import ChatCompletionsClient
            from azure.core.credentials import AzureKeyCredential

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model")
            tools = kwargs.get("tools", [])

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                endpoint = per_request_base_url or self._get_endpoint()
                credential = (
                    AzureKeyCredential(per_request_api_key)
                    if per_request_api_key
                    else self._get_credential()
                )
                chat_client = ChatCompletionsClient(
                    endpoint=endpoint,
                    credential=credential,
                )
            else:
                # Initialize shared client if needed
                if self._sync_chat_client is None:
                    self._sync_chat_client = ChatCompletionsClient(
                        endpoint=self._get_endpoint(),
                        credential=self._get_credential(),
                    )
                chat_client = self._sync_chat_client

            # Convert messages to Azure format
            azure_messages = self._convert_messages(messages)

            # Build request parameters
            request_params = {
                "messages": azure_messages,
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": kwargs.get("stream", False),
            }

            # Add model if specified
            if model:
                request_params["model"] = model

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            # Handle response_format translation for structured output (OpenAI-style -> Azure)
            # Azure AI Inference SDK uses JsonSchemaFormat class
            response_format = generation_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                response_type = response_format.get("type")

                try:
                    from azure.ai.inference.models import JsonSchemaFormat

                    if response_type == "json_schema":
                        # OpenAI strict mode -> Azure JSON Schema mode
                        # Format: {"type": "json_schema", "json_schema": {"name": "...", "strict": True, "schema": {...}}}
                        json_schema = response_format.get("json_schema", {})
                        request_params["response_format"] = JsonSchemaFormat(
                            name=json_schema.get("name", "response"),
                            schema=json_schema.get("schema", {}),
                            strict=json_schema.get("strict", True),
                        )
                    elif response_type == "json_object":
                        # OpenAI legacy mode -> Azure JSON mode (empty schema)
                        # Just force JSON output without strict schema
                        request_params["response_format"] = JsonSchemaFormat(
                            name="response",
                            schema={"type": "object"},
                            strict=False,
                        )
                except ImportError:
                    # Older SDK version doesn't support JsonSchemaFormat
                    pass

            # Remove None values
            request_params = {k: v for k, v in request_params.items() if v is not None}

            # Call Azure
            response = chat_client.complete(**request_params)

            # Format response
            choice = response.choices[0]
            return {
                "id": response.id,
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": (
                    int(response.created.timestamp()) if response.created else None
                ),
                "tool_calls": self._format_tool_calls(choice.message),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {"provider": "azure_ai_foundry"},
            }

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. "
                "Install with: pip install azure-ai-inference azure-identity"
            )
        except Exception as e:
            logger.error("Azure AI Foundry error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    async def chat_async(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate chat completion using Azure AI Foundry (async)."""
        try:
            from azure.ai.inference.aio import ChatCompletionsClient
            from azure.core.credentials import AzureKeyCredential

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model")
            tools = kwargs.get("tools", [])

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")
            per_request_base_url = kwargs.get("base_url")

            if per_request_api_key or per_request_base_url:
                endpoint = per_request_base_url or self._get_endpoint()
                credential = (
                    AzureKeyCredential(per_request_api_key)
                    if per_request_api_key
                    else self._get_credential()
                )
                async_chat_client = ChatCompletionsClient(
                    endpoint=endpoint,
                    credential=credential,
                )
            else:
                # Initialize shared async client if needed
                if self._async_chat_client is None:
                    self._async_chat_client = ChatCompletionsClient(
                        endpoint=self._get_endpoint(),
                        credential=self._get_credential(),
                    )
                async_chat_client = self._async_chat_client

            # Convert messages (same as sync)
            azure_messages = self._convert_messages(messages)

            # Build request
            request_params = {
                "messages": azure_messages,
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": kwargs.get("stream", False),
            }

            if model:
                request_params["model"] = model

            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            # Handle response_format translation for structured output (OpenAI-style -> Azure)
            # Azure AI Inference SDK uses JsonSchemaFormat class
            response_format = generation_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                response_type = response_format.get("type")

                try:
                    from azure.ai.inference.models import JsonSchemaFormat

                    if response_type == "json_schema":
                        # OpenAI strict mode -> Azure JSON Schema mode
                        json_schema = response_format.get("json_schema", {})
                        request_params["response_format"] = JsonSchemaFormat(
                            name=json_schema.get("name", "response"),
                            schema=json_schema.get("schema", {}),
                            strict=json_schema.get("strict", True),
                        )
                    elif response_type == "json_object":
                        # OpenAI legacy mode -> Azure JSON mode
                        request_params["response_format"] = JsonSchemaFormat(
                            name="response",
                            schema={"type": "object"},
                            strict=False,
                        )
                except ImportError:
                    pass

            request_params = {k: v for k, v in request_params.items() if v is not None}

            # Call Azure (async)
            response = await async_chat_client.complete(**request_params)

            choice = response.choices[0]
            return {
                "id": response.id,
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": (
                    int(response.created.timestamp()) if response.created else None
                ),
                "tool_calls": self._format_tool_calls(choice.message),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                "metadata": {"provider": "azure_ai_foundry"},
            }

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. "
                "Install with: pip install azure-ai-inference azure-identity"
            )
        except Exception as e:
            logger.error("Azure AI Foundry async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings using Azure AI Foundry."""
        try:
            from azure.ai.inference import EmbeddingsClient

            model = kwargs.get("model")

            # Initialize client if needed
            if self._sync_embed_client is None:
                self._sync_embed_client = EmbeddingsClient(
                    endpoint=self._get_endpoint(),
                    credential=self._get_credential(),
                )

            # Build request
            request_params = {"input": texts}
            if model:
                request_params["model"] = model

            response = self._sync_embed_client.embed(**request_params)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. "
                "Install with: pip install azure-ai-inference"
            )
        except Exception as e:
            logger.error("Azure AI Foundry embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings using Azure AI Foundry (async)."""
        try:
            from azure.ai.inference.aio import EmbeddingsClient

            model = kwargs.get("model")

            if self._async_embed_client is None:
                self._async_embed_client = EmbeddingsClient(
                    endpoint=self._get_endpoint(),
                    credential=self._get_credential(),
                )

            request_params = {"input": texts}
            if model:
                request_params["model"] = model

            response = await self._async_embed_client.embed(**request_params)
            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "Azure AI Inference library not installed. "
                "Install with: pip install azure-ai-inference"
            )
        except Exception as e:
            logger.error("Azure AI Foundry async embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Azure AI Foundry"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about an Azure AI Foundry model."""
        if model in self._model_cache:
            return self._model_cache[model]

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
            self._model_cache[model] = known_models[model]
            return known_models[model]

        return {
            "dimensions": 1536,
            "max_tokens": 8191,
            "description": f"Azure AI Foundry model: {model}",
            "capabilities": {},
        }


# ============================================================================
# Docker Model Runner Provider
# ============================================================================


class DockerModelRunnerProvider(UnifiedAIProvider):
    """
    Docker Model Runner provider for local LLM and embedding operations.

    Uses Docker Desktop's Model Runner with GPU acceleration. Provides an
    OpenAI-compatible API running locally with no API keys required.

    Prerequisites:
        * Docker Desktop 4.40+ with Model Runner enabled
        * Models pulled via: docker model pull ai/llama3.2
        * TCP access enabled: docker desktop enable model-runner --tcp 12434

    Supported LLM models (pull from Docker Hub):
        * ai/llama3.2 (default), ai/llama3.3
        * ai/gemma3, ai/gemma2
        * ai/mistral, ai/mixtral
        * ai/phi4, ai/qwen3

    Supported embedding models:
        * ai/mxbai-embed-large (1024 dimensions)
        * ai/nomic-embed-text (768 dimensions)
        * ai/all-minilm (384 dimensions)

    Tool Calling Support (Model-Dependent):
        * Supported: ai/qwen3, ai/llama3.3, ai/gemma3
        * Not Supported: ai/smollm2, smaller quantized models

    GPU Support:
        * Apple Silicon (Metal)
        * NVIDIA GPUs (CUDA)
        * AMD/Intel GPUs (Vulkan)
    """

    DEFAULT_BASE_URL = "http://localhost:12434/engines/llama.cpp/v1"
    CONTAINER_BASE_URL = "http://model-runner.docker.internal/engines/llama.cpp/v1"

    # Models known to support tool calling
    TOOL_CAPABLE_MODELS = frozenset(
        {
            "ai/qwen3",
            "ai/llama3.3",
            "ai/gemma3",
        }
    )

    def __init__(self, use_async: bool = False):
        """
        Initialize Docker Model Runner provider.

        Args:
            use_async: If True, prefer async operations.
        """
        super().__init__()
        self._use_async = use_async
        self._sync_client = None
        self._async_client = None
        self._model_cache = {}

    def _get_base_url(self) -> str:
        """Get base URL from environment or default."""
        import os

        return os.getenv("DOCKER_MODEL_RUNNER_URL", self.DEFAULT_BASE_URL)

    def is_available(self) -> bool:
        """Check if Docker Model Runner is running."""
        if self._available is not None:
            return self._available

        import urllib.error
        import urllib.request

        try:
            url = f"{self._get_base_url()}/models"
            req = urllib.request.urlopen(url, timeout=2)
            self._available = req.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            self._available = False
        except Exception:
            self._available = False

        return self._available

    def supports_tools(self, model: str) -> bool:
        """
        Check if a model supports tool calling.

        Args:
            model: Model name (e.g., "ai/qwen3", "ai/llama3.2")

        Returns:
            True if model is known to support tool calling
        """
        # Check if model starts with any tool-capable prefix
        return any(model.startswith(prefix) for prefix in self.TOOL_CAPABLE_MODELS)

    def _process_messages(self, messages: List[Message]) -> list:
        """Process messages, extracting text from complex content."""
        processed = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                # Extract text parts from complex content
                text_parts = [
                    item.get("text", "")
                    for item in content
                    if item.get("type") == "text"
                ]
                content = " ".join(text_parts)
            processed.append(
                {
                    "role": msg.get("role", "user"),
                    "content": content,
                }
            )
        return processed

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate chat completion using Docker Model Runner."""
        try:
            import openai

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model", "ai/llama3.2")
            tools = kwargs.get("tools", [])
            stream = kwargs.get("stream", False)

            # Warn if tools requested but model doesn't support them
            if tools and not self.supports_tools(model):
                import warnings

                warnings.warn(
                    f"Model {model} may not support tool calling. "
                    f"Consider using: {', '.join(sorted(self.TOOL_CAPABLE_MODELS))}",
                    UserWarning,
                    stacklevel=2,
                )

            # Limitation: Disable streaming when using tools (llama.cpp limitation)
            if tools and stream:
                stream = False

            # Per-request base URL override for BYOK multi-tenant
            per_request_base_url = kwargs.get("base_url")

            if per_request_base_url:
                client = openai.OpenAI(
                    api_key="docker-model-runner",
                    base_url=per_request_base_url,
                )
            else:
                # Initialize shared client if needed
                if self._sync_client is None:
                    self._sync_client = openai.OpenAI(
                        api_key="docker-model-runner",  # Required but not validated
                        base_url=self._get_base_url(),
                    )
                client = self._sync_client

            # Build request
            request_params = {
                "model": model,
                "messages": self._process_messages(messages),
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": stream,
            }

            # Add tools if provided and model supports them
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            # Remove None values
            request_params = {k: v for k, v in request_params.items() if v is not None}

            response = client.chat.completions.create(**request_params)

            # Format response
            choice = response.choices[0]
            usage = response.usage

            return {
                "id": response.id or f"docker_{hash(str(messages))}",
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    and choice.message.tool_calls
                    else []
                ),
                "finish_reason": choice.finish_reason or "stop",
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
                "metadata": {
                    "provider": "docker_model_runner",
                    "supports_tools": self.supports_tools(model),
                },
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Docker Model Runner error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    async def chat_async(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """Generate chat completion using Docker Model Runner (async)."""
        try:
            from openai import AsyncOpenAI

            generation_config = kwargs.get("generation_config", {})
            model = kwargs.get("model", "ai/llama3.2")
            tools = kwargs.get("tools", [])
            stream = kwargs.get("stream", False)

            # Warn if tools requested but model doesn't support them
            if tools and not self.supports_tools(model):
                import warnings

                warnings.warn(
                    f"Model {model} may not support tool calling. "
                    f"Consider using: {', '.join(sorted(self.TOOL_CAPABLE_MODELS))}",
                    UserWarning,
                    stacklevel=2,
                )

            # Limitation: Disable streaming when using tools
            if tools and stream:
                stream = False

            # Per-request base URL override for BYOK multi-tenant
            per_request_base_url = kwargs.get("base_url")

            if per_request_base_url:
                async_client = AsyncOpenAI(
                    api_key="docker-model-runner",
                    base_url=per_request_base_url,
                )
            else:
                if self._async_client is None:
                    self._async_client = AsyncOpenAI(
                        api_key="docker-model-runner",
                        base_url=self._get_base_url(),
                    )
                async_client = self._async_client

            request_params = {
                "model": model,
                "messages": self._process_messages(messages),
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens"),
                "top_p": generation_config.get("top_p"),
                "stop": generation_config.get("stop"),
                "stream": stream,
            }

            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            request_params = {k: v for k, v in request_params.items() if v is not None}

            response = await async_client.chat.completions.create(**request_params)

            choice = response.choices[0]
            usage = response.usage

            return {
                "id": response.id or f"docker_{hash(str(messages))}",
                "content": choice.message.content,
                "role": "assistant",
                "model": response.model,
                "created": response.created,
                "tool_calls": (
                    choice.message.tool_calls
                    if hasattr(choice.message, "tool_calls")
                    and choice.message.tool_calls
                    else []
                ),
                "finish_reason": choice.finish_reason or "stop",
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
                "metadata": {
                    "provider": "docker_model_runner",
                    "supports_tools": self.supports_tools(model),
                },
            }

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Docker Model Runner async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings using Docker Model Runner."""
        try:
            import openai

            model = kwargs.get("model", "ai/mxbai-embed-large")

            if self._sync_client is None:
                self._sync_client = openai.OpenAI(
                    api_key="docker-model-runner",
                    base_url=self._get_base_url(),
                )

            response = self._sync_client.embeddings.create(
                model=model,
                input=texts,
            )

            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Docker Model Runner embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings using Docker Model Runner (async)."""
        try:
            from openai import AsyncOpenAI

            model = kwargs.get("model", "ai/mxbai-embed-large")

            if self._async_client is None:
                self._async_client = AsyncOpenAI(
                    api_key="docker-model-runner",
                    base_url=self._get_base_url(),
                )

            response = await self._async_client.embeddings.create(
                model=model,
                input=texts,
            )

            return [item.embedding for item in response.data]

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error(
                "Docker Model Runner async embedding error: %s", e, exc_info=True
            )
            raise RuntimeError(sanitize_provider_error(e, "Docker Model Runner"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about a Docker Model Runner model."""
        if model in self._model_cache:
            return self._model_cache[model]

        known_models = {
            "ai/mxbai-embed-large": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "mxbai-embed-large embedding model (Matryoshka support)",
                "capabilities": {
                    "batch_processing": True,
                    "matryoshka_dimensions": [1024, 512, 256, 128, 64],
                },
            },
            "ai/nomic-embed-text": {
                "dimensions": 768,
                "max_tokens": 8192,
                "description": "Nomic embedding model (Matryoshka support)",
                "capabilities": {
                    "batch_processing": True,
                    "matryoshka_dimensions": [768, 512, 256, 128, 64],
                },
            },
            "ai/all-minilm": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "all-MiniLM-L6-v2 lightweight embedding model",
                "capabilities": {"batch_processing": True},
            },
            "ai/qwen3-embedding": {
                "dimensions": 1024,
                "max_tokens": 8192,
                "description": "Qwen3 embedding model",
                "capabilities": {"batch_processing": True},
            },
        }

        if model in known_models:
            self._model_cache[model] = known_models[model]
            return known_models[model]

        return {
            "dimensions": 1024,
            "max_tokens": 4096,
            "description": f"Docker Model Runner model: {model}",
            "capabilities": {},
        }


# ============================================================================
# Google Gemini Provider
# ============================================================================


class GoogleGeminiProvider(UnifiedAIProvider):
    """
    Google Gemini provider for LLM and embedding operations.

    Uses the new Google GenAI SDK (google-genai) for accessing Gemini models.
    Supports both chat completions and text embeddings.

    Prerequisites:
        * Install: ``pip install google-genai``
        * Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable
        * OR use Vertex AI with project configuration

    Supported LLM models:
        * gemini-2.5-flash (latest, recommended)
        * gemini-2.0-flash (fast, efficient)
        * gemini-1.5-pro (high capability)
        * gemini-1.5-flash (balanced)

    Supported embedding models:
        * text-embedding-004 (768 dimensions, recommended)
        * embedding-001 (768 dimensions, legacy)

    Environment Variables:
        * GOOGLE_API_KEY: Google AI API key (primary)
        * GEMINI_API_KEY: Alternative API key name
        * GOOGLE_CLOUD_PROJECT: For Vertex AI mode
        * GOOGLE_CLOUD_LOCATION: For Vertex AI mode (default: us-central1)
    """

    def __init__(self, use_async: bool = False):
        """
        Initialize Google Gemini provider.

        Args:
            use_async: If True, prefer async operations for non-blocking I/O.
        """
        super().__init__()
        self._use_async = use_async
        self._sync_client = None
        self._async_client = None
        self._model_cache = {}

    def is_available(self) -> bool:
        """Check if Google Gemini is configured."""
        if self._available is not None:
            return self._available

        import os

        # Check for API key (support both naming conventions)
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        # Also check for Vertex AI configuration
        project = os.getenv("GOOGLE_CLOUD_PROJECT")

        self._available = bool(api_key or project)
        return self._available

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._sync_client is not None:
            return self._sync_client

        try:
            import os

            from google import genai

            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

            if project:
                # Use Vertex AI
                self._sync_client = genai.Client(
                    vertexai=True,
                    project=project,
                    location=location,
                )
            elif api_key:
                # Use Gemini Developer API
                self._sync_client = genai.Client(api_key=api_key)
            else:
                raise RuntimeError(
                    "No Google credentials found. Set GOOGLE_API_KEY, GEMINI_API_KEY, "
                    "or GOOGLE_CLOUD_PROJECT environment variable."
                )

            return self._sync_client

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )

    def _convert_messages_to_contents(self, messages: List[Message]) -> list:
        """
        Convert OpenAI-format messages to Google GenAI content format.

        The Google GenAI SDK uses a different content structure. This method
        handles the conversion including vision/multimodal content.
        """
        from google.genai import types

        contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle system messages separately (used as system_instruction)
            if role == "system":
                if isinstance(content, str):
                    system_instruction = content
                elif isinstance(content, list):
                    # Extract text from complex content
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if item.get("type") == "text"
                    ]
                    system_instruction = " ".join(text_parts)
                continue

            # Map roles
            genai_role = "model" if role == "assistant" else "user"

            # Handle complex content (vision/multimodal)
            if isinstance(content, list):
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append(types.Part.from_text(text=item.get("text", "")))
                    elif item.get("type") == "image":
                        # Handle image content
                        if "path" in item:
                            from .vision_utils import encode_image, get_media_type

                            base64_data = encode_image(item["path"])
                            media_type = get_media_type(item["path"])
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(base64_data),
                                    mime_type=media_type,
                                )
                            )
                        elif "base64" in item:
                            media_type = item.get("media_type", "image/jpeg")
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(item["base64"]),
                                    mime_type=media_type,
                                )
                            )
                    elif item.get("type") == "image_url":
                        # Handle OpenAI-style image_url format
                        url = item.get("image_url", {}).get("url", "")
                        if url.startswith("data:"):
                            # Parse data URL
                            import re

                            match = re.match(
                                r"data:([^;]+);base64,(.+)", url, re.DOTALL
                            )
                            if match:
                                media_type, base64_data = match.groups()
                                parts.append(
                                    types.Part.from_bytes(
                                        data=__import__("base64").b64decode(
                                            base64_data
                                        ),
                                        mime_type=media_type,
                                    )
                                )
                    elif item.get("type") == "audio":
                        # Handle audio content (native multimodal audio support)
                        if "path" in item:
                            from .audio_utils import encode_audio, get_audio_media_type

                            base64_data = encode_audio(item["path"])
                            media_type = get_audio_media_type(item["path"])
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(base64_data),
                                    mime_type=media_type,
                                )
                            )
                        elif "base64" in item:
                            media_type = item.get("media_type", "audio/mpeg")
                            parts.append(
                                types.Part.from_bytes(
                                    data=__import__("base64").b64decode(item["base64"]),
                                    mime_type=media_type,
                                )
                            )
                        elif "bytes" in item:
                            media_type = item.get("media_type", "audio/mpeg")
                            parts.append(
                                types.Part.from_bytes(
                                    data=item["bytes"],
                                    mime_type=media_type,
                                )
                            )
                    elif item.get("type") == "audio_url":
                        # Handle audio data URLs (similar to image_url)
                        url = item.get("audio_url", {}).get("url", "")
                        if url.startswith("data:audio"):
                            import re

                            match = re.match(
                                r"data:([^;]+);base64,(.+)", url, re.DOTALL
                            )
                            if match:
                                media_type, base64_data = match.groups()
                                parts.append(
                                    types.Part.from_bytes(
                                        data=__import__("base64").b64decode(
                                            base64_data
                                        ),
                                        mime_type=media_type,
                                    )
                                )
                    else:
                        # Warn about unhandled content types to prevent silent failures
                        content_type = item.get("type", "unknown")
                        import warnings

                        warnings.warn(
                            f"Unhandled content type '{content_type}' in message. "
                            "This content will be skipped. Supported types: "
                            "text, image, image_url, audio, audio_url.",
                            UserWarning,
                            stacklevel=2,
                        )

                if parts:
                    contents.append(types.Content(role=genai_role, parts=parts))
            else:
                # Simple string content
                contents.append(
                    types.Content(
                        role=genai_role,
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        return contents, system_instruction

    def _convert_tools(self, tools: list) -> list:
        """Convert OpenAI-format tools to Google GenAI format."""
        if not tools:
            return []

        from google.genai import types

        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=func.get("name", ""),
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    )
                )

        if function_declarations:
            return [types.Tool(function_declarations=function_declarations)]
        return []

    def _format_tool_calls(self, response) -> list:
        """Extract and format tool calls from Google response."""
        tool_calls = []

        if not hasattr(response, "candidates") or not response.candidates:
            return tool_calls

        candidate = response.candidates[0]
        if not hasattr(candidate, "content") or not candidate.content:
            return tool_calls

        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append(
                    {
                        "id": f"call_{hashlib.md5(fc.name.encode()).hexdigest()[:8]}",
                        "type": "function",
                        "function": {
                            "name": fc.name,
                            "arguments": (
                                __import__("json").dumps(dict(fc.args))
                                if fc.args
                                else "{}"
                            ),
                        },
                    }
                )

        return tool_calls

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate chat completion using Google Gemini.

        Args:
            messages: Conversation messages in OpenAI format.
            **kwargs: Additional arguments including:
                model (str): Gemini model name (default: "gemini-2.0-flash")
                generation_config (dict): Generation parameters including:
                    * temperature, max_tokens (mapped to max_output_tokens)
                    * top_p, top_k, stop_sequences
                    * response_format (dict): OpenAI-style structured output config.
                      Supports both json_schema and json_object modes:
                      - {"type": "json_schema", "json_schema": {"name": "...", "schema": {...}}}
                        -> Translated to response_mime_type="application/json" + response_json_schema
                      - {"type": "json_object"}
                        -> Translated to response_mime_type="application/json"
                tools (List[Dict]): Function/tool definitions

        Returns:
            Dict containing the standardized response.
        """
        try:
            from google.genai import types

            model = kwargs.get("model", "gemini-2.0-flash")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            # Per-request API key override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")

            if per_request_api_key:
                from google import genai

                client = genai.Client(api_key=per_request_api_key)
            else:
                client = self._get_client()

            # Convert messages
            contents, system_instruction = self._convert_messages_to_contents(messages)

            # Build generation config
            config_params = {}
            if "temperature" in generation_config:
                config_params["temperature"] = generation_config["temperature"]
            if "max_tokens" in generation_config:
                config_params["max_output_tokens"] = generation_config["max_tokens"]
            if "max_output_tokens" in generation_config:
                config_params["max_output_tokens"] = generation_config[
                    "max_output_tokens"
                ]
            if "top_p" in generation_config:
                config_params["top_p"] = generation_config["top_p"]
            if "top_k" in generation_config:
                config_params["top_k"] = generation_config["top_k"]
            if "stop" in generation_config:
                config_params["stop_sequences"] = generation_config["stop"]

            # Handle response_format translation for structured output (OpenAI-style -> Google)
            # This enables JSON mode when using BaseAgent with output fields
            response_format = generation_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                response_type = response_format.get("type")

                if response_type == "json_schema":
                    # OpenAI strict mode -> Google JSON mode with schema
                    # Format: {"type": "json_schema", "json_schema": {"name": "...", "strict": True, "schema": {...}}}
                    config_params["response_mime_type"] = "application/json"
                    json_schema = response_format.get("json_schema", {})
                    if "schema" in json_schema:
                        config_params["response_json_schema"] = json_schema["schema"]
                elif response_type == "json_object":
                    # OpenAI legacy mode -> Google JSON mode (no schema)
                    # Format: {"type": "json_object"}
                    config_params["response_mime_type"] = "application/json"

            # Gemini rejects response_mime_type combined with tools (gh#340)
            if tools:
                config_params.pop("response_mime_type", None)
                config_params.pop("response_json_schema", None)

            # Build request config
            request_config = types.GenerateContentConfig(**config_params)

            # Add system instruction if present
            if system_instruction:
                request_config.system_instruction = system_instruction

            # Add tools if provided
            if tools:
                request_config.tools = self._convert_tools(tools)

            # Call Gemini
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=request_config,
            )

            # Extract response
            content_text = ""
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        content_text += part.text

            # Get usage info
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(
                        response.usage_metadata, "prompt_token_count", 0
                    ),
                    "completion_tokens": getattr(
                        response.usage_metadata, "candidates_token_count", 0
                    ),
                    "total_tokens": getattr(
                        response.usage_metadata, "total_token_count", 0
                    ),
                }

            # Determine finish reason
            finish_reason = "stop"
            if response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason"):
                    fr = str(candidate.finish_reason).lower()
                    if "tool" in fr or "function" in fr:
                        finish_reason = "tool_calls"
                    elif "max" in fr or "length" in fr:
                        finish_reason = "length"
                    elif "safety" in fr:
                        finish_reason = "content_filter"

            return {
                "id": f"gemini-{hashlib.md5(content_text.encode()).hexdigest()[:12]}",
                "content": content_text,
                "role": "assistant",
                "model": model,
                "created": __import__("time").time(),
                "tool_calls": self._format_tool_calls(response),
                "finish_reason": finish_reason,
                "usage": usage,
                "metadata": {"provider": "google_gemini"},
            }

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    async def chat_async(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate chat completion using Google Gemini (async version).

        This async method provides non-blocking I/O for production deployments.
        Uses the async client from google-genai SDK.

        Args:
            messages: Conversation messages in OpenAI format.
            **kwargs: Same as sync chat() method.

        Returns:
            Dict containing the standardized response (same format as sync chat())
        """
        try:
            from google.genai import types

            model = kwargs.get("model", "gemini-2.0-flash")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            # Per-request API key override for BYOK multi-tenant
            per_request_api_key = kwargs.get("api_key")

            if per_request_api_key:
                from google import genai

                client = genai.Client(api_key=per_request_api_key)
            else:
                # Get the sync client (we'll use its aio interface)
                client = self._get_client()

            # Convert messages
            contents, system_instruction = self._convert_messages_to_contents(messages)

            # Build generation config
            config_params = {}
            if "temperature" in generation_config:
                config_params["temperature"] = generation_config["temperature"]
            if "max_tokens" in generation_config:
                config_params["max_output_tokens"] = generation_config["max_tokens"]
            if "max_output_tokens" in generation_config:
                config_params["max_output_tokens"] = generation_config[
                    "max_output_tokens"
                ]
            if "top_p" in generation_config:
                config_params["top_p"] = generation_config["top_p"]
            if "top_k" in generation_config:
                config_params["top_k"] = generation_config["top_k"]
            if "stop" in generation_config:
                config_params["stop_sequences"] = generation_config["stop"]

            # Handle response_format translation for structured output (OpenAI-style -> Google)
            # This enables JSON mode when using BaseAgent with output fields
            response_format = generation_config.get("response_format")
            if response_format and isinstance(response_format, dict):
                response_type = response_format.get("type")

                if response_type == "json_schema":
                    # OpenAI strict mode -> Google JSON mode with schema
                    # Format: {"type": "json_schema", "json_schema": {"name": "...", "strict": True, "schema": {...}}}
                    config_params["response_mime_type"] = "application/json"
                    json_schema = response_format.get("json_schema", {})
                    if "schema" in json_schema:
                        config_params["response_json_schema"] = json_schema["schema"]
                elif response_type == "json_object":
                    # OpenAI legacy mode -> Google JSON mode (no schema)
                    # Format: {"type": "json_object"}
                    config_params["response_mime_type"] = "application/json"

            # Gemini rejects response_mime_type combined with tools (gh#340)
            if tools:
                config_params.pop("response_mime_type", None)
                config_params.pop("response_json_schema", None)

            request_config = types.GenerateContentConfig(**config_params)

            if system_instruction:
                request_config.system_instruction = system_instruction

            if tools:
                request_config.tools = self._convert_tools(tools)

            # Call Gemini (async via client.aio)
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=request_config,
            )

            # Extract response (same as sync)
            content_text = ""
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        content_text += part.text

            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(
                        response.usage_metadata, "prompt_token_count", 0
                    ),
                    "completion_tokens": getattr(
                        response.usage_metadata, "candidates_token_count", 0
                    ),
                    "total_tokens": getattr(
                        response.usage_metadata, "total_token_count", 0
                    ),
                }

            finish_reason = "stop"
            if response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason"):
                    fr = str(candidate.finish_reason).lower()
                    if "tool" in fr or "function" in fr:
                        finish_reason = "tool_calls"
                    elif "max" in fr or "length" in fr:
                        finish_reason = "length"
                    elif "safety" in fr:
                        finish_reason = "content_filter"

            return {
                "id": f"gemini-{hashlib.md5(content_text.encode()).hexdigest()[:12]}",
                "content": content_text,
                "role": "assistant",
                "model": model,
                "created": __import__("time").time(),
                "tool_calls": self._format_tool_calls(response),
                "finish_reason": finish_reason,
                "usage": usage,
                "metadata": {"provider": "google_gemini"},
            }

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini async error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings using Google Gemini.

        Args:
            texts: List of texts to embed.
            **kwargs: Additional arguments including:
                model (str): Embedding model (default: "text-embedding-004")
                task_type (str): Task type for embeddings (optional)
                    Options: RETRIEVAL_QUERY, RETRIEVAL_DOCUMENT,
                             SEMANTIC_SIMILARITY, CLASSIFICATION, CLUSTERING

        Returns:
            List of embedding vectors.
        """
        try:
            from google.genai import types

            model = kwargs.get("model", "text-embedding-004")
            task_type = kwargs.get("task_type")

            client = self._get_client()

            # Build embed config
            config_params = {}
            if task_type:
                config_params["task_type"] = task_type

            config = (
                types.EmbedContentConfig(**config_params) if config_params else None
            )

            # Generate embeddings
            embeddings = []
            for text in texts:
                response = client.models.embed_content(
                    model=model,
                    contents=text,
                    config=config,
                )
                if response.embeddings:
                    embeddings.append(list(response.embeddings[0].values))
                else:
                    embeddings.append([])

            return embeddings

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Generate embeddings using Google Gemini (async version).

        Args:
            texts: List of texts to embed.
            **kwargs: Same as sync embed() method.

        Returns:
            List of embedding vectors.
        """
        try:
            from google.genai import types

            model = kwargs.get("model", "text-embedding-004")
            task_type = kwargs.get("task_type")

            client = self._get_client()

            config_params = {}
            if task_type:
                config_params["task_type"] = task_type

            config = (
                types.EmbedContentConfig(**config_params) if config_params else None
            )

            # Generate embeddings (async)
            embeddings = []
            for text in texts:
                response = await client.aio.models.embed_content(
                    model=model,
                    contents=text,
                    config=config,
                )
                if response.embeddings:
                    embeddings.append(list(response.embeddings[0].values))
                else:
                    embeddings.append([])

            return embeddings

        except ImportError:
            raise RuntimeError(
                "Google GenAI library not installed. Install with: pip install google-genai"
            )
        except Exception as e:
            logger.error("Google Gemini async embedding error: %s", e, exc_info=True)
            raise RuntimeError(sanitize_provider_error(e, "Google Gemini"))

    def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about a Google Gemini embedding model."""
        if model in self._model_cache:
            return self._model_cache[model]

        known_models = {
            "text-embedding-004": {
                "dimensions": 768,
                "max_tokens": 2048,
                "description": "Google's latest text embedding model",
                "capabilities": {"variable_dimensions": False},
            },
            "embedding-001": {
                "dimensions": 768,
                "max_tokens": 2048,
                "description": "Google's legacy embedding model",
                "capabilities": {"variable_dimensions": False},
            },
        }

        if model in known_models:
            self._model_cache[model] = known_models[model]
            return known_models[model]

        return {
            "dimensions": 768,
            "max_tokens": 2048,
            "description": f"Google Gemini model: {model}",
            "capabilities": {},
        }


# ============================================================================
# Perplexity Provider
# ============================================================================


class PerplexityProvider(LLMProvider):
    """
    Perplexity AI provider for LLM operations with integrated web search.

    Perplexity provides real-time web search capabilities integrated directly
    into the language model, returning responses with citations and sources.
    Unlike standard LLMs, Perplexity models access current information from
    the web to provide up-to-date, factual answers.

    Prerequisites:
    - Set PERPLEXITY_API_KEY environment variable
    - Install openai package: `pip install openai` (uses OpenAI-compatible API)

    Supported models:
    - sonar: Lightweight search model for quick queries
    - sonar-pro: Advanced search with deeper analysis
    - sonar-reasoning: Chain-of-thought reasoning with search
    - sonar-reasoning-pro: Premier reasoning model with comprehensive search
    - sonar-deep-research: Exhaustive research with configurable effort levels

    Perplexity-Specific Features:
    - return_citations (bool): Include source citations in response
    - return_related_questions (bool): Get follow-up question suggestions
    - return_images (bool): Include relevant images in results
    - search_domain_filter (list): Allow/deny specific domains (max 20)
    - search_recency_filter (str): Time filter: "month", "week", "day", "hour"
    - search_mode (str): Search type: "web", "academic", "sec"
    - reasoning_effort (str): For deep-research: "low", "medium", "high"
    - language_preference (str): Preferred response language
    - disable_search (bool): Use only training data, no web search

    Generation Config Parameters:
    - temperature (float): Sampling temperature (default 0.2, range 0-2)
    - max_tokens (int): Maximum tokens to generate
    - top_p (float): Nucleus sampling probability (default 0.9)
    - presence_penalty (float): Penalize repeated topics
    - frequency_penalty (float): Penalize repeated tokens

    Response Metadata:
    The response includes Perplexity-specific metadata:
    - citations: List of source URLs used in the response
    - search_results: Full search result objects with title, URL, date
    - related_questions: Suggested follow-up questions
    - images: Relevant images when return_images=True
    """

    # Base URL for Perplexity API
    BASE_URL = "https://api.perplexity.ai"

    # Default model
    DEFAULT_MODEL = "sonar"

    # Supported models with their capabilities
    SUPPORTED_MODELS = {
        "sonar": {
            "description": "Lightweight search model",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 128000,
        },
        "sonar-pro": {
            "description": "Advanced search capabilities",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 200000,
        },
        "sonar-reasoning": {
            "description": "Reasoning with search",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 128000,
        },
        "sonar-reasoning-pro": {
            "description": "Premier reasoning model",
            "supports_search": True,
            "supports_citations": True,
            "context_length": 128000,
        },
        "sonar-deep-research": {
            "description": "Exhaustive research with effort levels",
            "supports_search": True,
            "supports_citations": True,
            "supports_reasoning_effort": True,
            "context_length": 128000,
        },
    }

    def __init__(self, use_async: bool = False):
        """
        Initialize Perplexity provider with async support.

        Args:
            use_async: If True, uses AsyncOpenAI client for non-blocking operations.
                      If False (default), uses synchronous OpenAI client.
        """
        super().__init__()
        self._use_async = use_async
        self._sync_client = None
        self._async_client = None

    def is_available(self) -> bool:
        """Check if Perplexity is available."""
        if self._available is not None:
            return self._available

        import os

        self._available = bool(os.getenv("PERPLEXITY_API_KEY"))
        return self._available

    def _get_api_key(self) -> str:
        """Get the Perplexity API key from environment."""
        import os

        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "PERPLEXITY_API_KEY not found. Set the environment variable to use Perplexity."
            )
        return api_key

    def _process_messages(self, messages: List[Message]) -> list:
        """
        Process messages for Perplexity API.

        Perplexity supports multimodal input including images and documents.
        This method handles both simple text and complex content formats.

        Args:
            messages: List of messages with potential complex content

        Returns:
            List of processed messages suitable for Perplexity API
        """
        processed = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                # Complex content - extract text and images
                processed_content = []
                for item in content:
                    if item.get("type") == "text":
                        processed_content.append(
                            {"type": "text", "text": item.get("text", "")}
                        )
                    elif item.get("type") == "image":
                        # Perplexity supports image URLs
                        if "url" in item:
                            processed_content.append(
                                {"type": "image_url", "image_url": {"url": item["url"]}}
                            )
                        elif "path" in item:
                            # Encode local images as base64
                            from .vision_utils import encode_image, get_media_type

                            base64_image = encode_image(item["path"])
                            media_type = get_media_type(item["path"])
                            processed_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{base64_image}"
                                    },
                                }
                            )
                        elif "base64" in item:
                            media_type = item.get("media_type", "image/jpeg")
                            processed_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{item['base64']}"
                                    },
                                }
                            )

                processed.append(
                    {"role": msg.get("role", "user"), "content": processed_content}
                )
            else:
                # Simple string content
                processed.append({"role": msg.get("role", "user"), "content": content})

        return processed

    def _build_request_params(
        self, messages: list, model: str, generation_config: dict, **kwargs
    ) -> dict:
        """
        Build request parameters for Perplexity API.

        Perplexity-specific parameters are passed via extra_body since the OpenAI
        SDK doesn't natively support them.

        Args:
            messages: Processed messages
            model: Model name
            generation_config: Generation configuration
            **kwargs: Additional Perplexity-specific parameters

        Returns:
            Dictionary of request parameters
        """
        # Base parameters (standard OpenAI-compatible params)
        params = {
            "model": model,
            "messages": messages,
            "temperature": generation_config.get("temperature", 0.2),
            "top_p": generation_config.get("top_p", 0.9),
        }

        # Optional generation parameters (standard OpenAI params)
        if "max_tokens" in generation_config:
            params["max_tokens"] = generation_config["max_tokens"]
        if "presence_penalty" in generation_config:
            params["presence_penalty"] = generation_config["presence_penalty"]
        if "frequency_penalty" in generation_config:
            params["frequency_penalty"] = generation_config["frequency_penalty"]
        if "stop" in generation_config:
            params["stop"] = generation_config["stop"]

        # Response format for structured output
        if "response_format" in generation_config:
            params["response_format"] = generation_config["response_format"]

        # Streaming
        if kwargs.get("stream", False):
            params["stream"] = True

        # Perplexity-specific parameters go in extra_body
        perplexity_config = kwargs.get("perplexity_config", {})
        extra_body = {}

        # Citation and search result options
        if "return_related_questions" in perplexity_config:
            extra_body["return_related_questions"] = perplexity_config[
                "return_related_questions"
            ]
        if "return_images" in perplexity_config:
            extra_body["return_images"] = perplexity_config["return_images"]

        # Search configuration
        if "search_domain_filter" in perplexity_config:
            # Validate max 20 domains
            domains = perplexity_config["search_domain_filter"]
            if len(domains) > 20:
                raise ValueError("search_domain_filter supports maximum 20 domains")
            extra_body["search_domain_filter"] = domains

        if "search_recency_filter" in perplexity_config:
            valid_recency = ["month", "week", "day", "hour"]
            recency = perplexity_config["search_recency_filter"]
            if recency not in valid_recency:
                raise ValueError(
                    f"search_recency_filter must be one of: {valid_recency}"
                )
            extra_body["search_recency_filter"] = recency

        if "search_mode" in perplexity_config:
            valid_modes = ["web", "academic", "sec"]
            mode = perplexity_config["search_mode"]
            if mode not in valid_modes:
                raise ValueError(f"search_mode must be one of: {valid_modes}")
            extra_body["search_mode"] = mode

        # Deep research reasoning effort (only for sonar-deep-research)
        if "reasoning_effort" in perplexity_config:
            if model == "sonar-deep-research":
                valid_efforts = ["low", "medium", "high"]
                effort = perplexity_config["reasoning_effort"]
                if effort not in valid_efforts:
                    raise ValueError(
                        f"reasoning_effort must be one of: {valid_efforts}"
                    )
                extra_body["reasoning_effort"] = effort

        # Language preference (sonar and sonar-pro only)
        if "language_preference" in perplexity_config:
            if model in ["sonar", "sonar-pro"]:
                extra_body["language_preference"] = perplexity_config[
                    "language_preference"
                ]

        # Disable search option
        if perplexity_config.get("disable_search", False):
            extra_body["disable_search"] = True

        # Date filters
        for date_filter in [
            "search_after_date_filter",
            "search_before_date_filter",
            "last_updated_after_filter",
            "last_updated_before_filter",
        ]:
            if date_filter in perplexity_config:
                extra_body[date_filter] = perplexity_config[date_filter]

        # Web search options (user location, context size)
        if "web_search_options" in perplexity_config:
            extra_body["web_search_options"] = perplexity_config["web_search_options"]

        # Add extra_body if there are Perplexity-specific parameters
        if extra_body:
            params["extra_body"] = extra_body

        return params

    def _format_response(self, response, raw_response: dict = None) -> dict:
        """
        Format Perplexity response to standard format.

        Includes Perplexity-specific metadata like citations and search results.

        Args:
            response: OpenAI-style response object
            raw_response: Optional raw response dict for additional fields

        Returns:
            Standardized response dictionary
        """
        choice = response.choices[0]

        # Build metadata with Perplexity-specific fields
        metadata = {}

        # Extract citations from response if available
        if hasattr(response, "citations") and response.citations:
            metadata["citations"] = response.citations
        elif raw_response and "citations" in raw_response:
            metadata["citations"] = raw_response["citations"]

        # Extract search results
        if hasattr(response, "search_results") and response.search_results:
            metadata["search_results"] = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "date": r.get("date", ""),
                }
                for r in response.search_results
            ]
        elif raw_response and "search_results" in raw_response:
            metadata["search_results"] = raw_response["search_results"]

        # Extract related questions
        if hasattr(response, "related_questions") and response.related_questions:
            metadata["related_questions"] = response.related_questions
        elif raw_response and "related_questions" in raw_response:
            metadata["related_questions"] = raw_response["related_questions"]

        # Extract images
        if hasattr(response, "images") and response.images:
            metadata["images"] = response.images
        elif raw_response and "images" in raw_response:
            metadata["images"] = raw_response["images"]

        # Build usage info
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                "total_tokens": getattr(response.usage, "total_tokens", 0),
            }
            # Perplexity-specific usage fields
            if hasattr(response.usage, "search_context_tokens"):
                usage["search_context_tokens"] = response.usage.search_context_tokens
            if hasattr(response.usage, "citation_tokens"):
                usage["citation_tokens"] = response.usage.citation_tokens

        return {
            "id": response.id if hasattr(response, "id") else "",
            "content": choice.message.content if choice.message.content else "",
            "role": "assistant",
            "model": response.model if hasattr(response, "model") else "",
            "created": response.created if hasattr(response, "created") else None,
            "tool_calls": [],  # Perplexity doesn't support tool calling yet
            "finish_reason": choice.finish_reason if choice.finish_reason else "stop",
            "usage": usage,
            "metadata": metadata,
        }

    def chat(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate a chat completion using Perplexity with integrated web search.

        Args:
            messages: Conversation messages in OpenAI format
            **kwargs: Additional parameters including:
                - model (str): Model name (default: "sonar")
                - generation_config (dict): Temperature, max_tokens, etc.
                - perplexity_config (dict): Perplexity-specific options:
                    - return_citations (bool): Include citations (default: True)
                    - return_related_questions (bool): Get follow-up suggestions
                    - return_images (bool): Include relevant images
                    - search_domain_filter (list): Domain allow/deny list
                    - search_recency_filter (str): Time filter
                    - search_mode (str): "web", "academic", or "sec"
                    - reasoning_effort (str): For deep-research model
                    - language_preference (str): Response language
                    - disable_search (bool): Use only training data

        Returns:
            Dict containing response with content, citations, and metadata

        Example:
            >>> provider = PerplexityProvider()
            >>> response = provider.chat(
            ...     [{"role": "user", "content": "What are the latest AI developments?"}],
            ...     model="sonar-pro",
            ...     perplexity_config={
            ...         "search_recency_filter": "week",
            ...         "return_related_questions": True
            ...     }
            ... )
            >>> print(response["content"])
            >>> print(response["metadata"]["citations"])
        """
        try:
            import openai

            model = kwargs.pop("model", self.DEFAULT_MODEL)
            generation_config = kwargs.pop("generation_config", {})

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.pop("api_key", None)
            per_request_base_url = kwargs.pop("base_url", None)

            if per_request_api_key or per_request_base_url:
                client = openai.OpenAI(
                    api_key=per_request_api_key or self._get_api_key(),
                    base_url=per_request_base_url or self.BASE_URL,
                )
            else:
                # Initialize shared sync client if needed
                if self._sync_client is None:
                    self._sync_client = openai.OpenAI(
                        api_key=self._get_api_key(),
                        base_url=self.BASE_URL,
                    )
                client = self._sync_client

            # Process messages
            processed_messages = self._process_messages(messages)

            # Build request parameters
            request_params = self._build_request_params(
                processed_messages, model, generation_config, **kwargs
            )

            # Make API call
            response = client.chat.completions.create(**request_params)

            # Format and return response
            return self._format_response(response)

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Perplexity error: %s", e, exc_info=True)
            if "api_key" in str(e).lower():
                raise RuntimeError(
                    "Perplexity API key invalid or not set. "
                    "Set PERPLEXITY_API_KEY environment variable."
                )
            raise RuntimeError(sanitize_provider_error(e, "Perplexity"))

    async def chat_async(self, messages: List[Message], **kwargs) -> dict[str, Any]:
        """
        Generate a chat completion using Perplexity (async version).

        This async method provides non-blocking I/O for production deployments
        and concurrent agent execution.

        Args:
            messages: Conversation messages in OpenAI format
            **kwargs: Same parameters as chat()

        Returns:
            Dict containing response with content, citations, and metadata
        """
        try:
            from openai import AsyncOpenAI

            model = kwargs.pop("model", self.DEFAULT_MODEL)
            generation_config = kwargs.pop("generation_config", {})

            # Per-request API key and base URL override for BYOK multi-tenant
            per_request_api_key = kwargs.pop("api_key", None)
            per_request_base_url = kwargs.pop("base_url", None)

            if per_request_api_key or per_request_base_url:
                client = AsyncOpenAI(
                    api_key=per_request_api_key or self._get_api_key(),
                    base_url=per_request_base_url or self.BASE_URL,
                )
            else:
                # Initialize shared async client if needed
                if self._async_client is None:
                    self._async_client = AsyncOpenAI(
                        api_key=self._get_api_key(),
                        base_url=self.BASE_URL,
                    )
                client = self._async_client

            # Process messages
            processed_messages = self._process_messages(messages)

            # Build request parameters
            request_params = self._build_request_params(
                processed_messages, model, generation_config, **kwargs
            )

            # Make async API call
            response = await client.chat.completions.create(**request_params)

            # Format and return response
            return self._format_response(response)

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            logger.error("Perplexity error: %s", e, exc_info=True)
            if "api_key" in str(e).lower():
                raise RuntimeError(
                    "Perplexity API key invalid or not set. "
                    "Set PERPLEXITY_API_KEY environment variable."
                )
            raise RuntimeError(sanitize_provider_error(e, "Perplexity"))

    def get_supported_models(self) -> dict:
        """
        Get information about supported Perplexity models.

        Returns:
            Dict mapping model names to their capabilities
        """
        return self.SUPPORTED_MODELS.copy()


# ============================================================================
# Provider Registry and Factory
# ============================================================================

# Import UnifiedAzureProvider for intelligent Azure backend selection
from .unified_azure_provider import UnifiedAzureProvider

# Provider registry mapping names to classes
PROVIDERS = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "cohere": CohereProvider,
    "huggingface": HuggingFaceProvider,
    "mock": MockProvider,
    "azure": UnifiedAzureProvider,  # Intelligent unified provider (auto-detects backend)
    "azure_openai": UnifiedAzureProvider,  # Alias pointing to unified provider
    "azure_ai_foundry": AzureAIFoundryProvider,  # Legacy direct access (deprecated)
    "docker": DockerModelRunnerProvider,
    "google": GoogleGeminiProvider,
    "gemini": GoogleGeminiProvider,  # Alias for convenience
    "perplexity": PerplexityProvider,
    "pplx": PerplexityProvider,  # Alias for convenience
}


def get_provider(
    provider_name: str, provider_type: str | None = None
) -> BaseAIProvider | LLMProvider | EmbeddingProvider:
    """
    Get an AI provider instance by name.

    This factory function creates and returns the appropriate provider instance
    based on the provider name. It can optionally check for specific capabilities.

    Args:
        provider_name (str): Name of the provider to instantiate.
            Valid options: "ollama", "openai", "anthropic", "cohere", "huggingface", "mock"
            Case-insensitive.
        provider_type (str, optional): Required capability - "chat", "embeddings", or None for any.
            If specified, will raise an error if the provider doesn't support it.

    Returns:
        Provider instance with the requested capabilities.

    Raises:
        ValueError: If the provider name is not recognized or doesn't support the requested type.

    Examples:
        >>> # Get any provider
        >>> provider = get_provider("openai")
        >>> if provider.supports_chat():
        ...     # Use for chat
        ...     pass
        >>> if provider.supports_embeddings():
        ...     # Use for embeddings
        ...     pass

        >>> # Get chat-only provider
        >>> chat_provider = get_provider("anthropic", "chat")
        >>> response = chat_provider.chat(messages, model="claude-3-sonnet")

        >>> # Get embedding-only provider
        >>> embed_provider = get_provider("cohere", "embeddings")
        >>> embeddings = embed_provider.embed(texts, model="embed-english-v3.0")

        >>> # Check provider capabilities
        >>> provider = get_provider("ollama")
        >>> capabilities = provider.get_capabilities()
        >>> print(f"Chat: {capabilities['chat']}, Embeddings: {capabilities['embeddings']}")
    """
    provider_class = PROVIDERS.get(provider_name.lower())
    if not provider_class:
        raise ValueError(
            f"Unknown provider: {provider_name}. Available: {list(PROVIDERS.keys())}"
        )

    provider = provider_class()

    # Check for required capability if specified
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
    """
    Get information about all available providers.

    Args:
        provider_type (str, optional): Filter by capability - "chat", "embeddings", or None for all.

    Returns:
        Dict mapping provider names to their availability and capabilities.

    Examples:
        >>> # Get all providers
        >>> all_providers = get_available_providers()
        >>> for name, info in all_providers.items():
        ...     print(f"{name}: Available={info['available']}, Chat={info['chat']}, Embeddings={info['embeddings']}")

        >>> # Get only chat providers
        >>> chat_providers = get_available_providers("chat")

        >>> # Get only embedding providers
        >>> embed_providers = get_available_providers("embeddings")
    """
    results = {}

    for name in PROVIDERS:
        try:
            provider = get_provider(name)
            capabilities = provider.get_capabilities()

            # Apply filter if specified
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

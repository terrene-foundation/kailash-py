"""Unified AI provider implementations for LLM and embedding operations.

This module provides a unified interface for AI providers that support both
language model chat operations and text embedding generation. It reduces
redundancy by consolidating common functionality while maintaining clean
separation between LLM and embedding capabilities.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Union

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
            return {
                "id": f"ollama_{hash(str(messages))}",
                "content": response["message"]["content"],
                "role": "assistant",
                "model": model,
                "created": response.get("created_at"),
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": response.get("prompt_eval_count", 0),
                    "completion_tokens": response.get("eval_count", 0),
                    "total_tokens": response.get("prompt_eval_count", 0)
                    + response.get("eval_count", 0),
                },
                "metadata": {
                    "duration_ms": response.get("total_duration", 0) / 1e6,
                    "load_duration_ms": response.get("load_duration", 0) / 1e6,
                    "eval_duration_ms": response.get("eval_duration", 0) / 1e6,
                },
            }

        except ImportError:
            raise RuntimeError(
                "Ollama library not installed. Install with: pip install ollama"
            )
        except Exception as e:
            raise RuntimeError(f"Ollama error: {str(e)}")

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
            raise RuntimeError(f"Ollama embedding error: {str(e)}")

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

            # Initialize client if needed
            if self._client is None:
                self._client = openai.OpenAI()

            # Process messages for vision content
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
            max_completion = generation_config.get(
                "max_completion_tokens"
            ) or generation_config.get("max_tokens", 500)

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

            # Prepare request
            request_params = {
                "model": model,
                "messages": processed_messages,
                "temperature": generation_config.get("temperature", 1.0),
                "max_completion_tokens": max_completion,  # Always use new parameter
                "top_p": generation_config.get("top_p", 1.0),
                "frequency_penalty": generation_config.get("frequency_penalty"),
                "presence_penalty": generation_config.get("presence_penalty"),
                "stop": generation_config.get("stop"),
                "n": generation_config.get("n", 1),
                "stream": kwargs.get("stream", False),
                "logit_bias": generation_config.get("logit_bias"),
                "user": generation_config.get("user"),
                "response_format": generation_config.get("response_format"),
                "seed": generation_config.get("seed"),
            }

            # Remove None values
            request_params = {k: v for k, v in request_params.items() if v is not None}

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = generation_config.get(
                    "tool_choice", "auto"
                )

            # Call OpenAI
            response = self._client.chat.completions.create(**request_params)

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
            if "max_tokens" in str(e):
                raise RuntimeError(
                    "This OpenAI provider requires models that support max_completion_tokens. "
                    "Please use o4-mini, o3 "
                    "Older models like gpt-4o or gpt-3.5-turbo are not supported."
                )
            raise RuntimeError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {str(e)}")

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

            # Initialize client if needed
            if self._client is None:
                self._client = openai.OpenAI()

            # Prepare request
            request_params = {"model": model, "input": texts}

            # Add optional parameters
            if dimensions and "embedding-3" in model:
                request_params["dimensions"] = dimensions
            if user:
                request_params["user"] = user

            # Call OpenAI
            response = self._client.embeddings.create(**request_params)

            # Extract embeddings
            embeddings = [item.embedding for item in response.data]

            return embeddings

        except ImportError:
            raise RuntimeError(
                "OpenAI library not installed. Install with: pip install openai"
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI embedding error: {str(e)}")

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

            # Initialize client if needed
            if self._client is None:
                self._client = anthropic.Anthropic()

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

            response = self._client.messages.create(**create_kwargs)

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
            raise RuntimeError(f"Anthropic error: {str(e)}")


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
            raise RuntimeError(f"Cohere embedding error: {str(e)}")

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
                    raise RuntimeError(f"API error: {response.text}")

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
            raise RuntimeError(f"HuggingFace API error: {str(e)}")

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
            raise RuntimeError(f"HuggingFace local error: {str(e)}")

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
        """Generate mock LLM response."""
        last_user_message = ""
        has_images = False

        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Handle complex content with images
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

        # Generate contextual mock response
        if has_images:
            response_content = (
                "I can see the image(s) you've provided. [Mock vision response]"
            )
        elif "analyze" in last_user_message.lower():
            response_content = "Based on the provided data and context, I can see several key patterns..."
        elif "create" in last_user_message.lower():
            response_content = "I'll help you create that. Based on the requirements..."
        elif "?" in last_user_message:
            response_content = f"Regarding your question about '{last_user_message[:50]}...', here's what I found..."
        else:
            response_content = f"I understand you want me to work with: '{last_user_message[:100]}...'."

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
# Provider Registry and Factory
# ============================================================================

# Provider registry mapping names to classes
PROVIDERS = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "cohere": CohereProvider,
    "huggingface": HuggingFaceProvider,
    "mock": MockProvider,
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
            results[name] = {
                "available": False,
                "error": str(e),
                "chat": False,
                "embeddings": False,
            }

    return results

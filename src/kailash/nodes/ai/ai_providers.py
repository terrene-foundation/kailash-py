"""Unified AI provider implementations for LLM and embedding operations.

This module provides a unified interface for AI providers that support both
language model chat operations and text embedding generation. It reduces
redundancy by consolidating common functionality while maintaining clean
separation between LLM and embedding capabilities.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class BaseAIProvider(ABC):
    """
    Base class for all AI provider implementations.

    This abstract class defines the common interface and shared functionality
    for providers that may support LLM operations, embedding operations, or both.

    Design Philosophy:
    - Single source of truth for provider availability
    - Shared client management and initialization
    - Common error handling patterns
    - Flexible support for providers with different capabilities
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
        pass

    def get_capabilities(self) -> Dict[str, bool]:
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

    Providers that support chat operations should inherit from this class
    and implement the chat() method.
    """

    def __init__(self):
        super().__init__()
        self._capabilities["chat"] = True

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Generate a chat completion using the provider's LLM.

        Args:
            messages: Conversation messages in OpenAI format
            **kwargs: Provider-specific parameters

        Returns:
            Dict containing the standardized response
        """
        pass


class EmbeddingProvider(BaseAIProvider):
    """
    Abstract base class for providers that support embedding generation.

    Providers that support embedding operations should inherit from this class
    and implement the embed() and get_model_info() methods.
    """

    def __init__(self):
        super().__init__()
        self._capabilities["embeddings"] = True

    @abstractmethod
    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            **kwargs: Provider-specific parameters

        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    def get_model_info(self, model: str) -> Dict[str, Any]:
        """
        Get information about a specific embedding model.

        Args:
            model: Model identifier

        Returns:
            Dict containing model information
        """
        pass


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
            import ollama

            # Check if Ollama is running
            ollama.list()
            self._available = True
        except Exception:
            self._available = False

        return self._available

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Generate a chat completion using Ollama.

        Args:
            messages: Conversation messages in OpenAI format.
            **kwargs: Additional arguments including:
                model (str): Ollama model name (default: "llama3.1:8b-instruct-q8_0")
                generation_config (dict): Generation parameters including:
                    * temperature, max_tokens, top_p, top_k, repeat_penalty
                    * seed, stop, num_ctx, num_batch, num_thread
                    * tfs_z, typical_p, mirostat, mirostat_tau, mirostat_eta

        Returns:
            Dict containing the standardized response.
        """
        try:
            import ollama

            model = kwargs.get("model", "llama3.1:8b-instruct-q8_0")
            generation_config = kwargs.get("generation_config", {})

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

            # Call Ollama
            response = ollama.chat(model=model, messages=messages, options=options)

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

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings using Ollama.

        Supported kwargs:
        - model (str): Ollama model name (default: "snowflake-arctic-embed2")
        - normalize (bool): Normalize embeddings to unit length
        """
        try:
            import ollama

            model = kwargs.get("model", "snowflake-arctic-embed2")
            normalize = kwargs.get("normalize", False)

            embeddings = []
            for text in texts:
                response = ollama.embeddings(model=model, prompt=text)
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

    def get_model_info(self, model: str) -> Dict[str, Any]:
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
    - gpt-4-turbo (latest GPT-4 Turbo)
    - gpt-4 (standard GPT-4)
    - gpt-4-32k (32k context window)
    - gpt-3.5-turbo (latest GPT-3.5)
    - gpt-3.5-turbo-16k (16k context window)

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

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        Generate a chat completion using OpenAI.

        Supported kwargs:
        - model (str): OpenAI model name (default: "gpt-4")
        - generation_config (dict): Generation parameters
        - tools (List[Dict]): Function/tool definitions for function calling
        """
        try:
            import openai

            model = kwargs.get("model", "gpt-4")
            generation_config = kwargs.get("generation_config", {})
            tools = kwargs.get("tools", [])

            # Initialize client if needed
            if self._client is None:
                self._client = openai.OpenAI()

            # Prepare request
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": generation_config.get("temperature", 0.7),
                "max_tokens": generation_config.get("max_tokens", 500),
                "top_p": generation_config.get("top_p", 0.9),
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
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {str(e)}")

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
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

    def get_model_info(self, model: str) -> Dict[str, Any]:
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

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
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
                    system_message = msg["content"]
                else:
                    user_messages.append(msg)

            # Call Anthropic
            response = self._client.messages.create(
                model=model,
                messages=user_messages,
                system=system_message,
                max_tokens=generation_config.get("max_tokens", 500),
                temperature=generation_config.get("temperature", 0.7),
                top_p=generation_config.get("top_p"),
                top_k=generation_config.get("top_k"),
                stop_sequences=generation_config.get("stop_sequences"),
                metadata=generation_config.get("metadata"),
            )

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

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
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

    def get_model_info(self, model: str) -> Dict[str, Any]:
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

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
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
        self, texts: List[str], model: str, normalize: bool
    ) -> List[List[float]]:
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
        self, texts: List[str], model: str, device: str, normalize: bool
    ) -> List[List[float]]:
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

    def get_model_info(self, model: str) -> Dict[str, Any]:
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

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Generate mock LLM response."""
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        # Generate contextual mock response
        if "analyze" in last_user_message.lower():
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
                "prompt_tokens": len(
                    " ".join(msg.get("content", "") for msg in messages)
                )
                // 4,
                "completion_tokens": len(response_content) // 4,
                "total_tokens": 0,  # Will be calculated
            },
            "metadata": {},
        }

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
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

    def get_model_info(self, model: str) -> Dict[str, Any]:
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
    provider_name: str, provider_type: Optional[str] = None
) -> Union[BaseAIProvider, LLMProvider, EmbeddingProvider]:
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

        Get any provider::

        provider = get_provider("openai")
        if provider.supports_chat():
            # Use for chat
        if provider.supports_embeddings():
            # Use for embeddings

        Get chat-only provider:

        chat_provider = get_provider("anthropic", "chat")
        response = chat_provider.chat(messages, model="claude-3-sonnet")

        Get embedding-only provider:

        embed_provider = get_provider("cohere", "embeddings")
        embeddings = embed_provider.embed(texts, model="embed-english-v3.0")

        Check provider capabilities:

        provider = get_provider("ollama")
        capabilities = provider.get_capabilities()
        print(f"Chat: {capabilities['chat']}, Embeddings: {capabilities['embeddings']}")
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
    provider_type: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Get information about all available providers.

    Args:
        provider_type (str, optional): Filter by capability - "chat", "embeddings", or None for all.

    Returns:
        Dict mapping provider names to their availability and capabilities.

    Examples:

        Get all providers::

        all_providers = get_available_providers()
        for name, info in all_providers.items():
            print(f"{name}: Available={info['available']}, Chat={info['chat']}, Embeddings={info['embeddings']}")

        Get only chat providers:

        chat_providers = get_available_providers("chat")

        Get only embedding providers:

        embed_providers = get_available_providers("embeddings")
    """
    results = {}

    for name in PROVIDERS:
        try:
            provider = get_provider(name)
            capabilities = provider.get_capabilities()

            # Apply filter if specified
            if provider_type == "chat" and not capabilities.get("chat"):
                continue
            elif provider_type == "embeddings" and not capabilities.get("embeddings"):
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

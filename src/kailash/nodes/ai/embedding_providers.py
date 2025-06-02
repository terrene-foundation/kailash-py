"""Embedding provider implementations for the EmbeddingGenerator node."""

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class EmbeddingProvider(ABC):
    """
    Base class for embedding provider implementations.

    This abstract class defines the interface that all embedding providers must implement.
    It enables the EmbeddingGenerator to work with different embedding services through
    a common interface.

    Design Philosophy:
    - Each provider manages its own dependencies and configuration
    - Providers should gracefully handle missing dependencies
    - All providers return embeddings in a standardized format
    - Provider-specific features are exposed through kwargs
    """

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the provider is available and properly configured.

        This method should verify:
        - Required dependencies are installed
        - API keys or credentials are configured
        - Services are accessible (for local services like Ollama)

        Returns:
            bool: True if the provider can be used, False otherwise

        Note:
            This method should not raise exceptions. It should return False
            for any configuration or dependency issues.
        """
        pass

    @abstractmethod
    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts (List[str]): List of texts to embed. Can be a single text.
            **kwargs: Provider-specific parameters that may include:
                model (str): Model identifier (provider-specific)
                dimensions (int): Desired embedding dimensions (if supported)
                normalize (bool): Whether to normalize embeddings
                truncate (bool): Whether to truncate long texts
                batch_size (int): Batch size for processing
                timeout (int): Request timeout in seconds

        Returns:
            List[List[float]]: List of embedding vectors, one per input text.
                Each embedding is a list of floats.

        Raises:
            RuntimeError: If the provider encounters an error

        Examples:
            See individual provider implementations for specific examples.
        """
        pass

    @abstractmethod
    def get_model_info(self, model: str) -> Dict[str, Any]:
        """
        Get information about a specific embedding model.

        Args:
            model (str): Model identifier

        Returns:
            Dict[str, Any]: Model information containing:
                dimensions (int): Embedding vector dimensions
                max_tokens (int): Maximum input tokens
                description (str): Model description
                capabilities (Dict): Model-specific capabilities

        Note:
            This method may return cached or estimated values
            if the provider doesn't expose this information.
        """
        pass


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Ollama provider implementation for local embedding models.

    Ollama runs embedding models locally on your machine. This provider
    interfaces with the Ollama service to generate embeddings.

    Prerequisites:
    - Install Ollama: https://ollama.ai
    - Pull an embedding model: `ollama pull snowflake-arctic-embed2`
    - Ensure Ollama service is running

    Supported models:
    - snowflake-arctic-embed2 (1024 dimensions)
    - avr/sfr-embedding-mistral (4096 dimensions)
    - nomic-embed-text (768 dimensions)
    - mxbai-embed-large (1024 dimensions)

    Examples:
        Basic usage:
        ```python
        provider = OllamaEmbeddingProvider()
        if provider.is_available():
            embeddings = provider.embed(
                ["Hello, world!", "How are you?"],
                model="snowflake-arctic-embed2"
            )
            print(f"Embedding shape: {len(embeddings)}x{len(embeddings[0])}")
        ```

        With normalization:
        ```python
        embeddings = provider.embed(
            ["Text to embed"],
            model="avr/sfr-embedding-mistral",
            normalize=True
        )
        ```
    """

    def __init__(self):
        self._client = None
        self._available = None
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

        # Known model dimensions
        known_models = {
            "snowflake-arctic-embed2": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "Snowflake's Arctic embedding model v2",
            },
            "avr/sfr-embedding-mistral": {
                "dimensions": 4096,
                "max_tokens": 512,
                "description": "SFR Mistral-based embedding model",
            },
            "nomic-embed-text": {
                "dimensions": 768,
                "max_tokens": 8192,
                "description": "Nomic's text embedding model",
            },
            "mxbai-embed-large": {
                "dimensions": 1024,
                "max_tokens": 512,
                "description": "MXBAI large embedding model",
            },
        }

        if model in known_models:
            info = known_models[model].copy()
            info["capabilities"] = {
                "batch_processing": True,
                "gpu_acceleration": True,
                "normalize": True,
            }
            self._model_cache[model] = info
            return info

        # Default for unknown models
        return {
            "dimensions": 1536,  # Common default
            "max_tokens": 512,
            "description": f"Ollama embedding model: {model}",
            "capabilities": {
                "batch_processing": True,
                "gpu_acceleration": True,
                "normalize": True,
            },
        }


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI provider implementation for embedding models.

    This provider interfaces with OpenAI's API to access text embedding models.

    Prerequisites:
    - Set OPENAI_API_KEY environment variable
    - Install openai package: `pip install openai`

    Supported models:
    - text-embedding-3-large (3072 dimensions, configurable)
    - text-embedding-3-small (1536 dimensions, configurable)
    - text-embedding-ada-002 (1536 dimensions, legacy)

    Examples:
        Basic usage:
        ```python
        provider = OpenAIEmbeddingProvider()
        if provider.is_available():
            embeddings = provider.embed(
                ["Hello, world!"],
                model="text-embedding-3-small"
            )
        ```

        With custom dimensions:
        ```python
        embeddings = provider.embed(
            ["Text to embed"],
            model="text-embedding-3-large",
            dimensions=1024  # Reduce from 3072 to 1024
        )
        ```

        Batch processing:
        ```python
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = provider.embed(
            texts,
            model="text-embedding-3-small",
            batch_size=100
        )
        ```
    """

    def __init__(self):
        self._client = None
        self._available = None

    def is_available(self) -> bool:
        """Check if OpenAI is available."""
        if self._available is not None:
            return self._available

        try:
            import os

            import openai

            # Check for API key
            self._available = bool(os.getenv("OPENAI_API_KEY"))
        except ImportError:
            self._available = False

        return self._available

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
                "description": f"OpenAI embedding model: {model}",
                "capabilities": {},
            },
        )


class CohereEmbeddingProvider(EmbeddingProvider):
    """
    Cohere provider implementation for embedding models.

    Prerequisites:
    - Set COHERE_API_KEY environment variable
    - Install cohere package: `pip install cohere`

    Supported models:
    - embed-english-v3.0 (1024 dimensions)
    - embed-multilingual-v3.0 (1024 dimensions)
    - embed-english-light-v3.0 (384 dimensions)
    - embed-multilingual-light-v3.0 (384 dimensions)

    Examples:
        Basic usage:
        ```python
        provider = CohereEmbeddingProvider()
        if provider.is_available():
            embeddings = provider.embed(
                ["Hello, world!"],
                model="embed-english-v3.0"
            )
        ```

        With input type specification:
        ```python
        embeddings = provider.embed(
            ["Search query"],
            model="embed-english-v3.0",
            input_type="search_query"  # or "search_document", "classification", "clustering"
        )
        ```
    """

    def __init__(self):
        self._client = None
        self._available = None

    def is_available(self) -> bool:
        """Check if Cohere is available."""
        if self._available is not None:
            return self._available

        try:
            import os

            import cohere

            # Check for API key
            self._available = bool(os.getenv("COHERE_API_KEY"))
        except ImportError:
            self._available = False

        return self._available

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings using Cohere.

        Supported kwargs:
        - model (str): Cohere model name (default: "embed-english-v3.0")
        - input_type (str): Type of input - "search_query", "search_document", "classification", "clustering"
        - truncate (str): How to handle long texts - "START", "END", "NONE"
        """
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


class HuggingFaceEmbeddingProvider(EmbeddingProvider):
    """
    HuggingFace provider implementation for embedding models.

    This provider can use both the HuggingFace Inference API and local models.

    Prerequisites for API:
    - Set HUGGINGFACE_API_KEY environment variable
    - Install requests: `pip install requests`

    Prerequisites for local:
    - Install transformers: `pip install transformers torch`

    Supported models:
    - sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
    - sentence-transformers/all-mpnet-base-v2 (768 dimensions)
    - BAAI/bge-large-en-v1.5 (1024 dimensions)
    - thenlper/gte-large (1024 dimensions)

    Examples:
        API usage:
        ```python
        provider = HuggingFaceEmbeddingProvider()
        if provider.is_available():
            embeddings = provider.embed(
                ["Hello, world!"],
                model="sentence-transformers/all-MiniLM-L6-v2",
                use_api=True
            )
        ```

        Local model:
        ```python
        embeddings = provider.embed(
            ["Text to embed"],
            model="sentence-transformers/all-mpnet-base-v2",
            use_api=False,
            device="cuda"  # or "cpu"
        )
        ```
    """

    def __init__(self):
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
            except:
                self._available_api = False

        # Check local availability
        if self._available_local is None:
            try:
                import torch
                import transformers

                self._available_local = True
            except ImportError:
                self._available_local = False

        return self._available_api or self._available_local

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate embeddings using HuggingFace.

        Supported kwargs:
        - model (str): Model name (default: "sentence-transformers/all-MiniLM-L6-v2")
        - use_api (bool): Use API instead of local model (default: True if API key available)
        - device (str): Device for local model - "cuda", "cpu" (default: "cpu")
        - normalize (bool): Normalize embeddings (default: True)
        """
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
                model_obj.eval()
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


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Mock provider for testing and development.

    This provider generates deterministic mock embeddings without making actual
    API calls. Useful for:
    - Testing workflows without API costs
    - Development when embedding services are unavailable
    - CI/CD pipelines
    - Demonstrating functionality

    Features:
    - Always available (no dependencies)
    - Generates consistent embeddings based on input hash
    - Simulates different model dimensions
    - Zero latency responses

    Examples:
        Basic usage:
        ```python
        provider = MockEmbeddingProvider()
        embeddings = provider.embed(
            ["Hello, world!"],
            model="mock-embedding-large"
        )
        ```

        Custom dimensions:
        ```python
        embeddings = provider.embed(
            ["Test text"],
            model="mock-custom",
            dimensions=2048
        )
        ```
    """

    def is_available(self) -> bool:
        """Mock provider is always available."""
        return True

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        Generate mock embeddings based on text content.

        Supported kwargs:
        - model (str): Mock model name (default: "mock-embedding")
        - dimensions (int): Embedding dimensions (default: 1536)
        - normalize (bool): Normalize embeddings (default: True)
        """
        model = kwargs.get("model", "mock-embedding")
        dimensions = kwargs.get("dimensions")
        normalize = kwargs.get("normalize", True)

        # Get dimensions from model or parameter
        if not dimensions:
            model_info = self.get_model_info(model)
            dimensions = model_info["dimensions"]

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
            "mock-embedding-small": {
                "dimensions": 384,
                "max_tokens": 512,
                "description": "Small mock embedding model",
            },
            "mock-embedding": {
                "dimensions": 1536,
                "max_tokens": 8192,
                "description": "Standard mock embedding model",
            },
            "mock-embedding-large": {
                "dimensions": 3072,
                "max_tokens": 8192,
                "description": "Large mock embedding model",
            },
        }

        return models.get(
            model,
            {
                "dimensions": 1536,
                "max_tokens": 8192,
                "description": f"Mock embedding model: {model}",
                "capabilities": {"variable_dimensions": True, "all_features": True},
            },
        )


# Provider registry
PROVIDERS = {
    "ollama": OllamaEmbeddingProvider,
    "openai": OpenAIEmbeddingProvider,
    "cohere": CohereEmbeddingProvider,
    "huggingface": HuggingFaceEmbeddingProvider,
    "mock": MockEmbeddingProvider,
}


def get_provider(provider_name: str) -> EmbeddingProvider:
    """
    Get an embedding provider instance by name.

    This factory function creates and returns the appropriate provider instance
    based on the provider name. It handles provider instantiation and provides
    helpful error messages for unknown providers.

    Args:
        provider_name (str): Name of the provider to instantiate.
            Valid options: "ollama", "openai", "cohere", "huggingface", "mock"
            Case-insensitive.

    Returns:
        EmbeddingProvider: An instance of the requested provider.

    Raises:
        ValueError: If the provider name is not recognized.

    Examples:
        Get Ollama provider:
        ```python
        ollama = get_provider("ollama")
        if ollama.is_available():
            embeddings = ollama.embed(
                ["Hello"],
                model="snowflake-arctic-embed2"
            )
        ```

        Get OpenAI provider:
        ```python
        try:
            openai = get_provider("openai")
            if openai.is_available():
                # Use the provider
                pass
            else:
                print("OpenAI not configured")
        except ValueError as e:
            print(f"Invalid provider: {e}")
        ```

        Check all available providers:
        ```python
        for name in ["ollama", "openai", "cohere", "huggingface", "mock"]:
            provider = get_provider(name)
            print(f"{name}: {'✓' if provider.is_available() else '✗'}")
        ```
    """
    provider_class = PROVIDERS.get(provider_name.lower())
    if not provider_class:
        raise ValueError(
            f"Unknown provider: {provider_name}. Available: {list(PROVIDERS.keys())}"
        )

    return provider_class()

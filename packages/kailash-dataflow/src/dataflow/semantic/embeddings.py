"""
Embedding providers for semantic search.

Supports multiple embedding models including OpenAI and Ollama.
"""

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import aiohttp
import numpy as np


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    embeddings: np.ndarray
    model: str
    dimension: int
    metadata: Dict[str, Any]


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, model_name: str, dimension: int, cache_ttl: int = 3600):
        """
        Initialize embedding provider.

        Args:
            model_name: Name of the embedding model
            dimension: Dimension of the embeddings
            cache_ttl: Cache time-to-live in seconds
        """
        self.model_name = model_name
        self.dimension = dimension
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[np.ndarray, datetime]] = {}

    @abstractmethod
    async def embed_text(self, text: Union[str, List[str]]) -> EmbeddingResult:
        """Generate embeddings for text."""
        pass

    @abstractmethod
    async def embed_batch(
        self, texts: List[str], batch_size: int = 100
    ) -> EmbeddingResult:
        """Generate embeddings for a batch of texts."""
        pass

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(f"{self.model_name}:{text}".encode()).hexdigest()

    def _get_from_cache(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache if available."""
        key = self._get_cache_key(text)
        if key in self._cache:
            embedding, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return embedding
            else:
                del self._cache[key]
        return None

    def _add_to_cache(self, text: str, embedding: np.ndarray):
        """Add embedding to cache."""
        key = self._get_cache_key(text)
        self._cache[key] = (embedding, datetime.now())

    async def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        dimension: int = 1536,
        **kwargs,
    ):
        """
        Initialize OpenAI embeddings.

        Args:
            api_key: OpenAI API key
            model_name: Model name (text-embedding-3-small, text-embedding-3-large)
            dimension: Embedding dimension
        """
        super().__init__(model_name, dimension, **kwargs)
        self.api_key = api_key
        self.api_url = "https://api.openai.com/v1/embeddings"

    async def embed_text(self, text: Union[str, List[str]]) -> EmbeddingResult:
        """Generate embeddings using OpenAI API."""
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text

        # Check cache for single text
        if len(texts) == 1:
            cached = self._get_from_cache(texts[0])
            if cached is not None:
                return EmbeddingResult(
                    embeddings=cached.reshape(1, -1),
                    model=self.model_name,
                    dimension=self.dimension,
                    metadata={"cached": True},
                )

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            data = {
                "model": self.model_name,
                "input": texts,
                "dimensions": self.dimension,
            }

            async with session.post(
                self.api_url, headers=headers, json=data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"OpenAI API error: {error_text}")

                result = await response.json()
                embeddings = np.array([item["embedding"] for item in result["data"]])

                # Cache single embeddings
                if len(texts) == 1:
                    self._add_to_cache(texts[0], embeddings[0])

                return EmbeddingResult(
                    embeddings=embeddings,
                    model=self.model_name,
                    dimension=self.dimension,
                    metadata={"usage": result.get("usage", {}), "cached": False},
                )

    async def embed_batch(
        self, texts: List[str], batch_size: int = 100
    ) -> EmbeddingResult:
        """Embed texts in batches."""
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = await self.embed_text(batch)
            all_embeddings.append(result.embeddings)

        combined_embeddings = np.vstack(all_embeddings)

        return EmbeddingResult(
            embeddings=combined_embeddings,
            model=self.model_name,
            dimension=self.dimension,
            metadata={"batch_count": len(all_embeddings)},
        )


class OllamaEmbeddings(EmbeddingProvider):
    """Ollama embedding provider for local models."""

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        dimension: int = 768,
        host: str = "http://localhost:11434",
        **kwargs,
    ):
        """
        Initialize Ollama embeddings.

        Args:
            model_name: Ollama model name
            dimension: Embedding dimension
            host: Ollama server host
        """
        super().__init__(model_name, dimension, **kwargs)
        self.host = host
        self.embed_url = f"{host}/api/embeddings"

    async def embed_text(self, text: Union[str, List[str]]) -> EmbeddingResult:
        """Generate embeddings using Ollama."""
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text

        all_embeddings = []

        async with aiohttp.ClientSession() as session:
            for txt in texts:
                # Check cache
                cached = self._get_from_cache(txt)
                if cached is not None:
                    all_embeddings.append(cached)
                    continue

                data = {"model": self.model_name, "prompt": txt}

                async with session.post(self.embed_url, json=data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ValueError(f"Ollama API error: {error_text}")

                    result = await response.json()
                    embedding = np.array(result["embedding"])
                    all_embeddings.append(embedding)

                    # Cache the embedding
                    self._add_to_cache(txt, embedding)

        embeddings_array = np.vstack(all_embeddings)

        return EmbeddingResult(
            embeddings=embeddings_array,
            model=self.model_name,
            dimension=self.dimension,
            metadata={"host": self.host},
        )

    async def embed_batch(
        self, texts: List[str], batch_size: int = 100
    ) -> EmbeddingResult:
        """Embed texts in batches."""
        # Ollama doesn't support batch embedding, so we process sequentially
        # but with concurrent requests up to batch_size
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            tasks = [self.embed_text(text) for text in batch]
            results = await asyncio.gather(*tasks)

            for result in results:
                all_embeddings.append(result.embeddings[0])

        combined_embeddings = np.vstack(all_embeddings)

        return EmbeddingResult(
            embeddings=combined_embeddings,
            model=self.model_name,
            dimension=self.dimension,
            metadata={"batch_count": len(texts) // batch_size + 1},
        )

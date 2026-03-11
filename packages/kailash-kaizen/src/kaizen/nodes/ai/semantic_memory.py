"""
Semantic memory nodes for A2A enhancement.

These nodes add embeddings and vector search capabilities to the A2A system,
allowing for semantic matching and contextual agent selection.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

import aiohttp
import numpy as np

from kailash.nodes.base import Node, NodeParameter, register_node


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    embeddings: np.ndarray
    model: str
    dimension: int
    metadata: Dict[str, Any]


@dataclass
class SemanticMemoryItem:
    """An item stored in semantic memory."""

    id: str
    content: str
    embedding: np.ndarray
    metadata: Dict[str, Any]
    created_at: datetime
    collection: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding.tolist(),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "collection": self.collection,
        }


class SimpleEmbeddingProvider:
    """Simple embedding provider using Ollama by default."""

    def __init__(
        self, model_name: str = "nomic-embed-text", host: str = "http://localhost:11434"
    ):
        self.model_name = model_name
        self.host = host
        self.embed_url = f"{host}/api/embeddings"
        self._cache = {}

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(f"{self.model_name}:{text}".encode()).hexdigest()

    async def embed_text(self, text: Union[str, List[str]]) -> EmbeddingResult:
        """Generate embeddings for text."""
        if isinstance(text, str):
            texts = [text]
        else:
            texts = text

        all_embeddings = []

        async with aiohttp.ClientSession() as session:
            for txt in texts:
                # Check cache
                cache_key = self._get_cache_key(txt)
                if cache_key in self._cache:
                    all_embeddings.append(self._cache[cache_key])
                    continue

                data = {"model": self.model_name, "prompt": txt}

                try:
                    async with session.post(self.embed_url, json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            embedding = np.array(result["embedding"])
                            all_embeddings.append(embedding)

                            # Cache the embedding
                            self._cache[cache_key] = embedding
                        else:
                            # Fallback to simple hash-based embedding
                            embedding = self._hash_embedding(txt)
                            all_embeddings.append(embedding)
                except Exception:
                    # Fallback to simple hash-based embedding
                    embedding = self._hash_embedding(txt)
                    all_embeddings.append(embedding)

        embeddings_array = np.vstack(all_embeddings)

        return EmbeddingResult(
            embeddings=embeddings_array,
            model=self.model_name,
            dimension=embeddings_array.shape[1],
            metadata={"host": self.host},
        )

    def _hash_embedding(self, text: str, dimension: int = 384) -> np.ndarray:
        """Create a simple hash-based embedding as fallback."""
        # Simple deterministic embedding based on text content
        hash_str = hashlib.md5(text.encode()).hexdigest()
        # Convert hex to numbers and normalize
        values = [
            int(hash_str[i : i + 2], 16) / 255.0
            for i in range(0, min(len(hash_str), dimension * 2), 2)
        ]
        # Pad or truncate to desired dimension
        while len(values) < dimension:
            values.extend(values[: dimension - len(values)])
        return np.array(values[:dimension])


class InMemoryVectorStore:
    """Simple in-memory vector store for development."""

    def __init__(self):
        self.items: Dict[str, SemanticMemoryItem] = {}
        self.collections: Dict[str, List[str]] = {}

    async def add(self, item: SemanticMemoryItem) -> str:
        """Add item to store."""
        self.items[item.id] = item

        # Add to collection index
        if item.collection not in self.collections:
            self.collections[item.collection] = []
        self.collections[item.collection].append(item.id)

        return item.id

    async def search_similar(
        self,
        embedding: np.ndarray,
        collection: Optional[str] = None,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> List[Tuple[SemanticMemoryItem, float]]:
        """Search for similar items."""
        results = []

        # Filter by collection if specified
        if collection:
            item_ids = self.collections.get(collection, [])
        else:
            item_ids = list(self.items.keys())

        # Calculate similarities
        for item_id in item_ids:
            item = self.items[item_id]

            # Cosine similarity
            similarity = np.dot(embedding, item.embedding) / (
                np.linalg.norm(embedding) * np.linalg.norm(item.embedding)
            )

            if similarity >= threshold:
                results.append((item, similarity))

        # Sort by similarity and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def get_collections(self) -> List[str]:
        """Get all collection names."""
        return list(self.collections.keys())


@register_node()
class SemanticMemoryStoreNode(Node):
    """Store content in semantic memory with embeddings."""

    def __init__(self, name: str = "semantic_memory_store", **kwargs):
        """Initialize semantic memory store node."""
        self.content = None
        self.metadata = None
        self.collection = "default"
        self.embedding_model = "nomic-embed-text"
        self.embedding_host = "http://localhost:11434"

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Shared store and provider (in production, use persistent storage)
        if not hasattr(self.__class__, "_store"):
            self.__class__._store = InMemoryVectorStore()
        if not hasattr(self.__class__, "_provider"):
            self.__class__._provider = SimpleEmbeddingProvider(
                model_name=self.embedding_model, host=self.embedding_host
            )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "content": NodeParameter(
                name="content",
                type=str,
                required=True,
                description="Content to store (string or list of strings)",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                description="Metadata to attach",
            ),
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=False,
                default="default",
                description="Collection name",
            ),
            "embedding_model": NodeParameter(
                name="embedding_model",
                type=str,
                required=False,
                default="nomic-embed-text",
                description="Embedding model name",
            ),
            "embedding_host": NodeParameter(
                name="embedding_host",
                type=str,
                required=False,
                default="http://localhost:11434",
                description="Embedding service host",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Store content in semantic memory."""
        # Get parameters
        content = kwargs.get("content", self.content)
        metadata = kwargs.get("metadata", self.metadata) or {}
        collection = kwargs.get("collection", self.collection)

        if not content:
            raise ValueError("Content is required")

        # Handle single or multiple content
        if isinstance(content, str):
            contents = [content]
        else:
            contents = content

        # Generate embeddings
        result = await self._provider.embed_text(contents)

        # Store items
        ids = []
        now = datetime.now(UTC)

        for i, (text, embedding) in enumerate(zip(contents, result.embeddings)):
            item = SemanticMemoryItem(
                id=str(uuid4()),
                content=text,
                embedding=embedding,
                metadata=metadata,
                created_at=now,
                collection=collection,
            )

            item_id = await self._store.add(item)
            ids.append(item_id)

        return {
            "success": True,
            "ids": ids,
            "count": len(ids),
            "collection": collection,
            "embedding_model": result.model,
        }


@register_node()
class SemanticMemorySearchNode(Node):
    """Search semantic memory for similar content."""

    def __init__(self, name: str = "semantic_memory_search", **kwargs):
        """Initialize semantic memory search node."""
        self.query = None
        self.limit = 10
        self.threshold = 0.5
        self.collection = None
        self.embedding_model = "nomic-embed-text"
        self.embedding_host = "http://localhost:11434"

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Use shared store and provider
        if not hasattr(self.__class__, "_store"):
            self.__class__._store = InMemoryVectorStore()
        if not hasattr(self.__class__, "_provider"):
            self.__class__._provider = SimpleEmbeddingProvider(
                model_name=self.embedding_model, host=self.embedding_host
            )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "query": NodeParameter(
                name="query", type=str, required=True, description="Search query"
            ),
            "limit": NodeParameter(
                name="limit",
                type=int,
                required=False,
                default=10,
                description="Maximum number of results",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.5,
                description="Minimum similarity threshold",
            ),
            "collection": NodeParameter(
                name="collection",
                type=str,
                required=False,
                description="Collection to search",
            ),
            "embedding_model": NodeParameter(
                name="embedding_model",
                type=str,
                required=False,
                default="nomic-embed-text",
                description="Embedding model name",
            ),
            "embedding_host": NodeParameter(
                name="embedding_host",
                type=str,
                required=False,
                default="http://localhost:11434",
                description="Embedding service host",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Search semantic memory."""
        # Get parameters
        query = kwargs.get("query", self.query)
        limit = kwargs.get("limit", self.limit)
        threshold = kwargs.get("threshold", self.threshold)
        collection = kwargs.get("collection", self.collection)

        if not query:
            raise ValueError("Query is required")

        # Generate query embedding
        result = await self._provider.embed_text(query)
        query_embedding = result.embeddings[0]

        # Search store
        results = await self._store.search_similar(
            embedding=query_embedding,
            collection=collection,
            limit=limit,
            threshold=threshold,
        )

        # Format results
        formatted_results = []
        for item, similarity in results:
            formatted_results.append(
                {
                    "id": item.id,
                    "content": item.content,
                    "similarity": similarity,
                    "metadata": item.metadata,
                    "collection": item.collection,
                }
            )

        return {
            "success": True,
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
            "embedding_model": result.model,
        }


@register_node()
class SemanticAgentMatchingNode(Node):
    """Enhanced agent matching using semantic similarity."""

    def __init__(self, name: str = "semantic_agent_matching", **kwargs):
        """Initialize semantic agent matching node."""
        self.requirements = None
        self.agents = None
        self.limit = 5
        self.threshold = 0.3
        self.weight_semantic = 0.6
        self.weight_keyword = 0.4

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Use shared store and provider
        if not hasattr(self.__class__, "_store"):
            self.__class__._store = InMemoryVectorStore()
        if not hasattr(self.__class__, "_provider"):
            self.__class__._provider = SimpleEmbeddingProvider()

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "requirements": NodeParameter(
                name="requirements",
                type=str,
                required=True,
                description="Task requirements (string or list)",
            ),
            "agents": NodeParameter(
                name="agents",
                type=list,
                required=True,
                description="List of agent descriptions",
            ),
            "limit": NodeParameter(
                name="limit",
                type=int,
                required=False,
                default=5,
                description="Maximum matches to return",
            ),
            "threshold": NodeParameter(
                name="threshold",
                type=float,
                required=False,
                default=0.3,
                description="Minimum similarity threshold",
            ),
            "weight_semantic": NodeParameter(
                name="weight_semantic",
                type=float,
                required=False,
                default=0.6,
                description="Weight for semantic similarity",
            ),
            "weight_keyword": NodeParameter(
                name="weight_keyword",
                type=float,
                required=False,
                default=0.4,
                description="Weight for keyword matching",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Perform semantic agent matching."""
        # Get parameters
        requirements = kwargs.get("requirements", self.requirements)
        agents = kwargs.get("agents", self.agents)
        limit = kwargs.get("limit", self.limit)
        threshold = kwargs.get("threshold", self.threshold)
        weight_semantic = kwargs.get("weight_semantic", self.weight_semantic)
        weight_keyword = kwargs.get("weight_keyword", self.weight_keyword)

        if not requirements or not agents:
            raise ValueError("Requirements and agents are required")

        # Convert requirements to text
        if isinstance(requirements, list):
            req_text = " ".join(str(req) for req in requirements)
        else:
            req_text = str(requirements)

        # Generate embeddings for requirements and agents
        all_texts = [req_text] + [str(agent) for agent in agents]
        result = await self._provider.embed_text(all_texts)

        req_embedding = result.embeddings[0]
        agent_embeddings = result.embeddings[1:]

        # Calculate similarities
        matches = []
        for i, (agent, agent_embedding) in enumerate(zip(agents, agent_embeddings)):
            # Semantic similarity
            semantic_sim = np.dot(req_embedding, agent_embedding) / (
                np.linalg.norm(req_embedding) * np.linalg.norm(agent_embedding)
            )

            # Keyword similarity (simple approach)
            keyword_sim = self._calculate_keyword_similarity(req_text, str(agent))

            # Combined score
            combined_score = (
                semantic_sim * weight_semantic + keyword_sim * weight_keyword
            )

            if combined_score >= threshold:
                matches.append(
                    {
                        "agent": agent,
                        "agent_index": i,
                        "semantic_similarity": semantic_sim,
                        "keyword_similarity": keyword_sim,
                        "combined_score": combined_score,
                    }
                )

        # Sort by combined score
        matches.sort(key=lambda x: x["combined_score"], reverse=True)

        return {
            "success": True,
            "requirements": req_text,
            "matches": matches[:limit],
            "count": len(matches),
            "embedding_model": result.model,
        }

    def _calculate_keyword_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple keyword similarity."""
        # Simple word overlap similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

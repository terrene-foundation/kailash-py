"""
Semantic memory implementation.

Embedding-based memory for concept recall and semantic similarity.
Best for: concept understanding, semantic search, knowledge graphs.
"""

from typing import Callable, Dict, List, Optional

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend


class SemanticMemory:
    """
    Semantic memory with embedding-based similarity search.

    Features:
    - Embedding-based storage for semantic similarity
    - Concept extraction and clustering
    - Similarity search using cosine distance
    - Optional integration with embedding providers

    Use cases:
    - Concept and fact recall
    - Semantic search over knowledge
    - Finding related memories
    - Knowledge graph construction

    Performance:
    - Retrieval: O(n) for similarity search (can be optimized with vector DB)
    - Storage: O(1) with embedding generation
    - Search: O(n) linear scan (optimizable with FAISS/Annoy)
    """

    def __init__(
        self,
        storage: StorageBackend,
        embedding_function: Optional[Callable[[str], List[float]]] = None,
        similarity_threshold: float = 0.7,  # Minimum similarity for matches
        max_entries: int = 50000,
    ):
        """
        Initialize semantic memory.

        Args:
            storage: Storage backend for persistence
            embedding_function: Function to generate embeddings (text -> vector)
            similarity_threshold: Minimum similarity score (0.0-1.0)
            max_entries: Maximum entries to keep
        """
        self.storage = storage
        self.embedding_function = embedding_function
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries

    def store(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        importance: float = 0.6,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """
        Store content in semantic memory.

        Args:
            content: Content to store
            metadata: Optional metadata
            importance: Initial importance score (default: 0.6)
            embedding: Pre-computed embedding (optional)

        Returns:
            Entry ID
        """
        # Generate embedding if not provided and function available
        if embedding is None and self.embedding_function is not None:
            embedding = self.embedding_function(content)

        # Create entry with semantic type
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.SEMANTIC,
            metadata=metadata or {},
            importance=importance,
            embedding=embedding,
        )

        # Store and return ID
        return self.storage.store(entry)

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve entry by ID.

        Args:
            entry_id: Entry ID to retrieve

        Returns:
            Memory entry or None if not found
        """
        return self.storage.retrieve(entry_id)

    def find_similar(
        self,
        query: str,
        limit: int = 5,
        min_similarity: Optional[float] = None,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict]:
        """
        Find semantically similar memories.

        Uses cosine similarity between embeddings.

        Args:
            query: Query text
            limit: Maximum results to return
            min_similarity: Minimum similarity threshold (default: self.similarity_threshold)
            query_embedding: Pre-computed query embedding (optional)

        Returns:
            List of dicts with 'entry' and 'similarity' keys, sorted by similarity
        """
        threshold = (
            min_similarity if min_similarity is not None else self.similarity_threshold
        )

        # Generate query embedding if not provided
        if query_embedding is None:
            if self.embedding_function is None:
                # Fallback to keyword search if no embedding function
                results = self.storage.search(
                    query, memory_type=MemoryType.SEMANTIC, limit=limit
                )
                return [{"entry": entry, "similarity": 0.5} for entry in results]

            query_embedding = self.embedding_function(query)

        # Get all semantic entries with embeddings
        entries = self.storage.list_entries(
            memory_type=MemoryType.SEMANTIC, limit=self.max_entries
        )
        entries_with_embeddings = [e for e in entries if e.embedding is not None]

        # Calculate similarities
        similarities = []
        for entry in entries_with_embeddings:
            similarity = self._cosine_similarity(query_embedding, entry.embedding)
            if similarity >= threshold:
                similarities.append({"entry": entry, "similarity": similarity})

        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x["similarity"], reverse=True)

        return similarities[:limit]

    def find_related(self, entry_id: str, limit: int = 5) -> List[Dict]:
        """
        Find memories related to a specific entry.

        Args:
            entry_id: Entry ID to find related memories for
            limit: Maximum results to return

        Returns:
            List of dicts with 'entry' and 'similarity' keys
        """
        # Get the source entry
        source = self.storage.retrieve(entry_id)
        if source is None or source.embedding is None:
            return []

        # Find similar entries (excluding the source)
        results = self.find_similar(
            query=source.content, limit=limit + 1, query_embedding=source.embedding
        )

        # Filter out the source entry
        return [r for r in results if r["entry"].id != entry_id][:limit]

    def search(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """
        Search for memories by keyword (fallback when no embeddings).

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching entries
        """
        return self.storage.search(query, memory_type=MemoryType.SEMANTIC, limit=limit)

    def get_concepts(self, limit: int = 100) -> List[MemoryEntry]:
        """
        Get stored semantic concepts.

        Args:
            limit: Maximum concepts to return

        Returns:
            List of semantic memory entries
        """
        return self.storage.list_entries(memory_type=MemoryType.SEMANTIC, limit=limit)

    def clear(self) -> int:
        """
        Clear all semantic memories.

        Returns:
            Number of entries cleared
        """
        return self.storage.clear(memory_type=MemoryType.SEMANTIC)

    def get_stats(self) -> Dict:
        """
        Get memory statistics.

        Returns:
            Dictionary with stats
        """
        entries = self.storage.list_entries(
            memory_type=MemoryType.SEMANTIC, limit=self.max_entries
        )

        with_embeddings = sum(1 for e in entries if e.embedding is not None)
        without_embeddings = len(entries) - with_embeddings

        return {
            "total_entries": len(entries),
            "with_embeddings": with_embeddings,
            "without_embeddings": without_embeddings,
            "embedding_coverage": with_embeddings / len(entries) if entries else 0.0,
            "similarity_threshold": self.similarity_threshold,
            "has_embedding_function": self.embedding_function is not None,
        }

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score (0.0-1.0)
        """
        if len(vec1) != len(vec2):
            return 0.0

        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Magnitudes
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        # Cosine similarity
        similarity = dot_product / (magnitude1 * magnitude2)

        # Normalize to 0-1 range
        return (similarity + 1) / 2

"""
VectorMemory: Semantic search over conversation history.

This memory implementation uses vector embeddings to enable semantic search
over conversation history, retrieving the most relevant past turns based on
similarity to the current query.

``embedding_fn`` is REQUIRED. It previously defaulted to a hash-based
pseudo-embedder, so a caller who omitted it got vectors of the right shape
carrying no semantic signal — every similarity search still returned ranked
results, but the ranking was over MD5 noise (#2174, ``zero-tolerance.md``
Rule 2). Nothing raised and nothing warned, which is why it survived.

Example:
    >>> from kaizen.memory.vector import VectorMemory
    >>> memory = VectorMemory(top_k=3, embedding_fn=my_embedder)
    >>> memory.save_turn("session1", {"user": "Python programming", "agent": "Great!"})
    >>> memory.save_turn("session1", {"user": "What's for dinner?", "agent": "Pizza"})
    >>> context = memory.load_context("session1", query="coding in Python")
    >>> print(len(context["relevant_turns"]))  # Returns programming-related turn
    1

Note: This is a Kaizen-owned implementation, inspired by LangChain's
VectorStoreRetrieverMemory but NOT integrated with LangChain.
"""

import hashlib
from typing import Any, Callable, Dict, List, Optional

from kaizen.config.providers import ConfigurationError
from kaizen.memory.conversation_base import KaizenMemory


def hash_embedder_for_tests(text: str, dimensions: int = 128) -> List[float]:
    """NOT AN EMBEDDER. A deterministic hash-derived vector, for tests only.

    Produces a stable vector of the right shape so storage/retrieval mechanics
    can be exercised without an embedding service. It carries NO semantic
    signal whatsoever: nearest-neighbour over these vectors is nearest-
    neighbour over MD5 noise, so any test asserting on the QUALITY of a
    ranking is meaningless with this function.

    It is deliberately module-level and explicitly named rather than a default
    on ``VectorMemory``. As ``VectorMemory._default_embedder`` it silently
    served every caller who omitted ``embedding_fn`` (#2174); the name has to
    make its status unmistakable at the call site.
    """
    hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [float((hash_val >> i) & 1) for i in range(dimensions)]


class VectorMemory(KaizenMemory):
    """
    Semantic search over conversation history using vector embeddings.

    Stores conversation turns as vector embeddings and performs semantic
    similarity search to retrieve relevant past conversations.

    Attributes:
        top_k: Maximum number of relevant turns to return (default: 5)
        embedding_fn: Function to generate embeddings from text
        _stores: Internal storage mapping session_id -> turn data
    """

    def __init__(
        self,
        top_k: int = 5,
        embedding_fn: Optional[Callable[[str], List[float]]] = None,
    ):
        """
        Initialize VectorMemory.

        Args:
            top_k: Maximum number of relevant turns to return in search (default: 5)
            embedding_fn: REQUIRED. Embedding function taking text and returning
                         a vector (list of floats).

        Raises:
            ConfigurationError: if ``embedding_fn`` is not supplied.
        """
        if embedding_fn is None:
            raise ConfigurationError(
                "VectorMemory: 'embedding_fn' is required. It no longer "
                "defaults to a hash-based pseudo-embedder, which returned "
                "vectors of the correct shape carrying no semantic signal — "
                "similarity search kept returning ranked results, but the "
                "ranking was over MD5 noise, with nothing raised and nothing "
                "logged (#2174). Pass a real embedding function (OpenAI, "
                "sentence-transformers, HuggingFace, ...), or for tests pass "
                "kaizen.memory.vector.hash_embedder_for_tests explicitly."
            )
        self.top_k = top_k
        self.embedding_fn = embedding_fn
        self._stores: Dict[str, Dict[str, Any]] = {}

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score (0-1, higher is more similar)
        """
        if len(vec1) != len(vec2):
            return 0.0

        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Magnitudes
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def load_context(
        self, session_id: str, query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Load conversation context for a specific session.

        If query is provided, performs semantic search to find relevant turns.
        Otherwise, returns all turns without ranking.

        Args:
            session_id: Unique identifier for the conversation session
            query: Optional search query for semantic similarity

        Returns:
            Dictionary with:
                - "relevant_turns": Turns most similar to query (if query provided)
                - "all_turns": All conversation turns for the session
        """
        if session_id not in self._stores:
            return {"relevant_turns": [], "all_turns": []}

        store = self._stores[session_id]
        all_turns = store.get("turns", [])

        # If no query or empty query, return all turns without search
        if not query:
            return {"relevant_turns": [], "all_turns": all_turns}

        # Perform semantic search
        query_embedding = self.embedding_fn(query)
        embeddings = store.get("embeddings", [])

        # Calculate similarities
        similarities = []
        for idx, embedding in enumerate(embeddings):
            similarity = self._cosine_similarity(query_embedding, embedding)
            similarities.append((idx, similarity))

        # Sort by similarity (descending) and take top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in similarities[: self.top_k]]

        # Retrieve relevant turns
        relevant_turns = [all_turns[idx] for idx in top_indices if idx < len(all_turns)]

        return {"relevant_turns": relevant_turns, "all_turns": all_turns}

    def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """
        Save a conversation turn and generate its embedding.

        Args:
            session_id: Unique identifier for the conversation session
            turn: Dictionary containing conversation turn data
        """
        # Initialize session if it doesn't exist
        if session_id not in self._stores:
            self._stores[session_id] = {"turns": [], "embeddings": []}

        # Generate embedding for the turn
        # Combine user and agent messages for embedding
        turn_text = f"{turn.get('user', '')} {turn.get('agent', '')}"
        embedding = self.embedding_fn(turn_text)

        # Store turn and embedding
        self._stores[session_id]["turns"].append(turn)
        self._stores[session_id]["embeddings"].append(embedding)

    def clear(self, session_id: str) -> None:
        """
        Clear all conversation history and embeddings for a specific session.

        Args:
            session_id: Unique identifier for the conversation session
        """
        if session_id in self._stores:
            del self._stores[session_id]

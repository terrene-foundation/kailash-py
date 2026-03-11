"""
Unit tests for SemanticMemory.

Tests embedding-based similarity search and concept recall.
"""

import tempfile
from pathlib import Path
from typing import List

import pytest
from kaizen.memory.semantic import SemanticMemory
from kaizen.memory.storage.sqlite_storage import SQLiteStorage


def simple_embedding_function(text: str) -> List[float]:
    """
    Simple mock embedding function for testing.

    Generates deterministic embeddings based on text content.
    """
    # Simple hash-based embedding (for testing only)
    words = text.lower().split()

    # Create 10-dimensional vector
    vector = [0.0] * 10

    for i, word in enumerate(words[:10]):
        # Use word hash to generate dimension values
        hash_val = hash(word)
        vector[i] = (hash_val % 100) / 100.0  # Normalize to 0-1

    return vector


@pytest.fixture
def temp_storage():
    """Create temporary SQLiteStorage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "test_semantic.db"
        yield SQLiteStorage(str(storage_path))


@pytest.fixture
def semantic_memory(temp_storage):
    """Create SemanticMemory instance with mock embedding function."""
    return SemanticMemory(
        storage=temp_storage,
        embedding_function=simple_embedding_function,
        similarity_threshold=0.5,
        max_entries=1000,
    )


@pytest.fixture
def semantic_memory_no_embeddings(temp_storage):
    """Create SemanticMemory without embedding function."""
    return SemanticMemory(
        storage=temp_storage, embedding_function=None, similarity_threshold=0.5
    )


class TestSemanticMemoryBasics:
    """Test basic CRUD operations."""

    def test_store_entry(self, semantic_memory):
        """Test storing a semantic memory."""
        entry_id = semantic_memory.store("Python is a programming language")
        assert entry_id is not None

    def test_store_generates_embedding(self, semantic_memory):
        """Test that embeddings are generated automatically."""
        entry_id = semantic_memory.store("Test content")
        entry = semantic_memory.retrieve(entry_id)

        assert entry is not None
        assert entry.embedding is not None
        assert len(entry.embedding) == 10  # Our mock function generates 10D vectors

    def test_store_with_custom_embedding(self, semantic_memory):
        """Test storing with custom embedding."""
        custom_embedding = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        entry_id = semantic_memory.store("Test", embedding=custom_embedding)
        entry = semantic_memory.retrieve(entry_id)

        assert entry.embedding == custom_embedding

    def test_store_without_embedding_function(self, semantic_memory_no_embeddings):
        """Test storing without embedding function."""
        entry_id = semantic_memory_no_embeddings.store("Test content")
        entry = semantic_memory_no_embeddings.retrieve(entry_id)

        assert entry is not None
        assert entry.embedding is None


class TestSemanticMemorySimilaritySearch:
    """Test similarity-based search."""

    def test_find_similar_basic(self, semantic_memory):
        """Test finding similar memories."""
        # Store some entries
        semantic_memory.store("Python programming language")
        semantic_memory.store("JavaScript coding framework")
        semantic_memory.store("Python Django web development")

        # Find similar to Python-related query
        results = semantic_memory.find_similar("Python", limit=5)

        # Should find Python-related entries
        assert len(results) > 0
        assert all("entry" in r and "similarity" in r for r in results)

        # Results should be sorted by similarity
        similarities = [r["similarity"] for r in results]
        assert similarities == sorted(similarities, reverse=True)

    def test_find_similar_respects_threshold(self, semantic_memory):
        """Test that similarity threshold is respected."""
        semantic_memory.store("Very similar content")
        semantic_memory.store("Completely different topic about elephants")

        # Find similar with high threshold
        results = semantic_memory.find_similar(
            "Very similar content", min_similarity=0.8, limit=10
        )

        # All results should meet threshold
        assert all(r["similarity"] >= 0.8 for r in results)

    def test_find_similar_with_custom_embedding(self, semantic_memory):
        """Test finding similar with custom query embedding."""
        # Store entry with known embedding
        embedding1 = [1.0] * 10
        semantic_memory.store("Entry 1", embedding=embedding1)

        # Search with identical embedding (should be 100% similar)
        results = semantic_memory.find_similar(
            query="dummy", query_embedding=[1.0] * 10, min_similarity=0.99
        )

        assert len(results) >= 1
        assert results[0]["similarity"] >= 0.99

    def test_find_similar_without_embedding_function(
        self, semantic_memory_no_embeddings
    ):
        """Test that find_similar falls back to keyword search."""
        semantic_memory_no_embeddings.store("Python programming")
        semantic_memory_no_embeddings.store("JavaScript coding")

        # Should fall back to keyword search
        results = semantic_memory_no_embeddings.find_similar("Python", limit=5)

        assert len(results) > 0
        assert results[0]["entry"].content == "Python programming"

    def test_find_similar_limit(self, semantic_memory):
        """Test that limit is respected."""
        # Store many entries
        for i in range(10):
            semantic_memory.store(f"Python entry {i}")

        results = semantic_memory.find_similar("Python", limit=3)
        assert len(results) == 3


class TestSemanticMemoryRelatedSearch:
    """Test finding related memories."""

    def test_find_related_basic(self, semantic_memory):
        """Test finding memories related to a specific entry."""
        # Store related entries
        id1 = semantic_memory.store("Python web development")
        semantic_memory.store("Python Django framework")
        semantic_memory.store("Python Flask API")
        semantic_memory.store("JavaScript React frontend")

        # Find related to first entry
        results = semantic_memory.find_related(id1, limit=3)

        # Should find related Python entries (excluding source)
        assert len(results) > 0
        assert all(r["entry"].id != id1 for r in results)  # Excludes source

    def test_find_related_nonexistent(self, semantic_memory):
        """Test finding related for nonexistent entry."""
        results = semantic_memory.find_related("nonexistent-id", limit=5)
        assert len(results) == 0

    def test_find_related_no_embedding(self, semantic_memory):
        """Test finding related when entry has no embedding."""
        # Store entry without embedding
        entry_id = semantic_memory.store("Test", embedding=None)

        results = semantic_memory.find_related(entry_id, limit=5)
        assert len(results) == 0


class TestSemanticMemoryKeywordSearch:
    """Test keyword-based search."""

    def test_search_basic(self, semantic_memory):
        """Test keyword search."""
        semantic_memory.store("Python is great")
        semantic_memory.store("JavaScript is good")
        semantic_memory.store("Python Django")

        results = semantic_memory.search("Python")
        assert len(results) == 2

    def test_get_concepts_basic(self, semantic_memory):
        """Test getting stored concepts."""
        # Store several concepts
        for i in range(5):
            semantic_memory.store(f"Concept {i}")

        concepts = semantic_memory.get_concepts(limit=10)
        assert len(concepts) == 5


class TestSemanticMemoryClear:
    """Test clear operations."""

    def test_clear_all(self, semantic_memory):
        """Test clearing all semantic memories."""
        for i in range(5):
            semantic_memory.store(f"Entry {i}")

        cleared = semantic_memory.clear()
        assert cleared == 5

        stats = semantic_memory.get_stats()
        assert stats["total_entries"] == 0


class TestSemanticMemoryStats:
    """Test statistics."""

    def test_get_stats_basic(self, semantic_memory):
        """Test getting memory statistics."""
        # Store entries with embeddings
        for i in range(3):
            semantic_memory.store(f"Entry {i}")

        stats = semantic_memory.get_stats()

        assert stats["total_entries"] == 3
        assert stats["with_embeddings"] == 3
        assert stats["without_embeddings"] == 0
        assert stats["embedding_coverage"] == 1.0
        assert stats["has_embedding_function"] is True

    def test_get_stats_partial_embeddings(self, semantic_memory_no_embeddings):
        """Test stats with partial embedding coverage."""
        # Store some with custom embeddings, some without
        semantic_memory_no_embeddings.store("With embedding", embedding=[0.1, 0.2, 0.3])
        semantic_memory_no_embeddings.store(
            "Also with embedding", embedding=[0.4, 0.5, 0.6]
        )
        semantic_memory_no_embeddings.store(
            "No embedding"
        )  # No embedding function, so no auto-generation

        stats = semantic_memory_no_embeddings.get_stats()

        assert stats["total_entries"] == 3
        assert stats["with_embeddings"] == 2
        assert stats["without_embeddings"] == 1
        assert abs(stats["embedding_coverage"] - 0.667) < 0.01

    def test_get_stats_no_embedding_function(self, semantic_memory_no_embeddings):
        """Test stats without embedding function."""
        semantic_memory_no_embeddings.store("Entry 1")

        stats = semantic_memory_no_embeddings.get_stats()

        assert stats["has_embedding_function"] is False
        assert stats["without_embeddings"] == 1


class TestSemanticMemoryCosineSimilarity:
    """Test cosine similarity calculation."""

    def test_cosine_similarity_identical(self, semantic_memory):
        """Test similarity of identical vectors."""
        vec = [1.0, 0.0, 1.0, 0.0]
        similarity = semantic_memory._cosine_similarity(vec, vec)

        # Should be maximum similarity (1.0 normalized to 1.0)
        # Use approximate comparison for floating point
        assert abs(similarity - 1.0) < 0.001

    def test_cosine_similarity_orthogonal(self, semantic_memory):
        """Test similarity of orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0, 0.0]

        similarity = semantic_memory._cosine_similarity(vec1, vec2)

        # Should be 0.5 (0 cosine similarity normalized to 0-1 range)
        assert abs(similarity - 0.5) < 0.01

    def test_cosine_similarity_different_lengths(self, semantic_memory):
        """Test similarity of vectors with different lengths."""
        vec1 = [1.0, 0.0, 1.0]
        vec2 = [1.0, 0.0]

        similarity = semantic_memory._cosine_similarity(vec1, vec2)

        # Should return 0.0 for incompatible vectors
        assert similarity == 0.0

    def test_cosine_similarity_zero_magnitude(self, semantic_memory):
        """Test similarity with zero magnitude vector."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 1.0, 1.0]

        similarity = semantic_memory._cosine_similarity(vec1, vec2)

        # Should return 0.0 for zero magnitude
        assert similarity == 0.0

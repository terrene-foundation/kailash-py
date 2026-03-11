"""
Tests for PostgreSQLVectorAdapter.

Unit tests for PostgreSQL vector similarity search adapter.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataflow.adapters import (
    BaseAdapter,
    DatabaseAdapter,
    PostgreSQLAdapter,
    PostgreSQLVectorAdapter,
)


class TestPostgreSQLVectorAdapter:
    """Test PostgreSQLVectorAdapter initialization and configuration."""

    def test_adapter_initialization(self):
        """PostgreSQLVectorAdapter initializes with correct defaults."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        assert adapter.database_type == "postgresql_vector"
        assert adapter.adapter_type == "sql"
        assert adapter.vector_dimensions == 1536  # OpenAI default
        assert adapter.default_distance == "cosine"

    def test_adapter_initialization_custom_vector_params(self):
        """PostgreSQLVectorAdapter accepts custom vector parameters."""
        adapter = PostgreSQLVectorAdapter(
            "postgresql://localhost/vectordb",
            vector_dimensions=768,  # BERT dimensions
            default_distance="l2",
        )

        assert adapter.vector_dimensions == 768
        assert adapter.default_distance == "l2"

    def test_adapter_hierarchy(self):
        """PostgreSQLVectorAdapter inherits correctly from adapter hierarchy."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Should be instance of all parent classes
        assert isinstance(adapter, BaseAdapter)
        assert isinstance(adapter, DatabaseAdapter)
        assert isinstance(adapter, PostgreSQLAdapter)
        assert isinstance(adapter, PostgreSQLVectorAdapter)

    def test_supports_vector_features(self):
        """PostgreSQLVectorAdapter supports vector-specific features."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Vector features
        assert adapter.supports_feature("vector_search") is True
        assert adapter.supports_feature("vector_index") is True
        assert adapter.supports_feature("hybrid_search") is True
        assert adapter.supports_feature("vector_l2") is True
        assert adapter.supports_feature("vector_cosine") is True
        assert adapter.supports_feature("vector_ip") is True

        # PostgreSQL features (inherited from PostgreSQLAdapter)
        assert adapter.supports_feature("json") is True
        assert adapter.supports_feature("arrays") is True
        assert adapter.supports_feature("fulltext_search") is True

        # Unsupported features
        assert adapter.supports_feature("graph_queries") is False
        assert adapter.supports_feature("mysql_specific") is False

    @pytest.mark.asyncio
    async def test_ensure_pgvector_extension(self):
        """Test pgvector extension installation."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Mock execute_query
        adapter.execute_query = AsyncMock(return_value=[])

        await adapter.ensure_pgvector_extension()

        # Should execute CREATE EXTENSION
        adapter.execute_query.assert_called_once_with(
            "CREATE EXTENSION IF NOT EXISTS vector"
        )

        # Should mark as installed
        assert adapter._pgvector_installed is True

    @pytest.mark.asyncio
    async def test_ensure_pgvector_extension_failure(self):
        """Test pgvector extension installation failure."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Mock execute_query to raise exception
        adapter.execute_query = AsyncMock(
            side_effect=Exception("pgvector not available")
        )

        with pytest.raises(RuntimeError, match="pgvector extension not available"):
            await adapter.ensure_pgvector_extension()

        assert adapter._pgvector_installed is False

    @pytest.mark.asyncio
    async def test_create_vector_column(self):
        """Test vector column creation."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Mock methods
        adapter.ensure_pgvector_extension = AsyncMock()
        adapter.execute_query = AsyncMock(return_value=[])

        await adapter.create_vector_column("documents", "embedding", 1536)

        # Should ensure pgvector is installed
        adapter.ensure_pgvector_extension.assert_called_once()

        # Should execute ALTER TABLE
        call_args = adapter.execute_query.call_args[0][0]
        assert "ALTER TABLE documents" in call_args
        assert "ADD COLUMN IF NOT EXISTS embedding vector(1536)" in call_args

    @pytest.mark.asyncio
    async def test_create_vector_column_default_dimensions(self):
        """Test vector column creation with default dimensions."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.ensure_pgvector_extension = AsyncMock()
        adapter.execute_query = AsyncMock(return_value=[])

        # Default dimensions should be used
        await adapter.create_vector_column("documents")

        call_args = adapter.execute_query.call_args[0][0]
        assert "vector(1536)" in call_args  # Default OpenAI dimensions

    @pytest.mark.asyncio
    async def test_create_vector_index_ivfflat(self):
        """Test IVFFlat vector index creation."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.ensure_pgvector_extension = AsyncMock()
        adapter.execute_query = AsyncMock(return_value=[])

        await adapter.create_vector_index(
            "documents", "embedding", "ivfflat", "cosine", lists=100
        )

        # Should create IVFFlat index
        call_args = adapter.execute_query.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS" in call_args
        assert "USING ivfflat" in call_args
        assert "vector_cosine_ops" in call_args
        assert "lists = 100" in call_args

    @pytest.mark.asyncio
    async def test_create_vector_index_hnsw(self):
        """Test HNSW vector index creation."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.ensure_pgvector_extension = AsyncMock()
        adapter.execute_query = AsyncMock(return_value=[])

        await adapter.create_vector_index(
            "documents",
            "embedding",
            "hnsw",
            "l2",
            m=16,
            ef_construction=64,
        )

        # Should create HNSW index
        call_args = adapter.execute_query.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS" in call_args
        assert "USING hnsw" in call_args
        assert "vector_l2_ops" in call_args
        assert "m = 16" in call_args
        assert "ef_construction = 64" in call_args

    @pytest.mark.asyncio
    async def test_create_vector_index_invalid_distance(self):
        """Test vector index creation with invalid distance metric."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.ensure_pgvector_extension = AsyncMock()

        with pytest.raises(ValueError, match="Unknown distance metric"):
            await adapter.create_vector_index(
                "documents", "embedding", "ivfflat", "invalid_distance"
            )

    @pytest.mark.asyncio
    async def test_create_vector_index_invalid_type(self):
        """Test vector index creation with invalid index type."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.ensure_pgvector_extension = AsyncMock()

        with pytest.raises(ValueError, match="Unknown index type"):
            await adapter.create_vector_index(
                "documents", "embedding", "invalid_type", "cosine"
            )

    @pytest.mark.asyncio
    async def test_vector_search_cosine(self):
        """Test vector similarity search with cosine distance."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Mock results
        mock_results = [
            {"id": "1", "title": "Doc 1", "distance": 0.1},
            {"id": "2", "title": "Doc 2", "distance": 0.2},
        ]
        adapter.execute_query = AsyncMock(return_value=mock_results)

        query_vector = [0.1] * 1536  # Dummy embedding
        results = await adapter.vector_search(
            "documents", query_vector, k=2, distance="cosine"
        )

        assert len(results) == 2
        assert results == mock_results

        # Check SQL query
        call_args = adapter.execute_query.call_args[0][0]
        assert "ORDER BY embedding <=>" in call_args  # Cosine operator
        assert "LIMIT 2" in call_args

    @pytest.mark.asyncio
    async def test_vector_search_with_filter(self):
        """Test vector search with filter conditions."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.execute_query = AsyncMock(return_value=[])

        query_vector = [0.1] * 1536
        await adapter.vector_search(
            "documents",
            query_vector,
            k=5,
            filter_conditions="category = 'tech' AND published = true",
        )

        # Check SQL query includes WHERE clause
        call_args = adapter.execute_query.call_args[0][0]
        assert "WHERE category = 'tech' AND published = true" in call_args

    @pytest.mark.asyncio
    async def test_vector_search_l2_distance(self):
        """Test vector search with L2 distance metric."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.execute_query = AsyncMock(return_value=[])

        query_vector = [0.1] * 768
        await adapter.vector_search("documents", query_vector, k=10, distance="l2")

        # Check SQL uses L2 operator
        call_args = adapter.execute_query.call_args[0][0]
        assert "<->" in call_args  # L2 operator

    @pytest.mark.asyncio
    async def test_vector_search_inner_product(self):
        """Test vector search with inner product."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")
        adapter.execute_query = AsyncMock(return_value=[])

        query_vector = [0.1] * 1536
        await adapter.vector_search("documents", query_vector, k=10, distance="ip")

        # Check SQL uses inner product operator
        call_args = adapter.execute_query.call_args[0][0]
        assert "<#>" in call_args  # Inner product operator

    @pytest.mark.asyncio
    async def test_vector_search_invalid_distance(self):
        """Test vector search with invalid distance metric."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        query_vector = [0.1] * 1536
        with pytest.raises(ValueError, match="Unknown distance metric"):
            await adapter.vector_search(
                "documents", query_vector, k=10, distance="invalid"
            )

    @pytest.mark.asyncio
    async def test_hybrid_search_vector_only(self):
        """Test hybrid search with no text query (vector only)."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        mock_vector_results = [
            {"id": "1", "title": "Doc 1", "distance": 0.1},
            {"id": "2", "title": "Doc 2", "distance": 0.2},
        ]

        # Mock vector_search method
        adapter.vector_search = AsyncMock(return_value=mock_vector_results)

        query_vector = [0.1] * 1536
        results = await adapter.hybrid_search(
            "documents", query_vector, text_query=None, k=5
        )

        # Should return vector results only
        assert results == mock_vector_results[:5]

    @pytest.mark.asyncio
    async def test_hybrid_search_combined(self):
        """Test hybrid search combining vector and text results."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        # Mock vector results
        mock_vector_results = [
            {"id": "1", "title": "Doc 1", "distance": 0.1},
            {"id": "2", "title": "Doc 2", "distance": 0.2},
        ]

        # Mock text results
        mock_text_results = [
            {"id": "2", "title": "Doc 2", "text_score": 0.9},
            {"id": "3", "title": "Doc 3", "text_score": 0.7},
        ]

        # Mock final combined results
        mock_final_results = [
            {"id": "2", "title": "Doc 2"},
            {"id": "1", "title": "Doc 1"},
        ]

        adapter.vector_search = AsyncMock(return_value=mock_vector_results)
        adapter.execute_query = AsyncMock(
            side_effect=[mock_text_results, mock_final_results]
        )

        query_vector = [0.1] * 1536
        results = await adapter.hybrid_search(
            "documents", query_vector, text_query="machine learning", k=2
        )

        # Should call vector_search
        adapter.vector_search.assert_called_once()

        # Should execute text search and final fetch
        assert adapter.execute_query.call_count == 2

        # Should return combined results
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_hybrid_search_text_failure_fallback(self):
        """Test hybrid search falls back to vector search if text search fails."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        mock_vector_results = [{"id": "1", "title": "Doc 1", "distance": 0.1}]

        adapter.vector_search = AsyncMock(return_value=mock_vector_results)
        adapter.execute_query = AsyncMock(side_effect=Exception("Text search failed"))

        query_vector = [0.1] * 1536
        results = await adapter.hybrid_search(
            "documents", query_vector, text_query="test", k=5
        )

        # Should fall back to vector results
        assert results == mock_vector_results[:5]

    @pytest.mark.asyncio
    async def test_get_vector_stats(self):
        """Test getting vector column statistics."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        mock_stats = {
            "total_vectors": 1000,
            "non_null_vectors": 950,
            "dimensions": 1536,
        }

        adapter.execute_query = AsyncMock(return_value=[mock_stats])

        stats = await adapter.get_vector_stats("documents", "embedding")

        assert stats["total_vectors"] == 1000
        assert stats["non_null_vectors"] == 950
        assert stats["dimensions"] == 1536

        # Check SQL query
        call_args = adapter.execute_query.call_args[0][0]
        assert "COUNT(*)" in call_args
        assert "COUNT(embedding)" in call_args
        assert "array_length(embedding, 1)" in call_args

    def test_adapter_repr(self):
        """Test __repr__ method."""
        adapter = PostgreSQLVectorAdapter("postgresql://localhost/vectordb")

        repr_str = repr(adapter)

        assert "PostgreSQLVectorAdapter" in repr_str
        assert "database_type='postgresql_vector'" in repr_str

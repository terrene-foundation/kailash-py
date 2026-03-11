"""
Unit tests for vector search nodes.

Tests for VectorSearchNode, CreateVectorIndexNode, and HybridSearchNode.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dataflow.adapters import PostgreSQLVectorAdapter
from dataflow.nodes.vector_nodes import (
    CreateVectorIndexNode,
    HybridSearchNode,
    VectorSearchNode,
)


@pytest.mark.unit
class TestVectorSearchNode:
    """Test VectorSearchNode initialization and configuration."""

    def test_node_initialization(self):
        """VectorSearchNode initializes correctly."""
        node = VectorSearchNode(
            table_name="documents",
            dataflow_instance=MagicMock(),
        )

        assert node.table_name == "documents"
        assert node.dataflow_instance is not None

    def test_get_parameters(self):
        """VectorSearchNode defines correct parameters."""
        node = VectorSearchNode(table_name="documents")
        params = node.get_parameters()

        # Required parameters
        assert "query_vector" in params
        assert params["query_vector"].required is True
        assert params["query_vector"].type == list

        # Optional parameters with defaults
        assert "k" in params
        assert params["k"].default == 10
        assert params["k"].type == int

        assert "column_name" in params
        assert params["column_name"].default == "embedding"

        assert "distance" in params
        assert params["distance"].default == "cosine"

        assert "filter_conditions" in params
        assert params["filter_conditions"].default is None

        assert "return_distance" in params
        assert params["return_distance"].default is True

    @pytest.mark.asyncio
    async def test_async_run_requires_dataflow_instance(self):
        """VectorSearchNode requires dataflow_instance."""
        node = VectorSearchNode(table_name="documents")

        with pytest.raises(ValueError, match="requires dataflow_instance"):
            await node.async_run(query_vector=[0.1] * 1536)

    @pytest.mark.asyncio
    async def test_async_run_requires_vector_adapter(self):
        """VectorSearchNode requires PostgreSQLVectorAdapter."""
        # Mock dataflow instance with wrong adapter type
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = MagicMock()  # Not PostgreSQLVectorAdapter

        node = VectorSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(ValueError, match="requires PostgreSQLVectorAdapter"):
            await node.async_run(query_vector=[0.1] * 1536)

    @pytest.mark.asyncio
    async def test_async_run_requires_table_name(self):
        """VectorSearchNode requires table_name."""
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        node = VectorSearchNode(
            table_name=None,  # Missing table_name
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(ValueError, match="table_name is required"):
            await node.async_run(query_vector=[0.1] * 1536)

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """VectorSearchNode executes successfully."""
        # Mock adapter
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_results = [
            {"id": "1", "title": "Doc 1", "distance": 0.1},
            {"id": "2", "title": "Doc 2", "distance": 0.2},
        ]
        mock_adapter.vector_search = AsyncMock(return_value=mock_results)

        # Mock dataflow instance
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        # Create node
        node = VectorSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        # Execute with parameters via kwargs
        result = await node.async_run(
            query_vector=[0.1] * 1536,
            k=5,
            column_name="embedding",
            distance="cosine",
            filter_conditions="category = 'tech'",
            return_distance=True,
        )

        # Verify adapter was called correctly
        mock_adapter.vector_search.assert_called_once_with(
            table_name="documents",
            query_vector=[0.1] * 1536,
            k=5,
            column_name="embedding",
            distance="cosine",
            filter_conditions="category = 'tech'",
            return_distance=True,
        )

        # Verify result
        assert result["results"] == mock_results
        assert result["count"] == 2
        assert result["table_name"] == "documents"
        assert result["distance_metric"] == "cosine"

    @pytest.mark.asyncio
    async def test_async_run_handles_errors(self):
        """VectorSearchNode handles adapter errors."""
        # Mock adapter that raises error
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_adapter.vector_search = AsyncMock(side_effect=Exception("Database error"))

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        node = VectorSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(RuntimeError, match="Vector search failed"):
            await node.async_run(query_vector=[0.1] * 1536)


@pytest.mark.unit
class TestCreateVectorIndexNode:
    """Test CreateVectorIndexNode initialization and configuration."""

    def test_node_initialization(self):
        """CreateVectorIndexNode initializes correctly."""
        node = CreateVectorIndexNode(
            table_name="documents",
            dataflow_instance=MagicMock(),
        )

        assert node.table_name == "documents"
        assert node.dataflow_instance is not None

    def test_get_parameters(self):
        """CreateVectorIndexNode defines correct parameters."""
        node = CreateVectorIndexNode(table_name="documents")
        params = node.get_parameters()

        assert "column_name" in params
        assert params["column_name"].default == "embedding"

        assert "index_type" in params
        assert params["index_type"].default == "ivfflat"

        assert "distance" in params
        assert params["distance"].default == "cosine"

        assert "lists" in params
        assert params["lists"].default == 100

        assert "m" in params
        assert params["m"].default == 16

        assert "ef_construction" in params
        assert params["ef_construction"].default == 64

    @pytest.mark.asyncio
    async def test_async_run_requires_dataflow_instance(self):
        """CreateVectorIndexNode requires dataflow_instance."""
        node = CreateVectorIndexNode(table_name="documents")

        with pytest.raises(ValueError, match="requires dataflow_instance"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_requires_vector_adapter(self):
        """CreateVectorIndexNode requires PostgreSQLVectorAdapter."""
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = MagicMock()  # Not PostgreSQLVectorAdapter

        node = CreateVectorIndexNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(ValueError, match="requires PostgreSQLVectorAdapter"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_requires_table_name(self):
        """CreateVectorIndexNode requires table_name."""
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        node = CreateVectorIndexNode(
            table_name=None,
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(ValueError, match="table_name is required"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_ivfflat_index(self):
        """CreateVectorIndexNode creates IVFFlat index."""
        # Mock adapter
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_adapter.create_vector_index = AsyncMock()

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        # Create node
        node = CreateVectorIndexNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        # Execute with parameters via kwargs
        result = await node.async_run(
            column_name="embedding",
            index_type="ivfflat",
            distance="cosine",
            lists=100,
        )

        # Verify adapter was called correctly (ivfflat doesn't use m/ef_construction)
        mock_adapter.create_vector_index.assert_called_once_with(
            table_name="documents",
            column_name="embedding",
            index_type="ivfflat",
            distance="cosine",
            lists=100,
        )

        # Verify result
        assert result["success"] is True
        assert result["index_created"] is True
        assert result["table_name"] == "documents"
        assert result["column_name"] == "embedding"
        assert result["index_type"] == "ivfflat"

    @pytest.mark.asyncio
    async def test_async_run_hnsw_index(self):
        """CreateVectorIndexNode creates HNSW index."""
        # Mock adapter
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_adapter.create_vector_index = AsyncMock()

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        # Create node
        node = CreateVectorIndexNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        # Execute with parameters via kwargs
        result = await node.async_run(
            column_name="embedding",
            index_type="hnsw",
            distance="l2",
            lists=100,
            m=16,
            ef_construction=64,
        )

        # Verify adapter was called with HNSW params
        mock_adapter.create_vector_index.assert_called_once_with(
            table_name="documents",
            column_name="embedding",
            index_type="hnsw",
            distance="l2",
            lists=100,
            m=16,
            ef_construction=64,
        )

        # Verify result
        assert result["index_type"] == "hnsw"
        assert result["distance"] == "l2"

    @pytest.mark.asyncio
    async def test_async_run_handles_errors(self):
        """CreateVectorIndexNode handles adapter errors."""
        # Mock adapter that raises error
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_adapter.create_vector_index = AsyncMock(
            side_effect=Exception("Index creation failed")
        )

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        node = CreateVectorIndexNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(RuntimeError, match="Vector index creation failed"):
            await node.async_run(column_name="embedding")


@pytest.mark.unit
class TestHybridSearchNode:
    """Test HybridSearchNode initialization and configuration."""

    def test_node_initialization(self):
        """HybridSearchNode initializes correctly."""
        node = HybridSearchNode(
            table_name="documents",
            dataflow_instance=MagicMock(),
        )

        assert node.table_name == "documents"
        assert node.dataflow_instance is not None

    def test_get_parameters(self):
        """HybridSearchNode defines correct parameters."""
        node = HybridSearchNode(table_name="documents")
        params = node.get_parameters()

        # Required parameters
        assert "query_vector" in params
        assert params["query_vector"].required is True

        # Optional parameters
        assert "text_query" in params
        assert params["text_query"].default is None

        assert "k" in params
        assert params["k"].default == 10

        assert "vector_weight" in params
        assert params["vector_weight"].default == 0.7

        assert "text_weight" in params
        assert params["text_weight"].default == 0.3

        assert "column_name" in params
        assert params["column_name"].default == "embedding"

        assert "text_column" in params
        assert params["text_column"].default == "content"

    @pytest.mark.asyncio
    async def test_async_run_requires_dataflow_instance(self):
        """HybridSearchNode requires dataflow_instance."""
        node = HybridSearchNode(table_name="documents")
        node.query_vector = [0.1] * 1536

        with pytest.raises(ValueError, match="requires dataflow_instance"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_requires_vector_adapter(self):
        """HybridSearchNode requires PostgreSQLVectorAdapter."""
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = MagicMock()  # Not PostgreSQLVectorAdapter

        node = HybridSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )
        node.query_vector = [0.1] * 1536

        with pytest.raises(ValueError, match="requires PostgreSQLVectorAdapter"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_requires_table_name(self):
        """HybridSearchNode requires table_name."""
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        node = HybridSearchNode(
            table_name=None,
            dataflow_instance=mock_dataflow,
        )
        node.query_vector = [0.1] * 1536

        with pytest.raises(ValueError, match="table_name is required"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_hybrid_search(self):
        """HybridSearchNode executes hybrid search successfully."""
        # Mock adapter
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_results = [
            {"id": "1", "title": "ML Doc", "content": "machine learning"},
            {"id": "2", "title": "AI Doc", "content": "artificial intelligence"},
        ]
        mock_adapter.hybrid_search = AsyncMock(return_value=mock_results)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        # Create node
        node = HybridSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        # Execute with parameters via kwargs
        result = await node.async_run(
            query_vector=[0.1] * 1536,
            text_query="machine learning",
            k=10,
            vector_weight=0.7,
            text_weight=0.3,
            column_name="embedding",
            text_column="content",
        )

        # Verify adapter was called correctly
        mock_adapter.hybrid_search.assert_called_once_with(
            table_name="documents",
            query_vector=[0.1] * 1536,
            text_query="machine learning",
            k=10,
            vector_weight=0.7,
            text_weight=0.3,
            column_name="embedding",
            text_column="content",
        )

        # Verify result
        assert result["results"] == mock_results
        assert result["count"] == 2
        assert result["table_name"] == "documents"
        assert result["search_type"] == "hybrid"

    @pytest.mark.asyncio
    async def test_async_run_vector_only_search(self):
        """HybridSearchNode executes vector-only search when text_query is None."""
        # Mock adapter
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_results = [{"id": "1", "title": "Doc 1"}]
        mock_adapter.hybrid_search = AsyncMock(return_value=mock_results)

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        # Create node
        node = HybridSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        # Execute with parameters via kwargs (no text_query)
        result = await node.async_run(
            query_vector=[0.1] * 1536,
            text_query=None,  # Vector-only search
            k=5,
        )

        # Verify result indicates vector-only search
        assert result["search_type"] == "vector_only"

    @pytest.mark.asyncio
    async def test_async_run_handles_errors(self):
        """HybridSearchNode handles adapter errors."""
        # Mock adapter that raises error
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_adapter.hybrid_search = AsyncMock(
            side_effect=Exception("Hybrid search failed")
        )

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        node = HybridSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        with pytest.raises(RuntimeError, match="Hybrid search failed"):
            await node.async_run(query_vector=[0.1] * 1536)


@pytest.mark.unit
class TestVectorNodesIntegration:
    """Test vector nodes work together."""

    @pytest.mark.asyncio
    async def test_create_index_then_search(self):
        """Test creating index and then searching."""
        # Mock adapter
        mock_adapter = MagicMock(spec=PostgreSQLVectorAdapter)
        mock_adapter.create_vector_index = AsyncMock()
        mock_adapter.vector_search = AsyncMock(return_value=[{"id": "1"}])

        mock_dataflow = MagicMock()
        mock_dataflow.adapter = mock_adapter

        # Create index first
        index_node = CreateVectorIndexNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        index_result = await index_node.async_run(
            column_name="embedding",
            index_type="ivfflat",
            distance="cosine",
            lists=100,
        )
        assert index_result["success"] is True

        # Then search
        search_node = VectorSearchNode(
            table_name="documents",
            dataflow_instance=mock_dataflow,
        )

        search_result = await search_node.async_run(
            query_vector=[0.1] * 1536,
            k=5,
            distance="cosine",
        )
        assert search_result["count"] == 1

        # Verify both operations called adapter
        mock_adapter.create_vector_index.assert_called_once()
        mock_adapter.vector_search.assert_called_once()

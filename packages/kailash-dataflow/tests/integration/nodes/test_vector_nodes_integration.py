"""
Integration tests for vector workflow nodes with real PostgreSQL + pgvector.

Tests VectorSearchNode, CreateVectorIndexNode, and HybridSearchNode
with real database infrastructure and DataFlow integration.

Following NO MOCKING policy for Tier 2 tests.
"""

import pytest
from dataflow import DataFlow
from dataflow.adapters import PostgreSQLVectorAdapter
from dataflow.nodes.vector_nodes import (
    CreateVectorIndexNode,
    HybridSearchNode,
    VectorSearchNode,
)

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create integration test suite with PostgreSQL infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def dataflow_vector(test_suite):
    """
    Create DataFlow instance with PostgreSQLVectorAdapter.

    NOTE: This test requires pgvector extension on PostgreSQL.
    Tests will be skipped if pgvector is not available.
    """
    db_url = test_suite.config.url

    # Create PostgreSQLVectorAdapter
    adapter = PostgreSQLVectorAdapter(db_url)

    # Test if pgvector is available
    await adapter.connect()
    try:
        await adapter.ensure_pgvector_extension()
    except RuntimeError as e:
        await adapter.disconnect()
        pytest.skip(f"pgvector extension not available: {e}")

    # Create DataFlow with vector adapter
    df = DataFlow(adapter=adapter)

    yield df

    # Cleanup
    await adapter.disconnect()


@pytest.fixture
async def vector_table_with_data(dataflow_vector, test_suite):
    """
    Create test table with vector data for node testing.

    Returns (dataflow, table_name) tuple.
    """
    import time

    table_name = f"test_node_vectors_{int(time.time() * 1000)}"

    async with test_suite.get_connection() as conn:
        # Create table
        await conn.execute(
            f"""
            CREATE TABLE {table_name} (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                embedding vector(1536)
            )
        """
        )

        # Insert sample data
        sample_data = [
            ("ML Tutorial", "Machine learning basics", "tech", [0.1] * 1536),
            ("Python Guide", "Learn Python programming", "tech", [0.15] * 1536),
            ("Cooking Tips", "Best pasta recipes", "food", [0.8] * 1536),
            ("Data Science", "Introduction to data science", "tech", [0.12] * 1536),
            ("Travel Blog", "Europe travel guide", "travel", [0.9] * 1536),
        ]

        for title, content, category, embedding in sample_data:
            embedding_str = f"'[{','.join(map(str, embedding))}]'"
            await conn.execute(
                f"""
                INSERT INTO {table_name} (title, content, category, embedding)
                VALUES ($1, $2, $3, {embedding_str}::vector)
            """,
                title,
                content,
                category,
            )

    yield dataflow_vector, table_name

    # Cleanup
    async with test_suite.get_connection() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {table_name}")


@pytest.mark.integration
@pytest.mark.asyncio
class TestVectorSearchNodeIntegration:
    """Integration tests for VectorSearchNode with real database."""

    async def test_vector_search_node_basic(self, vector_table_with_data):
        """Test VectorSearchNode performs semantic search."""
        dataflow, table_name = vector_table_with_data

        # Create VectorSearchNode
        node = VectorSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Execute search for tech-related content
        query_vector = [0.11] * 1536  # Close to tech documents
        result = await node.async_run(
            query_vector=query_vector,
            k=3,
            distance="cosine",
        )

        # Verify results
        assert "results" in result
        assert "count" in result
        assert result["count"] > 0
        assert len(result["results"]) <= 3

        # Should return tech documents first
        assert result["table_name"] == table_name
        assert result["distance_metric"] == "cosine"

    async def test_vector_search_with_filters(self, vector_table_with_data):
        """Test VectorSearchNode with filter conditions."""
        dataflow, table_name = vector_table_with_data

        node = VectorSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Search only in tech category
        result = await node.async_run(
            query_vector=[0.1] * 1536,
            k=10,
            filter_conditions="category = 'tech'",
            distance="cosine",
        )

        # All results should be tech
        assert result["count"] > 0
        for doc in result["results"]:
            assert doc["category"] == "tech"

    async def test_vector_search_l2_distance(self, vector_table_with_data):
        """Test VectorSearchNode with L2 distance metric."""
        dataflow, table_name = vector_table_with_data

        node = VectorSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        result = await node.async_run(
            query_vector=[0.15] * 1536,
            k=5,
            distance="l2",
            return_distance=True,
        )

        assert result["count"] > 0
        assert result["distance_metric"] == "l2"

        # Verify distances are included
        for doc in result["results"]:
            assert "distance" in doc


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreateVectorIndexNodeIntegration:
    """Integration tests for CreateVectorIndexNode with real database."""

    async def test_create_ivfflat_index(self, vector_table_with_data, test_suite):
        """Test CreateVectorIndexNode creates IVFFlat index."""
        dataflow, table_name = vector_table_with_data

        node = CreateVectorIndexNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Create IVFFlat index
        result = await node.async_run(
            column_name="embedding",
            index_type="ivfflat",
            distance="cosine",
            lists=10,
        )

        assert result["success"] is True
        assert result["index_created"] is True
        assert result["table_name"] == table_name
        assert result["index_type"] == "ivfflat"

        # Verify index exists in database
        async with test_suite.get_connection() as conn:
            index_name = f"{table_name}_embedding_ivfflat_idx"
            rows = await conn.fetch(
                f"""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = '{table_name}'
                AND indexname = '{index_name}'
            """
            )
            assert len(rows) == 1

    async def test_create_hnsw_index(self, vector_table_with_data, test_suite):
        """Test CreateVectorIndexNode creates HNSW index."""
        dataflow, table_name = vector_table_with_data

        node = CreateVectorIndexNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Create HNSW index (requires pgvector 0.5.0+)
        try:
            result = await node.async_run(
                column_name="embedding",
                index_type="hnsw",
                distance="l2",
                m=16,
                ef_construction=64,
            )

            assert result["success"] is True
            assert result["index_type"] == "hnsw"

            # Verify index exists
            async with test_suite.get_connection() as conn:
                index_name = f"{table_name}_embedding_hnsw_idx"
                rows = await conn.fetch(
                    f"""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = '{table_name}'
                    AND indexname = '{index_name}'
                """
                )
                assert len(rows) == 1

        except Exception as e:
            # HNSW may not be available on older pgvector versions
            if "hnsw" in str(e).lower() or "index type" in str(e).lower():
                pytest.skip("HNSW index not supported (requires pgvector 0.5.0+)")
            else:
                raise


@pytest.mark.integration
@pytest.mark.asyncio
class TestHybridSearchNodeIntegration:
    """Integration tests for HybridSearchNode with real database."""

    async def test_hybrid_search_vector_only(self, vector_table_with_data):
        """Test HybridSearchNode with vector-only search."""
        dataflow, table_name = vector_table_with_data

        node = HybridSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Search without text query (vector only)
        result = await node.async_run(
            query_vector=[0.1] * 1536,
            text_query=None,
            k=5,
        )

        assert result["count"] > 0
        assert result["search_type"] == "vector_only"
        assert len(result["results"]) <= 5

    async def test_hybrid_search_combined(self, vector_table_with_data, test_suite):
        """Test HybridSearchNode with combined vector and text search."""
        dataflow, table_name = vector_table_with_data

        # Create full-text search index
        async with test_suite.get_connection() as conn:
            await conn.execute(
                f"""
                CREATE INDEX {table_name}_content_fts
                ON {table_name}
                USING gin(to_tsvector('english', content))
            """
            )

        node = HybridSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Hybrid search
        result = await node.async_run(
            query_vector=[0.1] * 1536,
            text_query="python programming",
            k=5,
            vector_weight=0.7,
            text_weight=0.3,
            text_column="content",
        )

        assert "results" in result
        assert result["search_type"] == "hybrid"
        # May have no results if text query doesn't match exactly
        assert len(result["results"]) <= 5


@pytest.mark.integration
@pytest.mark.asyncio
class TestVectorNodesWorkflowIntegration:
    """Integration tests for complete vector workflow."""

    async def test_index_then_search_workflow(self, vector_table_with_data, test_suite):
        """Test complete workflow: create index, then search."""
        dataflow, table_name = vector_table_with_data

        # Step 1: Create vector index
        index_node = CreateVectorIndexNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        index_result = await index_node.async_run(
            column_name="embedding",
            index_type="ivfflat",
            distance="cosine",
            lists=10,
        )

        assert index_result["success"] is True

        # Verify index was created
        async with test_suite.get_connection() as conn:
            index_name = f"{table_name}_embedding_ivfflat_idx"
            rows = await conn.fetch(
                f"""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = '{table_name}'
                AND indexname = '{index_name}'
            """
            )
            assert len(rows) == 1

        # Step 2: Perform vector search (should use index)
        search_node = VectorSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        search_result = await search_node.async_run(
            query_vector=[0.1] * 1536,
            k=3,
            distance="cosine",
        )

        assert search_result["count"] > 0
        assert len(search_result["results"]) <= 3

    async def test_multiple_searches_workflow(self, vector_table_with_data):
        """Test performing multiple different vector searches."""
        dataflow, table_name = vector_table_with_data

        node = VectorSearchNode(
            table_name=table_name,
            dataflow_instance=dataflow,
        )

        # Search 1: Tech documents
        tech_result = await node.async_run(
            query_vector=[0.1] * 1536,
            k=3,
            distance="cosine",
        )

        # Search 2: Food documents
        food_result = await node.async_run(
            query_vector=[0.8] * 1536,
            k=3,
            distance="cosine",
        )

        # Both searches should return results
        assert tech_result["count"] > 0
        assert food_result["count"] > 0

        # Results should be different (different nearest neighbors)
        tech_ids = {r["id"] for r in tech_result["results"]}
        food_ids = {r["id"] for r in food_result["results"]}
        # At least some results should be different
        assert tech_ids != food_ids

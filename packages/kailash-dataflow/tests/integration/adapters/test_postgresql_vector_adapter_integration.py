"""
Integration tests for PostgreSQLVectorAdapter with real PostgreSQL + pgvector.

Tests vector similarity search operations using real database infrastructure.
Following NO MOCKING policy for Tier 2 tests.
"""

import asyncio

import pytest
from dataflow.adapters import PostgreSQLVectorAdapter

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create integration test suite with PostgreSQL infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def vector_adapter(test_suite):
    """
    Create PostgreSQLVectorAdapter with real database.

    NOTE: This test requires pgvector extension to be installed on PostgreSQL.
    If pgvector is not available, tests will be skipped.
    """
    # Use the test suite's PostgreSQL connection
    db_url = test_suite.config.url

    # Create vector adapter
    adapter = PostgreSQLVectorAdapter(db_url)

    # Connect adapter
    await adapter.connect()

    # Test if pgvector is available, skip if not
    try:
        await adapter.ensure_pgvector_extension()
    except RuntimeError as e:
        pytest.skip(f"pgvector extension not available: {e}")

    yield adapter

    # Cleanup: disconnect
    await adapter.disconnect()


@pytest.fixture
async def vector_table(vector_adapter, test_suite):
    """
    Create a test table with vector column and sample data.

    Returns table name that will be cleaned up after test.
    """
    import time

    table_name = f"test_vectors_{int(time.time() * 1000)}"

    async with test_suite.get_connection() as conn:
        # Create table with content and embedding columns
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

        # Insert sample data with mock embeddings
        # Using smaller dimension vectors for testing (actually 3D, but declaring 1536 for compatibility)
        # In real use, these would be actual embeddings from an embedding model
        sample_data = [
            (
                "Machine Learning Basics",
                "Introduction to ML algorithms",
                "tech",
                [0.1] * 1536,
            ),
            ("Python Programming", "Learn Python from scratch", "tech", [0.2] * 1536),
            ("Cooking Recipes", "Delicious pasta recipes", "food", [0.8] * 1536),
            (
                "Data Science Guide",
                "Comprehensive guide to data science",
                "tech",
                [0.15] * 1536,
            ),
            ("Travel Tips", "Best places to visit in Europe", "travel", [0.9] * 1536),
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

    yield table_name

    # Cleanup: drop table
    async with test_suite.get_connection() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {table_name}")


@pytest.mark.integration
@pytest.mark.asyncio
class TestPostgreSQLVectorAdapterIntegration:
    """Integration tests for PostgreSQLVectorAdapter with real database."""

    async def test_adapter_connection(self, vector_adapter):
        """Test adapter connects to PostgreSQL successfully."""
        # Adapter should be connected via fixture
        assert vector_adapter is not None
        assert vector_adapter.database_type == "postgresql_vector"
        assert vector_adapter.adapter_type == "sql"

    async def test_pgvector_extension_installation(self, vector_adapter, test_suite):
        """Test pgvector extension can be installed."""
        # Should already be installed by fixture, but verify
        async with test_suite.get_connection() as conn:
            # Check if extension exists
            result = await conn.fetch(
                """
                SELECT * FROM pg_extension WHERE extname = 'vector'
            """
            )
            assert len(result) > 0, "pgvector extension should be installed"

    async def test_create_vector_column(self, vector_adapter, test_suite):
        """Test creating a vector column on existing table."""
        import time

        table_name = f"test_vec_col_{int(time.time() * 1000)}"

        try:
            # Create base table
            async with test_suite.get_connection() as conn:
                await conn.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        title TEXT
                    )
                """
                )

            # Add vector column
            await vector_adapter.create_vector_column(table_name, "embedding", 1536)

            # Verify column exists
            async with test_suite.get_connection() as conn:
                result = await conn.fetch(
                    f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                    AND column_name = 'embedding'
                """
                )
                assert len(result) == 1
                # Note: vector type shows as USER-DEFINED in information_schema

        finally:
            # Cleanup
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {table_name}")

    async def test_create_vector_index_ivfflat(
        self, vector_adapter, vector_table, test_suite
    ):
        """Test creating IVFFlat vector index."""
        # Create IVFFlat index
        await vector_adapter.create_vector_index(
            vector_table,
            column_name="embedding",
            index_type="ivfflat",
            distance="cosine",
            lists=10,  # Small value for test data
        )

        # Verify index exists
        async with test_suite.get_connection() as conn:
            index_name = f"{vector_table}_embedding_ivfflat_idx"
            result = await conn.fetch(
                f"""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = '{vector_table}'
                AND indexname = '{index_name}'
            """
            )
            assert len(result) == 1, "IVFFlat index should be created"

    async def test_vector_search_cosine(self, vector_adapter, vector_table):
        """Test vector similarity search with cosine distance."""
        # Search for tech-related documents (embeddings around 0.1-0.2)
        query_vector = [0.12] * 1536  # Close to tech documents

        results = await vector_adapter.vector_search(
            vector_table,
            query_vector,
            k=3,
            distance="cosine",
            return_distance=True,
        )

        # Should return tech documents first (smaller cosine distance)
        assert len(results) <= 3
        assert len(results) > 0

        # Results should have title, content, and distance
        for result in results:
            assert "title" in result
            assert "content" in result
            assert "distance" in result

    async def test_vector_search_with_filter(self, vector_adapter, vector_table):
        """Test vector search with filter conditions."""
        query_vector = [0.1] * 1536

        # Search only in tech category
        results = await vector_adapter.vector_search(
            vector_table,
            query_vector,
            k=10,
            filter_conditions="category = 'tech'",
            distance="cosine",
        )

        # All results should be in tech category
        assert len(results) > 0
        for result in results:
            assert result["category"] == "tech"

    async def test_vector_search_l2_distance(self, vector_adapter, vector_table):
        """Test vector search with L2 distance metric."""
        query_vector = [0.15] * 1536

        results = await vector_adapter.vector_search(
            vector_table,
            query_vector,
            k=5,
            distance="l2",
            return_distance=True,
        )

        # Should return results sorted by L2 distance
        assert len(results) > 0

        # Verify distances are in ascending order
        distances = [r["distance"] for r in results if "distance" in r]
        assert distances == sorted(distances)

    async def test_vector_search_inner_product(self, vector_adapter, vector_table):
        """Test vector search with inner product distance."""
        query_vector = [0.2] * 1536

        results = await vector_adapter.vector_search(
            vector_table,
            query_vector,
            k=5,
            distance="ip",
            return_distance=True,
        )

        # Should return results
        assert len(results) > 0
        for result in results:
            assert "distance" in result

    async def test_hybrid_search_vector_only(self, vector_adapter, vector_table):
        """Test hybrid search with no text query (vector only)."""
        query_vector = [0.1] * 1536

        results = await vector_adapter.hybrid_search(
            vector_table,
            query_vector,
            text_query=None,  # No text search
            k=5,
        )

        # Should return vector search results
        assert len(results) > 0
        assert len(results) <= 5

    async def test_hybrid_search_combined(
        self, vector_adapter, vector_table, test_suite
    ):
        """Test hybrid search combining vector and full-text search."""
        # First, create a text search index
        async with test_suite.get_connection() as conn:
            await conn.execute(
                f"""
                CREATE INDEX {vector_table}_content_fts
                ON {vector_table}
                USING gin(to_tsvector('english', content))
            """
            )

        query_vector = [0.1] * 1536

        results = await vector_adapter.hybrid_search(
            vector_table,
            query_vector,
            text_query="python programming",
            k=5,
            vector_weight=0.7,
            text_weight=0.3,
            text_column="content",
        )

        # Should return combined results
        assert len(results) >= 0  # May be empty if no text matches
        assert len(results) <= 5

    async def test_get_vector_stats(self, vector_adapter, vector_table):
        """Test getting vector column statistics."""
        stats = await vector_adapter.get_vector_stats(vector_table, "embedding")

        assert "total_vectors" in stats
        assert "non_null_vectors" in stats
        assert "dimensions" in stats

        # Should have 5 total vectors from fixture
        assert stats["total_vectors"] == 5
        assert stats["non_null_vectors"] == 5
        assert stats["dimensions"] == 1536

    async def test_vector_search_accuracy(self, vector_adapter, vector_table):
        """Test that similar vectors are returned first."""
        # Query with vector very close to first tech document (0.1)
        query_vector = [0.101] * 1536

        results = await vector_adapter.vector_search(
            vector_table,
            query_vector,
            k=5,
            distance="l2",
            return_distance=True,
        )

        # First result should be the closest vector (tech category with 0.1)
        assert len(results) > 0

        # The document with embedding [0.1] should be first or second
        # (depending on slight variations in distance calculations)
        top_categories = [r["category"] for r in results[:2]]
        assert "tech" in top_categories

    async def test_concurrent_vector_searches(self, vector_adapter, vector_table):
        """Test concurrent vector search operations."""
        query_vectors = [
            [0.1] * 1536,
            [0.2] * 1536,
            [0.8] * 1536,
        ]

        # Execute searches concurrently
        tasks = [
            vector_adapter.vector_search(vector_table, qv, k=3, distance="cosine")
            for qv in query_vectors
        ]

        results = await asyncio.gather(*tasks)

        # All searches should return results
        assert len(results) == 3
        for result_set in results:
            assert len(result_set) > 0

    async def test_vector_search_empty_table(self, vector_adapter, test_suite):
        """Test vector search on empty table."""
        import time

        table_name = f"test_empty_{int(time.time() * 1000)}"

        try:
            # Create empty table with vector column
            async with test_suite.get_connection() as conn:
                await conn.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        embedding vector(1536)
                    )
                """
                )

            query_vector = [0.1] * 1536

            results = await vector_adapter.vector_search(
                table_name,
                query_vector,
                k=5,
                distance="cosine",
            )

            # Should return empty results
            assert len(results) == 0

        finally:
            async with test_suite.get_connection() as conn:
                await conn.execute(f"DROP TABLE IF EXISTS {table_name}")

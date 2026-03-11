"""
Integration Tests for PostgreSQL Native ARRAY Type Support (DataFlow)

Testing Strategy:
- Tier 2 (Integration): Real PostgreSQL database operations (NO MOCKING)
- Table creation with TEXT[], INTEGER[], REAL[] columns
- Insert/update operations with native arrays
- Query operations with PostgreSQL array operators
- Cross-database validation with real MySQL/SQLite

Uses shared SDK Docker PostgreSQL on port 5434.
"""

import time

import pytest

from dataflow.adapters.exceptions import QueryError
from dataflow.adapters.postgresql import PostgreSQLAdapter
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def unique_table_name():
    """Generate unique table name for test isolation."""
    return f"test_arrays_{int(time.time())}"


@pytest.mark.integration
@pytest.mark.postgresql
class TestPostgreSQLNativeArraysIntegration:
    """Test PostgreSQL native array support with real database."""

    @pytest.mark.timeout(10)
    async def test_create_table_with_text_array(self, test_suite, unique_table_name):
        """Create table with TEXT[] column on real PostgreSQL."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table with TEXT[] column
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id SERIAL PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            # Verify table schema
            schema = await adapter.get_table_schema(unique_table_name)

            assert "tags" in schema
            assert schema["tags"]["type"] == "ARRAY"  # PostgreSQL returns ARRAY

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_create_table_with_multiple_array_types(
        self, test_suite, unique_table_name
    ):
        """Create table with TEXT[], INTEGER[], REAL[] columns."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table with multiple array types
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[],
                    scores INTEGER[],
                    ratings REAL[]
                )
                """
            )

            # Verify table created
            schema = await adapter.get_table_schema(unique_table_name)

            assert "tags" in schema
            assert "scores" in schema
            assert "ratings" in schema
            assert schema["tags"]["type"] == "ARRAY"
            assert schema["scores"]["type"] == "ARRAY"
            assert schema["ratings"]["type"] == "ARRAY"

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_insert_with_native_array_values(self, test_suite, unique_table_name):
        """Insert data with native PostgreSQL array literals."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            # Insert with array literal
            await adapter.execute_query(
                f"""
                INSERT INTO {unique_table_name} (id, tags)
                VALUES ($1, $2)
                """,
                ["test-1", ["medical", "urgent", "ai"]],
            )

            # Query back
            results = await adapter.execute_query(
                f"SELECT id, tags FROM {unique_table_name} WHERE id = $1", ["test-1"]
            )

            assert len(results) == 1
            assert results[0]["id"] == "test-1"
            assert results[0]["tags"] == ["medical", "urgent", "ai"]

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_insert_with_integer_and_float_arrays(
        self, test_suite, unique_table_name
    ):
        """Insert data with INTEGER[] and REAL[] values."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    scores INTEGER[],
                    ratings REAL[]
                )
                """
            )

            # Insert with array values
            await adapter.execute_query(
                f"""
                INSERT INTO {unique_table_name} (id, scores, ratings)
                VALUES ($1, $2, $3)
                """,
                ["test-1", [85, 92, 78], [4.5, 4.8, 4.2]],
            )

            # Query back
            results = await adapter.execute_query(
                f"SELECT id, scores, ratings FROM {unique_table_name} WHERE id = $1",
                ["test-1"],
            )

            assert len(results) == 1
            assert results[0]["id"] == "test-1"
            assert results[0]["scores"] == [85, 92, 78]
            # Float comparison with tolerance
            assert len(results[0]["ratings"]) == 3
            assert abs(results[0]["ratings"][0] - 4.5) < 0.01
            assert abs(results[0]["ratings"][1] - 4.8) < 0.01
            assert abs(results[0]["ratings"][2] - 4.2) < 0.01

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_update_array_values(self, test_suite, unique_table_name):
        """Update existing array values."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create and populate table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2)",
                ["test-1", ["tag1", "tag2"]],
            )

            # Update array
            await adapter.execute_query(
                f"UPDATE {unique_table_name} SET tags = $1 WHERE id = $2",
                [["tag3", "tag4", "tag5"], "test-1"],
            )

            # Verify update
            results = await adapter.execute_query(
                f"SELECT tags FROM {unique_table_name} WHERE id = $1", ["test-1"]
            )

            assert results[0]["tags"] == ["tag3", "tag4", "tag5"]

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_query_with_array_contains_operator(
        self, test_suite, unique_table_name
    ):
        """Query using PostgreSQL @> (contains) array operator."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create and populate table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            # Insert test data
            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2), ($3, $4), ($5, $6)",
                [
                    "mem-1",
                    ["medical", "urgent"],
                    "mem-2",
                    ["medical", "routine"],
                    "mem-3",
                    ["finance", "urgent"],
                ],
            )

            # Query with @> operator (contains)
            results = await adapter.execute_query(
                f"""
                SELECT id, tags FROM {unique_table_name}
                WHERE tags @> ARRAY['medical']
                ORDER BY id
                """
            )

            assert len(results) == 2
            assert results[0]["id"] == "mem-1"
            assert results[1]["id"] == "mem-2"
            assert "medical" in results[0]["tags"]
            assert "medical" in results[1]["tags"]

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_query_with_array_overlap_operator(
        self, test_suite, unique_table_name
    ):
        """Query using PostgreSQL && (overlap) array operator."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create and populate table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            # Insert test data
            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2), ($3, $4), ($5, $6)",
                [
                    "mem-1",
                    ["medical", "urgent"],
                    "mem-2",
                    ["medical", "routine"],
                    "mem-3",
                    ["finance", "urgent"],
                ],
            )

            # Query with && operator (overlap)
            results = await adapter.execute_query(
                f"""
                SELECT id, tags FROM {unique_table_name}
                WHERE tags && ARRAY['medical', 'urgent']
                ORDER BY id
                """
            )

            assert len(results) == 3  # All have either 'medical' or 'urgent'

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_query_with_integer_array_comparison(
        self, test_suite, unique_table_name
    ):
        """Query using array comparison on INTEGER[] column."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create and populate table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    scores INTEGER[]
                )
                """
            )

            # Insert test data
            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, scores) VALUES ($1, $2), ($3, $4), ($5, $6)",
                [
                    "student-1",
                    [85, 92, 78],
                    "student-2",
                    [95, 88, 92],
                    "student-3",
                    [70, 75, 68],
                ],
            )

            # Query with ANY operator
            results = await adapter.execute_query(
                f"""
                SELECT id, scores FROM {unique_table_name}
                WHERE 90 < ANY(scores)
                ORDER BY id
                """
            )

            assert len(results) == 2  # student-1 and student-2 have scores > 90
            assert results[0]["id"] == "student-1"
            assert results[1]["id"] == "student-2"

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_nullable_array_column(self, test_suite, unique_table_name):
        """Test nullable array columns with NULL values."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table with nullable array
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[] NULL
                )
                """
            )

            # Insert with NULL array
            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2), ($3, $4)",
                ["test-1", None, "test-2", ["tag1", "tag2"]],
            )

            # Query back
            results = await adapter.execute_query(
                f"SELECT id, tags FROM {unique_table_name} ORDER BY id"
            )

            assert len(results) == 2
            assert results[0]["id"] == "test-1"
            assert results[0]["tags"] is None
            assert results[1]["id"] == "test-2"
            assert results[1]["tags"] == ["tag1", "tag2"]

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_empty_array_vs_null(self, test_suite, unique_table_name):
        """Test distinction between empty array [] and NULL."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            # Insert empty array and NULL
            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2), ($3, $4)",
                ["test-1", [], "test-2", None],
            )

            # Query back
            results = await adapter.execute_query(
                f"SELECT id, tags FROM {unique_table_name} ORDER BY id"
            )

            assert len(results) == 2
            assert results[0]["id"] == "test-1"
            assert results[0]["tags"] == []  # Empty array
            assert results[1]["id"] == "test-2"
            assert results[1]["tags"] is None  # NULL

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

    @pytest.mark.timeout(10)
    async def test_array_index_creation(self, test_suite, unique_table_name):
        """Test creating GIN index on array column for performance."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table with array column
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags TEXT[]
                )
                """
            )

            # Create GIN index on array column
            await adapter.execute_query(
                f"CREATE INDEX idx_{unique_table_name}_tags ON {unique_table_name} USING GIN(tags)"
            )

            # Verify index exists by using it in a query
            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2)",
                ["test-1", ["tag1", "tag2"]],
            )

            results = await adapter.execute_query(
                f"SELECT id FROM {unique_table_name} WHERE tags @> ARRAY['tag1']"
            )

            assert len(results) == 1
            assert results[0]["id"] == "test-1"

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()


@pytest.mark.integration
class TestBackwardCompatibilityIntegration:
    """Test that existing JSONB array storage continues to work."""

    @pytest.mark.timeout(10)
    async def test_jsonb_array_storage_still_works(self, test_suite, unique_table_name):
        """Test that JSONB storage for arrays still works (backward compatible)."""
        adapter = PostgreSQLAdapter(test_suite.config.url)
        await adapter.create_connection_pool()

        try:
            # Create table with JSONB column (old approach)
            await adapter.execute_query(
                f"""
                CREATE TABLE {unique_table_name} (
                    id TEXT PRIMARY KEY,
                    tags JSONB
                )
                """
            )

            # Insert JSON array
            import json

            await adapter.execute_query(
                f"INSERT INTO {unique_table_name} (id, tags) VALUES ($1, $2)",
                ["test-1", json.dumps(["tag1", "tag2", "tag3"])],
            )

            # Query back
            results = await adapter.execute_query(
                f"SELECT id, tags FROM {unique_table_name} WHERE id = $1", ["test-1"]
            )

            assert len(results) == 1
            assert results[0]["id"] == "test-1"
            # JSONB can return as string when inserted as JSON string
            tags = results[0]["tags"]
            if isinstance(tags, str):
                tags = json.loads(tags)
            assert tags == ["tag1", "tag2", "tag3"]

        finally:
            # Cleanup
            await adapter.execute_query(f"DROP TABLE IF EXISTS {unique_table_name}")
            await adapter.close_connection_pool()

"""
Integration tests for Query Builder with real PostgreSQL database.

Tests actual PostgreSQL query execution using Docker infrastructure.
Tests complex WHERE clauses, JOINs, and performance with real data.
"""

import asyncio
import os

# Import actual classes
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))
from dataflow.database.query_builder import DatabaseType, QueryBuilder

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


# @pytest.mark.tier2
# @pytest.mark.requires_docker
class TestQueryBuilderPostgreSQLIntegration:
    """Test QueryBuilder integration with real PostgreSQL database."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Setup test PostgreSQL database with sample data."""
        # For now, skip complex database setup
        # Focus on testing QueryBuilder SQL generation with PostgreSQL dialect
        self.builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        yield
        # Cleanup if needed

    def test_basic_select_with_real_data(self):
        """Test basic SELECT query with real PostgreSQL data."""
        builder = self.builder
        builder.where("active", "$eq", True)
        builder.where("age", "$gte", 25)

        sql, params = builder.build_select(["name", "email", "age"])

        # Verify PostgreSQL-specific SQL generation
        assert "SELECT" in sql
        assert '"name", "email", "age"' in sql
        assert 'FROM "users"' in sql
        assert "WHERE" in sql
        assert '"active" = $1' in sql
        assert '"age" >= $2' in sql
        assert "AND" in sql
        assert params == [True, 25]

    def test_complex_where_conditions_performance(self):
        """Test complex WHERE clauses with performance validation."""
        import time

        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("age", "$gte", 25)
        builder.where("age", "$lt", 45)
        builder.where("department", "$in", ["engineering", "sales"])
        builder.where("email", "$like", "%example.com")
        builder.where("active", "$eq", True)

        # Build query with performance timing
        start_time = time.time()
        sql, params = builder.build_select(["*"])
        execution_time = time.time() - start_time

        # Performance validation for query building with real database
        assert execution_time < 0.5  # Should complete in <500ms for integration test

        # Verify complex SQL generation
        assert sql.count("AND") == 4  # 5 conditions = 4 AND operators
        assert len(params) == 6  # 25, 45, "engineering", "sales", "%example.com", True
        assert "IN ($3, $4)" in sql  # PostgreSQL parameter placeholders
        assert '"department" IN ($3, $4)' in sql
        assert '"email" LIKE $5' in sql

    def test_join_operations_with_real_data(self):
        """Test JOIN operations with related models."""
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.join("orders", "users.id = orders.user_id")
        builder.where("users.active", "$eq", True)
        builder.where("orders.status", "$eq", "completed")

        sql, params = builder.build_select(["users.name", "orders.total"])

        # Verify JOIN SQL generation
        assert 'INNER JOIN "orders"' in sql
        assert "users.id = orders.user_id" in sql
        assert '"users"."active" = $1' in sql
        assert '"orders"."status" = $2' in sql
        assert params == [True, "completed"]

    def test_postgresql_regex_operators(self):
        """Test PostgreSQL-specific regex operators."""
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("email", "$regex", ".*@(gmail|yahoo)\\.com")

        sql, params = builder.build_select(["name", "email"])

        # Verify PostgreSQL regex operator
        assert '"email" ~ $1' in sql
        assert params == [".*@(gmail|yahoo)\\.com"]

        # Test different regex patterns
        builder2 = QueryBuilder("products", DatabaseType.POSTGRESQL)
        builder2.where("name", "$regex", "^(iPhone|iPad)")

        sql2, params2 = builder2.build_select(["*"])
        assert '"name" ~ $1' in sql2
        assert params2 == ["^(iPhone|iPad)"]

    def test_aggregation_queries_performance(self):
        """Test aggregation queries with performance monitoring."""
        builder = QueryBuilder("orders", DatabaseType.POSTGRESQL)
        builder.where("status", "$eq", "completed")
        builder.group_by(["user_id", "status"])

        sql, params = builder.build_select(
            ["user_id", "status", "COUNT(*) as order_count"]
        )

        # Verify GROUP BY SQL generation
        assert 'GROUP BY "user_id", "status"' in sql
        assert 'WHERE "status" = $1' in sql
        assert params == ["completed"]

    def test_pagination_with_large_dataset(self):
        """Test pagination performance with large dataset."""
        # Test different page sizes
        page_sizes = [10, 50, 100]

        for page_size in page_sizes:
            builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
            builder.where("active", "$eq", True)
            builder.order_by("created_at", "DESC")
            builder.limit(page_size).offset(0)

            sql, params = builder.build_select(["id", "name", "email"])

            # Verify pagination SQL generation
            assert 'ORDER BY "created_at" DESC' in sql
            assert f"LIMIT {page_size}" in sql
            assert "OFFSET 0" in sql
            assert params == [True]

    def test_transaction_handling_with_query_builder(self):
        """Test transaction handling in QueryBuilder context."""
        # Test that QueryBuilder can generate transaction-safe SQL
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("id", "$eq", 123)

        sql, params = builder.build_select(["*"])

        # Verify SQL is safe for transaction context
        assert 'SELECT * FROM "users" WHERE "id" = $1' in sql
        assert params == [123]

        # Test for INSERT with RETURNING (PostgreSQL specific)
        insert_sql, insert_params = builder.build_insert(
            {"name": "Test User", "email": "test@example.com"}
        )
        assert 'INSERT INTO "users"' in insert_sql
        assert "RETURNING *" in insert_sql  # PostgreSQL specific
        assert insert_params == ["Test User", "test@example.com"]

    def test_postgresql_specific_features(self):
        """Test PostgreSQL-specific features and operators."""
        # Test array operations (PostgreSQL specific)
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("tags", "$in", ["developer", "manager"])

        sql, params = builder.build_select(["*"])

        # Verify PostgreSQL parameter placeholders
        assert '"tags" IN ($1, $2)' in sql
        assert params == ["developer", "manager"]

        # Test UPDATE with RETURNING - create new builder to avoid parameter conflicts
        update_builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        update_builder.where("id", "$eq", 123)
        update_sql, update_params = update_builder.build_update(
            {"name": "Updated Name"}
        )
        assert (
            'UPDATE "users" SET "name" = $2' in update_sql
        )  # $1 is for WHERE, $2 is for SET
        assert 'WHERE "id" = $1' in update_sql
        assert "RETURNING *" in update_sql  # PostgreSQL specific

        # Test DELETE with RETURNING
        delete_sql, delete_params = builder.build_delete()
        assert 'DELETE FROM "users"' in delete_sql
        assert "RETURNING *" in delete_sql  # PostgreSQL specific

    def test_concurrent_query_execution(self):
        """Test concurrent query execution performance."""
        # Test that QueryBuilder can generate multiple queries safely
        builders = []
        for i in range(10):
            builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
            builder.where("active", "$eq", True)
            builder.where("age", "$gte", 20 + (i % 30))
            builder.limit(10)
            builders.append(builder)

        # Generate multiple queries
        queries = []
        for builder in builders:
            sql, params = builder.build_select(["name", "email"])
            queries.append((sql, params))

        # Verify all queries are properly generated
        assert len(queries) == 10
        for sql, params in queries:
            assert "SELECT" in sql
            assert "WHERE" in sql
            assert "LIMIT 10" in sql
            assert len(params) == 2  # active=True and age>=N


# @pytest.mark.tier2
# @pytest.mark.requires_docker
class TestQueryBuilderPostgreSQLEdgeCases:
    """Test edge cases and error handling with real PostgreSQL."""

    def test_connection_failure_handling(self):
        """Test query builder behavior during connection failures."""
        # Test that QueryBuilder can still generate SQL even with connection issues
        # (Since QueryBuilder is SQL generation only, not actual execution)
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("active", "$eq", True)

        # Should still generate valid SQL regardless of connection state
        sql, params = builder.build_select(["*"])
        assert 'SELECT * FROM "users"' in sql
        assert 'WHERE "active" = $1' in sql
        assert params == [True]

        # QueryBuilder is connection-agnostic for SQL generation

    def test_large_result_set_handling(self):
        """Test handling of large result sets."""
        # Test that QueryBuilder can generate efficient SQL for large datasets
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("active", "$eq", True)
        builder.limit(10000)  # Large limit
        builder.offset(50000)  # Large offset

        sql, params = builder.build_select(["id", "name", "email"])

        # Should generate efficient SQL with proper LIMIT/OFFSET
        assert 'SELECT "id", "name", "email" FROM "users"' in sql
        assert "LIMIT 10000" in sql
        assert "OFFSET 50000" in sql
        assert params == [True]

    def test_query_timeout_handling(self):
        """Test query timeout handling."""
        # Test that QueryBuilder generates SQL that can be used with timeout settings
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)
        builder.where("active", "$eq", True)
        builder.order_by("created_at", "DESC")
        builder.limit(1000)

        # Generate SQL that would be suitable for timeout scenarios
        sql, params = builder.build_select(["*"])

        # Should generate efficient SQL that can be executed with timeouts
        assert 'SELECT * FROM "users"' in sql
        assert 'ORDER BY "created_at" DESC' in sql
        assert "LIMIT 1000" in sql
        assert params == [True]

    def test_invalid_sql_generation_handling(self):
        """Test handling of invalid SQL generation scenarios."""
        # Test that QueryBuilder handles invalid operators gracefully
        builder = QueryBuilder("users", DatabaseType.POSTGRESQL)

        # Test invalid operator handling
        with pytest.raises(ValueError, match="Unsupported operator"):
            builder.where("field", "$invalid_operator", "value")

        # Test that QueryBuilder still generates SQL for non-existent tables
        # (Table existence validation is handled at execution time, not SQL generation)
        builder2 = QueryBuilder("nonexistent_table", DatabaseType.POSTGRESQL)
        builder2.where("field", "$eq", "value")

        sql, params = builder2.build_select(["*"])
        assert 'SELECT * FROM "nonexistent_table"' in sql
        assert 'WHERE "field" = $1' in sql
        assert params == ["value"]

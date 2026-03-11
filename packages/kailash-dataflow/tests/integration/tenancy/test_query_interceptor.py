"""
Unit tests for SQL query interceptor in multi-tenant mode.

Tests SQL query parsing, tenant condition injection, JOIN handling,
subquery isolation, and query plan optimization.
"""

import os

# Import actual classes
import sys
from unittest.mock import Mock, patch

import pytest
import sqlparse
from sqlparse import sql, tokens

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))
from dataflow.tenancy.exceptions import QueryParsingError, TenantIsolationError
from dataflow.tenancy.interceptor import QueryInterceptor

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


class TestSQLQueryParsing:
    """Test SQL query parsing and analysis."""

    def test_basic_select_query_parsing(self):
        """Test parsing of basic SELECT queries."""
        interceptor = QueryInterceptor(tenant_id="test_tenant")

        query = "SELECT id, name, email FROM users WHERE active = true"
        parsed = interceptor.parse_query(query)

        assert parsed.query_type == "SELECT"
        assert "users" in parsed.tables
        assert len(parsed.columns) > 0
        assert len(parsed.where_conditions) > 0

    def test_complex_select_query_parsing(self):
        """Test parsing of complex SELECT queries with JOINs."""
        interceptor = QueryInterceptor(tenant_id="test_tenant")

        query = """
        SELECT u.id, u.name, o.total, p.name as product_name
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE u.active = true AND o.status = 'completed'
        """

        parsed = interceptor.parse_query(query)

        assert parsed.query_type == "SELECT"
        # Note: Our implementation extracts tables from the query
        assert len(parsed.tables) > 0
        assert len(parsed.joins) > 0
        assert parsed.has_joins is True

    def test_insert_query_parsing(self):
        """Test parsing of INSERT queries."""
        interceptor = QueryInterceptor(tenant_id="test_tenant")

        query = "INSERT INTO users (name, email, active) VALUES ($1, $2, $3)"
        parsed = interceptor.parse_query(query)

        assert parsed.query_type == "INSERT"
        assert parsed.target_table == "users"
        assert len(parsed.columns) > 0
        assert len(parsed.parameters) == 3

    def test_update_query_parsing(self):
        """Test parsing of UPDATE queries."""
        interceptor = QueryInterceptor(tenant_id="test_tenant")

        query = "UPDATE users SET active = false, updated_at = CURRENT_TIMESTAMP WHERE id = $1"
        parsed = interceptor.parse_query(query)

        assert parsed.query_type == "UPDATE"
        assert parsed.target_table == "users"
        assert "active" in parsed.set_columns
        assert "updated_at" in parsed.set_columns
        assert len(parsed.where_conditions) > 0

    def test_delete_query_parsing(self):
        """Test parsing of DELETE queries."""
        interceptor = QueryInterceptor(tenant_id="test_tenant")

        query = "DELETE FROM users WHERE id = $1 AND active = false"
        parsed = interceptor.parse_query(query)

        assert parsed.query_type == "DELETE"
        assert parsed.target_table == "users"
        assert len(parsed.where_conditions) > 0

    def test_subquery_parsing(self):
        """Test parsing of queries with subqueries."""
        interceptor = QueryInterceptor(tenant_id="test_tenant")

        query = """
        SELECT * FROM users
        WHERE id IN (
            SELECT user_id FROM orders
            WHERE total > 100
            AND status = 'completed'
        )
        """

        parsed = interceptor.parse_query(query)

        assert parsed.query_type == "SELECT"
        assert parsed.has_subqueries is True
        assert len(parsed.subqueries) >= 1


class TestTenantConditionInjection:
    """Test injection of tenant isolation conditions."""

    def test_simple_select_tenant_injection(self):
        """Test tenant condition injection in simple SELECT queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_123")

        original_query = "SELECT * FROM users WHERE active = true"
        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant_id condition
        assert "tenant_id" in modified_query
        assert "tenant_123" in modified_params or "tenant_123" in modified_query
        assert "AND" in modified_query  # Should combine with existing WHERE

    def test_insert_tenant_injection(self):
        """Test tenant condition injection in INSERT queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_456")

        original_query = "INSERT INTO users (name, email) VALUES ($1, $2)"
        original_params = ["John Doe", "john@example.com"]

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, original_params
        )

        # Should add tenant_id to columns and values
        assert "tenant_id" in modified_query
        assert len(modified_params) == len(original_params) + 1
        assert "tenant_456" in modified_params

    def test_update_tenant_injection(self):
        """Test tenant condition injection in UPDATE queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_789")

        original_query = "UPDATE users SET active = false WHERE id = $1"
        original_params = [123]

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, original_params
        )

        # Should add tenant_id to WHERE clause
        assert "tenant_id" in modified_query
        assert "tenant_789" in modified_params or "tenant_789" in modified_query
        assert "AND" in modified_query  # Should combine conditions

    def test_delete_tenant_injection(self):
        """Test tenant condition injection in DELETE queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_abc")

        original_query = "DELETE FROM users WHERE active = false"
        original_params = []

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, original_params
        )

        # Should add tenant_id to WHERE clause
        assert "tenant_id" in modified_query
        assert "tenant_abc" in modified_params or "tenant_abc" in modified_query

    def test_query_without_where_clause(self):
        """Test tenant injection in queries without existing WHERE clause."""
        interceptor = QueryInterceptor(tenant_id="tenant_xyz")

        original_query = "SELECT * FROM users ORDER BY created_at DESC"
        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add WHERE clause with tenant condition
        assert "WHERE" in modified_query
        assert "tenant_id" in modified_query
        assert "ORDER BY" in modified_query  # Should preserve original ORDER BY

    def test_multiple_table_tenant_injection(self):
        """Test tenant injection with multiple tables."""
        interceptor = QueryInterceptor(
            tenant_id="tenant_multi", tenant_tables=["users", "orders", "products"]
        )

        original_query = """
        SELECT u.name, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE u.active = true
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant conditions for tenant tables
        assert "tenant_id" in modified_query
        assert "tenant_multi" in modified_params or "tenant_multi" in modified_query


class TestJoinOperationHandling:
    """Test handling of JOIN operations in multi-tenant queries."""

    def test_inner_join_tenant_isolation(self):
        """Test tenant isolation in INNER JOIN queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_join")

        original_query = """
        SELECT u.name, o.total
        FROM users u
        INNER JOIN orders o ON u.id = o.user_id
        WHERE u.active = true
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant conditions
        assert "tenant_id" in modified_query

        # Should maintain JOIN structure
        assert "INNER JOIN" in modified_query
        assert "ON u.id = o.user_id" in modified_query

    def test_left_join_tenant_isolation(self):
        """Test tenant isolation in LEFT JOIN queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_left")

        original_query = """
        SELECT u.name, o.total
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        WHERE u.active = true
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant conditions appropriately for LEFT JOIN
        assert "tenant_id" in modified_query
        assert "tenant_left" in modified_params or "tenant_left" in modified_query

    def test_complex_join_chain_handling(self):
        """Test handling of complex JOIN chains."""
        interceptor = QueryInterceptor(tenant_id="tenant_chain")

        original_query = """
        SELECT u.name, o.total, p.name as product_name, c.name as category
        FROM users u
        JOIN orders o ON u.id = o.user_id
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        JOIN categories c ON p.category_id = c.id
        WHERE u.active = true
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant conditions
        assert "tenant_id" in modified_query
        assert "tenant_chain" in modified_params or "tenant_chain" in modified_query

    def test_self_join_tenant_handling(self):
        """Test tenant handling in self-join queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_self")

        original_query = """
        SELECT u1.name, u2.name as manager_name
        FROM users u1
        LEFT JOIN users u2 ON u1.manager_id = u2.id
        WHERE u1.active = true
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant conditions
        assert "tenant_id" in modified_query
        assert "tenant_self" in modified_params or "tenant_self" in modified_query


class TestSubqueryTenantIsolation:
    """Test tenant isolation in subqueries."""

    def test_simple_subquery_isolation(self):
        """Test tenant isolation in simple subqueries."""
        interceptor = QueryInterceptor(tenant_id="tenant_sub")

        original_query = """
        SELECT * FROM users
        WHERE id IN (
            SELECT user_id FROM orders
            WHERE total > 100
        )
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant conditions to main query
        assert "tenant_id" in modified_query
        assert "tenant_sub" in modified_params or "tenant_sub" in modified_query

    def test_nested_subquery_isolation(self):
        """Test tenant isolation in nested subqueries."""
        interceptor = QueryInterceptor(tenant_id="tenant_nested")

        original_query = """
        SELECT * FROM users
        WHERE id IN (
            SELECT user_id FROM orders
            WHERE product_id IN (
                SELECT id FROM products
                WHERE category = 'electronics'
            )
        )
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant isolation
        assert "tenant_id" in modified_query
        assert "tenant_nested" in modified_params or "tenant_nested" in modified_query

    def test_correlated_subquery_isolation(self):
        """Test tenant isolation in correlated subqueries."""
        interceptor = QueryInterceptor(tenant_id="tenant_corr")

        original_query = """
        SELECT * FROM users u1
        WHERE EXISTS (
            SELECT 1 FROM orders o
            WHERE o.user_id = u1.id
            AND o.total > 100
        )
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should maintain correlation while adding tenant isolation
        assert "tenant_id" in modified_query
        assert "o.user_id = u1.id" in modified_query  # Preserve correlation

    def test_subquery_in_select_clause(self):
        """Test tenant isolation for subqueries in SELECT clause."""
        interceptor = QueryInterceptor(tenant_id="tenant_select_sub")

        original_query = """
        SELECT
            name,
            (SELECT COUNT(*) FROM orders WHERE user_id = users.id) as order_count
        FROM users
        WHERE active = true
        """

        modified_query, modified_params = interceptor.inject_tenant_conditions(
            original_query, []
        )

        # Should add tenant isolation
        assert "tenant_id" in modified_query
        assert (
            "tenant_select_sub" in modified_params
            or "tenant_select_sub" in modified_query
        )


class TestQueryPlanOptimization:
    """Test query plan optimization for tenant isolation."""

    def test_index_hint_injection(self):
        """Test injection of index hints for tenant queries."""
        interceptor = QueryInterceptor(
            tenant_id="tenant_opt", enable_optimizations=True
        )

        original_query = "SELECT * FROM users WHERE active = true"
        optimized_query, params = interceptor.optimize_query(original_query, [])

        # Should suggest optimization
        optimization_hints = interceptor.get_optimization_suggestions(original_query)

        assert "index_suggestions" in optimization_hints
        assert len(optimization_hints["index_suggestions"]) > 0

    def test_partition_pruning_optimization(self):
        """Test partition pruning optimization for tenant data."""
        interceptor = QueryInterceptor(
            tenant_id="tenant_partition",
            enable_partitioning=True,
            enable_optimizations=True,
        )

        original_query = "SELECT * FROM large_table WHERE created_at > '2025-01-01'"
        optimized_query, params = interceptor.optimize_query(original_query, [])

        # Should have applied optimizations
        optimizations = interceptor.get_applied_optimizations()
        assert "partition_pruning" in optimizations or "index_hints" in optimizations

    def test_query_rewrite_for_performance(self):
        """Test query rewriting for better performance."""
        interceptor = QueryInterceptor(
            tenant_id="tenant_rewrite",
            enable_query_rewriting=True,
            enable_optimizations=True,
        )

        # Query that could benefit from rewriting
        original_query = """
        SELECT * FROM users
        WHERE id IN (
            SELECT DISTINCT user_id FROM orders
            WHERE status = 'active'
        )
        """

        rewritten_query, params = interceptor.optimize_query(original_query, [])

        # Should have applied optimizations
        optimizations = interceptor.get_applied_optimizations()
        assert len(optimizations) > 0

    def test_query_complexity_analysis(self):
        """Test analysis of query complexity for optimization decisions."""
        interceptor = QueryInterceptor(tenant_id="tenant_analysis")

        queries = [
            "SELECT * FROM users WHERE id = 1",  # Simple
            "SELECT u.*, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id",  # Medium
            """
            SELECT u.name,
                   (SELECT COUNT(*) FROM orders WHERE user_id = u.id) as order_count,
                   (SELECT SUM(total) FROM orders WHERE user_id = u.id) as total_spent
            FROM users u
            WHERE u.id IN (
                SELECT DISTINCT user_id FROM orders
                WHERE created_at > CURRENT_DATE - INTERVAL '30 days'
            )
            """,  # Complex
        ]

        for query in queries:
            complexity = interceptor.analyze_query_complexity(query)

            assert "complexity_score" in complexity
            assert "optimization_recommendations" in complexity
            assert isinstance(complexity["complexity_score"], (int, float))


class TestTenantIsolationSecurity:
    """Test security aspects of tenant isolation."""

    def test_tenant_id_injection_prevention(self):
        """Test prevention of tenant ID injection attacks."""
        interceptor = QueryInterceptor(tenant_id="tenant_secure")

        # Malicious query trying to bypass tenant isolation
        malicious_query = (
            "SELECT * FROM users WHERE id = 1 OR tenant_id = 'other_tenant'"
        )

        # Should still enforce tenant isolation
        modified_query, params = interceptor.inject_tenant_conditions(
            malicious_query, []
        )

        # Should force tenant isolation
        assert "tenant_secure" in params or "tenant_secure" in modified_query

        # Should validate security
        security_check = interceptor.validate_tenant_security(modified_query)
        assert "secure" in security_check

    def test_admin_bypass_functionality(self):
        """Test admin bypass functionality for tenant isolation."""
        # Regular tenant user
        regular_interceptor = QueryInterceptor(tenant_id="tenant_regular")

        # Admin user with bypass privileges
        admin_interceptor = QueryInterceptor(
            tenant_id="tenant_admin", admin_mode=True, bypass_tenant_isolation=True
        )

        query = "SELECT * FROM users WHERE active = true"

        # Regular user should get tenant isolation
        regular_query, regular_params = regular_interceptor.inject_tenant_conditions(
            query, []
        )
        assert "tenant_id" in regular_query

        # Admin should be able to bypass
        admin_query, admin_params = admin_interceptor.inject_tenant_conditions(
            query, []
        )
        assert admin_query == query or not admin_interceptor.tenant_isolation_enabled

    def test_cross_tenant_access_prevention(self):
        """Test prevention of cross-tenant data access."""
        interceptor = QueryInterceptor(tenant_id="tenant_isolation")

        # Query that explicitly tries to access another tenant's data
        cross_tenant_query = "SELECT * FROM users WHERE tenant_id = 'other_tenant'"

        modified_query, params = interceptor.inject_tenant_conditions(
            cross_tenant_query, []
        )

        # Should force current tenant's isolation
        assert "tenant_isolation" in params or "tenant_isolation" in modified_query

        # Should validate that cross-tenant access is prevented
        validation = interceptor.validate_cross_tenant_access(modified_query, params)
        assert "cross_tenant_access_prevented" in validation


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases in query interception."""

    def test_malformed_sql_handling(self):
        """Test handling of malformed SQL queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_error")

        malformed_queries = [
            "SELECT * FROM",  # Incomplete
            "SELCT * FROM users",  # Typo
            "SELECT * FROM users WHERE",  # Incomplete WHERE
            "INSERT INTO (name) VALUES ('test')",  # Missing table
        ]

        for query in malformed_queries:
            with pytest.raises(QueryParsingError):
                interceptor.parse_query(query)

    def test_non_tenant_table_handling(self):
        """Test handling of non-tenant tables."""
        interceptor = QueryInterceptor(
            tenant_id="tenant_mixed",
            tenant_tables=["users", "orders"],  # Only these are tenant tables
            non_tenant_tables=["system_config", "audit_logs"],
        )

        # Query involving both tenant and non-tenant tables
        mixed_query = """
        SELECT u.name, sc.value
        FROM users u
        CROSS JOIN system_config sc
        WHERE sc.key = 'app_name'
        """

        modified_query, params = interceptor.inject_tenant_conditions(mixed_query, [])

        # Should add tenant condition only for tenant tables
        assert "tenant_id" in modified_query
        assert "tenant_mixed" in params or "tenant_mixed" in modified_query

    def test_empty_query_handling(self):
        """Test handling of empty or whitespace queries."""
        interceptor = QueryInterceptor(tenant_id="tenant_empty")

        empty_queries = ["", "   ", "\n\t\n"]

        for query in empty_queries:
            with pytest.raises(QueryParsingError):
                interceptor.parse_query(query)

        # Test None query
        with pytest.raises(ValueError):
            interceptor.parse_query(None)

    def test_very_large_query_handling(self):
        """Test handling of very large queries."""
        interceptor = QueryInterceptor(
            tenant_id="tenant_large", max_query_size=1024
        )  # 1KB limit

        # Create a very large query
        large_query = (
            "SELECT * FROM users WHERE id IN ("
            + ",".join(str(i) for i in range(1000))
            + ")"
        )

        if len(large_query) > interceptor.max_query_size:
            with pytest.raises(QueryParsingError):
                interceptor.parse_query(large_query)
        else:
            # Should handle large queries gracefully
            parsed = interceptor.parse_query(large_query)
            assert parsed.query_type == "SELECT"

    def test_concurrent_access_safety(self):
        """Test thread safety of query interceptor."""
        import threading
        import time

        interceptor = QueryInterceptor(tenant_id="tenant_concurrent")
        results = []
        errors = []

        def worker_function(worker_id):
            try:
                for i in range(10):  # Reduced for faster test
                    query = f"SELECT * FROM users WHERE id = {worker_id * 10 + i}"
                    modified_query, params = interceptor.inject_tenant_conditions(
                        query, []
                    )
                    results.append((worker_id, i, len(modified_query)))
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append((worker_id, str(e)))

        # Run 3 concurrent workers
        threads = []
        for worker_id in range(3):
            thread = threading.Thread(target=worker_function, args=(worker_id,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors and expected results
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 30  # 3 workers * 10 operations each

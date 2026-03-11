"""
Integration tests for AsyncSQL node functionality.

Tests the integration between DataFlow and AsyncSQL nodes for asynchronous
database operations, including connection management and query execution.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite

# Import DataFlow and workflow components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestAsyncSQLIntegration:
    """Test AsyncSQL node integration with DataFlow."""

    @pytest.fixture
    def postgres_config(self, test_suite):
        """Get PostgreSQL configuration for AsyncSQL nodes."""
        return {
            "connection_string": test_suite.config.url,
            "dialect": "postgresql",
        }

    def test_asyncsql_node_availability(self, test_suite):
        """Test that AsyncSQL nodes are available in workflow."""
        workflow = WorkflowBuilder()

        # Test AsyncSQL node can be added with proper PostgreSQL config
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "async_query",
            {
                "query": "SELECT 1 as test_value",
                "parameters": [],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        # Build workflow
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 1

    def test_asyncsql_with_dataflow_models(self, test_suite, postgres_config):
        """Test AsyncSQL nodes working with DataFlow generated models."""
        # Use PostgreSQL for DataFlow (required for alpha)
        db = DataFlow(
            test_suite.config.url, auto_migrate=True, existing_schema_mode=False
        )

        @db.model
        class AsyncTestModel:
            name: str
            email: str
            active: bool = True

        workflow = WorkflowBuilder()

        # Use AsyncSQL to query the model's table
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "async_select",
            {
                "query": "SELECT * FROM async_test_models WHERE active = $1",
                "parameters": [True],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "fetch_mode": "all",
            },
        )

        # Use AsyncSQL for insert
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "async_insert",
            {
                "query": "INSERT INTO async_test_models (name, email, active) VALUES ($1, $2, $3)",
                "parameters": ["John Doe", "john@example.com", True],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "return_lastrowid": True,
            },
        )

        workflow.add_connection("async_insert", "output", "async_select", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 2

    def test_asyncsql_parameter_types(self, test_suite):
        """Test AsyncSQL with different parameter types."""
        workflow = WorkflowBuilder()

        # Test with various parameter types
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "typed_query",
            {
                "query": """
                SELECT * FROM test_table
                WHERE name = $1 AND age > $2 AND created_at > $3 AND active = $4
            """,
                "parameters": ["John", 25, "2023-01-01", True],
                "parameter_types": {
                    "name": "TEXT",
                    "age": "INTEGER",
                    "created_at": "TEXT",
                    "active": "BOOLEAN",
                },
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_transaction_handling(self, test_suite):
        """Test AsyncSQL with transaction support."""
        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "begin_transaction",
            {
                "query": "BEGIN",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "auto_commit": False,
            },
        )

        # Insert within transaction
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "transactional_insert",
            {
                "query": "INSERT INTO transactions (amount, type) VALUES ($1, $2)",
                "parameters": [100.0, "deposit"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "auto_commit": False,
            },
        )

        # Commit transaction
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "commit_transaction",
            {
                "query": "COMMIT",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        # Connect transaction flow
        workflow.add_connection(
            "begin_transaction", "output", "transactional_insert", "input"
        )
        workflow.add_connection(
            "transactional_insert", "output", "commit_transaction", "input"
        )

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_asyncsql_connection_pooling(self, test_suite):
        """Test AsyncSQL with connection pool configuration."""
        workflow = WorkflowBuilder()

        # Configure connection pool
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "pooled_query",
            {
                "query": "SELECT COUNT(*) as count FROM users",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "pool_config": {
                    "min_size": 1,
                    "max_size": 10,
                    "max_queries": 50000,
                    "max_inactive_connection_lifetime": 300,
                },
            },
        )

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_error_handling(self, test_suite):
        """Test AsyncSQL error handling scenarios."""
        workflow = WorkflowBuilder()

        # Test invalid SQL
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "invalid_sql",
            {
                "query": "INVALID SQL STATEMENT",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "error_handling": "continue",
                "default_result": [],
            },
        )

        # Test connection error
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "connection_error",
            {
                "query": "SELECT 1",
                "connection_string": "postgresql://invalid:invalid@nonexistent:5432/invalid_db",
                "dialect": "postgresql",
                "error_handling": "retry",
                "retry_attempts": 3,
                "retry_delay": 1,
            },
        )

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_with_dataflow_enterprise_features(self, test_suite):
        """Test AsyncSQL integration with DataFlow enterprise features."""
        # Use PostgreSQL for enterprise features that require schema discovery
        db = DataFlow(test_suite.config.url, multi_tenant=True, audit_logging=True)

        @db.model
        class EnterpriseModel:
            name: str
            data: str
            tenant_id: str

            __dataflow__ = {"multi_tenant": True, "audit_log": True}

        workflow = WorkflowBuilder()

        # Multi-tenant AsyncSQL query
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "tenant_query",
            {
                "query": "SELECT * FROM enterprise_models WHERE tenant_id = $1",
                "parameters": ["tenant_123"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "tenant_isolation": True,
            },
        )

        # Audit log query
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "audit_query",
            {
                "query": "SELECT * FROM audit_log WHERE table_name = $1 AND tenant_id = $2",
                "parameters": ["enterprise_models", "tenant_123"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        workflow.add_connection("tenant_query", "output", "audit_query", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_bulk_operations(self, test_suite):
        """Test AsyncSQL with bulk operations."""
        workflow = WorkflowBuilder()

        # Bulk insert using AsyncSQL
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "bulk_insert",
            {
                "query": "INSERT INTO bulk_test (name, value) VALUES ($1, $2)",
                "parameters_batch": [
                    ["Item 1", 100],
                    ["Item 2", 200],
                    ["Item 3", 300],
                    ["Item 4", 400],
                    ["Item 5", 500],
                ],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "execute_many": True,
            },
        )

        # Bulk update
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "bulk_update",
            {
                "query": "UPDATE bulk_test SET value = value * 1.1 WHERE name LIKE $1",
                "parameters": ["%Item%"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        workflow.add_connection("bulk_insert", "output", "bulk_update", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_json_handling(self, test_suite):
        """Test AsyncSQL with JSON data handling."""
        workflow = WorkflowBuilder()

        # Insert JSON data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "json_insert",
            {
                "query": "INSERT INTO json_test (data) VALUES ($1)",
                "parameters": ['{"key": "value", "nested": {"count": 42}}'],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "json_serialization": True,
            },
        )

        # Query with JSON operations
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "json_query",
            {
                "query": "SELECT data->>'key' as key_value FROM json_test WHERE data->'nested'->>'count' = $1",
                "parameters": ["42"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "json_deserialization": True,
            },
        )

        workflow.add_connection("json_insert", "output", "json_query", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_streaming_results(self, test_suite):
        """Test AsyncSQL with streaming results for large datasets."""
        workflow = WorkflowBuilder()

        # Stream large result set
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "streaming_query",
            {
                "query": "SELECT * FROM large_table ORDER BY id",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "fetch_mode": "iterator",
                "chunk_size": 1000,
                "stream_results": True,
            },
        )

        # Process streamed data
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "process_stream",
            {
                "query": "INSERT INTO processed_data (source_id, processed_at) VALUES ($1, $2)",
                "parameters": ["${streaming_query.id}", "${current_timestamp}"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "batch_processing": True,
            },
        )

        workflow.add_connection("streaming_query", "output", "process_stream", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_performance_monitoring(self, test_suite):
        """Test AsyncSQL with performance monitoring."""
        workflow = WorkflowBuilder()

        # Monitored query execution
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "monitored_query",
            {
                "query": "SELECT COUNT(*) FROM performance_test",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "performance_monitoring": True,
                "slow_query_threshold": 1000,  # milliseconds
                "track_execution_time": True,
                "log_query_plans": True,
            },
        )

        # Performance analysis
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "performance_analysis",
            {
                "query": """
                SELECT
                    query_text,
                    avg_execution_time,
                    total_executions
                FROM query_performance_log
                WHERE execution_time > $1
            """,
                "parameters": [1000],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        workflow.add_connection(
            "monitored_query", "output", "performance_analysis", "input"
        )

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_with_multiple_databases(self, test_suite):
        """Test AsyncSQL with multiple database connections."""
        workflow = WorkflowBuilder()

        # Query from PostgreSQL
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "postgres_query",
            {
                "query": "SELECT * FROM users WHERE created_at > $1",
                "parameters": ["2023-01-01"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                # "connection_name": "postgres_main",
            },
        )

        # Query from MySQL (using same PostgreSQL config for test)
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "mysql_query",
            {
                "query": "SELECT * FROM analytics WHERE date > $1",
                "parameters": ["2023-01-01"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                # "connection_name": "postgres_analytics",
            },
        )

        # Aggregate results
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "aggregate_results",
            {
                "query": "INSERT INTO combined_results (user_count, analytics_count) VALUES ($1, $2)",
                "parameters": ["${postgres_query.count}", "${mysql_query.count}"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        workflow.add_connection(
            "postgres_query", "output", "aggregate_results", "input"
        )
        workflow.add_connection("mysql_query", "output", "aggregate_results", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_asyncsql_prepared_statements(self, test_suite):
        """Test AsyncSQL with prepared statements."""
        workflow = WorkflowBuilder()

        # Create prepared statement
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "prepare_statement",
            {
                "query": "PREPARE user_lookup AS SELECT * FROM users WHERE email = $1",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "statement_type": "prepare",
            },
        )

        # Execute prepared statement
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "execute_prepared",
            {
                "query": "EXECUTE user_lookup($1)",
                "parameters": ["john@example.com"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "use_prepared": True,
            },
        )

        workflow.add_connection(
            "prepare_statement", "output", "execute_prepared", "input"
        )

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_concurrent_execution(self, test_suite):
        """Test AsyncSQL with concurrent query execution."""
        workflow = WorkflowBuilder()

        # Multiple concurrent queries
        for i in range(5):
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                f"concurrent_query_{i}",
                {
                    "query": f"SELECT COUNT(*) as count_{i} FROM table_{i}",
                    "connection_string": test_suite.config.url,
                    "dialect": "postgresql",
                    "concurrent_execution": True,
                    "timeout": 30,
                },
            )

        # Aggregate concurrent results
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "aggregate_concurrent",
            {
                "query": "INSERT INTO concurrent_results (total_count) VALUES ($1)",
                "parameters": ["${sum(concurrent_query_*.count)}"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        # Connect all concurrent queries to aggregator
        for i in range(5):
            workflow.add_connection(
                f"concurrent_query_{i}", "output", "aggregate_concurrent", "input"
            )

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 6

    def test_asyncsql_database_migration_support(self, test_suite):
        """Test AsyncSQL with database migration operations."""
        workflow = WorkflowBuilder()

        # Check current schema version
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "check_version",
            {
                "query": "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1",
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "error_handling": "continue",
                "default_result": [{"version": 0}],
            },
        )

        # Run migration if needed
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "run_migration",
            {
                "query": """
                CREATE TABLE IF NOT EXISTS new_feature (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "migration": True,
                "conditional_execution": "version < 2",
                "validate_queries": False,
            },
        )

        # Update schema version
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "update_version",
            {
                "query": "INSERT INTO schema_migrations (version, applied_at) VALUES ($1, NOW())",
                "parameters": [2],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        workflow.add_connection("check_version", "output", "run_migration", "input")
        workflow.add_connection("run_migration", "output", "update_version", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_asyncsql_real_world_analytics_scenario(self, test_suite):
        """Test real-world analytics scenario with AsyncSQL."""
        workflow = WorkflowBuilder()

        # Extract data from source
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "extract_orders",
            {
                "query": """
                SELECT
                    customer_id,
                    product_id,
                    quantity,
                    price,
                    order_date
                FROM orders
                WHERE order_date >= $1 AND order_date < $2
            """,
                "parameters": ["2023-01-01", "2023-02-01"],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
            },
        )

        # Transform data with calculations
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "transform_data",
            {
                "query": """
                WITH order_totals AS (
                    SELECT
                        customer_id,
                        SUM(quantity * price) as total_amount,
                        COUNT(*) as order_count
                    FROM temp_orders
                    GROUP BY customer_id
                )
                SELECT
                    customer_id,
                    total_amount,
                    order_count,
                    total_amount / order_count as avg_order_value
                FROM order_totals
            """,
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "create_temp_table": "temp_orders",
                "temp_data_source": "extract_orders",
            },
        )

        # Load into data warehouse
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "load_warehouse",
            {
                "query": """
                INSERT INTO customer_analytics (
                    customer_id,
                    period,
                    total_amount,
                    order_count,
                    avg_order_value,
                    calculated_at
                )
                SELECT
                    $1, '2023-01', $2, $3, $4, NOW()
                FROM transform_results
            """,
                "parameters": [
                    "${transform_data.customer_id}",
                    "${transform_data.total_amount}",
                    "${transform_data.order_count}",
                    "${transform_data.avg_order_value}",
                ],
                "connection_string": test_suite.config.url,
                "dialect": "postgresql",
                "upsert_mode": True,
                "conflict_columns": ["customer_id", "period"],
            },
        )

        workflow.add_connection("extract_orders", "output", "transform_data", "input")
        workflow.add_connection("transform_data", "output", "load_warehouse", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

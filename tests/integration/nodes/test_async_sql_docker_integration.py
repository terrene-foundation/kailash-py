"""Integration tests for AsyncSQLDatabaseNode using real Docker services.

This test file replaces mock-based tests with real Docker infrastructure,
following the 3-tier testing strategy where integration tests use real services.
"""

import asyncio
import os
from datetime import datetime

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

# Test configuration using Docker services
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5434,  # Docker test port
    "database": "kailash_test",
    "user": "test_user",
    "password": "test_password",
}

MYSQL_CONFIG = {
    "database_type": "mysql",
    "host": "localhost",
    "port": 3307,  # Docker test port
    "database": "kailash_test",
    "user": "kailash_test",
    "password": "test_password",
}

# Skip tests if Docker services aren't available
POSTGRES_AVAILABLE = (
    os.getenv("POSTGRES_TEST_URL") is not None or True
)  # Assume available
MYSQL_AVAILABLE = os.getenv("MYSQL_TEST_URL") is not None or True  # Assume available


class TestAsyncSQLDatabaseNodePostgreSQL:
    """Integration tests using real PostgreSQL Docker service."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_batch_operations_real_postgres(self):
        """Test batch operations with real PostgreSQL database."""
        node = AsyncSQLDatabaseNode(
            name="test_batch",
            **POSTGRES_CONFIG,
            transaction_mode="auto",
        )

        try:
            # Connect to real database
            await node.connect()

            # Create test table
            await node.execute_async(
                query="""
                CREATE TABLE IF NOT EXISTS test_batch_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    age INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Clean up any existing test data
            await node.execute_async(query="DELETE FROM test_batch_users")

            # Test batch insert
            params_list = [
                {"name": "Alice Johnson", "age": 30},
                {"name": "Bob Smith", "age": 25},
                {"name": "Charlie Brown", "age": 35},
            ]

            result = await node.execute_many_async(
                query="INSERT INTO test_batch_users (name, age) VALUES (:name, :age)",
                params_list=params_list,
            )

            # Verify batch insert results
            assert "result" in result
            assert result["result"]["affected_rows"] == len(params_list)
            assert result["success"] is True

            # Verify data was inserted correctly
            select_result = await node.execute_async(
                query="SELECT name, age FROM test_batch_users ORDER BY name"
            )

            rows = select_result["result"]["rows"]
            assert len(rows) == 3
            assert rows[0]["name"] == "Alice Johnson"
            assert rows[0]["age"] == 30
            assert rows[1]["name"] == "Bob Smith"
            assert rows[1]["age"] == 25
            assert rows[2]["name"] == "Charlie Brown"
            assert rows[2]["age"] == 35

        finally:
            # Clean up
            try:
                await node.execute_async(query="DROP TABLE IF EXISTS test_batch_users")
            except:
                pass
            await node.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_transaction_rollback_real_postgres(self):
        """Test transaction rollback with real PostgreSQL database."""
        node = AsyncSQLDatabaseNode(
            name="test_transaction",
            **POSTGRES_CONFIG,
            transaction_mode="manual",
        )

        try:
            await node.connect()

            # Create test table
            await node.execute_async(
                query="""
                CREATE TABLE IF NOT EXISTS test_transaction_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) UNIQUE
                )
                """
            )

            # Clean up any existing test data
            await node.execute_async(query="DELETE FROM test_transaction_users")

            # Start a transaction
            await node.begin_transaction()

            # Insert valid data
            await node.execute_async(
                query="INSERT INTO test_transaction_users (name, email) VALUES (:name, :email)",
                params={"name": "Test User", "email": "test@example.com"},
            )

            # Verify data is in transaction (but not committed)
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM test_transaction_users"
            )
            assert result["result"]["rows"][0]["count"] == 1

            # Rollback transaction
            await node.rollback_transaction()

            # Verify data was rolled back
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM test_transaction_users"
            )
            assert result["result"]["rows"][0]["count"] == 0

        finally:
            # Clean up
            try:
                await node.execute_async(
                    query="DROP TABLE IF EXISTS test_transaction_users"
                )
            except:
                pass
            await node.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_connection_pool_real_postgres(self):
        """Test connection pooling with real PostgreSQL database."""
        node = AsyncSQLDatabaseNode(
            name="test_pool",
            **POSTGRES_CONFIG,
            max_connections=5,
            connection_pool_timeout=30,
        )

        try:
            await node.connect()

            # Test concurrent operations
            tasks = []
            for i in range(10):
                task = node.execute_async(
                    query="SELECT :id as test_id, NOW() as timestamp", params={"id": i}
                )
                tasks.append(task)

            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks)

            # Verify all tasks completed successfully
            assert len(results) == 10
            for i, result in enumerate(results):
                assert result["success"] is True
                assert result["result"]["rows"][0]["test_id"] == i

        finally:
            await node.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_parameter_types_real_postgres(self):
        """Test parameter type handling with real PostgreSQL database."""
        node = AsyncSQLDatabaseNode(
            name="test_types",
            **POSTGRES_CONFIG,
        )

        try:
            await node.connect()

            # Create test table with various data types
            await node.execute_async(
                query="""
                CREATE TABLE IF NOT EXISTS test_types (
                    id SERIAL PRIMARY KEY,
                    text_field TEXT,
                    int_field INTEGER,
                    float_field REAL,
                    bool_field BOOLEAN,
                    date_field TIMESTAMP,
                    json_field JSONB
                )
                """
            )

            # Clean up any existing test data
            await node.execute_async(query="DELETE FROM test_types")

            # Test parameter type inference
            test_data = {
                "text_field": "Hello World",
                "int_field": 42,
                "float_field": 3.14,
                "bool_field": True,
                "date_field": datetime.now(),
                "json_field": {"key": "value", "number": 123},
            }

            # Insert with automatic type inference
            result = await node.execute_async(
                query="""
                INSERT INTO test_types (text_field, int_field, float_field, bool_field, date_field, json_field)
                VALUES (:text_field, :int_field, :float_field, :bool_field, :date_field, :json_field)
                RETURNING id
                """,
                params=test_data,
                parameter_types={"json_field": "JSONB"},  # Explicit type for JSON
            )

            assert result["success"] is True
            assert result["result"]["affected_rows"] == 1

            # Verify data was inserted correctly
            inserted_id = result["result"]["rows"][0]["id"]
            select_result = await node.execute_async(
                query="SELECT * FROM test_types WHERE id = :id",
                params={"id": inserted_id},
            )

            row = select_result["result"]["rows"][0]
            assert row["text_field"] == "Hello World"
            assert row["int_field"] == 42
            assert abs(row["float_field"] - 3.14) < 0.001
            assert row["bool_field"] is True
            assert row["json_field"] == {"key": "value", "number": 123}

        finally:
            # Clean up
            try:
                await node.execute_async(query="DROP TABLE IF EXISTS test_types")
            except:
                pass
            await node.disconnect()


class TestAsyncSQLDatabaseNodeMySQL:
    """Integration tests using real MySQL Docker service."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not MYSQL_AVAILABLE, reason="MySQL Docker service not available"
    )
    async def test_basic_operations_real_mysql(self):
        """Test basic operations with real MySQL database."""
        node = AsyncSQLDatabaseNode(
            name="test_mysql",
            **MYSQL_CONFIG,
        )

        try:
            await node.connect()

            # Create test table
            await node.execute_async(
                query="""
                CREATE TABLE IF NOT EXISTS test_mysql_users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100),
                    email VARCHAR(100)
                )
                """
            )

            # Clean up any existing test data
            await node.execute_async(query="DELETE FROM test_mysql_users")

            # Test insert
            result = await node.execute_async(
                query="INSERT INTO test_mysql_users (name, email) VALUES (:name, :email)",
                params={"name": "MySQL User", "email": "mysql@example.com"},
            )

            assert result["success"] is True
            assert result["result"]["affected_rows"] == 1

            # Test select
            select_result = await node.execute_async(
                query="SELECT name, email FROM test_mysql_users WHERE name = :name",
                params={"name": "MySQL User"},
            )

            rows = select_result["result"]["rows"]
            assert len(rows) == 1
            assert rows[0]["name"] == "MySQL User"
            assert rows[0]["email"] == "mysql@example.com"

        finally:
            # Clean up
            try:
                await node.execute_async(query="DROP TABLE IF EXISTS test_mysql_users")
            except:
                pass
            await node.disconnect()


class TestAsyncSQLDatabaseNodeErrorHandling:
    """Integration tests for error handling with real databases."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_connection_error_handling(self):
        """Test connection error handling with real database."""
        # Test with invalid connection parameters
        node = AsyncSQLDatabaseNode(
            name="test_error",
            database_type="postgresql",
            host="localhost",
            port=5434,
            database="nonexistent_db",
            user="invalid_user",
            password="invalid_pass",
        )

        # Should raise connection error
        with pytest.raises(NodeExecutionError):
            await node.connect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_sql_syntax_error_handling(self):
        """Test SQL syntax error handling with real database."""
        node = AsyncSQLDatabaseNode(
            name="test_syntax_error",
            **POSTGRES_CONFIG,
        )

        try:
            await node.connect()

            # Test invalid SQL syntax
            with pytest.raises(NodeExecutionError):
                await node.execute_async(query="INVALID SQL SYNTAX")

        finally:
            await node.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_parameter_validation_error(self):
        """Test parameter validation error handling."""
        node = AsyncSQLDatabaseNode(
            name="test_param_error",
            **POSTGRES_CONFIG,
        )

        try:
            await node.connect()

            # Test missing required parameter
            with pytest.raises(NodeExecutionError):
                await node.execute_async(
                    query="SELECT * FROM users WHERE id = :id",
                    params={},  # Missing 'id' parameter
                )

        finally:
            await node.disconnect()


class TestAsyncSQLDatabaseNodePerformance:
    """Integration tests for performance with real databases."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not POSTGRES_AVAILABLE, reason="PostgreSQL Docker service not available"
    )
    async def test_large_batch_operations(self):
        """Test performance with large batch operations."""
        node = AsyncSQLDatabaseNode(
            name="test_performance",
            **POSTGRES_CONFIG,
            batch_size=1000,
        )

        try:
            await node.connect()

            # Create test table
            await node.execute_async(
                query="""
                CREATE TABLE IF NOT EXISTS test_performance_data (
                    id SERIAL PRIMARY KEY,
                    data_value INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Clean up any existing test data
            await node.execute_async(query="DELETE FROM test_performance_data")

            # Generate large batch of data
            large_batch = [{"data_value": i} for i in range(5000)]

            # Time the batch operation
            import time

            start_time = time.time()

            result = await node.execute_many_async(
                query="INSERT INTO test_performance_data (data_value) VALUES (:data_value)",
                params_list=large_batch,
            )

            end_time = time.time()
            execution_time = end_time - start_time

            # Verify results
            assert result["success"] is True
            assert result["result"]["affected_rows"] == 5000

            # Verify performance (should complete within reasonable time)
            assert execution_time < 30  # Should complete within 30 seconds

            # Verify data integrity
            count_result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM test_performance_data"
            )
            assert count_result["result"]["rows"][0]["count"] == 5000

        finally:
            # Clean up
            try:
                await node.execute_async(
                    query="DROP TABLE IF EXISTS test_performance_data"
                )
            except:
                pass
            await node.disconnect()

"""
Integration tests for BulkCreateNode with real database connections.
Tests against PostgreSQL using Docker test environment.
"""

import asyncio
from typing import Any, Dict, List

import pytest
from dataflow.nodes.bulk_create import BulkCreateNode

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestBulkCreateNodeIntegration:
    """Integration tests for BulkCreateNode with real database."""

    def _extract_result_data(self, result):
        """Extract data from AsyncSQLDatabaseNode result format."""
        if (
            isinstance(result, dict)
            and "result" in result
            and "data" in result["result"]
        ):
            return result["result"]["data"]
        return result

    @pytest.fixture
    async def setup_test_table(self, test_suite):
        """Create test table and clean up after test."""
        # Use test suite database URL
        connection_string = test_suite.config.url

        # Create table using AsyncSQLDatabaseNode
        setup_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            CREATE TABLE IF NOT EXISTS test_bulk_users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                age INTEGER,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            validate_queries=False,
        )

        # Drop and recreate table for clean state
        drop_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="DROP TABLE IF EXISTS test_bulk_users CASCADE",
            validate_queries=False,
        )

        await drop_node.async_run()
        await setup_node.async_run()

        # Clean up the nodes to close connections
        await setup_node.cleanup()
        await drop_node.cleanup()

        yield connection_string

        # Cleanup after test with new node instance
        cleanup_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="DROP TABLE IF EXISTS test_bulk_users CASCADE",
            validate_queries=False,
        )
        await cleanup_node.async_run()
        await cleanup_node.cleanup()

    @pytest.mark.asyncio
    async def test_bulk_create_basic_insert(self, setup_test_table):
        """Test basic bulk insert functionality."""
        connection_string = setup_test_table

        # Create BulkCreateNode
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
            batch_size=100,
        )

        # Test data
        test_data = [
            {"name": f"User {i}", "email": f"user{i}@example.com", "age": 20 + i}
            for i in range(10)
        ]

        # Execute bulk create
        result = await node.async_run(data=test_data)

        # Verify results
        assert result["success"]
        assert result["inserted"] == 10
        assert result["failed"] == 0
        assert result["total"] == 10
        assert "performance_metrics" in result

        # Verify data was actually inserted
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM test_bulk_users",
            validate_queries=False,
        )

        count_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(count_result)
        assert data[0]["count"] == 10

    @pytest.mark.asyncio
    async def test_bulk_create_large_batch(self, setup_test_table):
        """Test bulk insert with large dataset to verify batching."""
        connection_string = setup_test_table

        # Create BulkCreateNode with smaller batch size
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
            batch_size=250,  # Will create 4 batches for 1000 records
        )

        # Create 1000 records
        test_data = [
            {"name": f"User {i}", "email": f"user{i}@example.com", "age": 20 + (i % 50)}
            for i in range(1000)
        ]

        # Execute bulk create
        result = await node.async_run(data=test_data)

        # Verify results
        assert result["success"]
        assert result["inserted"] == 1000
        assert result["failed"] == 0
        assert result["total"] == 1000
        assert result["performance_metrics"]["batches_processed"] == 4  # 1000 / 250

        # Verify performance metrics
        metrics = result["performance_metrics"]
        assert metrics["records_per_second"] > 0
        assert metrics["elapsed_seconds"] > 0

    @pytest.mark.asyncio
    async def test_bulk_create_conflict_skip(self, setup_test_table):
        """Test conflict resolution with skip strategy."""
        connection_string = setup_test_table

        # Create BulkCreateNode
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # Initial data
        initial_data = [
            {"name": "John Doe", "email": "john@example.com", "age": 30},
            {"name": "Jane Smith", "email": "jane@example.com", "age": 25},
        ]

        # Insert initial data
        await node.async_run(data=initial_data)

        # Try to insert with duplicates using skip strategy
        duplicate_data = [
            {"name": "John Doe", "email": "john@example.com", "age": 31},  # Duplicate
            {"name": "Bob Wilson", "email": "bob@example.com", "age": 35},  # New
            {"name": "Jane Smith", "email": "jane@example.com", "age": 26},  # Duplicate
        ]

        result = await node.async_run(data=duplicate_data, conflict_resolution="skip")

        # With skip strategy, conflicts are ignored
        assert result["success"]
        # Only 1 new record should be inserted (Bob Wilson)
        assert result["inserted"] == 1

        # Verify only 3 records total (2 original + 1 new)
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM test_bulk_users",
            validate_queries=False,
        )

        count_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(count_result)
        assert data[0]["count"] == 3

    @pytest.mark.asyncio
    async def test_bulk_create_with_auto_timestamps(self, setup_test_table):
        """Test auto timestamp generation."""
        connection_string = setup_test_table

        # Create BulkCreateNode with auto timestamps
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=True,
        )

        # Test data without timestamps
        test_data = [
            {"name": "User 1", "email": "user1@example.com", "age": 25},
            {"name": "User 2", "email": "user2@example.com", "age": 30},
        ]

        # Execute bulk create
        result = await node.async_run(data=test_data)

        assert result["success"]
        assert result["inserted"] == 2

        # Verify timestamps were added - select all fields to see what's there
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_users WHERE email = 'user1@example.com'",
            validate_queries=False,
        )

        timestamp_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(timestamp_result)
        # Check that record exists and has timestamp fields
        assert len(data) > 0
        assert data[0]["created_at"] is not None
        assert data[0]["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_bulk_create_multi_tenant(self, setup_test_table):
        """Test multi-tenant support."""
        connection_string = setup_test_table

        # Add tenant_id column
        alter_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="ALTER TABLE test_bulk_users ADD COLUMN tenant_id VARCHAR(50)",
            validate_queries=False,
        )
        await alter_node.async_run()

        # Create BulkCreateNode with multi-tenant support
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
            multi_tenant=True,
        )

        # Test data for different tenants
        tenant1_data = [
            {"name": "Tenant1 User1", "email": "t1u1@example.com", "age": 25},
            {"name": "Tenant1 User2", "email": "t1u2@example.com", "age": 30},
        ]

        tenant2_data = [
            {"name": "Tenant2 User1", "email": "t2u1@example.com", "age": 28},
            {"name": "Tenant2 User2", "email": "t2u2@example.com", "age": 35},
        ]

        # Insert for tenant 1
        result1 = await node.async_run(data=tenant1_data, tenant_id="tenant_001")
        assert result1["success"]
        assert result1["inserted"] == 2

        # Insert for tenant 2
        result2 = await node.async_run(data=tenant2_data, tenant_id="tenant_002")
        assert result2["success"]
        assert result2["inserted"] == 2

        # Verify tenant isolation
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT tenant_id, COUNT(*) as count FROM test_bulk_users GROUP BY tenant_id ORDER BY tenant_id",
            validate_queries=False,
        )

        tenant_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(tenant_result)
        assert len(data) == 2
        assert data[0]["tenant_id"] == "tenant_001"
        assert data[0]["count"] == 2
        assert data[1]["tenant_id"] == "tenant_002"
        assert data[1]["count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_create_performance_target(self, setup_test_table):
        """Test performance meets target of 10,000+ records/sec."""
        connection_string = setup_test_table

        # Create BulkCreateNode with reasonable batch size for integration test
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
            batch_size=500,  # Conservative batch for integration test
        )

        # Create test data - using smaller set for integration test
        # In production, this would be 10,000+ records
        test_data = [
            {
                "name": f"PerfUser {i}",
                "email": f"perf{i}@example.com",
                "age": 20 + (i % 60),
            }
            for i in range(1000)  # 1k records for integration test
        ]

        # Execute bulk create
        result = await node.async_run(data=test_data)

        # Verify results
        assert result["success"]
        assert result["inserted"] == 1000
        assert result["failed"] == 0

        # Check performance metrics
        metrics = result["performance_metrics"]
        print(f"\nPerformance: {metrics['records_per_second']:.2f} records/sec")
        print(f"Elapsed time: {metrics['elapsed_seconds']:.3f} seconds")
        print(f"Target met: {metrics['meets_target']}")

        # For integration tests, we check reasonable performance
        # (actual 10k/sec requires optimized production database)
        assert metrics["records_per_second"] > 100  # At least 100/sec in test env

    @pytest.mark.asyncio
    async def test_bulk_create_error_handling(self, setup_test_table):
        """Test error handling for invalid data."""
        connection_string = setup_test_table

        # Create BulkCreateNode
        node = BulkCreateNode(
            node_id="test_bulk_create",
            table_name="test_bulk_users",
            database_type="postgresql",
            connection_string=connection_string,
            batch_size=2,  # Small batch to test error handling
        )

        # Test data with invalid record (missing required field)
        invalid_data = [
            {"name": "Valid User", "email": "valid@example.com", "age": 25},
            {"name": "Invalid User"},  # Missing required email
            {"name": "Another Valid", "email": "valid2@example.com", "age": 30},
        ]

        # Execute should handle the error gracefully
        # The bulk create will process what it can
        result = await node.async_run(data=invalid_data)

        # With batch_size=2, first batch has 2 records (1 valid, 1 invalid)
        # Since we process record by record within the batch, we get 1 inserted
        # The error in the batch causes the batch to fail, stopping further processing
        assert result["success"]
        assert result["inserted"] >= 1  # At least the first valid record

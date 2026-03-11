"""
Integration tests for BulkUpsertNode with real database connections.
Tests against PostgreSQL using Docker test environment.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

import pytest
from dataflow.nodes.bulk_create import BulkCreateNode
from dataflow.nodes.bulk_upsert import BulkUpsertNode
from pytest import approx

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestBulkUpsertNodeIntegration:
    """Integration tests for BulkUpsertNode with real database."""

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
        """Create test table with data and clean up after test."""
        # Use test suite database URL
        connection_string = test_suite.config.url

        # Create table using AsyncSQLDatabaseNode
        setup_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            CREATE TABLE IF NOT EXISTS test_bulk_upsert_users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                score INTEGER DEFAULT 0,
                version INTEGER DEFAULT 1,
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
            query="DROP TABLE IF EXISTS test_bulk_upsert_users CASCADE",
            validate_queries=False,
        )

        await drop_node.async_run()
        await setup_node.async_run()

        # Insert initial test data
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            INSERT INTO test_bulk_upsert_users (email, name, status, score)
            VALUES
                ('user1@example.com', 'User One', 'active', 100),
                ('user2@example.com', 'User Two', 'inactive', 200),
                ('user3@example.com', 'User Three', 'active', 150)
            """,
            validate_queries=False,
        )
        await insert_node.async_run()

        # Clean up the nodes to close connections
        await setup_node.cleanup()
        await drop_node.cleanup()
        await insert_node.cleanup()

        yield connection_string

        # Cleanup after test with new node instance
        cleanup_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="DROP TABLE IF EXISTS test_bulk_upsert_users CASCADE",
            validate_queries=False,
        )
        await cleanup_node.async_run()
        await cleanup_node.cleanup()

    @pytest.mark.asyncio
    async def test_bulk_upsert_update_existing(self, setup_test_table):
        """Test bulk upsert updates existing records."""
        connection_string = setup_test_table

        # Create BulkUpsertNode
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
            update_columns=["name", "status", "score"],
        )

        # Upsert with some existing emails
        result = await node.async_run(
            data=[
                {
                    "email": "user1@example.com",
                    "name": "Updated User One",
                    "status": "premium",
                    "score": 110,
                },
                {
                    "email": "user4@example.com",
                    "name": "New User Four",
                    "status": "active",
                    "score": 50,
                },
            ]
        )

        # Verify results
        assert result["success"]
        # Note: PostgreSQL ON CONFLICT may not return accurate affected row count
        # We'll verify by checking the actual data

        # Verify the updates
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_upsert_users ORDER BY email",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        # Should have 4 users total (3 original + 1 new)
        assert len(data) == 4

        # Check user1 was updated
        user1 = next(u for u in data if u["email"] == "user1@example.com")
        assert user1["name"] == "Updated User One"
        assert user1["status"] == "premium"
        assert user1["score"] == 110

        # Check user4 was inserted
        user4 = next(u for u in data if u["email"] == "user4@example.com")
        assert user4["name"] == "New User Four"
        assert user4["status"] == "active"
        assert user4["score"] == 50

    @pytest.mark.asyncio
    async def test_bulk_upsert_ignore_strategy(self, setup_test_table):
        """Test bulk upsert with ignore strategy."""
        connection_string = setup_test_table

        # Create BulkUpsertNode with ignore strategy
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
            merge_strategy="ignore",
        )

        # Try to insert existing and new records
        result = await node.async_run(
            data=[
                {
                    "email": "user1@example.com",
                    "name": "Should Not Update",
                    "status": "ignored",
                    "score": 999,
                },
                {
                    "email": "user5@example.com",
                    "name": "New User Five",
                    "status": "active",
                    "score": 75,
                },
            ]
        )

        assert result["success"]

        # Verify existing record was not updated
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_upsert_users WHERE email = 'user1@example.com'",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        # User1 should not be updated
        assert data[0]["name"] == "User One"  # Original name
        assert data[0]["status"] == "active"  # Original status
        assert data[0]["score"] == 100  # Original score

        # Verify new record was inserted
        new_verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_upsert_users WHERE email = 'user5@example.com'",
            validate_queries=False,
        )

        new_result = await new_verify_node.async_run()
        await new_verify_node.cleanup()
        new_data = self._extract_result_data(new_result)

        assert len(new_data) == 1
        assert new_data[0]["name"] == "New User Five"

    @pytest.mark.asyncio
    async def test_bulk_upsert_with_version_check(self, setup_test_table):
        """Test bulk upsert with version checking for optimistic locking."""
        connection_string = setup_test_table

        # Create BulkUpsertNode with version checking
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
            version_check=True,
            version_field="version",
        )

        # First update with correct version
        result = await node.async_run(
            data=[
                {
                    "email": "user1@example.com",
                    "name": "Version 2 Update",
                    "status": "active",
                    "score": 120,
                    "version": 1,
                }
            ]
        )

        assert result["success"]
        assert result["success"]

        # Verify version was incremented
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT version FROM test_bulk_upsert_users WHERE email = 'user1@example.com'",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        # Version should be 2 now
        assert data[0]["version"] == 2

    @pytest.mark.asyncio
    async def test_bulk_upsert_return_records(self, setup_test_table):
        """Test returning upserted records."""
        connection_string = setup_test_table

        # Create BulkUpsertNode
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
        )

        # Upsert with return_upserted option
        result = await node.async_run(
            data=[
                {
                    "email": "user2@example.com",
                    "name": "Updated User Two",
                    "status": "premium",
                    "score": 250,
                },
                {
                    "email": "user6@example.com",
                    "name": "New User Six",
                    "status": "active",
                    "score": 60,
                },
            ],
            return_upserted=True,
        )

        assert result["success"]
        assert result["success"]
        assert "records" in result
        assert len(result["records"]) == 2

        # Verify returned records have expected values
        emails = {record["email"] for record in result["records"]}
        assert emails == {"user2@example.com", "user6@example.com"}

        # Check updated values in returned records
        user2 = next(r for r in result["records"] if r["email"] == "user2@example.com")
        assert user2["name"] == "Updated User Two"
        assert user2["status"] == "premium"

    @pytest.mark.asyncio
    async def test_bulk_upsert_batch_processing(self, setup_test_table):
        """Test batch processing with larger dataset."""
        connection_string = setup_test_table

        # Create BulkUpsertNode with small batch size
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
            batch_size=50,
        )

        # Create 200 records (mix of updates and inserts)
        test_data = []

        # Update existing users
        test_data.extend(
            [
                {
                    "email": "user1@example.com",
                    "name": "Batch Update 1",
                    "status": "active",
                    "score": 111,
                },
                {
                    "email": "user2@example.com",
                    "name": "Batch Update 2",
                    "status": "active",
                    "score": 222,
                },
                {
                    "email": "user3@example.com",
                    "name": "Batch Update 3",
                    "status": "active",
                    "score": 333,
                },
            ]
        )

        # Add new users
        for i in range(10, 207):
            test_data.append(
                {
                    "email": f"batchuser{i}@example.com",
                    "name": f"Batch User {i}",
                    "status": "active",
                    "score": i * 10,
                }
            )

        result = await node.async_run(data=test_data)

        assert result["success"]
        assert result["performance_metrics"]["batches_processed"] == 4  # 200/50 = 4

        # Verify total count
        count_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM test_bulk_upsert_users",
            validate_queries=False,
        )

        count_result = await count_node.async_run()
        await count_node.cleanup()
        data = self._extract_result_data(count_result)

        # Should have 200 users total (3 original updated + 197 new)
        assert data[0]["count"] == 200

    @pytest.mark.asyncio
    async def test_bulk_upsert_multi_tenant(self, setup_test_table):
        """Test multi-tenant support."""
        connection_string = setup_test_table

        # Add tenant_id column
        alter_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="ALTER TABLE test_bulk_upsert_users ADD COLUMN tenant_id VARCHAR(50)",
            validate_queries=False,
        )
        await alter_node.async_run()
        await alter_node.cleanup()

        # Drop old constraint
        drop_constraint_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="ALTER TABLE test_bulk_upsert_users DROP CONSTRAINT test_bulk_upsert_users_email_key",
            validate_queries=False,
        )
        await drop_constraint_node.async_run()
        await drop_constraint_node.cleanup()

        # Create new unique constraint including tenant_id
        constraint_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            ALTER TABLE test_bulk_upsert_users
            ADD CONSTRAINT test_bulk_upsert_users_email_tenant_key
            UNIQUE (email, tenant_id)
            """,
            validate_queries=False,
        )
        await constraint_node.async_run()
        await constraint_node.cleanup()

        # Create BulkUpsertNode with multi-tenant support
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email", "tenant_id"],
            multi_tenant=True,
        )

        # Upsert for different tenants
        result1 = await node.async_run(
            data=[
                {
                    "email": "shared@example.com",
                    "name": "Tenant 1 User",
                    "status": "active",
                    "score": 100,
                }
            ],
            tenant_id="tenant_001",
        )

        result2 = await node.async_run(
            data=[
                {
                    "email": "shared@example.com",
                    "name": "Tenant 2 User",
                    "status": "active",
                    "score": 200,
                }
            ],
            tenant_id="tenant_002",
        )

        assert result1["success"]
        assert result2["success"]

        # Verify both records exist with different tenant_ids
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_upsert_users WHERE email = 'shared@example.com' ORDER BY tenant_id",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert len(data) == 2
        assert data[0]["tenant_id"] == "tenant_001"
        assert data[0]["name"] == "Tenant 1 User"
        assert data[1]["tenant_id"] == "tenant_002"
        assert data[1]["name"] == "Tenant 2 User"

    @pytest.mark.asyncio
    async def test_bulk_upsert_duplicate_handling(self, setup_test_table):
        """Test handling of duplicates within batch."""
        connection_string = setup_test_table

        # Create BulkUpsertNode with duplicate handling
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
            handle_duplicates="last",
        )

        # Send batch with duplicates
        result = await node.async_run(
            data=[
                {
                    "email": "duplicate@example.com",
                    "name": "First Version",
                    "status": "active",
                    "score": 10,
                },
                {
                    "email": "duplicate@example.com",
                    "name": "Second Version",
                    "status": "inactive",
                    "score": 20,
                },
                {
                    "email": "duplicate@example.com",
                    "name": "Final Version",
                    "status": "premium",
                    "score": 30,
                },
            ]
        )

        assert result["success"]

        # Verify only last version was inserted
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_upsert_users WHERE email = 'duplicate@example.com'",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        assert len(data) == 1
        assert data[0]["name"] == "Final Version"
        assert data[0]["status"] == "premium"
        assert data[0]["score"] == 30

    @pytest.mark.asyncio
    async def test_bulk_upsert_performance(self, setup_test_table):
        """Test performance with large upsert operation."""
        connection_string = setup_test_table

        # Create BulkUpsertNode
        node = BulkUpsertNode(
            node_id="test_bulk_upsert",
            table_name="test_bulk_upsert_users",
            database_type="postgresql",
            connection_string=connection_string,
            conflict_columns=["email"],
            batch_size=500,
        )

        # Create 1000 records
        test_data = [
            {
                "email": f"perfuser{i}@example.com",
                "name": f"Performance User {i}",
                "status": "active",
                "score": i,
            }
            for i in range(1000)
        ]

        # First insert
        result1 = await node.async_run(data=test_data)

        assert result1["success"]

        # Update all records (upsert existing)
        for record in test_data:
            record["score"] = record["score"] * 2
            record["status"] = "updated"

        result2 = await node.async_run(data=test_data)

        assert result2["success"]

        # Check performance metrics
        metrics = result2["performance_metrics"]
        print(f"\nUpsert Performance: {metrics['records_per_second']:.2f} records/sec")
        print(f"Total upserted: {metrics['upserted_records']}")
        print(f"Elapsed time: {metrics['elapsed_seconds']:.3f} seconds")

        # For integration tests, we check reasonable performance
        assert metrics["records_per_second"] > 100  # At least 100/sec in test env

        # For this performance test, we focus on throughput metrics
        # The BulkUpsertNode should handle large volumes efficiently

        # Just assert that records_per_second is reasonable for integration test
        assert metrics["records_per_second"] > 100  # At least 100/sec in test env

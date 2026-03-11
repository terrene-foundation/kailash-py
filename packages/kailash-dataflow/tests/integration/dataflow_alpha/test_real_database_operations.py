"""
Integration tests for DataFlow with real database operations - Alpha Release Critical

Tests the most critical blocking issue: all database operations return simulation data.
This validates that DataFlow actually performs real database operations, not mock data.

NO MOCKING - Uses real PostgreSQL via Docker infrastructure.
"""

import asyncio
import os
import sys
from typing import Any, Dict

import pytest

# Add test utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../tests/utils"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
sys.path.insert(0, os.path.dirname(__file__))

from docker_config import DATABASE_CONFIG

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
    from kailash.runtime.local import LocalRuntime

    return LocalRuntime()


@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.integration
class TestRealDatabaseOperations:
    """Test DataFlow performs real database operations - NO SIMULATION."""

    @pytest.fixture
    def real_dataflow(self, test_suite):
        """Create DataFlow with real database connection."""
        from dataflow import DataFlow

        # CRITICAL: This must connect to REAL database, not simulation
        # Use existing_schema_mode=True for incremental migrations (recommended for existing databases)
        db = DataFlow(
            database_url=test_suite.config.url,
            migration_enabled=True,
            existing_schema_mode=True,
        )
        return db

    @pytest.fixture
    def test_user_model(self, real_dataflow):
        """Define test model and return DataFlow instance."""

        # Clean up any existing test_users table to force fresh migration
        try:
            from dataflow.adapters.postgresql import PostgreSQLAdapter

            adapter = PostgreSQLAdapter(real_dataflow.config.database.url)
            adapter.execute_query("DROP TABLE IF EXISTS test_users CASCADE;")
        except Exception:
            pass  # Table might not exist

        @real_dataflow.model
        class TestUser:
            name: str
            email: str
            age: int = 25
            active: bool = True

        return real_dataflow

    def test_dataflow_connects_to_real_database(self, real_dataflow, test_suite):
        """Test that DataFlow connects to actual PostgreSQL database."""
        # Health check should connect to real database
        health = real_dataflow.health_check()

        assert health is not None, "Health check failed"
        assert health.get("database") == "connected", "Not connected to real database"

        # Verify it's connecting to our test database
        config = real_dataflow.config
        assert (
            test_suite.config.url in config.database_url
            or DATABASE_CONFIG["database"] in config.database_url
        )

    def test_create_tables_executes_real_ddl(self, test_user_model, test_suite):
        """Test that create_tables() executes real DDL, not just logging."""
        import asyncpg

        # Execute table creation
        test_user_model.create_tables()

        # Verify table actually exists in real database
        async def check_table_exists():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                # Query real database to verify table exists
                result = await conn.fetch(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'test_users'
                """
                )
                return len(result) > 0
            finally:
                await conn.close()

        # CRITICAL: Table must actually exist in real database
        table_exists = asyncio.run(check_table_exists())
        assert (
            table_exists
        ), "Table was not created in real database - still using simulation"

    def test_generated_nodes_execute_real_database_operations(
        self, test_user_model, test_suite
    ):
        """Test that generated nodes perform real database operations."""
        import asyncpg

        # Ensure table exists
        test_user_model.create_tables()

        # Get generated node
        create_node_class = test_user_model._nodes.get("TestUserCreateNode")
        assert create_node_class is not None, "TestUserCreateNode not generated"

        create_node = create_node_class()

        # Execute create operation
        result = create_node.execute(name="John Doe", email="john@example.com", age=30)

        # Verify real database insertion
        async def verify_real_insertion():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                # Query real database to verify record exists
                records = await conn.fetch(
                    "SELECT * FROM test_users WHERE email = $1", "john@example.com"
                )
                return len(records) > 0, records
            finally:
                await conn.close()

        # CRITICAL: Data must actually be in real database
        exists, records = asyncio.run(verify_real_insertion())
        assert (
            exists
        ), "Record was not inserted into real database - still using simulation"

        # Verify actual data matches
        record = records[0] if records else {}
        assert record.get("name") == "John Doe", "Real database data doesn't match"
        assert (
            record.get("email") == "john@example.com"
        ), "Real database data doesn't match"
        assert record.get("age") == 30, "Real database data doesn't match"

        # Verify result contains real ID, not simulation ID (1)
        assert (
            result.get("id") != 1 or len(records) == 1
        ), "Using simulation ID instead of real database ID"

    def test_read_operations_return_real_data(self, test_user_model, test_suite):
        """Test that read operations return actual database data."""
        import asyncpg

        # Insert test data directly into real database
        async def insert_test_data():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                await conn.execute(
                    """
                    INSERT INTO test_users (name, email, age, active)
                    VALUES ($1, $2, $3, $4)
                """,
                    "Jane Smith",
                    "jane@example.com",
                    28,
                    True,
                )

                # Get the inserted ID
                record = await conn.fetchrow(
                    "SELECT id FROM test_users WHERE email = $1", "jane@example.com"
                )
                return record["id"]
            finally:
                await conn.close()

        # Ensure table and data exist
        test_user_model.create_tables()
        real_id = asyncio.run(insert_test_data())

        # Test read operation
        read_node_class = test_user_model._nodes.get("TestUserReadNode")
        assert read_node_class is not None, "TestUserReadNode not generated"

        read_node = read_node_class()
        result = read_node.execute(id=real_id)

        # CRITICAL: Should return real data from database, not simulation
        assert result is not None, "Read operation returned None"
        assert result.get("name") == "Jane Smith", "Not returning real database data"
        assert (
            result.get("email") == "jane@example.com"
        ), "Not returning real database data"
        assert result.get("age") == 28, "Not returning real database data"
        assert result.get("found") is True, "Record should be found in real database"

    def test_update_operations_modify_real_data(self, test_user_model, test_suite):
        """Test that update operations modify actual database records."""
        import asyncpg

        # Setup: Insert and get real record
        test_user_model.create_tables()

        async def setup_and_verify_update():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                # Insert test record
                await conn.execute(
                    """
                    INSERT INTO test_users (name, email, age)
                    VALUES ($1, $2, $3)
                """,
                    "Bob Wilson",
                    "bob@example.com",
                    35,
                )

                # Get the ID
                record = await conn.fetchrow(
                    "SELECT id FROM test_users WHERE email = $1", "bob@example.com"
                )
                record_id = record["id"]

                # Execute update via DataFlow
                update_node_class = test_user_model._nodes.get("TestUserUpdateNode")
                update_node = update_node_class()

                result = update_node.execute(id=record_id, name="Robert Wilson", age=36)

                # Verify real database was updated
                updated_record = await conn.fetchrow(
                    "SELECT * FROM test_users WHERE id = $1", record_id
                )

                return result, updated_record
            finally:
                await conn.close()

        result, updated_record = asyncio.run(setup_and_verify_update())

        # CRITICAL: Real database must be updated, not just simulation response
        assert updated_record is not None, "Record not found after update"
        assert updated_record["name"] == "Robert Wilson", "Real database not updated"
        assert updated_record["age"] == 36, "Real database not updated"
        assert (
            updated_record["email"] == "bob@example.com"
        ), "Email should remain unchanged"

        # Verify operation result indicates real update
        assert result.get("updated") is True, "Update result should indicate success"

    def test_delete_operations_remove_real_data(self, test_user_model, test_suite):
        """Test that delete operations remove actual database records."""
        import asyncpg

        test_user_model.create_tables()

        async def setup_and_verify_delete():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                # Insert test record
                await conn.execute(
                    """
                    INSERT INTO test_users (name, email, age)
                    VALUES ($1, $2, $3)
                """,
                    "Alice Brown",
                    "alice@example.com",
                    32,
                )

                # Get the ID
                record = await conn.fetchrow(
                    "SELECT id FROM test_users WHERE email = $1", "alice@example.com"
                )
                record_id = record["id"]

                # Verify record exists before deletion
                exists_before = await conn.fetchrow(
                    "SELECT id FROM test_users WHERE id = $1", record_id
                )
                assert (
                    exists_before is not None
                ), "Test record not found before deletion"

                # Execute delete via DataFlow
                delete_node_class = test_user_model._nodes.get("TestUserDeleteNode")
                delete_node = delete_node_class()

                result = delete_node.execute(id=record_id)

                # Verify real database record was deleted
                exists_after = await conn.fetchrow(
                    "SELECT id FROM test_users WHERE id = $1", record_id
                )

                return result, exists_after
            finally:
                await conn.close()

        result, exists_after = asyncio.run(setup_and_verify_delete())

        # CRITICAL: Record must be actually deleted from real database
        assert (
            exists_after is None
        ), "Record still exists in real database - delete operation failed"
        assert result.get("deleted") is True, "Delete result should indicate success"

    def test_list_operations_query_real_data(self, test_user_model, test_suite):
        """Test that list operations query actual database records."""
        import asyncpg

        test_user_model.create_tables()

        async def setup_test_data():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                # Insert multiple test records
                test_users = [
                    ("User1", "user1@example.com", 25, True),
                    ("User2", "user2@example.com", 30, True),
                    ("User3", "user3@example.com", 35, False),
                ]

                for name, email, age, active in test_users:
                    await conn.execute(
                        """
                        INSERT INTO test_users (name, email, age, active)
                        VALUES ($1, $2, $3, $4)
                    """,
                        name,
                        email,
                        age,
                        active,
                    )

                # Count total records
                count_result = await conn.fetchrow(
                    "SELECT COUNT(*) as count FROM test_users"
                )
                return count_result["count"]
            finally:
                await conn.close()

        record_count = asyncio.run(setup_test_data())

        # Execute list operation
        list_node_class = test_user_model._nodes.get("TestUserListNode")
        assert list_node_class is not None, "TestUserListNode not generated"

        list_node = list_node_class()
        # Disable cache to ensure we query real database, not stale cached data
        # Use higher limit to ensure we get the newly inserted records
        result = list_node.execute(limit=50, enable_cache=False)

        # CRITICAL: Should return real data from database, not empty simulation
        assert result is not None, "List operation returned None"
        assert "records" in result, "Result missing records field"
        assert "count" in result, "Result missing count field"

        # Should have real records, not empty list
        records = result["records"]
        assert (
            len(records) >= 3
        ), f"Expected at least 3 records, got {len(records)} - not querying real database"

        # Verify actual data content
        found_emails = [record.get("email") for record in records]
        assert "user1@example.com" in found_emails, "Missing expected real data"
        assert "user2@example.com" in found_emails, "Missing expected real data"

    def test_transaction_handling_with_real_database(self, test_user_model, test_suite):
        """Test that transaction handling works with real database."""
        import asyncpg

        test_user_model.create_tables()

        async def test_transaction_rollback():
            conn = await asyncpg.connect(test_suite.config.url)
            try:
                # Start transaction
                async with conn.transaction():
                    # Insert record
                    await conn.execute(
                        """
                        INSERT INTO test_users (name, email, age)
                        VALUES ($1, $2, $3)
                    """,
                        "Transaction Test",
                        "transaction@example.com",
                        40,
                    )

                    # Verify record exists within transaction
                    record = await conn.fetchrow(
                        "SELECT id FROM test_users WHERE email = $1",
                        "transaction@example.com",
                    )
                    assert record is not None, "Record not found within transaction"

                    # Force rollback by raising exception
                    raise Exception("Intentional rollback")

            except Exception:
                # Expected rollback
                pass

            # Verify record was rolled back
            record_after = await conn.fetchrow(
                "SELECT id FROM test_users WHERE email = $1", "transaction@example.com"
            )
            return record_after is None

        rollback_worked = asyncio.run(test_transaction_rollback())
        assert (
            rollback_worked
        ), "Transaction rollback failed - not using real database transactions"

    def test_performance_with_real_database(self, test_user_model):
        """Test that real database operations have acceptable performance."""
        import time

        test_user_model.create_tables()

        # Test create operation performance
        create_node_class = test_user_model._nodes.get("TestUserCreateNode")
        create_node = create_node_class()

        start_time = time.time()
        result = create_node.execute(
            name="Performance Test", email="perf@example.com", age=25
        )
        execution_time = time.time() - start_time

        # Should complete within reasonable time (not infinite simulation loop)
        assert (
            execution_time < 5.0
        ), f"Operation too slow: {execution_time:.2f}s - may be using simulation"
        assert result is not None, "Operation failed"

    def test_concurrent_operations_with_real_database(self, test_user_model):
        """Test that concurrent operations work with real database."""
        import asyncio
        import concurrent.futures

        test_user_model.create_tables()

        def create_user(user_index):
            create_node_class = test_user_model._nodes.get("TestUserCreateNode")
            create_node = create_node_class()

            return create_node.execute(
                name=f"Concurrent User {user_index}",
                email=f"concurrent{user_index}@example.com",
                age=20 + user_index,
            )

        # Execute concurrent operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_user, i) for i in range(3)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All operations should succeed with real database
        assert len(results) == 3, "Not all concurrent operations completed"
        for result in results:
            assert result is not None, "Concurrent operation failed"
            assert "id" in result, "Result missing ID field"

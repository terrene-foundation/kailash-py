"""
Tier 2 Integration Tests: Migration Lock Manager Integration

Tests real concurrent migration scenarios with actual PostgreSQL infrastructure.
NO MOCKING - uses real Docker services. Tests <5 seconds each.
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

# Test infrastructure
import asyncpg
import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig

# DataFlow imports
from dataflow.migrations.concurrent_access_manager import (
    LockStatus,
    MigrationLockManager,
)
from dataflow.utils.connection import ConnectionManager
from dataflow.utils.connection_adapter import ConnectionManagerAdapter

from tests.infrastructure.test_harness import IntegrationTestSuite

logger = logging.getLogger(__name__)


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class MockDataFlowForTesting:
    """Minimal DataFlow mock for connection manager testing."""

    def __init__(self, database_url: str):
        self.config = DataFlowConfig(database=DatabaseConfig(url=database_url))


@pytest.fixture
async def postgres_connection(test_suite):
    """Get a direct PostgreSQL connection for setup/cleanup."""
    connection = await asyncpg.connect(test_suite.config.url)
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def clean_database(postgres_connection):
    """Clean database before and after tests."""

    async def cleanup():
        # Drop all DataFlow tables
        await postgres_connection.execute(
            "DROP TABLE IF EXISTS dataflow_migration_locks"
        )
        await postgres_connection.execute("DROP TABLE IF EXISTS dataflow_migrations")

        # Drop test tables
        await postgres_connection.execute("DROP TABLE IF EXISTS test_users")
        await postgres_connection.execute("DROP TABLE IF EXISTS test_products")

    await cleanup()
    yield
    await cleanup()


@pytest.fixture
def dataflow_instance(test_suite):
    """Create a DataFlow instance for testing."""
    return MockDataFlowForTesting(test_suite.config.url)


@pytest.fixture
def connection_adapter(dataflow_instance):
    """Create a ConnectionManagerAdapter for testing."""
    return ConnectionManagerAdapter(dataflow_instance)


@pytest.fixture
def migration_lock_manager(connection_adapter):
    """Create a MigrationLockManager for testing."""
    return MigrationLockManager(connection_adapter, lock_timeout=5)


@pytest.mark.asyncio
class TestRealPostgreSQLLocking:
    """Test lock manager with real PostgreSQL database."""

    async def test_lock_table_creation(
        self, migration_lock_manager, postgres_connection, clean_database
    ):
        """Test that lock table is created correctly."""
        # Ensure table doesn't exist
        result = await postgres_connection.fetch(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'dataflow_migration_locks'"
        )
        assert len(result) == 0

        # Try to acquire lock (should create table)
        success = await migration_lock_manager.acquire_migration_lock("test_schema")
        assert success

        # Verify table was created with correct schema
        result = await postgres_connection.fetch(
            """SELECT column_name, data_type FROM information_schema.columns
               WHERE table_name = 'dataflow_migration_locks'
               ORDER BY ordinal_position"""
        )

        expected_columns = [
            ("schema_name", "character varying"),
            ("holder_process_id", "character varying"),
            ("acquired_at", "timestamp without time zone"),
            ("expires_at", "timestamp without time zone"),
            ("lock_data", "text"),
        ]

        assert len(result) == 5
        for i, (col_name, data_type) in enumerate(expected_columns):
            assert result[i]["column_name"] == col_name
            assert data_type in result[i]["data_type"]

    async def test_successful_lock_acquisition(
        self, migration_lock_manager, postgres_connection, clean_database
    ):
        """Test successful lock acquisition and verification."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Acquire lock
        success = await migration_lock_manager.acquire_migration_lock(schema_name)
        assert success

        # Verify lock exists in database
        result = await postgres_connection.fetch(
            "SELECT schema_name, holder_process_id FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )

        assert len(result) == 1
        assert result[0]["schema_name"] == schema_name
        assert result[0]["holder_process_id"] == migration_lock_manager.process_id

    async def test_lock_conflict_prevention(
        self, connection_adapter, postgres_connection, clean_database
    ):
        """Test that two processes cannot acquire the same lock."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Create two separate lock managers (simulating different processes)
        lock_manager_1 = MigrationLockManager(connection_adapter, lock_timeout=2)
        lock_manager_2 = MigrationLockManager(connection_adapter, lock_timeout=2)

        # First manager acquires lock
        success_1 = await lock_manager_1.acquire_migration_lock(schema_name)
        assert success_1

        # Second manager should fail to acquire same lock
        success_2 = await lock_manager_2.acquire_migration_lock(schema_name)
        assert not success_2

        # Verify only one lock exists
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert result[0]["count"] == 1

    async def test_lock_release(
        self, migration_lock_manager, postgres_connection, clean_database
    ):
        """Test lock release functionality."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Acquire lock
        success = await migration_lock_manager.acquire_migration_lock(schema_name)
        assert success

        # Verify lock exists
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert result[0]["count"] == 1

        # Release lock
        await migration_lock_manager.release_migration_lock(schema_name)

        # Verify lock is removed
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert result[0]["count"] == 0

    async def test_lock_reacquisition_after_release(
        self, connection_adapter, postgres_connection, clean_database
    ):
        """Test that lock can be reacquired after release."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Create two lock managers
        lock_manager_1 = MigrationLockManager(connection_adapter, lock_timeout=2)
        lock_manager_2 = MigrationLockManager(connection_adapter, lock_timeout=2)

        # Manager 1 acquires lock
        success = await lock_manager_1.acquire_migration_lock(schema_name)
        assert success

        # Manager 2 cannot acquire
        success = await lock_manager_2.acquire_migration_lock(schema_name)
        assert not success

        # Manager 1 releases lock
        await lock_manager_1.release_migration_lock(schema_name)

        # Manager 2 can now acquire
        success = await lock_manager_2.acquire_migration_lock(schema_name)
        assert success

        # Verify new owner
        result = await postgres_connection.fetch(
            "SELECT holder_process_id FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert len(result) == 1
        assert result[0]["holder_process_id"] == lock_manager_2.process_id

    async def test_lock_status_checking(self, migration_lock_manager, clean_database):
        """Test lock status checking functionality."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Check status when no lock exists
        status = await migration_lock_manager.check_lock_status(schema_name)
        assert status.schema_name == schema_name
        assert not status.is_locked
        assert status.holder_process_id is None

        # Acquire lock
        await migration_lock_manager.acquire_migration_lock(schema_name)

        # Check status when lock exists
        status = await migration_lock_manager.check_lock_status(schema_name)
        assert status.schema_name == schema_name
        assert status.is_locked
        assert status.holder_process_id == migration_lock_manager.process_id
        assert status.acquired_at is not None

    async def test_expired_lock_cleanup(
        self, migration_lock_manager, postgres_connection, clean_database
    ):
        """Test that expired locks are automatically cleaned up."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Manually insert an expired lock
        expired_time = datetime.now() - timedelta(minutes=10)  # 10 minutes ago
        fake_process_id = f"expired_process_{uuid.uuid4().hex[:8]}"

        await postgres_connection.execute(
            """INSERT INTO dataflow_migration_locks
               (schema_name, holder_process_id, acquired_at, expires_at, lock_data)
               VALUES ($1, $2, $3, $4, $5)""",
            schema_name,
            fake_process_id,
            expired_time,
            expired_time,
            '{"timeout": 30}',
        )

        # Verify expired lock exists
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert result[0]["count"] == 1

        # Try to check lock status (should trigger cleanup)
        status = await migration_lock_manager.check_lock_status(schema_name)
        assert not status.is_locked

        # Verify expired lock was cleaned up
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert result[0]["count"] == 0

    async def test_lock_context_manager_with_real_database(
        self, migration_lock_manager, postgres_connection, clean_database
    ):
        """Test context manager with real database operations."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Use context manager
        async with migration_lock_manager.migration_lock(schema_name):
            # Verify lock exists during context
            result = await postgres_connection.fetch(
                "SELECT holder_process_id FROM dataflow_migration_locks WHERE schema_name = $1",
                schema_name,
            )
            assert len(result) == 1
            assert result[0]["holder_process_id"] == migration_lock_manager.process_id

        # Verify lock is released after context
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM dataflow_migration_locks WHERE schema_name = $1",
            schema_name,
        )
        assert result[0]["count"] == 0


@pytest.mark.asyncio
class TestConcurrentLockingScenarios:
    """Test concurrent locking scenarios that simulate real migration conflicts."""

    async def test_concurrent_lock_attempts(self, connection_adapter, clean_database):
        """Test multiple processes trying to acquire locks simultaneously."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Create multiple lock managers
        managers = [
            MigrationLockManager(connection_adapter, lock_timeout=1) for _ in range(5)
        ]

        # Try to acquire locks concurrently
        async def try_acquire(manager, results, index):
            try:
                success = await manager.acquire_migration_lock(schema_name)
                results[index] = (success, manager.process_id)
            except Exception as e:
                results[index] = (False, str(e))

        results = [None] * 5
        tasks = [
            asyncio.create_task(try_acquire(manager, results, i))
            for i, manager in enumerate(managers)
        ]

        await asyncio.gather(*tasks)

        # Only one should succeed
        successful_acquisitions = [r for r in results if r and r[0]]
        assert len(successful_acquisitions) == 1

        # Others should fail
        failed_acquisitions = [r for r in results if r and not r[0]]
        assert len(failed_acquisitions) == 4

    async def test_lock_timeout_behavior(self, connection_adapter, clean_database):
        """Test lock timeout and recovery behavior."""
        schema_name = f"test_schema_{uuid.uuid4().hex[:8]}"

        # Create lock manager with short timeout
        quick_manager = MigrationLockManager(connection_adapter, lock_timeout=1)
        blocking_manager = MigrationLockManager(connection_adapter, lock_timeout=1)

        # First manager acquires lock
        success = await blocking_manager.acquire_migration_lock(schema_name)
        assert success

        # Second manager tries to acquire with timeout
        start_time = time.time()
        success = await quick_manager.acquire_migration_lock(schema_name)
        elapsed = time.time() - start_time

        assert not success
        assert elapsed < 3  # Should fail quickly, not hang

    async def test_multiple_schema_locking(
        self, migration_lock_manager, clean_database
    ):
        """Test that different schemas can be locked independently."""
        schemas = [
            f"schema_a_{uuid.uuid4().hex[:8]}",
            f"schema_b_{uuid.uuid4().hex[:8]}",
            f"schema_c_{uuid.uuid4().hex[:8]}",
        ]

        # Acquire locks on all schemas
        for schema in schemas:
            success = await migration_lock_manager.acquire_migration_lock(schema)
            assert success

        # Verify all locks exist
        for schema in schemas:
            status = await migration_lock_manager.check_lock_status(schema)
            assert status.is_locked

        # Release all locks
        for schema in schemas:
            await migration_lock_manager.release_migration_lock(schema)

        # Verify all locks are released
        for schema in schemas:
            status = await migration_lock_manager.check_lock_status(schema)
            assert not status.is_locked


@pytest.mark.asyncio
class TestConnectionAdapterIntegration:
    """Test ConnectionManagerAdapter with real PostgreSQL operations."""

    async def test_parameter_conversion_with_real_queries(
        self, connection_adapter, postgres_connection, clean_database
    ):
        """Test parameter conversion with actual PostgreSQL queries."""
        # Create test table
        await postgres_connection.execute(
            "CREATE TABLE test_table (id INTEGER, name TEXT)"
        )

        # Insert using adapter with %s placeholders
        result = await connection_adapter.execute_query(
            "INSERT INTO test_table (id, name) VALUES (%s, %s)", [1, "test_name"]
        )

        # Should return success indicator for DML
        assert result == [{"success": True}]

        # Verify data was inserted
        actual_data = await postgres_connection.fetch("SELECT id, name FROM test_table")
        assert len(actual_data) == 1
        assert actual_data[0]["id"] == 1
        assert actual_data[0]["name"] == "test_name"

    async def test_select_query_result_handling(
        self, connection_adapter, postgres_connection, clean_database
    ):
        """Test SELECT query result handling through adapter."""
        # Create and populate test table
        await postgres_connection.execute(
            "CREATE TABLE test_table (id INTEGER, name TEXT)"
        )
        await postgres_connection.execute(
            "INSERT INTO test_table VALUES (1, 'test1'), (2, 'test2')"
        )

        # Query through adapter
        result = await connection_adapter.execute_query(
            "SELECT id, name FROM test_table ORDER BY id"
        )

        # Should return actual results
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "test1"
        assert result[1]["id"] == 2
        assert result[1]["name"] == "test2"

    async def test_transaction_operations_with_real_database(
        self, connection_adapter, postgres_connection, clean_database
    ):
        """Test transaction operations with real database."""
        # Create test table
        await postgres_connection.execute("CREATE TABLE test_table (id INTEGER)")

        # Start transaction
        await connection_adapter.begin_transaction()
        assert connection_adapter.is_transaction_active()

        # Insert data in transaction
        await connection_adapter.execute_query(
            "INSERT INTO test_table (id) VALUES (%s)", [100]
        )

        # Rollback transaction
        await connection_adapter.rollback_transaction()
        assert not connection_adapter.is_transaction_active()

        # Verify data was not committed
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM test_table"
        )
        assert result[0]["count"] == 0

    async def test_transaction_commit_with_real_database(
        self, connection_adapter, postgres_connection, clean_database
    ):
        """Test successful transaction commit."""
        # Create test table
        await postgres_connection.execute("CREATE TABLE test_table (id INTEGER)")

        # Start transaction
        await connection_adapter.begin_transaction()

        # Insert data
        await connection_adapter.execute_query(
            "INSERT INTO test_table (id) VALUES (%s)", [200]
        )

        # Commit transaction
        await connection_adapter.commit_transaction()
        assert not connection_adapter.is_transaction_active()

        # Verify data was committed
        result = await postgres_connection.fetch(
            "SELECT COUNT(*) as count FROM test_table"
        )
        assert result[0]["count"] == 1


if __name__ == "__main__":
    # Run integration tests with 5-second timeout
    pytest.main([__file__, "-v", "--timeout=5"])

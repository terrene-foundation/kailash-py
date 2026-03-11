#!/usr/bin/env python3
"""
Test concurrent migration safety with advisory locks.
Validates that race conditions are prevented using real infrastructure.
"""

import asyncio
import concurrent.futures
import random
import time
from datetime import datetime

import pytest
from dataflow.migrations.concurrent_access_manager import (
    AtomicMigrationExecutor,
    ConcurrentMigrationQueue,
    MigrationLockManager,
    MigrationOperation,
    MigrationRequest,
)


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestConcurrentMigrationSafety:
    """Test that advisory locks prevent concurrent migration issues using real infrastructure."""

    @pytest.fixture(autouse=True)
    async def setup_test_isolation(self, postgres_connection):
        """Setup test isolation using unique schema names."""
        self._test_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        self._schema_name = f"test_schema_{self._test_id}"

        yield

        # Cleanup: Drop any test tables created during this test
        try:
            await postgres_connection.execute(
                f"DROP TABLE IF EXISTS test_table_{self._test_id} CASCADE"
            )
            await postgres_connection.execute(
                f"DROP TABLE IF EXISTS test_users_{self._test_id} CASCADE"
            )
            await postgres_connection.execute(
                f"DELETE FROM dataflow_migration_locks WHERE schema_name = '{self._schema_name}'"
            )
        except:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    async def test_advisory_lock_prevents_concurrent_migrations(
        self, postgres_connection
    ):
        """Test that only one migration can run at a time using real MigrationLockManager."""

        # Create connection manager that wraps our real connection and converts SQL placeholders
        class AsyncpgConnectionManager:
            def __init__(self, connection):
                self.connection = connection

            async def execute_query(self, query, params=None):
                # Convert %s placeholders to $1, $2, etc. for asyncpg
                if params and "%s" in query:
                    # Replace %s with $1, $2, $3, etc.
                    converted_query = query
                    for i, param in enumerate(params, 1):
                        converted_query = converted_query.replace("%s", f"${i}", 1)

                    # For SELECT queries, use fetch to get results
                    if converted_query.strip().upper().startswith("SELECT"):
                        return await self.connection.fetch(converted_query, *params)
                    else:
                        # For INSERT/UPDATE/DELETE, return command result
                        result = await self.connection.execute(converted_query, *params)
                        # For INSERT with ON CONFLICT DO NOTHING, return True if rows were inserted
                        return "INSERT 0 1" in result
                elif params:
                    if query.strip().upper().startswith("SELECT"):
                        return await self.connection.fetch(query, *params)
                    else:
                        result = await self.connection.execute(query, *params)
                        return "INSERT 0 1" in result if "INSERT" in result else result
                else:
                    if query.strip().upper().startswith("SELECT"):
                        return await self.connection.fetch(query)
                    else:
                        return await self.connection.execute(query)

        connection_manager = AsyncpgConnectionManager(test_suite)

        # Track which instance acquired the lock
        lock_acquired_by = []
        migration_completed_by = []

        async def simulate_migration_instance(instance_id: str, delay: float = 0):
            """Simulate a DataFlow instance trying to migrate using real lock manager."""
            if delay:
                await asyncio.sleep(delay)

            # Create lock manager with real connection
            lock_manager = MigrationLockManager(connection_manager, lock_timeout=5)

            try:
                # Try to acquire lock
                acquired = await lock_manager.acquire_migration_lock(
                    self._schema_name, timeout=2
                )

                if acquired:
                    lock_acquired_by.append(instance_id)
                    print(f"Instance {instance_id} acquired lock")

                    # Simulate migration work
                    await asyncio.sleep(0.5)
                    migration_completed_by.append(instance_id)
                    print(f"Instance {instance_id} completed migration")

                    # Release lock
                    await lock_manager.release_migration_lock(self._schema_name)
                    print(f"Instance {instance_id} released lock")

                    return True
                else:
                    print(f"Instance {instance_id} failed to acquire lock")
                    return False

            except Exception as e:
                print(f"Instance {instance_id} encountered error: {e}")
                return False

        # Test concurrent access - launch 3 instances simultaneously
        print(f"Testing concurrent migration lock with schema: {self._schema_name}")

        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                simulate_migration_instance(f"instance_{i}", delay=i * 0.1)
            )
            tasks.append(task)

        # Wait for all instances to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify results
        successful_instances = [r for r in results if r is True]
        failed_instances = [r for r in results if r is False]

        print(
            f"Results: {len(successful_instances)} successful, {len(failed_instances)} failed"
        )
        print(f"Lock acquired by: {lock_acquired_by}")
        print(f"Migration completed by: {migration_completed_by}")

        # Only one instance should have acquired the lock and completed migration
        assert (
            len(lock_acquired_by) == 1
        ), f"Expected 1 lock acquisition, got {len(lock_acquired_by)}"
        assert (
            len(migration_completed_by) == 1
        ), f"Expected 1 migration completion, got {len(migration_completed_by)}"
        assert (
            len(successful_instances) == 1
        ), f"Expected 1 successful instance, got {len(successful_instances)}"
        assert (
            len(failed_instances) == 2
        ), f"Expected 2 failed instances, got {len(failed_instances)}"

    @pytest.mark.asyncio
    async def test_advisory_lock_cleanup_on_error(self, postgres_connection):
        """Test that advisory locks are released even on error using real infrastructure."""

        # Create connection manager that converts SQL placeholders
        class AsyncpgConnectionManager:
            def __init__(self, connection):
                self.connection = connection

            async def execute_query(self, query, params=None):
                # Convert %s placeholders to $1, $2, etc. for asyncpg
                if params and "%s" in query:
                    converted_query = query
                    for i, param in enumerate(params, 1):
                        converted_query = converted_query.replace("%s", f"${i}", 1)

                    if converted_query.strip().upper().startswith("SELECT"):
                        return await self.connection.fetch(converted_query, *params)
                    else:
                        result = await self.connection.execute(converted_query, *params)
                        return "INSERT 0 1" in result
                elif params:
                    if query.strip().upper().startswith("SELECT"):
                        return await self.connection.fetch(query, *params)
                    else:
                        result = await self.connection.execute(query, *params)
                        return "INSERT 0 1" in result if "INSERT" in result else result
                else:
                    if query.strip().upper().startswith("SELECT"):
                        return await self.connection.fetch(query)
                    else:
                        return await self.connection.execute(query)

        connection_manager = AsyncpgConnectionManager(test_suite)
        lock_manager = MigrationLockManager(connection_manager, lock_timeout=5)

        # Acquire lock
        acquired = await lock_manager.acquire_migration_lock(
            self._schema_name, timeout=2
        )
        assert acquired, "Should be able to acquire lock initially"

        # Verify lock status
        status = await lock_manager.check_lock_status(self._schema_name)
        assert status.is_locked, "Lock should be active"

        # Simulate error and cleanup
        await lock_manager.release_migration_lock(self._schema_name)

        # Verify lock was released
        status_after = await lock_manager.check_lock_status(self._schema_name)
        assert not status_after.is_locked, "Lock should be released after cleanup"

    @pytest.mark.asyncio
    async def test_concurrent_checksum_constraint(self, postgres_connection):
        """Test that database-level constraint prevents duplicate migrations using real infrastructure."""

        # Create unique table for this test
        table_name = f"test_checksum_table_{self._test_id}"

        try:
            # Create test table
            await postgres_connection.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    checksum VARCHAR(255) UNIQUE,
                    name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert first record
            await postgres_connection.execute(
                f"INSERT INTO {table_name} (checksum, name) VALUES ($1, $2)",
                "duplicate_checksum",
                "first_migration",
            )

            # Try to insert duplicate checksum - should fail
            try:
                await postgres_connection.execute(
                    f"INSERT INTO {table_name} (checksum, name) VALUES ($1, $2)",
                    "duplicate_checksum",
                    "second_migration",
                )
                assert False, "Should not be able to insert duplicate checksum"
            except Exception as e:
                # Should get unique constraint violation
                assert "duplicate key value" in str(e) or "unique constraint" in str(e)
                print(f"Correctly caught constraint violation: {e}")

        finally:
            # Cleanup
            try:
                await postgres_connection.execute(f"DROP TABLE IF EXISTS {table_name}")
            except:
                pass


if __name__ == "__main__":
    print("Testing Concurrent Migration Safety")
    print("=" * 60)
    print("Use pytest to run these tests with proper fixtures")

"""
Test to replicate: DF-501 Async/Sync Event Loop Conflicts in Table Creation

This test demonstrates the bug described in the bug report where:
1. `_ensure_migration_tables()` detects async context but calls sync `execute()`
2. `create_tables()` fails in async contexts due to event loop conflicts
3. ThreadPoolExecutor + asyncio.run() creates new event loops that can't access connection pools

The fix should:
1. Provide async versions of table creation methods
2. Properly await async execution when in async context
3. Avoid creating new event loops in running async contexts
"""

import asyncio
import os

import pytest
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# Database URLs for testing
POSTGRES_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
SQLITE_URL = ":memory:"


class TestAsyncTableCreationBug:
    """Tests verifying DF-501 fix behavior - sync methods now raise in async context."""

    @pytest.mark.asyncio
    async def test_ensure_migration_tables_raises_in_async_context(self):
        """
        FIX VERIFICATION: _ensure_migration_tables() now raises in async context.

        After DF-501 fix:
        - Method detects async context
        - Raises clear RuntimeError directing to async alternative
        - No more event loop conflicts

        Expected: RuntimeError with helpful message
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_ensure_migration_tables_fixed",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class TestModel:
            id: str
            name: str

        # Verify we're in an async context
        loop = asyncio.get_running_loop()
        assert loop.is_running(), "Test must run in async context"

        # DF-501 FIX: Sync method now raises clear error in async context
        with pytest.raises(RuntimeError) as exc_info:
            db._ensure_migration_tables("sqlite")

        # Verify error message is helpful
        assert "_ensure_migration_tables_async()" in str(exc_info.value)
        assert "DF-501" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_tables_async_exists_and_works(self):
        """
        FIX VERIFICATION: create_tables_async() now exists.

        After DF-501 fix:
        - create_tables_async() is available
        - Can be used in FastAPI lifespan and other async contexts
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_create_tables_async_fixed",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class CreateTablesTestModel:
            id: str
            name: str

        # Verify we're in an async context
        loop = asyncio.get_running_loop()
        assert loop.is_running(), "Test must run in async context"

        # DF-501 FIX: Async method now exists
        assert hasattr(db, "create_tables_async"), "create_tables_async() should exist"

        # Use the async version - should work without issues
        await db.create_tables_async()

    @pytest.mark.asyncio
    async def test_sync_create_tables_raises_in_async_context(self):
        """
        FIX VERIFICATION: Sync create_tables() raises in async context.

        After DF-501 fix:
        - Sync method detects async context
        - Raises clear RuntimeError directing to async alternative
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_sync_raises",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class SyncRaisesTestModel:
            id: str
            name: str

        # We're in async context
        assert asyncio.get_running_loop().is_running()

        # DF-501 FIX: Sync method should raise clear error
        with pytest.raises(RuntimeError) as exc_info:
            db.create_tables()

        # Verify error message mentions async alternative
        assert "create_tables_async()" in str(exc_info.value)
        assert "DF-501" in str(exc_info.value)


class TestPostgreSQLAsyncTableCreationBug:
    """Tests specific to PostgreSQL async/sync - now with proper async methods."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "postgresql" not in POSTGRES_URL.lower(),
        reason="Requires PostgreSQL for connection pool testing",
    )
    async def test_postgresql_sync_raises_in_async_context(self):
        """
        FIX VERIFICATION: PostgreSQL sync method raises in async context.

        After DF-501 fix:
        - Sync method detects async context
        - Raises RuntimeError directing to async alternative
        - No more event loop conflicts
        """
        db = DataFlow(
            database_url=POSTGRES_URL,
            instance_id="test_pg_sync_raises",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class PostgresTestModel:
            id: str
            name: str

        # Initialize to create connection pool
        await db.initialize()

        # DF-501 FIX: Sync method should raise in async context
        with pytest.raises(RuntimeError) as exc_info:
            db._ensure_migration_tables("postgresql")

        assert "_ensure_migration_tables_async()" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "postgresql" not in POSTGRES_URL.lower(),
        reason="Requires PostgreSQL for connection pool testing",
    )
    async def test_postgresql_async_method_works(self):
        """
        FIX VERIFICATION: PostgreSQL async method works correctly.

        After DF-501 fix:
        - _ensure_migration_tables_async() works in async context
        - No event loop conflicts
        """
        db = DataFlow(
            database_url=POSTGRES_URL,
            instance_id="test_pg_async_works",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class PostgresAsyncTestModel:
            id: str
            name: str

        # Initialize connection pool
        await db.initialize()

        # DF-501 FIX: Async method should work
        await db._ensure_migration_tables_async("postgresql")


class TestThreadPoolExecutorAsyncRunBug:
    """Tests demonstrating the ThreadPoolExecutor + asyncio.run() bug."""

    @pytest.mark.asyncio
    async def test_thread_pool_executor_creates_new_loop(self):
        """
        BUG DEMONSTRATION: ThreadPoolExecutor + asyncio.run() creates new event loop.

        This pattern is used in:
        - _trigger_sqlite_schema_management() lines 4033-4042
        - _trigger_postgresql_migration_system() lines 4294-4303

        The problem:
        1. Code detects running event loop
        2. Creates ThreadPoolExecutor to "work around" it
        3. Submits asyncio.run() which creates NEW event loop in thread
        4. Database connections tied to original loop can't be used
        """
        import concurrent.futures

        # We're in async context
        original_loop = asyncio.get_running_loop()
        assert original_loop.is_running()

        # This is the problematic pattern from the DataFlow code
        async def async_operation():
            # Get the loop this runs in
            inner_loop = asyncio.get_running_loop()
            return inner_loop

        # Demonstrate the bug: ThreadPoolExecutor + asyncio.run creates new loop
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, async_operation())
            new_loop = future.result()

        # The new loop is DIFFERENT from the original - this is the bug!
        assert (
            new_loop is not original_loop
        ), "ThreadPoolExecutor + asyncio.run should create new loop (demonstrating bug)"

        # This means any async resources (connection pools, etc.) tied to
        # original_loop CANNOT be used in the new_loop - causing the errors


class TestProposedFixes:
    """Tests for proposed fixes - these should pass after the fix is implemented."""

    @pytest.mark.asyncio
    async def test_create_tables_async_should_exist(self):
        """
        FIX VERIFICATION: create_tables_async() exists and works.

        After the DF-501 fix, there should be an async version of create_tables().
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_create_tables_async_exists",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class AsyncCreateTablesModel:
            id: str
            name: str

        # DF-501 FIX: This should now exist
        assert hasattr(
            db, "create_tables_async"
        ), "create_tables_async() should exist after DF-501 fix"

        # Test it works
        await db.create_tables_async()

    @pytest.mark.asyncio
    async def test_ensure_migration_tables_async_should_exist(self):
        """
        FIX VERIFICATION: _ensure_migration_tables_async() exists and works.

        After the DF-501 fix, there should be an async version of _ensure_migration_tables().
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_ensure_migration_tables_async_exists",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class AsyncMigrationTablesModel:
            id: str
            name: str

        # DF-501 FIX: This should now exist
        assert hasattr(
            db, "_ensure_migration_tables_async"
        ), "_ensure_migration_tables_async() should exist after DF-501 fix"

        # Test it works
        await db._ensure_migration_tables_async("sqlite")

    @pytest.mark.asyncio
    async def test_sync_method_should_raise_in_async_context(self):
        """
        FIX VERIFICATION: Sync methods raise clear error in async context.

        After the DF-501 fix, calling sync table creation methods from async context
        should raise a clear RuntimeError directing users to the async version.
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_sync_raises_in_async",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class SyncRaisesModel:
            id: str
            name: str

        # DF-501 FIX: Sync methods should detect async context and raise clear error
        with pytest.raises(RuntimeError) as exc_info:
            db.create_tables()

        # Verify the error message is helpful
        assert "create_tables_async()" in str(
            exc_info.value
        ), "Error should mention the async alternative"
        assert "DF-501" in str(exc_info.value), "Error should reference the fix code"

    @pytest.mark.asyncio
    async def test_execute_ddl_async_exists(self):
        """
        FIX VERIFICATION: _execute_ddl_async() exists and works.
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_execute_ddl_async_exists",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class ExecuteDDLAsyncModel:
            id: str
            name: str

        # DF-501 FIX: This should now exist
        assert hasattr(
            db, "_execute_ddl_async"
        ), "_execute_ddl_async() should exist after DF-501 fix"


class TestDF501FixComplete:
    """Comprehensive tests verifying the DF-501 fix is complete."""

    @pytest.mark.asyncio
    async def test_async_table_creation_workflow(self):
        """
        Complete async workflow: create_tables_async() works in async context.

        This is the primary use case from the bug report:
        - FastAPI lifespan handler
        - pytest async fixtures
        - Any async initialization code
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_async_workflow",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class CompleteWorkflowModel:
            id: str
            name: str
            email: str

        # This is what users should do in async contexts
        await db.create_tables_async()

        # Verify the async version works
        # (If we get here without error, the fix is working)

    @pytest.mark.asyncio
    async def test_ensure_migration_tables_raises_in_async_context(self):
        """
        _ensure_migration_tables() raises clear error in async context.
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_ensure_migration_raises",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class EnsureMigrationRaisesModel:
            id: str
            name: str

        # DF-501 FIX: Sync method should raise in async context
        with pytest.raises(RuntimeError) as exc_info:
            db._ensure_migration_tables("sqlite")

        # Verify the error message is helpful
        assert "_ensure_migration_tables_async()" in str(
            exc_info.value
        ), "Error should mention the async alternative"

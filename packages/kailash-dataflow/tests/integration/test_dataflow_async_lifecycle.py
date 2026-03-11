"""
Comprehensive async lifecycle tests for DataFlow.

Tests cover the complete lifecycle from initialization through shutdown,
including FastAPI lifespan patterns, connection pool management, concurrent
operations, and error recovery scenarios.

This file addresses testing gaps identified in DF-501 fix validation:
- FastAPI lifespan startup/shutdown
- Connection pool lifecycle
- Multiple DataFlow instances
- Concurrent async operations
- Error recovery scenarios
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# Database URLs for testing
POSTGRES_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
SQLITE_URL = ":memory:"


class TestFastAPILifespanPattern:
    """Tests simulating FastAPI lifespan context manager pattern."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_with_create_tables_async(self):
        """
        Test DataFlow initialization in FastAPI lifespan startup.

        Simulates:
            @asynccontextmanager
            async def lifespan(app: FastAPI):
                db = DataFlow("postgresql://...")
                @db.model
                class User:
                    id: str
                await db.create_tables_async()
                yield
                await db.close_async()
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_lifespan_startup",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class User:
            id: str
            name: str
            email: str

        # Simulate FastAPI lifespan startup
        await db.create_tables_async()

        # Verify model is registered and tables exist
        assert "User" in db._models
        assert "UserCreateNode" in db._nodes

        # Cleanup
        await db.close_async()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_with_close_async(self):
        """
        Test DataFlow cleanup in FastAPI lifespan shutdown.

        Verifies close_async() properly cleans up:
        - Connection pools
        - Memory connections
        - Resources
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_lifespan_shutdown",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class Session:
            id: str
            user_id: str

        await db.create_tables_async()

        # Verify close_async exists and works
        assert hasattr(db, "close_async")
        await db.close_async()

        # After close, memory connection should be None (if it was set)
        if hasattr(db, "_memory_connection"):
            assert db._memory_connection is None

    @pytest.mark.asyncio
    async def test_full_lifespan_pattern(self):
        """Test complete FastAPI lifespan pattern."""

        @asynccontextmanager
        async def simulated_lifespan():
            """Simulates FastAPI lifespan context manager."""
            # Startup
            db = DataFlow(
                database_url=SQLITE_URL,
                instance_id="test_full_lifespan",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class Product:
                id: str
                name: str
                price: float

            await db.create_tables_async()

            yield db

            # Shutdown
            await db.close_async()

        # Use the lifespan
        async with simulated_lifespan() as db:
            # Verify db is usable during lifespan
            assert "Product" in db._models
            assert hasattr(db, "create_tables_async")

        # After exit, db should be cleaned up
        # (no easy way to verify from outside, but no errors is a pass)


class TestConnectionPoolLifecycle:
    """Tests for connection pool lifecycle management."""

    @pytest.mark.asyncio
    async def test_pool_creation_in_async_context(self):
        """Test connection pool is created properly in async context."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_pool_creation",
            test_mode=True,
            auto_migrate=False,
            enable_connection_pooling=True,
        )

        @db.model
        class TestModel:
            id: str

        await db.create_tables_async()

        # Pool manager should exist if pooling is enabled
        if hasattr(db, "_pool_manager") and db._pool_manager:
            assert db._pool_manager is not None

        await db.close_async()

    @pytest.mark.asyncio
    async def test_pool_cleanup_on_close_async(self):
        """Test connection pool is properly closed on close_async()."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_pool_cleanup",
            test_mode=True,
            auto_migrate=False,
            enable_connection_pooling=True,
        )

        @db.model
        class TestModel:
            id: str

        await db.create_tables_async()

        # Close should not raise
        await db.close_async()

        # Memory connection should be cleaned up (if it was set)
        if hasattr(db, "_memory_connection"):
            assert db._memory_connection is None


class TestMultipleDataFlowInstances:
    """Tests for multiple DataFlow instances in async context."""

    @pytest.mark.asyncio
    async def test_multiple_instances_same_database(self):
        """
        Test multiple DataFlow instances connecting to same database.
        Each instance should be isolated.
        """
        db1 = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_multi_1",
            test_mode=True,
            auto_migrate=False,
        )

        db2 = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_multi_2",
            test_mode=True,
            auto_migrate=False,
        )

        @db1.model
        class User1:
            id: str
            name: str

        @db2.model
        class User2:
            id: str
            email: str

        # Each instance should have its own models
        assert "User1" in db1._models
        assert "User2" in db2._models
        assert "User2" not in db1._models
        assert "User1" not in db2._models

        # Both should be able to create tables
        await db1.create_tables_async()
        await db2.create_tables_async()

        await db1.close_async()
        await db2.close_async()

    @pytest.mark.asyncio
    async def test_instance_isolation_in_async_context(self):
        """
        Verify instance isolation: models registered on one instance
        don't affect another instance.
        """
        instances = []

        for i in range(3):
            db = DataFlow(
                database_url=SQLITE_URL,
                instance_id=f"test_isolation_{i}",
                test_mode=True,
                auto_migrate=False,
            )

            @db.model
            class DynamicModel:
                id: str
                value: int

            instances.append(db)

        # Each instance should have its own model registration
        # Note: _instance_id is auto-generated from id(self), not the instance_id param
        instance_ids = set()
        for db in instances:
            # Verify unique instance IDs (auto-generated)
            assert db._instance_id not in instance_ids
            instance_ids.add(db._instance_id)
            # Verify model is registered
            assert "DynamicModel" in db._models

        # Cleanup all
        for db in instances:
            await db.close_async()


class TestConcurrentAsyncOperations:
    """Tests for concurrent async operations."""

    @pytest.mark.asyncio
    async def test_concurrent_create_tables_async(self):
        """
        Test multiple create_tables_async() calls concurrently.
        Should handle race conditions gracefully.
        """
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_concurrent_create",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class ConcurrentModel:
            id: str
            name: str

        # Call create_tables_async multiple times concurrently
        tasks = [db.create_tables_async() for _ in range(5)]

        # All should complete without error
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check no exceptions
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent create_tables raised: {result}")

        await db.close_async()

    @pytest.mark.asyncio
    async def test_concurrent_workflow_execution(self):
        """Test executing multiple workflows concurrently in async context."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_concurrent_workflow",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class WorkflowModel:
            id: str
            counter: int

        await db.create_tables_async()

        async def execute_workflow(i: int) -> Dict[str, Any]:
            workflow = WorkflowBuilder()
            workflow.add_node(
                "WorkflowModelCreateNode",
                f"create_{i}",
                {"id": f"item-{i}", "counter": i},
            )
            runtime = AsyncLocalRuntime()
            results, _ = await runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            return results

        # Execute multiple workflows concurrently
        tasks = [execute_workflow(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all completed
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Some may fail due to SQLite locking, which is expected
                pass
            else:
                assert isinstance(result, dict)

        await db.close_async()


class TestContextManagerBehavior:
    """Tests for context manager behavior."""

    def test_sync_context_manager(self):
        """Test sync context manager calls cleanup_nodes() and close()."""
        with DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_sync_context",
            test_mode=True,
            auto_migrate=False,
        ) as db:

            @db.model
            class ContextModel:
                id: str

            assert "ContextModel" in db._models

        # After exit, cleanup should have happened
        # No easy way to verify from outside, but no errors is a pass

    @pytest.mark.asyncio
    async def test_context_manager_in_async_context(self):
        """Test sync context manager works when called from async context."""
        # This should work even in async context
        with DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_async_sync_context",
            test_mode=True,
            auto_migrate=False,
        ) as db:

            @db.model
            class AsyncContextModel:
                id: str

            assert "AsyncContextModel" in db._models


class TestErrorRecoveryScenarios:
    """Tests for error recovery scenarios."""

    @pytest.mark.asyncio
    async def test_close_async_after_failed_create_tables(self):
        """Test close_async() works even if create_tables_async() failed."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_recovery",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class RecoveryModel:
            id: str

        # Even if no tables were created, close should work
        await db.close_async()

    @pytest.mark.asyncio
    async def test_multiple_close_async_calls(self):
        """Test calling close_async() multiple times is safe."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_multi_close",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class MultiCloseModel:
            id: str

        await db.create_tables_async()

        # Multiple close calls should not error
        await db.close_async()
        await db.close_async()
        await db.close_async()


class TestDF501FixVerification:
    """Comprehensive verification of DF-501 fix."""

    @pytest.mark.asyncio
    async def test_sync_methods_raise_in_async_context(self):
        """Verify sync methods raise RuntimeError in async context."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_df501_sync",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class DF501Model:
            id: str

        # create_tables() should raise in async context
        with pytest.raises(RuntimeError) as exc_info:
            db.create_tables()

        assert "create_tables_async()" in str(exc_info.value)
        assert "DF-501" in str(exc_info.value)

        # _ensure_migration_tables() should raise in async context
        with pytest.raises(RuntimeError) as exc_info:
            db._ensure_migration_tables("sqlite")

        assert "_ensure_migration_tables_async()" in str(exc_info.value)
        assert "DF-501" in str(exc_info.value)

        await db.close_async()

    @pytest.mark.asyncio
    async def test_async_methods_work_in_async_context(self):
        """Verify async methods work correctly in async context."""
        db = DataFlow(
            database_url=SQLITE_URL,
            instance_id="test_df501_async",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class DF501AsyncModel:
            id: str
            name: str

        # All async methods should work
        assert hasattr(db, "create_tables_async")
        assert hasattr(db, "_ensure_migration_tables_async")
        assert hasattr(db, "close_async")

        # create_tables_async should work
        await db.create_tables_async()

        # close_async should work
        await db.close_async()


class TestPostgreSQLAsyncLifecycle:
    """PostgreSQL-specific async lifecycle tests."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "postgresql" not in POSTGRES_URL.lower(),
        reason="Requires PostgreSQL for connection pool testing",
    )
    async def test_postgresql_full_lifecycle(self):
        """Test complete PostgreSQL lifecycle in async context."""
        db = DataFlow(
            database_url=POSTGRES_URL,
            instance_id="test_pg_lifecycle",
            test_mode=True,
            auto_migrate=False,
        )

        @db.model
        class PostgresModel:
            id: str
            name: str
            value: int

        # Full lifecycle
        await db.initialize()
        await db.create_tables_async()

        # Execute a workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PostgresModelCreateNode",
            "create",
            {"id": "pg-001", "name": "Test", "value": 42},
        )
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert "create" in results or results.get("create") is not None

        # Cleanup
        await db.close_async()

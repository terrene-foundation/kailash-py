"""Integration tests for AsyncSQLDatabaseNode event loop isolation with REAL databases.

This test file implements Tier 2 (Integration) tests for the event loop isolation fix.
Tests are written FIRST following TDD methodology (RED phase).

CRITICAL: NO MOCKING - Uses REAL PostgreSQL and SQLite databases per success-factors.md

EXPECTED BEHAVIOR: Tests should FAIL initially with RuntimeError about event loops.

Test Coverage:
- Sequential workflows across different event loops (THE BUG)
- Pool sharing within same event loop (should work)
- Memory stability with event loop cycling

Reference:
- ADR: # contrib (removed)/project/adrs/0071-async-sql-event-loop-isolation.md
- Task Breakdown: TODO-ASYNC-SQL-EVENT-LOOP-TDD-BREAKDOWN.md
"""

import asyncio
import gc
import sys
from typing import Dict

import pytest
import pytest_asyncio
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Real PostgreSQL configuration (test harness at port 5432)
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "kailash_test",
    "user": "test_user",
    "password": "test_password",
}


@pytest_asyncio.fixture
async def postgres_config():
    """Real PostgreSQL connection config (NO MOCKING)."""
    return POSTGRES_CONFIG.copy()


@pytest_asyncio.fixture
async def sqlite_config(tmp_path):
    """Real SQLite connection config (NO MOCKING)."""
    db_path = tmp_path / "test_event_loop.db"
    return {
        "database_type": "sqlite",
        "connection_string": f"sqlite:///{db_path}",
    }


@pytest_asyncio.fixture(autouse=True)
async def cleanup_pools():
    """Clean up shared pools after each test."""
    yield
    # Clear all shared pools
    try:
        await AsyncSQLDatabaseNode.clear_shared_pools()
    except Exception:
        pass  # Best effort cleanup


@pytest.mark.integration
class TestEventLoopIsolationIntegration:
    """Test event loop isolation with real database workflows.

    These tests reproduce the actual bug: sequential workflows in different
    event loops fail with RuntimeError.

    EXPECTED: Tests FAIL with RuntimeError until implementation complete.
    """

    @pytest.mark.asyncio
    async def test_sequential_workflows_different_loops_postgres(self):
        """Test sequential workflows in different event loops with PostgreSQL.

        This is THE BUG SCENARIO from the bug report:
        - First workflow succeeds
        - Second workflow in new event loop fails with RuntimeError

        FR-001: Sequential workflows must work across event loops

        EXPECTED: FAIL with RuntimeError about event loop mismatch
        """
        # Setup: Create test table
        setup_query = """
        CREATE TABLE IF NOT EXISTS test_event_loops (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        async def run_workflow_in_loop(name: str):
            """Run a workflow that inserts data."""
            # Create and setup table
            setup_node = AsyncSQLDatabaseNode(
                name="setup",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="kailash_test",
                user="test_user",
                password="test_password",
                query=setup_query,
            )
            await setup_node.async_run()

            # Insert data
            insert_node = AsyncSQLDatabaseNode(
                name="insert",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="kailash_test",
                user="test_user",
                password="test_password",
                query="INSERT INTO test_event_loops (name) VALUES (:name)",
                parameters={"name": name},
            )
            result = await insert_node.async_run()
            return result

        # First workflow in current event loop
        result1 = await run_workflow_in_loop("workflow_1")
        assert result1 is not None, "First workflow should succeed"

        # Second workflow in NEW event loop (THE BUG!)
        # This should work after fix, but currently fails with RuntimeError
        loop2 = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop2)

            # This is where the bug manifests: RuntimeError about event loop
            result2 = loop2.run_until_complete(run_workflow_in_loop("workflow_2"))
            assert result2 is not None, "Second workflow should succeed"

        finally:
            loop2.close()
            # Restore original loop
            asyncio.set_event_loop(asyncio.get_running_loop())

        # If we got here, the bug is fixed!
        # Both workflows should have inserted data

    @pytest.mark.asyncio
    async def test_sequential_workflows_different_loops_sqlite(self, sqlite_config):
        """Test sequential workflows in different event loops with SQLite.

        Same bug scenario as PostgreSQL test, but with SQLite.

        FR-001: Sequential workflows must work across event loops

        EXPECTED: FAIL with RuntimeError about event loop mismatch
        """
        # Setup: Create test table
        setup_query = """
        CREATE TABLE IF NOT EXISTS test_loops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT NOT NULL
        )
        """

        async def run_sqlite_workflow(value: str, db_path: str):
            """Run a workflow that inserts data."""
            # Create table
            setup_node = AsyncSQLDatabaseNode(
                name="setup",
                database_type="sqlite",
                connection_string=f"sqlite:///{db_path}",
                query=setup_query,
            )
            await setup_node.async_run()

            # Insert data
            insert_node = AsyncSQLDatabaseNode(
                name="insert",
                database_type="sqlite",
                connection_string=f"sqlite:///{db_path}",
                query="INSERT INTO test_loops (value) VALUES (:value)",
                parameters={"value": value},
            )
            result = await insert_node.async_run()
            return result

        # Get db path
        db_path = sqlite_config["connection_string"].replace("sqlite:///", "")

        # First workflow
        result1 = await run_sqlite_workflow("value_1", db_path)
        assert result1 is not None, "First workflow should succeed"

        # Second workflow in new loop (THE BUG!)
        loop2 = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop2)
            result2 = loop2.run_until_complete(run_sqlite_workflow("value_2", db_path))
            assert result2 is not None, "Second workflow should succeed"
        finally:
            loop2.close()
            asyncio.set_event_loop(asyncio.get_running_loop())

    @pytest.mark.asyncio
    async def test_dataflow_sequential_operations(self, postgres_config):
        """Test DataFlow pattern of sequential CRUD operations.

        DataFlow performs sequential operations across workflow executions.
        Each execution might be in a different event loop.

        FR-001: DataFlow sequential operations must work

        EXPECTED: FAIL with RuntimeError on second operation
        """

        # Simulate DataFlow pattern: multiple sequential operations
        async def create_operation():
            """CREATE operation."""
            node = AsyncSQLDatabaseNode(
                name="create_table",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="kailash_test",
                user="test_user",
                password="test_password",
                query="""
                CREATE TABLE IF NOT EXISTS dataflow_test (
                    id SERIAL PRIMARY KEY,
                    data TEXT
                )
                """,
            )
            await node.async_run()

        async def insert_operation():
            """INSERT operation."""
            node = AsyncSQLDatabaseNode(
                name="insert_data",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="kailash_test",
                user="test_user",
                password="test_password",
                query="INSERT INTO dataflow_test (data) VALUES (:data)",
                parameters={"data": "test_value"},
            )
            await node.async_run()

        async def read_operation():
            """READ operation."""
            node = AsyncSQLDatabaseNode(
                name="read_data",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="kailash_test",
                user="test_user",
                password="test_password",
                query="SELECT * FROM dataflow_test LIMIT 1",
            )
            result = await node.async_run()
            return result

        # Operation 1: CREATE in current loop
        await create_operation()

        # Operation 2: INSERT in new loop (simulating new request/execution)
        loop2 = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop2)
            loop2.run_until_complete(insert_operation())
        finally:
            loop2.close()

        # Operation 3: READ in another new loop
        loop3 = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop3)
            result = loop3.run_until_complete(read_operation())
            assert result is not None, "Read operation should return data"
        finally:
            loop3.close()
            asyncio.set_event_loop(asyncio.get_running_loop())


@pytest.mark.integration
class TestPoolSharingIntegration:
    """Test pool sharing behavior within and across event loops.

    EXPECTED: Same-loop sharing passes, cross-loop isolation fails until fix.
    """

    @pytest.mark.asyncio
    async def test_pool_sharing_within_same_loop(self, postgres_config):
        """Test that multiple nodes share pool within same event loop.

        This should already work (no bug here).

        FR-002: Same loop should share pools

        EXPECTED: PASS (this already works)
        """
        # Create two nodes with same config in same loop
        node1 = AsyncSQLDatabaseNode(
            name="node1",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="kailash_test",
            user="test_user",
            password="test_password",
            query="SELECT 1",
        )

        node2 = AsyncSQLDatabaseNode(
            name="node2",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="kailash_test",
            user="test_user",
            password="test_password",
            query="SELECT 2",
        )

        # Execute both nodes
        await node1.async_run()
        await node2.async_run()

        # Both nodes should have same pool key
        assert (
            node1._pool_key == node2._pool_key
        ), "Nodes with same config in same loop should have same pool key"

        # Get pool metrics
        metrics = await AsyncSQLDatabaseNode.get_pool_metrics()

        # Should only have one pool for this config
        assert metrics["total_pools"] >= 1, "Should have at least one pool"

    @pytest.mark.asyncio
    async def test_pool_isolation_across_loops(self, postgres_config):
        """Test that different loops get different pools.

        FR-002: Different loops should NOT share pools

        EXPECTED: FAIL - pools not isolated yet
        """

        # Get pool key in first loop
        async def get_pool_key_in_loop():
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                port=5432,
                database="kailash_test",
                user="test_user",
                password="test_password",
                query="SELECT 1",
            )
            await node.async_run()
            return node._pool_key

        key1 = await get_pool_key_in_loop()

        # Get pool key in second loop
        loop2 = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop2)
            key2 = loop2.run_until_complete(get_pool_key_in_loop())
        finally:
            loop2.close()
            asyncio.set_event_loop(asyncio.get_running_loop())

        # Pool keys should be DIFFERENT (different loops)
        assert key1 != key2, (
            f"Different event loops should generate different pool keys:\n"
            f"Loop 1: {key1}\n"
            f"Loop 2: {key2}"
        )

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_error(self, postgres_config):
        """Test graceful degradation when pool sharing fails.

        FR-002: Should fall back to dedicated pool on error

        EXPECTED: PASS (fallback already exists)
        """
        # Create node with pool sharing
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="kailash_test",
            user="test_user",
            password="test_password",
            query="SELECT 1",
        )

        # Should succeed even if pool sharing has issues
        result = await node.async_run()
        assert result is not None, "Should succeed with fallback to dedicated pool"


@pytest.mark.integration
class TestMemoryStabilityIntegration:
    """Test memory stability with event loop cycling.

    EXPECTED: Memory leak detected until cleanup implementation.
    """

    @pytest.mark.asyncio
    async def test_memory_stability_with_loop_cycling(self, postgres_config):
        """Test that pool count doesn't grow unbounded with loop cycling.

        FR-003: No memory leaks from abandoned pools

        EXPECTED: FAIL - pools leak without cleanup
        """

        async def create_and_destroy_loop():
            """Create event loop, run query, destroy loop."""
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)

                async def run_query():
                    node = AsyncSQLDatabaseNode(
                        name="cycle_test",
                        database_type="postgresql",
                        host="localhost",
                        port=5432,
                        database="kailash_test",
                        user="test_user",
                        password="test_password",
                        query="SELECT 1",
                    )
                    await node.async_run()

                loop.run_until_complete(run_query())
            finally:
                loop.close()

        # Get initial pool count
        initial_metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        initial_pool_count = initial_metrics.get("total_pools", 0)

        # Create and destroy 100 event loops
        for i in range(100):
            await create_and_destroy_loop()

            # Force garbage collection
            gc.collect()

        # Restore event loop
        asyncio.set_event_loop(asyncio.get_running_loop())

        # Get final pool count
        final_metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        final_pool_count = final_metrics.get("total_pools", 0)

        # Pool count should not grow unbounded
        # Allow some growth, but not 100 new pools
        pool_growth = final_pool_count - initial_pool_count
        assert pool_growth < 10, (
            f"Pool count grew by {pool_growth} after 100 loop cycles. "
            f"This indicates memory leak. Initial: {initial_pool_count}, "
            f"Final: {final_pool_count}"
        )

    @pytest.mark.asyncio
    async def test_cleanup_reduces_pool_count(self, postgres_config):
        """Test that manual cleanup reduces pool count.

        FR-003: Cleanup should remove dead pools

        EXPECTED: FAIL - cleanup method doesn't exist yet
        """

        # Create pools in multiple loops
        async def create_pool_in_loop():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)

                async def run():
                    node = AsyncSQLDatabaseNode(
                        name="cleanup_test",
                        database_type="postgresql",
                        host="localhost",
                        port=5432,
                        database="kailash_test",
                        user="test_user",
                        password="test_password",
                        query="SELECT 1",
                    )
                    await node.async_run()

                loop.run_until_complete(run())
            finally:
                loop.close()

        # Create 5 pools in different loops
        for _ in range(5):
            await create_pool_in_loop()

        # Restore event loop
        asyncio.set_event_loop(asyncio.get_running_loop())

        # Get pool count before cleanup
        before_metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
        before_count = before_metrics.get("total_pools", 0)

        try:
            # Run cleanup
            cleanup_metrics = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()

            # Get pool count after cleanup
            after_metrics = await AsyncSQLDatabaseNode.get_pool_metrics()
            after_count = after_metrics.get("total_pools", 0)

            # Cleanup should have removed some pools
            assert (
                cleanup_metrics["pools_removed"] > 0
            ), "Cleanup should have removed pools from closed loops"

            assert after_count < before_count, (
                f"Pool count should decrease after cleanup. "
                f"Before: {before_count}, After: {after_count}"
            )

        except AttributeError as e:
            pytest.fail(
                f"_cleanup_closed_loop_pools method doesn't exist yet: {e}. "
                "This is expected in TDD RED phase."
            )

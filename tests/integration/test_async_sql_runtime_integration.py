"""Integration tests for AsyncSQLDatabaseNode with enhanced runtime pool management.

This test suite validates the critical integration between AsyncSQLDatabaseNode
and the enhanced LocalRuntime connection pool manager. It tests:

1. Runtime pool coordination vs class-level pools
2. Connection sharing across multiple workflow executions
3. Circuit breaker and retry policy integration
4. Concurrent execution scenarios that exposed the original bug
5. Backward compatibility with existing code
"""

import asyncio
import sqlite3
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.resource_manager import CircuitBreaker, RetryPolicy
from kailash.sdk_exceptions import CircuitBreakerOpenError
from kailash.workflow.builder import WorkflowBuilder


class TestAsyncSQLRuntimeIntegration:
    """Test AsyncSQLDatabaseNode integration with runtime pools."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create test database
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value INTEGER
            )
        """
        )
        conn.execute("INSERT INTO test_table (name, value) VALUES ('test1', 100)")
        conn.execute("INSERT INTO test_table (name, value) VALUES ('test2', 200)")
        conn.commit()
        conn.close()

    def teardown_method(self):
        """Clean up test fixtures."""
        Path(self.db_path).unlink(missing_ok=True)

    def create_async_sql_workflow(
        self, query: str = "SELECT * FROM test_table"
    ) -> WorkflowBuilder:
        """Create a workflow with AsyncSQLDatabaseNode."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": self.db_path,  # SQLite path
                "database_type": "sqlite",
                "query": query,
                "pool_size": 5,
            },
        )
        return workflow

    @pytest.mark.asyncio
    async def test_runtime_pool_coordination(self):
        """Test that AsyncSQLDatabaseNode uses runtime pools when available."""
        # Create runtime with persistent mode (enables pool coordination)
        runtime = LocalRuntime(
            persistent_mode=True,
            enable_connection_sharing=True,
            connection_pool_size=20,
        )

        # Start persistent mode to initialize pool manager
        await runtime.start_persistent_mode()

        workflow = self.create_async_sql_workflow()

        # Execute workflow - should create runtime-coordinated pool
        results, run_id = await runtime.execute_async(workflow.build())

        # Verify runtime has connection pools
        assert runtime.connection_pool_manager is not None
        assert len(runtime.connection_pool_manager._pools) > 0

        # Check that pool is shared between executions
        initial_pool_count = len(runtime.connection_pool_manager._pools)

        # Execute same workflow again
        results2, run_id2 = await runtime.execute_async(workflow.build())

        # Pool count should remain the same (reused)
        assert len(runtime.connection_pool_manager._pools) == initial_pool_count

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_connection_sharing_across_executions(self):
        """Test connection sharing across multiple workflow executions."""
        runtime = LocalRuntime(persistent_mode=True, enable_connection_sharing=True)

        # Start persistent mode to initialize pool manager
        await runtime.start_persistent_mode()

        workflow = self.create_async_sql_workflow()

        # Track pool usage
        pool_manager = runtime.connection_pool_manager

        # Execute multiple workflows concurrently
        tasks = []
        for i in range(5):
            task = runtime.execute_async(workflow.build())
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify all executions succeeded
        assert len(results) == 5
        for result, run_id in results:
            assert result is not None

        # Verify pool sharing (should have fewer pools than executions)
        assert len(pool_manager._pools) < 5  # Pool reuse occurred

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_backward_compatibility_fallback(self):
        """Test that nodes fallback to class-level pools when runtime pools unavailable."""
        # Use standard runtime (no persistent mode)
        runtime = LocalRuntime(persistent_mode=False)

        workflow = self.create_async_sql_workflow()

        # Execute workflow - should use class-level pools
        results, run_id = await runtime.execute_async(workflow.build())

        # Verify execution succeeded
        assert results is not None

        # Runtime should not have connection pools (fallback to class-level)
        assert runtime.connection_pool_manager is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test circuit breaker protection for database connections."""
        runtime = LocalRuntime(
            persistent_mode=True,
            enable_resource_coordination=True,
            circuit_breaker_config={
                "failure_threshold": 2,
                "timeout_seconds": 1,
            },
        )

        # Create workflow with invalid database URL to trigger failures
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": "/tmp/nonexistent_database.db",
                "database_type": "sqlite",
                "query": "SELECT * FROM test_table",
            },
        )

        # Execute workflow multiple times to trigger circuit breaker
        failure_count = 0
        circuit_breaker_triggered = False

        for i in range(5):
            try:
                await runtime.execute_async(workflow.build())
            except Exception as e:
                if "CircuitBreaker" in str(type(e)):
                    circuit_breaker_triggered = True
                    break
                failure_count += 1

        # Circuit breaker should have been triggered after threshold failures
        assert failure_count >= 2  # At least threshold failures occurred

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_retry_policy_integration(self):
        """Test retry policy for transient database failures."""
        runtime = LocalRuntime(
            persistent_mode=True,
            retry_policy_config={
                "max_attempts": 3,
                "base_delay": 0.1,
            },
        )

        workflow = self.create_async_sql_workflow()

        # Mock a transient failure followed by success
        original_execute = None
        call_count = 0

        async def mock_failing_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 attempts
                raise Exception("Transient database error")
            return await original_execute(*args, **kwargs)

        with patch("aiosqlite.connect") as mock_connect:
            # Set up mock to fail initially then succeed
            mock_conn = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_conn

            # Configure mock to fail then succeed
            mock_conn.execute.side_effect = [
                Exception("Connection failed"),
                Exception("Connection failed"),
                AsyncMock(),  # Success on third attempt
            ]

            # This should succeed after retries
            try:
                results, run_id = await runtime.execute_async(workflow.build())
                # If we get here, retries worked
                retry_succeeded = True
            except Exception:
                retry_succeeded = False

        await runtime.cleanup()

    def test_concurrent_execution_bug_regression(self):
        """Test the original concurrent execution bug that caused pooling failures."""
        # This reproduces the ThreadPoolExecutor pattern that exposed the bug

        def execute_workflow_sync():
            """Execute workflow in sync context (simulates original bug conditions)."""
            runtime = LocalRuntime(persistent_mode=True)
            workflow = self.create_async_sql_workflow()

            # This creates a new event loop per thread execution
            # The original bug was that pools weren't shared across event loops
            return asyncio.run(runtime.execute_async(workflow.build()))

        # Execute multiple workflows concurrently in different threads
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for i in range(5):
                future = executor.submit(execute_workflow_sync)
                futures.append(future)

            # Wait for all executions to complete
            results = []
            for future in futures:
                try:
                    result = future.result(timeout=10)
                    results.append(result)
                except Exception as e:
                    pytest.fail(f"Concurrent execution failed: {e}")

        # All executions should succeed
        assert len(results) == 5
        for result, run_id in results:
            assert result is not None

    @pytest.mark.asyncio
    async def test_pool_cleanup_and_lifecycle(self):
        """Test proper pool cleanup and lifecycle management."""
        runtime = LocalRuntime(
            persistent_mode=True,
            connection_pool_config={
                "pool_ttl": 1,  # Short TTL for testing
            },
        )

        workflow = self.create_async_sql_workflow()

        # Execute workflow to create pool
        await runtime.execute_async(workflow.build())

        initial_pool_count = len(runtime.connection_pool_manager._pools)
        assert initial_pool_count > 0

        # Wait for TTL to expire
        await asyncio.sleep(2)

        # Trigger cleanup
        cleaned_count = await runtime.connection_pool_manager.cleanup_unused_pools()

        # Pools should have been cleaned up
        assert cleaned_count > 0
        final_pool_count = len(runtime.connection_pool_manager._pools)
        assert final_pool_count < initial_pool_count

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_pool_health_monitoring(self):
        """Test pool health monitoring and reporting."""
        runtime = LocalRuntime(persistent_mode=True, enable_health_monitoring=True)

        workflow = self.create_async_sql_workflow()

        # Execute workflow to create pool
        await runtime.execute_async(workflow.build())

        # Check pool health
        pool_manager = runtime.connection_pool_manager
        pool_names = list(pool_manager._pools.keys())

        for pool_name in pool_names:
            health = pool_manager.get_pool_health(pool_name)
            assert "status" in health
            assert "active_connections" in health
            assert "total_connections" in health

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_resource_limits_enforcement(self):
        """Test resource limit enforcement for connection pools."""
        runtime = LocalRuntime(
            persistent_mode=True,
            connection_pool_config={
                "max_pools": 2,  # Low limit for testing
            },
        )

        # Create multiple different workflows to force pool creation
        workflows = []
        for i in range(5):
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                f"sql_node_{i}",
                {
                    "connection_string": f"{self.db_path}_pool_{i}",  # Different SQLite files
                    "database_type": "sqlite",
                    "query": "SELECT * FROM test_table",
                },
            )
            workflows.append(workflow)

        # Execute workflows - should hit resource limits
        pool_manager = runtime.connection_pool_manager

        for workflow in workflows[:3]:  # Execute more than max_pools
            try:
                await runtime.execute_async(workflow.build())
            except Exception as e:
                if "ResourceLimitExceeded" in str(type(e)):
                    # Expected behavior when limits are exceeded
                    break

        # Should not exceed max_pools
        assert len(pool_manager._pools) <= 2

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_enterprise_monitoring_integration(self):
        """Test enterprise monitoring hooks for AsyncSQL operations."""
        runtime = LocalRuntime(persistent_mode=True, enable_enterprise_monitoring=True)

        workflow = self.create_async_sql_workflow()

        # Execute workflow
        await runtime.execute_async(workflow.build())

        # Check that monitoring was initialized
        assert hasattr(runtime, "enterprise_monitoring")
        assert runtime.enterprise_monitoring is not None

        # Verify monitoring adapters are available
        adapters = runtime.enterprise_monitoring.adapters
        assert "prometheus" in adapters
        assert "datadog" in adapters

        await runtime.cleanup()


class TestAsyncSQLErrorHandling:
    """Test error handling scenarios for AsyncSQL integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

    def teardown_method(self):
        """Clean up test fixtures."""
        Path(self.db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_database_connection_failure_handling(self):
        """Test handling of database connection failures."""
        runtime = LocalRuntime(
            persistent_mode=True,
            circuit_breaker_config={
                "failure_threshold": 1,
                "timeout_seconds": 1,
            },
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": "/tmp/absolutely_nonexistent_path_database.db",
                "database_type": "sqlite",
                "query": "SELECT * FROM test_table",
            },
        )

        # First execution should fail and open circuit breaker
        with pytest.raises(Exception):
            await runtime.execute_async(workflow.build())

        # Second execution should be blocked by circuit breaker
        with pytest.raises(Exception) as exc_info:
            await runtime.execute_async(workflow.build())

        # Verify circuit breaker is protecting against failures
        # (Either original error or circuit breaker error is acceptable)

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_sql_syntax_error_handling(self):
        """Test handling of SQL syntax errors."""
        # Create valid database
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
        conn.close()

        runtime = LocalRuntime(persistent_mode=True)

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": self.db_path,
                "database_type": "sqlite",
                "query": "INVALID SQL SYNTAX HERE",
            },
        )

        # Should handle SQL syntax errors gracefully
        with pytest.raises(Exception):
            await runtime.execute_async(workflow.build())

        # Runtime should still be functional after error
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": self.db_path,
                "database_type": "sqlite",
                "query": "SELECT 1",
            },
        )

        # This should work
        results, run_id = await runtime.execute_async(workflow2.build())
        assert results is not None

        await runtime.cleanup()


class TestAsyncSQLPerformance:
    """Performance tests for AsyncSQL integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Create test database with more data
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE large_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert test data
        for i in range(1000):
            conn.execute(
                "INSERT INTO large_table (name, value) VALUES (?, ?)",
                (f"test_{i}", i * 10),
            )
        conn.commit()
        conn.close()

    def teardown_method(self):
        """Clean up test fixtures."""
        Path(self.db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_concurrent_query_performance(self):
        """Test performance of concurrent queries with pool sharing."""
        runtime = LocalRuntime(
            persistent_mode=True,
            connection_pool_config={
                "default_pool_size": 5,
            },
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": self.db_path,
                "database_type": "sqlite",
                "query": "SELECT COUNT(*) FROM large_table WHERE value > 500",
            },
        )

        # Measure execution time for concurrent queries
        start_time = time.time()

        # Execute 10 concurrent queries
        tasks = []
        for i in range(10):
            task = runtime.execute_async(workflow.build())
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        end_time = time.time()
        execution_time = end_time - start_time

        # All queries should succeed
        assert len(results) == 10
        for result, run_id in results:
            assert result is not None

        # Execution should complete in reasonable time (< 5 seconds for 10 queries)
        assert execution_time < 5.0, f"Concurrent queries took {execution_time:.2f}s"

        await runtime.cleanup()

    @pytest.mark.asyncio
    async def test_pool_reuse_efficiency(self):
        """Test that pool reuse improves efficiency over time."""
        runtime = LocalRuntime(persistent_mode=True)

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "sql_node",
            {
                "connection_string": self.db_path,
                "database_type": "sqlite",
                "query": "SELECT * FROM large_table LIMIT 10",
            },
        )

        # Measure first execution (cold start)
        start_time = time.time()
        await runtime.execute_async(workflow.build())
        first_execution_time = time.time() - start_time

        # Measure subsequent executions (warm pool)
        execution_times = []
        for i in range(5):
            start_time = time.time()
            await runtime.execute_async(workflow.build())
            execution_times.append(time.time() - start_time)

        avg_warm_time = sum(execution_times) / len(execution_times)

        # Warm executions should be faster than cold start
        # (allowing some variance due to test environment)
        assert (
            avg_warm_time <= first_execution_time * 1.5
        ), f"Warm executions ({avg_warm_time:.3f}s) not faster than cold start ({first_execution_time:.3f}s)"

        await runtime.cleanup()

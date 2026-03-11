"""
Integration Tests for DataFlow TDD Infrastructure

Tests the complete TDD infrastructure with real PostgreSQL connections,
transaction isolation, and performance validation. These tests verify
that the TDD infrastructure provides the promised performance improvements
while maintaining proper test isolation.

Key test scenarios:
- Real PostgreSQL connection management
- Savepoint-based test isolation
- Performance validation (<100ms target)
- Integration with DataFlow engine
- Zero impact on existing users
"""

import asyncio
import os
import time
from typing import Any, Dict

import asyncpg
import pytest

# Import DataFlow for engine integration tests
from dataflow import DataFlow

# Import TDD infrastructure
from dataflow.testing.tdd_support import (
    TDDDatabaseManager,
    TDDTestContext,
    TDDTransactionManager,
    clear_test_context,
    get_test_context,
    is_tdd_mode,
    set_test_context,
    setup_tdd_infrastructure,
    tdd_test_context,
    teardown_tdd_infrastructure,
)

from kailash.runtime.local import LocalRuntime
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
    return LocalRuntime()


@pytest.mark.asyncio
class TestTDDInfrastructureIntegration:
    """Integration tests for TDD infrastructure with real PostgreSQL."""

    async def test_database_manager_real_connection(self):
        """Test database manager with real PostgreSQL connection."""
        # Start test environment first
        await self._ensure_test_environment()

        db_manager = TDDDatabaseManager()
        await db_manager.initialize()

        context = TDDTestContext(test_id="integration_test_001")

        try:
            # Get real connection
            connection = await db_manager.get_test_connection(context)

            # Verify it's a real asyncpg connection
            assert isinstance(connection, asyncpg.Connection)

            # Test actual database operation
            result = await connection.fetch("SELECT 1 as test_value")
            assert len(result) == 1
            assert result[0]["test_value"] == 1

            # Test connection reuse
            connection2 = await db_manager.get_test_connection(context)
            assert connection == connection2  # Should be same connection

        finally:
            await db_manager.cleanup_test_connection(context)
            await db_manager.close()

    async def test_transaction_manager_real_savepoints(self):
        """Test transaction manager with real PostgreSQL savepoints."""
        await self._ensure_test_environment()

        db_manager = TDDDatabaseManager()
        tx_manager = TDDTransactionManager()
        await db_manager.initialize()

        context = TDDTestContext(test_id="integration_test_002")

        try:
            connection = await db_manager.get_test_connection(context)

            # Begin transaction and create savepoint
            await tx_manager.begin_test_transaction(connection, context)

            # Verify savepoint was created
            assert context.savepoint_created is True

            # Create a test table for isolation testing
            await connection.execute(
                """
                CREATE TEMPORARY TABLE tdd_test_isolation (
                    id SERIAL PRIMARY KEY,
                    value TEXT
                ) ON COMMIT PRESERVE ROWS
            """
            )

            # Insert test data
            await connection.execute(
                "INSERT INTO tdd_test_isolation (value) VALUES ('test_data')"
            )

            # Verify data exists
            result = await connection.fetch("SELECT * FROM tdd_test_isolation")
            assert len(result) == 1
            assert result[0]["value"] == "test_data"

            # Rollback to savepoint
            await tx_manager.rollback_to_savepoint(connection, context)

            # Verify rollback worked (data should be gone)
            result = await connection.fetch("SELECT * FROM tdd_test_isolation")
            assert len(result) == 0

        finally:
            await db_manager.cleanup_test_connection(context)
            await db_manager.close()

    async def test_tdd_context_manager_real_isolation(self):
        """Test TDD context manager with real transaction isolation."""
        await self._ensure_test_environment()

        # Test 1: Create data in first context
        async with tdd_test_context(test_id="isolation_test_1") as ctx1:
            connection = ctx1.connection

            # Create temporary table
            await connection.execute(
                """
                CREATE TEMPORARY TABLE tdd_isolation_test (
                    id SERIAL PRIMARY KEY,
                    test_context TEXT
                ) ON COMMIT PRESERVE ROWS
            """
            )

            # Insert data
            await connection.execute(
                "INSERT INTO tdd_isolation_test (test_context) VALUES ('context_1')"
            )

            # Verify data exists
            result = await connection.fetch("SELECT * FROM tdd_isolation_test")
            assert len(result) == 1
            assert result[0]["test_context"] == "context_1"

        # Test 2: Verify isolation in second context
        async with tdd_test_context(test_id="isolation_test_2") as ctx2:
            connection = ctx2.connection

            # The temporary table should not exist in this context
            # (each test gets its own isolated transaction)
            with pytest.raises(asyncpg.UndefinedTableError):
                await connection.fetch("SELECT * FROM tdd_isolation_test")

    async def test_performance_optimization(self, enable_tdd_mode):
        """Test that TDD infrastructure provides performance improvements."""
        await self._ensure_test_environment()

        performance_results = []

        # Test multiple TDD contexts to measure performance
        for i in range(5):
            start_time = time.time()

            async with tdd_test_context(test_id=f"perf_test_{i}") as ctx:
                connection = ctx.connection

                # Perform typical test operations
                await connection.execute("SELECT NOW()")
                await connection.execute("SELECT version()")

                # Simple transaction operation
                await connection.execute("BEGIN")
                await connection.execute("SELECT 1")
                await connection.execute("ROLLBACK")

            end_time = time.time()
            execution_time = (end_time - start_time) * 1000  # Convert to ms
            performance_results.append(execution_time)

        # Verify performance targets
        avg_time = sum(performance_results) / len(performance_results)
        max_time = max(performance_results)

        # These should be significantly faster than the 2000ms baseline
        assert avg_time < 100, f"Average time {avg_time:.2f}ms exceeds 100ms target"
        assert max_time < 200, f"Max time {max_time:.2f}ms exceeds 200ms limit"

        print(f"TDD Performance Results: avg={avg_time:.2f}ms, max={max_time:.2f}ms")

    async def test_engine_integration(self, enable_tdd_mode):
        """Test integration with DataFlow engine connection management."""
        await self._ensure_test_environment()

        # Create DataFlow with TDD-aware configuration
        config = {
            "database_url": "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
            "existing_schema_mode": True,
            "auto_migrate": False,
            "cache_enabled": False,
        }

        df = DataFlow(**config)

        try:
            # Test that engine uses TDD infrastructure when in TDD context
            async with tdd_test_context(test_id="engine_integration") as ctx:
                # Set test context for engine to use
                set_test_context(ctx)

                # Get connection through engine
                engine_connection = await df.engine._get_async_database_connection()

                # Should be the same connection as TDD context
                assert engine_connection == ctx.connection

                # Verify it works for actual operations
                result = await engine_connection.fetch("SELECT 'engine_test' as value")
                assert result[0]["value"] == "engine_test"

        finally:
            clear_test_context()
            df.close()

    async def test_concurrent_test_isolation(self, enable_tdd_mode):
        """Test that concurrent tests are properly isolated."""
        await self._ensure_test_environment()

        async def isolated_test_operation(test_id: str, test_value: str):
            """Simulate a test operation with data isolation."""
            async with tdd_test_context(test_id=test_id) as ctx:
                connection = ctx.connection

                # Create table and insert test-specific data
                await connection.execute(
                    f"""
                    CREATE TEMPORARY TABLE test_data_{test_id} (
                        value TEXT
                    ) ON COMMIT PRESERVE ROWS
                """
                )

                await connection.execute(
                    f"INSERT INTO test_data_{test_id} (value) VALUES ($1)", test_value
                )

                # Verify our data
                result = await connection.fetch(
                    f"SELECT value FROM test_data_{test_id}"
                )
                assert len(result) == 1
                assert result[0]["value"] == test_value

                # Small delay to simulate test work
                await asyncio.sleep(0.01)

                # Verify data is still there
                result = await connection.fetch(
                    f"SELECT value FROM test_data_{test_id}"
                )
                assert len(result) == 1
                assert result[0]["value"] == test_value

                return test_value

        # Run multiple tests concurrently
        tasks = [
            isolated_test_operation("concurrent_1", "value_1"),
            isolated_test_operation("concurrent_2", "value_2"),
            isolated_test_operation("concurrent_3", "value_3"),
        ]

        results = await asyncio.gather(*tasks)

        # All tests should complete successfully with their own data
        assert results == ["value_1", "value_2", "value_3"]

    async def test_error_handling_and_cleanup(self, enable_tdd_mode):
        """Test error handling and proper cleanup in TDD infrastructure."""
        await self._ensure_test_environment()

        # Test that errors are handled gracefully
        try:
            async with tdd_test_context(test_id="error_test") as ctx:
                connection = ctx.connection

                # Create some test data
                await connection.execute(
                    """
                    CREATE TEMPORARY TABLE error_test_table (
                        id SERIAL PRIMARY KEY
                    ) ON COMMIT PRESERVE ROWS
                """
                )

                await connection.execute("INSERT INTO error_test_table DEFAULT VALUES")

                # Intentionally cause an error
                raise Exception("Simulated test error")

        except Exception as e:
            assert str(e) == "Simulated test error"

        # Verify cleanup occurred - new context should not see the data
        async with tdd_test_context(test_id="cleanup_verify") as ctx:
            connection = ctx.connection

            # Table should not exist (proper cleanup/isolation)
            with pytest.raises(asyncpg.UndefinedTableError):
                await connection.fetch("SELECT * FROM error_test_table")

    async def test_feature_flag_integration(self):
        """Test integration with DataFlow feature flag system."""
        # Test with TDD mode disabled
        original_env = os.environ.get("DATAFLOW_TDD_MODE")

        try:
            # Disable TDD mode
            os.environ.pop("DATAFLOW_TDD_MODE", None)
            assert is_tdd_mode() is False

            # Enable TDD mode
            os.environ["DATAFLOW_TDD_MODE"] = "true"
            assert is_tdd_mode() is True

            # Test various truthy values
            for value in ["TRUE", "Yes", "1", "on"]:
                os.environ["DATAFLOW_TDD_MODE"] = value
                assert is_tdd_mode() is True, f"Failed for value: {value}"

            # Test falsy values
            for value in ["false", "no", "0", "off"]:
                os.environ["DATAFLOW_TDD_MODE"] = value
                assert is_tdd_mode() is False, f"Failed for value: {value}"

        finally:
            # Restore original environment
            if original_env is None:
                os.environ.pop("DATAFLOW_TDD_MODE", None)
            else:
                os.environ["DATAFLOW_TDD_MODE"] = original_env

    async def test_zero_impact_on_existing_users(self):
        """Test that TDD infrastructure has zero impact when disabled."""
        # Ensure TDD mode is disabled
        original_env = os.environ.get("DATAFLOW_TDD_MODE")

        try:
            os.environ.pop("DATAFLOW_TDD_MODE", None)

            # Create standard DataFlow instance
            df = DataFlow(
                database_url="postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                existing_schema_mode=True,
            )

            # Test that normal operations work unchanged
            await df.initialize()

            # Get connection through normal engine path
            connection = await df.engine._get_async_database_connection()

            # Should be a normal connection, not TDD-managed
            assert isinstance(connection, asyncpg.Connection)

            # Should work normally
            result = await connection.fetch("SELECT 'normal_operation' as test")
            assert result[0]["test"] == "normal_operation"

            await connection.close()
            df.close()

        finally:
            # Restore environment
            if original_env is not None:
                os.environ["DATAFLOW_TDD_MODE"] = original_env

    async def _ensure_test_environment(self):
        """Ensure test environment is available."""
        # Check if test database is available
        try:
            connection = await asyncpg.connect(
                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test"
            )
            await connection.close()
        except Exception as e:
            pytest.skip(f"Test database not available: {e}")


@pytest.mark.asyncio
class TestTDDPerformanceBenchmarks:
    """Performance benchmarks for TDD infrastructure."""

    async def test_connection_reuse_performance(self, enable_tdd_mode):
        """Benchmark connection reuse performance."""
        await self._ensure_test_environment()

        # Benchmark: Multiple operations with connection reuse
        start_time = time.time()

        async with tdd_test_context(test_id="perf_benchmark") as ctx:
            connection = ctx.connection

            # Perform 50 database operations
            for i in range(50):
                await connection.execute("SELECT $1", i)

        end_time = time.time()
        total_time = (end_time - start_time) * 1000  # Convert to ms

        # Should be very fast due to connection reuse
        assert total_time < 500, f"50 operations took {total_time:.2f}ms (too slow)"

        avg_per_operation = total_time / 50
        assert (
            avg_per_operation < 10
        ), f"Average per operation: {avg_per_operation:.2f}ms (too slow)"

    async def test_savepoint_performance(self, enable_tdd_mode):
        """Benchmark savepoint creation and rollback performance."""
        await self._ensure_test_environment()

        savepoint_times = []
        rollback_times = []

        for i in range(10):
            async with tdd_test_context(test_id=f"savepoint_perf_{i}") as ctx:
                connection = ctx.connection
                tx_manager = TDDTransactionManager()

                # Measure savepoint creation
                start_time = time.time()
                await tx_manager.create_savepoint(connection, ctx)
                savepoint_time = (time.time() - start_time) * 1000
                savepoint_times.append(savepoint_time)

                # Do some work
                await connection.execute("CREATE TEMPORARY TABLE perf_test (id INT)")
                await connection.execute("INSERT INTO perf_test VALUES (1), (2), (3)")

                # Measure rollback
                start_time = time.time()
                await tx_manager.rollback_to_savepoint(connection, ctx)
                rollback_time = (time.time() - start_time) * 1000
                rollback_times.append(rollback_time)

        avg_savepoint_time = sum(savepoint_times) / len(savepoint_times)
        avg_rollback_time = sum(rollback_times) / len(rollback_times)

        # Savepoints should be very fast
        assert (
            avg_savepoint_time < 10
        ), f"Average savepoint time: {avg_savepoint_time:.2f}ms"
        assert (
            avg_rollback_time < 10
        ), f"Average rollback time: {avg_rollback_time:.2f}ms"

    async def _ensure_test_environment(self):
        """Ensure test environment is available."""
        try:
            connection = await asyncpg.connect(
                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test"
            )
            await connection.close()
        except Exception as e:
            pytest.skip(f"Test database not available: {e}")

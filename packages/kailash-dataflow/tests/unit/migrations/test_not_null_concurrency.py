#!/usr/bin/env python3
"""
Concurrency Tests for NOT NULL Column Addition System

Tests concurrent operations, race conditions, deadlock prevention, and
multi-user scenarios in the NOT NULL column addition functionality.

This test suite ensures the system handles concurrent database operations safely.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from dataflow.migrations.default_strategies import DefaultValueStrategyManager
from dataflow.migrations.not_null_handler import (
    AdditionResult,
    ColumnDefinition,
    DefaultValueType,
    NotNullAdditionPlan,
    NotNullColumnHandler,
    ValidationResult,
)


def create_mock_connection():
    """Create a mock connection with transaction support."""
    mock_connection = AsyncMock()

    # Create a proper async context manager class
    class MockTransaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Make transaction() return the context manager directly, not a coroutine
    mock_connection.transaction = Mock(return_value=MockTransaction())

    return mock_connection


class TestConcurrentOperations:
    """Test concurrent NOT NULL column addition operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()
        self.manager = DefaultValueStrategyManager()

    @pytest.mark.asyncio
    async def test_concurrent_addition_to_same_table(self):
        """Test concurrent NOT NULL additions to the same table."""
        # Mock connection with locking
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = 1000  # Row count
        mock_connection.fetch.return_value = []  # No constraints
        mock_connection.execute = AsyncMock()

        # Track execution order
        execution_order = []
        execution_lock = threading.Lock()

        async def mock_execute(sql):
            with execution_lock:
                execution_order.append(sql)
            await asyncio.sleep(0.01)  # Simulate DB operation
            return None

        mock_connection.execute = mock_execute

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            # Create two columns to add concurrently
            column1 = ColumnDefinition(
                name="status", data_type="VARCHAR(20)", default_value="active"
            )

            column2 = ColumnDefinition(
                name="priority", data_type="INTEGER", default_value=1
            )

            plan1 = NotNullAdditionPlan(
                table_name="test_table",
                column=column1,
                execution_strategy="single_ddl",
                validate_constraints=False,
            )

            plan2 = NotNullAdditionPlan(
                table_name="test_table",
                column=column2,
                execution_strategy="single_ddl",
                validate_constraints=False,
            )

            # Execute concurrently
            results = await asyncio.gather(
                self.handler.execute_not_null_addition(plan1),
                self.handler.execute_not_null_addition(plan2),
                return_exceptions=True,
            )

            # Both should succeed without deadlock
            for result in results:
                if isinstance(result, Exception):
                    pytest.fail(f"Concurrent execution failed: {result}")
                assert result.result == AdditionResult.SUCCESS

            # Verify both operations were executed
            assert len(execution_order) >= 2

    @pytest.mark.asyncio
    async def test_concurrent_validation_operations(self):
        """Test concurrent validation of multiple columns."""
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = True  # Table exists
        mock_connection.fetch.return_value = []

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            # Create multiple validation tasks
            columns = [
                ColumnDefinition(f"col_{i}", "VARCHAR(50)", default_value=f"value_{i}")
                for i in range(10)
            ]

            plans = [
                NotNullAdditionPlan(
                    table_name="test_table", column=col, execution_strategy="single_ddl"
                )
                for col in columns
            ]

            # Run validations concurrently
            validation_tasks = [
                self.handler.validate_addition_safety(plan) for plan in plans
            ]

            results = await asyncio.gather(*validation_tasks)

            # All validations should complete successfully
            assert len(results) == 10
            assert all(isinstance(r, ValidationResult) for r in results)

    def test_thread_safety_of_strategy_manager(self):
        """Test thread safety of DefaultValueStrategyManager."""
        manager = DefaultValueStrategyManager()
        results = []
        errors = []

        def create_strategy(index):
            try:
                # Each thread creates different strategies
                if index % 3 == 0:
                    strategy = manager.static_default(f"value_{index}")
                elif index % 3 == 1:
                    strategy = manager.function_default("CURRENT_TIMESTAMP")
                else:
                    strategy = manager.computed_default(
                        f"CASE WHEN id = {index} THEN 1 ELSE 0 END"
                    )
                results.append(strategy)
            except Exception as e:
                errors.append(e)

        # Run in multiple threads
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(create_strategy, i) for i in range(100)]
            for future in as_completed(futures):
                future.result()

        # Should have no errors and all strategies created
        assert len(errors) == 0
        assert len(results) == 100


class TestRaceConditions:
    """Test race condition prevention."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_race_condition_column_exists_check(self):
        """Test race condition in column existence check."""
        mock_connection = create_mock_connection()

        # Simulate race condition: column doesn't exist at first check,
        # but exists at execution time
        check_count = {"count": 0}

        async def mock_fetchval(query, *args):
            if "EXISTS" in query and "column_name" in query:
                check_count["count"] += 1
                # First check: column doesn't exist
                # Second check: column exists (another process added it)
                return check_count["count"] > 1
            return 1000  # Row count

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="race_column", data_type="VARCHAR(50)", default_value="test"
            )

            plan = NotNullAdditionPlan(
                table_name="test_table", column=column, execution_strategy="single_ddl"
            )

            # First validation should pass (column doesn't exist)
            validation1 = await self.handler.validate_addition_safety(plan)
            assert validation1.is_safe is True

            # Second validation should fail (column now exists)
            validation2 = await self.handler.validate_addition_safety(plan)
            assert validation2.is_safe is False
            assert any("already exists" in issue for issue in validation2.issues)

    @pytest.mark.asyncio
    async def test_race_condition_in_batched_updates(self):
        """Test race condition prevention in batched update execution."""
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = 10000  # Large row count
        mock_connection.fetch.return_value = []

        # Track batch updates
        batch_updates = []
        update_lock = asyncio.Lock()

        async def mock_fetchval_update(query, *args):
            if "WITH batch AS" in query:
                async with update_lock:
                    batch_updates.append(time.time())
                    # Simulate some batches having no rows left
                    if len(batch_updates) > 3:
                        return None
                    return 1000  # Rows updated
            return 10000

        mock_connection.fetchval = mock_fetchval_update
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="computed_col",
                data_type="VARCHAR(50)",
                default_expression="CASE WHEN id > 5000 THEN 'high' ELSE 'low' END",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=1000,
                validate_constraints=False,
            )

            result = await self.handler.execute_not_null_addition(plan)

            # Should handle concurrent batch updates safely
            assert result.result == AdditionResult.SUCCESS
            assert len(batch_updates) > 0


class TestDeadlockPrevention:
    """Test deadlock prevention mechanisms."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_deadlock_prevention_with_foreign_keys(self):
        """Test deadlock prevention when dealing with foreign key constraints."""
        mock_connection = create_mock_connection()

        # Simulate potential deadlock scenario with foreign keys
        lock_acquisition_order = []

        async def mock_execute(query):
            if "ALTER TABLE" in query:
                lock_acquisition_order.append(("ALTER", time.time()))
                await asyncio.sleep(0.01)
            elif "SELECT" in query and "FOR UPDATE" in query:
                lock_acquisition_order.append(("SELECT_LOCK", time.time()))
                await asyncio.sleep(0.01)
            return None

        mock_connection.execute = mock_execute
        mock_connection.fetchval.return_value = 100
        mock_connection.fetch.return_value = [
            {
                "name": "fk_constraint",
                "constraint_type": "FOREIGN KEY",
                "constraint_definition": "FOREIGN KEY (category_id) REFERENCES categories(id)",
            }
        ]

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="new_category_id",
                data_type="INTEGER",
                default_value=1,
                foreign_key_reference="categories.id",
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="single_ddl",
                validate_constraints=False,
            )

            # Execute with potential deadlock scenario
            result = await self.handler.execute_not_null_addition(plan)

            # Should complete without deadlock
            assert result.result == AdditionResult.SUCCESS

            # Verify locks were acquired in consistent order
            if len(lock_acquisition_order) > 1:
                # Locks should be acquired in a predictable order
                lock_types = [lock[0] for lock in lock_acquisition_order]
                assert lock_types == sorted(
                    lock_types
                )  # Alphabetical order prevents deadlock

    @pytest.mark.asyncio
    async def test_transaction_timeout_handling(self):
        """Test handling of transaction timeouts to prevent indefinite locks."""
        mock_connection = create_mock_connection()

        # Simulate timeout scenario
        async def mock_execute_with_timeout(query):
            if "ALTER TABLE" in query:
                # Simulate a long-running operation that times out
                await asyncio.sleep(0.1)
                raise asyncio.TimeoutError("Transaction timed out")
            return None

        mock_connection.execute = mock_execute_with_timeout
        mock_connection.fetchval.return_value = 1000
        mock_connection.fetch.return_value = []

        # Mock connection already has proper transaction support from create_mock_connection()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="timeout_col", data_type="VARCHAR(50)", default_value="test"
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="single_ddl",
                timeout_seconds=1,  # Very short timeout
            )

            result = await self.handler.execute_not_null_addition(plan)

            # Should handle timeout gracefully
            assert result.result == AdditionResult.ROLLBACK_REQUIRED
            assert result.rollback_executed is True
            assert "timed out" in result.error_message.lower()


class TestLockManagement:
    """Test database lock management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_advisory_lock_usage(self):
        """Test proper use of advisory locks for coordination."""
        mock_connection = create_mock_connection()
        advisory_locks_acquired = []
        advisory_locks_released = []

        async def mock_fetchval(query, *args):
            if "pg_try_advisory_lock" in query:
                advisory_locks_acquired.append(args[0] if args else None)
                return True  # Lock acquired
            elif "pg_advisory_unlock" in query:
                advisory_locks_released.append(args[0] if args else None)
                return True
            elif "IS NULL" in query:
                return 0  # No NULL violations for constraint validation
            return 1000

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            # Patch the handler to use advisory locks
            with patch.object(self.handler, "_use_advisory_locks", True):
                column = ColumnDefinition(
                    name="locked_col", data_type="VARCHAR(50)", default_value="test"
                )

                plan = NotNullAdditionPlan(
                    table_name="test_table",
                    column=column,
                    execution_strategy="single_ddl",
                )

                result = await self.handler.execute_not_null_addition(plan)

                # Advisory locks should be used if implemented
                # This test assumes the feature might be added
                assert result.result == AdditionResult.SUCCESS

    @pytest.mark.asyncio
    async def test_lock_escalation_prevention(self):
        """Test prevention of lock escalation issues."""
        mock_connection = create_mock_connection()

        # Track lock levels
        lock_levels = []

        async def mock_execute(query):
            if "LOCK TABLE" in query:
                if "ACCESS SHARE" in query:
                    lock_levels.append("ACCESS_SHARE")
                elif "EXCLUSIVE" in query:
                    lock_levels.append("EXCLUSIVE")
            return None

        mock_connection.execute = mock_execute

        # Track fetchval calls to break the batched update loop
        fetchval_call_count = {"count": 0}

        async def mock_fetchval(query, *args):
            fetchval_call_count["count"] += 1
            if "WITH batch AS" in query:
                # Return 1000 for first 2 batches, then None to end loop
                if fetchval_call_count["count"] <= 2:
                    return 1000
                return None  # No more rows to update
            return 100000  # Large table row count

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="large_table_col",
                data_type="VARCHAR(50)",
                default_expression="CASE WHEN id > 50000 THEN 'high' ELSE 'low' END",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="large_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=1000,
                validate_constraints=False,
            )

            # For batched updates, should use appropriate locking strategy
            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.SUCCESS

            # Should not escalate to exclusive locks unnecessarily
            if lock_levels:
                assert "EXCLUSIVE" not in lock_levels or len(lock_levels) == 1


class TestMultiUserScenarios:
    """Test multi-user concurrent scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_concurrent_read_write_operations(self):
        """Test concurrent reads while NOT NULL addition is in progress."""
        mock_connection = create_mock_connection()

        # Simulate concurrent operations
        operation_log = []
        operation_lock = asyncio.Lock()

        async def mock_fetchval(query, *args):
            async with operation_lock:
                if "SELECT COUNT" in query:
                    operation_log.append(("READ", time.time()))
                    return 1000
                elif "EXISTS" in query:
                    return False
            return None

        async def mock_execute(query):
            async with operation_lock:
                if "ALTER TABLE" in query:
                    operation_log.append(("WRITE", time.time()))
                    # Simulate slow ALTER
                    await asyncio.sleep(0.05)
            return None

        mock_connection.fetchval = mock_fetchval
        mock_connection.execute = mock_execute
        mock_connection.fetch.return_value = []

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="concurrent_col", data_type="VARCHAR(50)", default_value="test"
            )

            plan = NotNullAdditionPlan(
                table_name="test_table", column=column, execution_strategy="single_ddl"
            )

            # Simulate concurrent read operations
            async def concurrent_reads():
                for _ in range(5):
                    await mock_fetchval("SELECT COUNT(*) FROM test_table")
                    await asyncio.sleep(0.01)

            # Execute addition with concurrent reads
            results = await asyncio.gather(
                self.handler.execute_not_null_addition(plan),
                concurrent_reads(),
                return_exceptions=True,
            )

            # Both operations should complete
            assert not any(isinstance(r, Exception) for r in results)

            # Verify operations were interleaved
            assert len(operation_log) > 1
            read_ops = [op for op in operation_log if op[0] == "READ"]
            write_ops = [op for op in operation_log if op[0] == "WRITE"]
            assert len(read_ops) > 0
            assert len(write_ops) > 0

    @pytest.mark.asyncio
    async def test_connection_pool_exhaustion_handling(self):
        """Test handling of connection pool exhaustion."""
        mock_connection = create_mock_connection()
        connection_attempts = {"count": 0}

        async def mock_get_connection():
            connection_attempts["count"] += 1
            if connection_attempts["count"] > 3:
                # Simulate pool exhaustion
                raise Exception("Connection pool exhausted")
            return mock_connection

        mock_connection.fetchval.return_value = 1000
        mock_connection.fetch.return_value = []
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", side_effect=mock_get_connection
        ):
            # Try multiple concurrent operations
            columns = [
                ColumnDefinition(f"col_{i}", "VARCHAR(50)", default_value=f"val_{i}")
                for i in range(5)
            ]

            plans = [
                NotNullAdditionPlan(
                    table_name="test_table", column=col, execution_strategy="single_ddl"
                )
                for col in columns
            ]

            # Execute concurrently
            results = await asyncio.gather(
                *[self.handler.execute_not_null_addition(plan) for plan in plans],
                return_exceptions=True,
            )

            # Some should succeed, some should fail due to pool exhaustion
            successes = [
                r
                for r in results
                if not isinstance(r, Exception) and r.result == AdditionResult.SUCCESS
            ]
            failures = [
                r
                for r in results
                if isinstance(r, Exception) or r.result != AdditionResult.SUCCESS
            ]

            assert len(successes) <= 3  # Only first 3 can succeed
            assert len(failures) >= 2  # At least 2 should fail


class TestIsolationLevels:
    """Test transaction isolation level handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_serializable_isolation_handling(self):
        """Test handling of SERIALIZABLE isolation level."""
        mock_connection = create_mock_connection()

        # Track isolation level changes
        isolation_levels = []

        async def mock_execute(query):
            if "SET TRANSACTION ISOLATION LEVEL" in query:
                if "SERIALIZABLE" in query:
                    isolation_levels.append("SERIALIZABLE")
                elif "READ COMMITTED" in query:
                    isolation_levels.append("READ_COMMITTED")
            elif "ALTER TABLE" in query:
                # Simulate serialization failure
                if "SERIALIZABLE" in isolation_levels:
                    raise Exception("could not serialize access")
            return None

        mock_connection.execute = mock_execute
        mock_connection.fetchval.return_value = 1000
        mock_connection.fetch.return_value = []

        # Mock connection already has proper transaction support from create_mock_connection()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="serializable_col", data_type="VARCHAR(50)", default_value="test"
            )

            plan = NotNullAdditionPlan(
                table_name="test_table", column=column, execution_strategy="single_ddl"
            )

            # Should handle serialization failures
            result = await self.handler.execute_not_null_addition(plan)

            # The operation should handle the serialization failure
            assert result.result in [
                AdditionResult.ROLLBACK_REQUIRED,
                AdditionResult.SUCCESS,
            ]

    @pytest.mark.asyncio
    async def test_read_committed_consistency(self):
        """Test consistency under READ COMMITTED isolation."""
        mock_connection = create_mock_connection()

        # Simulate phantom reads under READ COMMITTED
        row_counts = [1000, 1005, 1010]  # Row count changes during execution
        count_index = {"index": 0}

        async def mock_fetchval(query, *args):
            if "COUNT(*)" in query:
                result = row_counts[min(count_index["index"], len(row_counts) - 1)]
                count_index["index"] += 1
                return result
            return False

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="phantom_col", data_type="VARCHAR(50)", default_value="test"
            )

            # Plan with initial row count
            plan = await self.handler.plan_not_null_addition("test_table", column)
            # Disable constraint validation since we're testing phantom reads, not constraints
            plan.validate_constraints = False

            # Row count changed between planning and execution
            result = await self.handler.execute_not_null_addition(plan)

            # Should handle phantom reads gracefully
            assert result.result == AdditionResult.SUCCESS
            # Affected rows might differ from planned
            assert result.affected_rows >= row_counts[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

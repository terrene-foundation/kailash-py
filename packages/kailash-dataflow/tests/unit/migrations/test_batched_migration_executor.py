"""
Unit tests for BatchedMigrationExecutor.

Tests DDL operation batching logic and parallel execution safety
without external dependencies.
"""

from types import SimpleNamespace
from typing import List
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from dataflow.migrations.auto_migration_system import (
    Migration,
    MigrationOperation,
    MigrationStatus,
    MigrationType,
)
from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor


class TestBatchedMigrationExecutor:
    """Unit tests for BatchedMigrationExecutor class."""

    @pytest.fixture
    def mock_connection(self):
        """Model asyncpg's synchronous transaction factory and async execute.

        A plain namespace exercises the database path instead of the executor's
        legacy mock-detection branch.
        """
        return SimpleNamespace(
            transaction=Mock(return_value=AsyncMock()),
            execute=AsyncMock(),
        )

    @pytest.fixture
    def executor(self, mock_connection):
        """Create BatchedMigrationExecutor instance."""
        return BatchedMigrationExecutor(mock_connection)

    @pytest.fixture
    def sample_operations(self):
        """Create sample migration operations for testing."""
        return [
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="users",
                description="Create users table",
                sql_up="CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(255));",
                sql_down="DROP TABLE users;",
                metadata={"columns": 2},
            ),
            MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name="posts",
                description="Create posts table",
                sql_up="CREATE TABLE posts (id SERIAL PRIMARY KEY, user_id INTEGER);",
                sql_down="DROP TABLE posts;",
                metadata={"columns": 2},
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_COLUMN,
                table_name="users",
                description="Add email column to users",
                sql_up="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
                sql_down="ALTER TABLE users DROP COLUMN email;",
                metadata={"column_name": "email"},
            ),
            MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="users",
                description="Add index on email",
                sql_up="CREATE INDEX idx_users_email ON users(email);",
                sql_down="DROP INDEX idx_users_email;",
                metadata={"index_name": "idx_users_email"},
            ),
        ]

    def test_batch_ddl_operations_empty_list(self, executor):
        """Test batching with empty operations list."""
        batches = executor.batch_ddl_operations([])
        assert batches == []

    def test_batch_ddl_operations_single_operation(self, executor, sample_operations):
        """Test batching with single operation."""
        single_op = [sample_operations[0]]
        batches = executor.batch_ddl_operations(single_op)

        assert len(batches) == 1
        assert len(batches[0]) == 1
        assert batches[0][0] == sample_operations[0].sql_up

    def test_batch_ddl_operations_creates_can_batch_together(
        self, executor, sample_operations
    ):
        """Test that CREATE TABLE operations can be batched together."""
        create_ops = [sample_operations[0], sample_operations[1]]  # Both CREATE_TABLE
        batches = executor.batch_ddl_operations(create_ops)

        # CREATE operations should be batchable
        assert len(batches) == 1
        assert len(batches[0]) == 2
        assert sample_operations[0].sql_up in batches[0]
        assert sample_operations[1].sql_up in batches[0]

    def test_batch_ddl_operations_table_dependencies(self, executor, sample_operations):
        """Test that operations on same table are properly sequenced."""
        # Operations on same table: CREATE users, then ADD COLUMN to users
        same_table_ops = [sample_operations[0], sample_operations[2]]
        batches = executor.batch_ddl_operations(same_table_ops)

        # Should be in separate batches due to dependency
        assert len(batches) == 2
        assert len(batches[0]) == 1  # CREATE TABLE users first
        assert len(batches[1]) == 1  # ADD COLUMN users second
        assert sample_operations[0].sql_up in batches[0]
        assert sample_operations[2].sql_up in batches[1]

    def test_batch_ddl_operations_mixed_types(self, executor, sample_operations):
        """Test batching with mixed operation types."""
        batches = executor.batch_ddl_operations(sample_operations)

        # Should group compatible operations while respecting dependencies
        assert len(batches) >= 2  # At least CREATE and subsequent operations

        # First batch should contain CREATE operations
        create_sqls = [
            op.sql_up
            for op in sample_operations
            if op.operation_type == MigrationType.CREATE_TABLE
        ]
        assert all(sql in batches[0] for sql in create_sqls)

    def test_can_batch_together_same_type_different_tables(
        self, executor, sample_operations
    ):
        """Test that same operation types on different tables can batch."""
        op1 = sample_operations[0]  # CREATE TABLE users
        op2 = sample_operations[1]  # CREATE TABLE posts

        assert executor._can_batch_together(op1, op2)

    def test_can_batch_together_same_table_dependency(
        self, executor, sample_operations
    ):
        """Test that operations on same table cannot batch if they have dependencies."""
        op1 = sample_operations[0]  # CREATE TABLE users
        op2 = sample_operations[2]  # ADD COLUMN to users

        assert not executor._can_batch_together(op1, op2)

    def test_can_batch_together_incompatible_types(self, executor, sample_operations):
        """Test that incompatible operation types cannot batch."""
        create_op = sample_operations[0]  # CREATE_TABLE

        # Create a DROP operation
        drop_op = MigrationOperation(
            operation_type=MigrationType.DROP_TABLE,
            table_name="old_table",
            description="Drop old table",
            sql_up="DROP TABLE old_table;",
            sql_down="-- Cannot recreate",
            metadata={},
        )

        assert not executor._can_batch_together(create_op, drop_op)

    def test_is_safe_for_parallel_create_operations(self, executor, sample_operations):
        """Test that CREATE operations are safe for parallel execution."""
        create_ops = [sample_operations[0], sample_operations[1]]

        assert executor._is_safe_for_parallel(create_ops)

    def test_is_safe_for_parallel_with_dependencies(self, executor, sample_operations):
        """Test that operations with dependencies are not safe for parallel execution."""
        dependent_ops = [
            sample_operations[0],
            sample_operations[2],
        ]  # CREATE users, ADD COLUMN to users

        assert not executor._is_safe_for_parallel(dependent_ops)

    def test_is_safe_for_parallel_drop_operations(self, executor):
        """Test that DROP operations are not safe for parallel execution."""
        drop_ops = [
            MigrationOperation(
                operation_type=MigrationType.DROP_TABLE,
                table_name="table1",
                description="Drop table1",
                sql_up="DROP TABLE table1;",
                sql_down="-- Cannot recreate",
                metadata={},
            ),
            MigrationOperation(
                operation_type=MigrationType.DROP_TABLE,
                table_name="table2",
                description="Drop table2",
                sql_up="DROP TABLE table2;",
                sql_down="-- Cannot recreate",
                metadata={},
            ),
        ]

        # DROP operations should not be parallel due to potential cascade effects
        assert not executor._is_safe_for_parallel(drop_ops)

    @pytest.mark.asyncio
    async def test_execute_batched_migrations_empty_list(self, executor):
        """Test executing empty batches list."""
        result = await executor.execute_batched_migrations([])
        assert result

    @pytest.mark.asyncio
    async def test_execute_batched_migrations_single_batch(
        self, executor, mock_connection
    ):
        """Execute SQL inside a transaction and exit that transaction."""
        sql = "CREATE TABLE test (id SERIAL PRIMARY KEY);"
        assert await executor.execute_batched_migrations([[sql]]) is True
        mock_connection.execute.assert_awaited_once_with(sql)
        transaction = mock_connection.transaction.return_value
        transaction.__aenter__.assert_awaited_once()
        transaction.__aexit__.assert_awaited_once_with(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_batched_migrations_multiple_batches(
        self, executor, mock_connection
    ):
        """Every statement is awaited in order, in one transaction per batch."""
        batches = [
            [
                "CREATE TABLE users (id SERIAL PRIMARY KEY);",
                "CREATE TABLE posts (id SERIAL PRIMARY KEY);",
            ],
            ["ALTER TABLE users ADD COLUMN email VARCHAR(255);"],
        ]
        assert await executor.execute_batched_migrations(batches) is True
        assert mock_connection.execute.await_args_list == [
            call(sql) for batch in batches for sql in batch
        ]
        transaction = mock_connection.transaction.return_value
        assert transaction.__aenter__.await_count == len(batches)
        assert transaction.__aexit__.await_args_list == [
            call(None, None, None) for _ in batches
        ]

    @pytest.mark.asyncio
    async def test_execute_batch_parallel(self, executor, mock_connection):
        """Exercise the parallel helper, including each statement's transaction."""
        statements = [
            "CREATE TABLE users (id SERIAL PRIMARY KEY);",
            "CREATE TABLE posts (id SERIAL PRIMARY KEY);",
        ]
        assert await executor._execute_batch_parallel(statements) is True
        mock_connection.execute.assert_has_awaits(
            [call(sql) for sql in statements], any_order=True
        )
        assert mock_connection.execute.await_count == len(statements)
        transaction = mock_connection.transaction.return_value
        assert transaction.__aenter__.await_count == len(statements)
        assert transaction.__aexit__.await_count == len(statements)

    @pytest.mark.asyncio
    async def test_execute_batched_migrations_error_handling(
        self, executor, mock_connection
    ):
        """A real execution failure exits the transaction and stops the batch."""
        sql = "CREATE TABLE test (id SERIAL PRIMARY KEY);"
        error = RuntimeError("Test error")
        mock_connection.execute.side_effect = error
        assert await executor.execute_batched_migrations([[sql, "SELECT 1;"]]) is False
        mock_connection.execute.assert_awaited_once_with(sql)
        transaction = mock_connection.transaction.return_value
        transaction.__aenter__.assert_awaited_once()
        transaction.__aexit__.assert_awaited_once()
        exc_type, exc_value, traceback = transaction.__aexit__.await_args.args
        assert exc_type is RuntimeError
        assert exc_value is error
        assert traceback is not None

    def test_get_batch_execution_strategy_sequential(self, executor, sample_operations):
        """Test strategy selection for sequential execution."""
        # Operations with dependencies should use sequential strategy
        dependent_ops = [sample_operations[0], sample_operations[2]]
        strategy = executor._get_batch_execution_strategy(dependent_ops)

        assert strategy == "sequential"

    def test_get_batch_execution_strategy_parallel(self, executor, sample_operations):
        """Test strategy selection for parallel execution."""
        # Independent CREATE operations should use parallel strategy
        # Need at least 3 operations to meet parallel_threshold
        independent_ops = [sample_operations[0], sample_operations[1]]

        # Add a third CREATE operation on different table
        third_create_op = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="orders",  # Different table
            description="Create orders table",
            sql_up="CREATE TABLE orders (id SERIAL PRIMARY KEY);",
            sql_down="DROP TABLE orders;",
            metadata={"columns": 1},
        )
        independent_ops.append(third_create_op)

        strategy = executor._get_batch_execution_strategy(independent_ops)
        assert strategy == "parallel"

    def test_performance_estimation(self, executor, sample_operations):
        """Test performance estimation for batched operations."""
        batches = executor.batch_ddl_operations(sample_operations)
        estimated_time = executor.estimate_execution_time(batches)

        # Should provide reasonable time estimate
        assert isinstance(estimated_time, (int, float))
        assert estimated_time > 0
        assert estimated_time < 60  # Should be reasonable for test operations

    def test_batch_optimization_large_operations_list(self, executor):
        """Test batching optimization with large number of operations."""
        # Create many CREATE TABLE operations that can be batched
        operations = []
        for i in range(50):
            operations.append(
                MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name=f"table_{i}",
                    description=f"Create table_{i}",
                    sql_up=f"CREATE TABLE table_{i} (id SERIAL PRIMARY KEY);",
                    sql_down=f"DROP TABLE table_{i};",
                    metadata={"columns": 1},
                )
            )

        batches = executor.batch_ddl_operations(operations)

        # Should efficiently batch many CREATE operations
        assert len(batches) <= 10  # Should reduce to reasonable number of batches
        total_operations = sum(len(batch) for batch in batches)
        assert total_operations == 50  # All operations should be included

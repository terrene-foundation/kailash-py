"""
Integration tests for AsyncLocalRuntime transaction cleanup.

Tests the PostgreSQL transaction management fix for the critical bug where
sequential workflow executions fail due to "dirty" database connections.

Follows 3-Tier Testing Strategy - Tier 2 (Integration):
- Real PostgreSQL database (NO MOCKING)
- Test component interactions with real services
- Validate data flows between components

Prerequisites:
- PostgreSQL test database running on port 5434
- Run: ./tests/utils/test-env up && ./tests/utils/test-env status
"""

import asyncio

import pytest
from kailash.nodes.data.async_sql import (
    DatabaseConfig,
    DatabaseType,
    FetchMode,
    PostgreSQLAdapter,
)

from tests.utils.docker_config import DATABASE_CONFIG


@pytest.fixture
async def postgres_adapter():
    """Create PostgreSQL adapter for testing."""
    config = DatabaseConfig(
        type=DatabaseType.POSTGRESQL,
        host=DATABASE_CONFIG["host"],
        port=DATABASE_CONFIG["port"],
        database=DATABASE_CONFIG["database"],
        user=DATABASE_CONFIG["user"],
        password=DATABASE_CONFIG["password"],
        max_pool_size=10,
        pool_timeout=30.0,
        command_timeout=10.0,
    )
    adapter = PostgreSQLAdapter(config)
    await adapter.connect()

    # Create test table
    await adapter.execute(
        """
        CREATE TABLE IF NOT EXISTS test_transaction_cleanup (
            id SERIAL PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    yield adapter

    # Cleanup
    await adapter.execute("DROP TABLE IF EXISTS test_transaction_cleanup CASCADE")
    await adapter.disconnect()


class TestAsyncSQLTransactionCleanup:
    """Test suite for async SQL transaction cleanup."""

    @pytest.mark.asyncio
    async def test_auto_mode_cleanup_on_error(self, postgres_adapter):
        """Test that auto mode properly cleans up transactions on error."""
        # Arrange
        test_value = "test_auto_cleanup"

        # Act - Start transaction, insert data, but raise error before commit
        transaction = await postgres_adapter.begin_transaction()

        try:
            await postgres_adapter.execute(
                "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
                params=[test_value],
                transaction=transaction,
            )
            # Simulate error - raise exception before commit
            raise ValueError("Simulated error")
        except ValueError:
            # Let context manager handle rollback
            await postgres_adapter.rollback_transaction(transaction)

        # Assert - Data should NOT be in database
        result = await postgres_adapter.execute(
            "SELECT * FROM test_transaction_cleanup WHERE value = $1",
            params=[test_value],
            fetch_mode=FetchMode.ALL,
        )
        assert len(result) == 0, "Data should be rolled back"

    @pytest.mark.asyncio
    async def test_workflow_completion_releases_connections(self, postgres_adapter):
        """Test that workflow completion releases connections to pool."""
        # Arrange
        initial_pool_size = postgres_adapter._pool.get_size()

        # Act - Start and complete transaction
        transaction = await postgres_adapter.begin_transaction()

        await postgres_adapter.execute(
            "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
            params=["test_release"],
            transaction=transaction,
        )

        await postgres_adapter.commit_transaction(transaction)

        # Assert - Pool size should remain stable
        final_pool_size = postgres_adapter._pool.get_size()
        assert (
            final_pool_size <= initial_pool_size + 1
        ), "Pool should not grow unbounded"

    @pytest.mark.asyncio
    async def test_sequential_workflow_executions(self, postgres_adapter):
        """
        Test sequential workflow executions (original bug scenario).

        This is the critical test that reproduces the original bug:
        - First workflow: Succeeds
        - Second workflow: Fails with "dirty" connection error
        """
        # Arrange
        test_values = ["workflow_1", "workflow_2", "workflow_3"]

        # Act & Assert - Execute multiple sequential workflows
        for i, value in enumerate(test_values, 1):
            transaction = await postgres_adapter.begin_transaction()

            try:
                # Insert data
                await postgres_adapter.execute(
                    "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
                    params=[value],
                    transaction=transaction,
                )

                # Commit transaction
                await postgres_adapter.commit_transaction(transaction)

                # Verify data was inserted
                result = await postgres_adapter.execute(
                    "SELECT * FROM test_transaction_cleanup WHERE value = $1",
                    params=[value],
                    fetch_mode=FetchMode.ALL,
                )
                assert len(result) == 1, f"Workflow {i} should insert data"
                assert result[0]["value"] == value

            except Exception as e:
                # This should NOT happen in the fixed version
                await postgres_adapter.rollback_transaction(transaction)
                pytest.fail(
                    f"Sequential workflow {i} failed (original bug reproduced): {e}"
                )

    @pytest.mark.asyncio
    async def test_connection_pool_does_not_exhaust(self, postgres_adapter):
        """Test connection pool doesn't exhaust after 20+ workflows."""
        # Arrange
        num_workflows = 25
        max_pool_size = postgres_adapter.config.max_pool_size

        # Act - Execute many sequential workflows
        for i in range(num_workflows):
            transaction = await postgres_adapter.begin_transaction()

            await postgres_adapter.execute(
                "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
                params=[f"workflow_{i}"],
                transaction=transaction,
            )

            await postgres_adapter.commit_transaction(transaction)

        # Assert - Pool size should not exceed max_pool_size
        final_pool_size = postgres_adapter._pool.get_size()
        assert (
            final_pool_size <= max_pool_size
        ), f"Pool exhausted: {final_pool_size} > {max_pool_size}"

        # Verify all data was inserted
        result = await postgres_adapter.execute(
            "SELECT COUNT(*) as count FROM test_transaction_cleanup",
            fetch_mode=FetchMode.ONE,
        )
        assert result["count"] == num_workflows

    @pytest.mark.asyncio
    async def test_concurrent_transactions_do_not_interfere(self, postgres_adapter):
        """Test concurrent transactions don't interfere with each other."""

        # Arrange
        async def run_transaction(value: str):
            transaction = await postgres_adapter.begin_transaction()
            try:
                await postgres_adapter.execute(
                    "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
                    params=[value],
                    transaction=transaction,
                )
                await postgres_adapter.commit_transaction(transaction)
            except Exception:
                await postgres_adapter.rollback_transaction(transaction)
                raise

        # Act - Run 5 concurrent transactions
        tasks = [run_transaction(f"concurrent_{i}") for i in range(5)]
        await asyncio.gather(*tasks)

        # Assert - All 5 inserts should succeed
        result = await postgres_adapter.execute(
            "SELECT COUNT(*) as count FROM test_transaction_cleanup WHERE value LIKE 'concurrent_%'",
            fetch_mode=FetchMode.ONE,
        )
        assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_rollback_releases_connection_cleanly(self, postgres_adapter):
        """Test that rollback releases connection without leaking transaction state."""
        # Arrange
        initial_pool_size = postgres_adapter._pool.get_size()

        # Act - Start transaction, insert, rollback
        transaction = await postgres_adapter.begin_transaction()

        await postgres_adapter.execute(
            "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
            params=["rollback_test"],
            transaction=transaction,
        )

        await postgres_adapter.rollback_transaction(transaction)

        # Assert - Data should not be in database
        result = await postgres_adapter.execute(
            "SELECT * FROM test_transaction_cleanup WHERE value = 'rollback_test'",
            fetch_mode=FetchMode.ALL,
        )
        assert len(result) == 0

        # Assert - Pool size should be stable
        final_pool_size = postgres_adapter._pool.get_size()
        assert final_pool_size <= initial_pool_size + 1

    @pytest.mark.asyncio
    async def test_nested_transactions_not_supported_gracefully(self, postgres_adapter):
        """Test that nested transactions are handled gracefully."""
        # Arrange
        transaction1 = await postgres_adapter.begin_transaction()

        # Act - Try to start nested transaction (not supported in asyncpg)
        transaction2 = await postgres_adapter.begin_transaction()

        # Cleanup
        try:
            await postgres_adapter.rollback_transaction(transaction1)
        except Exception:
            pass  # May already be rolled back

        try:
            await postgres_adapter.rollback_transaction(transaction2)
        except Exception:
            pass  # May already be rolled back

    @pytest.mark.asyncio
    async def test_transaction_context_manager_pattern(self, postgres_adapter):
        """Test using transaction context manager for automatic cleanup."""
        # This test verifies the new PostgreSQLTransactionContext pattern

        # Arrange
        from kailash.nodes.data.async_sql import PostgreSQLTransactionContext

        # Act - Use context manager
        async with PostgreSQLTransactionContext(
            postgres_adapter._pool
        ) as transaction_ctx:
            await postgres_adapter.execute(
                "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
                params=["context_test"],
                transaction=transaction_ctx,
            )
            await transaction_ctx.commit()

        # Assert - Data should be in database
        result = await postgres_adapter.execute(
            "SELECT * FROM test_transaction_cleanup WHERE value = 'context_test'",
            fetch_mode=FetchMode.ALL,
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_transaction_context_auto_rollback_on_error(self, postgres_adapter):
        """Test context manager auto-rollback on exception."""
        # Arrange
        from kailash.nodes.data.async_sql import PostgreSQLTransactionContext

        # Act & Assert
        with pytest.raises(ValueError):
            async with PostgreSQLTransactionContext(
                postgres_adapter._pool
            ) as transaction_ctx:
                await postgres_adapter.execute(
                    "INSERT INTO test_transaction_cleanup (value) VALUES ($1)",
                    params=["auto_rollback_test"],
                    transaction=transaction_ctx,
                )
                raise ValueError("Simulated error")

        # Assert - Data should NOT be in database (auto-rolled back)
        result = await postgres_adapter.execute(
            "SELECT * FROM test_transaction_cleanup WHERE value = 'auto_rollback_test'",
            fetch_mode=FetchMode.ALL,
        )
        assert len(result) == 0

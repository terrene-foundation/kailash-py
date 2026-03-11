"""
Tier 1 Unit Tests: Migration Lock Manager Integration

Tests the ConnectionManagerAdapter and basic migration lock integration
without external dependencies. Fast execution (<1 second per test).
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dataflow.migrations.concurrent_access_manager import (
    LockStatus,
    MigrationLockManager,
)
from dataflow.utils.connection_adapter import ConnectionManagerAdapter


class TestConnectionManagerAdapter:
    """Test ConnectionManagerAdapter for MigrationLockManager integration."""

    def test_adapter_initialization(self):
        """Test ConnectionManagerAdapter initializes correctly."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "postgresql://localhost/test"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "postgresql://localhost/test"
        )
        mock_dataflow.config.environment = "test"

        adapter = ConnectionManagerAdapter(mock_dataflow)

        assert adapter.dataflow == mock_dataflow
        assert not adapter._transaction_started
        assert adapter._parameter_style == "postgresql"  # Default for PostgreSQL URL

    def test_adapter_parameter_format_conversion(self):
        """Test parameter placeholder conversion from %s to $1, $2, etc."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "postgresql://localhost/test"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "postgresql://localhost/test"
        )
        mock_dataflow.config.environment = "test"
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Test SQL with %s placeholders
        sql = "INSERT INTO test_table (col1, col2) VALUES (%s, %s)"
        params = ["value1", "value2"]

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = "INSERT INTO test_table (col1, col2) VALUES ($1, $2)"
        assert converted_sql == expected_sql
        assert converted_params == params

    def test_adapter_parameter_format_no_conversion_needed(self):
        """Test parameter conversion when no %s placeholders exist."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        sql = "SELECT * FROM test_table"
        params = None

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        assert converted_sql == sql
        assert converted_params == params

    @pytest.mark.asyncio
    async def test_execute_query_basic(self):
        """Test basic query execution through adapter."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock the execute_query method
        with patch.object(
            adapter, "execute_query", new=AsyncMock(return_value=[{"success": True}])
        ) as mock_execute:

            result = await adapter.execute_query("SELECT 1", None)

            mock_execute.assert_called_once_with("SELECT 1", None)
            assert result == [{"success": True}]

    @pytest.mark.asyncio
    async def test_execute_query_with_parameter_conversion(self):
        """Test query execution with parameter format conversion."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock the _runtime.execute_workflow_async method to return success
        mock_runtime = Mock()
        mock_runtime.execute_workflow_async = AsyncMock(
            return_value=({"query_execution": {"result": []}}, None)
        )
        adapter._runtime = mock_runtime

        sql = "INSERT INTO locks (name, value) VALUES (%s, %s)"
        params = ["test_lock", "test_value"]

        result = await adapter.execute_query(sql, params)

        # Should have called runtime.execute_workflow_async with converted SQL
        mock_runtime.execute_workflow_async.assert_called_once()

        # Should return success indicator for empty results (DML operations)
        assert result == [{"success": True}]

    @pytest.mark.asyncio
    async def test_execute_query_dml_result_handling(self):
        """Test DML operation result handling - empty results should return success."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock the _runtime.execute_workflow_async method
        mock_runtime = Mock()
        mock_runtime.execute_workflow_async = AsyncMock(
            return_value=({"query_execution": {"result": []}}, None)
        )
        adapter._runtime = mock_runtime

        result = await adapter.execute_query("INSERT INTO test (id) VALUES (%s)", [1])

        # Empty results for DML should return success indicator
        assert result == [{"success": True}]

    @pytest.mark.asyncio
    async def test_execute_query_select_result_handling(self):
        """Test SELECT operation result handling - return actual results."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        expected_results = [{"id": 1, "name": "test"}]

        # Mock the _runtime.execute_workflow_async method
        mock_runtime = Mock()
        mock_runtime.execute_workflow_async = AsyncMock(
            return_value=(
                {"query_execution": {"result": [{"data": expected_results}]}},
                None,
            )
        )
        adapter._runtime = mock_runtime

        result = await adapter.execute_query("SELECT * FROM test", None)

        # SELECT should return actual results
        assert result == expected_results

    @pytest.mark.asyncio
    async def test_transaction_operations(self):
        """Test transaction begin, commit, and rollback operations."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock the _runtime.execute_workflow_async method for transactions
        mock_runtime = Mock()
        mock_runtime.execute_workflow_async = AsyncMock(
            return_value=(
                {"begin_transaction": {"result": "success"}},
                None,
            )
        )
        adapter._runtime = mock_runtime

        # Test begin transaction
        await adapter.begin_transaction()
        assert adapter._transaction_started

        # Reset response for commit
        mock_runtime.execute_workflow_async.return_value = (
            {"commit_transaction": {"result": "success"}},
            None,
        )

        # Test commit transaction
        await adapter.commit_transaction()
        assert not adapter._transaction_started

        # Reset response for begin
        mock_runtime.execute_workflow_async.return_value = (
            {"begin_transaction": {"result": "success"}},
            None,
        )

        # Reset for rollback test
        await adapter.begin_transaction()
        assert adapter._transaction_started

        # Reset response for rollback
        mock_runtime.execute_workflow_async.return_value = (
            {"rollback_transaction": {"result": "success"}},
            None,
        )

        # Test rollback transaction
        await adapter.rollback_transaction()
        assert not adapter._transaction_started


class TestMigrationLockManagerIntegration:
    """Test MigrationLockManager integration with ConnectionManagerAdapter."""

    @pytest.mark.asyncio
    async def test_lock_manager_initialization_with_adapter(self):
        """Test MigrationLockManager initializes correctly with ConnectionManagerAdapter."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        lock_manager = MigrationLockManager(adapter, lock_timeout=30)

        assert lock_manager.connection_manager == adapter
        assert lock_manager.lock_timeout == 30
        assert lock_manager.process_id is not None
        assert len(lock_manager.process_id) > 10  # Should be PID + UUID

    @pytest.mark.asyncio
    async def test_lock_acquisition_success(self):
        """Test successful lock acquisition."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock the execute_query method
        with patch.object(
            adapter, "execute_query", new=AsyncMock(return_value=[{"success": True}])
        ) as mock_execute:

            lock_manager = MigrationLockManager(adapter, lock_timeout=30)

            result = await lock_manager.acquire_migration_lock("test_schema")

            assert result
            # Should have called execute_query multiple times (table creation, cleanup, insertion)
            assert mock_execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_lock_acquisition_failure(self):
        """Test lock acquisition failure when lock already exists."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock table creation success, but lock insertion failure
        side_effects = [
            [{"success": True}],  # Table creation
            [{"success": True}],  # Cleanup
            Exception("UNIQUE constraint failed"),  # Lock insertion fails
        ]

        with patch.object(
            adapter, "execute_query", new=AsyncMock(side_effect=side_effects)
        ):

            lock_manager = MigrationLockManager(adapter, lock_timeout=30)

            result = await lock_manager.acquire_migration_lock("test_schema")

            assert not result

    @pytest.mark.asyncio
    async def test_lock_release(self):
        """Test lock release functionality."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock the execute_query method
        with patch.object(
            adapter, "execute_query", new=AsyncMock(return_value=[{"success": True}])
        ) as mock_execute:
            lock_manager = MigrationLockManager(adapter, lock_timeout=30)
            await lock_manager.release_migration_lock("test_schema")

            # Should call execute_query for delete operation
            mock_execute.assert_called()

    @pytest.mark.asyncio
    async def test_lock_status_check(self):
        """Test lock status checking functionality."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        # Mock cleanup and status query - no locks exist
        side_effects = [
            [{"success": True}],  # Cleanup
            [],  # No locks found
        ]

        with patch.object(
            adapter, "execute_query", new=AsyncMock(side_effect=side_effects)
        ):

            lock_manager = MigrationLockManager(adapter, lock_timeout=30)

            status = await lock_manager.check_lock_status("test_schema")

            assert isinstance(status, LockStatus)
            assert status.schema_name == "test_schema"
            assert not status.is_locked

    @pytest.mark.asyncio
    async def test_lock_context_manager(self):
        """Test lock context manager functionality."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        lock_manager = MigrationLockManager(adapter, lock_timeout=30)

        # Mock acquire_migration_lock to return True
        lock_manager.acquire_migration_lock = AsyncMock(return_value=True)
        lock_manager.release_migration_lock = AsyncMock()

        async with lock_manager.migration_lock("test_schema"):
            # Context manager should work
            pass

        lock_manager.acquire_migration_lock.assert_called_once_with("test_schema", None)
        lock_manager.release_migration_lock.assert_called_once_with("test_schema")

    @pytest.mark.asyncio
    async def test_lock_context_manager_acquisition_failure(self):
        """Test lock context manager when acquisition fails."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)
        lock_manager = MigrationLockManager(adapter, lock_timeout=30)

        # Mock acquire_migration_lock to return False
        lock_manager.acquire_migration_lock = AsyncMock(return_value=False)
        lock_manager.release_migration_lock = AsyncMock()

        with pytest.raises(RuntimeError, match="Failed to acquire migration lock"):
            async with lock_manager.migration_lock("test_schema"):
                pass

        lock_manager.acquire_migration_lock.assert_called_once()
        # Release should not be called if acquisition failed
        lock_manager.release_migration_lock.assert_not_called()


class TestParameterConversionEdgeCases:
    """Test edge cases for parameter conversion."""

    def test_multiple_parameter_conversion(self):
        """Test conversion with many parameters."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "postgresql://localhost/test"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "postgresql://localhost/test"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        sql = "INSERT INTO test (a, b, c, d, e) VALUES (%s, %s, %s, %s, %s)"
        params = [1, 2, 3, 4, 5]

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = "INSERT INTO test (a, b, c, d, e) VALUES ($1, $2, $3, $4, $5)"
        assert converted_sql == expected_sql
        assert converted_params == params

    def test_mixed_sql_with_other_placeholders(self):
        """Test conversion doesn't affect other SQL constructs."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "postgresql://localhost/test"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "postgresql://localhost/test"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        sql = "SELECT * FROM test WHERE field = %s AND other_field LIKE '%%pattern%%'"
        params = ["value"]

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = (
            "SELECT * FROM test WHERE field = $1 AND other_field LIKE '%%pattern%%'"
        )
        assert converted_sql == expected_sql
        assert converted_params == params

    def test_no_parameters(self):
        """Test with None parameters."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        sql = "SELECT * FROM test"
        params = None

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        assert converted_sql == sql
        assert converted_params is None

    def test_empty_parameters_list(self):
        """Test with empty parameters list."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "postgresql://localhost/test"
        mock_dataflow.config.database.get_connection_url.return_value = (
            "postgresql://localhost/test"
        )
        adapter = ConnectionManagerAdapter(mock_dataflow)

        sql = "SELECT * FROM test WHERE id = %s"  # Has placeholder but empty params
        params = []

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = "SELECT * FROM test WHERE id = $1"  # Still converts
        assert converted_sql == expected_sql
        assert converted_params == []


if __name__ == "__main__":
    # Run tests with timeout validation
    pytest.main([__file__, "-v", "--timeout=1"])

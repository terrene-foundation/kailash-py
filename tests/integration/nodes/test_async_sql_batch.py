"""Unit tests for AsyncSQLDatabaseNode batch operations."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestAsyncSQLBatchOperations:
    """Test batch operations functionality."""

    @pytest.mark.asyncio
    async def test_execute_many_basic(self):
        """Test basic execute_many functionality."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="none",  # No transaction for basic test
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute_many = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True

        # Test data
        params_list = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]

        result = await node.execute_many_async(
            query="INSERT INTO users (name, age) VALUES (:name, :age)",
            params_list=params_list,
        )

        # Verify adapter was called (without transaction parameter in none mode)
        mock_adapter.execute_many.assert_called_once_with(
            "INSERT INTO users (name, age) VALUES (:name, :age)", params_list
        )

        # Verify result format
        assert "result" in result
        assert result["result"]["affected_rows"] == len(params_list)

    @pytest.mark.asyncio
    async def test_execute_many_with_retry(self):
        """Test execute_many with retry logic."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=3,
            retry_delay=0.1,
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        call_count = 0

        async def mock_execute_many(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("connection reset")
            # Success on third attempt

        mock_adapter.execute_many = mock_execute_many
        node._adapter = mock_adapter
        node._connected = True

        params_list = [{"value": 1}, {"value": 2}]

        result = await node.execute_many_async(
            query="INSERT INTO test (value) VALUES (:value)", params_list=params_list
        )

        # Should succeed after retries
        assert call_count == 3
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_many_with_auto_transaction(self):
        """Test execute_many with auto transaction mode."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute_many = AsyncMock()
        mock_transaction = AsyncMock()
        mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
        mock_adapter.commit_transaction = AsyncMock()
        mock_adapter.rollback_transaction = AsyncMock()

        node._adapter = mock_adapter
        node._connected = True

        params_list = [{"id": 1}, {"id": 2}]

        result = await node.execute_many_async(
            query="UPDATE users SET active = true WHERE id = :id",
            params_list=params_list,
        )

        # Verify transaction was used
        mock_adapter.begin_transaction.assert_called_once()
        mock_adapter.execute_many.assert_called_once_with(
            "UPDATE users SET active = true WHERE id = :id",
            params_list,
            mock_transaction,
        )
        mock_adapter.commit_transaction.assert_called_once_with(mock_transaction)
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_many_transaction_rollback(self):
        """Test execute_many rollback on failure in auto mode."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_transaction = AsyncMock()
        mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
        mock_adapter.execute_many = AsyncMock(
            side_effect=Exception("constraint violation")
        )
        mock_adapter.rollback_transaction = AsyncMock()

        node._adapter = mock_adapter
        node._connected = True

        params_list = [{"id": 1}]

        with pytest.raises(NodeExecutionError, match="constraint violation"):
            await node.execute_many_async(
                query="INSERT INTO users (id) VALUES (:id)", params_list=params_list
            )

        # Verify rollback was called
        mock_adapter.begin_transaction.assert_called_once()
        mock_adapter.rollback_transaction.assert_called_once_with(mock_transaction)

    @pytest.mark.asyncio
    async def test_execute_many_manual_transaction(self):
        """Test execute_many within manual transaction."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute_many = AsyncMock()
        mock_transaction = AsyncMock()
        mock_adapter.begin_transaction = AsyncMock(return_value=mock_transaction)
        mock_adapter.commit_transaction = AsyncMock()

        node._adapter = mock_adapter
        node._connected = True

        # Begin transaction
        await node.begin_transaction()

        # Execute batch operation
        params_list = [{"name": "Test1"}, {"name": "Test2"}]
        result = await node.execute_many_async(
            query="INSERT INTO test (name) VALUES (:name)", params_list=params_list
        )

        # Commit transaction
        await node.commit()

        # Verify transaction was reused
        mock_adapter.begin_transaction.assert_called_once()
        mock_adapter.execute_many.assert_called_once_with(
            "INSERT INTO test (name) VALUES (:name)", params_list, mock_transaction
        )
        mock_adapter.commit_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_many_none_transaction_mode(self):
        """Test execute_many with transaction_mode='none'."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="none",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute_many = AsyncMock()

        node._adapter = mock_adapter
        node._connected = True

        params_list = [{"id": 1}, {"id": 2}]

        result = await node.execute_many_async(
            query="DELETE FROM old_data WHERE id = :id", params_list=params_list
        )

        # Verify no transaction was used
        mock_adapter.execute_many.assert_called_once_with(
            "DELETE FROM old_data WHERE id = :id", params_list
        )
        assert "result" in result

    @pytest.mark.asyncio
    async def test_execute_many_empty_params(self):
        """Test execute_many with empty params list."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True

        # Empty params should be handled gracefully
        result = await node.execute_many_async(
            query="INSERT INTO test DEFAULT VALUES", params_list=[]
        )

        # Should not call adapter with empty list
        mock_adapter.execute_many.assert_not_called()
        assert "result" in result
        assert result["result"]["affected_rows"] == 0

    @pytest.mark.asyncio
    async def test_execute_many_validation(self):
        """Test execute_many query validation."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            validate_queries=True,
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True

        # Try dangerous query
        with pytest.raises(NodeExecutionError, match="potentially dangerous"):
            await node.execute_many_async(
                query="INSERT INTO users VALUES (:name); DROP TABLE users",
                params_list=[{"name": "test"}],
            )

    @pytest.mark.asyncio
    async def test_execute_many_parameter_styles(self):
        """Test execute_many with different parameter styles."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute_many = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True

        # Dict parameters
        dict_params = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

        await node.execute_many_async(
            query="INSERT INTO users (name, age) VALUES (:name, :age)",
            params_list=dict_params,
        )

        # Tuple parameters
        tuple_params = [
            ("Charlie", 35),
            ("David", 40),
        ]

        await node.execute_many_async(
            query="INSERT INTO users (name, age) VALUES ($1, $2)",
            params_list=tuple_params,
        )

        assert mock_adapter.execute_many.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_many_large_batch(self):
        """Test execute_many with large batch of parameters."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute_many = AsyncMock()
        node._adapter = mock_adapter
        node._connected = True

        # Large batch
        large_params = [{"id": i, "value": f"test_{i}"} for i in range(1000)]

        result = await node.execute_many_async(
            query="INSERT INTO large_table (id, value) VALUES (:id, :value)",
            params_list=large_params,
        )

        mock_adapter.execute_many.assert_called_once()
        assert result["result"]["affected_rows"] == 1000

    @pytest.mark.asyncio
    async def test_execute_many_concurrent_calls(self):
        """Test concurrent execute_many calls."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        call_count = 0

        async def mock_execute_many(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate some work

        mock_adapter.execute_many = mock_execute_many
        node._adapter = mock_adapter
        node._connected = True

        # Run multiple concurrent batch operations
        tasks = []
        for i in range(5):
            params = [{"batch": i, "item": j} for j in range(10)]
            task = node.execute_many_async(
                query="INSERT INTO concurrent_test VALUES (:batch, :item)",
                params_list=params,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all("result" in r for r in results)
        assert call_count == 5

    @pytest.mark.asyncio
    async def test_execute_many_adapter_specific(self):
        """Test execute_many calls correct adapter method."""
        # Test PostgreSQL
        pg_node = AsyncSQLDatabaseNode(
            name="pg_test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        with patch("kailash.nodes.data.async_sql.PostgreSQLAdapter") as mock_pg:
            mock_instance = AsyncMock()
            mock_instance.connect = AsyncMock()
            mock_instance.execute_many = AsyncMock()
            mock_pg.return_value = mock_instance

            await pg_node._get_adapter()
            await pg_node.execute_many_async(
                query="INSERT INTO test VALUES ($1)", params_list=[(1,), (2,)]
            )

            mock_instance.execute_many.assert_called_once()

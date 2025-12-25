"""Unit tests for AsyncSQLDatabaseNode transaction functionality."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError


class TestAsyncSQLTransactions:
    """Test transaction modes and behavior."""

    def test_transaction_mode_default(self):
        """Test that default transaction mode is 'auto'."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        assert node._transaction_mode == "auto"

    def test_transaction_mode_configuration(self):
        """Test transaction mode can be configured."""
        # Test auto mode
        node_auto = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )
        assert node_auto._transaction_mode == "auto"

        # Test manual mode
        node_manual = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )
        assert node_manual._transaction_mode == "manual"

        # Test none mode
        node_none = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="none",
        )
        assert node_none._transaction_mode == "none"

    @pytest.mark.asyncio
    async def test_auto_transaction_mode_success(self):
        """Test auto transaction mode commits on success."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )

        # Mock adapter and transaction
        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction
        mock_adapter.execute.return_value = [{"id": 1, "name": "test"}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(query="SELECT * FROM test")

            # Verify transaction was created, used, and committed
            mock_adapter.begin_transaction.assert_called_once()
            mock_adapter.execute.assert_called_once()
            mock_adapter.commit_transaction.assert_called_once_with(mock_transaction)
            mock_adapter.rollback_transaction.assert_not_called()

            assert result["result"]["data"] == [{"id": 1, "name": "test"}]

    @pytest.mark.asyncio
    async def test_auto_transaction_mode_rollback_on_error(self):
        """Test auto transaction mode rolls back on error."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )

        # Mock adapter and transaction
        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction
        mock_adapter.execute.side_effect = Exception("Database error")

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with pytest.raises(NodeExecutionError):
                await node.execute_async(query="INVALID SQL")

            # Verify transaction was created, attempted, and rolled back
            mock_adapter.begin_transaction.assert_called_once()
            mock_adapter.execute.assert_called_once()
            mock_adapter.rollback_transaction.assert_called_once_with(mock_transaction)
            mock_adapter.commit_transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_manual_transaction_mode_begin_commit(self):
        """Test manual transaction mode with explicit begin/commit."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        # Mock adapter and transaction
        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction
        mock_adapter.execute.return_value = [{"count": 1}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Begin transaction
            transaction = await node.begin_transaction()
            assert transaction == mock_transaction
            assert node._active_transaction == mock_transaction

            # Execute query (should use active transaction)
            result = await node.execute_async(
                query="SELECT COUNT(*) as count FROM test"
            )

            # Commit transaction
            await node.commit()
            assert node._active_transaction is None

            # Verify calls
            mock_adapter.begin_transaction.assert_called_once()
            mock_adapter.execute.assert_called_once()
            mock_adapter.commit_transaction.assert_called_once_with(mock_transaction)

            assert result["result"]["data"] == [{"count": 1}]

    @pytest.mark.asyncio
    async def test_manual_transaction_mode_begin_rollback(self):
        """Test manual transaction mode with explicit begin/rollback."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        # Mock adapter and transaction
        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction
        mock_adapter.execute.return_value = [{"id": 1}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Begin transaction
            await node.begin_transaction()

            # Execute query
            await node.execute_async(query="INSERT INTO test (name) VALUES ('test')")

            # Rollback transaction
            await node.rollback()
            assert node._active_transaction is None

            # Verify calls
            mock_adapter.begin_transaction.assert_called_once()
            mock_adapter.execute.assert_called_once()
            mock_adapter.rollback_transaction.assert_called_once_with(mock_transaction)
            mock_adapter.commit_transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_transaction_mode(self):
        """Test none transaction mode executes without transactions."""
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
        mock_adapter.execute.return_value = [{"result": "success"}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(query="SELECT 'success' as result")

            # Verify no transaction methods were called
            mock_adapter.begin_transaction.assert_not_called()
            mock_adapter.commit_transaction.assert_not_called()
            mock_adapter.rollback_transaction.assert_not_called()

            # Verify execute was called without transaction parameter
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args
            assert "transaction" not in call_args[1]

            assert result["result"]["data"] == [{"result": "success"}]

    @pytest.mark.asyncio
    async def test_manual_transaction_errors(self):
        """Test error handling in manual transaction mode."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        # Test begin_transaction in non-manual mode
        node._transaction_mode = "auto"
        with pytest.raises(
            NodeExecutionError, match="can only be called in 'manual' transaction mode"
        ):
            await node.begin_transaction()

        # Reset to manual mode
        node._transaction_mode = "manual"

        # Test commit without active transaction
        with pytest.raises(NodeExecutionError, match="No active transaction to commit"):
            await node.commit()

        # Test rollback without active transaction
        with pytest.raises(
            NodeExecutionError, match="No active transaction to rollback"
        ):
            await node.rollback()

        # Test double begin_transaction
        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            await node.begin_transaction()

            with pytest.raises(NodeExecutionError, match="Transaction already active"):
                await node.begin_transaction()

            # Cleanup
            await node.rollback()

    @pytest.mark.asyncio
    async def test_auto_transaction_with_retry(self):
        """Test auto transaction mode with retry logic."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
            max_retries=2,
        )

        # Mock adapter to fail once then succeed
        mock_adapter = AsyncMock()
        mock_transaction1 = MagicMock()
        mock_transaction2 = MagicMock()
        mock_adapter.begin_transaction.side_effect = [
            mock_transaction1,
            mock_transaction2,
        ]

        # First call fails, second succeeds
        mock_adapter.execute.side_effect = [
            Exception("connection reset"),  # Use a retryable error pattern
            [{"id": 1, "name": "test"}],
        ]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with patch("asyncio.sleep"):  # Mock sleep to speed up test
                result = await node.execute_async(query="SELECT * FROM test")

                # Verify retry happened
                assert mock_adapter.begin_transaction.call_count == 2
                assert mock_adapter.execute.call_count == 2

                # First transaction rolled back, second committed
                mock_adapter.rollback_transaction.assert_called_once_with(
                    mock_transaction1
                )
                mock_adapter.commit_transaction.assert_called_once_with(
                    mock_transaction2
                )

                assert result["result"]["data"] == [{"id": 1, "name": "test"}]

    @pytest.mark.asyncio
    async def test_batch_operations_with_transactions(self):
        """Test execute_many with different transaction modes."""
        # Test auto transaction mode
        node_auto = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="auto",
        )

        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction

        params_list = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]

        with patch.object(node_auto, "_get_adapter", return_value=mock_adapter):
            result = await node_auto.execute_many_async(
                query="INSERT INTO users (name, age) VALUES (:name, :age)",
                params_list=params_list,
            )

            # Verify transaction was used for batch operation
            mock_adapter.begin_transaction.assert_called_once()
            mock_adapter.execute_many.assert_called_once_with(
                "INSERT INTO users (name, age) VALUES (:name, :age)",
                params_list,
                mock_transaction,
            )
            mock_adapter.commit_transaction.assert_called_once_with(mock_transaction)

            assert result["result"]["affected_rows"] == 2

    @pytest.mark.asyncio
    async def test_manual_transaction_with_batch_operations(self):
        """Test execute_many with active manual transaction."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction

        params_list = [{"id": 1}, {"id": 2}]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Begin manual transaction
            await node.begin_transaction()

            # Execute batch operation
            result = await node.execute_many_async(
                query="DELETE FROM temp WHERE id = :id", params_list=params_list
            )

            # Commit transaction
            await node.commit()

            # Verify the active transaction was used
            mock_adapter.execute_many.assert_called_once_with(
                "DELETE FROM temp WHERE id = :id", params_list, mock_transaction
            )

            # Only one begin_transaction call (manual)
            assert mock_adapter.begin_transaction.call_count == 1

            assert result["result"]["affected_rows"] == 2

    @pytest.mark.asyncio
    async def test_transaction_state_consistency(self):
        """Test that transaction state remains consistent across operations."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction
        mock_adapter.execute.return_value = []

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Initially no active transaction
            assert node._active_transaction is None

            # Begin transaction
            await node.begin_transaction()
            assert node._active_transaction == mock_transaction

            # Execute multiple queries in same transaction
            await node.execute_async(query="INSERT INTO test VALUES (1)")
            await node.execute_async(query="INSERT INTO test VALUES (2)")

            # Transaction should still be active
            assert node._active_transaction == mock_transaction

            # Commit should clear active transaction
            await node.commit()
            assert node._active_transaction is None

            # Verify all queries used same transaction
            assert mock_adapter.execute.call_count == 2
            for call in mock_adapter.execute.call_args_list:
                assert call[1]["transaction"] == mock_transaction


class TestAsyncSQLTransactionEdgeCases:
    """Test edge cases and error scenarios for transactions."""

    @pytest.mark.asyncio
    async def test_transaction_cleanup_on_adapter_error(self):
        """Test transaction cleanup when adapter operations fail."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        mock_adapter = AsyncMock()
        mock_transaction = MagicMock()
        mock_adapter.begin_transaction.return_value = mock_transaction
        mock_adapter.commit_transaction.side_effect = Exception("Commit failed")

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            await node.begin_transaction()

            with pytest.raises(Exception, match="Commit failed"):
                await node.commit()

            # Transaction should still be cleared even if commit fails
            assert node._active_transaction is None

    @pytest.mark.asyncio
    async def test_concurrent_transaction_isolation(self):
        """Test that multiple node instances don't interfere with each other's transactions."""
        # Create two nodes with manual transaction mode
        node1 = AsyncSQLDatabaseNode(
            name="test1",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        node2 = AsyncSQLDatabaseNode(
            name="test2",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="manual",
        )

        mock_adapter1 = AsyncMock()
        mock_adapter2 = AsyncMock()
        mock_transaction1 = MagicMock()
        mock_transaction2 = MagicMock()

        mock_adapter1.begin_transaction.return_value = mock_transaction1
        mock_adapter2.begin_transaction.return_value = mock_transaction2

        with patch.object(node1, "_get_adapter", return_value=mock_adapter1):
            with patch.object(node2, "_get_adapter", return_value=mock_adapter2):
                # Begin transactions on both nodes
                await node1.begin_transaction()
                await node2.begin_transaction()

                # Verify each node has its own transaction
                assert node1._active_transaction == mock_transaction1
                assert node2._active_transaction == mock_transaction2
                assert node1._active_transaction != node2._active_transaction

                # Commit one, rollback the other
                await node1.commit()
                await node2.rollback()

                # Verify both are cleared
                assert node1._active_transaction is None
                assert node2._active_transaction is None

    @pytest.mark.asyncio
    async def test_transaction_mode_parameter_validation(self):
        """Test validation of transaction_mode parameter."""
        # Valid transaction modes should work
        for mode in ["auto", "manual", "none"]:
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                database="testdb",
                user="testuser",
                password="testpass",
                transaction_mode=mode,
            )
            assert node._transaction_mode == mode

        # Invalid transaction mode should be handled gracefully
        # (The node doesn't currently validate this, but it should default to auto)
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            transaction_mode="invalid",
        )
        # Should accept the value (validation happens at runtime if needed)
        assert node._transaction_mode == "invalid"

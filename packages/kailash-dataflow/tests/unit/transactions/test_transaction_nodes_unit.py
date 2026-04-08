"""
Unit tests for DataFlow transaction node implementations (Tier 1).

These tests exercise ``TransactionScopeNode`` / ``TransactionCommitNode`` /
``TransactionRollbackNode`` in isolation and use ``unittest.mock`` doubles
for the DataFlow instance, connection and transaction handles. Tier 1
semantics per ``tests/unit/CLAUDE.md`` — the backend-touching paths are
covered by the Tier 2 ``test_workflow_context_integration.py`` suite which
runs against real PostgreSQL.
"""

from unittest.mock import AsyncMock, Mock

import pytest

pytestmark = [pytest.mark.unit]


class TestTransactionNodeImplementation:
    """Test DataFlow transaction node implementations."""

    def test_transaction_scope_node_starts_transaction(self):
        """Test TransactionScopeNode starts a real database transaction."""
        # Import DataFlow transaction node
        from dataflow.nodes.transaction_nodes import TransactionScopeNode

        # Mock DataFlow instance and connection
        mock_dataflow = Mock()
        mock_connection = AsyncMock()
        mock_transaction = Mock()  # Regular mock, not AsyncMock

        # Set up async mocks correctly
        async def mock_get_connection():
            return mock_connection

        # The transaction object should be a regular mock with async methods
        mock_transaction.start = AsyncMock()
        # Mock the transaction() method to return the mock_transaction (not a coroutine)
        mock_connection.transaction = Mock(return_value=mock_transaction)
        mock_connection.execute = AsyncMock()

        mock_dataflow.get_connection = mock_get_connection

        # Create node and set workflow context
        node = TransactionScopeNode()
        node._workflow_context = {"dataflow_instance": mock_dataflow}

        # Execute the node
        result = node.execute(isolation_level="READ_COMMITTED", timeout=30)

        # Verify transaction was stored in context
        assert "transaction_connection" in node._workflow_context
        assert "active_transaction" in node._workflow_context
        assert node._workflow_context["active_transaction"] == mock_transaction

        # Verify result
        assert result["status"] == "started"
        assert "transaction_id" in result

    def test_transaction_commit_node_commits_from_context(self):
        """Test TransactionCommitNode commits transaction from context."""
        from dataflow.nodes.transaction_nodes import TransactionCommitNode

        # Mock transaction and connection
        mock_transaction = Mock()
        mock_connection = Mock()

        # Set up async methods
        mock_transaction.commit = AsyncMock()
        mock_connection.close = AsyncMock()

        node = TransactionCommitNode()
        node._workflow_context = {
            "active_transaction": mock_transaction,
            "transaction_connection": mock_connection,
        }

        result = node.execute()

        # Verify context was cleaned up (set to None, not removed)
        assert node._workflow_context["active_transaction"] is None
        assert node._workflow_context["transaction_connection"] is None

        # Verify result
        assert result["status"] == "committed"

    def test_transaction_rollback_node_rollback_from_context(self):
        """Test TransactionRollbackNode rolls back transaction from context."""
        from dataflow.nodes.transaction_nodes import TransactionRollbackNode

        # Mock transaction and connection
        mock_transaction = Mock()
        mock_connection = Mock()

        # Set up async methods
        mock_transaction.rollback = AsyncMock()
        mock_connection.close = AsyncMock()

        node = TransactionRollbackNode()
        node._workflow_context = {
            "active_transaction": mock_transaction,
            "transaction_connection": mock_connection,
            "rollback_reason": "User requested",
        }

        result = node.execute(reason="User requested")

        # Verify context was cleaned up (set to None, not removed)
        assert node._workflow_context["active_transaction"] is None
        assert node._workflow_context["transaction_connection"] is None

        # Verify result
        assert result["status"] == "rolled_back"
        # The rollback reason comes from workflow context, not parameters
        assert result["reason"] == "User requested"

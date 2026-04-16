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

        # Mock DataFlow instance and adapter
        mock_dataflow = Mock()
        mock_dataflow.config.database.url = "sqlite:///:memory:"

        mock_adapter = AsyncMock()
        mock_transaction_cm = AsyncMock()
        mock_transaction = AsyncMock()
        mock_transaction_cm.__aenter__.return_value = mock_transaction
        mock_adapter.transaction = Mock(return_value=mock_transaction_cm)

        mock_db_node = Mock()
        mock_db_node.adapter = mock_adapter
        mock_dataflow._get_cached_db_node = Mock(return_value=mock_db_node)

        # Create node and set workflow context
        node = TransactionScopeNode()
        node._workflow_context = {"dataflow_instance": mock_dataflow}

        # Execute the node
        result = node.execute(isolation_level="READ_COMMITTED", timeout=30)

        # Verify transaction was stored in context (current contract)
        assert "active_transaction" in node._workflow_context
        assert "transaction_context_manager" in node._workflow_context
        assert "transaction_id" in node._workflow_context
        assert node._workflow_context["active_transaction"] is mock_transaction
        assert (
            node._workflow_context["transaction_context_manager"] is mock_transaction_cm
        )

        # Verify result
        assert result["status"] == "started"
        assert "transaction_id" in result

    def test_transaction_commit_node_commits_from_context(self):
        """Test TransactionCommitNode commits transaction from context."""
        from dataflow.nodes.transaction_nodes import TransactionCommitNode

        # Mock transaction and context manager (current contract)
        mock_transaction = AsyncMock()
        mock_transaction.commit = AsyncMock()
        mock_txn_ctx = AsyncMock()
        mock_txn_ctx.__aexit__ = AsyncMock(return_value=None)

        node = TransactionCommitNode()
        node._workflow_context = {
            "active_transaction": mock_transaction,
            "transaction_context_manager": mock_txn_ctx,
            "transaction_id": "tx_test123",
        }

        result = node.execute()

        # Verify context was cleaned up (set to None, not removed)
        assert node._workflow_context["active_transaction"] is None
        assert node._workflow_context["transaction_context_manager"] is None
        assert node._workflow_context["transaction_id"] is None

        # Verify commit was actually called
        mock_transaction.commit.assert_awaited_once()

        # Verify result
        assert result["status"] == "committed"

    def test_transaction_rollback_node_rollback_from_context(self):
        """Test TransactionRollbackNode rolls back transaction from context."""
        from dataflow.nodes.transaction_nodes import TransactionRollbackNode

        # Mock transaction and context manager (current contract)
        mock_transaction = AsyncMock()
        mock_transaction.rollback = AsyncMock()
        mock_txn_ctx = AsyncMock()
        mock_txn_ctx.__aexit__ = AsyncMock(return_value=None)

        node = TransactionRollbackNode()
        node._workflow_context = {
            "active_transaction": mock_transaction,
            "transaction_context_manager": mock_txn_ctx,
            "transaction_id": "tx_test123",
            "rollback_reason": "User requested",
        }

        result = node.execute(reason="User requested")

        # Verify context was cleaned up (set to None, not removed)
        assert node._workflow_context["active_transaction"] is None
        assert node._workflow_context["transaction_context_manager"] is None

        # Verify rollback was actually called
        mock_transaction.rollback.assert_awaited_once()

        # Verify result
        assert result["status"] == "rolled_back"
        # The rollback reason comes from workflow context, not parameters
        assert result["reason"] == "User requested"

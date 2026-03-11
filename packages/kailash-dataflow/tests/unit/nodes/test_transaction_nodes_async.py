"""Unit tests for async transaction nodes.

Tier 1 (unit tests): Mocking is allowed per testing rules.
Tests verify that the transaction nodes correctly:
- Extend AsyncNode (not Node)
- Implement async_run() (not run())
- Call the adapter's transaction API correctly
- Store/retrieve transaction state via workflow context
- Handle errors properly with cleanup
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

from dataflow.nodes.transaction_nodes import (
    TransactionCommitNode,
    TransactionRollbackNode,
    TransactionRollbackToSavepointNode,
    TransactionSavepointNode,
    TransactionScopeNode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_adapter():
    """Create a mock adapter that returns a mock transaction context manager."""
    mock_txn = MagicMock()
    mock_txn.commit = AsyncMock()
    mock_txn.rollback = AsyncMock()
    mock_txn.connection = MagicMock()
    mock_txn.connection.execute = AsyncMock()

    mock_txn_ctx = AsyncMock()
    mock_txn_ctx.__aenter__ = AsyncMock(return_value=mock_txn)
    mock_txn_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_adapter = MagicMock()
    mock_adapter.transaction.return_value = mock_txn_ctx

    return mock_adapter, mock_txn_ctx, mock_txn


def _make_mock_dataflow(adapter):
    """Create a mock DataFlow instance that returns the given adapter via _get_cached_db_node."""
    mock_df = MagicMock()
    mock_df.config.database.url = "sqlite:///:memory:"

    mock_db_node = MagicMock()
    mock_db_node.adapter = adapter
    mock_df._get_cached_db_node.return_value = mock_db_node

    return mock_df


def _build_context(
    dataflow_instance=None,
    transaction=None,
    txn_ctx=None,
    transaction_id=None,
    savepoints=None,
):
    """Build a workflow context dict."""
    ctx = {}
    if dataflow_instance is not None:
        ctx["dataflow_instance"] = dataflow_instance
    if transaction is not None:
        ctx["active_transaction"] = transaction
    if txn_ctx is not None:
        ctx["transaction_context_manager"] = txn_ctx
    if transaction_id is not None:
        ctx["transaction_id"] = transaction_id
    if savepoints is not None:
        ctx["savepoints"] = savepoints
    return ctx


def _apply_context(node, context):
    """Patch get_workflow_context and set_workflow_context on a node."""
    store = dict(context)

    def getter(key, default=None):
        return store.get(key, default)

    def setter(key, value):
        store[key] = value

    node.get_workflow_context = getter
    node.set_workflow_context = setter
    return store


# ---------------------------------------------------------------------------
# Tests: Base class verification
# ---------------------------------------------------------------------------


class TestAsyncBaseClass:
    """Verify all transaction nodes extend AsyncNode."""

    def test_scope_node_is_async(self):
        assert issubclass(TransactionScopeNode, AsyncNode)

    def test_commit_node_is_async(self):
        assert issubclass(TransactionCommitNode, AsyncNode)

    def test_rollback_node_is_async(self):
        assert issubclass(TransactionRollbackNode, AsyncNode)

    def test_savepoint_node_is_async(self):
        assert issubclass(TransactionSavepointNode, AsyncNode)

    def test_rollback_to_savepoint_node_is_async(self):
        assert issubclass(TransactionRollbackToSavepointNode, AsyncNode)

    def test_scope_node_has_async_run(self):
        node = TransactionScopeNode(node_id="test")
        assert hasattr(node, "async_run")

    def test_commit_node_has_async_run(self):
        node = TransactionCommitNode(node_id="test")
        assert hasattr(node, "async_run")

    def test_rollback_node_has_async_run(self):
        node = TransactionRollbackNode(node_id="test")
        assert hasattr(node, "async_run")


# ---------------------------------------------------------------------------
# Tests: TransactionScopeNode
# ---------------------------------------------------------------------------


class TestTransactionScopeNode:
    """Test TransactionScopeNode async_run behavior."""

    @pytest.mark.asyncio
    async def test_begin_transaction_success(self):
        adapter, txn_ctx, txn = _make_mock_adapter()
        df = _make_mock_dataflow(adapter)

        node = TransactionScopeNode(node_id="scope_test")
        ctx = _build_context(dataflow_instance=df)
        store = _apply_context(node, ctx)

        result = await node.async_run()

        assert result["status"] == "started"
        assert "transaction_id" in result
        assert result["isolation_level"] == "READ_COMMITTED"
        assert result["timeout"] == 30
        assert result["rollback_on_error"] is True

        # Verify adapter.transaction() was called
        adapter.transaction.assert_called_once()

        # Verify transaction stored in context
        assert store["active_transaction"] is txn
        assert store["transaction_context_manager"] is txn_ctx
        assert store["transaction_id"] is not None
        assert store["savepoints"] == {}

    @pytest.mark.asyncio
    async def test_begin_transaction_custom_params(self):
        adapter, txn_ctx, txn = _make_mock_adapter()
        df = _make_mock_dataflow(adapter)

        node = TransactionScopeNode(node_id="scope_custom")
        store = _apply_context(node, _build_context(dataflow_instance=df))

        result = await node.async_run(
            isolation_level="SERIALIZABLE",
            timeout=60,
            rollback_on_error=False,
        )

        assert result["isolation_level"] == "SERIALIZABLE"
        assert result["timeout"] == 60
        assert result["rollback_on_error"] is False

    @pytest.mark.asyncio
    async def test_begin_transaction_no_dataflow_instance(self):
        node = TransactionScopeNode(node_id="scope_fail")
        _apply_context(node, {})

        with pytest.raises(NodeExecutionError, match="DataFlow instance not found"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_begin_transaction_adapter_failure(self):
        adapter, txn_ctx, txn = _make_mock_adapter()
        txn_ctx.__aenter__.side_effect = RuntimeError("Connection refused")
        df = _make_mock_dataflow(adapter)

        node = TransactionScopeNode(node_id="scope_err")
        _apply_context(node, _build_context(dataflow_instance=df))

        with pytest.raises(NodeExecutionError, match="Failed to begin transaction"):
            await node.async_run()


# ---------------------------------------------------------------------------
# Tests: TransactionCommitNode
# ---------------------------------------------------------------------------


class TestTransactionCommitNode:
    """Test TransactionCommitNode async_run behavior."""

    @pytest.mark.asyncio
    async def test_commit_success(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionCommitNode(node_id="commit_test")
        store = _apply_context(
            node,
            _build_context(
                transaction=txn,
                txn_ctx=txn_ctx,
                transaction_id="tx_abc123",
                savepoints={"sp1": True},
            ),
        )

        result = await node.async_run()

        assert result["status"] == "committed"
        assert result["transaction_id"] == "tx_abc123"
        txn.commit.assert_awaited_once()
        txn_ctx.__aexit__.assert_awaited_once()

        # Verify context cleaned up
        assert store["active_transaction"] is None
        assert store["transaction_context_manager"] is None
        assert store["transaction_id"] is None
        assert store["savepoints"] is None

    @pytest.mark.asyncio
    async def test_commit_no_transaction(self):
        node = TransactionCommitNode(node_id="commit_fail")
        _apply_context(node, {})

        with pytest.raises(NodeExecutionError, match="No active transaction"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_commit_failure_cleans_up(self):
        _, txn_ctx, txn = _make_mock_adapter()
        txn.commit.side_effect = RuntimeError("commit failed")

        node = TransactionCommitNode(node_id="commit_err")
        store = _apply_context(
            node,
            _build_context(transaction=txn, txn_ctx=txn_ctx, transaction_id="tx_err"),
        )

        with pytest.raises(NodeExecutionError, match="Failed to commit"):
            await node.async_run()

        # Context should be cleaned up even on failure
        assert store["active_transaction"] is None
        assert store["transaction_context_manager"] is None


# ---------------------------------------------------------------------------
# Tests: TransactionRollbackNode
# ---------------------------------------------------------------------------


class TestTransactionRollbackNode:
    """Test TransactionRollbackNode async_run behavior."""

    @pytest.mark.asyncio
    async def test_rollback_success(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionRollbackNode(node_id="rb_test")
        store = _apply_context(
            node,
            _build_context(transaction=txn, txn_ctx=txn_ctx, transaction_id="tx_rb"),
        )

        result = await node.async_run(reason="Test rollback")

        assert result["status"] == "rolled_back"
        assert result["reason"] == "Test rollback"
        assert result["transaction_id"] == "tx_rb"
        txn.rollback.assert_awaited_once()

        # Context cleaned up
        assert store["active_transaction"] is None

    @pytest.mark.asyncio
    async def test_rollback_default_reason(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionRollbackNode(node_id="rb_default")
        _apply_context(
            node,
            _build_context(transaction=txn, txn_ctx=txn_ctx, transaction_id="tx_x"),
        )

        result = await node.async_run()
        assert result["reason"] == "Manual rollback"

    @pytest.mark.asyncio
    async def test_rollback_no_transaction(self):
        node = TransactionRollbackNode(node_id="rb_fail")
        _apply_context(node, {})

        with pytest.raises(NodeExecutionError, match="No active transaction"):
            await node.async_run()


# ---------------------------------------------------------------------------
# Tests: TransactionSavepointNode
# ---------------------------------------------------------------------------


class TestTransactionSavepointNode:
    """Test TransactionSavepointNode async_run behavior."""

    @pytest.mark.asyncio
    async def test_create_savepoint_success(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionSavepointNode(node_id="sp_test")
        store = _apply_context(
            node,
            _build_context(
                transaction=txn,
                txn_ctx=txn_ctx,
                transaction_id="tx_sp",
                savepoints={},
            ),
        )

        result = await node.async_run(name="my_savepoint")

        assert result["status"] == "created"
        assert result["savepoint"] == "my_savepoint"
        txn.connection.execute.assert_awaited_once_with('SAVEPOINT "my_savepoint"')
        assert store["savepoints"] == {"my_savepoint": True}

    @pytest.mark.asyncio
    async def test_create_savepoint_no_name(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionSavepointNode(node_id="sp_noname")
        _apply_context(node, _build_context(transaction=txn, txn_ctx=txn_ctx))

        with pytest.raises(NodeExecutionError, match="Savepoint name is required"):
            await node.async_run()

    @pytest.mark.asyncio
    async def test_create_savepoint_no_transaction(self):
        node = TransactionSavepointNode(node_id="sp_notxn")
        _apply_context(node, {})

        with pytest.raises(NodeExecutionError, match="No active transaction"):
            await node.async_run(name="sp1")


# ---------------------------------------------------------------------------
# Tests: TransactionRollbackToSavepointNode
# ---------------------------------------------------------------------------


class TestTransactionRollbackToSavepointNode:
    """Test TransactionRollbackToSavepointNode async_run behavior."""

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint_success(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionRollbackToSavepointNode(node_id="rbsp_test")
        store = _apply_context(
            node,
            _build_context(
                transaction=txn,
                txn_ctx=txn_ctx,
                transaction_id="tx_rbsp",
                savepoints={"sp1": True, "sp2": True, "sp3": True},
            ),
        )

        result = await node.async_run(savepoint="sp2")

        assert result["status"] == "rolled_back_to_savepoint"
        assert result["savepoint"] == "sp2"
        txn.connection.execute.assert_awaited_once_with('ROLLBACK TO SAVEPOINT "sp2"')
        # sp2 and sp3 should be removed; only sp1 remains
        assert store["savepoints"] == {"sp1": True}

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint_not_found(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionRollbackToSavepointNode(node_id="rbsp_nf")
        _apply_context(
            node,
            _build_context(
                transaction=txn,
                txn_ctx=txn_ctx,
                savepoints={"sp1": True},
            ),
        )

        with pytest.raises(
            NodeExecutionError, match="Savepoint 'sp_missing' not found"
        ):
            await node.async_run(savepoint="sp_missing")

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint_no_transaction(self):
        node = TransactionRollbackToSavepointNode(node_id="rbsp_notxn")
        _apply_context(node, {})

        with pytest.raises(NodeExecutionError, match="No active transaction"):
            await node.async_run(savepoint="sp1")

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint_no_name(self):
        _, txn_ctx, txn = _make_mock_adapter()

        node = TransactionRollbackToSavepointNode(node_id="rbsp_noname")
        _apply_context(
            node, _build_context(transaction=txn, txn_ctx=txn_ctx, savepoints={})
        )

        with pytest.raises(NodeExecutionError, match="Savepoint name is required"):
            await node.async_run()


# ---------------------------------------------------------------------------
# Tests: Parameter definitions
# ---------------------------------------------------------------------------


class TestParameters:
    """Verify get_parameters returns correct definitions."""

    def test_scope_parameters(self):
        node = TransactionScopeNode(node_id="p1")
        params = node.get_parameters()
        assert "isolation_level" in params
        assert "timeout" in params
        assert "rollback_on_error" in params

    def test_commit_parameters(self):
        node = TransactionCommitNode(node_id="p2")
        params = node.get_parameters()
        assert params == {}

    def test_rollback_parameters(self):
        node = TransactionRollbackNode(node_id="p3")
        params = node.get_parameters()
        assert "reason" in params

    def test_savepoint_parameters(self):
        node = TransactionSavepointNode(node_id="p4")
        params = node.get_parameters()
        assert "name" in params
        assert params["name"].required is True

    def test_rollback_to_savepoint_parameters(self):
        node = TransactionRollbackToSavepointNode(node_id="p5")
        params = node.get_parameters()
        assert "savepoint" in params
        assert params["savepoint"].required is True

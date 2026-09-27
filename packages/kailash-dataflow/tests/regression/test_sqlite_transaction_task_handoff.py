"""Public transaction nodes may hand an explicit scope to another node task."""

import asyncio

import pytest

from dataflow import DataFlow
from dataflow.nodes.transaction_nodes import (
    TransactionCommitNode,
    TransactionRollbackNode,
    TransactionScopeNode,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_real_sqlite_public_transaction_node_task_handoff(tmp_path, finish):
    db = DataFlow("sqlite:///" + str(tmp_path / "handoff.db"), auto_migrate=True)
    try:
        assert await db.initialize()
        adapter = await db._get_or_create_async_sql_node("sqlite")._get_adapter()
        await adapter.execute("CREATE TABLE handoff(value INTEGER)")
        context = {"dataflow_instance": db}
        start = TransactionScopeNode(node_id="begin")
        end = (
            TransactionCommitNode if finish == "commit" else TransactionRollbackNode
        )(node_id="end")
        start._workflow_context = context
        end._workflow_context = context
        started = await asyncio.create_task(start.async_run())
        assert started["status"] == "started"
        scope = context["active_transaction"]
        await adapter.execute(
            "INSERT INTO handoff VALUES (1)", transaction=scope.transaction
        )
        result = await asyncio.create_task(end.async_run())
        assert result["status"] == (
            "committed" if finish == "commit" else "rolled_back"
        )
        assert context["active_transaction"] is None
        assert adapter._transaction_depth == 0
        assert adapter._transaction_connection is None
        assert await adapter.execute("SELECT value FROM handoff") == (
            [{"value": 1}] if finish == "commit" else []
        )
    finally:
        await db.close_async()

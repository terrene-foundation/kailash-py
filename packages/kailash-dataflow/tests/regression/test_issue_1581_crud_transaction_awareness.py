# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1581 — generated DataFlow CRUD nodes were NOT
transaction-aware: they ran every statement on their own cached
``AsyncSQLDatabaseNode`` in ``transaction_mode="auto"`` (per-statement
autocommit), so a CRUD write inside a ``TransactionScopeNode`` workflow
committed independently and survived a later ``TransactionRollbackNode``.

Root cause (confirmed by live PG:5434 + SQLite reproduction, not hypothesis):

``TransactionScopeNode`` stores an ``_AdapterTransactionScope`` under the
workflow-context key ``active_transaction`` (the runtime injects the SAME
``_workflow_context`` dict onto every node in the workflow — verified by
``id()`` equality of the context dict across the scope node and the CRUD node).
The generated CRUD nodes never read that key: each called
``sql_node.async_run(..., transaction_mode="auto")`` on the cached node, and the
``transaction_mode`` input was INERT (``async_run`` reads it from config at
init, never from inputs). So the CRUD write auto-committed on its own
connection and no rollback could reach it.

The fix (two surgical parts):
  * core ``kailash.nodes.data.async_sql`` — ``_AdapterTransactionScope`` gained
    a ``.transaction`` property (the raw adapter txn handle), and
    ``AsyncSQLDatabaseNode.async_run`` / ``execute_many_async`` accept an
    explicit ``transaction=`` input threaded to a borrow-don't-own branch in
    ``_execute_with_transaction`` / ``_execute_many_with_transaction`` (run ON
    the borrowed txn; do NOT begin/commit/rollback).
  * ``dataflow.core.nodes`` — every generated CRUD site routes through
    ``_run_sql_in_scope(node, sql_node, **kw)``, which reads
    ``active_transaction`` off workflow context and passes ``scope.transaction``
    into ``async_run``. The PG ``$11`` param-type retry fallback was ALSO fixed
    (it spawned a fresh non-pooled node that escaped the scope — now, when a
    scope is active, the retry runs on the pooled node that joins it).

Reads join too (LIST/READ/COUNT), giving read-your-writes inside the scope; a
``ROLLBACK TO SAVEPOINT`` discards post-savepoint CRUD writes because the CRUD
runs on the scope's connection.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import time

import pytest

from dataflow import DataFlow
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
async def pg_suite():
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


async def _drop_table(url: str, table: str) -> None:
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=url,
        database_type="postgresql",
        query=f"DROP TABLE IF EXISTS {table} CASCADE",
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


async def _raw_count(url: str, table: str, sku: str) -> int:
    """Count rows via a FRESH asyncpg connection — proves what actually
    committed to the database, independent of any pool / cache / scope."""
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(f"SELECT count(*) FROM {table} WHERE sku = $1", sku)
    finally:
        await conn.close()


def _sku(prefix: str = "s1581") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _ctx(db: DataFlow) -> dict:
    return {"workflow_context": {"dataflow_instance": db}}


# ---------------------------------------------------------------------------
# AC1 — commit PERSISTS: a CREATE inside a scope is durable after commit.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_create_in_scope_persists_after_commit(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1581_commit_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581CommitProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("commit")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode", "start_tx", {"isolation_level": "READ_COMMITTED"}
    )
    workflow.add_node(
        "Issue1581CommitProductCreateNode",
        "create",
        {"name": "Committed", "sku": sku},
    )
    workflow.add_node("TransactionCommitNode", "commit_tx", {})
    workflow.add_connection("start_tx", "transaction_id", "create", "transaction_id")
    workflow.add_connection("create", "id", "commit_tx", "record_count")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("commit_tx", {}).get("status") == "committed"
    # Durable on a FRESH connection → genuinely committed.
    assert await _raw_count(url, "issue1581_commit_products", sku) == 1


# ---------------------------------------------------------------------------
# AC2 — rollback DISCARDS: a CREATE inside a scope does NOT survive rollback.
#        (This is the exact #1581 bug: pre-fix the CREATE auto-committed.)
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_create_in_scope_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1581_rollback_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581RollbackProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("rollback")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode",
        "start_tx",
        {"isolation_level": "READ_COMMITTED", "rollback_on_error": True},
    )
    workflow.add_node(
        "Issue1581RollbackProductCreateNode",
        "create",
        {"name": "Doomed", "sku": sku},
    )
    # Trigger node returns normally (does NOT raise — raising would abort the
    # whole workflow before rollback_tx runs). It just signals the rollback.
    workflow.add_node(
        "PythonCodeNode",
        "trigger_error",
        {"code": "result = {'status': 'error', 'message': 'force rollback'}"},
    )
    workflow.add_node("TransactionRollbackNode", "rollback_tx", {})
    workflow.add_connection("start_tx", "result", "create", "input_data")
    workflow.add_connection("create", "result", "trigger_error", "input_data")
    workflow.add_connection("trigger_error", "result", "rollback_tx", "input_data")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    # The write MUST NOT have committed — pre-fix this was 1 (auto-commit).
    assert await _raw_count(url, "issue1581_rollback_products", sku) == 0


# ---------------------------------------------------------------------------
# AC3 — read-your-writes: a LIST inside the scope sees the uncommitted CREATE
#        (reads join the scope's connection too).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_read_your_writes_inside_scope(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1581_ryw_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581RywProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("ryw")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode", "start_tx", {"isolation_level": "READ_COMMITTED"}
    )
    workflow.add_node(
        "Issue1581RywProductCreateNode", "create", {"name": "Fresh", "sku": sku}
    )
    workflow.add_node(
        "Issue1581RywProductListNode",
        "list_in_tx",
        {"filter": {"sku": sku}, "limit": 10},
    )
    workflow.add_node("TransactionCommitNode", "commit_tx", {})
    workflow.add_connection("start_tx", "transaction_id", "create", "transaction_id")
    workflow.add_connection("create", "id", "list_in_tx", "previous_id")
    workflow.add_connection("list_in_tx", "count", "commit_tx", "record_count")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    # The in-scope LIST saw the row created earlier in the SAME transaction,
    # BEFORE commit — read-your-writes.
    assert results.get("list_in_tx", {}).get("count") == 1
    assert results.get("commit_tx", {}).get("status") == "committed"


# ---------------------------------------------------------------------------
# AC4 — back-compat: NO scope → CRUD still auto-commits (express path).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_no_scope_still_autocommits(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1581_nocope_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581NocopeProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("noscope")

    # express.create runs with NO workflow transaction scope → must persist.
    await db.express.create(
        "Issue1581NocopeProduct", {"name": "Autocommit", "sku": sku}
    )
    assert await _raw_count(url, "issue1581_nocope_products", sku) == 1


# ---------------------------------------------------------------------------
# AC5 — savepoint: ROLLBACK TO SAVEPOINT discards a post-savepoint CRUD write
#        while keeping the pre-savepoint one (CRUD runs on the scope conn).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_rollback_to_savepoint_discards_post_savepoint_create(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1581_sp_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581SpProduct:
        name: str
        sku: str

    await db.initialize()
    sku_a = _sku("sp-keep")
    sku_b = _sku("sp-drop")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode", "start_tx", {"isolation_level": "READ_COMMITTED"}
    )
    workflow.add_node(
        "Issue1581SpProductCreateNode", "create_a", {"name": "Keep", "sku": sku_a}
    )
    # TransactionSavepointNode's param is "name"; the rollback node's is
    # "savepoint" (distinct param names in the SDK).
    workflow.add_node("TransactionSavepointNode", "sp", {"name": "sp1"})
    workflow.add_node(
        "Issue1581SpProductCreateNode", "create_b", {"name": "Drop", "sku": sku_b}
    )
    workflow.add_node(
        "TransactionRollbackToSavepointNode", "rollback_sp", {"savepoint": "sp1"}
    )
    workflow.add_node("TransactionCommitNode", "commit_tx", {})
    workflow.add_connection("start_tx", "result", "create_a", "input_data")
    workflow.add_connection("create_a", "result", "sp", "input_data")
    workflow.add_connection("sp", "result", "create_b", "input_data")
    workflow.add_connection("create_b", "result", "rollback_sp", "input_data")
    workflow.add_connection("rollback_sp", "result", "commit_tx", "input_data")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("commit_tx", {}).get("status") == "committed"
    # A (before savepoint) survives; B (after savepoint) was rolled back.
    assert await _raw_count(url, "issue1581_sp_products", sku_a) == 1
    assert await _raw_count(url, "issue1581_sp_products", sku_b) == 0


# ---------------------------------------------------------------------------
# AC6 — SQLite parity: rollback discards the CRUD write on SQLite too.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_sqlite_create_in_scope_discarded_after_rollback(tmp_path):
    url = f"sqlite:///{tmp_path}/issue1581.db"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581SqliteProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("sqlite")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode",
        "start_tx",
        {"isolation_level": "READ_COMMITTED", "rollback_on_error": True},
    )
    workflow.add_node(
        "Issue1581SqliteProductCreateNode",
        "create",
        {"name": "Doomed", "sku": sku},
    )
    workflow.add_node(
        "PythonCodeNode",
        "trigger_error",
        {"code": "result = {'status': 'error', 'message': 'force rollback'}"},
    )
    workflow.add_node("TransactionRollbackNode", "rollback_tx", {})
    workflow.add_connection("start_tx", "result", "create", "input_data")
    workflow.add_connection("create", "result", "trigger_error", "input_data")
    workflow.add_connection("trigger_error", "result", "rollback_tx", "input_data")

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    # Verify via the framework read (SQLite file store) that the row is gone.
    remaining = await db.express.list("Issue1581SqliteProduct", {"sku": sku})
    assert remaining == []


# ---------------------------------------------------------------------------
# AC7 — fail-closed: an active scope whose object exposes no `.transaction`
#        handle MUST raise, NOT silently auto-commit (zero-tolerance Rule 3).
# ---------------------------------------------------------------------------
@pytest.mark.regression
async def test_run_sql_in_scope_fails_closed_without_transaction_handle():
    from dataflow.core.nodes import _run_sql_in_scope
    from kailash.sdk_exceptions import NodeExecutionError

    class _ScopeWithoutTransaction:
        """A stand-in for a corrupt/unexpected active_transaction object."""

    class _FakeNode:
        def get_workflow_context(self, key, default=None):
            if key == "active_transaction":
                return _ScopeWithoutTransaction()
            return default

    class _FakeSqlNode:
        async def async_run(self, **kwargs):  # must NEVER be reached
            raise AssertionError(
                "async_run must not run — the helper must fail closed first"
            )

    with pytest.raises(NodeExecutionError, match="escape the transaction scope"):
        await _run_sql_in_scope(_FakeNode(), _FakeSqlNode(), query="SELECT 1")


# ---------------------------------------------------------------------------
# AC8 — core batch borrow: execute_many_async(transaction=<borrowed>) runs ON
#        the borrowed transaction (rollback discards) and does NOT auto-commit.
#        Gives the #1581 batch plumbing a real consumer + test.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_execute_many_async_borrowed_transaction_rollback_discards(pg_suite):
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    url = pg_suite.config.url
    await _drop_table(url, "issue1581_batch_rows")

    node = AsyncSQLDatabaseNode(connection_string=url, database_type="postgresql")
    adapter = await node._get_adapter()
    await adapter.execute("CREATE TABLE IF NOT EXISTS issue1581_batch_rows (sku TEXT)")
    sku = _sku("batch")

    # Borrow a transaction via the uniform adapter.transaction() contract, run a
    # batch INSERT on it, then roll it back — the rows MUST NOT persist.
    async with adapter.transaction() as scope:
        await node.execute_many_async(
            "INSERT INTO issue1581_batch_rows (sku) VALUES (:sku)",
            [{"sku": sku}, {"sku": sku}, {"sku": sku}],
            transaction=scope.transaction,
        )
        await scope.rollback()

    assert await _raw_count(url, "issue1581_batch_rows", sku) == 0
    await node.cleanup()


# ---------------------------------------------------------------------------
# AC9 — DEFERRED CONTRACT (xfail-strict): bulk write nodes are NOT yet
#        transaction-aware. A BulkCreate inside a rolled-back scope currently
#        auto-commits and survives. When #1585 makes bulk scope-aware this test
#        XPASSes and the marker MUST be removed same-shard (rules/testing.md
#        § xfail-strict). Tracked by #1585.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Deferred: bulk CRUD nodes bypass the transaction scope (bulk.py / "
        "bulk_create_pool.py / bulk_upsert.py run auto-commit and do not join "
        "active_transaction). A BulkCreate inside a rolled-back TransactionScope "
        "auto-commits and survives, so count is 2 (not 0). XPASSes when #1585 "
        "makes bulk scope-aware; remove marker same-shard. Tracked by #1585."
    ),
)
async def test_bulk_create_in_scope_discarded_after_rollback_xfail(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1581_bulk_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1581BulkProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("bulk")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode",
        "start_tx",
        {"isolation_level": "READ_COMMITTED", "rollback_on_error": True},
    )
    workflow.add_node(
        "Issue1581BulkProductBulkCreateNode",
        "bulk",
        {"data": [{"name": "A", "sku": sku}, {"name": "B", "sku": sku}]},
    )
    workflow.add_node(
        "PythonCodeNode",
        "trigger_error",
        {"code": "result = {'status': 'error'}"},
    )
    workflow.add_node("TransactionRollbackNode", "rollback_tx", {})
    workflow.add_connection("start_tx", "result", "bulk", "input_data")
    workflow.add_connection("bulk", "result", "trigger_error", "input_data")
    workflow.add_connection("trigger_error", "result", "rollback_tx", "input_data")

    runtime = LocalRuntime()
    runtime.execute(workflow.build(), parameters=_ctx(db))

    # DESIRED (post-#1585) behavior: rollback discards the bulk write.
    assert await _raw_count(url, "issue1581_bulk_products", sku) == 0

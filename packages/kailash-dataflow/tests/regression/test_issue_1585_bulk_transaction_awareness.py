# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1585 — BULK DataFlow nodes were NOT
transaction-aware (the follow-up to #1581, which fixed single-record CRUD).

Pre-fix, ``BulkCreate``/``BulkUpdate``/``BulkDelete``/``BulkUpsert`` ran on their
own cached ``AsyncSQLDatabaseNode`` in ``transaction_mode="auto"`` (per-statement
autocommit). Inside a ``TransactionScopeNode`` workflow a bulk write committed
independently and SURVIVED a later ``TransactionRollbackNode`` — the same silent
data-integrity violation #1581 fixed for single-record CRUD, at a larger blast
radius (bulk ops move more rows).

The fix threads the scope's borrowed transaction handle through the bulk path:

  * Path A (generated ``<Model>Bulk*Node`` → ``db.bulk.bulk_*`` in
    ``features/bulk.py``): the 4 dispatch sites in ``core/nodes.py`` resolve the
    active scope via ``_resolve_scope_transaction`` and pass ``transaction=`` into
    ``bulk_*()``, which forwards it to every ``sql_node.async_run(transaction=...)``
    — routing to the #1581 borrow-don't-own branch. The borrowed handle is a
    ``(conn, tx)`` tuple that carries the scope's connection, so the batch INSERT
    runs ON the scope's connection and a rollback discards it. When no scope is
    active the call is byte-identical to the prior auto-commit path.

  * Path B (standalone ``DataFlowBulkUpsertNode`` / ``BulkCreatePoolNode``, which
    spawn FRESH non-pooled nodes): each resolves the scope in its execution path
    and threads the borrowed handle to the fresh node's ``async_run``. The upsert
    node normally resolves via ``async_safe_run`` (a SEPARATE event loop where a
    borrowed asyncpg connection cannot be used), so when a scope is active it
    bypasses that boundary and awaits directly on the runtime loop. The pool node
    forces its direct borrow path (its own pool cannot join the scope).

Verified against live PG:5434 + SQLite — NOT hypothesis. Permanent regression
tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import time

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# Import the standalone Path B nodes so their @register_node decorators run and
# the string node types ("DataFlowBulkUpsertNode" / "BulkCreatePoolNode") resolve
# in the workflow builder's registry.
from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode  # noqa: F401
from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode  # noqa: F401


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
    committed, independent of any pool / cache / scope."""
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(f"SELECT count(*) FROM {table} WHERE sku = $1", sku)
    finally:
        await conn.close()


async def _raw_name(url: str, table: str, sku: str) -> str | None:
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(f"SELECT name FROM {table} WHERE sku = $1", sku)
    finally:
        await conn.close()


def _sku(prefix: str = "s1585") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _ctx(db: DataFlow) -> dict:
    return {"workflow_context": {"dataflow_instance": db}}


def _rollback_workflow(bulk_node_type: str, bulk_id: str, bulk_params: dict):
    """A TransactionScopeNode → <bulk> → trigger → TransactionRollbackNode graph.

    The trigger returns normally (does NOT raise — raising would abort the whole
    workflow before rollback_tx runs); it just signals the rollback.
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode",
        "start_tx",
        {"isolation_level": "READ_COMMITTED", "rollback_on_error": True},
    )
    workflow.add_node(bulk_node_type, bulk_id, bulk_params)
    workflow.add_node(
        "PythonCodeNode",
        "trigger_error",
        {"code": "result = {'status': 'error', 'message': 'force rollback'}"},
    )
    workflow.add_node("TransactionRollbackNode", "rollback_tx", {})
    workflow.add_connection("start_tx", "result", bulk_id, "input_data")
    workflow.add_connection(bulk_id, "result", "trigger_error", "input_data")
    workflow.add_connection("trigger_error", "result", "rollback_tx", "input_data")
    return workflow


# ===========================================================================
# Path A — generated <Model>Bulk*Node → features/bulk.py (cached pooled node)
# ===========================================================================


# AC1 — commit PERSISTS: a BulkCreate inside a scope is durable after commit.
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_bulk_create_persists_after_commit(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1585_commit_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585CommitProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("commit")

    workflow = WorkflowBuilder()
    workflow.add_node(
        "TransactionScopeNode",
        "start_tx",
        {"isolation_level": "READ_COMMITTED", "rollback_on_error": True},
    )
    workflow.add_node(
        "Issue1585CommitProductBulkCreateNode",
        "bulk",
        {"data": [{"name": "A", "sku": sku}, {"name": "B", "sku": sku}]},
    )
    workflow.add_node("TransactionCommitNode", "commit_tx", {})
    workflow.add_connection("start_tx", "result", "bulk", "input_data")
    workflow.add_connection("bulk", "result", "commit_tx", "input_data")

    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("commit_tx", {}).get("status") == "committed"
    # Both rows MUST be durable after commit.
    assert await _raw_count(url, "issue1585_commit_products", sku) == 2


# AC2 — rollback DISCARDS a BulkCreate (the core #1585 bug at the create surface).
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_bulk_create_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1585_create_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585CreateProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("create")

    workflow = _rollback_workflow(
        "Issue1585CreateProductBulkCreateNode",
        "bulk",
        {"data": [{"name": "A", "sku": sku}, {"name": "B", "sku": sku}]},
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    # Pre-fix this was 2 (bulk auto-committed and survived the rollback).
    assert await _raw_count(url, "issue1585_create_products", sku) == 0


# AC3 — rollback DISCARDS a BulkUpdate: the pre-scope value survives.
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_bulk_update_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1585_update_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585UpdateProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("update")

    # Seed a committed row (no scope → auto-commit) with name "original".
    await db.express.create("Issue1585UpdateProduct", {"name": "original", "sku": sku})
    assert await _raw_name(url, "issue1585_update_products", sku) == "original"

    workflow = _rollback_workflow(
        "Issue1585UpdateProductBulkUpdateNode",
        "bulk",
        {"filter": {"sku": sku}, "fields": {"name": "mutated"}},
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    # The UPDATE MUST have been discarded — the seeded value survives.
    assert await _raw_name(url, "issue1585_update_products", sku) == "original"


# AC4 — rollback DISCARDS a BulkDelete: the row survives the rolled-back delete.
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_bulk_delete_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1585_delete_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585DeleteProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("delete")

    # Seed two committed rows.
    await db.express.create("Issue1585DeleteProduct", {"name": "keep", "sku": sku})
    await db.express.create("Issue1585DeleteProduct", {"name": "keep", "sku": sku})
    assert await _raw_count(url, "issue1585_delete_products", sku) == 2

    workflow = _rollback_workflow(
        "Issue1585DeleteProductBulkDeleteNode",
        "bulk",
        {"filter": {"sku": sku}},
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    # The DELETE MUST have been discarded — both rows survive.
    assert await _raw_count(url, "issue1585_delete_products", sku) == 2


# AC5 — rollback DISCARDS a BulkUpsert (insert path).
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_bulk_upsert_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "issue1585_upsert_products")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585UpsertProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("upsert")

    # Upsert on the PK: every record MUST supply the conflict-target column.
    # Fresh (non-existent) ids → INSERT via ON CONFLICT (id); rollback discards.
    base_id = int(time.time() * 1000) % 2_000_000_000
    workflow = _rollback_workflow(
        "Issue1585UpsertProductBulkUpsertNode",
        "bulk",
        {
            "data": [
                {"id": base_id, "name": "A", "sku": sku},
                {"id": base_id + 1, "name": "B", "sku": sku},
            ],
            "conflict_on": ["id"],
            "conflict_resolution": "update",
        },
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    assert await _raw_count(url, "issue1585_upsert_products", sku) == 0


# AC6 — SQLite parity: rollback discards a BulkCreate on SQLite too.
@pytest.mark.regression
@pytest.mark.integration
async def test_sqlite_bulk_create_discarded_after_rollback(tmp_path):
    url = f"sqlite:///{tmp_path}/issue1585.db"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585SqliteBulkProduct:
        name: str
        sku: str

    await db.initialize()
    sku = _sku("sqlite")

    workflow = _rollback_workflow(
        "Issue1585SqliteBulkProductBulkCreateNode",
        "bulk",
        {"data": [{"name": "A", "sku": sku}, {"name": "B", "sku": sku}]},
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    remaining = await db.express.list("Issue1585SqliteBulkProduct", {"sku": sku})
    assert remaining == []


# ===========================================================================
# Path B (AC3 in #1585) — standalone fresh-node bulk nodes join the scope.
# These validate that the async_safe_run bypass (bulk_upsert) and the
# force-direct-borrow routing (bulk_create_pool) keep the write on the scope's
# connection so a rollback discards it.
# ===========================================================================


# AC7 — standalone DataFlowBulkUpsertNode inside a scope is discarded on
#        rollback (exercises the async_safe_run bypass in async_run).
@pytest.mark.regression
@pytest.mark.integration
async def test_standalone_bulk_upsert_node_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585StandaloneUpsert:
        name: str
        sku: str

    await db.initialize()
    # The standalone node writes to a raw table by name — resolve the model's
    # ACTUAL table name (DataFlow pluralizes the class name).
    table = db._class_name_to_table_name("Issue1585StandaloneUpsert")
    sku = _sku("saupsert")

    workflow = _rollback_workflow(
        "DataFlowBulkUpsertNode",
        "bulk",
        {
            "table_name": table,
            "connection_string": url,
            "database_type": "postgresql",
            "data": [{"name": "A", "sku": sku}],
            "conflict_columns": ["id"],
        },
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    # Pre-fix the fresh non-pooled node auto-committed and survived rollback.
    assert await _raw_count(url, table, sku) == 0


# AC8 — standalone BulkCreatePoolNode (direct path) inside a scope is discarded
#        on rollback (exercises the force-direct-borrow routing).
@pytest.mark.regression
@pytest.mark.integration
async def test_standalone_bulk_create_pool_node_discarded_after_rollback(pg_suite):
    url = pg_suite.config.url

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1585StandalonePool:
        name: str
        sku: str

    await db.initialize()
    table = db._class_name_to_table_name("Issue1585StandalonePool")
    sku = _sku("sapool")

    workflow = _rollback_workflow(
        "BulkCreatePoolNode",
        "bulk",
        {
            "table_name": table,
            "connection_string": url,
            "database_type": "postgresql",
            "data": [{"name": "A", "sku": sku}, {"name": "B", "sku": sku}],
        },
    )
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow.build(), parameters=_ctx(db))

    assert results.get("rollback_tx", {}).get("status") == "rolled_back"
    assert await _raw_count(url, table, sku) == 0


# AC9 — fail-closed: a BulkCreatePoolNode inside a scope with NO connection_string
#        MUST raise rather than silently no-op (returning the simulation stub
#        would report fabricated success while writing nothing).
@pytest.mark.regression
async def test_bulk_create_pool_node_fails_closed_without_connection_string():
    from kailash.sdk_exceptions import NodeExecutionError

    from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode

    class _Scope:
        transaction = ("fake_conn", "fake_tx")  # non-None handle

    node = BulkCreatePoolNode(table_name="t", database_type="postgresql")
    # Inject an active scope with a usable handle but give the node no
    # connection_string — it cannot join, so it MUST fail closed.
    node._workflow_context = {"active_transaction": _Scope()}

    with pytest.raises(NodeExecutionError, match="TransactionScopeNode"):
        await node.async_run(data=[{"name": "A", "sku": "x"}])


# AC10 — fail-closed SYMMETRY: DataFlowBulkUpsertNode inside a scope with NO
#        connection_string MUST raise too (its dry-run-shaped else branch would
#        otherwise report fabricated success — rows_affected=len(data) — while
#        writing nothing and discarding the borrowed handle). Mirrors AC9 for the
#        sibling standalone node (security-reviewer #1585 MEDIUM).
@pytest.mark.regression
async def test_bulk_upsert_node_fails_closed_without_connection_string():
    from kailash.sdk_exceptions import NodeExecutionError

    from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode

    class _Scope:
        transaction = ("fake_conn", "fake_tx")  # non-None handle

    # No connection_string; real (non-dry-run) data inside an active scope.
    node = DataFlowBulkUpsertNode(table_name="t", database_type="postgresql")
    node._workflow_context = {"active_transaction": _Scope()}

    with pytest.raises(NodeExecutionError, match="TransactionScopeNode"):
        await node.async_run(data=[{"id": 1, "name": "A"}])

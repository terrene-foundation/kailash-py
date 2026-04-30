# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #714 — DDL connection thrash.

Origin
------

production incident (2026-04-29): pgbouncer in session mode
hit ``MaxClientsInSessionMode`` whenever ``DataFlow.create_tables_async()``
ran during FastAPI startup with multiple registered models.

Pre-fix path
~~~~~~~~~~~~

``DataFlow._execute_ddl`` / ``_execute_ddl_async`` constructed a fresh
``AsyncSQLDatabaseNode`` (and the matching ``WorkflowBuilder``) per DDL
statement. Even with ``share_pool=True`` reusing the asyncpg pool via
``_shared_pools``, each iteration paid the workflow build/teardown
overhead AND the operator had to size ``pool_size`` to handle DDL bursts.
With ``pool_size > pgbouncer_cap`` the cap was hit; the unrelated
async CRUD path then could not acquire its own clients and the
service deadlocked at lifespan boot.

Fix (this PR)
~~~~~~~~~~~~~

``_execute_ddl`` and ``_execute_ddl_async`` route the entire DDL batch
through ONE sync connection via
:meth:`SyncDDLExecutor.execute_ddl_batch_per_statement` (off the event
loop via :func:`asyncio.to_thread` for the async path). DDL is
single-connection work; the workflow runtime's pool plumbing is
unnecessary for it.

What this file pins
-------------------

These are Tier-2 regression tests against a real database adapter
(SQLite, no infrastructure required) that exercise the refactored
path. The pgbouncer-specific Tier-3 test exercises the upstream pool
cap behavior when an external pgbouncer container is available.

Per ``rules/orphan-detection.md`` § 1, the new wiring is exercised
through the framework facade (``db.create_tables`` / ``db.create_tables_async``)
rather than the manager class in isolation.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import tempfile
from pathlib import Path

import pytest

from dataflow import DataFlow

# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


def _strip_docstring_and_comments(src: str) -> str:
    """Return code lines only — no leading docstring, no ``#`` comments.

    The structural-invariant tests below look at the executable body only;
    a docstring narrating the historical AsyncSQLDatabaseNode path MUST NOT
    trip the assertion.
    """
    import ast
    import textwrap

    # ``inspect.getsource`` on a method returns it indented at the class
    # level; ``ast.parse`` rejects leading indentation.
    tree = ast.parse(textwrap.dedent(src))
    func = tree.body[0]
    body = getattr(func, "body", [])
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return ""
    return "\n".join(ast.unparse(node) for node in body)


def test_execute_ddl_does_not_import_async_sql_database_node():
    """The refactored sync DDL path MUST NOT route through AsyncSQLDatabaseNode.

    Pin the sync DDL implementation against the pre-fix shape: if a
    future refactor reintroduces AsyncSQLDatabaseNode in the
    ``_execute_ddl`` body, this test fails immediately and forces a
    re-audit before #714 regresses.
    """
    from dataflow.core import engine

    src = inspect.getsource(engine.DataFlow._execute_ddl)
    body = _strip_docstring_and_comments(src)
    assert "AsyncSQLDatabaseNode" not in body, (
        "_execute_ddl re-imported AsyncSQLDatabaseNode — issue #714 regression. "
        "DDL is single-connection work; route via SyncDDLExecutor."
    )
    assert "execute_ddl_batch_per_statement" in body, (
        "_execute_ddl no longer calls execute_ddl_batch_per_statement — "
        "the single-connection contract from #714 has drifted."
    )


def test_execute_ddl_async_does_not_import_async_sql_database_node():
    """The refactored async DDL path MUST NOT route through AsyncSQLDatabaseNode."""
    from dataflow.core import engine

    src = inspect.getsource(engine.DataFlow._execute_ddl_async)
    body = _strip_docstring_and_comments(src)
    assert "AsyncSQLDatabaseNode" not in body, (
        "_execute_ddl_async re-imported AsyncSQLDatabaseNode — "
        "issue #714 regression. DDL is single-connection work; "
        "route via SyncDDLExecutor + asyncio.to_thread."
    )
    assert "execute_ddl_batch_per_statement" in body, (
        "_execute_ddl_async no longer calls execute_ddl_batch_per_statement — "
        "the single-connection contract from #714 has drifted."
    )
    assert "asyncio.to_thread" in body, (
        "_execute_ddl_async no longer offloads the sync DDL batch to a thread — "
        "calling SyncDDLExecutor inline blocks the event loop."
    )


def test_execute_ddl_batch_per_statement_uses_one_connection_per_call():
    """SyncDDLExecutor.execute_ddl_batch_per_statement opens exactly one connection.

    Counts ``_get_sync_connection`` calls during a 5-statement batch.
    The pre-fix path opened 5 connections (one per AsyncSQLDatabaseNode);
    the post-fix path opens 1.
    """
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    executor = SyncDDLExecutor(f"sqlite:///{db_path}")
    call_count = 0
    real_get = executor._get_sync_connection

    def _counting_get():
        nonlocal call_count
        call_count += 1
        return real_get()

    executor._get_sync_connection = _counting_get  # type: ignore[method-assign]

    statements = [
        f"CREATE TABLE IF NOT EXISTS issue_714_t{i} (id INTEGER PRIMARY KEY)"
        for i in range(5)
    ]
    results = executor.execute_ddl_batch_per_statement(statements)

    assert all(
        r["success"] for r in results
    ), f"sample failure: {[r for r in results if not r.get('success')][:1]}"
    assert call_count == 1, (
        f"execute_ddl_batch_per_statement opened {call_count} connections for "
        f"5 statements — single-connection contract violated. "
        f"Per-iteration AsyncSQLDatabaseNode-style dispatch reintroduced?"
    )


# ---------------------------------------------------------------------------
# End-to-end via DataFlow facade
# ---------------------------------------------------------------------------


def _new_sqlite_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return Path(f.name)


@pytest.mark.regression
def test_create_tables_sync_completes_for_many_models():
    """``db.create_tables()`` runs all DDL through one sync connection.

    Per the orphan-detection rule we exercise the facade, not the
    SyncDDLExecutor in isolation: this proves DataFlow actually calls
    the refactored path on the production hot path.
    """
    db_path = _new_sqlite_db()
    db = DataFlow(f"sqlite:///{db_path}")

    @db.model
    class IssueA:  # noqa: D401
        title: str

    @db.model
    class IssueB:
        title: str

    @db.model
    class IssueC:
        title: str

    db.create_tables()

    # Fresh sync connection per executor call → query the file directly to
    # confirm the DDL landed.
    import sqlite3

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    table_names = {r[0] for r in rows}
    expected = {"issue_as", "issue_bs", "issue_cs"}
    assert expected.issubset(
        table_names
    ), f"expected tables {expected}, got {table_names}"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_create_tables_async_completes_for_many_models():
    """``await db.create_tables_async()`` runs DDL via ``asyncio.to_thread``.

    Repro of the downstream-consumer pattern: many models registered, async
    startup, single-connection DDL.
    """
    db_path = _new_sqlite_db()
    db = DataFlow(f"sqlite:///{db_path}")

    @db.model
    class StartupA:
        name: str

    @db.model
    class StartupB:
        name: str

    @db.model
    class StartupC:
        name: str

    @db.model
    class StartupD:
        name: str

    @db.model
    class StartupE:
        name: str

    await db.create_tables_async()

    import sqlite3

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    conn.close()
    table_names = {r[0] for r in rows}
    expected = {"startup_as", "startup_bs", "startup_cs", "startup_ds", "startup_es"}
    assert expected.issubset(
        table_names
    ), f"expected tables {expected}, got {table_names}"


@pytest.mark.regression
def test_create_tables_does_not_acquire_async_pool():
    """Pre-fix path created an asyncpg/AsyncSQLDatabaseNode pool per DDL.

    Post-fix MUST NOT acquire any AsyncSQL pool during DDL — confirmed
    by snapshot ``AsyncSQLDatabaseNode._shared_pools`` before/after.
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    pools_before = dict(getattr(AsyncSQLDatabaseNode, "_shared_pools", {}))

    db_path = _new_sqlite_db()
    db = DataFlow(f"sqlite:///{db_path}")

    @db.model
    class PoolProbe:
        name: str

    db.create_tables()

    pools_after = dict(getattr(AsyncSQLDatabaseNode, "_shared_pools", {}))

    new_pools = set(pools_after) - set(pools_before)
    assert not new_pools, (
        "DataFlow.create_tables() acquired AsyncSQLDatabaseNode pools: "
        f"{new_pools}. Issue #714 fix routes DDL via SyncDDLExecutor only; "
        "no async pool should be touched on the DDL path."
    )


@pytest.mark.regression
def test_fail_fast_circuit_breaker_preserved_through_refactor():
    """Issue #696 fail-fast invariant survives the #714 refactor.

    Force a CREATE TABLE failure via deliberate SQL syntax error
    (empty column list). SQLite raises a syntax error whose message
    does NOT contain "already exists" — the executor's idempotent
    no-op tolerance branch is bypassed, and the per-statement loop
    routes the failure into the #696 circuit-breaker.
    """
    from dataflow.core.engine import DataFlow as _DF
    from dataflow.core.exceptions import DataFlowError

    db_path = _new_sqlite_db()
    db = _DF(f"sqlite:///{db_path}")

    # Empty column list is rejected by every dialect; pin against the
    # behavior of the refactored single-connection batch executor.
    bad_sql = {
        "tables": ["CREATE TABLE bad_things ()"],
        "indexes": [],
        "foreign_keys": [],
    }

    extracted = db._extract_table_from_statement(bad_sql["tables"][0])
    assert extracted is not None and re.search(
        r"(?i)bad_things", extracted
    ), f"extractor returned {extracted!r}; test would no-op without it"

    with pytest.raises(DataFlowError):
        db._execute_ddl(bad_sql)

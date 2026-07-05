# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1564 — DataFlow node CRUD silently ran with an
EMPTY physical-column list, so ``updated_at`` was never bumped on PostgreSQL /
SQLite and SELECT column lists degraded to model fields.

Root cause (ground-truth verified, not hypothesis):

Every DataFlow node's CRUD SQL generation runs inside ``async def async_run``
(``dataflow/core/nodes.py``); the sync ``run()`` is a thin
``async_safe_run(self.async_run(...))`` wrapper, so ALL execution is inside a
running event loop. The five column-detection sites called the SYNC
``DataFlow._get_table_columns`` → ``discover_schema(use_real_inspection=True)``,
which raises ``"cannot be called from a running async context"`` inside any
event loop and returns ``[]``. Net effect: ``actual_columns`` was ALWAYS empty
and ``has_updated_at`` ALWAYS False, so the UPDATE/UPSERT SET clause never
included ``updated_at = CURRENT_TIMESTAMP`` (masked on MySQL by
``ON UPDATE CURRENT_TIMESTAMP``, but real on PostgreSQL & SQLite), and SELECT
column lists dropped ``created_at`` / ``updated_at``.

The fix wires async column resolution (``_resolve_table_columns_async``):
  * managed schema (``auto_migrate`` and not ``existing_schema_mode``): derives
    the column set from in-memory model metadata at ZERO DB cost —
    ``_generate_create_table_sql`` unconditionally appends both timestamps;
  * existing-schema / non-auto-migrate: cached async catalog introspection.

These tests exercise the node path END-TO-END (``WorkflowBuilder`` +
``AsyncLocalRuntime``, real SQLite + real PostgreSQL, NO mocking) and assert the
user-visible outcome via read-back. The ``updated_at``-bump tests FAIL on main
(``updated_at == created_at``) and pass with the fix.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import sqlite3
import tempfile
import time

import pytest
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


# ---------------------------------------------------------------------------
# Result-shape helpers (DataFlow node results wrap the row/list in "result").
# ---------------------------------------------------------------------------
def _rec(r):
    return r.get("result", r) if isinstance(r, dict) else r


def _rows(listed):
    listed = _rec(listed)
    if isinstance(listed, list):
        return listed
    if isinstance(listed, dict):
        for k in ("result", "data", "records", "rows"):
            if isinstance(listed.get(k), list):
                return listed[k]
    return listed


async def _create(rt, model, fields):
    wf = WorkflowBuilder()
    wf.add_node(f"{model}CreateNode", "c", fields)
    await rt.execute_workflow_async(wf.build(), inputs={})


async def _list(rt, model, flt=None):
    wf = WorkflowBuilder()
    wf.add_node(f"{model}ListNode", "l", {"filter": flt} if flt else {})
    r, _ = await rt.execute_workflow_async(wf.build(), inputs={})
    return _rows(r["l"])


async def _update(rt, model, rid, fields):
    wf = WorkflowBuilder()
    wf.add_node(f"{model}UpdateNode", "u", {"filter": {"id": rid}, "fields": fields})
    await rt.execute_workflow_async(wf.build(), inputs={})


async def _upsert(rt, model, where, update, create):
    wf = WorkflowBuilder()
    wf.add_node(
        f"{model}UpsertNode",
        "up",
        {"where": where, "update": update, "create": create},
    )
    r, _ = await rt.execute_workflow_async(wf.build(), inputs={})
    return _rec(r["up"])


@pytest.fixture
def sqlite_url():
    d = tempfile.mkdtemp()
    yield f"sqlite:///{d}/t.db", f"{d}/t.db"


# ---------------------------------------------------------------------------
# AC1 (SQLite) — node UPDATE bumps updated_at. Core bug; RED on main.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.asyncio
async def test_node_update_bumps_updated_at_sqlite(sqlite_url):
    url, _ = sqlite_url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class DocU1564:
        title: str

    await db.initialize()
    rt = AsyncLocalRuntime()

    await _create(rt, "DocU1564", {"title": "orig"})
    row0 = (await _list(rt, "DocU1564"))[0]
    rid = row0["id"]

    time.sleep(1.2)  # SQLite CURRENT_TIMESTAMP has 1-second resolution
    await _update(rt, "DocU1564", rid, {"title": "changed"})

    row1 = (await _list(rt, "DocU1564", {"id": rid}))[0]
    assert row1["title"] == "changed"  # write persisted (read-back)
    assert row1.get("created_at") and row1.get("updated_at")
    assert row1["updated_at"] > row1["created_at"], (
        "updated_at was NOT bumped on node UPDATE (issue #1564): "
        f"{row1['updated_at']!r} !> {row1['created_at']!r}"
    )


# ---------------------------------------------------------------------------
# AC2 (SQLite) — node UPSERT (UPDATE branch) bumps updated_at (site nodes.py:3407).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.asyncio
async def test_node_upsert_bumps_updated_at_sqlite(sqlite_url):
    url, _ = sqlite_url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class DocUp1564:
        slug: str
        title: str
        __dataflow__ = {"indexes": [{"fields": ["slug"], "unique": True}]}

    await db.initialize()
    rt = AsyncLocalRuntime()

    await _upsert(
        rt,
        "DocUp1564",
        {"slug": "s1"},
        {"title": "orig"},
        {"slug": "s1", "title": "orig"},
    )
    # CREATE branch (first upsert, no existing row) produced a COMPLETE row —
    # the async column resolution ran on the INSERT path too (LOW-2 coverage).
    created = (await _list(rt, "DocUp1564", {"slug": "s1"}))[0]
    assert created["title"] == "orig"
    assert created.get("created_at") and created.get("updated_at")

    time.sleep(1.2)
    await _upsert(
        rt,
        "DocUp1564",
        {"slug": "s1"},
        {"title": "changed"},
        {"slug": "s1", "title": "changed"},
    )

    row1 = (await _list(rt, "DocUp1564", {"slug": "s1"}))[0]
    assert row1["title"] == "changed"
    assert row1["updated_at"] > row1["created_at"], (
        "updated_at was NOT bumped on node UPSERT-UPDATE (issue #1564): "
        f"{row1['updated_at']!r} !> {row1['created_at']!r}"
    )


# ---------------------------------------------------------------------------
# AC3 (SQLite) — SELECT column list includes created_at + updated_at
# (async select-template sites nodes.py:2289/3105/3893).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.asyncio
async def test_node_list_select_includes_timestamps_sqlite(sqlite_url):
    url, _ = sqlite_url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class DocS1564:
        title: str

    await db.initialize()
    rt = AsyncLocalRuntime()

    await _create(rt, "DocS1564", {"title": "x"})
    row = (await _list(rt, "DocS1564"))[0]
    # Pre-fix the async select template dropped the timestamp columns.
    assert "created_at" in row and "updated_at" in row, (
        "SELECT column list dropped timestamp columns (issue #1564): "
        f"got keys {sorted(row.keys())}"
    )


# ---------------------------------------------------------------------------
# AC4 — the managed (auto_migrate) path resolves columns with ZERO DB I/O.
# Boundary-injection: patch discover_schema_async to raise; a full node
# UPDATE cycle MUST still succeed and bump updated_at, proving the managed
# branch never touches the catalog (the perf property of the fix).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.asyncio
async def test_managed_path_resolves_columns_with_zero_db_io(sqlite_url):
    url, _ = sqlite_url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class DocZ1564:
        title: str

    await db.initialize()

    async def _boom(*a, **k):
        raise AssertionError(
            "discover_schema_async MUST NOT run on the managed auto_migrate path"
        )

    db.discover_schema_async = _boom  # any introspection would raise loudly

    # Direct resolver assertion — derived, no catalog query.
    cols = await db._resolve_table_columns_async("DocZ1564")
    assert cols == ["id", "title", "created_at", "updated_at"]

    # End-to-end: the node UPDATE path still bumps updated_at without any
    # introspection round-trip.
    rt = AsyncLocalRuntime()
    await _create(rt, "DocZ1564", {"title": "orig"})
    rid = (await _list(rt, "DocZ1564"))[0]["id"]
    time.sleep(1.2)
    await _update(rt, "DocZ1564", rid, {"title": "changed"})
    row1 = (await _list(rt, "DocZ1564", {"id": rid}))[0]
    assert row1["title"] == "changed"
    assert row1["updated_at"] > row1["created_at"]


# ---------------------------------------------------------------------------
# AC5 — existing-schema branch uses cached async introspection and returns the
# REAL physical shape (a table lacking updated_at), populating _column_cache;
# clear_schema_cache evicts it.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.asyncio
async def test_existing_schema_branch_introspects_and_caches(sqlite_url):
    url, path = sqlite_url

    # Physical table created out-of-band with a CUSTOM name that differs from
    # the default pluralization ("LegacyDoc" -> "legacy_docs"), deliberately
    # WITHOUT updated_at — so the test actually exercises custom table-name
    # resolution in the introspection branch (MED-2).
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE legacy_archive (id INTEGER PRIMARY KEY, title TEXT, created_at TEXT)"
    )
    conn.commit()
    conn.close()

    db = DataFlow(url, auto_migrate=False, existing_schema_mode=True)

    @db.model
    class LegacyDoc:  # default plural "legacy_docs" != the real table name
        title: str
        __tablename__ = "legacy_archive"

    await db.initialize()

    cols = await db._resolve_table_columns_async("LegacyDoc")
    assert "title" in cols and "created_at" in cols, (
        "existing-schema introspection must resolve the CUSTOM table name "
        f"(legacy_archive, not the default legacy_docs) and read its real "
        f"columns; got {cols}"
    )
    assert "updated_at" not in cols, (
        "existing-schema introspection must report the REAL table shape "
        f"(no updated_at), got {cols}"
    )

    # The introspection result is cached under the custom table name.
    assert any(
        k.endswith(":legacy_archive") for k in db._column_cache
    ), db._column_cache

    # clear_schema_cache evicts the column cache.
    db.clear_schema_cache()
    assert db._column_cache == {}


# ---------------------------------------------------------------------------
# AC6 (PostgreSQL) — the primary production surface: node UPDATE bumps
# updated_at on real PostgreSQL (no ON UPDATE auto-bump masks it there).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_node_update_bumps_updated_at_postgresql():
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        url = suite.config.url
        # Fresh table.
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        drop = AsyncSQLDatabaseNode(
            connection_string=url,
            database_type="postgresql",
            query="DROP TABLE IF EXISTS docpg1564 CASCADE",
            validate_queries=False,
        )
        await drop.async_run()
        await drop.cleanup()

        db = DataFlow(url, auto_migrate=True)

        @db.model
        class DocPg1564:
            title: str

        await db.initialize()
        rt = AsyncLocalRuntime()

        await _create(rt, "DocPg1564", {"title": "orig"})
        row0 = (await _list(rt, "DocPg1564"))[0]
        rid = row0["id"]

        # PostgreSQL CURRENT_TIMESTAMP is microsecond-resolution; a separate
        # UPDATE transaction gets a strictly later value — no sleep needed.
        await _update(rt, "DocPg1564", rid, {"title": "changed"})

        row1 = (await _list(rt, "DocPg1564", {"id": rid}))[0]
        assert row1["title"] == "changed"
        assert str(row1["updated_at"]) > str(row1["created_at"]), (
            "updated_at was NOT bumped on node UPDATE on PostgreSQL (issue #1564): "
            f"{row1['updated_at']!r} !> {row1['created_at']!r}"
        )

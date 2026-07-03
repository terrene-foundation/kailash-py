# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1502 — bare ``:memory:`` multi-connection isolation.

Before #1502, a ``DataFlow(":memory:")`` instance handed every consumer a bare
``:memory:`` connection string. Each consumer (DDL executor, migration system,
Express CRUD node) independently opened its own SQLite connection, and every
anonymous ``:memory:`` connection gets a PRIVATE in-memory database — so DDL
created tables in one DB while CRUD read another ("no such table").

The fix computes ONE ``file:df_mem_<id>?mode=memory&cache=shared`` URI per
DataFlow instance, keeps a lifetime ANCHOR connection open so the shared-cache
DB survives between operations, and injects the URI at every
connection-construction site. ``config.database.url`` stays the literal
``:memory:`` so the dialect-detection branches are unaffected.

These are Tier-2 regression tests exercising REAL SQLite (no mocking).
"""

from __future__ import annotations

import gc
import sqlite3
import warnings

import pytest

from dataflow import DataFlow


@pytest.mark.regression
@pytest.mark.dataflow_lifecycle
def test_memory_anchor_closed_with_no_resource_warning():
    """R1: the anchor opens and closes cleanly — no ResourceWarning, anchor nulled.

    Marked ``dataflow_lifecycle`` so the regression-suite autouse close-fixture
    holds no strong reference and this test controls the instance's lifetime.

    A ``gc.collect()`` runs BEFORE the strict filter is armed to flush any
    unrelated garbage left by earlier tests (e.g. the model-registry SQLAlchemy
    engine pool — a Shard-2 concern, issue #1503), so this test isolates the
    behaviour of the #1502 anchor and nothing else. The instance is held
    referenced through the whole strict block, so its ``__del__`` cannot fire
    inside the window; the assertions prove the anchor was released by
    ``close()`` itself.
    """
    gc.collect()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)

        db = DataFlow(":memory:")
        # The anchor is opened eagerly in __init__ for a bare :memory: instance.
        assert db._memory_db_uri is not None
        assert db._memory_connection is not None

        db.close()

        # close() released and nulled the anchor (the finally block in teardown).
        assert db._memory_connection is None


@pytest.mark.regression
async def test_memory_shared_cache_ddl_and_crud_reach_same_db():
    """R2 (headline): DDL + Express CRUD land in the SAME shared in-memory DB.

    ``create_tables_async`` creates the table, ``express.create`` inserts a row,
    ``express.list`` reads it back, and a raw ``sqlite3`` connection over the
    same shared-cache URI sees the created table — proving every path reaches
    one DB.
    """
    db = DataFlow(":memory:")

    @db.model
    class User:
        name: str

    await db.create_tables_async()

    table_name = db._class_name_to_table_name("User")

    created = await db.express.create("User", {"name": "Alice"})
    assert created is not None

    rows = await db.express.list("User")
    assert any(row.get("name") == "Alice" for row in rows), rows

    # A fresh raw connection over the SAME shared-cache URI must see the table
    # the DDL path created — the definitive proof the DBs are shared, not
    # private-per-connection.
    assert db._memory_db_uri is not None
    raw = sqlite3.connect(db._memory_db_uri, uri=True)
    try:
        table_names = {
            r[0]
            for r in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        raw.close()

    assert table_name in table_names, table_names

    await db.close_async()


@pytest.mark.regression
async def test_two_memory_instances_are_isolated():
    """R6: two ``DataFlow(":memory:")`` instances do NOT share data.

    Each instance gets its own ``df_mem_<id>`` shared-cache DB, so a row created
    in instance A is invisible to instance B even for an identically-named model.
    """
    db_a = DataFlow(":memory:")
    db_b = DataFlow(":memory:")

    @db_a.model
    class Widget:
        name: str

    @db_b.model  # noqa: F811 — intentionally the same model name on a 2nd instance
    class Widget:  # type: ignore[no-redef]
        name: str

    await db_a.create_tables_async()
    await db_b.create_tables_async()

    await db_a.express.create("Widget", {"name": "only-in-a"})

    rows_b = await db_b.express.list("Widget")
    assert all(row.get("name") != "only-in-a" for row in rows_b), rows_b

    # Distinct per-instance URIs are the structural reason for the isolation.
    assert db_a._memory_db_uri != db_b._memory_db_uri

    await db_a.close_async()
    await db_b.close_async()


@pytest.mark.regression
def test_model_registry_sync_path_reaches_shared_memory_db():
    """R5 (Shard 2): the model-registry SYNC ``SQLDatabaseNode`` path round-trips.

    ``ModelRegistry.initialize()`` / ``register_model()`` / ``discover_models()``
    build core ``SQLDatabaseNode`` instances executed by the sync runtime in a
    THREAD-POOL offload. Two coupled #1502 bugs made this fail on a bare
    ``:memory:`` instance:

    1. ``SQLDatabaseNode`` used ``QueuePool`` with the default
       ``check_same_thread=True``, so the pooled connection created on the
       caller thread raised ``sqlite3.ProgrammingError: SQLite objects created
       in a thread can only be used in that same thread`` when the offload
       thread used it. (Shard-2 core fix: StaticPool + ``check_same_thread=False``
       for SQLite MEMORY connections.)
    2. The registry built its connection from a bare ``sqlite:///:memory:`` (via
       ``config.database.get_connection_url()``), landing in a DIFFERENT, empty
       in-memory DB → ``no such table: dataflow_model_registry``. (Shard-2 fix:
       route every registry ``SQLDatabaseNode`` through ``_memory_db_uri``.)

    This test drives the real sync path (no mocking) and asserts NEITHER failure
    mode fires AND the registered model round-trips back out of ``discover_models``.
    """
    db = DataFlow(":memory:")

    @db.model
    class Gadget:
        name: str

    registry = db._model_registry

    try:
        # initialize() creates dataflow_model_registry via the sync
        # SQLDatabaseNode thread-pool path (bug site #1) and flushes the
        # @db.model-queued Gadget into the registry table (bug site #2).
        assert registry.initialize() is True
        assert registry._initialized is True

        # discover_models() reads the registry back through the same sync path.
        discovered = registry.discover_models()
    except sqlite3.ProgrammingError as exc:  # pragma: no cover - regression guard
        pytest.fail(
            "issue #1502 regression: registry sync SQLDatabaseNode hit a "
            f"cross-thread SQLite error: {exc}"
        )
    except Exception as exc:  # pragma: no cover - regression guard
        # The pre-fix "no such table: dataflow_model_registry" surfaces here.
        assert "dataflow_model_registry" not in str(exc), (
            f"issue #1502 regression: registry table invisible to the sync "
            f"path (different in-memory DB): {exc}"
        )
        raise

    # The registry row round-tripped: the table was visible and the model
    # written on the caller thread is readable back through the offload path.
    assert isinstance(discovered, dict)
    assert "Gadget" in discovered, discovered

    # Definitive proof the sync path wrote into the SAME shared-cache DB the
    # anchor holds: a raw connection over the instance URI sees the registry table.
    assert db._memory_db_uri is not None
    raw = sqlite3.connect(db._memory_db_uri, uri=True)
    try:
        tables = {
            r[0]
            for r in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        raw.close()
    assert "dataflow_model_registry" in tables, tables

    db.close()


@pytest.mark.regression
def test_close_disposes_registry_pool_no_id_reuse_aliasing():
    """R7 (#1502 review): close() disposes the registry StaticPool for this URI.

    The registry sync path acquires a class-level ``SQLDatabaseNode._shared_pools``
    StaticPool keyed by this instance's ``file:df_mem_<id>?...`` URI. If close()
    left it open, the in-memory DB would leak AND — because CPython reuses freed
    ``id()`` addresses — a later ``DataFlow(":memory:")`` at the same address would
    compute the identical URI, hit the surviving pool, and alias this instance's
    data. Structural guard: after close(), no ``_shared_pools`` entry for the URI.
    """
    from kailash.nodes.data.sql import SQLDatabaseNode

    db = DataFlow(":memory:")
    uri = db._memory_db_uri
    assert uri is not None

    @db.model
    class Thing:
        id: str
        name: str

    # Drive the sync model-registry path so it acquires a StaticPool keyed by uri.
    db._model_registry.initialize()
    db._model_registry.discover_models()

    assert any(
        k[0] == uri for k in SQLDatabaseNode._shared_pools
    ), "registry StaticPool should exist for this instance's URI before close()"

    db.close()

    assert not any(
        k[0] == uri for k in SQLDatabaseNode._shared_pools
    ), "close() must dispose the registry StaticPool for this URI (id-reuse guard)"


@pytest.mark.regression
def test_secondary_ddl_connection_path_uses_shared_uri():
    """R8 (#1502 review): the ``_get_async_sql_connection`` fallback DDL/query path
    routes through the shared-cache URI, not a fresh bare ``:memory:``.

    This legacy/multi-statement-DDL path built its connection from
    ``config.database.url`` (bare ``:memory:``), which AsyncSQLDatabaseNode would
    rewrite to its OWN per-node ``file:kailash_<id(node)>`` DB — a different DB
    than CRUD/registry, reintroducing a scoped "no such table" for ALTER /
    multi-statement migrations on ``:memory:``.
    """
    db = DataFlow(":memory:")
    uri = db._memory_db_uri
    assert uri is not None
    try:
        conn = db._get_async_sql_connection()
        assert conn.connection_string == uri, (
            "secondary DDL path must use the shared-cache URI, "
            f"got {conn.connection_string!r} != {uri!r}"
        )
    finally:
        db.close()

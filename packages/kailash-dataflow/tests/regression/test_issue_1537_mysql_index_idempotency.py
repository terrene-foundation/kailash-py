# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #1537 (follow-up) — MySQL CREATE INDEX must be
idempotent across auto_migrate re-runs (app-restart scenario).

The #1537 fix dropped ``IF NOT EXISTS`` from every MySQL ``CREATE INDEX`` in
``engine._generate_indexes_sql`` because MySQL rejects ``IF NOT EXISTS`` on
``CREATE INDEX`` with a 1064 syntax error — so the UNIQUE index a single-record
upsert conflict target relies on was NEVER created before. That fix is correct,
but it introduced a NEW failure mode on re-migration: an application that starts
with ``auto_migrate=True`` against an ALREADY-migrated table re-issues the
``CREATE INDEX`` statements, and MySQL raises error 1061 "Duplicate key name".

The benign-error tolerance in the DDL execution paths only matched
``"already exists"`` (PostgreSQL / SQLite), NOT MySQL's ``"duplicate key name"``,
so every restart logged an ERROR + WARNINGs and thrashed the batch-DDL path into
per-model fallback (connection churn). Functionally the index existed and upsert
worked — but the noise violates ``rules/zero-tolerance.md`` Rule 1 (a warning is
an error) and ``rules/observability.md`` Rule 5 (WARN+-clean gate).

The canonical tolerance already existed in
``schema_state_manager.py`` (``"duplicate key name" in err or "already exists"``)
for the migration-history table's index; the follow-up mirrors it in every DDL
execution path that can see a MySQL ``CREATE INDEX`` 1061:

* ``sync_ddl_executor.execute_ddl`` / ``execute_ddl_batch`` (the ROOT log sites),
* ``engine._execute_ddl`` / ``_execute_ddl_async`` (per-statement batch),
* ``engine._create_tables_batch`` (the abort-on-first-error batch → the
  "Batch DDL failed at statement N ... Falling back to per-model" WARN),
* ``engine._create_table_sync`` index loop (the "Failed to create index" WARN),
* ``engine.create_tables_sync`` (standalone all-statements loop).

The 1061 tolerance is scoped to ``CREATE INDEX`` statements so a duplicate key
inside a ``CREATE TABLE`` definition — a genuine authoring bug — still surfaces.

This test migrates a model with a UNIQUE ``__dataflow__`` index TWICE without
dropping the table between (a FRESH ``DataFlow`` instance for the second
migration, so the in-memory schema cache is empty — the literal app-restart
condition), and asserts the second ``auto_migrate``:

1. does NOT raise, and
2. emits NO WARN+ log for the duplicate index (no ``ddl_execution_failed`` /
   ``ddl_batch_execution_failed_at_statement`` / "Duplicate key name" /
   "Failed to create index" / "Batch DDL failed at statement" at WARNING+),
3. and DOES take the benign already-present DEBUG path (positive proof the
   tolerance fired, not that the code path was simply skipped).

Permanent regression test — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import logging
import time

import pytest

from dataflow import DataFlow

# Real MySQL 8.0 on port 3307 (compose: db kailash_test, root/test_password).
MYSQL_URL = "mysql://root:test_password@localhost:3307/kailash_test"


async def _drop_table(table: str) -> None:
    """Drop the test table on real MySQL so each run starts clean / re-runnable."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=MYSQL_URL,
        database_type="mysql",
        query=f"DROP TABLE IF EXISTS {table}",
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


async def _table_exists(table: str) -> bool:
    """Return True iff *table* exists on real MySQL (behavioral proof, not a
    schema-cache read — the cache is exactly what the regression corrupts)."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=MYSQL_URL,
        database_type="mysql",
        query=f"SHOW TABLES LIKE '{table}'",
        validate_queries=False,
    )
    result = await node.async_run()
    await node.cleanup()
    data = result["result"]["data"] if isinstance(result, dict) else []
    return len(data) > 0


def _define_idem_model(db: DataFlow):
    """Register a fresh model class carrying a UNIQUE ``__dataflow__`` index on
    the given DataFlow instance.

    A NEW class object is created on each call (same ``__name__`` → same table
    name → same index name) so the two instances mirror a real app restart:
    the module is re-imported and the decorated class is re-created against a
    fresh DataFlow — NOT the same class object re-decorated.
    """

    @db.model
    class Issue1537IdemDoc:
        id: str
        email: str  # backed by the UNIQUE index below
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    return Issue1537IdemDoc


def _is_dup_index_warn_plus(rec: logging.LogRecord) -> bool:
    """True for a WARNING+ record that signals a duplicate-index DDL failure —
    the exact regression this test guards against."""
    if rec.levelno < logging.WARNING:
        return False
    combined = " ".join(
        [
            rec.getMessage().lower(),
            str(getattr(rec, "error", "")).lower(),
        ]
    )
    return (
        "duplicate key name" in combined
        or "ddl_execution_failed" in combined
        or "ddl_batch_execution_failed_at_statement" in combined
        or "failed to create index" in combined
        or "batch ddl failed at statement" in combined
    )


def _is_benign_already_present_debug(rec: logging.LogRecord) -> bool:
    """True for a DEBUG record proving the benign already-present tolerance
    fired on the re-migration (index already exists → swallowed)."""
    if rec.levelno != logging.DEBUG:
        return False
    combined = " ".join(
        [
            rec.getMessage().lower(),
            str(getattr(rec, "error", "")).lower(),
        ]
    )
    return "already_exist" in combined or "already exist" in combined


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_re_migration_unique_index_is_idempotent(caplog):
    """AC: a second ``auto_migrate`` against an existing MySQL table with a
    UNIQUE ``__dataflow__`` index does NOT raise and emits NO duplicate-index
    WARN+ — the app-restart idempotency the #1537 IF-NOT-EXISTS removal broke."""
    # --- First migration: clean CREATE TABLE + CREATE UNIQUE INDEX ---
    db1 = DataFlow(MYSQL_URL, auto_migrate=True)
    _define_idem_model(db1)
    table = db1._models["Issue1537IdemDoc"]["table_name"]
    await _drop_table(table)

    try:
        db1._ensure_connected()  # runs _create_tables_batch → table + unique idx
        db1.close()

        # --- Second migration: FRESH instance (empty schema cache = restart) ---
        # The benign already-present path logs at DEBUG on the DDL loggers, which
        # the SDK floors above DEBUG. Lower the SPECIFIC child loggers (setting
        # the "dataflow" parent alone does not lower children that carry their
        # own level) so the benign DEBUG line is emitted and captured; caplog
        # auto-restores the levels at test end.
        caplog.clear()
        caplog.set_level(logging.DEBUG, logger="dataflow.core.engine")
        caplog.set_level(logging.DEBUG, logger="dataflow.migrations.sync_ddl_executor")
        db2 = DataFlow(MYSQL_URL, auto_migrate=True)
        _define_idem_model(db2)
        # MUST NOT raise: the re-issued CREATE UNIQUE INDEX 1061 is benign.
        db2._ensure_connected()
        db2.close()

        # (1) No duplicate-index WARN+ on the second migration.
        offenders = [r for r in caplog.records if _is_dup_index_warn_plus(r)]
        assert offenders == [], [
            (r.levelname, r.name, r.getMessage(), getattr(r, "error", None))
            for r in offenders
        ]

        # (2) Positive proof the benign already-present tolerance actually fired
        # (the 1061 was swallowed at DEBUG, not merely skipped).
        benign = [r for r in caplog.records if _is_benign_already_present_debug(r)]
        assert benign, (
            "expected a benign already-present DEBUG log on the second migration; "
            "captured DEBUG events: "
            + str(
                [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
            )
        )
    finally:
        await _drop_table(table)


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_re_migration_upsert_still_works_after_restart(caplog):
    """AC (no-regression): after the second (WARN-clean) migration, the UNIQUE
    index still backs a single-record upsert conflict target end-to-end — the
    index really exists, not merely 'error swallowed'."""
    db1 = DataFlow(MYSQL_URL, auto_migrate=True)
    _define_idem_model(db1)
    table = db1._models["Issue1537IdemDoc"]["table_name"]
    await _drop_table(table)

    try:
        db1._ensure_connected()
        db1.close()

        db2 = DataFlow(MYSQL_URL, auto_migrate=True)
        _define_idem_model(db2)
        db2._ensure_connected()

        email = f"restart-{int(time.time() * 1_000_000)}@example.com"
        # First upsert on the UNIQUE email → INSERT.
        await db2.express.upsert_advanced(
            "Issue1537IdemDoc",
            where={"email": email},
            create={"id": "u1", "email": email, "name": "First"},
            update={"name": "First"},
            conflict_on=["email"],
        )
        # Second upsert on the same email → UPDATE in place (index-backed), no dup.
        await db2.express.upsert_advanced(
            "Issue1537IdemDoc",
            where={"email": email},
            create={"id": "u2", "email": email, "name": "Second"},
            update={"name": "Second"},
            conflict_on=["email"],
        )
        assert await db2.express.count("Issue1537IdemDoc", {"email": email}) == 1
        db2.close()
    finally:
        await _drop_table(table)


def _define_batch_model_a(db: DataFlow):
    """Model A: carries a UNIQUE ``__dataflow__`` index (the 1061 source on
    re-migration). Registered FIRST so its CREATE INDEX is ordered BEFORE B's
    CREATE TABLE in the single batch — the exact interleaving that made the
    abort-on-first-error ``execute_ddl_batch`` mask B."""

    @db.model
    class Issue1537BatchA:
        id: str
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    return Issue1537BatchA


def _define_batch_model_b(db: DataFlow):
    """Model B: a NEW model added at the SECOND migration (app restart + new
    model). Its CREATE TABLE is ordered AFTER A's CREATE INDEX in the batch, so
    the round-1 abort-on-first-error path never created it yet cached it as
    ensured — the HIGH regression this test locks closed."""

    @db.model
    class Issue1537BatchB:
        id: str
        title: str

    return Issue1537BatchB


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_batch_re_migration_creates_new_model_after_existing_index(
    caplog,
):
    """AC (HIGH regression, issue #1537 round-2): a re-migration batch where an
    EXISTING model A (with a UNIQUE index) is interleaved with a NEW model B must
    still CREATE B's table.

    Verbatim repro the round-1 abort-on-first-error path produced:
        migration 2 (restart + new model B): A exists=True, B exists=False  ← B MASKED

    Expected after the per-statement fix:
        migration 2 (restart + new model B): A exists=True, B exists=True

    Asserts (a) B's table EXISTS on real MySQL after the 2nd migration, (b) A's
    index 1061 produced NO WARN+ (caplog), (c) an insert on B succeeds.
    """
    # --- Migration 1: ONLY model A exists (B not defined yet) ---
    db1 = DataFlow(MYSQL_URL, auto_migrate=True)
    _define_batch_model_a(db1)
    table_a = db1._models["Issue1537BatchA"]["table_name"]
    await _drop_table(table_a)

    # Determine B's table name via a throwaway registration so we can pre-drop it.
    db_probe = DataFlow(MYSQL_URL, auto_migrate=False)
    _define_batch_model_b(db_probe)
    table_b = db_probe._models["Issue1537BatchB"]["table_name"]
    db_probe.close()
    await _drop_table(table_b)

    try:
        db1._ensure_connected()  # creates A + unique index only
        db1.close()

        assert await _table_exists(table_a) is True, "migration 1 must create A"
        assert (
            await _table_exists(table_b) is False
        ), "B must NOT exist before migration 2 (it is the newly-added model)"

        # --- Migration 2: FRESH instance (restart) registering A AND new B ---
        caplog.clear()
        caplog.set_level(logging.DEBUG, logger="dataflow.core.engine")
        caplog.set_level(logging.DEBUG, logger="dataflow.migrations.sync_ddl_executor")
        db2 = DataFlow(MYSQL_URL, auto_migrate=True)
        _define_batch_model_a(db2)  # registered FIRST → CREATE INDEX A precedes B
        _define_batch_model_b(db2)  # NEW model → CREATE TABLE B ordered AFTER
        db2._ensure_connected()  # single batch: [CREATE TABLE A, CREATE INDEX A(1061), CREATE TABLE B]

        # (a) B's table EXISTS — the regression is CLOSED (was False when masked).
        assert (
            await _table_exists(table_b) is True
        ), "REGRESSION: new model B's table was masked by A's benign index 1061"
        assert await _table_exists(table_a) is True

        # (b) A's re-run unique index 1061 produced NO duplicate-index WARN+.
        offenders = [r for r in caplog.records if _is_dup_index_warn_plus(r)]
        assert offenders == [], [
            (r.levelname, r.name, r.getMessage(), getattr(r, "error", None))
            for r in offenders
        ]

        # (c) CRUD on B works end-to-end (the table really exists, not just cached).
        await db2.express.create("Issue1537BatchB", {"id": "b1", "title": "hello"})
        assert await db2.express.count("Issue1537BatchB", {"id": "b1"}) == 1
        db2.close()
    finally:
        await _drop_table(table_a)
        await _drop_table(table_b)

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1520 — PostgreSQL single-record upsert with
``conflict_on`` on a field that has no backing PRIMARY KEY / UNIQUE constraint.

Before #1520, a single-record upsert (``db.express.upsert`` / the generated
``{Model}UpsertNode``) with ``conflict_on=["field"]`` where ``field`` is not
unique surfaced the raw PostgreSQL driver message::

    Database query failed: there is no unique or exclusion constraint matching
    the ON CONFLICT specification

The message never named ``conflict_on``, the offending field, or the remedy.

Why PG differs from the SQLite fix (#1508): SQLite's single-record upsert path
emits a WHERE-precheck INSERT/UPDATE (no ``ON CONFLICT``) and therefore never
reaches this error. PostgreSQL's ``ON CONFLICT`` is atomic and genuinely
requires the unique constraint — emulating via pre-check+branch would introduce
a TOCTOU race under PG concurrency. So PG correctly keeps ``ON CONFLICT``; the
fix converts the opaque driver error into the actionable typed
:class:`UpsertConflictTargetError` (naming the field + the two remedies),
mirroring the bulk path's :class:`BulkUpsertConflictTargetError` (#1519). No
runtime DDL — auto-creating the index is BLOCKED per ``schema-migration.md``
Rule 1 and would fail on existing duplicate data.

The single-record catch lives at the native-ON-CONFLICT execute site in
``dataflow/core/nodes.py``; the shared classifier is
``exceptions.is_conflict_target_error`` (also used by #1519's bulk path).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import time

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import (
    BulkUpsertConflictTargetError,
    UpsertConflictTargetError,
    is_conflict_target_error,
)


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


# ---------------------------------------------------------------------------
# Tier-2: PostgreSQL — the live #1520 path (real PG on port 5434)
# ---------------------------------------------------------------------------
@pytest.fixture
async def pg_suite():
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


async def _drop_table(url, table):
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=url,
        database_type="postgresql",
        query=f"DROP TABLE IF EXISTS {table} CASCADE",
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


@pytest.mark.regression
@pytest.mark.integration
async def test_pg_single_upsert_non_unique_conflict_target_raises(pg_suite):
    """AC1: PostgreSQL single-record ``db.express.upsert`` with ``conflict_on``
    on a non-unique field raises the typed :class:`UpsertConflictTargetError`
    (naming the field + remedy), NOT the raw driver message — and no row lands
    (ON CONFLICT is atomic; the statement aborts wholesale)."""
    url = pg_suite.config.url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1520PgNonuniq:
        tag: str  # deliberately NOT unique — the bug's precondition
        body: str

    table = db._models["Issue1520PgNonuniq"]["table_name"]
    await _drop_table(url, table)
    db._ensure_connected()

    try:
        with pytest.raises(UpsertConflictTargetError) as excinfo:
            await db.express.upsert(
                "Issue1520PgNonuniq",
                {"tag": "t", "body": "one"},
                conflict_on=["tag"],
            )

        # The typed error names conflict_on + the field + the remedy, and does
        # NOT leak the raw driver text.
        msg = str(excinfo.value)
        assert "tag" in msg
        assert "unique" in msg.lower()
        assert "unique=True" in msg or "UNIQUE index" in msg
        assert "no unique or exclusion constraint" not in msg.lower()
        assert excinfo.value.conflict_on == ["tag"]
        assert excinfo.value.model_name == "Issue1520PgNonuniq"

        # No row landed on the raise (atomic ON CONFLICT statement aborted).
        assert await db.express.count("Issue1520PgNonuniq") == 0
    finally:
        await _drop_table(url, table)
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_pg_single_upsert_unique_conflict_target_still_works(pg_suite):
    """AC2 (no-regression): PostgreSQL single-record upsert on a UNIQUE
    ``conflict_on`` field still works end-to-end (INSERT then UPDATE) — the new
    guard must NOT break the happy path."""
    url = pg_suite.config.url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1520PgUniq:
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    table = db._models["Issue1520PgUniq"]["table_name"]
    await _drop_table(url, table)
    db._ensure_connected()

    email = f"{_uid('alice')}@example.com"
    try:
        # First upsert → INSERT (email absent). The return is the executed
        # statement's RETURNING row (ground truth of what the SQL did).
        r1 = await db.express.upsert(
            "Issue1520PgUniq",
            {"email": email, "name": "Alice New"},
            conflict_on=["email"],
        )
        assert r1["name"] == "Alice New"
        original_id = r1["id"]

        # Second upsert on the same email → UPDATE (row present), same id.
        r2 = await db.express.upsert(
            "Issue1520PgUniq",
            {"email": email, "name": "Alice Updated"},
            conflict_on=["email"],
        )
        assert r2["name"] == "Alice Updated"
        assert r2["id"] == original_id  # UPDATE in place, NOT a second INSERT

        # Ground-truth read-back on a fresh pooled connection (real infra,
        # committed state) — exactly one row carrying the UPDATE payload. This
        # asserts persistence independent of the express read-cache layer.
        async with pg_suite.get_connection() as conn:
            db_rows = await conn.fetch(
                f"SELECT id, name FROM {table} WHERE email = $1", email
            )
        assert len(db_rows) == 1, db_rows
        assert db_rows[0]["name"] == "Alice Updated"
        assert db_rows[0]["id"] == original_id
    finally:
        await _drop_table(url, table)
        db.close()


# ---------------------------------------------------------------------------
# Tier-2: cross-dialect divergence pin — SQLite single-record upsert on a
# non-unique conflict_on field does NOT raise (uses the #1508 WHERE-precheck).
# Locks the guard as PG-path-only; a refactor that routed SQLite through
# ON CONFLICT (regressing #1508) would flip this test.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.asyncio
async def test_sqlite_single_upsert_non_unique_conflict_target_does_not_raise(tmp_path):
    """SQLite's single-record upsert on a non-unique conflict_on field upserts
    via the #1508 precheck (INSERT then UPDATE) — it MUST NOT raise
    :class:`UpsertConflictTargetError`; that error is PG-path-specific."""
    db = DataFlow(f"sqlite:///{tmp_path / 'issue_1520_sqlite.db'}", auto_migrate=True)

    @db.model
    class Note:
        id: str
        tag: str  # NOT unique
        body: str

    db._ensure_connected()
    tag = _uid("tag")
    nid = _uid("note")

    # INSERT then UPDATE on a non-unique conflict target — no raise on SQLite.
    await db.express.upsert(
        "Note", {"id": nid, "tag": tag, "body": "one"}, conflict_on=["tag"]
    )
    await db.express.upsert(
        "Note", {"id": nid, "tag": tag, "body": "two"}, conflict_on=["tag"]
    )

    rows = await db.express.list("Note", {"tag": tag})
    assert len(rows) == 1
    assert rows[0]["body"] == "two"
    db.close()


# ---------------------------------------------------------------------------
# Tier-1: structural pins on the typed error + shared classifier (no DB)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_upsert_conflict_target_error_message_is_actionable():
    """The typed error names conflict_on, the offending field(s), and the
    remedy — and never echoes the opaque driver text."""
    e = UpsertConflictTargetError(conflict_on=["tag"], model_name="Note")
    msg = str(e)
    assert "conflict_on" in msg
    assert "tag" in msg
    assert "unique=True" in msg  # the actionable remedy
    assert "PostgreSQL" in msg
    # Never surface the raw driver message the fix replaces.
    assert "no unique or exclusion constraint" not in msg.lower()
    # Structural: carries the caller's request for programmatic handling.
    assert e.conflict_on == ["tag"]
    assert e.model_name == "Note"


@pytest.mark.regression
def test_is_conflict_target_error_matches_pg_and_sqlite_messages():
    """The shared classifier (also used by #1519's bulk path) matches both the
    PostgreSQL and SQLite unmatched-ON-CONFLICT driver messages, and rejects
    unrelated errors."""
    pg = (
        "Database query failed: there is no unique or exclusion constraint "
        "matching the ON CONFLICT specification"
    )
    sqlite = "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint"
    assert is_conflict_target_error(pg) is True
    assert is_conflict_target_error(sqlite) is True
    # An unrelated unique-violation on a DIFFERENT column must NOT be reclassified.
    assert (
        is_conflict_target_error(
            'duplicate key value violates unique constraint "users_email_key"'
        )
        is False
    )
    assert is_conflict_target_error("") is False


@pytest.mark.regression
def test_upsert_and_bulk_conflict_errors_are_distinct_types():
    """Single-record (#1520) and bulk (#1519) conflict-target errors are
    distinct types so callers can ``try/except`` one without catching the
    other — but both derive from DataFlowError."""
    from dataflow.core.exceptions import DataFlowError

    assert not issubclass(UpsertConflictTargetError, BulkUpsertConflictTargetError)
    assert not issubclass(BulkUpsertConflictTargetError, UpsertConflictTargetError)
    assert issubclass(UpsertConflictTargetError, DataFlowError)
    assert issubclass(BulkUpsertConflictTargetError, DataFlowError)

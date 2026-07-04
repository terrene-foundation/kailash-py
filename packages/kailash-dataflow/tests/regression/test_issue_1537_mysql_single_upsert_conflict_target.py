# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1537 — MySQL single-record upsert with
``conflict_on`` on a field that has no backing PRIMARY KEY / UNIQUE constraint.

Before #1537, a single-record MySQL upsert (``db.express.upsert`` /
``upsert_advanced`` / the generated ``{Model}UpsertNode``) with
``conflict_on=["field"]`` where ``field`` is not unique SILENTLY upserted on the
``id`` PK instead of the requested field. MySQL's ``INSERT ... ON DUPLICATE KEY
UPDATE`` has no explicit conflict target and auto-detects whichever
UNIQUE/PRIMARY key a row violates; DataFlow mandates an ``id`` PK and generates a
fresh ``id`` on the create branch, so no key was violated → a plain INSERT
landed a DUPLICATE row and ``conflict_on`` was ignored. No error was raised —
the failure mode was a silent-wrong-result.

Why MySQL differs from the PostgreSQL fix (#1520): PostgreSQL's ``ON CONFLICT``
raises the opaque driver message "there is no unique or exclusion constraint
matching the ON CONFLICT specification" when the target is non-unique, which
DataFlow catches REACTIVELY and converts to
:class:`UpsertConflictTargetError`. MySQL produces NO error, so there is nothing
to catch. The MySQL fix is a PROACTIVE ``information_schema.statistics`` precheck
that verifies a UNIQUE/PRIMARY index whose column set is exactly
``set(conflict_on)`` backs the target BEFORE the upsert executes; if absent it
raises the same typed :class:`UpsertConflictTargetError` (naming the field +
remedy). No runtime DDL — auto-creating the index is BLOCKED per
``schema-migration.md`` Rule 1 and would fail on existing duplicate data.

The precheck lives at the single-record upsert execute site in
``dataflow/core/nodes.py`` (the one chokepoint every express.upsert /
upsert_advanced / sync variant / {Model}UpsertNode call funnels through),
alongside the SQLite WHERE-precheck (#1508) and the PostgreSQL reactive catch
(#1520).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import time

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import (
    BulkUpsertConflictTargetError,
    UpsertConflictTargetError,
)

# Real MySQL 8.0 on port 3307 (compose: db kailash_test, root/test_password).
# DataFlow connection strings use the ``mysql://`` scheme.
MYSQL_URL = "mysql://root:test_password@localhost:3307/kailash_test"


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


async def _drop_table(table: str) -> None:
    """Drop the test table on real MySQL so each run starts clean.

    The #1520 suite learned that persistent duplicate data from a prior run
    breaks re-runs; drop-first + auto_migrate re-creates a clean schema.
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=MYSQL_URL,
        database_type="mysql",
        query=f"DROP TABLE IF EXISTS {table}",
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


async def _raw_rows(table: str, where_col: str, where_val: str) -> list:
    """Ground-truth read-back on a fresh MySQL connection (committed state),
    independent of the express read-cache layer."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=MYSQL_URL,
        database_type="mysql",
        query=f"SELECT * FROM {table} WHERE {where_col} = %s",
        validate_queries=False,
    )
    result = await node.async_run(params=[where_val], fetch_mode="all")
    await node.cleanup()
    rows = result.get("result", {}).get("data", []) if result else []
    return rows if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# Tier-2: MySQL — the live #1537 error path (real MySQL on port 3307)
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_single_upsert_non_unique_conflict_target_raises():
    """AC1: MySQL single-record ``db.express.upsert`` with ``conflict_on`` on a
    NON-unique field raises the typed :class:`UpsertConflictTargetError` (naming
    the field + remedy) instead of silently landing a duplicate row on the id PK.
    No row lands — the proactive precheck aborts BEFORE the INSERT executes."""
    db = DataFlow(MYSQL_URL, auto_migrate=True)

    @db.model
    class Issue1537MyNonuniq:
        id: str
        tag: str  # deliberately NOT unique — the bug's precondition
        body: str

    table = db._models["Issue1537MyNonuniq"]["table_name"]
    await _drop_table(table)
    db._ensure_connected()

    try:
        with pytest.raises(UpsertConflictTargetError) as excinfo:
            await db.express.upsert(
                "Issue1537MyNonuniq",
                {"id": _uid("row"), "tag": "t", "body": "one"},
                conflict_on=["tag"],
            )

        # The typed error names conflict_on + the field + the remedy.
        msg = str(excinfo.value)
        assert "tag" in msg
        assert "unique" in msg.lower()
        assert "unique=True" in msg
        assert excinfo.value.conflict_on == ["tag"]
        assert excinfo.value.model_name == "Issue1537MyNonuniq"

        # No row landed on the raise (precheck aborted before INSERT).
        assert await db.express.count("Issue1537MyNonuniq") == 0
    finally:
        await _drop_table(table)
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_single_upsert_non_unique_no_duplicate_on_repeat():
    """AC1b (the silent-wrong-result core): repeating a non-unique-conflict_on
    upsert must NOT accumulate duplicate rows. Pre-fix, each call landed a fresh
    id-PK INSERT (2 calls → 2 rows). Post-fix, each call raises and zero rows
    land — proven by a ground-truth read-back on a fresh connection."""
    db = DataFlow(MYSQL_URL, auto_migrate=True)

    @db.model
    class Issue1537MyDup:
        id: str
        tag: str  # NOT unique
        body: str

    table = db._models["Issue1537MyDup"]["table_name"]
    await _drop_table(table)
    db._ensure_connected()

    tag = _uid("tag")
    try:
        for body in ("one", "two"):
            with pytest.raises(UpsertConflictTargetError):
                await db.express.upsert(
                    "Issue1537MyDup",
                    {"id": _uid("row"), "tag": tag, "body": body},
                    conflict_on=["tag"],
                )

        # Ground-truth: zero rows for this tag on real MySQL (no silent dups).
        rows = await _raw_rows(table, "tag", tag)
        assert rows == [], rows
        assert await db.express.count("Issue1537MyDup") == 0
    finally:
        await _drop_table(table)
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_single_upsert_unique_conflict_target_still_works():
    """AC2 (no-regression): MySQL single-record upsert on a DECLARED-UNIQUE
    ``conflict_on`` field still works end-to-end — INSERT then UPDATE IN PLACE,
    no duplicate row. The new precheck must NOT break the happy path."""
    db = DataFlow(MYSQL_URL, auto_migrate=True)

    @db.model
    class Issue1537MyUniq:
        id: str
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    table = db._models["Issue1537MyUniq"]["table_name"]
    await _drop_table(table)
    db._ensure_connected()

    email = f"{_uid('alice')}@example.com"
    try:
        # First upsert → INSERT (email absent).
        await db.express.upsert_advanced(
            "Issue1537MyUniq",
            where={"email": email},
            create={"id": _uid("u"), "email": email, "name": "Alice New"},
            update={"name": "Alice New"},
            conflict_on=["email"],
        )
        # Ground-truth read-back on a fresh MySQL connection (committed state),
        # independent of the express read-cache — exactly one row after INSERT.
        r1 = await _raw_rows(table, "email", email)
        assert len(r1) == 1, r1
        assert r1[0]["name"] == "Alice New"
        original_id = r1[0]["id"]

        # Second upsert on the same email → UPDATE in place, same id, no dup.
        await db.express.upsert_advanced(
            "Issue1537MyUniq",
            where={"email": email},
            create={"id": _uid("u2"), "email": email, "name": "Alice Updated"},
            update={"name": "Alice Updated"},
            conflict_on=["email"],
        )

        # Ground-truth read-back: still exactly one row (ON DUPLICATE KEY UPDATE
        # matched the UNIQUE email index — no second INSERT), same id, carrying
        # the UPDATE payload. Asserts the happy path did NOT regress.
        rows = await _raw_rows(table, "email", email)
        assert len(rows) == 1, rows
        assert rows[0]["id"] == original_id
        assert rows[0]["name"] == "Alice Updated"
    finally:
        await _drop_table(table)
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_single_upsert_on_id_pk_still_works():
    """AC3 (no-over-block): the default ``conflict_on`` — the ``id`` PRIMARY KEY —
    MUST still upsert. The precheck matches the PRIMARY index and proceeds; a
    conflict_on that IS a real key is never blocked."""
    db = DataFlow(MYSQL_URL, auto_migrate=True)

    @db.model
    class Issue1537MyPk:
        id: str
        name: str

    table = db._models["Issue1537MyPk"]["table_name"]
    await _drop_table(table)
    db._ensure_connected()

    rid = _uid("pk")
    try:
        # conflict_on defaults to the id PK (express.upsert uses ["id"]).
        await db.express.upsert("Issue1537MyPk", {"id": rid, "name": "First"})
        await db.express.upsert("Issue1537MyPk", {"id": rid, "name": "Second"})

        # Ground-truth: one row, updated in place on the PK conflict.
        rows = await _raw_rows(table, "id", rid)
        assert len(rows) == 1, rows
        assert await db.express.count("Issue1537MyPk") == 1
        fresh = await db.express.read("Issue1537MyPk", rid)
        assert fresh["name"] == "Second"
    finally:
        await _drop_table(table)
        db.close()


# ---------------------------------------------------------------------------
# Tier-1: structural pins on the typed error (no DB) — dialect-inclusive
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_upsert_conflict_target_error_actionable_for_mysql_field():
    """The typed error names conflict_on, the offending field, and the remedy —
    the SAME type PostgreSQL #1520 raises (single shared type for both dialects,
    so callers ``except UpsertConflictTargetError`` once)."""
    e = UpsertConflictTargetError(conflict_on=["tag"], model_name="Issue1537MyNonuniq")
    msg = str(e)
    assert "conflict_on" in msg
    assert "tag" in msg
    assert "unique=True" in msg  # the actionable remedy
    assert e.conflict_on == ["tag"]
    assert e.model_name == "Issue1537MyNonuniq"


@pytest.mark.regression
def test_upsert_conflict_target_error_type_identity():
    """#1537 (MySQL single-record) reuses the #1520 :class:`UpsertConflictTargetError`
    and stays distinct from the bulk (#1519) type so callers can catch one
    without the other — both derive from DataFlowError."""
    from dataflow.core.exceptions import DataFlowError

    assert not issubclass(UpsertConflictTargetError, BulkUpsertConflictTargetError)
    assert not issubclass(BulkUpsertConflictTargetError, UpsertConflictTargetError)
    assert issubclass(UpsertConflictTargetError, DataFlowError)

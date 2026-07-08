# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1614 — ``Model.query_builder()`` ignored
``__tablename__``.

Query-surface sibling of #1541 (CREATE INDEX / FK ALTER) and #1573 (migration
trigger/diff/tracking paths). Those closed the ``__tablename__`` asymmetry on
the DDL/migration surface by routing every table-name resolution through the
``__tablename__``-respecting resolver ``_get_table_name``. The QUERY surface was
the remaining sibling: the ``query_builder`` classmethod bound during model
registration (``engine.py``, ``_register_model_internal``) resolved the table
via ``_class_name_to_table_name(cls.__name__)`` — the pluralized class-name
default — NOT ``_get_table_name``. For a model with a custom ``__tablename__``,
``Model.query_builder().build_select(...)`` produced ``SELECT ... FROM
<pluralized_default>`` against a table that does not exist (the real table is
the custom ``__tablename__``), so every ``query_builder``-built query on such a
model targeted the wrong / nonexistent table.

The fix routes the ``query_builder`` binding through
``_get_table_name(cls.__name__)`` — the same resolver CREATE TABLE, the
index/FK generators (#1541), and the migration paths (#1573) already use.

RED→GREEN proven (against real PostgreSQL) with the ``engine.py`` fix reverted to
``_class_name_to_table_name``:
  * ``test_query_builder_build_select_targets_custom_tablename`` — the built
    SELECT targets the pluralized default, so the "custom present / default
    absent" assertions fail.
  * ``test_query_builder_round_trips_row_from_custom_table`` — the built SELECT
    targets the nonexistent pluralized-default table, so executing it against
    the real database raises ``UndefinedTableError`` and the row never
    round-trips.
Restoring the fix makes them pass. The default table name is computed from
``_class_name_to_table_name`` at runtime (never hardcoded), so the
default-absent assertion cannot be vacuously satisfied by a mis-guessed
pluralization (``rules/verify-claims-before-write.md``).

Behavioral (NO mocking, real PostgreSQL on port 5434). Assertions query the
real catalog / the engine's own resolution, NOT source text
(``rules/testing.md`` § Behavioral Regression Tests Over Source-Grep).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).

Run:
    TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5434/kailash_test" \
      .venv/bin/python -m pytest \
      packages/kailash-dataflow/tests/regression/test_issue_1614_tablename_query_builder.py \
      -p no:xdist -o "addopts=" -q --tb=short
"""

import os
import uuid

import asyncpg
import pytest

from dataflow import DataFlow
from dataflow.adapters.exceptions import InvalidIdentifierError
from dataflow.database.query_builder import DatabaseType, QueryBuilder

PG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


# --------------------------------------------------------------------------
# Raw read-back helper (reflects COMMITTED state, bypasses DataFlow entirely).
# --------------------------------------------------------------------------
async def _pg_drop(url: str, *tables: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        for t in tables:
            await conn.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
    finally:
        await conn.close()


# --------------------------------------------------------------------------
# Test 1 — the deterministic distinguisher: build_select targets __tablename__.
# RED without the fix: the built SELECT targets the pluralized class default.
# No DB round-trip needed — this exercises the query_builder binding + SQL
# construction directly (query_builder resolves the table at build time).
# --------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_query_builder_build_select_targets_custom_tablename():
    """``Model.query_builder().build_select(...)`` MUST target the resolved
    ``__tablename__`` — not the pluralized class-name default (issue #1614)."""
    custom = f"acct_q1614_{uuid.uuid4().hex[:8]}"

    db = DataFlow(PG_URL, auto_migrate=True)

    @db.model
    class Issue1614QueryAccount:
        __tablename__ = custom

        id: str
        name: str

    # Compute the pluralized default from the engine's own converter — a
    # hardcoded guess makes the "absent" assertion vacuous.
    default_plural = db._class_name_to_table_name("Issue1614QueryAccount")
    assert default_plural != custom  # the two names MUST differ for this test

    # Sanity: the resolver itself honors __tablename__ (from #1541).
    assert db._get_table_name("Issue1614QueryAccount") == custom

    builder = Issue1614QueryAccount.query_builder()
    builder.where("id", "$eq", "some-id")
    sql, _params = builder.build_select(["id", "name"])

    assert (
        custom in sql
    ), f"query_builder SELECT must target the custom table '{custom}' (issue #1614)"
    assert (
        default_plural not in sql
    ), "query_builder SELECT must NOT target the pluralized default table"


# --------------------------------------------------------------------------
# Test 2 — behavioral end-to-end (AC2): a row written to a custom-__tablename__
# model round-trips through query_builder's own SELECT against the real table.
# RED without the fix: the built SELECT targets the nonexistent pluralized
# default, so executing it raises UndefinedTableError and the row never returns.
# --------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_query_builder_round_trips_row_from_custom_table():
    """A row written to a custom-``__tablename__`` model MUST round-trip through
    the SQL ``query_builder`` builds — proving query_builder targets the real
    (custom) table, not the nonexistent pluralized default (issue #1614)."""
    custom = f"acct_r1614_{uuid.uuid4().hex[:8]}"
    default_plural = None  # bound before the finally references it

    db = DataFlow(PG_URL, auto_migrate=True)

    @db.model
    class Issue1614RoundTripAccount:
        __tablename__ = custom

        id: str
        name: str

    default_plural = db._class_name_to_table_name("Issue1614RoundTripAccount")
    assert default_plural != custom

    await db.initialize()
    try:
        await db.create_tables_async()

        rid = f"acct-{uuid.uuid4().hex[:8]}"
        await db.express.create(
            "Issue1614RoundTripAccount", {"id": rid, "name": "round-trip-1614"}
        )

        # Build the read query through query_builder (the surface under test),
        # then execute its SQL against the real database. PostgreSQL emits
        # native ``$N`` placeholders, so asyncpg runs (sql, params) directly.
        builder = Issue1614RoundTripAccount.query_builder()
        builder.where("id", "$eq", rid)
        sql, params = builder.build_select(["id", "name"])

        # Pre-fix, `sql` targets the nonexistent pluralized-default table and
        # this execute raises asyncpg.UndefinedTableError.
        conn = await asyncpg.connect(PG_URL)
        try:
            row = await conn.fetchrow(sql, *params)
        finally:
            await conn.close()

        assert row is not None, (
            "query_builder's SELECT must return the written row from the custom "
            f"table '{custom}' (issue #1614)"
        )
        assert row["id"] == rid
        assert row["name"] == "round-trip-1614"

        await db.express.close_async()
    finally:
        await _pg_drop(PG_URL, *(t for t in (custom, default_plural) if t))


# --------------------------------------------------------------------------
# Test 3 — defense-in-depth (surfaced by the #1614 security review): the TABLE
# surface is fail-closed. Before #1614, query_builder fed only the derived
# pluralized-default table name into its quoter; #1614 routes the raw
# developer-authored ``__tablename__`` there, so the TABLE-name quoter MUST
# validate (allowlist regex + reject-don't-escape) exactly as the DDL path does
# — a crafted table identifier raises InvalidIdentifierError instead of breaking
# out of the quotes (dataflow-identifier-safety.md MUST-1/2/5). The scope is the
# TABLE name only: the field list legitimately carries aggregate/alias
# EXPRESSIONS (``COUNT(*) AS total``), which are NOT plain identifiers and MUST
# NOT be allowlist-rejected (that contract is pinned below so a future
# over-reach fails loudly). No DB needed — rejection happens at SQL-build time.
# --------------------------------------------------------------------------
@pytest.mark.regression
def test_query_builder_rejects_injection_shaped_table_name():
    """QueryBuilder TABLE-name quoting is fail-closed across every dialect (the
    #1614-activated surface), while valid table names still build
    byte-identically (issue #1614 hardening)."""
    payload = 'x"; DROP TABLE users; --'

    for db_type in (
        DatabaseType.POSTGRESQL,
        DatabaseType.MYSQL,
        DatabaseType.SQLITE,
    ):
        # Malicious TABLE name (the surface #1614 newly routes __tablename__ to)
        # — rejected across EVERY build_* verb + join, so a future refactor that
        # bypasses the shared _quote_table_name on any one verb fails loudly.
        with pytest.raises(InvalidIdentifierError):
            QueryBuilder(payload, db_type).build_select(["id"])
        with pytest.raises(InvalidIdentifierError):
            QueryBuilder(payload, db_type).build_count()
        with pytest.raises(InvalidIdentifierError):
            QueryBuilder(payload, db_type).build_insert({"id": 1})
        with pytest.raises(InvalidIdentifierError):
            QueryBuilder(payload, db_type).build_update({"name": "x"})
        with pytest.raises(InvalidIdentifierError):
            QueryBuilder(payload, db_type).build_delete()
        # A malicious JOIN target is a table too — fail-closed at join() time.
        with pytest.raises(InvalidIdentifierError):
            QueryBuilder("accounts", db_type).join(payload, "1=1")

        # Valid table name still builds — zero-delta for the legitimate path.
        qb_ok = QueryBuilder("accounts", db_type)
        sql, _ = qb_ok.build_select(["id", "name"])
        assert "accounts" in sql
        assert "id" in sql and "name" in sql


@pytest.mark.regression
def test_query_builder_field_list_still_accepts_aggregate_expressions():
    """The FIELD list contract is preserved: aggregate/alias expressions
    (``COUNT(*) as total``) are NOT plain identifiers and MUST still build — the
    #1614 TABLE-name hardening MUST NOT over-reach onto the field surface
    (guards the regression the #1614 redteam caught: strict field validation
    broke ``COUNT(*) as ...`` on the public build_select API)."""
    for db_type in (
        DatabaseType.POSTGRESQL,
        DatabaseType.MYSQL,
        DatabaseType.SQLITE,
    ):
        qb = QueryBuilder("orders", db_type)
        # Aggregate + alias field expressions must pass through unrejected.
        sql, _ = qb.build_select(["user_id", "status", "COUNT(*) as order_count"])
        assert "COUNT(*)" in sql
        assert "order_count" in sql

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1573 — the AutoMigrationSystem trigger paths and
the migration-diff/tracking pipeline ignored ``__tablename__``.

Sibling of #1541. That fix routed the CREATE INDEX / FK ALTER DDL generators
through the ``__tablename__``-respecting resolver ``_get_table_name``. The
migration TRIGGER paths (``_trigger_sqlite_migration_system`` and the async
``_execute_*`` variants), the diff/target builders
(``_trigger_postgresql_enhanced_schema_management``,
``_trigger_postgresql_migration_system``, ``_build_incremental_model_schema``),
the tracking DDL path (``_execute_postgresql_migration_with_tracking`` →
``_generate_migration_sql``), and FK auto-detection
(``_auto_detect_relationships`` / ``get_relationships``) still keyed to the
pluralized class-name default (``_class_name_to_table_name``). For a model with
a custom ``__tablename__`` these built the migration TARGET schema, the diff,
and the ALTER DDL against the WRONG table name — planning a phantom
default-named table and/or emitting ALTER DDL against a table that does not
exist.

The fix routes every one of those sites through ``_get_table_name(model_name)``
(and the two ``_generate_migration_sql`` reverse-lookups + ``get_relationships``
through ``_get_table_name(name)``, since they must map the physical table name
resolved by the fixed callers back to the model consistently).

RED→GREEN proven (both, against real PostgreSQL): with the incremental-schema
and reverse-lookup ``_get_table_name`` swaps reverted to
``_class_name_to_table_name``:
  * ``test_incremental_model_schema_keys_to_custom_tablename`` — the model's
    table entry is added to the ModelSchema under the pluralized default, so the
    "default name is absent" assertion fails.
  * ``test_generate_migration_sql_reverse_lookup_resolves_custom_tablename`` —
    the reverse-lookup cannot map the custom physical name back to its model,
    so ``_generate_migration_sql`` returns "" (the ALTER is silently dropped);
    the non-empty assertion fails.
Restoring the fix makes them pass. The default table names are computed from
``_class_name_to_table_name`` at runtime (never hardcoded), so the
default-absent / phantom-table assertions cannot be vacuously satisfied by a
mis-guessed pluralization.

``test_custom_tablename_alter_lands_on_custom_table_no_phantom_history_consistent``
is an end-to-end guarding invariant (AC2): through ``create_tables_async`` the
physical DDL is owned by ``_generate_create_table_sql`` (which already respects
``__tablename__``), so this path did not visibly regress pre-fix — the test pins
the whole-pipeline invariant against future drift rather than distinguishing the
current fix.

Behavioral (NO mocking, real PostgreSQL on port 5434). Assertions query the
real catalog / the engine's own resolution, NOT source text.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).

Run:
    TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5434/kailash_test" \
      .venv/bin/python -m pytest \
      packages/kailash-dataflow/tests/regression/test_issue_1573_tablename_migration_tracking_paths.py \
      -p no:xdist -o "addopts=" -q --tb=short
"""

import os
import uuid

import asyncpg
import pytest

from dataflow import DataFlow
from dataflow.migrations.schema_state_manager import MigrationOperation

PG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


# --------------------------------------------------------------------------
# Raw read-back helpers (reflect COMMITTED state, bypass DataFlow entirely).
# --------------------------------------------------------------------------
async def _pg_table_exists(url: str, table: str) -> bool:
    conn = await asyncpg.connect(url)
    try:
        return bool(
            await conn.fetchval(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1 AND table_schema = current_schema()",
                table,
            )
        )
    finally:
        await conn.close()


async def _pg_columns(url: str, table: str) -> set:
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = $1 AND table_schema = current_schema()",
            table,
        )
        return {r["column_name"] for r in rows}
    finally:
        await conn.close()


async def _pg_fetch(url: str, table: str, rid: str):
    conn = await asyncpg.connect(url)
    try:
        row = await conn.fetchrow(f'SELECT * FROM "{table}" WHERE id = $1', rid)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def _pg_drop(url: str, *tables: str) -> None:
    conn = await asyncpg.connect(url)
    try:
        for t in tables:
            await conn.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')
    finally:
        await conn.close()


# --------------------------------------------------------------------------
# Test 1 — target/diff schema builder keys to __tablename__, not the default.
# Deterministic distinguisher for the _build_incremental_model_schema fix
# (and, by construction, the sibling _trigger_* target builders that key the
# same way). RED without the fix: schema is keyed under the pluralized default.
# --------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_incremental_model_schema_keys_to_custom_tablename():
    """``_build_incremental_model_schema`` MUST key the model's table entry
    under the resolved ``__tablename__`` — not the pluralized class default."""
    custom = f"acct_c1573_{uuid.uuid4().hex[:8]}"

    db = DataFlow(PG_URL, auto_migrate=True)

    @db.model
    class Issue1573SchemaAccount:
        __tablename__ = custom

        id: str
        name: str
        nickname: str

    # Compute the pluralized default from the engine's own converter — a
    # hardcoded guess (e.g. missing snake_case) makes the "absent" assertion
    # vacuous (rules/verify-claims-before-write.md).
    default_plural = db._class_name_to_table_name("Issue1573SchemaAccount")
    assert default_plural != custom  # the two names MUST differ for this test

    await db.initialize()
    try:
        # Sanity: the resolver itself honors __tablename__ (from #1541).
        assert db._get_table_name("Issue1573SchemaAccount") == custom

        fields = db.get_model_fields("Issue1573SchemaAccount")
        schema = db._build_incremental_model_schema("Issue1573SchemaAccount", fields)

        assert (
            custom in schema.tables
        ), f"incremental ModelSchema must key to '{custom}' (issue #1573)"
        assert (
            default_plural not in schema.tables
        ), "incremental ModelSchema must NOT key to the pluralized default"
    finally:
        await db.express.close_async()
        await _pg_drop(PG_URL, custom, default_plural)


# --------------------------------------------------------------------------
# Test 2 — the tracking-path ALTER generator resolves the custom table back to
# its model. Deterministic distinguisher for the _generate_migration_sql
# reverse-lookup fix. RED without the fix: the reverse-lookup compares the
# pluralized default against the custom physical name, never matches, and
# _generate_migration_sql returns "" — the ALTER is silently dropped.
# --------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_generate_migration_sql_reverse_lookup_resolves_custom_tablename():
    """``_generate_migration_sql`` MUST map the physical (``__tablename__``)
    table name back to its model so the ADD COLUMN DDL targets the real table,
    not an empty string."""
    custom = f"acct_g1573_{uuid.uuid4().hex[:8]}"

    db = DataFlow(PG_URL, auto_migrate=True)

    @db.model
    class Issue1573DdlAccount:
        __tablename__ = custom

        id: str
        name: str
        nickname: str

    default_plural = db._class_name_to_table_name("Issue1573DdlAccount")
    assert default_plural != custom

    await db.initialize()
    try:
        # Resolve the physical name exactly as the fixed tracking path does.
        resolved = db._get_table_name("Issue1573DdlAccount")
        assert resolved == custom

        op = MigrationOperation(
            operation_type="ADD_COLUMN",
            table_name=resolved,
            details={"column_name": "nickname"},
        )
        sql = db._generate_migration_sql(op, resolved, "postgresql")

        assert sql, (
            "reverse-lookup must map the custom table back to its model so the "
            "ALTER DDL is generated instead of silently dropped (issue #1573)"
        )
        assert custom in sql, f"ALTER DDL must target the custom table '{custom}'"
        assert "nickname" in sql, "ALTER DDL must add the new 'nickname' column"
        assert (
            default_plural not in sql
        ), "ALTER DDL must NOT target the pluralized default table"
    finally:
        await db.express.close_async()
        await _pg_drop(PG_URL, custom, default_plural)


# --------------------------------------------------------------------------
# Test 3 — AC2 end-to-end: a custom-__tablename__ model that gains a field is
# ALTER-ADDed on the REAL table; no phantom default-named table is created; and
# migration-history keying (dataflow_migration_history / dataflow_model_registry)
# never forks under the pluralized default name. This pins the whole-pipeline
# invariant the coordinated multi-site fix guarantees.
# --------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_custom_tablename_alter_lands_on_custom_table_no_phantom_history_consistent():
    """End-to-end: adding a field to a custom-``__tablename__`` model ALTERs the
    real table, creates NO phantom default-named table, and leaves the migration
    history / model registry free of the pluralized default name (issue #1573)."""
    custom = f"acct_e1573_{uuid.uuid4().hex[:8]}"
    default_plural = None  # bound before the finally references it

    try:
        # ---- V1: custom table with (id, name) ----
        db1 = DataFlow(PG_URL, auto_migrate=True)

        @db1.model
        class Issue1573E2eAccount:
            __tablename__ = custom

            id: str
            name: str

        # Computed default (not a hardcoded guess) — the phantom-table check is
        # vacuous if this string never matches the real pluralization.
        default_plural = db1._class_name_to_table_name("Issue1573E2eAccount")
        assert default_plural != custom

        await db1.initialize()
        await db1.create_tables_async()
        rid_legacy = f"legacy-{uuid.uuid4().hex[:8]}"
        await db1.express.create(
            "Issue1573E2eAccount", {"id": rid_legacy, "name": "legacy"}
        )
        assert await _pg_table_exists(PG_URL, custom), "custom table must exist"
        assert "nickname" not in await _pg_columns(PG_URL, custom)
        await db1.express.close_async()

        # ---- V2: SAME custom table, model now declares `nickname` ----
        db2 = DataFlow(PG_URL, auto_migrate=True)

        @db2.model
        class Issue1573E2eAccount:  # noqa: F811
            __tablename__ = custom

            id: str
            name: str
            nickname: str

        await db2.initialize()
        await db2.create_tables_async()

        # (a) the new column landed on the REAL (custom) table.
        cols = await _pg_columns(PG_URL, custom)
        assert "nickname" in cols, "ALTER-ADD must land on the custom table"

        # (b) NO phantom default-pluralized table was created.
        assert not await _pg_table_exists(
            PG_URL, default_plural
        ), "no phantom pluralized-default table may be created (issue #1573)"

        # (c) the new column accepts a value; the pre-existing row survives.
        rid_new = f"new-{uuid.uuid4().hex[:8]}"
        await db2.express.create(
            "Issue1573E2eAccount",
            {"id": rid_new, "name": "new", "nickname": "nick-1573"},
        )
        new_row = await _pg_fetch(PG_URL, custom, rid_new)
        assert new_row is not None and new_row["nickname"] == "nick-1573"
        legacy_row = await _pg_fetch(PG_URL, custom, rid_legacy)
        assert legacy_row is not None and legacy_row["nickname"] is None

        # (d) migration-history keying never forked under the default name.
        conn = await asyncpg.connect(PG_URL)
        try:
            for hist in ("dataflow_migration_history", "dataflow_model_registry"):
                if not await conn.fetchval(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = $1",
                    hist,
                ):
                    continue
                blob = await conn.fetchval(
                    f"SELECT string_agg(t::text, ' ') FROM {hist} t"
                )
                if blob:
                    assert default_plural not in blob, (
                        f"{hist} must not reference the pluralized default "
                        f"'{default_plural}' (issue #1573)"
                    )
        finally:
            await conn.close()

        await db2.express.close_async()
    finally:
        await _pg_drop(PG_URL, *(t for t in (custom, default_plural) if t))

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for migration 0002 — ``_kml_*`` prefix unification.

Covers the mechanical invariants — table inventory, identifier length,
DDL-composition shape, column inventory — using in-process SQLite. The
Tier 2 integration test exercises real SQLite + real PostgreSQL.
"""
from __future__ import annotations

import importlib
import re
import sqlite3

import pytest

from kailash.db.dialect import (
    DatabaseType,
    IdentifierError,
    PostgresDialect,
    SQLiteDialect,
)

# Numbered-migration module — import via importlib (leading digit in stem).
_mod = importlib.import_module(
    "kailash.tracking.migrations.0002_kml_prefix_tenant_audit"
)
Migration = _mod.Migration
MigrationResumeRequiredError = _mod.MigrationResumeRequiredError
DowngradeRefusedError = _mod.DowngradeRefusedError
TABLE_INVENTORY = _mod.TABLE_INVENTORY
PARKING_TABLE = _mod.PARKING_TABLE
_compose_create_table = _mod._compose_create_table
_compose_create_index = _mod._compose_create_index
_compose_audit_immutability_ddl = _mod._compose_audit_immutability_ddl


# --- Table inventory invariants ---------------------------------------


def test_table_inventory_has_exactly_15_tables():
    """W4 Invariant 0 — the plan commits to 15 tables."""
    assert len(TABLE_INVENTORY) == 15


def test_every_table_name_is_kml_prefixed():
    """W4 Invariant 1 — every table carries the ``_kml_`` prefix."""
    for spec in TABLE_INVENTORY:
        assert spec.name.startswith("_kml_"), spec.name


def test_every_write_path_table_carries_tenant_id():
    """W4 Invariant 3 — every write-path table has ``tenant_id TEXT NOT NULL``."""
    for spec in TABLE_INVENTORY:
        column_names = [c[0] for c in spec.columns]
        assert (
            "tenant_id" in column_names
        ), f"{spec.name} missing tenant_id column: {column_names}"
        # And the type key for tenant_id MUST be TENANT_ID (TEXT NOT NULL).
        tenant_type = next(t for n, t in spec.columns if n == "tenant_id")
        assert tenant_type == "TENANT_ID", spec.name


def test_audit_immutable_flag_set_only_on_audit_table():
    """W4 Invariant 4 — only ``_kml_audit`` is flagged audit-immutable."""
    immutable_tables = [s.name for s in TABLE_INVENTORY if s.audit_immutable]
    assert immutable_tables == ["_kml_audit"]


def test_classify_actions_has_fingerprint_check_constraint():
    """W4 Invariant 5 — record_fingerprint MUST match ``sha256:<8hex>``."""
    spec = next(s for s in TABLE_INVENTORY if s.name == "_kml_classify_actions")
    assert spec.check_constraints, "_kml_classify_actions missing CHECK constraint"
    check = spec.check_constraints[0]
    assert "sha256:" in check
    assert "length(record_fingerprint) = 15" in check


# --- Identifier-length invariant (W4 Invariant 2) ---------------------


def test_every_table_name_within_63_chars():
    for spec in TABLE_INVENTORY:
        assert len(spec.name) <= 63, f"{spec.name}: {len(spec.name)} chars > 63"


def test_every_index_name_within_63_chars():
    """Mechanical enumeration of every CREATE INDEX name."""
    for spec in TABLE_INVENTORY:
        for index in spec.indexes:
            assert (
                len(index.name) <= 63
            ), f"{spec.name}.{index.name}: {len(index.name)} chars > 63"


def test_every_audit_trigger_name_within_63_chars():
    """Audit-immutability trigger names derive from ``{table}_no_update`` etc."""
    for spec in TABLE_INVENTORY:
        if not spec.audit_immutable:
            continue
        for suffix in ("no_update", "no_delete", "reject_mutation"):
            name = f"{spec.name}_{suffix}"
            assert len(name) <= 63, f"{name}: {len(name)} chars > 63"


def test_quote_identifier_rejects_over_63_char_index_name_on_postgres():
    """W4 Invariant 2 — over-63 identifier raises BEFORE DDL executes."""
    dialect = PostgresDialect()
    over_long = "ix_" + "a" * 62  # 65 chars total
    with pytest.raises(IdentifierError):
        dialect.quote_identifier(over_long)


def test_quote_identifier_rejects_sql_injection_payload():
    """The quote_identifier contract — rejects, does not escape."""
    for dialect in (SQLiteDialect(), PostgresDialect()):
        with pytest.raises(IdentifierError):
            dialect.quote_identifier('users"; DROP TABLE victims; --')


# --- DDL-composition: no raw f-string identifier interpolation --------


def test_no_unquoted_identifier_interpolation_in_source():
    """W4 Invariant 6 / grep gate — no raw f-string identifier interpolation
    in 0002's DDL-composition helpers. Every identifier MUST route through
    ``dialect.quote_identifier``.
    """
    import inspect

    src = inspect.getsource(_mod)
    # The rule: every f-string that builds DDL references a ``quoted_*`` name,
    # never a bare table/column/index name. We flag any f-string fragment
    # containing "CREATE TABLE {", "CREATE INDEX {", "DROP TABLE {", etc.
    # where the braces enclose a non-``quoted_`` / non-``parking`` variable.
    offenders: list[str] = []
    pattern = re.compile(
        r"f\".*?(CREATE\s+TABLE|CREATE\s+INDEX|ALTER\s+TABLE|DROP\s+TABLE|"
        r"DROP\s+INDEX|DROP\s+TRIGGER|CREATE\s+TRIGGER)\s+(IF\s+NOT\s+EXISTS\s+)?"
        r"(\{[^}]+\}).*?\"",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(src):
        placeholder = m.group(3)
        # Permitted placeholders: quoted_*, fn_name, trg_*, table, parking, index
        bare = placeholder.strip("{}")
        if not re.match(
            r"^(quoted_[a-z_]+|fn_name|trg_upd|trg_del|table|parking|"
            r"quoted_table|quoted_col|quoted_index)$",
            bare,
        ):
            offenders.append(placeholder)
    assert not offenders, (
        f"raw identifier interpolation detected: {offenders}. "
        f"Every DDL identifier MUST route through dialect.quote_identifier."
    )


def test_compose_create_table_emits_quoted_identifiers_sqlite():
    dialect = SQLiteDialect()
    spec = next(s for s in TABLE_INVENTORY if s.name == "_kml_runs")
    sql = _compose_create_table(dialect, spec)
    assert '"_kml_runs"' in sql
    assert '"tenant_id" TEXT NOT NULL' in sql
    assert 'PRIMARY KEY ("tenant_id", "run_id")' in sql


def test_compose_create_table_uses_dialect_json_type():
    """Postgres → JSONB, SQLite → TEXT."""
    spec = next(s for s in TABLE_INVENTORY if s.name == "_kml_params")
    assert "JSONB NOT NULL" in _compose_create_table(PostgresDialect(), spec)
    assert "TEXT NOT NULL" in _compose_create_table(SQLiteDialect(), spec)


def test_compose_create_table_uses_bigint_on_postgres_for_metrics_step():
    """ml-tracking.md §6.3 — step MUST be int64. PG INTEGER is int32."""
    spec = next(s for s in TABLE_INVENTORY if s.name == "_kml_metrics")
    pg_sql = _compose_create_table(PostgresDialect(), spec)
    assert "BIGINT NOT NULL" in pg_sql
    sqlite_sql = _compose_create_table(SQLiteDialect(), spec)
    assert "INTEGER NOT NULL" in sqlite_sql  # SQLite INTEGER is already int64


def test_compose_create_index_uses_quoted_identifiers():
    dialect = SQLiteDialect()
    spec = next(s for s in TABLE_INVENTORY if s.name == "_kml_runs")
    idx = spec.indexes[0]
    sql = _compose_create_index(dialect, spec.name, idx)
    assert sql.startswith("CREATE INDEX IF NOT EXISTS ")
    assert f'"{idx.name}"' in sql
    assert '"_kml_runs"' in sql


def test_audit_immutability_ddl_sqlite_emits_raise_abort():
    dialect = SQLiteDialect()
    stmts = _compose_audit_immutability_ddl(dialect, "_kml_audit")
    joined = " ".join(stmts)
    assert "BEFORE UPDATE" in joined
    assert "BEFORE DELETE" in joined
    assert "RAISE(ABORT" in joined


def test_audit_immutability_ddl_postgres_emits_plpgsql():
    dialect = PostgresDialect()
    stmts = _compose_audit_immutability_ddl(dialect, "_kml_audit")
    joined = " ".join(stmts)
    assert "CREATE OR REPLACE FUNCTION" in joined
    assert "LANGUAGE plpgsql" in joined
    assert "RAISE EXCEPTION" in joined


# --- Apply: live against in-memory SQLite -----------------------------


class _SqliteConnAdapter:
    """Minimal async-looking wrapper around sqlite3 — mirrors 0001 test."""

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self.database_type = DatabaseType.SQLITE

    def execute(self, sql: str, params=None):
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)

    def close(self) -> None:
        self._conn.close()


@pytest.fixture
def conn():
    c = _SqliteConnAdapter()
    yield c
    c.close()


@pytest.mark.asyncio
async def test_verify_returns_false_on_empty_schema(conn):
    m = Migration()
    assert await m.verify(conn) is False


@pytest.mark.asyncio
async def test_apply_creates_all_15_tables(conn):
    m = Migration()
    result = await m.apply(conn)
    assert result.direction == "upgrade"
    assert result.rows_migrated == 15
    # All 15 tables exist now.
    rows = list(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_kml_%'"
        )
    )
    table_names = {r[0] for r in rows}
    for spec in TABLE_INVENTORY:
        assert spec.name in table_names, f"missing: {spec.name}"


@pytest.mark.asyncio
async def test_apply_is_idempotent(conn):
    m = Migration()
    first = await m.apply(conn)
    assert first.rows_migrated == 15
    second = await m.apply(conn)
    assert second.rows_migrated == 0
    assert "already applied" in second.notes


@pytest.mark.asyncio
async def test_verify_returns_true_after_apply(conn):
    m = Migration()
    await m.apply(conn)
    assert await m.verify(conn) is True


@pytest.mark.asyncio
async def test_dry_run_does_not_create_tables(conn):
    m = Migration()
    result = await m.apply(conn, dry_run=True)
    assert result.was_dry_run is True
    # No _kml_* tables should exist afterwards.
    rows = list(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_kml_%'"
        )
    )
    assert rows == []


# --- Audit immutability -----------------------------------------------


@pytest.mark.asyncio
async def test_audit_trigger_blocks_update_sqlite(conn):
    m = Migration()
    await m.apply(conn)
    # Insert a row first (allowed).
    conn.execute(
        "INSERT INTO _kml_audit "
        "(tenant_id, timestamp, actor_id, resource_kind, resource_id, action) "
        "VALUES ('t1', '2026-04-22', 'alice', 'run', 'r1', 'create')"
    )
    # UPDATE must be blocked by trigger.
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        conn.execute("UPDATE _kml_audit SET action = 'tamper'")
    assert "append-only" in str(excinfo.value)


@pytest.mark.asyncio
async def test_audit_trigger_blocks_delete_sqlite(conn):
    m = Migration()
    await m.apply(conn)
    conn.execute(
        "INSERT INTO _kml_audit "
        "(tenant_id, timestamp, actor_id, resource_kind, resource_id, action) "
        "VALUES ('t1', '2026-04-22', 'alice', 'run', 'r1', 'create')"
    )
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        conn.execute("DELETE FROM _kml_audit")
    assert "append-only" in str(excinfo.value)


# --- Classification fingerprint CHECK constraint ----------------------


@pytest.mark.asyncio
async def test_classify_actions_accepts_sha256_fingerprint(conn):
    m = Migration()
    await m.apply(conn)
    conn.execute(
        "INSERT INTO _kml_classify_actions "
        "(tenant_id, action_id, record_fingerprint, action_type, created_at) "
        "VALUES ('t1', 'a1', 'sha256:deadbeef', 'redact', '2026-04-22')"
    )


@pytest.mark.asyncio
async def test_classify_actions_rejects_bad_fingerprint(conn):
    m = Migration()
    await m.apply(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO _kml_classify_actions "
            "(tenant_id, action_id, record_fingerprint, action_type, created_at) "
            "VALUES ('t1', 'a2', 'plain-email@example.com', 'redact', '2026-04-22')"
        )


# --- Rollback + force_downgrade ---------------------------------------


@pytest.mark.asyncio
async def test_rollback_refuses_without_force_downgrade(conn):
    m = Migration()
    await m.apply(conn)
    with pytest.raises(DowngradeRefusedError):
        await m.rollback(conn)


@pytest.mark.asyncio
async def test_rollback_drops_created_tables_with_force(conn):
    m = Migration()
    await m.apply(conn)
    await m.rollback(conn, force_downgrade=True)
    # Every table we created should be gone.
    rows = list(
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_kml_%'"
        )
    )
    assert rows == [], f"tables leaked: {[r[0] for r in rows]}"


@pytest.mark.asyncio
async def test_rollback_noop_when_parking_absent(conn):
    m = Migration()
    # Never applied — parking table doesn't exist.
    result = await m.rollback(conn, force_downgrade=True)
    assert result.rows_migrated == 0
    assert "no-op" in result.notes.lower() or "absent" in result.notes.lower()


# --- MigrationResumeRequiredError taxonomy ----------------------------


def test_resume_error_is_mlerror_subclass():
    from kailash.ml.errors import MLError

    assert issubclass(MigrationResumeRequiredError, MLError)


def test_downgrade_refused_error_is_mlerror_subclass():
    from kailash.ml.errors import MLError

    assert issubclass(DowngradeRefusedError, MLError)


def test_resume_error_distinct_from_downgrade_refused():
    """Per rules/dataflow-identifier-safety.md Rule 6 — orchestrator-layer
    error types MUST be distinct so callers can try/except one without
    catching the other."""
    assert not issubclass(MigrationResumeRequiredError, DowngradeRefusedError)
    assert not issubclass(DowngradeRefusedError, MigrationResumeRequiredError)


# --- Extension mode: pre-existing table gains tenant_id ---------------


@pytest.mark.asyncio
async def test_apply_alters_pre_existing_table_to_add_tenant_id():
    """Upgrade-from-0.x path — existing ``_kml_runs`` without tenant_id
    gets ALTER TABLE ADD COLUMN, not CREATE TABLE."""
    c = _SqliteConnAdapter()
    try:
        # Simulate 0.x: _kml_runs exists without tenant_id.
        c.execute(
            "CREATE TABLE _kml_runs " "(run_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        c.execute("INSERT INTO _kml_runs VALUES ('r1', 'FINISHED')")

        m = Migration()
        await m.apply(c)

        # tenant_id column should now exist AND the existing row should
        # have defaulted to '_single'.
        rows = list(c.execute("SELECT run_id, tenant_id FROM _kml_runs"))
        assert len(rows) == 1
        assert rows[0][0] == "r1"
        assert rows[0][1] == "_single"
    finally:
        c.close()

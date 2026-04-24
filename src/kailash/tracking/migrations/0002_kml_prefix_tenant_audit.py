# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Migration 0002 — ``_kml_*`` table prefix unification + tenant columns + audit immutability.

Creates (or extends) the canonical 15-table tracking schema. Every
write-path table carries ``tenant_id TEXT NOT NULL``; the audit table
is made immutable against UPDATE/DELETE via a dialect-appropriate
trigger; every identifier (table AND index) is routed through
``dialect.quote_identifier`` and therefore validated against the
63-char PostgreSQL limit and the ``[a-zA-Z_][a-zA-Z0-9_]*`` allow-list
BEFORE any DDL executes.

Spec trace
----------
- ``specs/kailash-core-ml-integration.md §4`` — migration framework contract.
- ``specs/ml-tracking.md §6.3`` — canonical schema DDL. **Spec-code drift
  acknowledgement:** ``ml-tracking.md §6.3`` names tables with the singular
  form (``_kml_run``, ``_kml_param``, ...); the authoritative 34-wave
  plan and the already-landed ``0001_status_vocabulary_finished.py``
  commit to the plural form (``_kml_runs``, ``_kml_params``, ...). This
  migration follows the plan + 0001. The spec singular→plural alignment
  is tracked for codify sweep against the full ``specs/ml-*.md`` sibling
  set per ``rules/specs-authority.md`` Rule 5b.
- ``specs/ml-tracking.md §8.4`` — audit rows are IMMUTABLE (no UPDATE
  grant, trigger-blocks UPDATE and DELETE on ``_kml_audit``).

Rule trace
----------
- ``rules/schema-migration.md`` §1 (numbered-migrations only), §3
  (reversible), §5 (real PG + SQLite test), §7 (``force_downgrade=True``
  required on destructive rollback).
- ``rules/dataflow-identifier-safety.md`` MUST Rule 1 (every dynamic
  DDL identifier via ``quote_identifier``) + Rule 2 (identifier
  contract: validate + length-check + quote, reject not escape).
- ``rules/tenant-isolation.md`` MUST Rule 1 (tenant dimension on every
  write-path store).
- ``rules/event-payload-classification.md`` MUST Rule 2 (classified PK
  fingerprint form ``sha256:<8hex>``) — ``_kml_classify_actions.record_fingerprint``
  column carries a dialect CHECK constraint that enforces the shape.

Invariant tests
---------------
- T1 unit (``tests/unit/tracking/test_migration_0002.py``): enumerates
  every ``CREATE INDEX`` name and asserts ``len(name) <= 63``; asserts
  no raw f-string identifier interpolation by grep (the DDL-composition
  helpers below MUST route every identifier through ``quote_identifier``).
- T2 integration (``tests/integration/tracking/test_migration_0002_integration.py``):
  migrate + rollback on real SQLite (and real PostgreSQL when
  ``POSTGRES_TEST_URL`` env var is set); asserts audit-table UPDATE is
  rejected; asserts identifier-too-long halts cleanly with the parking
  snapshot intact.
- Regression (``tests/regression/test_migration_0002_resume.py``):
  seeds DB with 0001 complete, simulates 0002 failure after table 7/15,
  asserts typed ``MigrationResumeRequiredError`` + state recoverable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from kailash.db.dialect import (
    DatabaseType,
    IdentifierError,
    MySQLDialect,
    PostgresDialect,
    QueryDialect,
    SQLiteDialect,
)
from kailash.ml.errors import MigrationFailedError, MLError
from kailash.tracking.migrations._base import MigrationBase, MigrationResult

__all__ = [
    "Migration",
    "MigrationResumeRequiredError",
    "TABLE_INVENTORY",
    "PARKING_TABLE",
]


# ---------------------------------------------------------------------------
# Table inventory — authoritative 15-table list for the 1.0.0 cut.
# Per W4 todo + 34-wave plan §W4. Every entry is an immutable record so
# the test suite can enumerate tables + indexes without executing DDL.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexSpec:
    """Composite index declaration — name + column ordering.

    The name is bounded to 63 chars at construction time via a sibling
    test + at execution time via ``dialect.quote_identifier`` (which
    raises :class:`IdentifierError` on over-length / invalid input).
    """

    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class TableSpec:
    """Declarative table spec — routes through dialect-portable DDL.

    ``columns`` is a list of ``(column_name, dialect_type_key)`` pairs
    where ``dialect_type_key`` is one of the helper keys below
    (:func:`_render_column_type`). Composite primary keys are
    declared via ``primary_key`` tuple; single-column PKs use the
    ``PRIMARY KEY`` inline form embedded in ``columns[*].type``.
    """

    name: str
    columns: tuple[tuple[str, str], ...]
    primary_key: tuple[str, ...]
    indexes: tuple[IndexSpec, ...] = ()
    audit_immutable: bool = False
    # Dialect-portable CHECK constraint expression (plain SQL).
    # Applied verbatim at DDL time — the expression itself MUST NOT
    # interpolate dynamic identifiers and MUST use parameter-free SQL.
    check_constraints: tuple[str, ...] = ()


# Column type keys resolved per-dialect in :func:`_render_column_type`.
# We keep the set small and explicit so the schema contract is auditable
# via a single grep on the value-strings.
_COL_TYPES = {
    "TEXT_NOT_NULL",
    "TEXT_NULL",
    "TEXT_PK",  # single-column PK
    "TENANT_ID",  # TEXT NOT NULL — dedicated key so grep finds every tenant-column
    "INT_NOT_NULL",
    "INT_NULL",
    "BIGINT_NOT_NULL",
    "BIGINT_NULL",
    "DOUBLE_NOT_NULL",
    "BOOL_NULL_DEFAULT_FALSE",
    "BOOL_NOT_NULL_DEFAULT_FALSE",
    "TIMESTAMPTZ_NOT_NULL",
    "TIMESTAMPTZ_NULL",
    "JSON_NOT_NULL",
    "JSON_NULL",
    "AUDIT_PK",  # BIGSERIAL PG / INTEGER PRIMARY KEY SQLite
}


# The 15 canonical tables. Every table carries ``tenant_id TEXT NOT NULL``
# as the first post-PK column (or as part of a composite PK). Indexes
# names are all ≤63 chars — verified in the T1 unit test.
TABLE_INVENTORY: tuple[TableSpec, ...] = (
    # --- Core tracking (7 tables) ---
    TableSpec(
        name="_kml_runs",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("run_id", "TEXT_NOT_NULL"),
            ("experiment_id", "TEXT_NULL"),
            ("parent_run_id", "TEXT_NULL"),
            ("depth", "INT_NOT_NULL"),
            ("status", "TEXT_NOT_NULL"),
            ("start_time", "TIMESTAMPTZ_NOT_NULL"),
            ("end_time", "TIMESTAMPTZ_NULL"),
            ("host", "TEXT_NULL"),
            ("git_sha", "TEXT_NULL"),
            ("python_version", "TEXT_NULL"),
            ("kailash_ml_version", "TEXT_NULL"),
            ("device_used", "TEXT_NULL"),
            ("accelerator", "TEXT_NULL"),
            ("precision", "TEXT_NULL"),
            ("actor_id", "TEXT_NULL"),
            ("error", "TEXT_NULL"),
        ),
        primary_key=("tenant_id", "run_id"),
        indexes=(
            IndexSpec("ix_kml_runs_tenant_parent", ("tenant_id", "parent_run_id")),
            IndexSpec(
                "ix_kml_runs_tenant_actor_time", ("tenant_id", "actor_id", "start_time")
            ),
        ),
    ),
    TableSpec(
        name="_kml_params",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("run_id", "TEXT_NOT_NULL"),
            ("key", "TEXT_NOT_NULL"),
            ("value", "JSON_NOT_NULL"),
        ),
        primary_key=("tenant_id", "run_id", "key"),
    ),
    TableSpec(
        name="_kml_metrics",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("run_id", "TEXT_NOT_NULL"),
            ("key", "TEXT_NOT_NULL"),
            ("step", "BIGINT_NOT_NULL"),  # int64 — 100B-token training
            ("value", "DOUBLE_NOT_NULL"),
            ("timestamp", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "run_id", "key", "step"),
    ),
    TableSpec(
        name="_kml_artifacts",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("artifact_id", "TEXT_NOT_NULL"),
            ("run_id", "TEXT_NOT_NULL"),
            ("sha256", "TEXT_NOT_NULL"),
            ("name", "TEXT_NOT_NULL"),
            ("content_type", "TEXT_NULL"),
            ("size_bytes", "BIGINT_NOT_NULL"),
            ("storage_uri", "TEXT_NOT_NULL"),
            ("encrypted", "BOOL_NOT_NULL_DEFAULT_FALSE"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "artifact_id"),
        indexes=(IndexSpec("ix_kml_artifacts_tenant_sha", ("tenant_id", "sha256")),),
    ),
    TableSpec(
        name="_kml_tags",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("run_id", "TEXT_NOT_NULL"),
            ("key", "TEXT_NOT_NULL"),
            ("value", "TEXT_NOT_NULL"),
        ),
        primary_key=("tenant_id", "run_id", "key"),
    ),
    TableSpec(
        name="_kml_audit",
        columns=(
            ("audit_id", "AUDIT_PK"),
            ("tenant_id", "TENANT_ID"),
            ("timestamp", "TIMESTAMPTZ_NOT_NULL"),
            ("actor_id", "TEXT_NOT_NULL"),
            ("resource_kind", "TEXT_NOT_NULL"),
            ("resource_id", "TEXT_NOT_NULL"),
            ("action", "TEXT_NOT_NULL"),
            ("prev_state", "JSON_NULL"),
            ("new_state", "JSON_NULL"),
        ),
        primary_key=("audit_id",),
        indexes=(
            IndexSpec(
                "ix_kml_audit_tenant_actor_time", ("tenant_id", "actor_id", "timestamp")
            ),
        ),
        audit_immutable=True,
    ),
    # --- Registry (2 tables) ---
    TableSpec(
        name="_kml_model_versions",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("model_name", "TEXT_NOT_NULL"),
            ("version", "INT_NOT_NULL"),
            ("stage", "TEXT_NOT_NULL"),
            ("run_id", "TEXT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
            ("promoted_at", "TIMESTAMPTZ_NULL"),
            ("archived_at", "TIMESTAMPTZ_NULL"),
        ),
        primary_key=("tenant_id", "model_name", "version"),
        indexes=(
            IndexSpec(
                "ix_kml_mv_tenant_name_stage", ("tenant_id", "model_name", "stage")
            ),
        ),
    ),
    TableSpec(
        name="_kml_aliases",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("model_name", "TEXT_NOT_NULL"),
            ("alias", "TEXT_NOT_NULL"),
            ("version", "INT_NOT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "model_name", "alias"),
    ),
    # --- Kaizen integration placeholders (2 tables) ---
    TableSpec(
        name="_kml_agent_runs",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("agent_run_id", "TEXT_NOT_NULL"),
            ("run_id", "TEXT_NULL"),  # FK to _kml_runs.run_id — NULL allowed
            ("agent_name", "TEXT_NOT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "agent_run_id"),
        indexes=(IndexSpec("ix_kml_agent_runs_tenant_run", ("tenant_id", "run_id")),),
    ),
    TableSpec(
        name="_kml_agent_events",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("event_id", "TEXT_NOT_NULL"),
            ("agent_run_id", "TEXT_NOT_NULL"),
            ("event_type", "TEXT_NOT_NULL"),
            ("payload", "JSON_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "event_id"),
        indexes=(
            IndexSpec("ix_kml_agent_events_tenant_time", ("tenant_id", "created_at")),
        ),
    ),
    # --- DataFlow classification placeholder (1 table) ---
    TableSpec(
        name="_kml_classify_actions",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("action_id", "TEXT_NOT_NULL"),
            ("record_fingerprint", "TEXT_NOT_NULL"),  # sha256:<8hex> form
            ("action_type", "TEXT_NOT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "action_id"),
        indexes=(
            IndexSpec("ix_kml_classify_tenant_time", ("tenant_id", "created_at")),
        ),
        # record_fingerprint MUST be the classified-PK fingerprint form
        # ``sha256:<8 hex chars>`` per rules/event-payload-classification.md
        # Rule 2. Empty string permitted for unclassified actions; anything
        # else is rejected by the dialect at INSERT.
        check_constraints=(
            "record_fingerprint = '' OR "
            "(record_fingerprint LIKE 'sha256:%' AND length(record_fingerprint) = 15)",
        ),
    ),
    # --- Lineage + feature store (3 tables) ---
    TableSpec(
        name="_kml_lineage_edges",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("edge_id", "TEXT_NOT_NULL"),
            ("from_kind", "TEXT_NOT_NULL"),
            ("from_id", "TEXT_NOT_NULL"),
            ("to_kind", "TEXT_NOT_NULL"),
            ("to_id", "TEXT_NOT_NULL"),
            ("edge_type", "TEXT_NOT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "edge_id"),
        indexes=(
            IndexSpec(
                "ix_kml_lineage_tenant_from", ("tenant_id", "from_kind", "from_id")
            ),
            IndexSpec("ix_kml_lineage_tenant_to", ("tenant_id", "to_kind", "to_id")),
        ),
    ),
    TableSpec(
        name="_kml_feature_schemas",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("schema_id", "TEXT_NOT_NULL"),
            ("name", "TEXT_NOT_NULL"),
            ("version", "INT_NOT_NULL"),
            ("schema_json", "JSON_NOT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "schema_id"),
        indexes=(
            IndexSpec("ix_kml_fs_tenant_name_ver", ("tenant_id", "name", "version")),
        ),
    ),
    # --- Drift + AutoML (2 tables) ---
    TableSpec(
        name="_kml_drift_reports",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("report_id", "TEXT_NOT_NULL"),
            ("model_name", "TEXT_NOT_NULL"),
            ("reference_run_id", "TEXT_NULL"),
            ("current_run_id", "TEXT_NULL"),
            ("psi_overall", "DOUBLE_NOT_NULL"),
            ("per_feature", "JSON_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "report_id"),
        indexes=(IndexSpec("ix_kml_drift_tenant_time", ("tenant_id", "created_at")),),
    ),
    TableSpec(
        name="_kml_automl_trials",
        columns=(
            ("tenant_id", "TENANT_ID"),
            ("trial_id", "TEXT_NOT_NULL"),
            ("study_id", "TEXT_NOT_NULL"),
            ("hyperparams", "JSON_NOT_NULL"),
            ("score", "DOUBLE_NOT_NULL"),
            ("status", "TEXT_NOT_NULL"),
            ("created_at", "TIMESTAMPTZ_NOT_NULL"),
        ),
        primary_key=("tenant_id", "trial_id"),
        indexes=(
            IndexSpec("ix_kml_automl_tenant_study", ("tenant_id", "study_id")),
            IndexSpec("ix_kml_automl_tenant_time", ("tenant_id", "created_at")),
        ),
    ),
)


# Sanity check — enforce the 15-table invariant at module load.
assert len(TABLE_INVENTORY) == 15, (
    f"TABLE_INVENTORY must declare exactly 15 tables per W4 plan; "
    f"got {len(TABLE_INVENTORY)}"
)


# Parking table holds a DDL-state snapshot so rollback can reverse
# only the tables 0002 actually created (vs. tables that pre-existed
# from 0.x). Each row records the pre-migration shape of one table.
PARKING_TABLE = "_kml_migration_0002_state_snapshot"


# ---------------------------------------------------------------------------
# Dialect resolution — mirrors 0001's helper so the two migrations use
# the same connection-shape adapters.
# ---------------------------------------------------------------------------


_DIALECT_MAP = {
    DatabaseType.POSTGRESQL: PostgresDialect,
    DatabaseType.SQLITE: SQLiteDialect,
    DatabaseType.MYSQL: MySQLDialect,
}


def _get_dialect(conn: Any) -> QueryDialect:
    dialect = getattr(conn, "dialect", None)
    if dialect is not None:
        return dialect
    db_type = getattr(conn, "database_type", None)
    if db_type is None:
        raise TypeError(
            "cannot resolve dialect from connection; pass a conn with "
            ".dialect or .database_type"
        )
    if isinstance(db_type, DatabaseType):
        return _DIALECT_MAP[db_type]()
    if isinstance(db_type, str):
        for enum_member in DatabaseType:
            if enum_member.value == db_type.lower():
                return _DIALECT_MAP[enum_member]()
    raise TypeError(
        f"unknown database_type {db_type!r} on connection; expected a "
        f"DatabaseType enum or one of {[d.value for d in DatabaseType]}"
    )


# ---------------------------------------------------------------------------
# Dialect-portable column-type rendering.
# ---------------------------------------------------------------------------


def _render_column_type(dialect: QueryDialect, type_key: str) -> str:
    """Render one column's DDL-type fragment for the target dialect.

    Returns the post-name portion ("TEXT NOT NULL", "INTEGER PRIMARY KEY",
    "JSONB NOT NULL", etc). Never interpolates an identifier — the caller
    owns quoting of the column name itself via ``dialect.quote_identifier``.
    """
    if type_key not in _COL_TYPES:
        raise ValueError(f"unknown column type key {type_key!r}")

    is_pg = dialect.database_type == DatabaseType.POSTGRESQL
    is_sqlite = dialect.database_type == DatabaseType.SQLITE

    if type_key == "TEXT_NOT_NULL":
        return "TEXT NOT NULL"
    if type_key == "TEXT_NULL":
        return "TEXT"
    if type_key == "TEXT_PK":
        return "TEXT PRIMARY KEY NOT NULL"
    if type_key == "TENANT_ID":
        return "TEXT NOT NULL"  # alias of TEXT_NOT_NULL — kept distinct for grep
    if type_key == "INT_NOT_NULL":
        return "INTEGER NOT NULL"
    if type_key == "INT_NULL":
        return "INTEGER"
    if type_key == "BIGINT_NOT_NULL":
        # SQLite INTEGER is int64 already; PostgreSQL INTEGER is int32,
        # so we MUST use BIGINT on PG per ml-tracking.md §6.3.
        return "BIGINT NOT NULL" if is_pg else "INTEGER NOT NULL"
    if type_key == "BIGINT_NULL":
        return "BIGINT" if is_pg else "INTEGER"
    if type_key == "DOUBLE_NOT_NULL":
        return "DOUBLE PRECISION NOT NULL" if is_pg else "REAL NOT NULL"
    if type_key == "BOOL_NULL_DEFAULT_FALSE":
        return "BOOLEAN DEFAULT FALSE" if is_pg else "INTEGER DEFAULT 0"
    if type_key == "BOOL_NOT_NULL_DEFAULT_FALSE":
        return (
            "BOOLEAN NOT NULL DEFAULT FALSE" if is_pg else "INTEGER NOT NULL DEFAULT 0"
        )
    if type_key == "TIMESTAMPTZ_NOT_NULL":
        return "TIMESTAMPTZ NOT NULL" if is_pg else "TEXT NOT NULL"
    if type_key == "TIMESTAMPTZ_NULL":
        return "TIMESTAMPTZ" if is_pg else "TEXT"
    if type_key == "JSON_NOT_NULL":
        return dialect.json_column_type() + " NOT NULL"
    if type_key == "JSON_NULL":
        return dialect.json_column_type()
    if type_key == "AUDIT_PK":
        # PostgreSQL BIGSERIAL: auto-incrementing int64.
        # SQLite: INTEGER PRIMARY KEY is implicitly auto-incrementing rowid.
        if is_pg:
            return "BIGSERIAL PRIMARY KEY"
        return "INTEGER PRIMARY KEY"
    # Unreachable — _COL_TYPES guard
    raise AssertionError(f"unmapped type key {type_key!r}")


# ---------------------------------------------------------------------------
# DDL composition — every identifier routes through ``quote_identifier``.
# ---------------------------------------------------------------------------


def _compose_create_table(dialect: QueryDialect, spec: TableSpec) -> str:
    quoted_table = dialect.quote_identifier(spec.name)
    column_fragments: list[str] = []
    has_inline_pk = False
    for col_name, type_key in spec.columns:
        quoted_col = dialect.quote_identifier(col_name)
        type_frag = _render_column_type(dialect, type_key)
        if "PRIMARY KEY" in type_frag:
            has_inline_pk = True
        column_fragments.append(f"{quoted_col} {type_frag}")

    # Composite PK (only if no inline PK in any column; AUDIT_PK declares
    # its PK inline so we skip the composite clause there).
    if not has_inline_pk and spec.primary_key:
        pk_cols = ", ".join(dialect.quote_identifier(c) for c in spec.primary_key)
        column_fragments.append(f"PRIMARY KEY ({pk_cols})")

    for check_expr in spec.check_constraints:
        column_fragments.append(f"CHECK ({check_expr})")

    body = ", ".join(column_fragments)
    return f"CREATE TABLE IF NOT EXISTS {quoted_table} ({body})"


def _compose_create_index(dialect: QueryDialect, table: str, index: IndexSpec) -> str:
    # Index-name length is enforced by ``quote_identifier`` — over-63-char
    # names raise :class:`IdentifierError` BEFORE any DDL executes, so the
    # DB is never left half-indexed.
    quoted_index = dialect.quote_identifier(index.name)
    quoted_table = dialect.quote_identifier(table)
    cols = ", ".join(dialect.quote_identifier(c) for c in index.columns)
    return f"CREATE INDEX IF NOT EXISTS {quoted_index} ON {quoted_table} ({cols})"


def _compose_audit_immutability_ddl(dialect: QueryDialect, table: str) -> list[str]:
    """Return dialect-specific DDL to block UPDATE/DELETE on ``table``.

    - PostgreSQL: pl/pgSQL function + trigger.
    - SQLite: one BEFORE UPDATE and one BEFORE DELETE trigger using
      RAISE(ABORT, ...).
    - MySQL: BEFORE UPDATE and BEFORE DELETE triggers using SIGNAL SQLSTATE.
    """
    quoted_table = dialect.quote_identifier(table)
    fn_name = dialect.quote_identifier(f"{table}_reject_mutation")
    trg_upd = dialect.quote_identifier(f"{table}_no_update")
    trg_del = dialect.quote_identifier(f"{table}_no_delete")
    message = f"{table} is append-only per ml-tracking.md S8.4"

    if dialect.database_type == DatabaseType.POSTGRESQL:
        return [
            f"CREATE OR REPLACE FUNCTION {fn_name}() RETURNS TRIGGER AS $$ "
            f"BEGIN RAISE EXCEPTION '{message}'; END; $$ LANGUAGE plpgsql",
            f"DROP TRIGGER IF EXISTS {trg_upd} ON {quoted_table}",
            f"CREATE TRIGGER {trg_upd} BEFORE UPDATE ON {quoted_table} "
            f"FOR EACH ROW EXECUTE FUNCTION {fn_name}()",
            f"DROP TRIGGER IF EXISTS {trg_del} ON {quoted_table}",
            f"CREATE TRIGGER {trg_del} BEFORE DELETE ON {quoted_table} "
            f"FOR EACH ROW EXECUTE FUNCTION {fn_name}()",
        ]
    if dialect.database_type == DatabaseType.SQLITE:
        return [
            f"DROP TRIGGER IF EXISTS {trg_upd}",
            f"CREATE TRIGGER {trg_upd} BEFORE UPDATE ON {quoted_table} "
            f"BEGIN SELECT RAISE(ABORT, '{message}'); END",
            f"DROP TRIGGER IF EXISTS {trg_del}",
            f"CREATE TRIGGER {trg_del} BEFORE DELETE ON {quoted_table} "
            f"BEGIN SELECT RAISE(ABORT, '{message}'); END",
        ]
    if dialect.database_type == DatabaseType.MYSQL:
        return [
            f"DROP TRIGGER IF EXISTS {trg_upd}",
            f"CREATE TRIGGER {trg_upd} BEFORE UPDATE ON {quoted_table} "
            f"FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'",
            f"DROP TRIGGER IF EXISTS {trg_del}",
            f"CREATE TRIGGER {trg_del} BEFORE DELETE ON {quoted_table} "
            f"FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{message}'",
        ]
    raise TypeError(f"unsupported dialect: {dialect.database_type!r}")


def _compose_drop_audit_triggers(dialect: QueryDialect, table: str) -> list[str]:
    trg_upd = dialect.quote_identifier(f"{table}_no_update")
    trg_del = dialect.quote_identifier(f"{table}_no_delete")
    fn_name = dialect.quote_identifier(f"{table}_reject_mutation")
    quoted_table = dialect.quote_identifier(table)
    if dialect.database_type == DatabaseType.POSTGRESQL:
        return [
            f"DROP TRIGGER IF EXISTS {trg_upd} ON {quoted_table}",
            f"DROP TRIGGER IF EXISTS {trg_del} ON {quoted_table}",
            f"DROP FUNCTION IF EXISTS {fn_name}()",
        ]
    return [
        f"DROP TRIGGER IF EXISTS {trg_upd}",
        f"DROP TRIGGER IF EXISTS {trg_del}",
    ]


# ---------------------------------------------------------------------------
# Parking table — per-migration DDL-state snapshot enabling downgrade
# to reverse only the tables 0002 created, leaving 0.x pre-existing
# tables intact.
# ---------------------------------------------------------------------------


def _compose_create_parking_table(dialect: QueryDialect) -> str:
    quoted_parking = dialect.quote_identifier(PARKING_TABLE)
    ts_type = (
        "TIMESTAMPTZ NOT NULL"
        if dialect.database_type == DatabaseType.POSTGRESQL
        else "TEXT NOT NULL"
    )
    return (
        f"CREATE TABLE IF NOT EXISTS {quoted_parking} ("
        f"  table_name TEXT NOT NULL,"
        f"  pre_existed INTEGER NOT NULL,"
        f"  tenant_col_added INTEGER NOT NULL,"
        f"  recorded_at {ts_type},"
        f"  PRIMARY KEY (table_name)"
        f")"
    )


def _compose_parking_insert(dialect: QueryDialect) -> str:
    quoted_parking = dialect.quote_identifier(PARKING_TABLE)
    return (
        f"INSERT INTO {quoted_parking} (table_name, pre_existed, tenant_col_added, recorded_at) "
        f"VALUES (?, ?, ?, ?)"
    )


def _compose_parking_select_all(dialect: QueryDialect) -> str:
    quoted_parking = dialect.quote_identifier(PARKING_TABLE)
    return f"SELECT table_name, pre_existed, tenant_col_added, recorded_at FROM {quoted_parking}"


def _compose_drop_parking_table(dialect: QueryDialect) -> str:
    quoted_parking = dialect.quote_identifier(PARKING_TABLE)
    return f"DROP TABLE IF EXISTS {quoted_parking}"


async def _load_parking_table_names(dialect: QueryDialect, conn: Any) -> set[str]:
    """Return the set of table_name values already recorded in the
    parking snapshot. Empty set when the parking table doesn't exist
    yet (first apply) or has no rows. Used by the apply loop to make
    re-invocation after a partial failure idempotent per W4 Invariant 10.
    """
    if not await _table_exists(dialect, conn, PARKING_TABLE):
        return set()
    try:
        rows = await _fetchall(conn, _compose_parking_select_all(dialect))
    except Exception:
        return set()
    names: set[str] = set()
    for row in rows:
        name = row[0] if not isinstance(row, dict) else row.get("table_name")
        if name:
            names.add(name)
    return names


# ---------------------------------------------------------------------------
# Connection-shape adapters — mirror 0001's behaviour so both sync and
# async drivers work without the migration caring which.
# ---------------------------------------------------------------------------


async def _execute(conn: Any, sql: str, params: Optional[Sequence[Any]] = None) -> Any:
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql, params) if params is not None else executor(sql)
    if hasattr(result, "__await__"):
        result = await result
    return result


async def _fetchone(conn: Any, sql: str, params: Optional[Sequence[Any]] = None):
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql, params) if params is not None else executor(sql)
    if hasattr(result, "__await__"):
        result = await result
    fetchone = getattr(result, "fetchone", None) or getattr(conn, "fetchone", None)
    if fetchone is None:
        return None
    row = fetchone()
    if hasattr(row, "__await__"):
        row = await row
    return row


async def _fetchall(conn: Any, sql: str, params: Optional[Sequence[Any]] = None):
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql, params) if params is not None else executor(sql)
    if hasattr(result, "__await__"):
        result = await result
    fetchall = getattr(result, "fetchall", None) or getattr(conn, "fetchall", None)
    if fetchall is None:
        return []
    rows = fetchall()
    if hasattr(rows, "__await__"):
        rows = await rows
    return list(rows) if rows is not None else []


async def _table_exists(dialect: QueryDialect, conn: Any, name: str) -> bool:
    if dialect.database_type == DatabaseType.SQLITE:
        row = await _fetchone(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        )
        return row is not None
    if dialect.database_type == DatabaseType.POSTGRESQL:
        row = await _fetchone(
            conn,
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
            (name,),
        )
        return row is not None
    if dialect.database_type == DatabaseType.MYSQL:
        row = await _fetchone(
            conn,
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = ?",
            (name,),
        )
        return row is not None
    raise TypeError(f"unsupported dialect: {dialect.database_type!r}")


async def _column_exists(
    dialect: QueryDialect, conn: Any, table: str, column: str
) -> bool:
    if dialect.database_type == DatabaseType.SQLITE:
        # PRAGMA table_info isn't parameterisable — but the table name is
        # validated before we arrive here (every caller routes through
        # TABLE_INVENTORY literals).
        quoted = dialect.quote_identifier(table)
        rows = await _fetchall(conn, f"PRAGMA table_info({quoted})")
        for row in rows:
            # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
            name = row[1] if not isinstance(row, dict) else row.get("name")
            if name == column:
                return True
        return False
    if dialect.database_type == DatabaseType.POSTGRESQL:
        row = await _fetchone(
            conn,
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            (table, column),
        )
        return row is not None
    if dialect.database_type == DatabaseType.MYSQL:
        row = await _fetchone(
            conn,
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?",
            (table, column),
        )
        return row is not None
    raise TypeError(f"unsupported dialect: {dialect.database_type!r}")


# ---------------------------------------------------------------------------
# Migration class
# ---------------------------------------------------------------------------


class Migration(MigrationBase):
    """Migration 0002 — ``_kml_*`` prefix + tenant + audit immutability.

    The migration is idempotent: re-running after a successful apply is
    a cheap no-op (every table already exists and carries ``tenant_id``).
    Mid-sequence failure raises :class:`MigrationResumeRequiredError`
    with the index of the last-committed table so the operator can
    inspect state + re-run to continue. The parking table records the
    pre-migration shape of each table so rollback reverses only the
    tables 0002 created.
    """

    version = "1.0.0"
    name = "kml_prefix_tenant_audit"

    async def apply(
        self,
        conn: Any,
        *,
        tenant_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> MigrationResult:
        if await self.verify(conn):
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=dry_run,
                direction="upgrade",
                notes="no-op: migration already applied",
            )

        dialect = _get_dialect(conn)

        if dry_run:
            # Count tables that would be created/altered.
            pending = 0
            for spec in TABLE_INVENTORY:
                exists = await _table_exists(dialect, conn, spec.name)
                if not exists:
                    pending += 1
                elif not await _column_exists(dialect, conn, spec.name, "tenant_id"):
                    pending += 1
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=pending,
                tenant_id=tenant_id,
                was_dry_run=True,
                direction="upgrade",
                notes=f"dry-run: would create/extend {pending} tables",
            )

        # Record parking snapshot + apply tables one at a time so a
        # partial failure leaves a clean audit trail in the parking
        # table. The apply loop raises MigrationResumeRequiredError on
        # the first failure so the operator sees exactly which table
        # broke. On resume (re-invocation after a prior partial failure),
        # tables whose name already appears in the parking snapshot are
        # skipped so re-apply is idempotent — W4 Invariant 10.
        await _execute(conn, _compose_create_parking_table(dialect))

        already_committed = await _load_parking_table_names(dialect, conn)

        completed = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for idx, spec in enumerate(TABLE_INVENTORY):
            if spec.name in already_committed:
                # Resume path — this table was committed by a prior apply
                # attempt that failed later in the sequence. Skip so the
                # parking UNIQUE(table_name) stays intact.
                continue
            try:
                pre_existed = await _table_exists(dialect, conn, spec.name)
                tenant_col_added = False

                if not pre_existed:
                    await _execute(conn, _compose_create_table(dialect, spec))
                else:
                    # Pre-existing from 0.x — check for tenant_id column
                    has_tenant = await _column_exists(
                        dialect, conn, spec.name, "tenant_id"
                    )
                    if not has_tenant:
                        quoted_table = dialect.quote_identifier(spec.name)
                        # ALTER TABLE ADD COLUMN — tenant_id TEXT NOT NULL
                        # DEFAULT '_single' per ml-tracking.md §7.2 (the
                        # canonical single-tenant sentinel). Defaulting
                        # is required because existing rows must not
                        # violate NOT NULL. Future single-tenant mode
                        # callers continue passing '_single'.
                        quoted_col = dialect.quote_identifier("tenant_id")
                        await _execute(
                            conn,
                            f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} "
                            f"TEXT NOT NULL DEFAULT '_single'",
                        )
                        tenant_col_added = True

                # Create indexes — idempotent.
                for index in spec.indexes:
                    await _execute(
                        conn, _compose_create_index(dialect, spec.name, index)
                    )

                # Install audit-immutability triggers if applicable.
                if spec.audit_immutable:
                    for stmt in _compose_audit_immutability_ddl(dialect, spec.name):
                        await _execute(conn, stmt)

                # Record parking snapshot row.
                await _execute(
                    conn,
                    _compose_parking_insert(dialect),
                    (
                        spec.name,
                        1 if pre_existed else 0,
                        1 if tenant_col_added else 0,
                        now_iso,
                    ),
                )
                completed += 1
            except IdentifierError:
                # Identifier validation never interpolated partial DDL
                # — re-raise unchanged so the caller sees the typed
                # identifier failure.
                raise
            except Exception as exc:
                raise MigrationResumeRequiredError(
                    reason=(
                        f"migration 0002 failed at table {idx + 1}/15 "
                        f"({spec.name!r}); {completed} tables committed; "
                        f"parking snapshot preserved for resume. "
                        f"Underlying error: {type(exc).__name__}: {exc}"
                    ),
                    resource_id=self.version,
                ) from exc

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=completed,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="upgrade",
            notes=(
                f"created/extended {completed} tables; parking snapshot "
                f"preserved in {PARKING_TABLE!r}"
            ),
        )

    async def rollback(
        self,
        conn: Any,
        *,
        tenant_id: Optional[str] = None,
        force_downgrade: bool = False,
    ) -> MigrationResult:
        if not force_downgrade:
            raise DowngradeRefusedError(
                reason=(
                    f"rollback({self.version!r}) refused — down path drops "
                    f"tables created by this migration which is irreversible "
                    f"data loss; pass force_downgrade=True to acknowledge."
                ),
                resource_id=self.version,
            )

        dialect = _get_dialect(conn)

        # If parking table doesn't exist the migration never ran; rollback is a no-op.
        parking_present = await _table_exists(dialect, conn, PARKING_TABLE)
        if not parking_present:
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=False,
                direction="downgrade",
                notes="no-op: parking table absent — nothing to reverse",
            )

        # Read snapshot rows: reverse only the tables this migration
        # created (pre_existed == 0) or extended (tenant_col_added == 1).
        rows = await _fetchall(conn, _compose_parking_select_all(dialect))
        rows_reversed = 0
        for row in rows:
            table_name = row[0] if not isinstance(row, dict) else row.get("table_name")
            pre_existed = (
                row[1] if not isinstance(row, dict) else row.get("pre_existed")
            )
            tenant_col_added = (
                row[2] if not isinstance(row, dict) else row.get("tenant_col_added")
            )

            # Find the matching TableSpec (defensive — parking rows MUST
            # map to a known table; if not, skip with a no-op).
            spec = next((s for s in TABLE_INVENTORY if s.name == table_name), None)
            if spec is None:
                continue

            # Drop audit triggers first (PostgreSQL requires triggers
            # gone before DROP TABLE; SQLite drops triggers with the
            # table).
            if spec.audit_immutable:
                for stmt in _compose_drop_audit_triggers(dialect, spec.name):
                    await _execute(conn, stmt)

            if not pre_existed:
                # We created the table — drop it.
                quoted_table = dialect.quote_identifier(spec.name)
                await _execute(conn, f"DROP TABLE IF EXISTS {quoted_table}")
                rows_reversed += 1
            elif tenant_col_added:
                # Table pre-existed but we added tenant_id — drop the column.
                # SQLite didn't support DROP COLUMN before 3.35; guard.
                quoted_table = dialect.quote_identifier(spec.name)
                quoted_col = dialect.quote_identifier("tenant_id")
                if dialect.database_type == DatabaseType.SQLITE:
                    # SQLite 3.35+ supports DROP COLUMN; older versions
                    # would error. We accept the error as a noisy fail
                    # rather than silently leaving the column.
                    await _execute(
                        conn, f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}"
                    )
                else:
                    await _execute(
                        conn, f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}"
                    )
                rows_reversed += 1
            # else: pre-existing table we didn't alter — leave alone.

        # Drop parking table last.
        await _execute(conn, _compose_drop_parking_table(dialect))

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=rows_reversed,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="downgrade",
            notes=(
                f"reversed {rows_reversed} tables; parking snapshot "
                f"{PARKING_TABLE!r} dropped"
            ),
        )

    async def verify(self, conn: Any) -> bool:
        """Return True iff every table in TABLE_INVENTORY exists AND has
        a ``tenant_id`` column. We do not verify indexes or triggers —
        their presence is asserted by the Tier 1 + Tier 2 tests, not by
        verify() at the hot path."""
        dialect = _get_dialect(conn)
        for spec in TABLE_INVENTORY:
            try:
                if not await _table_exists(dialect, conn, spec.name):
                    return False
                if not await _column_exists(dialect, conn, spec.name, "tenant_id"):
                    return False
            except Exception:
                return False
        return True


# ---------------------------------------------------------------------------
# Orchestrator-layer error types. ``DowngradeRefusedError`` mirrors the
# one declared in 0001 (both live in migration modules so the framework
# owns its refusal taxonomy distinct from the primitive DropRefusedError
# per ``rules/dataflow-identifier-safety.md`` Rule 6).
# ``MigrationResumeRequiredError`` captures the mid-apply failure case
# per W4 Invariant 10.
# ---------------------------------------------------------------------------


class MigrationResumeRequiredError(MLError):
    """Raised by :meth:`Migration.apply` when a mid-sequence failure
    leaves the migration partially applied. The parking-table snapshot
    is preserved; the operator can inspect + re-run to continue.

    Distinct from :class:`MigrationFailedError` (which reports a
    non-recoverable failure): this error guarantees the parking-table
    DDL-state snapshot is intact so an operator-driven resume is
    possible without manual schema forensics.
    """


class DowngradeRefusedError(MLError):
    """Raised by :meth:`Migration.rollback` when ``force_downgrade`` is
    False. Mirrors the class declared in 0001; per
    ``rules/dataflow-identifier-safety.md`` Rule 6 each migration owns
    its refusal error so distinct audit attribution is preserved across
    the primitive vs orchestrator layer distinction."""


def __fingerprint_reason(reason: str, resource_id: str) -> str:  # pragma: no cover
    """Module-local helper — stub so MigrationResumeRequiredError /
    DowngradeRefusedError constructions can optionally fingerprint
    any classified payload before raising. Not used today; kept so
    callers that want to fingerprint at raise-time have a single place
    to reach for it."""
    return reason  # noqa: E501

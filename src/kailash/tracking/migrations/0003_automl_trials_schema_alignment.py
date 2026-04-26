# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Migration 0003 — align ``_kml_automl_trials`` to the AutoMLEngine
runtime schema.

The W6-020 follow-up: migration 0002 declared a placeholder seven-column
``_kml_automl_trials`` table (``trial_id``, ``study_id``, ``hyperparams``,
``score``, ``status``, ``tenant_id``, ``created_at``) that was never
written to in production. The actual runtime schema emitted by
``AutoMLEngine._ensure_trials_table`` (now retired) was a
nineteen-column form carrying ``run_id`` / ``actor_id`` / ``trial_number``
/ ``params_json`` / ``metric_name`` / ``metric_value`` /
``cost_microdollars`` / ``started_at`` / ``finished_at`` /
``admission_decision_id`` / ``admission_decision`` / ``error`` /
``source`` / ``fidelity`` / ``rung`` columns.

This migration brings the persisted schema up to the runtime form by:

1. Detecting the placeholder shape (presence of column ``hyperparams``).
2. If the placeholder exists AND has no rows, dropping it.
3. If the placeholder exists WITH rows, raising
   :class:`PlaceholderTablePopulatedError` so an operator can rescue the
   data manually before this migration's destructive rollback path runs.
4. Creating the canonical 19-column ``_kml_automl_trials`` table (and
   companion index ``idx_automl_trials_tenant_run``) in the dialect-portable
   form the engine had been emitting inline.
5. Recording the pre-migration shape (``placeholder_present``,
   ``rows_at_apply``) in the parking table
   ``_kml_migration_0003_state_snapshot`` so :meth:`Migration.rollback`
   can reverse only what this migration changed.

Spec trace
----------
- ``specs/ml-automl.md §8A.2`` — first-use DDL discipline; this migration
  is the W6 numbered-migration that supersedes the lazy DDL path.
- ``specs/kailash-core-ml-integration.md §4`` — migration framework
  contract.

Rule trace
----------
- ``rules/schema-migration.md`` Rule 1 (numbered migrations only),
  Rule 3 (reversible), Rule 4 (append-only — this is a NEW migration,
  NOT an edit to 0002), Rule 5 (real PG + SQLite test), Rule 7
  (``force_downgrade=True`` required on destructive rollback).
- ``rules/dataflow-identifier-safety.md`` Rule 1 (every dynamic DDL
  identifier through ``quote_identifier``).

Invariant tests
---------------
- T1 unit (``tests/unit/tracking/test_migration_0003.py``): verifies
  the column/index inventory and identifier-length compliance using
  the DDL-composition helpers (no DB roundtrip).
- T2 integration
  (``packages/kailash-ml/tests/integration/test_kml_automl_trials_migration.py``):
  fresh DB without migration → ``MigrationRequiredError`` from the
  engine; after migration applied → engine writes + reads trial rows
  through the canonical 19-column schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from kailash.db.dialect import (
    DatabaseType,
    PostgresDialect,
    MySQLDialect,
    QueryDialect,
    SQLiteDialect,
)
from kailash.ml.errors import MLError
from kailash.tracking.migrations._base import MigrationBase, MigrationResult

__all__ = [
    "Migration",
    "DowngradeRefusedError",
    "PlaceholderTablePopulatedError",
    "AUTOML_TRIALS_TABLE",
    "AUTOML_TRIALS_INDEX",
    "PARKING_TABLE",
]


# Canonical names — single source of truth used by the migration AND
# by the engine on probe. The engine module re-imports these so they
# cannot drift independently.
AUTOML_TRIALS_TABLE = "_kml_automl_trials"
AUTOML_TRIALS_INDEX = "idx_automl_trials_tenant_run"
PARKING_TABLE = "_kml_migration_0003_state_snapshot"


# Sentinel column that uniquely identifies the placeholder schema from
# 0002. The placeholder declared ``hyperparams`` (JSON_NOT_NULL); the
# canonical 19-column form does NOT.
_PLACEHOLDER_SENTINEL_COLUMN = "hyperparams"

# Sentinel column that uniquely identifies the canonical 19-column form.
# Verifying this column's presence is the migration's idempotent guard.
_CANONICAL_SENTINEL_COLUMN = "trial_number"


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
# Connection-shape adapters — mirror 0001/0002's behaviour.
# ---------------------------------------------------------------------------


async def _execute(
    conn: Any, sql: str, params: Optional[tuple[Any, ...]] = None
) -> Any:
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql, params) if params is not None else executor(sql)
    if hasattr(result, "__await__"):
        result = await result
    return result


async def _fetchone(
    conn: Any, sql: str, params: Optional[tuple[Any, ...]] = None
) -> Any:
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
        # PRAGMA table_info isn't parameterisable — but ``table`` is
        # routed through ``quote_identifier`` (validated allowlist) before
        # interpolation per ``rules/dataflow-identifier-safety.md`` Rule 1.
        quoted = dialect.quote_identifier(table)
        executor = getattr(conn, "execute", None)
        result = executor(f"PRAGMA table_info({quoted})")
        if hasattr(result, "__await__"):
            result = await result
        fetchall = getattr(result, "fetchall", None) or getattr(conn, "fetchall", None)
        if fetchall is None:
            return False
        rows = fetchall()
        if hasattr(rows, "__await__"):
            rows = await rows
        for row in rows or []:
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
            "WHERE table_schema = DATABASE() AND table_name = ? "
            "AND column_name = ?",
            (table, column),
        )
        return row is not None
    raise TypeError(f"unsupported dialect: {dialect.database_type!r}")


async def _row_count(dialect: QueryDialect, conn: Any, table: str) -> int:
    quoted = dialect.quote_identifier(table)
    row = await _fetchone(conn, f"SELECT COUNT(*) FROM {quoted}")
    if row is None:
        return 0
    n = row[0] if not isinstance(row, dict) else next(iter(row.values()))
    return int(n) if n is not None else 0


# ---------------------------------------------------------------------------
# DDL composition — every identifier routes through quote_identifier.
# ---------------------------------------------------------------------------


def _compose_create_canonical_table(dialect: QueryDialect) -> str:
    """Return the canonical 19-column DDL for ``_kml_automl_trials``.

    Dialect-portable types (``TEXT`` / ``INTEGER`` / ``REAL``) — the
    same lowest-common-denominator used by the engine's prior inline
    DDL. Postgres-native types (``UUID`` / ``JSONB`` / ``TIMESTAMPTZ``
    / ``BIGSERIAL``) are deferred to a future migration per
    ``specs/ml-automl.md §8A.1``.
    """
    table = dialect.quote_identifier(AUTOML_TRIALS_TABLE)
    cols = []
    for col_name, col_type in (
        ("trial_id", "TEXT PRIMARY KEY"),
        ("run_id", "TEXT NOT NULL"),
        ("tenant_id", "TEXT NOT NULL"),
        ("actor_id", "TEXT NOT NULL"),
        ("trial_number", "INTEGER NOT NULL"),
        ("strategy", "TEXT NOT NULL"),
        ("params_json", "TEXT NOT NULL"),
        ("metric_name", "TEXT NOT NULL"),
        ("metric_value", "REAL"),
        ("cost_microdollars", "INTEGER NOT NULL DEFAULT 0"),
        ("started_at", "TEXT NOT NULL"),
        ("finished_at", "TEXT"),
        ("status", "TEXT NOT NULL"),
        ("admission_decision_id", "TEXT"),
        ("admission_decision", "TEXT"),
        ("error", "TEXT"),
        ("source", "TEXT NOT NULL DEFAULT 'baseline'"),
        ("fidelity", "REAL NOT NULL DEFAULT 1.0"),
        ("rung", "INTEGER NOT NULL DEFAULT 0"),
    ):
        quoted_col = dialect.quote_identifier(col_name)
        cols.append(f"{quoted_col} {col_type}")
    body = ", ".join(cols)
    return f"CREATE TABLE IF NOT EXISTS {table} ({body})"


def _compose_create_canonical_index(dialect: QueryDialect) -> str:
    table = dialect.quote_identifier(AUTOML_TRIALS_TABLE)
    index = dialect.quote_identifier(AUTOML_TRIALS_INDEX)
    cols = ", ".join(
        dialect.quote_identifier(c) for c in ("tenant_id", "run_id", "trial_number")
    )
    return f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({cols})"


def _compose_drop_table(dialect: QueryDialect, table: str) -> str:
    quoted = dialect.quote_identifier(table)
    return f"DROP TABLE IF EXISTS {quoted}"


def _compose_drop_index(dialect: QueryDialect, index: str) -> str:
    if dialect.database_type == DatabaseType.POSTGRESQL:
        quoted = dialect.quote_identifier(index)
        return f"DROP INDEX IF EXISTS {quoted}"
    if dialect.database_type == DatabaseType.SQLITE:
        quoted = dialect.quote_identifier(index)
        return f"DROP INDEX IF EXISTS {quoted}"
    if dialect.database_type == DatabaseType.MYSQL:
        # MySQL DROP INDEX requires the table — caller passes both via
        # _compose_drop_index_mysql below.
        raise TypeError("use _compose_drop_index_mysql for MySQL")
    raise TypeError(f"unsupported dialect: {dialect.database_type!r}")


def _compose_create_parking(dialect: QueryDialect) -> str:
    quoted = dialect.quote_identifier(PARKING_TABLE)
    ts_type = (
        "TIMESTAMPTZ NOT NULL"
        if dialect.database_type == DatabaseType.POSTGRESQL
        else "TEXT NOT NULL"
    )
    return (
        f"CREATE TABLE IF NOT EXISTS {quoted} ("
        f"  scope TEXT PRIMARY KEY,"
        f"  placeholder_present INTEGER NOT NULL,"
        f"  rows_at_apply INTEGER NOT NULL,"
        f"  recorded_at {ts_type}"
        f")"
    )


def _compose_parking_insert(dialect: QueryDialect) -> str:
    quoted = dialect.quote_identifier(PARKING_TABLE)
    return (
        f"INSERT INTO {quoted} (scope, placeholder_present, rows_at_apply, recorded_at) "
        f"VALUES (?, ?, ?, ?)"
    )


def _compose_parking_select(dialect: QueryDialect) -> str:
    quoted = dialect.quote_identifier(PARKING_TABLE)
    return (
        f"SELECT scope, placeholder_present, rows_at_apply, recorded_at FROM {quoted}"
    )


def _compose_drop_parking(dialect: QueryDialect) -> str:
    quoted = dialect.quote_identifier(PARKING_TABLE)
    return f"DROP TABLE IF EXISTS {quoted}"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DowngradeRefusedError(MLError):
    """Raised by :meth:`Migration.rollback` when ``force_downgrade`` is
    False. Mirrors the class declared in 0001/0002 — per
    ``rules/dataflow-identifier-safety.md`` Rule 6 each migration owns
    its refusal error so distinct audit attribution is preserved."""


class PlaceholderTablePopulatedError(MLError):
    """Raised by :meth:`Migration.apply` when the 0002 placeholder
    ``_kml_automl_trials`` table contains rows.

    Migration 0003's destructive path (DROP placeholder + CREATE canonical)
    is gated on the placeholder being empty so no operator data is lost
    silently. When the placeholder has rows, the operator MUST manually
    extract / archive them before re-running this migration. The error
    carries ``rows_present`` in ``context`` so log triage can route to
    the right runbook.
    """


# ---------------------------------------------------------------------------
# Migration class
# ---------------------------------------------------------------------------


class Migration(MigrationBase):
    """Migration 0003 — ``_kml_automl_trials`` schema alignment."""

    version = "1.0.0"
    name = "automl_trials_schema_alignment"

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

        # Detect the placeholder + canonical states without touching DDL.
        table_present = await _table_exists(dialect, conn, AUTOML_TRIALS_TABLE)
        is_placeholder = False
        rows_present = 0
        if table_present:
            is_placeholder = await _column_exists(
                dialect, conn, AUTOML_TRIALS_TABLE, _PLACEHOLDER_SENTINEL_COLUMN
            )
            if is_placeholder:
                rows_present = await _row_count(dialect, conn, AUTOML_TRIALS_TABLE)

        if dry_run:
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=True,
                direction="upgrade",
                notes=(
                    f"dry-run: table_present={table_present}, "
                    f"is_placeholder={is_placeholder}, "
                    f"rows_present={rows_present}"
                ),
            )

        if is_placeholder and rows_present > 0:
            raise PlaceholderTablePopulatedError(
                reason=(
                    f"migration 0003 refuses to drop populated placeholder "
                    f"_kml_automl_trials ({rows_present} rows); manual data "
                    f"rescue required before re-applying"
                ),
                resource_id=AUTOML_TRIALS_TABLE,
                rows_present=rows_present,
            )

        # Record the parking snapshot first so rollback can reverse only
        # what this migration changed (vs. the canonical table that
        # pre-existed from a fresh install with the engine's old inline
        # DDL).
        await _execute(conn, _compose_create_parking(dialect))
        now_iso = datetime.now(timezone.utc).isoformat()
        await _execute(
            conn,
            _compose_parking_insert(dialect),
            (
                "automl_trials_alignment",
                1 if is_placeholder else 0,
                rows_present,
                now_iso,
            ),
        )

        if is_placeholder:
            # Drop empty placeholder + its 0002 indexes. SQLite drops
            # owned indexes implicitly; PG/MySQL too when DROP TABLE.
            await _execute(conn, _compose_drop_table(dialect, AUTOML_TRIALS_TABLE))

        # Create the canonical 19-column table + companion index.
        await _execute(conn, _compose_create_canonical_table(dialect))
        await _execute(conn, _compose_create_canonical_index(dialect))

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=1 if is_placeholder else 0,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="upgrade",
            notes=(
                f"created canonical {AUTOML_TRIALS_TABLE} (19 columns); "
                f"placeholder_dropped={is_placeholder}"
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
                    f"the canonical {AUTOML_TRIALS_TABLE} table which is "
                    f"irreversible data loss; pass force_downgrade=True "
                    f"to acknowledge."
                ),
                resource_id=self.version,
            )

        dialect = _get_dialect(conn)
        # If parking absent the migration never ran; rollback is a no-op.
        if not await _table_exists(dialect, conn, PARKING_TABLE):
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=False,
                direction="downgrade",
                notes="no-op: parking table absent — nothing to reverse",
            )

        # Drop the canonical table + its index.
        if dialect.database_type == DatabaseType.MYSQL:
            quoted_table = dialect.quote_identifier(AUTOML_TRIALS_TABLE)
            quoted_index = dialect.quote_identifier(AUTOML_TRIALS_INDEX)
            await _execute(conn, f"DROP INDEX {quoted_index} ON {quoted_table}")
        else:
            await _execute(conn, _compose_drop_index(dialect, AUTOML_TRIALS_INDEX))
        await _execute(conn, _compose_drop_table(dialect, AUTOML_TRIALS_TABLE))
        await _execute(conn, _compose_drop_parking(dialect))

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=1,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="downgrade",
            notes=f"dropped canonical {AUTOML_TRIALS_TABLE} + parking",
        )

    async def verify(self, conn: Any) -> bool:
        """Return True iff the canonical 19-column table exists.

        Verifies via the canonical sentinel column ``trial_number``
        (absent in the 0002 placeholder shape) so the check is
        unambiguous: presence of ``trial_number`` ⇒ canonical schema is
        in place.
        """
        try:
            dialect = _get_dialect(conn)
            if not await _table_exists(dialect, conn, AUTOML_TRIALS_TABLE):
                return False
            return await _column_exists(
                dialect, conn, AUTOML_TRIALS_TABLE, _CANONICAL_SENTINEL_COLUMN
            )
        except Exception:
            return False

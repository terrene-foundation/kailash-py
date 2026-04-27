# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Migration 0004 — create the canonical ``_kml_lineage`` table.

W7-001 follow-up to ``ml-tracking.md §6.3`` — the lineage table DDL was
declared in the spec at 1.0.0 but the numbered migration was deferred
along with the traversal walker (issue #657). This migration brings the
schema up to the canonical 8-column lineage form so
``ModelRegistry.build_lineage_graph()`` (W7-001) and
``km.lineage(...)`` (W7-001) can traverse it.

Spec trace
----------
- ``specs/ml-tracking.md §6.3`` — DDL declaration (8 columns).
- ``specs/ml-engines-v2-addendum §E10`` — traversal contract.
- ``specs/ml-tracking.md §7.1`` — lineage cache key
  ``kailash_ml:v1:{tenant_id}:lineage:{name}:{version}``.

Rule trace
----------
- ``rules/schema-migration.md`` Rule 1 (numbered migrations only),
  Rule 3 (reversible), Rule 4 (append-only — this is a NEW migration,
  NOT an edit to 0003), Rule 5 (real PG + SQLite test), Rule 7
  (``force_downgrade=True`` required on destructive rollback).
- ``rules/dataflow-identifier-safety.md`` Rule 1 (every dynamic DDL
  identifier through ``quote_identifier``).

Invariant tests
---------------
- T2 integration
  (``packages/kailash-ml/tests/integration/test_lineage_graph_wiring.py``):
  fresh DB without migration → ``MigrationRequiredError`` from the
  walker; after migration applied → walker materialises a real
  :class:`~kailash_ml.engines.lineage.LineageGraph`.
- T3 regression
  (``packages/kailash-ml/tests/regression/test_readme_lineage_quickstart.py``):
  end-to-end Quick Start path covers train → register → write
  ``_kml_lineage`` row → ``km.lineage()`` returns the graph.
"""
from __future__ import annotations

from typing import Any, Optional

from kailash.db.dialect import (
    DatabaseType,
    MySQLDialect,
    PostgresDialect,
    QueryDialect,
    SQLiteDialect,
)
from kailash.ml.errors import MLError
from kailash.tracking.migrations._base import MigrationBase, MigrationResult

__all__ = [
    "Migration",
    "DowngradeRefusedError",
    "LINEAGE_TABLE",
    "LINEAGE_INDEX",
]


# Canonical names — single source of truth used by the migration AND
# by ``kailash_ml.engines.lineage.LINEAGE_TABLE``. The two values MUST
# stay byte-for-byte identical so the engine's existence probe and the
# migration's CREATE TABLE write to the same table.
LINEAGE_TABLE = "_kml_lineage"
LINEAGE_INDEX = "idx_kml_lineage_tracker_run_id"


# Sentinel column whose presence proves migration 0004 has been
# applied. Mirrors the ``trial_number`` discipline in 0003.
_CANONICAL_SENTINEL_COLUMN = "tracker_run_id"


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
# Connection-shape adapters — mirror 0003's behaviour byte-for-byte.
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
        if executor is None:
            raise TypeError("conn has no .execute method")
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


# ---------------------------------------------------------------------------
# DDL composition — every identifier routes through quote_identifier.
# ---------------------------------------------------------------------------


def _compose_create_lineage_table(dialect: QueryDialect) -> str:
    """Return the canonical 8-column DDL for ``_kml_lineage``.

    Per ``specs/ml-tracking.md §6.3``::

        CREATE TABLE _kml_lineage (
            tenant_id     TEXT NOT NULL,
            model_name    TEXT NOT NULL,
            version       INTEGER NOT NULL,
            tracker_run_id TEXT NOT NULL,
            parent_version INTEGER,
            training_data_uri TEXT,
            feature_store_version TEXT,
            base_model_uri TEXT,
            PRIMARY KEY (tenant_id, model_name, version)
        )

    Dialect-portable types (``TEXT`` / ``INTEGER``) — the same
    lowest-common-denominator used by 0003. Postgres-native types
    (``UUID`` / ``JSONB`` / ``TIMESTAMPTZ``) deferred to a future
    migration if required.
    """
    table = dialect.quote_identifier(LINEAGE_TABLE)
    cols = []
    for col_name, col_type in (
        ("tenant_id", "TEXT NOT NULL"),
        ("model_name", "TEXT NOT NULL"),
        ("version", "INTEGER NOT NULL"),
        ("tracker_run_id", "TEXT NOT NULL"),
        ("parent_version", "INTEGER"),
        ("training_data_uri", "TEXT"),
        ("feature_store_version", "TEXT"),
        ("base_model_uri", "TEXT"),
    ):
        quoted_col = dialect.quote_identifier(col_name)
        cols.append(f"{quoted_col} {col_type}")
    body = ", ".join(cols)
    pk_cols = ", ".join(
        dialect.quote_identifier(c) for c in ("tenant_id", "model_name", "version")
    )
    return f"CREATE TABLE IF NOT EXISTS {table} ({body}, PRIMARY KEY ({pk_cols}))"


def _compose_create_lineage_index(dialect: QueryDialect) -> str:
    """Index for tracker_run_id lookup (audit-trail correlation)."""
    table = dialect.quote_identifier(LINEAGE_TABLE)
    index = dialect.quote_identifier(LINEAGE_INDEX)
    cols = ", ".join(
        dialect.quote_identifier(c) for c in ("tenant_id", "tracker_run_id")
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
        # MySQL DROP INDEX requires the table — caller composes inline.
        raise TypeError("use inline MySQL DROP INDEX in rollback path")
    raise TypeError(f"unsupported dialect: {dialect.database_type!r}")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DowngradeRefusedError(MLError):
    """Raised by :meth:`Migration.rollback` when ``force_downgrade`` is
    False. Mirrors the per-migration refusal class in 0003 — distinct
    audit attribution per ``rules/schema-migration.md`` Rule 7."""


# ---------------------------------------------------------------------------
# Migration class
# ---------------------------------------------------------------------------


class Migration(MigrationBase):
    """Migration 0004 — create canonical ``_kml_lineage`` table."""

    version = "1.0.0"
    name = "kml_lineage_table"

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
        table_present = await _table_exists(dialect, conn, LINEAGE_TABLE)

        if dry_run:
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=True,
                direction="upgrade",
                notes=f"dry-run: table_present={table_present}",
            )

        # Idempotent — IF NOT EXISTS on table + index. The verify()
        # short-circuit above already returns when the canonical
        # sentinel column is present, so this code only runs when the
        # table is absent (or in a partial state).
        await _execute(conn, _compose_create_lineage_table(dialect))
        await _execute(conn, _compose_create_lineage_index(dialect))

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=0,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="upgrade",
            notes=f"created canonical {LINEAGE_TABLE} (8 columns) + index",
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
                    f"the {LINEAGE_TABLE} table which is irreversible data "
                    f"loss; pass force_downgrade=True to acknowledge."
                ),
                resource_id=self.version,
            )

        dialect = _get_dialect(conn)
        if not await _table_exists(dialect, conn, LINEAGE_TABLE):
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=False,
                direction="downgrade",
                notes="no-op: table absent — nothing to reverse",
            )

        if dialect.database_type == DatabaseType.MYSQL:
            quoted_table = dialect.quote_identifier(LINEAGE_TABLE)
            quoted_index = dialect.quote_identifier(LINEAGE_INDEX)
            await _execute(conn, f"DROP INDEX {quoted_index} ON {quoted_table}")
        else:
            await _execute(conn, _compose_drop_index(dialect, LINEAGE_INDEX))
        await _execute(conn, _compose_drop_table(dialect, LINEAGE_TABLE))

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=1,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="downgrade",
            notes=f"dropped {LINEAGE_TABLE} + index",
        )

    async def verify(self, conn: Any) -> bool:
        """Return True iff the canonical ``_kml_lineage`` table exists.

        Verifies via the canonical sentinel column ``tracker_run_id``
        (a NOT NULL field per ``ml-tracking.md §6.3``) so the check is
        unambiguous: presence of ``tracker_run_id`` ⇒ canonical schema
        is in place.
        """
        try:
            dialect = _get_dialect(conn)
            if not await _table_exists(dialect, conn, LINEAGE_TABLE):
                return False
            return await _column_exists(
                dialect, conn, LINEAGE_TABLE, _CANONICAL_SENTINEL_COLUMN
            )
        except Exception:
            return False

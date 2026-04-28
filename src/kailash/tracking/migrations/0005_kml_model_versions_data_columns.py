# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Migration 0005 — add data-bearing columns to ``_kml_model_versions``.

Closes GH issue #699: three-way schema drift between migration 0002's
canonical 8-column ``_kml_model_versions`` table, ``ModelRegistry``'s
inline DDL (10 columns including 6 data-bearing ones), and spec
§5A.2's 15-column long-term canonical. The IF-NOT-EXISTS in the
inline DDL became a no-op once 0002 had landed, so the registry's
INSERT failed against the migration-canonical schema.

This migration adds the 6 data-bearing columns the registry's read
path depends on (``model_registry.py:148-272`` hydration helper):

- ``metrics_json``    — TEXT NOT NULL DEFAULT '[]'
- ``signature_json``  — TEXT NULL
- ``onnx_status``     — TEXT NOT NULL DEFAULT 'pending'
- ``onnx_error``      — TEXT NULL
- ``artifact_path``   — TEXT NOT NULL DEFAULT ''
- ``model_uuid``      — TEXT NOT NULL DEFAULT ''

The remaining 9 spec §5A.2 columns (``id`` UUID PK, ``format``,
``artifact_uri``, ``artifact_sha256``, ``lineage_*``, ``is_golden``,
``onnx_unsupported_ops``, ``onnx_opset_imports``, ``ort_extensions``,
``actor_id``) are deferred to a sibling 1.6.0 / 1.7.0 workstream —
they require new producer code (lineage tracker integration, sha256
computation, format detection) that does not exist in 1.5.x.

Spec trace
----------
- ``specs/ml-registry.md §5A.2`` — long-term canonical 15-column DDL.
- ``specs/ml-tracking.md §6.3`` — migration framework contract.
- ``workspaces/kailash-ml-1.5.x-followup/02-plans/01-architecture-plan.md``
  § ADR-1 (REVISED) — three-way drift discovery + decision rationale.
- ``workspaces/kailash-ml-1.5.x-followup/journal/0004-DISCOVERY-three-way-schema-drift-mandates-migration-0005.md``
  — 3-way drift evidence + load-bearing read path verification.

Rule trace
----------
- ``rules/schema-migration.md`` Rule 1 (numbered migrations only —
  ModelRegistry's inline DDL was always a Rule 1 violation; this
  migration makes the schema canonical so the inline DDL can be
  deleted), Rule 3 (reversible), Rule 4 (append-only — this is a
  NEW migration, NOT an edit to 0002), Rule 5 (real PG + SQLite
  test), Rule 7 (``force_downgrade=True`` required on destructive
  rollback — ``DROP COLUMN`` is destructive).
- ``rules/dataflow-identifier-safety.md`` Rule 1 (every dynamic DDL
  identifier through ``quote_identifier``), Rule 5 (hardcoded
  identifiers still validated).

Idempotency contract
--------------------
``apply()`` is idempotent: re-running after a successful apply is a
cheap no-op (every column already exists). Mid-sequence failure
between column adds is benign — the next ``apply()`` invocation will
``_column_exists()``-probe each column and add only the missing
ones.

Backwards-compatibility
-----------------------
All 6 columns ship with defaults (or NULL-allowed). Existing rows
(only present if a registry consumer wrote despite the broken
INSERT — none expected since #699 reports the INSERT as failing) get
the defaults. Forward-compatible with PG 9.6+ and SQLite 3.7+.
PG 11+ stores DEFAULT in metadata (no table rewrite); PG <11 may
take a brief table-lock during upgrade — operators on those
versions can either upgrade PG or apply during low-traffic windows.

Invariant tests
---------------
- T1 unit: enumerates the 6 ADDED_COLUMNS list, asserts each routes
  through ``dialect.quote_identifier`` (no raw f-string interpolation).
- T2 integration (regression
  ``packages/kailash-ml/tests/regression/test_issue_699_tracker_registry_shared_store.py``):
  ExperimentTracker + ModelRegistry on a shared SQLite store →
  ``register_model`` succeeds → ``get_model`` round-trip surfaces
  the metrics + signature + artifact_path + model_uuid.
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
    "TARGET_TABLE",
    "ADDED_COLUMNS",
]


# Target table — the canonical name owned by migration 0002. The two
# values MUST stay byte-for-byte identical so this migration's ALTER
# TABLE writes against the same table 0002 created.
TARGET_TABLE = "_kml_model_versions"


# Column adds — ``(name, sqlite_type_fragment, postgres_type_fragment)``.
# Every column carries a default (or NULL-allowed) so the ALTER TABLE
# ADD COLUMN succeeds against tables that already have rows. The
# ``DEFAULT`` literal is dialect-portable text per spec §5A.2.
#
# SQLite uses ``TEXT`` for TEXT-typed columns; PostgreSQL also uses
# ``TEXT`` (same spelling on both dialects, per ``ml-tracking.md``
# §6.3 lowest-common-denominator rule). MySQL would use ``TEXT`` as
# well — kept the per-dialect tuple for forward portability if a
# future column type diverges.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # (column_name, sqlite_type_with_default, postgres_type_with_default)
    ("metrics_json", "TEXT NOT NULL DEFAULT '[]'", "TEXT NOT NULL DEFAULT '[]'"),
    ("signature_json", "TEXT", "TEXT"),
    (
        "onnx_status",
        "TEXT NOT NULL DEFAULT 'pending'",
        "TEXT NOT NULL DEFAULT 'pending'",
    ),
    ("onnx_error", "TEXT", "TEXT"),
    ("artifact_path", "TEXT NOT NULL DEFAULT ''", "TEXT NOT NULL DEFAULT ''"),
    ("model_uuid", "TEXT NOT NULL DEFAULT ''", "TEXT NOT NULL DEFAULT ''"),
)


# Sentinel column whose presence proves migration 0005 has been
# applied. Mirrors the discipline used by 0003 / 0004 — pick the
# first NOT-NULL-DEFAULT column so a presence probe is unambiguous.
_CANONICAL_SENTINEL_COLUMN = "metrics_json"


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
# Connection-shape adapters — mirror 0004's behaviour byte-for-byte.
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


def _column_type_for_dialect(
    dialect: QueryDialect, sqlite_type: str, pg_type: str
) -> str:
    """Return the type fragment for the target dialect.

    Both fragments include the inline DEFAULT (when applicable) so
    the call site need not interpolate any DDL beyond the quoted
    identifier + this opaque type fragment.
    """
    if dialect.database_type == DatabaseType.POSTGRESQL:
        return pg_type
    # SQLite + MySQL share the same TEXT / TEXT NOT NULL form for the
    # 6 columns this migration adds.
    return sqlite_type


def _compose_add_column(
    dialect: QueryDialect, table: str, column: str, type_fragment: str
) -> str:
    """Return ``ALTER TABLE <table> ADD COLUMN <column> <type>``.

    Both identifiers route through ``quote_identifier`` so any
    invalid input raises :class:`IdentifierError` BEFORE the DDL
    fires. The type fragment is a curated literal from
    :data:`ADDED_COLUMNS` — never user-supplied.
    """
    quoted_table = dialect.quote_identifier(table)
    quoted_col = dialect.quote_identifier(column)
    return f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_col} {type_fragment}"


def _compose_drop_column(dialect: QueryDialect, table: str, column: str) -> str:
    """Return ``ALTER TABLE <table> DROP COLUMN <column>``.

    SQLite 3.35+ supports DROP COLUMN; older versions raise — we
    accept the noisy error rather than silently leaving the column.
    Per ``rules/schema-migration.md`` Rule 7 the orchestrator already
    refused unless ``force_downgrade=True`` was explicitly passed.
    """
    quoted_table = dialect.quote_identifier(table)
    quoted_col = dialect.quote_identifier(column)
    return f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DowngradeRefusedError(MLError):
    """Raised by :meth:`Migration.rollback` when ``force_downgrade`` is
    False. Mirrors the per-migration refusal class in 0002 / 0004 —
    distinct audit attribution per ``rules/schema-migration.md`` Rule 7.
    """


class MissingTargetTableError(MLError):
    """Raised by :meth:`Migration.apply` when ``_kml_model_versions``
    does not exist. Migration 0002 owns the table; 0005 only adds
    columns, so an absent table indicates 0002 has not run — the
    operator MUST apply 0002 first via the migration registry.
    """


# ---------------------------------------------------------------------------
# Migration class
# ---------------------------------------------------------------------------


class Migration(MigrationBase):
    """Migration 0005 — add data-bearing columns to ``_kml_model_versions``.

    The migration is idempotent: re-running after a successful apply
    is a cheap no-op (every column already exists). Each column add
    is independently probed via ``_column_exists`` so a partial
    failure leaves a clean state — the next apply picks up where the
    previous one stopped.
    """

    version = "1.0.0"
    name = "kml_model_versions_data_columns"

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

        # Migration 0002 owns ``_kml_model_versions`` — refuse to
        # extend a table this migration didn't create. Operator MUST
        # apply 0002 first via ``MigrationRegistry.apply_pending``.
        if not await _table_exists(dialect, conn, TARGET_TABLE):
            raise MissingTargetTableError(
                reason=(
                    f"{TARGET_TABLE!r} does not exist; migration 0002 has "
                    f"not been applied. Run "
                    f"``MigrationRegistry.apply_pending(conn)`` to bring "
                    f"the schema up to the canonical form before applying "
                    f"0005."
                ),
                resource_id=TARGET_TABLE,
            )

        # Count missing columns first so dry_run reports accurately.
        missing: list[tuple[str, str, str]] = []
        for col_name, sqlite_type, pg_type in ADDED_COLUMNS:
            if not await _column_exists(dialect, conn, TARGET_TABLE, col_name):
                missing.append((col_name, sqlite_type, pg_type))

        if dry_run:
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=len(missing),
                tenant_id=tenant_id,
                was_dry_run=True,
                direction="upgrade",
                notes=(
                    f"dry-run: would add {len(missing)} columns to "
                    f"{TARGET_TABLE}: {[c[0] for c in missing]}"
                ),
            )

        added = 0
        for col_name, sqlite_type, pg_type in missing:
            type_fragment = _column_type_for_dialect(dialect, sqlite_type, pg_type)
            await _execute(
                conn,
                _compose_add_column(dialect, TARGET_TABLE, col_name, type_fragment),
            )
            added += 1

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=added,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="upgrade",
            notes=(
                f"added {added} data-bearing column(s) to {TARGET_TABLE}: "
                f"{[c[0] for c in missing]}"
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
                    f"6 data-bearing columns from {TARGET_TABLE} which is "
                    f"irreversible data loss; pass force_downgrade=True to "
                    f"acknowledge per rules/schema-migration.md Rule 7."
                ),
                resource_id=self.version,
            )

        dialect = _get_dialect(conn)

        # If the target table is absent the migration never ran;
        # rollback is a no-op.
        if not await _table_exists(dialect, conn, TARGET_TABLE):
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=0,
                tenant_id=tenant_id,
                was_dry_run=False,
                direction="downgrade",
                notes=f"no-op: {TARGET_TABLE} absent — nothing to reverse",
            )

        dropped = 0
        # Drop in reverse order so the sentinel column is the LAST
        # to go — verify() will return False the moment it's gone,
        # so a partial-failure rollback can be re-invoked safely.
        for col_name, _sqlite_type, _pg_type in reversed(ADDED_COLUMNS):
            if await _column_exists(dialect, conn, TARGET_TABLE, col_name):
                await _execute(
                    conn, _compose_drop_column(dialect, TARGET_TABLE, col_name)
                )
                dropped += 1

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=dropped,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="downgrade",
            notes=(
                f"dropped {dropped} column(s) from {TARGET_TABLE}; "
                f"data was irreversibly lost"
            ),
        )

    async def verify(self, conn: Any) -> bool:
        """Return True iff every column in :data:`ADDED_COLUMNS` exists.

        Verifies via the canonical sentinel column ``metrics_json``
        first (cheap short-circuit), then walks the full column set
        so a partially-applied state surfaces as ``False`` (the next
        ``apply()`` invocation picks up the missing columns).
        """
        try:
            dialect = _get_dialect(conn)
            if not await _table_exists(dialect, conn, TARGET_TABLE):
                return False
            # Canonical sentinel — short-circuit the common case.
            if not await _column_exists(
                dialect, conn, TARGET_TABLE, _CANONICAL_SENTINEL_COLUMN
            ):
                return False
            for col_name, _sqlite_type, _pg_type in ADDED_COLUMNS:
                if not await _column_exists(dialect, conn, TARGET_TABLE, col_name):
                    return False
            return True
        except Exception:
            return False

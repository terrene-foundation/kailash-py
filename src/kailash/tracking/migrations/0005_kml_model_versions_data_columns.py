# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Migration 0005 — registry data columns + private bookkeeping tables.

Closes GH issue #699: three-way schema drift between migration 0002's
canonical 8-column ``_kml_model_versions`` table, ``ModelRegistry``'s
inline DDL (10 columns including 6 data-bearing ones), and spec
§5A.2's 15-column long-term canonical. The IF-NOT-EXISTS in the
inline DDL became a no-op once 0002 had landed, so the registry's
INSERT failed against the migration-canonical schema.

This migration does TWO related things:

1. **Adds 6 data-bearing columns to migration 0002's
   ``_kml_model_versions``** — the columns the registry's read path
   depends on (``model_registry.py:148-272`` hydration helper):

   - ``metrics_json``    — TEXT NOT NULL DEFAULT '[]'
   - ``signature_json``  — TEXT NULL
   - ``onnx_status``     — TEXT NOT NULL DEFAULT 'pending'
   - ``onnx_error``      — TEXT NULL
   - ``artifact_path``   — TEXT NOT NULL DEFAULT ''
   - ``model_uuid``      — TEXT NOT NULL DEFAULT ''

2. **Creates 2 registry-private bookkeeping tables** that ModelRegistry
   previously created via inline DDL (Rule 1 violation):

   - ``_kml_models`` — name → latest_version mapping (tenant-scoped).
   - ``_kml_model_transitions`` — audit trail of stage transitions.

   Both gain a ``tenant_id`` dimension to match the rest of the
   ``_kml_*`` schema per ``rules/tenant-isolation.md`` Rule 1.

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
  rollback — ``DROP COLUMN`` and ``DROP TABLE`` are destructive).
- ``rules/dataflow-identifier-safety.md`` Rule 1 (every dynamic DDL
  identifier through ``quote_identifier``), Rule 5 (hardcoded
  identifiers still validated).
- ``rules/tenant-isolation.md`` Rule 1 (every multi-tenant write-path
  store carries a ``tenant_id`` dimension).

Idempotency contract
--------------------
``apply()`` is idempotent: re-running after a successful apply is a
cheap no-op (every column exists; both tables exist). Mid-sequence
failure between adds is benign — the next ``apply()`` invocation
will probe each surface and add only the missing pieces.

Backwards-compatibility
-----------------------
All 6 added columns ship with defaults (or NULL-allowed). Existing
rows (only present if a registry consumer wrote despite the broken
INSERT — none expected since #699 reports the INSERT as failing) get
the defaults. The two new tables use ``CREATE TABLE IF NOT EXISTS``
so any prior inline-DDL state is left intact and the new schema
takes over write paths once the inline DDL is deleted from
``model_registry.py``.

Forward-compatible with PG 9.6+ and SQLite 3.7+. PG 11+ stores
DEFAULT in metadata (no table rewrite); PG <11 may take a brief
table-lock during upgrade — operators on those versions can either
upgrade PG or apply during low-traffic windows.

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
    "MissingTargetTableError",
    "TARGET_TABLE",
    "ADDED_COLUMNS",
    "MODELS_TABLE",
    "TRANSITIONS_TABLE",
]


# Target table — the canonical name owned by migration 0002. This
# value MUST stay byte-for-byte identical so the ALTER TABLE writes
# against the same table 0002 created.
TARGET_TABLE = "_kml_model_versions"

# Registry-private bookkeeping tables — created by this migration
# with a tenant_id dimension. Previously emitted by ModelRegistry's
# inline DDL (Rule 1 violation); now owned by the migration framework.
MODELS_TABLE = "_kml_models"
TRANSITIONS_TABLE = "_kml_model_transitions"


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


def _compose_create_models_table(dialect: QueryDialect) -> str:
    """Compose ``CREATE TABLE _kml_models (...)`` — tenant-scoped.

    Schema:
        tenant_id        TEXT NOT NULL
        model_name       TEXT NOT NULL
        latest_version   INTEGER NOT NULL DEFAULT 0
        created_at       TEXT NOT NULL
        updated_at       TEXT NOT NULL
        PRIMARY KEY (tenant_id, model_name)

    Composite PK ``(tenant_id, model_name)`` mirrors the other
    ``_kml_*`` tables in migration 0002. ``model_name`` (not ``name``)
    matches migration 0002's ``_kml_model_versions`` column naming.
    """
    table = dialect.quote_identifier(MODELS_TABLE)
    cols = []
    for col_name, col_type in (
        ("tenant_id", "TEXT NOT NULL"),
        ("model_name", "TEXT NOT NULL"),
        ("latest_version", "INTEGER NOT NULL DEFAULT 0"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
    ):
        cols.append(f"{dialect.quote_identifier(col_name)} {col_type}")
    body = ", ".join(cols)
    pk_cols = ", ".join(
        dialect.quote_identifier(c) for c in ("tenant_id", "model_name")
    )
    return f"CREATE TABLE IF NOT EXISTS {table} ({body}, PRIMARY KEY ({pk_cols}))"


def _compose_create_transitions_table(dialect: QueryDialect) -> str:
    """Compose ``CREATE TABLE _kml_model_transitions (...)`` — tenant-scoped.

    Schema:
        id                TEXT NOT NULL  (UUID, PK)
        tenant_id         TEXT NOT NULL
        model_name        TEXT NOT NULL
        version           INTEGER NOT NULL
        from_stage        TEXT NOT NULL
        to_stage          TEXT NOT NULL
        reason            TEXT NOT NULL DEFAULT ''
        transitioned_at   TEXT NOT NULL
        PRIMARY KEY (id)

    ``id`` is the UUID of the transition event. ``model_name`` (not
    ``name``) matches migration 0002's column naming. ``tenant_id``
    is required so transition queries scope to the caller's tenant.
    """
    table = dialect.quote_identifier(TRANSITIONS_TABLE)
    cols = []
    for col_name, col_type in (
        ("id", "TEXT NOT NULL"),
        ("tenant_id", "TEXT NOT NULL"),
        ("model_name", "TEXT NOT NULL"),
        ("version", "INTEGER NOT NULL"),
        ("from_stage", "TEXT NOT NULL"),
        ("to_stage", "TEXT NOT NULL"),
        ("reason", "TEXT NOT NULL DEFAULT ''"),
        ("transitioned_at", "TEXT NOT NULL"),
    ):
        cols.append(f"{dialect.quote_identifier(col_name)} {col_type}")
    body = ", ".join(cols)
    pk_col = dialect.quote_identifier("id")
    return f"CREATE TABLE IF NOT EXISTS {table} ({body}, PRIMARY KEY ({pk_col}))"


def _compose_drop_table(dialect: QueryDialect, table: str) -> str:
    quoted = dialect.quote_identifier(table)
    return f"DROP TABLE IF EXISTS {quoted}"


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
    """Migration 0005 — registry data columns + private bookkeeping tables.

    The migration is idempotent: re-running after a successful apply
    is a cheap no-op (every column / table already exists). Each
    surface (column add OR table create) is independently probed so
    a partial failure leaves a clean state — the next apply picks
    up where the previous one stopped.
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

        # Probe pending column adds.
        missing_cols: list[tuple[str, str, str]] = []
        for col_name, sqlite_type, pg_type in ADDED_COLUMNS:
            if not await _column_exists(dialect, conn, TARGET_TABLE, col_name):
                missing_cols.append((col_name, sqlite_type, pg_type))

        # Probe pending table creates.
        models_missing = not await _table_exists(dialect, conn, MODELS_TABLE)
        transitions_missing = not await _table_exists(dialect, conn, TRANSITIONS_TABLE)

        pending_total = (
            len(missing_cols)
            + (1 if models_missing else 0)
            + (1 if transitions_missing else 0)
        )

        if dry_run:
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=pending_total,
                tenant_id=tenant_id,
                was_dry_run=True,
                direction="upgrade",
                notes=(
                    f"dry-run: would add {len(missing_cols)} columns to "
                    f"{TARGET_TABLE} ({[c[0] for c in missing_cols]}) "
                    f"and create "
                    f"{[t for t, m in [(MODELS_TABLE, models_missing), (TRANSITIONS_TABLE, transitions_missing)] if m]}"
                ),
            )

        added = 0
        for col_name, sqlite_type, pg_type in missing_cols:
            type_fragment = _column_type_for_dialect(dialect, sqlite_type, pg_type)
            await _execute(
                conn,
                _compose_add_column(dialect, TARGET_TABLE, col_name, type_fragment),
            )
            added += 1

        if models_missing:
            await _execute(conn, _compose_create_models_table(dialect))
            added += 1

        if transitions_missing:
            await _execute(conn, _compose_create_transitions_table(dialect))
            added += 1

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=added,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="upgrade",
            notes=(
                f"added {len(missing_cols)} column(s) to {TARGET_TABLE} "
                f"and created {(1 if models_missing else 0) + (1 if transitions_missing else 0)} "
                f"registry-private table(s)"
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
                    f"6 columns from {TARGET_TABLE} and 2 registry-private "
                    f"tables ({MODELS_TABLE!r}, {TRANSITIONS_TABLE!r}); "
                    f"this is irreversible data loss. Pass "
                    f"force_downgrade=True to acknowledge per "
                    f"rules/schema-migration.md Rule 7."
                ),
                resource_id=self.version,
            )

        dialect = _get_dialect(conn)

        reversed_count = 0

        # Drop registry-private tables first (no dependencies).
        for table_name in (TRANSITIONS_TABLE, MODELS_TABLE):
            if await _table_exists(dialect, conn, table_name):
                await _execute(conn, _compose_drop_table(dialect, table_name))
                reversed_count += 1

        # If the target table is absent the column-add migration never
        # ran for that table; skip the column-drop loop.
        if not await _table_exists(dialect, conn, TARGET_TABLE):
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=reversed_count,
                tenant_id=tenant_id,
                was_dry_run=False,
                direction="downgrade",
                notes=(
                    f"reversed {reversed_count} table(s); {TARGET_TABLE} "
                    f"absent — column-drop loop skipped"
                ),
            )

        # Drop columns in reverse order so the sentinel column is the
        # LAST to go — verify() will return False the moment it's
        # gone, so a partial-failure rollback can be re-invoked safely.
        for col_name, _sqlite_type, _pg_type in reversed(ADDED_COLUMNS):
            if await _column_exists(dialect, conn, TARGET_TABLE, col_name):
                await _execute(
                    conn, _compose_drop_column(dialect, TARGET_TABLE, col_name)
                )
                reversed_count += 1

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=reversed_count,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="downgrade",
            notes=(
                f"reversed {reversed_count} schema element(s) "
                f"(columns + tables); data was irreversibly lost"
            ),
        )

    async def verify(self, conn: Any) -> bool:
        """Return True iff every column in :data:`ADDED_COLUMNS` exists
        AND both :data:`MODELS_TABLE` / :data:`TRANSITIONS_TABLE` exist.

        Verifies via the canonical sentinel column ``metrics_json``
        first (cheap short-circuit), then walks the full column set
        + table set so a partially-applied state surfaces as
        ``False`` (the next ``apply()`` invocation picks up the
        missing pieces).
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
            if not await _table_exists(dialect, conn, MODELS_TABLE):
                return False
            if not await _table_exists(dialect, conn, TRANSITIONS_TABLE):
                return False
            return True
        except Exception:
            return False

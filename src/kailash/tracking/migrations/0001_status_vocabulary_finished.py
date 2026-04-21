# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Migration 0001 — hard-migrate legacy status aliases into FINISHED.

Closes the kailash-ml 0.x → 1.0 status-vocabulary gap by rewriting every
``_kml_runs.status`` row whose value is in ``{COMPLETED, SUCCESS}`` to
``FINISHED``. The 1.0 enum is locked cross-SDK as
``{RUNNING, FINISHED, FAILED, KILLED}`` per Decision 3.

Pre-migration snapshot is preserved in ``_kml_migration_0001_prior_status``
so :meth:`Migration.rollback` can restore exact prior state when an
operator passes ``force_downgrade=True``.

See ``specs/kailash-core-ml-integration.md §4``,
``specs/ml-tracking.md §3.2 + §3.5``, and
``rules/schema-migration.md`` Rule 7.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from kailash.db.dialect import (
    DatabaseType,
    MySQLDialect,
    PostgresDialect,
    QueryDialect,
    SQLiteDialect,
)
from kailash.ml.errors import MigrationFailedError, MLError
from kailash.tracking.migrations._base import (
    STATUS_ALIASES_LEGACY,
    MigrationBase,
    MigrationResult,
)

PARKING_TABLE = "_kml_migration_0001_prior_status"
RUNS_TABLE = "_kml_runs"


class Migration(MigrationBase):
    version = "1.0.0"
    name = "status_vocabulary_finished"

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
        parking = dialect.quote_identifier(PARKING_TABLE)
        runs = dialect.quote_identifier(RUNS_TABLE)

        if dry_run:
            count = await _count_legacy(conn, runs)
            return MigrationResult.now(
                version=self.version,
                name=self.name,
                rows_migrated=count,
                tenant_id=tenant_id,
                was_dry_run=True,
                direction="upgrade",
                notes=f"dry-run: would rewrite {count} legacy-status rows",
            )

        await _create_parking_table(conn, parking)
        rows_snapshotted = await _snapshot_legacy(conn, parking, runs)
        rows_rewritten = await _rewrite_legacy_to_finished(conn, runs)

        if rows_snapshotted != rows_rewritten:
            raise MigrationFailedError(
                reason=(
                    "snapshot/rewrite row-count mismatch — parking table has "
                    f"{rows_snapshotted} rows; rewrite affected "
                    f"{rows_rewritten} rows. Manual reconciliation required."
                ),
                resource_id=self.version,
            )

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=rows_rewritten,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="upgrade",
            notes=(
                f"rewrote {rows_rewritten} rows from "
                f"{sorted(STATUS_ALIASES_LEGACY)} → FINISHED; parking "
                f"table {PARKING_TABLE!r} preserved for rollback"
            ),
        )

    async def rollback(
        self,
        conn: Any,
        *,
        tenant_id: Optional[str] = None,
        force_downgrade: bool = False,
    ) -> MigrationResult:
        from kailash.db.dialect import IdentifierError  # local to avoid cycle

        if not force_downgrade:
            raise DowngradeRefusedError(
                reason=(
                    f"rollback({self.version!r}) refused — down path restores "
                    f"legacy status aliases from the parking table which "
                    f"destroys the post-migration FINISHED state; pass "
                    f"force_downgrade=True to acknowledge."
                ),
                resource_id=self.version,
            )

        dialect = _get_dialect(conn)
        parking = dialect.quote_identifier(PARKING_TABLE)
        runs = dialect.quote_identifier(RUNS_TABLE)

        try:
            rows_restored = await _restore_from_parking(conn, parking, runs)
        except IdentifierError as e:  # shouldn't happen — literals are safe
            raise MigrationFailedError(
                reason=f"identifier validation failed on rollback: {e}",
                resource_id=self.version,
            ) from e

        return MigrationResult.now(
            version=self.version,
            name=self.name,
            rows_migrated=rows_restored,
            tenant_id=tenant_id,
            was_dry_run=False,
            direction="downgrade",
            notes=(
                f"restored {rows_restored} legacy-status rows from "
                f"parking table {PARKING_TABLE!r}"
            ),
        )

    async def verify(self, conn: Any) -> bool:
        dialect = _get_dialect(conn)
        runs = dialect.quote_identifier(RUNS_TABLE)
        aliases = _literal_list(STATUS_ALIASES_LEGACY)
        try:
            row = await _fetchone(
                conn,
                f"SELECT COUNT(*) AS n FROM {runs} " f"WHERE status IN ({aliases})",
            )
        except Exception:
            # If the table doesn't exist yet, the migration is trivially
            # pending (rows=0) but we keep returning False so apply() is
            # called once the schema is in place.
            return False
        n = row[0] if row else 0
        return int(n) == 0


# ---------------------------------------------------------------------
# Helpers — intentionally module-level so they can be unit-tested in
# isolation from Migration.apply orchestration.
# ---------------------------------------------------------------------


_DIALECT_MAP = {
    DatabaseType.POSTGRESQL: PostgresDialect,
    DatabaseType.SQLITE: SQLiteDialect,
    DatabaseType.MYSQL: MySQLDialect,
}


def _get_dialect(conn: Any) -> QueryDialect:
    """Resolve the dialect helper from whatever connection shape we
    have. Accepts a raw connection with ``.dialect``-attr, a wrapper
    with a ``database_type`` attr (either :class:`DatabaseType` enum or
    dialect name string).
    """
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


def _literal_list(items) -> str:
    """Render a set of string literals as a SQL IN-list. Values are
    themselves members of a closed vocabulary (`STATUS_ALIASES_LEGACY`)
    so literal interpolation is safe — the values never originate from
    user input."""
    quoted = [f"'{v}'" for v in sorted(items)]
    return ", ".join(quoted)


async def _create_parking_table(conn: Any, parking_quoted: str) -> None:
    # Schema intentionally minimal — run_id is the natural key; legacy
    # status is a string from a closed vocabulary; migrated_at is the
    # snapshot timestamp.
    sql = (
        f"CREATE TABLE IF NOT EXISTS {parking_quoted} ("
        "  run_id TEXT NOT NULL, "
        "  old_status TEXT NOT NULL, "
        "  migrated_at TIMESTAMP NOT NULL"
        ")"
    )
    await _execute(conn, sql)


async def _snapshot_legacy(conn: Any, parking_quoted: str, runs_quoted: str) -> int:
    aliases = _literal_list(STATUS_ALIASES_LEGACY)
    now = datetime.now(timezone.utc).isoformat()
    sql = (
        f"INSERT INTO {parking_quoted} (run_id, old_status, migrated_at) "
        f"SELECT run_id, status, '{now}' FROM {runs_quoted} "
        f"WHERE status IN ({aliases})"
    )
    return await _execute_rowcount(conn, sql)


async def _rewrite_legacy_to_finished(conn: Any, runs_quoted: str) -> int:
    aliases = _literal_list(STATUS_ALIASES_LEGACY)
    sql = (
        f"UPDATE {runs_quoted} SET status = 'FINISHED' " f"WHERE status IN ({aliases})"
    )
    return await _execute_rowcount(conn, sql)


async def _restore_from_parking(
    conn: Any, parking_quoted: str, runs_quoted: str
) -> int:
    sql = (
        f"UPDATE {runs_quoted} SET status = ("
        f"  SELECT old_status FROM {parking_quoted} "
        f"  WHERE {parking_quoted}.run_id = {runs_quoted}.run_id"
        f") WHERE run_id IN (SELECT run_id FROM {parking_quoted})"
    )
    return await _execute_rowcount(conn, sql)


async def _count_legacy(conn: Any, runs_quoted: str) -> int:
    aliases = _literal_list(STATUS_ALIASES_LEGACY)
    row = await _fetchone(
        conn,
        f"SELECT COUNT(*) AS n FROM {runs_quoted} WHERE status IN ({aliases})",
    )
    return int(row[0]) if row else 0


# Connection-shape adapters ------------------------------------------


async def _execute(conn: Any, sql: str) -> None:
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql)
    if hasattr(result, "__await__"):
        await result


async def _execute_rowcount(conn: Any, sql: str) -> int:
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql)
    if hasattr(result, "__await__"):
        result = await result
    # Different drivers expose rowcount differently. We accept any of
    # result.rowcount / conn.rowcount (sqlite3) / explicit int return.
    if isinstance(result, int):
        return result
    rowcount = getattr(result, "rowcount", None)
    if rowcount is None:
        rowcount = getattr(conn, "rowcount", None)
    return int(rowcount) if rowcount is not None else 0


async def _fetchone(conn: Any, sql: str):
    executor = getattr(conn, "execute", None)
    if executor is None:
        raise TypeError("conn has no .execute method")
    result = executor(sql)
    if hasattr(result, "__await__"):
        result = await result
    fetchone = getattr(result, "fetchone", None) or getattr(conn, "fetchone", None)
    if fetchone is None:
        return None
    row = fetchone()
    if hasattr(row, "__await__"):
        row = await row
    return row


# ---------------------------------------------------------------------
# DowngradeRefusedError — declared here so the migration framework owns
# its own refusal error distinct from the primitive DropRefusedError.
# Per `dataflow-identifier-safety.md` Rule 6 primitive vs orchestrator
# layer distinction.
# ---------------------------------------------------------------------


class DowngradeRefusedError(MLError):
    """Raised by :meth:`MigrationBase.rollback` when ``force_downgrade``
    is False and the down path is destructive / non-trivially
    irreversible. Distinct from the primitive-layer
    ``DropRefusedError`` per ``rules/dataflow-identifier-safety.md``
    Rule 6 and ``rules/schema-migration.md`` Rule 7."""

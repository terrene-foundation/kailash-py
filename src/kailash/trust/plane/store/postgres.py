# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""PostgreSQL-backed TrustPlaneStore implementation.

Provides a persistent store that satisfies the
:class:`TrustPlaneStore` protocol using PostgreSQL via ``psycopg`` (v3).

Features:
- Connection pooling via psycopg's built-in pool
- JSONB columns for efficient JSON storage and querying
- Schema versioning with forward-compatible migration support
- PostgreSQL MVCC for concurrent safety

Security notes:
- All record IDs are validated via ``validate_id()`` before SQL use.
- All writes are wrapped in PostgreSQL transactions (atomic).
- List methods honour a ``limit`` parameter (bounded results).
- The store is scoped to a single database (permission isolation).
- All queries use parameterized statements (no string interpolation).
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool, PoolTimeout
except ImportError:
    raise ImportError(
        "PostgreSQL store requires 'psycopg' and 'psycopg_pool'. "
        "Install with: pip install kailash[postgres]"
        "or: pip install 'psycopg[binary]>=3.0' psycopg_pool"
    )

from kailash.trust._locking import validate_id
from kailash.trust.plane.delegation import Delegate, DelegateStatus, ReviewResolution
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import DecisionRecord, MilestoneRecord, ProjectManifest
from kailash.trust.plane.exceptions import (
    RecordNotFoundError,
    SchemaMigrationError,
    SchemaTooNewError,
    StoreConnectionError,
    StoreQueryError,
    StoreTransactionError,
)

logger = logging.getLogger(__name__)

__all__ = ["PostgresTrustPlaneStore"]

# Current schema version. Increment when adding migrations.
SCHEMA_VERSION = 1

# Migration functions keyed by target version.
# Each function receives a psycopg Connection and runs DDL/DML
# within the caller's transaction.
#
# Example (v1 -> v2):
#   2: lambda conn: conn.execute("ALTER TABLE decisions ADD COLUMN tag TEXT DEFAULT ''")
MIGRATIONS: dict[int, Any] = {
    # Placeholder: when v2 is needed, add:
    # 2: _migrate_v1_to_v2,
}

_CREATE_META_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""

_CREATE_DECISIONS_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    data        JSONB NOT NULL
)
"""

_CREATE_MILESTONES_SQL = """
CREATE TABLE IF NOT EXISTS milestones (
    milestone_id TEXT PRIMARY KEY,
    data         JSONB NOT NULL
)
"""

_CREATE_HOLDS_SQL = """
CREATE TABLE IF NOT EXISTS holds (
    hold_id TEXT PRIMARY KEY,
    status  TEXT NOT NULL,
    data    JSONB NOT NULL
)
"""

_CREATE_DELEGATES_SQL = """
CREATE TABLE IF NOT EXISTS delegates (
    delegate_id TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    data        JSONB NOT NULL
)
"""

_CREATE_REVIEWS_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    review_key  TEXT PRIMARY KEY,
    hold_id     TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    data        JSONB NOT NULL
)
"""

_CREATE_ANCHORS_SQL = """
CREATE TABLE IF NOT EXISTS anchors (
    anchor_id TEXT PRIMARY KEY,
    data      JSONB NOT NULL
)
"""

_CREATE_MANIFEST_SQL = """
CREATE TABLE IF NOT EXISTS manifest (
    id   TEXT PRIMARY KEY DEFAULT 'manifest',
    data JSONB NOT NULL
)
"""

_CREATE_WAL_SQL = """
CREATE TABLE IF NOT EXISTS delegates_wal (
    id   TEXT PRIMARY KEY DEFAULT 'wal',
    data JSONB NOT NULL
)
"""

_ALL_CREATE_STMTS = [
    _CREATE_META_SQL,
    _CREATE_DECISIONS_SQL,
    _CREATE_MILESTONES_SQL,
    _CREATE_HOLDS_SQL,
    _CREATE_DELEGATES_SQL,
    _CREATE_REVIEWS_SQL,
    _CREATE_ANCHORS_SQL,
    _CREATE_MANIFEST_SQL,
    _CREATE_WAL_SQL,
]

# Indexes for filtered queries
_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_holds_status ON holds (status)",
    "CREATE INDEX IF NOT EXISTS idx_delegates_status ON delegates (status)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_hold_id ON reviews (hold_id)",
]


class PostgresTrustPlaneStore:
    """PostgreSQL-backed store for trust-plane records.

    Each record type is stored in a dedicated table with a ``data``
    JSONB column containing the full JSON blob, plus extracted key fields
    for indexed queries.

    Concurrent safety is achieved through PostgreSQL's MVCC and
    connection pooling via ``psycopg_pool.ConnectionPool``.

    Example::

        store = PostgresTrustPlaneStore("postgresql://user:pass@localhost/trustdb")
        store.initialize()
        store.store_decision(decision)
        retrieved = store.get_decision(decision.decision_id)
        store.close()
    """

    def __init__(self, connection_string: str, pool_size: int = 10) -> None:
        """Initialize the store with a PostgreSQL connection string.

        Args:
            connection_string: PostgreSQL connection string (conninfo).
                Example: ``postgresql://user:pass@localhost:5432/trustdb``
            pool_size: Maximum number of connections in the pool.
        """
        self._conninfo = connection_string
        self._pool_size = pool_size
        self._pool: ConnectionPool | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> psycopg.Connection:
        """Return a connection from the pool.

        This should be used as a context manager via ``self._pool.connection()``.
        For direct use, prefer ``_pool.connection()`` in a ``with`` block.

        Raises:
            RuntimeError: If the store has not been initialized.
        """
        if self._pool is None:
            raise RuntimeError(
                "PostgresTrustPlaneStore not initialized. Call initialize() first."
            )
        return self._pool.connection()

    def _sanitize_conninfo(self, msg: str) -> str:
        """Remove password fragments from error messages."""
        return re.sub(r"password=[^\s&]+", "password=***", msg)

    @contextmanager
    def _safe_connection(self) -> Generator[psycopg.Connection, None, None]:
        """Yield a pooled connection, wrapping psycopg errors in store exceptions.

        Raises:
            StoreConnectionError: If the pool is not initialized or the
                database is unreachable (``OperationalError``).
            StoreQueryError: For any other ``psycopg.Error`` during the
                block's execution.
        """
        if self._pool is None:
            raise StoreConnectionError(
                "PostgresTrustPlaneStore not initialized. Call initialize() first."
            )
        try:
            with self._pool.connection() as conn:
                yield conn
        except StoreConnectionError:
            raise
        except StoreQueryError:
            raise
        except PoolTimeout as exc:
            raise StoreConnectionError(
                f"Connection pool exhausted (all {self._pool_size} connections in use): {exc}"
            ) from exc
        except psycopg.OperationalError as exc:
            raise StoreConnectionError(self._sanitize_conninfo(str(exc))) from exc
        except psycopg.Error as exc:
            raise StoreQueryError(self._sanitize_conninfo(str(exc))) from exc

    # ------------------------------------------------------------------
    # Schema versioning & migrations
    # ------------------------------------------------------------------

    def _read_schema_version(self, conn: psycopg.Connection) -> int | None:
        """Read the current schema version from the meta table.

        Returns None if the meta table does not exist (fresh database).
        """
        row = conn.execute(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.tables "
            "  WHERE table_name = 'meta'"
            ")"
        ).fetchone()
        if row is None or not row[0]:
            return None
        result = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if result is None:
            return None
        return int(result[0])

    def _set_schema_version(self, conn: psycopg.Connection, version: int) -> None:
        """Write the schema version to the meta table."""
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            (str(version),),
        )

    def _run_migrations(self, conn: psycopg.Connection, from_version: int) -> None:
        """Apply migrations sequentially from *from_version* to SCHEMA_VERSION.

        Each migration runs in its own savepoint. On failure, the
        failed migration is rolled back and ``SchemaMigrationError``
        is raised -- the database remains at the last successful version.
        """
        for target in range(from_version + 1, SCHEMA_VERSION + 1):
            migrate_fn = MIGRATIONS.get(target)
            if migrate_fn is None:
                continue
            try:
                with conn.transaction():
                    migrate_fn(conn)
                    self._set_schema_version(conn, target)
                logger.info("Migrated trust-plane schema to version %d", target)
            except Exception as exc:
                raise SchemaMigrationError(
                    target_version=target,
                    reason=self._sanitize_conninfo(str(exc)),
                ) from exc

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the connection pool, tables, indexes, and run migrations.

        Safe to call multiple times (idempotent).

        Raises:
            SchemaTooNewError: If the database was created by a newer
                version of trust-plane than this code supports.
            SchemaMigrationError: If a migration fails (database is
                left at the last successful version).
        """
        self._pool = ConnectionPool(
            conninfo=self._conninfo,
            min_size=1,
            max_size=self._pool_size,
            kwargs={"row_factory": dict_row},
        )

        with self._safe_connection() as conn:
            existing_version = self._read_schema_version(conn)

            if existing_version is not None and existing_version > SCHEMA_VERSION:
                raise SchemaTooNewError(
                    db_version=existing_version,
                    current_version=SCHEMA_VERSION,
                )

            # Create all tables (IF NOT EXISTS -- safe for re-init)
            for stmt in _ALL_CREATE_STMTS:
                conn.execute(stmt)
            for idx_stmt in _CREATE_INDEXES_SQL:
                conn.execute(idx_stmt)
            conn.commit()

            if existing_version is None:
                # Fresh database -- stamp with current version
                self._set_schema_version(conn, SCHEMA_VERSION)
                conn.commit()
                logger.info(
                    "Initialized trust-plane PostgreSQL store (schema v%d)",
                    SCHEMA_VERSION,
                )
            elif existing_version < SCHEMA_VERSION:
                self._run_migrations(conn, existing_version)

    def close(self) -> None:
        """Close the connection pool.

        Safe to call multiple times.
        """
        if self._pool is not None:
            self._pool.close()
            self._pool = None
        logger.debug("PostgresTrustPlaneStore closed")

    # ------------------------------------------------------------------
    # Decision Records
    # ------------------------------------------------------------------

    def store_decision(self, record: DecisionRecord) -> None:
        """Persist a decision record.

        Raises:
            ValueError: If the decision_id fails validation.
        """
        validate_id(record.decision_id)
        data = json.dumps(record.to_dict(), default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO decisions (decision_id, data) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (decision_id) DO UPDATE SET data = EXCLUDED.data",
                (record.decision_id, data),
            )
            conn.commit()

    def get_decision(self, decision_id: str) -> DecisionRecord:
        """Retrieve a decision record by ID.

        Raises:
            RecordNotFoundError: If the decision is not found.
            ValueError: If the decision_id fails validation.
        """
        validate_id(decision_id)
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM decisions WHERE decision_id = %s",
                (decision_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError("decision", decision_id)
        return DecisionRecord.from_dict(row["data"])

    def list_decisions(self, limit: int = 1000) -> list[DecisionRecord]:
        """List decision records, bounded by *limit*."""
        limit = max(0, limit)
        with self._safe_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM decisions ORDER BY decision_id LIMIT %s",
                (limit,),
            )
            return [DecisionRecord.from_dict(row["data"]) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Milestone Records
    # ------------------------------------------------------------------

    def store_milestone(self, record: MilestoneRecord) -> None:
        """Persist a milestone record.

        Raises:
            ValueError: If the milestone_id fails validation.
        """
        validate_id(record.milestone_id)
        data = json.dumps(record.to_dict(), default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO milestones (milestone_id, data) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (milestone_id) DO UPDATE SET data = EXCLUDED.data",
                (record.milestone_id, data),
            )
            conn.commit()

    def get_milestone(self, milestone_id: str) -> MilestoneRecord:
        """Retrieve a milestone record by ID.

        Raises:
            RecordNotFoundError: If the milestone is not found.
            ValueError: If the milestone_id fails validation.
        """
        validate_id(milestone_id)
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM milestones WHERE milestone_id = %s",
                (milestone_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError("milestone", milestone_id)
        return MilestoneRecord.from_dict(row["data"])

    def list_milestones(self, limit: int = 1000) -> list[MilestoneRecord]:
        """List milestone records, bounded by *limit*."""
        limit = max(0, limit)
        with self._safe_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM milestones ORDER BY milestone_id LIMIT %s",
                (limit,),
            )
            return [MilestoneRecord.from_dict(row["data"]) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Hold Records
    # ------------------------------------------------------------------

    def store_hold(self, record: HoldRecord) -> None:
        """Persist a hold record.

        Raises:
            ValueError: If the hold_id fails validation.
        """
        validate_id(record.hold_id)
        data = json.dumps(record.to_dict(), default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO holds (hold_id, status, data) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (hold_id) DO UPDATE SET status = EXCLUDED.status, "
                "data = EXCLUDED.data",
                (record.hold_id, record.status, data),
            )
            conn.commit()

    def get_hold(self, hold_id: str) -> HoldRecord:
        """Retrieve a hold record by ID.

        Raises:
            RecordNotFoundError: If the hold is not found.
            ValueError: If the hold_id fails validation.
        """
        validate_id(hold_id)
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM holds WHERE hold_id = %s",
                (hold_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError("hold", hold_id)
        return HoldRecord.from_dict(row["data"])

    def list_holds(
        self, status: str | None = None, limit: int = 1000
    ) -> list[HoldRecord]:
        """List hold records, optionally filtered by *status*.

        Args:
            status: If provided, only return holds with this status.
            limit: Maximum number of records to return.
        """
        limit = max(0, limit)
        with self._safe_connection() as conn:
            if status is not None:
                cursor = conn.execute(
                    "SELECT data FROM holds WHERE status = %s "
                    "ORDER BY hold_id LIMIT %s",
                    (status, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT data FROM holds ORDER BY hold_id LIMIT %s",
                    (limit,),
                )
            return [HoldRecord.from_dict(row["data"]) for row in cursor.fetchall()]

    def update_hold(self, record: HoldRecord) -> None:
        """Update an existing hold record (e.g. after resolution).

        Raises:
            ValueError: If the hold_id fails validation.
        """
        self.store_hold(record)

    # ------------------------------------------------------------------
    # Delegate Records
    # ------------------------------------------------------------------

    def store_delegate(self, delegate: Delegate) -> None:
        """Persist a delegate record.

        Raises:
            ValueError: If the delegate_id fails validation.
        """
        validate_id(delegate.delegate_id)
        data = json.dumps(delegate.to_dict(), default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO delegates (delegate_id, status, data) "
                "VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (delegate_id) DO UPDATE SET status = EXCLUDED.status, "
                "data = EXCLUDED.data",
                (delegate.delegate_id, delegate.status.value, data),
            )
            conn.commit()

    def get_delegate(self, delegate_id: str) -> Delegate:
        """Retrieve a delegate by ID.

        Raises:
            RecordNotFoundError: If the delegate is not found.
            ValueError: If the delegate_id fails validation.
        """
        validate_id(delegate_id)
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM delegates WHERE delegate_id = %s",
                (delegate_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError("delegate", delegate_id)
        return Delegate.from_dict(row["data"])

    def list_delegates(
        self, active_only: bool = True, limit: int = 1000
    ) -> list[Delegate]:
        """List delegates, optionally filtered by active status.

        Args:
            active_only: If True, exclude revoked/expired delegates.
            limit: Maximum number of records to return.
        """
        limit = max(0, limit)
        with self._safe_connection() as conn:
            if active_only:
                # Filter by status column for efficiency, then apply
                # runtime is_active() check for expiry.
                cursor = conn.execute(
                    "SELECT data FROM delegates WHERE status = %s "
                    "ORDER BY delegate_id LIMIT %s",
                    (DelegateStatus.ACTIVE.value, limit),
                )
                results: list[Delegate] = []
                for row in cursor.fetchall():
                    d = Delegate.from_dict(row["data"])
                    if d.is_active():
                        results.append(d)
                return results
            else:
                cursor = conn.execute(
                    "SELECT data FROM delegates ORDER BY delegate_id LIMIT %s",
                    (limit,),
                )
                return [Delegate.from_dict(row["data"]) for row in cursor.fetchall()]

    def update_delegate(self, delegate: Delegate) -> None:
        """Update an existing delegate record (e.g. after revocation).

        Raises:
            ValueError: If the delegate_id fails validation.
        """
        self.store_delegate(delegate)

    # ------------------------------------------------------------------
    # Review Records
    # ------------------------------------------------------------------

    def store_review(self, review: ReviewResolution) -> None:
        """Persist a review resolution.

        Raises:
            ValueError: If hold_id or delegate_id fails validation.
        """
        validate_id(review.hold_id)
        validate_id(review.delegate_id)
        review_key = f"{review.hold_id}-{review.delegate_id}"
        data = json.dumps(review.to_dict(), default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO reviews "
                "(review_key, hold_id, delegate_id, data) VALUES (%s, %s, %s, %s::jsonb) "
                "ON CONFLICT (review_key) DO UPDATE SET "
                "hold_id = EXCLUDED.hold_id, "
                "delegate_id = EXCLUDED.delegate_id, "
                "data = EXCLUDED.data",
                (review_key, review.hold_id, review.delegate_id, data),
            )
            conn.commit()

    def list_reviews(
        self, hold_id: str | None = None, limit: int = 1000
    ) -> list[ReviewResolution]:
        """List review resolutions, optionally filtered by *hold_id*.

        Args:
            hold_id: If provided, only return reviews for this hold.
            limit: Maximum number of records to return.
        """
        limit = max(0, limit)
        with self._safe_connection() as conn:
            if hold_id is not None:
                cursor = conn.execute(
                    "SELECT data FROM reviews WHERE hold_id = %s "
                    "ORDER BY review_key LIMIT %s",
                    (hold_id, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT data FROM reviews ORDER BY review_key LIMIT %s",
                    (limit,),
                )
            results: list[ReviewResolution] = []
            for row in cursor.fetchall():
                data = row["data"]
                results.append(
                    ReviewResolution(
                        hold_id=data["hold_id"],
                        delegate_id=data["delegate_id"],
                        approved=data["approved"],
                        reason=data["reason"],
                        dimension=data["dimension"],
                        resolved_at=datetime.fromisoformat(data["resolved_at"]),
                    )
                )
            return results

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def store_manifest(self, manifest: ProjectManifest) -> None:
        """Persist the project manifest."""
        data = json.dumps(manifest.to_dict(), default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO manifest (id, data) VALUES ('manifest', %s::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (data,),
            )
            conn.commit()

    def get_manifest(self) -> ProjectManifest:
        """Retrieve the project manifest.

        Raises:
            RecordNotFoundError: If the manifest has not been stored yet.
        """
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM manifest WHERE id = 'manifest'"
            ).fetchone()
        if row is None:
            raise RecordNotFoundError("manifest", "manifest")
        return ProjectManifest.from_dict(row["data"])

    # ------------------------------------------------------------------
    # Anchor JSON (raw dict)
    # ------------------------------------------------------------------

    def store_anchor(self, anchor_id: str, data: dict) -> None:
        """Persist an EATP Audit Anchor as raw JSON.

        Args:
            anchor_id: The anchor identifier (validated).
            data: The anchor dict to store.

        Raises:
            ValueError: If the anchor_id fails validation.
        """
        validate_id(anchor_id)
        data_json = json.dumps(data, default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO anchors (anchor_id, data) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (anchor_id) DO UPDATE SET data = EXCLUDED.data",
                (anchor_id, data_json),
            )
            conn.commit()

    def get_anchor(self, anchor_id: str) -> dict:
        """Retrieve an anchor by ID.

        Raises:
            RecordNotFoundError: If the anchor is not found.
            ValueError: If the anchor_id fails validation.
        """
        validate_id(anchor_id)
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM anchors WHERE anchor_id = %s",
                (anchor_id,),
            ).fetchone()
        if row is None:
            raise RecordNotFoundError("anchor", anchor_id)
        return row["data"]

    def list_anchors(self, limit: int = 1000) -> list[dict]:
        """List anchors, bounded by *limit*."""
        limit = max(0, limit)
        with self._safe_connection() as conn:
            cursor = conn.execute(
                "SELECT data FROM anchors ORDER BY anchor_id LIMIT %s",
                (limit,),
            )
            return [row["data"] for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # WAL (Write-Ahead Log for cascade revocation)
    # ------------------------------------------------------------------

    def store_wal(self, wal_data: dict) -> None:
        """Persist the cascade-revocation WAL."""
        data_json = json.dumps(wal_data, default=str)
        with self._safe_connection() as conn:
            conn.execute(
                "INSERT INTO delegates_wal (id, data) VALUES ('wal', %s::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (data_json,),
            )
            conn.commit()

    def get_wal(self) -> dict | None:
        """Retrieve the WAL if it exists, or None."""
        with self._safe_connection() as conn:
            row = conn.execute(
                "SELECT data FROM delegates_wal WHERE id = 'wal'"
            ).fetchone()
        if row is None:
            return None
        return row["data"]

    def delete_wal(self) -> None:
        """Delete the WAL record. No-op if absent."""
        with self._safe_connection() as conn:
            conn.execute("DELETE FROM delegates_wal WHERE id = 'wal'")
            conn.commit()

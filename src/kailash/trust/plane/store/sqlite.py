# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SQLite-backed TrustPlaneStore implementation.

Provides a persistent single-file store that satisfies the
:class:`TrustPlaneStore` protocol using stdlib ``sqlite3``.

Features:
- Single-file persistence (``*.db``)
- WAL journal mode for concurrent readers
- Thread-safe via ``threading.local()`` per-thread connections
- Schema versioning with forward-compatible migration support
- Zero new dependencies (stdlib ``sqlite3`` only)

Security notes:
- All record IDs are validated via ``validate_id()`` before SQL use.
- All writes are wrapped in SQLite transactions (atomic).
- List methods honour a ``limit`` parameter (bounded results).
- The store is scoped to a single database file (permission isolation).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from kailash.trust._locking import validate_id
from kailash.trust.plane.delegation import Delegate, DelegateStatus, ReviewResolution
from kailash.trust.plane.exceptions import (
    RecordNotFoundError,
    SchemaMigrationError,
    SchemaTooNewError,
)
from kailash.trust.plane.holds import HoldRecord
from kailash.trust.plane.models import DecisionRecord, MilestoneRecord, ProjectManifest

logger = logging.getLogger(__name__)

__all__ = ["SqliteTrustPlaneStore"]

# Current schema version. Increment when adding migrations.
SCHEMA_VERSION = 1

# Migration functions keyed by target version.
# Each function receives a sqlite3.Connection and runs DDL/DML
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
    data        TEXT NOT NULL
)
"""

_CREATE_MILESTONES_SQL = """
CREATE TABLE IF NOT EXISTS milestones (
    milestone_id TEXT PRIMARY KEY,
    data         TEXT NOT NULL
)
"""

_CREATE_HOLDS_SQL = """
CREATE TABLE IF NOT EXISTS holds (
    hold_id TEXT PRIMARY KEY,
    status  TEXT NOT NULL,
    data    TEXT NOT NULL
)
"""

_CREATE_DELEGATES_SQL = """
CREATE TABLE IF NOT EXISTS delegates (
    delegate_id TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    data        TEXT NOT NULL
)
"""

_CREATE_REVIEWS_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    review_key  TEXT PRIMARY KEY,
    hold_id     TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    data        TEXT NOT NULL
)
"""

_CREATE_ANCHORS_SQL = """
CREATE TABLE IF NOT EXISTS anchors (
    anchor_id TEXT PRIMARY KEY,
    data      TEXT NOT NULL
)
"""

_CREATE_MANIFEST_SQL = """
CREATE TABLE IF NOT EXISTS manifest (
    id   TEXT PRIMARY KEY DEFAULT 'manifest',
    data TEXT NOT NULL
)
"""

_CREATE_WAL_SQL = """
CREATE TABLE IF NOT EXISTS delegates_wal (
    id   TEXT PRIMARY KEY DEFAULT 'wal',
    data TEXT NOT NULL
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


class SqliteTrustPlaneStore:
    """SQLite-backed store for trust-plane records.

    Each record type is stored in a dedicated table with a ``data``
    column containing the full JSON blob, plus extracted key fields
    for indexed queries.

    Thread safety is achieved through :class:`threading.local` so
    each thread gets its own ``sqlite3.Connection`` with WAL mode.

    Example::

        store = SqliteTrustPlaneStore("/tmp/trust.db")
        store.initialize()
        store.store_decision(decision)
        retrieved = store.get_decision(decision.decision_id)
        store.close()
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the store with a path to the SQLite database file.

        Args:
            db_path: Path to the SQLite database file. Parent
                directories are created on ``initialize()``.
        """
        self._db_path = str(db_path)
        self._local = threading.local()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection.

        Creates a new connection on the first call within each thread.
        Connections use WAL mode and return rows as ``sqlite3.Row``.
        """
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # ------------------------------------------------------------------
    # Schema versioning & migrations
    # ------------------------------------------------------------------

    def _read_schema_version(self, conn: sqlite3.Connection) -> int | None:
        """Read the current schema version from the meta table.

        Returns None if the meta table does not exist (fresh database).
        """
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
        )
        if cursor.fetchone() is None:
            return None
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return None
        return int(row["value"])

    def _set_schema_version(self, conn: sqlite3.Connection, version: int) -> None:
        """Write the schema version to the meta table."""
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )

    def _run_migrations(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Apply migrations sequentially from *from_version* to SCHEMA_VERSION.

        Each migration runs in its own transaction. On failure, the
        failed migration is rolled back and ``SchemaMigrationError``
        is raised — the database remains at the last successful version.
        """
        for target in range(from_version + 1, SCHEMA_VERSION + 1):
            migrate_fn = MIGRATIONS.get(target)
            if migrate_fn is None:
                continue
            try:
                conn.execute("BEGIN")
                migrate_fn(conn)
                self._set_schema_version(conn, target)
                conn.commit()
                logger.info("Migrated trust-plane schema to version %d", target)
            except Exception as exc:
                conn.rollback()
                raise SchemaMigrationError(
                    target_version=target,
                    reason=str(exc),
                ) from exc

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the database, tables, indexes, and run migrations.

        Safe to call multiple times (idempotent).

        Raises:
            SchemaTooNewError: If the database was created by a newer
                version of trust-plane than this code supports.
            SchemaMigrationError: If a migration fails (database is
                left at the last successful version).
        """
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        conn = self._get_connection()

        existing_version = self._read_schema_version(conn)

        if existing_version is not None and existing_version > SCHEMA_VERSION:
            raise SchemaTooNewError(
                db_version=existing_version,
                current_version=SCHEMA_VERSION,
            )

        # Create all tables (IF NOT EXISTS — safe for re-init)
        for stmt in _ALL_CREATE_STMTS:
            conn.execute(stmt)
        for idx_stmt in _CREATE_INDEXES_SQL:
            conn.execute(idx_stmt)
        conn.commit()

        # Restrict database file permissions (POSIX only — Windows
        # does not support fine-grained permissions via os.chmod).
        # Also set permissions on WAL and SHM auxiliary files which SQLite
        # creates lazily with default umask.
        for suffix in ("", "-wal", "-shm"):
            aux_path = self._db_path + suffix
            if os.path.exists(aux_path):
                try:
                    os.chmod(aux_path, 0o600)
                except OSError:
                    logger.debug("Could not set 0o600 on %s (non-POSIX?)", aux_path)

        if existing_version is None:
            # Fresh database — stamp with current version
            self._set_schema_version(conn, SCHEMA_VERSION)
            conn.commit()
            logger.info(
                "Initialized trust-plane SQLite store at %s (schema v%d)",
                self._db_path,
                SCHEMA_VERSION,
            )
        elif existing_version < SCHEMA_VERSION:
            self._run_migrations(conn, existing_version)

    def close(self) -> None:
        """Close the per-thread database connection.

        Safe to call multiple times.
        """
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        logger.debug("SqliteTrustPlaneStore closed")

    # ------------------------------------------------------------------
    # Decision Records
    # ------------------------------------------------------------------

    def store_decision(self, record: DecisionRecord) -> None:
        """Persist a decision record.

        Raises:
            ValueError: If the decision_id fails validation.
        """
        validate_id(record.decision_id)
        conn = self._get_connection()
        data_json = json.dumps(record.to_dict(), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO decisions (decision_id, data) VALUES (?, ?)",
            (record.decision_id, data_json),
        )
        conn.commit()

    def get_decision(self, decision_id: str) -> DecisionRecord:
        """Retrieve a decision record by ID.

        Raises:
            RecordNotFoundError: If the decision is not found.
            ValueError: If the decision_id fails validation.
        """
        validate_id(decision_id)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT data FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("decision", decision_id)
        return DecisionRecord.from_dict(json.loads(row["data"]))

    def list_decisions(self, limit: int = 1000) -> list[DecisionRecord]:
        """List decision records, bounded by *limit*."""
        limit = max(0, limit)
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT data FROM decisions ORDER BY decision_id LIMIT ?",
            (limit,),
        )
        return [
            DecisionRecord.from_dict(json.loads(row["data"]))
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Milestone Records
    # ------------------------------------------------------------------

    def store_milestone(self, record: MilestoneRecord) -> None:
        """Persist a milestone record.

        Raises:
            ValueError: If the milestone_id fails validation.
        """
        validate_id(record.milestone_id)
        conn = self._get_connection()
        data_json = json.dumps(record.to_dict(), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO milestones (milestone_id, data) VALUES (?, ?)",
            (record.milestone_id, data_json),
        )
        conn.commit()

    def get_milestone(self, milestone_id: str) -> MilestoneRecord:
        """Retrieve a milestone record by ID.

        Raises:
            RecordNotFoundError: If the milestone is not found.
            ValueError: If the milestone_id fails validation.
        """
        validate_id(milestone_id)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT data FROM milestones WHERE milestone_id = ?",
            (milestone_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("milestone", milestone_id)
        return MilestoneRecord.from_dict(json.loads(row["data"]))

    def list_milestones(self, limit: int = 1000) -> list[MilestoneRecord]:
        """List milestone records, bounded by *limit*."""
        limit = max(0, limit)
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT data FROM milestones ORDER BY milestone_id LIMIT ?",
            (limit,),
        )
        return [
            MilestoneRecord.from_dict(json.loads(row["data"]))
            for row in cursor.fetchall()
        ]

    # ------------------------------------------------------------------
    # Hold Records
    # ------------------------------------------------------------------

    def store_hold(self, record: HoldRecord) -> None:
        """Persist a hold record.

        Raises:
            ValueError: If the hold_id fails validation.
        """
        validate_id(record.hold_id)
        conn = self._get_connection()
        data_json = json.dumps(record.to_dict(), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO holds (hold_id, status, data) VALUES (?, ?, ?)",
            (record.hold_id, record.status, data_json),
        )
        conn.commit()

    def get_hold(self, hold_id: str) -> HoldRecord:
        """Retrieve a hold record by ID.

        Raises:
            RecordNotFoundError: If the hold is not found.
            ValueError: If the hold_id fails validation.
        """
        validate_id(hold_id)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT data FROM holds WHERE hold_id = ?",
            (hold_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("hold", hold_id)
        return HoldRecord.from_dict(json.loads(row["data"]))

    def list_holds(
        self, status: str | None = None, limit: int = 1000
    ) -> list[HoldRecord]:
        """List hold records, optionally filtered by *status*.

        Args:
            status: If provided, only return holds with this status.
            limit: Maximum number of records to return.
        """
        limit = max(0, limit)
        conn = self._get_connection()
        if status is not None:
            cursor = conn.execute(
                "SELECT data FROM holds WHERE status = ? ORDER BY hold_id LIMIT ?",
                (status, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT data FROM holds ORDER BY hold_id LIMIT ?",
                (limit,),
            )
        return [
            HoldRecord.from_dict(json.loads(row["data"])) for row in cursor.fetchall()
        ]

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
        conn = self._get_connection()
        data_json = json.dumps(delegate.to_dict(), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO delegates (delegate_id, status, data) "
            "VALUES (?, ?, ?)",
            (delegate.delegate_id, delegate.status.value, data_json),
        )
        conn.commit()

    def get_delegate(self, delegate_id: str) -> Delegate:
        """Retrieve a delegate by ID.

        Raises:
            RecordNotFoundError: If the delegate is not found.
            ValueError: If the delegate_id fails validation.
        """
        validate_id(delegate_id)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT data FROM delegates WHERE delegate_id = ?",
            (delegate_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("delegate", delegate_id)
        return Delegate.from_dict(json.loads(row["data"]))

    def list_delegates(
        self, active_only: bool = True, limit: int = 1000
    ) -> list[Delegate]:
        """List delegates, optionally filtered by active status.

        Args:
            active_only: If True, exclude revoked/expired delegates.
            limit: Maximum number of records to return.
        """
        limit = max(0, limit)
        conn = self._get_connection()
        if active_only:
            # Filter by status column for efficiency, then apply
            # runtime is_active() check for expiry.
            cursor = conn.execute(
                "SELECT data FROM delegates WHERE status = ? "
                "ORDER BY delegate_id LIMIT ?",
                (DelegateStatus.ACTIVE.value, limit),
            )
            results: list[Delegate] = []
            for row in cursor.fetchall():
                d = Delegate.from_dict(json.loads(row["data"]))
                if d.is_active():
                    results.append(d)
            return results
        else:
            cursor = conn.execute(
                "SELECT data FROM delegates ORDER BY delegate_id LIMIT ?",
                (limit,),
            )
            return [
                Delegate.from_dict(json.loads(row["data"])) for row in cursor.fetchall()
            ]

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
        conn = self._get_connection()
        review_key = f"{review.hold_id}-{review.delegate_id}"
        data_json = json.dumps(review.to_dict(), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO reviews "
            "(review_key, hold_id, delegate_id, data) VALUES (?, ?, ?, ?)",
            (review_key, review.hold_id, review.delegate_id, data_json),
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
        conn = self._get_connection()
        if hold_id is not None:
            cursor = conn.execute(
                "SELECT data FROM reviews WHERE hold_id = ? "
                "ORDER BY review_key LIMIT ?",
                (hold_id, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT data FROM reviews ORDER BY review_key LIMIT ?",
                (limit,),
            )
        results: list[ReviewResolution] = []
        for row in cursor.fetchall():
            data = json.loads(row["data"])
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
        conn = self._get_connection()
        data_json = json.dumps(manifest.to_dict(), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO manifest (id, data) VALUES ('manifest', ?)",
            (data_json,),
        )
        conn.commit()

    def get_manifest(self) -> ProjectManifest:
        """Retrieve the project manifest.

        Raises:
            RecordNotFoundError: If the manifest has not been stored yet.
        """
        conn = self._get_connection()
        row = conn.execute("SELECT data FROM manifest WHERE id = 'manifest'").fetchone()
        if row is None:
            raise RecordNotFoundError("manifest", "manifest")
        return ProjectManifest.from_dict(json.loads(row["data"]))

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
        conn = self._get_connection()
        data_json = json.dumps(data, default=str)
        conn.execute(
            "INSERT OR REPLACE INTO anchors (anchor_id, data) VALUES (?, ?)",
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
        conn = self._get_connection()
        row = conn.execute(
            "SELECT data FROM anchors WHERE anchor_id = ?",
            (anchor_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError("anchor", anchor_id)
        return json.loads(row["data"])

    def list_anchors(self, limit: int = 1000) -> list[dict]:
        """List anchors, bounded by *limit*."""
        limit = max(0, limit)
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT data FROM anchors ORDER BY anchor_id LIMIT ?",
            (limit,),
        )
        return [json.loads(row["data"]) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # WAL (Write-Ahead Log for cascade revocation)
    # ------------------------------------------------------------------

    def store_wal(self, wal_data: dict) -> None:
        """Persist the cascade-revocation WAL."""
        conn = self._get_connection()
        data_json = json.dumps(wal_data, default=str)
        conn.execute(
            "INSERT OR REPLACE INTO delegates_wal (id, data) VALUES ('wal', ?)",
            (data_json,),
        )
        conn.commit()

    def get_wal(self) -> dict | None:
        """Retrieve the WAL if it exists, or None."""
        conn = self._get_connection()
        row = conn.execute("SELECT data FROM delegates_wal WHERE id = 'wal'").fetchone()
        if row is None:
            return None
        return json.loads(row["data"])

    def delete_wal(self) -> None:
        """Delete the WAL record. No-op if absent."""
        conn = self._get_connection()
        conn.execute("DELETE FROM delegates_wal WHERE id = 'wal'")
        conn.commit()

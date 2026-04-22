# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQLite storage backend for ``km.track()`` experiment runs.

Implements the persistence half of ``specs/ml-tracking.md`` §2.4 +
§2.7: an auto-created ``experiment_runs`` table with one column per
mandatory auto-capture field plus a JSON ``params`` column. Writes go
through parameterised queries per ``rules/security.md`` (§ Parameterized
Queries); the table schema is fixed (no dynamic identifiers) per
``rules/infrastructure-sql.md``.

The backend is async-first so the ``ExperimentRun`` context manager in
``kailash_ml.tracking.runner`` can ``await`` start / metric / end /
read calls without leaking a sync DB connection into the caller's
event loop.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from kailash.db.dialect import _validate_identifier

__all__ = ["SQLiteTrackerBackend"]


# ---------------------------------------------------------------------------
# DDL — fixed identifiers (no interpolation, no injection surface).
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_runs (
    run_id                   TEXT PRIMARY KEY,
    experiment               TEXT NOT NULL,
    parent_run_id            TEXT,
    status                   TEXT NOT NULL,
    host                     TEXT,
    python_version           TEXT,
    kailash_ml_version       TEXT,
    lightning_version        TEXT,
    torch_version            TEXT,
    cuda_version             TEXT,
    git_sha                  TEXT,
    git_branch               TEXT,
    git_dirty                INTEGER,
    wall_clock_start         TEXT,
    wall_clock_end           TEXT,
    duration_seconds         REAL,
    tenant_id                TEXT,
    device_used              TEXT,
    accelerator              TEXT,
    precision                TEXT,
    device_family            TEXT,
    device_backend           TEXT,
    device_fallback_reason   TEXT,
    device_array_api         INTEGER,
    params                   TEXT NOT NULL DEFAULT '{}',
    error_type               TEXT,
    error_message            TEXT
);
"""

_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment
    ON experiment_runs (experiment);
"""

# W12 — logging-primitive auxiliary tables. Keyed by ``run_id`` so they
# mirror the ``_kml_metrics`` / ``_kml_artifacts`` / ``_kml_tags`` shapes
# from migration 0002 without requiring the tenant-scoped composite PKs
# that the migration-layer tables use. Schema unification is W14 work;
# W12 uses the parallel ``experiment_*`` schema of ``SQLiteTrackerBackend``.
_METRICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    key         TEXT NOT NULL,
    step        INTEGER,
    value       REAL NOT NULL,
    timestamp   TEXT NOT NULL
);
"""

_METRICS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_run_key_step
    ON experiment_metrics (run_id, key, step);
"""

_ARTIFACTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_artifacts (
    run_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    content_type  TEXT,
    size_bytes    INTEGER NOT NULL,
    storage_uri   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (run_id, name, sha256)
);
"""

_ARTIFACTS_SHA_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_experiment_artifacts_run_sha
    ON experiment_artifacts (run_id, sha256);
"""

_TAGS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_tags (
    run_id  TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (run_id, key)
);
"""

_MODEL_VERSIONS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_model_versions (
    run_id         TEXT NOT NULL,
    name           TEXT NOT NULL,
    format         TEXT NOT NULL,
    artifact_sha   TEXT NOT NULL,
    signature_json TEXT,
    lineage_json   TEXT,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (run_id, name)
);
"""

# Pre-0.14 databases carried a narrower schema. On first access we probe
# ``PRAGMA table_info`` and ALTER TABLE any missing columns so existing
# ``~/.kailash_ml/ml.db`` files keep working after the 0.14 schema
# expansion. Column names MUST match the 0.14 schema exactly; the list
# is hardcoded so the migration cannot inject an identifier from user
# input (``rules/dataflow-identifier-safety.md`` §5).
_COLUMNS_ADDED_IN_0_14: tuple[tuple[str, str], ...] = (
    ("kailash_ml_version", "TEXT"),
    ("lightning_version", "TEXT"),
    ("torch_version", "TEXT"),
    ("cuda_version", "TEXT"),
    ("device_used", "TEXT"),
    ("accelerator", "TEXT"),
    ("precision", "TEXT"),
)


class SQLiteTrackerBackend:
    """Async-friendly SQLite backend for experiment run records.

    Runs synchronous ``sqlite3`` calls inside ``asyncio.to_thread`` so
    the ``ExperimentRun`` context manager never blocks the event loop.
    All SQL uses fixed identifiers + parameterised values.

    A single backend instance holds one connection and serialises
    writes through an ``asyncio.Lock``. SQLite itself handles
    cross-process concurrency via ``journal_mode=WAL``.

    Args:
        db_path: Filesystem path (or ``":memory:"``) to the SQLite
            database. Parent directory is created if missing.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        # W14: in-memory stores route through a named URI with
        # ``cache=shared`` so multiple backend instances pointed at the
        # same ``:memory:`` address see one database (spec §6.1 +
        # ``rules/patterns.md`` "URI shared-cache for :memory:"). Raw
        # ``:memory:`` would give every call site a private DB, which
        # breaks fixtures that open two handles expecting the same
        # rows.
        connect_uri: str
        use_uri = False
        if self._db_path == ":memory:":
            connect_uri = "file:memdb_kailash_ml?mode=memory&cache=shared"
            use_uri = True
        else:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            connect_uri = self._db_path
        # ``check_same_thread=False`` lets us reuse the connection across
        # the worker threads that ``asyncio.to_thread`` hands us. The
        # ``_conn_lock`` makes that safe.
        self._conn = sqlite3.connect(
            connect_uri,
            check_same_thread=False,
            isolation_level=None,  # autocommit; per-statement atomic
            uri=use_uri,
        )
        self._conn.row_factory = sqlite3.Row
        # W14 PRAGMA stack (spec §6.1 / ``rules/patterns.md`` "Default
        # PRAGMAs on every connection"). Each PRAGMA is applied exactly
        # once at connect time so the on-disk state matches the
        # contract the tracker exposes to concurrent writers.
        #
        # - journal_mode=WAL — readers never block writers; mandatory
        #   for multi-process SQLite. Skipped on ``:memory:`` since
        #   there is no on-disk journal.
        # - busy_timeout=30000 — 30s retry window before SQLITE_BUSY
        #   surfaces to the caller; covers the common "test-suite
        #   parallelism holds a write lock for 200ms" case without
        #   forcing callers to catch.
        # - synchronous=NORMAL — durable across process crashes (WAL
        #   guarantees), faster than FULL by ~1 order for write-heavy
        #   tracker workloads.
        # - cache_size=-20000 — 20MB page cache (KB when positive, pages
        #   when negative; -20000 is 20MB regardless of page_size).
        # - foreign_keys=ON — enforced FK integrity at every write;
        #   W14 schema unification (future wave) relies on this.
        if self._db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-20000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Create the schema if absent. Idempotent.

        Also migrates pre-0.14 databases by adding any columns that
        landed in 0.14 (seven additional reproducibility fields —
        ``kailash_ml_version``, ``lightning_version``, ``torch_version``,
        ``cuda_version``, ``device_used``, ``accelerator``, ``precision``).
        The migration is additive (ALTER TABLE ADD COLUMN) so existing
        rows stay readable; new columns default to SQL NULL.
        """
        if self._initialized:
            return

        def _init() -> None:
            with self._conn_lock:
                self._conn.execute(_SCHEMA_SQL)
                self._conn.execute(_INDEX_SQL)
                # W12 logging-primitive tables (spec ml-tracking.md §4).
                self._conn.execute(_METRICS_SCHEMA_SQL)
                self._conn.execute(_METRICS_INDEX_SQL)
                self._conn.execute(_ARTIFACTS_SCHEMA_SQL)
                self._conn.execute(_ARTIFACTS_SHA_INDEX_SQL)
                self._conn.execute(_TAGS_SCHEMA_SQL)
                self._conn.execute(_MODEL_VERSIONS_SCHEMA_SQL)
                # Detect pre-0.14 databases and add missing columns.
                cur = self._conn.execute("PRAGMA table_info(experiment_runs)")
                existing = {row[1] for row in cur.fetchall()}
                for name, sql_type in _COLUMNS_ADDED_IN_0_14:
                    if name not in existing:
                        # Defense-in-depth validation per
                        # ``rules/dataflow-identifier-safety.md`` §5 —
                        # hardcoded lists MUST still validate so the
                        # check survives any future refactor that makes
                        # the list dynamic. ``sql_type`` is pinned to
                        # ``TEXT`` in the literal below.
                        _validate_identifier(name)
                        self._conn.execute(
                            f"ALTER TABLE experiment_runs ADD COLUMN {name} {sql_type}"
                        )

        await asyncio.to_thread(_init)
        self._initialized = True

    async def close(self) -> None:
        """Close the underlying SQLite connection."""

        def _close() -> None:
            with self._conn_lock:
                self._conn.close()

        await asyncio.to_thread(_close)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def insert_run(self, row: Mapping[str, Any]) -> None:
        """Insert a new run record.

        ``row`` MUST contain every column from :data:`_COLUMNS`;
        ``params`` is stored as JSON.
        """
        await self.initialize()
        params_json = json.dumps(dict(row.get("params") or {}), default=str)
        sql = (
            "INSERT INTO experiment_runs ("
            "run_id, experiment, parent_run_id, status, host, python_version, "
            "kailash_ml_version, lightning_version, torch_version, cuda_version, "
            "git_sha, git_branch, git_dirty, wall_clock_start, wall_clock_end, "
            "duration_seconds, tenant_id, device_used, accelerator, precision, "
            "device_family, device_backend, device_fallback_reason, "
            "device_array_api, params, error_type, error_message"
            ") VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?"
            ")"
        )
        values = (
            row["run_id"],
            row["experiment"],
            row.get("parent_run_id"),
            row["status"],
            row.get("host"),
            row.get("python_version"),
            row.get("kailash_ml_version"),
            row.get("lightning_version"),
            row.get("torch_version"),
            row.get("cuda_version"),
            row.get("git_sha"),
            row.get("git_branch"),
            _bool_to_int(row.get("git_dirty")),
            row.get("wall_clock_start"),
            row.get("wall_clock_end"),
            row.get("duration_seconds"),
            row.get("tenant_id"),
            row.get("device_used"),
            row.get("accelerator"),
            row.get("precision"),
            row.get("device_family"),
            row.get("device_backend"),
            row.get("device_fallback_reason"),
            _bool_to_int(row.get("device_array_api")),
            params_json,
            row.get("error_type"),
            row.get("error_message"),
        )

        def _write() -> None:
            with self._conn_lock:
                self._conn.execute(sql, values)

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def update_run(self, run_id: str, fields: Mapping[str, Any]) -> None:
        """Update selected columns on an existing run row.

        ``fields`` keys MUST be a subset of :data:`_COLUMNS` — arbitrary
        keys are rejected to prevent dynamic identifier interpolation.
        """
        await self.initialize()
        allowed = set(_UPDATABLE_COLUMNS)
        unknown = set(fields.keys()) - allowed
        if unknown:
            raise ValueError(
                f"SQLiteTrackerBackend.update_run received unknown column(s) "
                f"{sorted(unknown)}; allowed: {sorted(allowed)}"
            )
        if not fields:
            return

        assignments: list[str] = []
        values: list[Any] = []
        for name, value in fields.items():
            assignments.append(f"{name} = ?")
            if name in _BOOLEAN_COLUMNS:
                values.append(_bool_to_int(value))
            elif name == "params":
                values.append(json.dumps(dict(value or {}), default=str))
            else:
                values.append(value)
        values.append(run_id)
        sql = f"UPDATE experiment_runs SET {', '.join(assignments)} WHERE run_id = ?"

        def _write() -> None:
            with self._conn_lock:
                self._conn.execute(sql, tuple(values))

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def set_params(self, run_id: str, params: Mapping[str, Any]) -> None:
        """Merge-and-overwrite params for a run.

        Callers use this from ``ExperimentRun.set_param`` to accumulate
        params without hand-rolling JSON merging.
        """
        await self.initialize()
        current = await self.get_run(run_id)
        merged: dict[str, Any] = dict((current or {}).get("params") or {})
        merged.update({str(k): v for k, v in params.items()})
        await self.update_run(run_id, {"params": merged})

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Return the run row as a dict (or ``None`` if missing)."""
        await self.initialize()

        def _read() -> Optional[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(
                    "SELECT * FROM experiment_runs WHERE run_id = ?",
                    (run_id,),
                )
                return cur.fetchone()

        row = await asyncio.to_thread(_read)
        return _row_to_dict(row) if row else None

    async def list_runs(self, experiment: Optional[str] = None) -> list[dict[str, Any]]:
        """List runs, optionally filtered by experiment name."""
        await self.initialize()
        if experiment is None:
            sql = "SELECT * FROM experiment_runs ORDER BY wall_clock_start"
            params: tuple[Any, ...] = ()
        else:
            sql = (
                "SELECT * FROM experiment_runs WHERE experiment = ? "
                "ORDER BY wall_clock_start"
            )
            params = (experiment,)

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, params)
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # W13 — query primitives
    # ------------------------------------------------------------------

    async def query_runs(
        self,
        *,
        experiment: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Typed ``list_runs`` variant used by :class:`ExperimentTracker`.

        Accepts the spec §5.1 kwargs (``experiment`` / ``tenant_id`` /
        ``status`` / ``limit``) and composes them as an explicit
        ``AND`` chain. Returns raw row dicts; polars conversion lives
        in the tracker so the backend stays polars-agnostic.
        """
        await self.initialize()
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")

        clauses: list[str] = []
        params: list[Any] = []
        if experiment is not None:
            clauses.append("experiment = ?")
            params.append(experiment)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT * FROM experiment_runs"
            + where_sql
            + " ORDER BY wall_clock_end DESC, wall_clock_start DESC LIMIT ?"
        )
        params.append(int(limit))

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, tuple(params))
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [_row_to_dict(r) for r in rows]

    async def search_runs_raw(
        self, sql: str, params: Sequence[Any]
    ) -> list[dict[str, Any]]:
        """Execute a pre-built SELECT produced by
        :func:`kailash_ml.tracking.query.build_search_sql` and return row
        dicts.

        The SQL string is built from a static template + parameterised
        values — no user input is interpolated, so this path is safe
        even though the string is not audited locally. Identifier
        allowlisting lives in :mod:`kailash_ml.tracking.query`.
        """
        await self.initialize()

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, tuple(params))
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [_row_to_dict(r) for r in rows]

    async def list_experiments_summary(
        self, *, tenant_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Aggregate every experiment into a single summary row.

        Columns: ``experiment``, ``run_count``, ``finished_count``,
        ``failed_count``, ``killed_count``, ``latest_wall_clock_end``.
        Tenant-scoped when ``tenant_id`` is non-None.
        """
        await self.initialize()
        where = " WHERE tenant_id = ?" if tenant_id is not None else ""
        sql = (
            "SELECT experiment, "
            "COUNT(*) AS run_count, "
            "SUM(CASE WHEN status = 'FINISHED' THEN 1 ELSE 0 END) AS finished_count, "
            "SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed_count, "
            "SUM(CASE WHEN status = 'KILLED' THEN 1 ELSE 0 END) AS killed_count, "
            "MAX(wall_clock_end) AS latest_wall_clock_end "
            "FROM experiment_runs"
            + where
            + " GROUP BY experiment ORDER BY latest_wall_clock_end DESC"
        )
        params: tuple[Any, ...] = (tenant_id,) if tenant_id is not None else ()

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, params)
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # W12 — Logging primitives (metrics, artifacts, tags, model versions)
    # ------------------------------------------------------------------

    async def append_metric(
        self,
        run_id: str,
        key: str,
        value: float,
        step: Optional[int],
        timestamp: str,
    ) -> None:
        """Append one metric row. Append-only; no merge / update."""
        await self.initialize()
        sql = (
            "INSERT INTO experiment_metrics "
            "(run_id, key, step, value, timestamp) VALUES (?, ?, ?, ?, ?)"
        )
        values = (run_id, key, step, float(value), timestamp)

        def _write() -> None:
            with self._conn_lock:
                self._conn.execute(sql, values)

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def append_metrics_batch(
        self,
        run_id: str,
        rows: list[tuple[str, float, Optional[int], str]],
    ) -> None:
        """Append many metric rows atomically. ``rows`` is
        ``[(key, value, step, timestamp), ...]``.
        """
        await self.initialize()
        if not rows:
            return
        sql = (
            "INSERT INTO experiment_metrics "
            "(run_id, key, step, value, timestamp) VALUES (?, ?, ?, ?, ?)"
        )
        values = [(run_id, k, s, float(v), ts) for (k, v, s, ts) in rows]

        def _write() -> None:
            with self._conn_lock:
                self._conn.executemany(sql, values)

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def list_metrics(self, run_id: str) -> list[dict[str, Any]]:
        """Return every metric row for a run ordered by ``(key, step, id)``."""
        await self.initialize()
        sql = (
            "SELECT key, step, value, timestamp FROM experiment_metrics "
            "WHERE run_id = ? ORDER BY key, step, id"
        )

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, (run_id,))
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [dict(r) for r in rows]

    async def insert_artifact(
        self,
        run_id: str,
        name: str,
        sha256: str,
        content_type: Optional[str],
        size_bytes: int,
        storage_uri: str,
        created_at: str,
    ) -> bool:
        """Insert an artifact row; dedupe on ``(run_id, name, sha256)``.

        Returns ``True`` if a new row was inserted; ``False`` when the
        row already existed (content-addressed dedupe per spec §4.3).
        """
        await self.initialize()
        sql = (
            "INSERT OR IGNORE INTO experiment_artifacts "
            "(run_id, name, sha256, content_type, size_bytes, storage_uri, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        values = (
            run_id,
            name,
            sha256,
            content_type,
            int(size_bytes),
            storage_uri,
            created_at,
        )

        def _write() -> int:
            with self._conn_lock:
                cur = self._conn.execute(sql, values)
                return cur.rowcount

        async with self._async_lock:
            changed = await asyncio.to_thread(_write)
        return bool(changed)

    async def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        """Return every artifact row for a run ordered by ``created_at``."""
        await self.initialize()
        sql = (
            "SELECT name, sha256, content_type, size_bytes, storage_uri, created_at "
            "FROM experiment_artifacts WHERE run_id = ? ORDER BY created_at, name"
        )

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, (run_id,))
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [dict(r) for r in rows]

    async def upsert_tag(self, run_id: str, key: str, value: str) -> None:
        """Insert or update a single tag row."""
        await self.initialize()
        sql = (
            "INSERT INTO experiment_tags (run_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(run_id, key) DO UPDATE SET value = excluded.value"
        )

        def _write() -> None:
            with self._conn_lock:
                self._conn.execute(sql, (run_id, key, value))

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def upsert_tags(self, run_id: str, tags: Mapping[str, str]) -> None:
        """Insert or update many tag rows atomically."""
        await self.initialize()
        if not tags:
            return
        sql = (
            "INSERT INTO experiment_tags (run_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(run_id, key) DO UPDATE SET value = excluded.value"
        )
        values = [(run_id, k, v) for k, v in tags.items()]

        def _write() -> None:
            with self._conn_lock:
                self._conn.executemany(sql, values)

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def list_tags(self, run_id: str) -> dict[str, str]:
        """Return the tag map for a run."""
        await self.initialize()
        sql = "SELECT key, value FROM experiment_tags WHERE run_id = ?"

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, (run_id,))
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return {r["key"]: r["value"] for r in rows}

    async def insert_model_version(
        self,
        run_id: str,
        name: str,
        format: str,
        artifact_sha: str,
        signature_json: Optional[str],
        lineage_json: Optional[str],
        created_at: str,
    ) -> None:
        """Insert a run-scoped model-version snapshot (spec §4.5)."""
        await self.initialize()
        sql = (
            "INSERT INTO experiment_model_versions "
            "(run_id, name, format, artifact_sha, signature_json, lineage_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        values = (
            run_id,
            name,
            format,
            artifact_sha,
            signature_json,
            lineage_json,
            created_at,
        )

        def _write() -> None:
            with self._conn_lock:
                self._conn.execute(sql, values)

        async with self._async_lock:
            await asyncio.to_thread(_write)

    async def list_model_versions(self, run_id: str) -> list[dict[str, Any]]:
        """Return model-version rows for a run ordered by ``created_at``."""
        await self.initialize()
        sql = (
            "SELECT name, format, artifact_sha, signature_json, lineage_json, created_at "
            "FROM experiment_model_versions WHERE run_id = ? ORDER BY created_at, name"
        )

        def _read() -> list[sqlite3.Row]:
            with self._conn_lock:
                cur = self._conn.execute(sql, (run_id,))
                return list(cur.fetchall())

        rows = await asyncio.to_thread(_read)
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLUMNS = (
    "run_id",
    "experiment",
    "parent_run_id",
    "status",
    "host",
    "python_version",
    "kailash_ml_version",
    "lightning_version",
    "torch_version",
    "cuda_version",
    "git_sha",
    "git_branch",
    "git_dirty",
    "wall_clock_start",
    "wall_clock_end",
    "duration_seconds",
    "tenant_id",
    "device_used",
    "accelerator",
    "precision",
    "device_family",
    "device_backend",
    "device_fallback_reason",
    "device_array_api",
    "params",
    "error_type",
    "error_message",
)

# Columns allowed on the update path (same set, fixed identifiers only —
# prevents dynamic identifier interpolation into the UPDATE statement).
_UPDATABLE_COLUMNS: set[str] = {
    c for c in _COLUMNS if c not in ("run_id", "experiment")
}

_BOOLEAN_COLUMNS = {"git_dirty", "device_array_api"}


def _bool_to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _int_to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out: dict[str, Any] = dict(row)
    # Deserialise JSON params
    raw = out.get("params") or "{}"
    try:
        out["params"] = json.loads(raw)
    except (TypeError, ValueError):
        out["params"] = {}
    # Convert boolean-shaped integer columns back to bool / None
    for col in _BOOLEAN_COLUMNS:
        if col in out:
            out[col] = _int_to_bool(out[col])
    return out

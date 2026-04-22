# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQLite implementation of :class:`AbstractTrackerStore`.

Routes every statement through :class:`kailash.core.pool.AsyncSQLitePool`
per ``specs/ml-tracking.md`` §6.1 + ``rules/patterns.md`` "SQLite
Connection Management". The pool:

- One writer, multiple readers (WAL mode).
- PRAGMA stack applied at connect time
  (``journal_mode=WAL`` / ``busy_timeout=30000`` / ``synchronous=NORMAL``
  / ``cache_size=-20000`` / ``foreign_keys=ON``).
- Bounded reader concurrency via semaphore.
- URI shared-cache for ``:memory:`` — two backend instances against
  the same logical address see one database (named memory cache).

All SQL uses fixed identifiers + ``?`` parameterised values per
``rules/infrastructure-sql.md``. The UPDATE path enforces an allowlist
on ``fields`` keys so a caller cannot interpolate an arbitrary
identifier.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from kailash.core.pool.sqlite_pool import AsyncSQLitePool, SQLitePoolConfig
from kailash.db.dialect import _validate_identifier

__all__ = ["SqliteTrackerStore"]


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

# W15 — audit + GDPR infrastructure. Kept parallel to the ``experiment_*``
# naming of the 0.x-era tables so the schema-unification shard (deferred
# per the wave plan) can rename the entire surface in one pass without
# forcing W15 to block on it. Spec trace: ml-tracking.md §8.2 / §8.4.
_AUDIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_audit (
    audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id      TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    resource_kind  TEXT NOT NULL,
    resource_id    TEXT NOT NULL,
    action         TEXT NOT NULL,
    prev_state     TEXT,
    new_state      TEXT
);
"""

_AUDIT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_experiment_audit_tenant_actor_ts
    ON experiment_audit (tenant_id, actor_id, timestamp);
"""

# Append-only invariant (spec §8.4) — audit rows MUST NOT be rewritten
# or deleted. Per-dialect triggers raise ABORT on UPDATE / DELETE; the
# erasure path APPENDS a new row rather than rewriting existing ones
# so the forensic chain is preserved.
_AUDIT_NO_UPDATE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS experiment_audit_no_update
BEFORE UPDATE ON experiment_audit
BEGIN
    SELECT RAISE(ABORT, 'experiment_audit is append-only per ml-tracking.md S8.4');
END;
"""

_AUDIT_NO_DELETE_TRIGGER_SQL = """
CREATE TRIGGER IF NOT EXISTS experiment_audit_no_delete
BEFORE DELETE ON experiment_audit
BEGIN
    SELECT RAISE(ABORT, 'experiment_audit is append-only per ml-tracking.md S8.4');
END;
"""

_RUN_SUBJECTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_run_subjects (
    tenant_id  TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id, subject_id)
);
"""

_RUN_SUBJECTS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_experiment_run_subjects_tenant_subject
    ON experiment_run_subjects (tenant_id, subject_id);
"""

# Pre-0.14 databases carried a narrower schema. First access probes
# ``PRAGMA table_info`` and ALTER TABLE any missing columns so existing
# ``~/.kailash_ml/ml.db`` files keep working after the 0.14 schema
# expansion. Column names MUST match the 0.14 schema exactly; the list
# is hardcoded so the migration cannot inject identifiers from user
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


# Shared named memory cache — two SqliteTrackerStore(":memory:") handles
# see the same database. Plain ``:memory:`` gives every handle a private
# DB which breaks test fixtures that open two stores.
_SHARED_MEMORY_URI = "file:memdb_kailash_ml?mode=memory&cache=shared"


# In-memory runs land artifacts under the user's home by default —
# tests override via ``HOME`` or ``$KAILASH_ML_HOME``.
_DEFAULT_ARTIFACT_MEMORY_DIR = Path.home() / ".kailash_ml" / "artifacts-memory"


class SqliteTrackerStore:
    """SQLite backend for :class:`AbstractTrackerStore` via
    :class:`AsyncSQLitePool`.

    Args:
        db_path: Filesystem path (or ``":memory:"``) to the SQLite
            database. Parent directory is created if missing.
        max_read_connections: Max concurrent readers on file-based DBs
            (per ``rules/connection-pool.md`` — ``:memory:`` forces
            single-connection mode so the value is ignored).
    """

    def __init__(self, db_path: str | Path, *, max_read_connections: int = 5) -> None:
        # Preserve the user-supplied logical address for error messages
        # and artifact-root resolution. The URI rewrite for ``:memory:``
        # is internal to the pool.
        self._db_path = str(db_path)
        if self._db_path == ":memory:":
            connect_path = _SHARED_MEMORY_URI
            use_uri = True
        else:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            connect_path = self._db_path
            use_uri = False

        config = SQLitePoolConfig(
            db_path=connect_path,
            max_read_connections=max_read_connections,
            pragmas={
                "journal_mode": "WAL",
                "busy_timeout": "30000",
                "synchronous": "NORMAL",
                "cache_size": "-20000",
                "foreign_keys": "ON",
            },
            uri=use_uri,
        )
        self._pool = AsyncSQLitePool(config)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def artifact_root(self) -> Optional[str]:
        """Resolved directory where ``log_artifact`` materialises blobs.

        - ``:memory:`` → ``~/.kailash_ml/artifacts-memory`` (tests set
          ``$HOME`` / use ``tmp_path`` to isolate).
        - ``/foo/bar/ml.db`` → ``/foo/bar/artifacts``.

        Returning the resolved directory (not the DB path) lets the
        Postgres backend supply its own root without the caller
        needing to know which backend it has — the Protocol promises a
        directory, every backend delivers one.
        """
        if self._db_path == ":memory:":
            return str(_DEFAULT_ARTIFACT_MEMORY_DIR)
        return str(Path(self._db_path).parent / "artifacts")

    async def initialize(self) -> None:
        """Create schema if absent. Idempotent.

        Also migrates pre-0.14 databases by adding columns that landed
        in 0.14 (seven reproducibility fields — see
        :data:`_COLUMNS_ADDED_IN_0_14`). Migration is additive (ALTER
        TABLE ADD COLUMN) so existing rows stay readable; new columns
        default to SQL NULL.
        """
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            async with self._pool.acquire_write() as conn:
                await conn.execute(_SCHEMA_SQL)
                await conn.execute(_INDEX_SQL)
                await conn.execute(_METRICS_SCHEMA_SQL)
                await conn.execute(_METRICS_INDEX_SQL)
                await conn.execute(_ARTIFACTS_SCHEMA_SQL)
                await conn.execute(_ARTIFACTS_SHA_INDEX_SQL)
                await conn.execute(_TAGS_SCHEMA_SQL)
                await conn.execute(_MODEL_VERSIONS_SCHEMA_SQL)
                # W15 audit + GDPR tables.
                await conn.execute(_AUDIT_SCHEMA_SQL)
                await conn.execute(_AUDIT_INDEX_SQL)
                await conn.execute(_AUDIT_NO_UPDATE_TRIGGER_SQL)
                await conn.execute(_AUDIT_NO_DELETE_TRIGGER_SQL)
                await conn.execute(_RUN_SUBJECTS_SCHEMA_SQL)
                await conn.execute(_RUN_SUBJECTS_INDEX_SQL)
                # Detect pre-0.14 databases and add missing columns.
                cur = await conn.execute("PRAGMA table_info(experiment_runs)")
                rows = await cur.fetchall()
                existing = {row[1] for row in rows}
                for name, sql_type in _COLUMNS_ADDED_IN_0_14:
                    if name not in existing:
                        # Defense-in-depth validation per
                        # ``rules/dataflow-identifier-safety.md`` §5 —
                        # hardcoded lists MUST still validate so the
                        # check survives any future refactor that makes
                        # the list dynamic. ``sql_type`` is pinned to
                        # ``TEXT`` in :data:`_COLUMNS_ADDED_IN_0_14`.
                        _validate_identifier(name)
                        await conn.execute(
                            f"ALTER TABLE experiment_runs "
                            f"ADD COLUMN {name} {sql_type}"
                        )
                await conn.commit()
            self._initialized = True

    async def close(self) -> None:
        """Release every connection managed by the pool."""
        await self._pool.close()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def insert_run(self, row: Mapping[str, Any]) -> None:
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
        async with self._pool.acquire_write() as conn:
            await conn.execute(sql, values)
            await conn.commit()

    async def update_run(self, run_id: str, fields: Mapping[str, Any]) -> None:
        await self.initialize()
        allowed = set(_UPDATABLE_COLUMNS)
        unknown = set(fields.keys()) - allowed
        if unknown:
            raise ValueError(
                f"SqliteTrackerStore.update_run received unknown column(s) "
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
        sql = (
            f"UPDATE experiment_runs SET {', '.join(assignments)} " f"WHERE run_id = ?"
        )
        async with self._pool.acquire_write() as conn:
            await conn.execute(sql, tuple(values))
            await conn.commit()

    async def set_params(self, run_id: str, params: Mapping[str, Any]) -> None:
        await self.initialize()
        current = await self.get_run(run_id)
        merged: dict[str, Any] = dict((current or {}).get("params") or {})
        merged.update({str(k): v for k, v in params.items()})
        await self.update_run(run_id, {"params": merged})

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        await self.initialize()
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(
                "SELECT * FROM experiment_runs WHERE run_id = ?",
                (run_id,),
            )
            row = await cur.fetchone()
        return _row_to_dict(row) if row else None

    async def list_runs(self, experiment: Optional[str] = None) -> list[dict[str, Any]]:
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
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def query_runs(
        self,
        *,
        experiment: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
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
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def search_runs_raw(
        self, sql: str, params: Sequence[Any]
    ) -> list[dict[str, Any]]:
        await self.initialize()
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def list_experiments_summary(
        self, *, tenant_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
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
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    async def append_metric(
        self,
        run_id: str,
        key: str,
        value: float,
        step: Optional[int],
        timestamp: str,
    ) -> None:
        await self.initialize()
        sql = (
            "INSERT INTO experiment_metrics "
            "(run_id, key, step, value, timestamp) VALUES (?, ?, ?, ?, ?)"
        )
        values = (run_id, key, step, float(value), timestamp)
        async with self._pool.acquire_write() as conn:
            await conn.execute(sql, values)
            await conn.commit()

    async def append_metrics_batch(
        self,
        run_id: str,
        rows: list[tuple[str, float, Optional[int], str]],
    ) -> None:
        await self.initialize()
        if not rows:
            return
        sql = (
            "INSERT INTO experiment_metrics "
            "(run_id, key, step, value, timestamp) VALUES (?, ?, ?, ?, ?)"
        )
        values = [(run_id, k, s, float(v), ts) for (k, v, s, ts) in rows]
        async with self._pool.acquire_write() as conn:
            await conn.executemany(sql, values)
            await conn.commit()

    async def list_metrics(self, run_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        sql = (
            "SELECT key, step, value, timestamp FROM experiment_metrics "
            "WHERE run_id = ? ORDER BY key, step, id"
        )
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, (run_id,))
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

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
        async with self._pool.acquire_write() as conn:
            cur = await conn.execute(sql, values)
            await conn.commit()
            changed = cur.rowcount
        return bool(changed)

    async def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        sql = (
            "SELECT name, sha256, content_type, size_bytes, storage_uri, created_at "
            "FROM experiment_artifacts WHERE run_id = ? ORDER BY created_at, name"
        )
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, (run_id,))
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    async def upsert_tag(self, run_id: str, key: str, value: str) -> None:
        await self.initialize()
        sql = (
            "INSERT INTO experiment_tags (run_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(run_id, key) DO UPDATE SET value = excluded.value"
        )
        async with self._pool.acquire_write() as conn:
            await conn.execute(sql, (run_id, key, value))
            await conn.commit()

    async def upsert_tags(self, run_id: str, tags: Mapping[str, str]) -> None:
        await self.initialize()
        if not tags:
            return
        sql = (
            "INSERT INTO experiment_tags (run_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(run_id, key) DO UPDATE SET value = excluded.value"
        )
        values = [(run_id, k, v) for k, v in tags.items()]
        async with self._pool.acquire_write() as conn:
            await conn.executemany(sql, values)
            await conn.commit()

    async def list_tags(self, run_id: str) -> dict[str, str]:
        await self.initialize()
        sql = "SELECT key, value FROM experiment_tags WHERE run_id = ?"
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, (run_id,))
            rows = await cur.fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ------------------------------------------------------------------
    # Model versions
    # ------------------------------------------------------------------

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
        async with self._pool.acquire_write() as conn:
            await conn.execute(sql, values)
            await conn.commit()

    async def list_model_versions(self, run_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        sql = (
            "SELECT name, format, artifact_sha, signature_json, lineage_json, created_at "
            "FROM experiment_model_versions WHERE run_id = ? ORDER BY created_at, name"
        )
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, (run_id,))
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # W15 — audit + GDPR subject persistence
    # ------------------------------------------------------------------

    async def insert_audit_row(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        timestamp: str,
        resource_kind: str,
        resource_id: str,
        action: str,
        prev_state: Optional[str] = None,
        new_state: Optional[str] = None,
    ) -> None:
        await self.initialize()
        sql = (
            "INSERT INTO experiment_audit "
            "(tenant_id, actor_id, timestamp, resource_kind, resource_id, "
            "action, prev_state, new_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        values = (
            tenant_id,
            actor_id,
            timestamp,
            resource_kind,
            resource_id,
            action,
            prev_state,
            new_state,
        )
        async with self._pool.acquire_write() as conn:
            await conn.execute(sql, values)
            await conn.commit()

    async def list_audit_rows(
        self,
        *,
        tenant_id: str,
        actor_id: Optional[str] = None,
        resource_kind: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
        clauses: list[str] = ["tenant_id = ?"]
        params: list[Any] = [tenant_id]
        if actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if resource_kind is not None:
            clauses.append("resource_kind = ?")
            params.append(resource_kind)
        if resource_id is not None:
            clauses.append("resource_id = ?")
            params.append(resource_id)
        sql = (
            "SELECT audit_id, tenant_id, actor_id, timestamp, resource_kind, "
            "resource_id, action, prev_state, new_state FROM experiment_audit "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY timestamp, audit_id LIMIT ?"
        )
        params.append(int(limit))
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def register_run_subjects(
        self,
        *,
        tenant_id: str,
        run_id: str,
        subject_ids: Sequence[str],
    ) -> None:
        await self.initialize()
        # Dedupe — callers may replay with the same subject set.
        uniq = sorted({str(s) for s in subject_ids if s})
        if not uniq:
            return
        sql = (
            "INSERT OR IGNORE INTO experiment_run_subjects "
            "(tenant_id, run_id, subject_id) VALUES (?, ?, ?)"
        )
        values = [(tenant_id, run_id, s) for s in uniq]
        async with self._pool.acquire_write() as conn:
            await conn.executemany(sql, values)
            await conn.commit()

    async def list_subject_runs(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> list[str]:
        await self.initialize()
        sql = (
            "SELECT DISTINCT run_id FROM experiment_run_subjects "
            "WHERE tenant_id = ? AND subject_id = ? ORDER BY run_id"
        )
        async with self._pool.acquire_read() as conn:
            cur = await conn.execute(sql, (tenant_id, subject_id))
            rows = await cur.fetchall()
        return [r[0] if not isinstance(r, dict) else r["run_id"] for r in rows]

    async def erase_subject_content(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> dict[str, int]:
        await self.initialize()
        run_ids = await self.list_subject_runs(
            tenant_id=tenant_id, subject_id=subject_id
        )
        if not run_ids:
            return {
                "runs": 0,
                "params": 0,
                "metrics": 0,
                "artifacts": 0,
                "tags": 0,
                "model_versions": 0,
                "subjects": 0,
            }
        placeholders = ",".join("?" * len(run_ids))
        counters: dict[str, int] = {"runs": len(run_ids)}
        async with self._pool.acquire_write() as conn:
            # Metrics
            cur = await conn.execute(
                f"DELETE FROM experiment_metrics WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )
            counters["metrics"] = cur.rowcount or 0
            # Artifacts
            cur = await conn.execute(
                f"DELETE FROM experiment_artifacts WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )
            counters["artifacts"] = cur.rowcount or 0
            # Tags
            cur = await conn.execute(
                f"DELETE FROM experiment_tags WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )
            counters["tags"] = cur.rowcount or 0
            # Model versions
            cur = await conn.execute(
                f"DELETE FROM experiment_model_versions WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )
            counters["model_versions"] = cur.rowcount or 0
            # Null-out params JSON on each affected run (retain the row
            # shell per spec §8.4 — the run record persists for audit
            # forensics; its mutable content is cleared).
            cur = await conn.execute(
                f"UPDATE experiment_runs SET params = '{{}}' "
                f"WHERE run_id IN ({placeholders})",
                tuple(run_ids),
            )
            counters["params"] = cur.rowcount or 0
            # Subject-link rows for this tenant+subject pair.
            cur = await conn.execute(
                "DELETE FROM experiment_run_subjects "
                "WHERE tenant_id = ? AND subject_id = ?",
                (tenant_id, subject_id),
            )
            counters["subjects"] = cur.rowcount or 0
            await conn.commit()
        return counters


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


def _row_to_dict(row: Any) -> dict[str, Any]:
    out: dict[str, Any] = dict(row)
    raw = out.get("params") or "{}"
    try:
        out["params"] = json.loads(raw)
    except (TypeError, ValueError):
        out["params"] = {}
    for col in _BOOLEAN_COLUMNS:
        if col in out:
            out[col] = _int_to_bool(out[col])
    return out

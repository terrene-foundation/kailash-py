# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL implementation of :class:`AbstractTrackerStore`.

Routes every statement through :class:`kailash.db.connection.ConnectionManager`
using ``?`` canonical placeholders per ``rules/infrastructure-sql.md``
Rule 3 — ``ConnectionManager.translate_query`` converts to ``$N`` before
handing to asyncpg.

The on-disk schema mirrors the SQLite backend's ``experiment_*``
tables so the W14b parity invariant holds without a translation layer
at read time. Native PostgreSQL types (TIMESTAMPTZ, JSONB, BOOLEAN)
are deferred to the spec-mandated ``_kml_*`` schema unification (a
later wave in the 34-wave plan); keeping types identical across
backends is the cheapest structural defense against parity drift
until that wave lands.

``artifact_root`` is supplied at construction. Unlike SQLite — which
materialises artifacts next to the DB file — PostgreSQL has no
natural on-disk root, so callers MUST pass the path explicitly.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from kailash.db.connection import ConnectionManager

__all__ = ["PostgresTrackerStore"]


# ---------------------------------------------------------------------------
# DDL — PostgreSQL dialect. Fixed identifiers (no interpolation).
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
    duration_seconds         DOUBLE PRECISION,
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
)
"""

_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_runs_experiment "
    "ON experiment_runs (experiment)"
)

_METRICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_metrics (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    key         TEXT NOT NULL,
    step        BIGINT,
    value       DOUBLE PRECISION NOT NULL,
    timestamp   TEXT NOT NULL
)
"""

_METRICS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_metrics_run_key_step "
    "ON experiment_metrics (run_id, key, step)"
)

_ARTIFACTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_artifacts (
    run_id        TEXT NOT NULL,
    name          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    content_type  TEXT,
    size_bytes    BIGINT NOT NULL,
    storage_uri   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    PRIMARY KEY (run_id, name, sha256)
)
"""

_ARTIFACTS_SHA_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_artifacts_run_sha "
    "ON experiment_artifacts (run_id, sha256)"
)

_TAGS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_tags (
    run_id  TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (run_id, key)
)
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
)
"""


class PostgresTrackerStore:
    """PostgreSQL backend for :class:`AbstractTrackerStore` via
    :class:`ConnectionManager`.

    Args:
        url: ``postgresql://user:pass@host:port/dbname`` URL.
        artifact_root: Filesystem root where :meth:`insert_artifact`
            callers materialise blobs. Required — Postgres has no
            natural on-disk counterpart to the SQLite DB path.
    """

    def __init__(self, url: str, *, artifact_root: str | Path) -> None:
        if not url:
            raise ValueError("PostgresTrackerStore requires a non-empty URL")
        self._url = url
        self._artifact_root = str(artifact_root)
        Path(self._artifact_root).mkdir(parents=True, exist_ok=True)
        self._conn = ConnectionManager(url)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def artifact_root(self) -> Optional[str]:
        return self._artifact_root

    async def initialize(self) -> None:
        """Connect the pool + create schema if absent. Idempotent."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await self._conn.initialize()
            # ConnectionManager.execute() auto-commits on PostgreSQL;
            # each DDL lands as its own statement. IF NOT EXISTS keeps
            # the method idempotent across re-entries.
            await self._conn.execute(_SCHEMA_SQL)
            await self._conn.execute(_INDEX_SQL)
            await self._conn.execute(_METRICS_SCHEMA_SQL)
            await self._conn.execute(_METRICS_INDEX_SQL)
            await self._conn.execute(_ARTIFACTS_SCHEMA_SQL)
            await self._conn.execute(_ARTIFACTS_SHA_INDEX_SQL)
            await self._conn.execute(_TAGS_SCHEMA_SQL)
            await self._conn.execute(_MODEL_VERSIONS_SCHEMA_SQL)
            self._initialized = True

    async def close(self) -> None:
        """Release the underlying pool."""
        await self._conn.close()

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
        await self._conn.execute(sql, *values)

    async def update_run(self, run_id: str, fields: Mapping[str, Any]) -> None:
        await self.initialize()
        allowed = set(_UPDATABLE_COLUMNS)
        unknown = set(fields.keys()) - allowed
        if unknown:
            raise ValueError(
                f"PostgresTrackerStore.update_run received unknown column(s) "
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
        await self._conn.execute(sql, *values)

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
        row = await self._conn.fetchone(
            "SELECT * FROM experiment_runs WHERE run_id = ?", run_id
        )
        return _row_to_dict(row) if row else None

    async def list_runs(self, experiment: Optional[str] = None) -> list[dict[str, Any]]:
        await self.initialize()
        if experiment is None:
            rows = await self._conn.fetch(
                "SELECT * FROM experiment_runs ORDER BY wall_clock_start"
            )
        else:
            rows = await self._conn.fetch(
                "SELECT * FROM experiment_runs WHERE experiment = ? "
                "ORDER BY wall_clock_start",
                experiment,
            )
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
        rows = await self._conn.fetch(sql, *params)
        return [_row_to_dict(r) for r in rows]

    async def search_runs_raw(
        self, sql: str, params: Sequence[Any]
    ) -> list[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(sql, *params)
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
        if tenant_id is not None:
            rows = await self._conn.fetch(sql, tenant_id)
        else:
            rows = await self._conn.fetch(sql)
        # PostgreSQL's SUM(CASE ...) returns numeric; coerce to int
        # so the parity invariant vs SQLite holds (SQLite returns int).
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            for col in ("run_count", "finished_count", "failed_count", "killed_count"):
                if d.get(col) is not None:
                    d[col] = int(d[col])
            out.append(d)
        return out

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
        await self._conn.execute(
            "INSERT INTO experiment_metrics "
            "(run_id, key, step, value, timestamp) VALUES (?, ?, ?, ?, ?)",
            run_id,
            key,
            step,
            float(value),
            timestamp,
        )

    async def append_metrics_batch(
        self,
        run_id: str,
        rows: list[tuple[str, float, Optional[int], str]],
    ) -> None:
        await self.initialize()
        if not rows:
            return
        # ConnectionManager.transaction yields a TransactionProxy that
        # performs dialect translation on every statement. Wrapping the
        # batch in one transaction makes the insert atomic — parity
        # with SQLite's ``executemany`` inside a write-locked context.
        sql = (
            "INSERT INTO experiment_metrics "
            "(run_id, key, step, value, timestamp) VALUES (?, ?, ?, ?, ?)"
        )
        async with self._conn.transaction() as tx:
            for key, value, step, ts in rows:
                await tx.execute(sql, run_id, key, step, float(value), ts)

    async def list_metrics(self, run_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT key, step, value, timestamp FROM experiment_metrics "
            "WHERE run_id = ? ORDER BY key, step, id",
            run_id,
        )
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
        # ``RETURNING 1`` detects the ON CONFLICT DO NOTHING path —
        # fetchone returns None when the conflict fires, a 1-row dict
        # on new insert. Mirrors SQLite's ``INSERT OR IGNORE`` +
        # rowcount-based detection.
        row = await self._conn.fetchone(
            "INSERT INTO experiment_artifacts "
            "(run_id, name, sha256, content_type, size_bytes, storage_uri, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (run_id, name, sha256) DO NOTHING RETURNING 1",
            run_id,
            name,
            sha256,
            content_type,
            int(size_bytes),
            storage_uri,
            created_at,
        )
        return row is not None

    async def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT name, sha256, content_type, size_bytes, storage_uri, created_at "
            "FROM experiment_artifacts WHERE run_id = ? ORDER BY created_at, name",
            run_id,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    async def upsert_tag(self, run_id: str, key: str, value: str) -> None:
        await self.initialize()
        await self._conn.execute(
            "INSERT INTO experiment_tags (run_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT (run_id, key) DO UPDATE SET value = excluded.value",
            run_id,
            key,
            value,
        )

    async def upsert_tags(self, run_id: str, tags: Mapping[str, str]) -> None:
        await self.initialize()
        if not tags:
            return
        sql = (
            "INSERT INTO experiment_tags (run_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT (run_id, key) DO UPDATE SET value = excluded.value"
        )
        async with self._conn.transaction() as tx:
            for k, v in tags.items():
                await tx.execute(sql, run_id, k, v)

    async def list_tags(self, run_id: str) -> dict[str, str]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT key, value FROM experiment_tags WHERE run_id = ?",
            run_id,
        )
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
        await self._conn.execute(
            "INSERT INTO experiment_model_versions "
            "(run_id, name, format, artifact_sha, signature_json, lineage_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            run_id,
            name,
            format,
            artifact_sha,
            signature_json,
            lineage_json,
            created_at,
        )

    async def list_model_versions(self, run_id: str) -> list[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT name, format, artifact_sha, signature_json, lineage_json, created_at "
            "FROM experiment_model_versions WHERE run_id = ? ORDER BY created_at, name",
            run_id,
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers — identical to the SQLite-side helpers, duplicated here so
# the Postgres backend has no structural dependency on the SQLite
# backend's module (rule: storage backends are siblings, not a chain).
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

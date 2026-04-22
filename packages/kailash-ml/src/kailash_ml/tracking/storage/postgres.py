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
import uuid
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

# W15 — audit + GDPR infrastructure. Parity with the SQLite backend;
# schema-unification to ``_kml_*`` is a later wave.
_AUDIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_audit (
    audit_id       BIGSERIAL PRIMARY KEY,
    tenant_id      TEXT NOT NULL,
    actor_id       TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    resource_kind  TEXT NOT NULL,
    resource_id    TEXT NOT NULL,
    action         TEXT NOT NULL,
    prev_state     TEXT,
    new_state      TEXT
)
"""

_AUDIT_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_audit_tenant_actor_ts "
    "ON experiment_audit (tenant_id, actor_id, timestamp)"
)

# pl/pgSQL function + triggers to block UPDATE / DELETE on the audit
# table. ``CREATE OR REPLACE FUNCTION`` is idempotent; ``CREATE TRIGGER``
# needs a ``DROP IF EXISTS`` dance because PostgreSQL lacks
# ``CREATE OR REPLACE TRIGGER`` until v14.
_AUDIT_FN_SQL = (
    "CREATE OR REPLACE FUNCTION experiment_audit_reject_mutation() "
    "RETURNS TRIGGER AS $$ "
    "BEGIN RAISE EXCEPTION "
    "'experiment_audit is append-only per ml-tracking.md S8.4'; "
    "END; $$ LANGUAGE plpgsql"
)

_AUDIT_DROP_UPDATE_TRIGGER_SQL = (
    "DROP TRIGGER IF EXISTS experiment_audit_no_update ON experiment_audit"
)

_AUDIT_DROP_DELETE_TRIGGER_SQL = (
    "DROP TRIGGER IF EXISTS experiment_audit_no_delete ON experiment_audit"
)

_AUDIT_CREATE_UPDATE_TRIGGER_SQL = (
    "CREATE TRIGGER experiment_audit_no_update "
    "BEFORE UPDATE ON experiment_audit "
    "FOR EACH ROW EXECUTE FUNCTION experiment_audit_reject_mutation()"
)

_AUDIT_CREATE_DELETE_TRIGGER_SQL = (
    "CREATE TRIGGER experiment_audit_no_delete "
    "BEFORE DELETE ON experiment_audit "
    "FOR EACH ROW EXECUTE FUNCTION experiment_audit_reject_mutation()"
)

_RUN_SUBJECTS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_run_subjects (
    tenant_id  TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, run_id, subject_id)
)
"""

_RUN_SUBJECTS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_run_subjects_tenant_subject "
    "ON experiment_run_subjects (tenant_id, subject_id)"
)

# W16 — model registry (``ml-registry.md`` §3-§7). Parallel-schema with
# SQLite per ``ml-tracking.md`` §6. ``experiment_registry_*`` prefix
# matches SQLite; the schema-unification shard renames every
# ``experiment_*`` table to ``_kml_*`` per spec §5A in one pass.
_REGISTRY_VERSIONS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_registry_versions (
    id                        TEXT PRIMARY KEY,
    tenant_id                 TEXT NOT NULL,
    name                      TEXT NOT NULL,
    version                   INTEGER NOT NULL,
    format                    TEXT NOT NULL,
    artifact_uri              TEXT NOT NULL,
    artifact_sha256           TEXT NOT NULL,
    signature_json            TEXT NOT NULL,
    signature_sha256          TEXT NOT NULL,
    lineage_run_id            TEXT NOT NULL,
    lineage_dataset_hash      TEXT NOT NULL,
    lineage_code_sha          TEXT NOT NULL,
    lineage_parent_version_id TEXT,
    idempotency_key           TEXT NOT NULL,
    is_golden                 BOOLEAN NOT NULL DEFAULT FALSE,
    onnx_status               TEXT,
    onnx_unsupported_ops      TEXT,
    onnx_opset_imports        TEXT,
    ort_extensions            TEXT,
    metadata_json             TEXT,
    actor_id                  TEXT NOT NULL,
    created_at                TEXT NOT NULL,
    UNIQUE (tenant_id, name, version)
)
"""

_REGISTRY_VERSIONS_TENANT_NAME_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_registry_versions_tenant_name "
    "ON experiment_registry_versions (tenant_id, name)"
)

_REGISTRY_VERSIONS_IDEMPOTENCY_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS "
    "idx_experiment_registry_versions_idempotency "
    "ON experiment_registry_versions (tenant_id, name, idempotency_key)"
)

# W18 — alias table per ``ml-registry.md`` §4. See the SQLite-side
# comment for the rationale; this is the Postgres-dialect mirror.
_REGISTRY_ALIASES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_registry_aliases (
    id                 TEXT PRIMARY KEY,
    tenant_id          TEXT NOT NULL,
    model_name         TEXT NOT NULL,
    alias              TEXT NOT NULL,
    model_version_id   TEXT NOT NULL,
    actor_id           TEXT NOT NULL,
    set_at             TEXT NOT NULL,
    cleared_at         TEXT,
    sequence_num       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, model_name, alias)
)
"""

_REGISTRY_ALIASES_TENANT_NAME_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_registry_aliases_tenant_name "
    "ON experiment_registry_aliases (tenant_id, model_name)"
)

_REGISTRY_ALIASES_VERSION_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_experiment_registry_aliases_version_id "
    "ON experiment_registry_aliases (model_version_id)"
)


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
            # W15 audit + GDPR tables.
            await self._conn.execute(_AUDIT_SCHEMA_SQL)
            await self._conn.execute(_AUDIT_INDEX_SQL)
            await self._conn.execute(_AUDIT_FN_SQL)
            await self._conn.execute(_AUDIT_DROP_UPDATE_TRIGGER_SQL)
            await self._conn.execute(_AUDIT_CREATE_UPDATE_TRIGGER_SQL)
            await self._conn.execute(_AUDIT_DROP_DELETE_TRIGGER_SQL)
            await self._conn.execute(_AUDIT_CREATE_DELETE_TRIGGER_SQL)
            await self._conn.execute(_RUN_SUBJECTS_SCHEMA_SQL)
            await self._conn.execute(_RUN_SUBJECTS_INDEX_SQL)
            # W16 registry tables.
            await self._conn.execute(_REGISTRY_VERSIONS_SCHEMA_SQL)
            await self._conn.execute(_REGISTRY_VERSIONS_TENANT_NAME_INDEX_SQL)
            await self._conn.execute(_REGISTRY_VERSIONS_IDEMPOTENCY_INDEX_SQL)
            # W18 alias table.
            await self._conn.execute(_REGISTRY_ALIASES_SCHEMA_SQL)
            await self._conn.execute(_REGISTRY_ALIASES_TENANT_NAME_INDEX_SQL)
            await self._conn.execute(_REGISTRY_ALIASES_VERSION_INDEX_SQL)
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
        await self._conn.execute(
            sql,
            tenant_id,
            actor_id,
            timestamp,
            resource_kind,
            resource_id,
            action,
            prev_state,
            new_state,
        )

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
        rows = await self._conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def register_run_subjects(
        self,
        *,
        tenant_id: str,
        run_id: str,
        subject_ids: Sequence[str],
    ) -> None:
        await self.initialize()
        uniq = sorted({str(s) for s in subject_ids if s})
        if not uniq:
            return
        sql = (
            "INSERT INTO experiment_run_subjects "
            "(tenant_id, run_id, subject_id) VALUES (?, ?, ?) "
            "ON CONFLICT (tenant_id, run_id, subject_id) DO NOTHING"
        )
        async with self._conn.transaction() as tx:
            for s in uniq:
                await tx.execute(sql, tenant_id, run_id, s)

    async def list_subject_runs(
        self,
        *,
        tenant_id: str,
        subject_id: str,
    ) -> list[str]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT DISTINCT run_id FROM experiment_run_subjects "
            "WHERE tenant_id = ? AND subject_id = ? ORDER BY run_id",
            tenant_id,
            subject_id,
        )
        return [r["run_id"] if isinstance(r, dict) else r[0] for r in rows]

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
        counters: dict[str, int] = {"runs": len(run_ids)}
        # ``?`` placeholders in a CM ``= ANY($)`` clause — the dialect
        # translator expands ``?`` to ``$N``; passing the list as a
        # single parameter gives PG an array to match against, keeping
        # the statement count-free regardless of the number of runs.
        async with self._conn.transaction() as tx:
            counters["metrics"] = await _pg_delete_count(
                tx,
                "DELETE FROM experiment_metrics WHERE run_id = ANY(?)",
                run_ids,
            )
            counters["artifacts"] = await _pg_delete_count(
                tx,
                "DELETE FROM experiment_artifacts WHERE run_id = ANY(?)",
                run_ids,
            )
            counters["tags"] = await _pg_delete_count(
                tx,
                "DELETE FROM experiment_tags WHERE run_id = ANY(?)",
                run_ids,
            )
            counters["model_versions"] = await _pg_delete_count(
                tx,
                "DELETE FROM experiment_model_versions WHERE run_id = ANY(?)",
                run_ids,
            )
            counters["params"] = await _pg_delete_count(
                tx,
                "UPDATE experiment_runs SET params = '{}' " "WHERE run_id = ANY(?)",
                run_ids,
            )
            counters["subjects"] = await _pg_delete_count(
                tx,
                "DELETE FROM experiment_run_subjects "
                "WHERE tenant_id = ? AND subject_id = ?",
                [tenant_id, subject_id],
                expand=False,
            )
        return counters

    # ------------------------------------------------------------------
    # Model registry (W16 — ml-registry.md §3-§7)
    # ------------------------------------------------------------------

    async def insert_model_registration(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        name: str,
        format: str,
        artifact_uri: str,
        artifact_sha256: str,
        signature_json: str,
        signature_sha256: str,
        lineage_run_id: str,
        lineage_dataset_hash: str,
        lineage_code_sha: str,
        lineage_parent_version_id: Optional[str],
        idempotency_key: str,
        is_golden: bool,
        onnx_status: Optional[str],
        onnx_unsupported_ops: Optional[str],
        onnx_opset_imports: Optional[str],
        ort_extensions: Optional[str],
        metadata_json: Optional[str],
        created_at: str,
    ) -> dict[str, Any]:
        await self.initialize()
        row_id = str(uuid.uuid4())
        # Single-statement atomic insert per ml-registry.md §3.2. The
        # next version is computed from the same table inside the INSERT;
        # two concurrent callers either serialise on the unique index
        # (one succeeds, the other retries via the idempotency-key check
        # or surfaces the integrity error) or end up with distinct
        # versions because each caller's COALESCE(MAX) sees the prior's
        # commit. RETURNING * gives us the assigned version in one
        # round-trip.
        sql = (
            "INSERT INTO experiment_registry_versions ("
            "id, tenant_id, name, version, format, artifact_uri, "
            "artifact_sha256, signature_json, signature_sha256, "
            "lineage_run_id, lineage_dataset_hash, lineage_code_sha, "
            "lineage_parent_version_id, idempotency_key, is_golden, "
            "onnx_status, onnx_unsupported_ops, onnx_opset_imports, "
            "ort_extensions, metadata_json, actor_id, created_at"
            ") VALUES ("
            "?, ?, ?, COALESCE("
            "(SELECT MAX(version) FROM experiment_registry_versions "
            "WHERE tenant_id = ? AND name = ?), 0) + 1, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "RETURNING *"
        )
        rows = await self._conn.fetch(
            sql,
            row_id,
            tenant_id,
            name,
            tenant_id,
            name,
            format,
            artifact_uri,
            artifact_sha256,
            signature_json,
            signature_sha256,
            lineage_run_id,
            lineage_dataset_hash,
            lineage_code_sha,
            lineage_parent_version_id,
            idempotency_key,
            bool(is_golden),
            onnx_status,
            onnx_unsupported_ops,
            onnx_opset_imports,
            ort_extensions,
            metadata_json,
            actor_id,
            created_at,
        )
        if not rows:
            raise RuntimeError(
                "insert_model_registration failed to return inserted row"
            )
        return _pg_registry_row_to_dict(rows[0])

    async def find_model_registration_by_idempotency_key(
        self,
        *,
        tenant_id: str,
        name: str,
        idempotency_key: str,
    ) -> Optional[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT * FROM experiment_registry_versions "
            "WHERE tenant_id = ? AND name = ? AND idempotency_key = ? "
            "LIMIT 1",
            tenant_id,
            name,
            idempotency_key,
        )
        if not rows:
            return None
        return _pg_registry_row_to_dict(rows[0])

    async def get_model_version(
        self,
        *,
        tenant_id: str,
        name: str,
        version: int,
    ) -> Optional[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT * FROM experiment_registry_versions "
            "WHERE tenant_id = ? AND name = ? AND version = ?",
            tenant_id,
            name,
            int(version),
        )
        if not rows:
            return None
        return _pg_registry_row_to_dict(rows[0])

    async def list_model_versions_by_name(
        self,
        *,
        tenant_id: str,
        name: str,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT * FROM experiment_registry_versions "
            "WHERE tenant_id = ? AND name = ? ORDER BY version ASC",
            tenant_id,
            name,
        )
        return [_pg_registry_row_to_dict(r) for r in rows]

    async def get_model_version_by_id(
        self,
        *,
        tenant_id: str,
        version_id: str,
    ) -> Optional[dict[str, Any]]:
        await self.initialize()
        row = await self._conn.fetchone(
            "SELECT * FROM experiment_registry_versions "
            "WHERE tenant_id = ? AND id = ?",
            tenant_id,
            version_id,
        )
        return _pg_registry_row_to_dict(row) if row is not None else None

    # ------------------------------------------------------------------
    # W18 — registry aliases (``ml-registry.md`` §4)
    # ------------------------------------------------------------------

    async def upsert_alias(
        self,
        *,
        tenant_id: str,
        model_name: str,
        alias: str,
        model_version_id: str,
        actor_id: str,
        set_at: str,
    ) -> dict[str, Any]:
        await self.initialize()
        # INSERT ... ON CONFLICT DO UPDATE atomically upserts the single
        # ``(tenant_id, model_name, alias)`` row. Postgres's RETURNING
        # gives us prev + new state without a follow-up SELECT. The
        # ``xmax = 0`` predicate (common PG trick) lets us detect
        # insert-vs-update: on INSERT xmax is 0; on UPDATE it's the old
        # row's txid. Using a CTE keeps the prev_* values readable
        # alongside the final row.
        row_id = str(uuid.uuid4())
        sql = (
            "WITH prev AS (SELECT id, model_version_id AS prev_mv, "
            "  cleared_at AS prev_cleared_at, sequence_num AS prev_seq "
            "  FROM experiment_registry_aliases "
            "  WHERE tenant_id = ? AND model_name = ? AND alias = ? "
            "  FOR UPDATE) "
            "INSERT INTO experiment_registry_aliases "
            "(id, tenant_id, model_name, alias, model_version_id, "
            " actor_id, set_at, cleared_at, sequence_num) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, "
            "  COALESCE((SELECT prev_seq FROM prev), 0) + 1) "
            "ON CONFLICT (tenant_id, model_name, alias) DO UPDATE SET "
            "  model_version_id = EXCLUDED.model_version_id, "
            "  actor_id = EXCLUDED.actor_id, "
            "  set_at = EXCLUDED.set_at, "
            "  cleared_at = NULL, "
            "  sequence_num = "
            "    experiment_registry_aliases.sequence_num + 1 "
            "RETURNING "
            "  (SELECT prev_mv FROM prev) AS prev_mv, "
            "  (SELECT prev_cleared_at FROM prev) AS prev_cleared_at, "
            "  sequence_num, model_version_id"
        )
        row = await self._conn.fetchone(
            sql,
            tenant_id,
            model_name,
            alias,
            row_id,
            tenant_id,
            model_name,
            alias,
            model_version_id,
            actor_id,
            set_at,
        )
        if row is None:
            raise RuntimeError("upsert_alias did not return a row")
        row_d = dict(row)
        prev_cleared = row_d.get("prev_cleared_at") is not None
        return {
            "prev_model_version_id": (None if prev_cleared else row_d.get("prev_mv")),
            "new_model_version_id": row_d["model_version_id"],
            "prev_cleared": prev_cleared,
            "sequence_num": int(row_d["sequence_num"]),
        }

    async def clear_alias(
        self,
        *,
        tenant_id: str,
        model_name: str,
        alias: str,
        actor_id: str,
        cleared_at: str,
    ) -> Optional[dict[str, Any]]:
        await self.initialize()
        sql = (
            "UPDATE experiment_registry_aliases SET "
            "  cleared_at = ?, actor_id = ?, "
            "  sequence_num = sequence_num + 1 "
            "WHERE tenant_id = ? AND model_name = ? AND alias = ? "
            "  AND cleared_at IS NULL "
            "RETURNING model_version_id, sequence_num"
        )
        row = await self._conn.fetchone(
            sql,
            cleared_at,
            actor_id,
            tenant_id,
            model_name,
            alias,
        )
        if row is None:
            return None
        row_d = dict(row)
        return {
            "prev_model_version_id": row_d["model_version_id"],
            "sequence_num": int(row_d["sequence_num"]),
        }

    async def get_alias(
        self,
        *,
        tenant_id: str,
        model_name: str,
        alias: str,
    ) -> Optional[dict[str, Any]]:
        await self.initialize()
        sql = (
            "SELECT v.* FROM experiment_registry_aliases a "
            "JOIN experiment_registry_versions v ON v.id = a.model_version_id "
            "WHERE a.tenant_id = ? AND a.model_name = ? AND a.alias = ? "
            "AND a.cleared_at IS NULL"
        )
        row = await self._conn.fetchone(sql, tenant_id, model_name, alias)
        return _pg_registry_row_to_dict(row) if row is not None else None

    async def list_aliases_for_version(
        self,
        *,
        tenant_id: str,
        model_version_id: str,
    ) -> list[str]:
        await self.initialize()
        rows = await self._conn.fetch(
            "SELECT alias FROM experiment_registry_aliases "
            "WHERE tenant_id = ? AND model_version_id = ? "
            "AND cleared_at IS NULL ORDER BY alias",
            tenant_id,
            model_version_id,
        )
        return [r["alias"] if isinstance(r, dict) else r[0] for r in rows]

    async def list_aliases_for_name(
        self,
        *,
        tenant_id: str,
        model_name: str,
        include_cleared: bool = False,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        clause = "" if include_cleared else " AND cleared_at IS NULL"
        sql = (
            "SELECT alias, model_version_id, actor_id, set_at, "
            "cleared_at, sequence_num "
            "FROM experiment_registry_aliases "
            "WHERE tenant_id = ? AND model_name = ?" + clause + " ORDER BY alias"
        )
        rows = await self._conn.fetch(sql, tenant_id, model_name)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # W18 — registry queries (``ml-registry.md`` §9)
    # ------------------------------------------------------------------

    async def list_registry_versions(
        self,
        *,
        tenant_id: str,
        name: Optional[str] = None,
        alias: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        # Parameters appended in FINAL-SQL order: JOIN(?) first, then
        # WHERE(?) clauses, then LIMIT/OFFSET — mirrors the SQLite
        # side. See sqlite.py for the full comment on the ordering
        # constraint.
        params: list[Any] = []
        join_sql = ""
        if alias is not None:
            join_sql = (
                " JOIN experiment_registry_aliases a "
                "ON a.model_version_id = v.id "
                "AND a.tenant_id = v.tenant_id "
                "AND a.cleared_at IS NULL "
                "AND a.alias = ?"
            )
            params.append(alias)
        clauses = ["v.tenant_id = ?"]
        params.append(tenant_id)
        if name is not None:
            clauses.append("v.name = ?")
            params.append(name)
        where_sql = " WHERE " + " AND ".join(clauses)
        sql = (
            "SELECT v.* FROM experiment_registry_versions v"
            + join_sql
            + where_sql
            + " ORDER BY v.name, v.version DESC LIMIT ? OFFSET ?"
        )
        params.extend([int(limit), int(offset)])
        rows = await self._conn.fetch(sql, *params)
        return [_pg_registry_row_to_dict(r) for r in rows]

    async def search_registry_versions(
        self,
        *,
        tenant_id: str,
        where_sql: str,
        params: Sequence[Any],
        order_by_sql: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
        clause = f" AND ({where_sql})" if where_sql else ""
        order = f" ORDER BY {order_by_sql}" if order_by_sql else ""
        sql = (
            "SELECT * FROM experiment_registry_versions "
            "WHERE tenant_id = ?" + clause + order + " LIMIT ?"
        )
        values: list[Any] = [tenant_id, *params, int(limit)]
        rows = await self._conn.fetch(sql, *values)
        return [_pg_registry_row_to_dict(r) for r in rows]


def _pg_registry_row_to_dict(row: Any) -> dict[str, Any]:
    """Normalise a Postgres registry row — ``is_golden`` lands as a Python
    bool already via asyncpg, but surfacing through ``dict(row)`` keeps
    downstream code decoupled from the Record type."""
    out: dict[str, Any] = dict(row)
    if "is_golden" in out:
        out["is_golden"] = bool(out["is_golden"])
    return out


async def _pg_delete_count(tx: Any, sql: str, arg: Any, *, expand: bool = True) -> int:
    """Execute ``sql`` inside a transaction and return the affected-row count.

    ``ConnectionManager`` surfaces ``execute`` as "fire-and-forget"; the
    affected-row count is exposed by the underlying asyncpg status string.
    We parse that string (``DELETE <n>`` / ``UPDATE <n>``) to keep the
    counters accurate — a zero here would silently hide a bug in the
    GDPR erasure path. When ``expand`` is True the single list argument
    is passed as one parameter; when False, the list is a positional
    parameter sequence.
    """
    if expand:
        result = await tx.execute(sql, arg)
    else:
        result = await tx.execute(sql, *arg)
    if isinstance(result, str):
        parts = result.strip().split()
        if parts and parts[-1].isdigit():
            return int(parts[-1])
    return 0


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

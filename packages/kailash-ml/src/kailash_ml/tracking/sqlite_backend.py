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
from typing import Any, Mapping, Optional

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
    git_sha                  TEXT,
    git_branch               TEXT,
    git_dirty                INTEGER,
    wall_clock_start         TEXT,
    wall_clock_end           TEXT,
    duration_seconds         REAL,
    tenant_id                TEXT,
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
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        # ``check_same_thread=False`` lets us reuse the connection across
        # the worker threads that ``asyncio.to_thread`` hands us. The
        # ``_conn_lock`` makes that safe.
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; per-statement atomic
        )
        self._conn.row_factory = sqlite3.Row
        # WAL is not meaningful for ``:memory:`` — sqlite3 silently
        # accepts the pragma but there is no on-disk journal.
        if self._db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Create the schema if absent. Idempotent."""
        if self._initialized:
            return

        def _init() -> None:
            with self._conn_lock:
                self._conn.execute(_SCHEMA_SQL)
                self._conn.execute(_INDEX_SQL)

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
            "git_sha, git_branch, git_dirty, wall_clock_start, wall_clock_end, "
            "duration_seconds, tenant_id, device_family, device_backend, "
            "device_fallback_reason, device_array_api, params, error_type, "
            "error_message"
            ") VALUES ("
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
            ")"
        )
        values = (
            row["run_id"],
            row["experiment"],
            row.get("parent_run_id"),
            row["status"],
            row.get("host"),
            row.get("python_version"),
            row.get("git_sha"),
            row.get("git_branch"),
            _bool_to_int(row.get("git_dirty")),
            row.get("wall_clock_start"),
            row.get("wall_clock_end"),
            row.get("duration_seconds"),
            row.get("tenant_id"),
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
    "git_sha",
    "git_branch",
    "git_dirty",
    "wall_clock_start",
    "wall_clock_end",
    "duration_seconds",
    "tenant_id",
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
_UPDATABLE_COLUMNS = set(_COLUMNS) - {"run_id", "experiment"}

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

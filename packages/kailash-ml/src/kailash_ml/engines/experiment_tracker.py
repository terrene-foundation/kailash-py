# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ExperimentTracker engine -- experiment lifecycle, run logging, metric history.

Provides MLflow-compatible experiment tracking: experiments, runs, parameters,
step-based metrics (training curves), and artifact metadata. All persistence
is via ConnectionManager (same pattern as ModelRegistry and FeatureStore).

Artifacts are stored on the local filesystem under ``artifact_root``.
Database stores metadata only -- no binary blobs in SQL.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import _validate_identifier

logger = logging.getLogger(__name__)

__all__ = [
    "ExperimentTracker",
    "Experiment",
    "Run",
    "MetricEntry",
    "RunComparison",
    "RunContext",
    "ExperimentNotFoundError",
    "RunNotFoundError",
]

# ---------------------------------------------------------------------------
# Valid run statuses
# ---------------------------------------------------------------------------

VALID_STATUSES = {"RUNNING", "COMPLETED", "FAILED", "KILLED"}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExperimentNotFoundError(Exception):
    """Raised when an experiment is not found."""


class RunNotFoundError(Exception):
    """Raised when a run is not found."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Experiment:
    """An experiment grouping related runs."""

    id: str
    name: str
    description: str
    created_at: str
    tags: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "tags": dict(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Experiment:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            tags=data.get("tags", {}),
        )


@dataclass(frozen=True)
class Run:
    """A single training/evaluation run within an experiment."""

    id: str
    experiment_id: str
    name: str
    status: str  # RUNNING, COMPLETED, FAILED, KILLED
    start_time: str
    end_time: str | None
    tags: dict[str, str]
    params: dict[str, str]
    metrics: dict[str, float]  # Latest value per key
    artifacts: list[str]  # Artifact paths

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "tags": dict(self.tags),
            "params": dict(self.params),
            "metrics": dict(self.metrics),
            "artifacts": list(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        return cls(
            id=data["id"],
            experiment_id=data["experiment_id"],
            name=data.get("name", ""),
            status=data.get("status", "RUNNING"),
            start_time=data.get("start_time", ""),
            end_time=data.get("end_time"),
            tags=data.get("tags", {}),
            params=data.get("params", {}),
            metrics=data.get("metrics", {}),
            artifacts=data.get("artifacts", []),
        )


@dataclass(frozen=True)
class MetricEntry:
    """A single metric data point (for training curves)."""

    key: str
    value: float
    step: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "step": self.step,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricEntry:
        return cls(
            key=data["key"],
            value=data["value"],
            step=data.get("step", 0),
            timestamp=data.get("timestamp", ""),
        )


@dataclass(frozen=True)
class RunComparison:
    """Tabular comparison of metrics and params across runs."""

    run_ids: list[str]
    run_names: list[str]
    params: dict[str, list[str | None]]  # param_key -> [value_per_run]
    metrics: dict[str, list[float | None]]  # metric_key -> [value_per_run]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_ids": list(self.run_ids),
            "run_names": list(self.run_names),
            "params": {k: list(v) for k, v in self.params.items()},
            "metrics": {k: list(v) for k, v in self.metrics.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunComparison:
        return cls(
            run_ids=data["run_ids"],
            run_names=data["run_names"],
            params=data.get("params", {}),
            metrics=data.get("metrics", {}),
        )


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


async def _create_tracker_tables(conn: ConnectionManager) -> None:
    """Create experiment tracking tables if they do not exist."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS kailash_experiments ("
        "  id TEXT PRIMARY KEY,"
        "  name TEXT UNIQUE NOT NULL,"
        "  description TEXT DEFAULT '',"
        "  created_at TEXT NOT NULL,"
        "  tags_json TEXT DEFAULT '{}'"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS kailash_runs ("
        "  id TEXT PRIMARY KEY,"
        "  experiment_id TEXT NOT NULL,"
        "  name TEXT DEFAULT '',"
        "  status TEXT NOT NULL DEFAULT 'RUNNING',"
        "  start_time TEXT NOT NULL,"
        "  end_time TEXT,"
        "  tags_json TEXT DEFAULT '{}',"
        "  FOREIGN KEY (experiment_id) REFERENCES kailash_experiments(id)"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS kailash_run_params ("
        "  run_id TEXT NOT NULL,"
        "  key TEXT NOT NULL,"
        "  value TEXT NOT NULL,"
        "  PRIMARY KEY (run_id, key),"
        "  FOREIGN KEY (run_id) REFERENCES kailash_runs(id)"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS kailash_run_metrics ("
        "  run_id TEXT NOT NULL,"
        "  key TEXT NOT NULL,"
        "  value REAL NOT NULL,"
        "  step INTEGER DEFAULT 0,"
        "  timestamp TEXT NOT NULL,"
        "  FOREIGN KEY (run_id) REFERENCES kailash_runs(id)"
        ")"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_run_key "
        "ON kailash_run_metrics(run_id, key)"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS kailash_run_artifacts ("
        "  run_id TEXT NOT NULL,"
        "  path TEXT NOT NULL,"
        "  file_size INTEGER DEFAULT 0,"
        "  timestamp TEXT NOT NULL,"
        "  PRIMARY KEY (run_id, path),"
        "  FOREIGN KEY (run_id) REFERENCES kailash_runs(id)"
        ")"
    )


def _row_to_experiment(row: dict[str, Any]) -> Experiment:
    """Convert a database row to an Experiment dataclass."""
    tags_json = row.get("tags_json", "{}")
    return Experiment(
        id=row["id"],
        name=row["name"],
        description=row.get("description", ""),
        created_at=row.get("created_at", ""),
        tags=json.loads(tags_json) if tags_json else {},
    )


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def _validate_artifact_path(path: str) -> None:
    """Prevent path traversal in artifact paths."""
    if ".." in path or path.startswith("/") or path.startswith("\\"):
        raise ValueError(
            f"Invalid artifact path '{path}': must not contain '..' or start with '/' or '\\'"
        )
    if "\x00" in path:
        raise ValueError(f"Invalid artifact path '{path}': must not contain null bytes")


def _validate_status(status: str) -> None:
    """Validate run status against allowlist."""
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {sorted(VALID_STATUSES)}"
        )


def _validate_metric_value(value: float) -> None:
    """Reject NaN and Inf metric values."""
    if not math.isfinite(value):
        raise ValueError(
            f"Metric value must be finite, got {value}. " "NaN and Inf are not allowed."
        )


# ---------------------------------------------------------------------------
# RunContext (async context manager)
# ---------------------------------------------------------------------------


class RunContext:
    """Async context manager for run lifecycle.

    Usage::

        async with tracker.run("my-exp", run_name="trial-1") as ctx:
            ctx.log_params({"lr": "0.01"})
            ctx.log_metric("loss", 0.5, step=0)
            ctx.log_artifact("model.pkl")

    On normal exit: run is marked COMPLETED.
    On exception: run is marked FAILED.
    """

    def __init__(self, tracker: ExperimentTracker, run: Run) -> None:
        self._tracker = tracker
        self._run = run
        self._failed = False

    @property
    def run_id(self) -> str:
        return self._run.id

    @property
    def run(self) -> Run:
        return self._run

    async def log_param(self, key: str, value: str) -> None:
        """Log a single parameter."""
        await self._tracker.log_param(self._run.id, key, value)

    async def log_params(self, params: dict[str, str]) -> None:
        """Log multiple parameters."""
        await self._tracker.log_params(self._run.id, params)

    async def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        """Log a single metric value."""
        await self._tracker.log_metric(self._run.id, key, value, step)

    async def log_metrics(
        self, metrics: dict[str, float], step: int | None = None
    ) -> None:
        """Log multiple metrics."""
        await self._tracker.log_metrics(self._run.id, metrics, step)

    async def log_artifact(
        self, local_path: str, artifact_path: str | None = None
    ) -> None:
        """Copy file to artifact store, record metadata."""
        await self._tracker.log_artifact(self._run.id, local_path, artifact_path)

    async def set_tag(self, key: str, value: str) -> None:
        """Set a tag on the run."""
        await self._tracker.set_tag(self._run.id, key, value)

    async def __aenter__(self) -> RunContext:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self._tracker.end_run(self._run.id, status="FAILED")
        else:
            await self._tracker.end_run(self._run.id, status="COMPLETED")
        return None  # Do not suppress exceptions


# ---------------------------------------------------------------------------
# ExperimentTracker
# ---------------------------------------------------------------------------


class ExperimentTracker:
    """[P0: Production] Experiment tracking engine -- MLflow-compatible.

    Manages experiments, runs, parameters, step-based metrics, and artifact
    metadata. Artifacts are stored on the local filesystem; only metadata
    is persisted in the database.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
    artifact_root:
        Root directory for artifact storage. Defaults to ``./mlartifacts``.
    """

    def __init__(
        self,
        conn: ConnectionManager,
        artifact_root: str = "./mlartifacts",
        *,
        _owns_conn: bool = False,
    ) -> None:
        self._conn = conn
        self._artifact_root = Path(artifact_root)
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        self._initialized = False
        self._owns_conn = _owns_conn

    @classmethod
    async def create(
        cls,
        url: str = "sqlite:///experiments.db",
        artifact_root: str = "./mlartifacts",
    ) -> "ExperimentTracker":
        """Create an ExperimentTracker with an internally managed connection.

        Convenience factory for standalone usage. The returned tracker
        owns its connection -- call :meth:`close` or use as an async
        context manager to release resources.

        Args:
            url: Database URL (default: local SQLite).
            artifact_root: Directory for artifact storage.

        Returns:
            An initialized ExperimentTracker.
        """
        conn = ConnectionManager(url)
        await conn.initialize()
        return cls(conn, artifact_root, _owns_conn=True)

    async def close(self) -> None:
        """Close the tracker and release resources.

        Only closes the database connection if this tracker owns it
        (i.e., created via :meth:`create`). Trackers initialized with
        an external ``ConnectionManager`` leave connection lifecycle
        to the caller.
        """
        if self._owns_conn and self._conn is not None:
            await self._conn.close()

    async def __aenter__(self) -> "ExperimentTracker":
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def _ensure_tables(self) -> None:
        if not self._initialized:
            await _create_tracker_tables(self._conn)
            self._initialized = True

    # ------------------------------------------------------------------
    # Context manager for runs
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def run(
        self,
        experiment_name: str,
        run_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> AsyncIterator[RunContext]:
        """Context manager for run lifecycle.

        Auto-creates experiment if not exists. Ends run as COMPLETED on
        normal exit, FAILED on exception.
        """
        run_obj = await self.start_run(experiment_name, run_name, tags)
        ctx = RunContext(self, run_obj)
        try:
            yield ctx
        except BaseException:
            await self.end_run(run_obj.id, status="FAILED")
            raise
        else:
            await self.end_run(run_obj.id, status="COMPLETED")

    # ------------------------------------------------------------------
    # Experiment management
    # ------------------------------------------------------------------

    async def create_experiment(
        self,
        name: str,
        description: str = "",
        tags: dict[str, str] | None = None,
    ) -> str:
        """Create an experiment. Idempotent -- returns existing ID if name exists.

        Parameters
        ----------
        name:
            Unique experiment name.
        description:
            Optional description.
        tags:
            Optional key-value tags.

        Returns
        -------
        str
            Experiment ID (UUID).
        """
        await self._ensure_tables()

        tags = tags or {}
        now_iso = datetime.now(timezone.utc).isoformat()
        experiment_id = str(uuid.uuid4())
        tags_json = json.dumps(tags)

        # Use insert-ignore for idempotency (name is UNIQUE)
        sql = self._conn.dialect.insert_ignore(
            "kailash_experiments",
            ["id", "name", "description", "created_at", "tags_json"],
            ["name"],
        )
        await self._conn.execute(
            sql, experiment_id, name, description, now_iso, tags_json
        )

        # Fetch the experiment (may be pre-existing)
        row = await self._conn.fetchone(
            "SELECT id FROM kailash_experiments WHERE name = ?", name
        )
        if row is None:
            # Should not happen after insert_ignore, but fail-closed
            raise ExperimentNotFoundError(
                f"Failed to create or find experiment '{name}'"
            )

        logger.info("Experiment '%s' ensured (id=%s).", name, row["id"])
        return row["id"]

    async def get_experiment(self, name: str) -> Experiment:
        """Get experiment by name.

        Raises
        ------
        ExperimentNotFoundError
            If no experiment with the given name exists.
        """
        await self._ensure_tables()

        row = await self._conn.fetchone(
            "SELECT * FROM kailash_experiments WHERE name = ?", name
        )
        if row is None:
            raise ExperimentNotFoundError(f"Experiment '{name}' not found.")
        return _row_to_experiment(row)

    async def list_experiments(self) -> list[Experiment]:
        """List all experiments ordered by creation time."""
        await self._ensure_tables()

        rows = await self._conn.fetch(
            "SELECT * FROM kailash_experiments ORDER BY created_at"
        )
        return [_row_to_experiment(r) for r in rows]

    # ------------------------------------------------------------------
    # Run management
    # ------------------------------------------------------------------

    async def start_run(
        self,
        experiment_name: str,
        run_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> Run:
        """Start a new run. Auto-creates experiment if not exists.

        Parameters
        ----------
        experiment_name:
            Name of the parent experiment.
        run_name:
            Optional human-readable run name.
        tags:
            Optional key-value tags.

        Returns
        -------
        Run
            The newly created run (status=RUNNING).
        """
        await self._ensure_tables()

        # Ensure experiment exists
        experiment_id = await self.create_experiment(experiment_name)

        run_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        tags = tags or {}
        run_name = run_name or ""
        tags_json = json.dumps(tags)

        await self._conn.execute(
            "INSERT INTO kailash_runs "
            "(id, experiment_id, name, status, start_time, end_time, tags_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            run_id,
            experiment_id,
            run_name,
            "RUNNING",
            now_iso,
            None,
            tags_json,
        )

        logger.info(
            "Started run '%s' (id=%s) in experiment '%s'.",
            run_name,
            run_id,
            experiment_name,
        )

        return Run(
            id=run_id,
            experiment_id=experiment_id,
            name=run_name,
            status="RUNNING",
            start_time=now_iso,
            end_time=None,
            tags=tags,
            params={},
            metrics={},
            artifacts=[],
        )

    async def end_run(self, run_id: str, status: str = "COMPLETED") -> None:
        """End a run with the given status.

        Parameters
        ----------
        run_id:
            Run ID.
        status:
            Final status. Must be COMPLETED, FAILED, or KILLED.

        Raises
        ------
        ValueError
            If status is not valid.
        RunNotFoundError
            If run does not exist.
        """
        await self._ensure_tables()
        _validate_status(status)

        # Verify run exists
        row = await self._conn.fetchone(
            "SELECT id FROM kailash_runs WHERE id = ?", run_id
        )
        if row is None:
            raise RunNotFoundError(f"Run '{run_id}' not found.")

        now_iso = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE kailash_runs SET status = ?, end_time = ? WHERE id = ?",
            status,
            now_iso,
            run_id,
        )

        logger.info("Ended run '%s' with status %s.", run_id, status)

    async def get_run(self, run_id: str) -> Run:
        """Get a run with all params, latest metrics, and artifacts.

        Raises
        ------
        RunNotFoundError
            If run does not exist.
        """
        await self._ensure_tables()

        row = await self._conn.fetchone(
            "SELECT * FROM kailash_runs WHERE id = ?", run_id
        )
        if row is None:
            raise RunNotFoundError(f"Run '{run_id}' not found.")

        return await self._hydrate_run(row)

    async def list_runs(
        self,
        experiment_name: str,
        status: str | None = None,
    ) -> list[Run]:
        """List runs for an experiment, optionally filtered by status.

        Parameters
        ----------
        experiment_name:
            Experiment name.
        status:
            Optional status filter.

        Returns
        -------
        list[Run]
        """
        await self._ensure_tables()

        exp = await self.get_experiment(experiment_name)

        if status is not None:
            _validate_status(status)
            rows = await self._conn.fetch(
                "SELECT * FROM kailash_runs "
                "WHERE experiment_id = ? AND status = ? "
                "ORDER BY start_time DESC",
                exp.id,
                status,
            )
        else:
            rows = await self._conn.fetch(
                "SELECT * FROM kailash_runs "
                "WHERE experiment_id = ? ORDER BY start_time DESC",
                exp.id,
            )

        return [await self._hydrate_run(r) for r in rows]

    async def search_runs(
        self,
        experiment_name: str,
        filter_params: dict[str, str] | None = None,
        order_by: str | None = None,
        max_results: int = 100,
    ) -> list[Run]:
        """Search runs by parameter values.

        Parameters
        ----------
        experiment_name:
            Experiment name.
        filter_params:
            Dict of param key-value pairs to match.
        order_by:
            Ordering string like ``'metric.accuracy DESC'``.
        max_results:
            Maximum number of results (default 100).

        Returns
        -------
        list[Run]
        """
        await self._ensure_tables()

        exp = await self.get_experiment(experiment_name)

        # Start with all runs in this experiment
        if filter_params:
            # Build a query that finds runs matching ALL specified params
            # Uses N subquery joins for N filter conditions
            conditions = []
            args: list[Any] = [exp.id]
            for i, (pk, pv) in enumerate(filter_params.items()):
                alias = f"p{i}"
                conditions.append(
                    f"EXISTS (SELECT 1 FROM kailash_run_params {alias} "
                    f"WHERE {alias}.run_id = r.id AND {alias}.key = ? AND {alias}.value = ?)"
                )
                args.extend([pk, pv])

            where_clause = " AND ".join(conditions)
            query = (
                f"SELECT r.* FROM kailash_runs r "
                f"WHERE r.experiment_id = ? AND {where_clause} "
                f"ORDER BY r.start_time DESC LIMIT ?"
            )
            args.append(max_results)
            rows = await self._conn.fetch(query, *args)
        else:
            rows = await self._conn.fetch(
                "SELECT * FROM kailash_runs "
                "WHERE experiment_id = ? ORDER BY start_time DESC LIMIT ?",
                exp.id,
                max_results,
            )

        runs = [await self._hydrate_run(r) for r in rows]

        # Apply order_by on the hydrated runs (metric sorting requires
        # the latest metric value which is fetched during hydration)
        if order_by:
            runs = self._sort_runs(runs, order_by)

        return runs[:max_results]

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    async def log_param(self, run_id: str, key: str, value: str) -> None:
        """Log a single parameter. Idempotent (upsert).

        Parameters
        ----------
        run_id:
            Run ID.
        key:
            Parameter name.
        value:
            Parameter value (string).
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        sql, param_cols = self._conn.dialect.upsert(
            "kailash_run_params",
            ["run_id", "key", "value"],
            ["run_id", "key"],
        )
        await self._conn.execute(sql, run_id, key, value)

    async def log_params(self, run_id: str, params: dict[str, Any]) -> None:
        """Log multiple parameters.

        Parameters
        ----------
        run_id:
            Run ID.
        params:
            Dict of parameter name-value pairs. Values are converted to strings.
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        for k, v in params.items():
            sql, param_cols = self._conn.dialect.upsert(
                "kailash_run_params",
                ["run_id", "key", "value"],
                ["run_id", "key"],
            )
            await self._conn.execute(sql, run_id, k, str(v))

    async def log_metric(
        self,
        run_id: str,
        key: str,
        value: float,
        step: int | None = None,
    ) -> None:
        """Log a metric value. Supports step-based logging for training curves.

        Parameters
        ----------
        run_id:
            Run ID.
        key:
            Metric name.
        value:
            Metric value. Must be finite (NaN/Inf rejected).
        step:
            Optional step number (epoch, iteration). Auto-increments if None.
        """
        await self._ensure_tables()
        _validate_metric_value(value)
        await self._verify_run_exists(run_id)

        now_iso = datetime.now(timezone.utc).isoformat()

        if step is None:
            # Auto-increment: find the max step for this run+key
            row = await self._conn.fetchone(
                "SELECT COALESCE(MAX(step), -1) AS max_step "
                "FROM kailash_run_metrics WHERE run_id = ? AND key = ?",
                run_id,
                key,
            )
            step = (row["max_step"] if row else -1) + 1

        await self._conn.execute(
            "INSERT INTO kailash_run_metrics (run_id, key, value, step, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            run_id,
            key,
            value,
            step,
            now_iso,
        )

    async def log_metrics(
        self,
        run_id: str,
        metrics: dict[str, float],
        step: int | None = None,
    ) -> None:
        """Log multiple metrics.

        Parameters
        ----------
        run_id:
            Run ID.
        metrics:
            Dict of metric name-value pairs.
        step:
            Optional step number applied to all metrics.
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        for k, v in metrics.items():
            await self.log_metric(run_id, k, v, step)

    async def log_artifact(
        self,
        run_id: str,
        local_path: str,
        artifact_path: str | None = None,
    ) -> None:
        """Copy a file to the artifact store and record metadata.

        Parameters
        ----------
        run_id:
            Run ID.
        local_path:
            Path to the local file to store.
        artifact_path:
            Optional destination path within the run's artifact directory.
            Defaults to the filename of ``local_path``.
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        if not src.is_file():
            raise ValueError(f"Not a file: {local_path}")

        # Determine artifact path
        if artifact_path is None:
            artifact_path = src.name
        _validate_artifact_path(artifact_path)

        # Copy to artifact store
        dest_dir = self._artifact_root / run_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = (dest_dir / artifact_path).resolve()

        # Path traversal check: destination must be under artifact root
        if not str(dest).startswith(str(self._artifact_root.resolve())):
            raise ValueError(f"Path traversal detected: {artifact_path}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))

        file_size = dest.stat().st_size
        now_iso = datetime.now(timezone.utc).isoformat()

        # Record metadata (upsert in case of re-logging same artifact)
        sql, param_cols = self._conn.dialect.upsert(
            "kailash_run_artifacts",
            ["run_id", "path", "file_size", "timestamp"],
            ["run_id", "path"],
        )
        await self._conn.execute(sql, run_id, artifact_path, file_size, now_iso)

        logger.info(
            "Logged artifact '%s' for run '%s' (%d bytes).",
            artifact_path,
            run_id,
            file_size,
        )

    async def set_tag(self, run_id: str, key: str, value: str) -> None:
        """Set a tag on a run.

        Parameters
        ----------
        run_id:
            Run ID.
        key:
            Tag name.
        value:
            Tag value.
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        row = await self._conn.fetchone(
            "SELECT tags_json FROM kailash_runs WHERE id = ?", run_id
        )
        tags = json.loads(row["tags_json"]) if row and row["tags_json"] else {}
        tags[key] = value
        tags_json = json.dumps(tags)

        await self._conn.execute(
            "UPDATE kailash_runs SET tags_json = ? WHERE id = ?",
            tags_json,
            run_id,
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    async def compare_runs(self, run_ids: list[str]) -> RunComparison:
        """Compare metrics and params across runs.

        Parameters
        ----------
        run_ids:
            List of run IDs to compare.

        Returns
        -------
        RunComparison
            Tabular comparison with aligned param and metric values.
        """
        await self._ensure_tables()

        runs = []
        for rid in run_ids:
            runs.append(await self.get_run(rid))

        # Collect all param and metric keys across runs
        all_param_keys: set[str] = set()
        all_metric_keys: set[str] = set()
        for r in runs:
            all_param_keys.update(r.params.keys())
            all_metric_keys.update(r.metrics.keys())

        # Build aligned comparison
        params: dict[str, list[str | None]] = {}
        for pk in sorted(all_param_keys):
            params[pk] = [r.params.get(pk) for r in runs]

        metrics: dict[str, list[float | None]] = {}
        for mk in sorted(all_metric_keys):
            metrics[mk] = [r.metrics.get(mk) for r in runs]

        return RunComparison(
            run_ids=list(run_ids),
            run_names=[r.name for r in runs],
            params=params,
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Metric history
    # ------------------------------------------------------------------

    async def get_metric_history(self, run_id: str, key: str) -> list[MetricEntry]:
        """Get all logged values for a metric (for training curves).

        Parameters
        ----------
        run_id:
            Run ID.
        key:
            Metric name.

        Returns
        -------
        list[MetricEntry]
            All metric entries ordered by step.
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        rows = await self._conn.fetch(
            "SELECT key, value, step, timestamp "
            "FROM kailash_run_metrics "
            "WHERE run_id = ? AND key = ? ORDER BY step",
            run_id,
            key,
        )

        return [
            MetricEntry(
                key=r["key"],
                value=r["value"],
                step=r["step"],
                timestamp=r["timestamp"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def delete_run(self, run_id: str) -> None:
        """Delete a run and all its params, metrics, and artifacts.

        Parameters
        ----------
        run_id:
            Run ID to delete.

        Raises
        ------
        RunNotFoundError
            If run does not exist.
        """
        await self._ensure_tables()
        await self._verify_run_exists(run_id)

        # Delete in dependency order within a transaction
        async with self._conn.transaction() as tx:
            await tx.execute(
                "DELETE FROM kailash_run_artifacts WHERE run_id = ?", run_id
            )
            await tx.execute("DELETE FROM kailash_run_metrics WHERE run_id = ?", run_id)
            await tx.execute("DELETE FROM kailash_run_params WHERE run_id = ?", run_id)
            await tx.execute("DELETE FROM kailash_runs WHERE id = ?", run_id)

        # Clean up artifact directory
        artifact_dir = self._artifact_root / run_id
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)

        logger.info("Deleted run '%s' and all associated data.", run_id)

    async def delete_experiment(self, experiment_name: str) -> None:
        """Delete an experiment and all its runs.

        Parameters
        ----------
        experiment_name:
            Experiment name.

        Raises
        ------
        ExperimentNotFoundError
            If experiment does not exist.
        """
        await self._ensure_tables()

        exp = await self.get_experiment(experiment_name)

        # Get all runs for this experiment
        rows = await self._conn.fetch(
            "SELECT id FROM kailash_runs WHERE experiment_id = ?", exp.id
        )
        run_ids = [r["id"] for r in rows]

        # Delete all runs (cascading params, metrics, artifacts)
        for rid in run_ids:
            await self.delete_run(rid)

        # Delete experiment
        await self._conn.execute("DELETE FROM kailash_experiments WHERE id = ?", exp.id)

        logger.info(
            "Deleted experiment '%s' and %d run(s).",
            experiment_name,
            len(run_ids),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _verify_run_exists(self, run_id: str) -> None:
        """Verify a run exists, raise RunNotFoundError if not."""
        row = await self._conn.fetchone(
            "SELECT id FROM kailash_runs WHERE id = ?", run_id
        )
        if row is None:
            raise RunNotFoundError(f"Run '{run_id}' not found.")

    async def _hydrate_run(self, row: dict[str, Any]) -> Run:
        """Convert a run row + child data into a Run dataclass."""
        run_id = row["id"]
        tags_json = row.get("tags_json", "{}")

        # Fetch params
        param_rows = await self._conn.fetch(
            "SELECT key, value FROM kailash_run_params WHERE run_id = ?",
            run_id,
        )
        params = {r["key"]: r["value"] for r in param_rows}

        # Fetch latest metric per key
        metric_rows = await self._conn.fetch(
            "SELECT key, value FROM kailash_run_metrics "
            "WHERE run_id = ? AND (key, step) IN ("
            "  SELECT key, MAX(step) FROM kailash_run_metrics "
            "  WHERE run_id = ? GROUP BY key"
            ")",
            run_id,
            run_id,
        )
        metrics = {r["key"]: r["value"] for r in metric_rows}

        # Fetch artifact paths
        artifact_rows = await self._conn.fetch(
            "SELECT path FROM kailash_run_artifacts WHERE run_id = ?",
            run_id,
        )
        artifacts = [r["path"] for r in artifact_rows]

        return Run(
            id=run_id,
            experiment_id=row["experiment_id"],
            name=row.get("name", ""),
            status=row.get("status", "RUNNING"),
            start_time=row.get("start_time", ""),
            end_time=row.get("end_time"),
            tags=json.loads(tags_json) if tags_json else {},
            params=params,
            metrics=metrics,
            artifacts=artifacts,
        )

    @staticmethod
    def _sort_runs(runs: list[Run], order_by: str) -> list[Run]:
        """Sort runs by a metric or param specification.

        Supports ``'metric.<key> DESC'`` and ``'metric.<key> ASC'`` patterns.
        """
        parts = order_by.strip().split()
        if len(parts) < 1:
            return runs

        field_spec = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        reverse = direction == "DESC"

        if field_spec.startswith("metric."):
            metric_key = field_spec[len("metric.") :]

            def sort_key(r: Run) -> float:
                val = r.metrics.get(metric_key)
                if val is None:
                    return float("-inf") if reverse else float("inf")
                return val

            return sorted(runs, key=sort_key, reverse=reverse)

        if field_spec.startswith("param."):
            param_key = field_spec[len("param.") :]

            def sort_key_param(r: Run) -> str:
                val = r.params.get(param_key)
                return val if val is not None else ""

            return sorted(runs, key=sort_key_param, reverse=reverse)

        return runs

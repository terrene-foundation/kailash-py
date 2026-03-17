"""Database storage backend for task tracking."""

import json
import logging
import math
import re
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ..models import TaskMetrics, TaskRun, TaskStatus, WorkflowRun
from .base import StorageBackend

logger = logging.getLogger(__name__)

# Regex for validating search attribute names (safe identifier pattern)
_ATTR_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class SQLiteStorage(StorageBackend):
    """Optimized SQLite storage backend with WAL mode and inline metrics."""

    # Schema version for migrations
    SCHEMA_VERSION = 2

    def __init__(self, db_path: str | None = None):
        """Initialize with optimized pragmas and WAL mode.

        Args:
            db_path: Path to SQLite database file or sqlite:// URL (default: ~/.kailash/tracking/tracking.db)
        """
        import os
        import sqlite3

        if db_path is None:
            db_path = os.path.expanduser("~/.kailash/tracking/tracking.db")
        elif db_path.startswith("sqlite://"):
            # Support sqlite:// URL format for backward compatibility
            db_path = db_path.replace("sqlite://", "")
            db_path = os.path.expanduser(db_path)

        # Create parent directory if needed
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        # check_same_thread=False for cross-thread access (with locking)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()

        # Enable optimizations
        self._enable_optimizations()
        self._initialize_schema()

    def _enable_optimizations(self) -> None:
        """Enable WAL mode and optimal SQLite pragmas."""
        cursor = self.conn.cursor()

        # Enable WAL mode for concurrent access
        cursor.execute("PRAGMA journal_mode=WAL")

        # Busy timeout for concurrent access (5 seconds)
        cursor.execute("PRAGMA busy_timeout=5000")

        # Performance optimizations
        cursor.execute("PRAGMA synchronous=NORMAL")  # Reduced sync overhead
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        cursor.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        cursor.execute("PRAGMA foreign_keys=ON")  # Enforce FK constraints
        cursor.execute("PRAGMA automatic_index=ON")  # Auto-create better indexes

        self.conn.commit()

    def _initialize_schema(self) -> None:
        """Initialize database schema with optimizations."""
        cursor = self.conn.cursor()

        # Create schema version table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                upgraded_at TEXT NOT NULL
            )
        """
        )

        # Check current schema version
        cursor.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        result = cursor.fetchone()
        try:
            current_version = int(result[0]) if result else 0
        except (TypeError, ValueError):
            current_version = 0

        # Fresh database: create all schemas
        if current_version == 0:
            self._create_schema_v1()
            self._create_schema_v2()
            cursor.execute(
                "INSERT INTO schema_version (version, upgraded_at) VALUES (?, ?)",
                (self.SCHEMA_VERSION, datetime.now(UTC).isoformat()),
            )
            self.conn.commit()
        else:
            # Incremental migrations
            if current_version < 2:
                self._migrate_to_v2()
                cursor.execute(
                    "INSERT INTO schema_version (version, upgraded_at) VALUES (?, ?)",
                    (2, datetime.now(UTC).isoformat()),
                )
                self.conn.commit()

    def _create_schema_v1(self) -> None:
        """Create schema version 1 with inlined metrics and audit events."""
        cursor = self.conn.cursor()

        # Workflow runs table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                metadata TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Tasks table with inlined metrics
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'cancelled')),
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                result TEXT,
                error TEXT,
                metadata TEXT,
                input_data TEXT,
                output_data TEXT,
                metrics_duration REAL,
                metrics_cpu_usage REAL,
                metrics_memory_usage_mb REAL,
                metrics_custom TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
            )
        """
        )

        # Audit events table for CARE compliance
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                result TEXT NOT NULL CHECK (result IN ('success', 'failure', 'denied')),
                workflow_id TEXT,
                node_id TEXT,
                agent_id TEXT,
                human_origin_id TEXT,
                action TEXT,
                resource TEXT,
                context TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Optimized indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON workflow_runs(workflow_name)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_runs_created ON workflow_runs(created_at DESC)"
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_node ON tasks(node_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)"
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_trace ON audit_events(trace_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events(timestamp DESC)"
        )

        self.conn.commit()

    def _create_schema_v2(self) -> None:
        """Create schema version 2: workflow search attributes table."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_search_attributes (
                run_id      TEXT NOT NULL,
                attr_name   TEXT NOT NULL,
                attr_type   TEXT NOT NULL CHECK (attr_type IN ('text', 'int', 'float', 'datetime', 'bool')),
                text_value  TEXT,
                int_value   INTEGER,
                float_value REAL,
                dt_value    TEXT,
                PRIMARY KEY (run_id, attr_name)
            )
        """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sa_name_text ON workflow_search_attributes(attr_name, text_value)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sa_name_int ON workflow_search_attributes(attr_name, int_value)"
        )

        self.conn.commit()

    def _migrate_to_v2(self) -> None:
        """Migrate from schema v1 to v2: add workflow_search_attributes table."""
        self._create_schema_v2()

    def upsert_search_attributes(self, run_id: str, attributes: dict[str, Any]) -> None:
        """Upsert typed search attributes for a workflow run.

        Auto-detects attribute types and stores values in the appropriate
        typed column for efficient querying.

        Args:
            run_id: Workflow run ID.
            attributes: Key-value pairs to store. Values are auto-typed as
                text, int, float, datetime, or bool.

        Raises:
            ValueError: If an attribute name is invalid.
        """
        if not attributes:
            return

        with self._lock:
            cursor = self.conn.cursor()

            for attr_name, attr_value in attributes.items():
                # Validate attribute name
                if not _ATTR_NAME_RE.match(attr_name):
                    raise ValueError(
                        f"Invalid attribute name '{attr_name}': "
                        "must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
                    )

                # Auto-detect type and set appropriate column
                attr_type, text_val, int_val, float_val, dt_val = (
                    self._classify_attribute(attr_value)
                )

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO workflow_search_attributes
                    (run_id, attr_name, attr_type, text_value, int_value, float_value, dt_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        run_id,
                        attr_name,
                        attr_type,
                        text_val,
                        int_val,
                        float_val,
                        dt_val,
                    ),
                )

            self.conn.commit()

    def search_runs(
        self,
        filters: dict[str, Any],
        order_by: str = "created_at DESC",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Search workflow runs by search attribute filters.

        Builds a parameterized query that JOINs workflow_search_attributes
        with workflow_runs, applying one sub-condition per filter entry.

        Args:
            filters: Attribute name-value pairs to match.
            order_by: SQL ORDER BY clause (column must be from workflow_runs).
                      Only ``created_at``, ``started_at``, ``ended_at``,
                      ``workflow_name``, and ``status`` are accepted (with
                      optional ``ASC``/``DESC``).
            limit: Maximum number of results (capped at 1000).
            offset: Number of results to skip.

        Returns:
            List of workflow run dicts matching all filters.
        """
        # Validate order_by to prevent SQL injection
        allowed_columns = {
            "created_at",
            "started_at",
            "ended_at",
            "workflow_name",
            "status",
        }
        order_parts = order_by.strip().split()
        if not order_parts:
            order_by = "created_at DESC"
        else:
            col = order_parts[0]
            direction = order_parts[1].upper() if len(order_parts) > 1 else "DESC"
            if col not in allowed_columns:
                raise ValueError(
                    f"Invalid order_by column '{col}'. "
                    f"Allowed: {sorted(allowed_columns)}"
                )
            if direction not in ("ASC", "DESC"):
                raise ValueError(
                    f"Invalid order_by direction '{direction}'. Allowed: ASC, DESC"
                )
            order_by = f"w.{col} {direction}"

        # Cap limit
        limit = min(max(1, limit), 1000)
        offset = max(0, offset)

        with self._lock:
            cursor = self.conn.cursor()

            if not filters:
                # No attribute filters -- return recent runs
                query = f"SELECT w.* FROM workflow_runs w ORDER BY {order_by} LIMIT ? OFFSET ?"
                cursor.execute(query, (limit, offset))
            else:
                # Build JOINs for each filter attribute
                params: list[Any] = []
                join_clauses = []
                where_clauses = []

                for i, (attr_name, attr_value) in enumerate(filters.items()):
                    # Validate attribute name
                    if not _ATTR_NAME_RE.match(attr_name):
                        raise ValueError(
                            f"Invalid filter attribute name '{attr_name}': "
                            "must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
                        )

                    alias = f"sa{i}"
                    join_clauses.append(
                        f"JOIN workflow_search_attributes {alias} "
                        f"ON w.run_id = {alias}.run_id"
                    )
                    where_clauses.append(f"{alias}.attr_name = ?")
                    params.append(attr_name)

                    # Determine which typed column to compare
                    attr_type, text_val, int_val, float_val, dt_val = (
                        self._classify_attribute(attr_value)
                    )
                    if attr_type == "int":
                        where_clauses.append(f"{alias}.int_value = ?")
                        params.append(int_val)
                    elif attr_type == "float":
                        where_clauses.append(f"{alias}.float_value = ?")
                        params.append(float_val)
                    elif attr_type == "datetime":
                        where_clauses.append(f"{alias}.dt_value = ?")
                        params.append(dt_val)
                    elif attr_type == "bool":
                        where_clauses.append(f"{alias}.int_value = ?")
                        params.append(int_val)
                    else:
                        where_clauses.append(f"{alias}.text_value = ?")
                        params.append(text_val)

                joins_sql = " ".join(join_clauses)
                where_sql = " AND ".join(where_clauses)
                query = (
                    f"SELECT DISTINCT w.* FROM workflow_runs w "
                    f"{joins_sql} WHERE {where_sql} "
                    f"ORDER BY {order_by} LIMIT ? OFFSET ?"
                )
                params.extend([limit, offset])
                cursor.execute(query, params)

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            results = []
            for row in rows:
                data = dict(zip(columns, row, strict=False))
                if data.get("metadata"):
                    try:
                        data["metadata"] = json.loads(data["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        data["metadata"] = {}
                results.append(data)

            return results

    @staticmethod
    def _classify_attribute(
        value: Any,
    ) -> tuple[str, str | None, int | None, float | None, str | None]:
        """Classify a Python value into the search attribute type system.

        Returns:
            Tuple of (attr_type, text_value, int_value, float_value, dt_value).
        """
        if isinstance(value, bool):
            return ("bool", None, 1 if value else 0, None, None)
        if isinstance(value, int):
            return ("int", None, value, None, None)
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(f"Search attribute values must be finite: {value}")
            return ("float", None, None, value, None)
        if isinstance(value, datetime):
            return ("datetime", None, None, None, value.isoformat())
        # Default: text
        return ("text", str(value), None, None, None)

    def save_run(self, run: WorkflowRun) -> None:
        """Save a workflow run."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO workflow_runs
                (run_id, workflow_name, status, started_at, ended_at, metadata, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run.run_id,
                    run.workflow_name,
                    run.status,
                    run.started_at.isoformat(),
                    run.ended_at.isoformat() if run.ended_at else None,
                    json.dumps(run.metadata),
                    run.error,
                ),
            )
            self.conn.commit()

    def load_run(self, run_id: str) -> WorkflowRun | None:
        """Load a workflow run by ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()

            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, row, strict=False))
            data["metadata"] = json.loads(data["metadata"] or "{}")

            # Load task IDs from tasks table
            cursor.execute("SELECT task_id FROM tasks WHERE run_id = ?", (run_id,))
            data["tasks"] = [row[0] for row in cursor.fetchall()]

            return WorkflowRun.model_validate(data)

    def list_runs(
        self, workflow_name: str | None = None, status: str | None = None
    ) -> list[WorkflowRun]:
        """List workflow runs with optional filtering."""
        with self._lock:
            cursor = self.conn.cursor()

            query = "SELECT * FROM workflow_runs WHERE 1=1"
            params: list[Any] = []

            if workflow_name:
                query += " AND workflow_name = ?"
                params.append(workflow_name)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)

            runs = []
            columns = [desc[0] for desc in cursor.description]

            for row in cursor.fetchall():
                data = dict(zip(columns, row, strict=False))
                data["metadata"] = json.loads(data["metadata"] or "{}")

                cursor.execute(
                    "SELECT task_id FROM tasks WHERE run_id = ?", (data["run_id"],)
                )
                data["tasks"] = [row[0] for row in cursor.fetchall()]

                runs.append(WorkflowRun.model_validate(data))

            return runs

    def save_task(self, task: TaskRun) -> None:
        """Save a task with inlined metrics."""
        with self._lock:
            cursor = self.conn.cursor()

            metrics_duration = None
            metrics_cpu = None
            metrics_memory = None
            metrics_custom = None

            if task.metrics:
                metrics_duration = task.metrics.duration
                metrics_cpu = task.metrics.cpu_usage
                metrics_memory = task.metrics.memory_usage_mb
                if task.metrics.custom_metrics:
                    metrics_custom = json.dumps(task.metrics.custom_metrics)

            task_params = (
                task.task_id,
                task.run_id,
                task.node_id,
                task.node_type,
                task.status,
                task.started_at.isoformat() if task.started_at else None,
                task.ended_at.isoformat() if task.ended_at else None,
                json.dumps(task.result) if task.result else None,
                task.error,
                json.dumps(task.metadata),
                json.dumps(task.input_data) if task.input_data else None,
                json.dumps(task.output_data) if task.output_data else None,
            )

            # Save to primary tasks table with metrics inlined
            cursor.execute(
                """
                INSERT OR REPLACE INTO tasks
                (task_id, run_id, node_id, node_type, status, started_at, ended_at,
                 result, error, metadata, input_data, output_data,
                 metrics_duration, metrics_cpu_usage, metrics_memory_usage_mb, metrics_custom)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                task_params
                + (
                    metrics_duration,
                    metrics_cpu,
                    metrics_memory,
                    metrics_custom,
                ),
            )

            self.conn.commit()

    def save_tasks_batch(self, tasks: list[TaskRun]) -> None:
        """Batch insert tasks in single transaction using executemany()."""
        if not tasks:
            return

        with self._lock:
            cursor = self.conn.cursor()

            # Prepare batch data
            batch_data = []
            for task in tasks:
                metrics_duration = None
                metrics_cpu = None
                metrics_memory = None
                metrics_custom = None

                if task.metrics:
                    metrics_duration = task.metrics.duration
                    metrics_cpu = task.metrics.cpu_usage
                    metrics_memory = task.metrics.memory_usage_mb
                    if task.metrics.custom_metrics:
                        metrics_custom = json.dumps(task.metrics.custom_metrics)

                batch_data.append(
                    (
                        task.task_id,
                        task.run_id,
                        task.node_id,
                        task.node_type,
                        task.status,
                        task.started_at.isoformat() if task.started_at else None,
                        task.ended_at.isoformat() if task.ended_at else None,
                        json.dumps(task.result) if task.result else None,
                        task.error,
                        json.dumps(task.metadata),
                        json.dumps(task.input_data) if task.input_data else None,
                        json.dumps(task.output_data) if task.output_data else None,
                        metrics_duration,
                        metrics_cpu,
                        metrics_memory,
                        metrics_custom,
                    )
                )

            # Execute batch insert
            cursor.executemany(
                """
                INSERT OR REPLACE INTO tasks
                (task_id, run_id, node_id, node_type, status, started_at, ended_at,
                 result, error, metadata, input_data, output_data,
                 metrics_duration, metrics_cpu_usage, metrics_memory_usage_mb, metrics_custom)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                batch_data,
            )

            self.conn.commit()

    def load_task(self, task_id: str) -> TaskRun | None:
        """Load a task by ID."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()

            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, row, strict=False))

            # Reconstruct metrics from inlined fields
            self._reconstruct_metrics(data)

            # Parse JSON fields
            if data["result"]:
                data["result"] = json.loads(data["result"])
            data["metadata"] = json.loads(data["metadata"] or "{}")
            if data.get("input_data"):
                try:
                    data["input_data"] = json.loads(data["input_data"])
                except (json.JSONDecodeError, TypeError):
                    data["input_data"] = None
            if data.get("output_data"):
                try:
                    data["output_data"] = json.loads(data["output_data"])
                except (json.JSONDecodeError, TypeError):
                    data["output_data"] = None

            return TaskRun.model_validate(data)

    def list_tasks(
        self,
        run_id: str,
        node_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[TaskRun]:
        """List tasks for a run with optional filtering."""
        with self._lock:
            cursor = self.conn.cursor()

            query = "SELECT * FROM tasks WHERE run_id = ?"
            params: list[Any] = [run_id]

            if node_id:
                query += " AND node_id = ?"
                params.append(node_id)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at"

            cursor.execute(query, params)

            tasks = []
            columns = [desc[0] for desc in cursor.description]

            for row in cursor.fetchall():
                data = dict(zip(columns, row, strict=False))
                self._reconstruct_metrics(data)

                if data["result"]:
                    data["result"] = json.loads(data["result"])
                data["metadata"] = json.loads(data["metadata"] or "{}")
                if data.get("input_data"):
                    try:
                        data["input_data"] = json.loads(data["input_data"])
                    except (json.JSONDecodeError, TypeError):
                        data["input_data"] = None
                if data.get("output_data"):
                    try:
                        data["output_data"] = json.loads(data["output_data"])
                    except (json.JSONDecodeError, TypeError):
                        data["output_data"] = None

                tasks.append(TaskRun.model_validate(data))

            return tasks

    def save_audit_events(self, events: list[Any]) -> None:
        """Persist audit events from RuntimeAuditGenerator."""
        if not events:
            return

        with self._lock:
            cursor = self.conn.cursor()

            batch_data = []
            for event in events:
                # Handle both AuditEvent objects and dicts
                if hasattr(event, "to_dict"):
                    event_dict = event.to_dict()
                else:
                    event_dict = event

                batch_data.append(
                    (
                        event_dict.get("event_id"),
                        event_dict.get("event_type"),
                        event_dict.get("timestamp"),
                        event_dict.get("trace_id"),
                        event_dict.get("result"),
                        event_dict.get("workflow_id"),
                        event_dict.get("node_id"),
                        event_dict.get("agent_id"),
                        event_dict.get("human_origin_id"),
                        event_dict.get("action"),
                        event_dict.get("resource"),
                        json.dumps(event_dict.get("context", {})),
                    )
                )

            cursor.executemany(
                """
                INSERT OR REPLACE INTO audit_events
                (event_id, event_type, timestamp, trace_id, result,
                 workflow_id, node_id, agent_id, human_origin_id, action, resource, context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                batch_data,
            )

            self.conn.commit()

    def query_audit_events(self, **filters) -> list[dict]:
        """Query audit events with filters."""
        with self._lock:
            cursor = self.conn.cursor()

            query = "SELECT * FROM audit_events WHERE 1=1"
            params: list[Any] = []

            if "event_type" in filters:
                query += " AND event_type = ?"
                params.append(filters["event_type"])

            if "trace_id" in filters:
                query += " AND trace_id = ?"
                params.append(filters["trace_id"])

            if "workflow_id" in filters:
                query += " AND workflow_id = ?"
                params.append(filters["workflow_id"])

            if "result" in filters:
                query += " AND result = ?"
                params.append(filters["result"])

            query += " ORDER BY timestamp DESC LIMIT ?"
            limit = min(filters.get("limit", 10000), 10000)
            params.append(limit)

            cursor.execute(query, params)

            events = []
            columns = [desc[0] for desc in cursor.description]

            for row in cursor.fetchall():
                data = dict(zip(columns, row, strict=False))
                if data.get("context"):
                    data["context"] = json.loads(data["context"])
                events.append(data)

            return events

    def get_statistics(self) -> dict:
        """Return aggregate statistics for CARE reporting."""
        with self._lock:
            cursor = self.conn.cursor()

            stats = {}

            # Task statistics
            cursor.execute("SELECT COUNT(*) FROM tasks")
            stats["total_tasks"] = cursor.fetchone()[0] or 0

            cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            stats["tasks_by_status"] = dict(cursor.fetchall())

            # Run statistics
            cursor.execute("SELECT COUNT(*) FROM workflow_runs")
            stats["total_runs"] = cursor.fetchone()[0] or 0

            cursor.execute("SELECT status, COUNT(*) FROM workflow_runs GROUP BY status")
            stats["runs_by_status"] = dict(cursor.fetchall())

            # Performance statistics
            cursor.execute(
                "SELECT AVG(metrics_duration), MAX(metrics_duration) FROM tasks WHERE metrics_duration IS NOT NULL"
            )
            row = cursor.fetchone()
            stats["avg_task_duration"] = row[0] if row[0] else None
            stats["max_task_duration"] = row[1] if row[1] else None

            # Audit events statistics
            cursor.execute("SELECT COUNT(*) FROM audit_events")
            stats["total_audit_events"] = cursor.fetchone()[0] or 0

            return stats

    def maintenance(self) -> None:
        """Run ANALYZE and incremental VACUUM."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("ANALYZE")
            cursor.execute("PRAGMA optimize")
            self.conn.commit()

    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM tasks")
            cursor.execute("DELETE FROM workflow_search_attributes")
            cursor.execute("DELETE FROM workflow_runs")
            cursor.execute("DELETE FROM audit_events")
            self.conn.commit()

    def close(self) -> None:
        """Close connection cleanly."""
        with self._lock:
            if hasattr(self, "conn"):
                self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def __del__(self):
        """Close database connection on deletion."""
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _reconstruct_metrics(data: dict) -> None:
        """Reconstruct TaskMetrics from inlined fields."""
        if any(
            data.get(k) is not None
            for k in [
                "metrics_duration",
                "metrics_cpu_usage",
                "metrics_memory_usage_mb",
                "metrics_custom",
            ]
        ):
            metrics_dict = {
                "duration": data.pop("metrics_duration", None),
                "cpu_usage": data.pop("metrics_cpu_usage", None),
                "memory_usage_mb": data.pop("metrics_memory_usage_mb", None),
                "custom_metrics": (
                    json.loads(data.pop("metrics_custom", None))
                    if data.get("metrics_custom")
                    else {}
                ),
            }
            data["metrics"] = metrics_dict
        else:
            # Remove metric fields if all None
            for key in [
                "metrics_duration",
                "metrics_cpu_usage",
                "metrics_memory_usage_mb",
                "metrics_custom",
            ]:
                data.pop(key, None)

    # Backward compatibility aliases
    def save_task_batch(self, tasks: list[TaskRun]) -> None:
        """Alias for save_tasks_batch for API compatibility."""
        self.save_tasks_batch(tasks)

    def get_task(self, task_id: str) -> TaskRun | None:
        """Load a task by ID. Alias for load_task."""
        return self.load_task(task_id)

    def get_all_tasks(self) -> list[TaskRun]:
        """Get all tasks."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM tasks")

            tasks = []
            columns = [desc[0] for desc in cursor.description]

            for row in cursor.fetchall():
                data = dict(zip(columns, row, strict=False))
                self._reconstruct_metrics(data)

                if data["result"]:
                    data["result"] = json.loads(data["result"])
                data["metadata"] = json.loads(data["metadata"] or "{}")

                tasks.append(TaskRun.model_validate(data))

            return tasks

    def update_task(self, task: TaskRun) -> None:
        """Update an existing task. Uses save_task internally."""
        self.save_task(task)

    def delete_task(self, task_id: str) -> None:
        """Delete a task."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            self.conn.commit()

    def query_tasks(
        self,
        node_id: str | None = None,
        status: TaskStatus | None = None,
        started_after: datetime | None = None,
        completed_before: datetime | None = None,
    ) -> list[TaskRun]:
        """Query tasks with filters."""
        with self._lock:
            cursor = self.conn.cursor()

            query = "SELECT * FROM tasks WHERE 1=1"
            params: list[Any] = []

            if node_id:
                query += " AND node_id = ?"
                params.append(node_id)

            if status:
                query += " AND status = ?"
                params.append(status)

            if started_after:
                query += " AND started_at >= ?"
                params.append(
                    started_after.isoformat()
                    if hasattr(started_after, "isoformat")
                    else started_after
                )

            if completed_before:
                query += " AND ended_at < ?"
                params.append(
                    completed_before.isoformat()
                    if hasattr(completed_before, "isoformat")
                    else completed_before
                )

            cursor.execute(query, params)

            tasks = []
            columns = [desc[0] for desc in cursor.description]

            for row in cursor.fetchall():
                data = dict(zip(columns, row, strict=False))
                self._reconstruct_metrics(data)

                if data["result"]:
                    data["result"] = json.loads(data["result"])
                data["metadata"] = json.loads(data["metadata"] or "{}")

                tasks.append(TaskRun.model_validate(data))

            return tasks

    def export_run(self, run_id: str, output_path: str) -> None:
        """Export a run and its tasks."""
        run = self.load_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        tasks = self.list_tasks(run_id)

        export_data = {
            "run": run.to_dict(),
            "tasks": [task.to_dict() for task in tasks],
        }

        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2)

    def import_run(self, input_path: str) -> str:
        """Import a run and its tasks."""
        with open(input_path) as f:
            import_data = json.load(f)

        # Import run
        run_data = import_data["run"]
        run = WorkflowRun.model_validate(run_data)

        # Generate new run ID to avoid conflicts
        run.run_id = str(uuid4())

        # Save run
        self.save_run(run)

        # Import tasks with updated run ID
        for task_data in import_data.get("tasks", []):
            task = TaskRun.model_validate(task_data)
            task.run_id = run.run_id
            self.save_task(task)

        return run.run_id

    def _execute_query(self, query, params=()):
        """Execute a query with parameters. Helper for tests."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor


# Backward compatibility alias
DatabaseStorage = SQLiteStorage

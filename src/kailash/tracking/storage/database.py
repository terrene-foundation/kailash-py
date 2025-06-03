"""Database storage backend for task tracking."""

import json
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from ..models import TaskMetrics, TaskRun, TaskStatus, WorkflowRun
from .base import StorageBackend


class DatabaseStorage(StorageBackend):
    """Database storage backend using SQLite."""

    def __init__(self, connection_string: str = "sqlite:///~/.kailash/tracking.db"):
        """Initialize database storage.

        Args:
            connection_string: Database connection string
        """
        import os
        import sqlite3

        # Expand user path if using sqlite
        if connection_string.startswith("sqlite://"):
            db_path = connection_string.replace("sqlite://", "")
            db_path = os.path.expanduser(db_path)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        else:
            # If not a sqlite:// connection string, assume it's a direct path
            db_path = connection_string

        # For this implementation, we'll use direct SQLite
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._initialize_schema()

    def _initialize_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()

        # Create runs table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                metadata TEXT,
                error TEXT
            )
        """
        )

        # Create tasks table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                result TEXT,
                error TEXT,
                metadata TEXT,
                input_data TEXT,
                output_data TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
            )
        """
        )

        # Create metrics table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                task_id TEXT PRIMARY KEY,
                cpu_usage REAL,
                memory_usage_mb REAL,
                duration REAL,
                custom_metrics TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """
        )

        # For compatibility with code that uses task_runs
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                result TEXT,
                error TEXT,
                metadata TEXT,
                input_data TEXT,
                output_data TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
            )
        """
        )

        # Create indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_name)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_run ON tasks(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_node ON tasks(node_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_node_id ON tasks(node_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(started_at)")

        # Indexes for task_runs table
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_runs_run ON task_runs(run_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_runs_node ON task_runs(node_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_runs_status ON task_runs(status)"
        )

        self.conn.commit()

    def save_run(self, run: WorkflowRun) -> None:
        """Save a workflow run."""
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

    def load_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Load a workflow run by ID."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT * FROM workflow_runs WHERE run_id = ?
        """,
            (run_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        # Convert row to dict
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))

        # Parse JSON metadata
        data["metadata"] = json.loads(data["metadata"] or "{}")

        # Load task IDs
        cursor.execute("SELECT task_id FROM task_runs WHERE run_id = ?", (run_id,))
        data["tasks"] = [row[0] for row in cursor.fetchall()]

        return WorkflowRun.model_validate(data)

    def list_runs(
        self, workflow_name: Optional[str] = None, status: Optional[str] = None
    ) -> List[WorkflowRun]:
        """List workflow runs."""
        cursor = self.conn.cursor()

        query = "SELECT * FROM workflow_runs WHERE 1=1"
        params = []

        if workflow_name:
            query += " AND workflow_name = ?"
            params.append(workflow_name)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC"

        cursor.execute(query, params)

        runs = []
        columns = [desc[0] for desc in cursor.description]

        for row in cursor.fetchall():
            data = dict(zip(columns, row))
            data["metadata"] = json.loads(data["metadata"] or "{}")

            # Load task IDs
            cursor.execute(
                "SELECT task_id FROM task_runs WHERE run_id = ?", (data["run_id"],)
            )
            data["tasks"] = [row[0] for row in cursor.fetchall()]

            runs.append(WorkflowRun.model_validate(data))

        return runs

    def save_task(self, task: TaskRun) -> None:
        """Save a task."""
        cursor = self.conn.cursor()

        # Insert into both tables for compatibility
        for table_name in ["tasks", "task_runs"]:
            cursor.execute(
                f"""
                INSERT OR REPLACE INTO {table_name}
                (task_id, run_id, node_id, node_type, status, started_at, ended_at, result, error, metadata, input_data, output_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
                ),
            )

        # Save metrics if present
        if hasattr(task, "metrics") and task.metrics:
            cursor.execute(
                """
                INSERT OR REPLACE INTO metrics
                (task_id, cpu_usage, memory_usage_mb, duration, custom_metrics)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    task.task_id,
                    task.metrics.cpu_usage,
                    task.metrics.memory_usage_mb,
                    task.metrics.duration,
                    (
                        json.dumps(task.metrics.custom_metrics)
                        if hasattr(task.metrics, "custom_metrics")
                        else None
                    ),
                ),
            )

        self.conn.commit()

    def load_task(self, task_id: str) -> Optional[TaskRun]:
        """Load a task by ID."""
        cursor = self.conn.cursor()

        # Try tasks table first
        cursor.execute(
            """
            SELECT * FROM tasks WHERE task_id = ?
        """,
            (task_id,),
        )

        row = cursor.fetchone()
        if not row:
            # Fall back to task_runs if not found
            cursor.execute(
                """
                SELECT * FROM task_runs WHERE task_id = ?
            """,
                (task_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Convert row to dict
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))

        # Parse JSON fields
        if data["result"]:
            data["result"] = json.loads(data["result"])
        data["metadata"] = json.loads(data["metadata"] or "{}")
        if data.get("input_data"):
            try:
                data["input_data"] = json.loads(data["input_data"])
            except (json.JSONDecodeError, TypeError):
                # Handle case where it's already a dict or invalid JSON
                if isinstance(data["input_data"], str) and data["input_data"].strip():
                    # Try to sanitize it
                    try:
                        data["input_data"] = {"value": data["input_data"]}
                    except Exception:
                        data["input_data"] = None
        if data.get("output_data"):
            try:
                data["output_data"] = json.loads(data["output_data"])
            except (json.JSONDecodeError, TypeError):
                # Handle case where it's already a dict or invalid JSON
                if isinstance(data["output_data"], str) and data["output_data"].strip():
                    # Try to sanitize it
                    try:
                        data["output_data"] = {"value": data["output_data"]}
                    except Exception:
                        data["output_data"] = None

        task = TaskRun.model_validate(data)

        # Load metrics if available
        cursor.execute("SELECT * FROM metrics WHERE task_id = ?", (task_id,))
        metrics_row = cursor.fetchone()
        if metrics_row:
            metrics_columns = [desc[0] for desc in cursor.description]
            metrics_data = dict(zip(metrics_columns, metrics_row))

            # Parse custom metrics if present
            if metrics_data.get("custom_metrics"):
                metrics_data["custom_metrics"] = json.loads(
                    metrics_data["custom_metrics"]
                )

            # Create metrics object
            task.metrics = TaskMetrics(
                cpu_usage=metrics_data.get("cpu_usage"),
                memory_usage=metrics_data.get("memory_usage_mb"),
                duration=metrics_data.get("duration"),
                custom_metrics=metrics_data.get("custom_metrics"),
            )

        return task

    def list_tasks(
        self,
        run_id: str,
        node_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[TaskRun]:
        """List tasks for a run."""
        cursor = self.conn.cursor()

        query = "SELECT * FROM tasks WHERE run_id = ?"
        params = [run_id]

        if node_id:
            query += " AND node_id = ?"
            params.append(node_id)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at"

        cursor.execute(query, params)

        tasks = []
        columns = [desc[0] for desc in cursor.description]

        for row in cursor.fetchall():
            data = dict(zip(columns, row))

            # Parse JSON fields
            if data["result"]:
                data["result"] = json.loads(data["result"])
            data["metadata"] = json.loads(data["metadata"] or "{}")
            if data.get("input_data"):
                try:
                    data["input_data"] = json.loads(data["input_data"])
                except (json.JSONDecodeError, TypeError):
                    # Handle case where it's already a dict or invalid JSON
                    if (
                        isinstance(data["input_data"], str)
                        and data["input_data"].strip()
                    ):
                        # Try to sanitize it by wrapping in quotes if needed
                        try:
                            data["input_data"] = {"value": data["input_data"]}
                        except Exception:
                            data["input_data"] = None
            if data.get("output_data"):
                try:
                    data["output_data"] = json.loads(data["output_data"])
                except (json.JSONDecodeError, TypeError):
                    # Handle case where it's already a dict or invalid JSON
                    if (
                        isinstance(data["output_data"], str)
                        and data["output_data"].strip()
                    ):
                        # Try to sanitize it
                        try:
                            data["output_data"] = {"value": data["output_data"]}
                        except Exception:
                            data["output_data"] = None

            tasks.append(TaskRun.model_validate(data))

        return tasks

    def clear(self) -> None:
        """Clear all stored data."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM task_runs")
        cursor.execute("DELETE FROM workflow_runs")
        self.conn.commit()

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
        with open(input_path, "r") as f:
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

    def get_task(self, task_id: str) -> Optional[TaskRun]:
        """Load a task by ID.

        Alias for load_task for API compatibility.

        Args:
            task_id: Task ID to load

        Returns:
            TaskRun or None if not found
        """
        return self.load_task(task_id)

    def get_all_tasks(self) -> List[TaskRun]:
        """Get all tasks.

        Returns:
            List of all TaskRun objects
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM task_runs")

        tasks = []
        columns = [desc[0] for desc in cursor.description]

        for row in cursor.fetchall():
            data = dict(zip(columns, row))

            # Parse JSON fields
            if data["result"]:
                data["result"] = json.loads(data["result"])
            data["metadata"] = json.loads(data["metadata"] or "{}")

            tasks.append(TaskRun.model_validate(data))

        return tasks

    def update_task(self, task: TaskRun) -> None:
        """Update an existing task.

        Uses save_task internally since our implementation uses REPLACE.

        Args:
            task: TaskRun to update
        """
        self.save_task(task)

    def delete_task(self, task_id: str) -> None:
        """Delete a task.

        Args:
            task_id: Task ID to delete
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        cursor.execute("DELETE FROM task_runs WHERE task_id = ?", (task_id,))
        self.conn.commit()

    def query_tasks(
        self,
        node_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        started_after: Optional[datetime] = None,
        completed_before: Optional[datetime] = None,
    ) -> List[TaskRun]:
        """Query tasks with filters.

        Args:
            node_id: Filter by node ID
            status: Filter by status
            started_after: Filter by start time (inclusive)
            completed_before: Filter by completion time (exclusive)

        Returns:
            List of matching TaskRun objects
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM task_runs WHERE 1=1"
        params = []

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
            data = dict(zip(columns, row))

            # Parse JSON fields
            if data["result"]:
                data["result"] = json.loads(data["result"])
            data["metadata"] = json.loads(data["metadata"] or "{}")

            tasks.append(TaskRun.model_validate(data))

        return tasks

    def _execute_query(self, query, params=()):
        """Execute a query with parameters.

        This is a helper method for tests that mock query execution.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor after execution

        Raises:
            sqlite3.Error: If the query fails
        """
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor

    def __del__(self):
        """Close database connection."""
        if hasattr(self, "conn"):
            self.conn.close()

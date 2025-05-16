"""Database storage backend for task tracking."""
import json
from typing import List, Optional
from uuid import uuid4

from ..models import TaskRun, WorkflowRun, TaskStatus
from .base import StorageBackend


class DatabaseStorage(StorageBackend):
    """Database storage backend using SQLite."""
    
    def __init__(self, connection_string: str = "sqlite:///~/.kailash/tracking.db"):
        """Initialize database storage.
        
        Args:
            connection_string: Database connection string
        """
        import sqlite3
        import os
        
        # Expand user path if using sqlite
        if connection_string.startswith("sqlite://"):
            db_path = connection_string.replace("sqlite://", "")
            db_path = os.path.expanduser(db_path)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            connection_string = f"sqlite:///{db_path}"
        
        # For this implementation, we'll use direct SQLite
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._initialize_schema()
    
    def _initialize_schema(self):
        """Initialize database schema."""
        cursor = self.conn.cursor()
        
        # Create runs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                metadata TEXT,
                error TEXT
            )
        """)
        
        # Create tasks table
        cursor.execute("""
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
                FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON workflow_runs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_run ON task_runs(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_node ON task_runs(node_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON task_runs(status)")
        
        self.conn.commit()
    
    def save_run(self, run: WorkflowRun) -> None:
        """Save a workflow run."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO workflow_runs 
            (run_id, workflow_name, status, started_at, ended_at, metadata, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            run.run_id,
            run.workflow_name,
            run.status,
            run.started_at.isoformat(),
            run.ended_at.isoformat() if run.ended_at else None,
            json.dumps(run.metadata),
            run.error
        ))
        
        self.conn.commit()
    
    def load_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Load a workflow run by ID."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM workflow_runs WHERE run_id = ?
        """, (run_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Convert row to dict
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        
        # Parse JSON metadata
        data['metadata'] = json.loads(data['metadata'] or '{}')
        
        # Load task IDs
        cursor.execute("SELECT task_id FROM task_runs WHERE run_id = ?", (run_id,))
        data['tasks'] = [row[0] for row in cursor.fetchall()]
        
        return WorkflowRun.model_validate(data)
    
    def list_runs(self, workflow_name: Optional[str] = None,
                  status: Optional[str] = None) -> List[WorkflowRun]:
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
            data['metadata'] = json.loads(data['metadata'] or '{}')
            
            # Load task IDs
            cursor.execute("SELECT task_id FROM task_runs WHERE run_id = ?", (data['run_id'],))
            data['tasks'] = [row[0] for row in cursor.fetchall()]
            
            runs.append(WorkflowRun.model_validate(data))
        
        return runs
    
    def save_task(self, task: TaskRun) -> None:
        """Save a task."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO task_runs 
            (task_id, run_id, node_id, node_type, status, started_at, ended_at, result, error, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.task_id,
            task.run_id,
            task.node_id,
            task.node_type,
            task.status,
            task.started_at.isoformat() if task.started_at else None,
            task.ended_at.isoformat() if task.ended_at else None,
            json.dumps(task.result) if task.result else None,
            task.error,
            json.dumps(task.metadata)
        ))
        
        self.conn.commit()
    
    def load_task(self, task_id: str) -> Optional[TaskRun]:
        """Load a task by ID."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT * FROM task_runs WHERE task_id = ?
        """, (task_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Convert row to dict
        columns = [desc[0] for desc in cursor.description]
        data = dict(zip(columns, row))
        
        # Parse JSON fields
        if data['result']:
            data['result'] = json.loads(data['result'])
        data['metadata'] = json.loads(data['metadata'] or '{}')
        
        return TaskRun.model_validate(data)
    
    def list_tasks(self, run_id: str,
                   node_id: Optional[str] = None,
                   status: Optional[TaskStatus] = None) -> List[TaskRun]:
        """List tasks for a run."""
        cursor = self.conn.cursor()
        
        query = "SELECT * FROM task_runs WHERE run_id = ?"
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
            if data['result']:
                data['result'] = json.loads(data['result'])
            data['metadata'] = json.loads(data['metadata'] or '{}')
            
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
            "tasks": [task.to_dict() for task in tasks]
        }
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)
    
    def import_run(self, input_path: str) -> str:
        """Import a run and its tasks."""
        with open(input_path, 'r') as f:
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
    
    def __del__(self):
        """Close database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
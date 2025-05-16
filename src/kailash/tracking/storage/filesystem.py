"""Filesystem-based storage backend for task tracking."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from ..models import TaskRun, WorkflowRun, TaskStatus
from .base import StorageBackend


class FileSystemStorage(StorageBackend):
    """Filesystem-based storage backend."""
    
    def __init__(self, base_path: Optional[str] = None):
        """Initialize filesystem storage.
        
        Args:
            base_path: Base directory for storage. Defaults to ~/.kailash/tracking
        """
        if base_path is None:
            base_path = os.path.expanduser("~/.kailash/tracking")
        
        self.base_path = Path(base_path)
        self.runs_dir = self.base_path / "runs"
        self.tasks_dir = self.base_path / "tasks"
        
        # Create directories
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
    
    def save_run(self, run: WorkflowRun) -> None:
        """Save a workflow run."""
        run_path = self.runs_dir / f"{run.run_id}.json"
        with open(run_path, 'w') as f:
            json.dump(run.to_dict(), f, indent=2)
    
    def load_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Load a workflow run by ID."""
        run_path = self.runs_dir / f"{run_id}.json"
        if not run_path.exists():
            return None
        
        with open(run_path, 'r') as f:
            data = json.load(f)
        
        return WorkflowRun.model_validate(data)
    
    def list_runs(self, workflow_name: Optional[str] = None,
                  status: Optional[str] = None) -> List[WorkflowRun]:
        """List workflow runs."""
        runs = []
        
        for run_file in self.runs_dir.glob("*.json"):
            try:
                with open(run_file, 'r') as f:
                    data = json.load(f)
                
                run = WorkflowRun.model_validate(data)
                
                # Apply filters
                if workflow_name and run.workflow_name != workflow_name:
                    continue
                if status and run.status != status:
                    continue
                
                runs.append(run)
            except Exception:
                # Skip corrupted files
                continue
        
        # Sort by started_at (newest first)
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs
    
    def save_task(self, task: TaskRun) -> None:
        """Save a task."""
        # Create run-specific directory
        run_tasks_dir = self.tasks_dir / task.run_id
        run_tasks_dir.mkdir(exist_ok=True)
        
        task_path = run_tasks_dir / f"{task.task_id}.json"
        with open(task_path, 'w') as f:
            json.dump(task.to_dict(), f, indent=2)
    
    def load_task(self, task_id: str) -> Optional[TaskRun]:
        """Load a task by ID."""
        # Search all run directories
        for run_dir in self.tasks_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            task_path = run_dir / f"{task_id}.json"
            if task_path.exists():
                with open(task_path, 'r') as f:
                    data = json.load(f)
                return TaskRun.model_validate(data)
        
        return None
    
    def list_tasks(self, run_id: str,
                   node_id: Optional[str] = None,
                   status: Optional[TaskStatus] = None) -> List[TaskRun]:
        """List tasks for a run."""
        tasks = []
        run_tasks_dir = self.tasks_dir / run_id
        
        if not run_tasks_dir.exists():
            return tasks
        
        for task_file in run_tasks_dir.glob("*.json"):
            try:
                with open(task_file, 'r') as f:
                    data = json.load(f)
                
                task = TaskRun.model_validate(data)
                
                # Apply filters
                if node_id and task.node_id != node_id:
                    continue
                if status and task.status != status:
                    continue
                
                tasks.append(task)
            except Exception:
                # Skip corrupted files
                continue
        
        # Sort by started_at
        tasks.sort(key=lambda t: t.started_at or t.task_id)
        return tasks
    
    def clear(self) -> None:
        """Clear all stored data."""
        # Remove all files
        for run_file in self.runs_dir.glob("*.json"):
            run_file.unlink()
        
        for task_dir in self.tasks_dir.iterdir():
            if task_dir.is_dir():
                for task_file in task_dir.glob("*.json"):
                    task_file.unlink()
                task_dir.rmdir()
    
    def export_run(self, run_id: str, output_path: str) -> None:
        """Export a run and its tasks."""
        # Load run
        run = self.load_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        # Load tasks
        tasks = self.list_tasks(run_id)
        
        # Create export data
        export_data = {
            "run": run.to_dict(),
            "tasks": [task.to_dict() for task in tasks]
        }
        
        # Write export
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
        original_run_id = run.run_id
        run.run_id = str(uuid4())
        
        # Save run
        self.save_run(run)
        
        # Import tasks with updated run ID
        for task_data in import_data.get("tasks", []):
            task = TaskRun.model_validate(task_data)
            task.run_id = run.run_id
            self.save_task(task)
        
        return run.run_id
    
    def _get_index_file(self) -> Path:
        """Get path to index file."""
        return self.base_path / "index.json"
    
    def _update_index(self, run: WorkflowRun) -> None:
        """Update the index file with run information."""
        index_path = self._get_index_file()
        
        # Load existing index
        if index_path.exists():
            with open(index_path, 'r') as f:
                index = json.load(f)
        else:
            index = {"runs": {}}
        
        # Update index
        index["runs"][run.run_id] = {
            "workflow_name": run.workflow_name,
            "status": run.status,
            "started_at": run.started_at.isoformat(),
            "ended_at": run.ended_at.isoformat() if run.ended_at else None
        }
        
        # Save index
        with open(index_path, 'w') as f:
            json.dump(index, f, indent=2)
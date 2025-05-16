"""Task manager for workflow execution tracking."""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .models import TaskRun, WorkflowRun, TaskStatus, TaskSummary, RunSummary
from .storage.base import StorageBackend
from .storage.filesystem import FileSystemStorage


class TaskManager:
    """Manages task tracking for workflow executions."""
    
    def __init__(self, storage_backend: Optional[StorageBackend] = None):
        """Initialize task manager.
        
        Args:
            storage_backend: Storage backend for persistence. Defaults to FileSystemStorage.
        """
        self.storage = storage_backend or FileSystemStorage()
        self.logger = logging.getLogger("kailash.tracking.manager")
        
        # In-memory caches
        self._runs: Dict[str, WorkflowRun] = {}
        self._tasks: Dict[str, TaskRun] = {}
    
    def create_run(self, workflow_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new workflow run.
        
        Args:
            workflow_name: Name of the workflow
            metadata: Optional metadata for the run
            
        Returns:
            Run ID
        """
        run = WorkflowRun(
            workflow_name=workflow_name,
            metadata=metadata or {}
        )
        
        # Store in memory and persist
        self._runs[run.run_id] = run
        self.storage.save_run(run)
        
        self.logger.info(f"Created workflow run: {run.run_id}")
        return run.run_id
    
    def update_run_status(self, run_id: str, status: str, error: Optional[str] = None) -> None:
        """Update workflow run status.
        
        Args:
            run_id: Run ID
            status: New status
            error: Optional error message
        """
        run = self._runs.get(run_id)
        if not run:
            run = self.storage.load_run(run_id)
            if not run:
                raise ValueError(f"Run {run_id} not found")
            self._runs[run_id] = run
        
        run.update_status(status, error)
        self.storage.save_run(run)
        
        self.logger.info(f"Updated run {run_id} status to: {status}")
    
    def create_task(self, run_id: str, node_id: str, node_type: str, 
                   started_at: Optional[datetime] = None) -> TaskRun:
        """Create a new task.
        
        Args:
            run_id: Associated run ID
            node_id: Node ID in the workflow
            node_type: Type of node
            started_at: When the task started
            
        Returns:
            TaskRun instance
        """
        task = TaskRun(
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            started_at=started_at
        )
        
        # Store in memory and persist
        self._tasks[task.task_id] = task
        self.storage.save_task(task)
        
        # Add task to run
        run = self._runs.get(run_id)
        if run:
            run.add_task(task.task_id)
            self.storage.save_run(run)
        
        self.logger.info(f"Created task: {task.task_id} for node {node_id}")
        return task
    
    def update_task_status(self, task_id: str, status: TaskStatus,
                          result: Optional[Dict[str, Any]] = None,
                          error: Optional[str] = None,
                          ended_at: Optional[datetime] = None) -> None:
        """Update task status.
        
        Args:
            task_id: Task ID
            status: New status
            result: Task result
            error: Error message
            ended_at: When the task ended
        """
        task = self._tasks.get(task_id)
        if not task:
            task = self.storage.load_task(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            self._tasks[task_id] = task
        
        task.update_status(status, result, error, ended_at)
        self.storage.save_task(task)
        
        self.logger.info(f"Updated task {task_id} status to: {status}")
    
    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Get workflow run by ID.
        
        Args:
            run_id: Run ID
            
        Returns:
            WorkflowRun instance or None
        """
        run = self._runs.get(run_id)
        if not run:
            run = self.storage.load_run(run_id)
            if run:
                self._runs[run_id] = run
        return run
    
    def get_task(self, task_id: str) -> Optional[TaskRun]:
        """Get task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            TaskRun instance or None
        """
        task = self._tasks.get(task_id)
        if not task:
            task = self.storage.load_task(task_id)
            if task:
                self._tasks[task_id] = task
        return task
    
    def list_runs(self, workflow_name: Optional[str] = None,
                  status: Optional[str] = None) -> List[RunSummary]:
        """List workflow runs.
        
        Args:
            workflow_name: Filter by workflow name
            status: Filter by status
            
        Returns:
            List of run summaries
        """
        runs = self.storage.list_runs(workflow_name, status)
        summaries = []
        
        for run in runs:
            tasks = self.list_tasks(run.run_id)
            task_runs = [self.get_task(task.task_id) for task in tasks]
            task_runs = [t for t in task_runs if t]  # Filter None values
            
            summary = RunSummary.from_workflow_run(run, task_runs)
            summaries.append(summary)
        
        return summaries
    
    def list_tasks(self, run_id: str, 
                   node_id: Optional[str] = None,
                   status: Optional[TaskStatus] = None) -> List[TaskSummary]:
        """List tasks for a run.
        
        Args:
            run_id: Run ID
            node_id: Filter by node ID
            status: Filter by status
            
        Returns:
            List of task summaries
        """
        tasks = self.storage.list_tasks(run_id, node_id, status)
        return [TaskSummary.from_task_run(task) for task in tasks]
    
    def get_run_summary(self, run_id: str) -> Optional[RunSummary]:
        """Get summary for a specific run.
        
        Args:
            run_id: Run ID
            
        Returns:
            RunSummary or None
        """
        run = self.get_run(run_id)
        if not run:
            return None
        
        tasks = self.list_tasks(run_id)
        task_runs = [self.get_task(task.task_id) for task in tasks]
        task_runs = [t for t in task_runs if t]  # Filter None values
        
        return RunSummary.from_workflow_run(run, task_runs)
    
    def clear_cache(self) -> None:
        """Clear in-memory caches."""
        self._runs.clear()
        self._tasks.clear()
        self.logger.info("Cleared task manager cache")
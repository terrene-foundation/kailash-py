"""Task manager for workflow execution tracking."""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .models import TaskRun, WorkflowRun, TaskStatus, TaskSummary, RunSummary
from .storage.base import StorageBackend
from .storage.filesystem import FileSystemStorage
from kailash.sdk_exceptions import (
    TaskException,
    TaskStateError,
    StorageException,
    KailashException
)


logger = logging.getLogger(__name__)


class TaskManager:
    """Manages task tracking for workflow executions."""
    
    def __init__(self, storage_backend: Optional[StorageBackend] = None):
        """Initialize task manager.
        
        Args:
            storage_backend: Storage backend for persistence. Defaults to FileSystemStorage.
            
        Raises:
            TaskException: If initialization fails
        """
        try:
            self.storage = storage_backend or FileSystemStorage()
            self.logger = logger
            
            # In-memory caches
            self._runs: Dict[str, WorkflowRun] = {}
            self._tasks: Dict[str, TaskRun] = {}
        except Exception as e:
            raise TaskException(
                f"Failed to initialize task manager: {e}"
            ) from e
    
    def create_run(self, workflow_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new workflow run.
        
        Args:
            workflow_name: Name of the workflow
            metadata: Optional metadata for the run
            
        Returns:
            Run ID
            
        Raises:
            TaskException: If run creation fails
            StorageException: If storage operation fails
        """
        if not workflow_name:
            raise TaskException("Workflow name is required")
            
        try:
            run = WorkflowRun(
                workflow_name=workflow_name,
                metadata=metadata or {}
            )
        except Exception as e:
            raise TaskException(
                f"Failed to create workflow run: {e}"
            ) from e
        
        # Store in memory and persist
        self._runs[run.run_id] = run
        
        try:
            self.storage.save_run(run)
        except Exception as e:
            # Remove from cache if storage fails
            self._runs.pop(run.run_id, None)
            raise StorageException(
                f"Failed to persist workflow run: {e}"
            ) from e
        
        self.logger.info(f"Created workflow run: {run.run_id}")
        return run.run_id
    
    def update_run_status(self, run_id: str, status: str, error: Optional[str] = None) -> None:
        """Update workflow run status.
        
        Args:
            run_id: Run ID
            status: New status
            error: Optional error message
            
        Raises:
            TaskException: If run not found
            StorageException: If storage operation fails
            TaskStateError: If status transition is invalid
        """
        if not run_id:
            raise TaskException("Run ID is required")
            
        run = self._runs.get(run_id)
        if not run:
            try:
                run = self.storage.load_run(run_id)
            except Exception as e:
                raise StorageException(
                    f"Failed to load run '{run_id}': {e}"
                ) from e
                
            if not run:
                raise TaskException(
                    f"Run '{run_id}' not found. Available runs: {list(self._runs.keys())}"
                )
            self._runs[run_id] = run
        
        try:
            run.update_status(status, error)
        except ValueError as e:
            raise TaskStateError(
                f"Invalid status transition for run '{run_id}': {e}"
            ) from e
        except Exception as e:
            raise TaskException(
                f"Failed to update run status: {e}"
            ) from e
            
        try:
            self.storage.save_run(run)
        except Exception as e:
            raise StorageException(
                f"Failed to persist run status update: {e}"
            ) from e
        
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
            
        Raises:
            TaskException: If task creation fails
            StorageException: If storage operation fails
        """
        if not run_id:
            raise TaskException("Run ID is required")
        if not node_id:
            raise TaskException("Node ID is required")
        if not node_type:
            raise TaskException("Node type is required")
            
        try:
            task = TaskRun(
                run_id=run_id,
                node_id=node_id,
                node_type=node_type,
                started_at=started_at
            )
        except Exception as e:
            raise TaskException(
                f"Failed to create task: {e}"
            ) from e
        
        # Store in memory and persist
        self._tasks[task.task_id] = task
        
        try:
            self.storage.save_task(task)
        except Exception as e:
            # Remove from cache if storage fails
            self._tasks.pop(task.task_id, None)
            raise StorageException(
                f"Failed to persist task: {e}"
            ) from e
        
        # Add task to run
        run = self._runs.get(run_id)
        if run:
            try:
                run.add_task(task.task_id)
                self.storage.save_run(run)
            except Exception as e:
                self.logger.warning(f"Failed to add task to run: {e}")
                # Continue - task is created, just not linked to run
        
        self.logger.info(f"Created task: {task.task_id} for node {node_id}")
        return task
    
    def update_task_status(self, task_id: str, status: TaskStatus,
                          result: Optional[Dict[str, Any]] = None,
                          error: Optional[str] = None,
                          ended_at: Optional[datetime] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> None:
        """Update task status.
        
        Args:
            task_id: Task ID
            status: New status
            result: Task result
            error: Error message
            ended_at: When the task ended
            metadata: Additional metadata
            
        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
            TaskStateError: If status transition is invalid
        """
        if not task_id:
            raise TaskException("Task ID is required")
            
        task = self._tasks.get(task_id)
        if not task:
            try:
                task = self.storage.load_task(task_id)
            except Exception as e:
                raise StorageException(
                    f"Failed to load task '{task_id}': {e}"
                ) from e
                
            if not task:
                raise TaskException(
                    f"Task '{task_id}' not found. Available tasks: {list(self._tasks.keys())}"
                )
            self._tasks[task_id] = task
        
        try:
            task.update_status(status, result, error, ended_at, metadata)
        except ValueError as e:
            raise TaskStateError(
                f"Invalid status transition for task '{task_id}': {e}"
            ) from e
        except Exception as e:
            raise TaskException(
                f"Failed to update task status: {e}"
            ) from e
            
        try:
            self.storage.save_task(task)
        except Exception as e:
            raise StorageException(
                f"Failed to persist task status update: {e}"
            ) from e
        
        self.logger.info(f"Updated task {task_id} status to: {status}")
    
    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        """Get workflow run by ID.
        
        Args:
            run_id: Run ID
            
        Returns:
            WorkflowRun instance or None
            
        Raises:
            StorageException: If storage operation fails
        """
        if not run_id:
            return None
            
        run = self._runs.get(run_id)
        if not run:
            try:
                run = self.storage.load_run(run_id)
            except Exception as e:
                self.logger.error(f"Failed to load run '{run_id}': {e}")
                raise StorageException(
                    f"Failed to load run '{run_id}': {e}"
                ) from e
                
            if run:
                self._runs[run_id] = run
        return run
    
    def get_task(self, task_id: str) -> Optional[TaskRun]:
        """Get task by ID.
        
        Args:
            task_id: Task ID
            
        Returns:
            TaskRun instance or None
            
        Raises:
            StorageException: If storage operation fails
        """
        if not task_id:
            return None
            
        task = self._tasks.get(task_id)
        if not task:
            try:
                task = self.storage.load_task(task_id)
            except Exception as e:
                self.logger.error(f"Failed to load task '{task_id}': {e}")
                raise StorageException(
                    f"Failed to load task '{task_id}': {e}"
                ) from e
                
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
            
        Raises:
            StorageException: If storage operation fails
        """
        try:
            runs = self.storage.list_runs(workflow_name, status)
        except Exception as e:
            raise StorageException(
                f"Failed to list runs: {e}"
            ) from e
            
        summaries = []
        
        for run in runs:
            try:
                tasks = self.list_tasks(run.run_id)
                task_runs = []
                
                for task in tasks:
                    try:
                        task_run = self.get_task(task.task_id)
                        if task_run:
                            task_runs.append(task_run)
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to load task '{task.task_id}': {e}"
                        )
                
                summary = RunSummary.from_workflow_run(run, task_runs)
                summaries.append(summary)
                
            except Exception as e:
                self.logger.warning(
                    f"Failed to create summary for run '{run.run_id}': {e}"
                )
        
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
            
        Raises:
            TaskException: If run_id is not provided
            StorageException: If storage operation fails
        """
        if not run_id:
            raise TaskException("Run ID is required")
            
        try:
            tasks = self.storage.list_tasks(run_id, node_id, status)
        except Exception as e:
            raise StorageException(
                f"Failed to list tasks for run '{run_id}': {e}"
            ) from e
            
        summaries = []
        for task in tasks:
            try:
                summary = TaskSummary.from_task_run(task)
                summaries.append(summary)
            except Exception as e:
                self.logger.warning(
                    f"Failed to create summary for task '{task.task_id}': {e}"
                )
                
        return summaries
    
    def get_run_summary(self, run_id: str) -> Optional[RunSummary]:
        """Get summary for a specific run.
        
        Args:
            run_id: Run ID
            
        Returns:
            RunSummary or None
            
        Raises:
            StorageException: If storage operation fails
        """
        if not run_id:
            return None
            
        try:
            run = self.get_run(run_id)
        except Exception as e:
            self.logger.error(f"Failed to get run '{run_id}': {e}")
            return None
            
        if not run:
            return None
        
        try:
            tasks = self.list_tasks(run_id)
            task_runs = []
            
            for task in tasks:
                try:
                    task_run = self.get_task(task.task_id)
                    if task_run:
                        task_runs.append(task_run)
                except Exception as e:
                    self.logger.warning(
                        f"Failed to load task '{task.task_id}': {e}"
                    )
            
            return RunSummary.from_workflow_run(run, task_runs)
            
        except Exception as e:
            self.logger.error(
                f"Failed to create run summary for '{run_id}': {e}"
            )
            return None
    
    def clear_cache(self) -> None:
        """Clear in-memory caches."""
        self._runs.clear()
        self._tasks.clear()
        self.logger.info("Cleared task manager cache")
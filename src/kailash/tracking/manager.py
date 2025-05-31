"""Task manager for workflow execution tracking."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.sdk_exceptions import StorageException, TaskException, TaskStateError

from .models import (
    RunSummary,
    TaskMetrics,
    TaskRun,
    TaskStatus,
    TaskSummary,
    WorkflowRun,
)
from .storage.base import StorageBackend
from .storage.filesystem import FileSystemStorage

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
            raise TaskException(f"Failed to initialize task manager: {e}") from e

    def create_run(
        self, workflow_name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
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
            run = WorkflowRun(workflow_name=workflow_name, metadata=metadata or {})
        except Exception as e:
            raise TaskException(f"Failed to create workflow run: {e}") from e

        # Store in memory and persist
        self._runs[run.run_id] = run

        try:
            self.storage.save_run(run)
        except Exception as e:
            # Remove from cache if storage fails
            self._runs.pop(run.run_id, None)
            raise StorageException(f"Failed to persist workflow run: {e}") from e

        self.logger.info(f"Created workflow run: {run.run_id}")
        return run.run_id

    def update_run_status(
        self, run_id: str, status: str, error: Optional[str] = None
    ) -> None:
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
                raise StorageException(f"Failed to load run '{run_id}': {e}") from e

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
            raise TaskException(f"Failed to update run status: {e}") from e

        try:
            self.storage.save_run(run)
        except Exception as e:
            raise StorageException(f"Failed to persist run status update: {e}") from e

        self.logger.info(f"Updated run {run_id} status to: {status}")

    def create_task(
        self,
        node_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        run_id: str = "test-run-id",
        node_type: str = "default-node-type",
        dependencies: Optional[List[str]] = None,
        started_at: Optional[datetime] = None,
    ) -> TaskRun:
        """Create a new task.

        Args:
            node_id: Node ID in the workflow
            input_data: Input data for the task
            metadata: Additional metadata
            run_id: Associated run ID (defaults to "test-run-id" for backward compatibility)
            node_type: Type of node (defaults to "default-node-type" for backward compatibility)
            dependencies: List of task IDs this task depends on
            started_at: When the task started

        Returns:
            TaskRun instance

        Raises:
            TaskException: If task creation fails
            StorageException: If storage operation fails
        """
        if not node_id:
            raise TaskException("Node ID is required")

        try:
            task = TaskRun(
                run_id=run_id,
                node_id=node_id,
                node_type=node_type,
                started_at=started_at,
                input_data=input_data,
                metadata=metadata or {},
                dependencies=dependencies or [],
            )
        except Exception as e:
            raise TaskException(f"Failed to create task: {e}") from e

        # Store in memory and persist
        self._tasks[task.task_id] = task

        try:
            self.storage.save_task(task)
        except Exception as e:
            # Remove from cache if storage fails
            self._tasks.pop(task.task_id, None)
            raise StorageException(f"Failed to persist task: {e}") from e

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

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        ended_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
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
                raise StorageException(f"Failed to load task '{task_id}': {e}") from e

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
            raise TaskException(f"Failed to update task status: {e}") from e

        try:
            self.storage.save_task(task)
        except Exception as e:
            raise StorageException(f"Failed to persist task status update: {e}") from e

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
                raise StorageException(f"Failed to load run '{run_id}': {e}") from e

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
                raise StorageException(f"Failed to load task '{task_id}': {e}") from e

            if task:
                self._tasks[task_id] = task
        return task

    def list_runs(
        self, workflow_name: Optional[str] = None, status: Optional[str] = None
    ) -> List[RunSummary]:
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
            raise StorageException(f"Failed to list runs: {e}") from e

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

    def list_tasks(
        self,
        run_id: str,
        node_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[TaskSummary]:
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
                    self.logger.warning(f"Failed to load task '{task.task_id}': {e}")

            return RunSummary.from_workflow_run(run, task_runs)

        except Exception as e:
            self.logger.error(f"Failed to create run summary for '{run_id}': {e}")
            return None

    def clear_cache(self) -> None:
        """Clear in-memory caches."""
        self._runs.clear()
        self._tasks.clear()
        self.logger.info("Cleared task manager cache")

    def complete_task(
        self, task_id: str, output_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Complete a task successfully.

        Args:
            task_id: Task ID
            output_data: Output data for the task

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        task = self.get_task(task_id)
        if not task:
            raise TaskException(f"Task '{task_id}' not found")

        task.complete(output_data)

        # Add simple metrics if not present
        if not task.metrics:
            task.metrics = TaskMetrics(duration=task.duration or 0)

        try:
            self.storage.save_task(task)
        except Exception as e:
            raise StorageException(f"Failed to save completed task: {e}") from e

        self.logger.info(f"Completed task {task_id}")

    def fail_task(self, task_id: str, error_message: str) -> None:
        """Mark a task as failed.

        Args:
            task_id: Task ID
            error_message: Error message

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        task = self.get_task(task_id)
        if not task:
            raise TaskException(f"Task '{task_id}' not found")

        task.fail(error_message)

        try:
            self.storage.save_task(task)
        except Exception as e:
            raise StorageException(f"Failed to save failed task: {e}") from e

        self.logger.info(f"Failed task {task_id}: {error_message}")

    def cancel_task(self, task_id: str, reason: str) -> None:
        """Cancel a task.

        Args:
            task_id: Task ID
            reason: Cancellation reason

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        task = self.get_task(task_id)
        if not task:
            raise TaskException(f"Task '{task_id}' not found")

        task.cancel(reason)

        try:
            self.storage.save_task(task)
        except Exception as e:
            raise StorageException(f"Failed to save cancelled task: {e}") from e

        self.logger.info(f"Cancelled task {task_id}: {reason}")

    def retry_task(self, task_id: str) -> TaskRun:
        """Create a new task as a retry of an existing task.

        Args:
            task_id: Original task ID

        Returns:
            New task instance

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        original_task = self.get_task(task_id)
        if not original_task:
            raise TaskException(f"Task '{task_id}' not found")

        retry_task = original_task.create_retry()

        try:
            self.storage.save_task(retry_task)
        except Exception as e:
            raise StorageException(f"Failed to save retry task: {e}") from e

        self._tasks[retry_task.task_id] = retry_task
        self.logger.info(f"Created retry task {retry_task.task_id} for {task_id}")

        return retry_task

    def delete_task(self, task_id: str) -> None:
        """Delete a task.

        Args:
            task_id: Task ID

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        if task_id in self._tasks:
            del self._tasks[task_id]

        try:
            self.storage.delete_task(task_id)
        except Exception as e:
            raise StorageException(f"Failed to delete task: {e}") from e

        self.logger.info(f"Deleted task {task_id}")

    def get_tasks_by_status(self, status: TaskStatus) -> List[TaskRun]:
        """Get tasks by status.

        Args:
            status: Status to filter by

        Returns:
            List of matching tasks

        Raises:
            StorageException: If storage operation fails
        """
        try:
            if hasattr(self.storage, "query_tasks"):
                return self.storage.query_tasks(status=status)
            else:
                # Fallback for MockStorage
                return [t for t in self.storage.get_all_tasks() if t.status == status]
        except Exception as e:
            raise StorageException(f"Failed to query tasks by status: {e}") from e

    def get_tasks_by_node(self, node_id: str) -> List[TaskRun]:
        """Get tasks by node ID.

        Args:
            node_id: Node ID to filter by

        Returns:
            List of matching tasks

        Raises:
            StorageException: If storage operation fails
        """
        try:
            if hasattr(self.storage, "query_tasks"):
                return self.storage.query_tasks(node_id=node_id)
            else:
                # Fallback for MockStorage
                return [t for t in self.storage.get_all_tasks() if t.node_id == node_id]
        except Exception as e:
            raise StorageException(f"Failed to query tasks by node: {e}") from e

    def get_task_history(self, task_id: str) -> List[TaskRun]:
        """Get task history (original task and all retries).

        Args:
            task_id: Task ID

        Returns:
            List of tasks in order (original first, latest retry last)

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        task = self.get_task(task_id)
        if not task:
            raise TaskException(f"Task '{task_id}' not found")

        # Build history by following parent_task_id chain
        history = []
        current = task

        # First, find the original task by following parent_task_id backward
        while current.parent_task_id:
            parent = self.get_task(current.parent_task_id)
            if not parent:
                break
            current = parent

        # Now current is the original task, build history forward
        history.append(current)
        while True:
            # Find tasks with this task as parent
            children = []
            for t in self.storage.get_all_tasks():
                if t.parent_task_id == current.task_id:
                    children.append(t)

            if not children:
                break

            # Find the child with the lowest retry count
            next_task = min(children, key=lambda t: t.retry_count)
            history.append(next_task)
            current = next_task

        return history

    def get_tasks_by_timerange(
        self, start_time: datetime, end_time: datetime
    ) -> List[TaskRun]:
        """Get tasks created between start_time and end_time.

        Args:
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of matching tasks

        Raises:
            StorageException: If storage operation fails
        """
        try:
            if hasattr(self.storage, "query_tasks"):
                return self.storage.query_tasks(
                    started_after=start_time, completed_before=end_time
                )
            else:
                # Fallback for MockStorage
                return [
                    t
                    for t in self.storage.get_all_tasks()
                    if t.created_at >= start_time and t.created_at <= end_time
                ]
        except Exception as e:
            raise StorageException(f"Failed to query tasks by timerange: {e}") from e

    def get_task_statistics(self) -> Dict[str, Any]:
        """Get task statistics.

        Returns:
            Dictionary with statistics:
            - total_tasks: Total number of tasks
            - by_status: Count of tasks by status
            - by_node: Count of tasks by node ID

        Raises:
            StorageException: If storage operation fails
        """
        try:
            tasks = self.storage.get_all_tasks()
        except Exception as e:
            raise StorageException(f"Failed to get tasks for statistics: {e}") from e

        by_status = {}
        by_node = {}

        for task in tasks:
            # Count by status
            status = task.status
            by_status[status] = by_status.get(status, 0) + 1

            # Count by node
            node = task.node_id
            by_node[node] = by_node.get(node, 0) + 1

        return {"total_tasks": len(tasks), "by_status": by_status, "by_node": by_node}

    def cleanup_old_tasks(self, days: int = 30) -> int:
        """Delete tasks older than specified days.

        Args:
            days: Age in days

        Returns:
            Number of tasks deleted

        Raises:
            StorageException: If storage operation fails
        """
        try:
            tasks = self.storage.get_all_tasks()
        except Exception as e:
            raise StorageException(f"Failed to get tasks for cleanup: {e}") from e

        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0

        for task in tasks:
            if task.created_at and task.created_at < cutoff:
                try:
                    self.delete_task(task.task_id)
                    deleted += 1
                except Exception as e:
                    self.logger.warning(
                        f"Failed to delete old task {task.task_id}: {e}"
                    )

        return deleted

    def update_task_metrics(self, task_id: str, metrics: TaskMetrics) -> None:
        """Update task metrics.

        Args:
            task_id: Task ID
            metrics: Metrics to update

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        task = self.get_task(task_id)
        if not task:
            raise TaskException(f"Task '{task_id}' not found")

        task.metrics = metrics

        try:
            self.storage.save_task(task)
        except Exception as e:
            raise StorageException(f"Failed to update task metrics: {e}") from e

        self.logger.info(f"Updated metrics for task {task_id}")

    def get_running_tasks(self) -> List[TaskRun]:
        """Get all currently running tasks.

        Returns:
            List of running tasks

        Raises:
            StorageException: If storage operation fails
        """
        return self.get_tasks_by_status(TaskStatus.RUNNING)

    def get_task_dependencies(self, task_id: str) -> List[TaskRun]:
        """Get tasks that are dependencies for the given task.

        Args:
            task_id: Task ID

        Returns:
            List of dependency tasks

        Raises:
            TaskException: If task not found
            StorageException: If storage operation fails
        """
        task = self.get_task(task_id)
        if not task:
            raise TaskException(f"Task '{task_id}' not found")

        dependencies = []
        for dep_id in task.dependencies:
            dep = self.get_task(dep_id)
            if dep:
                dependencies.append(dep)

        return dependencies

    def save_task(self, task: TaskRun) -> None:
        """Save a task to storage.

        This is a convenience method that directly saves a task instance to storage.
        For new tasks, prefer using create_task() instead.

        Args:
            task: TaskRun instance to save

        Raises:
            StorageException: If storage operation fails
        """
        try:
            # Store in cache
            self._tasks[task.task_id] = task

            # Save to storage
            self.storage.save_task(task)
            self.logger.info(f"Saved task: {task.task_id}")

            # Add task to run if needed
            run = self._runs.get(task.run_id)
            if run and task.task_id not in run.tasks:
                run.add_task(task.task_id)
                self.storage.save_run(run)

        except Exception as e:
            raise StorageException(f"Failed to save task: {e}") from e

    def get_run_tasks(self, run_id: str) -> List[TaskRun]:
        """Get all tasks for a specific run.

        Args:
            run_id: Run ID to get tasks for

        Returns:
            List of tasks in the run
        """
        run = self.get_run(run_id)
        if not run:
            return []

        tasks = []
        for task_id in run.tasks:
            task = self.get_task(task_id)
            if task:
                tasks.append(task)

        return tasks

    def get_workflow_tasks(self, workflow_id: str) -> List[TaskRun]:
        """Get all tasks for a workflow.

        This is a compatibility method that returns all tasks across all runs for a workflow.
        In practice, tasks are tracked per run, not per workflow.

        Args:
            workflow_id: Workflow ID (used to filter runs)

        Returns:
            List of all TaskRun objects for the workflow

        Raises:
            StorageException: If storage operation fails
        """
        try:
            # Get all tasks from storage
            all_tasks = self.storage.get_all_tasks()

            # For now, return all tasks since we don't have a good way to filter by workflow_id
            # In a real implementation, we'd need to track workflow_id in tasks or runs
            return all_tasks
        except Exception as e:
            raise StorageException(f"Failed to get workflow tasks: {e}") from e

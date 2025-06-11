"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod

from ..models import TaskRun, TaskStatus, WorkflowRun


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def save_run(self, run: WorkflowRun) -> None:
        """Save a workflow run.

        Args:
            run: WorkflowRun to save
        """

    @abstractmethod
    def load_run(self, run_id: str) -> WorkflowRun | None:
        """Load a workflow run by ID.

        Args:
            run_id: Run ID

        Returns:
            WorkflowRun or None if not found
        """

    @abstractmethod
    def list_runs(
        self, workflow_name: str | None = None, status: str | None = None
    ) -> list[WorkflowRun]:
        """List workflow runs.

        Args:
            workflow_name: Filter by workflow name
            status: Filter by status

        Returns:
            List of WorkflowRun instances
        """

    @abstractmethod
    def save_task(self, task: TaskRun) -> None:
        """Save a task.

        Args:
            task: TaskRun to save
        """

    @abstractmethod
    def load_task(self, task_id: str) -> TaskRun | None:
        """Load a task by ID.

        Args:
            task_id: Task ID

        Returns:
            TaskRun or None if not found
        """

    @abstractmethod
    def list_tasks(
        self,
        run_id: str,
        node_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[TaskRun]:
        """List tasks for a run.

        Args:
            run_id: Run ID
            node_id: Filter by node ID
            status: Filter by status

        Returns:
            List of TaskRun instances
        """

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored data."""

    @abstractmethod
    def export_run(self, run_id: str, output_path: str) -> None:
        """Export a run and its tasks.

        Args:
            run_id: Run ID to export
            output_path: Path to write export
        """

    @abstractmethod
    def import_run(self, input_path: str) -> str:
        """Import a run and its tasks.

        Args:
            input_path: Path to read import from

        Returns:
            Imported run ID
        """

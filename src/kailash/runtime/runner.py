"""Main runner for workflow execution."""

import logging
from typing import Any, Dict, Optional, Tuple

from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager
from kailash.workflow import Workflow


class WorkflowRunner:
    """High-level interface for running workflows."""

    def __init__(self, debug: bool = False, task_manager: Optional[TaskManager] = None):
        """Initialize the workflow runner.

        Args:
            debug: Whether to enable debug mode
            task_manager: Optional task manager for tracking
        """
        self.debug = debug
        self.task_manager = task_manager or TaskManager()
        self.logger = logging.getLogger("kailash.runner")

        # Configure logging
        if debug:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
        else:
            logging.basicConfig(
                level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
            )

    def run(
        self,
        workflow: Workflow,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
        runtime_type: str = "local",
    ) -> Tuple[Dict[str, Any], str]:
        """Run a workflow.

        Args:
            workflow: Workflow to run
            parameters: Optional parameter overrides
            runtime_type: Type of runtime to use (currently only "local")

        Returns:
            Tuple of (results, run_id)
        """
        self.logger.info(f"Starting workflow: {workflow.name}")

        # Select runtime
        if runtime_type == "local":
            runtime = LocalRuntime(debug=self.debug)
        else:
            raise ValueError(f"Unknown runtime type: {runtime_type}")

        # Execute workflow
        try:
            results, run_id = runtime.execute(
                workflow=workflow, task_manager=self.task_manager, parameters=parameters
            )

            self.logger.info(f"Workflow completed successfully: {run_id}")
            return results, run_id

        except Exception as e:
            self.logger.error(f"Workflow failed: {e}")
            raise

    def validate(self, workflow: Workflow) -> list:
        """Validate a workflow.

        Args:
            workflow: Workflow to validate

        Returns:
            List of validation warnings
        """
        runtime = LocalRuntime(debug=self.debug)
        return runtime.validate_workflow(workflow)

    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """Get status of a workflow run.

        Args:
            run_id: Run ID to check

        Returns:
            Status information
        """
        return self.task_manager.get_run_status(run_id)

    def get_run_history(
        self, workflow_name: Optional[str] = None, limit: int = 10
    ) -> list:
        """Get run history.

        Args:
            workflow_name: Optional workflow name to filter by
            limit: Maximum number of runs to return

        Returns:
            List of run summaries
        """
        return self.task_manager.get_run_history(
            workflow_name=workflow_name, limit=limit
        )

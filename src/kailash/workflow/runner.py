"""Workflow runner for executing connected workflows.

This module provides tools for connecting and executing multiple workflows,
allowing for complex multi-stage processing pipelines.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.tracking import TaskManager
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class WorkflowConnection:
    """Defines a connection between two workflows."""

    def __init__(
        self,
        source_workflow_id: str,
        target_workflow_id: str,
        condition: Optional[Dict[str, Any]] = None,
        state_mapping: Optional[Dict[str, str]] = None,
    ):
        """Initialize a workflow connection.

        Args:
            source_workflow_id: ID of the source workflow
            target_workflow_id: ID of the target workflow
            condition: Optional condition for when this connection should be followed
            state_mapping: Optional mapping of state fields between workflows
        """
        self.source_workflow_id = source_workflow_id
        self.target_workflow_id = target_workflow_id
        self.condition = condition or {}
        self.state_mapping = state_mapping or {}

    def should_follow(self, state: BaseModel) -> bool:
        """Check if this connection should be followed based on state.

        Args:
            state: The current state object

        Returns:
            True if the connection should be followed, False otherwise
        """
        if not self.condition:
            # If no condition is specified, always follow the connection
            return True

        # Extract condition field and value from the state
        field_name = self.condition.get("field")
        operator = self.condition.get("operator", "==")
        expected_value = self.condition.get("value")

        if not field_name:
            # If no field name is specified, always follow the connection
            return True

        # Get the field value from the state
        field_value = getattr(state, field_name, None)

        # Check the condition
        if operator == "==":
            return field_value == expected_value
        elif operator == "!=":
            return field_value != expected_value
        elif operator == ">":
            return field_value > expected_value
        elif operator == ">=":
            return field_value >= expected_value
        elif operator == "<":
            return field_value < expected_value
        elif operator == "<=":
            return field_value <= expected_value
        elif operator == "in":
            return field_value in expected_value
        elif operator == "not in":
            return field_value not in expected_value
        else:
            # Unknown operator, default to always follow
            logger.warning(
                f"Unknown condition operator: {operator}. Always following connection."
            )
            return True

    def map_state(self, state: BaseModel) -> Dict[str, Any]:
        """Map state fields according to the mapping configuration.

        Args:
            state: The current state object

        Returns:
            Dictionary with mapped state fields
        """
        if not self.state_mapping:
            # If no mapping is specified, use the state as is
            return {"state": state}

        # Apply mappings
        mapped_state = {}
        for source_key, target_key in self.state_mapping.items():
            if hasattr(state, source_key):
                mapped_state[target_key] = getattr(state, source_key)

        return mapped_state


class WorkflowRunner:
    """Manages execution across multiple connected workflows.

    This class allows building complex processing pipelines by connecting
    multiple workflows together, with conditional branching based on state.
    """

    def __init__(self):
        """Initialize a workflow runner."""
        self.workflows = {}
        self.connections = []

    def add_workflow(self, workflow_id: str, workflow: Workflow) -> None:
        """Add a workflow to the runner.

        Args:
            workflow_id: Unique identifier for the workflow
            workflow: Workflow instance

        Raises:
            ValueError: If a workflow with the given ID already exists
        """
        if workflow_id in self.workflows:
            raise ValueError(f"Workflow with ID '{workflow_id}' already exists")

        self.workflows[workflow_id] = workflow
        logger.info(f"Added workflow '{workflow.name}' with ID '{workflow_id}'")

    def connect_workflows(
        self,
        source_workflow_id: str,
        target_workflow_id: str,
        condition: Optional[Dict[str, Any]] = None,
        state_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        """Connect two workflows.

        Args:
            source_workflow_id: ID of the source workflow
            target_workflow_id: ID of the target workflow
            condition: Optional condition for when this connection should be followed
            state_mapping: Optional mapping of state fields between workflows

        Raises:
            ValueError: If any workflow ID is invalid
        """
        # Validate workflow IDs
        if source_workflow_id not in self.workflows:
            raise ValueError(
                f"Source workflow with ID '{source_workflow_id}' not found"
            )

        if target_workflow_id not in self.workflows:
            raise ValueError(
                f"Target workflow with ID '{target_workflow_id}' not found"
            )

        # Create connection
        connection = WorkflowConnection(
            source_workflow_id=source_workflow_id,
            target_workflow_id=target_workflow_id,
            condition=condition,
            state_mapping=state_mapping,
        )

        self.connections.append(connection)
        logger.info(
            f"Connected workflow '{source_workflow_id}' to '{target_workflow_id}'"
        )

    def get_next_workflows(
        self, current_workflow_id: str, state: BaseModel
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Get the next workflows to execute based on current state.

        Args:
            current_workflow_id: ID of the current workflow
            state: Current state object

        Returns:
            List of (workflow_id, mapped_state) tuples for next workflows
        """
        next_workflows = []

        for connection in self.connections:
            if connection.source_workflow_id == current_workflow_id:
                if connection.should_follow(state):
                    mapped_state = connection.map_state(state)
                    next_workflows.append((connection.target_workflow_id, mapped_state))

        return next_workflows

    def execute(
        self,
        entry_workflow_id: str,
        initial_state: BaseModel,
        task_manager: Optional[TaskManager] = None,
        max_steps: int = 10,  # Prevent infinite loops
    ) -> Tuple[BaseModel, Dict[str, Dict[str, Any]]]:
        """Execute a sequence of connected workflows.

        Args:
            entry_workflow_id: ID of the first workflow to execute
            initial_state: Initial state for workflow execution
            task_manager: Optional task manager for tracking
            max_steps: Maximum number of workflow steps to execute

        Returns:
            Tuple of (final state, all results by workflow)

        Raises:
            WorkflowExecutionError: If workflow execution fails
            ValueError: If entry workflow is not found
        """
        if entry_workflow_id not in self.workflows:
            raise ValueError(f"Entry workflow with ID '{entry_workflow_id}' not found")

        # Initialize execution
        current_workflow_id = entry_workflow_id
        current_state = initial_state
        all_results = {}
        executed_workflows = set()
        step_count = 0

        # Execute workflows until no more connections to follow
        while current_workflow_id and step_count < max_steps:
            step_count += 1
            logger.info(
                f"Executing workflow '{current_workflow_id}' (step {step_count}/{max_steps})"
            )

            # Get the workflow
            workflow = self.workflows[current_workflow_id]

            # Track executed workflows to detect cycles
            if current_workflow_id in executed_workflows:
                logger.warning(
                    f"Cycle detected in workflow execution: already executed '{current_workflow_id}'"
                )
                # Continue to next workflow rather than stopping, to handle intentional cycles

            executed_workflows.add(current_workflow_id)

            try:
                # Execute the workflow
                final_state, workflow_results = workflow.execute_with_state(
                    state_model=current_state, task_manager=task_manager
                )

                # Store results
                all_results[current_workflow_id] = workflow_results

                # Update current state
                current_state = final_state

                # Find next workflows
                next_workflows = self.get_next_workflows(
                    current_workflow_id, current_state
                )

                if not next_workflows:
                    # No more workflows to execute
                    logger.info(
                        f"No more workflows to execute after '{current_workflow_id}'"
                    )
                    break

                # Take the first matching workflow as the next one
                current_workflow_id = next_workflows[0][0]

                # Apply state mapping if needed
                if next_workflows[0][1]:
                    # If a complete state object is provided, use it
                    if "state" in next_workflows[0][1] and isinstance(
                        next_workflows[0][1]["state"], BaseModel
                    ):
                        current_state = next_workflows[0][1]["state"]
                    # Otherwise, merge the mapped values into the current state
                    # using StateManager would be ideal here, but keeping it simple for now

            except Exception as e:
                logger.error(f"Error executing workflow '{current_workflow_id}': {e}")
                raise WorkflowExecutionError(
                    f"Failed to execute workflow '{current_workflow_id}': {e}"
                ) from e

        if step_count >= max_steps:
            logger.warning(f"Reached maximum steps ({max_steps}) in workflow execution")

        return current_state, all_results

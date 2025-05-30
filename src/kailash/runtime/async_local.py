"""Asynchronous local runtime engine for executing workflows.

This module provides an asynchronous execution engine for Kailash workflows,
particularly useful for workflows with I/O-bound nodes such as API calls,
database queries, or LLM interactions.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import networkx as nx

from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import (
    RuntimeExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class AsyncLocalRuntime:
    """Asynchronous local execution engine for workflows.

    This runtime provides asynchronous execution capabilities for workflows,
    allowing for more efficient processing of I/O-bound operations and potential
    parallel execution of independent nodes.

    Key features:
    - Support for AsyncNode.async_run() execution
    - Parallel execution of independent nodes (in development)
    - Task tracking and monitoring
    - Detailed execution metrics

    Usage:
        runtime = AsyncLocalRuntime()
        results = await runtime.execute(workflow, parameters={...})
    """

    def __init__(self, debug: bool = False, max_concurrency: int = 10):
        """Initialize the async local runtime.

        Args:
            debug: Whether to enable debug logging
            max_concurrency: Maximum number of nodes to execute concurrently
        """
        self.debug = debug
        self.max_concurrency = max_concurrency
        self.logger = logger

        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

    async def execute(
        self,
        workflow: Workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute a workflow asynchronously.

        Args:
            workflow: Workflow to execute
            task_manager: Optional task manager for tracking
            parameters: Optional parameter overrides per node

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            RuntimeExecutionError: If execution fails
            WorkflowValidationError: If workflow is invalid
        """
        if not workflow:
            raise RuntimeExecutionError("No workflow provided")

        run_id = None

        try:
            # Validate workflow
            workflow.validate()

            # Initialize tracking
            if task_manager:
                try:
                    run_id = task_manager.create_run(
                        workflow_name=workflow.name,
                        metadata={
                            "parameters": parameters,
                            "debug": self.debug,
                            "runtime": "async_local",
                        },
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to create task run: {e}")
                    # Continue without tracking

            # Execute workflow
            results = await self._execute_workflow(
                workflow=workflow,
                task_manager=task_manager,
                run_id=run_id,
                parameters=parameters or {},
            )

            # Mark run as completed
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "completed")
                except Exception as e:
                    self.logger.warning(f"Failed to update run status: {e}")

            return results, run_id

        except WorkflowValidationError:
            # Re-raise validation errors as-is
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(
                        run_id, "failed", error="Validation failed"
                    )
                except Exception:
                    pass
            raise
        except Exception as e:
            # Mark run as failed
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "failed", error=str(e))
                except Exception:
                    pass

            # Wrap other errors in RuntimeExecutionError
            raise RuntimeExecutionError(
                f"Async workflow execution failed: {type(e).__name__}: {e}"
            ) from e

    async def _execute_workflow(
        self,
        workflow: Workflow,
        task_manager: Optional[TaskManager],
        run_id: Optional[str],
        parameters: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute the workflow nodes asynchronously.

        Args:
            workflow: Workflow to execute
            task_manager: Task manager for tracking
            run_id: Run ID for tracking
            parameters: Parameter overrides

        Returns:
            Dictionary of node results

        Raises:
            WorkflowExecutionError: If execution fails
        """
        # Get execution order
        try:
            execution_order = list(nx.topological_sort(workflow.graph))
            self.logger.info(f"Determined execution order: {execution_order}")
        except nx.NetworkXError as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e

        # Initialize results storage
        results = {}
        node_outputs = {}
        failed_nodes = []

        # Execute each node
        for node_id in execution_order:
            self.logger.info(f"Executing node: {node_id}")

            # Get node instance
            node_instance = workflow._node_instances.get(node_id)
            if not node_instance:
                raise WorkflowExecutionError(
                    f"Node instance '{node_id}' not found in workflow"
                )

            # Start task tracking
            task = None
            if task_manager and run_id:
                try:
                    task = task_manager.create_task(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node_instance.__class__.__name__,
                        started_at=datetime.now(timezone.utc),
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to create task for node '{node_id}': {e}"
                    )

            try:
                # Prepare inputs
                inputs = self._prepare_node_inputs(
                    workflow=workflow,
                    node_id=node_id,
                    node_instance=node_instance,
                    node_outputs=node_outputs,
                    parameters=parameters.get(node_id, {}),
                )

                if self.debug:
                    self.logger.debug(f"Node {node_id} inputs: {inputs}")

                # Update task status
                if task:
                    task.update_status(TaskStatus.RUNNING)

                # Execute node - check if it supports async execution
                start_time = datetime.now(timezone.utc)

                if isinstance(node_instance, AsyncNode):
                    # Use async execution
                    outputs = await node_instance.execute_async(**inputs)
                else:
                    # Fall back to synchronous execution
                    outputs = node_instance.execute(**inputs)

                execution_time = (
                    datetime.now(timezone.utc) - start_time
                ).total_seconds()

                # Store outputs
                node_outputs[node_id] = outputs
                results[node_id] = outputs

                if self.debug:
                    self.logger.debug(f"Node {node_id} outputs: {outputs}")

                # Update task status
                if task:
                    task.update_status(
                        TaskStatus.COMPLETED,
                        result=outputs,
                        ended_at=datetime.now(timezone.utc),
                        metadata={"execution_time": execution_time},
                    )

                self.logger.info(
                    f"Node {node_id} completed successfully in {execution_time:.3f}s"
                )

            except Exception as e:
                failed_nodes.append(node_id)
                self.logger.error(f"Node {node_id} failed: {e}", exc_info=self.debug)

                # Update task status
                if task:
                    task.update_status(
                        TaskStatus.FAILED,
                        error=str(e),
                        ended_at=datetime.now(timezone.utc),
                    )

                # Determine if we should continue or stop
                if self._should_stop_on_error(workflow, node_id):
                    error_msg = f"Node '{node_id}' failed: {e}"
                    if len(failed_nodes) > 1:
                        error_msg += f" (Previously failed nodes: {failed_nodes[:-1]})"

                    raise WorkflowExecutionError(error_msg) from e
                else:
                    # Continue execution but record error
                    results[node_id] = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "failed": True,
                    }

        return results

    def _prepare_node_inputs(
        self,
        workflow: Workflow,
        node_id: str,
        node_instance: Any,
        node_outputs: Dict[str, Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare inputs for a node execution.

        Args:
            workflow: The workflow being executed
            node_id: Current node ID
            node_instance: Current node instance
            node_outputs: Outputs from previously executed nodes
            parameters: Parameter overrides

        Returns:
            Dictionary of inputs for the node

        Raises:
            WorkflowExecutionError: If input preparation fails
        """
        inputs = {}

        # Start with node configuration
        inputs.update(node_instance.config)

        # Add connected inputs from other nodes
        for edge in workflow.graph.in_edges(node_id, data=True):
            source_node_id = edge[0]
            mapping = edge[2].get("mapping", {})

            if source_node_id in node_outputs:
                source_outputs = node_outputs[source_node_id]

                # Check if the source node failed
                if isinstance(source_outputs, dict) and source_outputs.get("failed"):
                    raise WorkflowExecutionError(
                        f"Cannot use outputs from failed node '{source_node_id}'"
                    )

                for source_key, target_key in mapping.items():
                    if source_key in source_outputs:
                        inputs[target_key] = source_outputs[source_key]
                    else:
                        self.logger.warning(
                            f"Source output '{source_key}' not found in node '{source_node_id}'. "
                            f"Available outputs: {list(source_outputs.keys())}"
                        )

        # Apply parameter overrides
        inputs.update(parameters)

        return inputs

    def _should_stop_on_error(self, workflow: Workflow, node_id: str) -> bool:
        """Determine if execution should stop when a node fails.

        Args:
            workflow: The workflow being executed
            node_id: Failed node ID

        Returns:
            Whether to stop execution
        """
        # Check if any downstream nodes depend on this node
        has_dependents = workflow.graph.out_degree(node_id) > 0

        # For now, stop if the failed node has dependents
        # Future: implement configurable error handling policies
        return has_dependents

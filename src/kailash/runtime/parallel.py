"""Parallel runtime engine for executing workflows with concurrent node execution.

This module provides a parallel execution engine for Kailash workflows,
specifically designed to run independent nodes concurrently for maximum performance.
"""

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional, Set, Tuple

import networkx as nx

from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import (
    RuntimeExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.tracking.models import TaskMetrics
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class ParallelRuntime:
    """Parallel execution engine for workflows.

    This runtime provides true concurrent execution of independent nodes in a workflow,
    allowing for maximum performance with both synchronous and asynchronous nodes.

    Key features:
    - Concurrent execution of independent nodes
    - Dynamic scheduling based on dependency resolution
    - Support for both sync and async nodes
    - Configurable parallelism limits
    - Detailed execution metrics and visualization

    Usage:
        runtime = ParallelRuntime(max_workers=8)
        results, run_id = await runtime.execute(workflow, parameters={...})
    """

    def __init__(self, max_workers: int = 8, debug: bool = False):
        """Initialize the parallel runtime.

        Args:
            max_workers: Maximum number of concurrent node executions
            debug: Whether to enable debug logging
        """
        self.max_workers = max_workers
        self.debug = debug
        self.logger = logger

        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        self.semaphore = None  # Will be initialized during execution

    async def execute(
        self,
        workflow: Workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute a workflow with parallel node execution.

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
        start_time = time.time()

        try:
            # Validate workflow
            workflow.validate()

            # Initialize semaphore for concurrent execution control
            self.semaphore = asyncio.Semaphore(self.max_workers)

            # Initialize tracking
            if task_manager:
                try:
                    run_id = task_manager.create_run(
                        workflow_name=workflow.name,
                        metadata={
                            "parameters": parameters,
                            "debug": self.debug,
                            "runtime": "parallel",
                            "max_workers": self.max_workers,
                        },
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to create task run: {e}")
                    # Continue without tracking

            # Execute workflow with parallel node execution
            results = await self._execute_workflow_parallel(
                workflow=workflow,
                task_manager=task_manager,
                run_id=run_id,
                parameters=parameters or {},
            )

            # Mark run as completed
            if task_manager and run_id:
                try:
                    end_time = time.time()
                    execution_time = end_time - start_time
                    task_manager.update_run_status(
                        run_id, "completed", metadata={"execution_time": execution_time}
                    )
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
                f"Parallel workflow execution failed: {type(e).__name__}: {e}"
            ) from e

    async def _execute_workflow_parallel(
        self,
        workflow: Workflow,
        task_manager: Optional[TaskManager],
        run_id: Optional[str],
        parameters: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute the workflow nodes in parallel where possible.

        This method uses a dynamic scheduling approach to run independent nodes
        concurrently while respecting dependencies.

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
        # Initialize result storage and tracking
        results = {}
        node_outputs = {}
        node_tasks = {}
        failed_nodes = set()

        # Calculate initial dependencies for each node
        dependencies = {
            node: set(workflow.graph.predecessors(node))
            for node in workflow.graph.nodes()
        }
        ready_nodes = deque([node for node, deps in dependencies.items() if not deps])
        pending_nodes = set(workflow.graph.nodes()) - set(ready_nodes)

        self.logger.info(
            f"Starting parallel execution with {len(ready_nodes)} initially ready nodes"
        )

        # Process nodes until all are complete
        while ready_nodes or pending_nodes:
            # Schedule ready nodes up to max_workers limit
            while ready_nodes and len(node_tasks) < self.max_workers:
                node_id = ready_nodes.popleft()

                # Skip if node already failed
                if node_id in failed_nodes:
                    continue

                # Create and start task for this node
                task = asyncio.create_task(
                    self._execute_node(
                        workflow=workflow,
                        node_id=node_id,
                        node_outputs=node_outputs,
                        parameters=parameters.get(node_id, {}),
                        task_manager=task_manager,
                        run_id=run_id,
                    )
                )
                node_tasks[node_id] = task

                self.logger.debug(f"Scheduled node {node_id} for execution")

            # Wait for any node to complete if we have active tasks
            if node_tasks:
                # Wait for the first task to complete
                done, _ = await asyncio.wait(
                    node_tasks.values(), return_when=asyncio.FIRST_COMPLETED
                )

                # Process completed nodes
                for task in done:
                    # Find the node_id for this task
                    completed_node_id = next(
                        node_id
                        for node_id, node_task in node_tasks.items()
                        if node_task == task
                    )

                    # Remove from active tasks
                    node_tasks.pop(completed_node_id)

                    try:
                        # Get result and add to outputs
                        node_result, success = task.result()
                        results[completed_node_id] = node_result

                        if success:
                            node_outputs[completed_node_id] = node_result
                            self.logger.info(
                                f"Node {completed_node_id} completed successfully"
                            )

                            # Update dependent nodes
                            for dependent in workflow.graph.successors(
                                completed_node_id
                            ):
                                if dependent in pending_nodes:
                                    dependencies[dependent].remove(completed_node_id)
                                    # If all dependencies are satisfied, mark as ready
                                    if not dependencies[dependent]:
                                        ready_nodes.append(dependent)
                                        pending_nodes.remove(dependent)
                                        self.logger.debug(
                                            f"Node {dependent} is now ready"
                                        )
                        else:
                            # Node failed, mark it and check if we should continue
                            failed_nodes.add(completed_node_id)
                            self.logger.error(f"Node {completed_node_id} failed")

                            # Determine if we should stop execution
                            if self._should_stop_on_error(workflow, completed_node_id):
                                error_msg = f"Node '{completed_node_id}' failed"
                                raise WorkflowExecutionError(error_msg)

                            # Update dependent nodes to also mark as failed
                            self._mark_dependent_nodes_as_failed(
                                workflow,
                                completed_node_id,
                                failed_nodes,
                                pending_nodes,
                                ready_nodes,
                            )
                    except Exception as e:
                        # Handle unexpected task exceptions
                        failed_nodes.add(completed_node_id)
                        self.logger.error(
                            f"Unexpected error in node {completed_node_id}: {e}"
                        )

                        # Determine if we should stop execution
                        if self._should_stop_on_error(workflow, completed_node_id):
                            error_msg = f"Node '{completed_node_id}' failed with unexpected error: {e}"
                            raise WorkflowExecutionError(error_msg) from e

                        # Mark dependents as failed
                        self._mark_dependent_nodes_as_failed(
                            workflow,
                            completed_node_id,
                            failed_nodes,
                            pending_nodes,
                            ready_nodes,
                        )
            else:
                # No active tasks but we still have pending nodes - this indicates a deadlock
                if pending_nodes:
                    remaining = list(pending_nodes)
                    raise WorkflowExecutionError(
                        f"Deadlock detected. Nodes waiting for dependencies: {remaining}"
                    )
                # No tasks and no pending nodes means we're done
                break

        self.logger.info(
            f"Parallel execution complete. Succeeded: {len(results) - len(failed_nodes)}, Failed: {len(failed_nodes)}"
        )
        return results

    async def _execute_node(
        self,
        workflow: Workflow,
        node_id: str,
        node_outputs: Dict[str, Dict[str, Any]],
        parameters: Dict[str, Any],
        task_manager: Optional[TaskManager],
        run_id: Optional[str],
    ) -> Tuple[Dict[str, Any], bool]:
        """Execute a single node asynchronously.

        Args:
            workflow: The workflow being executed
            node_id: ID of the node to execute
            node_outputs: Dictionary of outputs from previously executed nodes
            parameters: Parameter overrides for this node
            task_manager: Task manager for tracking
            run_id: Run ID for tracking

        Returns:
            Tuple of (node_result, success)

        Note:
            This method never raises exceptions - it returns success=False instead
            to allow the caller to handle failures appropriately.
        """
        # Get node instance
        node_instance = workflow._node_instances.get(node_id)
        if not node_instance:
            self.logger.error(f"Node instance '{node_id}' not found in workflow")
            return {"error": "Node instance not found"}, False

        # Start task tracking
        task = None
        try:
            if task_manager and run_id:
                task = task_manager.create_task(
                    run_id=run_id,
                    node_id=node_id,
                    node_type=node_instance.__class__.__name__,
                    started_at=datetime.now(timezone.utc),
                )
        except Exception as e:
            self.logger.warning(f"Failed to create task for node '{node_id}': {e}")

        try:
            # Limit concurrent execution
            async with self.semaphore:
                # Update task status
                if task:
                    task.update_status(TaskStatus.RUNNING)

                # Prepare inputs
                inputs = self._prepare_node_inputs(
                    workflow=workflow,
                    node_id=node_id,
                    node_instance=node_instance,
                    node_outputs=node_outputs,
                    parameters=parameters,
                )

                if self.debug:
                    self.logger.debug(f"Node {node_id} inputs: {inputs}")

                # Execute node with metrics collection
                collector = MetricsCollector()

                if isinstance(node_instance, AsyncNode):
                    # Use async execution for AsyncNode
                    outputs, performance_metrics = await collector.collect_async(
                        node_instance.execute_async(**inputs), node_id=node_id
                    )
                else:
                    # Use sync execution in an executor for regular Node
                    loop = asyncio.get_running_loop()

                    async def execute_with_metrics():
                        with collector.collect(node_id=node_id) as context:
                            result = await loop.run_in_executor(
                                None, lambda: node_instance.execute(**inputs)
                            )
                            return result, context.result()

                    outputs, performance_metrics = await execute_with_metrics()

                # Update task status with enhanced metrics
                if task:
                    task.update_status(
                        TaskStatus.COMPLETED,
                        result=outputs,
                        ended_at=datetime.now(timezone.utc),
                        metadata={"execution_time": performance_metrics.duration},
                    )

                    # Convert and save performance metrics
                    if task_manager:
                        task_metrics_data = performance_metrics.to_task_metrics()
                        task_metrics = TaskMetrics(**task_metrics_data)
                        task_manager.update_task_metrics(task.task_id, task_metrics)

                self.logger.info(
                    f"Node {node_id} completed successfully in {performance_metrics.duration:.3f}s"
                )

                return outputs, True

        except Exception as e:
            self.logger.error(f"Node {node_id} failed: {e}", exc_info=self.debug)

            # Update task status
            if task:
                task.update_status(
                    TaskStatus.FAILED, error=str(e), ended_at=datetime.now(timezone.utc)
                )

            # Return error result
            error_result = {
                "error": str(e),
                "error_type": type(e).__name__,
                "failed": True,
            }

            return error_result, False

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

    def _mark_dependent_nodes_as_failed(
        self,
        workflow: Workflow,
        failed_node: str,
        failed_nodes: Set[str],
        pending_nodes: Set[str],
        ready_nodes: Deque[str],
    ) -> None:
        """Mark all dependent nodes as failed.

        Args:
            workflow: The workflow being executed
            failed_node: The node that failed
            failed_nodes: Set to track failed nodes
            pending_nodes: Set of nodes waiting for dependencies
            ready_nodes: Queue of nodes ready to execute
        """
        # Get all descendants of the failed node
        descendants = set(nx.descendants(workflow.graph, failed_node))

        # Mark all descendants as failed
        for node in descendants:
            failed_nodes.add(node)

            # Remove from pending or ready as appropriate
            if node in pending_nodes:
                pending_nodes.remove(node)

            # Need to handle as list comprehension since deque doesn't support
            # efficient removal of arbitrary elements
            if node in ready_nodes:
                ready_nodes_list = list(ready_nodes)
                ready_nodes_list.remove(node)
                ready_nodes.clear()
                ready_nodes.extend(ready_nodes_list)

        self.logger.debug(
            f"Marked {len(descendants)} dependent nodes as failed due to failure of node {failed_node}"
        )

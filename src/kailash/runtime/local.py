"""Enhanced Local Runtime Engine with Comprehensive Cycle Support.

This module provides a sophisticated local execution engine for workflows with
advanced support for both traditional DAG workflows and complex cyclic patterns.
It offers comprehensive task tracking, performance monitoring, and debugging
capabilities for development and production use.

Examples:
    Basic workflow execution:

    >>> from kailash.runtime.local import LocalRuntime
    >>> runtime = LocalRuntime(debug=True, enable_cycles=True)
    >>> results = runtime.execute(workflow, parameters={"input": "data"})

    With comprehensive tracking:

    >>> from kailash.tracking import TaskManager
    >>> runtime = LocalRuntime(enable_cycles=True)
    >>> task_manager = TaskManager()
    >>> results = runtime.execute(
    ...     workflow,
    ...     task_manager=task_manager,
    ...     parameters={"initial_value": 10}
    ... )
    >>> # Access detailed execution information
    >>> tasks = task_manager.get_tasks_for_workflow(workflow.workflow_id)
    >>> metrics = task_manager.get_performance_summary()

    Production configuration:

    >>> runtime = LocalRuntime(
    ...     debug=False,           # Optimized for performance
    ...     enable_cycles=True     # Support cyclic patterns
    ... )
    >>> results = runtime.execute(
    ...     workflow,
    ...     parameters=input_params,
    ...     run_id="production_run_001"
    ... )
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from kailash.nodes import Node
from kailash.sdk_exceptions import (
    RuntimeExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.tracking.models import TaskMetrics
from kailash.workflow import Workflow
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor

logger = logging.getLogger(__name__)


class LocalRuntime:
    """Local execution engine for workflows.

    This class provides a robust, production-ready execution engine that seamlessly
    handles both traditional workflows and advanced cyclic patterns.
    """

    def __init__(self, debug: bool = False, enable_cycles: bool = True):
        """Initialize the local runtime.

        Args:
            debug: Whether to enable debug logging.
            enable_cycles: Whether to enable cyclic workflow support.
        """
        self.debug = debug
        self.enable_cycles = enable_cycles
        self.logger = logger

        # Initialize cyclic workflow executor if enabled
        if enable_cycles:
            self.cyclic_executor = CyclicWorkflowExecutor()

        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

    def execute(
        self,
        workflow: Workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """Execute a workflow locally.

        Args:
            workflow: Workflow to execute.
            task_manager: Optional task manager for tracking.
            parameters: Optional parameter overrides per node.

        Returns:
            Tuple of (results dict, run_id).

        Raises:
            RuntimeExecutionError: If execution fails.
            WorkflowValidationError: If workflow is invalid.
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
                            "runtime": "local",
                        },
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to create task run: {e}")
                    # Continue without tracking

            # Check for cyclic workflows and delegate accordingly
            if self.enable_cycles and workflow.has_cycles():
                self.logger.info(
                    "Cyclic workflow detected, using CyclicWorkflowExecutor"
                )
                # Use cyclic executor for workflows with cycles
                try:
                    # Pass run_id to cyclic executor if available
                    cyclic_results, cyclic_run_id = self.cyclic_executor.execute(
                        workflow, parameters, task_manager, run_id
                    )
                    results = cyclic_results
                    # Update run_id if task manager is being used
                    if not run_id:
                        run_id = cyclic_run_id
                except Exception as e:
                    raise RuntimeExecutionError(
                        f"Cyclic workflow execution failed: {e}"
                    ) from e
            else:
                # Execute standard DAG workflow
                self.logger.info(
                    "Standard DAG workflow detected, using local execution"
                )
                results = self._execute_workflow(
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
                f"Workflow execution failed: {type(e).__name__}: {e}"
            ) from e

    def _execute_workflow(
        self,
        workflow: Workflow,
        task_manager: Optional[TaskManager],
        run_id: Optional[str],
        parameters: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute the workflow nodes in topological order.

        Args:
            workflow: Workflow to execute.
            task_manager: Task manager for tracking.
            run_id: Run ID for tracking.
            parameters: Parameter overrides.

        Returns:
            Dictionary of node results.

        Raises:
            WorkflowExecutionError: If execution fails.
        """
        # Get execution order
        try:
            execution_order = list(nx.topological_sort(workflow.graph))
            self.logger.info(f"Execution order: {execution_order}")
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
                    # Get node metadata if available
                    node_metadata = {}
                    if hasattr(node_instance, "config") and isinstance(
                        node_instance.config, dict
                    ):
                        raw_metadata = node_instance.config.get("metadata", {})
                        # Convert NodeMetadata object to dict if needed
                        if hasattr(raw_metadata, "model_dump"):
                            node_metadata_dict = raw_metadata.model_dump()
                            # Convert datetime objects to strings for JSON serialization
                            if "created_at" in node_metadata_dict:
                                node_metadata_dict["created_at"] = str(
                                    node_metadata_dict["created_at"]
                                )
                            # Convert sets to lists for JSON serialization
                            if "tags" in node_metadata_dict and isinstance(
                                node_metadata_dict["tags"], set
                            ):
                                node_metadata_dict["tags"] = list(
                                    node_metadata_dict["tags"]
                                )
                            node_metadata = node_metadata_dict
                        elif isinstance(raw_metadata, dict):
                            node_metadata = raw_metadata

                    task = task_manager.create_task(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node_instance.__class__.__name__,
                        started_at=datetime.now(timezone.utc),
                        metadata=node_metadata,
                    )
                    # Start the task
                    if task:
                        task_manager.update_task_status(
                            task.task_id, TaskStatus.RUNNING
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

                # Execute node with metrics collection
                collector = MetricsCollector()
                with collector.collect(node_id=node_id) as metrics_context:
                    outputs = node_instance.execute(**inputs)

                # Get performance metrics
                performance_metrics = metrics_context.result()

                # Store outputs
                node_outputs[node_id] = outputs
                results[node_id] = outputs

                if self.debug:
                    self.logger.debug(f"Node {node_id} outputs: {outputs}")

                # Update task status with enhanced metrics
                if task and task_manager:
                    # Convert performance metrics to TaskMetrics format
                    task_metrics_data = performance_metrics.to_task_metrics()
                    task_metrics = TaskMetrics(**task_metrics_data)

                    # Update task with metrics
                    task_manager.update_task_status(
                        task.task_id,
                        TaskStatus.COMPLETED,
                        result=outputs,
                        ended_at=datetime.now(timezone.utc),
                        metadata={"execution_time": performance_metrics.duration},
                    )

                    # Update task metrics separately
                    task_manager.update_task_metrics(task.task_id, task_metrics)

                self.logger.info(
                    f"Node {node_id} completed successfully in {performance_metrics.duration:.3f}s"
                )

            except Exception as e:
                failed_nodes.append(node_id)
                self.logger.error(f"Node {node_id} failed: {e}", exc_info=self.debug)

                # Update task status
                if task and task_manager:
                    task_manager.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(e),
                        ended_at=datetime.now(timezone.utc),
                    )

                # Determine if we should continue
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
        node_instance: Node,
        node_outputs: Dict[str, Dict[str, Any]],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare inputs for a node execution.

        Args:
            workflow: The workflow being executed.
            node_id: Current node ID.
            node_instance: Current node instance.
            node_outputs: Outputs from previously executed nodes.
            parameters: Parameter overrides.

        Returns:
            Dictionary of inputs for the node.

        Raises:
            WorkflowExecutionError: If input preparation fails.
        """
        inputs = {}

        # Start with node configuration
        inputs.update(node_instance.config)

        # Add connected inputs from other nodes
        for edge in workflow.graph.in_edges(node_id, data=True):
            source_node_id = edge[0]
            mapping = edge[2].get("mapping", {})

            print(f"LOCAL RUNTIME DEBUG: Processing edge {source_node_id} -> {node_id}")
            print(f"  Edge data: {edge[2]}")
            print(f"  Mapping: {mapping}")

            if source_node_id in node_outputs:
                source_outputs = node_outputs[source_node_id]
                print(f"  Source outputs: {list(source_outputs.keys())}")

                # Check if the source node failed
                if isinstance(source_outputs, dict) and source_outputs.get("failed"):
                    raise WorkflowExecutionError(
                        f"Cannot use outputs from failed node '{source_node_id}'"
                    )

                for source_key, target_key in mapping.items():
                    if source_key in source_outputs:
                        inputs[target_key] = source_outputs[source_key]
                        print(
                            f"  MAPPED: {source_key} -> {target_key} (type: {type(source_outputs[source_key])})"
                        )
                    else:
                        print(
                            f"  MISSING: {source_key} not in {list(source_outputs.keys())}"
                        )
                        self.logger.warning(
                            f"Source output '{source_key}' not found in node '{source_node_id}'. "
                            f"Available outputs: {list(source_outputs.keys())}"
                        )
            else:
                print(f"  No outputs found for source node {source_node_id}")

        # Apply parameter overrides
        inputs.update(parameters)

        return inputs

    def _should_stop_on_error(self, workflow: Workflow, node_id: str) -> bool:
        """Determine if execution should stop when a node fails.

        Args:
            workflow: The workflow being executed.
            node_id: Failed node ID.

        Returns:
            Whether to stop execution.
        """
        # Check if any downstream nodes depend on this node
        has_dependents = workflow.graph.out_degree(node_id) > 0

        # For now, stop if the failed node has dependents
        # Future: implement configurable error handling policies
        return has_dependents

    def validate_workflow(self, workflow: Workflow) -> List[str]:
        """Validate a workflow before execution.

        Args:
            workflow: Workflow to validate

        Returns:
            List of validation warnings (empty if valid)

        Raises:
            WorkflowValidationError: If workflow is invalid
        """
        warnings = []

        try:
            workflow.validate()
        except WorkflowValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            raise WorkflowValidationError(f"Workflow validation failed: {e}") from e

        # Check for disconnected nodes
        for node_id in workflow.graph.nodes():
            if (
                workflow.graph.in_degree(node_id) == 0
                and workflow.graph.out_degree(node_id) == 0
                and len(workflow.graph.nodes()) > 1
            ):
                warnings.append(f"Node '{node_id}' is disconnected from the workflow")

        # Check for missing required parameters
        for node_id, node_instance in workflow._node_instances.items():
            try:
                params = node_instance.get_parameters()
            except Exception as e:
                warnings.append(f"Failed to get parameters for node '{node_id}': {e}")
                continue

            for param_name, param_def in params.items():
                if param_def.required:
                    # Check if provided in config or connected
                    if param_name not in node_instance.config:
                        # Check if connected from another node
                        incoming_params = set()
                        for _, _, data in workflow.graph.in_edges(node_id, data=True):
                            mapping = data.get("mapping", {})
                            incoming_params.update(mapping.values())

                        if (
                            param_name not in incoming_params
                            and param_def.default is None
                        ):
                            warnings.append(
                                f"Node '{node_id}' missing required parameter '{param_name}' "
                                f"(no default value provided)"
                            )

        # Check for potential performance issues
        if len(workflow.graph.nodes()) > 100:
            warnings.append(
                f"Large workflow with {len(workflow.graph.nodes())} nodes "
                f"may have performance implications"
            )

        return warnings

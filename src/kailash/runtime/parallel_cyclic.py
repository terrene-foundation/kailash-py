"""Enhanced parallel runtime with cyclic workflow support."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import networkx as nx
from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowExecutionError
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.tracking.models import TaskMetrics
from kailash.workflow import Workflow
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor

logger = logging.getLogger(__name__)


class ParallelCyclicRuntime:
    """Enhanced parallel runtime with support for cyclic workflows and concurrent execution."""

    def __init__(
        self,
        debug: bool = False,
        max_workers: int = 4,
        enable_cycles: bool = True,
        enable_async: bool = True,
    ):
        """Initialize the parallel cyclic runtime.

        Args:
            debug: Whether to enable debug logging
            max_workers: Maximum number of worker threads for parallel execution
            enable_cycles: Whether to enable cyclic workflow support
            enable_async: Whether to enable async execution features
        """
        self.debug = debug
        self.max_workers = max_workers
        self.enable_cycles = enable_cycles
        self.enable_async = enable_async
        self.logger = logger

        # Initialize components
        self.local_runtime = LocalRuntime(debug=debug, enable_cycles=enable_cycles)
        if enable_cycles:
            self.cyclic_executor = CyclicWorkflowExecutor()

        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

    def execute(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None = None,
        parameters: dict[str, dict[str, Any]] | None = None,
        parallel_nodes: set[str] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Execute a workflow with parallel and cyclic support.

        Args:
            workflow: Workflow to execute
            task_manager: Optional task manager for tracking
            parameters: Optional parameter overrides per node
            parallel_nodes: Set of node IDs that can be executed in parallel

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            RuntimeExecutionError: If execution fails
            WorkflowValidationError: If workflow is invalid
        """
        if not workflow:
            raise RuntimeExecutionError("No workflow provided")

        try:
            # Validate workflow
            workflow.validate(runtime_parameters=parameters)

            # Check for cycles first
            if self.enable_cycles and workflow.has_cycles():
                self.logger.info(
                    "Cyclic workflow detected, checking for parallel execution opportunities"
                )
                return self._execute_cyclic_workflow(workflow, task_manager, parameters)

            # Check for parallel execution opportunities in DAG workflows
            if parallel_nodes or self._can_execute_in_parallel(workflow):
                self.logger.info("Parallel execution opportunities detected")
                return self._execute_parallel_dag(
                    workflow, task_manager, parameters, parallel_nodes
                )

            # Fall back to standard local runtime
            self.logger.info("Using standard local runtime execution")
            return self.local_runtime.execute(workflow, task_manager, parameters)

        except Exception as e:
            raise RuntimeExecutionError(
                f"Parallel runtime execution failed: {e}"
            ) from e

    def _execute_cyclic_workflow(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None,
        parameters: dict[str, dict[str, Any]] | None,
    ) -> tuple[dict[str, Any], str]:
        """Execute a cyclic workflow with potential parallel optimizations.

        Args:
            workflow: Cyclic workflow to execute
            task_manager: Optional task manager
            parameters: Optional parameters

        Returns:
            Tuple of (results dict, run_id)
        """
        # For now, delegate to cyclic executor
        # Future enhancement: identify parallelizable parts within cycles
        self.logger.info("Executing cyclic workflow with CyclicWorkflowExecutor")

        try:
            results, run_id = self.cyclic_executor.execute(workflow, parameters)

            # TODO: Add cycle-aware parallel execution optimizations
            # - Parallel execution of independent cycles
            # - Parallel execution of DAG portions between cycles
            # - Async cycle monitoring and resource management

            return results, run_id

        except Exception as e:
            raise RuntimeExecutionError(f"Cyclic workflow execution failed: {e}") from e

    def _execute_parallel_dag(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None,
        parameters: dict[str, dict[str, Any]] | None,
        parallel_nodes: set[str] | None,
    ) -> tuple[dict[str, Any], str | None]:
        """Execute a DAG workflow with parallel node execution.

        Args:
            workflow: DAG workflow to execute
            task_manager: Optional task manager
            parameters: Optional parameters
            parallel_nodes: Optional set of nodes that can be executed in parallel

        Returns:
            Tuple of (results dict, run_id)
        """
        import uuid

        run_id = str(uuid.uuid4())

        self.logger.info(
            f"Starting parallel DAG execution: {workflow.name} (run_id: {run_id})"
        )

        # Initialize tracking
        if task_manager:
            try:
                run_id = task_manager.create_run(
                    workflow_name=workflow.name,
                    metadata={
                        "parameters": parameters,
                        "debug": self.debug,
                        "runtime": "parallel_cyclic",
                        "max_workers": self.max_workers,
                    },
                )
            except Exception as e:
                self.logger.warning(f"Failed to create task run: {e}")

        try:
            # Analyze workflow for parallel execution groups
            execution_groups = self._analyze_parallel_groups(workflow, parallel_nodes)

            # Execute groups sequentially, but nodes within groups in parallel
            results = {}

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                for group_index, node_group in enumerate(execution_groups):
                    self.logger.info(
                        f"Executing parallel group {group_index + 1}/{len(execution_groups)}: {node_group}"
                    )

                    # Submit all nodes in this group for parallel execution
                    future_to_node = {}
                    for node_id in node_group:
                        future = executor.submit(
                            self._execute_single_node,
                            workflow,
                            node_id,
                            results,
                            parameters,
                            task_manager,
                            run_id,
                        )
                        future_to_node[future] = node_id

                    # Wait for all nodes in this group to complete
                    group_results = {}
                    for future in as_completed(future_to_node):
                        node_id = future_to_node[future]
                        try:
                            node_result = future.result()
                            group_results[node_id] = node_result
                            self.logger.debug(f"Node {node_id} completed successfully")
                        except Exception as e:
                            self.logger.error(f"Node {node_id} failed: {e}")
                            # Decide whether to continue or fail the entire workflow
                            if self._should_stop_on_group_error(
                                workflow, node_id, node_group
                            ):
                                raise WorkflowExecutionError(
                                    f"Critical node {node_id} failed: {e}"
                                ) from e
                            else:
                                group_results[node_id] = {
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                    "failed": True,
                                }

                    # Update results with this group's outputs
                    results.update(group_results)

            # Mark run as completed
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "completed")
                except Exception as e:
                    self.logger.warning(f"Failed to update run status: {e}")

            return results, run_id

        except Exception as e:
            # Mark run as failed
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "failed", error=str(e))
                except Exception:
                    pass
            raise

    def _analyze_parallel_groups(
        self, workflow: Workflow, parallel_nodes: set[str] | None
    ) -> list[list[str]]:
        """Analyze workflow to identify groups of nodes that can be executed in parallel.

        Args:
            workflow: Workflow to analyze
            parallel_nodes: Optional hint for nodes that can be parallelized

        Returns:
            List of execution groups, each containing nodes that can run in parallel
        """
        # Get topological ordering to respect dependencies
        try:
            topo_order = list(nx.topological_sort(workflow.graph))
        except nx.NetworkXError as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e

        # Group nodes by their dependency level
        # Nodes at the same level can potentially be executed in parallel
        levels = {}
        for node in topo_order:
            # Find the maximum level of all predecessors
            max_pred_level = -1
            for pred in workflow.graph.predecessors(node):
                max_pred_level = max(max_pred_level, levels.get(pred, 0))
            levels[node] = max_pred_level + 1

        # Group nodes by level
        level_groups = {}
        for node, level in levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(node)

        # Convert to execution groups
        execution_groups = []
        for level in sorted(level_groups.keys()):
            nodes_at_level = level_groups[level]

            # If parallel_nodes hint is provided, only parallelize those nodes
            if parallel_nodes:
                parallel_subset = [n for n in nodes_at_level if n in parallel_nodes]
                sequential_subset = [
                    n for n in nodes_at_level if n not in parallel_nodes
                ]

                # Add parallel subset as a group
                if parallel_subset:
                    execution_groups.append(parallel_subset)

                # Add sequential nodes one by one
                for node in sequential_subset:
                    execution_groups.append([node])
            else:
                # All nodes at this level can be parallelized
                if len(nodes_at_level) > 1:
                    execution_groups.append(nodes_at_level)
                else:
                    execution_groups.append(nodes_at_level)

        return execution_groups

    def _execute_single_node(
        self,
        workflow: Workflow,
        node_id: str,
        previous_results: dict[str, Any],
        parameters: dict[str, dict[str, Any]] | None,
        task_manager: TaskManager | None,
        run_id: str | None,
    ) -> dict[str, Any]:
        """Execute a single node in isolation.

        Args:
            workflow: Workflow containing the node
            node_id: ID of node to execute
            previous_results: Results from previously executed nodes
            parameters: Optional parameter overrides
            task_manager: Optional task manager
            run_id: Optional run ID for tracking

        Returns:
            Node execution results

        Raises:
            WorkflowExecutionError: If node execution fails
        """
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
                    started_at=datetime.now(UTC),
                    metadata={},
                )
                if task:
                    task_manager.update_task_status(task.task_id, TaskStatus.RUNNING)
            except Exception as e:
                self.logger.warning(f"Failed to create task for node '{node_id}': {e}")

        try:
            # Prepare inputs
            inputs = self._prepare_node_inputs_parallel(
                workflow,
                node_id,
                node_instance,
                previous_results,
                parameters.get(node_id, {}) if parameters else {},
            )

            if self.debug:
                self.logger.debug(f"Node {node_id} inputs: {inputs}")

            # Execute node with metrics collection
            collector = MetricsCollector()
            with collector.collect(node_id=node_id) as metrics_context:
                outputs = node_instance.execute(**inputs)

            # Get performance metrics
            performance_metrics = metrics_context.result()

            if self.debug:
                self.logger.debug(f"Node {node_id} outputs: {outputs}")

            # Update task status
            if task and task_manager:
                task_metrics_data = performance_metrics.to_task_metrics()
                task_metrics = TaskMetrics(**task_metrics_data)

                task_manager.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    result=outputs,
                    ended_at=datetime.now(UTC),
                    metadata={"execution_time": performance_metrics.duration},
                )
                task_manager.update_task_metrics(task.task_id, task_metrics)

            self.logger.info(
                f"Node {node_id} completed successfully in {performance_metrics.duration:.3f}s"
            )

            return outputs

        except Exception as e:
            # Update task status
            if task and task_manager:
                task_manager.update_task_status(
                    task.task_id,
                    TaskStatus.FAILED,
                    error=str(e),
                    ended_at=datetime.now(UTC),
                )

            self.logger.error(f"Node {node_id} failed: {e}", exc_info=self.debug)
            raise WorkflowExecutionError(
                f"Node '{node_id}' execution failed: {e}"
            ) from e

    def _prepare_node_inputs_parallel(
        self,
        workflow: Workflow,
        node_id: str,
        node_instance: Node,
        previous_results: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare inputs for a node execution in parallel context.

        Args:
            workflow: The workflow being executed
            node_id: Current node ID
            node_instance: Current node instance
            previous_results: Results from previously executed nodes
            parameters: Parameter overrides

        Returns:
            Dictionary of inputs for the node
        """
        inputs = {}

        # Start with node configuration
        inputs.update(node_instance.config)

        # Add connected inputs from other nodes
        for edge in workflow.graph.in_edges(node_id, data=True):
            source_node_id = edge[0]
            mapping = edge[2].get("mapping", {})

            if source_node_id in previous_results:
                source_outputs = previous_results[source_node_id]

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

    def _can_execute_in_parallel(self, workflow: Workflow) -> bool:
        """Determine if workflow has opportunities for parallel execution.

        Args:
            workflow: Workflow to analyze

        Returns:
            True if parallel execution is beneficial
        """
        # Simple heuristic: if there are nodes at the same dependency level
        try:
            topo_order = list(nx.topological_sort(workflow.graph))

            # Calculate dependency levels
            levels = {}
            for node in topo_order:
                max_pred_level = -1
                for pred in workflow.graph.predecessors(node):
                    max_pred_level = max(max_pred_level, levels.get(pred, 0))
                levels[node] = max_pred_level + 1

            # Check if any level has multiple nodes
            level_counts = {}
            for level in levels.values():
                level_counts[level] = level_counts.get(level, 0) + 1

            # If any level has more than one node, parallel execution is beneficial
            return any(count > 1 for count in level_counts.values())

        except nx.NetworkXError:
            return False

    def _should_stop_on_group_error(
        self, workflow: Workflow, failed_node: str, node_group: list[str]
    ) -> bool:
        """Determine if execution should stop when a node in a parallel group fails.

        Args:
            workflow: The workflow being executed
            failed_node: Failed node ID
            node_group: The parallel group containing the failed node

        Returns:
            Whether to stop execution
        """
        # Check if any other nodes in the workflow depend on this failed node
        has_dependents = workflow.graph.out_degree(failed_node) > 0

        # If the failed node has dependents, we should stop
        # Future enhancement: implement more sophisticated error handling policies
        return has_dependents

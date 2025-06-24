"""Comprehensive Execution Engine for Cyclic Workflows.

This module provides the core execution engine for cyclic workflows with
advanced parameter propagation, comprehensive task tracking, and performance
monitoring. It handles both DAG and cyclic portions of workflows with
sophisticated safety mechanisms and detailed execution analytics.

Design Philosophy:
    Provides a robust, production-ready execution engine that seamlessly
    handles both traditional DAG workflows and complex cyclic patterns.
    Emphasizes safety, observability, and performance with comprehensive
    tracking at multiple granularity levels.

Key Features:
    - Hybrid DAG/Cycle execution with automatic detection
    - Sophisticated parameter propagation between iterations
    - Multi-level task tracking (workflow → cycle → iteration → node)
    - Performance metrics collection with detailed analytics
    - Safety mechanisms with timeout, memory, and iteration limits
    - Real-time monitoring and health checks

Execution Architecture:
    - WorkflowState: Manages execution state and parameter flow
    - CyclicWorkflowExecutor: Main execution orchestrator
    - ExecutionPlan: Optimized execution strategy
    - CycleGroup: Manages individual cycle execution
    - Safety integration with CycleSafetyManager

Task Tracking Hierarchy:
    1. Workflow Run: Overall execution tracking
    2. Cycle Groups: Individual cycle execution tracking
    3. Cycle Iterations: Per-iteration execution tracking
    4. Node Executions: Individual node execution tracking
    5. Performance Metrics: Detailed timing and resource usage

Parameter Propagation:
    - Initial parameters for first iteration
    - Cross-iteration parameter flow with mapping
    - State preservation between iterations
    - Convergence value tracking
    - Error handling and recovery

Upstream Dependencies:
    - Workflow graph structure and validation
    - Node implementations and execution contracts
    - Safety managers for resource limits
    - Task tracking and metrics collection systems

Downstream Consumers:
    - Runtime engines for workflow execution
    - Monitoring systems for execution tracking
    - Performance analysis and optimization tools
    - Debug and development tools

Safety and Monitoring:
    - Configurable safety limits (iterations, timeout, memory)
    - Real-time convergence monitoring
    - Resource usage tracking and alerting
    - Graceful degradation and error recovery
    - Comprehensive logging and debugging support

Examples:
    Basic cyclic execution:

    >>> executor = CyclicWorkflowExecutor()
    >>> # Execute workflow with cycles
    >>> results, run_id = executor.execute(
    ...     workflow,
    ...     parameters={"initial_value": 10},
    ...     task_manager=task_manager
    ... )

    With safety configuration:

    >>> from kailash.workflow.safety import CycleSafetyManager
    >>> safety_manager = CycleSafetyManager(
    ...     default_max_iterations=100,
    ...     default_timeout=300,
    ...     default_memory_limit=1024
    ... )
    >>> executor = CyclicWorkflowExecutor(safety_manager)
    >>> results, run_id = executor.execute(workflow, parameters)

    With comprehensive tracking:

    >>> from kailash.tracking import TaskManager
    >>> task_manager = TaskManager()
    >>> results, run_id = executor.execute(
    ...     workflow, parameters, task_manager, run_id="custom_run_001"
    ... )
    >>> # Access detailed tracking information
    >>> tasks = task_manager.get_tasks_for_run(run_id)
    >>> metrics = task_manager.get_metrics_for_run(run_id)

See Also:
    - :mod:`kailash.workflow.safety` for safety mechanisms and limits
    - :mod:`kailash.tracking` for comprehensive execution tracking
    - :mod:`kailash.workflow.convergence` for convergence conditions
"""

import logging
from datetime import UTC, datetime
from typing import Any, Optional

import networkx as nx

from kailash.sdk_exceptions import WorkflowExecutionError, WorkflowValidationError
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.tracking.models import TaskMetrics
from kailash.workflow.convergence import create_convergence_condition
from kailash.workflow.cycle_state import CycleState, CycleStateManager
from kailash.workflow.graph import Workflow
from kailash.workflow.runner import WorkflowRunner
from kailash.workflow.safety import CycleSafetyManager, monitored_cycle

logger = logging.getLogger(__name__)


class WorkflowState:
    """Simple workflow execution state container."""

    def __init__(self, run_id: str):
        """Initialize workflow state.

        Args:
            run_id: Unique execution run ID
        """
        self.run_id = run_id
        self.node_outputs: dict[str, Any] = {}
        self.execution_order: list[str] = []
        self.metadata: dict[str, Any] = {}


class CyclicWorkflowExecutor:
    """Execution engine supporting cyclic workflows with fixed parameter propagation."""

    def __init__(self, safety_manager: CycleSafetyManager | None = None):
        """Initialize cyclic workflow executor.

        Args:
            safety_manager: Optional safety manager for resource limits
        """
        self.safety_manager = safety_manager or CycleSafetyManager()
        self.cycle_state_manager = CycleStateManager()
        self.dag_runner = WorkflowRunner()  # For executing DAG portions

    def execute(
        self,
        workflow: Workflow,
        parameters: dict[str, Any] | None = None,
        task_manager: TaskManager | None = None,
        run_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Execute workflow with cycle support.

        Args:
            workflow: Workflow to execute
            parameters: Initial parameters/overrides
            task_manager: Optional task manager for tracking execution
            run_id: Optional run ID to use (if not provided, one will be generated)

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            WorkflowExecutionError: If execution fails
            WorkflowValidationError: If workflow is invalid
        """
        # Validate workflow (including cycles)
        workflow.validate(runtime_parameters=parameters)

        # Generate run ID if not provided
        if not run_id:
            import uuid

            run_id = str(uuid.uuid4())

        logger.info(
            f"Starting cyclic workflow execution: {workflow.name} (run_id: {run_id})"
        )

        # Check if workflow has cycles
        if not workflow.has_cycles():
            # No cycles, use standard DAG execution
            logger.info("No cycles detected, using standard DAG execution")
            return self.dag_runner.run(workflow, parameters), run_id

        # Execute with cycle support
        try:
            results = self._execute_with_cycles(
                workflow, parameters, run_id, task_manager
            )
            logger.info(f"Cyclic workflow execution completed: {workflow.name}")
            return results, run_id

        except Exception as e:
            logger.error(f"Cyclic workflow execution failed: {e}")
            raise WorkflowExecutionError(f"Execution failed: {e}") from e

        finally:
            # Clean up cycle states
            self.cycle_state_manager.clear()

    def _filter_none_values(self, obj: Any) -> Any:
        """Recursively filter None values from nested dictionaries.

        Args:
            obj: Object to filter (dict, list, or other)

        Returns:
            Filtered object with None values removed
        """
        if isinstance(obj, dict):
            return {
                k: self._filter_none_values(v) for k, v in obj.items() if v is not None
            }
        elif isinstance(obj, list):
            return [self._filter_none_values(item) for item in obj if item is not None]
        else:
            return obj

    def _execute_with_cycles(
        self,
        workflow: Workflow,
        parameters: dict[str, Any] | None,
        run_id: str,
        task_manager: TaskManager | None = None,
    ) -> dict[str, Any]:
        """Execute workflow with cycle handling.

        Args:
            workflow: Workflow to execute
            parameters: Initial parameters
            run_id: Execution run ID
            task_manager: Optional task manager for tracking

        Returns:
            Final execution results
        """
        # Separate DAG and cycle edges
        dag_edges, cycle_edges = workflow.separate_dag_and_cycle_edges()
        cycle_groups = workflow.get_cycle_groups()

        # Create execution plan
        execution_plan = self._create_execution_plan(workflow, dag_edges, cycle_groups)

        # Initialize workflow state
        state = WorkflowState(run_id=run_id)

        # Store initial parameters separately (don't treat them as outputs!)
        state.initial_parameters = parameters or {}

        # Execute the plan
        results = self._execute_plan(workflow, execution_plan, state, task_manager)

        # Log cycle summaries
        summaries = self.cycle_state_manager.get_all_summaries()
        for cycle_id, summary in summaries.items():
            logger.info(f"Cycle {cycle_id} summary: {summary}")

        return results

    def _create_execution_plan(
        self,
        workflow: Workflow,
        dag_edges: list[tuple],
        cycle_groups: dict[str, list[tuple]],
    ) -> "ExecutionPlan":
        """Create execution plan handling cycles.

        Args:
            workflow: Workflow instance
            dag_edges: List of DAG edges
            cycle_groups: Grouped cycle edges

        Returns:
            ExecutionPlan instance
        """
        plan = ExecutionPlan()

        # Create DAG-only graph for topological analysis
        dag_graph = nx.DiGraph()
        dag_graph.add_nodes_from(workflow.graph.nodes(data=True))
        for source, target, data in dag_edges:
            dag_graph.add_edge(source, target, **data)

        # Get topological order for DAG portion
        try:
            topo_order = list(nx.topological_sort(dag_graph))
        except nx.NetworkXUnfeasible:
            raise WorkflowValidationError("DAG portion contains unmarked cycles")

        # Identify cycle entry and exit points
        for cycle_id, cycle_edges in cycle_groups.items():
            cycle_nodes = set()
            entry_nodes = set()
            exit_nodes = set()

            # First, collect all nodes in the cycle
            for source, target, data in cycle_edges:
                cycle_nodes.add(source)
                cycle_nodes.add(target)

            # Then identify entry and exit nodes
            for node in cycle_nodes:
                # Entry nodes have incoming edges from non-cycle nodes
                for pred in workflow.graph.predecessors(node):
                    if pred not in cycle_nodes:
                        entry_nodes.add(node)
                        logger.debug(
                            f"Cycle {cycle_id}: Node {node} is an entry node (has predecessor {pred})"
                        )

                # Exit nodes have outgoing edges to non-cycle nodes
                for succ in workflow.graph.successors(node):
                    if succ not in cycle_nodes:
                        exit_nodes.add(node)

            logger.debug(
                f"Cycle {cycle_id}: nodes={cycle_nodes}, entry_nodes={entry_nodes}, exit_nodes={exit_nodes}"
            )

            plan.add_cycle_group(
                cycle_id=cycle_id,
                nodes=cycle_nodes,
                entry_nodes=entry_nodes,
                exit_nodes=exit_nodes,
                edges=cycle_edges,
            )

        # Build execution stages
        plan.build_stages(topo_order, dag_graph, workflow)

        return plan

    def _execute_plan(
        self,
        workflow: Workflow,
        plan: "ExecutionPlan",
        state: WorkflowState,
        task_manager: TaskManager | None = None,
    ) -> dict[str, Any]:
        """Execute the workflow plan.

        Args:
            workflow: Workflow instance
            plan: Execution plan
            state: Workflow state
            task_manager: Optional task manager for tracking

        Returns:
            Execution results
        """
        results = {}

        logger.info(f"Executing plan with {len(plan.stages)} stages")

        for i, stage in enumerate(plan.stages):
            logger.info(
                f"Executing stage {i+1}: is_cycle={stage.is_cycle}, nodes={getattr(stage, 'nodes', 'N/A')}"
            )
            if stage.is_cycle:
                logger.info(
                    f"Stage {i+1} is a cycle group: {stage.cycle_group.cycle_id}"
                )
                # Execute cycle group
                cycle_results = self._execute_cycle_group(
                    workflow, stage.cycle_group, state, task_manager
                )
                results.update(cycle_results)
            else:
                # Execute DAG nodes
                for node_id in stage.nodes:
                    if node_id not in state.node_outputs:
                        logger.info(f"Executing DAG node: {node_id}")
                        node_result = self._execute_node(
                            workflow, node_id, state, task_manager=task_manager
                        )
                        results[node_id] = node_result
                        state.node_outputs[node_id] = node_result

        return results

    def _execute_cycle_group(
        self,
        workflow: Workflow,
        cycle_group: "CycleGroup",
        state: WorkflowState,
        task_manager: TaskManager | None = None,
    ) -> dict[str, Any]:
        """Execute a cycle group with proper parameter propagation.

        Args:
            workflow: Workflow instance
            cycle_group: Cycle group to execute
            state: Workflow state
            task_manager: Optional task manager for tracking

        Returns:
            Cycle execution results
        """
        cycle_id = cycle_group.cycle_id
        logger.info(f"*** EXECUTING CYCLE GROUP: {cycle_id} ***")
        logger.info(f"Cycle nodes: {cycle_group.nodes}")
        logger.info(f"Cycle edges: {cycle_group.edges}")

        # Get cycle configuration from first edge
        cycle_config = {}
        convergence_check = None
        if cycle_group.edges:
            _, _, edge_data = cycle_group.edges[0]
            # Extract convergence check separately
            convergence_check = edge_data.get("convergence_check")
            # Safety config only includes safety-related parameters
            cycle_config = {
                "max_iterations": edge_data.get("max_iterations"),
                "timeout": edge_data.get("timeout"),
                "memory_limit": edge_data.get("memory_limit"),
            }

        # Create convergence condition
        convergence_condition = None
        if convergence_check:
            convergence_condition = create_convergence_condition(convergence_check)

        # Get or create cycle state
        cycle_state = self.cycle_state_manager.get_or_create_state(cycle_id)

        # Start monitoring
        with monitored_cycle(self.safety_manager, cycle_id, **cycle_config) as monitor:
            results = {}

            # Store previous iteration results for parameter propagation
            previous_iteration_results = {}

            # Create cycle group task if task manager available
            cycle_task_id = None
            if task_manager and state.run_id:
                try:
                    cycle_task = task_manager.create_task(
                        run_id=state.run_id,
                        node_id=f"cycle_group_{cycle_id}",
                        node_type="CycleGroup",
                        started_at=datetime.now(UTC),
                        metadata={
                            "cycle_id": cycle_id,
                            "max_iterations": cycle_config.get("max_iterations"),
                            "nodes_in_cycle": list(cycle_group.nodes),
                        },
                    )
                    if cycle_task:
                        cycle_task_id = cycle_task.task_id
                        task_manager.update_task_status(
                            cycle_task_id, TaskStatus.RUNNING
                        )
                except Exception as e:
                    logger.warning(f"Failed to create cycle group task: {e}")

            loop_count = 0
            while True:
                loop_count += 1
                logger.info(f"Cycle {cycle_id} - Starting loop iteration {loop_count}")

                # Record iteration
                monitor.record_iteration()

                # Create iteration task if task manager available
                iteration_task_id = None
                if task_manager and state.run_id:
                    try:
                        iteration_task = task_manager.create_task(
                            run_id=state.run_id,
                            node_id=f"cycle_{cycle_id}_iteration_{loop_count}",
                            node_type="CycleIteration",
                            started_at=datetime.now(UTC),
                            metadata={
                                "cycle_id": cycle_id,
                                "iteration": loop_count,
                                "parent_task": cycle_task_id,
                            },
                        )
                        if iteration_task:
                            iteration_task_id = iteration_task.task_id
                            task_manager.update_task_status(
                                iteration_task_id, TaskStatus.RUNNING
                            )
                    except Exception as e:
                        logger.warning(f"Failed to create iteration task: {e}")

                # Execute nodes in cycle
                iteration_results = {}
                for node_id in cycle_group.get_execution_order(workflow.graph):
                    node_result = self._execute_node(
                        workflow,
                        node_id,
                        state,
                        cycle_state,
                        cycle_edges=cycle_group.edges,
                        previous_iteration_results=previous_iteration_results,
                        task_manager=task_manager,
                        iteration=loop_count,
                    )
                    iteration_results[node_id] = node_result
                    state.node_outputs[node_id] = node_result

                # Update results for this iteration
                results.update(iteration_results)

                # Store this iteration's results for next iteration
                previous_iteration_results = iteration_results.copy()

                # Log iteration info BEFORE state update
                logger.info(
                    f"Cycle {cycle_id} iteration {cycle_state.iteration} (before update) results: {iteration_results}"
                )

                # Update cycle state
                cycle_state.update(iteration_results)

                # Check convergence
                should_terminate = False

                # Log after update
                logger.info(
                    f"Cycle {cycle_id} iteration now at {cycle_state.iteration} (after update)"
                )

                # Check max iterations - loop_count represents actual iterations executed
                max_iterations = cycle_config.get("max_iterations", float("inf"))
                if loop_count >= max_iterations:
                    logger.info(
                        f"Cycle {cycle_id} reached max iterations: {loop_count}/{max_iterations}"
                    )
                    should_terminate = True

                # Check convergence condition
                if convergence_condition:
                    converged = convergence_condition.evaluate(
                        iteration_results, cycle_state
                    )
                    logger.info(
                        f"Cycle {cycle_id} convergence check: {convergence_condition.describe()} = {converged}"
                    )
                    if converged:
                        logger.info(
                            f"Cycle {cycle_id} converged: {convergence_condition.describe()}"
                        )
                        should_terminate = True

                # Check safety violations
                if monitor.check_violations():
                    logger.warning(
                        f"Cycle {cycle_id} safety violation: {monitor.violations}"
                    )
                    should_terminate = True

                # Complete iteration task
                if iteration_task_id and task_manager:
                    try:
                        task_manager.update_task_status(
                            iteration_task_id,
                            TaskStatus.COMPLETED,
                            ended_at=datetime.now(UTC),
                            result=iteration_results,
                            metadata={
                                "converged": (
                                    converged if "converged" in locals() else False
                                ),
                                "terminated": should_terminate,
                            },
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update iteration task: {e}")

                if should_terminate:
                    logger.info(
                        f"Cycle {cycle_id} terminating after {loop_count} iterations"
                    )
                    break

                logger.info(f"Cycle {cycle_id} continuing to next iteration")

            # Complete cycle group task
            if cycle_task_id and task_manager:
                try:
                    summary = cycle_state.get_summary()
                    task_manager.update_task_status(
                        cycle_task_id,
                        TaskStatus.COMPLETED,
                        ended_at=datetime.now(UTC),
                        result=results,
                        metadata={
                            "total_iterations": loop_count,
                            "converged": (
                                converged if "converged" in locals() else False
                            ),
                            "summary": summary,
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to update cycle group task: {e}")

            # Log cycle completion
            summary = cycle_state.get_summary()
            logger.info(f"Cycle {cycle_id} completed: {summary}")

            return results

    def _execute_node(
        self,
        workflow: Workflow,
        node_id: str,
        state: WorkflowState,
        cycle_state: CycleState | None = None,
        cycle_edges: list[tuple] | None = None,
        previous_iteration_results: dict[str, Any] | None = None,
        task_manager: TaskManager | None = None,
        iteration: int | None = None,
    ) -> Any:
        """Execute a single node with proper parameter handling for cycles.

        Args:
            workflow: Workflow instance
            node_id: Node to execute
            state: Workflow state
            cycle_state: Optional cycle state
            cycle_edges: List of edges in the current cycle
            previous_iteration_results: Results from previous cycle iteration

        Returns:
            Node execution result
        """
        node = workflow.get_node(node_id)
        if not node:
            raise WorkflowExecutionError(f"Node not found: {node_id}")

        # Gather inputs from connections
        inputs = {}

        logger.debug(
            f"_execute_node {node_id}: state.node_outputs keys = {list(state.node_outputs.keys())}"
        )

        # Check if we're in a cycle and this is not the first iteration
        in_cycle = cycle_state is not None
        is_cycle_iteration = in_cycle and cycle_state.iteration > 0

        for pred, _, edge_data in workflow.graph.in_edges(node_id, data=True):
            # Check if this edge is a cycle edge (but NOT synthetic)
            is_cycle_edge = edge_data.get("cycle", False) and not edge_data.get(
                "synthetic", False
            )

            # Determine where to get the predecessor output from
            if is_cycle_edge and is_cycle_iteration and previous_iteration_results:
                # For cycle edges after first iteration, use previous iteration results
                pred_output = previous_iteration_results.get(pred)
            elif pred in state.node_outputs:
                # For non-cycle edges or first iteration, use normal state
                pred_output = state.node_outputs[pred]
            else:
                # No output available
                continue

            if pred_output is None:
                continue

            # Apply mapping
            mapping = edge_data.get("mapping", {})
            logger.debug(
                f"Edge {pred} -> {node_id}: mapping = {mapping}, pred_output keys = {list(pred_output.keys()) if isinstance(pred_output, dict) else type(pred_output)}"
            )
            for src_key, dst_key in mapping.items():
                # Handle nested output access
                if "." in src_key:
                    # Navigate nested structure
                    value = pred_output
                    for part in src_key.split("."):
                        if isinstance(value, dict) and part in value:
                            value = value[part]
                        else:
                            value = None
                            break
                    if value is not None:
                        inputs[dst_key] = value
                elif isinstance(pred_output, dict) and src_key in pred_output:
                    inputs[dst_key] = pred_output[src_key]
                    logger.debug(
                        f"Mapped {src_key} -> {dst_key}: {type(pred_output[src_key])}, length={len(pred_output[src_key]) if hasattr(pred_output[src_key], '__len__') else 'N/A'}"
                    )
                elif src_key == "output":
                    # Default output mapping
                    inputs[dst_key] = pred_output

        # Create context with cycle information
        context = {
            "workflow_id": workflow.workflow_id,
            "run_id": state.run_id,
            "node_id": node_id,
        }

        if cycle_state:
            cycle_context = {
                "cycle_id": cycle_state.cycle_id,
                "iteration": cycle_state.iteration,
                "elapsed_time": cycle_state.elapsed_time,
            }
            # Always include node_state in context, defaulting to empty dict
            node_state = cycle_state.get_node_state(node_id)
            cycle_context["node_state"] = node_state if node_state is not None else {}
            context["cycle"] = cycle_context

        # Recursively filter None values from context to avoid security validation errors
        context = self._filter_none_values(context)

        # Merge node config with inputs
        # Order: config < initial_parameters < connection inputs
        merged_inputs = {**node.config}

        # Add initial parameters if available
        # For cycle nodes, initial parameters should be available throughout all iterations
        if hasattr(state, "initial_parameters") and node_id in state.initial_parameters:
            if node_id not in state.node_outputs or cycle_state is not None:
                # Use initial parameters on first execution or for any cycle iteration
                merged_inputs.update(state.initial_parameters[node_id])

        # Connection inputs override everything
        merged_inputs.update(inputs)

        # Filter out None values to avoid security validation errors
        merged_inputs = {k: v for k, v in merged_inputs.items() if v is not None}

        logger.debug(
            f"Final merged_inputs for {node_id}: keys={list(merged_inputs.keys())}"
        )

        # Create task for node execution if task manager available
        task = None
        if task_manager and state.run_id:
            try:
                # Build task node ID based on context
                task_node_id = node_id
                if cycle_state and iteration:
                    task_node_id = (
                        f"{node_id}_cycle_{cycle_state.cycle_id}_iteration_{iteration}"
                    )

                # Create metadata
                task_metadata = {
                    "node_type": node.__class__.__name__,
                }
                if cycle_state:
                    task_metadata.update(
                        {
                            "cycle_id": cycle_state.cycle_id,
                            "iteration": iteration or cycle_state.iteration,
                            "in_cycle": True,
                        }
                    )

                task = task_manager.create_task(
                    run_id=state.run_id,
                    node_id=task_node_id,
                    node_type=node.__class__.__name__,
                    started_at=datetime.now(UTC),
                    metadata=task_metadata,
                )
                if task:
                    task_manager.update_task_status(task.task_id, TaskStatus.RUNNING)
            except Exception as e:
                logger.warning(f"Failed to create task for node '{node_id}': {e}")

        # Execute node with metrics collection
        collector = MetricsCollector()
        logger.debug(
            f"Executing node: {node_id} (iteration: {cycle_state.iteration if cycle_state else 'N/A'})"
        )

        try:
            with collector.collect(node_id=node_id) as metrics_context:
                result = node.execute(context=context, **merged_inputs)

            # Get performance metrics
            performance_metrics = metrics_context.result()

            # Update task status with metrics
            if task and task_manager:
                try:
                    # Convert performance metrics to TaskMetrics format
                    task_metrics_data = performance_metrics.to_task_metrics()
                    task_metrics = TaskMetrics(**task_metrics_data)

                    task_manager.update_task_status(
                        task.task_id,
                        TaskStatus.COMPLETED,
                        result=result,
                        ended_at=datetime.now(UTC),
                        metadata={"execution_time": performance_metrics.duration},
                    )

                    # Update task metrics
                    task_manager.update_task_metrics(task.task_id, task_metrics)
                except Exception as e:
                    logger.warning(f"Failed to update task for node '{node_id}': {e}")

        except Exception as e:
            # Update task status on failure
            if task and task_manager:
                try:
                    task_manager.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(e),
                        ended_at=datetime.now(UTC),
                    )
                except Exception as update_error:
                    logger.warning(
                        f"Failed to update task status on error: {update_error}"
                    )
            raise

        # Store node state if in cycle
        if cycle_state and isinstance(result, dict) and "_cycle_state" in result:
            cycle_state.set_node_state(node_id, result["_cycle_state"])

        return result


class ExecutionPlan:
    """Execution plan for workflows with cycles."""

    def __init__(self):
        """Initialize execution plan."""
        self.stages: list["ExecutionStage"] = []
        self.cycle_groups: dict[str, "CycleGroup"] = {}

    def add_cycle_group(
        self,
        cycle_id: str,
        nodes: set[str],
        entry_nodes: set[str],
        exit_nodes: set[str],
        edges: list[tuple],
    ) -> None:
        """Add a cycle group to the plan.

        Args:
            cycle_id: Cycle identifier
            nodes: Nodes in the cycle
            entry_nodes: Entry points to the cycle
            exit_nodes: Exit points from the cycle
            edges: Cycle edges
        """
        self.cycle_groups[cycle_id] = CycleGroup(
            cycle_id=cycle_id,
            nodes=nodes,
            entry_nodes=entry_nodes,
            exit_nodes=exit_nodes,
            edges=edges,
        )

    def build_stages(
        self, topo_order: list[str], dag_graph: nx.DiGraph, workflow: Workflow
    ) -> None:
        """Build execution stages.

        Args:
            topo_order: Topological order of DAG nodes
            dag_graph: DAG portion of the graph
            workflow: The full workflow for checking dependencies
        """
        # Track which nodes have been scheduled
        scheduled = set()

        logger.debug(
            f"Building stages - cycle_groups: {list(self.cycle_groups.keys())}"
        )
        logger.debug(f"Building stages - topo_order: {topo_order}")

        for node_id in topo_order:
            if node_id in scheduled:
                continue

            # Check if node is part of a cycle
            in_cycle_id = None
            found_cycle_group = None
            for cycle_id, cycle_group in self.cycle_groups.items():
                logger.debug(
                    f"Checking node {node_id} against cycle {cycle_id} with nodes {cycle_group.nodes}"
                )
                if node_id in cycle_group.nodes:
                    in_cycle_id = cycle_id
                    found_cycle_group = cycle_group
                    logger.debug(f"Node {node_id} found in cycle {cycle_id}")
                    break

            logger.debug(
                f"in_cycle_id value: {in_cycle_id}, found_cycle_group: {found_cycle_group is not None}"
            )
            if found_cycle_group is not None:
                # Check if all DAG dependencies of cycle entry nodes are satisfied
                can_schedule_cycle = True
                logger.debug(
                    f"Checking dependencies for cycle {in_cycle_id}, entry_nodes: {found_cycle_group.entry_nodes}"
                )
                for entry_node in found_cycle_group.entry_nodes:
                    # Check all predecessors of this entry node in the FULL workflow graph
                    # (dag_graph only contains DAG edges, not connections to cycle nodes)
                    preds = list(workflow.graph.predecessors(entry_node))
                    logger.debug(
                        f"Entry node {entry_node} has predecessors: {preds}, scheduled: {scheduled}"
                    )
                    for pred in preds:
                        # Skip self-cycles and nodes within the same cycle group
                        logger.debug(
                            f"Checking pred {pred}: in scheduled? {pred in scheduled}, in cycle? {pred in found_cycle_group.nodes}"
                        )
                        if (
                            pred not in scheduled
                            and pred not in found_cycle_group.nodes
                        ):
                            # This predecessor hasn't been scheduled yet
                            logger.debug(
                                f"Cannot schedule cycle {in_cycle_id} yet - entry node {entry_node} "
                                f"depends on unscheduled node {pred}"
                            )
                            can_schedule_cycle = False
                            break
                    if not can_schedule_cycle:
                        break

                if can_schedule_cycle:
                    logger.debug(
                        f"Scheduling cycle group {in_cycle_id} for node {node_id}"
                    )
                    # Schedule entire cycle group
                    self.stages.append(
                        ExecutionStage(is_cycle=True, cycle_group=found_cycle_group)
                    )
                    scheduled.update(found_cycle_group.nodes)
                else:
                    # Skip this node for now, it will be scheduled when its dependencies are met
                    logger.debug(
                        f"Deferring cycle group {in_cycle_id} - dependencies not met"
                    )
                    continue
            else:
                logger.debug(f"Scheduling DAG node {node_id}")
                # Schedule DAG node
                self.stages.append(ExecutionStage(is_cycle=False, nodes=[node_id]))
                scheduled.add(node_id)

        # After processing all nodes in topological order, check for any unscheduled cycle groups
        for cycle_id, cycle_group in self.cycle_groups.items():
            if not any(node in scheduled for node in cycle_group.nodes):
                # This cycle group hasn't been scheduled yet
                # Check if all dependencies are now satisfied
                can_schedule = True
                for entry_node in cycle_group.entry_nodes:
                    for pred in workflow.graph.predecessors(entry_node):
                        if pred not in scheduled and pred not in cycle_group.nodes:
                            logger.warning(
                                f"Cycle group {cycle_id} has unsatisfied dependency: "
                                f"{entry_node} depends on {pred}"
                            )
                            can_schedule = False
                            break
                    if not can_schedule:
                        break

                if can_schedule:
                    logger.debug(f"Scheduling deferred cycle group {cycle_id}")
                    self.stages.append(
                        ExecutionStage(is_cycle=True, cycle_group=cycle_group)
                    )
                    scheduled.update(cycle_group.nodes)


class ExecutionStage:
    """Single stage in execution plan."""

    def __init__(
        self,
        is_cycle: bool,
        nodes: list[str] | None = None,
        cycle_group: Optional["CycleGroup"] = None,
    ):
        """Initialize execution stage.

        Args:
            is_cycle: Whether this is a cycle stage
            nodes: List of nodes (for DAG stage)
            cycle_group: Cycle group (for cycle stage)
        """
        self.is_cycle = is_cycle
        self.nodes = nodes or []
        self.cycle_group = cycle_group


class CycleGroup:
    """Group of nodes forming a cycle."""

    def __init__(
        self,
        cycle_id: str,
        nodes: set[str],
        entry_nodes: set[str],
        exit_nodes: set[str],
        edges: list[tuple],
    ):
        """Initialize cycle group.

        Args:
            cycle_id: Cycle identifier
            nodes: Nodes in the cycle
            entry_nodes: Entry points to the cycle
            exit_nodes: Exit points from the cycle
            edges: Cycle edges
        """
        self.cycle_id = cycle_id
        self.nodes = nodes
        self.entry_nodes = entry_nodes
        self.exit_nodes = exit_nodes
        self.edges = edges

    def get_execution_order(self, full_graph: nx.DiGraph) -> list[str]:
        """Get execution order for nodes in cycle.

        Args:
            full_graph: Full workflow graph

        Returns:
            Ordered list of node IDs
        """
        # Create subgraph with only cycle nodes
        cycle_subgraph = full_graph.subgraph(self.nodes)

        # Try topological sort on the subgraph (might work if cycle edges removed)
        try:
            # Remove cycle edges temporarily
            temp_graph = cycle_subgraph.copy()
            for source, target, _ in self.edges:
                if temp_graph.has_edge(source, target):
                    temp_graph.remove_edge(source, target)

            return list(nx.topological_sort(temp_graph))
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            # Fall back to entry nodes first, then others
            order = list(self.entry_nodes)
            for node in self.nodes:
                if node not in order:
                    order.append(node)
            return order

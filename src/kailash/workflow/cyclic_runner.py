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
        self.runtime = None  # Will be set by executor for enterprise features


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
        runtime=None,
    ) -> tuple[dict[str, Any], str]:
        """Execute workflow with cycle support.

        Args:
            workflow: Workflow to execute
            parameters: Initial parameters/overrides
            task_manager: Optional task manager for tracking execution
            run_id: Optional run ID to use (if not provided, one will be generated)
            runtime: Optional runtime instance for enterprise features (LocalRuntime)

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
            return self.dag_runner.execute(workflow, parameters), run_id

        # Execute with cycle support
        try:
            results = self._execute_with_cycles(
                workflow, parameters, run_id, task_manager, runtime
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

    def _should_skip_conditional_node_cyclic(
        self, workflow: Workflow, node_id: str, merged_inputs: dict[str, Any]
    ) -> bool:
        """Determine if a node should be skipped due to conditional routing in cyclic execution.

        This is similar to LocalRuntime._should_skip_conditional_node but adapted for cyclic execution.

        Args:
            workflow: The workflow being executed.
            node_id: Node ID to check.
            merged_inputs: Merged inputs for the node.

        Returns:
            True if the node should be skipped, False otherwise.
        """
        # Get all incoming edges for this node
        incoming_edges = list(workflow.graph.in_edges(node_id, data=True))

        # If the node has no incoming connections, don't skip it
        if not incoming_edges:
            return False

        # Check if any incoming edges are from conditional nodes
        has_conditional_inputs = False
        for source_node_id, _, edge_data in incoming_edges:
            try:
                source_node = workflow.get_node(source_node_id)
                if source_node and source_node.__class__.__name__ in ["SwitchNode"]:
                    has_conditional_inputs = True
                    break
            except:
                continue

        # If no conditional inputs, don't skip
        if not has_conditional_inputs:
            return False

        # Check if all connected inputs are None
        has_non_none_input = False
        for _, _, edge_data in incoming_edges:
            mapping = edge_data.get("mapping", {})
            for source_key, target_key in mapping.items():
                if (
                    target_key in merged_inputs
                    and merged_inputs[target_key] is not None
                ):
                    has_non_none_input = True
                    break
            if has_non_none_input:
                break

        # Skip the node if all connected inputs are None
        return not has_non_none_input

    def _execute_with_cycles(
        self,
        workflow: Workflow,
        parameters: dict[str, Any] | None,
        run_id: str,
        task_manager: TaskManager | None = None,
        runtime=None,
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
        # Store runtime for enterprise features
        state.runtime = runtime

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

        # Track nodes that need execution after cycles
        pending_post_cycle_nodes = set()

        logger.info(f"Executing plan with {len(plan.stages)} stages")

        for i, stage in enumerate(plan.stages):
            stage_nodes = getattr(stage, "nodes", "N/A")
            logger.info(
                f"Executing stage {i+1}: is_cycle={stage.is_cycle}, nodes={stage_nodes}"
            )
            if stage.is_cycle:
                logger.info(
                    f"Stage {i+1} is a cycle group: {stage.cycle_group.cycle_id}"
                )
                # Execute cycle group and get downstream nodes
                cycle_results, downstream_nodes = self._execute_cycle_group(
                    workflow, stage.cycle_group, state, task_manager
                )
                results.update(cycle_results)

                # Add downstream nodes to pending execution
                if downstream_nodes:
                    pending_post_cycle_nodes.update(downstream_nodes)
                    logger.info(
                        f"Added {len(downstream_nodes)} nodes for post-cycle execution"
                    )
            else:
                # Execute DAG nodes using extracted method
                dag_results = self._execute_dag_portion(
                    workflow, stage.nodes, state, task_manager
                )
                results.update(dag_results)

                # Remove executed nodes from pending
                for node in stage.nodes:
                    pending_post_cycle_nodes.discard(node)

        # Execute any remaining post-cycle nodes
        if pending_post_cycle_nodes:
            logger.info(f"Executing {len(pending_post_cycle_nodes)} post-cycle nodes")

            # We need to include all dependencies of post-cycle nodes to ensure they get their inputs
            # This includes both cycle and non-cycle dependencies
            nodes_to_execute = set(pending_post_cycle_nodes)

            # For each post-cycle node, check if it has unexecuted dependencies
            for node in list(pending_post_cycle_nodes):
                for pred in workflow.graph.predecessors(node):
                    if pred not in state.node_outputs and pred not in nodes_to_execute:
                        # This predecessor hasn't been executed yet
                        nodes_to_execute.add(pred)
                        logger.debug(
                            f"Adding dependency {pred} for post-cycle node {node}"
                        )

            # Order them topologically
            subgraph = workflow.graph.subgraph(nodes_to_execute)
            if nx.is_directed_acyclic_graph(subgraph):
                ordered_nodes = list(nx.topological_sort(subgraph))
            else:
                ordered_nodes = list(nodes_to_execute)

            post_cycle_results = self._execute_dag_portion(
                workflow, ordered_nodes, state, task_manager
            )
            results.update(post_cycle_results)

        return results

    def _execute_dag_portion(
        self,
        workflow: Workflow,
        dag_nodes: list[str],
        state: WorkflowState,
        task_manager: TaskManager | None = None,
    ) -> dict[str, Any]:
        """Execute DAG (non-cyclic) portion of the workflow.

        Args:
            workflow: Workflow instance
            dag_nodes: List of DAG node IDs to execute
            state: Workflow state
            task_manager: Optional task manager for tracking

        Returns:
            Dictionary with node IDs as keys and their results as values
        """
        results = {}

        for node_id in dag_nodes:
            if node_id not in state.node_outputs:
                logger.info(f"Executing DAG node: {node_id}")
                node_result = self._execute_node(
                    workflow, node_id, state, task_manager=task_manager
                )
                results[node_id] = node_result
                state.node_outputs[node_id] = node_result

        return results

    def _execute_cycle_groups(
        self,
        workflow: Workflow,
        cycle_groups: list["CycleGroup"],
        state: WorkflowState,
        task_manager: TaskManager | None = None,
    ) -> dict[str, Any]:
        """Execute cycle groups portion of the workflow.

        Args:
            workflow: Workflow instance
            cycle_groups: List of cycle groups to execute
            state: Workflow state
            task_manager: Optional task manager for tracking

        Returns:
            Dictionary with node IDs as keys and their results as values
        """
        results = {}

        for cycle_group in cycle_groups:
            logger.info(f"Executing cycle group: {cycle_group.cycle_id}")
            cycle_results, _ = self._execute_cycle_group(
                workflow, cycle_group, state, task_manager
            )
            results.update(cycle_results)

        return results

    def _propagate_parameters(
        self,
        current_params: dict[str, Any],
        current_results: dict[str, Any],
        cycle_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle parameter propagation between cycle iterations.

        Args:
            current_params: Current iteration parameters
            current_results: Results from current iteration
            cycle_config: Cycle configuration (optional)

        Returns:
            Updated parameters for the next iteration
        """
        # Base propagation: copy current results for next iteration
        next_params = current_results.copy() if current_results else {}

        # Apply any cycle-specific parameter mappings if provided
        if cycle_config and "parameter_mappings" in cycle_config:
            mappings = cycle_config["parameter_mappings"]
            for src_key, dst_key in mappings.items():
                if src_key in current_results:
                    next_params[dst_key] = current_results[src_key]

        # Preserve any initial parameters that aren't overridden
        for key, value in current_params.items():
            if key not in next_params:
                next_params[key] = value

        # Filter out None values to avoid validation errors
        next_params = self._filter_none_values(next_params)

        return next_params

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
        logger.info(f"Executing cycle group: {cycle_id}")
        logger.debug(f"Cycle nodes: {cycle_group.nodes}")
        logger.debug(f"Cycle edges: {cycle_group.edges}")

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
                execution_order = cycle_group.get_execution_order(workflow.graph)
                logger.debug(
                    f"Cycle {cycle_id} iteration {loop_count}: execution_order={execution_order}"
                )

                for node_id in execution_order:
                    logger.debug(f"Executing {node_id} in iteration {loop_count}")
                    node_result = self._execute_node(
                        workflow,
                        node_id,
                        state,
                        cycle_state,
                        cycle_edges=cycle_group.edges,
                        previous_iteration_results=previous_iteration_results,
                        current_iteration_results=iteration_results,  # CRITICAL FIX: Pass current iteration results
                        task_manager=task_manager,
                        iteration=loop_count,
                    )
                    # CRITICAL FIX: Handle None node results gracefully
                    if node_result is not None:
                        iteration_results[node_id] = node_result
                    else:
                        logger.debug(
                            f"Node {node_id} returned None result in iteration {loop_count}"
                        )
                        # Store None result to track execution but don't propagate
                        iteration_results[node_id] = None
                    # CRITICAL FIX: Don't update state.node_outputs during iteration
                    # This was causing non-deterministic behavior because later nodes
                    # in the same iteration could see current iteration results
                    # instead of previous iteration results

                # Update results for this iteration - filter out None values for final results
                for node_id, node_result in iteration_results.items():
                    if node_result is not None:
                        results[node_id] = node_result

                # CRITICAL FIX: Update state.node_outputs AFTER the entire iteration
                # This ensures all nodes in the current iteration only see previous iteration results
                for node_id, node_result in iteration_results.items():
                    # Only update state with non-None results to avoid downstream issues
                    if node_result is not None:
                        state.node_outputs[node_id] = node_result

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

                # CRITICAL FIX: Check for natural termination based on cycle connection pattern
                # Different patterns:
                # 1. true_output → continue cycle when True, terminate when False
                # 2. false_output → continue cycle when False, terminate when True
                natural_termination_detected = False
                termination_reasons = []  # Collect all termination reasons

                for node_id in cycle_group.nodes:
                    if node_id in iteration_results:
                        node_result = iteration_results[node_id]
                        if (
                            isinstance(node_result, dict)
                            and "condition_result" in node_result
                        ):
                            condition_result = node_result.get("condition_result")

                            # Check what type of cycle connection this node has
                            node_has_true_output_cycle = False
                            node_has_false_output_cycle = False

                            for pred, succ, edge_data in cycle_group.edges:
                                if pred == node_id and edge_data.get("mapping"):
                                    mapping = edge_data["mapping"]
                                    if "true_output" in mapping:
                                        node_has_true_output_cycle = True
                                    if "false_output" in mapping:
                                        node_has_false_output_cycle = True

                            # Only check nodes that are actually part of cycle connections
                            if (
                                node_has_true_output_cycle
                                or node_has_false_output_cycle
                            ):
                                # Determine if cycle should terminate based on connection pattern
                                should_terminate_naturally = False
                                if node_has_true_output_cycle and not condition_result:
                                    # true_output cycle: terminate when condition becomes False
                                    should_terminate_naturally = True
                                    reason = f"{node_id} condition=False in true_output cycle"
                                    termination_reasons.append(reason)
                                elif node_has_false_output_cycle and condition_result:
                                    # false_output cycle: terminate when condition becomes True
                                    should_terminate_naturally = True
                                    reason = f"{node_id} condition=True in false_output cycle"
                                    termination_reasons.append(reason)

                                if should_terminate_naturally:
                                    natural_termination_detected = True
                                    should_terminate = True
                                    # DON'T break - check all SwitchNodes for comprehensive logging

                # Log all termination reasons if any found
                if natural_termination_detected:
                    combined_reason = "; ".join(termination_reasons)
                    logger.info(
                        f"Cycle {cycle_id} naturally terminating: {combined_reason}"
                    )

                if should_terminate:
                    termination_reason = (
                        "max_iterations"
                        if loop_count
                        >= cycle_config.get("max_iterations", float("inf"))
                        else (
                            "natural" if natural_termination_detected else "convergence"
                        )
                    )
                    logger.info(
                        f"Cycle {cycle_id} terminating after {loop_count} iterations"
                    )

                    # CRITICAL FIX: Ensure final cycle results are in state for downstream nodes
                    # This is essential for natural cycle termination where downstream nodes
                    # need access to the final iteration data
                    for node_id in cycle_group.exit_nodes:
                        if node_id in iteration_results:
                            final_result = iteration_results[node_id]
                            state.node_outputs[node_id] = final_result
                            logger.debug(
                                f"Updated state.node_outputs[{node_id}] with final iteration result for downstream nodes"
                            )

                    # CRITICAL: For exit nodes that are conditional (like SwitchNode),
                    # we need to ensure downstream nodes can access the appropriate outputs
                    # This handles both max iteration termination AND natural termination
                    logger.info(
                        f"Processing exit nodes: {cycle_group.exit_nodes}, natural_termination_detected: {natural_termination_detected}"
                    )
                    for exit_node_id in cycle_group.exit_nodes:
                        exit_node = workflow.get_node(exit_node_id)
                        if exit_node and exit_node.__class__.__name__ == "SwitchNode":
                            if exit_node_id in iteration_results:
                                exit_result = iteration_results[exit_node_id]

                                # Check if we terminated at max iterations with condition=true
                                # In this case, synthesize false_output for downstream nodes
                                max_iterations = cycle_config.get(
                                    "max_iterations", float("inf")
                                )
                                terminated_at_max = loop_count >= max_iterations

                                if (
                                    terminated_at_max
                                    and exit_result is not None
                                    and exit_result.get("condition_result", False)
                                    and exit_result.get("true_output")
                                ):
                                    # Find the actual last data from the cycle
                                    # Look for the node that feeds into this exit node
                                    last_cycle_data = None

                                    # Check which nodes feed into the exit node
                                    for pred in workflow.graph.predecessors(
                                        exit_node_id
                                    ):
                                        if (
                                            pred in cycle_group.nodes
                                            and pred in iteration_results
                                        ):
                                            pred_result = iteration_results[pred]
                                            if (
                                                isinstance(pred_result, dict)
                                                and "result" in pred_result
                                            ):
                                                last_cycle_data = pred_result["result"]
                                                logger.debug(
                                                    f"Using data from {pred} for false_output: {last_cycle_data}"
                                                )
                                                break

                                    # Synthesize a false_output with the actual last iteration's data
                                    exit_result["false_output"] = (
                                        last_cycle_data or exit_result["true_output"]
                                    )
                                    state.node_outputs[exit_node_id] = exit_result
                                    logger.debug(
                                        f"Synthesized false_output for {exit_node_id} on max iteration termination with data: {exit_result['false_output']}"
                                    )

                                # For natural termination (condition=false), the SwitchNode should already
                                # have the correct false_output set, so we just ensure it's in state
                                elif (
                                    not terminated_at_max
                                    and exit_result is not None
                                    and not exit_result.get("condition_result", True)
                                ):
                                    # Natural termination - condition became false
                                    # The SwitchNode should have correctly set false_output
                                    state.node_outputs[exit_node_id] = exit_result
                                    logger.debug(
                                        f"Natural termination: {exit_node_id} condition_result={exit_result.get('condition_result')}, false_output present={exit_result.get('false_output') is not None}"
                                    )

                                # CRITICAL FIX: For exit nodes that have downstream connections via false_output
                                # but the cycle terminated due to a different node, we need to synthesize termination data
                                elif (
                                    natural_termination_detected
                                    and exit_result is not None
                                ):
                                    logger.debug(
                                        f"Processing exit node {exit_node_id} for natural termination synthesis"
                                    )
                                    # Check if this exit node has downstream connections via false_output
                                    has_false_output_connections = False
                                    for succ in workflow.graph.successors(exit_node_id):
                                        if (
                                            succ not in cycle_group.nodes
                                        ):  # Downstream node outside cycle
                                            logger.debug(
                                                f"  Checking downstream node {succ}"
                                            )
                                            for edge_data in workflow.graph[
                                                exit_node_id
                                            ][succ].values():
                                                # Handle both dict and string edge_data formats
                                                if isinstance(edge_data, dict):
                                                    mapping = edge_data.get(
                                                        "mapping", {}
                                                    )
                                                else:
                                                    # Old format where edge_data might be a string
                                                    logger.debug(
                                                        f"    Legacy edge_data format: {edge_data} (type: {type(edge_data)})"
                                                    )
                                                    mapping = {}
                                                logger.debug(
                                                    f"    Edge mapping: {mapping}"
                                                )
                                                if "false_output" in mapping:
                                                    has_false_output_connections = True
                                                    logger.debug(
                                                        f"    Found false_output connection to {succ}"
                                                    )
                                                    break

                                    logger.debug(
                                        f"  Exit node {exit_node_id} has_false_output_connections: {has_false_output_connections}"
                                    )
                                    logger.debug(
                                        f"  Exit node {exit_node_id} current false_output: {exit_result.get('false_output')}"
                                    )

                                    # If this exit node has false_output connections but the cycle terminated naturally
                                    # due to another node, synthesize appropriate termination data
                                    if (
                                        has_false_output_connections
                                        and exit_result.get("false_output") is None
                                    ):
                                        # Use the current true_output data as termination data for false_output
                                        termination_data = exit_result.get(
                                            "true_output"
                                        )
                                        if termination_data is not None:
                                            exit_result["false_output"] = (
                                                termination_data
                                            )
                                            state.node_outputs[exit_node_id] = (
                                                exit_result
                                            )
                                            logger.info(
                                                f"Synthesized false_output for {exit_node_id} on natural termination: {termination_data}"
                                            )

                    break

                logger.info(f"Cycle {cycle_id} continuing to next iteration")

            # Get downstream nodes if cycle has terminated
            downstream_nodes = None
            if should_terminate:
                # Get nodes that depend on cycle output
                downstream_nodes = cycle_group.get_downstream_nodes(workflow)
                if downstream_nodes:
                    logger.info(
                        f"Cycle {cycle_id} has downstream nodes: {downstream_nodes}"
                    )

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

            return results, downstream_nodes

    def _execute_node(
        self,
        workflow: Workflow,
        node_id: str,
        state: WorkflowState,
        cycle_state: CycleState | None = None,
        cycle_edges: list[tuple] | None = None,
        previous_iteration_results: dict[str, Any] | None = None,
        current_iteration_results: (
            dict[str, Any] | None
        ) = None,  # CRITICAL FIX: Current iteration results
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

        # CRITICAL FIX: Process edges in priority order - non-cycle edges first, then cycle edges
        # This ensures cycle data overwrites non-cycle data when mapping to the same parameter
        all_edges = list(workflow.graph.in_edges(node_id, data=True))

        # Sort edges: non-cycle edges first, cycle edges second (for priority)
        non_cycle_edges = []
        cycle_edges = []

        for pred, _, edge_data in all_edges:
            # CRITICAL FIX: Synthetic edges are also cycle edges and should have priority
            is_cycle_edge = edge_data.get(
                "cycle", False
            )  # Include synthetic cycle edges
            if is_cycle_edge:
                cycle_edges.append((pred, _, edge_data))
            else:
                non_cycle_edges.append((pred, _, edge_data))

        # Process non-cycle edges first, then cycle edges (so cycle data has priority)
        for pred, _, edge_data in non_cycle_edges + cycle_edges:
            # Check if this edge is a cycle edge (but NOT synthetic)
            is_cycle_edge = edge_data.get("cycle", False) and not edge_data.get(
                "synthetic", False
            )

            # Determine where to get the predecessor output from
            if is_cycle_edge and is_cycle_iteration and previous_iteration_results:
                # For cycle edges after first iteration, use previous iteration results
                pred_output = previous_iteration_results.get(pred)
                logger.debug(
                    f"Cycle edge {pred} -> {node_id}: using previous iteration results"
                )
            elif current_iteration_results and pred in current_iteration_results:
                # For non-cycle edges, prefer current iteration results over stale state
                pred_output = current_iteration_results[pred]
                logger.debug(
                    f"Non-cycle edge {pred} -> {node_id}: using current iteration results"
                )
            elif pred in state.node_outputs:
                # For non-cycle edges or first iteration, use normal state as fallback
                pred_output = state.node_outputs[pred]
                logger.debug(
                    f"Non-cycle edge {pred} -> {node_id}: using state fallback"
                )
            else:
                # No output available
                logger.debug(f"No output available for {pred} -> {node_id}")
                continue

            if pred_output is None:
                continue

            # Apply mapping - with None safety check
            mapping = edge_data.get("mapping", {})
            pred_output_info = (
                "None"
                if pred_output is None
                else (
                    list(pred_output.keys())
                    if isinstance(pred_output, dict)
                    else type(pred_output)
                )
            )
            logger.debug(
                f"Edge {pred} -> {node_id}: mapping = {mapping}, pred_output keys = {pred_output_info}"
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

        # CONDITIONAL EXECUTION: Skip nodes that only receive None inputs from conditional routing
        if self._should_skip_conditional_node_cyclic(workflow, node_id, merged_inputs):
            logger.info(f"Skipping node {node_id} - all conditional inputs are None")
            # Store None result to indicate the node was skipped
            if task and task_manager:
                task_manager.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    result=None,
                    ended_at=datetime.now(UTC),
                    metadata={"skipped": True, "reason": "conditional_routing"},
                )
            return None

        # Execute node with metrics collection
        collector = MetricsCollector()
        logger.debug(
            f"Executing node: {node_id} (iteration: {cycle_state.iteration if cycle_state else 'N/A'})"
        )

        try:
            with collector.collect(node_id=node_id) as metrics_context:
                # Use enterprise node execution if runtime is available
                if state.runtime and hasattr(
                    state.runtime, "execute_node_with_enterprise_features_sync"
                ):
                    # Use sync enterprise wrapper for automatic feature integration
                    result = state.runtime.execute_node_with_enterprise_features_sync(
                        node, node_id, dict(context=context, **merged_inputs)
                    )
                else:
                    # Standard node execution (backward compatibility)
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

        # Identify nodes that depend on cycle exit nodes through specific outputs
        # that are only available when the cycle terminates (e.g., false_output of a cycle-controlling switch)
        nodes_depending_on_cycles = set()
        for cycle_id, cycle_group in self.cycle_groups.items():
            for exit_node in cycle_group.exit_nodes:
                exit_node_obj = workflow.get_node(exit_node)
                # Special handling for SwitchNodes that control cycles
                if exit_node_obj and exit_node_obj.__class__.__name__ == "SwitchNode":
                    # For switch nodes, check which output is used for the cycle
                    # and which would be used for exit
                    for source, target, edge_data in workflow.graph.out_edges(
                        exit_node, data=True
                    ):
                        if target not in cycle_group.nodes:
                            # This edge goes outside the cycle
                            mapping = edge_data.get("mapping", {})
                            # Check if this uses an output that indicates cycle termination
                            for src_port, _ in mapping.items():
                                if (
                                    "false" in src_port.lower()
                                    or "exit" in src_port.lower()
                                ):
                                    # This node depends on cycle termination
                                    nodes_depending_on_cycles.add(target)
                                    logger.debug(
                                        f"Node {target} depends on cycle {cycle_id} exit condition via {exit_node}.{src_port}"
                                    )
                else:
                    # For non-switch nodes, use the original logic
                    for successor in workflow.graph.successors(exit_node):
                        if successor not in cycle_group.nodes:
                            nodes_depending_on_cycles.add(successor)
                            logger.debug(
                                f"Node {successor} depends on cycle {cycle_id} exit node {exit_node}"
                            )

        logger.debug(
            f"Building stages - cycle_groups: {list(self.cycle_groups.keys())}"
        )
        logger.debug(f"Building stages - topo_order: {topo_order}")
        logger.debug(f"Nodes depending on cycles: {nodes_depending_on_cycles}")

        for node_id in topo_order:
            if node_id in scheduled:
                continue

            # Skip nodes that depend on cycle outputs - they'll be executed post-cycle
            if node_id in nodes_depending_on_cycles:
                logger.debug(f"Skipping {node_id} - depends on cycle output")
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

    def get_downstream_nodes(self, workflow: Workflow) -> set[str]:
        """Get all nodes that depend on this cycle's output.

        Args:
            workflow: The workflow containing this cycle

        Returns:
            Set of node IDs that are downstream from the cycle
        """
        downstream = set()
        for exit_node in self.exit_nodes:
            for successor in workflow.graph.successors(exit_node):
                if successor not in self.nodes:  # Not part of cycle
                    downstream.add(successor)
        return downstream

    def get_execution_order(self, full_graph: nx.DiGraph) -> list[str]:
        """Get execution order for nodes in cycle.

        Args:
            full_graph: Full workflow graph

        Returns:
            Ordered list of node IDs
        """
        # Create subgraph with only cycle nodes
        cycle_subgraph = full_graph.subgraph(self.nodes).copy()

        # Remove only non-synthetic cycle edges
        # Synthetic edges represent real dependencies and should be kept
        edges_to_remove = []
        for source, target, data in cycle_subgraph.edges(data=True):
            # Only remove edges that are cycle edges and NOT synthetic
            if data.get("cycle", False) and not data.get("synthetic", False):
                edges_to_remove.append((source, target))

        # Remove the identified edges
        for source, target in edges_to_remove:
            cycle_subgraph.remove_edge(source, target)

        # Try topological sort on the subgraph
        try:
            return list(nx.topological_sort(cycle_subgraph))
        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            # Fall back to entry nodes first, then others
            order = list(self.entry_nodes)
            for node in self.nodes:
                if node not in order:
                    order.append(node)
            return order

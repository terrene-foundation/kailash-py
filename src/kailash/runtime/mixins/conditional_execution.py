"""
Conditional execution mixin for runtime conditional workflow execution.

Provides shared conditional execution logic for LocalRuntime and AsyncLocalRuntime.
All methods are 100% shared (no sync/async variants).

EXTRACTION SOURCE: LocalRuntime (local.py lines 1896-3849)
SHARED LOGIC: 100% - All logic is pure computation, delegates I/O to runtime

Design Pattern:
    This mixin uses the template method pattern to provide shared orchestration
    logic while delegating I/O operations to runtime-specific implementations.

    Shared Logic (100%):
        - Pattern detection (has_conditional_patterns, workflow_has_cycles)
        - Hierarchical execution detection
        - Node skipping logic
        - Performance tracking
        - Error logging
        - Template orchestration (validation, planning, coordination)

    Runtime-Specific (Delegated):
        - Node execution (_execute_single_node)
        - Async workflow execution (_execute_async)
        - Input preparation (_prepare_node_inputs)

Dependencies:
    - BaseRuntime: Reads debug, logger, conditional_execution, enable_hierarchical_switch
    - ValidationMixin: Uses _validate_conditional_execution_prerequisites()
    - No mixin-to-mixin dependencies

Version:
    Added in: v0.10.0
    Part of: Runtime parity remediation (Phase 2)
"""

import logging
import time
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowValidationError
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


class ConditionalExecutionMixin:
    """
    Conditional execution capabilities for workflow runtimes.

    Provides 100% shared conditional execution logic for both LocalRuntime
    and AsyncLocalRuntime. Uses template method pattern to delegate I/O
    operations to runtime-specific implementations.

    Shared Logic (100%):
        - Pattern detection (has_conditional_patterns, workflow_has_cycles)
        - Hierarchical execution detection
        - Node skipping logic
        - Performance tracking
        - Error logging
        - Template orchestration (validation, planning, coordination)

    Runtime-Specific (Delegated):
        - Node execution (_execute_single_node)
        - Async workflow execution (_execute_async)
        - Input preparation (_prepare_node_inputs)

    Dependencies:
        - BaseRuntime: Reads debug, logger, conditional_execution, enable_hierarchical_switch
        - ValidationMixin: Uses _validate_conditional_execution_prerequisites()
        - No mixin-to-mixin dependencies

    Usage:
        class LocalRuntime(BaseRuntime, ConditionalExecutionMixin, ...):
            def _execute_async(self, workflow, inputs):
                # Sync implementation wrapped for async
                ...

            def _execute_single_node(self, node_id, workflow, node_inputs):
                # Execute node synchronously
                ...

    Examples:
        # Pattern detection
        if runtime._has_conditional_patterns(workflow):
            print("Workflow uses conditional execution")

        # Cycle detection
        if runtime._workflow_has_cycles(workflow):
            print("Workflow contains cycles")

        # Hierarchical execution check
        if runtime._should_use_hierarchical_execution(workflow, switch_node_ids):
            print("Use hierarchical switch execution")

        # Node skipping check
        if runtime._should_skip_conditional_node(node_id, workflow, results):
            print(f"Skip node {node_id}")

    See Also:
        - ValidationMixin: Prerequisite validation
        - ConditionalBranchAnalyzer: Pattern analysis
        - HierarchicalSwitchExecutor: Hierarchical execution

    Version:
        Added in: v0.10.0
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize conditional execution mixin.

        IMPORTANT: Calls super().__init__() for MRO chain.
        Follows SecureGovernedNode pattern for mixin initialization.
        """
        super().__init__(*args, **kwargs)
        # Stateless - no attributes created

    # ========================================================================
    # Pattern Detection Methods
    # ========================================================================

    def _has_conditional_patterns(self, workflow: Workflow) -> bool:
        """
        Check if workflow has conditional patterns (SwitchNodes) and is suitable for conditional execution.

        CRITICAL: Only enable conditional execution for DAG workflows.
        Cyclic workflows must use normal execution to preserve cycle safety mechanisms.

        EXTRACTED FROM: LocalRuntime._has_conditional_patterns() (lines 2693-2736)
        SHARED LOGIC: 100% - Pure pattern detection, no I/O

        Args:
            workflow: Workflow to analyze

        Returns:
            True if workflow contains SwitchNode instances AND is a DAG (no cycles)

        Examples:
            if runtime._has_conditional_patterns(workflow):
                print("Workflow uses conditional execution")

        Raises:
            None - Errors are logged and False is returned for safety
        """
        try:
            # Handle None workflow gracefully
            if workflow is None:
                return False

            if not hasattr(workflow, "graph") or workflow.graph is None:
                return False

            # CRITICAL: Check for cycles first - conditional execution is only safe for DAGs
            if self._workflow_has_cycles(workflow):
                self.logger.info(
                    "Cyclic workflow detected - using normal execution to preserve cycle safety mechanisms"
                )
                return False

            # Import here to avoid circular dependencies
            from kailash.analysis import ConditionalBranchAnalyzer

            analyzer = ConditionalBranchAnalyzer(workflow)
            switch_nodes = analyzer._find_switch_nodes()

            has_switches = len(switch_nodes) > 0

            if has_switches:
                self.logger.debug(
                    f"Found {len(switch_nodes)} SwitchNodes in DAG workflow - eligible for conditional execution"
                )
            else:
                self.logger.debug("No SwitchNodes found - using normal execution")

            return has_switches

        except Exception as e:
            self.logger.warning(f"Error checking conditional patterns: {e}")
            return False

    def _workflow_has_cycles(self, workflow: Workflow) -> bool:
        """
        Detect if workflow has cycles using multiple detection methods.

        EXTRACTED FROM: LocalRuntime._workflow_has_cycles() (lines 2738-2783)
        SHARED LOGIC: 100% - Pure cycle detection, no I/O

        Args:
            workflow: Workflow to check

        Returns:
            True if workflow contains any cycles

        Examples:
            if runtime._workflow_has_cycles(workflow):
                print("Workflow contains cycles")

        Raises:
            None - Errors are logged and True is returned for safety
        """
        try:
            # Method 1: Check for explicitly marked cycle connections
            if hasattr(workflow, "has_cycles") and callable(workflow.has_cycles):
                if workflow.has_cycles():
                    self.logger.debug("Detected cycles via workflow.has_cycles()")
                    return True

            # Method 2: Check for cycle edges in connections
            if hasattr(workflow, "connections"):
                for connection in workflow.connections:
                    if hasattr(connection, "cycle") and connection.cycle:
                        self.logger.debug("Detected cycle via connection.cycle flag")
                        return True

            # Method 3: NetworkX graph cycle detection
            if hasattr(workflow, "graph") and workflow.graph is not None:
                import networkx as nx

                is_dag = nx.is_directed_acyclic_graph(workflow.graph)
                if not is_dag:
                    self.logger.debug("Detected cycles via NetworkX graph analysis")
                    return True

            # Method 4: Check graph edges for cycle metadata
            if hasattr(workflow, "graph") and workflow.graph is not None:
                for u, v, edge_data in workflow.graph.edges(data=True):
                    if edge_data.get("cycle", False):
                        self.logger.debug("Detected cycle via edge metadata")
                        return True

            return False

        except Exception as e:
            self.logger.warning(f"Error detecting cycles: {e}")
            # On error, assume cycles exist for safety
            return True

    def _should_use_hierarchical_execution(
        self, workflow: Workflow, switch_node_ids: List[str]
    ) -> bool:
        """
        Determine if hierarchical switch execution should be used.

        EXTRACTED FROM: LocalRuntime._should_use_hierarchical_execution() (lines 3527-3565)
        SHARED LOGIC: 100% - Pure analysis, no I/O

        Args:
            workflow: The workflow to analyze
            switch_node_ids: List of switch node IDs

        Returns:
            True if hierarchical execution would be beneficial

        Examples:
            if runtime._should_use_hierarchical_execution(workflow, switch_node_ids):
                print("Use hierarchical switch execution")

        Raises:
            None - Errors are logged and False is returned
        """
        try:
            # Use hierarchical execution if:
            # 1. There are multiple switches
            if len(switch_node_ids) < 2:
                return False

            # 2. Check if switches have dependencies on each other
            from kailash.analysis import ConditionalBranchAnalyzer

            analyzer = ConditionalBranchAnalyzer(workflow)
            hierarchy_info = analyzer.analyze_switch_hierarchies(switch_node_ids)

            # Use hierarchical if there are multiple execution layers
            execution_layers = hierarchy_info.get("execution_layers", [])
            if len(execution_layers) > 1:
                self.logger.debug(
                    f"Detected {len(execution_layers)} execution layers in switch hierarchy"
                )
                return True

            # Use hierarchical if there are dependency chains
            dependency_chains = hierarchy_info.get("dependency_chains", [])
            if dependency_chains and any(len(chain) > 1 for chain in dependency_chains):
                self.logger.debug("Detected dependency chains in switch hierarchy")
                return True

            return False

        except Exception as e:
            self.logger.warning(f"Error analyzing hierarchical execution: {e}")
            return False

    # ========================================================================
    # Node Skipping Logic
    # ========================================================================

    def _should_skip_conditional_node(
        self,
        workflow: Workflow,
        node_id: str,
        inputs: Dict[str, Any],
        current_results: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Determine if a node should be skipped due to conditional routing.

        This is the CANONICAL implementation shared by LocalRuntime and AsyncLocalRuntime.
        Replaces the previous LocalRuntime override with a unified mixin version.

        A node should be skipped if:
        1. It has incoming connections from conditional nodes (like SwitchNode)
        2. All of its connected inputs are None from conditional routing
        3. It has no node-level configuration parameters that would make it run independently

        REFACTORED FROM: LocalRuntime._should_skip_conditional_node() (lines 1870-1995)
        SHARED LOGIC: 100% - Complete logic with edge case handling
        VERSION: v0.10.0 Phase 2 completion (2025-10-27)

        Args:
            workflow: The workflow being executed
            node_id: Node ID to check
            inputs: Prepared inputs for the node (after parameter mapping)
            current_results: Current execution results for transitive dependency checking
                           (optional, can be None if not available)

        Returns:
            True if the node should be skipped, False otherwise

        Examples:
            # LocalRuntime usage
            if self._should_skip_conditional_node(workflow, node_id, inputs, self._current_results):
                results[node_id] = None
                continue

            # AsyncLocalRuntime usage
            if self._should_skip_conditional_node(workflow, node_id, inputs, tracker.results):
                await tracker.record_result(node_id, None, 0.0)
                return

        Raises:
            None - Method is defensive and returns False on any error
        """
        try:
            # Get all incoming edges for this node
            if not hasattr(workflow, "graph") or workflow.graph is None:
                return False

            incoming_edges = list(workflow.graph.in_edges(node_id, data=True))

            # If the node has no incoming connections, don't skip it
            # (it might be a source node or have configuration parameters)
            if not incoming_edges:
                return False

            # Check for conditional inputs and analyze the nature of the data
            has_conditional_inputs = False
            has_non_none_connected_input = False

            for source_node_id, _, edge_data in incoming_edges:
                source_node = workflow._node_instances.get(source_node_id)
                mapping = edge_data.get("mapping", {})

                # Check if this edge provides any non-None inputs
                for source_key, target_key in mapping.items():
                    if target_key in inputs and inputs[target_key] is not None:
                        has_non_none_connected_input = True

                # Direct connection from SwitchNode
                if source_node and source_node.__class__.__name__ in ["SwitchNode"]:
                    has_conditional_inputs = True
                # Transitive dependency: source node was skipped due to conditional routing
                elif current_results and source_node_id in current_results:
                    if current_results[source_node_id] is None:
                        has_conditional_inputs = True

            # If no conditional inputs, don't skip
            if not has_conditional_inputs:
                return False

            # If we have conditional inputs but also have non-None data, don't skip
            # This handles mixed scenarios where some inputs are skipped but others provide data
            if has_non_none_connected_input:
                return False

            # Get the node instance to check for configuration parameters
            node_instance = workflow._node_instances.get(node_id)
            if not node_instance:
                return False

            # Check if the node has configuration parameters that would make it run independently
            # (excluding standard parameters and None values)
            node_config = getattr(node_instance, "config", {})
            significant_config = {
                k: v
                for k, v in node_config.items()
                if k not in ["metadata", "name", "id"] and v is not None
            }

            # If the node has significant configuration, it might still be valuable to run
            if significant_config:
                # Check if any connected inputs have actual data (not None)
                connected_inputs = {}
                for _, _, edge_data in incoming_edges:
                    mapping = edge_data.get("mapping", {})
                    for source_key, target_key in mapping.items():
                        if target_key in inputs:
                            connected_inputs[target_key] = inputs[target_key]

                # If all connected inputs are None but node has config, still skip
                # The user can configure the node to run with default values if needed
                if connected_inputs and all(
                    v is None for v in connected_inputs.values()
                ):
                    return True

            # Check if all connected inputs are None
            # This is the main condition for conditional routing
            has_non_none_input = False

            # Count total connected inputs and None inputs from conditional sources
            total_connected_inputs = 0
            none_conditional_inputs = 0

            for source_node_id, _, edge_data in incoming_edges:
                mapping = edge_data.get("mapping", {})
                for source_key, target_key in mapping.items():
                    if target_key in inputs:
                        total_connected_inputs += 1
                        if inputs[target_key] is not None:
                            has_non_none_input = True
                        else:
                            # Check if this None input came from conditional routing
                            source_node = workflow._node_instances.get(source_node_id)
                            is_from_conditional = (
                                source_node
                                and source_node.__class__.__name__ in ["SwitchNode"]
                            ) or (
                                current_results
                                and source_node_id in current_results
                                and current_results[source_node_id] is None
                            )
                            if is_from_conditional:
                                none_conditional_inputs += 1

            # Skip the node only if ALL connected inputs are None AND from conditional routing
            # This means nodes with mixed inputs (some None from conditional, some real data) should still execute
            if (
                total_connected_inputs > 0
                and none_conditional_inputs == total_connected_inputs
            ):
                return True

            return False

        except Exception as e:
            # Defensive: on any error, execute the node for safety
            if hasattr(self, "logger"):
                self.logger.warning(
                    f"Error checking if node {node_id} should be skipped: {e}"
                )
            return False

    # ========================================================================
    # Performance Tracking and Logging
    # ========================================================================

    def _track_conditional_execution_performance(
        self, workflow: Workflow, results: Dict[str, Any], duration: float
    ) -> None:
        """
        Track performance metrics for conditional execution.

        EXTRACTED FROM: LocalRuntime._track_conditional_execution_performance() (lines 3732-3768)
        SHARED LOGIC: 100% - Pure metric calculation and logging

        Args:
            workflow: Executed workflow
            results: Execution results (can be None)
            duration: Execution duration in seconds

        Examples:
            runtime._track_conditional_execution_performance(workflow, results, 1.5)

        Raises:
            None - Errors are logged and swallowed
        """
        try:
            # Skip if monitoring is disabled
            if hasattr(self, "enable_monitoring") and not self.enable_monitoring:
                return

            # Handle None workflow or results gracefully
            if workflow is None:
                return

            if not hasattr(workflow, "graph") or workflow.graph is None:
                return

            total_nodes = len(workflow.graph.nodes)
            # Handle None results gracefully
            executed_nodes = len(results) if results is not None else 0
            skipped_nodes = total_nodes - executed_nodes

            # Log performance metrics
            if skipped_nodes > 0:
                performance_improvement = (skipped_nodes / total_nodes) * 100
                self.logger.info(
                    f"Conditional execution performance: {performance_improvement:.1f}% reduction in executed nodes ({skipped_nodes}/{total_nodes} skipped)"
                )

            # Track for monitoring (could be sent to metrics system)
            if hasattr(self, "_record_execution_metrics"):
                metrics = {
                    "execution_mode": "conditional",
                    "total_nodes": total_nodes,
                    "executed_nodes": executed_nodes,
                    "skipped_nodes": skipped_nodes,
                    "performance_improvement_percent": (
                        (skipped_nodes / total_nodes) * 100 if total_nodes > 0 else 0
                    ),
                    "duration": duration,
                }
                self._record_execution_metrics(metrics)

        except Exception as e:
            self.logger.warning(
                f"Error tracking conditional execution performance: {e}"
            )

    def _log_conditional_execution_failure(
        self, workflow: Workflow, error: Exception, context: Dict[str, Any]
    ) -> None:
        """
        Log detailed information about conditional execution failure.

        EXTRACTED FROM: LocalRuntime._log_conditional_execution_failure() (lines 3770-3803)
        SHARED LOGIC: 100% - Pure logging, no I/O

        Args:
            workflow: Workflow that failed
            error: Exception that caused the failure
            context: Execution context (nodes_completed, total_nodes, etc.)

        Examples:
            context = {"nodes_completed": 2, "total_nodes": 4}
            runtime._log_conditional_execution_failure(workflow, error, context)

        Raises:
            None - Errors are logged and swallowed
        """
        try:
            total_nodes = len(workflow.graph.nodes) if hasattr(workflow, "graph") else 0
            nodes_completed = context.get("nodes_completed", 0)

            self.logger.error(
                f"Conditional execution failed after {nodes_completed}/{total_nodes} nodes"
            )
            self.logger.error(f"Error type: {type(error).__name__}")
            self.logger.error(f"Error message: {str(error)}")

            # Log workflow characteristics for debugging
            from kailash.analysis import ConditionalBranchAnalyzer

            analyzer = ConditionalBranchAnalyzer(workflow)
            switch_nodes = analyzer._find_switch_nodes()

            self.logger.debug(
                f"Workflow characteristics: {len(switch_nodes)} switches, {total_nodes} total nodes"
            )

            # Log additional context
            if context:
                self.logger.debug(f"Execution context: {context}")

        except Exception as log_error:
            self.logger.warning(
                f"Error logging conditional execution failure: {log_error}"
            )

    def _track_fallback_usage(self, workflow: Workflow, reason: str) -> None:
        """
        Track fallback to standard execution.

        EXTRACTED FROM: LocalRuntime._track_fallback_usage() (lines 3805-3849)
        SHARED LOGIC: 100% - Pure tracking and logging

        Args:
            workflow: Workflow using fallback
            reason: Reason for fallback

        Examples:
            runtime._track_fallback_usage(workflow, "Prerequisites validation failed")

        Raises:
            None - Errors are logged and swallowed
        """
        try:
            # Log fallback usage
            self.logger.info(f"Fallback used for workflow '{workflow.name}': {reason}")

            # Track for monitoring (could be sent to metrics system)
            if hasattr(self, "_record_execution_metrics"):
                metrics = {
                    "execution_mode": "fallback",
                    "workflow_name": workflow.name,
                    "workflow_id": workflow.workflow_id,
                    "fallback_reason": reason,
                    "timestamp": time.time(),
                }
                self._record_execution_metrics(metrics)

        except Exception as e:
            self.logger.warning(f"Error tracking fallback usage: {e}")

    # ========================================================================
    # Template Methods (Orchestration with Runtime-Specific Delegation)
    # ========================================================================

    async def _execute_conditional_approach(
        self, workflow: Workflow, inputs: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Execute workflow using conditional approach with two-phase execution (template method).

        Phase 1: Execute SwitchNodes to determine branches
        Phase 2: Execute only reachable nodes based on switch results

        This template method provides shared orchestration logic and delegates
        I/O operations to runtime-specific methods (_execute_async, _execute_single_node).

        EXTRACTED FROM: LocalRuntime._execute_conditional_approach() (lines 2785-2933)
        SHARED LOGIC: Orchestration, validation, planning, coordination
        RUNTIME-SPECIFIC: Node execution (delegated to _execute_single_node)

        Args:
            workflow: Workflow to execute
            inputs: Workflow inputs
            **kwargs: Additional execution parameters (task_manager, run_id, workflow_context)

        Returns:
            Dictionary mapping node_id -> execution results

        Examples:
            results = await runtime._execute_conditional_approach(workflow, {"initial_data": "test"})

        Raises:
            ValueError: If prerequisites validation fails
            RuntimeExecutionError: If execution fails and fallback also fails
        """
        self.logger.info("Starting conditional execution approach")
        results = {}
        fallback_reason = None
        start_time = time.time()

        try:
            # Validate prerequisites using ValidationMixin
            if hasattr(self, "_validate_conditional_execution_prerequisites"):
                if not self._validate_conditional_execution_prerequisites(workflow):
                    fallback_reason = "Prerequisites validation failed"
                    raise WorkflowValidationError(
                        f"Conditional execution prerequisites not met: {fallback_reason}"
                    )

            # Phase 1: Execute SwitchNodes to determine conditional branches
            self.logger.info("Phase 1: Executing SwitchNodes")
            phase1_results = await self._execute_switch_nodes(
                workflow, inputs, **kwargs
            )

            # Extract switch results for validation and planning
            from kailash.analysis import ConditionalBranchAnalyzer

            analyzer = ConditionalBranchAnalyzer(workflow)
            switch_node_ids = analyzer._find_switch_nodes()
            switch_results = {
                node_id: phase1_results[node_id]
                for node_id in switch_node_ids
                if node_id in phase1_results
            }

            # Validate switch results before proceeding
            if hasattr(self, "_validate_switch_results"):
                if not self._validate_switch_results(switch_results):
                    fallback_reason = "Invalid switch results detected"
                    raise WorkflowValidationError(
                        f"Switch results validation failed: {fallback_reason}"
                    )

            # Add all phase 1 results to overall results
            results.update(phase1_results)

            # Phase 2: Create pruned execution plan and execute remaining nodes
            self.logger.info("Phase 2: Creating and executing pruned plan")

            # Create execution plan based on switch results
            from kailash.planning import DynamicExecutionPlanner

            planner = DynamicExecutionPlanner(workflow)
            execution_plan = planner.create_execution_plan(switch_results)

            # Execute pruned plan
            remaining_results = await self._execute_pruned_plan(
                workflow, execution_plan, inputs, **kwargs
            )

            # Merge remaining results
            results.update(remaining_results)

            # Final validation of conditional execution results
            if hasattr(self, "_validate_conditional_execution_results"):
                if not self._validate_conditional_execution_results(results, workflow):
                    fallback_reason = "Results validation failed"
                    raise WorkflowValidationError(
                        f"Conditional execution results invalid: {fallback_reason}"
                    )

            # Performance tracking
            duration = time.time() - start_time
            self._track_conditional_execution_performance(workflow, results, duration)

            self.logger.info(
                f"Conditional execution completed successfully: {len(results)} nodes executed"
            )
            return results

        except Exception as e:
            # Enhanced error logging with fallback reasoning
            self.logger.error(f"Error in conditional execution approach: {e}")
            if fallback_reason:
                self.logger.warning(f"Fallback reason: {fallback_reason}")

            # Log performance impact before fallback
            context = {
                "nodes_completed": len(results),
                "total_nodes": (
                    len(workflow.graph.nodes) if hasattr(workflow, "graph") else 0
                ),
            }
            self._log_conditional_execution_failure(workflow, e, context)

            # Enhanced fallback with detailed logging
            self.logger.warning(
                "Falling back to normal execution approach due to conditional execution failure"
            )

            try:
                # Execute fallback with additional monitoring
                fallback_results = await self._execute_async(workflow, inputs)

                # Track fallback usage for monitoring
                self._track_fallback_usage(workflow, fallback_reason or str(e))

                return fallback_results

            except Exception as fallback_error:
                self.logger.error(f"Fallback execution also failed: {fallback_error}")
                # If both conditional and fallback fail, re-raise the original error
                raise e from fallback_error

    async def _execute_switch_nodes(
        self, workflow: Workflow, inputs: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Execute SwitchNodes first to determine conditional branches (template method).

        This template method executes all SwitchNodes and their dependencies to
        determine which branches should be taken in the workflow.

        EXTRACTED FROM: LocalRuntime._execute_switch_nodes() (lines 2935-3131)
        SHARED LOGIC: Orchestration, dependency analysis, execution planning
        RUNTIME-SPECIFIC: Node execution (delegated to _execute_single_node)

        Args:
            workflow: Workflow being executed
            inputs: Workflow inputs
            **kwargs: Additional execution parameters

        Returns:
            Dictionary mapping node_id -> execution results (includes switches and dependencies)

        Examples:
            results = await runtime._execute_switch_nodes(workflow, {})

        Raises:
            None - Errors are logged and execution continues with other nodes
        """
        self.logger.info("Phase 1: Executing SwitchNodes and their dependencies")
        all_phase1_results = {}  # Store ALL results from Phase 1, not just switches

        try:
            # Import here to avoid circular dependencies
            from kailash.analysis import ConditionalBranchAnalyzer

            # Check if we should use hierarchical switch execution
            analyzer = ConditionalBranchAnalyzer(workflow)
            switch_node_ids = analyzer._find_switch_nodes()

            if not switch_node_ids:
                self.logger.info("No SwitchNodes found in workflow")
                return all_phase1_results

            # Check for hierarchical execution
            if switch_node_ids and self._should_use_hierarchical_execution(
                workflow, switch_node_ids
            ):
                # Use hierarchical switch executor for complex switch patterns
                self.logger.info(
                    "Using hierarchical switch execution for optimized performance"
                )
                from kailash.runtime.hierarchical_switch_executor import (
                    HierarchicalSwitchExecutor,
                )

                executor = HierarchicalSwitchExecutor(workflow, debug=self.debug)

                # Define node executor function (delegates to runtime-specific method)
                async def node_executor(
                    node_id,
                    node_instance,
                    all_results,
                    parameters,
                    *args,
                    **executor_kwargs,
                ):
                    node_inputs = self._prepare_node_inputs(
                        workflow=workflow,
                        node_id=node_id,
                        node_instance=node_instance,
                        node_outputs=all_results,
                        parameters=parameters,
                    )

                    result = await self._execute_single_node(
                        node_id=node_id,
                        node_instance=node_instance,
                        node_inputs=node_inputs,
                        **executor_kwargs,
                    )
                    return result

                # Execute switches hierarchically
                all_results, switch_results = (
                    await executor.execute_switches_hierarchically(
                        parameters=inputs, node_executor=node_executor, **kwargs
                    )
                )

                # Log execution summary
                if self.debug:
                    summary = executor.get_execution_summary(switch_results)
                    self.logger.debug(f"Hierarchical execution summary: {summary}")

                return all_results

            # Otherwise, use standard execution
            self.logger.info("Using standard switch execution")

            # Get topological order for all nodes
            import networkx as nx

            all_nodes_order = list(nx.topological_sort(workflow.graph))

            # Find all nodes that switches depend on (need to execute these too)
            nodes_to_execute = set(switch_node_ids)
            for switch_id in switch_node_ids:
                # Get all predecessors (direct and indirect) of this switch
                predecessors = nx.ancestors(workflow.graph, switch_id)
                nodes_to_execute.update(predecessors)

            # Execute nodes in topological order, but only those needed for switches
            execution_order = [
                node_id for node_id in all_nodes_order if node_id in nodes_to_execute
            ]

            self.logger.info(
                f"Executing {len(execution_order)} nodes in Phase 1 (switches and their dependencies)"
            )
            self.logger.debug(f"Phase 1 execution order: {execution_order}")

            # Execute all nodes needed for switches in dependency order
            for node_id in execution_order:
                try:
                    # Get node instance
                    node_data = workflow.graph.nodes[node_id]
                    # Try both 'node' and 'instance' keys for compatibility
                    node_instance = node_data.get("node") or node_data.get("instance")

                    if node_instance is None:
                        self.logger.warning(f"No instance found for node {node_id}")
                        continue

                    # Prepare inputs for the node (delegates to runtime-specific method)
                    node_inputs = self._prepare_node_inputs(
                        workflow=workflow,
                        node_id=node_id,
                        node_instance=node_instance,
                        node_outputs=all_phase1_results,  # Use all results so far
                        parameters=inputs,
                    )

                    # Execute the node (delegates to runtime-specific method)
                    self.logger.debug(f"Executing node: {node_id}")
                    result = await self._execute_single_node(
                        node_id=node_id,
                        workflow=workflow,
                        node_inputs=node_inputs,
                    )

                    all_phase1_results[node_id] = result
                    self.logger.debug(
                        f"Node {node_id} completed with result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}"
                    )

                except Exception as e:
                    self.logger.error(f"Error executing node {node_id}: {e}")
                    # Continue with other nodes
                    all_phase1_results[node_id] = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "failed": True,
                    }

            self.logger.info(
                f"Phase 1 completed: {len(all_phase1_results)} nodes executed"
            )
            return all_phase1_results  # Return ALL results, not just switches

        except Exception as e:
            self.logger.error(f"Error in switch execution phase: {e}")
            return all_phase1_results

    async def _execute_pruned_plan(
        self,
        workflow: Workflow,
        execution_plan: List[str],
        inputs: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute pruned execution plan based on SwitchNode results (template method).

        This template method executes only the nodes that are reachable based on
        the SwitchNode results, skipping unreachable branches.

        EXTRACTED FROM: LocalRuntime._execute_pruned_plan() (lines 3133-3282)
        SHARED LOGIC: Orchestration, plan execution, error handling
        RUNTIME-SPECIFIC: Node execution (delegated to _execute_single_node)

        Args:
            workflow: Workflow being executed
            execution_plan: Pruned execution plan (list of node IDs to execute)
            inputs: Workflow inputs
            **kwargs: Additional execution parameters

        Returns:
            Dictionary mapping node_id -> execution results for remaining nodes

        Examples:
            plan = ["input", "switch", "true_branch"]
            results = await runtime._execute_pruned_plan(workflow, plan, {})

        Raises:
            None - Errors are logged and execution continues with other nodes
        """
        self.logger.info("Phase 2: Executing pruned plan based on switch results")
        remaining_results = {}

        try:
            if not execution_plan:
                self.logger.info("Empty execution plan - no nodes to execute")
                return remaining_results

            self.logger.info(f"Executing {len(execution_plan)} nodes in pruned plan")
            self.logger.debug(f"Execution plan: {execution_plan}")

            # Execute nodes in the pruned order
            for node_id in execution_plan:
                try:
                    # Get node instance
                    node_data = workflow.graph.nodes[node_id]
                    # Try both 'node' and 'instance' keys for compatibility
                    node_instance = node_data.get("node") or node_data.get("instance")

                    if node_instance is None:
                        self.logger.warning(f"No instance found for node {node_id}")
                        continue

                    # Prepare inputs using all results so far (delegates to runtime-specific method)
                    node_inputs = self._prepare_node_inputs(
                        workflow=workflow,
                        node_id=node_id,
                        node_instance=node_instance,
                        node_outputs=remaining_results,
                        parameters=inputs,
                    )

                    # Execute the node (delegates to runtime-specific method)
                    self.logger.debug(f"Executing node: {node_id}")
                    result = await self._execute_single_node(
                        node_id=node_id,
                        workflow=workflow,
                        node_inputs=node_inputs,
                    )

                    remaining_results[node_id] = result
                    self.logger.debug(f"Node {node_id} completed")

                except Exception as e:
                    self.logger.error(f"Error executing node {node_id}: {e}")
                    # Continue with other nodes or stop based on error handling
                    if hasattr(self, "_should_stop_on_error"):
                        if self._should_stop_on_error(e, node_id):
                            raise
                    # Store error result
                    remaining_results[node_id] = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "failed": True,
                    }

            self.logger.info(
                f"Phase 2 completed: {len(remaining_results)} nodes executed"
            )
            return remaining_results

        except Exception as e:
            self.logger.error(f"Error in pruned plan execution: {e}")
            return remaining_results

    # ========================================================================
    # Abstract Methods (Must be Implemented by Runtime)
    # ========================================================================

    @abstractmethod
    async def _execute_async(
        self, workflow: Workflow, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute workflow asynchronously (runtime-specific).

        This method must be implemented by the runtime to provide actual
        workflow execution. LocalRuntime wraps synchronous execution,
        AsyncLocalRuntime provides true async execution.

        Args:
            workflow: Workflow to execute
            inputs: Workflow inputs

        Returns:
            Execution results

        Raises:
            NotImplementedError: Must be implemented by runtime
        """
        pass

    @abstractmethod
    def _execute_single_node(
        self, node_id: str, workflow: Workflow, node_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute single node (runtime-specific).

        This method must be implemented by the runtime to provide actual
        node execution.

        Args:
            node_id: Node identifier
            workflow: Workflow containing the node
            node_inputs: Prepared inputs for the node

        Returns:
            Node execution results

        Raises:
            NotImplementedError: Must be implemented by runtime
        """
        pass

    @abstractmethod
    def _prepare_node_inputs(
        self,
        workflow: Workflow,
        node_id: str,
        node_instance: Any,
        node_outputs: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prepare node inputs (runtime-specific).

        This method must be implemented by the runtime to provide input
        preparation logic.

        Args:
            workflow: Workflow containing the node
            node_id: Node identifier
            node_instance: Node instance
            node_outputs: Previous node outputs
            parameters: Workflow parameters

        Returns:
            Prepared inputs for the node

        Raises:
            NotImplementedError: Must be implemented by runtime
        """
        pass

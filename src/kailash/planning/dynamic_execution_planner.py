"""
DynamicExecutionPlanner for creating optimized execution plans.

Creates execution plans based on runtime conditional results, pruning unreachable
branches to optimize workflow execution performance.
"""

import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from kailash.analysis.conditional_branch_analyzer import ConditionalBranchAnalyzer
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class DynamicExecutionPlanner:
    """
    Creates execution plans based on runtime conditional results.

    The planner analyzes SwitchNode results and creates optimized execution plans
    that skip unreachable branches entirely, improving performance.
    """

    def __init__(self, workflow: Workflow):
        """
        Initialize the DynamicExecutionPlanner.

        Args:
            workflow: The workflow to create execution plans for
        """
        self.workflow = workflow
        self.analyzer = ConditionalBranchAnalyzer(workflow)
        self._execution_plan_cache: Dict[str, List[str]] = {}
        self._dependency_cache: Optional[Dict[str, List[str]]] = None

    def create_execution_plan(
        self, switch_results: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """
        Create pruned execution plan based on SwitchNode results.

        Args:
            switch_results: Dictionary mapping switch_id -> {output_port -> result}
                           None results indicate the port was not activated

        Returns:
            List of node IDs in execution order, with unreachable branches pruned
        """
        # Handle None or invalid switch_results
        if switch_results is None:
            return self._get_all_nodes_topological_order()

        if not switch_results:
            # No switches or no switch results - return all nodes in topological order
            return self._get_all_nodes_topological_order()

        # Create cache key from switch results
        cache_key = self._create_cache_key(switch_results)
        if cache_key in self._execution_plan_cache:
            logger.debug("Using cached execution plan")
            return self._execution_plan_cache[cache_key]

        try:
            # Get all nodes in topological order
            all_nodes = self._get_all_nodes_topological_order()

            # Determine reachable nodes
            reachable_nodes = self.analyzer.get_reachable_nodes(switch_results)

            # Add nodes that are not dependent on any switches (always reachable)
            always_reachable = self._get_always_reachable_nodes(switch_results.keys())
            reachable_nodes.update(always_reachable)

            # Create pruned execution plan
            pruned_plan = self._prune_unreachable_branches(all_nodes, reachable_nodes)

            # Cache the result
            self._execution_plan_cache[cache_key] = pruned_plan

            logger.info(
                f"Created execution plan: {len(pruned_plan)}/{len(all_nodes)} nodes"
            )
            return pruned_plan

        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            # Fallback to all nodes
            return self._get_all_nodes_topological_order()

    def _analyze_dependencies(self) -> Dict[str, List[str]]:
        """
        Analyze dependencies for SwitchNode execution ordering.

        Returns:
            Dictionary mapping node_id -> list of dependency node_ids
        """
        if self._dependency_cache is not None:
            return self._dependency_cache

        dependencies = defaultdict(list)

        if not hasattr(self.workflow, "graph") or self.workflow.graph is None:
            return dict(dependencies)

        # Build dependency map from graph edges
        for source, target, edge_data in self.workflow.graph.edges(data=True):
            dependencies[target].append(source)

        # Ensure all nodes are in the dependency map
        for node_id in self.workflow.graph.nodes():
            if node_id not in dependencies:
                dependencies[node_id] = []

        self._dependency_cache = dict(dependencies)
        logger.debug(f"Analyzed dependencies for {len(dependencies)} nodes")
        return self._dependency_cache

    def _prune_unreachable_branches(
        self, all_nodes: List[str], reachable_nodes: Set[str]
    ) -> List[str]:
        """
        Prune unreachable branches from execution plan.

        Args:
            all_nodes: All nodes in topological order
            reachable_nodes: Set of nodes that are reachable

        Returns:
            Pruned list of nodes in execution order
        """
        pruned_plan = []

        for node_id in all_nodes:
            if node_id in reachable_nodes:
                pruned_plan.append(node_id)
            else:
                logger.debug(f"Pruning unreachable node: {node_id}")

        return pruned_plan

    def validate_execution_plan(
        self, execution_plan: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Validate execution plan for correctness.

        Args:
            execution_plan: List of node IDs in execution order

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not hasattr(self.workflow, "graph") or self.workflow.graph is None:
            errors.append("Workflow has no graph to validate against")
            return False, errors

        # Check all nodes exist in workflow
        workflow_nodes = set(self.workflow.graph.nodes())
        for node_id in execution_plan:
            if node_id not in workflow_nodes:
                errors.append(f"Node '{node_id}' not found in workflow")

        # Check dependencies are satisfied
        dependencies = self._analyze_dependencies()
        seen_nodes = set()

        for node_id in execution_plan:
            # Check if all dependencies have been seen
            for dep in dependencies.get(node_id, []):
                if dep not in seen_nodes:
                    if dep in execution_plan:
                        # Dependency is in plan but hasn't been seen yet - order issue
                        errors.append(
                            f"Node '{node_id}' dependency '{dep}' not satisfied"
                        )
                    else:
                        # Dependency is missing from execution plan entirely
                        errors.append(
                            f"Node '{node_id}' dependency '{dep}' missing from execution plan"
                        )

            seen_nodes.add(node_id)

        is_valid = len(errors) == 0
        if is_valid:
            logger.debug("Execution plan validation passed")
        else:
            logger.warning(f"Execution plan validation failed: {errors}")

        return is_valid, errors

    def _get_all_nodes_topological_order(self) -> List[str]:
        """Get all nodes in topological order."""
        if not hasattr(self.workflow, "graph") or self.workflow.graph is None:
            return []

        try:
            return list(nx.topological_sort(self.workflow.graph))
        except Exception as e:
            logger.error(f"Error getting topological order: {e}")
            # Fallback to node list
            return list(self.workflow.graph.nodes())

    def _get_always_reachable_nodes(self, switch_node_ids: Set[str]) -> Set[str]:
        """
        Get nodes that are always reachable (not dependent on any switches).

        Args:
            switch_node_ids: Set of switch node IDs

        Returns:
            Set of node IDs that are always reachable
        """
        always_reachable = set()

        if not hasattr(self.workflow, "graph") or self.workflow.graph is None:
            return always_reachable

        # Find nodes that don't depend on any switches
        for node_id in self.workflow.graph.nodes():
            if self._is_reachable_without_switches(node_id, switch_node_ids):
                always_reachable.add(node_id)

        logger.debug(f"Found {len(always_reachable)} always reachable nodes")
        return always_reachable

    def _is_reachable_without_switches(
        self, node_id: str, switch_node_ids: Set[str]
    ) -> bool:
        """
        Check if a node is reachable without going through any switches.

        Args:
            node_id: Node to check
            switch_node_ids: Set of switch node IDs

        Returns:
            True if node is reachable without switches
        """
        if node_id in switch_node_ids:
            return True  # Switches themselves are always reachable

        # BFS backwards to see if we can reach a source without going through switches
        visited = set()
        queue = deque([node_id])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue

            visited.add(current)

            # Get predecessors
            if hasattr(self.workflow.graph, "predecessors"):
                predecessors = list(self.workflow.graph.predecessors(current))

                if not predecessors:
                    # Found a source node - reachable without switches
                    return True

                for pred in predecessors:
                    if pred in switch_node_ids:
                        # Path goes through a switch - not always reachable
                        continue
                    queue.append(pred)

        return False

    def _create_cache_key(self, switch_results: Dict[str, Dict[str, Any]]) -> str:
        """Create cache key from switch results."""
        # Create a stable string representation of switch results
        key_parts = []
        for switch_id in sorted(switch_results.keys()):
            ports = switch_results[switch_id]
            port_parts = []

            # Handle None ports (invalid switch results)
            if ports is None:
                port_parts.append("None")
            elif isinstance(ports, dict):
                for port in sorted(ports.keys()):
                    result = ports[port]
                    # Create simple representation (None vs not-None)
                    result_repr = "None" if result is None else "active"
                    port_parts.append(f"{port}:{result_repr}")
            else:
                # Invalid port format, represent as string
                port_parts.append(f"invalid:{str(ports)}")

            key_parts.append(f"{switch_id}({','.join(port_parts)})")

        return "|".join(key_parts)

    def create_hierarchical_plan(self, workflow: Workflow) -> List[List[str]]:
        """
        Create execution plan with hierarchical switch dependencies.

        Execute SwitchNodes in dependency layers:
        - Phase 1: Independent SwitchNodes
        - Phase 2: Dependent SwitchNodes based on Phase 1 results
        - Phase 3: Final conditional branches

        Args:
            workflow: Workflow to analyze

        Returns:
            List of execution phases, each containing list of node IDs
        """
        switch_nodes = self.analyzer._find_switch_nodes()
        if not switch_nodes:
            # No switches - single phase with all nodes
            return [self._get_all_nodes_topological_order()]

        dependencies = self._analyze_dependencies()

        # Build switch dependency graph
        switch_deps = nx.DiGraph()
        switch_deps.add_nodes_from(switch_nodes)

        for switch_id in switch_nodes:
            for dep in dependencies.get(switch_id, []):
                if dep in switch_nodes:
                    switch_deps.add_edge(dep, switch_id)

        # Get switch execution layers
        try:
            layers = []
            remaining_switches = set(switch_nodes)

            while remaining_switches:
                # Find switches with no dependencies in remaining set
                current_layer = []
                for switch_id in remaining_switches:
                    deps = [
                        d
                        for d in switch_deps.predecessors(switch_id)
                        if d in remaining_switches
                    ]
                    if not deps:
                        current_layer.append(switch_id)

                if not current_layer:
                    # Circular dependency - add all remaining
                    current_layer = list(remaining_switches)

                layers.append(current_layer)
                remaining_switches -= set(current_layer)

            return layers

        except Exception as e:
            logger.error(f"Error creating hierarchical plan: {e}")
            # Fallback to single layer
            return [switch_nodes]

    def _handle_merge_with_conditional_inputs(
        self,
        merge_node: str,
        workflow: Workflow,
        switch_results: Dict[str, Dict[str, Any]],
    ) -> bool:
        """
        Handle merge node with conditional inputs.

        Args:
            merge_node: ID of the merge node
            workflow: Workflow containing the merge node
            switch_results: Switch results to determine available inputs

        Returns:
            True if merge node should be included in execution plan
        """
        if not hasattr(workflow, "graph") or workflow.graph is None:
            return True

        # Check how many inputs to the merge node are available
        available_inputs = 0

        for pred in workflow.graph.predecessors(merge_node):
            # Check if predecessor is reachable based on switch results
            reachable_nodes = self.analyzer.get_reachable_nodes(switch_results)
            if pred in reachable_nodes:
                available_inputs += 1

        # Merge nodes can typically handle partial inputs
        # Include if at least one input is available
        return available_inputs > 0

    def invalidate_cache(self):
        """Invalidate cached execution plans and dependencies."""
        self._execution_plan_cache.clear()
        self._dependency_cache = None
        # Also invalidate the analyzer's cache when workflow structure changes
        if hasattr(self.analyzer, "invalidate_cache"):
            self.analyzer.invalidate_cache()
        logger.debug("DynamicExecutionPlanner cache invalidated")

    # ===== PHASE 4: ADVANCED FEATURES =====

    def create_hierarchical_execution_plan(
        self, switch_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create advanced execution plan with hierarchical switch support and merge strategies.

        Args:
            switch_results: Results from SwitchNode execution

        Returns:
            Dictionary containing detailed execution plan with layers and strategies
        """
        plan = {
            "switch_layers": [],
            "execution_plan": [],
            "merge_strategies": {},
            "performance_metrics": {},
            "reachable_nodes": set(),
            "skipped_nodes": set(),
        }

        try:
            # Use analyzer's hierarchical capabilities
            if hasattr(self.analyzer, "create_hierarchical_execution_plan"):
                hierarchical_plan = self.analyzer.create_hierarchical_execution_plan(
                    switch_results
                )
                plan.update(hierarchical_plan)

            # Create traditional execution plan as fallback
            traditional_plan = self.create_execution_plan(switch_results)
            if not plan["execution_plan"]:
                plan["execution_plan"] = traditional_plan

            # Calculate performance metrics
            total_nodes = len(self.workflow.graph.nodes)
            executed_nodes = len(plan["execution_plan"])
            plan["performance_metrics"] = {
                "total_nodes": total_nodes,
                "executed_nodes": executed_nodes,
                "skipped_nodes": total_nodes - executed_nodes,
                "performance_improvement": (
                    (total_nodes - executed_nodes) / total_nodes
                    if total_nodes > 0
                    else 0
                ),
            }

            # Convert sets to lists for JSON serialization
            if isinstance(plan["reachable_nodes"], set):
                plan["reachable_nodes"] = list(plan["reachable_nodes"])
            if isinstance(plan["skipped_nodes"], set):
                plan["skipped_nodes"] = list(plan["skipped_nodes"])

        except Exception as e:
            logger.warning(f"Error creating hierarchical execution plan: {e}")
            # Fallback to basic execution plan
            plan["execution_plan"] = self.create_execution_plan(switch_results)

        return plan

    def handle_merge_nodes_with_conditional_inputs(
        self, execution_plan: List[str], switch_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze and handle MergeNodes that receive conditional inputs.

        Args:
            execution_plan: Current execution plan
            switch_results: Results from switch execution

        Returns:
            Dictionary with merge handling strategies
        """
        merge_handling = {
            "merge_nodes": [],
            "strategies": {},
            "execution_modifications": [],
            "warnings": [],
        }

        try:
            # Find merge nodes in the workflow
            if hasattr(self.analyzer, "_find_merge_nodes"):
                merge_nodes = self.analyzer._find_merge_nodes()
            else:
                merge_nodes = self._find_merge_nodes_fallback()

            reachable_nodes = set(execution_plan)

            for merge_id in merge_nodes:
                if merge_id in execution_plan:
                    strategy = self._create_merge_strategy(
                        merge_id, reachable_nodes, switch_results
                    )
                    merge_handling["strategies"][merge_id] = strategy
                    merge_handling["merge_nodes"].append(merge_id)

                    # Add execution modifications if needed
                    if strategy["strategy_type"] == "skip":
                        merge_handling["execution_modifications"].append(
                            {
                                "type": "skip_node",
                                "node_id": merge_id,
                                "reason": "No available inputs",
                            }
                        )
                    elif strategy["strategy_type"] == "partial":
                        merge_handling["execution_modifications"].append(
                            {
                                "type": "partial_merge",
                                "node_id": merge_id,
                                "available_inputs": strategy["available_inputs"],
                                "missing_inputs": strategy["missing_inputs"],
                            }
                        )

        except Exception as e:
            logger.warning(f"Error handling merge nodes: {e}")
            merge_handling["warnings"].append(f"Merge node analysis failed: {e}")

        return merge_handling

    def _find_merge_nodes_fallback(self) -> List[str]:
        """Fallback method to find merge nodes when analyzer doesn't have the method."""
        merge_nodes = []

        try:
            from kailash.nodes.logic.operations import MergeNode

            for node_id, node_data in self.workflow.graph.nodes(data=True):
                node_instance = node_data.get("node") or node_data.get("instance")
                if node_instance and isinstance(node_instance, MergeNode):
                    merge_nodes.append(node_id)

        except Exception as e:
            logger.warning(f"Error in merge node fallback detection: {e}")

        return merge_nodes

    def _create_merge_strategy(
        self,
        merge_id: str,
        reachable_nodes: Set[str],
        switch_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create merge strategy for a specific MergeNode.

        Args:
            merge_id: ID of the merge node
            reachable_nodes: Set of nodes that will be executed
            switch_results: Results from switch execution

        Returns:
            Dictionary describing merge strategy
        """
        strategy = {
            "merge_id": merge_id,
            "available_inputs": [],
            "missing_inputs": [],
            "strategy_type": "unknown",
            "confidence": 0.0,
            "recommendations": [],
        }

        try:
            # Get all predecessors of the merge node
            predecessors = list(self.workflow.graph.predecessors(merge_id))

            for pred in predecessors:
                if pred in reachable_nodes:
                    strategy["available_inputs"].append(pred)
                else:
                    strategy["missing_inputs"].append(pred)

            # Determine strategy type
            available_count = len(strategy["available_inputs"])
            total_count = len(predecessors)

            if available_count == 0:
                strategy["strategy_type"] = "skip"
                strategy["confidence"] = 1.0
                strategy["recommendations"].append(
                    "Skip merge node - no inputs available"
                )
            elif available_count == total_count:
                strategy["strategy_type"] = "full"
                strategy["confidence"] = 1.0
                strategy["recommendations"].append("Execute merge with all inputs")
            else:
                strategy["strategy_type"] = "partial"
                strategy["confidence"] = available_count / total_count
                strategy["recommendations"].append(
                    f"Execute merge with {available_count}/{total_count} inputs"
                )
                strategy["recommendations"].append(
                    "Consider merge node's skip_none parameter"
                )

        except Exception as e:
            logger.warning(f"Error creating merge strategy for {merge_id}: {e}")
            strategy["strategy_type"] = "error"
            strategy["recommendations"].append(f"Error analyzing merge: {e}")

        return strategy

    def optimize_execution_plan(
        self, execution_plan: List[str], switch_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Optimize execution plan with advanced performance techniques.

        Args:
            execution_plan: Basic execution plan
            switch_results: Results from switch execution

        Returns:
            Dictionary with optimized execution plan and performance data
        """
        optimization_result = {
            "original_plan": execution_plan.copy(),
            "optimized_plan": execution_plan.copy(),
            "optimizations_applied": [],
            "performance_improvement": 0.0,
            "analysis": {},
        }

        try:
            # Parallel execution opportunities
            parallel_groups = self._identify_parallel_execution_groups(execution_plan)
            if parallel_groups:
                optimization_result["optimizations_applied"].append(
                    "parallel_execution_grouping"
                )
                optimization_result["analysis"]["parallel_groups"] = parallel_groups

            # Merge node optimizations
            merge_handling = self.handle_merge_nodes_with_conditional_inputs(
                execution_plan, switch_results
            )
            if merge_handling["execution_modifications"]:
                optimization_result["optimizations_applied"].append(
                    "merge_node_optimization"
                )
                optimization_result["analysis"]["merge_optimizations"] = merge_handling

                # Apply merge optimizations to plan
                modified_plan = execution_plan.copy()
                for mod in merge_handling["execution_modifications"]:
                    if mod["type"] == "skip_node":
                        if mod["node_id"] in modified_plan:
                            modified_plan.remove(mod["node_id"])

                optimization_result["optimized_plan"] = modified_plan

            # Calculate performance improvement
            original_count = len(optimization_result["original_plan"])
            optimized_count = len(optimization_result["optimized_plan"])
            if original_count > 0:
                optimization_result["performance_improvement"] = (
                    original_count - optimized_count
                ) / original_count

        except Exception as e:
            logger.warning(f"Error optimizing execution plan: {e}")
            optimization_result["analysis"]["error"] = str(e)

        return optimization_result

    def _identify_parallel_execution_groups(
        self, execution_plan: List[str]
    ) -> List[List[str]]:
        """
        Identify groups of nodes that can be executed in parallel.

        Args:
            execution_plan: List of nodes in execution order

        Returns:
            List of parallel execution groups
        """
        parallel_groups = []

        try:
            # Build dependency graph for nodes in the execution plan
            plan_nodes = set(execution_plan)
            dependencies = {}

            for node_id in execution_plan:
                predecessors = list(self.workflow.graph.predecessors(node_id))
                # Only consider dependencies within the execution plan
                plan_predecessors = [
                    pred for pred in predecessors if pred in plan_nodes
                ]
                dependencies[node_id] = plan_predecessors

            # Group nodes by their dependency depth
            depth_groups = self._group_by_dependency_depth(execution_plan, dependencies)

            # Each depth level can potentially be executed in parallel
            for depth, nodes in depth_groups.items():
                if len(nodes) > 1:
                    parallel_groups.append(nodes)

        except Exception as e:
            logger.warning(f"Error identifying parallel execution groups: {e}")

        return parallel_groups

    def _group_by_dependency_depth(
        self, execution_plan: List[str], dependencies: Dict[str, List[str]]
    ) -> Dict[int, List[str]]:
        """
        Group nodes by their dependency depth for parallel execution analysis.

        Args:
            execution_plan: List of nodes in execution order
            dependencies: Dictionary mapping node_id -> list of dependencies

        Returns:
            Dictionary mapping depth -> list of nodes at that depth
        """
        depth_groups = defaultdict(list)
        node_depths = {}

        try:
            # Calculate depth for each node
            for node_id in execution_plan:
                depth = self._calculate_node_depth(node_id, dependencies, node_depths)
                depth_groups[depth].append(node_id)
                node_depths[node_id] = depth

        except Exception as e:
            logger.warning(f"Error grouping by dependency depth: {e}")

        return dict(depth_groups)

    def _calculate_node_depth(
        self,
        node_id: str,
        dependencies: Dict[str, List[str]],
        node_depths: Dict[str, int],
    ) -> int:
        """
        Calculate the dependency depth of a node.

        Args:
            node_id: ID of the node
            dependencies: Dictionary mapping node_id -> list of dependencies
            node_depths: Cache of already calculated depths

        Returns:
            Dependency depth of the node
        """
        if node_id in node_depths:
            return node_depths[node_id]

        node_deps = dependencies.get(node_id, [])
        if not node_deps:
            # No dependencies - depth 0
            return 0

        # Depth is 1 + max depth of dependencies
        max_dep_depth = 0
        for dep in node_deps:
            dep_depth = self._calculate_node_depth(dep, dependencies, node_depths)
            max_dep_depth = max(max_dep_depth, dep_depth)

        return max_dep_depth + 1

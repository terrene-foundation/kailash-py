"""
ConditionalBranchAnalyzer for analyzing workflow conditional patterns.

Analyzes workflow graphs to identify conditional execution patterns and determine
which nodes are reachable based on SwitchNode outputs.
"""

import logging
from typing import Any, Dict, List, Optional, Set

import networkx as nx
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class ConditionalBranchAnalyzer:
    """
    Analyzes workflow graph to identify conditional execution patterns.

    This analyzer examines workflows containing SwitchNode instances and maps
    out the conditional branches to determine which nodes are reachable based
    on runtime switch results.
    """

    def __init__(self, workflow: Workflow):
        """
        Initialize the ConditionalBranchAnalyzer.

        Args:
            workflow: The workflow to analyze for conditional patterns
        """
        self.workflow = workflow
        self._switch_nodes: Optional[List[str]] = None
        self._branch_map: Optional[Dict[str, Dict[str, Set[str]]]] = None

    def _find_switch_nodes(self) -> List[str]:
        """
        Find all SwitchNode instances in the workflow.

        Returns:
            List of node IDs that are SwitchNode instances
        """
        if self._switch_nodes is not None:
            return self._switch_nodes

        switch_nodes = []

        if not hasattr(self.workflow, "graph") or self.workflow.graph is None:
            logger.warning("Workflow has no graph to analyze")
            return switch_nodes

        for node_id in self.workflow.graph.nodes():
            try:
                node_data = self.workflow.graph.nodes[node_id]
                # Try both 'node' and 'instance' keys for compatibility
                node_instance = node_data.get("node") or node_data.get("instance")

                if isinstance(node_instance, SwitchNode):
                    switch_nodes.append(node_id)
                    logger.debug(f"Found SwitchNode: {node_id}")

            except (KeyError, AttributeError) as e:
                logger.debug(f"Skipping node {node_id} - no valid instance: {e}")
                continue

        self._switch_nodes = switch_nodes
        logger.info(f"Found {len(switch_nodes)} SwitchNode instances")
        return switch_nodes

    def _build_branch_map(self) -> Dict[str, Dict[str, Set[str]]]:
        """
        Build map of SwitchNode -> {output_port -> downstream_nodes}.

        Returns:
            Dictionary mapping switch node IDs to their output ports and
            the downstream nodes reachable from each port
        """
        if self._branch_map is not None:
            return self._branch_map

        branch_map = {}
        switch_nodes = self._find_switch_nodes()

        for switch_id in switch_nodes:
            branch_map[switch_id] = {}

            # Find all outgoing edges from this switch
            if hasattr(self.workflow.graph, "out_edges"):
                for source, target, edge_data in self.workflow.graph.out_edges(
                    switch_id, data=True
                ):
                    mapping = edge_data.get("mapping", {})

                    # Extract output ports from mapping
                    for source_port, target_port in mapping.items():
                        # Output ports typically start with output name (true_output, false_output, case_X)
                        if source_port not in branch_map[switch_id]:
                            branch_map[switch_id][source_port] = set()

                        branch_map[switch_id][source_port].add(target)
                        logger.debug(
                            f"Switch {switch_id} port {source_port} -> {target} (direct connection only)"
                        )

                        # Don't recursively add downstream nodes - that breaks nested conditionals
                        # The get_reachable_nodes method will traverse downstream from activated branches

        self._branch_map = branch_map
        logger.info(f"Built branch map for {len(branch_map)} switches")
        return branch_map

    def _find_downstream_nodes(
        self, start_node: str, exclude_switches: List[str]
    ) -> Set[str]:
        """
        Find all downstream nodes from a starting node, excluding switches.

        Args:
            start_node: Node to start traversal from
            exclude_switches: Switch nodes to stop traversal at

        Returns:
            Set of downstream node IDs
        """
        downstream = set()
        visited = set()
        stack = [start_node]

        while stack:
            current = stack.pop()
            if current in visited:
                continue

            visited.add(current)

            # Don't traverse past other switches (they create their own branches)
            if current in exclude_switches and current != start_node:
                continue

            downstream.add(current)

            # Add successors to stack
            if hasattr(self.workflow.graph, "successors"):
                for successor in self.workflow.graph.successors(current):
                    if successor not in visited:
                        stack.append(successor)

        # Remove the start node from downstream set
        downstream.discard(start_node)
        return downstream

    def get_reachable_nodes(
        self, switch_results: Dict[str, Dict[str, Any]]
    ) -> Set[str]:
        """
        Get reachable nodes based on SwitchNode results.

        Args:
            switch_results: Dictionary mapping switch_id -> {output_port -> result}
                           None results indicate the port was not activated

        Returns:
            Set of node IDs that are reachable based on switch results
        """
        reachable = set()
        branch_map = self._build_branch_map()

        # Always include switches that executed
        reachable.update(switch_results.keys())

        # Track nodes to process for downstream traversal
        to_process = set()

        # Process each switch result to find directly connected nodes
        logger.debug(f"Processing switch results: {switch_results}")
        for switch_id, port_results in switch_results.items():
            if switch_id not in branch_map:
                logger.warning(f"Switch {switch_id} not found in branch map")
                continue

            switch_branches = branch_map[switch_id]
            logger.debug(f"Branch map for {switch_id}: {switch_branches}")

            for port, result in port_results.items():
                if result is not None:  # This port was activated
                    if port in switch_branches:
                        direct_nodes = switch_branches[port]
                        reachable.update(direct_nodes)
                        to_process.update(direct_nodes)
                        logger.debug(
                            f"Switch {switch_id} port {port} activated - added direct nodes: {direct_nodes}"
                        )
                else:
                    logger.debug(f"Switch {switch_id} port {port} NOT activated (None)")

        # Now traverse the graph to find ALL downstream nodes from the activated branches
        # BUT: Don't traverse through switches - they control their own branches
        while to_process:
            current_node = to_process.pop()

            # Skip switches during downstream traversal - they've already been processed
            node_data = self.workflow.graph.nodes.get(current_node, {})
            node_instance = node_data.get("node") or node_data.get("instance")
            if isinstance(node_instance, SwitchNode):
                # Don't traverse through switches - only their explicitly activated branches
                # were added in the first loop
                logger.debug(
                    f"Skipping switch {current_node} during downstream traversal"
                )
                continue

            # Get all successors of the current node
            if hasattr(self.workflow.graph, "successors"):
                successors = list(self.workflow.graph.successors(current_node))
                for successor in successors:
                    if successor not in reachable:
                        reachable.add(successor)
                        to_process.add(successor)
                        logger.debug(
                            f"Added downstream node {successor} from {current_node}"
                        )

        logger.info(
            f"Determined {len(reachable)} reachable nodes from switch results (including downstream)"
        )
        return reachable

    def detect_conditional_patterns(self) -> Dict[str, Any]:
        """
        Detect complex conditional patterns in the workflow.

        Returns:
            Dictionary containing information about detected patterns
        """
        patterns = {}
        switch_nodes = self._find_switch_nodes()
        branch_map = self._build_branch_map()

        # Basic statistics
        patterns["total_switches"] = len(switch_nodes)
        patterns["has_cycles"] = self._detect_cycles()

        # Pattern classification
        if len(switch_nodes) == 1:
            patterns["single_switch"] = switch_nodes
        elif len(switch_nodes) > 1:
            patterns["multiple_switches"] = switch_nodes
            patterns["cascading_switches"] = self._detect_cascading_switches(
                switch_nodes
            )

        # Detect merge nodes
        merge_nodes = self._find_merge_nodes()
        if merge_nodes:
            patterns["merge_nodes"] = merge_nodes

        # Complex pattern detection
        if patterns["has_cycles"] and switch_nodes:
            patterns["cyclic_conditional"] = True

        if len(merge_nodes) > 1:
            patterns["complex_merge_patterns"] = True

        # Detect circular switch dependencies
        if self._detect_circular_switch_dependencies(switch_nodes):
            patterns["circular_switches"] = True

        # Multi-case switch detection
        multi_case_switches = self._detect_multi_case_switches(switch_nodes)
        if multi_case_switches:
            patterns["multi_case_switches"] = multi_case_switches

        logger.info(f"Detected conditional patterns: {patterns}")
        return patterns

    def _detect_cycles(self) -> bool:
        """Detect if the workflow has cycles."""
        try:
            # Prioritize NetworkX cycle detection (detects structural cycles)
            if hasattr(self.workflow.graph, "nodes"):
                # Use NetworkX to detect cycles in graph structure
                has_structural_cycles = not nx.is_directed_acyclic_graph(
                    self.workflow.graph
                )
                if has_structural_cycles:
                    return True

            # Also check for explicitly marked cycle connections
            if hasattr(self.workflow, "has_cycles"):
                return self.workflow.has_cycles()

            return False
        except Exception as e:
            logger.debug(f"Error detecting cycles: {e}")
            return False

    def _detect_cascading_switches(self, switch_nodes: List[str]) -> List[List[str]]:
        """Detect cascading switch patterns (switch -> switch -> ...)."""
        cascading = []

        for switch_id in switch_nodes:
            # Check if this switch leads to other switches
            if switch_id in self._branch_map:
                for port, downstream in self._branch_map[switch_id].items():
                    switch_chain = [switch_id]

                    # Find switches in downstream nodes
                    downstream_switches = [
                        node for node in downstream if node in switch_nodes
                    ]
                    if downstream_switches:
                        switch_chain.extend(downstream_switches)
                        if len(switch_chain) > 1:
                            cascading.append(switch_chain)

        return cascading

    def _find_merge_nodes(self) -> List[str]:
        """Find all MergeNode instances in the workflow."""
        merge_nodes = []

        if not hasattr(self.workflow, "graph") or self.workflow.graph is None:
            return merge_nodes

        for node_id in self.workflow.graph.nodes():
            try:
                node_data = self.workflow.graph.nodes[node_id]
                # Try both 'node' and 'instance' keys for compatibility
                node_instance = node_data.get("node") or node_data.get("instance")

                if isinstance(node_instance, MergeNode):
                    merge_nodes.append(node_id)

            except (KeyError, AttributeError):
                continue

        return merge_nodes

    def _detect_circular_switch_dependencies(self, switch_nodes: List[str]) -> bool:
        """Detect circular dependencies between switches."""
        if len(switch_nodes) < 2:
            return False

        # Build dependency graph between switches
        switch_deps = nx.DiGraph()
        switch_deps.add_nodes_from(switch_nodes)

        for switch_id in switch_nodes:
            if switch_id in self._branch_map:
                for port, downstream in self._branch_map[switch_id].items():
                    for downstream_switch in downstream:
                        if downstream_switch in switch_nodes:
                            switch_deps.add_edge(switch_id, downstream_switch)

        # Check for cycles in switch dependency graph
        try:
            return not nx.is_directed_acyclic_graph(switch_deps)
        except Exception:
            return False

    def _detect_multi_case_switches(self, switch_nodes: List[str]) -> List[str]:
        """Detect multi-case switches (more than true/false outputs)."""
        multi_case = []

        for switch_id in switch_nodes:
            if switch_id in self._branch_map:
                ports = list(self._branch_map[switch_id].keys())

                # Multi-case switches have more than 2 output ports or case_X patterns
                case_ports = [p for p in ports if p.startswith("case_")]
                if len(ports) > 2 or case_ports:
                    multi_case.append(switch_id)

        return multi_case

    def _get_switch_branch_map(self, switch_id: str) -> Dict[str, Set[str]]:
        """
        Get the branch map for a specific switch node.

        Args:
            switch_id: ID of the switch node

        Returns:
            Dictionary mapping output ports to downstream nodes
        """
        branch_map = self._build_branch_map()
        return branch_map.get(switch_id, {})

    def detect_switch_hierarchies(self) -> List[Dict[str, Any]]:
        """
        Detect hierarchical switch patterns.

        Returns:
            List of hierarchy information dictionaries
        """
        hierarchies = []
        switch_nodes = self._find_switch_nodes()

        if len(switch_nodes) <= 1:
            return hierarchies

        # Get hierarchy analysis
        hierarchy_info = self.analyze_switch_hierarchies(switch_nodes)

        if hierarchy_info["has_hierarchies"]:
            hierarchies.append(
                {
                    "layers": hierarchy_info["execution_layers"],
                    "max_depth": hierarchy_info["max_depth"],
                    "dependency_chains": hierarchy_info["dependency_chains"],
                }
            )

        return hierarchies

    def invalidate_cache(self):
        """Invalidate cached analysis results."""
        self._switch_nodes = None
        self._branch_map = None
        logger.debug("ConditionalBranchAnalyzer cache invalidated")

    # ===== PHASE 4: ADVANCED FEATURES =====

    def analyze_switch_hierarchies(
        self, switch_nodes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze hierarchical relationships between SwitchNodes.

        Args:
            switch_nodes: Optional list of SwitchNode IDs to analyze

        Returns:
            Dictionary with hierarchy analysis results
        """
        if switch_nodes is None:
            switch_nodes = self._find_switch_nodes()

        hierarchy_info = {
            "has_hierarchies": False,
            "max_depth": 0,
            "dependency_chains": [],
            "independent_switches": [],
            "execution_layers": [],
        }

        try:
            if len(switch_nodes) <= 1:
                hierarchy_info["independent_switches"] = switch_nodes
                hierarchy_info["execution_layers"] = (
                    [switch_nodes] if switch_nodes else []
                )
                hierarchy_info["max_depth"] = 1 if switch_nodes else 0
                return hierarchy_info

            # Build dependency graph between switches
            switch_dependencies = {}
            for switch_id in switch_nodes:
                predecessors = list(self.workflow.graph.predecessors(switch_id))
                switch_predecessors = [
                    pred for pred in predecessors if pred in switch_nodes
                ]
                switch_dependencies[switch_id] = switch_predecessors

                if switch_predecessors:
                    hierarchy_info["has_hierarchies"] = True

            # Calculate execution layers (topological ordering of switches)
            if hierarchy_info["has_hierarchies"]:
                layers = self._create_execution_layers(
                    switch_nodes, switch_dependencies
                )
                hierarchy_info["execution_layers"] = layers
                hierarchy_info["max_depth"] = len(layers)

                # Find dependency chains
                hierarchy_info["dependency_chains"] = self._find_dependency_chains(
                    switch_dependencies
                )
            else:
                hierarchy_info["independent_switches"] = switch_nodes
                hierarchy_info["execution_layers"] = [switch_nodes]
                hierarchy_info["max_depth"] = 1

        except Exception as e:
            logger.warning(f"Error analyzing switch hierarchies: {e}")

        return hierarchy_info

    def _create_execution_layers(
        self, switch_nodes: List[str], dependencies: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        Create execution layers for hierarchical switches.

        Args:
            switch_nodes: List of all switch node IDs
            dependencies: Dictionary mapping switch_id -> list of dependent switches

        Returns:
            List of execution layers, each containing switches that can execute in parallel
        """
        layers = []
        remaining_switches = set(switch_nodes)
        processed_switches = set()

        while remaining_switches:
            # Find switches with no unprocessed dependencies
            current_layer = []
            for switch_id in remaining_switches:
                switch_deps = dependencies.get(switch_id, [])
                if all(dep in processed_switches for dep in switch_deps):
                    current_layer.append(switch_id)

            if not current_layer:
                # Circular dependency or error - add remaining switches to avoid infinite loop
                logger.warning("Circular dependency detected in switch hierarchy")
                current_layer = list(remaining_switches)

            layers.append(current_layer)
            remaining_switches -= set(current_layer)
            processed_switches.update(current_layer)

        return layers

    def _find_dependency_chains(
        self, dependencies: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        Find dependency chains in switch hierarchies.

        Args:
            dependencies: Dictionary mapping switch_id -> list of dependent switches

        Returns:
            List of dependency chains (each chain is a list of switch IDs)
        """
        chains = []
        visited = set()

        def build_chain(switch_id: str, current_chain: List[str]):
            if switch_id in visited or switch_id in current_chain:
                return  # Avoid cycles

            current_chain.append(switch_id)
            deps = dependencies.get(switch_id, [])

            if not deps:
                # End of chain
                if len(current_chain) > 1:
                    chains.append(current_chain.copy())
            else:
                for dep in deps:
                    build_chain(dep, current_chain.copy())

        for switch_id in dependencies:
            if switch_id not in visited:
                build_chain(switch_id, [])
                visited.add(switch_id)

        return chains

    def create_hierarchical_execution_plan(
        self, switch_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create execution plan that handles hierarchical switch dependencies.

        Args:
            switch_results: Results from SwitchNode execution

        Returns:
            Dictionary containing hierarchical execution plan
        """
        plan = {
            "execution_layers": [],
            "reachable_nodes": set(),
            "merge_strategies": {},
            "performance_estimate": 0,
        }

        try:
            switch_nodes = self._find_switch_nodes()
            hierarchy_info = self.analyze_switch_hierarchies(switch_nodes)

            # Process each execution layer
            for layer_index, layer_switches in enumerate(
                hierarchy_info["execution_layers"]
            ):
                layer_plan = {
                    "layer_index": layer_index,
                    "switches": layer_switches,
                    "reachable_from_layer": set(),
                    "blocked_from_layer": set(),
                }

                # Determine reachable nodes from this layer
                for switch_id in layer_switches:
                    if switch_id in switch_results:
                        reachable = self._get_reachable_from_switch(
                            switch_id, switch_results[switch_id]
                        )
                        layer_plan["reachable_from_layer"].update(reachable)
                        plan["reachable_nodes"].update(reachable)
                    else:
                        # Switch not executed yet - add to blocked
                        layer_plan["blocked_from_layer"].add(switch_id)

                plan["execution_layers"].append(layer_plan)

            # Analyze merge nodes and their strategies
            merge_nodes = self._find_merge_nodes()
            for merge_id in merge_nodes:
                plan["merge_strategies"][merge_id] = self._determine_merge_strategy(
                    merge_id, plan["reachable_nodes"]
                )

            # Estimate performance improvement
            total_nodes = len(self.workflow.graph.nodes)
            reachable_count = len(plan["reachable_nodes"])
            plan["performance_estimate"] = (
                (total_nodes - reachable_count) / total_nodes if total_nodes > 0 else 0
            )

        except Exception as e:
            logger.warning(f"Error creating hierarchical execution plan: {e}")

        return plan

    def _get_reachable_from_switch(
        self, switch_id: str, switch_result: Dict[str, Any]
    ) -> Set[str]:
        """
        Get nodes reachable from a specific switch result.

        Args:
            switch_id: ID of the switch node
            switch_result: Result from switch execution

        Returns:
            Set of node IDs reachable from this switch
        """
        reachable = set()

        try:
            # Get the branch map for this switch
            branch_map = self._build_branch_map()
            switch_branches = branch_map.get(switch_id, {})

            # Check which branches are active
            for output_key, nodes in switch_branches.items():
                if (
                    output_key in switch_result
                    and switch_result[output_key] is not None
                ):
                    reachable.update(nodes)

        except Exception as e:
            logger.warning(
                f"Error getting reachable nodes from switch {switch_id}: {e}"
            )

        return reachable

    def _determine_merge_strategy(
        self, merge_id: str, reachable_nodes: Set[str]
    ) -> Dict[str, Any]:
        """
        Determine merge strategy for a MergeNode based on reachable inputs.

        Args:
            merge_id: ID of the merge node
            reachable_nodes: Set of nodes that will be executed

        Returns:
            Dictionary describing the merge strategy
        """
        strategy = {
            "merge_id": merge_id,
            "available_inputs": [],
            "missing_inputs": [],
            "strategy_type": "partial",
            "skip_merge": False,
        }

        try:
            # Get predecessors of the merge node
            predecessors = list(self.workflow.graph.predecessors(merge_id))

            for pred in predecessors:
                if pred in reachable_nodes:
                    strategy["available_inputs"].append(pred)
                else:
                    strategy["missing_inputs"].append(pred)

            # Determine strategy based on available inputs
            if not strategy["available_inputs"]:
                strategy["strategy_type"] = "skip"
                strategy["skip_merge"] = True
            elif not strategy["missing_inputs"]:
                strategy["strategy_type"] = "full"
            else:
                strategy["strategy_type"] = "partial"

        except Exception as e:
            logger.warning(f"Error determining merge strategy for {merge_id}: {e}")

        return strategy

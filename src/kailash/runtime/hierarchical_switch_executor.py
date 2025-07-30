"""
Hierarchical Switch Executor for LocalRuntime.

This module implements hierarchical switch execution to optimize conditional workflow
execution by respecting switch dependencies and executing them in layers.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.analysis import ConditionalBranchAnalyzer
from kailash.tracking import TaskManager
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class HierarchicalSwitchExecutor:
    """
    Executes switches in hierarchical layers to optimize conditional execution.

    This executor analyzes switch dependencies and executes them in layers where
    switches in the same layer can be executed in parallel, and each layer depends
    on the results of the previous layer.
    """

    def __init__(
        self,
        workflow: Workflow,
        debug: bool = False,
        max_parallelism: int = 10,
        layer_timeout: float = None,
    ):
        """
        Initialize the hierarchical switch executor.

        Args:
            workflow: The workflow containing switches to execute
            debug: Enable debug logging
            max_parallelism: Maximum concurrent switches per layer
            layer_timeout: Timeout in seconds for each layer execution
        """
        self.workflow = workflow
        self.debug = debug
        self.analyzer = ConditionalBranchAnalyzer(workflow)
        self.max_parallelism = max_parallelism
        self.layer_timeout = layer_timeout
        self._execution_metrics = {
            "layer_timings": [],
            "parallelism_achieved": [],
            "errors_by_layer": [],
        }

    async def execute_switches_hierarchically(
        self,
        parameters: Dict[str, Any],
        task_manager: Optional[TaskManager] = None,
        run_id: str = "",
        workflow_context: Dict[str, Any] = None,
        node_executor=None,  # Function to execute individual nodes
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        """
        Execute switches in hierarchical layers.

        Args:
            parameters: Node-specific parameters
            task_manager: Task manager for execution tracking
            run_id: Unique run identifier
            workflow_context: Workflow execution context
            node_executor: Function to execute individual nodes

        Returns:
            Tuple of (all_results, switch_results) where:
                - all_results: All node execution results including dependencies
                - switch_results: Just the switch node results
        """
        if workflow_context is None:
            workflow_context = {}

        all_results = {}
        switch_results = {}

        # Find all switch nodes
        switch_node_ids = self.analyzer._find_switch_nodes()
        if not switch_node_ids:
            logger.info("No switch nodes found in workflow")
            return all_results, switch_results

        # Analyze switch hierarchies
        hierarchy_info = self.analyzer.analyze_switch_hierarchies(switch_node_ids)
        execution_layers = hierarchy_info.get("execution_layers", [])

        if not execution_layers:
            # Fallback to simple execution if no layers detected
            logger.warning(
                "No execution layers detected, falling back to simple execution"
            )
            execution_layers = [switch_node_ids]

        logger.info(
            f"Executing switches in {len(execution_layers)} hierarchical layers"
        )

        # Execute each layer
        for layer_index, layer_switches in enumerate(execution_layers):
            layer_start_time = asyncio.get_event_loop().time()
            layer_errors = []

            logger.info(
                f"Executing layer {layer_index + 1}/{len(execution_layers)} with {len(layer_switches)} switches"
            )

            # First, execute dependencies for switches in this layer
            layer_dependencies = self._get_layer_dependencies(
                layer_switches, all_results.keys()
            )

            if layer_dependencies:
                logger.debug(
                    f"Executing {len(layer_dependencies)} dependencies for layer {layer_index + 1}"
                )
                # Execute dependencies sequentially (could be optimized for parallel execution)
                for dep_node_id in layer_dependencies:
                    if dep_node_id not in all_results:
                        result = await self._execute_node_with_dependencies(
                            dep_node_id,
                            all_results,
                            parameters,
                            task_manager,
                            run_id,
                            workflow_context,
                            node_executor,
                        )
                        if result is not None:
                            all_results[dep_node_id] = result

            # Execute switches in this layer in parallel with concurrency limit
            layer_tasks = []
            for switch_id in layer_switches:
                if switch_id not in all_results:
                    task = self._execute_switch_with_context(
                        switch_id,
                        all_results,
                        parameters,
                        task_manager,
                        run_id,
                        workflow_context,
                        node_executor,
                    )
                    layer_tasks.append((switch_id, task))

            # Wait for all switches in this layer to complete with timeout
            if layer_tasks:
                # Apply concurrency limit by chunking tasks
                task_chunks = [
                    layer_tasks[i : i + self.max_parallelism]
                    for i in range(0, len(layer_tasks), self.max_parallelism)
                ]

                for chunk in task_chunks:
                    try:
                        if self.layer_timeout:
                            chunk_results = await asyncio.wait_for(
                                asyncio.gather(
                                    *[task for _, task in chunk], return_exceptions=True
                                ),
                                timeout=self.layer_timeout,
                            )
                        else:
                            chunk_results = await asyncio.gather(
                                *[task for _, task in chunk], return_exceptions=True
                            )

                        # Process results
                        for (switch_id, _), result in zip(chunk, chunk_results):
                            if isinstance(result, Exception):
                                logger.error(
                                    f"Error executing switch {switch_id}: {result}"
                                )
                                layer_errors.append(
                                    {"switch": switch_id, "error": str(result)}
                                )
                                # Store error result
                                all_results[switch_id] = {"error": str(result)}
                                switch_results[switch_id] = {"error": str(result)}
                            else:
                                all_results[switch_id] = result
                                switch_results[switch_id] = result

                    except asyncio.TimeoutError:
                        logger.error(
                            f"Layer {layer_index + 1} execution timed out after {self.layer_timeout}s"
                        )
                        for switch_id, _ in chunk:
                            if switch_id not in all_results:
                                error_msg = f"Timeout after {self.layer_timeout}s"
                                layer_errors.append(
                                    {"switch": switch_id, "error": error_msg}
                                )
                                all_results[switch_id] = {"error": error_msg}
                                switch_results[switch_id] = {"error": error_msg}

            # Record layer metrics
            layer_execution_time = asyncio.get_event_loop().time() - layer_start_time
            self._execution_metrics["layer_timings"].append(
                {
                    "layer": layer_index + 1,
                    "switches": len(layer_switches),
                    "execution_time": layer_execution_time,
                    "parallelism": min(len(layer_switches), self.max_parallelism),
                }
            )
            self._execution_metrics["parallelism_achieved"].append(
                min(len(layer_switches), self.max_parallelism)
            )
            self._execution_metrics["errors_by_layer"].append(layer_errors)

        # Log execution summary
        successful_switches = sum(
            1 for r in switch_results.values() if "error" not in r
        )
        logger.info(
            f"Hierarchical switch execution complete: {successful_switches}/{len(switch_results)} switches executed successfully"
        )

        return all_results, switch_results

    def _get_layer_dependencies(
        self, layer_switches: List[str], already_executed: Set[str]
    ) -> List[str]:
        """
        Get all dependencies needed for switches in this layer.

        Args:
            layer_switches: Switches in the current layer
            already_executed: Set of node IDs that have already been executed

        Returns:
            List of node IDs that need to be executed before the layer switches
        """
        dependencies = []
        visited = set(already_executed)

        for switch_id in layer_switches:
            # Get all predecessors of this switch
            predecessors = list(self.workflow.graph.predecessors(switch_id))

            for pred_id in predecessors:
                if pred_id not in visited:
                    # Recursively get dependencies of this predecessor
                    self._collect_dependencies(pred_id, dependencies, visited)

        return dependencies

    def _collect_dependencies(
        self, node_id: str, dependencies: List[str], visited: Set[str]
    ):
        """
        Recursively collect dependencies for a node.

        Args:
            node_id: Node to collect dependencies for
            dependencies: List to append dependencies to
            visited: Set of already visited nodes
        """
        if node_id in visited:
            return

        visited.add(node_id)

        # Get predecessors
        predecessors = list(self.workflow.graph.predecessors(node_id))

        # Recursively collect their dependencies first (depth-first)
        for pred_id in predecessors:
            if pred_id not in visited:
                self._collect_dependencies(pred_id, dependencies, visited)

        # Add this node after its dependencies
        dependencies.append(node_id)

    async def _execute_node_with_dependencies(
        self,
        node_id: str,
        all_results: Dict[str, Dict[str, Any]],
        parameters: Dict[str, Any],
        task_manager: Optional[TaskManager],
        run_id: str,
        workflow_context: Dict[str, Any],
        node_executor,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a node after ensuring its dependencies are met.

        Args:
            node_id: Node to execute
            all_results: Results from previously executed nodes
            parameters: Node-specific parameters
            task_manager: Task manager for execution tracking
            run_id: Unique run identifier
            workflow_context: Workflow execution context
            node_executor: Function to execute the node

        Returns:
            Execution result or None if execution failed
        """
        try:
            # Get node instance
            node_data = self.workflow.graph.nodes[node_id]
            node_instance = node_data.get("node") or node_data.get("instance")

            if node_instance is None:
                logger.warning(f"No instance found for node {node_id}")
                return None

            # Execute using provided executor
            if node_executor:
                result = await node_executor(
                    node_id=node_id,
                    node_instance=node_instance,
                    all_results=all_results,
                    parameters=parameters,
                    task_manager=task_manager,
                    workflow=self.workflow,
                    workflow_context=workflow_context,
                )
                return result
            else:
                logger.error(f"No node executor provided for {node_id}")
                return None

        except Exception as e:
            logger.error(f"Error executing node {node_id}: {e}")
            return {"error": str(e)}

    async def _execute_switch_with_context(
        self,
        switch_id: str,
        all_results: Dict[str, Dict[str, Any]],
        parameters: Dict[str, Any],
        task_manager: Optional[TaskManager],
        run_id: str,
        workflow_context: Dict[str, Any],
        node_executor,
    ) -> Dict[str, Any]:
        """
        Execute a switch node with proper context from dependencies.

        Args:
            switch_id: Switch node to execute
            all_results: Results from previously executed nodes
            parameters: Node-specific parameters
            task_manager: Task manager for execution tracking
            run_id: Unique run identifier
            workflow_context: Workflow execution context
            node_executor: Function to execute the node

        Returns:
            Switch execution result
        """
        logger.debug(
            f"Executing switch {switch_id} with context from {len(all_results)} previous results"
        )

        # Execute the switch using the standard node execution
        result = await self._execute_node_with_dependencies(
            switch_id,
            all_results,
            parameters,
            task_manager,
            run_id,
            workflow_context,
            node_executor,
        )

        if result and self.debug:
            # Log switch decision for debugging
            if "true_output" in result and result["true_output"] is not None:
                logger.debug(f"Switch {switch_id} took TRUE branch")
            elif "false_output" in result and result["false_output"] is not None:
                logger.debug(f"Switch {switch_id} took FALSE branch")
            else:
                logger.debug(f"Switch {switch_id} result: {result}")

        return result or {"error": "Switch execution failed"}

    def get_execution_summary(
        self, switch_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get a summary of the hierarchical switch execution.

        Args:
            switch_results: Results from switch execution

        Returns:
            Summary dictionary with execution statistics
        """
        hierarchy_info = self.analyzer.analyze_switch_hierarchies(
            list(switch_results.keys())
        )

        summary = {
            "total_switches": len(switch_results),
            "successful_switches": sum(
                1 for r in switch_results.values() if "error" not in r
            ),
            "failed_switches": sum(1 for r in switch_results.values() if "error" in r),
            "execution_layers": hierarchy_info.get("execution_layers", []),
            "max_depth": hierarchy_info.get("max_depth", 0),
            "has_circular_dependencies": hierarchy_info.get(
                "has_circular_dependencies", False
            ),
            "dependency_chains": hierarchy_info.get("dependency_chains", []),
        }

        # Analyze branch decisions
        true_branches = 0
        false_branches = 0
        multi_branches = 0

        for result in switch_results.values():
            if "error" not in result:
                if "true_output" in result and result["true_output"] is not None:
                    true_branches += 1
                elif "false_output" in result and result["false_output"] is not None:
                    false_branches += 1
                else:
                    # Multi-way switch or other pattern
                    multi_branches += 1

        summary["branch_decisions"] = {
            "true_branches": true_branches,
            "false_branches": false_branches,
            "multi_branches": multi_branches,
        }

        return summary

    def get_execution_metrics(self) -> Dict[str, Any]:
        """
        Get detailed execution metrics for performance analysis.

        Returns:
            Dictionary containing execution metrics
        """
        total_time = sum(
            timing["execution_time"]
            for timing in self._execution_metrics["layer_timings"]
        )
        total_errors = sum(
            len(errors) for errors in self._execution_metrics["errors_by_layer"]
        )

        metrics = {
            "total_execution_time": total_time,
            "layer_count": len(self._execution_metrics["layer_timings"]),
            "layer_timings": self._execution_metrics["layer_timings"],
            "average_layer_time": (
                total_time / len(self._execution_metrics["layer_timings"])
                if self._execution_metrics["layer_timings"]
                else 0
            ),
            "max_parallelism_used": (
                max(self._execution_metrics["parallelism_achieved"])
                if self._execution_metrics["parallelism_achieved"]
                else 0
            ),
            "total_errors": total_errors,
            "errors_by_layer": self._execution_metrics["errors_by_layer"],
            "configuration": {
                "max_parallelism": self.max_parallelism,
                "layer_timeout": self.layer_timeout,
            },
        }

        return metrics

    def handle_circular_dependencies(self, switch_nodes: List[str]) -> List[List[str]]:
        """
        Handle circular dependencies by breaking cycles intelligently.

        Args:
            switch_nodes: List of switch node IDs

        Returns:
            Execution layers with cycles broken
        """
        # Try to detect and break cycles
        try:
            import networkx as nx

            # Create directed graph of dependencies
            G = nx.DiGraph()
            for switch_id in switch_nodes:
                G.add_node(switch_id)
                predecessors = list(self.workflow.graph.predecessors(switch_id))
                for pred in predecessors:
                    if pred in switch_nodes:
                        G.add_edge(pred, switch_id)

            # Find cycles
            cycles = list(nx.simple_cycles(G))

            if cycles:
                logger.warning(
                    f"Found {len(cycles)} circular dependencies in switch hierarchy"
                )

                # Break cycles by removing back edges
                for cycle in cycles:
                    # Remove the edge that creates the cycle (last -> first)
                    if len(cycle) >= 2:
                        G.remove_edge(cycle[-1], cycle[0])
                        logger.debug(
                            f"Breaking cycle by removing edge {cycle[-1]} -> {cycle[0]}"
                        )

                # Now create layers from the acyclic graph
                layers = []
                remaining = set(switch_nodes)

                while remaining:
                    # Find nodes with no incoming edges from remaining nodes
                    current_layer = []
                    for node in remaining:
                        has_deps = any(
                            pred in remaining for pred in G.predecessors(node)
                        )
                        if not has_deps:
                            current_layer.append(node)

                    if not current_layer:
                        # Shouldn't happen after breaking cycles, but handle it
                        current_layer = list(remaining)

                    layers.append(current_layer)
                    remaining -= set(current_layer)

                return layers

        except ImportError:
            logger.warning("NetworkX not available for cycle detection")

        # Fallback to analyzer's method
        hierarchy_info = self.analyzer.analyze_switch_hierarchies(switch_nodes)
        return hierarchy_info.get("execution_layers", [switch_nodes])

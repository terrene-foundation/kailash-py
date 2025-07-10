"""
Unified Async Runtime for Kailash Workflows.

This module provides the AsyncLocalRuntime, a specialized async-first runtime that
extends LocalRuntime with advanced concurrent execution, workflow optimization,
and integrated resource management.

Key Features:
- Native async/await execution with concurrent node processing
- Workflow analysis and optimization for parallel execution
- Integrated ResourceRegistry support
- Advanced execution context and tracking
- Performance profiling and metrics
- Circuit breaker patterns for resilient execution
"""

import asyncio
import logging
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx

from kailash.nodes.base import Node
from kailash.nodes.base_async import AsyncNode
from kailash.resources import ResourceRegistry
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowExecutionError
from kailash.tracking import TaskManager, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class ExecutionLevel:
    """Represents a level of nodes that can execute concurrently."""

    level: int
    nodes: Set[str] = field(default_factory=set)
    dependencies_satisfied: Set[str] = field(default_factory=set)


@dataclass
class ExecutionPlan:
    """Execution plan for optimized workflow execution."""

    workflow_id: str
    async_nodes: Set[str] = field(default_factory=set)
    sync_nodes: Set[str] = field(default_factory=set)
    execution_levels: List[ExecutionLevel] = field(default_factory=list)
    required_resources: Set[str] = field(default_factory=set)
    estimated_duration: float = 0.0
    max_concurrent_nodes: int = 1

    @property
    def is_fully_async(self) -> bool:
        """Check if workflow contains only async nodes."""
        return len(self.sync_nodes) == 0 and len(self.async_nodes) > 0

    @property
    def has_async_nodes(self) -> bool:
        """Check if workflow contains any async nodes."""
        return len(self.async_nodes) > 0

    @property
    def can_parallelize(self) -> bool:
        """Check if workflow can benefit from parallelization."""
        return self.max_concurrent_nodes > 1


@dataclass
class ExecutionMetrics:
    """Metrics collected during execution."""

    total_duration: float = 0.0
    node_durations: Dict[str, float] = field(default_factory=dict)
    concurrent_executions: int = 0
    resource_access_count: Dict[str, int] = field(default_factory=dict)
    error_count: int = 0
    retry_count: int = 0


class ExecutionContext:
    """Context passed through workflow execution with resource access."""

    def __init__(self, resource_registry: Optional[ResourceRegistry] = None):
        self.resource_registry = resource_registry
        self.variables: Dict[str, Any] = {}
        self.metrics = ExecutionMetrics()
        self.start_time = time.time()
        self._weak_refs: Dict[str, weakref.ref] = {}

    def set_variable(self, key: str, value: Any) -> None:
        """Set a context variable accessible to all nodes."""
        self.variables[key] = value

    def get_variable(self, key: str, default=None) -> Any:
        """Get a context variable."""
        return self.variables.get(key, default)

    async def get_resource(self, name: str) -> Any:
        """Get resource from registry."""
        if not self.resource_registry:
            raise RuntimeError("No resource registry available in execution context")

        # Track resource access
        self.metrics.resource_access_count[name] = (
            self.metrics.resource_access_count.get(name, 0) + 1
        )

        return await self.resource_registry.get_resource(name)


class WorkflowAnalyzer:
    """Analyzes workflows for optimization opportunities."""

    def __init__(self, enable_profiling: bool = True):
        self.enable_profiling = enable_profiling
        self._analysis_cache: Dict[str, ExecutionPlan] = {}

    def analyze(self, workflow) -> ExecutionPlan:
        """Analyze workflow and create execution plan."""
        workflow_id = (
            workflow.workflow_id
            if hasattr(workflow, "workflow_id")
            else str(id(workflow))
        )

        # Check cache first
        if workflow_id in self._analysis_cache:
            return self._analysis_cache[workflow_id]

        plan = ExecutionPlan(workflow_id=workflow_id)

        # Identify node types
        for node_id, node_instance in workflow._node_instances.items():
            if isinstance(node_instance, AsyncNode):
                plan.async_nodes.add(node_id)
            else:
                plan.sync_nodes.add(node_id)

        # Identify resource requirements
        plan.required_resources = self._identify_resources(workflow)

        # Compute execution levels for parallelization
        plan.execution_levels = self._compute_execution_levels(workflow)

        # Calculate max concurrent nodes
        plan.max_concurrent_nodes = (
            max(len(level.nodes) for level in plan.execution_levels)
            if plan.execution_levels
            else 1
        )

        # Estimate execution duration (simplified)
        plan.estimated_duration = self._estimate_duration(workflow, plan)

        # Cache the plan
        self._analysis_cache[workflow_id] = plan

        logger.debug(
            f"Workflow analysis complete: {len(plan.async_nodes)} async nodes, "
            f"{len(plan.sync_nodes)} sync nodes, "
            f"{len(plan.execution_levels)} execution levels"
        )

        return plan

    def _compute_execution_levels(self, workflow) -> List[ExecutionLevel]:
        """Compute execution levels for parallel execution."""
        levels = []
        remaining_nodes = set(workflow._node_instances.keys())
        completed_nodes = set()
        level_num = 0

        while remaining_nodes:
            current_level = ExecutionLevel(level=level_num)

            # Find nodes that can execute at this level
            for node_id in list(remaining_nodes):
                # Check if all dependencies are satisfied
                dependencies = set(workflow.graph.predecessors(node_id))
                if dependencies.issubset(completed_nodes):
                    current_level.nodes.add(node_id)
                    current_level.dependencies_satisfied.update(dependencies)

            if not current_level.nodes:
                # No nodes can execute - likely a dependency cycle
                logger.warning(
                    f"No executable nodes at level {level_num}, remaining: {remaining_nodes}"
                )
                break

            levels.append(current_level)
            completed_nodes.update(current_level.nodes)
            remaining_nodes -= current_level.nodes
            level_num += 1

        return levels

    def _identify_resources(self, workflow) -> Set[str]:
        """Identify required resources from workflow metadata."""
        resources = set()

        # Check workflow-level metadata
        if hasattr(workflow, "metadata") and workflow.metadata:
            workflow_resources = workflow.metadata.get("required_resources", [])
            resources.update(workflow_resources)

        # Check node-level metadata
        for node_id, node_instance in workflow._node_instances.items():
            if hasattr(node_instance, "config") and isinstance(
                node_instance.config, dict
            ):
                node_resources = node_instance.config.get("required_resources", [])
                resources.update(node_resources)

        return resources

    def _estimate_duration(self, workflow, plan: ExecutionPlan) -> float:
        """Estimate workflow execution duration."""
        # Simplified estimation based on node count and type
        base_duration_per_node = 0.1  # 100ms per node
        async_multiplier = 0.5  # Async nodes are typically faster
        sync_multiplier = 1.0

        async_duration = (
            len(plan.async_nodes) * base_duration_per_node * async_multiplier
        )
        sync_duration = len(plan.sync_nodes) * base_duration_per_node * sync_multiplier

        # Account for parallelization
        if plan.execution_levels:
            # Use the longest level as bottleneck
            max_level_size = max(len(level.nodes) for level in plan.execution_levels)
            parallelization_factor = (
                max_level_size / len(plan.execution_levels)
                if plan.execution_levels
                else 1
            )
        else:
            parallelization_factor = 1

        return (async_duration + sync_duration) * parallelization_factor


class AsyncExecutionTracker:
    """Tracks async execution state and results."""

    def __init__(self, workflow, context: ExecutionContext):
        self.workflow = workflow
        self.context = context
        self.results: Dict[str, Any] = {}
        self.node_outputs: Dict[str, Any] = {}
        self.errors: Dict[str, Exception] = {}
        self.execution_times: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def get_lock(self, node_id: str) -> asyncio.Lock:
        """Get or create a lock for a node."""
        if node_id not in self._locks:
            self._locks[node_id] = asyncio.Lock()
        return self._locks[node_id]

    async def record_result(
        self, node_id: str, result: Any, execution_time: float
    ) -> None:
        """Record execution result for a node."""
        async with self.get_lock(node_id):
            self.results[node_id] = result
            self.node_outputs[node_id] = result
            self.execution_times[node_id] = execution_time
            self.context.metrics.node_durations[node_id] = execution_time

    async def record_error(self, node_id: str, error: Exception) -> None:
        """Record execution error for a node."""
        async with self.get_lock(node_id):
            self.errors[node_id] = error
            self.context.metrics.error_count += 1

    def get_result(self) -> Dict[str, Any]:
        """Get final execution results."""
        return {
            "results": self.results.copy(),
            "errors": {node_id: str(error) for node_id, error in self.errors.items()},
            "execution_times": self.execution_times.copy(),
            "total_duration": time.time() - self.context.start_time,
            "metrics": self.context.metrics,
        }


class AsyncLocalRuntime(LocalRuntime):
    """
    Async-optimized runtime for Kailash workflows.

    Extends LocalRuntime with advanced async execution capabilities:
    - Concurrent node execution where possible
    - Integrated ResourceRegistry support
    - Workflow analysis and optimization
    - Advanced performance tracking
    - Circuit breaker patterns

    Example:
        ```python
        from kailash.resources import ResourceRegistry, DatabasePoolFactory
        from kailash.runtime.async_local import AsyncLocalRuntime

        # Setup resources
        registry = ResourceRegistry()
        registry.register_factory("db", DatabasePoolFactory(...))

        # Create async runtime
        runtime = AsyncLocalRuntime(
            resource_registry=registry,
            max_concurrent_nodes=10,
            enable_analysis=True
        )

        # Execute workflow
        result = await runtime.execute_workflow_async(workflow, inputs)
        ```
    """

    def __init__(
        self,
        resource_registry: Optional[ResourceRegistry] = None,
        max_concurrent_nodes: int = 10,
        enable_analysis: bool = True,
        enable_profiling: bool = True,
        thread_pool_size: int = 4,
        **kwargs,
    ):
        """
        Initialize AsyncLocalRuntime.

        Args:
            resource_registry: Optional ResourceRegistry for resource management
            max_concurrent_nodes: Maximum number of nodes to execute concurrently
            enable_analysis: Whether to analyze workflows for optimization
            enable_profiling: Whether to collect detailed performance metrics
            thread_pool_size: Size of thread pool for sync node execution
            **kwargs: Additional arguments passed to LocalRuntime
        """
        # Ensure async is enabled
        kwargs["enable_async"] = True
        super().__init__(**kwargs)

        self.resource_registry = resource_registry
        self.max_concurrent_nodes = max_concurrent_nodes
        self.enable_analysis = enable_analysis
        self.enable_profiling = enable_profiling

        # Workflow analyzer
        self.analyzer = (
            WorkflowAnalyzer(enable_profiling=enable_profiling)
            if enable_analysis
            else None
        )

        # Thread pool for sync node execution
        self.thread_pool = ThreadPoolExecutor(max_workers=thread_pool_size)

        # Execution semaphore for concurrency control
        self.execution_semaphore = asyncio.Semaphore(max_concurrent_nodes)

        logger.info(
            f"AsyncLocalRuntime initialized with max_concurrent_nodes={max_concurrent_nodes}"
        )

    async def execute_workflow_async(
        self,
        workflow,
        inputs: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow with native async support.

        This method provides first-class async execution with:
        - Concurrent node execution where dependencies allow
        - Integrated resource management
        - Performance optimization based on workflow analysis
        - Advanced error handling and recovery

        Args:
            workflow: Workflow to execute
            inputs: Input data for the workflow
            context: Optional execution context

        Returns:
            Dictionary containing execution results and metrics

        Raises:
            WorkflowExecutionError: If execution fails
        """
        start_time = time.time()

        # Create execution context
        if context is None:
            context = ExecutionContext(resource_registry=self.resource_registry)

        # Add inputs to context
        context.variables.update(inputs)

        try:
            # Analyze workflow if enabled
            execution_plan = None
            if self.analyzer:
                execution_plan = self.analyzer.analyze(workflow)
                logger.info(
                    f"Execution plan: {execution_plan.max_concurrent_nodes} max concurrent, "
                    f"{len(execution_plan.execution_levels)} levels"
                )

            # Choose execution strategy based on analysis
            if execution_plan and execution_plan.is_fully_async:
                result = await self._execute_fully_async_workflow(
                    workflow, context, execution_plan
                )
            elif execution_plan and execution_plan.has_async_nodes:
                result = await self._execute_mixed_workflow(
                    workflow, context, execution_plan
                )
            else:
                result = await self._execute_sync_workflow(workflow, context)

            # Update total execution time
            total_time = time.time() - start_time
            context.metrics.total_duration = total_time

            logger.info(f"Workflow execution completed in {total_time:.2f}s")

            return result

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            context.metrics.error_count += 1
            raise WorkflowExecutionError(f"Async execution failed: {e}") from e

    async def _execute_fully_async_workflow(
        self, workflow, context: ExecutionContext, execution_plan: ExecutionPlan
    ) -> Dict[str, Any]:
        """Execute fully async workflow with maximum concurrency."""
        logger.debug("Executing fully async workflow with concurrent levels")

        tracker = AsyncExecutionTracker(workflow, context)

        # Execute by levels to respect dependencies
        for level in execution_plan.execution_levels:
            if not level.nodes:
                continue

            logger.debug(f"Executing level {level.level} with {len(level.nodes)} nodes")

            # Create tasks for all nodes in this level
            tasks = []
            for node_id in level.nodes:
                task = self._execute_node_async(workflow, node_id, tracker, context)
                tasks.append(task)

            # Execute all tasks in this level concurrently
            try:
                await asyncio.gather(*tasks, return_exceptions=False)
            except Exception as e:
                logger.error(f"Level {level.level} execution failed: {e}")
                raise

        return tracker.get_result()

    async def _execute_mixed_workflow(
        self, workflow, context: ExecutionContext, execution_plan: ExecutionPlan
    ) -> Dict[str, Any]:
        """Execute workflow with mixed sync/async nodes."""
        logger.debug("Executing mixed workflow with sync/async optimization")

        tracker = AsyncExecutionTracker(workflow, context)

        # Execute by levels, handling sync/async appropriately
        for level in execution_plan.execution_levels:
            if not level.nodes:
                continue

            # Separate sync and async nodes in this level
            async_nodes = [n for n in level.nodes if n in execution_plan.async_nodes]
            sync_nodes = [n for n in level.nodes if n in execution_plan.sync_nodes]

            tasks = []

            # Add async node tasks
            for node_id in async_nodes:
                task = self._execute_node_async(workflow, node_id, tracker, context)
                tasks.append(task)

            # Add sync node tasks (wrapped in thread pool)
            for node_id in sync_nodes:
                task = self._execute_sync_node_async(
                    workflow, node_id, tracker, context
                )
                tasks.append(task)

            # Execute all tasks in this level concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=False)

        return tracker.get_result()

    async def _execute_sync_workflow(
        self, workflow, context: ExecutionContext
    ) -> Dict[str, Any]:
        """Execute sync-only workflow in thread pool."""
        logger.debug("Executing sync-only workflow")

        # Use parent's sync execution but wrap in async
        loop = asyncio.get_event_loop()

        def sync_execute():
            # Convert context back to inputs for sync execution
            return self._execute_sync_workflow_internal(workflow, context.variables)

        result = await loop.run_in_executor(self.thread_pool, sync_execute)

        # Wrap result in expected format
        return {
            "results": result,
            "errors": {},
            "execution_times": {},
            "total_duration": time.time() - context.start_time,
            "metrics": context.metrics,
        }

    def _execute_sync_workflow_internal(
        self, workflow, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Internal sync workflow execution."""
        # Use parent's synchronous execution logic
        # This is a simplified version - in practice, you'd call the parent's method
        results = {}

        try:
            execution_order = list(nx.topological_sort(workflow.graph))
        except nx.NetworkXError as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e

        node_outputs = {}

        for node_id in execution_order:
            node_instance = workflow._node_instances.get(node_id)
            if not node_instance:
                raise WorkflowExecutionError(f"Node instance '{node_id}' not found")

            # Prepare inputs (simplified)
            node_inputs = self._prepare_sync_node_inputs(
                workflow, node_id, node_outputs, inputs
            )

            # Execute node
            try:
                result = node_instance.execute(**node_inputs)
                results[node_id] = result
                node_outputs[node_id] = result
            except Exception as e:
                raise WorkflowExecutionError(
                    f"Node '{node_id}' execution failed: {e}"
                ) from e

        return results

    def _prepare_sync_node_inputs(
        self,
        workflow,
        node_id: str,
        node_outputs: Dict[str, Any],
        context_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare inputs for sync node execution."""
        inputs = context_inputs.copy()

        # Add outputs from predecessor nodes using proper connection mapping
        for predecessor in workflow.graph.predecessors(node_id):
            if predecessor in node_outputs:
                # Use the actual connection mapping if available
                edge_data = workflow.graph.get_edge_data(predecessor, node_id)
                if edge_data and "mapping" in edge_data:
                    # Handle new graph format with mapping
                    mapping = edge_data["mapping"]
                    source_data = node_outputs[predecessor]

                    for source_path, target_param in mapping.items():
                        if source_path == "result":
                            # Source path is 'result' - use the entire source data
                            inputs[target_param] = source_data
                        elif "." in source_path and isinstance(source_data, dict):
                            # Navigate dotted path (e.g., "result.data" or "nested.field")
                            path_parts = source_path.split(".")

                            # Special case: if path starts with "result." and source_data doesn't have "result" key,
                            # try stripping "result." since AsyncPythonCodeNode returns direct dict
                            if (
                                path_parts[0] == "result"
                                and "result" not in source_data
                                and len(path_parts) > 1
                            ):
                                # Try the remaining path without "result"
                                remaining_path = ".".join(path_parts[1:])
                                if remaining_path in source_data:
                                    inputs[target_param] = source_data[remaining_path]
                                    continue
                                else:
                                    # Try navigating remaining path parts
                                    path_parts = path_parts[1:]

                            current_data = source_data
                            # Navigate through each part of the path
                            for part in path_parts:
                                if (
                                    isinstance(current_data, dict)
                                    and part in current_data
                                ):
                                    current_data = current_data[part]
                                else:
                                    current_data = None
                                    break
                            inputs[target_param] = current_data
                        elif (
                            isinstance(source_data, dict) and source_path in source_data
                        ):
                            # Direct key access
                            inputs[target_param] = source_data[source_path]
                        else:
                            # Fallback - use source data directly
                            inputs[target_param] = source_data
                else:
                    # Fallback to legacy behavior if no mapping
                    inputs[f"{predecessor}_output"] = node_outputs[predecessor]

        return inputs

    async def _execute_node_async(
        self,
        workflow,
        node_id: str,
        tracker: AsyncExecutionTracker,
        context: ExecutionContext,
    ) -> None:
        """Execute a single async node."""
        start_time = time.time()

        async with self.execution_semaphore:
            try:
                node_instance = workflow._node_instances.get(node_id)
                if not node_instance:
                    raise WorkflowExecutionError(f"Node instance '{node_id}' not found")

                # Prepare inputs
                inputs = await self._prepare_async_node_inputs(
                    workflow, node_id, tracker, context
                )

                # Execute async node
                if isinstance(node_instance, AsyncNode):
                    # Pass resource registry if available
                    if context.resource_registry:
                        result = await node_instance.async_run(
                            resource_registry=context.resource_registry, **inputs
                        )
                    else:
                        result = await node_instance.async_run(**inputs)
                else:
                    # Shouldn't happen in fully async workflow, but handle gracefully
                    result = await self._execute_sync_node_in_thread(
                        node_instance, inputs
                    )

                execution_time = time.time() - start_time
                await tracker.record_result(node_id, result, execution_time)

                logger.debug(f"Node '{node_id}' completed in {execution_time:.2f}s")

            except Exception as e:
                execution_time = time.time() - start_time
                await tracker.record_error(node_id, e)
                logger.error(
                    f"Node '{node_id}' failed after {execution_time:.2f}s: {e}"
                )
                raise WorkflowExecutionError(
                    f"Node '{node_id}' execution failed: {e}"
                ) from e

    async def _execute_sync_node_async(
        self,
        workflow,
        node_id: str,
        tracker: AsyncExecutionTracker,
        context: ExecutionContext,
    ) -> None:
        """Execute a sync node in thread pool."""
        start_time = time.time()

        async with self.execution_semaphore:
            try:
                node_instance = workflow._node_instances.get(node_id)
                if not node_instance:
                    raise WorkflowExecutionError(f"Node instance '{node_id}' not found")

                # Prepare inputs
                inputs = await self._prepare_async_node_inputs(
                    workflow, node_id, tracker, context
                )

                # Execute sync node in thread pool
                result = await self._execute_sync_node_in_thread(node_instance, inputs)

                execution_time = time.time() - start_time
                await tracker.record_result(node_id, result, execution_time)

                logger.debug(
                    f"Sync node '{node_id}' completed in {execution_time:.2f}s"
                )

            except Exception as e:
                execution_time = time.time() - start_time
                await tracker.record_error(node_id, e)
                logger.error(
                    f"Sync node '{node_id}' failed after {execution_time:.2f}s: {e}"
                )
                raise WorkflowExecutionError(
                    f"Sync node '{node_id}' execution failed: {e}"
                ) from e

    async def _execute_sync_node_in_thread(
        self, node_instance: Node, inputs: Dict[str, Any]
    ) -> Any:
        """Execute sync node in thread pool."""
        loop = asyncio.get_event_loop()

        def execute_sync():
            return node_instance.execute(**inputs)

        return await loop.run_in_executor(self.thread_pool, execute_sync)

    async def _prepare_async_node_inputs(
        self,
        workflow,
        node_id: str,
        tracker: AsyncExecutionTracker,
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Prepare inputs for async node execution."""
        inputs = context.variables.copy()

        # Add outputs from predecessor nodes
        for predecessor in workflow.graph.predecessors(node_id):
            if predecessor in tracker.node_outputs:
                # Use the actual connection mapping if available
                edge_data = workflow.graph.get_edge_data(predecessor, node_id)
                if edge_data and "mapping" in edge_data:
                    # Handle new graph format with mapping
                    mapping = edge_data["mapping"]
                    source_data = tracker.node_outputs[predecessor]

                    for source_path, target_param in mapping.items():
                        if source_path == "result":
                            # Source path is 'result' - use the entire source data
                            inputs[target_param] = source_data
                        elif "." in source_path and isinstance(source_data, dict):
                            # Navigate dotted path (e.g., "result.data" or "nested.field")
                            path_parts = source_path.split(".")

                            # Special case: if path starts with "result." and source_data doesn't have "result" key,
                            # try stripping "result." since AsyncPythonCodeNode returns direct dict
                            if (
                                path_parts[0] == "result"
                                and "result" not in source_data
                                and len(path_parts) > 1
                            ):
                                # Try the remaining path without "result"
                                remaining_path = ".".join(path_parts[1:])
                                if remaining_path in source_data:
                                    inputs[target_param] = source_data[remaining_path]
                                    continue
                                else:
                                    # Try navigating remaining path parts
                                    path_parts = path_parts[1:]

                            current_data = source_data
                            # Navigate through each part of the path
                            for part in path_parts:
                                if (
                                    isinstance(current_data, dict)
                                    and part in current_data
                                ):
                                    current_data = current_data[part]
                                else:
                                    current_data = None
                                    break
                            inputs[target_param] = current_data
                        elif (
                            isinstance(source_data, dict) and source_path in source_data
                        ):
                            # Direct key access
                            inputs[target_param] = source_data[source_path]
                        else:
                            # Fallback - use source data directly
                            inputs[target_param] = source_data
                elif edge_data and "connections" in edge_data:
                    # Handle legacy connection format
                    connections = edge_data["connections"]
                    for connection in connections:
                        source_path = connection.get("source_path", "result")
                        target_param = connection.get(
                            "target_param", f"{predecessor}_output"
                        )

                        # Extract data using source path
                        source_data = tracker.node_outputs[predecessor]
                        if source_path != "result" and isinstance(source_data, dict):
                            # Navigate the path (e.g., "result.data")
                            path_parts = source_path.split(".")
                            current_data = source_data
                            for part in path_parts:
                                if (
                                    isinstance(current_data, dict)
                                    and part in current_data
                                ):
                                    current_data = current_data[part]
                                else:
                                    current_data = None
                                    break
                            inputs[target_param] = current_data
                        else:
                            inputs[target_param] = source_data
                else:
                    # Default behavior - use predecessor output directly
                    inputs[f"{predecessor}_output"] = tracker.node_outputs[predecessor]

        return inputs

    async def cleanup(self) -> None:
        """Clean up runtime resources."""
        logger.info("Cleaning up AsyncLocalRuntime")

        # Clean up thread pool
        self.thread_pool.shutdown(wait=True)

        # Clean up resource registry if owned
        if self.resource_registry:
            await self.resource_registry.cleanup()

        logger.info("AsyncLocalRuntime cleanup complete")

    def __del__(self):
        """Cleanup on deletion."""
        try:
            # Schedule cleanup if event loop is available
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.cleanup())
        except Exception:
            # If no event loop, just shutdown thread pool
            if hasattr(self, "thread_pool"):
                self.thread_pool.shutdown(wait=False)

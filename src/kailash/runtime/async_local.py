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
import os
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
    """
    Context passed through workflow execution with resource access.

    Enhanced with production features:
    - Connection lifecycle management
    - Task tracking and cancellation
    - Resource usage monitoring
    - Cleanup guarantees
    """

    def __init__(self, resource_registry: Optional[ResourceRegistry] = None):
        self.resource_registry = resource_registry
        self.variables: Dict[str, Any] = {}
        self.metrics = ExecutionMetrics()
        self.start_time = time.time()
        self._weak_refs: Dict[str, weakref.ref] = {}

        # Connection lifecycle (P0 Component 1: Connection Lifecycle Management)
        self.connections: Dict[str, Any] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}

        # Task tracking (P0 Component 1: Task Cancellation)
        self.tasks: List[asyncio.Task] = []
        self._tasks_lock = asyncio.Lock()

        # Cleanup state
        self._cleaned_up = False

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

    async def acquire_connections(self) -> None:
        """
        Acquire database connections for workflow execution.

        P0 Component 1: Explicit connection acquisition.
        """
        # Placeholder for future connection pooling integration
        # Currently no explicit acquisition needed as connections are lazy
        logger.debug("Connection acquisition (placeholder for future pooling)")

    async def release_connections(self) -> None:
        """
        Release all database connections.

        P0 Component 1: Connection cleanup in finally blocks.
        """
        if not self.connections:
            return

        logger.debug(f"Releasing {len(self.connections)} connections")

        for conn_id, conn in list(self.connections.items()):
            try:
                if hasattr(conn, "close"):
                    await conn.close()
                elif hasattr(conn, "disconnect"):
                    await conn.disconnect()
                logger.debug(f"Released connection: {conn_id}")
            except Exception as e:
                logger.warning(f"Error releasing connection {conn_id}: {e}")

        self.connections.clear()

    def get_connection_state(self) -> Dict[str, Any]:
        """
        Get current connection state.

        P0 Component 1: Connection state tracking.

        Returns:
            Dictionary with connection state information
        """
        return {
            "connection_count": len(self.connections),
            "connections": list(self.connections.keys()),
            "active": not self._cleaned_up,
        }

    async def cancel_all_tasks(self) -> None:
        """
        Cancel all running tasks gracefully.

        P0 Component 1: Task cancellation.
        """
        if not self.tasks:
            return

        logger.info(f"Cancelling {len(self.tasks)} running tasks")

        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for cancellation to complete
        results = await asyncio.gather(*self.tasks, return_exceptions=True)

        # Log any errors (besides CancelledError)
        for i, result in enumerate(results):
            if isinstance(result, Exception) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.warning(f"Task {i} raised error during cancellation: {result}")

        logger.info("All tasks cancelled successfully")

    async def cleanup(self) -> None:
        """
        Cleanup all resources (idempotent).

        P0 Component 1: Cleanup guarantees.
        Safe to call multiple times.
        """
        if self._cleaned_up:
            logger.debug("ExecutionContext already cleaned up, skipping")
            return

        logger.debug("Cleaning up ExecutionContext")

        try:
            # Cancel running tasks first
            await self.cancel_all_tasks()
        except Exception as e:
            logger.warning(f"Error cancelling tasks during cleanup: {e}")

        try:
            # Release connections
            await self.release_connections()
        except Exception as e:
            logger.warning(f"Error releasing connections during cleanup: {e}")

        self._cleaned_up = True
        logger.debug("ExecutionContext cleanup complete")

    # Context manager support (P0 Component 1: Connection Lifecycle)
    async def __aenter__(self):
        """Enter async context manager."""
        await self.acquire_connections()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        await self.cleanup()
        return False


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

    Extends LocalRuntime with advanced async execution capabilities while
    inheriting all enterprise features through shared mixin architecture.

    Inherits from:
        LocalRuntime: Provides 100% feature parity with sync runtime
            ├─ BaseRuntime: Core runtime foundation and configuration
            ├─ CycleExecutionMixin: Cyclic workflow execution delegation
            ├─ ValidationMixin: Workflow validation and contract checking
            └─ ConditionalExecutionMixin: Conditional execution and branching logic

    Async-Specific Extensions:
        - WorkflowAnalyzer: Analyzes workflows for optimization opportunities
        - ExecutionContext: Async context with integrated resource access
        - Level-based parallel execution: Executes independent nodes concurrently
        - Semaphore-based concurrency control: Limits concurrent node execution
        - Thread pool for sync nodes: Executes sync nodes without blocking async loop
        - Advanced performance tracking: Detailed metrics collection

    Execution Strategies:
        The runtime automatically selects the optimal execution strategy:
        - Pure async: All nodes are async (fastest, full concurrency)
        - Mixed: Combination of sync and async nodes (balanced)
        - Sync in thread pool: All sync nodes (compatibility mode)

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
        execution_timeout: Optional[int] = None,
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
            execution_timeout: Workflow execution timeout in seconds (default: 300 or DATAFLOW_EXECUTION_TIMEOUT env var)
            **kwargs: Additional arguments passed to LocalRuntime
        """
        # Ensure async is enabled
        kwargs["enable_async"] = True
        super().__init__(**kwargs)

        self.resource_registry = resource_registry
        self.max_concurrent_nodes = max_concurrent_nodes
        self.enable_analysis = enable_analysis
        self.enable_profiling = enable_profiling

        # P0 Component 1: Timeout Protection
        # Priority: execution_timeout param > DATAFLOW_EXECUTION_TIMEOUT env var > 300s default
        if execution_timeout is not None:
            self.execution_timeout = execution_timeout
        else:
            # Try to read from environment variable
            env_timeout = os.getenv("DATAFLOW_EXECUTION_TIMEOUT")
            if env_timeout:
                try:
                    self.execution_timeout = int(env_timeout)
                    logger.info(
                        f"Using DATAFLOW_EXECUTION_TIMEOUT={self.execution_timeout}s from environment"
                    )
                except ValueError:
                    logger.warning(
                        f"Invalid DATAFLOW_EXECUTION_TIMEOUT='{env_timeout}', using default 300s"
                    )
                    self.execution_timeout = 300
            else:
                self.execution_timeout = 300  # 5 minute default

        # Workflow analyzer
        self.analyzer = (
            WorkflowAnalyzer(enable_profiling=enable_profiling)
            if enable_analysis
            else None
        )

        # Thread pool for sync node execution
        self.thread_pool = ThreadPoolExecutor(max_workers=thread_pool_size)

        # P0-7 FIX: Don't create event loop or semaphore in __init__
        # Will be lazily initialized during execute_workflow_async() execution
        # This prevents race conditions where __init__ runs outside async context
        self._semaphore = None
        self._max_concurrent = max_concurrent_nodes

        logger.info(
            f"AsyncLocalRuntime initialized with max_concurrent_nodes={max_concurrent_nodes}, "
            f"execution_timeout={self.execution_timeout}s"
        )

    @property
    def execution_semaphore(self) -> asyncio.Semaphore:
        """
        Lazily create execution semaphore when accessed.

        P0-7 FIX: Semaphore must be created in async context (with running event loop).
        Creating in __init__ causes race conditions in FastAPI/Docker deployments.
        """
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
            logger.debug(
                f"Execution semaphore created with limit={self._max_concurrent}"
            )
        return self._semaphore

    def execute(
        self,
        workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Execute workflow without creating threads (Docker-safe).

        This override prevents the parent's threading-based execution that causes
        Docker file descriptor issues. Uses pure async execution via asyncio.run
        or returns the async task if already in an event loop.

        Args:
            workflow: Workflow to execute
            task_manager: Optional task manager for tracking
            parameters: Input parameters for the workflow

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            RuntimeError: If called from async context (use execute_workflow_async instead)
        """
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # If we get here, we're in an event loop - can't use asyncio.run()
            # User should call execute_workflow_async() instead
            raise RuntimeError(
                "AsyncLocalRuntime.execute() called from async context. "
                "Use 'await runtime.execute_workflow_async(workflow, inputs)' instead. "
                "This prevents thread creation which causes Docker/FastAPI deadlocks."
            )
        except RuntimeError as e:
            # Check if this is the error we just raised or no-loop error
            if "async context" in str(e):
                # Our error - re-raise it
                raise
            # Otherwise it's the "no running loop" error - proceed with asyncio.run()
            inputs = parameters if parameters else {}
            result_dict = asyncio.run(
                self.execute_workflow_async(workflow, inputs=inputs)
            )

            # Extract results and generate run_id for compatibility
            results = result_dict.get("results", result_dict)
            run_id = result_dict.get("run_id", None)

            return (results, run_id)

    async def execute_async(
        self,
        workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Execute workflow asynchronously (for LocalRuntime compatibility).

        This method provides compatibility with LocalRuntime's execute_async()
        interface while using AsyncLocalRuntime's execution engine.

        Args:
            workflow: Workflow to execute
            task_manager: Optional task manager for tracking
            parameters: Input parameters for the workflow

        Returns:
            Tuple of (results dict, run_id)
        """
        inputs = parameters if parameters else {}
        result_dict = await self.execute_workflow_async(workflow, inputs=inputs)

        # Extract results and generate run_id for compatibility
        results = result_dict.get("results", result_dict)
        run_id = result_dict.get("run_id", None)

        return (results, run_id)

    async def execute_workflow_async(
        self,
        workflow,
        inputs: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Execute workflow with native async support and production safeguards.

        P0 Component 1 Features:
        - Timeout protection (configurable via execution_timeout)
        - Connection lifecycle management
        - Task cancellation on timeout
        - Cleanup guarantees

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
            Tuple of (results dict, run_id) - For compatibility with tests
            - results: Dictionary mapping node_id -> node output
            - run_id: Unique execution identifier

        Note:
            Returns tuple for compatibility with LocalRuntime.execute() pattern.
            Existing tests may expect dict - use results, run_id = await execute_workflow_async()

        Raises:
            asyncio.TimeoutError: If execution exceeds configured timeout
            WorkflowExecutionError: If execution fails
        """
        start_time = time.time()

        # Generate run_id for tracking (consistent with LocalRuntime)
        run_id = f"run_{int(time.time() * 1000)}"

        # Create execution context
        if context is None:
            context = ExecutionContext(resource_registry=self.resource_registry)

        # Add inputs to context
        context.variables.update(inputs)

        try:
            # P0 Component 1: Timeout Protection
            # Wrap execution with timeout if configured
            if self.execution_timeout and self.execution_timeout > 0:
                logger.debug(f"Executing with timeout={self.execution_timeout}s")
                tracker_result = await asyncio.wait_for(
                    self._execute_workflow_internal(workflow, inputs, context, run_id),
                    timeout=self.execution_timeout,
                )
            else:
                tracker_result = await self._execute_workflow_internal(
                    workflow, inputs, context, run_id
                )

            # Update total execution time
            total_time = time.time() - start_time
            context.metrics.total_duration = total_time

            logger.info(f"Workflow execution completed in {total_time:.2f}s")

            # Extract plain results dict
            # Conditional approach (skip_branches mode) returns plain dict, other methods return tracker wrapper
            if (
                self._has_conditional_patterns(workflow)
                and self.conditional_execution == "skip_branches"
            ):
                results = (
                    tracker_result  # Already plain dict from conditional execution
                )
            else:
                results = (
                    tracker_result.get("results", {})
                    if isinstance(tracker_result, dict)
                    else tracker_result
                )

            # P0 Component 1: Return tuple (results, run_id) for consistency
            # This matches LocalRuntime.execute() return structure
            return (results, run_id)

        except asyncio.TimeoutError:
            # P0 Component 1: Task cancellation on timeout
            logger.error(f"Workflow execution timeout after {self.execution_timeout}s")
            context.metrics.error_count += 1
            # Cancel running tasks
            await context.cancel_all_tasks()
            raise  # Re-raise TimeoutError

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            context.metrics.error_count += 1
            raise WorkflowExecutionError(f"Async execution failed: {e}") from e

        finally:
            # P0 Component 1: Cleanup guarantees
            # Always cleanup connections and resources
            try:
                await context.cleanup()
            except Exception as cleanup_error:
                logger.warning(f"Error during context cleanup: {cleanup_error}")

    async def _execute_workflow_internal(
        self, workflow, inputs: Dict[str, Any], context: ExecutionContext, run_id: str
    ):
        """
        Internal workflow execution (extracted for timeout wrapping).

        P0 Component 1: Separated from execute_workflow_async to enable
        timeout protection via asyncio.wait_for().
        """
        # Check for conditional workflow with skip_branches mode
        # Only use conditional execution approach if skip_branches is enabled
        if (
            self._has_conditional_patterns(workflow)
            and self.conditional_execution == "skip_branches"
        ):
            logger.info(
                "Conditional workflow with skip_branches mode detected, using conditional execution"
            )
            # Use inherited conditional execution from ConditionalExecutionMixin
            tracker_result = await self._execute_conditional_approach(
                workflow=workflow,
                parameters=inputs,
                task_manager=None,
                run_id=run_id,
                workflow_context=None,
            )
        else:
            # Regular execution path
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
                tracker_result = await self._execute_fully_async_workflow(
                    workflow, context, execution_plan
                )
            elif execution_plan and execution_plan.has_async_nodes:
                tracker_result = await self._execute_mixed_workflow(
                    workflow, context, execution_plan
                )
            else:
                tracker_result = await self._execute_sync_workflow(workflow, context)

        return tracker_result

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

            # CONDITIONAL EXECUTION: Skip nodes that only receive None inputs from conditional routing
            # Uses shared mixin method (ConditionalExecutionMixin._should_skip_conditional_node)
            # Pass results dict for transitive dependency checking
            if self._should_skip_conditional_node(
                workflow, node_id, node_inputs, results
            ):
                logger.info(
                    f"Skipping node {node_id} - all conditional inputs are None"
                )
                results[node_id] = None
                node_outputs[node_id] = None
                continue

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
        """Prepare inputs for sync node execution with proper parameter scoping."""

        # Get all node IDs for filtering
        node_ids_in_graph = set(workflow.graph.nodes())

        # Start with empty inputs (not copying all variables)
        inputs = {}

        # Filter and unwrap parameters from context_inputs
        for key, value in context_inputs.items():
            if key == node_id:
                # ✅ FIX: Unwrap node-specific parameters
                if isinstance(value, dict):
                    inputs.update(value)
                else:
                    logger.warning(
                        f"Node-specific parameter for '{node_id}' is not a dict: {type(value)}"
                    )
            elif key not in node_ids_in_graph:
                # ✅ Include workflow-level parameters (not meant for specific nodes)
                inputs[key] = value
            # ✅ Skip parameters meant for other nodes

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

                # CONDITIONAL EXECUTION: Skip nodes that only receive None inputs from conditional routing
                # Uses shared mixin method (ConditionalExecutionMixin._should_skip_conditional_node)
                # Pass tracker.results for transitive dependency checking
                if self._should_skip_conditional_node(
                    workflow, node_id, inputs, tracker.results
                ):
                    logger.info(
                        f"Skipping node {node_id} - all conditional inputs are None"
                    )
                    await tracker.record_result(node_id, None, 0.0)
                    return

                # Execute async node
                if isinstance(node_instance, AsyncNode):
                    # Add resource registry to inputs if available
                    # (execute_async will merge node.config and validate inputs)
                    if context.resource_registry:
                        inputs["resource_registry"] = context.resource_registry

                    # BUGFIX v0.9.26: Call execute_async() instead of async_run()
                    # execute_async() merges node.config with runtime inputs (base_async.py:190)
                    # This matches LocalRuntime's pattern (local.py:1362)
                    # Previous behavior: async_run() was called directly, bypassing config merge
                    result = await node_instance.execute_async(**inputs)
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

                # CONDITIONAL EXECUTION: Skip nodes that only receive None inputs from conditional routing
                # Uses shared mixin method (ConditionalExecutionMixin._should_skip_conditional_node)
                # Pass tracker.results for transitive dependency checking
                if self._should_skip_conditional_node(
                    workflow, node_id, inputs, tracker.results
                ):
                    logger.info(
                        f"Skipping node {node_id} - all conditional inputs are None"
                    )
                    await tracker.record_result(node_id, None, 0.0)
                    return

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
        """Prepare inputs for async node execution with proper parameter scoping."""

        # Get all node IDs for filtering
        node_ids_in_graph = set(workflow.graph.nodes())

        # Start with empty inputs (not copying all variables)
        inputs = {}

        # Filter and unwrap parameters from context.variables
        for key, value in context.variables.items():
            if key == node_id:
                # ✅ FIX: Unwrap node-specific parameters
                if isinstance(value, dict):
                    inputs.update(value)
                else:
                    logger.warning(
                        f"Node-specific parameter for '{node_id}' is not a dict: {type(value)}"
                    )
            elif key not in node_ids_in_graph:
                # ✅ Include workflow-level parameters (not meant for specific nodes)
                inputs[key] = value
            # ✅ Skip parameters meant for other nodes

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
        """
        Clean up runtime resources (idempotent).

        P0-8 FIX: Enhanced cleanup with proper resource management.
        Safe to call multiple times - tracks cleanup state.

        Recommended usage with FastAPI lifespan:
            ```python
            from contextlib import asynccontextmanager
            from fastapi import FastAPI

            @asynccontextmanager
            async def lifespan(app: FastAPI):
                # Startup
                runtime = AsyncLocalRuntime()
                yield {"runtime": runtime}
                # Shutdown
                await runtime.cleanup()

            app = FastAPI(lifespan=lifespan)
            ```
        """
        # Track cleanup to make it idempotent
        if hasattr(self, "_cleaned_up") and self._cleaned_up:
            logger.debug("AsyncLocalRuntime already cleaned up, skipping")
            return

        logger.info("Cleaning up AsyncLocalRuntime resources...")

        # Clean up thread pool (if exists and not already shutdown)
        if hasattr(self, "thread_pool") and self.thread_pool:
            try:
                self.thread_pool.shutdown(wait=True)
                logger.debug("Thread pool shutdown successfully")
            except Exception as e:
                logger.warning(f"Error shutting down thread pool: {e}")
            finally:
                self.thread_pool = None

        # Clean up resource registry (if owned)
        if hasattr(self, "resource_registry") and self.resource_registry:
            try:
                await self.resource_registry.cleanup()
                logger.debug("Resource registry cleaned up")
            except Exception as e:
                logger.warning(f"Error cleaning up resource registry: {e}")

        # Clean up semaphore reference
        if hasattr(self, "_semaphore"):
            self._semaphore = None

        # Mark as cleaned up
        self._cleaned_up = True
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

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
import contextvars
import hashlib
import logging
import os
import sys
import time
import weakref
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Union

from kailash.nodes.base import Node, _get_execution_attribute
from kailash.nodes.base_async import AsyncNode
from kailash.resources import ResourceRegistry
from kailash.runtime._time_limits import (
    _TimeLimitClassifier,
    _validate_limits,
    arm_time_limits_async,
)
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.durable import (
    NodeCompletionEvent,
    _validate_force_resume_with_drift,
    build_checkpoint_key,
    check_shape_drift_or_raise,
    compute_workflow_fingerprint,
    decode_checkpoint_payload,
    encode_checkpoint_payload,
    redact_event_for_persistence,
    redacted_tracker_state_for_checkpoint,
    resolve_tenant_id,
)
from kailash.runtime.execution_tracker import ExecutionTracker
from kailash.runtime.local import (
    ContentAwareExecutionError,
    LocalRuntime,
    _ConditionalExecutionState,
)
from kailash.runtime.metrics import get_metrics_bridge
from kailash.runtime.resource_manager import (
    _exception_is,
    _is_retry_observer_failure,
    _raise_if_execution_control,
    _retry_execution_scope,
)
from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    RuntimeExecutionError,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
    WorkflowExecutionError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.utils.async_types import _is_native_awaitable
from kailash.utils.finalizer import warn_unclosed
from kailash.utils.resource_manager import (
    _await_cleanup,
    _cleanup_admit,
    _cleanup_control,
    _cleanup_observation,
    _cleanup_observe,
    _cleanup_owner,
    _CleanupOutcome,
    _current_cleanup_outcome,
    _run_resource_cleanup,
)
from kailash.utils.secure_logging import safe_exception_frames, safe_type_name

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
        self._cleanup_started = False
        self._cleanup_outcome = _CleanupOutcome()
        self._connection_cleanup: Dict[str, Dict[str, Any]] = {}
        self._task_cleanup: Dict[int, Dict[str, Any]] = {}
        self._cleanup_phases: Dict[str, Dict[str, Any]] = {}
        self._cleanup_callers: Set[asyncio.Task] = set()

        # W1: durable-execution context attached via attributes (NOT
        # ``variables``) so node-input sanitisation never sees the
        # ExecutionTracker as a "user variable".
        self._w1_workflow_fingerprint: Optional[str] = None
        self._w1_checkpoint_key: Optional[str] = None
        self._w1_tenant_id: Optional[str] = None
        self._w1_idempotency_key: Optional[str] = None
        self._w1_run_id: Optional[str] = None
        self._w1_execution_tracker: Optional["ExecutionTracker"] = None
        self._w1_cancellation_token: CancellationToken | None = None

    def set_variable(self, key: str, value: Any) -> None:
        """Set a context variable accessible to all nodes."""
        self.variables[key] = value

    def get_variable(self, key: str, default=None) -> Any:
        """Get a context variable."""
        return self.variables.get(key, default)

    async def get_resource(self, name: str) -> Any:
        """Get resource from registry."""
        self._require_active()
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
        self._require_active()
        # Placeholder for future connection pooling integration
        # Currently no explicit acquisition needed as connections are lazy
        logger.debug("Connection acquisition (placeholder for future pooling)")

    async def release_connections(self) -> None:
        """
        Release all database connections.

        P0 Component 1: Connection cleanup in finally blocks.
        """
        self._cleanup_started = True
        caller = asyncio.current_task()
        self._cleanup_callers.add(caller)
        try:
            with _cleanup_owner(_CleanupOutcome()):
                if self.connections:
                    await self._cleanup_diagnostic(
                        "connections_start",
                        lambda: logger.debug(
                            f"Releasing {len(self.connections)} connections"
                        ),
                    )
                for conn_id, conn in list(self.connections.items()):
                    request = self._connection_cleanup.get(conn_id)
                    if request is None:
                        request = self._new_cleanup_request(conn)
                        self._connection_cleanup[conn_id] = request
                    elif request["resource"] is not conn:
                        self._record_cleanup_error(
                            RuntimeError("Connection changed during retained cleanup")
                        )
                        continue

                    async def release(record, conn_id=conn_id, conn=conn):
                        missing = object()
                        callback = _get_execution_attribute(
                            conn, "close", missing, strict=True
                        )
                        if callback is missing:
                            callback = _get_execution_attribute(
                                conn, "disconnect", missing, strict=True
                            )
                        if callback is missing:
                            raise TypeError("Connection has no cleanup callback")
                        result = callback()
                        if _is_native_awaitable(result):
                            native_mro = type.__dict__["__mro__"].__get__(type(result))
                            if any(base is asyncio.Future for base in native_mro):
                                await _await_cleanup(
                                    result, on_cancel=self._record_wait_cancel
                                )
                            else:
                                await result
                        elif result is not None:
                            raise TypeError(
                                "Connection cleanup returned non-awaitable work"
                            )
                        record["operation_complete"] = True
                        if self.connections.get(conn_id) is conn:
                            del self.connections[conn_id]
                        logger.debug(f"Released connection: {conn_id}")

                    def report(e, conn_id=conn_id):
                        logger.warning(
                            f"Error releasing connection {conn_id}: {safe_exception_frames(e)}"
                        )

                    await self._run_cleanup_request(request, release, report)
                self._raise_cleanup_failure()
        finally:
            self._cleanup_callers.discard(caller)

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
            "active": not self._cleanup_started,
        }

    async def cancel_all_tasks(self) -> None:
        """
        Cancel all running tasks gracefully.

        P0 Component 1: Task cancellation.
        """
        self._cleanup_started = True
        caller = asyncio.current_task()
        self._cleanup_callers.add(caller)
        try:
            with _cleanup_owner(_CleanupOutcome()):
                targets = list(self.tasks)
                if targets:
                    await self._cleanup_diagnostic(
                        "tasks_start",
                        lambda: logger.info(
                            f"Cancelling {len(self.tasks)} running tasks"
                        ),
                    )
                # Publish each request before cancellation, and request every
                # eligible target before beginning any retained join.
                for task in targets:
                    if id(task) in self._task_cleanup:
                        continue
                    request = self._new_cleanup_request(task)
                    request["token"] = object()
                    request["requested"] = False
                    self._task_cleanup[id(task)] = request
                    try:
                        _cleanup_admit(task, asyncio.get_running_loop())
                        if task in self._cleanup_callers:
                            raise RuntimeError("Cleanup cannot cancel its active owner")
                        if not _cleanup_observe(task, asyncio.Future.done):
                            if asyncio.Task.cancelling(task) == 0:
                                request["requested"] = asyncio.Task.cancel(
                                    task, request["token"]
                                )
                    except BaseException as error:
                        request["admission_error"] = error
                        control = _cleanup_control(error)
                        if control is not None:
                            self._record_cleanup_admission(control, request["outcome"])

                for i, task in enumerate(targets):
                    request = self._task_cleanup[id(task)]

                    async def observe(record, task=task):
                        if record.get("admission_error") is not None:
                            raise record["admission_error"]
                        try:
                            result = await _await_cleanup(
                                task, on_cancel=self._record_wait_cancel
                            )
                        except BaseException as caught:
                            result = caught
                        record["operation_complete"] = _cleanup_observe(
                            task, asyncio.Future.done
                        )
                        if _exception_is(result, BaseException):
                            record["result_error"] = result
                            if record["requested"] and _exception_is(
                                result, asyncio.CancelledError
                            ):
                                values = BaseException.args.__get__(result)
                                if len(values) == 1 and values[0] is record["token"]:
                                    return
                            raise result

                    def report(result, i=i):
                        logger.warning(
                            "Task %s raised error during cancellation: %s",
                            i,
                            safe_exception_frames(result),
                        )

                    await self._run_cleanup_request(request, observe, report)
                if targets and all(
                    self._request_complete(self._task_cleanup[id(task)])
                    for task in targets
                ):
                    await self._cleanup_diagnostic(
                        "tasks_complete",
                        lambda: logger.info("All tasks cancelled successfully"),
                    )
                self._raise_cleanup_failure()
        finally:
            self._cleanup_callers.discard(caller)

    async def cleanup(self) -> None:
        """
        Cleanup all resources (idempotent).

        P0 Component 1: Cleanup guarantees.
        Safe to call multiple times.
        """
        self._cleanup_started = True
        caller = asyncio.current_task()
        self._cleanup_callers.add(caller)
        try:
            with _cleanup_owner(_CleanupOutcome()):
                if self._cleaned_up:
                    await self._cleanup_diagnostic(
                        "already_cleaned",
                        lambda: logger.debug(
                            "ExecutionContext already cleaned up, skipping"
                        ),
                    )
                    self._raise_cleanup_failure()
                    return
                await self._cleanup_diagnostic(
                    "context_start",
                    lambda: logger.debug("Cleaning up ExecutionContext"),
                )
                for name, callback, report in (
                    (
                        "cancel_tasks",
                        lambda _: self.cancel_all_tasks(),
                        lambda e: logger.warning(
                            f"Error cancelling tasks during cleanup: {safe_exception_frames(e)}"
                        ),
                    ),
                    (
                        "release_connections",
                        lambda _: self.release_connections(),
                        lambda e: logger.warning(
                            f"Error releasing connections during cleanup: {safe_exception_frames(e)}"
                        ),
                    ),
                ):
                    request = self._cleanup_phases.setdefault(
                        name, self._new_cleanup_request(self)
                    )
                    await self._run_cleanup_request(request, callback, report)
                if (
                    not self.connections
                    and all(
                        self._request_complete(r)
                        for r in self._connection_cleanup.values()
                    )
                    and all(
                        self._request_complete(r) for r in self._task_cleanup.values()
                    )
                    and all(
                        self._request_complete(self._cleanup_phases[name])
                        for name in ("cancel_tasks", "release_connections")
                    )
                ):
                    self._cleaned_up = True
                    await self._cleanup_diagnostic(
                        "context_complete",
                        lambda: logger.debug("ExecutionContext cleanup complete"),
                    )
                self._raise_cleanup_failure()
        finally:
            self._cleanup_callers.discard(caller)

    def _require_active(self) -> None:
        if self._cleanup_started:
            raise RuntimeError(
                "ExecutionContext cleanup has started; reuse is not allowed"
            )

    @staticmethod
    def _new_cleanup_request(resource):
        return {
            "resource": resource,
            "outcome": _CleanupOutcome(),
            "attempted": False,
            "task": None,
            "error": None,
            "settled": False,
            "operation_complete": False,
        }

    @staticmethod
    def _request_complete(request):
        return request["settled"] and request["operation_complete"]

    def _raise_cleanup_failure(self):
        control = self._cleanup_outcome.first(controls_only=True)
        failure = control[1] if control is not None else self._cleanup_outcome.error()
        if failure is not None:
            raise failure

    def _record_wait_cancel(self, error):
        with _cleanup_observation(error) as observation:
            if not observation.excluded:
                observation.record(self._cleanup_outcome)
            observation.snapshot(self._cleanup_outcome, controls_only=True)
            observation.publish()

    def _record_cleanup_error(self, error, outcome=None):
        if outcome is None:
            outcome = self._cleanup_outcome
        with _cleanup_observation(error) as observation:
            if not observation.excluded:
                observation.record(outcome)

    def _record_cleanup_admission(self, error, outcome):
        with _cleanup_observation(error) as observation:
            if not observation.excluded:
                observation.record(outcome)
            if observation.snapshot(outcome, controls_only=True) is not None:
                observation.publish()

    async def _run_cleanup_request(self, request, callback, report):
        detach = self._cleanup_outcome.link(request["outcome"], controls_only=True)
        owner_detach = None
        try:
            owner = _current_cleanup_outcome()
            if owner is not None:
                # Refuse an ancestor dependency before callback admission or
                # observation, using the canonical graph's cycle check.
                owner_detach = owner.link(request["outcome"], controls_only=True)
            if request["attempted"]:
                if request["task"] is not None and not request["settled"]:
                    try:
                        await _await_cleanup(
                            request["task"], on_cancel=self._record_wait_cancel
                        )
                    except BaseException as error:
                        self._record_cleanup_error(error)
                return
            request["attempted"] = True

            async def owned(_):
                request["task"] = asyncio.current_task()
                try:
                    result = callback(request)
                    if _is_native_awaitable(result):
                        await result
                    request["operation_complete"] = True
                except BaseException as error:
                    request["error"] = error
                    raise

            context = self

            class Reporter:
                def error(self, *_args):
                    error = request["error"]
                    if error is None:
                        return
                    control = _cleanup_control(error)
                    if control is not None:
                        raise control
                    try:
                        report(error)
                    except BaseException as diagnostic:
                        context._record_cleanup_error(diagnostic)
                        raise

            try:
                await _run_resource_cleanup(
                    owned,
                    request["resource"],
                    outcome=request["outcome"],
                    reporter=Reporter(),
                )
            except BaseException as error:
                self._record_cleanup_error(error)
        except BaseException as error:
            self._record_cleanup_error(error)
        finally:
            task = request["task"]
            if task is not None:
                request["settled"] = _cleanup_observe(task, asyncio.Future.done)
            try:
                if owner_detach is not None:
                    owner_detach()
            finally:
                detach()

    async def _cleanup_diagnostic(self, name, callback):
        request = self._cleanup_phases.setdefault(name, self._new_cleanup_request(self))
        await self._run_cleanup_request(
            request, lambda _: callback(), self._record_cleanup_error
        )

    # Context manager support (P0 Component 1: Connection Lifecycle)
    async def __aenter__(self):
        """Enter async context manager."""
        self._require_active()
        await self.acquire_connections()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        caller = asyncio.current_task()
        self._cleanup_callers.add(caller)
        context = self

        async def finish(_):
            try:
                await self.cleanup()
            except BaseException as error:
                context._record_cleanup_error(error)
                raise

        class Reporter:
            def error(self, *_args):
                context._raise_cleanup_failure()

        try:
            await _run_resource_cleanup(finish, self, exc_val, reporter=Reporter())
            if exc_val is None:
                self._raise_cleanup_failure()
        finally:
            self._cleanup_callers.discard(caller)
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
        .. code-block:: python

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
        self._native_loop = None
        self._close_task = None
        self._close_error = None

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

    async def _w1_emit_node_completion(
        self,
        *,
        workflow,
        node_id: str,
        node_type: str,
        result: Any,
        started_at: datetime,
        ended_at: datetime,
        context: "ExecutionContext",
        error: Optional[str] = None,
    ) -> None:
        """W1: emit a NodeCompletionEvent post-redaction.

        Persists the checkpoint blob (if checkpoint_after_each_node=True
        AND a store is configured) and dispatches the redacted event to
        every subscriber registered via ``runtime.on_node_complete``.

        The asyncio.Lock keyed by run_id serialises parallel-node saves
        so the persisted blob represents a consistent snapshot of the
        execution tracker.  Save failures WARN-log; they MUST NOT take
        down the workflow execution.
        """
        # Read W1 context stashed by execute_workflow_async.  Defensive
        # gets — when the AsyncLocalRuntime is invoked through a code
        # path that didn't go through execute_workflow_async (legacy
        # entry points), these are None and the W1 wiring is a no-op.
        wf_fp: str = getattr(context, "_w1_workflow_fingerprint", None) or ""
        ckpt_key: Optional[str] = getattr(context, "_w1_checkpoint_key", None)
        tenant_id: Optional[str] = getattr(context, "_w1_tenant_id", None)
        idempotency_key: Optional[str] = getattr(context, "_w1_idempotency_key", None)
        run_id: Optional[str] = getattr(context, "_w1_run_id", None)
        tracker: Optional[ExecutionTracker] = getattr(
            context, "_w1_execution_tracker", None
        )

        # Record into the tracker so the persisted blob includes this node.
        if tracker is not None:
            tracker.record_completion(node_id, result)

        duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        raw_outputs: Mapping[str, Any] = (
            result if isinstance(result, Mapping) else {"result": result}
        )
        event = NodeCompletionEvent(
            run_id=run_id,
            workflow_id=getattr(workflow, "workflow_id", "") or "",
            workflow_fingerprint=wf_fp,
            node_id=node_id,
            node_type=node_type,
            outputs=raw_outputs,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            error=error,
            metadata={},
        )
        classification_policy = getattr(self, "_classification_policy", None)
        redacted = redact_event_for_persistence(
            event, classification_policy=classification_policy
        )

        if (
            self._checkpoint_after_each_node
            and self._checkpoint_store is not None
            and ckpt_key is not None
            and tracker is not None
        ):
            # W6 redaction discipline: tracker.to_dict() embeds raw
            # classified node outputs in node_outputs[<node_id>].  Route
            # through the same classification-aware helper that the
            # subscriber surface uses (see redacted dispatch above) so
            # the persisted blob carries [REDACTED] / hashed-PK sentinels
            # for every classified field.  Mirrors the sync runtime fix
            # in local.py; both paths SHARE the helper from
            # kailash.runtime.durable so divergence is structurally
            # impossible.  See rules/zero-tolerance.md Rule 2 ("fake
            # redaction") and rules/dataflow-classification.md MUST
            # Rule 1 ("every mutation return-path applies redaction").
            lock_key = run_id or ckpt_key
            lock = self._get_or_create_checkpoint_lock(lock_key)
            async with lock:
                redacted_tracker_state = redacted_tracker_state_for_checkpoint(
                    tracker.to_dict(),
                    classification_policy=classification_policy,
                    workflow_id=getattr(workflow, "workflow_id", "") or "",
                    workflow_fingerprint=wf_fp,
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                )
                blob = encode_checkpoint_payload(
                    workflow_fingerprint=wf_fp,
                    tracker_state=redacted_tracker_state,
                    tenant_id=tenant_id,
                    workflow_id=getattr(workflow, "workflow_id", "") or "",
                    idempotency_key=idempotency_key,
                )
                try:
                    await self._checkpoint_store.save(ckpt_key, blob)
                except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                    raise
                except Exception as save_err:
                    _raise_if_execution_control(save_err)
                    logger.warning(
                        "durable.checkpoint.save_failed",
                        extra={
                            "node_id_hash": hashlib.sha256(
                                node_id.encode("utf-8")
                            ).hexdigest()[:8],
                            "error_type": safe_type_name(save_err),
                        },
                    )

        if self._hook_registry.subscriber_count > 0:
            await self._hook_registry.dispatch_async(redacted)

    @staticmethod
    def _validate_compatibility_controls(**controls: Any) -> None:
        """Reject LocalRuntime controls the native async engine cannot honor."""
        unsupported = [name for name, value in controls.items() if value is not None]
        if unsupported:
            raise TypeError(
                "AsyncLocalRuntime does not support execution controls: "
                + ", ".join(unsupported)
                + "; use LocalRuntime for these controls or omit them"
            )

    def execute(
        self,
        workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Any]] = None,
        cancellation_token: Any = None,
        search_attributes: Optional[Dict[str, Any]] = None,
        *,
        soft_time_limit: float | None = None,
        time_limit: float | None = None,
        **kwargs: Any,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Execute workflow without creating threads (Docker-safe).

        This override prevents the parent's threading-based execution that causes
        Docker file descriptor issues. Drives pure async execution on the owned loop
        and rejects calls made from an already-running event loop.

        Args:
            workflow: Workflow to execute
            task_manager: LocalRuntime compatibility argument; must be None.
            parameters: Input parameters for the workflow
            cancellation_token: LocalRuntime compatibility argument; must be None.
            search_attributes: LocalRuntime compatibility argument; must be None.
            kwargs: Forwarded to execute_workflow_async, including context,
                idempotency_key and force_resume_with_drift. Unsupported options
                raise TypeError before workflow execution.
            soft_time_limit: Optional advisory deadline in seconds (#912).
                Raises :class:`~kailash.sdk_exceptions.SoftTimeLimitExceeded`
                when reached; user code MAY catch and exit cleanly.
            time_limit: Optional unconditional kill deadline in seconds (#912).
                Raises :class:`~kailash.sdk_exceptions.HardTimeLimitExceeded`
                after ``time_limit + grace`` regardless of acknowledgement.

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            RuntimeError: If called from async context (use execute_workflow_async instead)
            SoftTimeLimitExceeded: If ``soft_time_limit`` elapses.
            HardTimeLimitExceeded: If ``time_limit + grace`` elapses.

        Time-Limit Example::

            from kailash.runtime.async_local import AsyncLocalRuntime
            from kailash.sdk_exceptions import SoftTimeLimitExceeded

            runtime = AsyncLocalRuntime()
            try:
                results, run_id = runtime.execute(
                    workflow.build(),
                    soft_time_limit=2.0,
                    time_limit=5.0,
                )
            except SoftTimeLimitExceeded:
                ...  # save partial work, exit cleanly
        """
        # #912 Shard 1: validate typed time-limit kwargs at the entry point.
        _validate_limits(soft_time_limit, time_limit)

        self._validate_compatibility_controls(
            task_manager=task_manager,
            cancellation_token=cancellation_token,
            search_attributes=search_attributes,
        )

        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # A synchronous driver cannot run inside an active caller loop.
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
            # Otherwise no caller loop is running; drive the owned loop directly.
            inputs = parameters if parameters else {}
            if not self._persistent_execution_lock.acquire(blocking=False):
                raise RuntimeError(
                    "AsyncLocalRuntime synchronous execution is already active"
                )
            try:
                loop = self._ensure_event_loop()
                operation = self.execute_workflow_async(
                    workflow,
                    inputs=inputs,
                    soft_time_limit=soft_time_limit,
                    time_limit=time_limit,
                    **kwargs,
                )
                try:
                    result = loop.run_until_complete(operation)
                finally:
                    operation.close()
            finally:
                self._persistent_execution_lock.release()

            # extract_workflow_async returns Tuple[Dict, str]
            if isinstance(result, tuple):
                results = result[0]
                run_id = result[1] if len(result) > 1 else None
            elif isinstance(result, dict):
                results = result.get("results", result)
                run_id = result.get("run_id", None)
            else:
                results = result
                run_id = None

            return (results, run_id)

    async def execute_async(
        self,
        workflow,
        task_manager: Optional[TaskManager] = None,
        parameters: Optional[Dict[str, Any]] = None,
        cancellation_token: Any = None,
        execution_tracker: Any = None,
        search_attributes: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Execute workflow asynchronously (for LocalRuntime compatibility).

        This method preserves LocalRuntime's tuple return interface while using
        AsyncLocalRuntime's execution engine. Non-None task_manager,
        cancellation_token, execution_tracker and search_attributes are rejected
        because this engine does not implement those execution controls.

        Args:
            workflow: Workflow to execute
            task_manager: LocalRuntime compatibility argument; must be None.
            parameters: Input parameters for the workflow
            cancellation_token: LocalRuntime compatibility argument; must be None.
            search_attributes: LocalRuntime compatibility argument; must be None.
            kwargs: Forwarded to execute_workflow_async, including context,
                idempotency_key and force_resume_with_drift. Unsupported options
                raise TypeError before workflow execution.

        Returns:
            Tuple of (results dict, run_id)
        """
        self._validate_compatibility_controls(
            task_manager=task_manager,
            cancellation_token=cancellation_token,
            execution_tracker=execution_tracker,
            search_attributes=search_attributes,
        )
        inputs = parameters if parameters else {}
        result = await self.execute_workflow_async(workflow, inputs=inputs, **kwargs)

        # execute_workflow_async returns Tuple[Dict, str]
        if isinstance(result, tuple):
            results = result[0]
            run_id = result[1] if len(result) > 1 else None
        elif isinstance(result, dict):
            results = result.get("results", result)
            run_id = result.get("run_id", None)
        else:
            results = result
            run_id = None

        return (results, run_id)

    @_retry_execution_scope
    async def execute_workflow_async(
        self,
        workflow,
        inputs: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
        *,
        idempotency_key: Optional[str] = None,
        force_resume_with_drift: bool = False,
        soft_time_limit: float | None = None,
        time_limit: float | None = None,
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
            soft_time_limit: Optional advisory deadline in seconds (#912).
                Raises :class:`~kailash.sdk_exceptions.SoftTimeLimitExceeded`
                when reached; user code MAY catch and exit cleanly.
            time_limit: Optional unconditional kill deadline in seconds (#912).
                Raises :class:`~kailash.sdk_exceptions.HardTimeLimitExceeded`
                after ``time_limit + grace``.

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
            SoftTimeLimitExceeded: If ``soft_time_limit`` elapses.
            HardTimeLimitExceeded: If ``time_limit + grace`` elapses.

        Time-Limit Example (async)::

            from kailash.runtime.async_local import AsyncLocalRuntime
            from kailash.sdk_exceptions import SoftTimeLimitExceeded

            runtime = AsyncLocalRuntime()
            try:
                results, run_id = await runtime.execute_workflow_async(
                    workflow.build(),
                    inputs={},
                    soft_time_limit=2.0,
                    time_limit=5.0,
                )
            except SoftTimeLimitExceeded:
                ...  # save partial work, exit cleanly
        """
        # #912 Shard 1: validate typed time-limit kwargs at the entry point.
        _validate_force_resume_with_drift(force_resume_with_drift)
        _validate_limits(soft_time_limit, time_limit)
        self._claim_native_loop()
        cyclic_executor = self._cycle_executor_for_attempt()

        # #912 Shard 6: arm asyncio-task-based deadlines around the
        # in-process async execution path. Mirrors the LocalRuntime
        # pattern but uses arm_time_limits_async (asyncio tasks) so the
        # timers run on the same event loop as the workflow. The
        # cancellation token is layered onto a fresh CancellationToken
        # so the timers don't poison any user-supplied token; the soft
        # timer cancels the token, and the post-completion poll raises
        # SoftTimeLimitExceeded / HardTimeLimitExceeded per Shard 2
        # invariant 5 (hard kill is non-negotiable).
        _has_time_limit = soft_time_limit is not None or time_limit is not None
        _attempt_token: CancellationToken | None = None
        cancellable = None
        if _has_time_limit:
            _attempt_token = CancellationToken()
            cancellable = arm_time_limits_async(
                _attempt_token,
                soft_time_limit=soft_time_limit,
                time_limit=time_limit,
            )

        # Timers cover preparation as well as execution. Every early context,
        # checkpoint or drift exit must finish the same owned timer tasks.
        try:
            start_time = time.time()

            # Issue #1708 W1f: canonical workflow RED (Rate/Errors/Duration) via
            # the OTel MetricsBridge, mirroring LocalRuntime.execute(). Bounded
            # {workflow.name} label only — NEVER workflow_id (the per-build UUID
            # cardinality bomb Wave 1d fixed). Recorded once, in the `finally`
            # block below, on BOTH the success and exception path.
            _metrics_bridge = get_metrics_bridge()
            _metrics_workflow_name = getattr(workflow, "name", "") or ""

            # Generate run_id for tracking (consistent with LocalRuntime)
            run_id = f"run_{int(time.time() * 1000)}"

            # Create execution context
            if context is None:
                context = ExecutionContext(resource_registry=self.resource_registry)

            # Add inputs to context
            context.variables.update(inputs)

            # CARE-017: Get effective trust context and set up propagation
            effective_trust_ctx = self._get_effective_trust_context()
            trust_token = None
            preparing_checkpoint = False
            execution_succeeded = False

            try:
                if self.enable_audit:
                    await self._log_audit_event_async(
                        "workflow_execution_start",
                        {
                            "workflow_id": workflow.workflow_id,
                            "user_context": self._serialize_user_context(),
                            "parameters": inputs,
                        },
                    )
                # Set trust context in ContextVar if available
                if effective_trust_ctx is not None:
                    from kailash.runtime.trust.context import (
                        TrustVerificationMode,
                        _runtime_trust_context,
                    )

                    trust_token = _runtime_trust_context.set(effective_trust_ctx)

                    # Verify workflow trust before execution
                    if (
                        self._trust_verification_mode != TrustVerificationMode.DISABLED
                        and self._trust_verifier is not None
                    ):
                        allowed = await self._verify_workflow_trust(
                            workflow, effective_trust_ctx
                        )
                        if not allowed:
                            raise WorkflowExecutionError(
                                "Trust verification denied workflow execution"
                            )
                preparing_checkpoint = True
                # === W1: Durable execution — shape-drift check + checkpoint context ===
                # Compute the fingerprint once, build the checkpoint key, and run
                # the shape-drift gate BEFORE any node executes.  The same
                # invariants apply here as in LocalRuntime._execute_async — the
                # per-node hot path below will emit + persist + dispatch events
                # using the values stashed onto the context.
                workflow_fingerprint = compute_workflow_fingerprint(workflow)
                tenant_id = resolve_tenant_id(self)
                checkpoint_key: Optional[str] = None
                execution_tracker: Optional[ExecutionTracker] = None
                if idempotency_key is not None:
                    checkpoint_key = build_checkpoint_key(
                        workflow_fingerprint,
                        idempotency_key,
                        inputs if isinstance(inputs, dict) else None,
                        tenant_id=tenant_id,
                    )
                    if self._checkpoint_store is not None:
                        try:
                            prior_blob = await self._checkpoint_store.load(
                                checkpoint_key
                            )
                        except Exception as load_err:  # pragma: no cover — defensive
                            _raise_if_execution_control(load_err)
                            logger.warning(
                                "durable.checkpoint.load_failed",
                                extra={"error_type": safe_type_name(load_err)},
                            )
                            prior_blob = None
                        if prior_blob is not None:
                            stored_payload = decode_checkpoint_payload(prior_blob)
                            check_shape_drift_or_raise(
                                idempotency_key=idempotency_key,
                                stored_payload=stored_payload,
                                current_fingerprint=workflow_fingerprint,
                                force_resume_with_drift=force_resume_with_drift,
                            )
                            execution_tracker = ExecutionTracker.from_dict(
                                stored_payload.get("tracker", {})
                            )

                # Stash durable-execution context as ATTRIBUTES on the
                # ExecutionContext (not ``variables``) so the per-node input
                # sanitiser never treats them as user-supplied parameters.  The
                # attribute path is initialised on every ExecutionContext (see
                # ExecutionContext.__init__) so a None default is always present.
                context._w1_workflow_fingerprint = workflow_fingerprint
                context._w1_checkpoint_key = checkpoint_key
                context._w1_tenant_id = tenant_id
                context._w1_idempotency_key = idempotency_key
                context._w1_run_id = run_id
                context._w1_cancellation_token = _attempt_token
                context._w1_execution_tracker = (
                    execution_tracker
                    if execution_tracker is not None
                    else ExecutionTracker()
                )

                preparing_checkpoint = False

                # P0 Component 1: Timeout Protection
                # Wrap execution with timeout if configured
                if self.execution_timeout and self.execution_timeout > 0:
                    logger.debug(f"Executing with timeout={self.execution_timeout}s")
                    tracker_result = await asyncio.wait_for(
                        self._execute_workflow_internal(
                            workflow,
                            inputs,
                            context,
                            run_id,
                            cyclic_executor=cyclic_executor,
                        ),
                        timeout=self.execution_timeout,
                    )
                else:
                    tracker_result = await self._execute_workflow_internal(
                        workflow,
                        inputs,
                        context,
                        run_id,
                        cyclic_executor=cyclic_executor,
                    )

                # Update total execution time
                total_time = time.time() - start_time
                context.metrics.total_duration = total_time

                logger.info(f"Workflow execution completed in {total_time:.2f}s")

                # Every internal strategy returns the tracker wrapper, including
                # conditional success and the standard conditional fallback.
                results = tracker_result.get("results", {})

                # #912 Shard 6: post-completion poll for hard-deadline-fired-
                # after-success (Shard 2 invariant 5). Even when the workflow
                # returned cleanly, the asyncio timer task may have set the
                # hard flag — the kill is non-negotiable.
                if cancellable is not None:
                    if cancellable.hard_deadline_reached:
                        raise HardTimeLimitExceeded(
                            f"workflow exceeded hard time limit "
                            f"(time_limit={cancellable.time_limit}s + "
                            f"grace_seconds={cancellable.grace_seconds}s)"
                        )
                    if (
                        _attempt_token is not None
                        and _attempt_token.is_cancelled
                        and cancellable.soft_time_limit is not None
                    ):
                        raise SoftTimeLimitExceeded(
                            f"workflow exceeded soft time limit "
                            f"(soft_time_limit={cancellable.soft_time_limit}s)"
                        )

                # P0 Component 1: Return tuple (results, run_id) for consistency
                # This matches LocalRuntime.execute() return structure
                execution_succeeded = True
                return (results, run_id)

            except asyncio.TimeoutError:
                # P0 Component 1: Task cancellation on timeout
                logger.error(
                    f"Workflow execution timeout after {self.execution_timeout}s"
                )
                context.metrics.error_count += 1
                # Cancel running tasks
                await context.cancel_all_tasks()
                raise  # Re-raise TimeoutError

            except WorkflowCancelledError as cancel_exc:
                # #912 Shard 6: classify time-limit cancellations into the
                # subclass that names the deadline. The runtime observed
                # our token cancelled and raised; if our timers were armed,
                # classify.
                context.metrics.error_count += 1
                if cancellable is not None:
                    classified = _TimeLimitClassifier(cancellable).classify(cancel_exc)
                    if classified is not cancel_exc:
                        raise classified from cancel_exc
                raise

            except (SoftTimeLimitExceeded, HardTimeLimitExceeded):
                # #912 Shard 6: typed deadline exceptions MUST propagate
                # untouched. Without this catch-and-re-raise above the
                # broad `except Exception`, the time-limit raise would
                # be swallowed and re-wrapped as WorkflowExecutionError —
                # callers could not catch the typed exception that the
                # docstring promises.
                context.metrics.error_count += 1
                raise

            except WorkflowExecutionError:
                # Re-raise WorkflowExecutionError without wrapping (includes trust verification errors)
                context.metrics.error_count += 1
                raise

            except Exception as e:
                _raise_if_execution_control(e)
                if preparing_checkpoint:
                    # Preparation errors keep their original public identity.
                    raise
                logger.error(f"Workflow execution failed: {safe_exception_frames(e)}")
                context.metrics.error_count += 1
                if _is_retry_observer_failure(e):
                    raise
                raise WorkflowExecutionError(f"Async execution failed: {e}") from e

            finally:
                if self.enable_audit:
                    audit_error = None if execution_succeeded else sys.exc_info()[1]
                    if audit_error is None:
                        await self._log_audit_event_async(
                            "workflow_execution_completed",
                            {
                                "workflow_id": workflow.workflow_id,
                                "run_id": run_id,
                                "result_summary": {
                                    key: type(value).__name__
                                    for key, value in results.items()
                                },
                            },
                        )
                    else:
                        await self._log_audit_event_async(
                            "workflow_execution_failed",
                            {
                                "workflow_id": workflow.workflow_id,
                                "error": safe_exception_frames(audit_error),
                            },
                        )
                # Issue #1708 W1f: record the canonical workflow RED triple.
                # An explicit completion flag avoids inheriting a caller's
                # handled exception through sys.exc_info() on successful sync
                # execution. All exception exits leave this flag false.
                _metrics_success = execution_succeeded
                _metrics_bridge.record_workflow_execution(
                    _metrics_workflow_name,
                    time.time() - start_time,
                    success=_metrics_success,
                )
                # CARE-017: Reset trust context token
                if trust_token is not None:
                    from kailash.runtime.trust.context import _runtime_trust_context

                    _runtime_trust_context.reset(trust_token)

                # BYOK hardening: clear credential store after execution completes
                from kailash.workflow.credentials import get_credential_store

                get_credential_store().clear()

                # P0 Component 1: Cleanup guarantees
                # Always cleanup connections and resources
                try:
                    await context.cleanup()
                except Exception as cleanup_error:
                    logger.warning(
                        f"Error during context cleanup: {safe_exception_frames(cleanup_error)}"
                    )
        finally:
            if cancellable is not None:
                await cancellable.disarm_async()

    async def _execute_workflow_internal(
        self,
        workflow,
        inputs: Dict[str, Any],
        context: ExecutionContext,
        run_id: str,
        *,
        cyclic_executor,
    ):
        """
        Internal workflow execution (extracted for timeout wrapping).

        P0 Component 1: Separated from execute_workflow_async to enable
        timeout protection via asyncio.wait_for().
        """
        if cyclic_executor is not None and workflow.has_cycles():
            results, _ = await self._execute_cyclic_workflow_async(
                workflow,
                inputs,
                None,
                run_id,
                workflow_context=None,
                cyclic_executor=cyclic_executor,
                execution_state=_ConditionalExecutionState(
                    execution_tracker=context._w1_execution_tracker,
                    cancellation_token=context._w1_cancellation_token,
                    workflow_fingerprint=context._w1_workflow_fingerprint,
                    checkpoint_key=context._w1_checkpoint_key,
                    tenant_id=context._w1_tenant_id,
                    idempotency_key=context._w1_idempotency_key,
                ),
            )
            return {"results": results}

        # Check for conditional workflow with skip_branches mode
        # Only use conditional execution approach if skip_branches is enabled
        if (
            self._has_conditional_patterns(workflow)
            and self.conditional_execution == "skip_branches"
        ):
            logger.info(
                "Conditional workflow with skip_branches mode detected, using conditional execution"
            )
            try:
                results = await self._execute_conditional_approach(
                    workflow=workflow,
                    parameters=inputs,
                    task_manager=None,
                    run_id=run_id,
                    workflow_context=None,
                    execution_state=_ConditionalExecutionState(
                        execution_tracker=context._w1_execution_tracker,
                        cancellation_token=context._w1_cancellation_token,
                        workflow_fingerprint=context._w1_workflow_fingerprint,
                        checkpoint_key=context._w1_checkpoint_key,
                        tenant_id=context._w1_tenant_id,
                        idempotency_key=context._w1_idempotency_key,
                    ),
                )
                return {"results": results}
            except (
                ContentAwareExecutionError,
                WorkflowCancelledError,
                SoftTimeLimitExceeded,
                HardTimeLimitExceeded,
            ):
                raise
            except Exception as error:
                _raise_if_execution_control(error)
                if _is_retry_observer_failure(error):
                    raise
                logger.warning(
                    "Conditional optimization failed; using standard execution: %s",
                    safe_exception_frames(error),
                )

        # Regular execution path
        # Analyze workflow if enabled
        execution_plan = None
        if self.analyzer:
            execution_plan = self.analyzer.analyze(workflow)
            logger.info(
                f"Execution plan: {execution_plan.max_concurrent_nodes} max concurrent, "
                f"{len(execution_plan.execution_levels)} levels"
            )

        # W1: when durable execution wiring is active, force the
        # node-level async path (mixed workflow) so per-node hooks
        # fire.  The sync-only fallback (``_execute_sync_workflow``)
        # bypasses ``_execute_sync_node_async`` and would silently
        # swallow every NodeCompletionEvent — exactly the orphan
        # failure mode this routing override prevents.
        w1_active = (
            self._checkpoint_after_each_node
            or self._hook_registry.subscriber_count > 0
            or getattr(context, "_w1_idempotency_key", None) is not None
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
        elif w1_active:
            # Force the mixed-workflow path so the per-node async
            # entry point fires.  When the analyzer hasn't classified
            # any nodes as async, treat them all as sync — they go
            # through _execute_sync_node_async (thread pool) which
            # IS a W1-emit caller.
            synthetic_plan = self._build_w1_sync_only_plan(workflow)
            tracker_result = await self._execute_mixed_workflow(
                workflow, context, synthetic_plan
            )
        else:
            tracker_result = await self._execute_sync_workflow(workflow, context)

        return tracker_result

    def _build_w1_sync_only_plan(self, workflow) -> "ExecutionPlan":
        """Build a synthetic ExecutionPlan that classifies every node as sync.

        Routes the workflow through ``_execute_mixed_workflow`` so the
        per-node async entry point (`_execute_sync_node_async`) fires —
        that's the only sync-node code path that calls
        ``_w1_emit_node_completion``.  Without this synthetic plan a
        pure-sync workflow under W1 wiring would bypass hook + checkpoint
        emission entirely.

        Each level groups nodes that share the same longest-path depth
        from any source.  Predecessors land in earlier levels so that
        ``_prepare_async_node_inputs`` finds their outputs in the tracker
        when the level executes.
        """
        graph = workflow.graph
        all_nodes = set(graph.nodes())
        # Compute longest-path-from-source depth per node.
        depth: Dict[str, int] = {}
        try:
            order = workflow.get_execution_order()
        except Exception:
            order = list(all_nodes)
        for node in order:
            preds = list(graph.predecessors(node))
            depth[node] = 0 if not preds else 1 + max(depth.get(p, 0) for p in preds)
        # Group nodes by depth → ExecutionLevel.
        max_depth = max(depth.values()) if depth else 0
        levels: List[ExecutionLevel] = []
        for d in range(max_depth + 1):
            level_nodes = {n for n in all_nodes if depth.get(n, 0) == d}
            if level_nodes:
                levels.append(ExecutionLevel(level=d, nodes=level_nodes))

        plan = ExecutionPlan(
            workflow_id=getattr(workflow, "workflow_id", "") or "",
            async_nodes=set(),
            sync_nodes=set(all_nodes),
            execution_levels=levels,
            required_resources=set(),
            estimated_duration=0.0,
            max_concurrent_nodes=max(1, max(len(level.nodes) for level in levels)),
        )
        return plan

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
                _raise_if_execution_control(e)
                logger.error(
                    f"Level {level.level} execution failed: {safe_exception_frames(e)}"
                )
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

        # Propagate the caller's contextvars.Context across the thread-pool
        # boundary. ``loop.run_in_executor`` does NOT copy the calling context
        # (unlike ``asyncio.to_thread``), so a ContextVar set before
        # ``execute_workflow_async`` would otherwise be invisible inside the
        # sync node's ``run()``. Snapshot in THIS (caller) frame and run the
        # dispatched callable through ``ctx.run(...)`` (#1200).
        ctx = contextvars.copy_context()
        result = await loop.run_in_executor(
            self.thread_pool, lambda: ctx.run(sync_execute)
        )

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

        # P0C-003: Use cached topological sort from Workflow
        try:
            execution_order = workflow.get_execution_order()
        except Exception as e:
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

            # CARE-039: Node-level trust verification before execution
            node_type = node_instance.__class__.__name__
            # Run trust check synchronously since we're in a sync context
            import asyncio as _asyncio

            try:
                _loop = _asyncio.get_event_loop()
                if _loop.is_running():
                    # We're inside an executor; create new loop for the check
                    import concurrent.futures

                    _check_loop = _asyncio.new_event_loop()
                    try:
                        node_trust_allowed = _check_loop.run_until_complete(
                            self._verify_node_trust(
                                node_id=node_id,
                                node_type=node_type,
                                trust_context=self._get_effective_trust_context(),
                            )
                        )
                    finally:
                        _check_loop.close()
                else:
                    node_trust_allowed = _loop.run_until_complete(
                        self._verify_node_trust(
                            node_id=node_id,
                            node_type=node_type,
                            trust_context=self._get_effective_trust_context(),
                        )
                    )
            except RuntimeError as error:
                _raise_if_execution_control(error)
                # No event loop available, create one for the check
                _check_loop = _asyncio.new_event_loop()
                try:
                    node_trust_allowed = _check_loop.run_until_complete(
                        self._verify_node_trust(
                            node_id=node_id,
                            node_type=node_type,
                            trust_context=self._get_effective_trust_context(),
                        )
                    )
                finally:
                    _check_loop.close()

            if not node_trust_allowed:
                raise WorkflowExecutionError(
                    f"Trust verification denied execution of node '{node_id}' (type={node_type})"
                )

            # Execute node
            try:
                result = node_instance.execute(**node_inputs)
                self._check_node_result(node_id, result)
                results[node_id] = result
                node_outputs[node_id] = result
            except Exception as e:
                _raise_if_execution_control(e)
                if isinstance(
                    e, ContentAwareExecutionError
                ) or _is_retry_observer_failure(e):
                    raise
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
                        f"Node-specific parameter for '{node_id}' is not a dict: {safe_type_name(value)}"
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

    async def _w1_resume_short_circuit(
        self,
        node_id: str,
        tracker: AsyncExecutionTracker,
        context: ExecutionContext,
    ) -> bool:
        """Replay a node's checkpointed output instead of re-executing it.

        This is the async-runtime sibling of the sync LocalRuntime
        resume short-circuit (``local.py``: "Skipping node '%s'
        (restored from checkpoint)").  On a durable resume the W1
        ``ExecutionTracker`` stashed on ``context._w1_execution_tracker``
        is rehydrated from the prior checkpoint blob in
        ``execute_workflow_async``; any node whose output is already in
        that tracker has provably completed on the prior run and MUST
        NOT be re-executed — re-execution fires side effects twice and
        breaks the "exactly once on resume" guarantee that
        DurableExecutionEngine documents.

        When the node is already complete this method:

        * feeds the cached output into the per-run
          ``AsyncExecutionTracker`` via ``record_result`` so dependents
          receive the restored output through the exact same
          ``node_outputs`` path a fresh execution would populate (see
          ``_prepare_async_node_inputs``);
        * re-records completion into the W1 tracker (idempotent) so the
          checkpoint stays consistent if a later node triggers a save;
        * returns ``True`` so the caller skips ``execute_async`` and the
          ``_w1_emit_node_completion`` re-save/re-dispatch.

        Returns ``False`` (no short-circuit) when there is no W1 tracker
        or the node is not yet completed — the normal execution path.
        """
        w1_tracker: Optional[ExecutionTracker] = getattr(
            context, "_w1_execution_tracker", None
        )
        if w1_tracker is None or not w1_tracker.is_completed(node_id):
            return False

        cached_output = w1_tracker.get_output(node_id)
        self._check_node_result(node_id, cached_output)
        # Mirror the sync runtime: dependents must receive the restored
        # output exactly as a fresh execution would have produced it.
        await tracker.record_result(node_id, cached_output, 0.0)
        # Idempotent re-record keeps the W1 tracker (and any checkpoint
        # save triggered by a later, not-yet-completed node) consistent.
        w1_tracker.record_completion(node_id, cached_output)
        logger.info("Skipping node '%s' (restored from checkpoint)", node_id)
        return True

    async def _execute_node_async(
        self,
        workflow,
        node_id: str,
        tracker: AsyncExecutionTracker,
        context: ExecutionContext,
    ) -> None:
        """Execute a single async node."""
        start_time = time.time()
        node_started_at = datetime.now(UTC)
        node_instance = None

        async with self.execution_semaphore:
            node_primary = None
            try:
                try:
                    # === W1: resume short-circuit ===
                    # On a durable resume, skip nodes already completed on the
                    # prior run and replay their checkpointed output.  Mirrors
                    # the sync LocalRuntime gate.
                    if await self._w1_resume_short_circuit(node_id, tracker, context):
                        return

                    node_instance = workflow._node_instances.get(node_id)
                    if not node_instance:
                        raise WorkflowExecutionError(
                            f"Node instance '{node_id}' not found"
                        )

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

                    # CARE-039: Node-level trust verification before execution
                    node_type = node_instance.__class__.__name__
                    node_trust_allowed = await self._verify_node_trust(
                        node_id=node_id,
                        node_type=node_type,
                        trust_context=self._get_effective_trust_context(),
                    )
                    if not node_trust_allowed:
                        raise WorkflowExecutionError(
                            f"Trust verification denied execution of node '{node_id}' (type={node_type})"
                        )

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

                    self._check_node_result(node_id, result)
                    execution_time = time.time() - start_time
                    await tracker.record_result(node_id, result, execution_time)

                    # === W1: emit checkpoint + dispatch hook event ===
                    await self._w1_emit_node_completion(
                        workflow=workflow,
                        node_id=node_id,
                        node_type=node_instance.__class__.__name__,
                        result=result,
                        started_at=node_started_at,
                        ended_at=datetime.now(UTC),
                        context=context,
                        error=None,
                    )

                    logger.debug(f"Node '{node_id}' completed in {execution_time:.2f}s")

                except Exception as e:
                    _raise_if_execution_control(e)
                    execution_time = time.time() - start_time
                    await tracker.record_error(node_id, e)
                    logger.error(
                        f"Node '{node_id}' failed after {execution_time:.2f}s: {safe_exception_frames(e)}"
                    )
                    if isinstance(
                        e, ContentAwareExecutionError
                    ) or _is_retry_observer_failure(e):
                        raise
                    raise WorkflowExecutionError(
                        f"Node '{node_id}' execution failed: {e}"
                    ) from e
            except BaseException as error:
                node_primary = error
                raise
            finally:
                cleanup_error = None

                async def cleanup_node(resource):
                    nonlocal cleanup_error
                    try:
                        _cleanup = (
                            getattr(resource, "cleanup", None) if resource else None
                        )
                        if _cleanup is not None:
                            await _cleanup()
                    except BaseException as error:
                        cleanup_error = error
                        raise

                class NodeCleanupReporter:
                    def error(self, *_args):
                        if cleanup_error is not None:
                            _raise_if_execution_control(cleanup_error)
                            logger.warning(
                                f"Error during node '{node_id}' cleanup: {safe_exception_frames(cleanup_error)}"
                            )

                await _run_resource_cleanup(
                    cleanup_node,
                    node_instance,
                    node_primary,
                    reporter=NodeCleanupReporter(),
                )

    async def _execute_sync_node_async(
        self,
        workflow,
        node_id: str,
        tracker: AsyncExecutionTracker,
        context: ExecutionContext,
    ) -> None:
        """Execute a sync node in thread pool."""
        start_time = time.time()
        node_started_at = datetime.now(UTC)

        async with self.execution_semaphore:
            try:
                # === W1: resume short-circuit ===
                # On a durable resume, skip nodes already completed on the
                # prior run and replay their checkpointed output.  Mirrors
                # the sync LocalRuntime gate.
                if await self._w1_resume_short_circuit(node_id, tracker, context):
                    return

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

                # CARE-039: Node-level trust verification before execution
                node_type = node_instance.__class__.__name__
                node_trust_allowed = await self._verify_node_trust(
                    node_id=node_id,
                    node_type=node_type,
                    trust_context=self._get_effective_trust_context(),
                )
                if not node_trust_allowed:
                    raise WorkflowExecutionError(
                        f"Trust verification denied execution of node '{node_id}' (type={node_type})"
                    )

                # Execute sync node in thread pool
                result = await self._execute_sync_node_in_thread(node_instance, inputs)

                self._check_node_result(node_id, result)
                execution_time = time.time() - start_time
                await tracker.record_result(node_id, result, execution_time)

                # === W1: emit checkpoint + dispatch hook event ===
                await self._w1_emit_node_completion(
                    workflow=workflow,
                    node_id=node_id,
                    node_type=node_instance.__class__.__name__,
                    result=result,
                    started_at=node_started_at,
                    ended_at=datetime.now(UTC),
                    context=context,
                    error=None,
                )

                logger.debug(
                    f"Sync node '{node_id}' completed in {execution_time:.2f}s"
                )

            except Exception as e:
                _raise_if_execution_control(e)
                execution_time = time.time() - start_time
                await tracker.record_error(node_id, e)
                logger.error(
                    f"Sync node '{node_id}' failed after {execution_time:.2f}s: {safe_exception_frames(e)}"
                )
                if isinstance(
                    e, ContentAwareExecutionError
                ) or _is_retry_observer_failure(e):
                    raise
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

        # Propagate the caller's contextvars.Context across the thread-pool
        # boundary so a ContextVar set before execution is visible inside the
        # sync node's ``run()`` (#1200). Snapshot in this (caller) frame.
        ctx = contextvars.copy_context()
        return await loop.run_in_executor(
            self.thread_pool, lambda: ctx.run(execute_sync)
        )

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
                        f"Node-specific parameter for '{node_id}' is not a dict: {safe_type_name(value)}"
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

        Recommended usage with a web framework lifespan:

        .. code-block:: python

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
                logger.warning(
                    f"Error shutting down thread pool: {safe_exception_frames(e)}"
                )
            finally:
                self.thread_pool = None

        # Clean up resource registry (if owned)
        if hasattr(self, "resource_registry") and self.resource_registry:
            try:
                await self.resource_registry.cleanup()
                logger.debug("Resource registry cleaned up")
            except Exception as e:
                logger.warning(
                    f"Error cleaning up resource registry: {safe_exception_frames(e)}"
                )

        # Dispose connection pools
        try:
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            _clear_pools = getattr(AsyncSQLDatabaseNode, "clear_shared_pools", None)
            if _clear_pools is not None:
                # Bind the inner coroutine so we can close it in
                # ``finally`` if ``asyncio.wait_for`` raises BEFORE
                # driving it (e.g., monkeypatched wait_for that
                # swallows its coro arg, or CancelledError mid-await).
                # Without this, the orphaned coroutine emits
                # ``RuntimeWarning: coroutine 'clear_shared_pools'
                # was never awaited``. Sibling fix to LocalRuntime
                # ``_cleanup_event_loop`` and ``_execute_sync``
                # teardown paths landed for issue #942.
                #
                # Issue #1248: scope disposal to THIS runtime's loop
                # (``loop_id=id(...)``) so cleanup does not dispose pools
                # owned by another, still-live loop. ``cleanup`` runs as a
                # coroutine, so a running loop is always present here — AND
                # that running loop is the loop that created this runtime's
                # pools (the runtime executes workflows on the same loop that
                # awaits ``cleanup``, e.g. a FastAPI lifespan loop). A future
                # refactor that drives ``cleanup`` from a foreign loop would
                # break this assumption and MUST re-scope accordingly.
                _inner = _clear_pools(
                    graceful=True, loop_id=id(asyncio.get_running_loop())
                )
                try:
                    await asyncio.wait_for(_inner, timeout=5.0)
                finally:
                    _inner_close = getattr(_inner, "close", None)
                    if _inner_close is not None:
                        try:
                            _inner_close()
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(
                f"Error disposing AsyncSQL pools during cleanup: {safe_exception_frames(e)}"
            )
        try:
            from kailash.nodes.data.sql import SQLDatabaseNode

            _cleanup = getattr(SQLDatabaseNode, "cleanup_pools", None)
            if _cleanup is not None:
                _cleanup()
        except Exception as e:
            logger.warning(
                f"Error disposing SQL pools during cleanup: {safe_exception_frames(e)}"
            )

        # Clean up semaphore reference
        if hasattr(self, "_semaphore"):
            self._semaphore = None

        # Mark as cleaned up
        self._cleaned_up = True
        logger.info("AsyncLocalRuntime cleanup complete")

    def _closed_loop_can_rebind(self) -> bool:
        """Allow closed-loop reuse only when no owned async resources survive."""
        if self._native_loop is None or not self._native_loop.is_closed():
            return False
        if self.resource_registry is not None:
            return False
        if self._semaphore is not None and (
            self._semaphore._value != self._max_concurrent
            or any(not waiter.done() for waiter in (self._semaphore._waiters or ()))
        ):
            return False
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        prefix = f"{id(self._native_loop)}|"
        return not any(
            key.startswith(prefix) for key in AsyncSQLDatabaseNode._shared_pools
        )

    def _claim_native_loop(self) -> asyncio.AbstractEventLoop:
        """Bind loop-affine runtime resources before executing user work."""
        loop = asyncio.get_running_loop()
        with self._loop_lock:
            if self._ref_count <= 0 or getattr(self, "_cleaned_up", False):
                raise RuntimeError("AsyncLocalRuntime is closed; create a new runtime")
            if self._native_loop is not None and self._native_loop is not loop:
                if not self._closed_loop_can_rebind():
                    raise RuntimeError(
                        "AsyncLocalRuntime belongs to another event loop; "
                        "use a separate runtime and close each on its owning loop"
                    )
                self._semaphore = None
            self._native_loop = loop
        return loop

    async def _finish_async_close(self) -> None:
        """Finish owned resources without stopping the caller's event loop."""
        try:
            await self.cleanup()
        except BaseException as error:
            self._close_error = error
            raise
        finally:
            # An overridden or interrupted cleanup must not strand the executor.
            if self.thread_pool is not None:
                try:
                    self.thread_pool.shutdown(wait=True)
                except Exception as error:
                    logger.warning(
                        "Error shutting down thread pool: %s",
                        safe_exception_frames(error),
                    )
                finally:
                    self.thread_pool = None
            self._workflow_signals.clear()
            # An owned loop driven by sync close is retired after its driver
            # returns. Caller-owned loops are never passed to loop teardown.
            if self._persistent_loop is not asyncio.get_running_loop():
                self._cleanup_event_loop()

    def _observe_async_close(self, future) -> None:
        """Observe retained asynchronous close failures even without an awaiter."""
        try:
            future.result()
        except BaseException as error:
            logger.error(
                "AsyncLocalRuntime cleanup failed: %s", safe_exception_frames(error)
            )

    def close(self) -> None:
        """Release one reference and finish resources on their owning loop.

        Outside an active caller loop, close waits for completion. On the owning
        loop it retains a cleanup task; async context exit awaits that task.
        """
        with self._loop_lock:
            if self._ref_count <= 0:
                return
            if (
                self._ref_count == 1
                and self._native_loop is not None
                and self._native_loop.is_closed()
                and not getattr(self, "_cleaned_up", False)
            ):
                if not self._closed_loop_can_rebind():
                    raise RuntimeError(
                        "AsyncLocalRuntime owner loop closed before cleanup; "
                        "close the runtime before closing its event loop"
                    )
                self._native_loop = None
                self._semaphore = None
            self._ref_count -= 1
            if self._ref_count > 0:
                return

        if getattr(self, "_cleaned_up", False):
            self._workflow_signals.clear()
            self._cleanup_event_loop()
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        owner = self._native_loop or self._persistent_loop
        if owner is None:
            owner = current_loop or self._ensure_event_loop()
            self._native_loop = owner

        if owner is current_loop:
            self._close_task = owner.create_task(self._finish_async_close())
            self._close_task.add_done_callback(self._observe_async_close)
        elif owner.is_running():
            self._close_task = asyncio.run_coroutine_threadsafe(
                self._finish_async_close(), owner
            )
            self._close_task.add_done_callback(self._observe_async_close)
            if current_loop is None:
                self._close_task.result()
        elif current_loop is None:
            owner.run_until_complete(self._finish_async_close())
            self._cleanup_event_loop()
        else:
            # A dormant owner cannot run on this already-running thread.
            # Drive its existing loop off-thread; never migrate its resources.
            async def finish_dormant_owner():
                await asyncio.to_thread(
                    owner.run_until_complete, self._finish_async_close()
                )
                self._cleanup_event_loop()

            self._close_task = current_loop.create_task(finish_dormant_owner())
            self._close_task.add_done_callback(self._observe_async_close)

    def __del__(self, _warn=warn_unclosed) -> None:
        """Emit ResourceWarning if the runtime was not properly closed.

        Warns and RETURNS. This finalizer performs no cleanup, deliberately —
        see :meth:`LocalRuntime.__del__` for the full deadlock rationale
        (``close()`` logs, takes ``self._loop_lock``, then runs
        ``_cleanup_event_loop()``; a finalizer can fire on a thread already
        holding either lock, and neither is reentrant).

        Deliberately does NOT call ``super().__del__()``. Python does not
        chain ``__del__`` implicitly, so the parent finalizer runs only if
        invoked explicitly — and now that both are warn-only with the SAME
        ``_ref_count > 0`` predicate, chaining would emit two
        ``ResourceWarning``s for one leaked object. The previous code chained
        safely only by accident: it forced ``close()`` first, which drove
        ``_ref_count`` to 0, so the parent's guard never fired. With the
        cleanup gone that accident disappears, so the chain is removed and the
        override subsumes the parent entirely, differing only in naming
        ``async with`` as the remedy. Pinned by
        ``tests/regression/test_issue_2107_del_finalizers_no_close.py::
        test_async_local_runtime_warns_exactly_once``.

        See ``rules/patterns.md`` § "Async Resource Cleanup" and issue #2107.
        """
        ref_count = getattr(self, "_ref_count", 0)
        if ref_count > 0:
            _warn(
                self,
                f"Use 'async with {type(self).__name__}() as runtime:' "
                "or call runtime.close().",
                detail=f"ref_count={ref_count}",
            )

    async def __aenter__(self) -> "AsyncLocalRuntime":
        """Async context manager entry.

        Usage:
            async with AsyncLocalRuntime() as runtime:
                results = await runtime.execute_workflow_async(workflow, inputs)
        """
        self._claim_native_loop()
        self._is_context_managed = True
        return self

    async def aclose(self) -> None:
        """Release one reference and await final cleanup on the resource owner.

        Cleanup completes through caller cancellation before that cancellation
        is propagated. References retained with acquire() remain usable.
        """
        self.close()
        if self._close_task is not None:
            pending = self._close_task
            if isinstance(pending, asyncio.Future):
                owner = pending.get_loop()
                if owner is not asyncio.get_running_loop() and not pending.done():
                    owner_task = pending

                    async def wait_on_owner():
                        await asyncio.shield(owner_task)

                    pending = asyncio.wrap_future(
                        asyncio.run_coroutine_threadsafe(wait_on_owner(), owner)
                    )
            else:
                pending = asyncio.wrap_future(pending)
            cancellation = None
            while True:
                try:
                    await asyncio.shield(pending)
                    break
                except asyncio.CancelledError as error:
                    if pending.cancelled():
                        # shield() can discard an inner cancellation's message.
                        if isinstance(self._close_error, asyncio.CancelledError):
                            raise self._close_error
                        raise
                    if cancellation is None:
                        cancellation = error
            if cancellation is not None:
                raise cancellation

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Release the context's reference and await owned cleanup."""
        self._is_context_managed = False
        await self.aclose()

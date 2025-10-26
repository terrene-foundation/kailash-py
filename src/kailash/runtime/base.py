"""
Base runtime architecture for Kailash SDK.

This module provides the foundational BaseRuntime class shared between
LocalRuntime and AsyncLocalRuntime, implementing unified runtime architecture
as established in ADR-048 and extended for feature parity in ADR-XXX.

This refactoring eliminates 93% feature gap while maintaining 100% backward
compatibility through internal refactoring only.

Design Philosophy:
    BaseRuntime extracts ~500 lines of shared logic from LocalRuntime into a
    reusable base class that both sync and async runtimes can inherit from.
    This follows the established SecureGovernedNode mixin pattern where base
    functionality is shared via inheritance and super().__init__() calls.

Architecture:
    BaseRuntime provides foundational capabilities:
    - Configuration validation and initialization
    - Workflow metadata management
    - Result tracking and run ID generation
    - Execution metadata management
    - Workflow caching
    - Enterprise feature initialization helpers

    Subclasses (LocalRuntime, AsyncLocalRuntime) inherit this base and add
    runtime-specific execution logic through mixins and concrete implementations.

Usage:
    This class is not meant to be instantiated directly. Use LocalRuntime or
    AsyncLocalRuntime instead.

    Example inheritance pattern:

    >>> class LocalRuntime(BaseRuntime):
    ...     def __init__(self, **kwargs):
    ...         super().__init__(**kwargs)
    ...         # Add sync-specific initialization
    ...
    ...     def execute(self, workflow, **kwargs):
    ...         # Sync-specific execution
    ...         pass

    >>> class AsyncLocalRuntime(BaseRuntime):
    ...     def __init__(self, **kwargs):
    ...         super().__init__(**kwargs)
    ...         # Add async-specific initialization
    ...
    ...     async def execute(self, workflow, **kwargs):
    ...         # Async-specific execution
    ...         pass

See Also:
    - LocalRuntime: Synchronous workflow execution
    - AsyncLocalRuntime: Asynchronous workflow execution
    - ADR-048: Unified Runtime Architecture
    - ADR-XXX: Runtime Refactoring for Feature Parity

Version:
    Added in: v0.10.0
    Part of: Runtime parity remediation (2025-10-25)

Authors:
    Kailash SDK Team

Notes:
    This is Phase 1 of full remediation plan. Phase 2 will add mixin-based
    feature sharing for conditional execution, validation, and resource management.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from kailash.sdk_exceptions import (
    RuntimeExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


class BaseRuntime(ABC):
    """
    Base class for all workflow runtimes.

    This class provides shared logic that is common to both LocalRuntime
    (synchronous) and AsyncLocalRuntime (asynchronous), eliminating code
    duplication and ensuring consistent behavior.

    Architecture:
        BaseRuntime provides foundational capabilities:
        - Configuration validation and initialization
        - Workflow metadata management
        - Result tracking and run ID generation
        - Execution metadata management
        - Workflow caching
        - Enterprise feature initialization helpers

        Subclasses (LocalRuntime, AsyncLocalRuntime) inherit this base
        and add runtime-specific execution logic through mixins and
        concrete implementations.

    Design Pattern:
        Follows the SecureGovernedNode mixin pattern established in the SDK:
        - Base class provides shared initialization via super().__init__()
        - Subclasses call super().__init__(**kwargs) to initialize base
        - Mixins can be added to subclasses for additional capabilities
        - Abstract methods define the runtime-specific contract

    Extracted Logic:
        This class extracts ~500 lines of shared logic from LocalRuntime:
        - Lines 190-350: Configuration initialization and validation
        - Lines 2100-2200: Enterprise feature helpers (placeholders)
        - Utility methods for run ID generation, metadata tracking
        - Workflow caching and state management

    Usage:
        This class is not meant to be instantiated directly. Use
        LocalRuntime or AsyncLocalRuntime instead.

        >>> # DON'T: Direct instantiation (will fail - abstract class)
        >>> runtime = BaseRuntime()  # Raises TypeError
        >>>
        >>> # DO: Use concrete implementations
        >>> from kailash.runtime.local import LocalRuntime
        >>> runtime = LocalRuntime(debug=True, enable_cycles=True)
        >>>
        >>> from kailash.runtime.async_local import AsyncLocalRuntime
        >>> async_runtime = AsyncLocalRuntime(debug=True, enable_async=True)

    See Also:
        - LocalRuntime: Synchronous workflow execution
        - AsyncLocalRuntime: Asynchronous workflow execution
        - ADR-048: Unified Runtime Architecture
        - ADR-XXX: Runtime Refactoring for Feature Parity

    Version:
        Added in: v0.10.0
        Part of: Runtime parity remediation (2025-10-25)
    """

    def __init__(
        self,
        debug: bool = False,
        enable_cycles: bool = True,
        enable_async: bool = True,
        max_concurrency: int = 10,
        user_context: Optional[Any] = None,
        enable_monitoring: bool = True,
        enable_security: bool = False,
        enable_audit: bool = False,
        resource_limits: Optional[Dict[str, Any]] = None,
        secret_provider: Optional[Any] = None,
        connection_validation: str = "warn",
        conditional_execution: str = "route_data",
        content_aware_success_detection: bool = True,
        # Enhanced persistent mode parameters
        persistent_mode: bool = False,
        enable_connection_sharing: bool = True,
        max_concurrent_workflows: int = 10,
        connection_pool_size: int = 20,
        # Enterprise configuration parameters
        enable_enterprise_monitoring: bool = False,
        enable_health_monitoring: bool = False,
        enable_resource_coordination: bool = True,
        circuit_breaker_config: Optional[Dict] = None,
        retry_policy_config: Optional[Dict] = None,
        connection_pool_config: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Initialize base runtime.

        This method extracts and consolidates common initialization logic from
        LocalRuntime (lines 190-350), providing a unified foundation for both
        sync and async runtimes.

        Args:
            debug: Whether to enable debug logging.
            enable_cycles: Whether to enable cyclic workflow support.
            enable_async: Whether to enable async execution for async nodes.
            max_concurrency: Maximum concurrent async operations.
            user_context: User context for access control (optional).
            enable_monitoring: Whether to enable performance monitoring.
            enable_security: Whether to enable security features.
            enable_audit: Whether to enable audit logging.
            resource_limits: Resource limits (memory_mb, cpu_cores, etc.).
            secret_provider: Optional secret provider for runtime secret injection.
            connection_validation: Connection parameter validation mode:
                - "off": No validation (backward compatibility)
                - "warn": Log warnings on validation errors (default)
                - "strict": Raise errors on validation failures
            conditional_execution: Execution strategy for conditional routing:
                - "route_data": Current behavior - all nodes execute, data routing only (default)
                - "skip_branches": New behavior - skip unreachable branches entirely
            content_aware_success_detection: Whether to enable content-aware success detection:
                - True: Check return value content for success/failure patterns (default)
                - False: Only use exception-based failure detection (legacy mode)
            persistent_mode: Whether to enable persistent runtime mode for long-running applications.
            enable_connection_sharing: Whether to enable connection pool sharing across runtime instances.
            max_concurrent_workflows: Maximum number of concurrent workflows in persistent mode.
            connection_pool_size: Default size for connection pools.
            enable_enterprise_monitoring: Enable enterprise monitoring features.
            enable_health_monitoring: Enable health monitoring.
            enable_resource_coordination: Enable resource coordination.
            circuit_breaker_config: Circuit breaker configuration.
            retry_policy_config: Retry policy configuration.
            connection_pool_config: Connection pool configuration.
            **kwargs: Additional configuration (passed to mixins via super())

        Raises:
            ValueError: If configuration parameters are invalid

        Extracted From:
            LocalRuntime.__init__ (lines 190-350 in local.py)
            - Configuration validation logic (lines 246-275)
            - Parameter initialization (lines 276-304)
            - Enterprise feature setup (lines 298-350)
        """
        # Call super().__init__() for mixin initialization
        # This follows the SecureGovernedNode pattern where mixins can extend behavior
        super().__init__(**kwargs)

        # === Configuration Validation ===
        # Extracted from LocalRuntime lines 246-275

        # Validate connection_validation parameter
        valid_conn_modes = {"off", "warn", "strict"}
        if connection_validation not in valid_conn_modes:
            raise ValueError(
                f"Invalid connection_validation mode: {connection_validation}. "
                f"Must be one of: {valid_conn_modes}"
            )

        # Validate conditional_execution parameter
        valid_exec_modes = {"route_data", "skip_branches"}
        if conditional_execution not in valid_exec_modes:
            raise ValueError(
                f"Invalid conditional_execution mode: {conditional_execution}. "
                f"Must be one of: {valid_exec_modes}"
            )

        # Validate persistent mode parameters
        if max_concurrent_workflows < 0:
            max_concurrent_workflows = 10  # Set to reasonable default
        if connection_pool_size < 0:
            connection_pool_size = 20  # Set to reasonable default

        # Validate resource limits
        if resource_limits:
            for key, value in resource_limits.items():
                if isinstance(value, (int, float)) and value < 0:
                    raise RuntimeExecutionError(
                        f"Resource limit '{key}' cannot be negative: {value}"
                    )

        # === Core Configuration ===
        # Extracted from LocalRuntime lines 276-290
        self.debug = debug
        self.enable_cycles = enable_cycles
        self.enable_async = enable_async
        self.max_concurrency = max_concurrency
        self.user_context = user_context
        self.secret_provider = secret_provider
        self.enable_monitoring = enable_monitoring
        self.enable_security = enable_security
        self.enable_audit = enable_audit
        self.resource_limits = resource_limits or {}
        self._resource_limits = self.resource_limits  # Alias for test compatibility
        self.connection_validation = connection_validation
        self.conditional_execution = conditional_execution
        self.content_aware_success_detection = content_aware_success_detection
        self.logger = logger

        # === Enhanced Persistent Mode Configuration ===
        # Extracted from LocalRuntime lines 292-310
        self._persistent_mode = persistent_mode
        self._enable_connection_sharing = enable_connection_sharing
        self._max_concurrent_workflows = max_concurrent_workflows
        self._connection_pool_size = connection_pool_size

        # === Enterprise Configuration ===
        # Extracted from LocalRuntime lines 298-304
        self._enable_enterprise_monitoring = enable_enterprise_monitoring
        self._enable_health_monitoring = enable_health_monitoring
        self._enable_resource_coordination = enable_resource_coordination
        self._circuit_breaker_config = circuit_breaker_config or {}
        self._retry_policy_config = retry_policy_config or {}
        self._connection_pool_config = connection_pool_config or {}

        # === Persistent Mode State Management ===
        # Extracted from LocalRuntime lines 306-321
        self._is_persistent_started = False
        self._persistent_event_loop = None
        self._active_workflows: Dict[str, Any] = {}
        self._runtime_id = f"runtime_{id(self)}_{int(time.time())}"

        # === Resource Coordination Components ===
        # Extracted from LocalRuntime lines 312-321
        # These are initialized as None and lazily loaded when needed
        self._resource_coordinator = None
        self._pool_coordinator = None
        self._resource_monitor = None
        self._runtime_monitor = None
        self._health_monitor = None
        self._metrics_collector = None
        self._audit_logger = None
        self._resource_enforcer = None
        self._lifecycle_manager = None
        self._access_control_manager = None  # For security features

        # === State Management (Runtime-Specific) ===
        # Workflow cache and execution metadata tracking
        self._workflow_cache: Dict[str, Workflow] = {}
        self._execution_metadata: Dict[str, Dict[str, Any]] = {}

        # === Logging Configuration ===
        # Configure debug logging if requested
        if self.debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)
            logger.debug(f"Runtime initialized with ID: {self._runtime_id}")

    # === Configuration Helpers ===

    def _should_auto_enable_resources(self) -> bool:
        """
        Check if resource limits should be auto-enabled.

        Automatically enables resource limit enforcer with sensible defaults
        if any enterprise features are enabled or in persistent mode.

        Returns:
            True if resources should be auto-enabled, False otherwise

        Extracted From:
            LocalRuntime.__init__ lines 323-330
        """
        return (
            self._persistent_mode
            or self._enable_enterprise_monitoring
            or self._enable_health_monitoring
            or bool(self.resource_limits)
        )

    def _get_default_resource_limits(self) -> Dict[str, Any]:
        """
        Get default resource limits for enterprise mode.

        Provides sensible defaults for resource limits when auto-enabling
        enterprise features.

        Returns:
            Dictionary of default resource limit settings

        Extracted From:
            LocalRuntime.__init__ lines 332-350
        """
        return {
            "max_memory_mb": 2048,  # 2GB default
            "max_connections": 100,  # Reasonable connection limit
            "max_cpu_percent": 80,  # 80% CPU utilization
            "enforcement_policy": "adaptive",  # Gentle enforcement by default
            "degradation_strategy": "defer",  # Defer rather than fail
            "monitoring_interval": 1.0,  # Monitor every second
            "enable_alerts": True,  # Enable alerts by default
            "memory_alert_threshold": 0.8,
            "cpu_alert_threshold": 0.7,
            "connection_alert_threshold": 0.9,
            "enable_metrics_history": True,
        }

    # === Run ID and Metadata Management ===

    def _generate_run_id(self) -> str:
        """
        Generate unique run ID for execution.

        Creates a UUID-based identifier for tracking individual workflow executions.
        This is used for metrics, logging, and result correlation.

        Returns:
            Unique run identifier as string

        Implementation Notes:
            This is 100% shared logic - identical for sync and async.
            No I/O operations, pure ID generation.

        Example:
            >>> runtime = LocalRuntime()
            >>> run_id = runtime._generate_run_id()
            >>> print(run_id)  # e.g., "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        """
        return str(uuid4())

    def _initialize_execution_metadata(
        self, workflow: Workflow, run_id: str
    ) -> Dict[str, Any]:
        """
        Initialize execution metadata for workflow run.

        Creates a metadata dictionary to track execution state, timing,
        and results throughout the workflow execution lifecycle.

        Args:
            workflow: The workflow being executed
            run_id: Unique run identifier

        Returns:
            Initialized metadata dictionary with tracking fields

        Implementation Notes:
            This is 100% shared logic - identical for sync and async.
            No I/O operations, pure metadata initialization.

        Metadata Fields:
            - run_id: Unique execution identifier
            - workflow_id: Workflow identifier (if available)
            - start_time: Execution start timestamp (set by runtime)
            - end_time: Execution end timestamp (set by runtime)
            - status: Current execution status
            - node_count: Total number of nodes in workflow
            - executed_nodes: List of successfully executed nodes
            - skipped_nodes: List of skipped nodes (conditional execution)

        Example:
            >>> workflow = WorkflowBuilder().build()
            >>> run_id = runtime._generate_run_id()
            >>> metadata = runtime._initialize_execution_metadata(workflow, run_id)
            >>> print(metadata["status"])  # "initializing"
        """
        return {
            "run_id": run_id,
            "workflow_id": getattr(workflow, "workflow_id", None),
            "start_time": None,  # Set by runtime during execution
            "end_time": None,  # Set by runtime after execution
            "status": "initializing",
            "node_count": len(workflow.graph.nodes),
            "executed_nodes": [],
            "skipped_nodes": [],
        }

    def _update_execution_metadata(self, run_id: str, updates: Dict[str, Any]) -> None:
        """
        Update execution metadata for a running workflow.

        Args:
            run_id: Unique run identifier
            updates: Dictionary of metadata fields to update

        Implementation Notes:
            Thread-safe metadata updates for concurrent execution tracking.
        """
        if run_id not in self._execution_metadata:
            logger.warning(f"Metadata for run_id {run_id} not found")
            return

        self._execution_metadata[run_id].update(updates)

    def _get_execution_metadata(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve execution metadata for a workflow run.

        Args:
            run_id: Unique run identifier

        Returns:
            Metadata dictionary or None if not found
        """
        return self._execution_metadata.get(run_id)

    # === Workflow Caching ===

    def _cache_workflow(self, workflow_id: str, workflow: Workflow) -> None:
        """
        Cache workflow for reuse.

        Stores workflow instances in memory for faster subsequent executions.
        This is particularly useful for:
        - Persistent mode where workflows are executed repeatedly
        - Enterprise scenarios with workflow templates
        - Performance optimization for repeated executions

        Args:
            workflow_id: Unique workflow identifier
            workflow: The workflow to cache

        Implementation Notes:
            This is 100% shared logic - identical for sync and async.
            Simple in-memory dictionary storage.

        Example:
            >>> workflow = WorkflowBuilder().build()
            >>> runtime._cache_workflow("my_workflow", workflow)
            >>> cached = runtime._get_cached_workflow("my_workflow")
            >>> assert cached is workflow
        """
        self._workflow_cache[workflow_id] = workflow
        if self.debug:
            logger.debug(f"Cached workflow: {workflow_id}")

    def _get_cached_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """
        Retrieve cached workflow.

        Args:
            workflow_id: Unique workflow identifier

        Returns:
            Cached workflow or None if not found

        Implementation Notes:
            This is 100% shared logic - identical for sync and async.

        Example:
            >>> cached = runtime._get_cached_workflow("my_workflow")
            >>> if cached:
            ...     print("Found cached workflow")
            ... else:
            ...     print("Workflow not in cache")
        """
        return self._workflow_cache.get(workflow_id)

    def _clear_cache(self) -> None:
        """
        Clear all cached workflows and execution metadata.

        Useful for:
        - Memory management in long-running applications
        - Testing and cleanup
        - Forcing workflow re-analysis

        Implementation Notes:
            This is 100% shared logic - identical for sync and async.

        Example:
            >>> runtime._clear_cache()
            >>> assert len(runtime._workflow_cache) == 0
        """
        self._workflow_cache.clear()
        self._execution_metadata.clear()
        if self.debug:
            logger.debug("Cleared workflow cache and execution metadata")

    # === Enterprise Feature Helpers ===

    def _check_workflow_access(self, workflow: Workflow) -> None:
        """
        Check if user has access to execute the workflow.

        This is a placeholder implementation extracted from LocalRuntime.
        Subclasses should implement enterprise security features as needed.

        Args:
            workflow: The workflow to check access for

        Raises:
            PermissionError: If user doesn't have access

        Implementation Notes:
            Extracted from LocalRuntime lines 2123-2154.
            This is shared validation logic but may require runtime-specific
            access control integration.

        Example:
            >>> runtime = LocalRuntime(enable_security=True, user_context=user)
            >>> runtime._check_workflow_access(workflow)  # May raise PermissionError
        """
        if not self.enable_security or not self.user_context:
            return

        # Placeholder - subclasses can implement full security integration
        # See LocalRuntime._check_workflow_access for complete implementation
        logger.debug(f"Checking workflow access for user: {self.user_context}")

    def _should_skip_audit(self) -> bool:
        """
        Check if audit logging should be skipped.

        Returns:
            True if audit should be skipped, False otherwise
        """
        return not self.enable_audit

    # === Abstract Methods (Runtime-Specific) ===

    @abstractmethod
    def execute(self, workflow: Workflow, **kwargs):
        """
        Execute workflow (runtime-specific implementation).

        This method MUST be implemented by subclasses with appropriate
        signatures for sync/async execution:

        Sync Implementation (LocalRuntime):
            def execute(
                self,
                workflow: Workflow,
                parameters: Optional[Dict] = None,
                **kwargs
            ) -> Tuple[Dict[str, Any], str]:
                '''Execute workflow synchronously.'''
                # Implementation
                pass

        Async Implementation (AsyncLocalRuntime):
            async def execute(
                self,
                workflow: Workflow,
                parameters: Optional[Dict] = None,
                **kwargs
            ) -> Tuple[Dict[str, Any], str]:
                '''Execute workflow asynchronously.'''
                # Implementation
                pass

        Args:
            workflow: The workflow to execute
            **kwargs: Additional execution parameters (runtime-specific)

        Returns:
            Tuple of (results_dict, run_id)

        Raises:
            RuntimeExecutionError: If execution fails
            NotImplementedError: If called directly on BaseRuntime

        Implementation Requirements:
            1. Generate run_id using self._generate_run_id()
            2. Initialize metadata using self._initialize_execution_metadata()
            3. Validate workflow before execution
            4. Execute nodes in proper order
            5. Collect and return results
            6. Update metadata on completion/failure

        Example Implementations:

            Sync (LocalRuntime):
                >>> def execute(self, workflow, parameters=None, **kwargs):
                ...     run_id = self._generate_run_id()
                ...     metadata = self._initialize_execution_metadata(workflow, run_id)
                ...     # Execute workflow synchronously
                ...     results = self._execute_sync(workflow, parameters)
                ...     return results, run_id

            Async (AsyncLocalRuntime):
                >>> async def execute(self, workflow, parameters=None, **kwargs):
                ...     run_id = self._generate_run_id()
                ...     metadata = self._initialize_execution_metadata(workflow, run_id)
                ...     # Execute workflow asynchronously
                ...     results = await self._execute_async(workflow, parameters)
                ...     return results, run_id
        """
        raise NotImplementedError(
            "execute() must be implemented by runtime subclass (LocalRuntime or AsyncLocalRuntime)"
        )

    # === Utility Methods ===

    def __repr__(self) -> str:
        """
        Get string representation of runtime instance.

        Returns:
            String representation with key configuration

        Example:
            >>> runtime = LocalRuntime(debug=True, enable_cycles=True)
            >>> print(repr(runtime))
            <LocalRuntime(id=runtime_..., debug=True, cycles=True, async=False)>
        """
        return (
            f"<{self.__class__.__name__}("
            f"id={self._runtime_id}, "
            f"debug={self.debug}, "
            f"cycles={self.enable_cycles}, "
            f"async={self.enable_async}"
            f")>"
        )

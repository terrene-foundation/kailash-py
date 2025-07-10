"""Unified Runtime Engine with Enterprise Capabilities.

This module provides a unified, production-ready execution engine that seamlessly
integrates all enterprise features through the composable node architecture. It
combines sync/async execution, enterprise security, monitoring, and resource
management - all implemented through existing enterprise nodes and SDK patterns.

Examples:
    Basic workflow execution (backward compatible):

    >>> from kailash.runtime.local import LocalRuntime
    >>> runtime = LocalRuntime(debug=True, enable_cycles=True)
    >>> results, run_id = runtime.execute(workflow, parameters={"input": "data"})

    Enterprise configuration with security:

    >>> from kailash.access_control import UserContext
    >>> user_context = UserContext(user_id="user123", roles=["analyst"])
    >>> runtime = LocalRuntime(
    ...     user_context=user_context,
    ...     enable_monitoring=True,
    ...     enable_security=True
    ... )
    >>> results, run_id = runtime.execute(workflow, parameters={"data": input_data})

    Full enterprise features:

    >>> runtime = LocalRuntime(
    ...     enable_async=True,           # Async node execution
    ...     enable_monitoring=True,      # Performance tracking
    ...     enable_security=True,        # Access control
    ...     enable_audit=True,           # Compliance logging
    ...     max_concurrency=10           # Parallel execution
    ... )
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Optional

import networkx as nx

from kailash.nodes import Node
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.sdk_exceptions import (
    RuntimeExecutionError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.tracking.models import TaskMetrics
from kailash.workflow import Workflow
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor

logger = logging.getLogger(__name__)


class LocalRuntime:
    """Unified runtime with enterprise capabilities.

    This class provides a comprehensive, production-ready execution engine that
    seamlessly handles both traditional workflows and advanced cyclic patterns,
    with full enterprise feature integration through composable nodes.

    Enterprise Features (Composably Integrated):
    - Access control via existing AccessControlManager and security nodes
    - Real-time monitoring via TaskManager and MetricsCollector
    - Audit logging via AuditLogNode and SecurityEventNode
    - Resource management via enterprise monitoring nodes
    - Async execution support for AsyncNode instances
    - Performance optimization via PerformanceBenchmarkNode
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
        resource_limits: Optional[dict[str, Any]] = None,
    ):
        """Initialize the unified runtime.

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
        """
        self.debug = debug
        self.enable_cycles = enable_cycles
        self.enable_async = enable_async
        self.max_concurrency = max_concurrency
        self.user_context = user_context
        self.enable_monitoring = enable_monitoring
        self.enable_security = enable_security
        self.enable_audit = enable_audit
        self.resource_limits = resource_limits or {}
        self.logger = logger

        # Enterprise feature managers (lazy initialization)
        self._access_control_manager = None

        # Initialize cyclic workflow executor if enabled
        if enable_cycles:
            self.cyclic_executor = CyclicWorkflowExecutor()

        # Configure logging
        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        # Enterprise execution context
        self._execution_context = {
            "security_enabled": enable_security,
            "monitoring_enabled": enable_monitoring,
            "audit_enabled": enable_audit,
            "async_enabled": enable_async,
            "resource_limits": self.resource_limits,
            "user_context": user_context,
        }

    def execute(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None = None,
        parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Execute a workflow with unified enterprise capabilities.

        Args:
            workflow: Workflow to execute.
            task_manager: Optional task manager for tracking.
            parameters: Optional parameter overrides per node.

        Returns:
            Tuple of (results dict, run_id).

        Raises:
            RuntimeExecutionError: If execution fails.
            WorkflowValidationError: If workflow is invalid.
            PermissionError: If access control denies execution.
        """
        # For backward compatibility, run the async version in a sync wrapper
        try:
            # Check if we're already in an event loop
            loop = asyncio.get_running_loop()
            # If we're in an event loop, run synchronously instead
            return self._execute_sync(
                workflow=workflow, task_manager=task_manager, parameters=parameters
            )
        except RuntimeError:
            # No event loop running, safe to use asyncio.run
            return asyncio.run(
                self._execute_async(
                    workflow=workflow, task_manager=task_manager, parameters=parameters
                )
            )

    async def execute_async(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None = None,
        parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Execute a workflow asynchronously (for AsyncLocalRuntime compatibility).

        Args:
            workflow: Workflow to execute.
            task_manager: Optional task manager for tracking.
            parameters: Optional parameter overrides per node.

        Returns:
            Tuple of (results dict, run_id).

        Raises:
            RuntimeExecutionError: If execution fails.
            WorkflowValidationError: If workflow is invalid.
            PermissionError: If access control denies execution.
        """
        return await self._execute_async(
            workflow=workflow, task_manager=task_manager, parameters=parameters
        )

    def _execute_sync(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None = None,
        parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Execute workflow synchronously when already in an event loop.

        This method creates a new event loop in a separate thread to avoid
        conflicts with existing event loops. This ensures backward compatibility
        when LocalRuntime.execute() is called from within async contexts.

        Args:
            workflow: Workflow to execute.
            task_manager: Optional task manager for tracking.
            parameters: Optional parameter overrides per node.

        Returns:
            Tuple of (results dict, run_id).

        Raises:
            RuntimeExecutionError: If execution fails.
            WorkflowValidationError: If workflow is invalid.
        """
        # Create new event loop for sync execution
        import threading

        result_container = []
        exception_container = []

        def run_in_thread():
            """Run async execution in separate thread."""
            loop = None
            try:
                # Create new event loop in thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    self._execute_async(
                        workflow=workflow,
                        task_manager=task_manager,
                        parameters=parameters,
                    )
                )
                result_container.append(result)
            except Exception as e:
                exception_container.append(e)
            finally:
                if loop:
                    loop.close()

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        if exception_container:
            raise exception_container[0]

        return result_container[0]

    async def _execute_async(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None = None,
        parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        """Core async execution implementation with enterprise features.

        This method orchestrates the entire workflow execution including:
        - Security checks via AccessControlManager (if enabled)
        - Audit logging via AuditLogNode (if enabled)
        - Performance monitoring via TaskManager/MetricsCollector
        - Async node detection and execution
        - Resource limit enforcement
        - Error handling and recovery

        Args:
            workflow: Workflow to execute.
            task_manager: Optional task manager for tracking.
            parameters: Optional parameter overrides per node.

        Returns:
            Tuple of (results dict, run_id).

        Raises:
            RuntimeExecutionError: If execution fails.
            WorkflowValidationError: If workflow is invalid.
            PermissionError: If access control denies execution.
        """
        if not workflow:
            raise RuntimeExecutionError("No workflow provided")

        run_id = None

        try:
            # Enterprise Security Check: Validate user access to workflow
            if self.enable_security and self.user_context:
                self._check_workflow_access(workflow)

            # Transform workflow-level parameters if needed
            processed_parameters = self._process_workflow_parameters(
                workflow, parameters
            )

            # Validate workflow with runtime parameters (Session 061)
            workflow.validate(runtime_parameters=processed_parameters)

            # Enterprise Audit: Log workflow execution start
            if self.enable_audit:
                await self._log_audit_event_async(
                    "workflow_execution_start",
                    {
                        "workflow_id": workflow.workflow_id,
                        "user_context": self._serialize_user_context(),
                        "parameters": processed_parameters,
                    },
                )

            # Initialize enhanced tracking with enterprise context
            if task_manager is None and self.enable_monitoring:
                task_manager = TaskManager()

            if task_manager:
                try:
                    run_id = task_manager.create_run(
                        workflow_name=workflow.name,
                        metadata={
                            "parameters": processed_parameters,
                            "debug": self.debug,
                            "runtime": "unified_enterprise",
                            "enterprise_features": self._execution_context,
                            "user_context": self._serialize_user_context(),
                        },
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to create task run: {e}")
                    # Continue without tracking

            # Check for cyclic workflows and delegate accordingly
            if self.enable_cycles and workflow.has_cycles():
                self.logger.info(
                    "Cyclic workflow detected, using CyclicWorkflowExecutor"
                )
                # Use cyclic executor for workflows with cycles
                try:
                    # Pass run_id to cyclic executor if available
                    cyclic_results, cyclic_run_id = self.cyclic_executor.execute(
                        workflow, processed_parameters, task_manager, run_id
                    )
                    results = cyclic_results
                    # Update run_id if task manager is being used
                    if not run_id:
                        run_id = cyclic_run_id
                except Exception as e:
                    raise RuntimeExecutionError(
                        f"Cyclic workflow execution failed: {e}"
                    ) from e
            else:
                # Execute standard DAG workflow with enterprise features
                self.logger.info(
                    "Standard DAG workflow detected, using unified enterprise execution"
                )
                results = await self._execute_workflow_async(
                    workflow=workflow,
                    task_manager=task_manager,
                    run_id=run_id,
                    parameters=processed_parameters or {},
                )

            # Enterprise Audit: Log successful completion
            if self.enable_audit:
                await self._log_audit_event_async(
                    "workflow_execution_completed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "run_id": run_id,
                        "result_summary": {
                            k: type(v).__name__ for k, v in results.items()
                        },
                    },
                )

            # Mark run as completed
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "completed")
                except Exception as e:
                    self.logger.warning(f"Failed to update run status: {e}")

            return results, run_id

        except WorkflowValidationError:
            # Enterprise Audit: Log validation failure
            if self.enable_audit:
                await self._log_audit_event_async(
                    "workflow_validation_failed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "error": "Validation failed",
                    },
                )
            # Re-raise validation errors as-is
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(
                        run_id, "failed", error="Validation failed"
                    )
                except Exception:
                    pass
            raise
        except PermissionError as e:
            # Enterprise Audit: Log access denial
            if self.enable_audit:
                await self._log_audit_event_async(
                    "workflow_access_denied",
                    {
                        "workflow_id": workflow.workflow_id,
                        "user_context": self._serialize_user_context(),
                        "error": str(e),
                    },
                )
            # Re-raise permission errors as-is
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "failed", error=str(e))
                except Exception:
                    pass
            raise
        except Exception as e:
            # Enterprise Audit: Log execution failure
            if self.enable_audit:
                await self._log_audit_event_async(
                    "workflow_execution_failed",
                    {
                        "workflow_id": workflow.workflow_id,
                        "error": str(e),
                    },
                )
            # Mark run as failed
            if task_manager and run_id:
                try:
                    task_manager.update_run_status(run_id, "failed", error=str(e))
                except Exception:
                    pass

            # Wrap other errors in RuntimeExecutionError
            raise RuntimeExecutionError(
                f"Unified enterprise workflow execution failed: {type(e).__name__}: {e}"
            ) from e

    async def _execute_workflow_async(
        self,
        workflow: Workflow,
        task_manager: TaskManager | None,
        run_id: str | None,
        parameters: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute the workflow nodes in topological order.

        Args:
            workflow: Workflow to execute.
            task_manager: Task manager for tracking.
            run_id: Run ID for tracking.
            parameters: Parameter overrides.

        Returns:
            Dictionary of node results.

        Raises:
            WorkflowExecutionError: If execution fails.
        """
        # Get execution order
        try:
            execution_order = list(nx.topological_sort(workflow.graph))
            self.logger.info(f"Execution order: {execution_order}")
        except nx.NetworkXError as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e

        # Initialize results storage
        results = {}
        node_outputs = {}
        failed_nodes = []

        # Execute each node
        for node_id in execution_order:
            self.logger.info(f"Executing node: {node_id}")

            # Get node instance
            node_instance = workflow._node_instances.get(node_id)
            if not node_instance:
                raise WorkflowExecutionError(
                    f"Node instance '{node_id}' not found in workflow"
                )

            # Start task tracking
            task = None
            if task_manager and run_id:
                try:
                    # Get node metadata if available
                    node_metadata = {}
                    if hasattr(node_instance, "config") and isinstance(
                        node_instance.config, dict
                    ):
                        raw_metadata = node_instance.config.get("metadata", {})
                        # Convert NodeMetadata object to dict if needed
                        if hasattr(raw_metadata, "model_dump"):
                            node_metadata_dict = raw_metadata.model_dump()
                            # Convert datetime objects to strings for JSON serialization
                            if "created_at" in node_metadata_dict:
                                node_metadata_dict["created_at"] = str(
                                    node_metadata_dict["created_at"]
                                )
                            # Convert sets to lists for JSON serialization
                            if "tags" in node_metadata_dict and isinstance(
                                node_metadata_dict["tags"], set
                            ):
                                node_metadata_dict["tags"] = list(
                                    node_metadata_dict["tags"]
                                )
                            node_metadata = node_metadata_dict
                        elif isinstance(raw_metadata, dict):
                            node_metadata = raw_metadata

                    task = task_manager.create_task(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node_instance.__class__.__name__,
                        started_at=datetime.now(UTC),
                        metadata=node_metadata,
                    )
                    # Start the task
                    if task:
                        task_manager.update_task_status(
                            task.task_id, TaskStatus.RUNNING
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to create task for node '{node_id}': {e}"
                    )

            try:
                # Prepare inputs
                inputs = self._prepare_node_inputs(
                    workflow=workflow,
                    node_id=node_id,
                    node_instance=node_instance,
                    node_outputs=node_outputs,
                    parameters=parameters.get(node_id, {}),
                )

                # Update node config with parameters (Session 061: direct config update)
                {**node_instance.config, **parameters.get(node_id, {})}
                node_instance.config.update(parameters.get(node_id, {}))

                # ENTERPRISE PARAMETER INJECTION FIX: Injected parameters should override connection inputs
                # This ensures workflow parameters take precedence over connection inputs for the same parameter names
                injected_params = parameters.get(node_id, {})
                if injected_params:
                    inputs.update(injected_params)
                    if self.debug:
                        self.logger.debug(
                            f"Applied parameter injections for {node_id}: {list(injected_params.keys())}"
                        )

                if self.debug:
                    self.logger.debug(f"Node {node_id} inputs: {inputs}")

                # Execute node with unified async/sync support and metrics collection
                collector = MetricsCollector()
                with collector.collect(node_id=node_id) as metrics_context:
                    # Unified async/sync execution
                    # Validate inputs before execution
                    from kailash.utils.data_validation import DataTypeValidator

                    validated_inputs = DataTypeValidator.validate_node_input(
                        node_id, inputs
                    )

                    if self.enable_async and hasattr(node_instance, "execute_async"):
                        # Use async execution method that includes validation
                        outputs = await node_instance.execute_async(**validated_inputs)
                    else:
                        # Standard synchronous execution
                        outputs = node_instance.execute(**validated_inputs)

                # Get performance metrics
                performance_metrics = metrics_context.result()

                # Store outputs
                node_outputs[node_id] = outputs
                results[node_id] = outputs

                if self.debug:
                    self.logger.debug(f"Node {node_id} outputs: {outputs}")

                # Update task status with enhanced metrics
                if task and task_manager:
                    # Convert performance metrics to TaskMetrics format
                    task_metrics_data = performance_metrics.to_task_metrics()
                    task_metrics = TaskMetrics(**task_metrics_data)

                    # Update task with metrics
                    task_manager.update_task_status(
                        task.task_id,
                        TaskStatus.COMPLETED,
                        result=outputs,
                        ended_at=datetime.now(UTC),
                        metadata={"execution_time": performance_metrics.duration},
                    )

                    # Update task metrics separately
                    task_manager.update_task_metrics(task.task_id, task_metrics)

                self.logger.info(
                    f"Node {node_id} completed successfully in {performance_metrics.duration:.3f}s"
                )

            except Exception as e:
                failed_nodes.append(node_id)
                self.logger.error(f"Node {node_id} failed: {e}", exc_info=self.debug)

                # Update task status
                if task and task_manager:
                    task_manager.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error=str(e),
                        ended_at=datetime.now(UTC),
                    )

                # Determine if we should continue
                if self._should_stop_on_error(workflow, node_id):
                    error_msg = f"Node '{node_id}' failed: {e}"
                    if len(failed_nodes) > 1:
                        error_msg += f" (Previously failed nodes: {failed_nodes[:-1]})"

                    raise WorkflowExecutionError(error_msg) from e
                else:
                    # Continue execution but record error
                    results[node_id] = {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "failed": True,
                    }

        return results

    def _prepare_node_inputs(
        self,
        workflow: Workflow,
        node_id: str,
        node_instance: Node,
        node_outputs: dict[str, dict[str, Any]],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Prepare inputs for a node execution.

        Args:
            workflow: The workflow being executed.
            node_id: Current node ID.
            node_instance: Current node instance.
            node_outputs: Outputs from previously executed nodes.
            parameters: Parameter overrides.

        Returns:
            Dictionary of inputs for the node.

        Raises:
            WorkflowExecutionError: If input preparation fails.
        """
        inputs = {}

        # NOTE: Node configuration is handled separately in configure() call
        # Only add runtime inputs and data from connected nodes here

        # Add runtime parameters (those not used for node configuration)
        # Map specific runtime parameters for known node types
        if "consumer_timeout_ms" in parameters:
            inputs["timeout_ms"] = parameters["consumer_timeout_ms"]

        # Add other potential runtime parameters that are not configuration
        runtime_param_names = {"max_messages", "timeout_ms", "limit", "offset"}
        for param_name, param_value in parameters.items():
            if param_name in runtime_param_names:
                inputs[param_name] = param_value

        # Add connected inputs from other nodes
        for edge in workflow.graph.in_edges(node_id, data=True):
            source_node_id = edge[0]
            mapping = edge[2].get("mapping", {})

            if self.debug:
                self.logger.debug(f"Processing edge {source_node_id} -> {node_id}")
                self.logger.debug(f"  Edge data: {edge[2]}")
                self.logger.debug(f"  Mapping: {mapping}")

            if source_node_id in node_outputs:
                source_outputs = node_outputs[source_node_id]
                if self.debug:
                    self.logger.debug(
                        f"  Source outputs: {list(source_outputs.keys())}"
                    )

                # Check if the source node failed
                if isinstance(source_outputs, dict) and source_outputs.get("failed"):
                    raise WorkflowExecutionError(
                        f"Cannot use outputs from failed node '{source_node_id}'"
                    )

                # Validate source outputs before mapping
                from kailash.utils.data_validation import DataTypeValidator

                try:
                    source_outputs = DataTypeValidator.validate_node_output(
                        source_node_id, source_outputs
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Data validation failed for node '{source_node_id}': {e}"
                    )

                for source_key, target_key in mapping.items():
                    # Handle nested output access (e.g., "result.files")
                    if "." in source_key:
                        # Navigate nested structure
                        value = source_outputs
                        parts = source_key.split(".")
                        found = True

                        if self.debug:
                            self.logger.debug(f"  Navigating nested path: {source_key}")
                            self.logger.debug(f"  Starting value: {value}")

                        for i, part in enumerate(parts):
                            if isinstance(value, dict) and part in value:
                                value = value[part]
                                if self.debug:
                                    self.logger.debug(
                                        f"    Part '{part}' found, value type: {type(value)}"
                                    )
                            else:
                                # Check if it's a direct key in source_outputs (for backwards compatibility)
                                if i == 0 and source_key in source_outputs:
                                    value = source_outputs[source_key]
                                    if self.debug:
                                        self.logger.debug(
                                            f"    Found direct key '{source_key}' in source_outputs"
                                        )
                                    break
                                else:
                                    found = False
                                    if self.debug:
                                        self.logger.debug(
                                            f"  MISSING: Nested path '{source_key}' - failed at part '{part}'"
                                        )
                                        self.logger.debug(
                                            f"    Current value type: {type(value)}"
                                        )
                                        if isinstance(value, dict):
                                            self.logger.debug(
                                                f"    Available keys: {list(value.keys())}"
                                            )
                                    self.logger.warning(
                                        f"Source output '{source_key}' not found in node '{source_node_id}'. "
                                        f"Available outputs: {list(source_outputs.keys())}"
                                    )
                                    break

                        if found:
                            inputs[target_key] = value
                            if self.debug:
                                self.logger.debug(
                                    f"  MAPPED: {source_key} -> {target_key} (type: {type(value)})"
                                )
                    else:
                        # Simple key mapping
                        if source_key in source_outputs:
                            inputs[target_key] = source_outputs[source_key]
                            if self.debug:
                                self.logger.debug(
                                    f"  MAPPED: {source_key} -> {target_key} (type: {type(source_outputs[source_key])})"
                                )
                        else:
                            if self.debug:
                                self.logger.debug(
                                    f"  MISSING: {source_key} not in {list(source_outputs.keys())}"
                                )
                            self.logger.warning(
                                f"Source output '{source_key}' not found in node '{source_node_id}'. "
                                f"Available outputs: {list(source_outputs.keys())}"
                            )
            else:
                if self.debug:
                    self.logger.debug(
                        f"  No outputs found for source node {source_node_id}"
                    )

        # Apply parameter overrides
        inputs.update(parameters)

        return inputs

    def _should_stop_on_error(self, workflow: Workflow, node_id: str) -> bool:
        """Determine if execution should stop when a node fails.

        Args:
            workflow: The workflow being executed.
            node_id: Failed node ID.

        Returns:
            Whether to stop execution.
        """
        # Check if any downstream nodes depend on this node
        has_dependents = workflow.graph.out_degree(node_id) > 0

        # For now, stop if the failed node has dependents
        # Future: implement configurable error handling policies
        return has_dependents

    def validate_workflow(self, workflow: Workflow) -> list[str]:
        """Validate a workflow before execution.

        Args:
            workflow: Workflow to validate

        Returns:
            List of validation warnings (empty if valid)

        Raises:
            WorkflowValidationError: If workflow is invalid
        """
        warnings = []

        try:
            workflow.validate()
        except WorkflowValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            raise WorkflowValidationError(f"Workflow validation failed: {e}") from e

        # Check for disconnected nodes
        for node_id in workflow.graph.nodes():
            if (
                workflow.graph.in_degree(node_id) == 0
                and workflow.graph.out_degree(node_id) == 0
                and len(workflow.graph.nodes()) > 1
            ):
                warnings.append(f"Node '{node_id}' is disconnected from the workflow")

        # Check for missing required parameters
        for node_id, node_instance in workflow._node_instances.items():
            try:
                params = node_instance.get_parameters()
            except Exception as e:
                warnings.append(f"Failed to get parameters for node '{node_id}': {e}")
                continue

            for param_name, param_def in params.items():
                if param_def.required:
                    # Check if provided in config or connected
                    if param_name not in node_instance.config:
                        # Check if connected from another node
                        incoming_params = set()
                        for _, _, data in workflow.graph.in_edges(node_id, data=True):
                            mapping = data.get("mapping", {})
                            incoming_params.update(mapping.values())

                        if (
                            param_name not in incoming_params
                            and param_def.default is None
                        ):
                            warnings.append(
                                f"Node '{node_id}' missing required parameter '{param_name}' "
                                f"(no default value provided)"
                            )

        # Check for potential performance issues
        if len(workflow.graph.nodes()) > 100:
            warnings.append(
                f"Large workflow with {len(workflow.graph.nodes())} nodes "
                f"may have performance implications"
            )

        return warnings

    # Enterprise Feature Helper Methods

    def _check_workflow_access(self, workflow: Workflow) -> None:
        """Check if user has access to execute the workflow."""
        if not self.enable_security or not self.user_context:
            return

        try:
            # Use existing AccessControlManager pattern
            from kailash.access_control import (
                WorkflowPermission,
                get_access_control_manager,
            )

            if self._access_control_manager is None:
                self._access_control_manager = get_access_control_manager()

            decision = self._access_control_manager.check_workflow_access(
                self.user_context, workflow.workflow_id, WorkflowPermission.EXECUTE
            )
            if not decision.allowed:
                raise PermissionError(
                    f"Access denied to workflow '{workflow.workflow_id}': {decision.reason}"
                )
        except ImportError:
            # Access control not available, log and continue
            self.logger.warning(
                "Access control system not available, skipping security check"
            )
        except Exception as e:
            if isinstance(e, PermissionError):
                raise
            # Log but don't fail on access control errors
            self.logger.warning(f"Access control check failed: {e}")

    def _log_audit_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Log audit events using enterprise audit logging (synchronous)."""
        if not self.enable_audit:
            return

        try:
            # Use existing AuditLogNode pattern
            from kailash.nodes.security.audit_log import AuditLogNode

            audit_node = AuditLogNode()
            # Use the SDK pattern - execute the node
            audit_node.execute(
                event_type=event_type,
                event_data=event_data,
                user_context=self.user_context,
                timestamp=datetime.now(UTC),
            )
        except ImportError:
            # Audit logging not available, fall back to standard logging
            self.logger.info(f"AUDIT: {event_type} - {event_data}")
        except Exception as e:
            # Audit logging failures shouldn't stop execution
            self.logger.warning(f"Audit logging failed: {e}")

    async def _log_audit_event_async(
        self, event_type: str, event_data: dict[str, Any]
    ) -> None:
        """Log audit events using enterprise audit logging (asynchronous)."""
        if not self.enable_audit:
            return

        try:
            # Use existing AuditLogNode pattern
            from kailash.nodes.security.audit_log import AuditLogNode

            audit_node = AuditLogNode()
            # Use the SDK pattern - try async first, fallback to sync
            if hasattr(audit_node, "async_run"):
                await audit_node.async_run(
                    event_type=event_type,
                    event_data=event_data,
                    user_context=self.user_context,
                    timestamp=datetime.now(UTC),
                )
            else:
                # Fallback to sync execution
                audit_node.execute(
                    event_type=event_type,
                    event_data=event_data,
                    user_context=self.user_context,
                    timestamp=datetime.now(UTC),
                )
        except ImportError:
            # Audit logging not available, fall back to standard logging
            self.logger.info(f"AUDIT: {event_type} - {event_data}")
        except Exception as e:
            # Audit logging failures shouldn't stop execution
            self.logger.warning(f"Audit logging failed: {e}")

    def _serialize_user_context(self) -> dict[str, Any] | None:
        """Serialize user context for logging/tracking."""
        if not self.user_context:
            return None

        try:
            # Try to use model_dump if it's a Pydantic model
            if hasattr(self.user_context, "model_dump"):
                return self.user_context.model_dump()
            # Try to use dict() if it's a Pydantic model
            elif hasattr(self.user_context, "dict"):
                return self.user_context.dict()
            # Convert to dict if possible
            elif hasattr(self.user_context, "__dict__"):
                return self.user_context.__dict__
            else:
                return {"user_context": str(self.user_context)}
        except Exception as e:
            self.logger.warning(f"Failed to serialize user context: {e}")
            return {"user_context": str(self.user_context)}

    def _process_workflow_parameters(
        self,
        workflow: Workflow,
        parameters: dict[str, dict[str, Any]] | dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]] | None:
        """Process workflow parameters to handle both formats intelligently.

        This method detects whether parameters are in workflow-level format
        (flat dictionary) or node-specific format (nested dictionary) and
        transforms them appropriately for execution.

        ENTERPRISE ENHANCEMENT: Handles mixed format parameters where both
        node-specific and workflow-level parameters are present in the same
        parameter dictionary - critical for enterprise production workflows.

        Args:
            workflow: The workflow being executed
            parameters: Either workflow-level, node-specific, or MIXED format parameters

        Returns:
            Node-specific parameters ready for execution with workflow-level
            parameters properly injected
        """
        if not parameters:
            return None

        # ENTERPRISE FIX: Handle mixed format parameters
        # Extract node-specific and workflow-level parameters separately
        node_specific_params, workflow_level_params = self._separate_parameter_formats(
            parameters, workflow
        )

        # Start with node-specific parameters
        result = node_specific_params.copy() if node_specific_params else {}

        # If we have workflow-level parameters, inject them
        if workflow_level_params:
            injector = WorkflowParameterInjector(workflow, debug=self.debug)

            # Transform workflow parameters to node-specific format
            injected_params = injector.transform_workflow_parameters(
                workflow_level_params
            )

            # Merge injected parameters with existing node-specific parameters
            # IMPORTANT: Node-specific parameters take precedence over workflow-level
            for node_id, node_params in injected_params.items():
                if node_id not in result:
                    result[node_id] = {}
                # First set workflow-level parameters, then override with node-specific
                for param_name, param_value in node_params.items():
                    if param_name not in result[node_id]:  # Only if not already set
                        result[node_id][param_name] = param_value

            # Validate the transformation
            warnings = injector.validate_parameters(workflow_level_params)
            if warnings and self.debug:
                for warning in warnings:
                    self.logger.warning(f"Parameter validation: {warning}")

        return result if result else None

    def _separate_parameter_formats(
        self, parameters: dict[str, Any], workflow: Workflow
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Separate mixed format parameters into node-specific and workflow-level.

        ENTERPRISE CAPABILITY: Intelligently separates complex enterprise parameter
        patterns where both node-specific and workflow-level parameters coexist.

        Args:
            parameters: Mixed format parameters
            workflow: The workflow being executed

        Returns:
            Tuple of (node_specific_params, workflow_level_params)
        """
        node_specific_params = {}
        workflow_level_params = {}

        # Get node IDs for classification
        node_ids = set(workflow.graph.nodes()) if workflow else set()

        for key, value in parameters.items():
            # Node-specific parameter: key is a node ID and value is a dict
            if key in node_ids and isinstance(value, dict):
                node_specific_params[key] = value
            # Workflow-level parameter: key is not a node ID or value is not a dict
            else:
                workflow_level_params[key] = value

        if self.debug:
            self.logger.debug(
                f"Separated parameters: "
                f"node_specific={list(node_specific_params.keys())}, "
                f"workflow_level={list(workflow_level_params.keys())}"
            )

        return node_specific_params, workflow_level_params

    def _is_node_specific_format(
        self, parameters: dict[str, Any], workflow: Workflow = None
    ) -> bool:
        """Detect if parameters are in node-specific format.

        Node-specific format has structure: {node_id: {param: value}}
        Workflow-level format has structure: {param: value}

        Args:
            parameters: Parameters to check
            workflow: Optional workflow for node ID validation

        Returns:
            True if node-specific format, False if workflow-level
        """
        if not parameters:
            return True

        # Get node IDs if workflow provided
        node_ids = set(workflow.graph.nodes()) if workflow else set()

        # If any key is a node ID and its value is a dict, it's node-specific
        for key, value in parameters.items():
            if key in node_ids and isinstance(value, dict):
                return True

        # Additional heuristic: if all values are dicts and keys look like IDs
        all_dict_values = all(isinstance(v, dict) for v in parameters.values())
        keys_look_like_ids = any(
            "_" in k or k.startswith("node") or k in node_ids for k in parameters.keys()
        )

        if all_dict_values and keys_look_like_ids:
            return True

        # Default to workflow-level format
        return False

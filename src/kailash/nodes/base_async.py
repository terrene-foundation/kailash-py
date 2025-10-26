"""Asynchronous base node class extension for the Kailash SDK.

This module extends the base Node class with asynchronous execution capabilities
AND enterprise features through mixin inheritance.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from kailash.nodes.base import Node
from kailash.nodes.mixins import (
    EventEmitterMixin,
    LoggingMixin,
    PerformanceMixin,
    SecurityMixin,
)
from kailash.runtime.template_resolver import resolve_templates
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class AsyncNode(
    EventEmitterMixin,  # Event emission (already async-compatible)
    SecurityMixin,  # Security features (input validation, sanitization)
    PerformanceMixin,  # Performance monitoring and tracking
    LoggingMixin,  # Enhanced logging with context
    Node,  # Base node (must be last)
):
    """Base class for asynchronous nodes with enterprise capabilities.

    This class extends the standard Node class with:
    1. Async execution capabilities
    2. Event emission for monitoring
    3. Security features (input validation, sanitization)
    4. Performance monitoring (execution tracking)
    5. Enhanced logging (structured logging with context)

    Inherits from:
        EventEmitterMixin: Async-compatible event emission for monitoring
        SecurityMixin: Security validation and input sanitization
        PerformanceMixin: Performance tracking and metrics collection
        LoggingMixin: Enhanced logging with context support
        Node: Base node functionality and validation

    Use Cases:
    1. API calls and network operations
    2. Database queries
    3. File operations
    4. External service integrations
    5. LLM/AI model inference

    Design Philosophy:
    - Maintain backward compatibility with synchronous nodes
    - Support both sync and async execution methods
    - Provide enterprise-grade features through mixins
    - Clear error handling and logging for async operations
    - Enable efficient parallel execution in workflows

    Mixin Order Rationale:
    - EventEmitterMixin first: Already async, no conflicts
    - SecurityMixin: May need methods from PerformanceMixin
    - PerformanceMixin: May need logging from LoggingMixin
    - LoggingMixin: May need Node methods
    - Node last: Base class with fundamental methods

    Usage Pattern:
    - Override async_run() instead of run() for async functionality
    - All enterprise features automatically available
    - Use event emission for monitoring
    - Security validation automatic in execute_async()

    Upstream components:
    - Workflow: Creates and manages node instances
    - AsyncWorkflowExecutor: Executes nodes in parallel where possible
    - AsyncLocalRuntime: Runs workflows with async support

    Downstream usage:
    - Custom AsyncNodes: Implement async_run() for I/O-bound operations
    - TaskManager: Tracks node execution status
    """

    def __init__(self, **kwargs):
        """Initialize AsyncNode with all enterprise capabilities.

        This calls the MRO chain to initialize all mixins and the base Node.
        The MRO ensures each mixin's __init__ is called exactly once.

        Args:
            **kwargs: Configuration parameters for node and mixins
                - All Node parameters (node_id, node_type, config, etc.)
                - security_config: Optional SecurityConfig for SecurityMixin
                - log_level: Log level for LoggingMixin (default: "INFO")
                - enable_performance_tracking: Enable performance metrics (default: True)
        """
        # Initialize all mixins and base Node via MRO
        super().__init__(**kwargs)

    def execute(self, **runtime_inputs) -> dict[str, Any]:
        """Execute the node synchronously by running async code with proper event loop handling.

        This enhanced implementation handles all event loop scenarios:
        1. No event loop: Create new one with asyncio.run()
        2. Event loop running: Use ThreadPoolExecutor with isolated loop
        3. Threaded contexts: Proper thread-safe execution
        4. Windows compatibility: ProactorEventLoopPolicy support

        Args:
            **runtime_inputs: Runtime inputs for node execution

        Returns:
            Dictionary of validated outputs

        Raises:
            NodeValidationError: If inputs or outputs are invalid
            NodeExecutionError: If execution fails
        """
        import asyncio
        import concurrent.futures
        import sys
        import threading

        # For sync execution, we always create a new event loop
        # This avoids complexity with nested loops and ensures clean execution
        if sys.platform == "win32":
            # Windows requires special handling
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Check if we're in a thread without an event loop
        current_thread = threading.current_thread()
        is_main_thread = isinstance(current_thread, threading._MainThread)

        # Run the async method - handle existing event loop
        try:
            # Try to get current event loop
            loop = asyncio.get_running_loop()
            # Event loop is running - need to run in separate thread
            return self._execute_in_thread(**runtime_inputs)
        except RuntimeError:
            # No event loop running
            if is_main_thread:
                # Main thread without loop - safe to use asyncio.run()
                return asyncio.run(self.execute_async(**runtime_inputs))
            else:
                # Non-main thread without loop - create new loop
                return self._execute_in_new_loop(**runtime_inputs)

    def _execute_in_thread(self, **runtime_inputs) -> dict[str, Any]:
        """Execute async code in a separate thread with its own event loop."""
        import asyncio
        import concurrent.futures

        def run_in_new_loop():
            """Run async code in a completely new event loop."""
            # Create fresh event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(self.execute_async(**runtime_inputs))
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            return future.result()

    def _execute_in_new_loop(self, **runtime_inputs) -> dict[str, Any]:
        """Execute async code by creating a new event loop in current thread."""
        import asyncio

        # Create and set new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.execute_async(**runtime_inputs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def run(self, **kwargs) -> dict[str, Any]:
        """Synchronous run is not supported for AsyncNode.

        AsyncNode subclasses should implement async_run() instead of run().
        This method exists to provide a clear error message if someone
        accidentally tries to implement run() on an async node.

        Raises:
            NotImplementedError: Always, as async nodes must use async_run()
        """
        raise NotImplementedError(
            f"AsyncNode '{self.__class__.__name__}' should implement async_run() method, not run()"
        )

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Asynchronous execution method for the node.

        This method should be overridden by subclasses to implement asynchronous
        execution logic. The default implementation raises NotImplementedError
        to ensure async nodes properly implement their async behavior.

        Args:
            **kwargs: Input parameters for node execution

        Returns:
            Dictionary of outputs matching the node's output schema

        Raises:
            NodeExecutionError: If execution fails
        """
        raise NotImplementedError(
            f"AsyncNode '{self.__class__.__name__}' must implement async_run() method"
        )

    async def execute_async(self, **runtime_inputs) -> dict[str, Any]:
        """Execute the node asynchronously with validation and error handling.

        This method follows the same pattern as execute() but supports asynchronous
        execution. It performs:

        1. Input validation
        2. Execution via async_run()
        3. Output validation
        4. Error handling and logging

        Args:
            **runtime_inputs: Runtime inputs for node execution

        Returns:
            Dictionary of validated outputs

        Raises:
            NodeValidationError: If inputs or outputs are invalid
            NodeExecutionError: If execution fails
        """
        start_time = datetime.now(UTC)
        try:
            self.logger.info(f"Executing node {self.id} asynchronously")

            # Merge runtime inputs with config (runtime inputs take precedence)
            merged_inputs = {**self.config, **runtime_inputs}

            # Resolve ${param} templates in merged parameters (v0.9.30)
            # This enables dynamic parameter injection in nested configurations
            # Example: {"filter": {"tag": "${tag}"}} with runtime_inputs={"tag": "local"}
            # Becomes: {"filter": {"tag": "local"}}
            merged_inputs = resolve_templates(merged_inputs, runtime_inputs)

            # Handle nested config case (for nodes that store parameters in config['config'])
            if "config" in merged_inputs and isinstance(merged_inputs["config"], dict):
                # Extract nested config
                nested_config = merged_inputs["config"]
                merged_inputs.update(nested_config)
                # Don't remove the config key as some nodes might need it

            # Validate inputs
            validated_inputs = self.validate_inputs(**merged_inputs)
            self.logger.debug(f"Validated inputs for {self.id}: {validated_inputs}")

            # Execute node logic asynchronously
            outputs = await self.async_run(**validated_inputs)

            # Validate outputs
            validated_outputs = self.validate_outputs(outputs)

            execution_time = (datetime.now(UTC) - start_time).total_seconds()
            self.logger.info(
                f"Node {self.id} executed successfully in {execution_time:.3f}s"
            )
            return validated_outputs

        except NodeValidationError:
            # Re-raise validation errors as-is
            raise
        except NodeExecutionError:
            # Re-raise execution errors as-is
            raise
        except Exception as e:
            # Wrap any other exception in NodeExecutionError
            self.logger.error(f"Node {self.id} execution failed: {e}", exc_info=True)
            raise NodeExecutionError(
                f"Node '{self.id}' execution failed: {type(e).__name__}: {e}"
            ) from e

    # ========================================================================
    # Async Method Overrides for Mixin Methods with I/O Operations
    # ========================================================================
    # These overrides prevent event loop blocking by offloading I/O operations
    # to a thread pool using asyncio.to_thread().

    # SecurityMixin Async Overrides
    # ---------------------------------------------------------------------

    async def audit_log(self, action: str, details: Dict[str, Any]) -> None:
        """Log an audit event (async override).

        Overrides SecurityMixin.audit_log to prevent blocking the event loop.
        Uses asyncio.to_thread() to offload print() to thread pool.

        Args:
            action: Action being audited
            details: Additional details about the action
        """
        if self._audit_enabled:
            await asyncio.to_thread(print, f"[AUDIT] {action}: {details}")

    async def log_security_event(self, event: str, level: str = "INFO") -> None:
        """Log a security-related event (async override).

        This method provides async logging for security events when
        audit logging is enabled in security_config.

        Args:
            event: Description of the security event
            level: Log level (INFO, WARNING, ERROR)
        """
        if (
            not hasattr(self, "security_config")
            or not self.security_config.enable_audit_logging
        ):
            return

        log_msg = f"Security event in {self.__class__.__name__}: {event}"

        if level.upper() == "ERROR":
            await asyncio.to_thread(self.logger.error, log_msg)
        elif level.upper() == "WARNING":
            await asyncio.to_thread(self.logger.warning, log_msg)
        else:
            await asyncio.to_thread(self.logger.info, log_msg)

    async def validate_and_sanitize_inputs(
        self, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and sanitize input parameters (async override).

        Overrides SecurityMixin.validate_and_sanitize_inputs when the full
        SecurityMixin from mixins.py is used (with logging).

        Args:
            inputs: Dictionary of input parameters

        Returns:
            Dictionary of validated and sanitized parameters
        """
        # If the simple SecurityMixin is used (no logging), delegate to parent
        if not hasattr(self, "security_config"):
            # Call parent method via super() - it won't have logging I/O
            return super().validate_and_sanitize_inputs(inputs)

        # If full SecurityMixin is used, implement async version with logging
        try:
            from kailash.security import SecurityError, validate_node_parameters

            # First validate using the security framework
            validated_inputs = validate_node_parameters(inputs, self.security_config)

            if self.security_config.enable_audit_logging:
                await asyncio.to_thread(
                    self.logger.debug,
                    f"Inputs validated for {self.__class__.__name__}: {list(validated_inputs.keys())}",
                )

            return validated_inputs

        except Exception as e:
            # Import SecurityError if validation module is available
            try:
                from kailash.security import SecurityError

                if isinstance(e, SecurityError):
                    if self.security_config.enable_audit_logging:
                        await asyncio.to_thread(
                            self.logger.error,
                            f"Security validation failed for {self.__class__.__name__}: {e}",
                        )
                    raise
            except ImportError:
                pass

            if (
                hasattr(self, "security_config")
                and self.security_config.enable_audit_logging
            ):
                await asyncio.to_thread(
                    self.logger.error,
                    f"Unexpected validation error for {self.__class__.__name__}: {e}",
                )
            raise

    # LoggingMixin Async Overrides
    # ---------------------------------------------------------------------

    async def log_with_context(self, level: str, message: str, **context) -> None:
        """Log a message with additional context (async override).

        Overrides LoggingMixin.log_with_context to prevent blocking.

        Args:
            level: Log level (debug, info, warning, error, critical)
            message: Log message
            **context: Additional context to include
        """
        # LoggingMixin uses _log_context (private attribute)
        log_ctx = getattr(self, "_log_context", {}) or getattr(self, "log_context", {})
        full_context = {**log_ctx, **context}
        context_str = " | ".join(f"{k}={v}" for k, v in full_context.items())
        full_message = f"{message} | {context_str}"

        log_func = getattr(self.logger, level.lower())
        await asyncio.to_thread(log_func, full_message)

    async def log_node_execution(self, operation: str, **context) -> None:
        """Log node execution information (async override).

        Overrides LoggingMixin.log_node_execution to prevent blocking.

        Args:
            operation: Type of operation being performed
            **context: Additional context
        """
        await self.log_with_context("info", f"Node operation: {operation}", **context)

    async def log_error_with_traceback(
        self, error: Exception, operation: str = "unknown"
    ) -> None:
        """Log an error with full traceback information (async override).

        Overrides LoggingMixin.log_error_with_traceback to prevent blocking.

        Args:
            error: Exception that occurred
            operation: Operation that failed
        """
        import traceback

        await self.log_with_context(
            "error",
            f"Operation failed: {operation}",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
        )

    async def log_info(self, message: str, **extra) -> None:
        """Log info message with context (async override).

        Overrides LoggingMixin.log_info to prevent blocking.

        Args:
            message: Log message
            **extra: Additional context
        """
        # Handle both simple and full LoggingMixin versions
        if hasattr(self, "_log_context"):
            # Full version from mixins.py
            await asyncio.to_thread(
                self.logger.info, message, extra={**self._log_context, **extra}
            )
        else:
            # Simple version or direct call
            await asyncio.to_thread(self.logger.info, message, extra=extra)

    async def log_error(
        self, message: str, error: Optional[Exception] = None, **extra
    ) -> None:
        """Log error message with context (async override).

        Overrides LoggingMixin.log_error to prevent blocking.

        Args:
            message: Log message
            error: Optional exception to include
            **extra: Additional context
        """
        # Handle both simple and full LoggingMixin versions
        if hasattr(self, "_log_context"):
            log_data = {**self._log_context, **extra}
        else:
            log_data = extra.copy()

        if error:
            log_data["error_type"] = type(error).__name__
            log_data["error_message"] = str(error)

        await asyncio.to_thread(self.logger.error, message, extra=log_data)

    async def log_warning(self, message: str, **extra) -> None:
        """Log warning message with context (async override).

        Overrides LoggingMixin.log_warning to prevent blocking.

        Args:
            message: Log message
            **extra: Additional context
        """
        # Handle both simple and full LoggingMixin versions
        if hasattr(self, "_log_context"):
            await asyncio.to_thread(
                self.logger.warning, message, extra={**self._log_context, **extra}
            )
        else:
            await asyncio.to_thread(self.logger.warning, message, extra=extra)

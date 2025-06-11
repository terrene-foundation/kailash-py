"""
Node mixins for the Kailash SDK.

This module provides mixins that add common functionality to nodes,
including security features, validation, and utility methods.

Design Philosophy:
    - Composition over inheritance for optional features
    - Security by default
    - Minimal performance overhead
    - Easy to integrate with existing nodes
"""

import logging
from typing import Any

from kailash.security import (
    SecurityConfig,
    SecurityError,
    get_security_config,
    sanitize_input,
    validate_node_parameters,
)

logger = logging.getLogger(__name__)


class SecurityMixin:
    """
    Mixin that adds security features to nodes.

    This mixin provides:
    - Input parameter validation and sanitization
    - Security policy enforcement
    - Audit logging for security events
    - Protection against common attack vectors

    Usage:
        class MySecureNode(SecurityMixin, Node):
            def run(self, **kwargs):
                # Input is automatically sanitized
                safe_params = self.validate_and_sanitize_inputs(kwargs)
                return self.process_safely(safe_params)
    """

    def __init__(self, *args, security_config: SecurityConfig | None = None, **kwargs):
        """
        Initialize security mixin.

        Args:
            security_config: Security configuration to use
            *args: Arguments passed to parent class
            **kwargs: Keyword arguments passed to parent class
        """
        super().__init__(*args, **kwargs)
        self.security_config = security_config or get_security_config()

        if self.security_config.enable_audit_logging:
            logger.info(f"Security mixin initialized for {self.__class__.__name__}")

    def validate_and_sanitize_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and sanitize input parameters.

        Args:
            inputs: Dictionary of input parameters

        Returns:
            Dictionary of validated and sanitized parameters

        Raises:
            SecurityError: If validation fails
        """
        try:
            # First validate using the security framework
            validated_inputs = validate_node_parameters(inputs, self.security_config)

            if self.security_config.enable_audit_logging:
                logger.debug(
                    f"Inputs validated for {self.__class__.__name__}: {list(validated_inputs.keys())}"
                )

            return validated_inputs

        except SecurityError as e:
            if self.security_config.enable_audit_logging:
                logger.error(
                    f"Security validation failed for {self.__class__.__name__}: {e}"
                )
            raise
        except Exception as e:
            if self.security_config.enable_audit_logging:
                logger.error(
                    f"Unexpected validation error for {self.__class__.__name__}: {e}"
                )
            raise SecurityError(f"Input validation failed: {e}")

    def sanitize_single_input(self, value: Any, max_length: int = 10000) -> Any:
        """
        Sanitize a single input value.

        Args:
            value: Value to sanitize
            max_length: Maximum string length

        Returns:
            Sanitized value
        """
        return sanitize_input(value, max_length, config=self.security_config)

    def is_security_enabled(self) -> bool:
        """Check if security features are enabled."""
        return (
            self.security_config.enable_path_validation
            or self.security_config.enable_command_validation
            or hasattr(self, "security_config")
        )

    def log_security_event(self, event: str, level: str = "INFO") -> None:
        """
        Log a security-related event.

        Args:
            event: Description of the security event
            level: Log level (INFO, WARNING, ERROR)
        """
        if not self.security_config.enable_audit_logging:
            return

        log_msg = f"Security event in {self.__class__.__name__}: {event}"

        if level.upper() == "ERROR":
            logger.error(log_msg)
        elif level.upper() == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)


class ValidationMixin:
    """
    Mixin that adds enhanced input validation to nodes.

    This mixin provides:
    - Type checking and conversion
    - Range and constraint validation
    - Custom validation rules
    - Detailed error reporting
    """

    def validate_required_params(
        self, inputs: dict[str, Any], required_params: list
    ) -> None:
        """
        Validate that all required parameters are present.

        Args:
            inputs: Input parameters
            required_params: List of required parameter names

        Raises:
            ValueError: If required parameters are missing
        """
        missing_params = [param for param in required_params if param not in inputs]
        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

    def validate_param_types(
        self, inputs: dict[str, Any], type_mapping: dict[str, type]
    ) -> dict[str, Any]:
        """
        Validate and convert parameter types.

        Args:
            inputs: Input parameters
            type_mapping: Dictionary mapping parameter names to expected types

        Returns:
            Dictionary with converted types

        Raises:
            TypeError: If type conversion fails
        """
        converted = {}

        for param_name, value in inputs.items():
            if param_name in type_mapping:
                expected_type = type_mapping[param_name]
                try:
                    if isinstance(value, expected_type):
                        converted[param_name] = value
                    else:
                        converted[param_name] = expected_type(value)
                except (ValueError, TypeError) as e:
                    raise TypeError(
                        f"Cannot convert {param_name} to {expected_type.__name__}: {e}"
                    )
            else:
                converted[param_name] = value

        return converted

    def validate_param_ranges(
        self, inputs: dict[str, Any], range_mapping: dict[str, tuple]
    ) -> None:
        """
        Validate that numeric parameters are within acceptable ranges.

        Args:
            inputs: Input parameters
            range_mapping: Dictionary mapping parameter names to (min, max) tuples

        Raises:
            ValueError: If parameters are out of range
        """
        for param_name, (min_val, max_val) in range_mapping.items():
            if param_name in inputs:
                value = inputs[param_name]
                if isinstance(value, (int, float)):
                    if value < min_val or value > max_val:
                        raise ValueError(
                            f"{param_name} must be between {min_val} and {max_val}, got {value}"
                        )


class PerformanceMixin:
    """
    Mixin that adds performance monitoring to nodes.

    This mixin provides:
    - Execution time tracking
    - Memory usage monitoring
    - Performance metrics collection
    - Optimization hints
    """

    def __init__(self, *args, **kwargs):
        """Initialize performance mixin."""
        super().__init__(*args, **kwargs)
        self.execution_times = []
        self.memory_usage = []
        self.performance_enabled = True

    def track_performance(self, func):
        """
        Decorator to track performance of node methods.

        Args:
            func: Function to wrap

        Returns:
            Wrapped function with performance tracking
        """
        import time
        import tracemalloc
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not self.performance_enabled:
                return func(*args, **kwargs)

            # Start tracking
            start_time = time.time()
            tracemalloc.start()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Record metrics
                execution_time = time.time() - start_time
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                self.execution_times.append(execution_time)
                self.memory_usage.append(peak)

                if len(self.execution_times) > 100:  # Keep last 100 measurements
                    self.execution_times = self.execution_times[-100:]
                    self.memory_usage = self.memory_usage[-100:]

        return wrapper

    def get_performance_stats(self) -> dict[str, Any]:
        """
        Get performance statistics for this node.

        Returns:
            Dictionary containing performance metrics
        """
        if not self.execution_times:
            return {"status": "No performance data available"}

        import statistics

        return {
            "executions": len(self.execution_times),
            "avg_execution_time": statistics.mean(self.execution_times),
            "min_execution_time": min(self.execution_times),
            "max_execution_time": max(self.execution_times),
            "avg_memory_usage": (
                statistics.mean(self.memory_usage) if self.memory_usage else 0
            ),
            "peak_memory_usage": max(self.memory_usage) if self.memory_usage else 0,
        }

    def reset_performance_stats(self) -> None:
        """Reset performance statistics."""
        self.execution_times.clear()
        self.memory_usage.clear()


class LoggingMixin:
    """
    Mixin that adds enhanced logging capabilities to nodes.

    This mixin provides:
    - Structured logging with context
    - Log level management
    - Performance logging
    - Debug information
    """

    def __init__(self, *args, log_level: str = "INFO", **kwargs):
        """
        Initialize logging mixin.

        Args:
            log_level: Default log level for this node
            *args: Arguments passed to parent class
            **kwargs: Keyword arguments passed to parent class
        """
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )
        self.logger.setLevel(getattr(logging, log_level.upper()))
        self.log_context = {"node_class": self.__class__.__name__}

    def log_with_context(self, level: str, message: str, **context) -> None:
        """
        Log a message with additional context.

        Args:
            level: Log level
            message: Log message
            **context: Additional context to include
        """
        full_context = {**self.log_context, **context}
        context_str = " | ".join(f"{k}={v}" for k, v in full_context.items())
        full_message = f"{message} | {context_str}"

        log_func = getattr(self.logger, level.lower())
        log_func(full_message)

    def log_node_execution(self, operation: str, **context) -> None:
        """
        Log node execution information.

        Args:
            operation: Type of operation being performed
            **context: Additional context
        """
        self.log_with_context("INFO", f"Node operation: {operation}", **context)

    def log_error_with_traceback(
        self, error: Exception, operation: str = "unknown"
    ) -> None:
        """
        Log an error with full traceback information.

        Args:
            error: Exception that occurred
            operation: Operation that failed
        """
        import traceback

        self.log_with_context(
            "ERROR",
            f"Operation failed: {operation}",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
        )

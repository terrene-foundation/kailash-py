"""
Security-related mixins for Kailash nodes.

These mixins provide security, performance, and logging capabilities
that can be mixed into any node class.
"""

import logging
import time
from functools import wraps
from typing import Any, Dict, Optional


class SecurityMixin:
    """
    Mixin that adds security features to nodes.

    Provides:
    - Security context management
    - Audit logging capabilities
    - Access control integration
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._security_context = {}
        self._audit_enabled = kwargs.get("audit_enabled", True)
        self._log_context = {}  # Initialize log context for log_with_context method

    def set_security_context(self, context: Dict[str, Any]) -> None:
        """Set security context for the node."""
        self._security_context = context

    def get_security_context(self) -> Dict[str, Any]:
        """Get current security context."""
        return self._security_context

    def audit_log(self, action: str, details: Dict[str, Any]) -> None:
        """Log an audit event."""
        if self._audit_enabled:
            # In a real implementation, this would integrate with AuditLogNode
            print(f"[AUDIT] {action}: {details}")

    def validate_and_sanitize_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize input parameters."""
        # Basic implementation - in production this would do more validation
        sanitized = {}
        for key, value in inputs.items():
            if isinstance(value, str):
                # Basic sanitization - remove leading/trailing whitespace
                sanitized[key] = value.strip()
            else:
                sanitized[key] = value
        return sanitized


class PerformanceMixin:
    """
    Mixin that adds performance monitoring to nodes.

    Provides:
    - Execution time tracking
    - Performance metrics collection
    - SLA monitoring
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._performance_metrics = []
        self._sla_target_ms = kwargs.get("sla_target_ms", 1000)

    def track_performance(self, func):
        """Decorator to track method performance."""

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000  # Convert to ms
                self._performance_metrics.append(
                    {
                        "method": func.__name__,
                        "execution_time_ms": execution_time,
                        "sla_met": execution_time <= self._sla_target_ms,
                    }
                )
                return result
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                self._performance_metrics.append(
                    {
                        "method": func.__name__,
                        "execution_time_ms": execution_time,
                        "error": str(e),
                    }
                )
                raise

        return wrapper

    def get_performance_metrics(self) -> list:
        """Get collected performance metrics."""
        return self._performance_metrics


class LoggingMixin:
    """
    Mixin that adds enhanced logging capabilities to nodes.

    Provides:
    - Structured logging
    - Context-aware logging
    - Log level management
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self._log_context = {}

    def set_log_context(self, **context):
        """Set logging context."""
        self._log_context.update(context)

    def log_info(self, message: str, **extra):
        """Log info message with context."""
        self.logger.info(message, extra={**self._log_context, **extra})

    def log_error(self, message: str, error: Optional[Exception] = None, **extra):
        """Log error message with context."""
        log_data = {**self._log_context, **extra}
        if error:
            log_data["error_type"] = type(error).__name__
            log_data["error_message"] = str(error)
        self.logger.error(message, extra=log_data)

    def log_warning(self, message: str, **extra):
        """Log warning message with context."""
        self.logger.warning(message, extra={**self._log_context, **extra})

    def log_error_with_traceback(
        self, error: Exception, operation: str = "unknown"
    ) -> None:
        """Log an error with full traceback information."""
        import traceback

        self.log_error(
            f"Operation failed: {operation}",
            error=error,
            traceback=traceback.format_exc(),
        )

    def log_node_execution(self, operation: str, **context) -> None:
        """Log node execution information."""
        self.log_info(f"Node operation: {operation}", **context)

    def log_with_context(self, level: str, message: str, **context) -> None:
        """Log a message with additional context."""
        full_context = {**self._log_context, **context}
        context_str = " | ".join(f"{k}={v}" for k, v in full_context.items())
        full_message = f"{message} | {context_str}"

        log_func = getattr(self.logger, level.lower())
        log_func(full_message)

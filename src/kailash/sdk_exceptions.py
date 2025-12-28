"""Comprehensive Exception System for the Kailash SDK.

This module provides a comprehensive hierarchy of custom exceptions designed to
provide clear, actionable error information throughout the Kailash SDK. Each
exception includes detailed context, suggestions for resolution, and integration
with debugging and monitoring systems.

Design Philosophy:
    Provides a clear, hierarchical exception system that enables precise error
    handling and debugging. Each exception includes comprehensive context,
    actionable suggestions, and integration points for monitoring and logging
    systems.

Key Features:
    - Hierarchical exception structure for precise error handling
    - Rich context information with actionable suggestions
    - Integration with logging and monitoring systems
    - Cycle-specific exceptions for advanced workflow patterns
    - Security and safety violation reporting
    - Performance and resource-related error tracking

Exception Categories:
    - **Core Exceptions**: Fundamental SDK operations
    - **Workflow Exceptions**: Workflow creation and validation
    - **Execution Exceptions**: Runtime execution errors
    - **Cycle Exceptions**: Cyclic workflow-specific errors
    - **Security Exceptions**: Safety and security violations
    - **Configuration Exceptions**: Parameter and setup errors

Core Exception Hierarchy:
    - KailashException: Base exception for all SDK errors
        - NodeException: Node-related errors
            - NodeValidationError: Validation failures
            - NodeExecutionError: Runtime execution issues
            - NodeConfigurationError: Configuration problems
        - WorkflowException: Workflow-related errors
            - WorkflowValidationError: Validation failures
            - WorkflowExecutionError: Execution failures
        - RuntimeException: Runtime execution errors
        - SecurityException: Security and safety violations

Cycle-Specific Exceptions (v0.2.0):
    Enhanced exception handling for cyclic workflows with detailed context
    and resolution guidance for cycle-specific issues.

Examples:
    Basic exception handling:

    >>> from kailash.sdk_exceptions import WorkflowValidationError, NodeExecutionError
    >>> try:
    ...     workflow.validate()
    ... except WorkflowValidationError as e:
    ...     print(f"Validation failed: {e}")
    ...     # Exception includes helpful context and suggestions

    Production error monitoring:

    >>> import logging
    >>> from kailash.sdk_exceptions import KailashException
    >>> logger = logging.getLogger(__name__)
    >>> try:
    ...     runtime.execute(workflow)
    ... except KailashException as e:
    ...     logger.error(f"SDK Error: {e}", extra={
    ...         'error_type': type(e).__name__,
    ...         'workflow_id': getattr(workflow, 'workflow_id', None)
            })
            raise

See Also:
    - :mod:`kailash.workflow.cycle_exceptions` for cycle-specific errors
    - :mod:`kailash.security` for security validation and exceptions
    - :doc:`/guides/error_handling` for comprehensive error handling patterns
"""


class KailashException(Exception):
    """Base exception for all Kailash SDK errors."""


# Node-related exceptions
class NodeException(KailashException):
    """Base exception for node-related errors."""


class NodeValidationError(NodeException):
    """Raised when node validation fails.

    This typically occurs when:
    - Required parameters are missing
    - Input/output types don't match expectations
    - Configuration is invalid
    """


class NodeExecutionError(NodeException):
    """Raised when node execution fails.

    This typically occurs when:
    - An error happens during node processing
    - External resources are unavailable
    - Data transformation fails
    """


class NodeConfigurationError(NodeException):
    """Raised when node configuration is invalid.

    This typically occurs when:
    - Invalid parameter values are provided
    - Configuration schema is violated
    - Required environment variables are missing
    """


class SafetyViolationError(NodeException):
    """Raised when code safety validation fails.

    This typically occurs when:
    - Code contains dangerous operations (eval, exec, import)
    - Unsafe module imports are attempted
    - Malicious code patterns are detected
    """


# Workflow-related exceptions
class WorkflowException(KailashException):
    """Base exception for workflow-related errors."""


class WorkflowValidationError(WorkflowException):
    """Raised when workflow validation fails.

    This typically occurs when:
    - Node connections are invalid
    - Required nodes are missing
    - Workflow structure is invalid
    """


class WorkflowExecutionError(WorkflowException):
    """Raised when workflow execution fails.

    This typically occurs when:
    - A node fails during execution
    - Data cannot flow between nodes
    - Runtime resources are exhausted
    """


class CyclicDependencyError(WorkflowException):
    """Raised when a cyclic dependency is detected in the workflow graph.

    This occurs when nodes form a circular dependency chain,
    making it impossible to determine execution order.
    """


class ConnectionError(WorkflowException):
    """Raised when node connections are invalid.

    This typically occurs when:
    - Trying to connect incompatible node outputs/inputs
    - Connection already exists
    - Node not found in workflow
    """


class CycleConfigurationError(WorkflowException):
    """Raised when cycle configuration is invalid.

    This exception is thrown by the CycleBuilder API when cycle parameters
    are missing, invalid, or conflicting. It provides actionable error messages
    to guide developers toward correct cycle configuration.

    Common scenarios:
    - Missing required cycle parameters (max_iterations or convergence_check)
    - Invalid parameter values (negative iterations, empty conditions)
    - Unsafe expressions in convergence conditions
    - Missing source/target nodes before build()
    """


# Runtime-related exceptions
class RuntimeException(KailashException):
    """Base exception for runtime-related errors."""


class RuntimeExecutionError(RuntimeException):
    """Raised when runtime execution fails.

    This typically occurs when:
    - Execution environment is not properly configured
    - Resources are unavailable
    - Execution is interrupted
    """


class ResourceLimitExceededError(RuntimeException):
    """Raised when runtime resource limits are exceeded.

    This typically occurs when:
    - Connection pool limits are exceeded
    - Memory usage exceeds configured limits
    - CPU usage exceeds thresholds
    - Too many concurrent workflows
    """


class CircuitBreakerOpenError(RuntimeException):
    """Raised when circuit breaker is open.

    This typically occurs when:
    - Service has exceeded failure threshold
    - Circuit breaker is protecting against cascading failures
    - Service is temporarily unavailable
    """


class RetryExhaustedException(RuntimeException):
    """Raised when all retry attempts are exhausted for an operation.

    This exception is raised when an operation fails after all configured retry
    attempts have been exhausted. It provides detailed information about the
    failure and retry attempts made.

    This typically occurs when:
    - Database connection cannot be established after multiple retries
    - SQLite database remains locked beyond retry timeout
    - PostgreSQL server is unavailable after retry period
    - Network errors persist beyond retry attempts

    Attributes:
        operation: Description of the operation that failed
        attempts: Number of retry attempts made
        last_error: The final error that caused the failure
        total_wait_time: Total time spent waiting between retries (seconds)
    """

    def __init__(
        self,
        operation: str,
        attempts: int,
        last_error: Exception,
        total_wait_time: float = None,
    ):
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error
        self.total_wait_time = total_wait_time

        message = f"{operation} failed after {attempts} retry attempts. Last error: {last_error}"
        if total_wait_time is not None:
            message += f" (Total wait time: {total_wait_time:.2f}s)"

        super().__init__(message)


# Task tracking exceptions
class TaskException(KailashException):
    """Base exception for task tracking errors."""


class TaskStateError(TaskException):
    """Raised when task state operations fail.

    This typically occurs when:
    - Invalid state transitions are attempted
    - Task state is corrupted
    - Concurrent modification conflicts occur
    """


# Storage exceptions
class StorageException(KailashException):
    """Base exception for storage-related errors."""


class KailashStorageError(StorageException):
    """Raised when storage operations fail.

    This typically occurs when:
    - File I/O operations fail
    - Database connections fail
    - Storage permissions are insufficient
    - Data formatting is incorrect
    """


# Import/Export exceptions
class ExportException(KailashException):
    """Raised when export operations fail.

    This typically occurs when:
    - Export format is unsupported
    - File permissions are insufficient
    - Serialization fails
    """


class ImportException(KailashException):
    """Raised when import operations fail.

    This typically occurs when:
    - Import format is unsupported
    - File is corrupted or invalid
    - Deserialization fails
    """


# Configuration exceptions
class ConfigurationException(KailashException):
    """Raised when configuration is invalid.

    This typically occurs when:
    - Configuration file is missing
    - Required configuration values are not provided
    - Configuration schema is invalid
    """


class KailashConfigError(ConfigurationException):
    """Raised when configuration is invalid (legacy name).

    This is an alias for ConfigurationException for backward compatibility.
    """


# Manifest exceptions
class ManifestError(KailashException):
    """Raised when manifest operations fail.

    This typically occurs when:
    - Manifest file is invalid
    - Required manifest fields are missing
    - Version incompatibility
    """


# CLI exceptions
class CLIException(KailashException):
    """Raised when CLI operations fail.

    This typically occurs when:
    - Invalid command arguments
    - Required arguments are missing
    - Command execution fails
    """


# Visualization exceptions
class VisualizationError(KailashException):
    """Raised when visualization operations fail.

    This typically occurs when:
    - Graph layout fails
    - Rendering engine is unavailable
    - Output format is unsupported
    """


# Template exceptions
class TemplateError(KailashException):
    """Raised when template operations fail.

    This typically occurs when:
    - Template file is missing
    - Template syntax is invalid
    - Variable substitution fails
    """


# Code execution exceptions
# (SafetyViolationError already defined above - removing duplicate)


class CodeExecutionError(NodeException):
    """Raised when code execution fails.

    This typically occurs when:
    - Syntax errors in user code
    - Runtime errors during execution
    - Import or dependency issues
    """


# Resource exceptions
class KailashNotFoundException(KailashException):
    """Raised when a requested resource cannot be found.

    This typically occurs when:
    - A template ID doesn't exist in the registry
    - A node type is not registered
    - A file or resource is missing
    """


# Workflow-specific exceptions
class KailashWorkflowException(WorkflowException):
    """Raised for general workflow-related errors.

    This is an alias for WorkflowException for consistency.
    """


# Legacy exception name compatibility for tests and backwards compatibility
KailashRuntimeError = RuntimeExecutionError
KailashValidationError = NodeValidationError

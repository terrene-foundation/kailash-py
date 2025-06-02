"""Exception classes for the Kailash SDK.

This module defines all custom exceptions used throughout the Kailash SDK.
Each exception includes helpful error messages and context to guide users
toward correct usage.
"""


class KailashException(Exception):
    """Base exception for all Kailash SDK errors."""

    pass


# Node-related exceptions
class NodeException(KailashException):
    """Base exception for node-related errors."""

    pass


class NodeValidationError(NodeException):
    """Raised when node validation fails.

    This typically occurs when:
    - Required parameters are missing
    - Input/output types don't match expectations
    - Configuration is invalid
    """

    pass


class NodeExecutionError(NodeException):
    """Raised when node execution fails.

    This typically occurs when:
    - An error happens during node processing
    - External resources are unavailable
    - Data transformation fails
    """

    pass


class NodeConfigurationError(NodeException):
    """Raised when node configuration is invalid.

    This typically occurs when:
    - Invalid parameter values are provided
    - Configuration schema is violated
    - Required environment variables are missing
    """

    pass


class SafetyViolationError(NodeException):
    """Raised when code safety validation fails.

    This typically occurs when:
    - Code contains dangerous operations (eval, exec, import)
    - Unsafe module imports are attempted
    - Malicious code patterns are detected
    """

    pass


# Workflow-related exceptions
class WorkflowException(KailashException):
    """Base exception for workflow-related errors."""

    pass


class WorkflowValidationError(WorkflowException):
    """Raised when workflow validation fails.

    This typically occurs when:
    - Node connections are invalid
    - Required nodes are missing
    - Workflow structure is invalid
    """

    pass


class WorkflowExecutionError(WorkflowException):
    """Raised when workflow execution fails.

    This typically occurs when:
    - A node fails during execution
    - Data cannot flow between nodes
    - Runtime resources are exhausted
    """

    pass


class CyclicDependencyError(WorkflowException):
    """Raised when a cyclic dependency is detected in the workflow graph.

    This occurs when nodes form a circular dependency chain,
    making it impossible to determine execution order.
    """

    pass


class ConnectionError(WorkflowException):
    """Raised when node connections are invalid.

    This typically occurs when:
    - Trying to connect incompatible node outputs/inputs
    - Connection already exists
    - Node not found in workflow
    """

    pass


# Runtime-related exceptions
class RuntimeException(KailashException):
    """Base exception for runtime-related errors."""

    pass


class RuntimeExecutionError(RuntimeException):
    """Raised when runtime execution fails.

    This typically occurs when:
    - Execution environment is not properly configured
    - Resources are unavailable
    - Execution is interrupted
    """

    pass


# Task tracking exceptions
class TaskException(KailashException):
    """Base exception for task tracking errors."""

    pass


class TaskStateError(TaskException):
    """Raised when task state operations fail.

    This typically occurs when:
    - Invalid state transitions are attempted
    - Task state is corrupted
    - Concurrent modification conflicts occur
    """

    pass


# Storage exceptions
class StorageException(KailashException):
    """Base exception for storage-related errors."""

    pass


class KailashStorageError(StorageException):
    """Raised when storage operations fail.

    This typically occurs when:
    - File I/O operations fail
    - Database connections fail
    - Storage permissions are insufficient
    - Data formatting is incorrect
    """

    pass


# Import/Export exceptions
class ExportException(KailashException):
    """Raised when export operations fail.

    This typically occurs when:
    - Export format is unsupported
    - File permissions are insufficient
    - Serialization fails
    """

    pass


class ImportException(KailashException):
    """Raised when import operations fail.

    This typically occurs when:
    - Import format is unsupported
    - File is corrupted or invalid
    - Deserialization fails
    """

    pass


# Configuration exceptions
class ConfigurationException(KailashException):
    """Raised when configuration is invalid.

    This typically occurs when:
    - Configuration file is missing
    - Required configuration values are not provided
    - Configuration schema is invalid
    """

    pass


class KailashConfigError(ConfigurationException):
    """Raised when configuration is invalid (legacy name).

    This is an alias for ConfigurationException for backward compatibility.
    """

    pass


# Manifest exceptions
class ManifestError(KailashException):
    """Raised when manifest operations fail.

    This typically occurs when:
    - Manifest file is invalid
    - Required manifest fields are missing
    - Version incompatibility
    """

    pass


# CLI exceptions
class CLIException(KailashException):
    """Raised when CLI operations fail.

    This typically occurs when:
    - Invalid command arguments
    - Required arguments are missing
    - Command execution fails
    """

    pass


# Visualization exceptions
class VisualizationError(KailashException):
    """Raised when visualization operations fail.

    This typically occurs when:
    - Graph layout fails
    - Rendering engine is unavailable
    - Output format is unsupported
    """

    pass


# Template exceptions
class TemplateError(KailashException):
    """Raised when template operations fail.

    This typically occurs when:
    - Template file is missing
    - Template syntax is invalid
    - Variable substitution fails
    """

    pass


# Code execution exceptions
# (SafetyViolationError already defined above - removing duplicate)


class CodeExecutionError(NodeException):
    """Raised when code execution fails.

    This typically occurs when:
    - Syntax errors in user code
    - Runtime errors during execution
    - Import or dependency issues
    """

    pass


# Resource exceptions
class KailashNotFoundException(KailashException):
    """Raised when a requested resource cannot be found.

    This typically occurs when:
    - A template ID doesn't exist in the registry
    - A node type is not registered
    - A file or resource is missing
    """

    pass


# Workflow-specific exceptions
class KailashWorkflowException(WorkflowException):
    """Raised for general workflow-related errors.

    This is an alias for WorkflowException for consistency.
    """

    pass


# Legacy exception name compatibility for tests and backwards compatibility
KailashRuntimeError = RuntimeExecutionError
KailashValidationError = NodeValidationError

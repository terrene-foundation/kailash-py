"""Exception classes for the Kailash SDK."""


class KailashError(Exception):
    """Base exception for all Kailash SDK errors."""
    pass


class NodeError(KailashError):
    """Base exception for node-related errors."""
    pass


class NodeValidationError(NodeError):
    """Raised when node validation fails."""
    pass


class NodeExecutionError(NodeError):
    """Raised when node execution fails."""
    pass


class WorkflowError(KailashError):
    """Base exception for workflow-related errors."""
    pass


class WorkflowValidationError(WorkflowError):
    """Raised when workflow validation fails."""
    pass


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow execution fails."""
    pass


class RuntimeError(KailashError):
    """Base exception for runtime-related errors."""
    pass


class TaskError(KailashError):
    """Base exception for task tracking errors."""
    pass


class StorageError(KailashError):
    """Base exception for storage-related errors."""
    pass


class ExportError(KailashError):
    """Base exception for export-related errors."""
    pass


class ManifestError(KailashError):
    """Base exception for manifest-related errors."""
    pass
"""
Exception classes for DataFlow Web components.
"""


class WebMigrationAPIError(Exception):
    """Base exception for WebMigrationAPI errors."""

    pass


class DatabaseConnectionError(WebMigrationAPIError):
    """Raised when database connection fails."""

    pass


class ValidationError(WebMigrationAPIError):
    """Raised when migration validation fails."""

    pass


class SessionNotFoundError(WebMigrationAPIError):
    """Raised when requested session is not found."""

    pass


class SerializationError(WebMigrationAPIError):
    """Raised when JSON serialization fails."""

    pass


class SQLExecutionError(WebMigrationAPIError):
    """Raised when SQL execution fails."""

    pass


class MigrationConflictError(WebMigrationAPIError):
    """Raised when migration conflicts are detected."""

    pass

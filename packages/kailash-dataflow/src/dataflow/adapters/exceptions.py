"""
Database Adapter Exceptions

Custom exceptions for database adapter operations.
"""


class AdapterError(Exception):
    """Base exception for database adapter errors."""

    pass


class UnsupportedDatabaseError(AdapterError):
    """Raised when trying to use an unsupported database type."""

    pass


class ConnectionError(AdapterError):
    """Raised when database connection fails."""

    pass


class QueryError(AdapterError):
    """Raised when query execution fails."""

    pass


class TransactionError(AdapterError):
    """Raised when transaction operations fail."""

    pass


class SchemaError(AdapterError):
    """Raised when schema operations fail."""

    pass

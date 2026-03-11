"""
SQL Module

Database-specific SQL generation and dialect abstraction.
"""

from .dialects import (
    MySQLDialect,
    PostgreSQLDialect,
    SQLDialect,
    SQLDialectFactory,
    SQLiteDialect,
    UpsertQuery,
)

__all__ = [
    "SQLDialect",
    "PostgreSQLDialect",
    "SQLiteDialect",
    "MySQLDialect",
    "SQLDialectFactory",
    "UpsertQuery",
]

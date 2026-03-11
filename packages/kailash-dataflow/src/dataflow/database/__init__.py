"""
DataFlow Database Module

Comprehensive multi-database support for PostgreSQL, MySQL, and SQLite
with dialect-specific features and optimizations.
"""

from .multi_database import (
    DatabaseAdapter,
    DatabaseDialect,
    DatabaseFeature,
    MySQLAdapter,
    PostgreSQLAdapter,
    SQLGenerator,
    SQLiteAdapter,
    TypeMapping,
    detect_dialect,
    get_database_adapter,
)
from .query_builder import DatabaseType, QueryBuilder, create_query_builder

__all__ = [
    "DatabaseDialect",
    "DatabaseAdapter",
    "PostgreSQLAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
    "get_database_adapter",
    "detect_dialect",
    "DatabaseFeature",
    "TypeMapping",
    "SQLGenerator",
    "QueryBuilder",
    "DatabaseType",
    "create_query_builder",
]

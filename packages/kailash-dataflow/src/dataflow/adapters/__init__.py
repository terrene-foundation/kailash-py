"""
Database Adapters

Multi-database support for DataFlow with tiered adapter hierarchy:
- BaseAdapter: Minimal interface for all adapter types
- DatabaseAdapter: SQL-specific adapter (PostgreSQL, MySQL, SQLite)
- PostgreSQLVectorAdapter: PostgreSQL with pgvector for vector similarity search
- MongoDBAdapter: MongoDB document database adapter
- Future: VectorAdapter, GraphAdapter, KeyValueAdapter
"""

from .base import DatabaseAdapter
from .base_adapter import BaseAdapter
from .mysql import MySQLAdapter
from .postgresql import PostgreSQLAdapter
from .sqlite import SQLiteAdapter


def __getattr__(name: str):
    """Lazy-load adapters that require optional driver packages."""
    if name == "MongoDBAdapter":
        from .mongodb import MongoDBAdapter

        return MongoDBAdapter
    if name == "PostgreSQLVectorAdapter":
        from .postgresql_vector import PostgreSQLVectorAdapter

        return PostgreSQLVectorAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseAdapter",
    "DatabaseAdapter",
    "MongoDBAdapter",
    "PostgreSQLAdapter",
    "PostgreSQLVectorAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
]

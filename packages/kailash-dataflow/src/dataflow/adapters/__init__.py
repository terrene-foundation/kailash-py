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

# MongoDB + pgvector adapter modules import cleanly without their optional
# driver packages (motor / pgvector) — the ImportError is deferred to
# .connect() time. Eager-importing the class objects here lets CodeQL
# py/modification-of-default-value resolve the __all__ entries per
# rules/orphan-detection.md §6; the driver check still fires at first
# connect for users without the optional extra.
from .mongodb import MongoDBAdapter
from .postgresql_vector import PostgreSQLVectorAdapter

__all__ = [
    "BaseAdapter",
    "DatabaseAdapter",
    "MongoDBAdapter",
    "PostgreSQLAdapter",
    "PostgreSQLVectorAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
]

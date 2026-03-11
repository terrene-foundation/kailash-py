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
from .mongodb import MongoDBAdapter
from .mysql import MySQLAdapter
from .postgresql import PostgreSQLAdapter
from .postgresql_vector import PostgreSQLVectorAdapter
from .sqlite import SQLiteAdapter

__all__ = [
    "BaseAdapter",
    "DatabaseAdapter",
    "MongoDBAdapter",
    "PostgreSQLAdapter",
    "PostgreSQLVectorAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
]

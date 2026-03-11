"""
Storage backends for Kaizen memory system.

Provides multiple storage implementations:
- FileStorage: JSONL-based storage (simple, no dependencies)
- SQLiteStorage: SQLite database (best default for local development)
- PostgreSQLStorage: PostgreSQL database (production-ready, scales well)
"""

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend
from kaizen.memory.storage.file_storage import FileStorage
from kaizen.memory.storage.sqlite_storage import SQLiteStorage

__all__ = [
    "MemoryEntry",
    "MemoryType",
    "StorageBackend",
    "FileStorage",
    "SQLiteStorage",
]

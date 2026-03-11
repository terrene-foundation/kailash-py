"""
SQLite storage backend for memory system.

Uses SQLite database for efficient, indexed storage with full SQL capabilities.
Best for: local development, moderate datasets (up to 1M entries), single-user scenarios.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from kaizen.memory.storage.base import (
    MemoryEntry,
    MemoryType,
    StorageBackend,
    StorageError,
)


class SQLiteStorage(StorageBackend):
    """
    SQLite database storage for memory entries.

    Features:
    - Indexed queries (fast ID lookup, type filtering)
    - Full SQL capabilities (joins, aggregations, etc.)
    - Transaction support (ACID guarantees)
    - Suitable for: <1,000,000 entries

    Performance characteristics:
    - Write: O(log n) - B-tree index
    - Read by ID: O(log n) - indexed lookup
    - Search: O(n) with FTS, O(n) without
    - Concurrent reads: Yes (multiple readers)
    - Concurrent writes: No (single writer lock)

    For multi-user or large-scale deployments, use PostgreSQLStorage.
    """

    def __init__(self, db_path: str = ".kaizen/memory/memories.db"):
        """
        Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._ensure_db_exists()
        self._create_tables()

    def _ensure_db_exists(self) -> None:
        """Create database file and parent directories if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite database connection."""
        conn = sqlite3.Connection(self.db_path)
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    metadata TEXT,  -- JSON string
                    timestamp TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT,
                    embedding TEXT  -- JSON array of floats
                )
                """
            )

            # Create indexes for common queries
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_type
                ON memories(memory_type)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON memories(timestamp DESC)
                """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_importance
                ON memories(importance DESC)
                """
            )

            # Full-text search index (optional, for faster search)
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(id, content, tokenize='porter')
                    """
                )
            except sqlite3.OperationalError:
                # FTS5 not available, skip (search will still work, just slower)
                pass

            conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert database row to MemoryEntry."""
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            memory_type=MemoryType(row["memory_type"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            timestamp=datetime.fromisoformat(row["timestamp"]),
            importance=row["importance"],
            access_count=row["access_count"],
            last_accessed=(
                datetime.fromisoformat(row["last_accessed"])
                if row["last_accessed"]
                else None
            ),
            embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        )

    def store(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry.

        Args:
            entry: The memory entry to store

        Returns:
            The ID of the stored entry

        Raises:
            StorageError: If storage fails
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO memories
                    (id, content, memory_type, metadata, timestamp, importance,
                     access_count, last_accessed, embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.content,
                        entry.memory_type.value,
                        json.dumps(entry.metadata) if entry.metadata else None,
                        entry.timestamp.isoformat(),
                        entry.importance,
                        entry.access_count,
                        (
                            entry.last_accessed.isoformat()
                            if entry.last_accessed
                            else None
                        ),
                        json.dumps(entry.embedding) if entry.embedding else None,
                    ),
                )

                # Update FTS index if available
                try:
                    conn.execute(
                        """
                        INSERT INTO memories_fts(id, content)
                        VALUES (?, ?)
                        """,
                        (entry.id, entry.content),
                    )
                except sqlite3.OperationalError:
                    # FTS table doesn't exist, skip
                    pass

                conn.commit()
            return entry.id
        except sqlite3.IntegrityError as e:
            raise StorageError(f"Entry with ID {entry.id} already exists: {e}")
        except (sqlite3.Error, json.JSONDecodeError) as e:
            raise StorageError(f"Failed to store entry: {e}")

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a memory entry by ID.

        Args:
            entry_id: The ID of the entry to retrieve

        Returns:
            The memory entry if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM memories WHERE id = ?
                """,
                (entry_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            entry = self._row_to_entry(row)
            entry.update_access()  # Track access

            # Update access count in database
            conn.execute(
                """
                UPDATE memories
                SET access_count = ?, last_accessed = ?
                WHERE id = ?
                """,
                (entry.access_count, entry.last_accessed.isoformat(), entry.id),
            )
            conn.commit()

            return entry

    def update(self, entry: MemoryEntry) -> None:
        """
        Update an existing memory entry.

        Args:
            entry: The updated memory entry

        Raises:
            StorageError: If entry not found
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    UPDATE memories
                    SET content = ?, memory_type = ?, metadata = ?,
                        importance = ?, access_count = ?, last_accessed = ?,
                        embedding = ?
                    WHERE id = ?
                    """,
                    (
                        entry.content,
                        entry.memory_type.value,
                        json.dumps(entry.metadata) if entry.metadata else None,
                        entry.importance,
                        entry.access_count,
                        (
                            entry.last_accessed.isoformat()
                            if entry.last_accessed
                            else None
                        ),
                        json.dumps(entry.embedding) if entry.embedding else None,
                        entry.id,
                    ),
                )

                if cursor.rowcount == 0:
                    raise StorageError(f"Entry not found: {entry.id}")

                # Update FTS index if available
                try:
                    conn.execute(
                        """
                        UPDATE memories_fts
                        SET content = ?
                        WHERE id = ?
                        """,
                        (entry.content, entry.id),
                    )
                except sqlite3.OperationalError:
                    # FTS table doesn't exist, skip
                    pass

                conn.commit()
        except (sqlite3.Error, json.JSONDecodeError) as e:
            raise StorageError(f"Failed to update entry: {e}")

    def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.

        Args:
            entry_id: The ID of the entry to delete

        Returns:
            True if deleted, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM memories WHERE id = ?
                """,
                (entry_id,),
            )

            # Delete from FTS index if available
            try:
                conn.execute(
                    """
                    DELETE FROM memories_fts WHERE id = ?
                    """,
                    (entry_id,),
                )
            except sqlite3.OperationalError:
                # FTS table doesn't exist, skip
                pass

            conn.commit()
            return cursor.rowcount > 0

    def list_entries(
        self,
        memory_type: Optional[MemoryType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MemoryEntry]:
        """
        List memory entries with optional filtering.

        Args:
            memory_type: Filter by memory type (None for all)
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)

        Returns:
            List of memory entries
        """
        query = "SELECT * FROM memories"
        params = []

        if memory_type is not None:
            query += " WHERE memory_type = ?"
            params.append(memory_type.value)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def count(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Count memory entries.

        Args:
            memory_type: Filter by memory type (None for all)

        Returns:
            Total number of entries
        """
        query = "SELECT COUNT(*) FROM memories"
        params = []

        if memory_type is not None:
            query += " WHERE memory_type = ?"
            params.append(memory_type.value)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()[0]

    def clear(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Clear memory entries.

        Args:
            memory_type: Clear specific type (None for all)

        Returns:
            Number of entries cleared
        """
        with self._get_connection() as conn:
            if memory_type is None:
                # Clear all entries
                cursor = conn.execute("DELETE FROM memories")
                # Clear FTS index
                try:
                    conn.execute("DELETE FROM memories_fts")
                except sqlite3.OperationalError:
                    pass
            else:
                # Clear specific type
                cursor = conn.execute(
                    "DELETE FROM memories WHERE memory_type = ?",
                    (memory_type.value,),
                )
                # Clear FTS index for deleted entries
                try:
                    conn.execute(
                        """
                        DELETE FROM memories_fts
                        WHERE id NOT IN (SELECT id FROM memories)
                        """
                    )
                except sqlite3.OperationalError:
                    pass

            conn.commit()
            return cursor.rowcount

    def search(
        self, query: str, memory_type: Optional[MemoryType] = None, limit: int = 10
    ) -> List[MemoryEntry]:
        """
        Search for memories by keyword/content.

        Uses FTS5 full-text search if available, otherwise falls back to LIKE.

        Args:
            query: Search query string
            memory_type: Filter by memory type
            limit: Maximum results to return

        Returns:
            List of matching memory entries
        """
        with self._get_connection() as conn:
            try:
                # Try FTS search first (faster, better ranking)
                fts_query = """
                    SELECT m.* FROM memories m
                    JOIN memories_fts fts ON m.id = fts.id
                    WHERE memories_fts MATCH ?
                """
                params = [query]

                if memory_type is not None:
                    fts_query += " AND m.memory_type = ?"
                    params.append(memory_type.value)

                fts_query += " ORDER BY rank LIMIT ?"
                params.append(limit)

                cursor = conn.execute(fts_query, params)
                return [self._row_to_entry(row) for row in cursor.fetchall()]

            except sqlite3.OperationalError:
                # FTS not available, fall back to LIKE
                like_query = "SELECT * FROM memories WHERE content LIKE ?"
                params = [f"%{query}%"]

                if memory_type is not None:
                    like_query += " AND memory_type = ?"
                    params.append(memory_type.value)

                like_query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(like_query, params)
                return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """
        Get storage statistics.

        Returns:
            Dictionary with storage stats (count by type, database size, etc.)
        """
        with self._get_connection() as conn:
            stats = {
                "total_entries": self.count(),
                "db_size_bytes": (
                    self.db_path.stat().st_size if self.db_path.exists() else 0
                ),
                "db_path": str(self.db_path),
                "by_type": {},
            }

            # Count by type
            for memory_type in MemoryType:
                count = self.count(memory_type)
                if count > 0:
                    stats["by_type"][memory_type.value] = count

            # Database-specific stats
            cursor = conn.execute("PRAGMA page_count")
            stats["page_count"] = cursor.fetchone()[0]

            cursor = conn.execute("PRAGMA page_size")
            stats["page_size"] = cursor.fetchone()[0]

            return stats

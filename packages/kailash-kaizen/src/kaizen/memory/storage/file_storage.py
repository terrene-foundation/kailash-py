"""
File-based storage backend for memory system.

Uses JSONL format (one JSON object per line) for simple, dependency-free storage.
Best for: prototyping, small datasets, no database dependencies.
"""

import json
from pathlib import Path
from typing import List, Optional

from kaizen.memory.storage.base import (
    MemoryEntry,
    MemoryType,
    StorageBackend,
    StorageError,
)


class FileStorage(StorageBackend):
    """
    JSONL-based file storage for memory entries.

    Each memory entry is stored as a JSON object on a separate line.
    Simple, human-readable, no dependencies.

    Performance characteristics:
    - Write: O(1) - append to file
    - Read by ID: O(n) - linear scan
    - Search: O(n) - linear scan
    - Suitable for: <10,000 entries

    For larger datasets, use SQLiteStorage or PostgreSQLStorage.
    """

    def __init__(self, file_path: str = ".kaizen/memory/memories.jsonl"):
        """
        Initialize file storage.

        Args:
            file_path: Path to JSONL file for storage
        """
        self.file_path = Path(file_path)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create file and parent directories if they don't exist."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.touch()

    def _read_all_entries(self) -> List[MemoryEntry]:
        """Read all entries from file."""
        entries = []
        try:
            with open(self.file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:  # Skip empty lines
                        try:
                            data = json.loads(line)
                            entries.append(MemoryEntry.from_dict(data))
                        except (json.JSONDecodeError, KeyError, TypeError) as e:
                            # Skip malformed lines (invalid JSON or missing fields)
                            print(f"Warning: Skipping malformed line: {e}")
                            continue
        except FileNotFoundError:
            # File doesn't exist yet, return empty list
            return []

        return entries

    def _write_all_entries(self, entries: List[MemoryEntry]) -> None:
        """Write all entries to file (overwrites existing file)."""
        with open(self.file_path, "w") as f:
            for entry in entries:
                json.dump(entry.to_dict(), f)
                f.write("\n")

    def store(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry.

        Appends entry to file (O(1) operation).

        Args:
            entry: The memory entry to store

        Returns:
            The ID of the stored entry
        """
        try:
            with open(self.file_path, "a") as f:
                json.dump(entry.to_dict(), f)
                f.write("\n")
            return entry.id
        except (IOError, OSError) as e:
            raise StorageError(f"Failed to store entry: {e}")

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve a memory entry by ID.

        Linear scan through file (O(n) operation).

        Args:
            entry_id: The ID of the entry to retrieve

        Returns:
            The memory entry if found, None otherwise
        """
        entries = self._read_all_entries()
        for entry in entries:
            if entry.id == entry_id:
                entry.update_access()  # Track access
                # Update access count in file
                self._write_all_entries(entries)
                return entry
        return None

    def update(self, entry: MemoryEntry) -> None:
        """
        Update an existing memory entry.

        Reads all entries, updates matching entry, writes back (O(n) operation).

        Args:
            entry: The updated memory entry

        Raises:
            StorageError: If entry not found
        """
        entries = self._read_all_entries()
        found = False
        for i, existing_entry in enumerate(entries):
            if existing_entry.id == entry.id:
                entries[i] = entry
                found = True
                break

        if not found:
            raise StorageError(f"Entry not found: {entry.id}")

        self._write_all_entries(entries)

    def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.

        Reads all entries, filters out target, writes back (O(n) operation).

        Args:
            entry_id: The ID of the entry to delete

        Returns:
            True if deleted, False if not found
        """
        entries = self._read_all_entries()
        original_count = len(entries)
        entries = [e for e in entries if e.id != entry_id]

        if len(entries) == original_count:
            return False  # Not found

        self._write_all_entries(entries)
        return True

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
        entries = self._read_all_entries()

        # Filter by type if specified
        if memory_type is not None:
            entries = [e for e in entries if e.memory_type == memory_type]

        # Apply pagination
        return entries[offset : offset + limit]

    def count(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Count memory entries.

        Args:
            memory_type: Filter by memory type (None for all)

        Returns:
            Total number of entries
        """
        entries = self._read_all_entries()

        if memory_type is not None:
            entries = [e for e in entries if e.memory_type == memory_type]

        return len(entries)

    def clear(self, memory_type: Optional[MemoryType] = None) -> int:
        """
        Clear memory entries.

        Args:
            memory_type: Clear specific type (None for all)

        Returns:
            Number of entries cleared
        """
        if memory_type is None:
            # Clear all entries
            count = self.count()
            self.file_path.write_text("")  # Truncate file
            return count
        else:
            # Clear specific type
            entries = self._read_all_entries()
            original_count = len(entries)
            entries = [e for e in entries if e.memory_type != memory_type]
            cleared_count = original_count - len(entries)
            self._write_all_entries(entries)
            return cleared_count

    def search(
        self, query: str, memory_type: Optional[MemoryType] = None, limit: int = 10
    ) -> List[MemoryEntry]:
        """
        Search for memories by keyword/content.

        Simple case-insensitive substring search (O(n) operation).
        For semantic search, use VectorMemory with embeddings.

        Args:
            query: Search query string
            memory_type: Filter by memory type
            limit: Maximum results to return

        Returns:
            List of matching memory entries
        """
        entries = self._read_all_entries()

        # Filter by type if specified
        if memory_type is not None:
            entries = [e for e in entries if e.memory_type == memory_type]

        # Case-insensitive keyword search
        query_lower = query.lower()
        matches = []
        for entry in entries:
            if query_lower in entry.content.lower():
                matches.append(entry)
                if len(matches) >= limit:
                    break

        return matches

    def get_stats(self) -> dict:
        """
        Get storage statistics.

        Returns:
            Dictionary with storage stats (count by type, file size, etc.)
        """
        entries = self._read_all_entries()
        stats = {
            "total_entries": len(entries),
            "file_size_bytes": (
                self.file_path.stat().st_size if self.file_path.exists() else 0
            ),
            "file_path": str(self.file_path),
            "by_type": {},
        }

        # Count by type
        for memory_type in MemoryType:
            count = len([e for e in entries if e.memory_type == memory_type])
            if count > 0:
                stats["by_type"][memory_type.value] = count

        return stats

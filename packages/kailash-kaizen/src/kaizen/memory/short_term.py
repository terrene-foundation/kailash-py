"""
Short-term memory implementation.

Session-based memory that automatically expires after a configurable duration.
Best for: recent interactions, temporary context, working memory.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend


class ShortTermMemory:
    """
    Short-term memory with automatic expiration.

    Features:
    - Session-based storage (expires after TTL)
    - Automatic cleanup of old entries
    - Fast retrieval for recent memories
    - Configurable retention duration

    Use cases:
    - Recent conversation context
    - Temporary working memory
    - Session-specific data

    Performance:
    - Retrieval: O(1) for recent entries (with cache)
    - Storage: O(1) append
    - Cleanup: O(n) periodic sweep
    """

    def __init__(
        self,
        storage: StorageBackend,
        ttl_seconds: int = 3600,  # 1 hour default
        max_entries: int = 100,  # Prevent unbounded growth
        auto_cleanup: bool = True,
    ):
        """
        Initialize short-term memory.

        Args:
            storage: Storage backend for persistence
            ttl_seconds: Time-to-live in seconds (default: 1 hour)
            max_entries: Maximum entries to keep (default: 100)
            auto_cleanup: Automatically cleanup expired entries (default: True)
        """
        self.storage = storage
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.auto_cleanup = auto_cleanup
        self._last_cleanup = datetime.now(timezone.utc)

    def store(self, content: str, metadata: Optional[Dict] = None) -> str:
        """
        Store content in short-term memory.

        Args:
            content: Content to store
            metadata: Optional metadata

        Returns:
            Entry ID
        """
        # Auto-cleanup if enabled
        if self.auto_cleanup:
            self._cleanup_if_needed()

        # Create entry with short-term type
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.SHORT_TERM,
            metadata=metadata or {},
            importance=0.3,  # Lower importance (transient)
        )

        # Store and return ID
        return self.storage.store(entry)

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve entry by ID.

        Returns None if entry doesn't exist or has expired.

        Args:
            entry_id: Entry ID to retrieve

        Returns:
            Memory entry or None if not found/expired
        """
        entry = self.storage.retrieve(entry_id)

        if entry is None:
            return None

        # Check if expired
        if self._is_expired(entry):
            # Delete expired entry
            self.storage.delete(entry_id)
            return None

        return entry

    def get_recent(self, limit: int = 10) -> List[MemoryEntry]:
        """
        Get recent short-term memories.

        Only returns non-expired entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent memory entries (newest first)
        """
        # Get all short-term entries
        entries = self.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM,
            limit=limit * 2,  # Get extra in case some expired
        )

        # Filter out expired entries
        valid_entries = [e for e in entries if not self._is_expired(e)]

        # Return only requested limit
        return valid_entries[:limit]

    def search(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """
        Search for memories by content.

        Only searches non-expired entries.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching entries
        """
        # Search short-term memories
        results = self.storage.search(
            query, memory_type=MemoryType.SHORT_TERM, limit=limit * 2
        )

        # Filter out expired
        valid_results = [e for e in results if not self._is_expired(e)]

        return valid_results[:limit]

    def clear(self) -> int:
        """
        Clear all short-term memories.

        Returns:
            Number of entries cleared
        """
        return self.storage.clear(memory_type=MemoryType.SHORT_TERM)

    def cleanup_expired(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries removed
        """
        # Get all short-term entries
        entries = self.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM, limit=10000
        )

        # Delete expired ones
        deleted_count = 0
        for entry in entries:
            if self._is_expired(entry):
                self.storage.delete(entry.id)
                deleted_count += 1

        self._last_cleanup = datetime.now(timezone.utc)
        return deleted_count

    def get_stats(self) -> Dict:
        """
        Get memory statistics.

        Returns:
            Dictionary with stats (total, expired, active, oldest, newest)
        """
        entries = self.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM, limit=10000
        )

        total = len(entries)
        expired = sum(1 for e in entries if self._is_expired(e))
        active = total - expired

        oldest = min((e.timestamp for e in entries), default=None)
        newest = max((e.timestamp for e in entries), default=None)

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": expired,
            "oldest_entry": oldest.isoformat() if oldest else None,
            "newest_entry": newest.isoformat() if newest else None,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
        }

    def _is_expired(self, entry: MemoryEntry) -> bool:
        """Check if entry has expired based on TTL."""
        age = datetime.now(timezone.utc) - entry.timestamp
        return age.total_seconds() > self.ttl_seconds

    def _cleanup_if_needed(self) -> None:
        """Cleanup expired entries if auto_cleanup is enabled."""
        # Only cleanup periodically (every 5 minutes)
        if (datetime.now(timezone.utc) - self._last_cleanup).total_seconds() < 300:
            return

        # Cleanup expired entries
        self.cleanup_expired()

        # Enforce max_entries limit
        entries = self.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM, limit=10000
        )
        if len(entries) > self.max_entries:
            # Sort by timestamp (oldest first)
            sorted_entries = sorted(entries, key=lambda e: e.timestamp)

            # Delete oldest entries beyond limit
            for entry in sorted_entries[: len(entries) - self.max_entries]:
                self.storage.delete(entry.id)

"""
Long-term memory implementation.

Persistent memory with importance-based retention and forgetting curve.
Best for: learned preferences, important facts, persistent knowledge.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend


class LongTermMemory:
    """
    Long-term memory with importance-based retention.

    Features:
    - Persistent storage across sessions
    - Importance-based ranking using Ebbinghaus forgetting curve
    - Automatic consolidation of important memories
    - Pruning of low-importance memories

    Use cases:
    - User preferences and settings
    - Learned patterns and behaviors
    - Important facts and knowledge
    - Historical context

    Performance:
    - Retrieval: O(log n) with indexed storage
    - Storage: O(log n) with importance indexing
    - Consolidation: O(n) periodic sweep
    """

    def __init__(
        self,
        storage: StorageBackend,
        importance_threshold: float = 0.1,  # Prune below this
        max_entries: int = 10000,  # Prevent unbounded growth
        auto_consolidate: bool = True,
    ):
        """
        Initialize long-term memory.

        Args:
            storage: Storage backend for persistence
            importance_threshold: Minimum importance to keep (default: 0.1)
            max_entries: Maximum entries to keep (default: 10,000)
            auto_consolidate: Automatically consolidate memories (default: True)
        """
        self.storage = storage
        self.importance_threshold = importance_threshold
        self.max_entries = max_entries
        self.auto_consolidate = auto_consolidate
        self._last_consolidation = datetime.now(timezone.utc)

    def store(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        importance: float = 0.5,
    ) -> str:
        """
        Store content in long-term memory.

        Args:
            content: Content to store
            metadata: Optional metadata
            importance: Initial importance score (0.0-1.0)

        Returns:
            Entry ID
        """
        # Auto-consolidate if enabled
        if self.auto_consolidate:
            self._consolidate_if_needed()

        # Create entry with long-term type
        entry = MemoryEntry(
            content=content,
            memory_type=MemoryType.LONG_TERM,
            metadata=metadata or {},
            importance=importance,
        )

        # Store and return ID
        return self.storage.store(entry)

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Retrieve entry by ID.

        Updates access tracking for importance calculation.

        Args:
            entry_id: Entry ID to retrieve

        Returns:
            Memory entry or None if not found
        """
        return self.storage.retrieve(entry_id)

    def get_important(
        self, limit: int = 10, min_importance: Optional[float] = None
    ) -> List[MemoryEntry]:
        """
        Get most important long-term memories.

        Sorted by calculated importance (Ebbinghaus curve).

        Args:
            limit: Maximum number of entries to return
            min_importance: Minimum importance threshold (default: self.importance_threshold)

        Returns:
            List of important memory entries
        """
        threshold = (
            min_importance if min_importance is not None else self.importance_threshold
        )

        # Get all long-term entries
        entries = self.storage.list_entries(
            memory_type=MemoryType.LONG_TERM, limit=limit * 5
        )

        # Calculate current importance for each
        for entry in entries:
            entry.importance = entry.calculate_importance()

        # Filter by threshold and sort
        important = [e for e in entries if e.importance >= threshold]
        important.sort(key=lambda e: e.importance, reverse=True)

        return important[:limit]

    def search(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """
        Search for memories by content.

        Results ranked by importance.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching entries, sorted by importance
        """
        # Search long-term memories
        results = self.storage.search(
            query, memory_type=MemoryType.LONG_TERM, limit=limit * 2
        )

        # Calculate importance and sort
        for entry in results:
            entry.importance = entry.calculate_importance()

        results.sort(key=lambda e: e.importance, reverse=True)

        return results[:limit]

    def update_importance(self, entry_id: str, importance: float) -> None:
        """
        Update importance score for an entry.

        Args:
            entry_id: Entry ID to update
            importance: New importance score (0.0-1.0)

        Raises:
            StorageError: If entry not found
        """
        entry = self.storage.retrieve(entry_id)
        if entry is None:
            from kaizen.memory.storage.base import StorageError

            raise StorageError(f"Entry not found: {entry_id}")

        entry.importance = importance
        self.storage.update(entry)

    def consolidate(self) -> Dict[str, int]:
        """
        Consolidate memories by pruning low-importance entries.

        Uses Ebbinghaus forgetting curve to calculate current importance.

        Returns:
            Dictionary with consolidation stats (pruned, kept, total)
        """
        # Get all long-term entries
        entries = self.storage.list_entries(
            memory_type=MemoryType.LONG_TERM, limit=100000
        )

        # Calculate current importance
        for entry in entries:
            entry.importance = entry.calculate_importance()

        # Separate into keep and prune
        to_keep = [e for e in entries if e.importance >= self.importance_threshold]
        to_prune = [e for e in entries if e.importance < self.importance_threshold]

        # Enforce max_entries by pruning lowest importance first
        if len(to_keep) > self.max_entries:
            to_keep.sort(key=lambda e: e.importance, reverse=True)
            to_prune.extend(to_keep[self.max_entries :])
            to_keep = to_keep[: self.max_entries]

        # Delete pruned entries
        pruned_count = 0
        for entry in to_prune:
            self.storage.delete(entry.id)
            pruned_count += 1

        # Update importance scores for kept entries
        for entry in to_keep:
            self.storage.update(entry)

        self._last_consolidation = datetime.now(timezone.utc)

        return {
            "pruned": pruned_count,
            "kept": len(to_keep),
            "total": len(entries),
        }

    def clear(self) -> int:
        """
        Clear all long-term memories.

        Returns:
            Number of entries cleared
        """
        return self.storage.clear(memory_type=MemoryType.LONG_TERM)

    def get_stats(self) -> Dict:
        """
        Get memory statistics.

        Returns:
            Dictionary with stats
        """
        entries = self.storage.list_entries(
            memory_type=MemoryType.LONG_TERM, limit=100000
        )

        # Calculate importance distribution
        for entry in entries:
            entry.importance = entry.calculate_importance()

        high_importance = sum(1 for e in entries if e.importance >= 0.7)
        medium_importance = sum(1 for e in entries if 0.3 <= e.importance < 0.7)
        low_importance = sum(1 for e in entries if e.importance < 0.3)

        avg_importance = (
            sum(e.importance for e in entries) / len(entries) if entries else 0.0
        )

        return {
            "total_entries": len(entries),
            "high_importance": high_importance,
            "medium_importance": medium_importance,
            "low_importance": low_importance,
            "avg_importance": avg_importance,
            "importance_threshold": self.importance_threshold,
            "max_entries": self.max_entries,
        }

    def _consolidate_if_needed(self) -> None:
        """Consolidate memories if auto_consolidate is enabled."""
        # Only consolidate periodically (every 1 hour)
        if (
            datetime.now(timezone.utc) - self._last_consolidation
        ).total_seconds() < 3600:
            return

        # Consolidate memories
        self.consolidate()

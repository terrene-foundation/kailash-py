"""
MemoryProvider Abstract Interface.

Defines the standard interface for memory providers used by
autonomous agents like LocalKaizenAdapter.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from .types import MemoryContext, MemoryEntry, RetrievalStrategy


class MemoryProvider(ABC):
    """Abstract interface for memory providers.

    Provides a standardized API for memory operations used by
    autonomous agents. Memory providers handle storage, retrieval,
    context building, and memory management.

    The interface is designed to be:
    - Session-aware: Operations are scoped to sessions
    - Strategy-aware: Different retrieval strategies supported
    - Token-aware: Context building respects token budgets
    - LLM-ready: Output formats suitable for LLM consumption

    Implementations:
    - BufferMemoryAdapter: Wraps existing BufferMemory
    - HierarchicalMemory: Multi-tier with hot/warm/cold storage
    """

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry.

        Persists the entry to storage and returns its ID.
        If the entry already has an ID, it may be used or
        a new one generated depending on implementation.

        Args:
            entry: The memory entry to store

        Returns:
            The ID of the stored entry

        Raises:
            MemoryStorageError: If storage fails
        """
        pass

    @abstractmethod
    async def recall(
        self,
        query: str = "",
        session_id: str = "",
        max_entries: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryEntry]:
        """Recall relevant memory entries.

        Retrieves entries matching the query and filters.
        If query is empty, returns recent entries.
        If session_id is provided, only entries from that
        session are returned.

        Args:
            query: Search query (optional, for semantic search)
            session_id: Filter by session (optional)
            max_entries: Maximum entries to return
            filters: Additional filters (source, role, tags, etc.)

        Returns:
            List of matching memory entries

        Raises:
            MemoryRetrievalError: If retrieval fails
        """
        pass

    @abstractmethod
    async def build_context(
        self,
        query: str = "",
        session_id: str = "",
        max_tokens: int = 4000,
        strategy: RetrievalStrategy = RetrievalStrategy.RECENCY,
    ) -> MemoryContext:
        """Build LLM-ready context from memories.

        Retrieves and compiles memories into a context suitable
        for LLM prompt injection. Respects token budget by
        summarizing overflow entries when necessary.

        Token allocation (default):
        - 70% for verbatim entries
        - 30% reserved for summary

        Args:
            query: Query for relevance ranking (optional)
            session_id: Filter by session (optional)
            max_tokens: Maximum token budget for context
            strategy: Retrieval strategy to use

        Returns:
            MemoryContext with entries and optional summary

        Raises:
            MemoryContextError: If context building fails
        """
        pass

    @abstractmethod
    async def summarize(
        self,
        session_id: str = "",
        entries: Optional[List[MemoryEntry]] = None,
    ) -> str:
        """Summarize memory entries.

        Creates a summary of the provided entries or all
        entries from the session. Used for context overflow
        and long-term consolidation.

        Args:
            session_id: Session to summarize (used if entries not provided)
            entries: Specific entries to summarize (optional)

        Returns:
            Summary string (empty if nothing to summarize)

        Raises:
            MemorySummarizationError: If summarization fails
        """
        pass

    @abstractmethod
    async def forget(
        self,
        entry_id: Optional[str] = None,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Remove memory entries.

        Deletes entries matching the criteria:
        - If entry_id provided: Delete specific entry
        - If session_id provided: Delete all entries in session
        - If before provided: Delete entries before timestamp
        - Multiple criteria can be combined

        Args:
            entry_id: Specific entry to delete
            session_id: Session to clear
            before: Delete entries before this time

        Returns:
            Number of entries deleted

        Raises:
            MemoryDeletionError: If deletion fails
        """
        pass

    # Optional methods with default implementations

    async def store_many(self, entries: List[MemoryEntry]) -> List[str]:
        """Store multiple memory entries.

        Bulk storage operation. Default implementation
        calls store() for each entry.

        Args:
            entries: List of entries to store

        Returns:
            List of IDs for stored entries
        """
        return [await self.store(entry) for entry in entries]

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a specific entry by ID.

        Default implementation uses recall with empty query.
        Implementations may override for efficiency.

        Args:
            entry_id: ID of entry to retrieve

        Returns:
            MemoryEntry if found, None otherwise
        """
        # Default: Search through all entries
        # Implementations should override with direct lookup
        entries = await self.recall(max_entries=1000)
        for entry in entries:
            if entry.id == entry_id:
                return entry
        return None

    async def count(
        self,
        session_id: str = "",
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count entries matching criteria.

        Default implementation retrieves and counts.
        Implementations may override for efficiency.

        Args:
            session_id: Filter by session
            filters: Additional filters

        Returns:
            Count of matching entries
        """
        entries = await self.recall(
            session_id=session_id,
            max_entries=100000,
            filters=filters,
        )
        return len(entries)

    async def clear(self, session_id: str = "") -> int:
        """Clear all entries, optionally for a specific session.

        Args:
            session_id: Session to clear (empty = all)

        Returns:
            Number of entries cleared
        """
        return await self.forget(session_id=session_id if session_id else None)

    async def health_check(self) -> bool:
        """Check if the memory provider is healthy.

        Returns:
            True if healthy, False otherwise
        """
        return True


class MemoryProviderError(Exception):
    """Base exception for memory provider errors."""

    pass


class MemoryStorageError(MemoryProviderError):
    """Exception raised when storage operations fail."""

    pass


class MemoryRetrievalError(MemoryProviderError):
    """Exception raised when retrieval operations fail."""

    pass


class MemoryContextError(MemoryProviderError):
    """Exception raised when context building fails."""

    pass


class MemorySummarizationError(MemoryProviderError):
    """Exception raised when summarization fails."""

    pass


class MemoryDeletionError(MemoryProviderError):
    """Exception raised when deletion fails."""

    pass

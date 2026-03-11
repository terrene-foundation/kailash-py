"""
BufferMemoryAdapter - Adapter wrapping existing BufferMemory.

Provides MemoryProvider interface for the existing BufferMemory
implementation, enabling backward compatibility while supporting
the new autonomous agent integration.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from kaizen.memory.buffer import BufferMemory

from .provider import MemoryProvider
from .types import (
    MemoryContext,
    MemoryEntry,
    MemorySource,
    RetrievalStrategy,
    estimate_tokens,
)

logger = logging.getLogger(__name__)


class BufferMemoryAdapter(MemoryProvider):
    """Adapter wrapping BufferMemory to provide MemoryProvider interface.

    This adapter enables existing BufferMemory instances to be used
    with the new MemoryProvider interface required by LocalKaizenAdapter
    and other autonomous agent implementations.

    Features:
    - Wraps existing BufferMemory with no changes to underlying storage
    - Converts between turn format and MemoryEntry format
    - Supports keyword-based recall (no semantic search)
    - Context building with recency strategy
    - Session-scoped operations

    Example:
        >>> from kaizen.memory import BufferMemory
        >>> from kaizen.memory.providers import BufferMemoryAdapter
        >>>
        >>> buffer = BufferMemory(max_turns=100)
        >>> adapter = BufferMemoryAdapter(buffer)
        >>>
        >>> entry = MemoryEntry(
        ...     content="Hello, how are you?",
        ...     role="user",
        ...     session_id="session-1",
        ... )
        >>> entry_id = await adapter.store(entry)
        >>> context = await adapter.build_context(session_id="session-1")
    """

    def __init__(
        self,
        buffer_memory: Optional[BufferMemory] = None,
        max_turns: int = 100,
    ):
        """Initialize the adapter.

        Args:
            buffer_memory: Existing BufferMemory to wrap (optional)
            max_turns: Max turns if creating new BufferMemory
        """
        self._buffer = buffer_memory or BufferMemory(max_turns=max_turns)
        self._entries: Dict[str, MemoryEntry] = {}  # Entry ID -> Entry lookup

    @property
    def buffer_memory(self) -> BufferMemory:
        """Access the underlying BufferMemory."""
        return self._buffer

    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry.

        Converts the entry to a turn format and stores it in
        the underlying BufferMemory. Also maintains an entry
        lookup for recall operations.

        Args:
            entry: The memory entry to store

        Returns:
            The ID of the stored entry
        """
        # Store in lookup for recall
        self._entries[entry.id] = entry

        # Convert to turn format for BufferMemory
        if entry.role == "user":
            turn = {
                "user": entry.content,
                "agent": "",
                "timestamp": entry.timestamp.isoformat(),
                "entry_id": entry.id,
                "metadata": entry.metadata,
            }
        elif entry.role == "assistant":
            turn = {
                "user": "",
                "agent": entry.content,
                "timestamp": entry.timestamp.isoformat(),
                "entry_id": entry.id,
                "metadata": entry.metadata,
            }
        else:
            # System or tool messages stored as metadata-annotated turns
            turn = {
                "user": "",
                "agent": entry.content,
                "timestamp": entry.timestamp.isoformat(),
                "entry_id": entry.id,
                "metadata": {
                    **entry.metadata,
                    "role": entry.role,
                    "source": entry.source.value,
                },
            }

        self._buffer.save_turn(entry.session_id, turn)

        logger.debug(f"Stored entry {entry.id} for session {entry.session_id}")
        return entry.id

    async def recall(
        self,
        query: str = "",
        session_id: str = "",
        max_entries: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryEntry]:
        """Recall relevant memory entries.

        Uses keyword matching on the query and filters by session.
        Returns entries sorted by recency (newest first).

        Args:
            query: Search query (keyword matching)
            session_id: Filter by session
            max_entries: Maximum entries to return
            filters: Additional filters

        Returns:
            List of matching memory entries
        """
        results = []

        # Get entries from lookup
        for entry in self._entries.values():
            # Session filter
            if session_id and entry.session_id != session_id:
                continue

            # Filter check
            if not entry.matches_filter(filters):
                continue

            # Query matching (keyword-based)
            if query:
                query_lower = query.lower()
                content_lower = entry.content.lower()
                if query_lower not in content_lower:
                    # Check tags too
                    tag_match = any(query_lower in tag.lower() for tag in entry.tags)
                    if not tag_match:
                        continue

            results.append(entry)

        # Sort by timestamp (newest first)
        results.sort(key=lambda e: e.timestamp, reverse=True)

        return results[:max_entries]

    async def build_context(
        self,
        query: str = "",
        session_id: str = "",
        max_tokens: int = 4000,
        strategy: RetrievalStrategy = RetrievalStrategy.RECENCY,
    ) -> MemoryContext:
        """Build LLM-ready context from memories.

        For BufferMemoryAdapter, uses recency strategy regardless
        of requested strategy (no semantic search capability).

        Args:
            query: Query (used for keyword filtering)
            session_id: Session to build context for
            max_tokens: Maximum token budget
            strategy: Retrieval strategy (ignored, uses recency)

        Returns:
            MemoryContext with entries within token budget
        """
        # Get all entries for session
        entries = await self.recall(
            query=query,
            session_id=session_id,
            max_entries=1000,
        )

        # Sort by strategy (all implemented as recency for buffer)
        if strategy == RetrievalStrategy.IMPORTANCE:
            entries.sort(key=lambda e: e.importance, reverse=True)
        else:
            entries.sort(key=lambda e: e.timestamp, reverse=True)

        # Token-aware selection
        entry_budget = int(max_tokens * 0.7)  # 70% for entries
        selected_entries = []
        current_tokens = 0

        for entry in entries:
            entry_tokens = estimate_tokens(entry.content)
            if current_tokens + entry_tokens > entry_budget:
                break
            selected_entries.append(entry)
            current_tokens += entry_tokens

        # Reverse to chronological order for context
        selected_entries.reverse()

        context = MemoryContext(
            entries=selected_entries,
            summary="",  # BufferMemory doesn't summarize
            total_tokens=current_tokens,
            entries_retrieved=len(selected_entries),
            entries_summarized=0,
            retrieval_strategy=strategy,
            retrieval_query=query,
        )

        return context

    async def summarize(
        self,
        session_id: str = "",
        entries: Optional[List[MemoryEntry]] = None,
    ) -> str:
        """Summarize memory entries.

        BufferMemoryAdapter does not support summarization.
        Returns empty string.

        Args:
            session_id: Session to summarize
            entries: Entries to summarize

        Returns:
            Empty string (no summarization support)
        """
        # BufferMemory doesn't have summarization capability
        return ""

    async def forget(
        self,
        entry_id: Optional[str] = None,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Remove memory entries.

        Args:
            entry_id: Specific entry to delete
            session_id: Session to clear
            before: Delete entries before this time

        Returns:
            Number of entries deleted
        """
        deleted = 0

        if entry_id:
            # Delete specific entry
            if entry_id in self._entries:
                del self._entries[entry_id]
                deleted = 1
        elif not session_id and not before:
            # No criteria = delete all entries
            deleted = len(self._entries)
            self._entries.clear()
        else:
            # Find entries to delete based on criteria
            to_delete = []
            for eid, entry in self._entries.items():
                should_delete = False

                if session_id and entry.session_id == session_id:
                    should_delete = True
                elif before and entry.timestamp < before:
                    should_delete = True

                if should_delete:
                    to_delete.append(eid)

            # Delete entries
            for eid in to_delete:
                del self._entries[eid]
                deleted += 1

        # Clear underlying buffer if session cleared
        if session_id and not entry_id:
            self._buffer.clear(session_id)

        logger.debug(f"Forgot {deleted} entries")
        return deleted

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a specific entry by ID.

        Direct lookup from internal dictionary.

        Args:
            entry_id: ID of entry to retrieve

        Returns:
            MemoryEntry if found, None otherwise
        """
        return self._entries.get(entry_id)

    async def count(
        self,
        session_id: str = "",
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count entries matching criteria.

        Args:
            session_id: Filter by session
            filters: Additional filters

        Returns:
            Count of matching entries
        """
        count = 0
        for entry in self._entries.values():
            if session_id and entry.session_id != session_id:
                continue
            if not entry.matches_filter(filters):
                continue
            count += 1
        return count

    def load_from_buffer(self, session_id: str) -> None:
        """Load existing turns from BufferMemory into entry lookup.

        Useful when wrapping a BufferMemory that already has data.

        Args:
            session_id: Session to load from
        """
        context = self._buffer.load_context(session_id)
        turns = context.get("turns", [])

        for turn in turns:
            # Create entry for user message
            if turn.get("user"):
                entry = MemoryEntry(
                    id=turn.get("entry_id", str(id(turn))),
                    content=turn["user"],
                    role="user",
                    session_id=session_id,
                    source=MemorySource.CONVERSATION,
                )
                self._entries[entry.id] = entry

            # Create entry for agent message
            if turn.get("agent"):
                entry = MemoryEntry(
                    id=f"{turn.get('entry_id', str(id(turn)))}_agent",
                    content=turn["agent"],
                    role="assistant",
                    session_id=session_id,
                    source=MemorySource.CONVERSATION,
                )
                self._entries[entry.id] = entry

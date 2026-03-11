"""
HierarchicalMemory - Multi-tier memory with hot/warm/cold storage.

Implements MemoryProvider with automatic tier management:
- Hot tier: In-memory for fast access (<1ms)
- Warm tier: Database storage for persistence (10-50ms)
- Cold tier: Archive storage (optional, 100ms+)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .buffer_adapter import BufferMemoryAdapter
from .provider import MemoryProvider
from .types import (
    MemoryContext,
    MemoryEntry,
    MemorySource,
    RetrievalStrategy,
    estimate_tokens,
)

try:
    from .dataflow_backend import DATAFLOW_AVAILABLE, DataFlowMemoryBackend
except ImportError:
    DataFlowMemoryBackend = None
    DATAFLOW_AVAILABLE = False


logger = logging.getLogger(__name__)


class HierarchicalMemory(MemoryProvider):
    """Multi-tier hierarchical memory with automatic promotion/demotion.

    Implements a three-tier memory architecture:

    Hot Tier (In-Memory):
        - BufferMemoryAdapter-based storage
        - Fastest access (<1ms)
        - Limited size (configurable max entries)
        - Entries automatically demoted to warm tier when hot is full

    Warm Tier (Database):
        - DataFlow-backed persistent storage
        - Medium access speed (10-50ms)
        - Persistent across restarts
        - Supports indexed search

    Cold Tier (Archive):
        - Optional archive storage
        - Slowest access (100ms+)
        - For long-term archival

    Retrieval Strategy:
        - Retrieves from all tiers in parallel
        - Merges results based on strategy (recency, importance, relevance)
        - Builds context within token budget

    Example:
        >>> from kaizen.memory.providers import HierarchicalMemory
        >>>
        >>> memory = HierarchicalMemory(
        ...     hot_size=1000,
        ...     warm_backend=dataflow_backend,  # Optional
        ... )
        >>>
        >>> entry = MemoryEntry(content="Important info", session_id="s1")
        >>> await memory.store(entry)
        >>>
        >>> context = await memory.build_context(session_id="s1", max_tokens=4000)
    """

    def __init__(
        self,
        hot_size: int = 1000,
        warm_backend: Optional["DataFlowMemoryBackend"] = None,
        cold_backend: Optional[Any] = None,
        embedding_provider: Optional[Callable[[str], List[float]]] = None,
        promotion_threshold: float = 0.7,
        demotion_age_hours: int = 24,
        summarizer: Optional[Callable[[List[MemoryEntry]], str]] = None,
    ):
        """Initialize HierarchicalMemory.

        Args:
            hot_size: Maximum entries in hot tier
            warm_backend: DataFlow backend for warm tier (optional)
            cold_backend: Archive backend for cold tier (optional)
            embedding_provider: Function to generate embeddings (optional)
            promotion_threshold: Importance threshold for hot promotion
            demotion_age_hours: Hours of inactivity before demotion
            summarizer: Function to summarize entries (optional)
        """
        # Hot tier (always in-memory)
        self._hot = BufferMemoryAdapter(max_turns=hot_size)
        self._hot_size = hot_size

        # Warm tier (optional database)
        self._warm = warm_backend

        # Cold tier (optional archive)
        self._cold = cold_backend

        # Embedding provider for semantic search
        self._embedding_provider = embedding_provider

        # Tier management settings
        self._promotion_threshold = promotion_threshold
        self._demotion_age_hours = demotion_age_hours

        # Summarizer for context overflow
        self._summarizer = summarizer

        logger.debug(
            f"Initialized HierarchicalMemory: "
            f"hot_size={hot_size}, "
            f"warm={'enabled' if warm_backend else 'disabled'}, "
            f"cold={'enabled' if cold_backend else 'disabled'}"
        )

    @property
    def has_warm_tier(self) -> bool:
        """Check if warm tier is available."""
        return self._warm is not None

    @property
    def has_cold_tier(self) -> bool:
        """Check if cold tier is available."""
        return self._cold is not None

    @property
    def has_embeddings(self) -> bool:
        """Check if embedding provider is available."""
        return self._embedding_provider is not None

    async def store(self, entry: MemoryEntry) -> str:
        """Store entry in appropriate tier.

        High importance entries go to hot tier.
        Lower importance entries go directly to warm tier.

        Args:
            entry: MemoryEntry to store

        Returns:
            Entry ID
        """
        # Generate embedding if provider available
        if self._embedding_provider and not entry.embedding:
            try:
                entry.embedding = self._embedding_provider(entry.content)
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")

        # Determine target tier
        if entry.importance >= self._promotion_threshold:
            # Store in hot tier
            await self._hot.store(entry)

            # Check if hot tier needs demotion
            await self._maybe_demote()
        elif self._warm:
            # Store in warm tier directly
            self._warm.store(entry)
        else:
            # No warm tier, use hot tier
            await self._hot.store(entry)
            await self._maybe_demote()

        logger.debug(f"Stored entry {entry.id} (importance={entry.importance})")
        return entry.id

    async def recall(
        self,
        query: str = "",
        session_id: str = "",
        max_entries: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryEntry]:
        """Recall entries from all tiers.

        Retrieves from hot and warm tiers in parallel,
        merges and deduplicates results.

        Args:
            query: Search query (optional)
            session_id: Filter by session
            max_entries: Maximum entries to return
            filters: Additional filters

        Returns:
            List of matching entries
        """
        # Retrieve from all tiers in parallel
        tasks = []

        # Hot tier
        tasks.append(
            self._hot.recall(
                query=query,
                session_id=session_id,
                max_entries=max_entries,
                filters=filters,
            )
        )

        # Warm tier (if available)
        if self._warm:
            tasks.append(
                self._recall_from_warm(
                    query=query,
                    session_id=session_id,
                    max_entries=max_entries,
                    filters=filters,
                )
            )

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results
        all_entries: Dict[str, MemoryEntry] = {}

        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Tier recall failed: {result}")
                continue
            for entry in result:
                # Deduplicate by ID (hot tier takes precedence)
                if entry.id not in all_entries:
                    all_entries[entry.id] = entry

        entries = list(all_entries.values())

        # Sort by timestamp (newest first)
        entries.sort(key=lambda e: e.timestamp, reverse=True)

        return entries[:max_entries]

    async def _recall_from_warm(
        self,
        query: str,
        session_id: str,
        max_entries: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[MemoryEntry]:
        """Recall from warm tier (sync to async wrapper)."""
        if not self._warm:
            return []

        if query:
            return self._warm.search(query, session_id, max_entries)
        else:
            return self._warm.list_entries(
                session_id=session_id,
                filters=filters,
                limit=max_entries,
            )

    async def build_context(
        self,
        query: str = "",
        session_id: str = "",
        max_tokens: int = 4000,
        strategy: RetrievalStrategy = RetrievalStrategy.RECENCY,
    ) -> MemoryContext:
        """Build LLM-ready context from all tiers.

        Args:
            query: Query for relevance ranking
            session_id: Filter by session
            max_tokens: Maximum token budget
            strategy: Retrieval strategy

        Returns:
            MemoryContext with entries and optional summary
        """
        # Recall all relevant entries
        entries = await self.recall(
            query=query,
            session_id=session_id,
            max_entries=1000,  # Get many, then filter by tokens
        )

        # Sort by strategy
        entries = self._sort_by_strategy(entries, query, strategy)

        # Token-aware selection
        entry_budget = int(max_tokens * 0.7)  # 70% for entries
        summary_budget = int(max_tokens * 0.3)  # 30% for summary

        selected_entries = []
        overflow_entries = []
        current_tokens = 0

        for entry in entries:
            entry_tokens = estimate_tokens(entry.content)
            if current_tokens + entry_tokens <= entry_budget:
                selected_entries.append(entry)
                current_tokens += entry_tokens
            else:
                overflow_entries.append(entry)

        # Generate summary for overflow if summarizer available
        summary = ""
        entries_summarized = 0

        if overflow_entries and self._summarizer:
            try:
                summary = self._summarizer(overflow_entries)
                summary_tokens = estimate_tokens(summary)
                if summary_tokens > summary_budget:
                    # Truncate summary
                    summary = summary[: summary_budget * 4]
                entries_summarized = len(overflow_entries)
            except Exception as e:
                logger.warning(f"Summarization failed: {e}")

        # Sort selected entries chronologically for context
        selected_entries.sort(key=lambda e: e.timestamp)

        return MemoryContext(
            entries=selected_entries,
            summary=summary,
            total_tokens=current_tokens + estimate_tokens(summary),
            entries_retrieved=len(selected_entries),
            entries_summarized=entries_summarized,
            retrieval_strategy=strategy,
            retrieval_query=query,
        )

    async def summarize(
        self,
        session_id: str = "",
        entries: Optional[List[MemoryEntry]] = None,
    ) -> str:
        """Summarize memory entries.

        Args:
            session_id: Session to summarize
            entries: Specific entries to summarize

        Returns:
            Summary string (empty if no summarizer or no entries)
        """
        if not self._summarizer:
            return ""

        if entries is None:
            entries = await self.recall(session_id=session_id, max_entries=1000)

        if not entries:
            return ""

        try:
            return self._summarizer(entries)
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return ""

    async def forget(
        self,
        entry_id: Optional[str] = None,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Remove entries from all tiers.

        Args:
            entry_id: Specific entry to delete
            session_id: Session to clear
            before: Delete entries before timestamp

        Returns:
            Total entries deleted
        """
        total_deleted = 0

        # Delete from hot tier
        hot_deleted = await self._hot.forget(
            entry_id=entry_id,
            session_id=session_id,
            before=before,
        )
        total_deleted += hot_deleted

        # Delete from warm tier
        if self._warm:
            if entry_id:
                if self._warm.delete(entry_id):
                    total_deleted += 1
            else:
                warm_deleted = self._warm.delete_many(
                    session_id=session_id,
                    before=before,
                )
                total_deleted += warm_deleted

        return total_deleted

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get entry by ID from any tier.

        Checks hot tier first, then warm.

        Args:
            entry_id: Entry ID to retrieve

        Returns:
            MemoryEntry if found, None otherwise
        """
        # Check hot tier first
        entry = await self._hot.get(entry_id)
        if entry:
            return entry

        # Check warm tier
        if self._warm:
            entry = self._warm.get(entry_id)
            if entry:
                # Promote to hot if accessed
                await self._maybe_promote(entry)
                return entry

        return None

    async def count(
        self,
        session_id: str = "",
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count entries across all tiers.

        Args:
            session_id: Filter by session
            filters: Additional filters

        Returns:
            Total count
        """
        total = 0

        # Count hot tier
        total += await self._hot.count(session_id=session_id, filters=filters)

        # Count warm tier (avoiding duplicates is complex, so this is approximate)
        if self._warm:
            total += self._warm.count(session_id=session_id, filters=filters)

        return total

    def _sort_by_strategy(
        self,
        entries: List[MemoryEntry],
        query: str,
        strategy: RetrievalStrategy,
    ) -> List[MemoryEntry]:
        """Sort entries by retrieval strategy.

        Args:
            entries: Entries to sort
            query: Query for relevance
            strategy: Sorting strategy

        Returns:
            Sorted entries
        """
        if strategy == RetrievalStrategy.RECENCY:
            return sorted(entries, key=lambda e: e.timestamp, reverse=True)

        elif strategy == RetrievalStrategy.IMPORTANCE:
            return sorted(entries, key=lambda e: e.importance, reverse=True)

        elif strategy == RetrievalStrategy.RELEVANCE:
            if not query or not self._embedding_provider:
                # Fall back to recency
                return sorted(entries, key=lambda e: e.timestamp, reverse=True)

            # Calculate relevance scores
            try:
                query_embedding = self._embedding_provider(query)
                for entry in entries:
                    if entry.embedding:
                        entry.metadata["_relevance"] = self._cosine_similarity(
                            query_embedding, entry.embedding
                        )
                    else:
                        entry.metadata["_relevance"] = 0.0

                return sorted(
                    entries,
                    key=lambda e: e.metadata.get("_relevance", 0.0),
                    reverse=True,
                )
            except Exception as e:
                logger.warning(f"Relevance scoring failed: {e}")
                return sorted(entries, key=lambda e: e.timestamp, reverse=True)

        elif strategy == RetrievalStrategy.HYBRID:
            # Weighted combination: 0.4 recency + 0.3 importance + 0.3 relevance
            now = datetime.now(timezone.utc)
            max_age = 86400 * 7  # 7 days in seconds

            for entry in entries:
                # Recency score (0-1, newer = higher)
                age_seconds = (now - entry.timestamp).total_seconds()
                recency = max(0, 1 - (age_seconds / max_age))

                # Importance score (already 0-1)
                importance = entry.importance

                # Relevance score
                relevance = entry.metadata.get("_relevance", 0.5)

                # Combined score
                entry.metadata["_hybrid"] = (
                    0.4 * recency + 0.3 * importance + 0.3 * relevance
                )

            return sorted(
                entries, key=lambda e: e.metadata.get("_hybrid", 0.0), reverse=True
            )

        return entries

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Similarity score (0-1)
        """
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    async def _maybe_demote(self) -> None:
        """Demote entries from hot to warm if hot tier is full."""
        if not self._warm:
            return

        hot_count = await self._hot.count()
        if hot_count <= self._hot_size:
            return

        # Get oldest entries to demote
        entries_to_demote = await self._hot.recall(max_entries=hot_count)

        # Sort by timestamp (oldest first)
        entries_to_demote.sort(key=lambda e: e.timestamp)

        # Demote oldest 10% or until under limit
        demote_count = max(1, int(hot_count * 0.1))
        demote_count = min(demote_count, hot_count - self._hot_size + 1)

        for entry in entries_to_demote[:demote_count]:
            # Move to warm tier
            self._warm.store(entry)
            await self._hot.forget(entry_id=entry.id)

        logger.debug(f"Demoted {demote_count} entries from hot to warm tier")

    async def _maybe_promote(self, entry: MemoryEntry) -> None:
        """Promote entry from warm to hot if important enough."""
        if entry.importance >= self._promotion_threshold:
            await self._hot.store(entry)
            logger.debug(f"Promoted entry {entry.id} to hot tier")

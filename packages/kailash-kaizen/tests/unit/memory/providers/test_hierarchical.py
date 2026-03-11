"""
Unit Tests for HierarchicalMemory (Tier 1)

Tests the HierarchicalMemory implementation:
- Hot tier operations
- Context building with strategies
- Tier promotion/demotion
- Parallel retrieval merging
"""

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from kaizen.memory.providers import (
    HierarchicalMemory,
    MemoryContext,
    MemoryEntry,
    MemorySource,
    RetrievalStrategy,
)


class TestHierarchicalMemoryCreation:
    """Tests for HierarchicalMemory initialization."""

    def test_create_default(self):
        """Test creating with defaults."""
        memory = HierarchicalMemory()

        assert memory._hot_size == 1000
        assert not memory.has_warm_tier
        assert not memory.has_cold_tier
        assert not memory.has_embeddings

    def test_create_with_hot_size(self):
        """Test creating with custom hot size."""
        memory = HierarchicalMemory(hot_size=500)

        assert memory._hot_size == 500

    def test_create_with_embedding_provider(self):
        """Test creating with embedding provider."""

        def mock_embedder(text: str) -> List[float]:
            return [0.1, 0.2, 0.3]

        memory = HierarchicalMemory(embedding_provider=mock_embedder)

        assert memory.has_embeddings


class TestHierarchicalMemoryStore:
    """Tests for HierarchicalMemory.store()."""

    @pytest.mark.asyncio
    async def test_store_high_importance_to_hot(self):
        """Test high importance entries go to hot tier."""
        memory = HierarchicalMemory(promotion_threshold=0.5)

        entry = MemoryEntry(
            content="Important info",
            session_id="s1",
            importance=0.8,
        )
        entry_id = await memory.store(entry)

        assert entry_id == entry.id

        # Verify in hot tier
        hot_count = await memory._hot.count(session_id="s1")
        assert hot_count == 1

    @pytest.mark.asyncio
    async def test_store_low_importance_to_hot_without_warm(self):
        """Test low importance goes to hot when no warm tier."""
        memory = HierarchicalMemory(promotion_threshold=0.7)

        entry = MemoryEntry(
            content="Less important",
            session_id="s1",
            importance=0.3,
        )
        await memory.store(entry)

        # Without warm tier, goes to hot
        hot_count = await memory._hot.count(session_id="s1")
        assert hot_count == 1

    @pytest.mark.asyncio
    async def test_store_generates_embedding(self):
        """Test embedding is generated when provider available."""
        embeddings_called = []

        def mock_embedder(text: str) -> List[float]:
            embeddings_called.append(text)
            return [0.1, 0.2]

        memory = HierarchicalMemory(embedding_provider=mock_embedder)

        entry = MemoryEntry(content="Test content", session_id="s1")
        await memory.store(entry)

        assert len(embeddings_called) == 1
        assert embeddings_called[0] == "Test content"


class TestHierarchicalMemoryRecall:
    """Tests for HierarchicalMemory.recall()."""

    @pytest.mark.asyncio
    async def test_recall_from_hot_tier(self):
        """Test recalling entries from hot tier."""
        memory = HierarchicalMemory()

        for i in range(3):
            await memory.store(
                MemoryEntry(
                    content=f"Message {i}",
                    session_id="s1",
                )
            )

        entries = await memory.recall(session_id="s1")

        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_recall_by_session(self):
        """Test filtering recall by session."""
        memory = HierarchicalMemory()

        await memory.store(MemoryEntry(content="S1 msg", session_id="s1"))
        await memory.store(MemoryEntry(content="S2 msg", session_id="s2"))

        entries = await memory.recall(session_id="s1")

        assert len(entries) == 1
        assert entries[0].session_id == "s1"

    @pytest.mark.asyncio
    async def test_recall_with_query(self):
        """Test recall with keyword query."""
        memory = HierarchicalMemory()

        await memory.store(MemoryEntry(content="Hello world", session_id="s1"))
        await memory.store(MemoryEntry(content="Goodbye world", session_id="s1"))
        await memory.store(MemoryEntry(content="Something else", session_id="s1"))

        entries = await memory.recall(query="world", session_id="s1")

        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_recall_max_entries(self):
        """Test max_entries limit."""
        memory = HierarchicalMemory()

        for i in range(10):
            await memory.store(MemoryEntry(content=f"Msg {i}", session_id="s1"))

        entries = await memory.recall(session_id="s1", max_entries=5)

        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_recall_sorted_by_recency(self):
        """Test recall returns newest first."""
        memory = HierarchicalMemory()

        now = datetime.now(timezone.utc)
        for i in range(3):
            entry = MemoryEntry(
                content=f"Message {i}",
                session_id="s1",
                timestamp=now + timedelta(minutes=i),
            )
            await memory.store(entry)

        entries = await memory.recall(session_id="s1")

        # Newest first
        assert "Message 2" in entries[0].content
        assert "Message 0" in entries[-1].content


class TestHierarchicalMemoryBuildContext:
    """Tests for HierarchicalMemory.build_context()."""

    @pytest.mark.asyncio
    async def test_build_context_basic(self):
        """Test basic context building."""
        memory = HierarchicalMemory()

        await memory.store(MemoryEntry(content="Hello", role="user", session_id="s1"))
        await memory.store(
            MemoryEntry(content="Hi!", role="assistant", session_id="s1")
        )

        context = await memory.build_context(session_id="s1")

        assert isinstance(context, MemoryContext)
        assert len(context.entries) == 2
        assert context.entries_retrieved == 2

    @pytest.mark.asyncio
    async def test_build_context_recency_strategy(self):
        """Test context with recency strategy."""
        memory = HierarchicalMemory()

        now = datetime.now(timezone.utc)
        await memory.store(
            MemoryEntry(
                content="Old message",
                session_id="s1",
                timestamp=now - timedelta(hours=1),
            )
        )
        await memory.store(
            MemoryEntry(
                content="New message",
                session_id="s1",
                timestamp=now,
            )
        )

        context = await memory.build_context(
            session_id="s1",
            strategy=RetrievalStrategy.RECENCY,
        )

        # Should be in chronological order for context
        assert context.entries[-1].content == "New message"

    @pytest.mark.asyncio
    async def test_build_context_importance_strategy(self):
        """Test context with importance strategy."""
        memory = HierarchicalMemory()

        await memory.store(
            MemoryEntry(
                content="Low importance",
                session_id="s1",
                importance=0.3,
            )
        )
        await memory.store(
            MemoryEntry(
                content="High importance",
                session_id="s1",
                importance=0.9,
            )
        )

        context = await memory.build_context(
            session_id="s1",
            strategy=RetrievalStrategy.IMPORTANCE,
            max_tokens=100,
        )

        # High importance should be included
        contents = [e.content for e in context.entries]
        assert "High importance" in contents

    @pytest.mark.asyncio
    async def test_build_context_respects_token_budget(self):
        """Test context respects token budget."""
        memory = HierarchicalMemory()

        # Add many entries
        for i in range(20):
            await memory.store(
                MemoryEntry(
                    content="A" * 100,  # ~25 tokens each
                    session_id="s1",
                )
            )

        # Small budget
        context = await memory.build_context(
            session_id="s1",
            max_tokens=100,
        )

        # Should only include what fits in 70% of budget
        assert context.total_tokens <= 100

    @pytest.mark.asyncio
    async def test_build_context_with_summarizer(self):
        """Test context building with summarizer."""

        def mock_summarizer(entries: List[MemoryEntry]) -> str:
            return f"Summary of {len(entries)} entries"

        memory = HierarchicalMemory(summarizer=mock_summarizer)

        # Add many entries to trigger summarization
        for i in range(20):
            await memory.store(
                MemoryEntry(
                    content="A" * 100,
                    session_id="s1",
                )
            )

        context = await memory.build_context(
            session_id="s1",
            max_tokens=200,  # Small budget to trigger overflow
        )

        # Summary should be generated for overflow
        if context.entries_summarized > 0:
            assert "Summary of" in context.summary

    @pytest.mark.asyncio
    async def test_build_context_chronological_order(self):
        """Test context entries are in chronological order."""
        memory = HierarchicalMemory()

        now = datetime.now(timezone.utc)
        for i in range(3):
            entry = MemoryEntry(
                content=f"Message {i}",
                session_id="s1",
                timestamp=now + timedelta(minutes=i),
            )
            await memory.store(entry)

        context = await memory.build_context(session_id="s1")

        # Entries should be chronological (oldest first)
        assert context.entries[0].content == "Message 0"
        assert context.entries[-1].content == "Message 2"


class TestHierarchicalMemorySummarize:
    """Tests for HierarchicalMemory.summarize()."""

    @pytest.mark.asyncio
    async def test_summarize_without_summarizer(self):
        """Test summarize returns empty without summarizer."""
        memory = HierarchicalMemory()

        await memory.store(MemoryEntry(content="Test", session_id="s1"))

        summary = await memory.summarize(session_id="s1")

        assert summary == ""

    @pytest.mark.asyncio
    async def test_summarize_with_summarizer(self):
        """Test summarize uses provided summarizer."""

        def mock_summarizer(entries: List[MemoryEntry]) -> str:
            return f"Summary: {len(entries)} entries"

        memory = HierarchicalMemory(summarizer=mock_summarizer)

        await memory.store(MemoryEntry(content="Test 1", session_id="s1"))
        await memory.store(MemoryEntry(content="Test 2", session_id="s1"))

        summary = await memory.summarize(session_id="s1")

        assert "Summary: 2 entries" in summary


class TestHierarchicalMemoryForget:
    """Tests for HierarchicalMemory.forget()."""

    @pytest.mark.asyncio
    async def test_forget_by_entry_id(self):
        """Test forgetting specific entry."""
        memory = HierarchicalMemory()

        entry = MemoryEntry(content="Test", session_id="s1")
        await memory.store(entry)

        deleted = await memory.forget(entry_id=entry.id)

        assert deleted == 1
        assert await memory.count(session_id="s1") == 0

    @pytest.mark.asyncio
    async def test_forget_by_session(self):
        """Test forgetting all entries in session."""
        memory = HierarchicalMemory()

        for i in range(5):
            await memory.store(MemoryEntry(content=f"Msg {i}", session_id="s1"))
        await memory.store(MemoryEntry(content="Other", session_id="s2"))

        deleted = await memory.forget(session_id="s1")

        assert deleted == 5
        assert await memory.count(session_id="s1") == 0
        assert await memory.count(session_id="s2") == 1

    @pytest.mark.asyncio
    async def test_forget_by_timestamp(self):
        """Test forgetting entries before timestamp."""
        memory = HierarchicalMemory()

        now = datetime.now(timezone.utc)
        old_entry = MemoryEntry(
            content="Old",
            session_id="s1",
            timestamp=now - timedelta(hours=2),
        )
        new_entry = MemoryEntry(
            content="New",
            session_id="s1",
            timestamp=now,
        )

        await memory.store(old_entry)
        await memory.store(new_entry)

        deleted = await memory.forget(before=now - timedelta(hours=1))

        assert deleted == 1
        assert await memory.count(session_id="s1") == 1


class TestHierarchicalMemoryGet:
    """Tests for HierarchicalMemory.get()."""

    @pytest.mark.asyncio
    async def test_get_existing_entry(self):
        """Test getting existing entry."""
        memory = HierarchicalMemory()

        entry = MemoryEntry(content="Test content", session_id="s1")
        await memory.store(entry)

        retrieved = await memory.get(entry.id)

        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.content == "Test content"

    @pytest.mark.asyncio
    async def test_get_nonexistent_entry(self):
        """Test getting nonexistent entry."""
        memory = HierarchicalMemory()

        retrieved = await memory.get("nonexistent-id")

        assert retrieved is None


class TestHierarchicalMemoryCount:
    """Tests for HierarchicalMemory.count()."""

    @pytest.mark.asyncio
    async def test_count_all(self):
        """Test counting all entries."""
        memory = HierarchicalMemory()

        for i in range(5):
            await memory.store(MemoryEntry(content=f"Msg {i}", session_id=f"s{i}"))

        count = await memory.count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_by_session(self):
        """Test counting by session."""
        memory = HierarchicalMemory()

        for i in range(3):
            await memory.store(MemoryEntry(content=f"Msg {i}", session_id="s1"))
        for i in range(2):
            await memory.store(MemoryEntry(content=f"Msg {i}", session_id="s2"))

        count_s1 = await memory.count(session_id="s1")
        count_s2 = await memory.count(session_id="s2")

        assert count_s1 == 3
        assert count_s2 == 2


class TestRetrievalStrategySorting:
    """Tests for retrieval strategy sorting."""

    @pytest.mark.asyncio
    async def test_recency_sorting(self):
        """Test recency strategy sorts by timestamp."""
        memory = HierarchicalMemory()

        now = datetime.now(timezone.utc)
        entries = [
            MemoryEntry(
                content="Old", session_id="s1", timestamp=now - timedelta(hours=2)
            ),
            MemoryEntry(content="New", session_id="s1", timestamp=now),
            MemoryEntry(
                content="Mid", session_id="s1", timestamp=now - timedelta(hours=1)
            ),
        ]

        sorted_entries = memory._sort_by_strategy(
            entries, "", RetrievalStrategy.RECENCY
        )

        assert sorted_entries[0].content == "New"
        assert sorted_entries[-1].content == "Old"

    @pytest.mark.asyncio
    async def test_importance_sorting(self):
        """Test importance strategy sorts by importance."""
        memory = HierarchicalMemory()

        entries = [
            MemoryEntry(content="Low", session_id="s1", importance=0.2),
            MemoryEntry(content="High", session_id="s1", importance=0.9),
            MemoryEntry(content="Mid", session_id="s1", importance=0.5),
        ]

        sorted_entries = memory._sort_by_strategy(
            entries, "", RetrievalStrategy.IMPORTANCE
        )

        assert sorted_entries[0].content == "High"
        assert sorted_entries[-1].content == "Low"

    @pytest.mark.asyncio
    async def test_relevance_without_embeddings_falls_back_to_recency(self):
        """Test relevance falls back to recency without embeddings."""
        memory = HierarchicalMemory()  # No embedding provider

        now = datetime.now(timezone.utc)
        entries = [
            MemoryEntry(
                content="Old", session_id="s1", timestamp=now - timedelta(hours=1)
            ),
            MemoryEntry(content="New", session_id="s1", timestamp=now),
        ]

        sorted_entries = memory._sort_by_strategy(
            entries, "query", RetrievalStrategy.RELEVANCE
        )

        # Should fall back to recency
        assert sorted_entries[0].content == "New"


class TestCosineSimilarity:
    """Tests for cosine similarity calculation."""

    def test_identical_vectors(self):
        """Test identical vectors have similarity 1."""
        memory = HierarchicalMemory()

        similarity = memory._cosine_similarity([1, 0, 0], [1, 0, 0])

        assert abs(similarity - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        """Test orthogonal vectors have similarity 0."""
        memory = HierarchicalMemory()

        similarity = memory._cosine_similarity([1, 0], [0, 1])

        assert abs(similarity) < 0.001

    def test_opposite_vectors(self):
        """Test opposite vectors have similarity -1."""
        memory = HierarchicalMemory()

        similarity = memory._cosine_similarity([1, 0], [-1, 0])

        assert abs(similarity - (-1.0)) < 0.001

    def test_different_lengths(self):
        """Test different length vectors return 0."""
        memory = HierarchicalMemory()

        similarity = memory._cosine_similarity([1, 0], [1, 0, 0])

        assert similarity == 0.0

    def test_zero_vector(self):
        """Test zero vector returns 0."""
        memory = HierarchicalMemory()

        similarity = memory._cosine_similarity([0, 0], [1, 0])

        assert similarity == 0.0

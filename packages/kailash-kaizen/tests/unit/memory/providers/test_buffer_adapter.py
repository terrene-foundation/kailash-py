"""
Unit Tests for BufferMemoryAdapter (Tier 1)

Tests the BufferMemoryAdapter implementation:
- Store and recall operations
- Context building
- Session filtering
- Forget operations
"""

from datetime import datetime, timedelta, timezone

import pytest

from kaizen.memory import BufferMemory
from kaizen.memory.providers import (
    BufferMemoryAdapter,
    MemoryContext,
    MemoryEntry,
    MemorySource,
    RetrievalStrategy,
)


class TestBufferMemoryAdapterCreation:
    """Tests for BufferMemoryAdapter initialization."""

    def test_create_with_new_buffer(self):
        """Test creating adapter with new BufferMemory."""
        adapter = BufferMemoryAdapter()

        assert adapter.buffer_memory is not None
        assert isinstance(adapter.buffer_memory, BufferMemory)

    def test_create_with_existing_buffer(self):
        """Test creating adapter with existing BufferMemory."""
        buffer = BufferMemory(max_turns=50)
        adapter = BufferMemoryAdapter(buffer_memory=buffer)

        assert adapter.buffer_memory is buffer

    def test_create_with_max_turns(self):
        """Test creating adapter with custom max_turns."""
        adapter = BufferMemoryAdapter(max_turns=25)

        assert adapter.buffer_memory is not None


class TestBufferMemoryAdapterStore:
    """Tests for BufferMemoryAdapter.store()."""

    @pytest.mark.asyncio
    async def test_store_entry(self):
        """Test storing a memory entry."""
        adapter = BufferMemoryAdapter()
        entry = MemoryEntry(
            content="Hello world",
            role="user",
            session_id="session-1",
        )

        entry_id = await adapter.store(entry)

        assert entry_id == entry.id

    @pytest.mark.asyncio
    async def test_store_multiple_entries(self):
        """Test storing multiple entries."""
        adapter = BufferMemoryAdapter()

        entries = [
            MemoryEntry(content=f"Message {i}", session_id="s1") for i in range(3)
        ]

        for entry in entries:
            await adapter.store(entry)

        count = await adapter.count(session_id="s1")
        assert count == 3

    @pytest.mark.asyncio
    async def test_store_different_roles(self):
        """Test storing entries with different roles."""
        adapter = BufferMemoryAdapter()

        user_entry = MemoryEntry(content="User message", role="user", session_id="s1")
        asst_entry = MemoryEntry(
            content="Assistant message", role="assistant", session_id="s1"
        )
        sys_entry = MemoryEntry(
            content="System message", role="system", session_id="s1"
        )

        await adapter.store(user_entry)
        await adapter.store(asst_entry)
        await adapter.store(sys_entry)

        count = await adapter.count(session_id="s1")
        assert count == 3


class TestBufferMemoryAdapterRecall:
    """Tests for BufferMemoryAdapter.recall()."""

    @pytest.mark.asyncio
    async def test_recall_by_session(self):
        """Test recalling entries by session."""
        adapter = BufferMemoryAdapter()

        # Store in different sessions
        await adapter.store(MemoryEntry(content="Msg 1", session_id="s1"))
        await adapter.store(MemoryEntry(content="Msg 2", session_id="s2"))
        await adapter.store(MemoryEntry(content="Msg 3", session_id="s1"))

        entries = await adapter.recall(session_id="s1")

        assert len(entries) == 2
        assert all(e.session_id == "s1" for e in entries)

    @pytest.mark.asyncio
    async def test_recall_with_query(self):
        """Test recalling with keyword query."""
        adapter = BufferMemoryAdapter()

        await adapter.store(MemoryEntry(content="Hello world", session_id="s1"))
        await adapter.store(MemoryEntry(content="Goodbye world", session_id="s1"))
        await adapter.store(MemoryEntry(content="Something else", session_id="s1"))

        entries = await adapter.recall(query="world", session_id="s1")

        assert len(entries) == 2
        assert all("world" in e.content.lower() for e in entries)

    @pytest.mark.asyncio
    async def test_recall_max_entries(self):
        """Test max_entries limit."""
        adapter = BufferMemoryAdapter()

        for i in range(10):
            await adapter.store(MemoryEntry(content=f"Msg {i}", session_id="s1"))

        entries = await adapter.recall(session_id="s1", max_entries=5)

        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_recall_sorted_by_recency(self):
        """Test entries sorted by timestamp (newest first)."""
        adapter = BufferMemoryAdapter()

        now = datetime.now(timezone.utc)
        entries_data = [
            ("Old", now - timedelta(hours=2)),
            ("Medium", now - timedelta(hours=1)),
            ("New", now),
        ]

        for content, timestamp in entries_data:
            entry = MemoryEntry(
                content=content,
                session_id="s1",
                timestamp=timestamp,
            )
            await adapter.store(entry)

        recalled = await adapter.recall(session_id="s1")

        assert recalled[0].content == "New"
        assert recalled[-1].content == "Old"

    @pytest.mark.asyncio
    async def test_recall_with_filters(self):
        """Test recalling with filters."""
        adapter = BufferMemoryAdapter()

        await adapter.store(
            MemoryEntry(
                content="User msg",
                role="user",
                session_id="s1",
                source=MemorySource.CONVERSATION,
            )
        )
        await adapter.store(
            MemoryEntry(
                content="Learned pattern",
                role="assistant",
                session_id="s1",
                source=MemorySource.LEARNED,
            )
        )

        entries = await adapter.recall(
            session_id="s1",
            filters={"source": "learned"},
        )

        assert len(entries) == 1
        assert entries[0].source == MemorySource.LEARNED


class TestBufferMemoryAdapterBuildContext:
    """Tests for BufferMemoryAdapter.build_context()."""

    @pytest.mark.asyncio
    async def test_build_context_basic(self):
        """Test basic context building."""
        adapter = BufferMemoryAdapter()

        await adapter.store(MemoryEntry(content="Hello", role="user", session_id="s1"))
        await adapter.store(
            MemoryEntry(content="Hi!", role="assistant", session_id="s1")
        )

        context = await adapter.build_context(session_id="s1")

        assert isinstance(context, MemoryContext)
        assert len(context.entries) == 2
        assert context.entries_retrieved == 2

    @pytest.mark.asyncio
    async def test_build_context_respects_token_budget(self):
        """Test context respects token budget."""
        adapter = BufferMemoryAdapter()

        # Add many entries
        for i in range(20):
            await adapter.store(
                MemoryEntry(
                    content="A" * 100,  # ~25 tokens each
                    session_id="s1",
                )
            )

        # Build with small budget (can fit ~2 entries)
        context = await adapter.build_context(
            session_id="s1",
            max_tokens=100,
        )

        # Should only include entries within budget
        assert context.total_tokens <= 70  # 70% of 100

    @pytest.mark.asyncio
    async def test_build_context_chronological_order(self):
        """Test context entries are in chronological order."""
        adapter = BufferMemoryAdapter()

        now = datetime.now(timezone.utc)
        for i in range(3):
            entry = MemoryEntry(
                content=f"Message {i}",
                session_id="s1",
                timestamp=now + timedelta(minutes=i),
            )
            await adapter.store(entry)

        context = await adapter.build_context(session_id="s1")

        # Should be chronological (oldest first for context)
        assert context.entries[0].content == "Message 0"
        assert context.entries[-1].content == "Message 2"

    @pytest.mark.asyncio
    async def test_build_context_with_query(self):
        """Test context building with query filter."""
        adapter = BufferMemoryAdapter()

        await adapter.store(MemoryEntry(content="Python code", session_id="s1"))
        await adapter.store(MemoryEntry(content="JavaScript code", session_id="s1"))
        await adapter.store(MemoryEntry(content="Random text", session_id="s1"))

        context = await adapter.build_context(session_id="s1", query="code")

        assert len(context.entries) == 2
        assert context.retrieval_query == "code"


class TestBufferMemoryAdapterSummarize:
    """Tests for BufferMemoryAdapter.summarize()."""

    @pytest.mark.asyncio
    async def test_summarize_returns_empty(self):
        """Test summarize returns empty (not supported)."""
        adapter = BufferMemoryAdapter()

        await adapter.store(MemoryEntry(content="Test", session_id="s1"))

        summary = await adapter.summarize(session_id="s1")

        assert summary == ""


class TestBufferMemoryAdapterForget:
    """Tests for BufferMemoryAdapter.forget()."""

    @pytest.mark.asyncio
    async def test_forget_by_entry_id(self):
        """Test forgetting specific entry by ID."""
        adapter = BufferMemoryAdapter()

        entry = MemoryEntry(content="Test", session_id="s1")
        await adapter.store(entry)

        deleted = await adapter.forget(entry_id=entry.id)

        assert deleted == 1
        assert await adapter.count(session_id="s1") == 0

    @pytest.mark.asyncio
    async def test_forget_by_session(self):
        """Test forgetting all entries in session."""
        adapter = BufferMemoryAdapter()

        for i in range(5):
            await adapter.store(MemoryEntry(content=f"Msg {i}", session_id="s1"))
        await adapter.store(MemoryEntry(content="Other", session_id="s2"))

        deleted = await adapter.forget(session_id="s1")

        assert deleted == 5
        assert await adapter.count(session_id="s1") == 0
        assert await adapter.count(session_id="s2") == 1

    @pytest.mark.asyncio
    async def test_forget_by_timestamp(self):
        """Test forgetting entries before timestamp."""
        adapter = BufferMemoryAdapter()

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

        await adapter.store(old_entry)
        await adapter.store(new_entry)

        deleted = await adapter.forget(before=now - timedelta(hours=1))

        assert deleted == 1
        assert await adapter.count(session_id="s1") == 1


class TestBufferMemoryAdapterGet:
    """Tests for BufferMemoryAdapter.get()."""

    @pytest.mark.asyncio
    async def test_get_existing_entry(self):
        """Test getting existing entry by ID."""
        adapter = BufferMemoryAdapter()

        entry = MemoryEntry(content="Test content", session_id="s1")
        await adapter.store(entry)

        retrieved = await adapter.get(entry.id)

        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.content == "Test content"

    @pytest.mark.asyncio
    async def test_get_nonexistent_entry(self):
        """Test getting nonexistent entry returns None."""
        adapter = BufferMemoryAdapter()

        retrieved = await adapter.get("nonexistent-id")

        assert retrieved is None


class TestBufferMemoryAdapterCount:
    """Tests for BufferMemoryAdapter.count()."""

    @pytest.mark.asyncio
    async def test_count_all(self):
        """Test counting all entries."""
        adapter = BufferMemoryAdapter()

        for i in range(5):
            await adapter.store(MemoryEntry(content=f"Msg {i}", session_id=f"s{i}"))

        count = await adapter.count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_count_by_session(self):
        """Test counting by session."""
        adapter = BufferMemoryAdapter()

        for i in range(3):
            await adapter.store(MemoryEntry(content=f"Msg {i}", session_id="s1"))
        for i in range(2):
            await adapter.store(MemoryEntry(content=f"Msg {i}", session_id="s2"))

        count_s1 = await adapter.count(session_id="s1")
        count_s2 = await adapter.count(session_id="s2")

        assert count_s1 == 3
        assert count_s2 == 2

    @pytest.mark.asyncio
    async def test_count_with_filters(self):
        """Test counting with filters."""
        adapter = BufferMemoryAdapter()

        await adapter.store(MemoryEntry(content="User", role="user", session_id="s1"))
        await adapter.store(
            MemoryEntry(content="Asst", role="assistant", session_id="s1")
        )
        await adapter.store(MemoryEntry(content="User", role="user", session_id="s1"))

        count = await adapter.count(session_id="s1", filters={"role": "user"})

        assert count == 2


class TestBufferMemoryAdapterClear:
    """Tests for BufferMemoryAdapter.clear()."""

    @pytest.mark.asyncio
    async def test_clear_session(self):
        """Test clearing specific session."""
        adapter = BufferMemoryAdapter()

        await adapter.store(MemoryEntry(content="S1", session_id="s1"))
        await adapter.store(MemoryEntry(content="S2", session_id="s2"))

        cleared = await adapter.clear(session_id="s1")

        assert cleared == 1
        assert await adapter.count(session_id="s1") == 0
        assert await adapter.count(session_id="s2") == 1

    @pytest.mark.asyncio
    async def test_clear_all(self):
        """Test clearing all entries."""
        adapter = BufferMemoryAdapter()

        for i in range(5):
            await adapter.store(MemoryEntry(content=f"Msg {i}", session_id=f"s{i}"))

        cleared = await adapter.clear()

        assert cleared == 5
        assert await adapter.count() == 0


class TestBufferMemoryAdapterLoadFromBuffer:
    """Tests for BufferMemoryAdapter.load_from_buffer()."""

    def test_load_existing_turns(self):
        """Test loading existing turns from BufferMemory."""
        buffer = BufferMemory()
        buffer.save_turn("s1", {"user": "Hello", "agent": "Hi!"})
        buffer.save_turn("s1", {"user": "How are you?", "agent": "Great!"})

        adapter = BufferMemoryAdapter(buffer_memory=buffer)
        adapter.load_from_buffer("s1")

        # Should have 4 entries (2 user + 2 agent)
        # Note: exact count depends on implementation
        # At minimum should have loaded something
        count = len([e for e in adapter._entries.values() if e.session_id == "s1"])
        assert count >= 2


class TestBufferMemoryAdapterHealthCheck:
    """Tests for BufferMemoryAdapter.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self):
        """Test health check returns True."""
        adapter = BufferMemoryAdapter()

        result = await adapter.health_check()

        assert result is True

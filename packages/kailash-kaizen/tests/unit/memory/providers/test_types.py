"""
Unit Tests for Memory Provider Types (Tier 1)

Tests the core types for the MemoryProvider interface:
- MemorySource enum
- MemoryEntry dataclass
- MemoryContext dataclass
- RetrievalStrategy enum
- Token estimation
"""

from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from kaizen.memory.providers.types import (
    MemoryContext,
    MemoryEntry,
    MemorySource,
    RetrievalStrategy,
    estimate_tokens,
)


class TestMemorySource:
    """Tests for MemorySource enum."""

    def test_all_sources_exist(self):
        """Test all expected sources exist."""
        assert MemorySource.CONVERSATION
        assert MemorySource.LEARNED
        assert MemorySource.EXTERNAL
        assert MemorySource.SYSTEM

    def test_source_count(self):
        """Test expected number of sources."""
        assert len(MemorySource) == 4

    def test_source_values(self):
        """Test source string values."""
        assert MemorySource.CONVERSATION.value == "conversation"
        assert MemorySource.LEARNED.value == "learned"
        assert MemorySource.EXTERNAL.value == "external"
        assert MemorySource.SYSTEM.value == "system"

    def test_source_from_string(self):
        """Test creating source from string."""
        assert MemorySource("conversation") == MemorySource.CONVERSATION
        assert MemorySource("learned") == MemorySource.LEARNED

    def test_invalid_source_raises(self):
        """Test invalid source string raises error."""
        with pytest.raises(ValueError):
            MemorySource("invalid")


class TestRetrievalStrategy:
    """Tests for RetrievalStrategy enum."""

    def test_all_strategies_exist(self):
        """Test all expected strategies exist."""
        assert RetrievalStrategy.RECENCY
        assert RetrievalStrategy.IMPORTANCE
        assert RetrievalStrategy.RELEVANCE
        assert RetrievalStrategy.HYBRID

    def test_strategy_count(self):
        """Test expected number of strategies."""
        assert len(RetrievalStrategy) == 4

    def test_strategy_values(self):
        """Test strategy string values."""
        assert RetrievalStrategy.RECENCY.value == "recency"
        assert RetrievalStrategy.IMPORTANCE.value == "importance"
        assert RetrievalStrategy.RELEVANCE.value == "relevance"
        assert RetrievalStrategy.HYBRID.value == "hybrid"


class TestMemoryEntryCreation:
    """Tests for MemoryEntry creation."""

    def test_minimal_entry(self):
        """Test creating entry with minimal fields."""
        entry = MemoryEntry(content="Hello world")

        assert entry.content == "Hello world"
        assert entry.session_id == ""
        assert entry.role == "assistant"
        assert entry.source == MemorySource.CONVERSATION
        assert entry.importance == 0.5
        assert entry.tags == []
        assert entry.metadata == {}
        assert entry.embedding is None
        assert entry.id is not None
        assert entry.timestamp is not None

    def test_full_entry(self):
        """Test creating entry with all fields."""
        now = datetime.now(timezone.utc)
        entry = MemoryEntry(
            id="test-id",
            content="User message",
            session_id="session-123",
            role="user",
            timestamp=now,
            source=MemorySource.CONVERSATION,
            importance=0.9,
            tags=["greeting", "initial"],
            metadata={"key": "value"},
            embedding=[0.1, 0.2, 0.3],
        )

        assert entry.id == "test-id"
        assert entry.content == "User message"
        assert entry.session_id == "session-123"
        assert entry.role == "user"
        assert entry.timestamp == now
        assert entry.source == MemorySource.CONVERSATION
        assert entry.importance == 0.9
        assert entry.tags == ["greeting", "initial"]
        assert entry.metadata == {"key": "value"}
        assert entry.embedding == [0.1, 0.2, 0.3]

    def test_unique_ids_generated(self):
        """Test that unique IDs are generated."""
        entry1 = MemoryEntry(content="Content 1")
        entry2 = MemoryEntry(content="Content 2")

        assert entry1.id != entry2.id


class TestMemoryEntryToMessage:
    """Tests for MemoryEntry.to_message()."""

    def test_to_message_user(self):
        """Test converting user entry to message."""
        entry = MemoryEntry(content="Hello", role="user")
        msg = entry.to_message()

        assert msg == {"role": "user", "content": "Hello"}

    def test_to_message_assistant(self):
        """Test converting assistant entry to message."""
        entry = MemoryEntry(content="Hi there!", role="assistant")
        msg = entry.to_message()

        assert msg == {"role": "assistant", "content": "Hi there!"}

    def test_to_message_system(self):
        """Test converting system entry to message."""
        entry = MemoryEntry(content="System prompt", role="system")
        msg = entry.to_message()

        assert msg == {"role": "system", "content": "System prompt"}


class TestMemoryEntrySerialization:
    """Tests for MemoryEntry serialization."""

    def test_to_dict(self):
        """Test serializing entry to dict."""
        entry = MemoryEntry(
            id="test-id",
            content="Test content",
            session_id="session-1",
            role="user",
            source=MemorySource.LEARNED,
            importance=0.8,
            tags=["test"],
            metadata={"key": "value"},
        )
        data = entry.to_dict()

        assert data["id"] == "test-id"
        assert data["content"] == "Test content"
        assert data["session_id"] == "session-1"
        assert data["role"] == "user"
        assert data["source"] == "learned"
        assert data["importance"] == 0.8
        assert data["tags"] == ["test"]
        assert data["metadata"] == {"key": "value"}
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserializing entry from dict."""
        data = {
            "id": "test-id",
            "content": "Test content",
            "session_id": "session-1",
            "role": "user",
            "timestamp": "2025-01-21T12:00:00+00:00",
            "source": "external",
            "importance": 0.7,
            "tags": ["tag1", "tag2"],
            "metadata": {"foo": "bar"},
        }
        entry = MemoryEntry.from_dict(data)

        assert entry.id == "test-id"
        assert entry.content == "Test content"
        assert entry.session_id == "session-1"
        assert entry.role == "user"
        assert entry.source == MemorySource.EXTERNAL
        assert entry.importance == 0.7
        assert entry.tags == ["tag1", "tag2"]
        assert entry.metadata == {"foo": "bar"}

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        entry = MemoryEntry(
            content="Test",
            session_id="s1",
            role="assistant",
            source=MemorySource.SYSTEM,
            importance=0.6,
            tags=["a", "b"],
        )
        data = entry.to_dict()
        restored = MemoryEntry.from_dict(data)

        assert restored.content == entry.content
        assert restored.session_id == entry.session_id
        assert restored.role == entry.role
        assert restored.source == entry.source
        assert restored.importance == entry.importance
        assert restored.tags == entry.tags


class TestMemoryEntryFromMessage:
    """Tests for MemoryEntry.from_message()."""

    def test_from_message_basic(self):
        """Test creating entry from message dict."""
        msg = {"role": "user", "content": "Hello there"}
        entry = MemoryEntry.from_message(msg, session_id="s1")

        assert entry.content == "Hello there"
        assert entry.role == "user"
        assert entry.session_id == "s1"
        assert entry.source == MemorySource.CONVERSATION

    def test_from_message_with_source(self):
        """Test creating entry with custom source."""
        msg = {"role": "assistant", "content": "Response"}
        entry = MemoryEntry.from_message(
            msg,
            session_id="s1",
            source=MemorySource.LEARNED,
            importance=0.9,
        )

        assert entry.source == MemorySource.LEARNED
        assert entry.importance == 0.9


class TestMemoryEntryFilters:
    """Tests for MemoryEntry.matches_filter()."""

    def test_empty_filter_matches(self):
        """Test empty filter matches all."""
        entry = MemoryEntry(content="Test")
        assert entry.matches_filter(None) is True
        assert entry.matches_filter({}) is True

    def test_source_filter_single(self):
        """Test filtering by single source."""
        entry = MemoryEntry(content="Test", source=MemorySource.LEARNED)

        assert entry.matches_filter({"source": "learned"}) is True
        assert entry.matches_filter({"source": "conversation"}) is False

    def test_source_filter_list(self):
        """Test filtering by source list."""
        entry = MemoryEntry(content="Test", source=MemorySource.LEARNED)

        assert entry.matches_filter({"source": ["learned", "external"]}) is True
        assert entry.matches_filter({"source": ["conversation", "system"]}) is False

    def test_role_filter_single(self):
        """Test filtering by single role."""
        entry = MemoryEntry(content="Test", role="user")

        assert entry.matches_filter({"role": "user"}) is True
        assert entry.matches_filter({"role": "assistant"}) is False

    def test_role_filter_list(self):
        """Test filtering by role list."""
        entry = MemoryEntry(content="Test", role="user")

        assert entry.matches_filter({"role": ["user", "assistant"]}) is True
        assert entry.matches_filter({"role": ["system", "tool"]}) is False

    def test_tags_filter_single(self):
        """Test filtering by single tag."""
        entry = MemoryEntry(content="Test", tags=["greeting", "formal"])

        assert entry.matches_filter({"tags": "greeting"}) is True
        assert entry.matches_filter({"tags": "informal"}) is False

    def test_tags_filter_list(self):
        """Test filtering by tag list (any match)."""
        entry = MemoryEntry(content="Test", tags=["greeting"])

        assert entry.matches_filter({"tags": ["greeting", "farewell"]}) is True
        assert entry.matches_filter({"tags": ["question", "answer"]}) is False

    def test_importance_filter_min(self):
        """Test filtering by minimum importance."""
        entry = MemoryEntry(content="Test", importance=0.7)

        assert entry.matches_filter({"min_importance": 0.5}) is True
        assert entry.matches_filter({"min_importance": 0.8}) is False

    def test_importance_filter_max(self):
        """Test filtering by maximum importance."""
        entry = MemoryEntry(content="Test", importance=0.7)

        assert entry.matches_filter({"max_importance": 0.9}) is True
        assert entry.matches_filter({"max_importance": 0.5}) is False

    def test_combined_filters(self):
        """Test combining multiple filters."""
        entry = MemoryEntry(
            content="Test",
            role="user",
            source=MemorySource.CONVERSATION,
            importance=0.7,
            tags=["greeting"],
        )

        # All match
        assert (
            entry.matches_filter(
                {
                    "role": "user",
                    "source": "conversation",
                    "min_importance": 0.5,
                }
            )
            is True
        )

        # One doesn't match
        assert (
            entry.matches_filter(
                {
                    "role": "user",
                    "source": "learned",
                }
            )
            is False
        )


class TestMemoryContextCreation:
    """Tests for MemoryContext creation."""

    def test_empty_context(self):
        """Test creating empty context."""
        ctx = MemoryContext()

        assert ctx.entries == []
        assert ctx.summary == ""
        assert ctx.total_tokens == 0
        assert ctx.entries_retrieved == 0
        assert ctx.entries_summarized == 0
        assert ctx.retrieval_strategy == RetrievalStrategy.RECENCY
        assert ctx.retrieval_query == ""

    def test_context_with_entries(self):
        """Test creating context with entries."""
        entries = [
            MemoryEntry(content="Hello", role="user"),
            MemoryEntry(content="Hi!", role="assistant"),
        ]
        ctx = MemoryContext(
            entries=entries,
            total_tokens=100,
            entries_retrieved=2,
        )

        assert len(ctx.entries) == 2
        assert ctx.total_tokens == 100
        assert ctx.entries_retrieved == 2

    def test_empty_factory(self):
        """Test empty() factory method."""
        ctx = MemoryContext.empty()

        assert ctx.entries == []
        assert ctx.is_empty is True


class TestMemoryContextIsEmpty:
    """Tests for MemoryContext.is_empty property."""

    def test_empty_context_is_empty(self):
        """Test empty context is marked as empty."""
        ctx = MemoryContext()
        assert ctx.is_empty is True

    def test_context_with_entries_not_empty(self):
        """Test context with entries is not empty."""
        ctx = MemoryContext(entries=[MemoryEntry(content="Test")])
        assert ctx.is_empty is False

    def test_context_with_summary_not_empty(self):
        """Test context with summary is not empty."""
        ctx = MemoryContext(summary="Summary text")
        assert ctx.is_empty is False


class TestMemoryContextToSystemPrompt:
    """Tests for MemoryContext.to_system_prompt()."""

    def test_empty_context_returns_empty(self):
        """Test empty context returns empty string."""
        ctx = MemoryContext()
        assert ctx.to_system_prompt() == ""

    def test_with_entries_only(self):
        """Test context with entries only."""
        entries = [
            MemoryEntry(content="Hello", role="user"),
            MemoryEntry(content="Hi there!", role="assistant"),
        ]
        ctx = MemoryContext(entries=entries)
        prompt = ctx.to_system_prompt()

        assert "## Relevant Memory" in prompt
        assert "[User]: Hello" in prompt
        assert "[Assistant]: Hi there!" in prompt

    def test_with_summary_only(self):
        """Test context with summary only."""
        ctx = MemoryContext(summary="Previous discussion about coding.")
        prompt = ctx.to_system_prompt()

        assert "## Previous Context Summary" in prompt
        assert "Previous discussion about coding." in prompt

    def test_with_both(self):
        """Test context with summary and entries."""
        entries = [MemoryEntry(content="Current message", role="user")]
        ctx = MemoryContext(
            entries=entries,
            summary="Earlier context summary.",
        )
        prompt = ctx.to_system_prompt()

        assert "## Previous Context Summary" in prompt
        assert "Earlier context summary." in prompt
        assert "## Relevant Memory" in prompt
        assert "[User]: Current message" in prompt


class TestMemoryContextToMessages:
    """Tests for MemoryContext.to_messages()."""

    def test_empty_context_returns_empty_list(self):
        """Test empty context returns empty list."""
        ctx = MemoryContext()
        assert ctx.to_messages() == []

    def test_with_entries(self):
        """Test context with entries."""
        entries = [
            MemoryEntry(content="Hello", role="user"),
            MemoryEntry(content="Hi!", role="assistant"),
        ]
        ctx = MemoryContext(entries=entries)
        messages = ctx.to_messages()

        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "Hello"}
        assert messages[1] == {"role": "assistant", "content": "Hi!"}

    def test_with_summary(self):
        """Test context with summary prepends system message."""
        ctx = MemoryContext(summary="Previous context summary.")
        messages = ctx.to_messages()

        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert "summary" in messages[0]["content"].lower()

    def test_with_both(self):
        """Test context with summary and entries."""
        entries = [MemoryEntry(content="Hello", role="user")]
        ctx = MemoryContext(entries=entries, summary="Summary text")
        messages = ctx.to_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestMemoryContextSerialization:
    """Tests for MemoryContext serialization."""

    def test_to_dict(self):
        """Test serializing context to dict."""
        entries = [MemoryEntry(content="Test", role="user")]
        ctx = MemoryContext(
            entries=entries,
            summary="Summary",
            total_tokens=50,
            entries_retrieved=1,
            entries_summarized=2,
            retrieval_strategy=RetrievalStrategy.IMPORTANCE,
            retrieval_query="test query",
        )
        data = ctx.to_dict()

        assert len(data["entries"]) == 1
        assert data["summary"] == "Summary"
        assert data["total_tokens"] == 50
        assert data["entries_retrieved"] == 1
        assert data["entries_summarized"] == 2
        assert data["retrieval_strategy"] == "importance"
        assert data["retrieval_query"] == "test query"

    def test_from_dict(self):
        """Test deserializing context from dict."""
        data = {
            "entries": [{"content": "Test", "role": "user"}],
            "summary": "Summary",
            "total_tokens": 100,
            "entries_retrieved": 1,
            "entries_summarized": 0,
            "retrieval_strategy": "hybrid",
            "retrieval_query": "query",
        }
        ctx = MemoryContext.from_dict(data)

        assert len(ctx.entries) == 1
        assert ctx.summary == "Summary"
        assert ctx.total_tokens == 100
        assert ctx.retrieval_strategy == RetrievalStrategy.HYBRID

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        entries = [MemoryEntry(content="Test", role="user")]
        ctx = MemoryContext(
            entries=entries,
            summary="Summary",
            total_tokens=50,
            retrieval_strategy=RetrievalStrategy.RELEVANCE,
        )
        data = ctx.to_dict()
        restored = MemoryContext.from_dict(data)

        assert len(restored.entries) == 1
        assert restored.summary == ctx.summary
        assert restored.total_tokens == ctx.total_tokens
        assert restored.retrieval_strategy == ctx.retrieval_strategy


class TestEstimateTokens:
    """Tests for token estimation function."""

    def test_empty_string(self):
        """Test empty string returns 0."""
        assert estimate_tokens("") == 0

    def test_short_text(self):
        """Test short text estimation."""
        # "Hello" = 5 chars / 4 = 1 token
        assert estimate_tokens("Hello") == 1

    def test_longer_text(self):
        """Test longer text estimation."""
        # 100 chars / 4 = 25 tokens
        text = "a" * 100
        assert estimate_tokens(text) == 25

    def test_realistic_text(self):
        """Test realistic text."""
        text = "This is a sample sentence that contains multiple words."
        tokens = estimate_tokens(text)
        # Should be roughly in the expected range
        assert 10 < tokens < 20

"""
Unit tests for ShortTermMemory.

Tests session-based storage, TTL expiration, and automatic cleanup.
"""

import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kaizen.memory.short_term import ShortTermMemory
from kaizen.memory.storage.sqlite_storage import SQLiteStorage


@pytest.fixture
def temp_storage():
    """Create temporary SQLiteStorage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "test_short_term.db"
        yield SQLiteStorage(str(storage_path))


@pytest.fixture
def short_term_memory(temp_storage):
    """Create ShortTermMemory instance for testing."""
    return ShortTermMemory(
        storage=temp_storage,
        ttl_seconds=5,
        max_entries=10,
        auto_cleanup=False,  # 5 seconds for testing
    )


class TestShortTermMemoryBasics:
    """Test basic CRUD operations."""

    def test_store_entry(self, short_term_memory):
        """Test storing a short-term memory."""
        entry_id = short_term_memory.store("User asked about Python")
        assert entry_id is not None

    def test_retrieve_entry(self, short_term_memory):
        """Test retrieving a stored entry."""
        entry_id = short_term_memory.store("Test content")
        entry = short_term_memory.retrieve(entry_id)

        assert entry is not None
        assert entry.content == "Test content"
        assert entry.memory_type.value == "short_term"

    def test_retrieve_with_metadata(self, short_term_memory):
        """Test storing and retrieving entry with metadata."""
        entry_id = short_term_memory.store("Test content", metadata={"source": "test"})
        entry = short_term_memory.retrieve(entry_id)

        assert entry.metadata["source"] == "test"

    def test_retrieve_nonexistent_entry(self, short_term_memory):
        """Test retrieving a nonexistent entry."""
        entry = short_term_memory.retrieve("nonexistent-id")
        assert entry is None


class TestShortTermMemoryExpiration:
    """Test TTL expiration behavior."""

    def test_retrieve_expired_entry(self, short_term_memory):
        """Test that expired entries return None."""
        entry_id = short_term_memory.store("Test content")

        # Wait for TTL to expire (5 seconds)
        time.sleep(6)

        # Should return None for expired entry
        entry = short_term_memory.retrieve(entry_id)
        assert entry is None

    def test_get_recent_filters_expired(self, short_term_memory):
        """Test that get_recent filters out expired entries."""
        # Store some entries
        short_term_memory.store("Recent 1")
        short_term_memory.store("Recent 2")

        # Wait for expiration
        time.sleep(6)

        # Store new entry after expiration
        short_term_memory.store("Recent 3")

        # Should only return non-expired entry
        recent = short_term_memory.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].content == "Recent 3"

    def test_cleanup_expired(self, short_term_memory):
        """Test manual cleanup of expired entries."""
        # Store entries
        for i in range(5):
            short_term_memory.store(f"Entry {i}")

        # Wait for expiration
        time.sleep(6)

        # Cleanup
        deleted = short_term_memory.cleanup_expired()
        assert deleted == 5

        # Verify all deleted
        stats = short_term_memory.get_stats()
        assert stats["total_entries"] == 0


class TestShortTermMemoryRetrieval:
    """Test retrieval operations."""

    def test_get_recent_basic(self, short_term_memory):
        """Test getting recent memories."""
        # Store multiple entries
        for i in range(5):
            short_term_memory.store(f"Memory {i}")

        # Get recent (should be in reverse order)
        recent = short_term_memory.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_recent_with_limit(self, short_term_memory):
        """Test that limit is respected."""
        for i in range(10):
            short_term_memory.store(f"Memory {i}")

        recent = short_term_memory.get_recent(limit=5)
        assert len(recent) == 5

    def test_search_basic(self, short_term_memory):
        """Test searching for memories."""
        short_term_memory.store("Python is great")
        short_term_memory.store("JavaScript is good")
        short_term_memory.store("Python Django")

        results = short_term_memory.search("Python")
        assert len(results) == 2

    def test_search_filters_expired(self, short_term_memory):
        """Test that search filters out expired entries."""
        short_term_memory.store("Python old")

        # Wait for expiration
        time.sleep(6)

        short_term_memory.store("Python new")

        results = short_term_memory.search("Python")
        assert len(results) == 1
        assert results[0].content == "Python new"


class TestShortTermMemoryMaxEntries:
    """Test max_entries enforcement."""

    def test_auto_cleanup_enforces_max_entries(self, temp_storage):
        """Test that max_entries is enforced during auto_cleanup."""
        memory = ShortTermMemory(
            storage=temp_storage, ttl_seconds=3600, max_entries=5, auto_cleanup=True
        )

        # Store more than max_entries
        for i in range(10):
            memory.store(f"Entry {i}")
            time.sleep(0.01)  # Small delay to ensure different timestamps

        # Trigger cleanup manually
        memory._last_cleanup = datetime.now(timezone.utc) - timedelta(
            seconds=400
        )  # Force cleanup
        memory._cleanup_if_needed()

        # Should only have max_entries
        stats = memory.get_stats()
        assert stats["total_entries"] <= 5


class TestShortTermMemoryClear:
    """Test clear operations."""

    def test_clear_all(self, short_term_memory):
        """Test clearing all short-term memories."""
        for i in range(5):
            short_term_memory.store(f"Entry {i}")

        cleared = short_term_memory.clear()
        assert cleared == 5

        stats = short_term_memory.get_stats()
        assert stats["total_entries"] == 0


class TestShortTermMemoryStats:
    """Test statistics."""

    def test_get_stats_basic(self, short_term_memory):
        """Test getting memory statistics."""
        # Store some entries
        for i in range(3):
            short_term_memory.store(f"Entry {i}")

        stats = short_term_memory.get_stats()

        assert stats["total_entries"] == 3
        assert stats["active_entries"] == 3
        assert stats["expired_entries"] == 0
        assert stats["ttl_seconds"] == 5
        assert stats["max_entries"] == 10

    def test_get_stats_with_expired(self, short_term_memory):
        """Test stats with both active and expired entries."""
        # Store entries
        short_term_memory.store("Old 1")
        short_term_memory.store("Old 2")

        # Wait for expiration
        time.sleep(6)

        # Store new entry
        short_term_memory.store("New 1")

        stats = short_term_memory.get_stats()
        assert stats["total_entries"] == 3
        assert stats["active_entries"] == 1
        assert stats["expired_entries"] == 2

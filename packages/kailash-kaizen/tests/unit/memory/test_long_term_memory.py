"""
Unit tests for LongTermMemory.

Tests importance-based retention, consolidation, and forgetting curve.
"""

import tempfile
from pathlib import Path

import pytest
from kaizen.memory.long_term import LongTermMemory
from kaizen.memory.storage.sqlite_storage import SQLiteStorage


@pytest.fixture
def temp_storage():
    """Create temporary SQLiteStorage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "test_long_term.db"
        yield SQLiteStorage(str(storage_path))


@pytest.fixture
def long_term_memory(temp_storage):
    """Create LongTermMemory instance for testing."""
    return LongTermMemory(
        storage=temp_storage,
        importance_threshold=0.2,
        max_entries=100,
        auto_consolidate=False,
    )


class TestLongTermMemoryBasics:
    """Test basic CRUD operations."""

    def test_store_entry(self, long_term_memory):
        """Test storing a long-term memory."""
        entry_id = long_term_memory.store("Important fact", importance=0.8)
        assert entry_id is not None

    def test_store_with_default_importance(self, long_term_memory):
        """Test storing with default importance."""
        entry_id = long_term_memory.store("Fact")
        entry = long_term_memory.retrieve(entry_id)

        assert entry.importance == 0.5  # Default

    def test_retrieve_entry(self, long_term_memory):
        """Test retrieving a stored entry."""
        entry_id = long_term_memory.store("Test fact", importance=0.9)
        entry = long_term_memory.retrieve(entry_id)

        assert entry is not None
        assert entry.content == "Test fact"
        assert entry.memory_type.value == "long_term"
        assert entry.importance == 0.9

    def test_retrieve_updates_access_count(self, long_term_memory):
        """Test that retrieval updates access tracking."""
        entry_id = long_term_memory.store("Test")

        # Retrieve multiple times
        long_term_memory.retrieve(entry_id)
        long_term_memory.retrieve(entry_id)
        entry = long_term_memory.retrieve(entry_id)

        assert entry.access_count == 3

    def test_update_importance(self, long_term_memory):
        """Test updating importance score."""
        entry_id = long_term_memory.store("Test", importance=0.5)

        # Update importance
        long_term_memory.update_importance(entry_id, 0.9)

        entry = long_term_memory.retrieve(entry_id)
        assert entry.importance == 0.9


class TestLongTermMemoryRetrieval:
    """Test retrieval operations."""

    def test_get_important_basic(self, long_term_memory):
        """Test getting important memories."""
        # Store with varying importance
        long_term_memory.store("Very important", importance=0.9)
        long_term_memory.store("Important", importance=0.7)
        long_term_memory.store("Low importance", importance=0.3)
        long_term_memory.store("Very low", importance=0.1)

        # Get important (threshold 0.2)
        important = long_term_memory.get_important(limit=10)

        # Should have 3 entries (0.9, 0.7, 0.3) above threshold
        assert len(important) >= 3

        # Should be sorted by importance
        assert important[0].importance >= important[1].importance

    def test_get_important_with_custom_threshold(self, long_term_memory):
        """Test getting important with custom threshold."""
        long_term_memory.store("High", importance=0.9)
        long_term_memory.store("Medium", importance=0.5)
        long_term_memory.store("Low", importance=0.3)

        # Get with higher threshold
        important = long_term_memory.get_important(limit=10, min_importance=0.6)

        # Should only have high importance entry
        assert len(important) == 1
        assert important[0].importance == 0.9

    def test_search_basic(self, long_term_memory):
        """Test searching for memories."""
        long_term_memory.store("Python is great", importance=0.8)
        long_term_memory.store("JavaScript is good", importance=0.5)
        long_term_memory.store("Python Django", importance=0.7)

        results = long_term_memory.search("Python")
        assert len(results) == 2

        # Should be sorted by importance
        assert results[0].importance >= results[1].importance

    def test_search_respects_limit(self, long_term_memory):
        """Test that search respects limit."""
        for i in range(10):
            long_term_memory.store(f"Python entry {i}", importance=0.5 + i * 0.01)

        results = long_term_memory.search("Python", limit=5)
        assert len(results) == 5


class TestLongTermMemoryConsolidation:
    """Test memory consolidation."""

    def test_consolidate_basic(self, long_term_memory):
        """Test basic consolidation."""
        # Store entries with different importance
        long_term_memory.store("Important 1", importance=0.9)
        long_term_memory.store("Important 2", importance=0.8)
        long_term_memory.store("Low 1", importance=0.15)  # Below threshold (0.2)
        long_term_memory.store("Low 2", importance=0.1)  # Below threshold

        # Consolidate
        stats = long_term_memory.consolidate()

        assert stats["pruned"] == 2  # Two low-importance entries
        assert stats["kept"] == 2  # Two high-importance entries
        assert stats["total"] == 4

    def test_consolidate_enforces_max_entries(self, long_term_memory):
        """Test that consolidation enforces max_entries."""
        # Store more than max_entries (100)
        for i in range(150):
            long_term_memory.store(f"Entry {i}", importance=0.5)

        # Consolidate
        stats = long_term_memory.consolidate()

        # Should only keep max_entries
        assert stats["kept"] <= 100
        assert stats["pruned"] >= 50

    def test_consolidate_keeps_highest_importance(self, long_term_memory):
        """Test that consolidation keeps highest importance entries."""
        # Create memory with small max_entries for testing
        memory = LongTermMemory(
            storage=long_term_memory.storage,
            importance_threshold=0.0,  # Don't prune by threshold
            max_entries=5,
            auto_consolidate=False,
        )

        # Store entries with different importance
        memory.store("Highest", importance=0.9)
        memory.store("High", importance=0.8)
        memory.store("Medium", importance=0.5)
        memory.store("Low", importance=0.3)
        memory.store("Lower", importance=0.2)
        memory.store("Lowest", importance=0.1)

        # Consolidate
        memory.consolidate()

        # Get all entries
        all_entries = memory.get_important(limit=10, min_importance=0.0)

        # Should have exactly max_entries
        assert len(all_entries) == 5

        # Should have kept the highest importance ones
        importances = [e.importance for e in all_entries]
        assert 0.9 in importances
        assert 0.8 in importances
        assert 0.1 not in importances


class TestLongTermMemoryClear:
    """Test clear operations."""

    def test_clear_all(self, long_term_memory):
        """Test clearing all long-term memories."""
        for i in range(5):
            long_term_memory.store(f"Entry {i}", importance=0.5)

        cleared = long_term_memory.clear()
        assert cleared == 5

        stats = long_term_memory.get_stats()
        assert stats["total_entries"] == 0


class TestLongTermMemoryStats:
    """Test statistics."""

    def test_get_stats_basic(self, long_term_memory):
        """Test getting memory statistics."""
        # Store entries with different importance
        long_term_memory.store("High 1", importance=0.9)
        long_term_memory.store("High 2", importance=0.8)
        long_term_memory.store("Medium", importance=0.5)
        long_term_memory.store("Low", importance=0.2)

        stats = long_term_memory.get_stats()

        assert stats["total_entries"] == 4
        assert stats["high_importance"] == 2  # >= 0.7
        assert stats["medium_importance"] == 1  # 0.3-0.7
        assert stats["low_importance"] == 1  # < 0.3
        assert 0.0 <= stats["avg_importance"] <= 1.0

    def test_get_stats_importance_distribution(self, long_term_memory):
        """Test importance distribution in stats."""
        # Store many high importance entries
        for i in range(10):
            long_term_memory.store(f"High {i}", importance=0.8)

        # Store few low importance
        long_term_memory.store("Low", importance=0.2)

        stats = long_term_memory.get_stats()

        assert stats["high_importance"] == 10
        assert stats["low_importance"] == 1
        assert stats["avg_importance"] > 0.7  # Should be high average

"""
Unit tests for SQLiteStorage backend.

Tests all CRUD operations, search, FTS, indexing, and SQL-specific features.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageError
from kaizen.memory.storage.sqlite_storage import SQLiteStorage


@pytest.fixture
def temp_storage():
    """Create temporary SQLiteStorage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "test_memories.db"
        yield SQLiteStorage(str(storage_path))


@pytest.fixture
def sample_entry():
    """Create a sample memory entry for testing."""
    return MemoryEntry(
        content="User prefers concise responses",
        memory_type=MemoryType.PREFERENCE,
        metadata={"source": "test"},
        importance=0.8,
    )


class TestSQLiteStorageBasics:
    """Test basic CRUD operations."""

    def test_store_entry(self, temp_storage, sample_entry):
        """Test storing a memory entry."""
        entry_id = temp_storage.store(sample_entry)
        assert entry_id == sample_entry.id
        assert entry_id is not None

    def test_store_duplicate_id(self, temp_storage, sample_entry):
        """Test storing entry with duplicate ID fails."""
        temp_storage.store(sample_entry)

        # Try to store same entry again
        with pytest.raises(StorageError, match="already exists"):
            temp_storage.store(sample_entry)

    def test_retrieve_entry(self, temp_storage, sample_entry):
        """Test retrieving a stored entry."""
        temp_storage.store(sample_entry)
        retrieved = temp_storage.retrieve(sample_entry.id)

        assert retrieved is not None
        assert retrieved.id == sample_entry.id
        assert retrieved.content == sample_entry.content
        assert retrieved.memory_type == sample_entry.memory_type
        assert retrieved.metadata == sample_entry.metadata
        assert retrieved.importance == sample_entry.importance

    def test_retrieve_nonexistent_entry(self, temp_storage):
        """Test retrieving an entry that doesn't exist."""
        retrieved = temp_storage.retrieve("nonexistent-id")
        assert retrieved is None

    def test_update_entry(self, temp_storage, sample_entry):
        """Test updating an existing entry."""
        temp_storage.store(sample_entry)

        # Update content
        sample_entry.content = "User prefers detailed explanations"
        sample_entry.importance = 0.9

        temp_storage.update(sample_entry)

        # Retrieve and verify
        retrieved = temp_storage.retrieve(sample_entry.id)
        assert retrieved.content == "User prefers detailed explanations"
        assert retrieved.importance == 0.9

    def test_update_nonexistent_entry(self, temp_storage, sample_entry):
        """Test updating an entry that doesn't exist."""
        with pytest.raises(StorageError, match="Entry not found"):
            temp_storage.update(sample_entry)

    def test_delete_entry(self, temp_storage, sample_entry):
        """Test deleting an entry."""
        temp_storage.store(sample_entry)
        deleted = temp_storage.delete(sample_entry.id)

        assert deleted is True
        assert temp_storage.retrieve(sample_entry.id) is None

    def test_delete_nonexistent_entry(self, temp_storage):
        """Test deleting an entry that doesn't exist."""
        deleted = temp_storage.delete("nonexistent-id")
        assert deleted is False


class TestSQLiteStorageListingAndCounting:
    """Test listing and counting operations."""

    def test_list_all_entries(self, temp_storage):
        """Test listing all entries."""
        # Store multiple entries
        entries = [
            MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            for i in range(5)
        ]
        for entry in entries:
            temp_storage.store(entry)

        # List all
        listed = temp_storage.list_entries()
        assert len(listed) == 5

    def test_list_entries_by_type(self, temp_storage):
        """Test filtering entries by type."""
        # Store different types
        temp_storage.store(
            MemoryEntry(content="Short term", memory_type=MemoryType.SHORT_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="Long term", memory_type=MemoryType.LONG_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="Preference", memory_type=MemoryType.PREFERENCE)
        )

        # List short-term only
        short_term = temp_storage.list_entries(memory_type=MemoryType.SHORT_TERM)
        assert len(short_term) == 1
        assert short_term[0].memory_type == MemoryType.SHORT_TERM

    def test_list_entries_ordered_by_timestamp(self, temp_storage):
        """Test that entries are ordered by timestamp (newest first)."""
        # Store entries with small delays
        entries = []
        for i in range(3):
            entry = MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            temp_storage.store(entry)
            entries.append(entry)

        listed = temp_storage.list_entries()

        # Should be in reverse order (newest first)
        assert listed[0].content == "Memory 2"
        assert listed[1].content == "Memory 1"
        assert listed[2].content == "Memory 0"

    def test_list_entries_with_pagination(self, temp_storage):
        """Test pagination of listing."""
        # Store 10 entries
        for i in range(10):
            temp_storage.store(
                MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            )

        # Get first page (5 entries)
        page1 = temp_storage.list_entries(limit=5, offset=0)
        assert len(page1) == 5

        # Get second page (5 entries)
        page2 = temp_storage.list_entries(limit=5, offset=5)
        assert len(page2) == 5

        # Verify no overlap
        page1_ids = {e.id for e in page1}
        page2_ids = {e.id for e in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_count_all_entries(self, temp_storage):
        """Test counting all entries."""
        for i in range(7):
            temp_storage.store(
                MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            )

        count = temp_storage.count()
        assert count == 7

    def test_count_by_type(self, temp_storage):
        """Test counting entries by type."""
        # Store different types
        for i in range(3):
            temp_storage.store(
                MemoryEntry(content=f"Short {i}", memory_type=MemoryType.SHORT_TERM)
            )
        for i in range(5):
            temp_storage.store(
                MemoryEntry(content=f"Long {i}", memory_type=MemoryType.LONG_TERM)
            )

        assert temp_storage.count(MemoryType.SHORT_TERM) == 3
        assert temp_storage.count(MemoryType.LONG_TERM) == 5
        assert temp_storage.count() == 8


class TestSQLiteStorageSearch:
    """Test search functionality."""

    def test_search_basic(self, temp_storage):
        """Test basic keyword search."""
        temp_storage.store(
            MemoryEntry(content="Python is great", memory_type=MemoryType.LONG_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="JavaScript is good", memory_type=MemoryType.LONG_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="Python Django", memory_type=MemoryType.LONG_TERM)
        )

        results = temp_storage.search("Python")
        assert len(results) == 2

    def test_search_case_insensitive(self, temp_storage):
        """Test case-insensitive search."""
        temp_storage.store(
            MemoryEntry(content="PYTHON is GREAT", memory_type=MemoryType.LONG_TERM)
        )

        results = temp_storage.search("python")
        assert len(results) >= 1  # Should find it (FTS or LIKE)

    def test_search_with_type_filter(self, temp_storage):
        """Test search with memory type filter."""
        temp_storage.store(
            MemoryEntry(content="Python short", memory_type=MemoryType.SHORT_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="Python long", memory_type=MemoryType.LONG_TERM)
        )

        results = temp_storage.search("Python", memory_type=MemoryType.LONG_TERM)
        assert len(results) == 1
        assert results[0].memory_type == MemoryType.LONG_TERM

    def test_search_with_limit(self, temp_storage):
        """Test search respects limit."""
        for i in range(10):
            temp_storage.store(
                MemoryEntry(content=f"Python {i}", memory_type=MemoryType.LONG_TERM)
            )

        results = temp_storage.search("Python", limit=5)
        assert len(results) == 5

    def test_search_no_results(self, temp_storage):
        """Test search with no matching results."""
        temp_storage.store(
            MemoryEntry(content="JavaScript", memory_type=MemoryType.LONG_TERM)
        )

        results = temp_storage.search("Python")
        assert len(results) == 0


class TestSQLiteStorageClear:
    """Test clear operations."""

    def test_clear_all(self, temp_storage):
        """Test clearing all entries."""
        for i in range(5):
            temp_storage.store(
                MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            )

        cleared = temp_storage.clear()
        assert cleared == 5
        assert temp_storage.count() == 0

    def test_clear_by_type(self, temp_storage):
        """Test clearing specific type."""
        # Store different types
        for i in range(3):
            temp_storage.store(
                MemoryEntry(content=f"Short {i}", memory_type=MemoryType.SHORT_TERM)
            )
        for i in range(4):
            temp_storage.store(
                MemoryEntry(content=f"Long {i}", memory_type=MemoryType.LONG_TERM)
            )

        # Clear short-term only
        cleared = temp_storage.clear(memory_type=MemoryType.SHORT_TERM)
        assert cleared == 3
        assert temp_storage.count(MemoryType.SHORT_TERM) == 0
        assert temp_storage.count(MemoryType.LONG_TERM) == 4


class TestSQLiteStorageAccessTracking:
    """Test access tracking functionality."""

    def test_access_count_updates(self, temp_storage, sample_entry):
        """Test that access count increases on retrieval."""
        temp_storage.store(sample_entry)

        # Retrieve multiple times
        temp_storage.retrieve(sample_entry.id)
        temp_storage.retrieve(sample_entry.id)
        retrieved = temp_storage.retrieve(sample_entry.id)

        assert retrieved.access_count == 3

    def test_last_accessed_updates(self, temp_storage, sample_entry):
        """Test that last_accessed updates on retrieval."""
        temp_storage.store(sample_entry)

        retrieved = temp_storage.retrieve(sample_entry.id)
        assert retrieved.last_accessed is not None
        assert isinstance(retrieved.last_accessed, datetime)


class TestSQLiteStorageStats:
    """Test storage statistics."""

    def test_get_stats(self, temp_storage):
        """Test getting storage statistics."""
        # Store entries of different types
        temp_storage.store(
            MemoryEntry(content="Short", memory_type=MemoryType.SHORT_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="Long", memory_type=MemoryType.LONG_TERM)
        )
        temp_storage.store(
            MemoryEntry(content="Pref", memory_type=MemoryType.PREFERENCE)
        )

        stats = temp_storage.get_stats()

        assert stats["total_entries"] == 3
        assert stats["db_size_bytes"] > 0
        assert "by_type" in stats
        assert stats["by_type"]["short_term"] == 1
        assert stats["by_type"]["long_term"] == 1
        assert stats["by_type"]["preference"] == 1
        assert "page_count" in stats
        assert "page_size" in stats


class TestSQLiteStoragePerformance:
    """Test performance characteristics."""

    def test_large_dataset_storage(self, temp_storage):
        """Test storing large number of entries."""
        # Store 1000 entries
        for i in range(1000):
            temp_storage.store(
                MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            )

        assert temp_storage.count() == 1000

    def test_large_dataset_retrieval(self, temp_storage):
        """Test retrieving from large dataset."""
        entries = []
        for i in range(1000):
            entry = MemoryEntry(content=f"Memory {i}", memory_type=MemoryType.LONG_TERM)
            temp_storage.store(entry)
            entries.append(entry)

        # Retrieve random entry
        retrieved = temp_storage.retrieve(entries[500].id)
        assert retrieved is not None
        assert retrieved.id == entries[500].id


class TestSQLiteStorageEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_storage(self, temp_storage):
        """Test operations on empty storage."""
        assert temp_storage.count() == 0
        assert temp_storage.list_entries() == []
        assert temp_storage.search("anything") == []

    def test_very_long_content(self, temp_storage):
        """Test storing very long content."""
        long_content = "A" * 100000  # 100KB content
        entry = MemoryEntry(content=long_content, memory_type=MemoryType.LONG_TERM)

        temp_storage.store(entry)
        retrieved = temp_storage.retrieve(entry.id)

        assert retrieved.content == long_content

    def test_special_characters_in_content(self, temp_storage):
        """Test storing content with special characters."""
        special_content = 'Test with "quotes", \nnewlines, and unicode: 你好 🎉'
        entry = MemoryEntry(content=special_content, memory_type=MemoryType.LONG_TERM)

        temp_storage.store(entry)
        retrieved = temp_storage.retrieve(entry.id)

        assert retrieved.content == special_content

    def test_null_metadata(self, temp_storage):
        """Test storing entry with no metadata."""
        entry = MemoryEntry(content="Test", memory_type=MemoryType.LONG_TERM)
        entry.metadata = {}

        temp_storage.store(entry)
        retrieved = temp_storage.retrieve(entry.id)

        assert retrieved.metadata == {}

    def test_complex_metadata(self, temp_storage):
        """Test storing entry with complex metadata."""
        complex_metadata = {
            "tags": ["ai", "ml", "nlp"],
            "confidence": 0.95,
            "nested": {"key": "value"},
        }
        entry = MemoryEntry(
            content="Test",
            memory_type=MemoryType.LONG_TERM,
            metadata=complex_metadata,
        )

        temp_storage.store(entry)
        retrieved = temp_storage.retrieve(entry.id)

        assert retrieved.metadata == complex_metadata

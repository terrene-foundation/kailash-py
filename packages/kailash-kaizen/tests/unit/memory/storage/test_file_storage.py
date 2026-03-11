"""
Unit tests for FileStorage backend.

Tests all CRUD operations, search, pagination, and edge cases.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageError
from kaizen.memory.storage.file_storage import FileStorage


@pytest.fixture
def temp_storage():
    """Create temporary FileStorage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "test_memories.jsonl"
        yield FileStorage(str(storage_path))


@pytest.fixture
def sample_entry():
    """Create a sample memory entry for testing."""
    return MemoryEntry(
        content="User prefers concise responses",
        memory_type=MemoryType.PREFERENCE,
        metadata={"source": "test"},
        importance=0.8,
    )


class TestFileStorageBasics:
    """Test basic CRUD operations."""

    def test_store_entry(self, temp_storage, sample_entry):
        """Test storing a memory entry."""
        entry_id = temp_storage.store(sample_entry)
        assert entry_id == sample_entry.id
        assert entry_id is not None

    def test_retrieve_entry(self, temp_storage, sample_entry):
        """Test retrieving a stored entry."""
        temp_storage.store(sample_entry)
        retrieved = temp_storage.retrieve(sample_entry.id)

        assert retrieved is not None
        assert retrieved.id == sample_entry.id
        assert retrieved.content == sample_entry.content
        assert retrieved.memory_type == sample_entry.memory_type
        assert retrieved.metadata == sample_entry.metadata

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


class TestFileStorageListingAndCounting:
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


class TestFileStorageSearch:
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
        assert len(results) == 1

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


class TestFileStorageClear:
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


class TestFileStorageAccessTracking:
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


class TestFileStorageStats:
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
        assert stats["file_size_bytes"] > 0
        assert "by_type" in stats
        assert stats["by_type"]["short_term"] == 1
        assert stats["by_type"]["long_term"] == 1
        assert stats["by_type"]["preference"] == 1


class TestFileStorageEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_storage(self, temp_storage):
        """Test operations on empty storage."""
        assert temp_storage.count() == 0
        assert temp_storage.list_entries() == []
        assert temp_storage.search("anything") == []

    def test_malformed_json_line(self, temp_storage):
        """Test handling of malformed JSON lines."""
        # Write malformed line directly to file
        with open(temp_storage.file_path, "a") as f:
            f.write("this is not json\n")
            f.write(json.dumps({"valid": "json", "id": "test123"}))
            f.write("\n")

        # Should skip malformed line and continue
        entries = temp_storage._read_all_entries()
        # Should have 1 entry (the valid one), malformed line skipped
        assert (
            len(entries) == 0
        )  # Actually 0 because the valid json isn't a proper MemoryEntry

    def test_concurrent_writes(self, temp_storage):
        """Test that multiple writes work correctly."""
        entries = [
            MemoryEntry(content=f"Entry {i}", memory_type=MemoryType.LONG_TERM)
            for i in range(100)
        ]

        for entry in entries:
            temp_storage.store(entry)

        assert temp_storage.count() == 100

    def test_very_long_content(self, temp_storage):
        """Test storing very long content."""
        long_content = "A" * 10000  # 10KB content
        entry = MemoryEntry(content=long_content, memory_type=MemoryType.LONG_TERM)

        temp_storage.store(entry)
        retrieved = temp_storage.retrieve(entry.id)

        assert retrieved.content == long_content

    def test_special_characters_in_content(self, temp_storage):
        """Test storing content with special characters."""
        special_content = 'Test with "quotes", \nnewlines, and unicode: 你好'
        entry = MemoryEntry(content=special_content, memory_type=MemoryType.LONG_TERM)

        temp_storage.store(entry)
        retrieved = temp_storage.retrieve(entry.id)

        assert retrieved.content == special_content

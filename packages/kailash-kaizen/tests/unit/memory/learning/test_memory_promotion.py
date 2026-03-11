"""
Unit tests for memory promotion.

Tests short-term to long-term promotion based on access patterns and importance.
"""

from datetime import datetime, timedelta, timezone

import pytest

from kaizen.memory.learning.memory_promotion import MemoryPromoter
from kaizen.memory.long_term import LongTermMemory
from kaizen.memory.short_term import ShortTermMemory
from kaizen.memory.storage.base import MemoryType
from kaizen.memory.storage.file_storage import FileStorage


@pytest.fixture
def storage(tmp_path):
    """Create temporary file storage for testing."""
    storage_file = tmp_path / "promotion_test.jsonl"
    return FileStorage(str(storage_file))


@pytest.fixture
def short_term_memory(storage):
    """Create short-term memory instance."""
    return ShortTermMemory(
        storage=storage,
        ttl_seconds=3600,  # 1 hour
    )


@pytest.fixture
def long_term_memory(storage):
    """Create long-term memory instance."""
    return LongTermMemory(
        storage=storage,
        importance_threshold=0.3,
    )


@pytest.fixture
def promoter(short_term_memory, long_term_memory):
    """Create memory promoter with test memories."""
    return MemoryPromoter(
        short_term_memory=short_term_memory,
        long_term_memory=long_term_memory,
        access_threshold=3,
        importance_threshold=0.7,
        age_threshold_hours=24,
    )


class TestMemoryPromoterBasics:
    """Test basic memory promoter functionality."""

    def test_initialization(self, promoter, short_term_memory, long_term_memory):
        """Test promoter initializes correctly."""
        assert promoter.short_term == short_term_memory
        assert promoter.long_term == long_term_memory
        assert promoter.access_threshold == 3
        assert promoter.importance_threshold == 0.7
        assert promoter.age_threshold_hours == 24

    def test_get_stats_empty(self, promoter):
        """Test stats with no candidates."""
        stats = promoter.get_stats()

        assert stats["eligible_candidates"] == 0
        assert stats["avg_promotion_score"] == 0.0
        assert stats["access_threshold"] == 3
        assert stats["importance_threshold"] == 0.7


class TestAutoPromotion:
    """Test automatic promotion functionality."""

    def test_auto_promote_no_candidates(self, promoter, short_term_memory):
        """Test auto promotion with no eligible entries."""
        # Store recent entry with low access
        short_term_memory.store("Recent low access entry")

        result = promoter.auto_promote()

        assert result["promoted"] == 0
        assert result["total_candidates"] >= 0

    def test_auto_promote_with_eligible_entry(
        self, promoter, short_term_memory, storage
    ):
        """Test auto promotion with eligible entry."""
        # Create entry
        entry_id = short_term_memory.store(
            content="Important frequently accessed information"
        )

        # Simulate age, access, and importance
        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=48)  # Old enough
        entry.access_count = 5  # Above threshold
        entry.importance = 0.8  # High importance
        storage.update(entry)

        result = promoter.auto_promote()

        assert result["promoted"] >= 1
        assert result["failed"] == 0

    def test_auto_promote_result_structure(self, promoter, short_term_memory, storage):
        """Test auto promote result structure."""
        # Create eligible entry
        entry_id = short_term_memory.store("Test content")

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 10
        entry.importance = 0.9
        storage.update(entry)

        result = promoter.auto_promote()

        assert "promoted" in result
        assert "skipped" in result
        assert "failed" in result
        assert "total_candidates" in result

    def test_auto_promote_skips_young_entries(
        self, promoter, short_term_memory, storage
    ):
        """Test that young entries are not promoted."""
        # Create recent entry (not old enough)
        entry_id = short_term_memory.store("Recent entry")

        entry = storage.retrieve(entry_id)
        entry.access_count = 10  # High access
        entry.importance = 0.9
        storage.update(entry)

        result = promoter.auto_promote()

        # Should skip due to age
        assert result["promoted"] == 0


class TestManualPromotion:
    """Test manual entry promotion."""

    def test_promote_entry_success(
        self, promoter, short_term_memory, long_term_memory, storage
    ):
        """Test successful entry promotion."""
        # Create eligible entry
        entry_id = short_term_memory.store("Content to promote")

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 5
        entry.importance = 0.8
        storage.update(entry)

        new_id = promoter.promote_entry(entry_id)

        assert new_id is not None

        # Verify promoted entry exists in long-term
        promoted = long_term_memory.retrieve(new_id)
        assert promoted is not None
        assert promoted.memory_type == MemoryType.LONG_TERM
        assert "promoted_from" in promoted.metadata
        assert promoted.metadata["promoted_from"] == "short_term"

    def test_promote_entry_with_override(
        self, promoter, short_term_memory, long_term_memory
    ):
        """Test promotion with eligibility override."""
        # Create ineligible entry (too young)
        entry_id = short_term_memory.store("Recent entry")

        # Promote with override
        new_id = promoter.promote_entry(entry_id, override=True)

        assert new_id is not None

        # Verify promotion occurred despite ineligibility
        promoted = long_term_memory.retrieve(new_id)
        assert promoted is not None

    def test_promote_entry_not_found(self, promoter):
        """Test promotion of non-existent entry."""
        result = promoter.promote_entry("nonexistent_id")

        assert result is None

    def test_promote_entry_metadata_preservation(
        self, promoter, short_term_memory, long_term_memory, storage
    ):
        """Test that metadata is preserved during promotion."""
        # Create entry with metadata
        entry_id = short_term_memory.store(
            content="Entry with metadata",
            metadata={"source": "user", "category": "important"},
        )

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 5
        entry.importance = 0.9
        storage.update(entry)

        new_id = promoter.promote_entry(entry_id)

        # Verify metadata preserved
        promoted = long_term_memory.retrieve(new_id)
        assert promoted.metadata["source"] == "user"
        assert promoted.metadata["category"] == "important"
        assert "promoted_from" in promoted.metadata
        assert "original_id" in promoted.metadata


class TestPatternPromotion:
    """Test pattern and preference promotion."""

    def test_promote_pattern(self, promoter, long_term_memory):
        """Test promoting a recognized pattern."""
        pattern_id = promoter.promote_pattern(
            pattern_content="Users frequently ask about password reset",
            importance=0.85,
        )

        assert pattern_id is not None

        # Verify pattern stored
        pattern = long_term_memory.retrieve(pattern_id)
        assert pattern is not None
        assert pattern.metadata["source"] == "pattern_recognition"
        assert pattern.importance == 0.85

    def test_promote_preference(self, promoter, long_term_memory):
        """Test promoting a learned preference."""
        pref_id = promoter.promote_preference(
            preference_content="User prefers detailed code examples",
            confidence=0.9,
        )

        assert pref_id is not None

        # Verify preference stored
        pref = long_term_memory.retrieve(pref_id)
        assert pref is not None
        assert pref.metadata["source"] == "preference_learning"
        assert pref.metadata["confidence"] == 0.9
        assert pref.importance == 0.9


class TestPromotionCandidates:
    """Test promotion candidate identification."""

    def test_get_promotion_candidates_empty(self, promoter):
        """Test getting candidates when none exist."""
        candidates = promoter.get_promotion_candidates()

        assert len(candidates) == 0

    def test_get_promotion_candidates_with_eligible(
        self, promoter, short_term_memory, storage
    ):
        """Test getting promotion candidates."""
        # Create multiple entries with varying eligibility
        for i in range(3):
            entry_id = short_term_memory.store(content=f"Entry {i}")

            entry = storage.retrieve(entry_id)
            entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
            entry.access_count = 5 + i
            entry.importance = 0.7 + i * 0.1
            storage.update(entry)

        candidates = promoter.get_promotion_candidates()

        assert len(candidates) > 0

    def test_promotion_candidate_structure(self, promoter, short_term_memory, storage):
        """Test promotion candidate structure."""
        # Create eligible candidate
        entry_id = short_term_memory.store("Candidate entry")

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 10
        entry.importance = 0.9
        storage.update(entry)

        candidates = promoter.get_promotion_candidates()

        assert len(candidates) > 0
        candidate = candidates[0]

        assert "entry_id" in candidate
        assert "content" in candidate
        assert "access_count" in candidate
        assert "importance" in candidate
        assert "calculated_importance" in candidate
        assert "promotion_score" in candidate
        assert "age_hours" in candidate

    def test_get_promotion_candidates_limit(self, promoter, short_term_memory, storage):
        """Test candidate retrieval respects limit."""
        # Create many eligible candidates
        for i in range(10):
            entry_id = short_term_memory.store(f"Entry {i}")

            entry = storage.retrieve(entry_id)
            entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
            entry.access_count = 5
            entry.importance = 0.8
            storage.update(entry)

        candidates = promoter.get_promotion_candidates(limit=5)

        assert len(candidates) <= 5

    def test_candidates_sorted_by_score(self, promoter, short_term_memory, storage):
        """Test candidates are sorted by promotion score."""
        # Create candidates with different scores
        for i in range(3):
            entry_id = short_term_memory.store(f"Entry {i}")

            entry = storage.retrieve(entry_id)
            entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
            entry.access_count = 3 + i * 2
            entry.importance = 0.5 + i * 0.2
            storage.update(entry)

        candidates = promoter.get_promotion_candidates()

        # Verify sorted by promotion score descending
        if len(candidates) > 1:
            for i in range(len(candidates) - 1):
                assert (
                    candidates[i]["promotion_score"]
                    >= candidates[i + 1]["promotion_score"]
                )


class TestPromotionHistory:
    """Test promotion history tracking."""

    def test_get_promotion_history_empty(self, promoter):
        """Test getting history when no promotions."""
        history = promoter.get_promotion_history()

        assert len(history) == 0

    def test_get_promotion_history_with_promotions(
        self, promoter, short_term_memory, storage
    ):
        """Test getting promotion history."""
        # Promote an entry
        entry_id = short_term_memory.store("Promoted content")

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 5
        entry.importance = 0.9
        storage.update(entry)

        promoter.promote_entry(entry_id)

        # Get history
        history = promoter.get_promotion_history(days=7)

        assert len(history) > 0

    def test_promotion_history_structure(self, promoter, short_term_memory, storage):
        """Test promotion history entry structure."""
        # Promote entry
        entry_id = short_term_memory.store("Test content")

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 7
        entry.importance = 0.8
        storage.update(entry)

        promoter.promote_entry(entry_id)

        history = promoter.get_promotion_history()

        if len(history) > 0:
            entry = history[0]

            assert "entry_id" in entry
            assert "content" in entry
            assert "promoted_from" in entry
            assert "promoted_at" in entry
            assert "importance" in entry


class TestMemoryPromoterStats:
    """Test memory promoter statistics."""

    def test_stats_with_candidates(self, promoter, short_term_memory, storage):
        """Test stats with promotion candidates."""
        # Create eligible candidates
        for i in range(3):
            entry_id = short_term_memory.store(f"Entry {i}")

            entry = storage.retrieve(entry_id)
            entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
            entry.access_count = 5
            entry.importance = 0.8
            storage.update(entry)

        stats = promoter.get_stats()

        assert stats["eligible_candidates"] > 0
        assert stats["avg_promotion_score"] > 0
        assert stats["access_threshold"] == 3
        assert stats["importance_threshold"] == 0.7
        assert stats["age_threshold_hours"] == 24

    def test_stats_after_promotions(self, promoter, short_term_memory, storage):
        """Test stats reflect recent promotions."""
        # Create and promote entry
        entry_id = short_term_memory.store("Promoted entry")

        entry = storage.retrieve(entry_id)
        entry.timestamp = datetime.now(timezone.utc) - timedelta(hours=30)
        entry.access_count = 10
        entry.importance = 0.9
        storage.update(entry)

        promoter.promote_entry(entry_id)

        stats = promoter.get_stats()

        assert stats["promoted_last_7_days"] > 0

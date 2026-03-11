"""
Unit tests for pattern recognition learning.

Tests FAQ detection, access pattern analysis, and consolidation suggestions.
"""

from datetime import datetime, timedelta, timezone

import pytest

from kaizen.memory.learning.pattern_recognition import PatternRecognizer
from kaizen.memory.storage.base import MemoryEntry, MemoryType
from kaizen.memory.storage.file_storage import FileStorage


@pytest.fixture
def storage(tmp_path):
    """Create temporary file storage for testing."""
    storage_file = tmp_path / "pattern_test.jsonl"
    return FileStorage(str(storage_file))


@pytest.fixture
def recognizer(storage):
    """Create pattern recognizer with test storage."""
    return PatternRecognizer(
        storage=storage,
        min_frequency=2,
        time_window_days=7,
    )


class TestPatternRecognizerBasics:
    """Test basic pattern recognizer functionality."""

    def test_initialization(self, recognizer, storage):
        """Test recognizer initializes correctly."""
        assert recognizer.storage == storage
        assert recognizer.min_frequency == 2
        assert recognizer.time_window_days == 7
        assert recognizer.similarity_threshold == 0.8

    def test_get_stats_empty(self, recognizer):
        """Test stats with no entries."""
        stats = recognizer.get_stats()

        assert stats["total_entries"] == 0
        assert stats["recent_entries"] == 0
        assert stats["avg_access_count"] == 0
        assert stats["highly_accessed"] == 0


class TestFAQDetection:
    """Test FAQ detection functionality."""

    def test_detect_faqs_no_patterns(self, recognizer, storage):
        """Test FAQ detection with no patterns."""
        # Store entries with low access count
        for i in range(3):
            entry = MemoryEntry(
                content=f"Unique question {i}",
                memory_type=MemoryType.SHORT_TERM,
                importance=0.5,
            )
            entry.access_count = 1  # Below min_frequency
            storage.store(entry)

        faqs = recognizer.detect_faqs()
        assert len(faqs) == 0

    def test_detect_faqs_with_patterns(self, recognizer, storage):
        """Test FAQ detection with repeated patterns."""
        # Create similar questions with high access count
        for i in range(3):
            entry = MemoryEntry(
                content="How do I reset my password?",
                memory_type=MemoryType.SHORT_TERM,
                importance=0.7,
            )
            entry.access_count = 5
            storage.store(entry)

        faqs = recognizer.detect_faqs()

        assert len(faqs) >= 1
        assert faqs[0]["frequency"] >= 2
        assert faqs[0]["total_accesses"] >= 10

    def test_detect_faqs_with_limit(self, recognizer, storage):
        """Test FAQ detection respects limit."""
        # Create multiple FAQ patterns
        patterns = ["How to login?", "Reset password?", "Change email?"]

        for pattern in patterns:
            for i in range(3):
                entry = MemoryEntry(
                    content=pattern,
                    memory_type=MemoryType.SHORT_TERM,
                    importance=0.6,
                )
                entry.access_count = 4
                storage.store(entry)

        faqs = recognizer.detect_faqs(limit=2)
        assert len(faqs) <= 2

    def test_faq_structure(self, recognizer, storage):
        """Test FAQ entry structure."""
        # Store repeated question
        for i in range(3):
            entry = MemoryEntry(
                content="What is the meaning of life?",
                memory_type=MemoryType.LONG_TERM,
                importance=0.8,
            )
            entry.access_count = 10
            storage.store(entry)

        faqs = recognizer.detect_faqs()

        assert len(faqs) > 0
        faq = faqs[0]

        assert "pattern" in faq
        assert "frequency" in faq
        assert "total_accesses" in faq
        assert "example_query" in faq
        assert "entries" in faq
        assert "avg_importance" in faq
        assert "first_seen" in faq
        assert "last_seen" in faq


class TestAccessPatterns:
    """Test access pattern detection."""

    def test_detect_frequent_entries(self, recognizer, storage):
        """Test frequent access pattern detection."""
        # Create frequently accessed entry
        entry = MemoryEntry(
            content="Frequently accessed information",
            memory_type=MemoryType.LONG_TERM,
            importance=0.9,
        )
        entry.access_count = 50
        storage.store(entry)

        patterns = recognizer.detect_access_patterns()

        assert "frequent" in patterns
        assert len(patterns["frequent"]) > 0
        assert patterns["frequent"][0].access_count == 50

    def test_detect_trending_entries(self, recognizer, storage):
        """Test trending access pattern detection."""
        # Create recently accessed entry
        entry = MemoryEntry(
            content="Trending topic",
            memory_type=MemoryType.SHORT_TERM,
            importance=0.7,
        )
        entry.access_count = 5
        entry.last_accessed = datetime.now(timezone.utc)
        storage.store(entry)

        patterns = recognizer.detect_access_patterns()

        assert "trending" in patterns
        assert len(patterns["trending"]) > 0

    def test_detect_abandoned_entries(self, recognizer, storage):
        """Test abandoned entry detection."""
        # Create old entry with high access but not recent
        entry = MemoryEntry(
            content="Old frequently accessed",
            memory_type=MemoryType.LONG_TERM,
            importance=0.6,
        )
        entry.access_count = 20
        entry.last_accessed = datetime.now(timezone.utc) - timedelta(days=30)
        storage.store(entry)

        patterns = recognizer.detect_access_patterns()

        assert "abandoned" in patterns
        assert len(patterns["abandoned"]) > 0
        assert patterns["abandoned"][0].access_count >= 20


class TestConsolidationSuggestions:
    """Test consolidation suggestion functionality."""

    def test_suggest_consolidation_no_candidates(self, recognizer, storage):
        """Test consolidation with no high-access entries."""
        # Store low-access entries
        for i in range(3):
            entry = MemoryEntry(
                content=f"Low access entry {i}",
                memory_type=MemoryType.SHORT_TERM,
                importance=0.4,
            )
            entry.access_count = 1
            storage.store(entry)

        suggestions = recognizer.suggest_consolidation()
        assert len(suggestions) == 0

    def test_suggest_consolidation_with_candidates(self, recognizer, storage):
        """Test consolidation suggestions for promotion candidates."""
        # Store high-access, high-importance short-term entry
        entry = MemoryEntry(
            content="Important frequently accessed information",
            memory_type=MemoryType.SHORT_TERM,
            importance=0.8,
        )
        entry.access_count = 10
        storage.store(entry)

        suggestions = recognizer.suggest_consolidation()

        assert len(suggestions) > 0
        assert suggestions[0]["action"] == "promote_to_long_term"
        assert suggestions[0]["access_count"] >= 10
        assert suggestions[0]["importance"] >= 0.6

    def test_consolidation_suggestion_structure(self, recognizer, storage):
        """Test consolidation suggestion structure."""
        # Create promotion candidate
        entry = MemoryEntry(
            content="Candidate for promotion",
            memory_type=MemoryType.SHORT_TERM,
            importance=0.9,
        )
        entry.access_count = 15
        storage.store(entry)

        suggestions = recognizer.suggest_consolidation()

        assert len(suggestions) > 0
        suggestion = suggestions[0]

        assert "action" in suggestion
        assert "entry_id" in suggestion
        assert "reason" in suggestion
        assert "importance" in suggestion
        assert "access_count" in suggestion


class TestQueryPatternAnalysis:
    """Test query pattern analysis."""

    def test_analyze_query_patterns_empty(self, recognizer):
        """Test analysis with no queries."""
        result = recognizer.analyze_query_patterns([])

        assert result["total_queries"] == 0
        assert result["unique_queries"] == 0
        assert result["repetition_rate"] == 0

    def test_analyze_query_patterns_unique(self, recognizer):
        """Test analysis with all unique queries."""
        queries = ["Question 1", "Question 2", "Question 3"]

        result = recognizer.analyze_query_patterns(queries)

        assert result["total_queries"] == 3
        assert result["unique_queries"] == 3
        assert result["repetition_rate"] == 0.0

    def test_analyze_query_patterns_repeated(self, recognizer):
        """Test analysis with repeated queries."""
        queries = ["Same question"] * 5 + ["Different question"] * 2

        result = recognizer.analyze_query_patterns(queries)

        assert result["total_queries"] == 7
        assert result["unique_queries"] == 2
        assert result["repetition_rate"] > 0

    def test_analyze_question_detection(self, recognizer):
        """Test question word detection."""
        queries = [
            "What is the weather?",
            "How do I reset password?",
            "This is not a question",
        ]

        result = recognizer.analyze_query_patterns(queries)

        assert result["question_queries"] >= 2
        assert "common_keywords" in result


class TestPatternRecognizerStats:
    """Test pattern recognizer statistics."""

    def test_stats_with_entries(self, recognizer, storage):
        """Test stats with various entries."""
        # Create mix of entries
        for i in range(5):
            entry = MemoryEntry(
                content=f"Entry {i}",
                memory_type=MemoryType.SHORT_TERM,
                importance=0.5 + i * 0.1,
            )
            entry.access_count = i + 1
            storage.store(entry)

        stats = recognizer.get_stats()

        assert stats["total_entries"] == 5
        assert stats["avg_access_count"] > 0
        assert stats["time_window_days"] == 7
        assert stats["min_frequency"] == 2

    def test_stats_highly_accessed_count(self, recognizer, storage):
        """Test highly accessed entry count in stats."""
        # Create entries with varying access counts
        for i in range(3):
            entry = MemoryEntry(
                content=f"High access {i}",
                memory_type=MemoryType.LONG_TERM,
                importance=0.7,
            )
            entry.access_count = 5
            storage.store(entry)

        # Low access entry
        entry = MemoryEntry(
            content="Low access",
            memory_type=MemoryType.SHORT_TERM,
            importance=0.4,
        )
        entry.access_count = 1
        storage.store(entry)

        stats = recognizer.get_stats()

        # Should count entries with access_count >= min_frequency (2)
        assert stats["highly_accessed"] >= 3

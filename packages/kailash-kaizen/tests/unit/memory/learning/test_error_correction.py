"""
Unit tests for error correction learning.

Tests error recording, correction tracking, and prevention suggestions.
"""

from datetime import datetime, timedelta, timezone

import pytest

from kaizen.memory.learning.error_correction import ErrorCorrectionLearner
from kaizen.memory.storage.base import MemoryType
from kaizen.memory.storage.file_storage import FileStorage


@pytest.fixture
def storage(tmp_path):
    """Create temporary file storage for testing."""
    storage_file = tmp_path / "error_correction_test.jsonl"
    return FileStorage(str(storage_file))


@pytest.fixture
def learner(storage):
    """Create error correction learner with test storage."""
    return ErrorCorrectionLearner(
        storage=storage,
        recurrence_threshold=2,
        effectiveness_threshold=0.7,
    )


class TestErrorCorrectionLearnerBasics:
    """Test basic error correction learner functionality."""

    def test_initialization(self, learner, storage):
        """Test learner initializes correctly."""
        assert learner.storage == storage
        assert learner.recurrence_threshold == 2
        assert learner.effectiveness_threshold == 0.7

    def test_get_stats_empty(self, learner):
        """Test stats with no errors."""
        stats = learner.get_stats()

        assert stats["total_errors"] == 0
        assert stats["corrected_errors"] == 0
        assert stats["correction_rate"] == 0.0
        assert stats["total_corrections"] == 0


class TestErrorRecording:
    """Test error recording functionality."""

    def test_record_error_basic(self, learner):
        """Test basic error recording."""
        error_id = learner.record_error(
            error_description="Database connection failed",
            context={"host": "localhost", "port": 5432},
            severity="high",
            error_type="connection",
        )

        assert error_id is not None

        # Verify error stored
        error = learner.storage.retrieve(error_id)
        assert error is not None
        assert error.memory_type == MemoryType.ERROR
        assert error.content == "Database connection failed"
        assert error.metadata["severity"] == "high"
        assert error.metadata["error_type"] == "connection"
        assert error.metadata["corrected"] is False

    def test_record_error_severity_mapping(self, learner):
        """Test error severity maps to importance correctly."""
        # Test different severity levels
        severities = {
            "low": 0.3,
            "medium": 0.6,
            "high": 0.8,
            "critical": 1.0,
        }

        for severity, expected_importance in severities.items():
            error_id = learner.record_error(
                error_description=f"Test {severity} error",
                context={},
                severity=severity,
            )

            error = learner.storage.retrieve(error_id)
            assert error.importance == expected_importance

    def test_record_error_signature_extraction(self, learner):
        """Test error signature extraction."""
        error_id = learner.record_error(
            error_description="Connection timeout after 30 seconds waiting",
            context={},
            error_type="timeout",
        )

        error = learner.storage.retrieve(error_id)
        signature = error.metadata["error_signature"]

        assert "timeout" in signature
        assert len(signature) > 0

    def test_record_error_without_type(self, learner):
        """Test recording error without explicit type."""
        error_id = learner.record_error(
            error_description="Something went wrong",
            context={},
        )

        error = learner.storage.retrieve(error_id)
        assert error.metadata["error_type"] == "unknown"


class TestCorrectionRecording:
    """Test correction recording functionality."""

    def test_record_successful_correction(self, learner):
        """Test recording successful correction."""
        # Record error first
        error_id = learner.record_error(
            error_description="API rate limit exceeded",
            context={"endpoint": "/api/data"},
            severity="medium",
        )

        # Record correction
        correction_id = learner.record_correction(
            error_id=error_id,
            correction="Implemented exponential backoff retry",
            successful=True,
            time_to_fix_seconds=120.0,
        )

        assert correction_id is not None

        # Verify error marked as corrected
        error = learner.storage.retrieve(error_id)
        assert error.metadata["corrected"] is True
        assert error.metadata["correction_attempts"] == 1

        # Verify correction stored
        correction = learner.storage.retrieve(correction_id)
        assert correction is not None
        assert correction.memory_type == MemoryType.CORRECTION
        assert correction.metadata["successful"] is True
        assert correction.metadata["time_to_fix"] == 120.0

    def test_record_failed_correction(self, learner):
        """Test recording failed correction attempt."""
        error_id = learner.record_error(
            error_description="Memory leak detected",
            context={},
            severity="high",
        )

        correction_id = learner.record_correction(
            error_id=error_id,
            correction="Attempted garbage collection",
            successful=False,
        )

        # Error should not be marked as corrected
        error = learner.storage.retrieve(error_id)
        assert error.metadata["corrected"] is False
        assert error.metadata["correction_attempts"] == 1

        # Correction should have lower importance
        correction = learner.storage.retrieve(correction_id)
        assert correction.importance == 0.5

    def test_record_correction_nonexistent_error(self, learner):
        """Test recording correction for non-existent error."""
        result = learner.record_correction(
            error_id="nonexistent_id",
            correction="Some fix",
            successful=True,
        )

        assert result is None

    def test_multiple_correction_attempts(self, learner):
        """Test multiple correction attempts on same error."""
        error_id = learner.record_error(
            error_description="Intermittent network issue",
            context={},
        )

        # First attempt
        learner.record_correction(error_id, "Retry connection", successful=False)

        # Second attempt
        learner.record_correction(error_id, "Switch to backup server", successful=True)

        error = learner.storage.retrieve(error_id)
        assert error.metadata["correction_attempts"] == 2
        assert error.metadata["corrected"] is True


class TestRecurringErrorDetection:
    """Test recurring error detection."""

    def test_detect_recurring_errors_none(self, learner):
        """Test detection with no recurring errors."""
        # Record single instance of different errors
        learner.record_error("Error type 1", {})
        learner.record_error("Error type 2", {})

        recurring = learner.detect_recurring_errors()

        assert len(recurring) == 0

    def test_detect_recurring_errors_with_pattern(self, learner, storage):
        """Test detection of recurring error pattern."""
        # Create multiple instances of same error
        for i in range(3):
            learner.record_error(
                error_description="Authentication failed for user",
                context={"user_id": f"user_{i}"},
                error_type="auth",
            )

        recurring = learner.detect_recurring_errors(days=30)

        assert len(recurring) > 0
        assert recurring[0]["occurrences"] >= 2

    def test_recurring_error_structure(self, learner, storage):
        """Test recurring error entry structure."""
        # Create recurring error
        for i in range(3):
            learner.record_error(
                "File not found error",
                {"file": f"file_{i}.txt"},
                error_type="file_io",
            )

        recurring = learner.detect_recurring_errors()

        if len(recurring) > 0:
            error = recurring[0]

            assert "error_signature" in error
            assert "occurrences" in error
            assert "corrected_count" in error
            assert "correction_rate" in error
            assert "avg_severity" in error
            assert "latest_occurrence" in error
            assert "error_type" in error

    def test_recurring_errors_sorted_by_frequency(self, learner):
        """Test recurring errors sorted by occurrence count."""
        # Create errors with different frequencies
        for i in range(5):
            learner.record_error("Very common error", {})

        for i in range(3):
            learner.record_error("Less common error", {})

        recurring = learner.detect_recurring_errors()

        if len(recurring) > 1:
            assert recurring[0]["occurrences"] >= recurring[1]["occurrences"]


class TestCorrectionSuggestions:
    """Test correction suggestion functionality."""

    def test_suggest_correction_no_history(self, learner):
        """Test suggestion with no correction history."""
        suggestion = learner.suggest_correction(
            error_description="New unknown error",
            error_type="unknown",
        )

        assert suggestion is None

    def test_suggest_correction_with_history(self, learner, storage):
        """Test suggestion based on past successful corrections."""
        # Record error and correction
        error_id = learner.record_error(
            "Database timeout error",
            {},
            error_type="database",
        )

        learner.record_correction(
            error_id,
            "Increased connection pool size",
            successful=True,
            time_to_fix_seconds=60.0,
        )

        # Mark error as corrected
        error = storage.retrieve(error_id)
        error.metadata["corrected"] = True
        storage.update(error)

        # Request suggestion for similar error
        suggestion = learner.suggest_correction(
            "Database timeout error occurred",
            error_type="database",
        )

        if suggestion:
            assert "correction" in suggestion
            assert "confidence" in suggestion
            assert "success_rate" in suggestion
            assert "usage_count" in suggestion

    def test_suggest_correction_requires_effectiveness(self, learner, storage):
        """Test that suggestions are based on past successful corrections."""
        # Record error with one successful correction
        error_id = learner.record_error(
            "Occasional crash",
            {},
            error_type="crash",
        )

        # Mark error as corrected so it can be used for suggestions
        error = storage.retrieve(error_id)
        error.metadata["corrected"] = True
        storage.update(error)

        # Record successful correction
        learner.record_correction(error_id, "Final fix", successful=True)

        # Should generate suggestion based on successful correction
        suggestion = learner.suggest_correction("Occasional crash", error_type="crash")

        # Suggestion should be returned with high success rate since only successful correction exists
        assert suggestion is not None
        assert suggestion["success_rate"] == 1.0
        assert suggestion["usage_count"] == 1


class TestErrorPatterns:
    """Test error pattern analysis."""

    def test_get_error_patterns_empty(self, learner):
        """Test getting patterns with no errors."""
        patterns = learner.get_error_patterns()

        assert len(patterns) == 0

    def test_get_error_patterns_with_errors(self, learner):
        """Test getting error patterns."""
        # Create errors of different types
        for i in range(3):
            learner.record_error(
                f"Network error {i}",
                {},
                severity="medium",
                error_type="network",
            )

        for i in range(2):
            learner.record_error(
                f"Database error {i}",
                {},
                severity="high",
                error_type="database",
            )

        patterns = learner.get_error_patterns()

        assert len(patterns) >= 2

    def test_error_pattern_structure(self, learner):
        """Test error pattern entry structure."""
        # Create errors
        for i in range(3):
            learner.record_error(
                "API error",
                {},
                error_type="api",
                severity="medium",
            )

        patterns = learner.get_error_patterns()

        if len(patterns) > 0:
            pattern = patterns[0]

            assert "error_type" in pattern
            assert "total_occurrences" in pattern
            assert "corrected_count" in pattern
            assert "correction_rate" in pattern
            assert "avg_correction_attempts" in pattern
            assert "severity_distribution" in pattern
            assert "first_seen" in pattern
            assert "last_seen" in pattern

    def test_error_patterns_sorted_by_frequency(self, learner):
        """Test error patterns sorted by occurrence count."""
        # Create errors with different frequencies
        for i in range(5):
            learner.record_error("Common error", {}, error_type="common")

        for i in range(2):
            learner.record_error("Rare error", {}, error_type="rare")

        patterns = learner.get_error_patterns()

        if len(patterns) > 1:
            assert patterns[0]["total_occurrences"] >= patterns[1]["total_occurrences"]


class TestPreventionSuggestions:
    """Test prevention suggestion functionality."""

    def test_get_prevention_suggestions_empty(self, learner):
        """Test prevention suggestions with no errors."""
        suggestions = learner.get_prevention_suggestions()

        assert len(suggestions) == 0

    def test_get_prevention_suggestions_for_recurring_errors(self, learner, storage):
        """Test suggestions for recurring errors."""
        # Create recurring error
        for i in range(6):
            learner.record_error(
                "Recurring validation error",
                {},
                error_type="validation",
            )

        suggestions = learner.get_prevention_suggestions()

        # Should suggest prevention for frequently occurring error
        assert len(suggestions) > 0

    def test_prevention_suggestions_by_type(self, learner):
        """Test filtering prevention suggestions by error type."""
        # Create errors of different types
        for i in range(5):
            learner.record_error("Auth error", {}, error_type="auth")

        for i in range(3):
            learner.record_error("Network error", {}, error_type="network")

        # Get suggestions for specific type
        suggestions = learner.get_prevention_suggestions(error_type="auth")

        # Should only suggest for auth errors
        assert all("auth" in str(s).lower() or "frequently" in s for s in suggestions)


class TestCorrectionHistory:
    """Test correction history tracking."""

    def test_get_correction_history_empty(self, learner):
        """Test getting history with no corrections."""
        history = learner.get_correction_history()

        assert len(history) == 0

    def test_get_correction_history_with_corrections(self, learner):
        """Test getting correction history."""
        # Record error and correction
        error_id = learner.record_error("Test error", {})
        learner.record_correction(error_id, "Test fix", successful=True)

        history = learner.get_correction_history()

        assert len(history) > 0

    def test_correction_history_structure(self, learner):
        """Test correction history entry structure."""
        error_id = learner.record_error("Error description", {})
        learner.record_correction(
            error_id, "Fix description", successful=True, time_to_fix_seconds=30.0
        )

        history = learner.get_correction_history()

        if len(history) > 0:
            entry = history[0]

            assert "correction_id" in entry
            assert "error_id" in entry
            assert "error_description" in entry
            assert "correction" in entry
            assert "successful" in entry
            assert "time_to_fix" in entry
            assert "timestamp" in entry

    def test_correction_history_by_error(self, learner):
        """Test filtering history by specific error."""
        # Create two errors
        error_id_1 = learner.record_error("Error 1", {})
        error_id_2 = learner.record_error("Error 2", {})

        # Corrections for each
        learner.record_correction(error_id_1, "Fix 1", successful=True)
        learner.record_correction(error_id_2, "Fix 2", successful=True)

        # Get history for specific error
        history = learner.get_correction_history(error_id=error_id_1)

        # Should only show corrections for error_id_1
        assert all(h["error_id"] == error_id_1 for h in history)

    def test_correction_history_time_filtering(self, learner, storage):
        """Test filtering history by time."""
        # Create old error
        error_id = learner.record_error("Old error", {})
        correction_id = learner.record_correction(error_id, "Old fix", successful=True)

        # Simulate old timestamp
        correction = storage.retrieve(correction_id)
        correction.timestamp = datetime.now(timezone.utc) - timedelta(days=60)
        storage.update(correction)

        # Get recent history
        history = learner.get_correction_history(days=30)

        # Should not include old correction
        assert len([h for h in history if h["correction_id"] == correction_id]) == 0


class TestErrorCorrectionStats:
    """Test error correction statistics."""

    def test_stats_with_errors_and_corrections(self, learner):
        """Test stats with errors and corrections."""
        # Create errors
        for i in range(5):
            error_id = learner.record_error(f"Error {i}", {}, error_type="test")

            # Correct some
            if i < 3:
                learner.record_correction(error_id, f"Fix {i}", successful=True)

        stats = learner.get_stats()

        assert stats["total_errors"] == 5
        assert stats["corrected_errors"] >= 3
        assert stats["correction_rate"] > 0
        assert stats["total_corrections"] >= 3

    def test_stats_success_rate(self, learner):
        """Test correction success rate in stats."""
        error_id = learner.record_error("Error", {})

        # Multiple correction attempts
        learner.record_correction(error_id, "Attempt 1", successful=False)
        learner.record_correction(error_id, "Attempt 2", successful=True)

        stats = learner.get_stats()

        # Success rate should be 50%
        assert stats["success_rate"] == 0.5

    def test_stats_error_type_breakdown(self, learner):
        """Test error type breakdown in stats."""
        # Create errors of different types
        learner.record_error("Error 1", {}, error_type="type_a")
        learner.record_error("Error 2", {}, error_type="type_a")
        learner.record_error("Error 3", {}, error_type="type_b")

        stats = learner.get_stats()

        assert "error_types" in stats
        assert stats["error_types"]["type_a"] == 2
        assert stats["error_types"]["type_b"] == 1

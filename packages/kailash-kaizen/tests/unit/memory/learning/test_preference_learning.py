"""
Unit tests for preference learning.

Tests feedback-based learning, behavior analysis, and confidence scoring.
"""

import pytest
from kaizen.memory.learning.preference_learning import PreferenceLearner
from kaizen.memory.storage.base import MemoryType
from kaizen.memory.storage.file_storage import FileStorage


@pytest.fixture
def storage(tmp_path):
    """Create temporary file storage for testing."""
    storage_file = tmp_path / "preference_test.jsonl"
    return FileStorage(str(storage_file))


@pytest.fixture
def learner(storage):
    """Create preference learner with test storage."""
    return PreferenceLearner(
        storage=storage,
        confidence_threshold=0.6,
        min_evidence=2,
    )


class TestPreferenceLearnerBasics:
    """Test basic preference learner functionality."""

    def test_initialization(self, learner, storage):
        """Test learner initializes correctly."""
        assert learner.storage == storage
        assert learner.confidence_threshold == 0.6
        assert learner.min_evidence == 2

    def test_get_stats_empty(self, learner):
        """Test stats with no preferences."""
        stats = learner.get_stats()

        assert stats["total_preference_entries"] == 0
        assert stats["unique_preferences"] == 0
        assert stats["avg_confidence"] == 0.0


class TestFeedbackLearning:
    """Test learning from user feedback."""

    def test_learn_from_positive_feedback(self, learner):
        """Test learning from positive feedback."""
        entry_id = learner.learn_from_feedback(
            content="Generated response about Python",
            feedback="I prefer detailed code examples",
            feedback_type="positive",
        )

        assert entry_id is not None

        # Retrieve and verify
        entry = learner.storage.retrieve(entry_id)
        assert entry is not None
        assert entry.memory_type == MemoryType.PREFERENCE
        assert "prefer" in entry.content.lower()
        assert entry.metadata["feedback_type"] == "positive"
        assert entry.importance == 0.8

    def test_learn_from_negative_feedback(self, learner):
        """Test learning from negative feedback."""
        entry_id = learner.learn_from_feedback(
            content="Generated very technical response",
            feedback="Too technical, simplify please",
            feedback_type="negative",
        )

        assert entry_id is not None

        entry = learner.storage.retrieve(entry_id)
        assert entry is not None
        assert "dislikes" in entry.content.lower()
        assert entry.metadata["feedback_type"] == "negative"
        assert entry.importance == 0.6

    def test_learn_from_neutral_feedback(self, learner):
        """Test learning from neutral feedback."""
        entry_id = learner.learn_from_feedback(
            content="Standard response",
            feedback="This is okay but could be better",
            feedback_type="neutral",
        )

        assert entry_id is not None

        entry = learner.storage.retrieve(entry_id)
        assert entry is not None
        assert entry.metadata["feedback_type"] == "neutral"

    def test_feedback_metadata_storage(self, learner):
        """Test that feedback metadata is stored correctly."""
        entry_id = learner.learn_from_feedback(
            content="Original content here",
            feedback="User feedback text",
            feedback_type="positive",
        )

        entry = learner.storage.retrieve(entry_id)

        assert "source" in entry.metadata
        assert entry.metadata["source"] == "feedback"
        assert "original_content" in entry.metadata
        assert "feedback_text" in entry.metadata


class TestBehaviorLearning:
    """Test learning from user behavior."""

    def test_learn_from_selection_behavior(self, learner):
        """Test learning from selection behavior."""
        entry_id = learner.learn_from_behavior(
            action="selected",
            context={"content_type": "code_example"},
        )

        assert entry_id is not None

        entry = learner.storage.retrieve(entry_id)
        assert entry is not None
        assert "prefers" in entry.content.lower()
        assert entry.metadata["action"] == "selected"
        assert entry.metadata["source"] == "behavior"

    def test_learn_from_ignore_behavior(self, learner):
        """Test learning from ignore behavior."""
        entry_id = learner.learn_from_behavior(
            action="ignored",
            context={"content_type": "theoretical_explanation"},
        )

        assert entry_id is not None

        entry = learner.storage.retrieve(entry_id)
        assert "ignores" in entry.content.lower()

    def test_learn_from_request_behavior(self, learner):
        """Test learning from request behavior."""
        entry_id = learner.learn_from_behavior(
            action="requested",
            context={"feature": "dark_mode"},
        )

        assert entry_id is not None

        entry = learner.storage.retrieve(entry_id)
        assert "requests" in entry.content.lower()

    def test_learn_from_unknown_behavior(self, learner):
        """Test handling unknown behavior."""
        entry_id = learner.learn_from_behavior(
            action="unknown_action",
            context={"some": "data"},
        )

        # Should return None for unrecognized actions
        assert entry_id is None


class TestPreferenceRetrieval:
    """Test preference retrieval and confidence scoring."""

    def test_get_preferences_empty(self, learner):
        """Test getting preferences when none exist."""
        prefs = learner.get_preferences()

        assert len(prefs) == 0

    def test_get_preferences_insufficient_evidence(self, learner):
        """Test that preferences need minimum evidence."""
        # Store single preference (below min_evidence=2)
        learner.learn_from_feedback(
            content="Test",
            feedback="I like detailed examples",
            feedback_type="positive",
        )

        prefs = learner.get_preferences()

        # Should not return preference with insufficient evidence
        assert len(prefs) == 0

    def test_get_preferences_with_sufficient_evidence(self, learner):
        """Test preferences with sufficient evidence."""
        # Store multiple similar preferences
        for i in range(3):
            learner.learn_from_feedback(
                content=f"Test content {i}",
                feedback="I prefer concise responses",
                feedback_type="positive",
            )

        prefs = learner.get_preferences()

        assert len(prefs) > 0
        assert prefs[0]["evidence_count"] >= 2
        assert prefs[0]["confidence"] >= learner.confidence_threshold

    def test_preference_structure(self, learner):
        """Test preference entry structure."""
        # Create preference with evidence
        for i in range(3):
            learner.learn_from_feedback(
                content=f"Test {i}",
                feedback="I like code examples",
                feedback_type="positive",
            )

        prefs = learner.get_preferences()

        assert len(prefs) > 0
        pref = prefs[0]

        assert "preference" in pref
        assert "confidence" in pref
        assert "evidence_count" in pref
        assert "first_seen" in pref
        assert "last_seen" in pref
        assert "sources" in pref

    def test_get_preferences_limit(self, learner):
        """Test preference retrieval respects limit."""
        # Create multiple different preferences
        preferences = [
            "I prefer detailed explanations",
            "I like short summaries",
            "I want code examples",
        ]

        for pref_text in preferences:
            for i in range(3):
                learner.learn_from_feedback(
                    content=f"Test {pref_text} {i}",
                    feedback=pref_text,
                    feedback_type="positive",
                )

        prefs = learner.get_preferences(limit=2)

        assert len(prefs) <= 2


class TestPreferenceUpdating:
    """Test preference updating and reinforcement."""

    def test_update_preference_strengthen(self, learner):
        """Test strengthening a preference."""
        # Create initial preference
        entry_id = learner.learn_from_feedback(
            content="Test",
            feedback="I prefer detailed responses",
            feedback_type="positive",
        )

        initial_entry = learner.storage.retrieve(entry_id)
        initial_importance = initial_entry.importance

        # Strengthen preference (use the actual stored content prefix)
        learner.update_preference(
            preference="User prefers: I prefer detailed",  # Match first 5 words
            reinforcement=True,
            strength=0.1,
        )

        # Verify importance increased
        updated_entry = learner.storage.retrieve(entry_id)
        assert updated_entry.importance > initial_importance

    def test_update_preference_weaken(self, learner):
        """Test weakening a preference."""
        # Create initial preference
        entry_id = learner.learn_from_feedback(
            content="Test",
            feedback="I like short answers",
            feedback_type="positive",
        )

        initial_entry = learner.storage.retrieve(entry_id)
        initial_importance = initial_entry.importance

        # Weaken preference (use the actual stored content prefix)
        learner.update_preference(
            preference="User prefers: I like short",  # Match first 5 words
            reinforcement=False,
            strength=0.1,
        )

        # Verify importance decreased
        updated_entry = learner.storage.retrieve(entry_id)
        assert updated_entry.importance < initial_importance


class TestPreferenceConsolidation:
    """Test preference consolidation."""

    def test_consolidate_preferences_no_duplicates(self, learner):
        """Test consolidation with unique preferences."""
        # Create unique preferences
        for i in range(3):
            learner.learn_from_feedback(
                content=f"Test {i}",
                feedback=f"Unique preference {i}",
                feedback_type="positive",
            )

        result = learner.consolidate_preferences()

        assert result["total_groups"] == 3
        assert result["merged_preferences"] == 0

    def test_consolidate_preferences_with_duplicates(self, learner):
        """Test consolidation merges similar preferences."""
        # Create duplicate preferences with varying importance
        for i in range(3):
            learner.learn_from_feedback(
                content=f"Test {i}",
                feedback="I prefer detailed explanations with examples",
                feedback_type="positive",
            )

        initial_count = len(
            learner.storage.list_entries(memory_type=MemoryType.PREFERENCE)
        )

        result = learner.consolidate_preferences()

        final_count = len(
            learner.storage.list_entries(memory_type=MemoryType.PREFERENCE)
        )

        # Should have merged duplicates
        assert final_count < initial_count
        assert result["merged_preferences"] > 0


class TestPreferenceDrift:
    """Test preference drift detection."""

    def test_detect_preference_drift_no_changes(self, learner):
        """Test drift detection with stable preferences."""
        # Create preference
        learner.learn_from_feedback(
            content="Test",
            feedback="I like code examples",
            feedback_type="positive",
        )

        changes = learner.detect_preference_drift(days=30)

        # No drift expected with single preference
        assert isinstance(changes, list)

    def test_detect_preference_drift_new_preference(self, learner):
        """Test detection of new preferences."""
        # Create recent preference
        learner.learn_from_feedback(
            content="Test",
            feedback="I now prefer visual diagrams",
            feedback_type="positive",
        )

        changes = learner.detect_preference_drift(days=1)

        # Should detect new preference
        new_prefs = [c for c in changes if c["type"] == "new"]
        assert len(new_prefs) > 0


class TestPreferenceLearnerStats:
    """Test preference learner statistics."""

    def test_stats_with_preferences(self, learner):
        """Test stats with stored preferences."""
        # Create preferences from different sources
        learner.learn_from_feedback(
            content="Test 1",
            feedback="I prefer details",
            feedback_type="positive",
        )

        learner.learn_from_behavior(
            action="selected",
            context={"content_type": "code"},
        )

        stats = learner.get_stats()

        assert stats["total_preference_entries"] >= 2
        assert "sources" in stats
        assert stats["confidence_threshold"] == 0.6
        assert stats["min_evidence"] == 2

    def test_stats_source_breakdown(self, learner):
        """Test stats show source breakdown."""
        # Create preferences from multiple sources
        learner.learn_from_feedback(
            content="Test",
            feedback="Preference 1",
            feedback_type="positive",
        )

        learner.learn_from_behavior(
            action="selected",
            context={"content_type": "example"},
        )

        stats = learner.get_stats()

        assert "feedback" in stats["sources"]
        assert "behavior" in stats["sources"]
        assert stats["sources"]["feedback"] >= 1
        assert stats["sources"]["behavior"] >= 1

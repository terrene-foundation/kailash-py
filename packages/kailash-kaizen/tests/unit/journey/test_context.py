"""
Unit tests for ContextAccumulator and merge strategies (TODO-JO-004).

Tests cover:
- REQ-PM-002: ContextAccumulator class
- MergeStrategy enum and all strategies
- Field-level merge configuration
- Context versioning and snapshots
- Size limit validation
- AccumulatedField and ContextSnapshot dataclasses

These are Tier 1 (Unit) tests that don't require real infrastructure.
"""

from datetime import datetime, timezone

import pytest

from kaizen.journey import JourneyConfig
from kaizen.journey.context import (
    AccumulatedField,
    ContextAccumulator,
    ContextSnapshot,
    MergeStrategy,
)
from kaizen.journey.errors import ContextSizeExceededError

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def config():
    """Create default JourneyConfig."""
    return JourneyConfig()


@pytest.fixture
def accumulator(config):
    """Create ContextAccumulator instance."""
    return ContextAccumulator(config)


@pytest.fixture
def small_config():
    """Create JourneyConfig with small context size limit."""
    return JourneyConfig(max_context_size_bytes=100)


# ============================================================================
# MergeStrategy Enum Tests
# ============================================================================


class TestMergeStrategy:
    """Tests for MergeStrategy enum."""

    def test_all_strategies_defined(self):
        """Test that all expected strategies are defined."""
        strategies = [
            MergeStrategy.REPLACE,
            MergeStrategy.APPEND,
            MergeStrategy.MERGE_DICT,
            MergeStrategy.MAX,
            MergeStrategy.MIN,
            MergeStrategy.SUM,
            MergeStrategy.UNION,
        ]
        assert len(strategies) == 7

    def test_strategy_values(self):
        """Test strategy string values."""
        assert MergeStrategy.REPLACE.value == "replace"
        assert MergeStrategy.APPEND.value == "append"
        assert MergeStrategy.MERGE_DICT.value == "merge"
        assert MergeStrategy.MAX.value == "max"
        assert MergeStrategy.MIN.value == "min"
        assert MergeStrategy.SUM.value == "sum"
        assert MergeStrategy.UNION.value == "union"


# ============================================================================
# AccumulatedField Tests
# ============================================================================


class TestAccumulatedField:
    """Tests for AccumulatedField dataclass."""

    def test_create_accumulated_field(self):
        """Test creating AccumulatedField."""
        now = datetime.now(timezone.utc)
        field = AccumulatedField(
            name="customer_name",
            value="Alice",
            source_pathway="intake",
            timestamp=now,
            version=1,
        )

        assert field.name == "customer_name"
        assert field.value == "Alice"
        assert field.source_pathway == "intake"
        assert field.timestamp == now
        assert field.version == 1

    def test_accumulated_field_default_version(self):
        """Test AccumulatedField default version is 1."""
        field = AccumulatedField(
            name="test",
            value="value",
            source_pathway="path",
            timestamp=datetime.now(timezone.utc),
        )
        assert field.version == 1


# ============================================================================
# ContextSnapshot Tests
# ============================================================================


class TestContextSnapshot:
    """Tests for ContextSnapshot dataclass."""

    def test_create_context_snapshot(self):
        """Test creating ContextSnapshot."""
        now = datetime.now(timezone.utc)
        context = {"name": "Alice", "email": "alice@example.com"}

        snapshot = ContextSnapshot(
            context=context,
            pathway_id="booking",
            timestamp=now,
            version=5,
        )

        assert snapshot.context == context
        assert snapshot.pathway_id == "booking"
        assert snapshot.timestamp == now
        assert snapshot.version == 5


# ============================================================================
# ContextAccumulator Initialization Tests
# ============================================================================


class TestContextAccumulatorInit:
    """Tests for ContextAccumulator initialization."""

    def test_init_with_config(self, config):
        """Test ContextAccumulator initialization."""
        accumulator = ContextAccumulator(config)

        assert accumulator.config is config
        assert accumulator._merge_strategies == {}
        assert accumulator._field_history == {}
        assert accumulator._snapshots == []
        assert accumulator._version == 0

    def test_get_version_initial(self, accumulator):
        """Test initial version is 0."""
        assert accumulator.get_version() == 0


# ============================================================================
# Field Configuration Tests
# ============================================================================


class TestFieldConfiguration:
    """Tests for field-level merge strategy configuration."""

    def test_configure_field(self, accumulator):
        """Test configuring a single field."""
        accumulator.configure_field("rejected_doctors", MergeStrategy.APPEND)

        strategies = accumulator.get_configured_strategies()
        assert strategies["rejected_doctors"] == MergeStrategy.APPEND

    def test_configure_multiple_fields(self, accumulator):
        """Test configuring multiple fields."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)
        accumulator.configure_field("preferences", MergeStrategy.UNION)
        accumulator.configure_field("total", MergeStrategy.SUM)

        strategies = accumulator.get_configured_strategies()
        assert len(strategies) == 3
        assert strategies["rejected"] == MergeStrategy.APPEND
        assert strategies["preferences"] == MergeStrategy.UNION
        assert strategies["total"] == MergeStrategy.SUM

    def test_configure_fields_batch(self, accumulator):
        """Test configuring fields in batch."""
        accumulator.configure_fields(
            {
                "rejected_doctors": MergeStrategy.APPEND,
                "preferences": MergeStrategy.UNION,
                "visit_count": MergeStrategy.SUM,
            }
        )

        strategies = accumulator.get_configured_strategies()
        assert len(strategies) == 3

    def test_get_configured_strategies_returns_copy(self, accumulator):
        """Test that get_configured_strategies returns a copy."""
        accumulator.configure_field("test", MergeStrategy.APPEND)

        strategies1 = accumulator.get_configured_strategies()
        strategies2 = accumulator.get_configured_strategies()

        assert strategies1 is not strategies2
        assert strategies1 == strategies2


# ============================================================================
# Accumulate Tests - REPLACE Strategy
# ============================================================================


class TestReplaceStrategy:
    """Tests for REPLACE merge strategy (default)."""

    def test_replace_new_field(self, accumulator):
        """Test adding a new field uses REPLACE by default."""
        context = {}
        accumulator.accumulate(context, {"name": "Alice"}, "intake")

        assert context["name"] == "Alice"

    def test_replace_existing_field(self, accumulator):
        """Test replacing an existing field."""
        context = {"name": "Alice"}
        accumulator.accumulate(context, {"name": "Bob"}, "intake")

        assert context["name"] == "Bob"

    def test_replace_skips_none_values(self, accumulator):
        """Test that None values are skipped."""
        context = {"name": "Alice"}
        accumulator.accumulate(context, {"name": None, "age": 30}, "intake")

        assert context["name"] == "Alice"  # Not replaced by None
        assert context["age"] == 30


# ============================================================================
# Accumulate Tests - APPEND Strategy
# ============================================================================


class TestAppendStrategy:
    """Tests for APPEND merge strategy."""

    def test_append_to_empty_context(self, accumulator):
        """Test appending to empty context creates list."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)

        context = {}
        accumulator.accumulate(context, {"rejected": "Dr. Smith"}, "booking")

        assert context["rejected"] == "Dr. Smith"  # Single value, not wrapped

    def test_append_to_existing_single_value(self, accumulator):
        """Test appending to existing single value creates list."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)

        context = {"rejected": "Dr. Smith"}
        accumulator.accumulate(context, {"rejected": "Dr. Jones"}, "booking")

        assert context["rejected"] == ["Dr. Smith", "Dr. Jones"]

    def test_append_to_existing_list(self, accumulator):
        """Test appending to existing list."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)

        context = {"rejected": ["Dr. Smith"]}
        accumulator.accumulate(context, {"rejected": "Dr. Jones"}, "booking")

        assert context["rejected"] == ["Dr. Smith", "Dr. Jones"]

    def test_append_list_to_list(self, accumulator):
        """Test appending a list to existing list."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)

        context = {"rejected": ["Dr. Smith"]}
        accumulator.accumulate(
            context, {"rejected": ["Dr. Jones", "Dr. Brown"]}, "booking"
        )

        assert context["rejected"] == ["Dr. Smith", "Dr. Jones", "Dr. Brown"]


# ============================================================================
# Accumulate Tests - MERGE_DICT Strategy
# ============================================================================


class TestMergeDictStrategy:
    """Tests for MERGE_DICT merge strategy."""

    def test_merge_dict_new_field(self, accumulator):
        """Test merging to empty context."""
        accumulator.configure_field("metadata", MergeStrategy.MERGE_DICT)

        context = {}
        accumulator.accumulate(context, {"metadata": {"key": "value"}}, "intake")

        assert context["metadata"] == {"key": "value"}

    def test_merge_dict_existing_dict(self, accumulator):
        """Test merging two dictionaries."""
        accumulator.configure_field("metadata", MergeStrategy.MERGE_DICT)

        context = {"metadata": {"a": 1, "b": 2}}
        accumulator.accumulate(context, {"metadata": {"b": 3, "c": 4}}, "intake")

        assert context["metadata"] == {"a": 1, "b": 3, "c": 4}

    def test_merge_dict_replaces_non_dict(self, accumulator):
        """Test that merging replaces non-dict values."""
        accumulator.configure_field("metadata", MergeStrategy.MERGE_DICT)

        context = {"metadata": "not_a_dict"}
        accumulator.accumulate(context, {"metadata": {"key": "value"}}, "intake")

        assert context["metadata"] == {"key": "value"}


# ============================================================================
# Accumulate Tests - MAX Strategy
# ============================================================================


class TestMaxStrategy:
    """Tests for MAX merge strategy."""

    def test_max_new_field(self, accumulator):
        """Test MAX on new field."""
        accumulator.configure_field("score", MergeStrategy.MAX)

        context = {}
        accumulator.accumulate(context, {"score": 50}, "intake")

        assert context["score"] == 50

    def test_max_keeps_larger_value(self, accumulator):
        """Test MAX keeps larger value."""
        accumulator.configure_field("score", MergeStrategy.MAX)

        context = {"score": 50}
        accumulator.accumulate(context, {"score": 75}, "intake")

        assert context["score"] == 75

    def test_max_keeps_existing_if_larger(self, accumulator):
        """Test MAX keeps existing if larger."""
        accumulator.configure_field("score", MergeStrategy.MAX)

        context = {"score": 100}
        accumulator.accumulate(context, {"score": 75}, "intake")

        assert context["score"] == 100


# ============================================================================
# Accumulate Tests - MIN Strategy
# ============================================================================


class TestMinStrategy:
    """Tests for MIN merge strategy."""

    def test_min_new_field(self, accumulator):
        """Test MIN on new field."""
        accumulator.configure_field("wait_time", MergeStrategy.MIN)

        context = {}
        accumulator.accumulate(context, {"wait_time": 30}, "booking")

        assert context["wait_time"] == 30

    def test_min_keeps_smaller_value(self, accumulator):
        """Test MIN keeps smaller value."""
        accumulator.configure_field("wait_time", MergeStrategy.MIN)

        context = {"wait_time": 30}
        accumulator.accumulate(context, {"wait_time": 15}, "booking")

        assert context["wait_time"] == 15

    def test_min_keeps_existing_if_smaller(self, accumulator):
        """Test MIN keeps existing if smaller."""
        accumulator.configure_field("wait_time", MergeStrategy.MIN)

        context = {"wait_time": 10}
        accumulator.accumulate(context, {"wait_time": 15}, "booking")

        assert context["wait_time"] == 10


# ============================================================================
# Accumulate Tests - SUM Strategy
# ============================================================================


class TestSumStrategy:
    """Tests for SUM merge strategy."""

    def test_sum_new_field(self, accumulator):
        """Test SUM on new field."""
        accumulator.configure_field("total_cost", MergeStrategy.SUM)

        context = {}
        accumulator.accumulate(context, {"total_cost": 100}, "booking")

        assert context["total_cost"] == 100

    def test_sum_adds_values(self, accumulator):
        """Test SUM adds values."""
        accumulator.configure_field("total_cost", MergeStrategy.SUM)

        context = {"total_cost": 100}
        accumulator.accumulate(context, {"total_cost": 50}, "booking")

        assert context["total_cost"] == 150

    def test_sum_handles_floats(self, accumulator):
        """Test SUM handles float values."""
        accumulator.configure_field("total", MergeStrategy.SUM)

        context = {"total": 10.5}
        accumulator.accumulate(context, {"total": 5.5}, "booking")

        assert context["total"] == 16.0


# ============================================================================
# Accumulate Tests - UNION Strategy
# ============================================================================


class TestUnionStrategy:
    """Tests for UNION merge strategy."""

    def test_union_new_field(self, accumulator):
        """Test UNION on new field."""
        accumulator.configure_field("preferences", MergeStrategy.UNION)

        context = {}
        accumulator.accumulate(
            context, {"preferences": ["morning", "female"]}, "intake"
        )

        assert context["preferences"] == ["morning", "female"]

    def test_union_removes_duplicates(self, accumulator):
        """Test UNION removes duplicates."""
        accumulator.configure_field("preferences", MergeStrategy.UNION)

        context = {"preferences": ["morning", "female"]}
        accumulator.accumulate(
            context, {"preferences": ["morning", "telehealth"]}, "booking"
        )

        # Check all unique values present
        assert set(context["preferences"]) == {"morning", "female", "telehealth"}

    def test_union_preserves_order(self, accumulator):
        """Test UNION preserves order from old + new unique."""
        accumulator.configure_field("tags", MergeStrategy.UNION)

        context = {"tags": ["a", "b"]}
        accumulator.accumulate(context, {"tags": ["c", "b", "d"]}, "intake")

        # Order: old items first, then new unique items
        assert context["tags"] == ["a", "b", "c", "d"]


# ============================================================================
# Version and History Tests
# ============================================================================


class TestVersioning:
    """Tests for context versioning."""

    def test_version_increments_on_accumulate(self, accumulator):
        """Test version increments with each accumulation."""
        context = {}

        accumulator.accumulate(context, {"a": 1}, "p1")
        assert accumulator.get_version() == 1

        accumulator.accumulate(context, {"b": 2}, "p2")
        assert accumulator.get_version() == 2

        accumulator.accumulate(context, {"c": 3}, "p3")
        assert accumulator.get_version() == 3


class TestFieldHistory:
    """Tests for field history tracking."""

    def test_get_field_history(self, accumulator):
        """Test retrieving field history."""
        context = {}
        accumulator.accumulate(context, {"name": "Alice"}, "intake")
        accumulator.accumulate(context, {"name": "Alice Smith"}, "update")

        history = accumulator.get_field_history("name")

        assert len(history) == 2
        assert history[0].value == "Alice"
        assert history[0].source_pathway == "intake"
        assert history[1].value == "Alice Smith"
        assert history[1].source_pathway == "update"

    def test_get_field_history_returns_copy(self, accumulator):
        """Test that get_field_history returns a copy."""
        context = {}
        accumulator.accumulate(context, {"name": "Alice"}, "intake")

        history1 = accumulator.get_field_history("name")
        history2 = accumulator.get_field_history("name")

        assert history1 is not history2

    def test_get_field_history_empty(self, accumulator):
        """Test get_field_history for non-existent field."""
        history = accumulator.get_field_history("nonexistent")
        assert history == []


# ============================================================================
# Snapshot Tests
# ============================================================================


class TestSnapshots:
    """Tests for context snapshots."""

    def test_create_snapshot(self, accumulator):
        """Test creating a snapshot."""
        context = {"name": "Alice", "email": "alice@example.com"}
        snapshot = accumulator.snapshot(context, "booking")

        assert snapshot.context == context
        assert snapshot.pathway_id == "booking"
        assert snapshot.version == accumulator.get_version()
        assert isinstance(snapshot.timestamp, datetime)

    def test_snapshot_creates_copy(self, accumulator):
        """Test that snapshot creates a copy of context."""
        context = {"name": "Alice"}
        snapshot = accumulator.snapshot(context, "booking")

        # Modify original context
        context["name"] = "Bob"

        # Snapshot should retain original value
        assert snapshot.context["name"] == "Alice"

    def test_get_latest_snapshot(self, accumulator):
        """Test getting latest snapshot."""
        context = {"v": 1}
        accumulator.snapshot(context, "p1")
        context["v"] = 2
        accumulator.snapshot(context, "p2")
        context["v"] = 3
        snapshot = accumulator.snapshot(context, "p3")

        latest = accumulator.get_latest_snapshot()

        assert latest is snapshot
        assert latest.context["v"] == 3
        assert latest.pathway_id == "p3"

    def test_get_latest_snapshot_empty(self, accumulator):
        """Test get_latest_snapshot when no snapshots exist."""
        assert accumulator.get_latest_snapshot() is None

    def test_restore_snapshot(self, accumulator):
        """Test restoring from snapshot."""
        context = {"name": "Alice", "count": 1}
        accumulator.accumulate(context, {}, "p1")  # Version 1
        accumulator.snapshot(context, "p1")

        context["name"] = "Bob"
        context["count"] = 2
        accumulator.accumulate(context, {}, "p2")  # Version 2

        # Restore to version 1
        restored = accumulator.restore_snapshot(1)

        assert restored["name"] == "Alice"
        assert restored["count"] == 1

    def test_restore_snapshot_returns_copy(self, accumulator):
        """Test that restore_snapshot returns a copy."""
        context = {"name": "Alice"}
        accumulator.accumulate(context, {}, "p1")
        accumulator.snapshot(context, "p1")

        restored1 = accumulator.restore_snapshot(1)
        restored2 = accumulator.restore_snapshot(1)

        assert restored1 is not restored2

    def test_restore_nonexistent_version(self, accumulator):
        """Test restoring non-existent version returns None."""
        restored = accumulator.restore_snapshot(999)
        assert restored is None


# ============================================================================
# Size Validation Tests
# ============================================================================


class TestSizeValidation:
    """Tests for context size validation."""

    def test_get_context_size(self, accumulator):
        """Test getting context size."""
        context = {"name": "Alice"}
        size = accumulator.get_context_size(context)

        assert size > 0
        assert isinstance(size, int)

    def test_validate_size_within_limit(self, accumulator):
        """Test validation passes within limit."""
        context = {"name": "Alice"}
        assert accumulator.validate_size(context) is True

    def test_validate_size_exceeds_limit(self, small_config):
        """Test validation fails when exceeding limit."""
        accumulator = ContextAccumulator(small_config)

        # Create large context
        context = {"data": "x" * 200}  # Exceeds 100 byte limit

        assert accumulator.validate_size(context) is False

    def test_accumulate_raises_on_size_exceeded(self, small_config):
        """Test that accumulate raises ContextSizeExceededError."""
        accumulator = ContextAccumulator(small_config)

        context = {}
        with pytest.raises(ContextSizeExceededError) as exc_info:
            accumulator.accumulate(context, {"data": "x" * 200}, "intake")

        assert exc_info.value.max_size == 100


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStats:
    """Tests for accumulator statistics."""

    def test_get_stats_initial(self, accumulator):
        """Test initial statistics."""
        stats = accumulator.get_stats()

        assert stats["version"] == 0
        assert stats["configured_fields"] == 0
        assert stats["tracked_fields"] == 0
        assert stats["snapshot_count"] == 0
        assert stats["total_history_entries"] == 0

    def test_get_stats_after_operations(self, accumulator):
        """Test statistics after operations."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)
        accumulator.configure_field("total", MergeStrategy.SUM)

        context = {}
        accumulator.accumulate(context, {"name": "Alice"}, "intake")
        accumulator.accumulate(context, {"rejected": "Dr. Smith"}, "booking")
        accumulator.snapshot(context, "booking")

        stats = accumulator.get_stats()

        assert stats["version"] == 2
        assert stats["configured_fields"] == 2
        assert stats["tracked_fields"] == 2  # name, rejected
        assert stats["snapshot_count"] == 1
        assert stats["total_history_entries"] == 2

    def test_clear_history(self, accumulator):
        """Test clearing history."""
        context = {}
        accumulator.accumulate(context, {"name": "Alice"}, "intake")
        accumulator.snapshot(context, "intake")

        accumulator.clear_history()

        stats = accumulator.get_stats()
        assert stats["tracked_fields"] == 0
        assert stats["snapshot_count"] == 0


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_accumulate_returns_context(self, accumulator):
        """Test that accumulate returns the context."""
        context = {}
        result = accumulator.accumulate(context, {"name": "Alice"}, "intake")

        assert result is context

    def test_mixed_strategies_in_single_call(self, accumulator):
        """Test multiple strategies in single accumulate call."""
        accumulator.configure_field("rejected", MergeStrategy.APPEND)
        accumulator.configure_field("total", MergeStrategy.SUM)

        context = {"rejected": ["Dr. A"], "total": 100, "name": "Alice"}
        accumulator.accumulate(
            context,
            {"rejected": "Dr. B", "total": 50, "name": "Alice Smith"},
            "booking",
        )

        assert context["rejected"] == ["Dr. A", "Dr. B"]  # APPEND
        assert context["total"] == 150  # SUM
        assert context["name"] == "Alice Smith"  # REPLACE (default)

    def test_handle_non_json_serializable(self, accumulator):
        """Test handling non-JSON-serializable objects."""
        context = {"func": lambda x: x}  # Non-serializable

        # get_context_size should return 0 for non-serializable
        size = accumulator.get_context_size(context)
        assert size == 0

    def test_max_with_incompatible_types(self, accumulator):
        """Test MAX with incompatible types falls back to new value."""
        accumulator.configure_field("score", MergeStrategy.MAX)

        context = {"score": "not_a_number"}
        accumulator.accumulate(context, {"score": 100}, "intake")

        assert context["score"] == 100

    def test_sum_with_strings_falls_back(self, accumulator):
        """Test SUM with strings concatenates (Python behavior)."""
        accumulator.configure_field("data", MergeStrategy.SUM)

        context = {"data": "Hello "}
        accumulator.accumulate(context, {"data": "World"}, "intake")

        assert context["data"] == "Hello World"

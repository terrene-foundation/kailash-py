"""Unit tests for ExecutionTracker (TODO-005/006).

Tests cover:
- record_completion / is_completed / get_output
- to_dict / from_dict round-trip fidelity
- Non-serialisable output handling (graceful degradation)
- Edge cases: empty tracker, None output, non-dict output
"""

import math

import pytest

from kailash.runtime.execution_tracker import ExecutionTracker


class TestRecordAndQuery:
    """Tests for the recording and query API."""

    def test_empty_tracker(self):
        tracker = ExecutionTracker()
        assert tracker.completed_node_ids == []
        assert tracker.serialized_outputs == {}
        assert not tracker.is_completed("any_node")
        assert tracker.get_output("any_node") is None

    def test_record_single_completion(self):
        tracker = ExecutionTracker()
        tracker.record_completion("node_a", {"value": 42})
        assert tracker.is_completed("node_a")
        assert tracker.get_output("node_a") == {"value": 42}
        assert tracker.completed_node_ids == ["node_a"]

    def test_record_multiple_completions_preserves_order(self):
        tracker = ExecutionTracker()
        for node_id in ["alpha", "beta", "gamma"]:
            tracker.record_completion(node_id, {"id": node_id})
        assert tracker.completed_node_ids == ["alpha", "beta", "gamma"]

    def test_duplicate_record_updates_output_not_order(self):
        tracker = ExecutionTracker()
        tracker.record_completion("node_a", {"v": 1})
        tracker.record_completion("node_b", {"v": 2})
        tracker.record_completion("node_a", {"v": 99})

        # Output is updated
        assert tracker.get_output("node_a") == {"v": 99}
        # Order is NOT duplicated
        assert tracker.completed_node_ids == ["node_a", "node_b"]

    def test_none_output_becomes_empty_dict(self):
        tracker = ExecutionTracker()
        tracker.record_completion("node_x", None)
        assert tracker.is_completed("node_x")
        assert tracker.get_output("node_x") == {}

    def test_non_dict_output_wrapped(self):
        tracker = ExecutionTracker()
        tracker.record_completion("node_int", 42)
        assert tracker.get_output("node_int") == {"result": 42}

        tracker.record_completion("node_str", "hello")
        assert tracker.get_output("node_str") == {"result": "hello"}

        tracker.record_completion("node_list", [1, 2, 3])
        assert tracker.get_output("node_list") == {"result": [1, 2, 3]}


class TestSerializationRoundTrip:
    """Tests for to_dict / from_dict round-trip."""

    def test_empty_round_trip(self):
        tracker = ExecutionTracker()
        data = tracker.to_dict()
        restored = ExecutionTracker.from_dict(data)
        assert restored.completed_node_ids == []
        assert restored.serialized_outputs == {}

    def test_populated_round_trip(self):
        tracker = ExecutionTracker()
        tracker.record_completion("step_1", {"result": "data_1"})
        tracker.record_completion("step_2", {"result": "data_2"})
        tracker.record_completion("step_3", {"count": 10})

        data = tracker.to_dict()
        restored = ExecutionTracker.from_dict(data)

        assert restored.completed_node_ids == ["step_1", "step_2", "step_3"]
        assert restored.get_output("step_1") == {"result": "data_1"}
        assert restored.get_output("step_2") == {"result": "data_2"}
        assert restored.get_output("step_3") == {"count": 10}

    def test_round_trip_preserves_execution_order(self):
        tracker = ExecutionTracker()
        for i in range(5):
            tracker.record_completion(f"node_{i}", {"index": i})

        data = tracker.to_dict()
        restored = ExecutionTracker.from_dict(data)
        assert restored.completed_node_ids == [f"node_{i}" for i in range(5)]

    def test_from_dict_with_missing_fields(self):
        """from_dict should handle missing keys gracefully."""
        restored = ExecutionTracker.from_dict({})
        assert restored.completed_node_ids == []
        assert restored.serialized_outputs == {}

    def test_from_dict_with_partial_data(self):
        """from_dict with nodes listed but missing from outputs."""
        data = {
            "completed_nodes": ["a", "b"],
            "node_outputs": {"a": {"val": 1}},
            # "b" is missing from node_outputs
        }
        restored = ExecutionTracker.from_dict(data)
        assert restored.is_completed("a")
        assert restored.get_output("a") == {"val": 1}
        assert restored.is_completed("b")
        assert restored.get_output("b") == {}


class TestNonSerializableOutput:
    """Tests for graceful handling of non-JSON-serialisable outputs."""

    def test_dict_with_non_serialisable_values(self):
        tracker = ExecutionTracker()
        # Objects that are not JSON-serialisable
        output = {"obj": object(), "num": 42}
        tracker.record_completion("node_obj", output)
        result = tracker.get_output("node_obj")
        # Values should be stringified
        assert "num" in result
        assert result["num"] == "42" or result["num"] == 42

    def test_non_serialisable_non_dict_output(self):
        tracker = ExecutionTracker()
        tracker.record_completion("node_set", {1, 2, 3})
        result = tracker.get_output("node_set")
        # Should be wrapped as {"result": str({1,2,3})}
        assert "result" in result

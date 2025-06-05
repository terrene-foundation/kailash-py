"""Consolidated tests for logic operation nodes."""

import pytest

from kailash.nodes.logic.async_operations import AsyncMergeNode, AsyncSwitchNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.sdk_exceptions import NodeExecutionError


class TestLogicNodes:
    """Consolidated tests for all logic nodes."""

    def test_switch_node_operations(self):
        """Test SwitchNode with various conditions."""
        # Boolean condition - true case
        node = SwitchNode(
            input_data={"status": "success", "value": 100},
            condition_field="status",
            operator="==",
            value="success",
        )
        result = node.execute()
        assert result["true_output"] == {"status": "success", "value": 100}
        assert result["false_output"] is None
        assert result["condition_result"] is True

        # Boolean condition - false case
        node = SwitchNode(
            input_data={"status": "error", "value": 0},
            condition_field="status", 
            operator="==",
            value="success",
        )
        result = node.execute()
        assert result["true_output"] is None
        assert result["false_output"] == {"status": "error", "value": 0}
        assert result["condition_result"] is False

        # Numeric comparison
        node = SwitchNode(
            input_data={"score": 85},
            condition_field="score",
            operator=">",
            value=80,
        )
        result = node.execute()
        assert result["condition_result"] is True

    def test_merge_node_operations(self):
        """Test MergeNode with various merge strategies."""
        # Simple merge
        node = MergeNode(
            inputs=[
                {"name": "Alice", "age": 30},
                {"name": "Bob", "city": "NYC"}
            ]
        )
        result = node.execute()
        assert "merged_data" in result
        assert isinstance(result["merged_data"], list)
        assert len(result["merged_data"]) == 2

        # Merge with conflict resolution
        node = MergeNode(
            inputs=[
                {"id": 1, "name": "Alice"},
                {"id": 1, "name": "Alice Updated"}
            ],
            merge_strategy="last_wins"
        )
        result = node.execute()
        merged = result["merged_data"]
        # Should prefer last value in conflicts
        assert any("Updated" in str(item) for item in merged)

    def test_async_switch_node(self):
        """Test AsyncSwitchNode functionality."""
        node = AsyncSwitchNode(
            input_data={"value": 42},
            condition_field="value",
            operator=">",
            value=40,
        )
        result = node.execute()
        assert result["condition_result"] is True
        assert result["true_output"] == {"value": 42}

    def test_async_merge_node(self):
        """Test AsyncMergeNode functionality."""
        node = AsyncMergeNode(
            inputs=[
                {"data": "first"},
                {"data": "second"}
            ]
        )
        result = node.execute()
        assert "merged_data" in result
        assert len(result["merged_data"]) == 2

    def test_logic_node_edge_cases(self):
        """Test edge cases and error handling."""
        # Empty inputs for merge
        node = MergeNode(inputs=[])
        result = node.execute()
        assert result["merged_data"] == []

        # Missing field in switch
        with pytest.raises(NodeExecutionError):
            node = SwitchNode(
                input_data={"value": 10},
                condition_field="missing_field",
                operator="==",
                value="test"
            )
            node.execute()

        # Invalid operator
        with pytest.raises(NodeExecutionError):
            node = SwitchNode(
                input_data={"value": 10},
                condition_field="value",
                operator="invalid_op",
                value=5
            )
            node.execute()

    def test_complex_conditions(self):
        """Test complex conditional logic."""
        # Multiple conditions could be tested here
        # For now, test numeric comparisons
        test_cases = [
            ({"score": 95}, "score", ">", 90, True),
            ({"score": 85}, "score", ">=", 85, True),
            ({"score": 75}, "score", "<", 80, True),
            ({"score": 65}, "score", "<=", 65, True),
            ({"status": "active"}, "status", "!=", "inactive", True),
        ]
        
        for data, field, op, value, expected in test_cases:
            node = SwitchNode(
                input_data=data,
                condition_field=field,
                operator=op,
                value=value
            )
            result = node.execute()
            assert result["condition_result"] == expected
"""Consolidated tests for logic operation nodes."""

import pytest
from kailash.nodes.logic.async_operations import AsyncMergeNode, AsyncSwitchNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode


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
        # Simple list concatenation
        node = MergeNode(merge_type="concat")
        result = node.execute(
            data1=[{"name": "Alice", "age": 30}], data2=[{"name": "Bob", "city": "NYC"}]
        )
        assert "merged_data" in result
        assert isinstance(result["merged_data"], list)
        assert len(result["merged_data"]) == 2

        # Dictionary merging
        node = MergeNode(merge_type="merge_dict")
        result = node.execute(
            data1={"id": 1, "name": "Alice"},
            data2={"id": 1, "name": "Alice Updated", "age": 30},
        )
        merged = result["merged_data"]
        # Should merge dictionaries
        assert merged["name"] == "Alice Updated"
        assert merged["age"] == 30

    @pytest.mark.asyncio
    async def test_async_switch_node(self):
        """Test AsyncSwitchNode functionality."""
        node = AsyncSwitchNode(
            condition_field="value",
            operator=">",
            value=40,
        )
        result = await node.execute_async(input_data={"value": 42})
        assert result["condition_result"] is True
        assert result["true_output"] == {"value": 42}

    @pytest.mark.asyncio
    async def test_async_merge_node(self):
        """Test AsyncMergeNode functionality."""
        node = AsyncMergeNode(merge_type="concat")
        result = await node.execute_async(
            data1=[{"data": "first"}], data2=[{"data": "second"}]
        )
        assert "merged_data" in result
        assert len(result["merged_data"]) == 2

    def test_logic_node_edge_cases(self):
        """Test edge cases and error handling."""
        # Empty inputs for merge
        node = MergeNode(merge_type="concat")
        result = node.execute(data1=[], data2=[])
        assert result["merged_data"] == []

        # Missing field in switch - should return false
        node = SwitchNode(condition_field="missing_field", operator="==", value="test")
        result = node.execute(input_data={"value": 10})
        # Missing field returns None, which doesn't equal "test"
        assert result["condition_result"] is False
        assert result["false_output"] == {"value": 10}

        # Invalid operator - should return false
        node = SwitchNode(condition_field="value", operator="invalid_op", value=5)
        result = node.execute(input_data={"value": 10})
        # Invalid operator returns False
        assert result["condition_result"] is False
        assert result["false_output"] == {"value": 10}

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
                input_data=data, condition_field=field, operator=op, value=value
            )
            result = node.execute()
            assert result["condition_result"] == expected

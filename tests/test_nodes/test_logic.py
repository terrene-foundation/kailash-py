"""Tests for logic operation nodes."""

import pytest

from kailash.nodes.logic.async_operations import AsyncMergeNode, AsyncSwitchNode
from kailash.nodes.logic.operations import MergeNode, SwitchNode
from kailash.sdk_exceptions import NodeExecutionError


class TestSwitchNode:
    """Test Switch node functionality."""

    def test_boolean_condition_true(self):
        """Test boolean condition evaluating to true."""
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

    def test_boolean_condition_false(self):
        """Test boolean condition evaluating to false."""
        node = SwitchNode(
            input_data={"status": "error", "value": 100},
            condition_field="status",
            operator="==",
            value="success",
        )

        result = node.execute()

        assert result["true_output"] is None
        assert result["false_output"] == {"status": "error", "value": 100}
        assert result["condition_result"] is False

    def test_multi_case_switching(self):
        """Test multi-case switching with cases."""
        node = SwitchNode(
            input_data={"status": "warning", "message": "Alert"},
            condition_field="status",
            cases=["success", "warning", "error"],
        )

        result = node.execute()

        assert "case_warning" in result
        assert result["case_warning"] == {"status": "warning", "message": "Alert"}
        assert result["default"] == {"status": "warning", "message": "Alert"}
        assert result["condition_result"] == "warning"

    def test_multi_case_no_match(self):
        """Test multi-case switching with no matches."""
        node = SwitchNode(
            input_data={"status": "unknown", "message": "Unknown status"},
            condition_field="status",
            cases=["success", "warning", "error"],
        )

        result = node.execute()

        assert result["default"] == {"status": "unknown", "message": "Unknown status"}
        assert result["condition_result"] is None

    def test_numeric_comparison(self):
        """Test numeric comparison operations."""
        node = SwitchNode(
            input_data={"score": 85}, condition_field="score", operator=">", value=80
        )

        result = node.execute()

        assert result["true_output"] == {"score": 85}
        assert result["false_output"] is None
        assert result["condition_result"] is True

    def test_contains_operation(self):
        """Test contains operation."""
        node = SwitchNode(
            input_data={"tags": ["python", "node", "test"]},
            condition_field="tags",
            operator="contains",
            value="python",
        )

        result = node.execute()

        assert result["true_output"] == {"tags": ["python", "node", "test"]}
        assert result["condition_result"] is True

    def test_list_data_grouping(self):
        """Test switch with list of dictionaries."""
        node = SwitchNode(
            input_data=[
                {"status": "success", "id": 1},
                {"status": "error", "id": 2},
                {"status": "success", "id": 3},
            ],
            condition_field="status",
            cases=["success", "error"],
        )

        result = node.execute()

        assert len(result["case_success"]) == 2
        assert len(result["case_error"]) == 1
        assert result["case_success"][0]["id"] == 1
        assert result["case_error"][0]["id"] == 2

    def test_custom_case_prefix(self):
        """Test custom case prefix."""
        node = SwitchNode(
            input_data={"type": "urgent"},
            condition_field="type",
            cases=["urgent", "normal"],
            case_prefix="priority_",
        )

        result = node.execute()

        assert "priority_urgent" in result
        assert result["priority_urgent"] == {"type": "urgent"}

    def test_custom_default_field(self):
        """Test custom default field name."""
        node = SwitchNode(
            input_data={"status": "unknown"},
            condition_field="status",
            cases=["success", "warning", "error"],
            default_field="unmatched",
        )

        result = node.execute()

        assert "unmatched" in result
        assert result["unmatched"] == {"status": "unknown"}


class TestMergeNode:
    """Test Merge node functionality."""

    def test_concat_lists(self):
        """Test concatenating lists."""
        node = MergeNode(data1=[1, 2, 3], data2=[4, 5, 6], merge_type="concat")

        result = node.execute()

        assert result["merged_data"] == [1, 2, 3, 4, 5, 6]

    def test_concat_mixed_types(self):
        """Test concatenating mixed types."""
        node = MergeNode(data1="hello", data2="world", merge_type="concat")

        result = node.execute()

        assert result["merged_data"] == ["hello", "world"]

    def test_zip_merge(self):
        """Test zip merging."""
        node = MergeNode(data1=[1, 2, 3], data2=["a", "b", "c"], merge_type="zip")

        result = node.execute()

        assert result["merged_data"] == [(1, "a"), (2, "b"), (3, "c")]

    def test_merge_dictionaries(self):
        """Test merging dictionaries."""
        node = MergeNode(
            data1={"a": 1, "b": 2}, data2={"c": 3, "d": 4}, merge_type="merge_dict"
        )

        result = node.execute()

        assert result["merged_data"] == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test_merge_dict_with_key(self):
        """Test merging lists of dictionaries by key."""
        node = MergeNode(
            data1=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            data2=[{"id": 1, "age": 30}, {"id": 3, "age": 25}],
            merge_type="merge_dict",
            key="id",
        )

        result = node.execute()

        merged = result["merged_data"]
        assert len(merged) == 3

        # Find Alice's record
        alice = next(item for item in merged if item["name"] == "Alice")
        assert alice["age"] == 30  # Should be merged

    def test_multiple_data_sources(self):
        """Test merging multiple data sources."""
        node = MergeNode(data1=[1, 2], data2=[3, 4], data3=[5, 6], merge_type="concat")

        result = node.execute()

        assert result["merged_data"] == [1, 2, 3, 4, 5, 6]

    def test_skip_none_values(self):
        """Test skipping None values."""
        node = MergeNode(
            data1=[1, 2, 3],
            data2=None,
            data3=[4, 5, 6],
            merge_type="concat",
            skip_none=True,
        )

        result = node.execute()

        assert result["merged_data"] == [1, 2, 3, 4, 5, 6]

    def test_with_all_none_values(self):
        """Test with all None values."""
        node = MergeNode(
            data1=None, data2=None, data3=None, merge_type="concat", skip_none=True
        )

        result = node.execute()

        assert result["merged_data"] is None

    def test_single_input(self):
        """Test with single input."""
        node = MergeNode(data1=[1, 2, 3], merge_type="concat")

        result = node.execute()

        assert result["merged_data"] == [1, 2, 3]

    def test_unknown_merge_type(self):
        """Test unknown merge type raises error."""
        node = MergeNode(data1=[1, 2, 3], data2=[4, 5, 6])

        with pytest.raises(ValueError, match="Unknown merge type"):
            node.execute(merge_type="unknown_type")


class TestAsyncSwitchNode:
    """Test AsyncSwitch node functionality."""

    @pytest.mark.asyncio
    async def test_async_boolean_condition(self):
        """Test async boolean condition."""
        node = AsyncSwitchNode(
            input_data={"status": "success"},
            condition_field="status",
            operator="==",
            value="success",
        )

        result = await node.execute_async()

        assert result["true_output"] == {"status": "success"}
        assert result["false_output"] is None
        assert result["condition_result"] is True

    @pytest.mark.asyncio
    async def test_async_multi_case(self):
        """Test async multi-case switching."""
        node = AsyncSwitchNode(
            input_data={"priority": "high"},
            condition_field="priority",
            cases=["low", "medium", "high"],
        )

        result = await node.execute_async()

        assert "case_high" in result
        assert result["case_high"] == {"priority": "high"}
        assert result["condition_result"] == "high"

    @pytest.mark.asyncio
    async def test_async_list_grouping(self):
        """Test async list grouping."""
        node = AsyncSwitchNode(
            input_data=[
                {"category": "A", "value": 1},
                {"category": "B", "value": 2},
                {"category": "A", "value": 3},
            ],
            condition_field="category",
            cases=["A", "B"],
        )

        result = await node.execute_async()

        assert len(result["case_A"]) == 2
        assert len(result["case_B"]) == 1


class TestAsyncMergeNode:
    """Test AsyncMerge node functionality."""

    @pytest.mark.asyncio
    async def test_async_concat(self):
        """Test async concatenation."""
        node = AsyncMergeNode(data1=[1, 2, 3], data2=[4, 5, 6], merge_type="concat")

        result = await node.execute_async()

        assert result["merged_data"] == [1, 2, 3, 4, 5, 6]

    @pytest.mark.asyncio
    async def test_async_zip(self):
        """Test async zip merge."""
        node = AsyncMergeNode(data1=[1, 2, 3], data2=["x", "y", "z"], merge_type="zip")

        result = await node.execute_async()

        assert result["merged_data"] == [(1, "x"), (2, "y"), (3, "z")]

    @pytest.mark.asyncio
    async def test_async_merge_dict(self):
        """Test async dictionary merge."""
        node = AsyncMergeNode(
            data1={"x": 1, "y": 2}, data2={"z": 3, "w": 4}, merge_type="merge_dict"
        )

        result = await node.execute_async()

        assert result["merged_data"] == {"x": 1, "y": 2, "z": 3, "w": 4}

    @pytest.mark.asyncio
    async def test_async_large_dataset(self):
        """Test async merge with large dataset."""
        # Create large lists to test chunking
        large_list1 = list(range(1500))
        large_list2 = list(range(1500, 3000))

        node = AsyncMergeNode(
            data1=large_list1, data2=large_list2, merge_type="concat", chunk_size=1000
        )

        result = await node.execute_async()

        assert len(result["merged_data"]) == 3000
        assert result["merged_data"][:10] == list(range(10))
        assert result["merged_data"][-10:] == list(range(2990, 3000))

    @pytest.mark.asyncio
    async def test_async_with_none_values(self):
        """Test async merge with None values."""
        node = AsyncMergeNode(
            data1=[1, 2, 3],
            data2=None,
            data3=[4, 5, 6],
            merge_type="concat",
            skip_none=True,
        )

        result = await node.execute_async()

        assert result["merged_data"] == [1, 2, 3, 4, 5, 6]


class TestLogicNodeValidation:
    """Test validation and error handling."""

    def test_switch_missing_input_data(self):
        """Test Switch node with missing input data."""
        node = SwitchNode(condition_field="status", operator="==", value="success")

        with pytest.raises(
            NodeExecutionError, match="Required parameter 'input_data' not provided"
        ):
            node.execute()

    def test_merge_missing_data1(self):
        """Test Merge node with missing required data1."""
        node = MergeNode(merge_type="concat")

        # Merge node doesn't require data1 in constructor, only at execution time
        # It should return None merged_data when no valid inputs
        result = node.execute()
        assert result["merged_data"] is None

    def test_merge_invalid_dict_merge(self):
        """Test invalid merge_dict without proper inputs."""
        node = MergeNode(
            data1="not_a_dict", data2="also_not_a_dict", merge_type="merge_dict"
        )

        with pytest.raises(NodeExecutionError, match="merge_dict requires dict inputs"):
            node.execute()

    def test_switch_invalid_operator(self):
        """Test Switch with invalid operator."""
        node = SwitchNode(
            input_data={"value": 100},
            condition_field="value",
            operator="invalid_op",
            value=50,
        )

        result = node.execute()

        # Should handle gracefully and return false
        assert result["condition_result"] is False

    @pytest.mark.asyncio
    async def test_async_switch_missing_input(self):
        """Test AsyncSwitch with missing input data."""
        node = AsyncSwitchNode(condition_field="status", operator="==", value="success")

        with pytest.raises(
            NodeExecutionError, match="Required parameter 'input_data' not provided"
        ):
            await node.execute_async()

    @pytest.mark.asyncio
    async def test_async_merge_missing_data(self):
        """Test AsyncMerge with missing data1."""
        node = AsyncMergeNode(merge_type="concat")

        # AsyncMerge handles missing data gracefully and returns None
        result = await node.execute_async()
        assert result == {"merged_data": None}


class TestLogicNodeEdgeCases:
    """Test edge cases and special scenarios."""

    def test_switch_null_checks(self):
        """Test Switch with null check operators."""
        node = SwitchNode(
            input_data={"value": None}, condition_field="value", operator="is_null"
        )

        result = node.execute()

        assert result["condition_result"] is True
        assert result["true_output"] == {"value": None}

    def test_switch_not_null_checks(self):
        """Test Switch with not null check."""
        node = SwitchNode(
            input_data={"value": 42}, condition_field="value", operator="is_not_null"
        )

        result = node.execute()

        assert result["condition_result"] is True
        assert result["true_output"] == {"value": 42}

    def test_merge_dict_overlapping_keys(self):
        """Test merge_dict with overlapping keys."""
        node = MergeNode(
            data1={"a": 1, "b": 2},
            data2={"b": 3, "c": 4},  # 'b' overlaps
            merge_type="merge_dict",
        )

        result = node.execute()

        # Later values should override earlier ones
        assert result["merged_data"]["b"] == 3
        assert result["merged_data"]["a"] == 1
        assert result["merged_data"]["c"] == 4

    def test_switch_empty_cases(self):
        """Test Switch with empty cases list."""
        node = SwitchNode(
            input_data={"status": "success"},
            condition_field="status",
            operator="==",
            value="success",
            cases=[],  # Empty cases - should use boolean mode
        )

        result = node.execute()

        # Should fall back to boolean mode
        assert result["true_output"] == {"status": "success"}
        assert result["condition_result"] is True

    def test_merge_empty_lists(self):
        """Test merging empty lists."""
        node = MergeNode(data1=[], data2=[], merge_type="concat")

        result = node.execute()

        assert result["merged_data"] == []

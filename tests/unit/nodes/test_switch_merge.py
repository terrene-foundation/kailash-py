"""Tests for Switch and enhanced Merge nodes."""

import pytest
from kailash.nodes.logic.operations import MergeNode, SwitchNode


class TestSwitchNode:
    """Test Switch node for conditional branching."""

    def test_boolean_condition_true(self):
        """Test boolean condition with true result."""
        node = SwitchNode()

        result = node.execute(
            input_data={"status": "success"},
            condition_field="status",
            operator="==",
            value="success",
        )

        assert "true_output" in result
        assert result["true_output"]["status"] == "success"
        assert result["false_output"] is None
        assert result["condition_result"] is True

    def test_boolean_condition_false(self):
        """Test boolean condition with false result."""
        node = SwitchNode()

        result = node.execute(
            input_data={"status": "error"},
            condition_field="status",
            operator="==",
            value="success",
        )

        assert result["true_output"] is None
        assert result["false_output"]["status"] == "error"
        assert result["condition_result"] is False

    def test_numeric_comparison(self):
        """Test numeric comparison operators."""
        node = SwitchNode()

        # Greater than
        result = node.execute(
            input_data={"value": 20}, condition_field="value", operator=">", value=10
        )
        assert result["true_output"] is not None
        assert result["false_output"] is None

        # Less than
        result = node.execute(
            input_data={"value": 5}, condition_field="value", operator="<", value=10
        )
        assert result["true_output"] is not None
        assert result["false_output"] is None

        # Equal
        result = node.execute(
            input_data={"value": 10}, condition_field="value", operator="==", value=10
        )
        assert result["true_output"] is not None
        assert result["false_output"] is None

    def test_direct_value_condition(self):
        """Test condition on direct input value (not a field)."""
        node = SwitchNode()

        result = node.execute(input_data="success", operator="==", value="success")

        assert result["true_output"] == "success"
        assert result["false_output"] is None

    def test_contains_operator(self):
        """Test contains operator."""
        node = SwitchNode()

        # String contains
        result = node.execute(
            input_data={"message": "Hello world"},
            condition_field="message",
            operator="contains",
            value="world",
        )
        assert result["true_output"] is not None

        # List contains
        result = node.execute(input_data=[1, 2, 3, 4], operator="contains", value=3)
        assert result["true_output"] is not None

        # Not contains
        result = node.execute(input_data=[1, 2, 3, 4], operator="contains", value=5)
        assert result["true_output"] is None
        assert result["false_output"] is not None

    def test_null_conditions(self):
        """Test null/not null conditions."""
        node = SwitchNode()

        # Is null
        result = node.execute(
            input_data={"optional_field": None},
            condition_field="optional_field",
            operator="is_null",
        )
        assert result["true_output"] is not None

        # Is not null
        result = node.execute(
            input_data={"required_field": "value"},
            condition_field="required_field",
            operator="is_not_null",
        )
        assert result["true_output"] is not None

    def test_invalid_operator(self):
        """Test with invalid operator."""
        node = SwitchNode()

        # This should not raise an exception but log an error and return false
        result = node.execute(
            input_data={"value": 10},
            condition_field="value",
            operator="invalid_op",
            value=10,
        )
        assert result["true_output"] is None
        assert result["false_output"] is not None
        assert result["condition_result"] is False

    def test_exception_in_evaluation(self):
        """Test handling exceptions during condition evaluation."""
        node = SwitchNode()

        # Should handle gracefully when a field doesn't exist
        result = node.execute(
            input_data={"status": "error"},
            condition_field="non_existent_field",  # This field doesn't exist
            operator="==",
            value="success",
        )
        assert result["true_output"] is None
        assert result["false_output"] is not None

    def test_multi_case_switching(self):
        """Test multi-case switching."""
        node = SwitchNode()

        result = node.execute(
            input_data={"status": "warning"},
            condition_field="status",
            cases=["success", "warning", "error"],
        )

        # Should output to case_warning
        assert "case_warning" in result
        assert result["case_warning"]["status"] == "warning"
        assert "default" in result  # Default is always present
        assert result["condition_result"] == "warning"

    def test_multi_case_no_match(self):
        """Test multi-case with no matching case."""
        node = SwitchNode()

        result = node.execute(
            input_data={"status": "unknown"},
            condition_field="status",
            cases=["success", "warning", "error"],
        )

        # Should only have default output
        assert "case_success" not in result
        assert "case_warning" not in result
        assert "case_error" not in result
        assert "default" in result
        assert result["default"]["status"] == "unknown"
        assert result["condition_result"] is None

    def test_case_sanitization(self):
        """Test case name sanitization for special characters."""
        node = SwitchNode()

        result = node.execute(
            input_data={"type": "special:value"},
            condition_field="type",
            cases=["normal", "special:value", "other.type"],
        )

        # Should convert special characters in output field names
        assert "case_special_value" in result
        assert result["case_special_value"]["type"] == "special:value"

    def test_custom_case_prefix(self):
        """Test custom prefix for case output fields."""
        node = SwitchNode()

        result = node.execute(
            input_data={"status": "error"},
            condition_field="status",
            cases=["success", "warning", "error"],
            case_prefix="branch_",
        )

        # Should use custom prefix
        assert "branch_error" in result
        assert "case_error" not in result

    def test_custom_default_field(self):
        """Test custom field name for default case."""
        node = SwitchNode()

        result = node.execute(
            input_data={"status": "unknown"},
            condition_field="status",
            cases=["success", "warning", "error"],
            default_field="unmatched",
        )

        # Should use custom default field name
        assert "unmatched" in result
        assert "default" not in result


class TestMergeNode:
    """Test enhanced Merge node."""

    def test_merge_two_dicts(self):
        """Test merging two dictionaries."""
        node = MergeNode()

        result = node.execute(
            data1={"a": 1, "b": 2}, data2={"c": 3, "d": 4}, merge_type="merge_dict"
        )

        assert result["merged_data"] == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test_merge_with_overlapping_keys(self):
        """Test merging dictionaries with overlapping keys."""
        node = MergeNode()

        result = node.execute(
            data1={"a": 1, "b": 2, "c": 3},
            data2={"c": 30, "d": 4},
            merge_type="merge_dict",
        )

        # Second dict's values should override first
        assert result["merged_data"]["c"] == 30

    def test_merge_multiple_dicts(self):
        """Test merging multiple dictionaries."""
        node = MergeNode()

        result = node.execute(
            data1={"a": 1},
            data2={"b": 2},
            data3={"c": 3},
            data4={"d": 4},
            data5={"e": 5},
            merge_type="merge_dict",
        )

        expected = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        assert result["merged_data"] == expected

    def test_concat_lists(self):
        """Test concatenating lists."""
        node = MergeNode()

        result = node.execute(data1=[1, 2], data2=[3, 4], merge_type="concat")

        assert result["merged_data"] == [1, 2, 3, 4]

    def test_concat_multiple_lists(self):
        """Test concatenating multiple lists."""
        node = MergeNode()

        result = node.execute(
            data1=[1], data2=[2], data3=[3], data4=[4], merge_type="concat"
        )

        assert result["merged_data"] == [1, 2, 3, 4]

    def test_concat_non_lists(self):
        """Test concatenating non-list items."""
        node = MergeNode()

        result = node.execute(data1="Hello", data2="World", merge_type="concat")

        # Non-lists should be treated as single items
        assert result["merged_data"] == ["Hello", "World"]

    def test_zip_lists(self):
        """Test zipping lists."""
        node = MergeNode()

        result = node.execute(data1=[1, 2, 3], data2=["a", "b", "c"], merge_type="zip")

        assert result["merged_data"] == [(1, "a"), (2, "b"), (3, "c")]

    def test_zip_multiple_lists(self):
        """Test zipping multiple lists."""
        node = MergeNode()

        result = node.execute(
            data1=[1, 2], data2=["a", "b"], data3=[True, False], merge_type="zip"
        )

        assert result["merged_data"] == [(1, "a", True), (2, "b", False)]

    def test_zip_with_non_list(self):
        """Test zipping with non-list items."""
        node = MergeNode()

        result = node.execute(data1=[1, 2, 3], data2="x", merge_type="zip")

        # Non-lists should be treated as single-item lists
        assert result["merged_data"] == [(1, "x")]

    def test_merge_list_of_dicts_by_key(self):
        """Test merging lists of dicts by key."""
        node = MergeNode()

        data1 = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        data2 = [{"id": 1, "age": 30}, {"id": 3, "name": "Charlie", "age": 25}]

        result = node.execute(
            data1=data1, data2=data2, merge_type="merge_dict", key="id"
        )

        # Should merge items with same id, and include items with unique ids

        # Check each item is present (order may vary)
        assert len(result["merged_data"]) == 3

        # Check merged content by id
        result_by_id = {item["id"]: item for item in result["merged_data"]}
        assert result_by_id[1] == {"id": 1, "name": "Alice", "age": 30}
        assert result_by_id[2] == {"id": 2, "name": "Bob"}
        assert result_by_id[3] == {"id": 3, "name": "Charlie", "age": 25}

    def test_merge_multiple_list_of_dicts_by_key(self):
        """Test merging multiple lists of dicts by key."""
        node = MergeNode()

        data1 = [{"id": 1, "name": "Alice"}]
        data2 = [{"id": 1, "age": 30}]
        data3 = [{"id": 1, "email": "alice@example.com"}]

        result = node.execute(
            data1=data1, data2=data2, data3=data3, merge_type="merge_dict", key="id"
        )

        # Should merge all three dicts with id=1
        expected = [{"id": 1, "name": "Alice", "age": 30, "email": "alice@example.com"}]
        assert result["merged_data"][0] == expected[0]

    def test_skip_none_values(self):
        """Test skipping None values during merge."""
        node = MergeNode()

        result = node.execute(
            data1={"a": 1},
            data2=None,
            data3={"b": 2},
            merge_type="merge_dict",
            skip_none=True,
        )

        assert result["merged_data"] == {"a": 1, "b": 2}

    def test_with_all_none_values(self):
        """Test merging with all None values."""
        node = MergeNode()

        result = node.execute(data1=None, data2=None, skip_none=True)

        assert result["merged_data"] is None

    def test_single_input(self):
        """Test with only one input."""
        node = MergeNode()

        result = node.execute(data1={"single": "value"}, data2=None, skip_none=True)

        # Should just return the single input
        assert result["merged_data"] == {"single": "value"}

    def test_unknown_merge_type(self):
        """Test with unknown merge type."""
        node = MergeNode()

        with pytest.raises(ValueError):
            node.execute(data1=[1, 2], data2=[3, 4], merge_type="unknown_type")

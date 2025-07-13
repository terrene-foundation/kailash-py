"""Unit tests for DataFlow AggregateNode functionality.

These tests ensure that AggregateNode correctly parses and applies
natural language aggregation expressions for various mathematical operations.
"""

import os
import sys

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../apps/kailash-dataflow/src")
)

from dataflow.nodes.aggregate_operations import AggregateNode


class TestAggregateNode:
    """Test AggregateNode natural language aggregation operations."""

    def setup_method(self):
        """Set up test data for each test."""
        self.node = AggregateNode()

        # Sample sales data
        self.sales_data = [
            {
                "id": 1,
                "amount": 250.00,
                "category": "electronics",
                "region": "north",
                "quantity": 2,
            },
            {
                "id": 2,
                "amount": 150.00,
                "category": "books",
                "region": "south",
                "quantity": 3,
            },
            {
                "id": 3,
                "amount": 500.00,
                "category": "electronics",
                "region": "north",
                "quantity": 1,
            },
            {
                "id": 4,
                "amount": 75.00,
                "category": "books",
                "region": "east",
                "quantity": 5,
            },
            {
                "id": 5,
                "amount": 300.00,
                "category": "clothing",
                "region": "south",
                "quantity": 2,
            },
            {
                "id": 6,
                "amount": 450.00,
                "category": "electronics",
                "region": "west",
                "quantity": 1,
            },
            {
                "id": 7,
                "amount": 200.00,
                "category": "clothing",
                "region": "north",
                "quantity": 4,
            },
            {
                "id": 8,
                "amount": 125.00,
                "category": "books",
                "region": "west",
                "quantity": 2,
            },
        ]

    def test_simple_sum_aggregation(self):
        """Test simple sum aggregation without grouping."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="sum of amount"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "sum"
        assert result["field"] == "amount"
        assert result["result"] == 2050.00  # Sum of all amounts

    def test_simple_average_aggregation(self):
        """Test simple average aggregation."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="average of amount"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "average"
        assert result["field"] == "amount"
        assert result["result"] == 256.25  # 2050 / 8

    def test_simple_count_aggregation(self):
        """Test simple count aggregation."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="count of amount"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "count"
        assert result["result"] == 8  # Total records

    def test_min_max_aggregation(self):
        """Test minimum and maximum aggregations."""
        result_min = self.node.execute(
            data=self.sales_data, aggregate_expression="minimum of amount"
        )

        result_max = self.node.execute(
            data=self.sales_data, aggregate_expression="maximum of amount"
        )

        assert result_min["parsed_successfully"] is True
        assert result_min["aggregation_function"] == "min"
        assert result_min["result"] == 75.00

        assert result_max["parsed_successfully"] is True
        assert result_max["aggregation_function"] == "max"
        assert result_max["result"] == 500.00

    def test_median_mode_aggregation(self):
        """Test median and mode aggregations."""
        result_median = self.node.execute(
            data=self.sales_data, aggregate_expression="median of amount"
        )

        result_mode = self.node.execute(
            data=self.sales_data, aggregate_expression="mode of quantity"
        )

        assert result_median["parsed_successfully"] is True
        assert result_median["aggregation_function"] == "median"
        # Median of [75, 125, 150, 200, 250, 300, 450, 500] = (200 + 250) / 2 = 225
        assert result_median["result"] == 225.0

        assert result_mode["parsed_successfully"] is True
        assert result_mode["aggregation_function"] == "mode"

    def test_grouped_aggregation_single_field(self):
        """Test aggregation with single field grouping."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="sum of amount by category"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "sum"
        assert result["field"] == "amount"
        assert result["group_by"] == ["category"]

        # Verify grouped results
        grouped_result = result["result"]
        assert isinstance(grouped_result, dict)

        # Electronics: 250 + 500 + 450 = 1200
        assert grouped_result["electronics"]["value"] == 1200.00
        # Books: 150 + 75 + 125 = 350
        assert grouped_result["books"]["value"] == 350.00
        # Clothing: 300 + 200 = 500
        assert grouped_result["clothing"]["value"] == 500.00

    def test_grouped_aggregation_multiple_fields(self):
        """Test aggregation with multiple field grouping."""
        result = self.node.execute(
            data=self.sales_data,
            aggregate_expression="average of amount by category, region",
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "average"
        assert "category" in result["group_by"]
        assert "region" in result["group_by"]

        grouped_result = result["result"]
        assert isinstance(grouped_result, dict)
        assert len(grouped_result) > 0

    def test_alternative_expression_formats(self):
        """Test alternative ways to express aggregations."""
        # Test "total" instead of "sum"
        result_total = self.node.execute(
            data=self.sales_data, aggregate_expression="total amount"
        )

        # Test "avg" instead of "average"
        result_avg = self.node.execute(
            data=self.sales_data, aggregate_expression="avg of amount"
        )

        # Test "number of" instead of "count"
        result_number = self.node.execute(
            data=self.sales_data, aggregate_expression="number of records"
        )

        assert result_total["aggregation_function"] == "sum"
        assert result_avg["aggregation_function"] == "average"
        assert result_number["aggregation_function"] == "count"

    def test_auto_field_detection(self):
        """Test automatic numeric field detection."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="sum"  # No field specified
        )

        assert result["parsed_successfully"] is True
        # Should auto-detect a numeric field (likely 'amount')
        assert result["field"] in ["amount", "quantity", "id"]

    def test_explicit_field_specification(self):
        """Test explicit numeric field specification."""
        result = self.node.execute(
            data=self.sales_data,
            aggregate_expression="sum of quantity",
            numeric_fields=["quantity", "amount"],
        )

        assert result["parsed_successfully"] is True
        assert result["field"] == "quantity"

    def test_filtering_with_aggregation(self):
        """Test aggregation with filtering."""
        result = self.node.execute(
            data=self.sales_data,
            aggregate_expression="sum of amount",
            filter_expression="where category is electronics",
        )

        assert result["parsed_successfully"] is True
        assert result["filtered_records"] == 3  # 3 electronics records
        # Electronics sum: 250 + 500 + 450 = 1200
        assert result["result"] == 1200.00

    def test_statistical_aggregations(self):
        """Test statistical aggregation functions."""
        result_std = self.node.execute(
            data=self.sales_data, aggregate_expression="standard deviation of amount"
        )

        result_var = self.node.execute(
            data=self.sales_data, aggregate_expression="variance of amount"
        )

        assert result_std["parsed_successfully"] is True
        assert result_std["aggregation_function"] == "std"
        assert result_std["result"] > 0  # Should have some standard deviation

        assert result_var["parsed_successfully"] is True
        assert result_var["aggregation_function"] == "variance"
        assert result_var["result"] > 0  # Should have some variance

    def test_empty_data_handling(self):
        """Test handling of empty dataset."""
        result = self.node.execute(data=[], aggregate_expression="sum of amount")

        assert result["result"] is None
        assert result["total_records"] == 0
        assert result["parsed_successfully"] is True

    def test_invalid_field_handling(self):
        """Test handling of invalid field names."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="sum of nonexistent_field"
        )

        assert result["parsed_successfully"] is True
        assert result["field"] == "nonexistent_field"
        # Should return None or 0 for non-existent field
        assert result["result"] in [None, 0]

    def test_non_numeric_field_aggregation(self):
        """Test aggregation on non-numeric fields."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="count of category"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "count"
        assert result["result"] == 8  # Should count all non-null values

    def test_mixed_data_types(self):
        """Test aggregation with mixed data types."""
        mixed_data = [
            {"value": 100, "text": "a"},
            {"value": "200", "text": "b"},  # String number
            {"value": 300.5, "text": "c"},
            {"value": None, "text": "d"},  # Null value
            {"value": "invalid", "text": "e"},  # Non-numeric string
        ]

        result = self.node.execute(data=mixed_data, aggregate_expression="sum of value")

        assert result["parsed_successfully"] is True
        # Should sum convertible values: 100 + 200 + 300.5 = 600.5
        assert result["result"] == 600.5

    def test_return_details_option(self):
        """Test detailed return information."""
        result = self.node.execute(
            data=self.sales_data,
            aggregate_expression="sum of amount by category",
            return_details=True,
        )

        assert result["parsed_successfully"] is True
        assert "details" in result
        assert result["details"] is not None
        assert "detected_function" in result["details"]
        assert "detected_field" in result["details"]

    def test_node_parameters_definition(self):
        """Test that node parameters are properly defined."""
        params = self.node.get_parameters()

        # Verify required parameters
        assert "data" in params
        assert "aggregate_expression" in params
        assert params["data"].required is True
        assert params["aggregate_expression"].required is True

        # Verify optional parameters
        assert "group_by" in params
        assert "filter_expression" in params
        assert "numeric_fields" in params
        assert "return_details" in params

    def test_complex_expressions(self):
        """Test parsing of complex aggregation expressions."""
        # Test with extra words
        result = self.node.execute(
            data=self.sales_data,
            aggregate_expression="calculate the sum of amount for all records",
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "sum"

    def test_case_insensitive_parsing(self):
        """Test case insensitive expression parsing."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="SUM OF AMOUNT BY CATEGORY"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "sum"
        assert result["field"] == "amount"

    def test_grouped_count_aggregation(self):
        """Test count aggregation with grouping."""
        result = self.node.execute(
            data=self.sales_data, aggregate_expression="count by category"
        )

        assert result["parsed_successfully"] is True
        assert result["aggregation_function"] == "count"

        grouped_result = result["result"]
        # Electronics: 3 records, Books: 3 records, Clothing: 2 records
        assert grouped_result["electronics"]["count"] == 3
        assert grouped_result["books"]["count"] == 3
        assert grouped_result["clothing"]["count"] == 2

    def test_error_handling(self):
        """Test error handling for invalid expressions."""
        result = self.node.execute(
            data=self.sales_data,
            aggregate_expression="invalid complex expression that cannot be parsed at all",
        )

        # Should handle gracefully with fallback behavior
        assert "error" in result or result["parsed_successfully"] is True

    def test_multiple_group_by_formats(self):
        """Test different formats for group by expressions."""
        # Comma-separated groups
        result1 = self.node.execute(
            data=self.sales_data,
            aggregate_expression="sum of amount by category, region",
        )

        # Explicit group_by parameter
        result2 = self.node.execute(
            data=self.sales_data,
            aggregate_expression="sum of amount",
            group_by=["category", "region"],
        )

        assert result1["parsed_successfully"] is True
        assert result2["parsed_successfully"] is True
        assert len(result1["group_by"]) >= 2
        assert len(result2["group_by"]) == 2

    def test_numerical_precision(self):
        """Test numerical precision in calculations."""
        precise_data = [{"value": 1.11}, {"value": 2.22}, {"value": 3.33}]

        result = self.node.execute(
            data=precise_data, aggregate_expression="sum of value"
        )

        assert result["parsed_successfully"] is True
        # Should handle floating point precision correctly
        expected_sum = 1.11 + 2.22 + 3.33
        assert abs(result["result"] - expected_sum) < 0.001

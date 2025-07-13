"""Unit tests for DataFlow NaturalLanguageFilterNode functionality.

These tests ensure that NaturalLanguageFilterNode correctly parses and applies
natural language filter expressions for date/time and numeric filtering.
"""

import os
import sys
from datetime import date, datetime, timedelta

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../apps/kailash-dataflow/src")
)

from dataflow.nodes.natural_language_filter import NaturalLanguageFilterNode


class TestNaturalLanguageFilterNode:
    """Test NaturalLanguageFilterNode natural language filtering."""

    def setup_method(self):
        """Set up test data for each test."""
        self.node = NaturalLanguageFilterNode()

        # Sample data with various field types
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        self.sample_data = [
            {
                "id": 1,
                "name": "Alice Johnson",
                "amount": 250.50,
                "status": "active",
                "created_at": today.isoformat(),
                "category": "premium",
            },
            {
                "id": 2,
                "name": "Bob Smith",
                "amount": 150.00,
                "status": "pending",
                "created_at": yesterday.isoformat(),
                "category": "standard",
            },
            {
                "id": 3,
                "name": "Charlie Brown",
                "amount": 500.75,
                "status": "active",
                "created_at": last_week.isoformat(),
                "category": "premium",
            },
            {
                "id": 4,
                "name": "Diana Prince",
                "amount": 75.25,
                "status": "inactive",
                "created_at": (today - timedelta(days=30)).isoformat(),
                "category": "basic",
            },
        ]

    def test_date_filtering_today(self):
        """Test filtering for 'today' records."""
        result = self.node.execute(data=self.sample_data, filter_expression="today")

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1
        assert len(result["filtered_data"]) == 1
        assert result["filtered_data"][0]["name"] == "Alice Johnson"

    def test_date_filtering_yesterday(self):
        """Test filtering for 'yesterday' records."""
        result = self.node.execute(data=self.sample_data, filter_expression="yesterday")

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1
        assert len(result["filtered_data"]) == 1
        assert result["filtered_data"][0]["name"] == "Bob Smith"

    def test_date_filtering_last_week(self):
        """Test filtering for 'last week' records."""
        result = self.node.execute(data=self.sample_data, filter_expression="last week")

        assert result["parsed_successfully"] is True
        # Should include records from 7 days ago
        assert result["matches"] >= 1

    def test_date_filtering_last_30_days(self):
        """Test filtering for 'last 30 days' records."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="last 30 days"
        )

        assert result["parsed_successfully"] is True
        # Should include all records within 30 days
        assert result["matches"] == 4

    def test_numeric_filtering_greater_than(self):
        """Test numeric filtering with 'greater than' expression."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="greater than 200"
        )

        assert result["parsed_successfully"] is True
        # Should include Alice (250.50) and Charlie (500.75)
        assert result["matches"] == 2
        amounts = [record["amount"] for record in result["filtered_data"]]
        assert all(amount > 200 for amount in amounts)

    def test_numeric_filtering_less_than(self):
        """Test numeric filtering with 'less than' expression."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="less than 100"
        )

        assert result["parsed_successfully"] is True
        # Should include Diana (75.25)
        assert result["matches"] == 1
        assert result["filtered_data"][0]["name"] == "Diana Prince"

    def test_numeric_filtering_above_below(self):
        """Test numeric filtering with 'above' and 'below' expressions."""
        result_above = self.node.execute(
            data=self.sample_data, filter_expression="above 150"
        )

        result_below = self.node.execute(
            data=self.sample_data, filter_expression="below 150"
        )

        assert result_above["parsed_successfully"] is True
        assert result_below["parsed_successfully"] is True

        # Above 150: Alice (250.50), Charlie (500.75)
        assert result_above["matches"] == 2

        # Below 150: Diana (75.25)
        assert result_below["matches"] == 1

    def test_string_filtering_contains(self):
        """Test string filtering with 'contains' expression."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="contains Johnson"
        )

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1
        assert result["filtered_data"][0]["name"] == "Alice Johnson"

    def test_string_filtering_starts_with(self):
        """Test string filtering with 'starts with' expression."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="starts with Alice"
        )

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1
        assert result["filtered_data"][0]["name"] == "Alice Johnson"

    def test_string_filtering_ends_with(self):
        """Test string filtering with 'ends with' expression."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="ends with Smith"
        )

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1
        assert result["filtered_data"][0]["name"] == "Bob Smith"

    def test_compound_filtering_and(self):
        """Test compound filtering with AND logic."""
        result = self.node.execute(
            data=self.sample_data,
            filter_expression="greater than 100 and contains premium",
        )

        assert result["parsed_successfully"] is True
        # Should include Alice and Charlie (both > 100 and premium category)
        assert result["matches"] == 2
        for record in result["filtered_data"]:
            assert record["amount"] > 100
            assert record["category"] == "premium"

    def test_compound_filtering_or(self):
        """Test compound filtering with OR logic."""
        result = self.node.execute(
            data=self.sample_data,
            filter_expression="contains Alice or contains Charlie",
        )

        assert result["parsed_successfully"] is True
        assert result["matches"] == 2
        names = [record["name"] for record in result["filtered_data"]]
        assert "Alice Johnson" in names
        assert "Charlie Brown" in names

    def test_case_sensitive_filtering(self):
        """Test case sensitive vs case insensitive filtering."""
        # Case insensitive (default)
        result_insensitive = self.node.execute(
            data=self.sample_data,
            filter_expression="contains ALICE",
            case_sensitive=False,
        )

        # Case sensitive
        result_sensitive = self.node.execute(
            data=self.sample_data,
            filter_expression="contains ALICE",
            case_sensitive=True,
        )

        assert result_insensitive["matches"] == 1  # Should find Alice
        assert result_sensitive["matches"] == 0  # Should not find ALICE

    def test_auto_field_detection(self):
        """Test automatic date and numeric field detection."""
        result = self.node.execute(data=self.sample_data, filter_expression="today")

        # Should auto-detect 'created_at' as date field
        assert result["date_field"] == "created_at"
        # Should auto-detect 'amount' as numeric field
        assert result["numeric_field"] == "amount"

    def test_explicit_field_specification(self):
        """Test explicit date and numeric field specification."""
        result = self.node.execute(
            data=self.sample_data,
            filter_expression="today",
            date_field="created_at",
            numeric_field="id",
        )

        assert result["date_field"] == "created_at"
        assert result["numeric_field"] == "id"

    def test_reference_date_specification(self):
        """Test custom reference date for relative calculations."""
        custom_date = "2024-01-15"

        result = self.node.execute(
            data=self.sample_data, filter_expression="today", reference_date=custom_date
        )

        assert result["reference_date"] == "2024-01-15T00:00:00"

    def test_empty_data_handling(self):
        """Test handling of empty dataset."""
        result = self.node.execute(data=[], filter_expression="today")

        assert result["filtered_data"] == []
        assert result["matches"] == 0
        assert result["total_records"] == 0

    def test_invalid_expression_handling(self):
        """Test handling of invalid filter expressions."""
        result = self.node.execute(
            data=self.sample_data,
            filter_expression="invalid complex expression that cannot be parsed",
        )

        # Should return unfiltered data and error information
        assert result["parsed_successfully"] is False
        assert "error" in result
        assert result["matches"] == len(self.sample_data)  # Unfiltered

    def test_node_parameters_definition(self):
        """Test that node parameters are properly defined."""
        params = self.node.get_parameters()

        # Verify required parameters
        assert "data" in params
        assert "filter_expression" in params
        assert params["data"].required is True
        assert params["filter_expression"].required is True

        # Verify optional parameters
        assert "date_field" in params
        assert "numeric_field" in params
        assert "reference_date" in params
        assert "case_sensitive" in params
        assert params["case_sensitive"].default is False

    def test_complex_date_ranges(self):
        """Test complex date range expressions."""
        # Create data spanning multiple months
        base_date = datetime(2024, 6, 15).date()
        test_data = [
            {"id": 1, "created_at": base_date.isoformat()},
            {"id": 2, "created_at": (base_date - timedelta(days=30)).isoformat()},
            {"id": 3, "created_at": (base_date - timedelta(days=7)).isoformat()},
        ]

        # Test this month
        result = self.node.execute(
            data=test_data,
            filter_expression="this month",
            reference_date=base_date.isoformat(),
        )

        assert result["parsed_successfully"] is True

    def test_relative_date_expressions(self):
        """Test relative date expressions like '7 days ago'."""
        result = self.node.execute(
            data=self.sample_data, filter_expression="7 days ago"
        )

        assert result["parsed_successfully"] is True

    def test_numeric_range_expressions(self):
        """Test numeric range expressions."""
        # Test 'at least' and 'at most'
        result_at_least = self.node.execute(
            data=self.sample_data, filter_expression="at least 150"
        )

        result_at_most = self.node.execute(
            data=self.sample_data, filter_expression="at most 150"
        )

        assert result_at_least["parsed_successfully"] is True
        assert result_at_most["parsed_successfully"] is True

        # At least 150: Bob (150), Alice (250.50), Charlie (500.75)
        assert result_at_least["matches"] == 3

        # At most 150: Bob (150), Diana (75.25)
        assert result_at_most["matches"] == 2

    def test_multiple_field_search(self):
        """Test search across multiple fields."""
        result = self.node.execute(
            data=self.sample_data,
            filter_expression="active",  # Should match status or other fields
        )

        assert result["parsed_successfully"] is True
        # Should find records with "active" in any field
        assert result["matches"] >= 2

    def test_datetime_object_handling(self):
        """Test handling of datetime objects in data."""
        # Data with datetime objects instead of strings
        datetime_data = [
            {
                "id": 1,
                "name": "Test User",
                "created_at": datetime.now(),
                "amount": 100.0,
            }
        ]

        result = self.node.execute(data=datetime_data, filter_expression="today")

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1

    def test_mixed_data_types(self):
        """Test handling of mixed data types in records."""
        mixed_data = [
            {"id": 1, "value": 100, "flag": True, "text": "hello"},
            {"id": 2, "value": "200", "flag": False, "text": "world"},
            {"id": 3, "value": None, "flag": True, "text": None},
        ]

        result = self.node.execute(data=mixed_data, filter_expression="contains hello")

        assert result["parsed_successfully"] is True
        assert result["matches"] == 1

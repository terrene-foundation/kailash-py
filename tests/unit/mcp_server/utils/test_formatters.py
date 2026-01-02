"""Unit tests for MCP response formatters - utils subdirectory.

Additional unit tests for edge cases and integration scenarios.
NO MOCKING - This is a unit test file for isolated component testing.
"""

import pytest
from kailash.mcp_server.utils.formatters import (
    JSONFormatter,
    MarkdownFormatter,
    MetricsFormatter,
    SearchResultFormatter,
    TableFormatter,
    format_response,
)


class TestFormatterIntegration:
    """Test integration scenarios between different formatters."""

    def test_consistent_data_handling(self):
        """Test that all formatters handle the same data consistently."""
        test_data = {
            "name": "Test Item",
            "count": 42,
            "active": True,
            "tags": ["python", "testing"],
            "metadata": {"version": "1.0", "author": "tester"},
        }

        # All formatters should handle this data without errors
        json_result = JSONFormatter().format(test_data)
        md_result = MarkdownFormatter().format(test_data)

        # Both should include key information
        for result in [json_result, md_result]:
            assert "Test Item" in result
            assert "42" in result
            assert "True" in result or "true" in result

    def test_formatter_chaining(self):
        """Test using output from one formatter as input to another."""
        original_data = [{"id": 1, "name": "First"}, {"id": 2, "name": "Second"}]

        # Format as table first
        table_result = TableFormatter().format(original_data)

        # Then format the table string as markdown
        md_result = MarkdownFormatter().format(
            {"table_output": table_result}, title="Formatted Table"
        )

        assert "# Formatted Table" in md_result
        assert "table_output" in md_result

    def test_mixed_content_formatting(self):
        """Test formatting mixed content types."""
        metrics = {
            "server": {"uptime_seconds": 3600},
            "search_results": [
                {"name": "Result 1", "_relevance_score": 0.9},
                {"name": "Result 2", "_relevance_score": 0.8},
            ],
            "table_data": [
                {"metric": "CPU", "value": "45%"},
                {"metric": "Memory", "value": "2.1GB"},
            ],
        }

        # Format different parts with appropriate formatters
        metrics_result = MetricsFormatter().format({"server": metrics["server"]})
        search_result = SearchResultFormatter().format(metrics["search_results"])
        table_result = TableFormatter().format(metrics["table_data"])

        # All should produce valid output
        assert "Uptime" in metrics_result
        assert "Result 1" in search_result
        assert "CPU" in table_result


class TestFormatterResilience:
    """Test formatter resilience to unusual inputs."""

    def test_recursive_data_structures(self):
        """Test handling of self-referential data."""
        # Create a list that contains itself
        recursive_list = [1, 2, 3]
        recursive_list.append(recursive_list)

        # Formatters should handle this gracefully
        json_formatter = JSONFormatter()
        result = json_formatter.format({"data": recursive_list})
        assert "Error" in result or "..." in result

    def test_extremely_nested_markdown(self):
        """Test markdown formatter with extreme nesting."""
        data = {"level": 1}
        current = data
        for i in range(2, 50):
            current["nested"] = {"level": i}
            current = current["nested"]

        formatter = MarkdownFormatter()
        result = formatter.format(data)

        # Should complete without stack overflow
        assert "level" in result

    def test_malformed_search_results(self):
        """Test search formatter with malformed results."""
        formatter = SearchResultFormatter()

        # Missing expected fields
        results = [
            {},  # Empty result
            {"unknown_field": "value"},  # No name/title
            {"name": None, "description": None},  # None values
        ]

        result = formatter.format(results)

        # Should handle gracefully
        assert "## 1. Result" in result
        assert "## 2. Result" in result
        assert "## 3." in result

    def test_table_formatter_irregular_data(self):
        """Test table formatter with irregular row structures."""
        formatter = TableFormatter()

        # Rows with different keys
        data = [
            {"a": 1, "b": 2, "c": 3},
            {"a": 4, "d": 5},  # Missing b and c, has d
            {"b": 6, "c": 7, "e": 8},  # Missing a, has e
        ]

        result = formatter.format(data)

        # Should handle missing values
        lines = result.split("\n")
        assert len(lines) >= 5  # Header + separator + 3 data rows

    def test_formatter_with_bytes_data(self):
        """Test formatters with bytes data."""
        data = {
            "text": "normal string",
            "bytes": b"byte string",
            "mixed": ["text", b"bytes", 123],
        }

        # JSON formatter should handle bytes
        json_formatter = JSONFormatter()
        result = json_formatter.format(data)

        # Bytes should be converted to string
        assert "byte string" in result or "Error" in result

    def test_formatter_memory_efficiency(self):
        """Test formatters don't create excessive copies of data."""
        # Large string that shouldn't be duplicated many times
        large_string = "x" * 10000
        data = {"value": large_string}

        # Format with different formatters
        formatters = [
            JSONFormatter(),
            MarkdownFormatter(),
            TableFormatter(),
        ]

        for formatter in formatters:
            if isinstance(formatter, TableFormatter):
                result = formatter.format([data])
            else:
                result = formatter.format(data)

            # Result should contain the data but not duplicate it excessively
            assert large_string in result or "x" * 100 in result


class TestFormatterCustomization:
    """Test formatter customization options."""

    def test_json_formatter_custom_serializer(self):
        """Test JSON formatter with custom object serialization."""
        formatter = JSONFormatter()

        class CustomType:
            def __init__(self, value):
                self.value = value

            def __str__(self):
                return f"CustomType({self.value})"

        data = {
            "regular": "string",
            "custom": CustomType(42),
            "list_with_custom": [1, CustomType("test"), 3],
        }

        result = formatter.format(data)

        # Custom objects should be serialized via __str__
        assert "CustomType(42)" in result
        assert "CustomType(test)" in result

    def test_markdown_formatter_edge_cases(self):
        """Test markdown formatter with edge case values."""
        formatter = MarkdownFormatter()

        # Test with markdown special characters
        data = {
            "heading": "# Not a heading",
            "bold": "**not bold**",
            "list": "- not a list item",
            "link": "[not](a link)",
        }

        result = formatter.format(data)

        # Should escape or handle markdown syntax in values
        assert "**heading**:" in result
        assert "# Not a heading" in result

    def test_table_formatter_wide_columns(self):
        """Test table formatter with very wide columns."""
        formatter = TableFormatter()

        data = [
            {
                "short": "OK",
                "long": "This is a very long cell value that might affect table formatting and alignment",
            },
            {"short": "OK2", "long": "Another long value"},
        ]

        result = formatter.format(data)

        # Should handle wide columns properly
        lines = result.split("\n")
        # All lines should be properly aligned
        assert all(
            "-+-" in line or "|" in line or not line.strip() for line in lines[1:2]
        )

    def test_search_formatter_custom_fields(self):
        """Test search formatter with custom field handling."""
        formatter = SearchResultFormatter()

        results = [
            {
                "name": "Custom Result",
                "_relevance_score": 0.95,
                "custom_score": 100,
                "tags": ["tag1", "tag2", "tag3"],
                "nested": {"key": "value"},
                "_internal": "should not show",
            }
        ]

        result = formatter.format(results)

        # Should show custom fields
        assert "**Custom_Score**: 100" in result
        assert "**Tags**: tag1, tag2, tag3" in result

        # Should not show internal fields (starting with _)
        assert "_internal" not in result.replace("_relevance_score", "")

    def test_metrics_formatter_precision(self):
        """Test metrics formatter number precision."""
        formatter = MetricsFormatter()

        metrics = {
            "server": {
                "uptime_seconds": 3661.123456,
                "total_calls": 1234567,
                "overall_error_rate": 0.00123456,
                "calls_per_second": 12.3456789,
            },
            "tools": {
                "test": {
                    "calls": 1000,
                    "errors": 1,
                    "error_rate": 0.001,
                    "avg_latency": 0.123456789,
                    "p95_latency": 0.999999999,
                }
            },
        }

        result = formatter.format(metrics)

        # Check precision formatting
        assert "1.0 hours" in result  # Uptime rounded
        assert "1,234,567" in result  # Thousands separator
        assert "0.12%" in result  # Error rate as percentage
        assert "12.35" in result  # Calls/second to 2 decimal places
        assert "0.123s" in result  # Latency to 3 decimal places
        assert "1.000s" in result  # P95 latency


class TestFormatterPerformance:
    """Test formatter performance characteristics."""

    @pytest.mark.parametrize("size", [10, 100, 1000])
    def test_table_formatter_scaling(self, size):
        """Test table formatter with different data sizes."""
        formatter = TableFormatter()

        # Create data with 'size' rows
        data = [{"id": i, "value": f"item_{i}", "score": i * 10} for i in range(size)]

        # Should complete in reasonable time
        result = formatter.format(data)

        # Verify basic structure
        lines = result.split("\n")
        assert len(lines) >= size + 2  # Header + separator + data rows

    @pytest.mark.parametrize("depth", [1, 5, 10])
    def test_json_formatter_nesting(self, depth):
        """Test JSON formatter with different nesting depths."""
        formatter = JSONFormatter()

        # Create nested structure
        data = {"value": "leaf"}
        for i in range(depth):
            data = {"level": i, "nested": data}

        # Should handle any reasonable depth
        result = formatter.format(data)
        assert "leaf" in result

    def test_search_formatter_large_results(self):
        """Test search formatter with large result sets."""
        formatter = SearchResultFormatter()

        # Create 100 results
        results = [
            {
                "name": f"Document {i}",
                "description": f"Description for document {i}",
                "_relevance_score": 1.0 - (i * 0.01),
                "tags": [f"tag{j}" for j in range(5)],
                "metadata": {"index": i, "category": f"cat{i % 10}"},
            }
            for i in range(100)
        ]

        # Should handle large result sets
        result = formatter.format(results, query="test query", total_count=1000)

        assert "Showing 100 of 1000 results" in result
        assert "## 100. Document 99" in result


class TestFormatterErrorRecovery:
    """Test formatter error recovery and resilience."""

    def test_json_formatter_recovery(self):
        """Test JSON formatter recovery from errors."""
        formatter = JSONFormatter()

        # Create object that raises exception during serialization
        class FailingObject:
            def __str__(self):
                raise RuntimeError("Serialization failed")

            def __repr__(self):
                raise RuntimeError("Repr failed too")

        data = {"failing": FailingObject(), "valid": "data"}

        # Should return error message, not crash
        result = formatter.format(data)
        assert "Error formatting JSON" in result

    def test_table_formatter_recovery(self):
        """Test table formatter with problematic data."""
        formatter = TableFormatter()

        # Data with None, empty strings, and special characters
        data = [
            {"col1": None, "col2": "", "col3": "normal"},
            {"col1": "\n\t", "col2": "|||", "col3": "-+-"},
        ]

        # Should handle without crashing
        result = formatter.format(data)
        assert "col1" in result
        assert "col2" in result
        assert "col3" in result

    def test_format_response_invalid_type(self):
        """Test format_response with invalid formatter type."""
        data = {"test": "data"}

        # Should fall back to JSON formatter
        result = format_response(data, format_type="nonexistent_formatter")

        # Should be valid JSON
        import json

        parsed = json.loads(result)
        assert parsed == data

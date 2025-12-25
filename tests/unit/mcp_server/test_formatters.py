"""Unit tests for MCP response formatters.

Tests for the formatting utilities in kailash.mcp_server.utils.formatters.
NO MOCKING - This is a unit test file for isolated component testing.
"""

import json
from datetime import datetime

import pytest
from kailash.mcp_server.utils.formatters import (
    JSONFormatter,
    MarkdownFormatter,
    MetricsFormatter,
    ResponseFormatter,
    SearchResultFormatter,
    TableFormatter,
    format_response,
    json_formatter,
    markdown_formatter,
    metrics_formatter,
    search_formatter,
    table_formatter,
)


class TestResponseFormatter:
    """Test base ResponseFormatter class."""

    def test_abstract_format_method(self):
        """Test that base formatter raises NotImplementedError."""
        formatter = ResponseFormatter()

        with pytest.raises(NotImplementedError):
            formatter.format("test data")


class TestJSONFormatter:
    """Test JSON formatting functionality."""

    def test_init_with_defaults(self):
        """Test JSONFormatter initialization with default values."""
        formatter = JSONFormatter()
        assert formatter.indent == 2
        assert formatter.ensure_ascii is False

    def test_init_with_custom_values(self):
        """Test JSONFormatter initialization with custom values."""
        formatter = JSONFormatter(indent=4, ensure_ascii=True)
        assert formatter.indent == 4
        assert formatter.ensure_ascii is True

    def test_format_simple_dict(self):
        """Test formatting a simple dictionary."""
        formatter = JSONFormatter()
        data = {"name": "test", "value": 42}
        result = formatter.format(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

        # Should be pretty-printed
        assert "\n" in result
        assert "  " in result  # Default 2-space indent

    def test_format_nested_data(self):
        """Test formatting nested data structures."""
        formatter = JSONFormatter()
        data = {
            "user": {
                "name": "John",
                "scores": [85, 90, 95],
                "metadata": {"level": 5, "active": True},
            }
        }
        result = formatter.format(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

    def test_format_list(self):
        """Test formatting a list."""
        formatter = JSONFormatter()
        data = ["item1", "item2", "item3"]
        result = formatter.format(data)

        parsed = json.loads(result)
        assert parsed == data

    def test_format_with_datetime(self):
        """Test formatting data containing datetime objects."""
        formatter = JSONFormatter()
        now = datetime.now()
        data = {"timestamp": now, "event": "test"}

        result = formatter.format(data)
        parsed = json.loads(result)

        # Datetime should be converted to ISO format
        assert parsed["timestamp"] == now.isoformat()
        assert parsed["event"] == "test"

    def test_format_with_non_serializable_object(self):
        """Test formatting data with custom non-serializable objects."""
        formatter = JSONFormatter()

        class CustomObject:
            def __str__(self):
                return "custom_object_string"

        data = {"obj": CustomObject(), "value": 123}
        result = formatter.format(data)

        parsed = json.loads(result)
        assert parsed["obj"] == "custom_object_string"
        assert parsed["value"] == 123

    def test_format_error_handling(self):
        """Test error handling during formatting."""
        formatter = JSONFormatter()

        # Create an object that will cause JSON encoding to fail
        class BadObject:
            def __str__(self):
                raise Exception("Cannot convert to string")

        # Even with error, should return error message
        data = {"bad": BadObject()}
        result = formatter.format(data)

        assert "Error formatting JSON" in result

    def test_format_with_ensure_ascii(self):
        """Test formatting with ensure_ascii option."""
        formatter_ascii = JSONFormatter(ensure_ascii=True)
        formatter_unicode = JSONFormatter(ensure_ascii=False)

        data = {"text": "Hello 世界"}

        result_ascii = formatter_ascii.format(data)
        result_unicode = formatter_unicode.format(data)

        # ASCII version should escape unicode
        assert "\\u" in result_ascii
        # Unicode version should keep original characters
        assert "世界" in result_unicode


class TestMarkdownFormatter:
    """Test Markdown formatting functionality."""

    def test_format_simple_dict(self):
        """Test formatting a simple dictionary as Markdown."""
        formatter = MarkdownFormatter()
        data = {"name": "Test Item", "value": 42, "active": True}

        result = formatter.format(data)

        assert "**name**: Test Item" in result
        assert "**value**: 42" in result
        assert "**active**: True" in result

    def test_format_dict_with_title(self):
        """Test formatting dictionary with title."""
        formatter = MarkdownFormatter()
        data = {"key1": "value1", "key2": "value2"}

        result = formatter.format(data, title="Test Title")

        assert "# Test Title" in result
        assert "**key1**: value1" in result
        assert "**key2**: value2" in result

    def test_format_simple_list(self):
        """Test formatting a simple list."""
        formatter = MarkdownFormatter()
        data = ["item1", "item2", "item3"]

        result = formatter.format(data)

        assert "1. item1" in result
        assert "2. item2" in result
        assert "3. item3" in result

    def test_format_list_of_dicts(self):
        """Test formatting a list of dictionaries."""
        formatter = MarkdownFormatter()
        data = [{"name": "Alice", "score": 95}, {"name": "Bob", "score": 87}]

        result = formatter.format(data)

        assert "## 1. Item" in result
        assert "- **name**: Alice" in result
        assert "- **score**: 95" in result
        assert "## 2. Item" in result
        assert "- **name**: Bob" in result
        assert "- **score**: 87" in result

    def test_format_list_with_title(self):
        """Test formatting list with title."""
        formatter = MarkdownFormatter()
        data = ["first", "second", "third"]

        result = formatter.format(data, title="My List")

        assert "# My List" in result
        assert "1. first" in result

    def test_format_simple_value(self):
        """Test formatting a simple value."""
        formatter = MarkdownFormatter()

        # String
        result = formatter.format("Hello World")
        assert "Hello World" in result

        # Number
        result = formatter.format(42)
        assert "42" in result

        # Boolean
        result = formatter.format(True)
        assert "True" in result

    def test_format_simple_value_with_title(self):
        """Test formatting simple value with title."""
        formatter = MarkdownFormatter()
        result = formatter.format("test content", title="Document")

        assert "# Document" in result
        assert "test content" in result

    def test_format_value_with_small_lists(self):
        """Test _format_value with small lists."""
        formatter = MarkdownFormatter()

        # Small list (<=5 items)
        value = formatter._format_value([1, 2, 3, 4, 5])
        assert value == "1, 2, 3, 4, 5"

        # Large list (>5 items)
        value = formatter._format_value([1, 2, 3, 4, 5, 6])
        assert value == "[1, 2, 3, 4, 5, 6]"

    def test_format_value_with_small_dicts(self):
        """Test _format_value with small dictionaries."""
        formatter = MarkdownFormatter()

        # Small dict (<=3 items)
        value = formatter._format_value({"a": 1, "b": 2, "c": 3})
        assert value == "a: 1, b: 2, c: 3"

        # Large dict (>3 items)
        value = formatter._format_value({"a": 1, "b": 2, "c": 3, "d": 4})
        assert value == "{'a': 1, 'b': 2, 'c': 3, 'd': 4}"

    def test_format_value_with_tuples(self):
        """Test _format_value with tuples."""
        formatter = MarkdownFormatter()

        # Small tuple
        value = formatter._format_value((1, 2, 3))
        assert value == "1, 2, 3"


class TestTableFormatter:
    """Test table formatting functionality."""

    def test_format_simple_table(self):
        """Test formatting a simple table."""
        formatter = TableFormatter()
        data = [
            {"name": "Alice", "age": 30, "city": "NYC"},
            {"name": "Bob", "age": 25, "city": "LA"},
        ]

        result = formatter.format(data)

        # Check header row
        assert "name" in result
        assert "age" in result
        assert "city" in result

        # Check separator line
        assert "---" in result
        assert "-+-" in result

        # Check data rows
        assert "Alice" in result
        assert "30" in result
        assert "NYC" in result
        assert "Bob" in result
        assert "25" in result
        assert "LA" in result

    def test_format_with_custom_headers(self):
        """Test formatting with custom headers."""
        formatter = TableFormatter()
        data = [
            {"name": "Alice", "age": 30, "city": "NYC", "extra": "data"},
            {"name": "Bob", "age": 25, "city": "LA", "extra": "more"},
        ]

        # Only show specific headers
        result = formatter.format(data, headers=["name", "city"])

        assert "name" in result
        assert "city" in result
        assert "age" not in result
        assert "extra" not in result

    def test_format_empty_data(self):
        """Test formatting empty data."""
        formatter = TableFormatter()

        result = formatter.format([])
        assert result == "No data available"

    def test_format_invalid_data(self):
        """Test formatting invalid data types."""
        formatter = TableFormatter()

        # Not a list
        result = formatter.format("not a list")
        assert "Data must be a list of dictionaries" in result

        # List of non-dicts
        result = formatter.format(["item1", "item2"])
        assert "Data must be a list of dictionaries" in result

    def test_format_with_missing_values(self):
        """Test formatting with missing values in some rows."""
        formatter = TableFormatter()
        data = [
            {"name": "Alice", "age": 30, "city": "NYC"},
            {"name": "Bob", "city": "LA"},  # Missing age
            {"name": "Charlie", "age": 35},  # Missing city
        ]

        result = formatter.format(data)

        # Should handle missing values gracefully
        lines = result.split("\n")
        assert len(lines) == 5  # Header + separator + 3 data rows

    def test_column_width_calculation(self):
        """Test proper column width calculation."""
        formatter = TableFormatter()
        data = [
            {"short": "a", "medium": "hello", "long": "this is a long value"},
            {"short": "bb", "medium": "world!", "long": "x"},
        ]

        result = formatter.format(data)
        lines = result.split("\n")

        # All lines should have consistent width
        header_len = len(lines[0])
        for line in lines[2:]:  # Skip separator
            # Account for potential trailing spaces
            assert len(line.rstrip()) <= header_len

    def test_format_with_various_types(self):
        """Test formatting with various data types."""
        formatter = TableFormatter()
        data = [
            {"string": "text", "int": 42, "float": 3.14, "bool": True},
            {"string": "more", "int": 100, "float": 2.71, "bool": False},
        ]

        result = formatter.format(data)

        assert "text" in result
        assert "42" in result
        assert "3.14" in result
        assert "True" in result
        assert "False" in result


class TestSearchResultFormatter:
    """Test search result formatting functionality."""

    def test_format_basic_results(self):
        """Test formatting basic search results."""
        formatter = SearchResultFormatter()
        results = [
            {"name": "Document 1", "description": "First document"},
            {"title": "Document 2", "description": "Second document"},
        ]

        result = formatter.format(results)

        assert "# Search Results" in result
        assert "Found 2 results" in result
        assert "## 1. Document 1" in result
        assert "First document" in result
        assert "## 2. Document 2" in result
        assert "Second document" in result

    def test_format_with_query(self):
        """Test formatting with search query."""
        formatter = SearchResultFormatter()
        results = [{"name": "Test Result"}]

        result = formatter.format(results, query="test query")

        assert "# Search Results for: 'test query'" in result

    def test_format_with_total_count(self):
        """Test formatting with total count greater than results."""
        formatter = SearchResultFormatter()
        results = [{"name": "Result 1"}, {"name": "Result 2"}]

        result = formatter.format(results, total_count=10)

        assert "Showing 2 of 10 results" in result

    def test_format_with_relevance_scores(self):
        """Test formatting results with relevance scores."""
        formatter = SearchResultFormatter()
        results = [
            {"name": "Doc 1", "_relevance_score": 0.95},
            {"name": "Doc 2", "_relevance_score": 0.82},
        ]

        result = formatter.format(results)

        assert "**Relevance**: 0.95" in result
        assert "**Relevance**: 0.82" in result

    def test_format_with_additional_fields(self):
        """Test formatting with various additional fields."""
        formatter = SearchResultFormatter()
        results = [
            {
                "name": "Test Document",
                "description": "A test document",
                "tags": ["python", "testing"],
                "author": "John Doe",
                "created": "2023-01-01",
                "_relevance_score": 0.9,
                "empty_list": [],
                "empty_string": "",
            }
        ]

        result = formatter.format(results)

        # Should include non-empty fields
        assert "**Tags**: python, testing" in result
        assert "**Author**: John Doe" in result
        assert "**Created**: 2023-01-01" in result

        # Should not include empty fields
        assert "empty_list" not in result
        assert "empty_string" not in result

        # Should not duplicate standard fields
        result_lines = result.split("\n")
        name_count = sum(1 for line in result_lines if "Test Document" in line)
        assert name_count == 1  # Only in header

    def test_format_empty_results(self):
        """Test formatting empty search results."""
        formatter = SearchResultFormatter()

        result = formatter.format([])

        assert "Found 0 results" in result

    def test_format_result_without_name_or_title(self):
        """Test formatting result without name or title field."""
        formatter = SearchResultFormatter()
        results = [{"description": "Anonymous result", "type": "unknown"}]

        result = formatter.format(results)

        assert "## 1. Result" in result
        assert "Anonymous result" in result


class TestMetricsFormatter:
    """Test metrics formatting functionality."""

    def test_format_server_metrics(self):
        """Test formatting server metrics."""
        formatter = MetricsFormatter()
        metrics = {
            "server": {
                "uptime_seconds": 3661.5,
                "total_calls": 1000000,
                "total_errors": 50,
                "overall_error_rate": 0.005,
                "calls_per_second": 12.5,
            }
        }

        result = formatter.format(metrics)

        assert "# Server Metrics" in result
        assert "## Server Statistics" in result
        assert "**Uptime**: 1.0 hours" in result
        assert "**Total Calls**: 1,000,000" in result
        assert "**Total Errors**: 50" in result
        assert "**Error Rate**: 0.50%" in result
        assert "**Calls/Second**: 12.50" in result

    def test_format_tool_metrics(self):
        """Test formatting tool metrics."""
        formatter = MetricsFormatter()
        metrics = {
            "tools": {
                "search": {
                    "calls": 5000,
                    "errors": 10,
                    "error_rate": 0.002,
                    "avg_latency": 0.125,
                    "p95_latency": 0.250,
                },
                "fetch": {"calls": 3000, "errors": 5, "error_rate": 0.00167},
            }
        }

        result = formatter.format(metrics)

        assert "## Tool Statistics" in result
        assert "### search" in result
        assert "**Calls**: 5,000" in result
        assert "**Errors**: 10" in result
        assert "**Error Rate**: 0.20%" in result
        assert "**Avg Latency**: 0.125s" in result
        assert "**P95 Latency**: 0.250s" in result

        assert "### fetch" in result
        assert "**Calls**: 3,000" in result

    def test_format_complete_metrics(self):
        """Test formatting complete metrics with both server and tools."""
        formatter = MetricsFormatter()
        metrics = {
            "server": {
                "uptime_seconds": 86400,
                "total_calls": 50000,
                "total_errors": 100,
                "overall_error_rate": 0.002,
                "calls_per_second": 0.58,
            },
            "tools": {"tool1": {"calls": 1000, "errors": 5, "error_rate": 0.005}},
        }

        result = formatter.format(metrics)

        assert "# Server Metrics" in result
        assert "## Server Statistics" in result
        assert "## Tool Statistics" in result

    def test_format_empty_metrics(self):
        """Test formatting empty metrics."""
        formatter = MetricsFormatter()

        result = formatter.format({})
        assert "# Server Metrics" in result

        # Should handle missing sections gracefully
        result = formatter.format({"server": {}})
        assert "## Server Statistics" in result

    def test_format_duration_various_scales(self):
        """Test _format_duration with various time scales."""
        formatter = MetricsFormatter()

        # Seconds
        assert formatter._format_duration(30) == "30.0 seconds"
        assert formatter._format_duration(59.9) == "59.9 seconds"

        # Minutes
        assert formatter._format_duration(60) == "1.0 minutes"
        assert formatter._format_duration(150) == "2.5 minutes"
        assert formatter._format_duration(3599) == "60.0 minutes"

        # Hours
        assert formatter._format_duration(3600) == "1.0 hours"
        assert formatter._format_duration(7200) == "2.0 hours"
        assert formatter._format_duration(86399) == "24.0 hours"

        # Days
        assert formatter._format_duration(86400) == "1.0 days"
        assert formatter._format_duration(172800) == "2.0 days"

    def test_format_metrics_without_optional_fields(self):
        """Test formatting metrics without optional fields."""
        formatter = MetricsFormatter()
        metrics = {
            "tools": {
                "basic_tool": {
                    "calls": 100,
                    "errors": 0,
                    "error_rate": 0.0,
                    # No latency metrics
                }
            }
        }

        result = formatter.format(metrics)

        assert "### basic_tool" in result
        assert "**Calls**: 100" in result
        assert "Latency" not in result


class TestFormatResponseFunction:
    """Test the format_response convenience function."""

    def test_format_response_json(self):
        """Test format_response with JSON format."""
        data = {"test": "data"}
        result = format_response(data, format_type="json")

        assert json.loads(result) == data

    def test_format_response_markdown(self):
        """Test format_response with Markdown format."""
        data = {"title": "Test", "content": "Data"}
        result = format_response(data, format_type="markdown")

        assert "**title**: Test" in result
        assert "**content**: Data" in result

    def test_format_response_table(self):
        """Test format_response with table format."""
        data = [{"col1": "a", "col2": "b"}]
        result = format_response(data, format_type="table")

        assert "col1" in result
        assert "col2" in result
        assert "-+-" in result

    def test_format_response_search(self):
        """Test format_response with search format."""
        data = [{"name": "Result"}]
        result = format_response(data, format_type="search", query="test")

        assert "Search Results for: 'test'" in result

    def test_format_response_metrics(self):
        """Test format_response with metrics format."""
        data = {"server": {"uptime_seconds": 100}}
        result = format_response(data, format_type="metrics")

        assert "Server Metrics" in result

    def test_format_response_default(self):
        """Test format_response with unknown format defaults to JSON."""
        data = {"test": "data"}
        result = format_response(data, format_type="unknown")

        # Should default to JSON
        assert json.loads(result) == data

    def test_format_response_with_kwargs(self):
        """Test format_response passes kwargs to formatter."""
        data = {"test": "data"}
        result = format_response(data, format_type="markdown", title="Custom Title")

        assert "# Custom Title" in result


class TestDefaultFormatterInstances:
    """Test the default formatter instances."""

    def test_default_instances_exist(self):
        """Test that default formatter instances are available."""
        assert isinstance(json_formatter, JSONFormatter)
        assert isinstance(markdown_formatter, MarkdownFormatter)
        assert isinstance(table_formatter, TableFormatter)
        assert isinstance(search_formatter, SearchResultFormatter)
        assert isinstance(metrics_formatter, MetricsFormatter)

    def test_default_instances_work(self):
        """Test that default instances can format data."""
        data = {"test": "data"}

        # All should produce output without errors
        assert json_formatter.format(data)
        assert markdown_formatter.format(data)
        assert table_formatter.format([data])
        assert search_formatter.format([data])
        assert metrics_formatter.format(data)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_format_none_values(self):
        """Test formatting None values."""
        # JSON
        assert json_formatter.format(None) == "null"

        # Markdown
        result = markdown_formatter.format(None)
        assert "None" in result

        # Table with None values
        data = [{"a": None, "b": "value"}]
        result = table_formatter.format(data)
        assert "None" in result

    def test_format_empty_strings(self):
        """Test formatting empty strings."""
        # JSON
        assert json_formatter.format("") == '""'

        # Markdown
        result = markdown_formatter.format("")
        assert result == ""

    def test_format_special_characters(self):
        """Test formatting with special characters."""
        data = {"text": "Line1\nLine2\tTab", "symbols": "<>&\"'"}

        # JSON should escape properly
        json_result = json_formatter.format(data)
        parsed = json.loads(json_result)
        assert parsed == data

        # Markdown should preserve characters
        md_result = markdown_formatter.format(data)
        assert "Line1\nLine2\tTab" in md_result

    def test_format_very_long_values(self):
        """Test formatting with very long values."""
        long_string = "x" * 1000
        data = {"long": long_string}

        # All formatters should handle long strings
        assert json_formatter.format(data)
        assert markdown_formatter.format(data)
        assert table_formatter.format([data])

    def test_format_circular_references(self):
        """Test handling of circular references."""
        # Create circular reference
        data = {"a": 1}
        data["self"] = data

        # JSON formatter should handle gracefully
        result = json_formatter.format(data)
        assert "Error formatting JSON" in result

    def test_format_deeply_nested_data(self):
        """Test formatting deeply nested data structures."""
        data = {"level1": {"level2": {"level3": {"level4": {"value": "deep"}}}}}

        # Should handle deep nesting
        json_result = json_formatter.format(data)
        assert "deep" in json_result

        md_result = markdown_formatter.format(data)
        # Check that the nested structure is represented in some form
        assert "level1" in md_result
        assert "level2" in md_result or "level3" in md_result or "deep" in md_result

    def test_unicode_handling(self):
        """Test proper Unicode handling."""
        data = {
            "english": "Hello",
            "chinese": "你好",
            "emoji": "👋",
            "mixed": "Hello 世界 🌍",
        }

        # All formatters should handle Unicode
        for formatter in [json_formatter, markdown_formatter]:
            result = formatter.format(data)
            assert "你好" in result or "\\u" in result  # Either preserved or escaped
            assert "👋" in result or "\\u" in result

    def test_performance_large_datasets(self):
        """Test performance with large datasets doesn't hang."""
        # Create large dataset
        large_data = [{"id": i, "value": f"item_{i}"} for i in range(1000)]

        # Should complete without hanging
        result = table_formatter.format(large_data[:10])  # Limit for table
        assert "id" in result

        result = search_formatter.format(large_data[:50])  # Reasonable search results
        assert "Found 50 results" in result

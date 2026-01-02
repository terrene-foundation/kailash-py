"""Unit tests for LogProcessorNode.

Tests basic log processing functionality with proper .execute() usage.
Follows 3-tier testing policy: no Docker dependencies, isolated testing.
"""

from datetime import UTC, datetime

import pytest
from kailash.nodes.monitoring.log_processor import (
    AggregationType,
    LogFormat,
    LogLevel,
    LogProcessorNode,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestLogProcessorNode:
    """Test cases for LogProcessorNode - Tier 1 Unit Tests."""

    @pytest.fixture
    def log_processor(self):
        """Create a LogProcessorNode instance for testing."""
        return LogProcessorNode()

    @pytest.fixture
    def sample_logs(self):
        """Sample log entries for testing."""
        return [
            "2024-01-01 10:00:00 ERROR Failed to connect to database",
            "2024-01-01 10:00:01 INFO User logged in successfully",
            "2024-01-01 10:00:02 WARNING High memory usage detected",
            "2024-01-01 10:00:03 DEBUG Processing request",
            "2024-01-01 10:00:04 CRITICAL System failure detected",
        ]

    @pytest.fixture
    def json_logs(self):
        """Sample JSON log entries for testing."""
        return [
            '{"timestamp": "2024-01-01T10:00:00Z", "level": "ERROR", "message": "Database connection failed"}',
            '{"timestamp": "2024-01-01T10:00:01Z", "level": "INFO", "message": "User authentication successful"}',
            '{"timestamp": "2024-01-01T10:00:02Z", "level": "WARNING", "message": "Memory usage at 85%"}',
        ]

    def test_initialization(self, log_processor):
        """Test LogProcessorNode initialization."""
        assert log_processor.id is not None
        assert hasattr(log_processor, "compiled_patterns")
        assert hasattr(log_processor, "aggregation_buffer")
        assert hasattr(log_processor, "last_aggregation_time")

    def test_get_parameters(self, log_processor):
        """Test parameter definitions."""
        params = log_processor.get_parameters()

        assert "logs" in params
        assert params["logs"].required is True
        assert "log_format" in params
        assert params["log_format"].default == "auto"
        assert "filters" in params
        assert "patterns" in params
        assert "aggregation" in params
        assert "output_format" in params
        assert "alerts" in params

    def test_get_output_schema(self, log_processor):
        """Test output schema definition."""
        schema = log_processor.get_output_schema()

        expected_outputs = [
            "processed_logs",
            "filtered_count",
            "total_count",
            "patterns_matched",
            "aggregations",
            "alerts_triggered",
            "processing_time",
            "timestamp",
        ]

        for output in expected_outputs:
            assert output in schema

    def test_basic_log_processing(self, log_processor, sample_logs):
        """Test basic log processing functionality."""
        result = log_processor.execute(
            logs=sample_logs, log_format="auto", output_format="json"
        )

        assert result["success"] is True
        assert result["total_count"] == 5
        assert result["filtered_count"] == 5
        assert len(result["processed_logs"]) == 5
        assert "processing_time" in result
        assert "timestamp" in result

    def test_json_log_processing(self, log_processor, json_logs):
        """Test JSON log format processing."""
        result = log_processor.execute(
            logs=json_logs, log_format="json", output_format="json"
        )

        assert result["success"] is True
        assert result["total_count"] == 3
        assert result["filtered_count"] == 3

        # Check that JSON was properly parsed
        processed_logs = result["processed_logs"]
        assert all(isinstance(log, dict) for log in processed_logs)
        assert all("timestamp" in log for log in processed_logs)
        assert all("level" in log for log in processed_logs)
        assert all("message" in log for log in processed_logs)

    def test_log_filtering_by_level(self, log_processor, sample_logs):
        """Test log filtering by minimum level."""
        result = log_processor.execute(
            logs=sample_logs, filters={"min_level": "WARNING"}, output_format="json"
        )

        assert result["success"] is True
        assert result["total_count"] == 5
        # Should filter to WARNING, ERROR, CRITICAL (3 logs)
        assert result["filtered_count"] == 3

        # Check that filtered logs have correct levels
        processed_logs = result["processed_logs"]
        levels = [log["level"] for log in processed_logs]
        assert all(level in ["WARNING", "ERROR", "CRITICAL"] for level in levels)

    def test_log_filtering_by_content(self, log_processor, sample_logs):
        """Test log filtering by content."""
        result = log_processor.execute(
            logs=sample_logs, filters={"contains": "User"}, output_format="json"
        )

        assert result["success"] is True
        assert result["filtered_count"] == 1
        assert "User logged in successfully" in result["processed_logs"][0]["message"]

    def test_log_filtering_by_exclusion(self, log_processor, sample_logs):
        """Test log filtering by exclusion."""
        result = log_processor.execute(
            logs=sample_logs, filters={"excludes": "DEBUG"}, output_format="json"
        )

        assert result["success"] is True
        assert result["filtered_count"] == 4  # All except DEBUG

    def test_pattern_matching(self, log_processor, sample_logs):
        """Test pattern matching functionality."""
        patterns = [
            {
                "name": "error_pattern",
                "regex": r"ERROR.*database",
                "extract_fields": ["level", "timestamp"],
            },
            {"name": "user_pattern", "regex": r"User.*successfully"},
        ]

        result = log_processor.execute(
            logs=sample_logs, patterns=patterns, output_format="json"
        )

        assert result["success"] is True
        patterns_matched = result["patterns_matched"]

        assert "error_pattern" in patterns_matched
        assert patterns_matched["error_pattern"]["match_count"] == 1

        assert "user_pattern" in patterns_matched
        assert patterns_matched["user_pattern"]["match_count"] == 1

    def test_log_aggregation_count(self, log_processor, sample_logs):
        """Test count aggregation."""
        result = log_processor.execute(
            logs=sample_logs,
            aggregation={"type": "count", "field": "level"},
            output_format="json",
        )

        assert result["success"] is True
        aggregations = result["aggregations"]

        assert "counts" in aggregations
        counts = aggregations["counts"]
        assert counts["ERROR"] == 1
        assert counts["INFO"] == 1
        assert counts["WARNING"] == 1
        assert counts["DEBUG"] == 1
        assert counts["CRITICAL"] == 1

    def test_log_aggregation_unique(self, log_processor, sample_logs):
        """Test unique value aggregation."""
        result = log_processor.execute(
            logs=sample_logs,
            aggregation={"type": "unique", "field": "level"},
            output_format="json",
        )

        assert result["success"] is True
        aggregations = result["aggregations"]

        assert "unique_count" in aggregations
        assert aggregations["unique_count"] == 5  # 5 unique levels
        assert "unique_values" in aggregations
        unique_values = aggregations["unique_values"]
        assert "ERROR" in unique_values
        assert "INFO" in unique_values

    def test_alert_threshold(self, log_processor):
        """Test threshold-based alerts."""
        # Create logs with multiple errors
        error_logs = [
            "2024-01-01 10:00:00 ERROR Database error 1",
            "2024-01-01 10:00:01 ERROR Database error 2",
            "2024-01-01 10:00:02 ERROR Database error 3",
            "2024-01-01 10:00:03 INFO Normal log",
        ]

        alerts = [
            {
                "name": "error_threshold",
                "type": "threshold",
                "field": "level",
                "condition": "ERROR",
                "threshold": 2,
                "severity": "high",
            }
        ]

        result = log_processor.execute(
            logs=error_logs, alerts=alerts, output_format="json"
        )

        assert result["success"] is True
        alerts_triggered = result["alerts_triggered"]

        assert len(alerts_triggered) == 1
        alert = alerts_triggered[0]
        assert alert["name"] == "error_threshold"
        assert alert["actual_count"] == 3
        assert alert["threshold"] == 2

    def test_alert_pattern(self, log_processor, sample_logs):
        """Test pattern-based alerts."""
        patterns = [
            {
                "name": "database_error",
                "regex": r"database",
            }
        ]

        alerts = [
            {
                "name": "db_alert",
                "type": "pattern",
                "pattern_name": "database_error",
                "threshold": 1,
                "severity": "medium",
            }
        ]

        result = log_processor.execute(
            logs=sample_logs, patterns=patterns, alerts=alerts, output_format="json"
        )

        assert result["success"] is True
        alerts_triggered = result["alerts_triggered"]

        assert len(alerts_triggered) == 1
        alert = alerts_triggered[0]
        assert alert["name"] == "db_alert"
        assert alert["pattern_name"] == "database_error"

    def test_log_enrichment(self, log_processor, sample_logs):
        """Test log enrichment functionality."""
        enrichment = {
            "static_fields": {"environment": "test", "service": "api"},
            "computed_fields": {"parsed_timestamp": {"type": "timestamp_parse"}},
        }

        result = log_processor.execute(
            logs=sample_logs, enrichment=enrichment, output_format="json"
        )

        assert result["success"] is True
        processed_logs = result["processed_logs"]

        # Check static fields were added
        for log in processed_logs:
            assert log["environment"] == "test"
            assert log["service"] == "api"
            assert "_processed_at" in log
            assert "_processor_id" in log

    def test_output_formats(self, log_processor, sample_logs):
        """Test different output formats."""
        # Test JSON format
        result_json = log_processor.execute(logs=sample_logs[:2], output_format="json")
        assert isinstance(result_json["processed_logs"], list)
        assert isinstance(result_json["processed_logs"][0], dict)

        # Test structured format
        result_structured = log_processor.execute(
            logs=sample_logs[:2], output_format="structured"
        )
        assert isinstance(result_structured["processed_logs"], list)
        assert isinstance(result_structured["processed_logs"][0], str)

        # Test raw format
        result_raw = log_processor.execute(logs=sample_logs[:2], output_format="raw")
        assert isinstance(result_raw["processed_logs"], list)
        assert isinstance(result_raw["processed_logs"][0], str)

    def test_buffer_size_limit(self, log_processor):
        """Test buffer size limiting."""
        # Create many logs
        many_logs = [
            f"2024-01-01 10:00:{i:02d} INFO Log message {i}" for i in range(50)
        ]

        result = log_processor.execute(
            logs=many_logs, max_buffer_size=10, output_format="json"  # Limit to 10
        )

        assert result["success"] is True
        assert result["total_count"] == 10  # Should be truncated
        assert result["filtered_count"] == 10

    def test_single_string_log(self, log_processor):
        """Test processing a single string log."""
        single_log = "2024-01-01 10:00:00 INFO Single log message"

        result = log_processor.execute(logs=single_log, output_format="json")

        assert result["success"] is True
        assert result["total_count"] == 1
        assert result["filtered_count"] == 1

    def test_invalid_json_fallback(self, log_processor):
        """Test fallback for invalid JSON logs."""
        invalid_json_logs = [
            '{"timestamp": "2024-01-01T10:00:00Z", "level": "INFO"',  # Missing closing brace
            "Not JSON at all",
        ]

        result = log_processor.execute(
            logs=invalid_json_logs, log_format="json", output_format="json"
        )

        assert result["success"] is True
        assert result["total_count"] == 2

        # Should create minimal log entries for invalid JSON
        processed_logs = result["processed_logs"]
        assert all("message" in log for log in processed_logs)
        assert all("timestamp" in log for log in processed_logs)

    def test_regex_pattern_compilation_error(self, log_processor, sample_logs):
        """Test handling of invalid regex patterns."""
        patterns = [
            {
                "name": "invalid_pattern",
                "regex": r"[invalid regex()",  # Invalid regex
            }
        ]

        result = log_processor.execute(
            logs=sample_logs, patterns=patterns, output_format="json"
        )

        # Should still succeed but skip invalid pattern
        assert result["success"] is True
        patterns_matched = result["patterns_matched"]
        assert "invalid_pattern" not in patterns_matched

    def test_time_range_filtering(self, log_processor):
        """Test time range filtering."""
        time_logs = [
            "2024-01-01T09:00:00Z INFO Early log",
            "2024-01-01T10:30:00Z INFO Middle log",
            "2024-01-01T12:00:00Z INFO Late log",
        ]

        result = log_processor.execute(
            logs=time_logs,
            log_format="auto",
            filters={
                "start_time": "2024-01-01T10:00:00Z",
                "end_time": "2024-01-01T11:00:00Z",
            },
            output_format="json",
        )

        assert result["success"] is True
        assert result["filtered_count"] == 1  # Only middle log should pass
        assert "Middle log" in result["processed_logs"][0]["message"]

    def test_error_handling(self, log_processor):
        """Test error handling for invalid inputs."""
        # Test with None logs - should raise NodeExecutionError
        with pytest.raises(NodeExecutionError, match="Failed to process logs"):
            log_processor.execute(logs=None, output_format="json")

    def test_log_level_enum(self):
        """Test LogLevel enum values."""
        assert LogLevel.CRITICAL.value == 50
        assert LogLevel.ERROR.value == 40
        assert LogLevel.WARNING.value == 30
        assert LogLevel.INFO.value == 20
        assert LogLevel.DEBUG.value == 10

    def test_log_format_enum(self):
        """Test LogFormat enum values."""
        assert LogFormat.JSON.value == "json"
        assert LogFormat.STRUCTURED.value == "structured"
        assert LogFormat.RAW.value == "raw"
        assert LogFormat.SYSLOG.value == "syslog"
        assert LogFormat.ELK.value == "elk"

    def test_aggregation_type_enum(self):
        """Test AggregationType enum values."""
        assert AggregationType.COUNT.value == "count"
        assert AggregationType.RATE.value == "rate"
        assert AggregationType.UNIQUE.value == "unique"
        assert AggregationType.TOP_VALUES.value == "top_values"
        assert AggregationType.TIMELINE.value == "timeline"

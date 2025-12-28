"""Integration tests for LogProcessorNode using real services.

Tests log processing functionality with real infrastructure and component interactions.
Follows 3-tier testing policy: uses real Docker services, no mocking.
"""

import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from kailash.nodes.monitoring.log_processor import LogProcessorNode
from kailash.sdk_exceptions import NodeExecutionError

# Mark all tests in this file as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestLogProcessorNodeIntegration:
    """Integration tests for LogProcessorNode with real services."""

    @pytest.fixture(scope="class")
    def log_processor(self):
        """Create a LogProcessorNode instance for testing."""
        return LogProcessorNode()

    @pytest.fixture
    def large_log_dataset(self):
        """Generate a large, realistic log dataset for testing."""
        logs = []
        base_time = datetime.now(UTC)

        # Generate various types of log entries
        log_types = [
            {"level": "INFO", "pattern": "User {user_id} logged in from {ip}"},
            {"level": "ERROR", "pattern": "Database connection failed: {error}"},
            {
                "level": "WARNING",
                "pattern": "High memory usage detected: {percentage}%",
            },
            {"level": "DEBUG", "pattern": "Processing request {request_id}"},
            {"level": "CRITICAL", "pattern": "System failure in module {module}"},
            {
                "level": "INFO",
                "pattern": "API request to {endpoint} completed in {time}ms",
            },
            {"level": "ERROR", "pattern": "Authentication failed for user {user_id}"},
            {"level": "WARNING", "pattern": "Rate limit exceeded for IP {ip}"},
        ]

        for i in range(1000):  # Generate 1000 log entries
            log_type = log_types[i % len(log_types)]
            timestamp = base_time.replace(microsecond=0).isoformat() + "Z"

            # Create varied log data
            if "user_id" in log_type["pattern"]:
                user_id = 1000 + (i % 100)  # 100 different users
                ip = f"192.168.1.{(i % 254) + 1}"
                message = log_type["pattern"].format(user_id=user_id, ip=ip)
            elif "error" in log_type["pattern"]:
                errors = [
                    "Connection timeout",
                    "Invalid credentials",
                    "Network unreachable",
                ]
                error = errors[i % len(errors)]
                message = log_type["pattern"].format(error=error)
            elif "percentage" in log_type["pattern"]:
                percentage = 70 + (i % 30)  # Memory usage 70-99%
                message = log_type["pattern"].format(percentage=percentage)
            elif "request_id" in log_type["pattern"]:
                request_id = f"req_{i:06d}"
                message = log_type["pattern"].format(request_id=request_id)
            elif "module" in log_type["pattern"]:
                modules = ["auth", "database", "cache", "api", "scheduler"]
                module = modules[i % len(modules)]
                message = log_type["pattern"].format(module=module)
            elif "endpoint" in log_type["pattern"]:
                endpoints = ["/api/users", "/api/orders", "/api/products", "/api/auth"]
                endpoint = endpoints[i % len(endpoints)]
                time_ms = 50 + (i % 200)  # Response time 50-249ms
                message = log_type["pattern"].format(endpoint=endpoint, time=time_ms)
            else:
                message = log_type["pattern"]

            # Format as structured log
            log_entry = f"{timestamp} {log_type['level']} {message}"
            logs.append(log_entry)

        return logs

    @pytest.fixture
    def json_log_dataset(self):
        """Generate JSON-formatted log entries."""
        logs = []
        base_time = datetime.now(UTC)

        for i in range(100):
            log_data = {
                "timestamp": base_time.replace(microsecond=0).isoformat() + "Z",
                "level": ["INFO", "ERROR", "WARNING", "DEBUG"][i % 4],
                "message": f"JSON log message {i}",
                "service": "integration-test",
                "request_id": f"req_{i:06d}",
                "user_id": 1000 + (i % 50),
                "metadata": {
                    "source": "integration_test",
                    "environment": "test",
                    "version": "1.0.0",
                },
            }
            logs.append(json.dumps(log_data))

        return logs

    def test_large_log_processing_performance(self, log_processor, large_log_dataset):
        """Test processing large log datasets for performance."""
        start_time = time.time()

        result = log_processor.execute(
            logs=large_log_dataset,
            log_format="auto",
            output_format="json",
            max_buffer_size=2000,  # Allow larger buffer for this test
        )

        processing_time = time.time() - start_time

        assert result["success"] is True
        assert result["total_count"] == 1000
        assert result["filtered_count"] == 1000
        assert len(result["processed_logs"]) == 1000
        assert result["processing_time"] > 0

        # Performance check - should process 1000 logs reasonably quickly
        assert processing_time < 5.0  # Less than 5 seconds

        # Verify log structure
        sample_log = result["processed_logs"][0]
        assert "timestamp" in sample_log
        assert "level" in sample_log
        assert "message" in sample_log

    def test_json_log_batch_processing(self, log_processor, json_log_dataset):
        """Test batch processing of JSON-formatted logs."""
        result = log_processor.execute(
            logs=json_log_dataset, log_format="json", output_format="json"
        )

        assert result["success"] is True
        assert result["total_count"] == 100
        assert result["filtered_count"] == 100

        # Verify JSON parsing worked correctly
        processed_logs = result["processed_logs"]
        for log in processed_logs[:5]:  # Check first 5
            assert "request_id" in log
            assert "user_id" in log
            assert "metadata" in log
            assert isinstance(log["metadata"], dict)

    def test_real_time_log_filtering_and_aggregation(
        self, log_processor, large_log_dataset
    ):
        """Test real-time filtering and aggregation with large dataset."""
        result = log_processor.execute(
            logs=large_log_dataset,
            filters={
                "min_level": "WARNING",  # Only WARNING, ERROR, CRITICAL
                "contains": "failed",  # Only logs containing "failed"
            },
            aggregation={"type": "count", "field": "level"},
            output_format="json",
        )

        assert result["success"] is True
        assert result["total_count"] == 1000
        assert result["filtered_count"] > 0  # Should have some matching logs

        # Check aggregation results
        aggregations = result["aggregations"]
        assert "counts" in aggregations
        counts = aggregations["counts"]

        # Should only have WARNING, ERROR, CRITICAL levels
        for level in counts.keys():
            assert level in ["WARNING", "ERROR", "CRITICAL"]

    def test_pattern_matching_with_large_dataset(
        self, log_processor, large_log_dataset
    ):
        """Test pattern matching capabilities with large dataset."""
        patterns = [
            {
                "name": "database_errors",
                "regex": r"Database.*failed",
                "extract_fields": ["level", "timestamp"],
            },
            {
                "name": "auth_events",
                "regex": r"(login|Authentication)",
                "extract_fields": ["level"],
            },
            {
                "name": "performance_warnings",
                "regex": r"High.*usage.*(\d+)%",
                "extract_fields": ["message"],
            },
        ]

        result = log_processor.execute(
            logs=large_log_dataset, patterns=patterns, output_format="json"
        )

        assert result["success"] is True
        patterns_matched = result["patterns_matched"]

        # Should find matches for each pattern
        assert "database_errors" in patterns_matched
        assert "auth_events" in patterns_matched
        assert "performance_warnings" in patterns_matched

        # Check pattern match details
        for pattern_name, pattern_data in patterns_matched.items():
            assert "match_count" in pattern_data
            assert "matches" in pattern_data
            assert pattern_data["match_count"] > 0

    def test_alerting_system_integration(self, log_processor, large_log_dataset):
        """Test alerting system with realistic thresholds."""
        patterns = [
            {
                "name": "critical_errors",
                "regex": r"CRITICAL.*failure",
            },
            {
                "name": "auth_failures",
                "regex": r"Authentication failed",
            },
        ]

        alerts = [
            {
                "name": "high_error_rate",
                "type": "threshold",
                "field": "level",
                "condition": "ERROR",
                "threshold": 50,  # Alert if more than 50 errors
                "severity": "high",
            },
            {
                "name": "critical_system_alert",
                "type": "pattern",
                "pattern_name": "critical_errors",
                "threshold": 1,  # Alert on any critical error
                "severity": "critical",
            },
            {
                "name": "auth_failure_spike",
                "type": "pattern",
                "pattern_name": "auth_failures",
                "threshold": 10,  # Alert on 10+ auth failures
                "severity": "medium",
            },
        ]

        result = log_processor.execute(
            logs=large_log_dataset,
            patterns=patterns,
            alerts=alerts,
            output_format="json",
        )

        assert result["success"] is True
        alerts_triggered = result["alerts_triggered"]

        # Should trigger some alerts given the large dataset
        assert len(alerts_triggered) > 0

        # Check alert structure
        for alert in alerts_triggered:
            assert "name" in alert
            assert "type" in alert
            assert "triggered_at" in alert
            assert "severity" in alert

    def test_log_enrichment_with_metadata(self, log_processor, json_log_dataset):
        """Test log enrichment functionality."""
        enrichment = {
            "static_fields": {
                "environment": "integration_test",
                "service_version": "2.0.0",
                "cluster": "test-cluster",
            },
            "computed_fields": {
                "parsed_timestamp": {"type": "timestamp_parse"},
                "request_info": {
                    "type": "field_extraction",
                    "source_field": "message",
                    "pattern": r"req_(\d+)",
                },
            },
        }

        result = log_processor.execute(
            logs=json_log_dataset[:10],  # Use smaller subset for enrichment test
            enrichment=enrichment,
            output_format="json",
        )

        assert result["success"] is True
        processed_logs = result["processed_logs"]

        # Verify enrichment was applied
        for log in processed_logs:
            # Static fields
            assert log["environment"] == "integration_test"
            assert log["service_version"] == "2.0.0"
            assert log["cluster"] == "test-cluster"

            # Processing metadata
            assert "_processed_at" in log
            assert "_processor_id" in log

    def test_multiple_output_formats(self, log_processor, large_log_dataset):
        """Test different output formats with large dataset."""
        # Test all supported output formats
        formats = ["json", "structured", "raw", "syslog", "elk"]

        for output_format in formats:
            result = log_processor.execute(
                logs=large_log_dataset[:100],  # Use subset for format testing
                log_format="auto",
                output_format=output_format,
            )

            assert result["success"] is True
            assert result["total_count"] == 100
            assert len(result["processed_logs"]) == 100

            # Verify format-specific structure
            if output_format == "json":
                assert isinstance(result["processed_logs"][0], dict)
            elif output_format in ["structured", "raw", "syslog"]:
                assert isinstance(result["processed_logs"][0], str)
            elif output_format == "elk":
                assert isinstance(result["processed_logs"][0], dict)
                assert "@timestamp" in result["processed_logs"][0]
                assert "@version" in result["processed_logs"][0]

    def test_memory_and_buffer_management(self, log_processor):
        """Test memory management with very large log streams."""
        # Generate very large log stream
        large_stream = []
        for i in range(5000):  # 5000 log entries
            timestamp = datetime.now(UTC).isoformat()
            large_stream.append(f"{timestamp} INFO Large stream test message {i}")

        # Test with buffer size limit
        result = log_processor.execute(
            logs=large_stream,
            max_buffer_size=2000,  # Limit to 2000 entries
            output_format="json",
        )

        assert result["success"] is True
        assert result["total_count"] == 2000  # Should be truncated
        assert result["filtered_count"] == 2000
        assert len(result["processed_logs"]) == 2000

    def test_concurrent_log_processing(self, log_processor, large_log_dataset):
        """Test concurrent processing capabilities."""
        import concurrent.futures
        import threading

        def process_logs_batch(batch_id, logs_batch):
            """Process a batch of logs."""
            return log_processor.execute(
                logs=logs_batch,
                filters={"min_level": "INFO"},
                aggregation={"type": "count", "field": "level"},
                output_format="json",
            )

        # Split large dataset into batches
        batch_size = 200
        batches = [
            large_log_dataset[i : i + batch_size]
            for i in range(0, len(large_log_dataset), batch_size)
        ]

        # Process batches concurrently
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_batch = {
                executor.submit(process_logs_batch, i, batch): i
                for i, batch in enumerate(batches[:3])  # Test with first 3 batches
            }

            for future in concurrent.futures.as_completed(future_to_batch):
                batch_id = future_to_batch[future]
                try:
                    result = future.result()
                    assert result["success"] is True
                    results.append(result)
                except Exception as exc:
                    pytest.fail(f"Batch {batch_id} generated an exception: {exc}")

        assert len(results) == 3

        # Verify each batch was processed correctly
        for result in results:
            assert result["total_count"] == batch_size
            assert result["filtered_count"] <= result["total_count"]

    def test_file_based_log_processing(self, log_processor, large_log_dataset):
        """Test processing logs from file-like sources."""
        # Create temporary log file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as temp_file:
            for log_entry in large_log_dataset[:500]:  # Write subset to file
                temp_file.write(log_entry + "\n")
            temp_file_path = temp_file.name

        try:
            # Read logs from file
            with open(temp_file_path, "r") as file:
                file_logs = [line.strip() for line in file if line.strip()]

            # Process logs from file
            result = log_processor.execute(
                logs=file_logs,
                log_format="auto",
                filters={"min_level": "WARNING"},
                aggregation={"type": "timeline", "interval": 60},
                output_format="json",
            )

            assert result["success"] is True
            assert result["total_count"] == 500
            assert "aggregations" in result
            assert "timeline" in result["aggregations"]

        finally:
            # Cleanup
            os.unlink(temp_file_path)

    def test_error_recovery_and_resilience(self, log_processor):
        """Test error recovery with malformed logs."""
        # Mix of valid and invalid log entries
        mixed_logs = [
            "2024-01-01T10:00:00Z INFO Valid log entry 1",
            "Invalid log entry without timestamp",
            '{"timestamp": "2024-01-01T10:00:01Z", "level": "INFO", "message": "Valid JSON log"}',
            '{"timestamp": "2024-01-01T10:00:02Z", "level": "ERROR"',  # Invalid JSON
            "",  # Empty line
            "2024-01-01T10:00:03Z WARNING Another valid entry",
            None,  # None entry (will be filtered by framework)
        ]

        # Filter out None entries (as the framework would)
        filtered_logs = [log for log in mixed_logs if log is not None]

        result = log_processor.execute(
            logs=filtered_logs, log_format="auto", output_format="json"
        )

        assert result["success"] is True
        assert result["total_count"] == len(filtered_logs)
        assert result["filtered_count"] > 0  # Should process valid entries

        # Verify processor handled malformed entries gracefully
        processed_logs = result["processed_logs"]
        assert len(processed_logs) == len(filtered_logs)

        # All processed logs should have required fields
        for log in processed_logs:
            assert "timestamp" in log
            assert "level" in log
            assert "message" in log

    def test_real_time_metrics_and_monitoring(self, log_processor, large_log_dataset):
        """Test real-time metrics collection and monitoring."""
        # Process logs with comprehensive monitoring
        result = log_processor.execute(
            logs=large_log_dataset,
            filters={"min_level": "INFO"},
            aggregation={"type": "rate"},  # Calculate log rate
            patterns=[
                {
                    "name": "error_patterns",
                    "regex": r"(ERROR|failed|error)",
                },
                {
                    "name": "performance_patterns",
                    "regex": r"(High.*usage|timeout|slow)",
                },
            ],
            alerts=[
                {
                    "name": "processing_time_alert",
                    "type": "rate",
                    "rate_threshold": 100,  # logs per second
                    "time_window": 60,
                    "severity": "medium",
                }
            ],
            output_format="json",
        )

        assert result["success"] is True
        assert "processing_time" in result
        assert "aggregations" in result
        assert "patterns_matched" in result

        # Verify performance metrics
        processing_time = result["processing_time"]
        assert processing_time > 0
        assert processing_time < 10.0  # Should complete within 10 seconds

        # Verify rate aggregation
        if "rate" in result["aggregations"]:
            rate = result["aggregations"]["rate"]
            assert rate >= 0

    def test_integration_with_external_systems(self, log_processor, json_log_dataset):
        """Test integration patterns with external monitoring systems."""
        # Simulate processing for external system integration
        result = log_processor.execute(
            logs=json_log_dataset,
            enrichment={
                "static_fields": {
                    "source_system": "integration_test",
                    "processing_node": "test_node_001",
                    "datacenter": "test_dc",
                }
            },
            output_format="elk",  # ELK format for Elasticsearch integration
            aggregation={"type": "top_values", "field": "level", "top_n": 5},
        )

        assert result["success"] is True

        # Verify ELK format structure
        processed_logs = result["processed_logs"]
        for log in processed_logs[:5]:  # Check first 5
            assert "@timestamp" in log
            assert "@version" in log
            assert "fields" in log
            assert log["fields"]["source_system"] == "integration_test"
            assert log["fields"]["processing_node"] == "test_node_001"

        # Verify aggregation for monitoring dashboards
        aggregations = result["aggregations"]
        assert "top_values" in aggregations
        top_values = aggregations["top_values"]
        assert len(top_values) <= 5

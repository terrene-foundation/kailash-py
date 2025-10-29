"""
Unit tests for validation performance monitoring and metrics collection.

Tests Task 1.5: Performance Monitoring
- ValidationMetricsCollector for tracking performance
- Security violation logging
- Cache statistics
- Performance summaries and reports
"""

import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.runtime.validation.error_categorizer import ErrorCategory
from kailash.runtime.validation.metrics import (
    ValidationEventType,
    ValidationMetric,
    ValidationMetricsCollector,
    get_metrics_collector,
    reset_global_metrics,
)
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow.builder import WorkflowBuilder


class TestValidationMetricsCollector:
    """Test the ValidationMetricsCollector class."""

    def test_metrics_collector_initialization(self):
        """Test basic initialization of metrics collector."""
        collector = ValidationMetricsCollector(enable_detailed_logging=True)

        assert collector.metrics == []
        assert collector.security_violations == []
        assert collector.enable_detailed_logging is True
        assert collector._cache_stats == {"hits": 0, "misses": 0}

    def test_validation_timing_tracking(self):
        """Test tracking validation start and end with timing."""
        collector = ValidationMetricsCollector()

        # Start validation
        collector.start_validation("node1", "TestNode", "strict")

        # Simulate some processing time
        time.sleep(0.01)  # 10ms

        # End validation successfully
        collector.end_validation("node1", "TestNode", success=True)

        # Check metrics
        assert len(collector.metrics) == 2
        assert collector.metrics[0].event_type == ValidationEventType.VALIDATION_STARTED
        assert (
            collector.metrics[1].event_type == ValidationEventType.VALIDATION_COMPLETED
        )
        assert collector.metrics[1].duration_ms is not None
        assert collector.metrics[1].duration_ms >= 10  # At least 10ms

        # Check timing aggregation
        assert "TestNode" in collector.node_validation_times
        assert len(collector.node_validation_times["TestNode"]) == 1

    def test_validation_failure_tracking(self):
        """Test tracking validation failures with error categories."""
        collector = ValidationMetricsCollector()

        # Track a type mismatch failure
        collector.start_validation("node2", "DataNode", "strict")
        collector.end_validation(
            "node2",
            "DataNode",
            success=False,
            error_category=ErrorCategory.TYPE_MISMATCH,
            connection_info={"source": "api", "target": "processor"},
        )

        # Check metrics
        assert len(collector.metrics) == 2
        assert collector.metrics[1].event_type == ValidationEventType.VALIDATION_FAILED
        assert collector.metrics[1].error_category == ErrorCategory.TYPE_MISMATCH
        assert collector.metrics[1].connection_source == "api"
        assert collector.metrics[1].connection_target == "processor"

        # Check error counts
        assert collector.error_counts[ErrorCategory.TYPE_MISMATCH] == 1

    def test_security_violation_tracking(self):
        """Test tracking security violations with detailed logging."""
        collector = ValidationMetricsCollector()

        # Record a security violation
        violation_details = {
            "message": "SQL injection detected",
            "pattern": "DROP TABLE",
            "input": "'; DROP TABLE users; --",
        }

        collector.record_security_violation(
            "sql_node",
            "SQLDatabaseNode",
            violation_details,
            connection_info={"source": "user_input", "target": "database"},
        )

        # Check security violations
        assert len(collector.security_violations) == 1
        violation = collector.security_violations[0]
        assert violation.event_type == ValidationEventType.SECURITY_VIOLATION
        assert violation.node_id == "sql_node"
        assert violation.additional_data == violation_details
        assert collector.error_counts[ErrorCategory.SECURITY_VIOLATION] == 1

    def test_cache_statistics(self):
        """Test cache hit/miss tracking."""
        collector = ValidationMetricsCollector()

        # Record cache operations
        collector.record_cache_hit("CSVReaderNode")
        collector.record_cache_hit("CSVReaderNode")
        collector.record_cache_miss("JSONReaderNode")

        # Check cache stats
        assert collector._cache_stats["hits"] == 2
        assert collector._cache_stats["misses"] == 1

        # Check metrics
        cache_metrics = [
            m
            for m in collector.metrics
            if m.event_type
            in [ValidationEventType.CACHE_HIT, ValidationEventType.CACHE_MISS]
        ]
        assert len(cache_metrics) == 3

    def test_mode_bypass_tracking(self):
        """Test tracking when validation is bypassed due to mode."""
        collector = ValidationMetricsCollector()

        # Record mode bypass
        collector.record_mode_bypass("node3", "ProcessorNode", "off")

        # Check metrics
        assert len(collector.metrics) == 1
        assert collector.metrics[0].event_type == ValidationEventType.MODE_BYPASS
        assert collector.metrics[0].validation_mode == "off"

    def test_performance_summary_generation(self):
        """Test generation of performance summary statistics."""
        collector = ValidationMetricsCollector()

        # Add various metrics
        collector.start_validation("n1", "TypeA", "strict")
        time.sleep(0.005)
        collector.end_validation("n1", "TypeA", success=True)

        collector.start_validation("n2", "TypeA", "strict")
        time.sleep(0.010)
        collector.end_validation("n2", "TypeA", success=True)

        collector.start_validation("n3", "TypeB", "strict")
        collector.end_validation(
            "n3", "TypeB", success=False, error_category=ErrorCategory.MISSING_PARAMETER
        )

        collector.record_cache_hit("TypeA")
        collector.record_cache_miss("TypeA")
        collector.record_mode_bypass("n4", "TypeC", "off")

        # Get summary
        summary = collector.get_performance_summary()

        assert summary["total_validations"] == 3
        assert summary["failed_validations"] == 1
        assert summary["failure_rate"] == pytest.approx(33.33, rel=0.1)
        assert summary["security_violations"] == 0
        assert summary["mode_bypasses"] == 1

        # Check performance by node type
        assert "TypeA" in summary["performance_by_node_type"]
        type_a_perf = summary["performance_by_node_type"]["TypeA"]
        assert type_a_perf["count"] == 2
        assert type_a_perf["min_ms"] >= 5
        assert type_a_perf["max_ms"] >= 10

        # Check cache stats
        assert summary["cache_stats"]["hits"] == 1
        assert summary["cache_stats"]["misses"] == 1
        assert summary["cache_stats"]["hit_rate"] == 50.0

    def test_security_report_generation(self):
        """Test generation of security violation report."""
        collector = ValidationMetricsCollector()

        # Add multiple security violations
        collector.record_security_violation(
            "node1",
            "SQLNode",
            {"message": "SQL injection", "severity": "high"},
            {"source": "api", "target": "db"},
        )

        time.sleep(0.001)  # Ensure different timestamps

        collector.record_security_violation(
            "node2",
            "SQLNode",
            {"message": "Another injection", "severity": "critical"},
            {"source": "form", "target": "db"},
        )

        collector.record_security_violation(
            "node3",
            "FileNode",
            {"message": "Path traversal", "severity": "medium"},
            {"source": "upload", "target": "filesystem"},
        )

        # Get security report
        report = collector.get_security_report()

        assert report["total_violations"] == 3
        assert "SQLNode" in report["violations_by_node_type"]
        assert len(report["violations_by_node_type"]["SQLNode"]) == 2
        assert "FileNode" in report["violations_by_node_type"]
        assert len(report["most_recent_violations"]) == 3

        # Check most recent is first
        recent = report["most_recent_violations"][0]
        assert "node3" in recent["node"]

    def test_metrics_export(self):
        """Test exporting metrics for external processing."""
        collector = ValidationMetricsCollector()

        # Add some metrics
        collector.start_validation("n1", "NodeType", "strict")
        collector.end_validation("n1", "NodeType", success=True)
        collector.record_security_violation("n2", "SQLNode", {"msg": "test"})

        # Export metrics
        exported = collector.export_metrics()

        assert len(exported) == 3
        assert all(isinstance(m, dict) for m in exported)
        assert all("timestamp" in m for m in exported)
        assert all("event_type" in m for m in exported)

    def test_metrics_reset(self):
        """Test resetting all metrics."""
        collector = ValidationMetricsCollector()

        # Add various metrics
        collector.start_validation("n1", "Type", "strict")
        collector.end_validation("n1", "Type", success=True)
        collector.record_security_violation("n2", "Type", {})
        collector.record_cache_hit("Type")

        # Reset
        collector.reset_metrics()

        # Check everything is cleared
        assert len(collector.metrics) == 0
        assert len(collector.security_violations) == 0
        assert len(collector.node_validation_times) == 0
        assert len(collector.error_counts) == 0
        assert collector._cache_stats == {"hits": 0, "misses": 0}


class TestGlobalMetricsCollector:
    """Test global metrics collector singleton."""

    def test_global_collector_singleton(self):
        """Test that global collector returns same instance."""
        reset_global_metrics()  # Start fresh

        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_global_collector_reset(self):
        """Test resetting global collector."""
        collector = get_metrics_collector()

        # Add a metric
        collector.start_validation("n1", "Type", "strict")
        assert len(collector.metrics) == 1

        # Reset globally
        reset_global_metrics()

        # Should be empty
        assert len(collector.metrics) == 0


class TestLocalRuntimeMetricsIntegration:
    """Test metrics integration with LocalRuntime."""

    def test_runtime_metrics_collection(self):
        """Test that LocalRuntime collects validation metrics."""
        reset_global_metrics()  # Start fresh

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "source", {"code": "result = 123"})
        workflow.add_node("PythonCodeNode", "consumer", {"code": "result = data"})
        workflow.add_connection("source", "result", "consumer", "data")

        with LocalRuntime(connection_validation="strict") as runtime:
            # Execute workflow
            results, run_id = runtime.execute(workflow.build())

        # Get metrics
        metrics = runtime.get_validation_metrics()

        # Should have performance summary
        assert "performance_summary" in metrics
        summary = metrics["performance_summary"]
        assert summary["total_validations"] >= 2  # At least source and consumer
        assert summary["failed_validations"] == 0  # Should all pass

    def test_runtime_security_violation_metrics(self):
        """Test that security violations are tracked in metrics."""
        reset_global_metrics()

        # Directly test the metrics collector functionality
        from kailash.runtime.validation.metrics import get_metrics_collector

        collector = get_metrics_collector()

        # Simulate a security violation during validation
        collector.start_validation("test_node", "SQLNode", "strict")
        collector.end_validation(
            "test_node",
            "SQLNode",
            success=False,
            error_category=ErrorCategory.SECURITY_VIOLATION,
            connection_info={"source": "input", "target": "database"},
        )

        # Record the security violation
        collector.record_security_violation(
            "test_node",
            "SQLNode",
            {"message": "SQL injection detected", "pattern": "DROP TABLE"},
            {"source": "input", "target": "database"},
        )

        # Get metrics through a runtime instance
        with LocalRuntime() as runtime:
            metrics = runtime.get_validation_metrics()

        # Check security report
        security_report = metrics["security_report"]
        assert security_report["total_violations"] == 1
        assert "SQLNode" in str(security_report["violations_by_node_type"])

    def test_runtime_metrics_reset(self):
        """Test resetting runtime metrics."""
        reset_global_metrics()  # Start fresh

        with LocalRuntime(
            connection_validation="warn"
        ) as runtime:  # Explicitly set to warn
            # Add some metrics by running a workflow
            workflow = WorkflowBuilder()
            workflow.add_node("PythonCodeNode", "node", {"code": "result = 1"})
            runtime.execute(workflow.build())

            # Check that we have some metrics (either validations or bypasses)
            metrics = runtime.get_validation_metrics()
            summary = metrics["performance_summary"]
            # With warn mode, we should have validations
            assert summary["total_validations"] > 0 or summary["mode_bypasses"] > 0

            # Reset
            runtime.reset_validation_metrics()

            # Should be empty
            metrics = runtime.get_validation_metrics()
            assert metrics["performance_summary"]["total_validations"] == 0
            assert metrics["performance_summary"]["mode_bypasses"] == 0

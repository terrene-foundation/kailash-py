"""Unit tests for PerformanceBenchmarkNode.

MOVED FROM: tests/integration/nodes/monitoring/
REASON: This test uses extensive mocking and belongs in unit tier.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import NodeParameter
from kailash.nodes.monitoring import PerformanceBenchmarkNode
from kailash.nodes.monitoring.performance_benchmark import (
    AlertType,
    BenchmarkResult,
    MetricType,
    PerformanceTarget,
)


class TestPerformanceBenchmarkNode:
    """Test suite for PerformanceBenchmarkNode."""

    def test_node_initialization(self):
        """Test that PerformanceBenchmarkNode initializes correctly."""
        node = PerformanceBenchmarkNode(name="Test Benchmark Node")
        assert node.metadata.name == "Test Benchmark Node"
        assert node.targets == {}
        assert node.alerts == {}

    def test_get_parameters(self):
        """Test parameter definition."""
        node = PerformanceBenchmarkNode()
        params = node.get_parameters()

        # Check required parameters
        assert "operations" in params
        assert params["operations"].required is True
        assert params["operations"].type == list

        # Check optional parameters
        assert "enable_monitoring" in params
        assert params["enable_monitoring"].required is False
        assert params["enable_monitoring"].default is True

        assert "performance_targets" in params
        assert "alert_thresholds" in params
        assert "enable_mcp_metrics" in params

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = PerformanceBenchmarkNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "results" in schema
        assert schema["results"].type == list

        assert "summary" in schema
        assert schema["summary"].type == dict

        assert "alerts" in schema
        assert schema["alerts"].type == list

        assert "recommendations" in schema

    @patch("kailash.nodes.monitoring.performance_benchmark.psutil")
    @patch("kailash.nodes.monitoring.performance_benchmark.tracemalloc")
    def test_execute_simple_operation(self, mock_tracemalloc, mock_psutil):
        """Test executing a simple benchmark operation."""
        # Mock system metrics
        mock_process = Mock()
        mock_process.cpu_percent.return_value = 25.0
        mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_psutil.Process.return_value = mock_process

        # Mock tracemalloc
        mock_tracemalloc.get_traced_memory.return_value = (
            50 * 1024 * 1024,
            100 * 1024 * 1024,
        )

        # Create node and execute
        node = PerformanceBenchmarkNode()

        # Simple operation that returns immediately
        def simple_operation():
            return {"status": "success", "value": 42}

        result = node.execute(
            operations=[simple_operation],
            iterations=1,
            warmup_iterations=0,
            enable_monitoring=False,  # Disable monitoring for simple test
        )

        # Check results
        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["operation_name"] == "simple_operation"
        assert result["results"][0]["success"] is True

        assert "summary" in result
        assert result["summary"]["total_operations"] == 1
        assert result["summary"]["successful_operations"] == 1

    def test_performance_target_validation(self):
        """Test performance target creation and validation."""
        target = PerformanceTarget(
            operation="test_op",
            metric_type=MetricType.RESPONSE_TIME,
            target_value=100.0,
            threshold_warning=150.0,
            threshold_critical=200.0,
            unit="ms",
            description="Test response time target",
        )

        assert target.operation == "test_op"
        assert target.metric_type == MetricType.RESPONSE_TIME
        assert target.target_value == 100.0
        assert target.threshold_warning == 150.0
        assert target.threshold_critical == 200.0

    def test_benchmark_result_creation(self):
        """Test BenchmarkResult dataclass."""
        result = BenchmarkResult(
            operation_name="test_operation",
            execution_time_ms=150.0,
            memory_used_mb=50.0,
            cpu_usage_percent=30.0,
            success=True,
            error_message=None,
            metadata={"iterations": 10},
            timestamp=datetime.now(),
        )

        assert result.operation_name == "test_operation"
        assert result.execution_time_ms == 150.0
        assert result.memory_used_mb == 50.0
        assert result.success is True
        assert result.metadata["iterations"] == 10

    def test_alert_types(self):
        """Test alert type enumeration."""
        assert AlertType.THRESHOLD_EXCEEDED.value == "threshold_exceeded"
        assert AlertType.TREND_DEGRADATION.value == "trend_degradation"
        assert AlertType.ANOMALY_DETECTED.value == "anomaly_detected"
        assert AlertType.RESOURCE_EXHAUSTION.value == "resource_exhaustion"

    def test_metric_types(self):
        """Test metric type enumeration."""
        assert MetricType.RESPONSE_TIME.value == "response_time"
        assert MetricType.THROUGHPUT.value == "throughput"
        assert MetricType.CPU_USAGE.value == "cpu_usage"
        assert MetricType.MEMORY_USAGE.value == "memory_usage"

    @patch("kailash.nodes.monitoring.performance_benchmark.psutil")
    def test_failed_operation_handling(self, mock_psutil):
        """Test handling of failed operations."""
        # Mock system metrics
        mock_process = Mock()
        mock_process.cpu_percent.return_value = 25.0
        mock_process.memory_info.return_value = Mock(rss=100 * 1024 * 1024)
        mock_psutil.Process.return_value = mock_process

        node = PerformanceBenchmarkNode()

        # Operation that raises an exception
        def failing_operation():
            raise ValueError("Test error")

        result = node.execute(
            operations=[failing_operation],
            iterations=1,
            warmup_iterations=0,
            enable_monitoring=False,
        )

        # Check that failure is recorded
        assert result["results"][0]["success"] is False
        assert "Test error" in result["results"][0]["error_message"]
        assert result["summary"]["failed_operations"] == 1

    def test_node_import(self):
        """Test that PerformanceBenchmarkNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import PerformanceBenchmarkNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "PerformanceBenchmarkNode"

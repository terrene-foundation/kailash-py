"""Unit tests for MetricsCollectorNode."""

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.nodes.monitoring import MetricsCollectorNode
from kailash.nodes.monitoring.metrics_collector import MetricFormat, MetricType
from kailash.sdk_exceptions import NodeExecutionError


class TestMetricsCollectorNode:
    """Test suite for MetricsCollectorNode."""

    def test_node_initialization(self):
        """Test that MetricsCollectorNode initializes correctly."""
        node = MetricsCollectorNode(id="test_metrics")
        assert node.id == "test_metrics"
        assert node.metric_buffer == []
        assert node.last_collection_time is None

    def test_get_parameters(self):
        """Test parameter definition."""
        node = MetricsCollectorNode()
        params = node.get_parameters()

        # Check optional parameters with defaults
        assert "metric_types" in params
        assert params["metric_types"].required is False
        assert params["metric_types"].default == ["system.cpu", "system.memory"]

        assert "format" in params
        assert params["format"].default == "json"

        assert "custom_metrics" in params
        assert params["custom_metrics"].type == list

        assert "labels" in params
        assert params["labels"].type == dict

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = MetricsCollectorNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "metrics" in schema
        assert "metric_count" in schema
        assert "collection_time" in schema
        assert "timestamp" in schema
        assert "format" in schema

    def test_metric_format_enum(self):
        """Test MetricFormat enumeration."""
        assert MetricFormat.JSON.value == "json"
        assert MetricFormat.PROMETHEUS.value == "prometheus"
        assert MetricFormat.OPENTELEMETRY.value == "opentelemetry"
        assert MetricFormat.STATSD.value == "statsd"

    def test_metric_type_enum(self):
        """Test MetricType enumeration."""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"
        assert MetricType.HISTOGRAM.value == "histogram"
        assert MetricType.SUMMARY.value == "summary"

    @pytest.mark.asyncio
    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    async def test_system_metrics_collection(self, mock_memory, mock_cpu):
        """Test system metrics collection."""
        # Mock system metrics
        mock_cpu.return_value = [25.0, 30.0]  # 2 cores
        mock_memory.return_value = Mock(
            total=8 * 1024 * 1024 * 1024,  # 8GB
            used=4 * 1024 * 1024 * 1024,  # 4GB
            available=4 * 1024 * 1024 * 1024,
            percent=50.0,
        )

        node = MetricsCollectorNode()
        result = await node.execute_async(
            metric_types=["system.cpu", "system.memory"], format="json"
        )

        # Verify results
        assert result["format"] == "json"
        assert result["metric_count"] > 0
        assert isinstance(result["metrics"], list)

        # Check for CPU metrics
        cpu_metrics = [m for m in result["metrics"] if "cpu" in m["name"]]
        assert len(cpu_metrics) > 0

        # Check for memory metrics
        memory_metrics = [m for m in result["metrics"] if "memory" in m["name"]]
        assert len(memory_metrics) > 0

    @pytest.mark.asyncio
    async def test_custom_metrics(self):
        """Test custom metrics collection."""
        node = MetricsCollectorNode()

        custom_metrics = [
            {"name": "requests_total", "type": "counter", "value": 1000},
            {"name": "response_time_ms", "type": "gauge", "value": 125.5},
            {"name": "queue_size", "value": 42},  # Should default to gauge
        ]

        result = await node.execute_async(
            metric_types=[],  # No system metrics
            custom_metrics=custom_metrics,
            include_process=False,  # Also disable process metrics
            format="json",
        )

        # Verify custom metrics
        assert result["metric_count"] == 3
        metrics = result["metrics"]

        # Check counter metric
        counter = next(m for m in metrics if m["name"] == "requests_total")
        assert counter["type"] == "counter"
        assert counter["value"] == 1000.0

        # Check gauge metric
        gauge = next(m for m in metrics if m["name"] == "response_time_ms")
        assert gauge["type"] == "gauge"
        assert gauge["value"] == 125.5

        # Check defaulted metric
        defaulted = next(m for m in metrics if m["name"] == "queue_size")
        assert defaulted["type"] == "gauge"
        assert defaulted["value"] == 42.0

    @pytest.mark.asyncio
    async def test_prometheus_format(self):
        """Test Prometheus format output."""
        node = MetricsCollectorNode()

        custom_metrics = [
            {
                "name": "http_requests_total",
                "type": "counter",
                "value": 100,
                "labels": {"method": "GET", "status": "200"},
            },
            {
                "name": "memory_usage_bytes",
                "type": "gauge",
                "value": 1024000,
                "labels": {"host": "server1"},
            },
        ]

        result = await node.execute_async(
            metric_types=[], custom_metrics=custom_metrics, format="prometheus"
        )

        # Verify Prometheus format
        assert result["format"] == "prometheus"
        assert isinstance(result["metrics"], str)

        metrics_str = result["metrics"]
        assert "# TYPE http_requests_total counter" in metrics_str
        assert 'http_requests_total{method="GET",status="200"} 100' in metrics_str
        assert "# TYPE memory_usage_bytes gauge" in metrics_str
        assert 'memory_usage_bytes{host="server1"} 1024000' in metrics_str

    @pytest.mark.asyncio
    async def test_statsd_format(self):
        """Test StatsD format output."""
        node = MetricsCollectorNode()

        custom_metrics = [
            {
                "name": "api.request.count",
                "type": "counter",
                "value": 50,
                "labels": {"endpoint": "/users"},
            },
            {"name": "api.response.time", "type": "gauge", "value": 0.125},
        ]

        result = await node.execute_async(
            metric_types=[], custom_metrics=custom_metrics, format="statsd"
        )

        # Verify StatsD format
        assert result["format"] == "statsd"
        assert isinstance(result["metrics"], str)

        metrics_str = result["metrics"]
        assert "api.request.count:50.0|c|#endpoint:/users" in metrics_str  # Float value
        assert "api.response.time:0.125|g" in metrics_str

    @pytest.mark.asyncio
    async def test_labels_addition(self):
        """Test adding global labels to all metrics."""
        node = MetricsCollectorNode()

        custom_metrics = [
            {"name": "test_metric", "value": 10, "labels": {"custom": "label"}}
        ]

        result = await node.execute_async(
            metric_types=[],
            custom_metrics=custom_metrics,
            include_process=False,  # Disable process metrics
            labels={"env": "production", "region": "us-west"},
            format="json",
        )

        # Verify labels were added
        metric = result["metrics"][0]
        assert metric["labels"]["env"] == "production"
        assert metric["labels"]["region"] == "us-west"
        assert metric["labels"]["custom"] == "label"  # Original label preserved

    @pytest.mark.asyncio
    @patch("psutil.Process")
    async def test_process_metrics(self, mock_process_class):
        """Test process metrics collection."""
        # Mock process
        mock_process = Mock()
        mock_process.cpu_percent.return_value = 15.0
        mock_process.memory_info.return_value = Mock(
            rss=100 * 1024 * 1024, vms=200 * 1024 * 1024  # 100MB  # 200MB
        )
        mock_process.num_threads.return_value = 5
        mock_process.name.return_value = "test_process"

        mock_process_class.return_value = mock_process

        node = MetricsCollectorNode()
        result = await node.execute_async(
            metric_types=[], include_process=True, format="json"
        )

        # Verify process metrics
        process_metrics = [m for m in result["metrics"] if "process" in m["name"]]
        assert len(process_metrics) > 0

        # Check specific metrics
        cpu_metric = next(
            (m for m in process_metrics if m["name"] == "process_cpu_usage_percent"),
            None,
        )
        assert cpu_metric is not None
        assert cpu_metric["value"] == 15.0

    def test_validate_custom_metrics(self):
        """Test custom metrics validation."""
        node = MetricsCollectorNode()

        # Test valid and invalid metrics
        input_metrics = [
            {"name": "valid_metric", "value": 100},
            {"value": 200},  # Missing name
            {"name": "no_value"},  # Missing value
            {"name": "invalid_type", "value": 50, "type": "invalid"},
        ]

        validated = node._validate_custom_metrics(input_metrics)

        # Only valid metrics should pass
        assert len(validated) == 2
        assert validated[0]["name"] == "valid_metric"
        assert validated[0]["value"] == 100.0
        assert validated[0]["type"] == "gauge"  # Default

        assert validated[1]["name"] == "invalid_type"
        assert validated[1]["type"] == "gauge"  # Defaulted from invalid

    def test_metric_aggregation(self):
        """Test metric aggregation functionality."""
        node = MetricsCollectorNode()

        # Add metrics to buffer
        base_time = time.time()
        metrics = [
            {
                "name": "cpu_usage",
                "type": "gauge",
                "value": 25.0,
                "timestamp": base_time - 30,
                "labels": {"host": "server1"},
            },
            {
                "name": "cpu_usage",
                "type": "gauge",
                "value": 35.0,
                "timestamp": base_time - 20,
                "labels": {"host": "server1"},
            },
            {
                "name": "cpu_usage",
                "type": "gauge",
                "value": 30.0,
                "timestamp": base_time - 10,
                "labels": {"host": "server1"},
            },
        ]

        # Test aggregation
        aggregated = node._aggregate_metrics(metrics, interval=60.0)

        # Should have one aggregated metric
        assert len(aggregated) == 1
        agg_metric = aggregated[0]
        assert agg_metric["name"] == "cpu_usage"
        assert agg_metric["value"] == 30.0  # Average of 25, 35, 30
        assert agg_metric["sample_count"] == 3

    def test_node_import(self):
        """Test that MetricsCollectorNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import MetricsCollectorNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "MetricsCollectorNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = MetricsCollectorNode()

        with patch.object(node, "async_run") as mock_async_run:
            mock_async_run.return_value = {
                "metrics": [],
                "metric_count": 0,
                "collection_time": 0.1,
                "timestamp": datetime.now().isoformat(),
                "format": "json",
            }

            # Execute synchronously
            result = node.execute(metric_types=[], format="json")

            assert result["format"] == "json"
            assert result["metric_count"] == 0

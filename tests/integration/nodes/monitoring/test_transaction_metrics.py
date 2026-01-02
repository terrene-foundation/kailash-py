"""Unit tests for TransactionMetricsNode."""

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.monitoring import TransactionMetricsNode
from kailash.nodes.monitoring.transaction_metrics import (
    AggregationType,
    MetricExportFormat,
    TransactionMetric,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestTransactionMetricsNode:
    """Test suite for TransactionMetricsNode."""

    def test_node_initialization(self):
        """Test that TransactionMetricsNode initializes correctly."""
        node = TransactionMetricsNode(id="test_txn_metrics")
        assert node.id == "test_txn_metrics"
        assert node._active_transactions == {}
        assert node._completed_transactions == []
        assert node._metric_buffer == {}
        assert node._last_aggregation_time is not None

    def test_get_parameters(self):
        """Test parameter definition."""
        node = TransactionMetricsNode()
        params = node.get_parameters()

        # Check required parameters
        assert "operation" in params
        assert params["operation"].required is True

        # Check optional parameters with defaults
        assert "transaction_id" in params
        assert params["transaction_id"].required is False

        assert "name" in params
        assert params["name"].required is False

        assert "status" in params
        assert params["status"].default == "success"

        assert "tags" in params
        assert params["tags"].default == {}

        assert "custom_metrics" in params
        assert params["custom_metrics"].default == {}

        assert "export_format" in params
        assert params["export_format"].default == "json"

        assert "aggregation_types" in params
        assert params["aggregation_types"].default == [
            "count",
            "avg",
            "p50",
            "p95",
            "p99",
        ]

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = TransactionMetricsNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "metrics" in schema
        assert "transaction_count" in schema
        assert "aggregations" in schema
        assert "export_format" in schema
        assert "timestamp" in schema
        assert "status" in schema

    def test_metric_export_format_enum(self):
        """Test MetricExportFormat enumeration."""
        assert MetricExportFormat.JSON.value == "json"
        assert MetricExportFormat.PROMETHEUS.value == "prometheus"
        assert MetricExportFormat.CLOUDWATCH.value == "cloudwatch"
        assert MetricExportFormat.DATADOG.value == "datadog"
        assert MetricExportFormat.OPENTELEMETRY.value == "opentelemetry"

    def test_aggregation_type_enum(self):
        """Test AggregationType enumeration."""
        assert AggregationType.COUNT.value == "count"
        assert AggregationType.AVG.value == "avg"
        assert AggregationType.P50.value == "p50"
        assert AggregationType.P95.value == "p95"
        assert AggregationType.P99.value == "p99"

    def test_start_transaction(self):
        """Test starting a transaction."""
        node = TransactionMetricsNode()

        result = node.execute(
            operation="start_transaction",
            transaction_id="txn_123",
            name="test_operation",
            tags={"service": "api", "version": "1.0"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["metrics"]["transaction_id"] == "txn_123"
        assert result["metrics"]["status"] == "started"
        assert result["transaction_count"] == 1

        # Verify internal state
        assert "txn_123" in node._active_transactions
        txn = node._active_transactions["txn_123"]
        assert txn.transaction_id == "txn_123"
        assert txn.name == "test_operation"
        assert txn.tags["service"] == "api"
        assert txn.status == "in_progress"

    def test_start_transaction_missing_id(self):
        """Test starting a transaction without transaction_id."""
        node = TransactionMetricsNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="start_transaction")

        assert "transaction_id is required" in str(exc_info.value)

    def test_end_transaction(self):
        """Test ending a transaction."""
        node = TransactionMetricsNode()

        # Start transaction first
        node.execute(
            operation="start_transaction",
            transaction_id="txn_456",
            name="payment_processing",
        )

        # Wait a small amount to ensure duration > 0
        import time

        time.sleep(0.01)

        # End transaction
        result = node.execute(
            operation="end_transaction",
            transaction_id="txn_456",
            status="success",
            custom_metrics={"items_processed": 5, "db_calls": 3},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["metrics"]["transaction_id"] == "txn_456"
        assert result["metrics"]["status"] == "success"
        assert result["metrics"]["duration"] > 0

        # Verify internal state
        assert "txn_456" not in node._active_transactions
        assert len(node._completed_transactions) == 1

        completed_txn = node._completed_transactions[0]
        assert completed_txn.transaction_id == "txn_456"
        assert completed_txn.status == "success"
        assert completed_txn.duration is not None
        assert completed_txn.custom_metrics["items_processed"] == 5

    def test_end_transaction_missing_id(self):
        """Test ending a transaction without transaction_id."""
        node = TransactionMetricsNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="end_transaction")

        assert "transaction_id is required" in str(exc_info.value)

    def test_end_transaction_not_found(self):
        """Test ending a transaction that doesn't exist."""
        node = TransactionMetricsNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="end_transaction", transaction_id="nonexistent")

        assert "Transaction nonexistent not found" in str(exc_info.value)

    def test_get_metrics_json(self):
        """Test getting metrics in JSON format."""
        node = TransactionMetricsNode()

        # Create a completed transaction manually
        txn = TransactionMetric(
            transaction_id="txn_789",
            name="data_processing",
            start_time=time.time() - 1.0,
            end_time=time.time(),
            duration=1.0,
            status="success",
            tags={"region": "us-west"},
        )
        node._completed_transactions.append(txn)

        result = node.execute(
            operation="get_metrics", include_raw=True, export_format="json"
        )

        # Verify result
        assert result["status"] == "success"
        assert result["export_format"] == "json"
        assert result["transaction_count"] == 1
        assert isinstance(result["metrics"], list)
        assert len(result["metrics"]) == 1

        metric_data = result["metrics"][0]
        assert metric_data["transaction_id"] == "txn_789"
        assert metric_data["name"] == "data_processing"
        assert metric_data["duration"] == 1.0

    def test_get_metrics_filtered(self):
        """Test getting filtered metrics."""
        node = TransactionMetricsNode()

        # Create multiple completed transactions
        txn1 = TransactionMetric(
            transaction_id="txn_1",
            name="operation_a",
            start_time=time.time() - 1.0,
            end_time=time.time(),
            duration=1.0,
            status="success",
        )
        txn2 = TransactionMetric(
            transaction_id="txn_2",
            name="operation_b",
            start_time=time.time() - 1.0,
            end_time=time.time(),
            duration=2.0,
            status="success",
        )
        node._completed_transactions.extend([txn1, txn2])

        result = node.execute(
            operation="get_metrics", metric_names=["operation_a"], include_raw=True
        )

        # Verify filtering
        assert result["transaction_count"] == 1
        metric_data = result["metrics"][0]
        assert metric_data["name"] == "operation_a"

    def test_get_aggregated_metrics(self):
        """Test getting aggregated metrics."""
        node = TransactionMetricsNode()

        # Create multiple completed transactions with same name
        base_time = time.time()
        durations = [0.5, 1.0, 1.5, 2.0, 3.0]  # For percentile testing

        for i, duration in enumerate(durations):
            txn = TransactionMetric(
                transaction_id=f"txn_{i}",
                name="api_call",
                start_time=base_time - duration - 1,
                end_time=base_time - 1,
                duration=duration,
                status="success",
                tags={"service": "api"},
            )
            node._completed_transactions.append(txn)
            node._metric_buffer["api_call"].append(txn)

        result = node.execute(
            operation="get_aggregated",
            metric_names=["api_call"],
            aggregation_window=3600.0,  # Large window to include all
            aggregation_types=["count", "avg", "p50", "p95", "p99"],
        )

        # Verify aggregation
        assert result["status"] == "success"
        assert result["transaction_count"] == 5
        assert "api_call" in result["aggregations"]

        agg_data = result["aggregations"]["api_call"]
        assert agg_data["count"] == 5
        assert agg_data["avg_duration"] == 1.6  # (0.5+1.0+1.5+2.0+3.0)/5
        assert agg_data["min_duration"] == 0.5
        assert agg_data["max_duration"] == 3.0
        assert agg_data["success_count"] == 5
        assert agg_data["error_count"] == 0
        assert agg_data["error_rate"] == 0.0

        # Check percentiles
        assert "p50" in agg_data["percentiles"]
        assert "p95" in agg_data["percentiles"]
        assert agg_data["percentiles"]["p50"] == 1.5  # Middle value
        assert agg_data["percentiles"]["p95"] == 3.0  # Near-max value

    def test_prometheus_format_export(self):
        """Test Prometheus format export."""
        node = TransactionMetricsNode()

        # Create completed transaction
        txn = TransactionMetric(
            transaction_id="txn_prom",
            name="http_request",
            start_time=time.time() - 1.0,
            end_time=time.time(),
            duration=0.125,
            status="success",
            tags={"method": "GET", "status": "200"},
        )
        node._completed_transactions.append(txn)

        result = node.execute(operation="get_metrics", export_format="prometheus")

        # Verify Prometheus format
        assert result["export_format"] == "prometheus"
        assert isinstance(result["metrics"], str)

        metrics_str = result["metrics"]
        assert "# TYPE transaction_duration_seconds histogram" in metrics_str
        assert "transaction_duration_seconds" in metrics_str
        assert "# TYPE transaction_total counter" in metrics_str
        assert 'name="http_request"' in metrics_str
        assert 'method="GET"' in metrics_str
        assert 'status="200"' in metrics_str

    def test_cloudwatch_format_export(self):
        """Test CloudWatch format export."""
        node = TransactionMetricsNode()

        # Create completed transaction with custom metrics
        txn = TransactionMetric(
            transaction_id="txn_cw",
            name="order_processing",
            start_time=time.time() - 1.0,
            end_time=time.time(),
            duration=2.5,
            status="success",
            tags={"region": "us-east-1"},
            custom_metrics={"items_count": 10},
        )
        node._completed_transactions.append(txn)

        result = node.execute(operation="get_metrics", export_format="cloudwatch")

        # Verify CloudWatch format
        assert result["export_format"] == "cloudwatch"
        assert isinstance(result["metrics"], dict)
        assert "MetricData" in result["metrics"]

        metric_data = result["metrics"]["MetricData"]
        assert len(metric_data) == 2  # Duration + custom metric

        # Check duration metric
        duration_metric = next(
            m
            for m in metric_data
            if m["MetricName"] == "TransactionDuration_order_processing"
        )
        assert duration_metric["Value"] == 2500  # Converted to milliseconds
        assert duration_metric["Unit"] == "Milliseconds"
        assert any(
            d["Name"] == "region" and d["Value"] == "us-east-1"
            for d in duration_metric["Dimensions"]
        )

        # Check custom metric
        custom_metric = next(
            m
            for m in metric_data
            if m["MetricName"] == "Custom_order_processing_items_count"
        )
        assert custom_metric["Value"] == 10
        assert custom_metric["Unit"] == "Count"

    def test_datadog_format_export(self):
        """Test DataDog format export."""
        node = TransactionMetricsNode()

        # Create completed transaction
        txn = TransactionMetric(
            transaction_id="txn_dd",
            name="api_endpoint",
            start_time=time.time() - 1.0,
            end_time=time.time(),
            duration=0.075,
            status="success",
            tags={"endpoint": "/users", "method": "POST"},
        )
        node._completed_transactions.append(txn)

        result = node.execute(operation="get_metrics", export_format="datadog")

        # Verify DataDog format
        assert result["export_format"] == "datadog"
        assert isinstance(result["metrics"], dict)
        assert "series" in result["metrics"]

        series = result["metrics"]["series"]
        assert len(series) == 2  # Duration + count

        # Check duration metric
        duration_metric = next(
            m for m in series if m["metric"] == "transaction.duration"
        )
        assert duration_metric["type"] == "gauge"
        assert len(duration_metric["points"]) == 1
        assert duration_metric["points"][0][1] == 0.075  # Duration value
        assert "endpoint:/users" in duration_metric["tags"]
        assert "transaction_name:api_endpoint" in duration_metric["tags"]

        # Check count metric
        count_metric = next(m for m in series if m["metric"] == "transaction.count")
        assert count_metric["type"] == "count"
        assert count_metric["points"][0][1] == 1  # Count value
        assert "status:success" in count_metric["tags"]

    def test_calculate_aggregations(self):
        """Test metric aggregation calculations."""
        node = TransactionMetricsNode()

        # Create test metrics with known values
        base_time = time.time()
        metrics = []
        durations = [1.0, 2.0, 3.0, 4.0, 5.0]  # Known values for easy testing

        for i, duration in enumerate(durations):
            metric = TransactionMetric(
                transaction_id=f"txn_{i}",
                name="test_metric",
                start_time=base_time - duration - 1,
                end_time=base_time - 1,
                duration=duration,
                status="success" if i < 4 else "error",  # 4 success, 1 error
                tags={"common": "tag"},
            )
            metrics.append(metric)

        # Calculate aggregations
        agg = node._calculate_aggregations(metrics, ["count", "avg", "p50", "p95"])

        # Verify calculations
        assert agg.name == "test_metric"
        assert agg.count == 5
        assert agg.sum_duration == 15.0  # 1+2+3+4+5
        assert agg.min_duration == 1.0
        assert agg.max_duration == 5.0
        assert agg.avg_duration == 3.0  # 15/5
        assert agg.success_count == 4
        assert agg.error_count == 1
        assert agg.error_rate == 0.2  # 1/5

        # Check percentiles
        assert agg.percentiles["p50"] == 3.0  # Middle value
        assert agg.percentiles["p95"] == 5.0  # 95th percentile

        # Check aggregated tags
        assert agg.tags["common"] == "tag"

    def test_serialize_metric(self):
        """Test metric serialization."""
        node = TransactionMetricsNode()

        metric = TransactionMetric(
            transaction_id="txn_serialize",
            name="test_operation",
            start_time=1234567890.0,
            end_time=1234567891.5,
            duration=1.5,
            status="success",
            error=None,
            tags={"key": "value"},
            custom_metrics={"count": 42},
        )

        serialized = node._serialize_metric(metric)

        # Verify serialization
        assert serialized["transaction_id"] == "txn_serialize"
        assert serialized["name"] == "test_operation"
        assert serialized["start_time"] == 1234567890.0
        assert serialized["end_time"] == 1234567891.5
        assert serialized["duration"] == 1.5
        assert serialized["status"] == "success"
        assert serialized["error"] is None
        assert serialized["tags"]["key"] == "value"
        assert serialized["custom_metrics"]["count"] == 42

    def test_format_prometheus_labels(self):
        """Test Prometheus label formatting."""
        node = TransactionMetricsNode()

        tags = {
            "service": "api",
            "method": "GET",
            "quoted": 'has"quote',
            "backslash": "has\\slash",
        }

        formatted = node._format_prometheus_labels(tags)

        # Verify formatting
        assert 'service="api"' in formatted
        assert 'method="GET"' in formatted
        assert 'quoted="has\\"quote"' in formatted  # Escaped quote
        assert 'backslash="has\\\\slash"' in formatted  # Escaped backslash

    def test_unknown_operation(self):
        """Test unknown operation handling."""
        node = TransactionMetricsNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="unknown_operation")

        assert "Unknown operation: unknown_operation" in str(exc_info.value)

    def test_node_import(self):
        """Test that TransactionMetricsNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import TransactionMetricsNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "TransactionMetricsNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = TransactionMetricsNode()

        with patch.object(node, "async_run") as mock_async_run:
            mock_async_run.return_value = {
                "metrics": {},
                "transaction_count": 0,
                "total_transactions": 0,  # Added new required field
                "success_rate": 1.0,  # Added new required field
                "aggregations": {},
                "export_format": "json",
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "success",
            }

            # Execute synchronously
            result = node.execute(operation="get_metrics")

            assert result["status"] == "success"
            assert result["export_format"] == "json"

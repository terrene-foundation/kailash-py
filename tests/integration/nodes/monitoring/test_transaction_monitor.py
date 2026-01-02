"""Unit tests for TransactionMonitorNode."""

import asyncio
import time
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.monitoring import TransactionMonitorNode
from kailash.nodes.monitoring.transaction_monitor import (
    AlertSeverity,
    TracingProtocol,
    TransactionAlert,
    TransactionSpan,
    TransactionTrace,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestTransactionMonitorNode:
    """Test suite for TransactionMonitorNode."""

    def test_node_initialization(self):
        """Test that TransactionMonitorNode initializes correctly."""
        node = TransactionMonitorNode(id="test_monitor")
        assert node.id == "test_monitor"
        assert node._active_traces == {}
        assert node._active_spans == {}
        assert node._monitoring_active is False
        assert node._alert_handlers == []
        assert node._stream_handlers == []
        assert node._metrics_buffer == []
        assert node._trace_sampling_rate == 1.0
        assert isinstance(node._background_tasks, set)

    def test_get_parameters(self):
        """Test parameter definition."""
        node = TransactionMonitorNode()
        params = node.get_parameters()

        # Check required parameters
        assert "operation" in params
        assert params["operation"].required is True

        # Check optional parameters with defaults
        assert "trace_id" in params
        assert params["trace_id"].required is False

        assert "span_id" in params
        assert params["span_id"].required is False

        assert "trace_sampling_rate" in params
        assert params["trace_sampling_rate"].default == 1.0

        assert "tracing_protocol" in params
        assert params["tracing_protocol"].default == "opentelemetry"

        assert "enable_streaming" in params
        assert params["enable_streaming"].default is False

        assert "correlation_window" in params
        assert params["correlation_window"].default == 30.0

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = TransactionMonitorNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "monitoring_status" in schema
        assert "trace_data" in schema
        assert "span_data" in schema
        assert "alerts" in schema
        assert "metrics" in schema
        assert "correlation_id" in schema
        assert "timestamp" in schema
        assert "status" in schema

    def test_alert_severity_enum(self):
        """Test AlertSeverity enumeration."""
        assert AlertSeverity.LOW.value == "low"
        assert AlertSeverity.MEDIUM.value == "medium"
        assert AlertSeverity.HIGH.value == "high"
        assert AlertSeverity.CRITICAL.value == "critical"

    def test_tracing_protocol_enum(self):
        """Test TracingProtocol enumeration."""
        assert TracingProtocol.OPENTELEMETRY.value == "opentelemetry"
        assert TracingProtocol.JAEGER.value == "jaeger"
        assert TracingProtocol.ZIPKIN.value == "zipkin"
        assert TracingProtocol.CUSTOM.value == "custom"

    def test_transaction_span_creation(self):
        """Test TransactionSpan dataclass."""
        span = TransactionSpan(
            span_id="span_123",
            trace_id="trace_456",
            operation_name="test_operation",
            service_name="test_service",
            tags={"key": "value"},
        )

        assert span.span_id == "span_123"
        assert span.trace_id == "trace_456"
        assert span.operation_name == "test_operation"
        assert span.service_name == "test_service"
        assert span.tags["key"] == "value"
        assert span.status == "ok"
        assert span.parent_span_id is None
        assert span.error is None

    def test_transaction_trace_creation(self):
        """Test TransactionTrace dataclass."""
        trace = TransactionTrace(trace_id="trace_789", root_span_id="span_root")

        assert trace.trace_id == "trace_789"
        assert trace.root_span_id == "span_root"
        assert trace.spans == []
        assert trace.total_duration is None
        assert trace.service_count == 0
        assert trace.span_count == 0
        assert trace.error_count == 0
        assert trace.critical_path == []

    def test_transaction_alert_creation(self):
        """Test TransactionAlert dataclass."""
        alert = TransactionAlert(
            alert_id="alert_123",
            severity=AlertSeverity.HIGH,
            message="Test alert",
            trace_id="trace_456",
            metric_name="duration",
            metric_value=5.0,
            threshold=2.0,
            tags={"service": "api"},
        )

        assert alert.alert_id == "alert_123"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.message == "Test alert"
        assert alert.trace_id == "trace_456"
        assert alert.metric_name == "duration"
        assert alert.metric_value == 5.0
        assert alert.threshold == 2.0
        assert alert.tags["service"] == "api"
        assert alert.resolved is False

    def test_start_monitoring(self):
        """Test starting monitoring."""
        node = TransactionMonitorNode()

        result = node.execute(
            operation="start_monitoring",
            trace_sampling_rate=0.5,
            alert_thresholds={
                "duration": {"p95": 2.0},
                "error_rate": {"threshold": 0.01},
            },
        )

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "active"
        assert result["metrics"]["sampling_rate"] == 0.5

        # Verify internal state
        assert node._monitoring_active is True
        assert node._trace_sampling_rate == 0.5
        assert "duration" in node._alert_thresholds
        assert node._alert_thresholds["duration"]["p95"] == 2.0

        # Cleanup
        asyncio.run(node._stop_monitoring())

    def test_stop_monitoring(self):
        """Test stopping monitoring."""
        node = TransactionMonitorNode()

        # Start monitoring first
        node.execute(operation="start_monitoring")

        # Stop monitoring
        result = node.execute(operation="stop_monitoring")

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "stopped"

        # Verify internal state
        assert node._monitoring_active is False
        assert len(node._background_tasks) == 0

    def test_create_trace(self):
        """Test creating a distributed trace."""
        node = TransactionMonitorNode()

        result = node.execute(
            operation="create_trace",
            trace_id="trace_test_123",
            operation_name="order_processing",
            service_name="order-service",
            tags={"customer_id": "12345", "priority": "high"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "trace_created"
        assert result["trace_data"]["trace_id"] == "trace_test_123"
        assert result["trace_data"]["sampled"] is True
        assert result["span_data"]["operation_name"] == "order_processing"
        assert result["span_data"]["service_name"] == "order-service"

        # Verify internal state
        assert "trace_test_123" in node._active_traces
        trace = node._active_traces["trace_test_123"]
        assert trace.trace_id == "trace_test_123"
        assert trace.span_count == 1
        assert trace.service_count == 1
        assert len(trace.spans) == 1

        root_span = trace.spans[0]
        assert root_span.operation_name == "order_processing"
        assert root_span.service_name == "order-service"
        assert root_span.tags["customer_id"] == "12345"

    def test_create_trace_with_sampling(self):
        """Test trace creation with sampling."""
        node = TransactionMonitorNode()
        node._trace_sampling_rate = 0.0  # Skip all traces

        with patch("random.random", return_value=0.5):  # > sampling rate
            result = node.execute(
                operation="create_trace",
                trace_id="trace_sampled_out",
                operation_name="test_op",
            )

        # Verify trace was skipped
        assert result["monitoring_status"] == "sampling_skipped"
        assert result["trace_data"]["sampled"] is False
        assert "trace_sampled_out" not in node._active_traces

    def test_add_span(self):
        """Test adding a span to an existing trace."""
        node = TransactionMonitorNode()

        # Create trace first
        node.execute(
            operation="create_trace",
            trace_id="trace_span_test",
            operation_name="root_operation",
            service_name="root-service",
        )

        # Get root span ID
        trace = node._active_traces["trace_span_test"]
        root_span_id = trace.root_span_id

        # Add child span
        result = node.execute(
            operation="add_span",
            trace_id="trace_span_test",
            span_id="span_child_123",
            parent_span_id=root_span_id,
            operation_name="database_query",
            service_name="db-service",
            tags={"query_type": "SELECT", "table": "orders"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "span_added"
        assert result["trace_data"]["trace_id"] == "trace_span_test"
        assert result["trace_data"]["span_count"] == 2
        assert result["trace_data"]["service_count"] == 2
        assert result["span_data"]["span_id"] == "span_child_123"
        assert result["span_data"]["parent_span_id"] == root_span_id

        # Verify internal state
        assert "span_child_123" in node._active_spans
        child_span = node._active_spans["span_child_123"]
        assert child_span.parent_span_id == root_span_id
        assert child_span.operation_name == "database_query"
        assert child_span.tags["query_type"] == "SELECT"

        # Verify trace updated
        assert trace.span_count == 2
        assert trace.service_count == 2

    def test_add_span_trace_not_found(self):
        """Test adding span to non-existent trace."""
        node = TransactionMonitorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(
                operation="add_span",
                trace_id="nonexistent_trace",
                operation_name="test_op",
            )

        assert "Trace nonexistent_trace not found" in str(exc_info.value)

    def test_finish_span(self):
        """Test finishing a span."""
        node = TransactionMonitorNode()

        # Create trace and add span
        node.execute(
            operation="create_trace",
            trace_id="trace_finish_test",
            operation_name="test_operation",
        )

        trace = node._active_traces["trace_finish_test"]
        span_id = trace.root_span_id

        # Wait to ensure duration > 0
        import time

        time.sleep(0.01)

        # Finish span
        result = node.execute(operation="finish_span", span_id=span_id, error=None)

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "span_finished"
        assert result["span_data"]["span_id"] == span_id
        assert result["span_data"]["duration"] > 0
        assert result["span_data"]["status"] == "ok"

        # Verify span is no longer active
        assert span_id not in node._active_spans

        # Verify trace duration is set (root span finished)
        assert trace.total_duration is not None
        assert trace.total_duration > 0

    def test_finish_span_with_error(self):
        """Test finishing a span with an error."""
        node = TransactionMonitorNode()

        # Create trace
        node.execute(
            operation="create_trace",
            trace_id="trace_error_test",
            operation_name="test_operation",
        )

        trace = node._active_traces["trace_error_test"]
        span_id = trace.root_span_id

        # Finish span with error
        result = node.execute(
            operation="finish_span", span_id=span_id, error="Database connection failed"
        )

        # Verify result
        assert result["span_data"]["status"] == "error"

        # Verify trace error count updated
        assert trace.error_count == 1

    def test_finish_span_not_found(self):
        """Test finishing a span that doesn't exist."""
        node = TransactionMonitorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="finish_span", span_id="nonexistent_span")

        assert "Span nonexistent_span not found" in str(exc_info.value)

    def test_get_trace(self):
        """Test getting trace information."""
        node = TransactionMonitorNode()

        # Create trace with spans
        node.execute(
            operation="create_trace",
            trace_id="trace_get_test",
            operation_name="root_op",
            service_name="root-service",
        )

        trace = node._active_traces["trace_get_test"]
        root_span_id = trace.root_span_id

        # Add child span
        node.execute(
            operation="add_span",
            trace_id="trace_get_test",
            parent_span_id=root_span_id,
            operation_name="child_op",
            service_name="child-service",
        )

        # Get trace
        result = node.execute(operation="get_trace", trace_id="trace_get_test")

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "trace_retrieved"

        trace_data = result["trace_data"]
        assert trace_data["trace_id"] == "trace_get_test"
        assert trace_data["span_count"] == 2
        assert trace_data["service_count"] == 2
        assert len(trace_data["spans"]) == 2

        # Verify span data
        spans = trace_data["spans"]
        root_span = next(s for s in spans if s["span_id"] == root_span_id)
        assert root_span["operation_name"] == "root_op"
        assert root_span["service_name"] == "root-service"

    def test_get_trace_not_found(self):
        """Test getting a trace that doesn't exist."""
        node = TransactionMonitorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="get_trace", trace_id="nonexistent")

        assert "Trace nonexistent not found" in str(exc_info.value)

    def test_get_trace_missing_id(self):
        """Test getting trace without trace_id."""
        node = TransactionMonitorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="get_trace")

        assert "trace_id is required" in str(exc_info.value)

    def test_get_alerts(self):
        """Test getting active alerts."""
        node = TransactionMonitorNode()

        result = node.execute(operation="get_alerts")

        # Verify result (no alerts in basic implementation)
        assert result["status"] == "success"
        assert result["monitoring_status"] == "alerts_retrieved"
        assert result["alerts"] == []
        assert result["metrics"]["active_alerts"] == 0

    def test_correlate_transactions(self):
        """Test transaction correlation."""
        node = TransactionMonitorNode()

        # Create multiple traces with common tags
        for i in range(3):
            node.execute(
                operation="create_trace",
                trace_id=f"trace_corr_{i}",
                operation_name=f"operation_{i}",
                service_name=f"service_{i}",
                tags={"customer_id": "12345", "region": "us-west"},
            )

        result = node.execute(
            operation="correlate_transactions", correlation_window=60.0
        )

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "correlations_found"
        assert result["metrics"]["traces_analyzed"] == 3

    def test_serialize_span(self):
        """Test span serialization."""
        node = TransactionMonitorNode()

        span = TransactionSpan(
            span_id="span_serialize",
            trace_id="trace_serialize",
            parent_span_id="parent_span",
            operation_name="test_operation",
            service_name="test_service",
            start_time=1234567890.0,
            end_time=1234567891.5,
            duration=1.5,
            status="ok",
            tags={"key": "value"},
            baggage={"context": "data"},
        )

        serialized = node._serialize_span(span)

        # Verify serialization
        assert serialized["span_id"] == "span_serialize"
        assert serialized["trace_id"] == "trace_serialize"
        assert serialized["parent_span_id"] == "parent_span"
        assert serialized["operation_name"] == "test_operation"
        assert serialized["service_name"] == "test_service"
        assert serialized["start_time"] == 1234567890.0
        assert serialized["end_time"] == 1234567891.5
        assert serialized["duration"] == 1.5
        assert serialized["status"] == "ok"
        assert serialized["tags"]["key"] == "value"
        assert serialized["baggage"]["context"] == "data"

    def test_serialize_alert(self):
        """Test alert serialization."""
        node = TransactionMonitorNode()

        alert = TransactionAlert(
            alert_id="alert_serialize",
            severity=AlertSeverity.HIGH,
            message="Test alert message",
            trace_id="trace_123",
            metric_name="duration",
            metric_value=5.0,
            threshold=2.0,
            timestamp=1234567890.0,
            tags={"service": "api"},
            resolved=False,
        )

        serialized = node._serialize_alert(alert)

        # Verify serialization
        assert serialized["alert_id"] == "alert_serialize"
        assert serialized["severity"] == "high"
        assert serialized["message"] == "Test alert message"
        assert serialized["trace_id"] == "trace_123"
        assert serialized["metric_name"] == "duration"
        assert serialized["metric_value"] == 5.0
        assert serialized["threshold"] == 2.0
        assert serialized["timestamp"] == 1234567890.0
        assert serialized["tags"]["service"] == "api"
        assert serialized["resolved"] is False

    def test_check_span_alerts(self):
        """Test span alert checking."""
        node = TransactionMonitorNode()

        # Set alert thresholds
        node._alert_thresholds = {"duration": {"p95": 2.0, "p99": 5.0}}

        # Create span that exceeds threshold
        span = TransactionSpan(
            span_id="span_alert_test",
            trace_id="trace_alert_test",
            operation_name="slow_operation",
            duration=3.0,  # Exceeds p95 threshold
            tags={"service": "api"},
        )

        alerts = asyncio.run(node._check_span_alerts(span))

        # Verify alert generated
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.severity == AlertSeverity.MEDIUM  # p95 threshold
        assert "exceeds p95 threshold" in alert.message
        assert alert.metric_value == 3.0
        assert alert.threshold == 2.0

    def test_check_span_alerts_with_error(self):
        """Test span alert checking with error."""
        node = TransactionMonitorNode()

        # Create span with error
        span = TransactionSpan(
            span_id="span_error_alert",
            trace_id="trace_error_alert",
            operation_name="failed_operation",
            error="Connection timeout",
            tags={"service": "api"},
        )

        alerts = asyncio.run(node._check_span_alerts(span))

        # Verify error alert generated
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.severity == AlertSeverity.HIGH
        assert "Span error: Connection timeout" in alert.message
        assert alert.metric_name == "span_error"

    def test_calculate_critical_path(self):
        """Test critical path calculation."""
        node = TransactionMonitorNode()

        # Create trace with spans of different durations
        spans = [
            TransactionSpan("span1", "trace1", duration=1.0),
            TransactionSpan("span2", "trace1", duration=3.0),
            TransactionSpan("span3", "trace1", duration=2.0),
            TransactionSpan("span4", "trace1", duration=0.5),
        ]

        trace = TransactionTrace("trace1", "span1", spans=spans)
        critical_path = node._calculate_critical_path(trace)

        # Should return top 3 spans by duration
        assert len(critical_path) == 3
        assert critical_path[0] == "span2"  # 3.0s
        assert critical_path[1] == "span3"  # 2.0s
        assert critical_path[2] == "span1"  # 1.0s

    def test_unknown_operation(self):
        """Test unknown operation handling."""
        node = TransactionMonitorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="unknown_operation")

        assert "Unknown operation: unknown_operation" in str(exc_info.value)

    def test_node_import(self):
        """Test that TransactionMonitorNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import TransactionMonitorNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "TransactionMonitorNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = TransactionMonitorNode()

        with patch.object(node, "async_run") as mock_async_run:
            mock_async_run.return_value = {
                "monitoring_status": "test",
                "trace_data": {},
                "span_data": {},
                "alerts": [],
                "metrics": {},
                "correlation_id": "test_id",
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "success",
            }

            # Execute synchronously
            result = node.execute(operation="get_alerts")

            assert result["status"] == "success"
            assert result["monitoring_status"] == "test"

    def test_cleanup(self):
        """Test node cleanup."""
        node = TransactionMonitorNode()

        # Start monitoring to create background tasks
        node.execute(operation="start_monitoring")

        # Cleanup
        asyncio.run(node.cleanup())

        # Verify monitoring stopped
        assert node._monitoring_active is False

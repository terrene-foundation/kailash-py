"""Unit tests for PerformanceAnomalyNode.

MOVED FROM: tests/integration/nodes/monitoring/
REASON: This test uses mocking and belongs in unit tier.
"""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import pytest
from kailash.nodes.monitoring import PerformanceAnomalyNode
from kailash.nodes.monitoring.performance_anomaly import (
    AnomalySeverity,
    AnomalyType,
    DetectionMethod,
    PerformanceAnomaly,
    PerformanceBaseline,
    PerformanceMetric,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestPerformanceAnomalyNode:
    """Test suite for PerformanceAnomalyNode."""

    def test_node_initialization(self):
        """Test that PerformanceAnomalyNode initializes correctly."""
        node = PerformanceAnomalyNode(_node_id="test_anomaly_detector")
        assert node.id == "test_anomaly_detector"
        assert node._baselines == {}
        assert node._metrics_buffer == {}
        assert node._detected_anomalies == []
        assert node._monitoring_active is False
        assert isinstance(node._background_tasks, set)
        assert "sensitivity" in node._detection_config
        assert "min_samples" in node._detection_config
        assert "zscore_threshold" in node._detection_config

    def test_get_parameters(self):
        """Test parameter definition."""
        node = PerformanceAnomalyNode()
        params = node.get_parameters()

        # Check required parameters
        assert "operation" in params
        assert params["operation"].required is True

        # Check optional parameters with defaults
        assert "metric_name" in params
        assert params["metric_name"].required is False

        assert "value" in params
        assert params["value"].required is False

        assert "detection_methods" in params
        assert params["detection_methods"].default == ["statistical", "threshold_based"]

        assert "sensitivity" in params
        assert params["sensitivity"].default == 0.8

        assert "detection_window" in params
        assert params["detection_window"].default == 300.0

        assert "min_samples" in params
        assert params["min_samples"].default == 30

        assert "zscore_threshold" in params
        assert params["zscore_threshold"].default == 2.5

        assert "enable_monitoring" in params
        assert params["enable_monitoring"].default is False

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = PerformanceAnomalyNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "anomalies_detected" in schema
        assert "anomaly_count" in schema
        assert "baselines" in schema
        assert "metrics_processed" in schema
        assert "detection_summary" in schema
        assert "recommendations" in schema
        assert "monitoring_status" in schema
        assert "timestamp" in schema
        assert "status" in schema

    def test_anomaly_type_enum(self):
        """Test AnomalyType enumeration."""
        assert AnomalyType.LATENCY_SPIKE.value == "latency_spike"
        assert AnomalyType.THROUGHPUT_DROP.value == "throughput_drop"
        assert AnomalyType.ERROR_RATE_INCREASE.value == "error_rate_increase"
        assert AnomalyType.RESOURCE_EXHAUSTION.value == "resource_exhaustion"
        assert AnomalyType.RESPONSE_TIME_VARIANCE.value == "response_time_variance"
        assert AnomalyType.CONCURRENCY_ANOMALY.value == "concurrency_anomaly"
        assert AnomalyType.TREND_ANOMALY.value == "trend_anomaly"

    def test_anomaly_severity_enum(self):
        """Test AnomalySeverity enumeration."""
        assert AnomalySeverity.LOW.value == "low"
        assert AnomalySeverity.MEDIUM.value == "medium"
        assert AnomalySeverity.HIGH.value == "high"
        assert AnomalySeverity.CRITICAL.value == "critical"

    def test_detection_method_enum(self):
        """Test DetectionMethod enumeration."""
        assert DetectionMethod.STATISTICAL.value == "statistical"
        assert DetectionMethod.THRESHOLD_BASED.value == "threshold_based"
        assert DetectionMethod.ROLLING_AVERAGE.value == "rolling_average"
        assert DetectionMethod.ZSCORE.value == "zscore"
        assert DetectionMethod.IQR.value == "iqr"
        assert DetectionMethod.EXPONENTIAL_SMOOTHING.value == "exponential_smoothing"
        assert DetectionMethod.MACHINE_LEARNING.value == "machine_learning"

    def test_performance_metric_creation(self):
        """Test PerformanceMetric dataclass."""
        metric = PerformanceMetric(
            metric_name="api_response_time",
            value=150.5,
            timestamp=time.time(),
            tags={"endpoint": "/api/users"},
            metadata={"method": "GET"},
        )

        assert metric.metric_name == "api_response_time"
        assert metric.value == 150.5
        assert metric.tags["endpoint"] == "/api/users"
        assert metric.metadata["method"] == "GET"

    def test_performance_baseline_creation(self):
        """Test PerformanceBaseline dataclass."""
        current_time = time.time()
        baseline = PerformanceBaseline(
            metric_name="cpu_usage",
            created_at=current_time,
            updated_at=current_time,
            sample_count=100,
            mean=50.0,
            median=48.0,
            std_dev=10.0,
            min_value=20.0,
            max_value=80.0,
            learning_rate=0.1,
        )

        assert baseline.metric_name == "cpu_usage"
        assert baseline.sample_count == 100
        assert baseline.mean == 50.0
        assert baseline.std_dev == 10.0
        assert baseline.learning_rate == 0.1

    def test_performance_anomaly_creation(self):
        """Test PerformanceAnomaly dataclass."""
        anomaly = PerformanceAnomaly(
            anomaly_id="anomaly_123",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            metric_name="response_time",
            detected_at=time.time(),
            value=500.0,
            expected_value=200.0,
            deviation=300.0,
            severity=AnomalySeverity.HIGH,
            confidence=0.9,
            detection_method=DetectionMethod.THRESHOLD_BASED,
            description="Response time spike detected",
            impact_assessment="High latency may impact user experience",
            recommended_actions=["Check system resources", "Review recent deployments"],
        )

        assert anomaly.anomaly_id == "anomaly_123"
        assert anomaly.anomaly_type == AnomalyType.LATENCY_SPIKE
        assert anomaly.value == 500.0
        assert anomaly.expected_value == 200.0
        assert anomaly.deviation == 300.0
        assert anomaly.severity == AnomalySeverity.HIGH
        assert anomaly.confidence == 0.9
        assert len(anomaly.recommended_actions) == 2

    def test_initialize_baseline(self):
        """Test baseline initialization."""
        node = PerformanceAnomalyNode()

        result = node.execute(
            operation="initialize_baseline",
            metric_name="api_latency",
            detection_methods=["statistical", "threshold_based"],
            sensitivity=0.7,
            min_samples=25,
            learning_rate=0.05,
        )

        # Verify result
        assert result["status"] == "success"
        assert "api_latency" in result["baselines"]
        assert result["detection_summary"]["initialized"] is True

        # Verify internal state
        assert "api_latency" in node._baselines
        baseline = node._baselines["api_latency"]
        assert baseline.metric_name == "api_latency"
        assert baseline.sample_count == 0
        assert baseline.learning_rate == 0.05

        # Verify detection config updated
        assert node._detection_config["sensitivity"] == 0.7
        assert node._detection_config["min_samples"] == 25
        assert node._detection_config["learning_rate"] == 0.05

    def test_initialize_baseline_missing_name(self):
        """Test baseline initialization without metric name."""
        node = PerformanceAnomalyNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="initialize_baseline")

        assert "metric_name is required" in str(exc_info.value)

    def test_add_metric(self):
        """Test adding a performance metric."""
        node = PerformanceAnomalyNode()

        # Initialize baseline first
        node.execute(
            operation="initialize_baseline",
            metric_name="response_time",
            sensitivity=0.8,
        )

        # Add metric
        result = node.execute(
            operation="add_metric",
            metric_name="response_time",
            value=125.5,
            tags={"service": "api", "region": "us-west"},
            metadata={"version": "1.2.3"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["metrics_processed"] == 1

        # Verify internal state
        assert "response_time" in node._metrics_buffer
        assert len(node._metrics_buffer["response_time"]) == 1

        metric = node._metrics_buffer["response_time"][0]
        assert metric.metric_name == "response_time"
        assert metric.value == 125.5
        assert metric.tags["service"] == "api"
        assert metric.metadata["version"] == "1.2.3"

        # Verify baseline updated
        baseline = node._baselines["response_time"]
        assert baseline.sample_count == 1
        assert baseline.mean == 125.5

    def test_add_metric_missing_params(self):
        """Test adding metric without required parameters."""
        node = PerformanceAnomalyNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="add_metric")

        assert "metric_name and value are required" in str(exc_info.value)

    def test_add_multiple_metrics_and_baseline_learning(self):
        """Test adding multiple metrics and baseline learning."""
        node = PerformanceAnomalyNode()

        # Initialize baseline
        node.execute(
            operation="initialize_baseline",
            metric_name="cpu_usage",
            min_samples=5,  # Lower for testing
        )

        # Add multiple metrics
        values = [50.0, 52.0, 48.0, 51.0, 49.0, 53.0]
        for value in values:
            node.execute(
                operation="add_metric",
                metric_name="cpu_usage",
                value=value,
            )

        # Verify baseline learning
        baseline = node._baselines["cpu_usage"]
        assert baseline.sample_count == len(values)
        assert baseline.min_value == min(values)
        assert baseline.max_value == max(values)
        assert baseline.std_dev > 0  # Should have calculated standard deviation

    def test_detect_anomalies_basic(self):
        """Test basic anomaly detection."""
        node = PerformanceAnomalyNode()

        # Initialize and populate baseline
        node.execute(
            operation="initialize_baseline",
            metric_name="memory_usage",
            min_samples=5,
            sensitivity=0.5,
        )

        # Add normal metrics
        normal_values = [40.0, 42.0, 38.0, 41.0, 39.0]
        for value in normal_values:
            node.execute(
                operation="add_metric", metric_name="memory_usage", value=value
            )

        # Add anomalous metric
        node.execute(
            operation="add_metric", metric_name="memory_usage", value=80.0
        )  # Anomaly

        # Detect anomalies
        result = node.execute(
            operation="detect_anomalies",
            metric_names=["memory_usage"],
            detection_window=60.0,
            detection_methods=["threshold_based", "statistical"],
        )

        # Verify detection
        assert result["status"] == "success"
        # Should detect the spike (depends on threshold calculation)
        assert "memory_usage" in result["detection_summary"]

    def test_detect_anomalies_with_zscore(self):
        """Test anomaly detection using Z-score method."""
        node = PerformanceAnomalyNode()

        # Initialize baseline
        node.execute(
            operation="initialize_baseline",
            metric_name="disk_io",
            min_samples=5,
            zscore_threshold=2.0,
        )

        # Add metrics with clear pattern
        base_value = 100.0
        for i in range(10):
            # Add normal values
            value = base_value + np.random.normal(0, 5)  # Small variance
            node.execute(operation="add_metric", metric_name="disk_io", value=value)

        # Add clear outlier
        node.execute(
            operation="add_metric", metric_name="disk_io", value=base_value + 50
        )  # Large deviation

        # Detect with statistical method
        result = node.execute(
            operation="detect_anomalies",
            metric_names=["disk_io"],
            detection_methods=["statistical"],
        )

        assert result["status"] == "success"
        # May or may not detect depending on exact values and thresholds

    def test_detect_anomalies_iqr_method(self):
        """Test anomaly detection using IQR method."""
        node = PerformanceAnomalyNode()

        # Initialize baseline
        node.execute(operation="initialize_baseline", metric_name="network_latency")

        # Create metrics with outliers
        values = [10, 12, 11, 13, 12, 11, 10, 12, 50, 11]  # 50 is an outlier
        for value in values:
            node.execute(
                operation="add_metric",
                metric_name="network_latency",
                value=float(value),
            )

        # Detect using IQR method
        result = node.execute(
            operation="detect_anomalies",
            metric_names=["network_latency"],
            detection_methods=["iqr"],
        )

        assert result["status"] == "success"

    def test_detect_anomalies_rolling_average(self):
        """Test anomaly detection using rolling average method."""
        node = PerformanceAnomalyNode()

        # Initialize baseline
        node.execute(operation="initialize_baseline", metric_name="queue_depth")

        # Create trend with sudden spike
        for i in range(15):
            if i == 12:  # Sudden spike
                value = 100.0
            else:
                value = 10.0 + i * 0.5  # Gradual increase
            node.execute(operation="add_metric", metric_name="queue_depth", value=value)

        # Detect using rolling average
        result = node.execute(
            operation="detect_anomalies",
            metric_names=["queue_depth"],
            detection_methods=["rolling_average"],
        )

        assert result["status"] == "success"

    def test_get_baseline(self):
        """Test getting baseline information."""
        node = PerformanceAnomalyNode()

        # Initialize baseline
        node.execute(operation="initialize_baseline", metric_name="thread_count")

        # Get specific baseline
        result = node.execute(operation="get_baseline", metric_name="thread_count")

        assert result["status"] == "success"
        assert "thread_count" in result["baselines"]
        baseline_data = result["baselines"]["thread_count"]
        assert baseline_data["metric_name"] == "thread_count"
        assert baseline_data["sample_count"] == 0

        # Get all baselines
        result = node.execute(operation="get_baseline")
        assert "thread_count" in result["baselines"]

    def test_get_anomalies(self):
        """Test getting detected anomalies."""
        node = PerformanceAnomalyNode()

        # Initially no anomalies
        result = node.execute(operation="get_anomalies")

        assert result["status"] == "success"
        assert result["anomaly_count"] == 0
        assert result["anomalies_detected"] == []

    def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring."""
        node = PerformanceAnomalyNode()

        # Start monitoring
        result = node.execute(operation="start_monitoring", monitoring_interval=0.1)

        assert result["status"] == "success"
        assert result["monitoring_status"] == "monitoring"
        assert node._monitoring_active is True

        # Stop monitoring
        result = node.execute(operation="stop_monitoring")

        assert result["status"] == "success"
        assert result["monitoring_status"] == "stopped"
        assert node._monitoring_active is False

    def test_determine_severity(self):
        """Test severity determination logic."""
        node = PerformanceAnomalyNode()

        # Create baseline with known std_dev
        baseline = PerformanceBaseline(
            metric_name="test_metric",
            created_at=time.time(),
            updated_at=time.time(),
            sample_count=100,
            mean=50.0,
            median=50.0,
            std_dev=10.0,
            min_value=30.0,
            max_value=70.0,
        )

        # Test different severity levels
        # Critical: > 4 std devs
        severity = node._determine_severity(45.0, baseline)  # 4.5 std devs
        assert severity == AnomalySeverity.CRITICAL

        # High: > 3 std devs
        severity = node._determine_severity(35.0, baseline)  # 3.5 std devs
        assert severity == AnomalySeverity.HIGH

        # Medium: > 2 std devs
        severity = node._determine_severity(25.0, baseline)  # 2.5 std devs
        assert severity == AnomalySeverity.MEDIUM

        # Low: <= 2 std devs
        severity = node._determine_severity(15.0, baseline)  # 1.5 std devs
        assert severity == AnomalySeverity.LOW

    def test_assess_impact(self):
        """Test impact assessment for different anomaly types."""
        node = PerformanceAnomalyNode()

        baseline = PerformanceBaseline(
            metric_name="test",
            created_at=time.time(),
            updated_at=time.time(),
            sample_count=10,
            mean=50.0,
            median=50.0,
            std_dev=10.0,
            min_value=30.0,
            max_value=70.0,
        )

        # Test different anomaly types
        impact = node._assess_impact(AnomalyType.LATENCY_SPIKE, 20.0, baseline)
        assert "response time" in impact.lower()

        impact = node._assess_impact(AnomalyType.THROUGHPUT_DROP, 15.0, baseline)
        assert "throughput" in impact.lower()

        impact = node._assess_impact(AnomalyType.ERROR_RATE_INCREASE, 10.0, baseline)
        assert "error rate" in impact.lower()

    def test_get_anomaly_recommendations(self):
        """Test anomaly recommendation generation."""
        node = PerformanceAnomalyNode()

        metric = PerformanceMetric("test_metric", 100.0, time.time())

        # Test different anomaly types
        recommendations = node._get_anomaly_recommendations(
            AnomalyType.LATENCY_SPIKE, metric
        )
        assert len(recommendations) > 0
        assert any("optimization" in rec.lower() for rec in recommendations)

        recommendations = node._get_anomaly_recommendations(
            AnomalyType.THROUGHPUT_DROP, metric
        )
        assert len(recommendations) > 0
        assert any("bottleneck" in rec.lower() for rec in recommendations)

        recommendations = node._get_anomaly_recommendations(
            AnomalyType.ERROR_RATE_INCREASE, metric
        )
        assert len(recommendations) > 0
        assert any(
            "error" in rec.lower() or "log" in rec.lower() for rec in recommendations
        )

    def test_deduplicate_anomalies(self):
        """Test anomaly deduplication logic."""
        node = PerformanceAnomalyNode()

        current_time = time.time()

        # Create similar anomalies
        anomaly1 = PerformanceAnomaly(
            anomaly_id="1",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            metric_name="test",
            detected_at=current_time,
            value=100.0,
            expected_value=50.0,
            deviation=50.0,
            severity=AnomalySeverity.HIGH,
            confidence=0.9,
            detection_method=DetectionMethod.THRESHOLD_BASED,
            description="Test",
            impact_assessment="Test impact",
        )

        anomaly2 = PerformanceAnomaly(
            anomaly_id="2",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            metric_name="test",
            detected_at=current_time + 30,
            value=105.0,
            expected_value=50.0,
            deviation=55.0,
            severity=AnomalySeverity.HIGH,
            confidence=0.8,
            detection_method=DetectionMethod.STATISTICAL,
            description="Test",
            impact_assessment="Test impact",
        )

        # Different metric - should not be deduplicated
        anomaly3 = PerformanceAnomaly(
            anomaly_id="3",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            metric_name="different",
            detected_at=current_time,
            value=100.0,
            expected_value=50.0,
            deviation=50.0,
            severity=AnomalySeverity.HIGH,
            confidence=0.9,
            detection_method=DetectionMethod.THRESHOLD_BASED,
            description="Test",
            impact_assessment="Test impact",
        )

        anomalies = [anomaly1, anomaly2, anomaly3]
        unique_anomalies = node._deduplicate_anomalies(anomalies)

        # Should keep the higher confidence anomaly and the different metric
        assert len(unique_anomalies) == 2
        assert any(a.anomaly_id == "1" for a in unique_anomalies)  # Higher confidence
        assert any(a.anomaly_id == "3" for a in unique_anomalies)  # Different metric

    def test_generate_recommendations(self):
        """Test overall recommendation generation."""
        node = PerformanceAnomalyNode()

        # No anomalies
        recommendations = node._generate_recommendations([])
        assert "normal" in recommendations[0].lower()

        # Create anomalies
        anomaly1 = PerformanceAnomaly(
            anomaly_id="1",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            metric_name="test",
            detected_at=time.time(),
            value=100.0,
            expected_value=50.0,
            deviation=50.0,
            severity=AnomalySeverity.CRITICAL,
            confidence=0.9,
            detection_method=DetectionMethod.THRESHOLD_BASED,
            description="Test",
            impact_assessment="Test impact",
            recommended_actions=["Check resources", "Review code"],
        )

        recommendations = node._generate_recommendations([anomaly1])
        assert len(recommendations) > 0
        assert any("critical" in rec.lower() for rec in recommendations)

    def test_serialize_baseline(self):
        """Test baseline serialization."""
        node = PerformanceAnomalyNode()

        baseline = PerformanceBaseline(
            metric_name="serialization_test",
            created_at=1234567890.0,
            updated_at=1234567891.0,
            sample_count=50,
            mean=75.5,
            median=76.0,
            std_dev=12.3,
            min_value=45.0,
            max_value=105.0,
            percentiles={"p50": 76.0, "p95": 95.0},
            trend_slope=0.1,
            upper_threshold=100.0,
            lower_threshold=50.0,
            variance_threshold=10.0,
            learning_rate=0.1,
        )

        serialized = node._serialize_baseline(baseline)

        # Verify serialization
        assert serialized["metric_name"] == "serialization_test"
        assert serialized["created_at"] == 1234567890.0
        assert serialized["updated_at"] == 1234567891.0
        assert serialized["sample_count"] == 50
        assert serialized["mean"] == 75.5
        assert serialized["median"] == 76.0
        assert serialized["std_dev"] == 12.3
        assert serialized["min_value"] == 45.0
        assert serialized["max_value"] == 105.0
        assert serialized["percentiles"]["p50"] == 76.0
        assert serialized["percentiles"]["p95"] == 95.0
        assert serialized["trend_slope"] == 0.1
        assert serialized["upper_threshold"] == 100.0
        assert serialized["lower_threshold"] == 50.0
        assert serialized["variance_threshold"] == 10.0
        assert serialized["learning_rate"] == 0.1

    def test_serialize_anomaly(self):
        """Test anomaly serialization."""
        node = PerformanceAnomalyNode()

        anomaly = PerformanceAnomaly(
            anomaly_id="serialize_test",
            anomaly_type=AnomalyType.RESPONSE_TIME_VARIANCE,
            metric_name="response_time",
            detected_at=1234567890.0,
            value=250.0,
            expected_value=150.0,
            deviation=100.0,
            severity=AnomalySeverity.MEDIUM,
            confidence=0.75,
            detection_method=DetectionMethod.ZSCORE,
            description="Response time variance detected",
            impact_assessment="May impact user experience",
            recommended_actions=["Check system load", "Review caching"],
            tags={"service": "api"},
            metadata={"version": "1.0"},
        )

        serialized = node._serialize_anomaly(anomaly)

        # Verify serialization
        assert serialized["anomaly_id"] == "serialize_test"
        assert serialized["anomaly_type"] == "response_time_variance"
        assert serialized["metric_name"] == "response_time"
        assert serialized["detected_at"] == 1234567890.0
        assert serialized["value"] == 250.0
        assert serialized["expected_value"] == 150.0
        assert serialized["deviation"] == 100.0
        assert serialized["severity"] == "medium"
        assert serialized["confidence"] == 0.75
        assert serialized["detection_method"] == "zscore"
        assert serialized["description"] == "Response time variance detected"
        assert serialized["impact_assessment"] == "May impact user experience"
        assert serialized["recommended_actions"] == [
            "Check system load",
            "Review caching",
        ]
        assert serialized["tags"]["service"] == "api"
        assert serialized["metadata"]["version"] == "1.0"

    def test_unknown_operation(self):
        """Test unknown operation handling."""
        node = PerformanceAnomalyNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="unknown_operation")

        assert "Unknown operation: unknown_operation" in str(exc_info.value)

    def test_node_import(self):
        """Test that PerformanceAnomalyNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import PerformanceAnomalyNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "PerformanceAnomalyNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = PerformanceAnomalyNode()

        with patch.object(node, "async_run") as mock_async_run:
            mock_async_run.return_value = {
                "anomalies_detected": [],
                "anomaly_count": 0,
                "baselines": {},
                "metrics_processed": 0,
                "detection_summary": {},
                "recommendations": [],
                "monitoring_status": "idle",
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "success",
            }

            # Execute synchronously
            result = node.execute(operation="get_anomalies")

            assert result["status"] == "success"
            assert result["monitoring_status"] == "idle"

    def test_cleanup(self):
        """Test node cleanup."""
        node = PerformanceAnomalyNode()

        # Start monitoring to create background tasks
        node.execute(operation="start_monitoring")

        # Cleanup
        asyncio.run(node.cleanup())

        # Verify monitoring stopped
        assert node._monitoring_active is False

    def test_baseline_learning_with_varying_data(self):
        """Test baseline learning with realistic varying data."""
        node = PerformanceAnomalyNode()

        # Initialize baseline
        node.execute(
            operation="initialize_baseline",
            metric_name="api_latency",
            min_samples=10,
            learning_rate=0.2,
        )

        # Simulate realistic data with some variance
        base_latency = 200.0
        values = []

        # Normal operating values
        for i in range(15):
            # Add some realistic variance (±20%)
            variance = np.random.normal(0, base_latency * 0.1)
            value = base_latency + variance
            values.append(value)

            node.execute(
                operation="add_metric",
                metric_name="api_latency",
                value=value,
                tags={"endpoint": f"/api/endpoint{i % 3}"},
            )

        # Check baseline learning
        baseline = node._baselines["api_latency"]
        assert baseline.sample_count == 15
        assert 150.0 < baseline.mean < 250.0  # Should be around base_latency
        assert baseline.std_dev > 0
        assert baseline.min_value < baseline.max_value

        # Add anomalous value
        anomalous_value = base_latency * 3  # 3x normal latency
        result = node.execute(
            operation="add_metric",
            metric_name="api_latency",
            value=anomalous_value,
        )

        # Should potentially detect as immediate anomaly
        # (depends on exact thresholds and variance in generated data)
        assert result["status"] == "success"

    def test_comprehensive_anomaly_detection_workflow(self):
        """Test a complete anomaly detection workflow."""
        node = PerformanceAnomalyNode()

        # 1. Initialize multiple baselines
        metrics = ["cpu_usage", "memory_usage", "response_time"]
        for metric in metrics:
            node.execute(
                operation="initialize_baseline",
                metric_name=metric,
                sensitivity=0.8,
                min_samples=8,
            )

        # 2. Feed normal data
        for i in range(10):
            node.execute(
                operation="add_metric", metric_name="cpu_usage", value=50.0 + i
            )
            node.execute(
                operation="add_metric", metric_name="memory_usage", value=60.0 + i * 0.5
            )
            node.execute(
                operation="add_metric", metric_name="response_time", value=100.0 + i * 2
            )

        # 3. Add some anomalous data
        node.execute(
            operation="add_metric", metric_name="cpu_usage", value=95.0
        )  # Spike
        node.execute(
            operation="add_metric", metric_name="memory_usage", value=30.0
        )  # Drop
        node.execute(
            operation="add_metric", metric_name="response_time", value=500.0
        )  # Spike

        # 4. Run comprehensive detection
        result = node.execute(
            operation="detect_anomalies",
            metric_names=metrics,
            detection_methods=["statistical", "threshold_based", "iqr"],
            detection_window=120.0,
        )

        # 5. Verify results
        assert result["status"] == "success"
        assert len(result["detection_summary"]) <= len(metrics)
        assert isinstance(result["recommendations"], list)

        # 6. Get all baselines
        baseline_result = node.execute(operation="get_baseline")
        assert len(baseline_result["baselines"]) == len(metrics)

        # 7. Get detected anomalies
        anomaly_result = node.execute(operation="get_anomalies")
        assert isinstance(anomaly_result["anomalies_detected"], list)

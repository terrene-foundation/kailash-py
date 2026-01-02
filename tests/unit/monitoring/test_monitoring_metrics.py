"""
Unit tests for monitoring metrics system.

Tests Task 4.4: Monitoring & Alerting
- Metrics collection and aggregation
- Time-series data handling
- Validation, security, and performance metrics
- Metrics registry and export functionality
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from kailash.monitoring.metrics import (
    MetricPoint,
    MetricsCollector,
    MetricSeries,
    MetricSeverity,
    MetricsRegistry,
    MetricType,
    PerformanceMetrics,
    SecurityMetrics,
    ValidationMetrics,
    get_metrics_registry,
    get_performance_metrics,
    get_security_metrics,
    get_validation_metrics,
)


class TestMetricPoint:
    """Test metric data point functionality."""

    def test_metric_point_creation(self):
        """Test creating metric points."""
        timestamp = datetime.now(UTC)
        point = MetricPoint(
            timestamp=timestamp,
            value=42.5,
            labels={"node_type": "TestNode"},
            metadata={"source": "test"},
        )

        assert point.timestamp == timestamp
        assert point.value == 42.5
        assert point.labels["node_type"] == "TestNode"
        assert point.metadata["source"] == "test"


class TestMetricSeries:
    """Test metric series functionality."""

    def test_metric_series_creation(self):
        """Test creating metric series."""
        series = MetricSeries(
            name="test_metric",
            metric_type=MetricType.COUNTER,
            description="Test metric for validation",
            unit="count",
        )

        assert series.name == "test_metric"
        assert series.metric_type == MetricType.COUNTER
        assert series.description == "Test metric for validation"
        assert series.unit == "count"
        assert len(series.points) == 0

    def test_add_point(self):
        """Test adding data points to series."""
        series = MetricSeries("test", MetricType.GAUGE, "Test gauge")

        series.add_point(10.5, labels={"env": "test"})
        series.add_point(15.2, metadata={"source": "node1"})

        assert len(series.points) == 2
        assert series.points[0].value == 10.5
        assert series.points[0].labels["env"] == "test"
        assert series.points[1].value == 15.2
        assert series.points[1].metadata["source"] == "node1"

    def test_get_latest_value(self):
        """Test getting latest metric value."""
        series = MetricSeries("test", MetricType.GAUGE, "Test gauge")

        # No points
        assert series.get_latest_value() is None

        # Add points
        series.add_point(10.0)
        series.add_point(20.0)
        series.add_point(15.0)

        assert series.get_latest_value() == 15.0

    def test_get_average(self):
        """Test calculating average values."""
        series = MetricSeries("test", MetricType.TIMER, "Test timer")

        # No points
        assert series.get_average() is None

        # Add points
        series.add_point(10.0)
        series.add_point(20.0)
        series.add_point(30.0)

        assert series.get_average() == 20.0

    def test_get_max(self):
        """Test getting maximum values."""
        series = MetricSeries("test", MetricType.HISTOGRAM, "Test histogram")

        # No points
        assert series.get_max() is None

        # Add points
        series.add_point(5.0)
        series.add_point(25.0)
        series.add_point(15.0)

        assert series.get_max() == 25.0

    def test_get_rate(self):
        """Test calculating rate of change."""
        series = MetricSeries("test", MetricType.COUNTER, "Test counter")

        # Not enough points
        assert series.get_rate() is None

        series.add_point(1.0)
        assert series.get_rate() is None

        # Add more points with slight delay
        time.sleep(0.01)
        series.add_point(2.0)
        time.sleep(0.01)
        series.add_point(3.0)

        rate = series.get_rate(timedelta(seconds=1))
        assert rate is not None
        assert rate > 0  # Should be positive rate


class TestMetricsCollector:
    """Test base metrics collector."""

    def test_collector_creation(self):
        """Test creating metrics collector."""
        collector = MetricsCollector(max_series=50)

        assert collector.max_series == 50
        assert len(collector._metrics) == 0

    def test_create_metric(self):
        """Test creating new metrics."""
        collector = MetricsCollector()

        metric = collector.create_metric(
            "test_counter", MetricType.COUNTER, "Test counter metric", "requests"
        )

        assert metric.name == "test_counter"
        assert metric.metric_type == MetricType.COUNTER
        assert metric.description == "Test counter metric"
        assert metric.unit == "requests"
        assert "test_counter" in collector._metrics

    def test_increment_counter(self):
        """Test incrementing counter metrics."""
        collector = MetricsCollector()

        # First increment creates metric
        collector.increment("request_count", 1, labels={"endpoint": "/api"})

        metric = collector.get_metric("request_count")
        assert metric is not None
        assert metric.get_latest_value() == 1

        # Second increment
        collector.increment("request_count", 2)
        assert metric.get_latest_value() == 3

    def test_set_gauge(self):
        """Test setting gauge metrics."""
        collector = MetricsCollector()

        collector.set_gauge("memory_usage", 85.5, labels={"process": "kailash"})

        metric = collector.get_metric("memory_usage")
        assert metric is not None
        assert metric.get_latest_value() == 85.5
        assert metric.metric_type == MetricType.GAUGE

    def test_record_timer(self):
        """Test recording timer metrics."""
        collector = MetricsCollector()

        collector.record_timer("validation_time", 125.5, labels={"node": "TestNode"})

        metric = collector.get_metric("validation_time")
        assert metric is not None
        assert metric.get_latest_value() == 125.5
        assert metric.metric_type == MetricType.TIMER
        assert metric.unit == "milliseconds"

    def test_record_histogram(self):
        """Test recording histogram metrics."""
        collector = MetricsCollector()

        collector.record_histogram("response_size", 1024, labels={"api": "v1"})

        metric = collector.get_metric("response_size")
        assert metric is not None
        assert metric.get_latest_value() == 1024
        assert metric.metric_type == MetricType.HISTOGRAM

    def test_max_series_limit(self):
        """Test maximum series limit enforcement."""
        collector = MetricsCollector(max_series=2)

        # Add metrics up to limit
        collector.create_metric("metric1", MetricType.COUNTER, "First metric")
        collector.create_metric("metric2", MetricType.GAUGE, "Second metric")

        assert len(collector._metrics) == 2

        # Add third metric should remove oldest
        collector.create_metric("metric3", MetricType.TIMER, "Third metric")

        assert len(collector._metrics) == 2
        assert "metric3" in collector._metrics

    def test_clear_metrics(self):
        """Test clearing all metrics."""
        collector = MetricsCollector()

        collector.increment("test1")
        collector.set_gauge("test2", 50)

        assert len(collector.get_all_metrics()) == 2

        collector.clear_metrics()

        assert len(collector.get_all_metrics()) == 0


class TestValidationMetrics:
    """Test validation metrics collector."""

    def test_validation_metrics_initialization(self):
        """Test validation metrics initialization."""
        metrics = ValidationMetrics()

        # Check core metrics are created
        assert metrics.get_metric("validation_total") is not None
        assert metrics.get_metric("validation_success") is not None
        assert metrics.get_metric("validation_failure") is not None
        assert metrics.get_metric("validation_duration") is not None
        assert metrics.get_metric("validation_cache_hits") is not None
        assert metrics.get_metric("validation_cache_misses") is not None

    def test_record_validation_attempt(self):
        """Test recording validation attempts."""
        metrics = ValidationMetrics()

        # Record successful validation
        metrics.record_validation_attempt(
            "TestNode", success=True, duration_ms=25.5, cached=False
        )

        total_metric = metrics.get_metric("validation_total")
        success_metric = metrics.get_metric("validation_success")
        duration_metric = metrics.get_metric("validation_duration")
        cache_miss_metric = metrics.get_metric("validation_cache_misses")

        assert total_metric.get_latest_value() == 1
        assert success_metric.get_latest_value() == 1
        assert duration_metric.get_latest_value() == 25.5
        assert cache_miss_metric.get_latest_value() == 1

        # Record failed validation from cache
        metrics.record_validation_attempt(
            "OtherNode", success=False, duration_ms=5.0, cached=True
        )

        failure_metric = metrics.get_metric("validation_failure")
        cache_hit_metric = metrics.get_metric("validation_cache_hits")

        assert total_metric.get_latest_value() == 2
        assert failure_metric.get_latest_value() == 1
        assert cache_hit_metric.get_latest_value() == 1

    def test_get_success_rate(self):
        """Test calculating validation success rate."""
        metrics = ValidationMetrics()

        # Record some validations
        metrics.record_validation_attempt("Node1", success=True, duration_ms=10.0)
        metrics.record_validation_attempt("Node2", success=True, duration_ms=15.0)
        metrics.record_validation_attempt("Node3", success=False, duration_ms=20.0)

        success_rate = metrics.get_success_rate()
        assert success_rate == 2 / 3  # 2 successes out of 3 total

    def test_get_cache_hit_rate(self):
        """Test calculating cache hit rate."""
        metrics = ValidationMetrics()

        # Record some validations
        metrics.record_validation_attempt(
            "Node1", success=True, duration_ms=10.0, cached=True
        )
        metrics.record_validation_attempt(
            "Node2", success=True, duration_ms=15.0, cached=True
        )
        metrics.record_validation_attempt(
            "Node3", success=False, duration_ms=20.0, cached=False
        )

        hit_rate = metrics.get_cache_hit_rate()
        assert hit_rate == 2 / 3  # 2 hits out of 3 total


class TestSecurityMetrics:
    """Test security metrics collector."""

    def test_security_metrics_initialization(self):
        """Test security metrics initialization."""
        metrics = SecurityMetrics()

        # Check core security metrics are created
        assert metrics.get_metric("security_violations_total") is not None
        assert metrics.get_metric("sql_injection_attempts") is not None
        assert metrics.get_metric("code_injection_attempts") is not None
        assert metrics.get_metric("path_traversal_attempts") is not None
        assert metrics.get_metric("credential_exposure_attempts") is not None
        assert metrics.get_metric("blocked_connections") is not None

    def test_record_security_violation(self):
        """Test recording security violations."""
        metrics = SecurityMetrics()

        # Record SQL injection attempt
        metrics.record_security_violation(
            "sql_injection",
            MetricSeverity.CRITICAL,
            "DatabaseNode",
            {"query": "'; DROP TABLE users; --"},
        )

        violations_metric = metrics.get_metric("security_violations_total")
        sql_metric = metrics.get_metric("sql_injection_attempts")

        assert violations_metric.get_latest_value() == 1
        assert sql_metric.get_latest_value() == 1

        # Check labels
        latest_point = violations_metric.points[-1]
        assert latest_point.labels["violation_type"] == "sql_injection"
        assert latest_point.labels["severity"] == "critical"
        assert latest_point.labels["source"] == "DatabaseNode"

    def test_record_different_violation_types(self):
        """Test recording different types of security violations."""
        metrics = SecurityMetrics()

        # Record different violation types
        metrics.record_security_violation(
            "code_injection", MetricSeverity.HIGH, "PythonNode"
        )
        metrics.record_security_violation(
            "path_traversal", MetricSeverity.MEDIUM, "FileNode"
        )
        metrics.record_security_violation(
            "credential_exposure", MetricSeverity.CRITICAL, "APINode"
        )

        # Check specific counters
        assert metrics.get_metric("code_injection_attempts").get_latest_value() == 1
        assert metrics.get_metric("path_traversal_attempts").get_latest_value() == 1
        assert (
            metrics.get_metric("credential_exposure_attempts").get_latest_value() == 1
        )
        assert metrics.get_metric("security_violations_total").get_latest_value() == 3

    def test_record_blocked_connection(self):
        """Test recording blocked connections."""
        metrics = SecurityMetrics()

        metrics.record_blocked_connection(
            "malicious_input", "database", "SQL injection detected"
        )

        blocked_metric = metrics.get_metric("blocked_connections")
        assert blocked_metric.get_latest_value() == 1

        latest_point = blocked_metric.points[-1]
        assert latest_point.labels["source_node"] == "malicious_input"
        assert latest_point.labels["target_node"] == "database"
        assert latest_point.labels["reason"] == "SQL injection detected"

    def test_get_violation_rate(self):
        """Test calculating violation rate."""
        metrics = SecurityMetrics()

        # Add multiple violations with slight delays
        metrics.record_security_violation("sql_injection", MetricSeverity.HIGH, "Node1")
        time.sleep(0.01)
        metrics.record_security_violation(
            "code_injection", MetricSeverity.CRITICAL, "Node2"
        )

        rate = metrics.get_violation_rate(timedelta(seconds=1))
        assert rate is not None
        assert rate > 0

    def test_get_critical_violations(self):
        """Test counting critical violations."""
        metrics = SecurityMetrics()

        # Record violations with different severities
        metrics.record_security_violation(
            "sql_injection", MetricSeverity.CRITICAL, "Node1"
        )
        metrics.record_security_violation(
            "code_injection", MetricSeverity.MEDIUM, "Node2"
        )
        metrics.record_security_violation(
            "path_traversal", MetricSeverity.CRITICAL, "Node3"
        )

        critical_count = metrics.get_critical_violations()
        assert critical_count == 2


class TestPerformanceMetrics:
    """Test performance metrics collector."""

    def test_performance_metrics_initialization(self):
        """Test performance metrics initialization."""
        metrics = PerformanceMetrics()

        # Check core performance metrics are created
        assert metrics.get_metric("response_time") is not None
        assert metrics.get_metric("throughput") is not None
        assert metrics.get_metric("memory_usage") is not None
        assert metrics.get_metric("cpu_usage") is not None
        assert metrics.get_metric("error_rate") is not None
        assert metrics.get_metric("slow_operations") is not None

    def test_record_operation(self):
        """Test recording operations."""
        metrics = PerformanceMetrics()

        # Record successful operation
        metrics.record_operation("validation", 125.5, success=True)

        response_time_metric = metrics.get_metric("response_time")
        assert response_time_metric.get_latest_value() == 125.5

        # Record failed operation
        metrics.record_operation("validation", 250.0, success=False)

        error_rate_metric = metrics.get_metric("error_rate")
        assert error_rate_metric.get_latest_value() == 1

    def test_record_slow_operation(self):
        """Test recording slow operations."""
        metrics = PerformanceMetrics()

        # Record slow operation (>1000ms)
        metrics.record_operation("complex_validation", 1500.0, success=True)

        slow_ops_metric = metrics.get_metric("slow_operations")
        assert slow_ops_metric.get_latest_value() == 1

    def test_update_system_metrics(self):
        """Test updating system metrics."""
        metrics = PerformanceMetrics()

        metrics.update_system_metrics(memory_mb=512.5, cpu_percent=75.2, rps=150.0)

        assert metrics.get_metric("memory_usage").get_latest_value() == 512.5
        assert metrics.get_metric("cpu_usage").get_latest_value() == 75.2
        assert metrics.get_metric("throughput").get_latest_value() == 150.0

    def test_get_p95_response_time(self):
        """Test calculating 95th percentile response time."""
        metrics = PerformanceMetrics()

        # Record response times
        response_times = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        for rt in response_times:
            metrics.record_operation("test", rt, success=True)

        p95 = metrics.get_p95_response_time()
        assert p95 is not None
        assert p95 >= 90  # Should be high percentile value


class TestMetricsRegistry:
    """Test metrics registry functionality."""

    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = MetricsRegistry()

        assert len(registry._collectors) == 0

    def test_register_collector(self):
        """Test registering collectors."""
        registry = MetricsRegistry()
        collector = MetricsCollector()

        registry.register_collector("test", collector)

        assert registry.get_collector("test") is collector
        assert "test" in registry.get_all_collectors()

    def test_export_json(self):
        """Test JSON export."""
        registry = MetricsRegistry()
        collector = MetricsCollector()

        collector.increment("test_counter", 5)
        collector.set_gauge("test_gauge", 42.5)

        registry.register_collector("test", collector)

        json_export = registry.export_metrics("json")

        assert "test" in json_export
        assert "test_counter" in json_export
        assert "test_gauge" in json_export

    def test_export_prometheus(self):
        """Test Prometheus export."""
        registry = MetricsRegistry()
        collector = MetricsCollector()

        collector.increment("requests_total", 10)

        registry.register_collector("web", collector)

        prometheus_export = registry.export_metrics("prometheus")

        assert "# HELP kailash_web_requests_total" in prometheus_export
        assert "# TYPE kailash_web_requests_total" in prometheus_export
        assert "kailash_web_requests_total" in prometheus_export

    def test_unsupported_export_format(self):
        """Test unsupported export format."""
        registry = MetricsRegistry()

        with pytest.raises(ValueError, match="Unsupported format"):
            registry.export_metrics("xml")


class TestGlobalMetricsAccess:
    """Test global metrics access functions."""

    def test_get_metrics_registry(self):
        """Test getting global metrics registry."""
        registry = get_metrics_registry()

        assert isinstance(registry, MetricsRegistry)

        # Should return same instance
        registry2 = get_metrics_registry()
        assert registry is registry2

    def test_get_validation_metrics(self):
        """Test getting validation metrics collector."""
        validation_metrics = get_validation_metrics()

        assert isinstance(validation_metrics, ValidationMetrics)
        assert validation_metrics.get_metric("validation_total") is not None

    def test_get_security_metrics(self):
        """Test getting security metrics collector."""
        security_metrics = get_security_metrics()

        assert isinstance(security_metrics, SecurityMetrics)
        assert security_metrics.get_metric("security_violations_total") is not None

    def test_get_performance_metrics(self):
        """Test getting performance metrics collector."""
        performance_metrics = get_performance_metrics()

        assert isinstance(performance_metrics, PerformanceMetrics)
        assert performance_metrics.get_metric("response_time") is not None


class TestMetricsIntegration:
    """Test metrics integration scenarios."""

    def test_complete_validation_flow(self):
        """Test complete validation metrics flow."""
        metrics = get_validation_metrics()

        # Simulate validation workflow
        metrics.record_validation_attempt("NodeA", True, 15.0, cached=False)
        metrics.record_validation_attempt("NodeB", True, 8.0, cached=True)
        metrics.record_validation_attempt("NodeC", False, 25.0, cached=False)

        # Check aggregated metrics
        assert metrics.get_success_rate() == 2 / 3
        assert metrics.get_cache_hit_rate() == 1 / 3

        total_metric = metrics.get_metric("validation_total")
        assert total_metric.get_latest_value() == 3

    def test_security_monitoring_flow(self):
        """Test security monitoring flow."""
        metrics = get_security_metrics()

        # Simulate security events
        metrics.record_security_violation(
            "sql_injection", MetricSeverity.CRITICAL, "DB1"
        )
        metrics.record_blocked_connection("malicious", "target", "blocked")
        metrics.record_security_violation(
            "code_injection", MetricSeverity.HIGH, "Code1"
        )

        # Check security state
        violations = metrics.get_metric("security_violations_total")
        assert violations.get_latest_value() == 2

        blocked = metrics.get_metric("blocked_connections")
        assert blocked.get_latest_value() == 1

        critical_count = metrics.get_critical_violations()
        assert critical_count == 1

    def test_performance_monitoring_flow(self):
        """Test performance monitoring flow."""
        metrics = get_performance_metrics()

        # Simulate system load
        metrics.record_operation("fast_op", 50.0, True)
        metrics.record_operation("slow_op", 1200.0, True)  # Slow operation
        metrics.record_operation("failed_op", 100.0, False)

        metrics.update_system_metrics(256.0, 45.0, 100.0)

        # Check performance state
        slow_ops = metrics.get_metric("slow_operations")
        assert slow_ops.get_latest_value() == 1

        errors = metrics.get_metric("error_rate")
        assert errors.get_latest_value() == 1

        memory = metrics.get_metric("memory_usage")
        assert memory.get_latest_value() == 256.0

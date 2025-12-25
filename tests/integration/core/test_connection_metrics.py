"""Unit tests for connection metrics collection."""

import time
from unittest.mock import Mock, patch

import pytest
from kailash.core.monitoring.connection_metrics import (
    ConnectionMetricsCollector,
    ErrorCategory,
    HistogramData,
    MetricPoint,
    MetricsAggregator,
)


class TestConnectionMetricsCollector:
    """Test metrics collection functionality."""

    @pytest.fixture
    def collector(self):
        """Create test metrics collector."""
        return ConnectionMetricsCollector("test_pool", retention_minutes=5)

    def test_initial_state(self, collector):
        """Test collector starts with empty metrics."""
        assert collector.pool_name == "test_pool"
        assert collector.retention_minutes == 5

        metrics = collector.get_all_metrics()
        assert metrics["pool_name"] == "test_pool"
        assert all(v == 0 for v in metrics["counters"].values())

    def test_track_acquisition(self, collector):
        """Test connection acquisition tracking."""
        # Track multiple acquisitions with mocked time
        with patch("time.time") as mock_time:
            # First acquisition - simulate 10ms
            mock_time.return_value = 1000.0
            timer1 = collector.track_acquisition()
            timer1.__enter__()
            mock_time.return_value = 1000.01  # 10ms later
            timer1.__exit__(None, None, None)

            # Second acquisition - simulate 20ms
            mock_time.return_value = 1001.0
            timer2 = collector.track_acquisition()
            timer2.__enter__()
            mock_time.return_value = 1001.02  # 20ms later
            timer2.__exit__(None, None, None)

        # Check counters
        assert collector._counters["connections_acquired"] == 2

        # Check histogram
        hist = collector.get_histogram("connection_acquisition_ms")
        assert hist is not None
        assert hist.count == 2
        assert hist.min >= 9.99  # At least ~10ms (allowing for float precision)
        assert hist.max > hist.min

    def test_track_release(self, collector):
        """Test connection release tracking."""
        collector.track_release(reusable=True)
        collector.track_release(reusable=True)
        collector.track_release(reusable=False)

        assert collector._counters["connections_released"] == 3
        assert collector._counters["connections_reused"] == 2
        assert collector._counters["connections_discarded"] == 1

    def test_track_query(self, collector):
        """Test query execution tracking."""
        # Track different query types with mocked time
        with patch("time.time") as mock_time:
            # SELECT query - simulate 10ms
            mock_time.return_value = 1000.0
            timer1 = collector.track_query("SELECT", "users")
            timer1.__enter__()
            mock_time.return_value = 1000.01  # 10ms later
            timer1.__exit__(None, None, None)

            # INSERT query - simulate 20ms
            mock_time.return_value = 1001.0
            timer2 = collector.track_query("INSERT", "orders")
            timer2.__enter__()
            mock_time.return_value = 1001.02  # 20ms later
            timer2.__exit__(None, None, None)

            # UPDATE query - simulate 15ms
            mock_time.return_value = 1002.0
            timer3 = collector.track_query("UPDATE", "products")
            timer3.__enter__()
            mock_time.return_value = 1002.015  # 15ms later
            timer3.__exit__(None, None, None)

        # Check counters
        assert collector._counters["queries_total"] == 3
        assert collector._counters["queries_select"] == 1
        assert collector._counters["queries_insert"] == 1
        assert collector._counters["queries_update"] == 1

        # Check query summary
        summary = collector.get_query_summary()
        assert "SELECT:users" in summary
        assert summary["SELECT:users"]["count"] == 1
        assert summary["SELECT:users"]["avg_time_ms"] >= 9.99  # ~10ms (float precision)

    def test_track_query_error(self, collector):
        """Test query error tracking."""
        # Track different error types
        collector.track_query_error("SELECT", TimeoutError("Query timeout"))
        collector.track_query_error("INSERT", ConnectionError("Connection refused"))
        collector.track_query_error("UPDATE", ValueError("Invalid syntax"))

        # Check error counts
        assert collector._counters["query_errors"] == 3
        assert collector._counters["query_errors_select"] == 1

        # Check error summary
        error_summary = collector.get_error_summary()
        assert error_summary["total_errors"] == 3
        assert ErrorCategory.QUERY_TIMEOUT.value in error_summary["errors_by_category"]
        assert (
            ErrorCategory.CONNECTION_REFUSED.value
            in error_summary["errors_by_category"]
        )

    def test_update_pool_stats(self, collector):
        """Test pool statistics updates."""
        collector.update_pool_stats(active=5, idle=3, total=8)

        assert collector._gauges["pool_connections_active"] == 5
        assert collector._gauges["pool_connections_idle"] == 3
        assert collector._gauges["pool_connections_total"] == 8
        assert collector._gauges["pool_utilization"] == 5 / 8

    def test_track_health_check(self, collector):
        """Test health check tracking."""
        # Track successful checks
        collector.track_health_check(success=True, duration_ms=5.0)
        collector.track_health_check(success=True, duration_ms=6.0)
        collector.track_health_check(success=True, duration_ms=4.0)

        # Track failed check
        collector.track_health_check(success=False, duration_ms=100.0)

        # Check metrics
        assert collector._counters["health_checks_total"] == 4
        assert collector._counters["health_checks_success"] == 3
        assert collector._counters["health_checks_failed"] == 1
        assert collector._gauges["health_check_success_rate"] == 0.75

        # Check histogram
        hist = collector.get_histogram("health_check_duration_ms")
        assert hist.count == 4
        assert hist.min == 4.0
        assert hist.max == 100.0

    def test_error_categorization(self, collector):
        """Test error categorization logic."""
        # Test various error types
        errors = [
            (TimeoutError("Connection timeout"), ErrorCategory.CONNECTION_TIMEOUT),
            (ConnectionError("Connection refused"), ErrorCategory.CONNECTION_REFUSED),
            (ValueError("Authentication failed"), ErrorCategory.AUTHENTICATION_FAILED),
            (RuntimeError("Pool exhausted"), ErrorCategory.POOL_EXHAUSTED),
            (SyntaxError("Invalid syntax"), ErrorCategory.QUERY_ERROR),
            (Exception("Unknown error"), ErrorCategory.UNKNOWN),
        ]

        for error, expected_category in errors:
            category = collector._categorize_error(error)
            assert category == expected_category

    def test_time_series_data(self, collector):
        """Test time series data collection."""
        # Add some data points with mocked time
        with patch("time.time") as mock_time:
            base_time = 1000.0
            for i in range(5):
                mock_time.return_value = base_time + (i * 0.1)
                collector._record_time_series("test_metric", float(i))

            # Mock current time for retrieval (within the minute window)
            mock_time.return_value = base_time + 1.0  # 1 second later

            # Get recent data
            points = collector.get_time_series("test_metric", minutes=1)

        assert len(points) == 5
        assert all(isinstance(p, MetricPoint) for p in points)
        assert [p.value for p in points] == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_histogram_percentiles(self):
        """Test histogram percentile calculations."""
        values = list(range(100))  # 0-99
        hist = HistogramData.from_values(values)

        assert hist.count == 100
        assert hist.min == 0
        assert hist.max == 99
        assert hist.p50 == 50
        assert hist.p75 == 75
        assert hist.p90 == 90
        assert hist.p95 == 95
        assert hist.p99 == 99

    def test_export_prometheus(self, collector):
        """Test Prometheus format export."""
        # Add some metrics
        collector.track_release(reusable=True)
        collector.update_pool_stats(5, 3, 8)

        with collector.track_query("SELECT"):
            pass

        # Export
        prometheus_output = collector.export_prometheus()

        # Check format
        assert (
            "# TYPE connection_pool_connections_released counter" in prometheus_output
        )
        assert (
            'connection_pool_connections_released{pool="test_pool"} 1'
            in prometheus_output
        )
        assert "# TYPE connection_pool_pool_utilization gauge" in prometheus_output
        assert (
            'connection_pool_pool_utilization{pool="test_pool"} 0.625'
            in prometheus_output
        )

    def test_metrics_reset(self, collector):
        """Test metrics reset functionality."""
        # Add some metrics
        collector.track_release(reusable=True)
        collector.track_query_error("SELECT", Exception("test"))

        # Reset
        collector.reset()

        # Check everything is cleared
        assert all(v == 0 for v in collector._counters.values())
        assert all(v == 0.0 for v in collector._gauges.values())
        assert len(collector._histograms) == 0
        assert len(collector._errors) == 0


class TestMetricsAggregator:
    """Test metrics aggregation across pools."""

    @pytest.fixture
    def aggregator(self):
        """Create test aggregator."""
        return MetricsAggregator()

    def test_register_collector(self, aggregator):
        """Test collector registration."""
        collector1 = ConnectionMetricsCollector("pool1")
        collector2 = ConnectionMetricsCollector("pool2")

        aggregator.register_collector(collector1)
        aggregator.register_collector(collector2)

        assert len(aggregator._collectors) == 2
        assert "pool1" in aggregator._collectors
        assert "pool2" in aggregator._collectors

    def test_get_global_metrics(self, aggregator):
        """Test global metrics aggregation."""
        # Create collectors with data
        collector1 = ConnectionMetricsCollector("pool1")
        collector1._counters["queries_total"] = 100
        collector1._errors[ErrorCategory.QUERY_ERROR] = 5
        collector1._gauges["pool_connections_total"] = 10

        collector2 = ConnectionMetricsCollector("pool2")
        collector2._counters["queries_total"] = 200
        collector2._errors[ErrorCategory.CONNECTION_TIMEOUT] = 3
        collector2._gauges["pool_connections_total"] = 20

        aggregator.register_collector(collector1)
        aggregator.register_collector(collector2)

        # Get global metrics
        global_metrics = aggregator.get_global_metrics()

        assert global_metrics["total_pools"] == 2
        assert global_metrics["total_queries"] == 300
        assert global_metrics["total_errors"] == 8
        assert global_metrics["total_connections"] == 30
        assert global_metrics["global_error_rate"] == 8 / 300

    def test_export_all_prometheus(self, aggregator):
        """Test exporting all metrics in Prometheus format."""
        collector1 = ConnectionMetricsCollector("pool1")
        collector1._counters["queries_total"] = 100

        collector2 = ConnectionMetricsCollector("pool2")
        collector2._counters["queries_total"] = 200

        aggregator.register_collector(collector1)
        aggregator.register_collector(collector2)

        # Export all
        output = aggregator.export_all_prometheus()

        # Check both pools are included
        assert 'pool="pool1"' in output
        assert 'pool="pool2"' in output
        assert output.count('connection_pool_queries_total{pool="pool1"}') == 1
        assert output.count('connection_pool_queries_total{pool="pool2"}') == 1

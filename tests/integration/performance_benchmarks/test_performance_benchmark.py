"""
Test PerformanceBenchmarkNode functionality.

This module tests the performance benchmarking capabilities including:
- Latency measurement
- Throughput tracking
- Resource utilization monitoring
- Performance baselines
- Anomaly detection
- SLA compliance
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import psutil
import pytest

from kailash.nodes.monitoring.performance_benchmark import PerformanceBenchmarkNode


class TestPerformanceBenchmarkNode:
    """Test suite for PerformanceBenchmarkNode."""

    @pytest.fixture
    def benchmark_node(self):
        """Create a performance benchmark node instance."""
        return PerformanceBenchmarkNode(
            name="test_performance_benchmark",
            metrics_config={
                "latency": {
                    "enabled": True,
                    "percentiles": [50, 90, 95, 99],
                    "window_size": 300,  # 5 minutes
                    "threshold_ms": {"p50": 100, "p90": 200, "p95": 300, "p99": 500},
                },
                "throughput": {
                    "enabled": True,
                    "window_size": 60,  # 1 minute
                    "threshold_rps": 1000,
                    "min_threshold_rps": 100,
                },
                "resource_usage": {
                    "enabled": True,
                    "cpu_threshold": 80,
                    "memory_threshold": 85,
                    "disk_io_threshold": 90,
                    "network_threshold_mbps": 100,
                },
                "error_rate": {
                    "enabled": True,
                    "threshold_percent": 1.0,
                    "window_size": 300,
                },
            },
            sla_config={
                "availability": 99.9,
                "latency_p95": 200,
                "error_rate": 0.1,
                "measurement_period": "monthly",
            },
            storage_backend="prometheus",
            anomaly_detection={
                "enabled": True,
                "algorithm": "isolation_forest",
                "sensitivity": 0.8,
                "training_window_hours": 168,  # 1 week
            },
        )

    def test_initialization(self, benchmark_node):
        """Test node initialization."""
        assert benchmark_node.metadata.name == "test_performance_benchmark"
        assert benchmark_node.metrics_config["latency"]["enabled"] is True
        assert benchmark_node.sla_config["availability"] == 99.9
        assert benchmark_node.anomaly_detection["enabled"] is True
        assert benchmark_node.storage_backend == "prometheus"

    def test_get_parameters(self, benchmark_node):
        """Test parameter definition."""
        params = benchmark_node.get_parameters()

        assert "action" in params
        assert params["action"].required is True

        assert "metric_type" in params
        assert params["metric_type"].required is False

        assert "metric_data" in params
        assert params["metric_data"].required is False

        assert "time_range" in params
        assert params["time_range"].required is False

    def test_record_latency(self, benchmark_node):
        """Test latency metric recording."""
        # Record multiple latency measurements
        latencies = [85, 92, 110, 95, 88, 105, 98, 120, 95, 89]

        for latency in latencies:
            result = benchmark_node.execute(
                action="record",
                metric_type="latency",
                metric_data={
                    "value": latency,
                    "operation": "api_request",
                    "endpoint": "/api/users",
                    "method": "GET",
                    "status_code": 200,
                },
            )
            assert result["success"] is True

        # Get latency statistics
        stats_result = benchmark_node.execute(
            action="stats", metric_type="latency", time_range={"minutes": 5}
        )

        assert stats_result["success"] is True
        assert stats_result["count"] == 10
        assert stats_result["percentiles"]["p50"] > 0
        assert stats_result["percentiles"]["p90"] > stats_result["percentiles"]["p50"]
        assert stats_result["mean"] > 0
        assert stats_result["std_dev"] > 0

    def test_throughput_measurement(self, benchmark_node):
        """Test throughput measurement."""
        # Simulate requests over time
        start_time = time.time()
        request_count = 100

        for i in range(request_count):
            benchmark_node.execute(
                action="record",
                metric_type="throughput",
                metric_data={
                    "operation": "process_order",
                    "success": True,
                    "timestamp": start_time + (i * 0.01),  # 100 req/sec
                },
            )

        # Calculate throughput
        result = benchmark_node.execute(
            action="calculate", metric_type="throughput", time_range={"seconds": 10}
        )

        assert result["success"] is True
        assert result["throughput_rps"] > 0
        assert (
            result["throughput_rps"] <= 110
        )  # Should be around 100 req/sec, allow some variance
        assert result["total_requests"] == request_count
        assert "peak_rps" in result

    def test_resource_usage_monitoring(self, benchmark_node):
        """Test resource usage monitoring."""
        # Mock psutil for consistent test results
        with patch("psutil.cpu_percent") as mock_cpu:
            with patch("psutil.virtual_memory") as mock_memory:
                with patch("psutil.disk_io_counters") as mock_disk:
                    with patch("psutil.net_io_counters") as mock_network:
                        # Set mock values
                        mock_cpu.return_value = 65.5
                        mock_memory.return_value = MagicMock(percent=72.3)
                        mock_disk.return_value = MagicMock(
                            read_bytes=1000000, write_bytes=500000
                        )
                        mock_network.return_value = MagicMock(
                            bytes_sent=2000000, bytes_recv=3000000
                        )

                        result = benchmark_node.execute(
                            action="monitor", metric_type="resources"
                        )

        assert result["success"] is True
        assert result["cpu_percent"] == 65.5
        assert result["memory_percent"] == 72.3
        assert result["disk_io"]["read_mb"] > 0
        assert result["disk_io"]["write_mb"] > 0
        assert result["network"]["sent_mb"] > 0
        assert result["network"]["recv_mb"] > 0

        # Check threshold alerts
        assert result["cpu_alert"] is False  # 65.5 < 80
        assert result["memory_alert"] is False  # 72.3 < 85

    def test_error_rate_tracking(self, benchmark_node):
        """Test error rate calculation."""
        # Record mixed success/failure
        total_requests = 1000
        error_count = 8  # 0.8% error rate

        for i in range(total_requests):
            success = i >= error_count  # First 8 are errors

            result = benchmark_node.execute(
                action="record",
                metric_type="request",
                metric_data={
                    "operation": "api_call",
                    "success": success,
                    "status_code": 200 if success else 500,
                    "error": None if success else "Internal Server Error",
                },
            )

        # Calculate error rate
        error_result = benchmark_node.execute(
            action="calculate", metric_type="error_rate", time_range={"minutes": 5}
        )

        assert error_result["success"] is True
        assert error_result["total_requests"] == total_requests
        assert error_result["error_count"] == error_count
        assert error_result["error_rate_percent"] == 0.8
        assert error_result["sla_compliant"] is True  # 0.8% < 1.0% threshold

    def test_performance_baseline(self, benchmark_node):
        """Test performance baseline establishment."""
        # Generate baseline data
        baseline_data = {
            "latency": {"p50": 95, "p90": 150, "p95": 180, "p99": 250},
            "throughput": {"average_rps": 850, "peak_rps": 1200, "min_rps": 500},
            "error_rate": 0.05,
            "resource_usage": {
                "avg_cpu": 45,
                "avg_memory": 60,
                "peak_cpu": 75,
                "peak_memory": 80,
            },
        }

        # Set baseline
        result = benchmark_node.execute(
            action="set_baseline",
            metric_data=baseline_data,
            options={
                "name": "v2.0_baseline",
                "description": "Baseline after optimization",
            },
        )

        assert result["success"] is True
        assert result["baseline_id"] is not None
        assert result["baseline_name"] == "v2.0_baseline"

        # Compare current performance to baseline
        compare_result = benchmark_node.execute(
            action="compare_baseline", options={"baseline_id": result["baseline_id"]}
        )

        assert compare_result["success"] is True
        assert "latency_diff" in compare_result
        assert "throughput_diff" in compare_result
        assert "improvement_areas" in compare_result

    def test_anomaly_detection(self, benchmark_node):
        """Test performance anomaly detection."""
        # Train anomaly detector with normal data
        normal_latencies = np.random.normal(100, 10, 1000)  # Mean 100ms, std 10ms

        for latency in normal_latencies[:800]:  # Use 80% for training
            benchmark_node.execute(
                action="record",
                metric_type="latency",
                metric_data={"value": float(latency), "operation": "normal"},
            )

        # Train model
        train_result = benchmark_node.execute(
            action="train_anomaly_detector", options={"retrain": True}
        )

        assert train_result["success"] is True
        assert train_result["samples_used"] >= 800

        # Test with anomalous data
        anomaly_latencies = [500, 600, 1000, 50, 45, 800]  # Outliers

        anomalies_detected = 0
        for latency in anomaly_latencies:
            result = benchmark_node.execute(
                action="detect_anomaly",
                metric_type="latency",
                metric_data={"value": latency},
            )

            if result["is_anomaly"]:
                anomalies_detected += 1

        assert anomalies_detected >= 4  # Should detect most anomalies

    def test_sla_compliance_check(self, benchmark_node):
        """Test SLA compliance monitoring."""
        # Mock historical data
        with patch.object(benchmark_node, "_get_historical_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "availability": 99.95,
                "latency_p95": 185,
                "error_rate": 0.08,
                "uptime_seconds": 2592000,  # 30 days
                "total_requests": 10000000,
                "failed_requests": 8000,
            }

            result = benchmark_node.execute(
                action="sla_report", time_range={"days": 30}
            )

        assert result["success"] is True
        assert result["sla_met"] is True
        assert result["metrics"]["availability"]["value"] == 99.95
        assert result["metrics"]["availability"]["target"] == 99.9
        assert result["metrics"]["availability"]["compliant"] is True

        assert result["metrics"]["latency_p95"]["value"] == 185
        assert result["metrics"]["latency_p95"]["target"] == 200
        assert result["metrics"]["latency_p95"]["compliant"] is True

        assert result["overall_compliance"] is True

    def test_performance_trends(self, benchmark_node):
        """Test performance trend analysis."""
        # Generate trending data
        hours = 24
        base_latency = 100

        for hour in range(hours):
            # Simulate daily pattern (higher latency during peak hours)
            if 9 <= hour <= 17:  # Business hours
                latency = base_latency * 1.5 + np.random.normal(0, 10)
            else:
                latency = base_latency + np.random.normal(0, 5)

            benchmark_node.execute(
                action="record",
                metric_type="latency",
                metric_data={
                    "value": float(latency),
                    "timestamp": datetime.now(UTC) - timedelta(hours=hours - hour),
                },
            )

        # Analyze trends
        trend_result = benchmark_node.execute(
            action="analyze_trend", metric_type="latency", time_range={"hours": 24}
        )

        assert trend_result["success"] is True
        assert "trend_direction" in trend_result  # "increasing", "decreasing", "stable"
        assert "peak_periods" in trend_result
        assert len(trend_result["peak_periods"]) > 0
        assert "predictions" in trend_result

    def test_real_time_alerting(self, benchmark_node):
        """Test real-time performance alerting."""
        # Configure alerts
        alert_config = {
            "latency_spike": {
                "threshold_ms": 500,
                "duration_seconds": 30,
                "severity": "critical",
            },
            "throughput_drop": {
                "min_rps": 100,
                "duration_seconds": 60,
                "severity": "warning",
            },
            "error_rate_high": {
                "threshold_percent": 5.0,
                "duration_seconds": 120,
                "severity": "critical",
            },
        }

        benchmark_node.configure_alerts(alert_config)

        # Trigger latency spike
        for _ in range(10):
            result = benchmark_node.execute(
                action="record",
                metric_type="latency",
                metric_data={"value": 600},  # Above threshold
            )

        # Check alerts
        alerts_result = benchmark_node.execute(
            action="get_alerts", time_range={"minutes": 5}
        )

        assert alerts_result["success"] is True
        assert len(alerts_result["active_alerts"]) > 0

        latency_alert = next(
            (a for a in alerts_result["active_alerts"] if a["type"] == "latency_spike"),
            None,
        )
        assert latency_alert is not None
        assert latency_alert["severity"] == "critical"

    def test_benchmark_comparison(self, benchmark_node):
        """Test performance benchmark comparison."""
        # Create two benchmark runs
        benchmark1 = {
            "name": "before_optimization",
            "timestamp": datetime.now(UTC) - timedelta(days=7),
            "metrics": {
                "latency_p95": 250,
                "throughput_avg": 500,
                "error_rate": 0.5,
                "cpu_avg": 70,
            },
        }

        benchmark2 = {
            "name": "after_optimization",
            "timestamp": datetime.now(UTC),
            "metrics": {
                "latency_p95": 180,
                "throughput_avg": 800,
                "error_rate": 0.1,
                "cpu_avg": 50,
            },
        }

        # Store benchmarks
        benchmark_node.store_benchmark(benchmark1)
        benchmark_node.store_benchmark(benchmark2)

        # Compare benchmarks
        compare_result = benchmark_node.execute(
            action="compare_benchmarks",
            options={
                "benchmark1": "before_optimization",
                "benchmark2": "after_optimization",
            },
        )

        assert compare_result["success"] is True
        assert compare_result["improvements"]["latency_p95"] == 28.0  # 28% improvement
        assert (
            compare_result["improvements"]["throughput_avg"] == 60.0
        )  # 60% improvement
        assert compare_result["improvements"]["error_rate"] == 80.0  # 80% improvement
        assert compare_result["overall_improvement"] is True

    def test_capacity_planning(self, benchmark_node):
        """Test capacity planning based on performance data."""
        # Mock performance and growth data
        with patch.object(benchmark_node, "_get_growth_metrics") as mock_growth:
            mock_growth.return_value = {
                "daily_growth_rate": 0.02,  # 2% daily growth
                "peak_utilization": 0.75,
                "average_utilization": 0.55,
            }

            result = benchmark_node.execute(
                action="capacity_planning",
                options={"projection_days": 90, "target_utilization": 0.80},
            )

        assert result["success"] is True
        assert result["current_capacity"]["utilization"] == 0.55
        assert result["projected_capacity"]["days_until_limit"] > 0
        assert "scaling_recommendations" in result
        assert result["scaling_recommendations"]["increase_percent"] > 0

    def test_export_metrics(self, benchmark_node):
        """Test metrics export functionality."""
        # Generate some metrics
        for i in range(100):
            benchmark_node.execute(
                action="record",
                metric_type="latency",
                metric_data={"value": 100 + i % 50},
            )

        # Export metrics
        export_result = benchmark_node.execute(
            action="export",
            options={
                "format": "prometheus",
                "time_range": {"hours": 1},
                "include_metadata": True,
            },
        )

        assert export_result["success"] is True
        assert export_result["format"] == "prometheus"
        assert "metrics" in export_result
        assert len(export_result["metrics"]) > 0

        # Verify Prometheus format
        metric_line = export_result["metrics"][0]
        assert "latency_milliseconds" in metric_line
        assert "{" in metric_line  # Labels
        assert "}" in metric_line

    def test_performance_dashboard_data(self, benchmark_node):
        """Test dashboard data generation."""
        result = benchmark_node.execute(
            action="dashboard_data", time_range={"hours": 24}
        )

        assert result["success"] is True
        assert "widgets" in result

        # Verify dashboard widgets
        widget_types = [w["type"] for w in result["widgets"]]
        assert "latency_chart" in widget_types
        assert "throughput_gauge" in widget_types
        assert "error_rate_trend" in widget_types
        assert "resource_usage_heatmap" in widget_types
        assert "sla_compliance_scorecard" in widget_types

    def test_load_test_mode(self, benchmark_node):
        """Test load testing mode with synthetic load."""
        # Start load test
        load_test_result = benchmark_node.execute(
            action="load_test",
            options={
                "duration_seconds": 10,
                "target_rps": 1000,
                "ramp_up_seconds": 2,
                "scenario": "read_heavy",
            },
        )

        assert load_test_result["success"] is True
        assert load_test_result["test_id"] is not None
        assert load_test_result["status"] == "running"

        # Get load test results
        results = benchmark_node.execute(
            action="load_test_results", options={"test_id": load_test_result["test_id"]}
        )

        assert results["success"] is True
        assert "summary" in results
        assert results["summary"]["total_requests"] > 0
        assert "latency_distribution" in results["summary"]
        assert "error_types" in results["summary"]

    def test_integration_with_apm(self, benchmark_node):
        """Test integration with APM systems."""
        # Configure APM integration
        apm_config = {
            "provider": "datadog",
            "api_key": "test_key",
            "app_name": "test_app",
            "environment": "production",
        }

        result = benchmark_node.execute(action="configure_apm", options=apm_config)

        assert result["success"] is True
        assert result["apm_enabled"] is True

        # Verify metrics are tagged for APM
        metric_result = benchmark_node.execute(
            action="record", metric_type="latency", metric_data={"value": 100}
        )

        assert metric_result["apm_tags"]["app"] == "test_app"
        assert metric_result["apm_tags"]["env"] == "production"

    def test_custom_metrics(self, benchmark_node):
        """Test custom metric definitions."""
        # Define custom metric
        custom_metric = {
            "name": "cache_hit_rate",
            "type": "gauge",
            "unit": "percent",
            "aggregation": "average",
            "thresholds": {"low": 50, "target": 80, "high": 95},
        }

        define_result = benchmark_node.execute(
            action="define_metric", metric_data=custom_metric
        )

        assert define_result["success"] is True

        # Record custom metric
        record_result = benchmark_node.execute(
            action="record", metric_type="cache_hit_rate", metric_data={"value": 85}
        )

        assert record_result["success"] is True
        assert record_result["threshold_status"] == "good"  # 85 > 80 (target)

    def test_error_handling(self, benchmark_node):
        """Test error handling for various scenarios."""
        # Invalid action
        result = benchmark_node.execute(action="invalid_action")
        assert result["success"] is False
        assert "Unknown action" in result["error"]

        # Invalid metric type
        result = benchmark_node.execute(action="record", metric_type="invalid_metric")
        assert result["success"] is False
        assert "Unknown metric type" in result["error"]

        # Missing required data
        result = benchmark_node.execute(
            action="record",
            metric_type="latency",
            # Missing metric_data
        )
        assert result["success"] is False
        assert "metric_data required" in result["error"].lower()


@pytest.mark.asyncio
class TestPerformanceBenchmarkNodeAsync:
    """Test asynchronous operations if supported."""

    async def test_async_performance_monitoring(self):
        """Test async performance monitoring if implemented."""
        # This is a placeholder for future async implementation
        # Currently PerformanceBenchmarkNode is synchronous
        pass

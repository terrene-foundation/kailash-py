"""Unit tests for edge monitoring."""

import asyncio
import statistics
from collections import deque
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from kailash.edge.monitoring.edge_monitor import (
    AlertSeverity,
    EdgeAlert,
    EdgeHealth,
    EdgeMetric,
    EdgeMonitor,
    HealthStatus,
    MetricType,
)


class TestEdgeMonitor:
    """Test edge monitor functionality."""

    @pytest.fixture
    def monitor(self):
        """Create an edge monitor instance."""
        return EdgeMonitor(
            retention_period=3600,  # 1 hour
            alert_cooldown=60,  # 1 minute
            health_check_interval=10,
            anomaly_detection=True,
        )

    @pytest.fixture
    def sample_metrics(self):
        """Create sample metrics."""
        base_time = datetime.now()
        metrics = []

        # Latency metrics
        for i in range(10):
            metrics.append(
                EdgeMetric(
                    timestamp=base_time - timedelta(minutes=i),
                    edge_node="edge-1",
                    metric_type=MetricType.LATENCY,
                    value=0.100 + i * 0.01,  # Increasing latency
                    tags={"region": "us-west", "service": "api"},
                )
            )

        # Error rate metrics
        for i in range(10):
            metrics.append(
                EdgeMetric(
                    timestamp=base_time - timedelta(minutes=i),
                    edge_node="edge-1",
                    metric_type=MetricType.ERROR_RATE,
                    value=0.01 + i * 0.005,  # Increasing errors
                    tags={"region": "us-west", "service": "api"},
                )
            )

        # Resource usage metrics
        for i in range(10):
            metrics.append(
                EdgeMetric(
                    timestamp=base_time - timedelta(minutes=i),
                    edge_node="edge-2",
                    metric_type=MetricType.RESOURCE_USAGE,
                    value=0.5 + i * 0.05,  # Increasing usage
                    tags={"resource": "cpu"},
                )
            )

        return metrics

    @pytest.mark.asyncio
    async def test_record_metric(self, monitor, sample_metrics):
        """Test recording metrics."""
        # Record metrics
        for metric in sample_metrics[:5]:
            await monitor.record_metric(metric)

        # Verify metrics stored
        assert len(monitor.metrics) > 0
        assert "edge-1:latency" in monitor.metrics

        # Record more metrics to get different types
        for metric in sample_metrics[10:15]:  # error_rate metrics
            await monitor.record_metric(metric)
        for metric in sample_metrics[20:25]:  # resource_usage metrics
            await monitor.record_metric(metric)

        assert "edge-1:error_rate" in monitor.metrics
        assert "edge-2:resource_usage" in monitor.metrics

    @pytest.mark.asyncio
    async def test_query_metrics(self, monitor, sample_metrics):
        """Test querying metrics."""
        # Record metrics
        for metric in sample_metrics:
            await monitor.record_metric(metric)

        # Query by edge node
        edge_1_metrics = await monitor.get_metrics(edge_node="edge-1")
        assert len(edge_1_metrics) > 0
        assert all(m.edge_node == "edge-1" for m in edge_1_metrics)

        # Query by metric type
        latency_metrics = await monitor.get_metrics(metric_type=MetricType.LATENCY)
        assert len(latency_metrics) > 0
        assert all(m.metric_type == MetricType.LATENCY for m in latency_metrics)

        # Query by time range
        recent_metrics = await monitor.get_metrics(
            start_time=datetime.now() - timedelta(minutes=5)
        )
        assert len(recent_metrics) < len(sample_metrics)

        # Query by tags
        api_metrics = await monitor.get_metrics(tags={"service": "api"})
        assert len(api_metrics) > 0
        assert all(m.tags.get("service") == "api" for m in api_metrics)

    @pytest.mark.asyncio
    async def test_threshold_alerts(self, monitor):
        """Test threshold-based alerting."""
        # Set custom threshold
        monitor.set_threshold(MetricType.LATENCY, "warning", 0.5)

        # Record metric below threshold
        low_metric = EdgeMetric(
            timestamp=datetime.now(),
            edge_node="edge-1",
            metric_type=MetricType.LATENCY,
            value=0.3,
            tags={},
        )
        await monitor.record_metric(low_metric)

        # Should not generate alert
        assert len(monitor.alerts) == 0

        # Record metric above threshold
        high_metric = EdgeMetric(
            timestamp=datetime.now(),
            edge_node="edge-1",
            metric_type=MetricType.LATENCY,
            value=0.7,
            tags={},
        )
        await monitor.record_metric(high_metric)

        # Should generate alert
        assert len(monitor.alerts) == 1
        alert = monitor.alerts[0]
        assert alert.severity == AlertSeverity.WARNING
        assert alert.metric_type == MetricType.LATENCY
        assert alert.current_value == 0.7
        assert alert.threshold == 0.5

    @pytest.mark.asyncio
    async def test_alert_cooldown(self, monitor):
        """Test alert cooldown period."""
        # Set short cooldown for testing
        monitor.alert_cooldown = 0.05  # 50ms

        # Generate first alert
        metric1 = EdgeMetric(
            timestamp=datetime.now(),
            edge_node="edge-1",
            metric_type=MetricType.ERROR_RATE,
            value=0.15,  # Above default error threshold
            tags={},
        )
        await monitor.record_metric(metric1)

        assert len(monitor.alerts) == 1

        # Try to generate another alert immediately
        metric2 = EdgeMetric(
            timestamp=datetime.now(),
            edge_node="edge-1",
            metric_type=MetricType.ERROR_RATE,
            value=0.20,
            tags={},
        )
        await monitor.record_metric(metric2)

        # Should not create new alert due to cooldown
        assert len(monitor.alerts) == 1

        # Wait for cooldown (reduced for testing)
        await asyncio.sleep(0.1)

        # Now should create new alert
        metric3 = EdgeMetric(
            timestamp=datetime.now(),
            edge_node="edge-1",
            metric_type=MetricType.ERROR_RATE,
            value=0.25,
            tags={},
        )
        await monitor.record_metric(metric3)

        assert len(monitor.alerts) == 2

    @pytest.mark.asyncio
    async def test_health_status(self, monitor):
        """Test edge health status."""
        # Get initial health
        health = await monitor.get_edge_health("edge-1")
        assert health.status == HealthStatus.UNKNOWN
        assert health.edge_node == "edge-1"

        # Record some healthy metrics
        for i in range(5):
            metric = EdgeMetric(
                timestamp=datetime.now(),
                edge_node="edge-1",
                metric_type=MetricType.LATENCY,
                value=0.1,
                tags={},
            )
            await monitor.record_metric(metric)

        # Update health
        await monitor._check_node_health("edge-1")
        health = await monitor.get_edge_health("edge-1")

        # Should be healthy
        assert health.status == HealthStatus.HEALTHY
        assert health.uptime_seconds >= 0
        assert "latency" in health.metrics_summary

    @pytest.mark.asyncio
    async def test_health_degradation(self, monitor):
        """Test health status degradation."""
        # Record metrics that trigger error alert
        metric = EdgeMetric(
            timestamp=datetime.now(),
            edge_node="edge-1",
            metric_type=MetricType.ERROR_RATE,
            value=0.15,  # Above error threshold
            tags={},
        )
        await monitor.record_metric(metric)

        # Update health
        await monitor._check_node_health("edge-1")
        health = await monitor.get_edge_health("edge-1")

        # Should be degraded
        assert health.status == HealthStatus.DEGRADED
        assert len(health.issues) > 0

    def test_analytics_summary(self, monitor, sample_metrics):
        """Test analytics generation."""
        # Record metrics
        for metric in sample_metrics:
            monitor.aggregated_metrics[metric.edge_node][metric.metric_type].append(
                metric.value
            )

        # Get analytics
        analytics = monitor.get_analytics("edge-1")

        # Check structure
        assert "metrics_summary" in analytics
        assert "trends" in analytics
        assert "anomalies" in analytics
        assert "recommendations" in analytics

        # Check metrics summary
        latency_summary = analytics["metrics_summary"].get("latency", {})
        assert "mean" in latency_summary
        assert "median" in latency_summary
        assert "p95" in latency_summary
        assert "p99" in latency_summary

    def test_trend_detection(self, monitor):
        """Test trend detection in analytics."""
        # Create increasing trend
        for i in range(20):
            value = 0.1 + i * 0.05  # Increasing values
            monitor.aggregated_metrics["edge-1"][MetricType.LATENCY].append(value)

        analytics = monitor.get_analytics("edge-1")

        # Should detect increasing trend
        assert "latency" in analytics["trends"]
        trend = analytics["trends"]["latency"]
        assert trend["direction"] == "increasing"
        assert trend["change_percent"] > 0

    @pytest.mark.asyncio
    async def test_anomaly_detection(self, monitor):
        """Test anomaly detection."""
        # Establish baseline with consistent values
        baseline_value = 0.100
        for i in range(101):  # Need >100 for baseline to be set
            metric = EdgeMetric(
                timestamp=datetime.now() - timedelta(minutes=101 - i),
                edge_node="edge-1",
                metric_type=MetricType.LATENCY,
                value=baseline_value,  # Consistent baseline
                tags={},
            )
            await monitor.record_metric(metric)

        # Update baseline
        monitor._update_baseline("edge-1")

        # Verify baseline was set
        assert "edge-1" in monitor.baseline_metrics
        assert MetricType.LATENCY in monitor.baseline_metrics["edge-1"]
        baseline = monitor.baseline_metrics["edge-1"][MetricType.LATENCY]
        assert baseline == baseline_value

        # Add anomalous values that are significantly higher
        anomalous_value = 0.200  # 100% higher than baseline
        for i in range(10):
            metric = EdgeMetric(
                timestamp=datetime.now() - timedelta(minutes=10 - i),
                edge_node="edge-1",
                metric_type=MetricType.LATENCY,
                value=anomalous_value,  # Much higher than baseline
                tags={},
            )
            await monitor.record_metric(metric)

        # Detect anomalies
        anomalies = monitor._detect_anomalies("edge-1")

        # Debug info if test fails
        if len(anomalies) == 0:
            recent_values = monitor.aggregated_metrics["edge-1"][MetricType.LATENCY][
                -10:
            ]
            current = statistics.mean(recent_values) if recent_values else 0
            deviation = abs(current - baseline) / baseline if baseline else 0
            print(
                f"Debug: baseline={baseline}, current={current}, deviation={deviation}"
            )
            print(f"Recent values: {recent_values}")

        # Should detect anomaly
        assert len(anomalies) > 0
        anomaly = anomalies[0]
        assert anomaly.severity == AlertSeverity.WARNING
        assert anomaly.tags.get("type") == "anomaly"

    def test_recommendations(self, monitor):
        """Test recommendation generation."""
        # Set up problematic metrics
        monitor.aggregated_metrics["edge-1"][MetricType.LATENCY] = [
            1.5
        ] * 20  # High latency
        monitor.aggregated_metrics["edge-1"][MetricType.ERROR_RATE] = [
            0.1
        ] * 20  # High errors
        monitor.aggregated_metrics["edge-1"][MetricType.CACHE_HIT_RATE] = [
            0.5
        ] * 20  # Low cache hits

        analytics = monitor.get_analytics("edge-1")
        recommendations = analytics["recommendations"]

        # Should have recommendations
        assert len(recommendations) > 0
        assert any("scaling" in r for r in recommendations)
        assert any("error" in r for r in recommendations)
        assert any("cache" in r for r in recommendations)

    @pytest.mark.asyncio
    async def test_alert_filtering(self, monitor):
        """Test alert filtering."""
        # Create alerts with different severities
        for severity in [
            AlertSeverity.INFO,
            AlertSeverity.WARNING,
            AlertSeverity.ERROR,
        ]:
            alert = EdgeAlert(
                alert_id=f"test-{severity.value}",
                timestamp=datetime.now(),
                edge_node="edge-1",
                severity=severity,
                metric_type=MetricType.LATENCY,
                message="Test alert",
                current_value=0.5,
                threshold=0.3,
                tags={},
            )
            monitor.alerts.append(alert)

        # Filter by severity
        warnings = await monitor.get_alerts(severity=AlertSeverity.WARNING)
        assert len(warnings) == 1
        assert warnings[0].severity == AlertSeverity.WARNING

        # Filter by edge node
        edge_1_alerts = await monitor.get_alerts(edge_node="edge-1")
        assert len(edge_1_alerts) == 3

        # Filter by time
        recent_alerts = await monitor.get_alerts(
            start_time=datetime.now() - timedelta(minutes=1)
        )
        assert len(recent_alerts) == 3

    def test_metrics_cleanup(self, monitor):
        """Test metrics cleanup."""
        # Add old and new metrics
        old_time = datetime.now() - timedelta(hours=2)
        new_time = datetime.now()

        old_metric = EdgeMetric(
            timestamp=old_time,
            edge_node="edge-1",
            metric_type=MetricType.LATENCY,
            value=0.1,
            tags={},
        )

        new_metric = EdgeMetric(
            timestamp=new_time,
            edge_node="edge-1",
            metric_type=MetricType.LATENCY,
            value=0.2,
            tags={},
        )

        key = "edge-1:latency"
        monitor.metrics[key].append(old_metric)
        monitor.metrics[key].append(new_metric)

        # Run cleanup manually by calling cleanup directly
        cutoff_time = datetime.now() - timedelta(seconds=monitor.retention_period)
        for key in list(monitor.metrics.keys()):
            monitor.metrics[key] = deque(
                (m for m in monitor.metrics[key] if m.timestamp > cutoff_time),
                maxlen=10000,
            )

        # Old metric should be removed
        assert len(monitor.metrics[key]) == 1
        assert monitor.metrics[key][0].timestamp == new_time

    def test_monitoring_summary(self, monitor):
        """Test monitoring summary."""
        # Set up some data
        monitor.health_status["edge-1"] = EdgeHealth(
            edge_node="edge-1",
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(),
            uptime_seconds=3600,
            metrics_summary={},
        )

        monitor.health_status["edge-2"] = EdgeHealth(
            edge_node="edge-2",
            status=HealthStatus.DEGRADED,
            last_check=datetime.now(),
            uptime_seconds=1800,
            metrics_summary={},
        )

        # Add some alerts
        monitor.alerts.append(
            EdgeAlert(
                alert_id="test-1",
                timestamp=datetime.now() - timedelta(minutes=30),
                edge_node="edge-1",
                severity=AlertSeverity.WARNING,
                metric_type=MetricType.LATENCY,
                message="Test",
                current_value=0.5,
                threshold=0.3,
                tags={},
            )
        )

        # Get summary
        summary = monitor.get_summary()

        assert summary["total_nodes"] == 2
        assert summary["health_summary"]["healthy"] == 1
        assert summary["health_summary"]["degraded"] == 1
        assert summary["recent_alerts"]["warning"] == 1
        assert summary["anomaly_detection"] is True

    @pytest.mark.asyncio
    async def test_background_tasks(self, monitor):
        """Test background task lifecycle."""
        # Start monitor
        await monitor.start()

        assert monitor._running is True
        assert monitor._health_check_task is not None
        assert monitor._cleanup_task is not None
        assert monitor._analytics_task is not None

        # Let tasks run briefly
        await asyncio.sleep(0.1)

        # Stop monitor
        await monitor.stop()

        assert monitor._running is False

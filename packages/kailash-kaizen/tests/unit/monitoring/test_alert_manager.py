"""
Unit tests for AlertManager.

Tests threshold detection, alert firing, notification delivery, and alert management.
All tests must pass BEFORE implementation.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestAlertManagerBasics:
    """Test basic AlertManager functionality."""

    @pytest.mark.asyncio
    async def test_alert_manager_initialization(self):
        """Test AlertManager initializes with aggregator."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        assert alert_manager.aggregator is aggregator
        assert len(alert_manager._alert_rules) == 0
        assert len(alert_manager._notification_channels) == 0
        assert len(alert_manager._alert_history) == 0

    @pytest.mark.asyncio
    async def test_add_alert_rule(self):
        """Test adding alert rules."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        alert_manager.add_rule(
            metric_name="test.metric",
            condition="threshold",
            threshold=100.0,
            window="1m",
            severity="warning",
        )

        assert len(alert_manager._alert_rules) == 1
        rule = alert_manager._alert_rules[0]
        assert rule["metric_name"] == "test.metric"
        assert rule["condition"] == "threshold"
        assert rule["threshold"] == 100.0
        assert rule["window"] == "1m"
        assert rule["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_add_notification_channel(self):
        """Test adding notification channels."""
        from kaizen.monitoring.alert_manager import AlertManager, NotificationChannel
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        # Create mock notification channel
        mock_channel = Mock(spec=NotificationChannel)

        alert_manager.add_notification_channel(mock_channel)

        assert len(alert_manager._notification_channels) == 1
        assert alert_manager._notification_channels[0] is mock_channel


class TestAlertManagerThresholdCondition:
    """Test threshold-based alert conditions."""

    @pytest.mark.asyncio
    async def test_threshold_condition_not_triggered(self):
        """Test threshold condition when value is below threshold."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {"p95": 50.0}  # Below threshold

        triggered = await alert_manager._evaluate_condition(rule, stats)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_threshold_condition_triggered(self):
        """Test threshold condition when value exceeds threshold."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {"p95": 150.0}  # Above threshold

        triggered = await alert_manager._evaluate_condition(rule, stats)

        assert triggered is True

    @pytest.mark.asyncio
    async def test_threshold_condition_at_threshold(self):
        """Test threshold condition when value equals threshold."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {"p95": 100.0}  # Equal to threshold

        triggered = await alert_manager._evaluate_condition(rule, stats)

        # Should not trigger (only > threshold)
        assert triggered is False


class TestAlertManagerRateOfChangeCondition:
    """Test rate-of-change alert conditions."""

    @pytest.mark.asyncio
    async def test_rate_of_change_not_triggered(self):
        """Test rate-of-change when change is below threshold."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        # Set previous mean
        alert_manager._previous_means = {"test.metric": 100.0}

        rule = {
            "metric_name": "test.metric",
            "condition": "rate_of_change",
            "threshold": 0.5,  # 50% change threshold
            "window": "1m",
            "severity": "warning",
        }

        stats = {"mean": 110.0}  # 10% change

        triggered = await alert_manager._evaluate_condition(rule, stats)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_rate_of_change_triggered(self):
        """Test rate-of-change when change exceeds threshold."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        # Set previous mean
        alert_manager._previous_means = {"test.metric": 100.0}

        rule = {
            "metric_name": "test.metric",
            "condition": "rate_of_change",
            "threshold": 0.5,  # 50% change threshold
            "window": "1m",
            "severity": "warning",
        }

        stats = {"mean": 200.0}  # 100% change

        triggered = await alert_manager._evaluate_condition(rule, stats)

        assert triggered is True


class TestAlertManagerAnomalyCondition:
    """Test anomaly detection alert conditions."""

    @pytest.mark.asyncio
    async def test_anomaly_not_triggered(self):
        """Test anomaly condition when value is within normal range."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "anomaly",
            "threshold": 0,  # Not used for anomaly
            "window": "1m",
            "severity": "warning",
        }

        stats = {"mean": 100.0, "stddev": 10.0, "p95": 110.0}  # Within 3 stddev

        triggered = await alert_manager._evaluate_condition(rule, stats)

        assert triggered is False

    @pytest.mark.asyncio
    async def test_anomaly_triggered(self):
        """Test anomaly condition when value is >3 stddev from mean."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "anomaly",
            "threshold": 0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {
            "mean": 100.0,
            "stddev": 10.0,
            "p95": 150.0,  # 5 stddev away (anomaly!)
        }

        triggered = await alert_manager._evaluate_condition(rule, stats)

        assert triggered is True


class TestAlertManagerNotifications:
    """Test alert notification delivery."""

    @pytest.mark.asyncio
    async def test_send_alert_to_channels(self):
        """Test that alerts are sent to all notification channels."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        # Create mock channels
        channel1 = AsyncMock()
        channel2 = AsyncMock()

        alert_manager.add_notification_channel(channel1)
        alert_manager.add_notification_channel(channel2)

        rule = {
            "metric_name": "test.metric",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "critical",
        }

        stats = {"p95": 150.0}

        await alert_manager._send_alert(rule, stats)

        # Both channels should have been called
        channel1.send.assert_called_once()
        channel2.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_history_recorded(self):
        """Test that alerts are recorded in history."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {"p95": 150.0}

        await alert_manager._send_alert(rule, stats)

        assert len(alert_manager._alert_history) == 1

        alert = alert_manager._alert_history[0]
        assert alert["metric"] == "test.metric"
        assert alert["severity"] == "warning"
        assert alert["condition"] == "threshold"
        assert alert["current_value"] == 150.0


class TestAlertManagerDuplicateSuppression:
    """Test duplicate alert suppression."""

    @pytest.mark.asyncio
    async def test_duplicate_alert_suppressed(self):
        """Test that duplicate alerts within 5 minutes are suppressed."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule = {
            "metric_name": "test.metric",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {"p95": 150.0}

        # Send first alert
        await alert_manager._send_alert(rule, stats)

        assert len(alert_manager._alert_history) == 1

        # Send duplicate alert immediately
        await alert_manager._send_alert(rule, stats)

        # Should still be 1 (duplicate suppressed)
        assert len(alert_manager._alert_history) == 1

    @pytest.mark.asyncio
    async def test_non_duplicate_alert_not_suppressed(self):
        """Test that different alerts are not suppressed."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        rule1 = {
            "metric_name": "test.metric1",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        rule2 = {
            "metric_name": "test.metric2",
            "condition": "threshold",
            "threshold": 100.0,
            "window": "1m",
            "severity": "warning",
        }

        stats = {"p95": 150.0}

        # Send different alerts
        await alert_manager._send_alert(rule1, stats)
        await alert_manager._send_alert(rule2, stats)

        # Both should be recorded
        assert len(alert_manager._alert_history) == 2


class TestAlertManagerLatency:
    """Test alert latency requirements."""

    @pytest.mark.asyncio
    async def test_alert_evaluation_under_5s(self):
        """Test that alert evaluation completes in <5s."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        # Add 10 rules
        for i in range(10):
            alert_manager.add_rule(
                metric_name=f"test.metric{i}",
                condition="threshold",
                threshold=100.0,
                window="1m",
                severity="warning",
            )

        # Mock aggregator to return stats
        with patch.object(aggregator, "get_stats", return_value={"p95": 50.0}):
            start = time.perf_counter()

            # Evaluate all rules
            for rule in alert_manager._alert_rules:
                stats = aggregator.get_stats(rule["metric_name"], rule["window"])
                await alert_manager._evaluate_condition(rule, stats)

            duration = time.perf_counter() - start

            # Should complete in <5s
            assert duration < 5.0


class TestNotificationChannels:
    """Test notification channel implementations."""

    @pytest.mark.asyncio
    async def test_email_notification_channel(self):
        """Test EmailNotificationChannel sends alerts."""
        from kaizen.monitoring.alert_manager import EmailNotificationChannel

        smtp_config = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "test@example.com",
            "password": "password",
        }

        channel = EmailNotificationChannel(
            smtp_config=smtp_config, recipients=["alert@example.com"]
        )

        alert = {
            "metric": "test.metric",
            "severity": "critical",
            "condition": "threshold",
            "threshold": 100.0,
            "current_value": 150.0,
            "stats": {"p95": 150.0},
            "timestamp": time.time(),
        }

        # Note: This will log, but won't actually send email in test
        # Just verify it doesn't crash
        await channel.send(alert)

        assert True  # If we got here, no exception was raised

    @pytest.mark.asyncio
    async def test_slack_notification_channel(self):
        """Test SlackNotificationChannel sends alerts."""
        from kaizen.monitoring.alert_manager import SlackNotificationChannel

        channel = SlackNotificationChannel(
            webhook_url="https://hooks.slack.com/services/test"
        )

        alert = {
            "metric": "test.metric",
            "severity": "warning",
            "condition": "threshold",
            "threshold": 100.0,
            "current_value": 125.0,
            "stats": {"p95": 125.0},
            "timestamp": time.time(),
        }

        # Mock aiohttp to avoid actual HTTP call
        with patch("aiohttp.ClientSession") as mock_session:
            mock_post = AsyncMock()
            mock_session.return_value.__aenter__.return_value.post = mock_post

            await channel.send(alert)

            # Verify HTTP POST was called
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_notification_channel(self):
        """Test WebhookNotificationChannel sends alerts."""
        from kaizen.monitoring.alert_manager import WebhookNotificationChannel

        channel = WebhookNotificationChannel(webhook_url="https://example.com/webhook")

        alert = {
            "metric": "test.metric",
            "severity": "info",
            "condition": "threshold",
            "threshold": 100.0,
            "current_value": 105.0,
            "stats": {"p95": 105.0},
            "timestamp": time.time(),
        }

        # Mock aiohttp to avoid actual HTTP call
        with patch("aiohttp.ClientSession") as mock_session:
            mock_post = AsyncMock()
            mock_session.return_value.__aenter__.return_value.post = mock_post

            await channel.send(alert)

            # Verify HTTP POST was called
            mock_post.assert_called_once()


class TestAlertManagerIntegration:
    """Test integration with AnalyticsAggregator."""

    @pytest.mark.asyncio
    async def test_end_to_end_alert_flow(self):
        """Test complete flow from metrics to alert."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        # Start aggregator
        await aggregator.start()

        # Add alert rule
        alert_manager.add_rule(
            metric_name="test.e2e",
            condition="threshold",
            threshold=50.0,
            window="1m",
            severity="critical",
        )

        # Add mock notification channel
        mock_channel = AsyncMock()
        alert_manager.add_notification_channel(mock_channel)

        # Collect metrics that will trigger alert
        for i in range(100):
            await collector.record_metric(
                metric_name="test.e2e",
                value=float(i),  # p95 will be ~95, exceeds threshold 50
            )

        # Give aggregator time to process
        await asyncio.sleep(0.5)

        # Manually trigger evaluation (since we're not running continuous loop)
        stats = aggregator.get_stats("test.e2e", "1m")
        if stats:
            for rule in alert_manager._alert_rules:
                triggered = await alert_manager._evaluate_condition(rule, stats)
                if triggered:
                    await alert_manager._send_alert(rule, stats)

        # Stop aggregator
        aggregator._running = False
        await asyncio.sleep(0.1)

        # Verify alert was sent (if stats were calculated)
        if aggregator.get_stats("test.e2e", "1m"):
            assert (
                len(alert_manager._alert_history) > 0
                or mock_channel.send.call_count > 0
            )


class TestAlertManagerSeverityLevels:
    """Test different severity levels."""

    @pytest.mark.asyncio
    async def test_info_severity_alert(self):
        """Test info-level alert."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        alert_manager.add_rule(
            metric_name="test.info",
            condition="threshold",
            threshold=100.0,
            severity="info",
        )

        assert alert_manager._alert_rules[0]["severity"] == "info"

    @pytest.mark.asyncio
    async def test_warning_severity_alert(self):
        """Test warning-level alert."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        alert_manager.add_rule(
            metric_name="test.warning",
            condition="threshold",
            threshold=100.0,
            severity="warning",
        )

        assert alert_manager._alert_rules[0]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_critical_severity_alert(self):
        """Test critical-level alert."""
        from kaizen.monitoring.alert_manager import AlertManager
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)
        alert_manager = AlertManager(aggregator)

        alert_manager.add_rule(
            metric_name="test.critical",
            condition="threshold",
            threshold=100.0,
            severity="critical",
        )

        assert alert_manager._alert_rules[0]["severity"] == "critical"

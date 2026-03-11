"""
AlertManager: Threshold-based alerting with <5s latency.

This module provides alert rule evaluation and notification delivery
through multiple channels (email, Slack, webhook).
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List

from .analytics_aggregator import AnalyticsAggregator

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Abstract notification channel."""

    @abstractmethod
    async def send(self, alert: Dict):
        """Send alert notification."""
        pass


class EmailNotificationChannel(NotificationChannel):
    """Email notification channel."""

    def __init__(self, smtp_config: Dict, recipients: List[str]):
        """
        Initialize email channel.

        Args:
            smtp_config: SMTP configuration (host, port, username, password)
            recipients: List of email addresses
        """
        self.smtp_config = smtp_config
        self.recipients = recipients

    async def send(self, alert: Dict):
        """
        Send alert email.

        Args:
            alert: Alert dictionary
        """
        subject = (
            f"[{alert['severity'].upper()}] Kaizen Performance Alert: {alert['metric']}"
        )
        body = f"""
        Performance alert triggered:

        Metric: {alert['metric']}
        Severity: {alert['severity']}
        Condition: {alert['condition']}
        Threshold: {alert['threshold']}
        Current Value: {alert['current_value']}

        Statistics:
        {json.dumps(alert['stats'], indent=2)}

        Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(alert['timestamp']))}
        """

        # Log the alert (actual email sending would require SMTP setup)
        logger.info(f"Email alert: {subject}")
        logger.debug(f"Alert body: {body}")
        logger.info(f"Would send email to {self.recipients}")


class SlackNotificationChannel(NotificationChannel):
    """Slack webhook notification channel."""

    def __init__(self, webhook_url: str):
        """
        Initialize Slack channel.

        Args:
            webhook_url: Slack webhook URL
        """
        self.webhook_url = webhook_url

    async def send(self, alert: Dict):
        """
        Send alert to Slack.

        Args:
            alert: Alert dictionary
        """
        import aiohttp

        color = {"info": "#36a64f", "warning": "#ff9900", "critical": "#ff0000"}.get(
            alert["severity"], "#808080"
        )

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"Performance Alert: {alert['metric']}",
                    "fields": [
                        {
                            "title": "Severity",
                            "value": alert["severity"],
                            "short": True,
                        },
                        {
                            "title": "Condition",
                            "value": alert["condition"],
                            "short": True,
                        },
                        {
                            "title": "Threshold",
                            "value": str(alert["threshold"]),
                            "short": True,
                        },
                        {
                            "title": "Current Value",
                            "value": f"{alert['current_value']:.2f}",
                            "short": True,
                        },
                    ],
                    "timestamp": int(alert["timestamp"]),
                }
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=payload)
            logger.info("Sent Slack alert")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")


class WebhookNotificationChannel(NotificationChannel):
    """Generic webhook notification channel."""

    def __init__(self, webhook_url: str):
        """
        Initialize webhook channel.

        Args:
            webhook_url: Webhook URL
        """
        self.webhook_url = webhook_url

    async def send(self, alert: Dict):
        """
        Send alert to webhook.

        Args:
            alert: Alert dictionary
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=alert)
            logger.info(f"Sent webhook alert to {self.webhook_url}")
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")


class AlertManager:
    """
    Threshold-based alerting with <5s latency.

    Features:
    - Rule-based alerts (threshold, rate of change, anomaly)
    - Multiple notification channels
    - Alert aggregation (prevent storms)
    - Configurable thresholds
    """

    def __init__(self, aggregator: AnalyticsAggregator):
        """
        Initialize alert manager.

        Args:
            aggregator: AnalyticsAggregator instance
        """
        self.aggregator = aggregator
        self._alert_rules: List[Dict] = []
        self._alert_history: List[Dict] = []
        self._notification_channels: List[NotificationChannel] = []
        self._previous_means: Dict[str, float] = {}

    def add_rule(
        self,
        metric_name: str,
        condition: str,  # 'threshold', 'rate_of_change', 'anomaly'
        threshold: float,
        window: str = "1m",
        severity: str = "warning",  # 'info', 'warning', 'critical'
    ):
        """
        Add alert rule.

        Args:
            metric_name: Name of the metric to monitor
            condition: Alert condition type
            threshold: Threshold value
            window: Time window for statistics
            severity: Alert severity level
        """
        self._alert_rules.append(
            {
                "metric_name": metric_name,
                "condition": condition,
                "threshold": threshold,
                "window": window,
                "severity": severity,
            }
        )

    def add_notification_channel(self, channel: NotificationChannel):
        """
        Add notification channel.

        Args:
            channel: NotificationChannel instance
        """
        self._notification_channels.append(channel)

    async def evaluate_rules(self):
        """Evaluate alert rules continuously."""
        while True:
            try:
                for rule in self._alert_rules:
                    stats = self.aggregator.get_stats(
                        rule["metric_name"], rule["window"]
                    )

                    if stats:  # Only evaluate if stats exist
                        triggered = await self._evaluate_condition(rule, stats)

                        if triggered:
                            await self._send_alert(rule, stats)

                await asyncio.sleep(5)  # Check every 5s

            except Exception as e:
                logger.error(f"Alert evaluation error: {e}")
                await asyncio.sleep(5)

    async def _evaluate_condition(self, rule: Dict, stats: Dict) -> bool:
        """
        Evaluate if alert condition is met.

        Args:
            rule: Alert rule dictionary
            stats: Statistics dictionary

        Returns:
            True if alert should be triggered
        """
        if rule["condition"] == "threshold":
            # Check if p95 exceeds threshold
            return stats.get("p95", 0) > rule["threshold"]

        elif rule["condition"] == "rate_of_change":
            # Check if rate of change exceeds threshold
            current = stats.get("mean", 0)
            previous = self._previous_means.get(rule["metric_name"], current)

            if previous > 0:
                change_rate = abs(current - previous) / previous
                # Update previous mean
                self._previous_means[rule["metric_name"]] = current
                return change_rate > rule["threshold"]

            # Update previous mean
            self._previous_means[rule["metric_name"]] = current
            return False

        elif rule["condition"] == "anomaly":
            # Check if value is anomalous (>3 stddev from mean)
            mean = stats.get("mean", 0)
            stddev = stats.get("stddev", 0)
            current = stats.get("p95", 0)

            if stddev > 0:
                return abs(current - mean) > (3 * stddev)

            return False

        return False

    async def _send_alert(self, rule: Dict, stats: Dict):
        """
        Send alert to all notification channels.

        Args:
            rule: Alert rule that triggered
            stats: Current statistics
        """
        alert = {
            "metric": rule["metric_name"],
            "severity": rule["severity"],
            "condition": rule["condition"],
            "threshold": rule["threshold"],
            "current_value": stats.get("p95", 0),
            "stats": stats,
            "timestamp": time.time(),
        }

        # Check if duplicate alert (aggregation)
        if self._is_duplicate_alert(alert):
            logger.debug(f"Suppressing duplicate alert for {rule['metric_name']}")
            return

        # Record alert
        self._alert_history.append(alert)

        # Send to all channels
        for channel in self._notification_channels:
            try:
                await channel.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {e}")

    def _is_duplicate_alert(self, alert: Dict) -> bool:
        """
        Check if alert is duplicate within 5 minutes.

        Args:
            alert: Alert to check

        Returns:
            True if duplicate
        """
        cutoff = time.time() - 300  # 5 minutes

        for prev_alert in reversed(self._alert_history):
            if prev_alert["timestamp"] < cutoff:
                break

            if (
                prev_alert["metric"] == alert["metric"]
                and prev_alert["condition"] == alert["condition"]
            ):
                return True

        return False

    def get_alert_history(self, limit: int = 100) -> List[Dict]:
        """
        Get recent alert history.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of recent alerts
        """
        return list(reversed(self._alert_history[-limit:]))

    def clear_alert_history(self):
        """Clear alert history."""
        self._alert_history.clear()

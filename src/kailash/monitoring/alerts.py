"""
Alerting system for monitoring validation failures and security violations.

Provides configurable alerting rules, notification channels, and alert management
for critical events in the Kailash SDK validation system.
"""

import json
import logging
import smtplib
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import requests

from .metrics import MetricSeries, MetricsRegistry

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status."""

    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"


@dataclass
class Alert:
    """Alert instance."""

    id: str
    rule_name: str
    severity: AlertSeverity
    title: str
    description: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    status: AlertStatus = AlertStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    fired_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    last_notification: Optional[datetime] = None
    notification_count: int = 0

    def fire(self):
        """Mark alert as firing."""
        if self.status != AlertStatus.FIRING:
            self.status = AlertStatus.FIRING
            self.fired_at = datetime.now(UTC)

    def resolve(self):
        """Mark alert as resolved."""
        if self.status == AlertStatus.FIRING:
            self.status = AlertStatus.RESOLVED
            self.resolved_at = datetime.now(UTC)

    def silence(self):
        """Silence the alert."""
        self.status = AlertStatus.SILENCED

    def should_notify(self, notification_interval: timedelta) -> bool:
        """Check if alert should send notification."""
        if self.status != AlertStatus.FIRING:
            return False

        if self.last_notification is None:
            return True

        return datetime.now(UTC) - self.last_notification >= notification_interval

    def mark_notified(self):
        """Mark that notification was sent."""
        self.last_notification = datetime.now(UTC)
        self.notification_count += 1


@dataclass
class AlertRule:
    """Alert rule configuration."""

    name: str
    description: str
    severity: AlertSeverity
    metric_name: str
    condition: str  # e.g., "> 10", "< 0.95", "== 0"
    threshold: Union[int, float]
    time_window: timedelta = timedelta(minutes=5)
    evaluation_interval: timedelta = timedelta(minutes=1)
    notification_interval: timedelta = timedelta(minutes=15)
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def evaluate(self, metric_series: MetricSeries) -> bool:
        """Evaluate if alert condition is met.

        Args:
            metric_series: Metric series to evaluate

        Returns:
            True if alert condition is met
        """
        if not self.enabled:
            return False

        # Get metric value over time window
        if self.condition.startswith("rate"):
            # Rate-based condition
            value = metric_series.get_rate(self.time_window)
        elif self.condition.startswith("avg"):
            # Average-based condition
            value = metric_series.get_average(self.time_window)
        elif self.condition.startswith("max"):
            # Maximum-based condition
            value = metric_series.get_max(self.time_window)
        else:
            # Latest value condition
            value = metric_series.get_latest_value()

        if value is None:
            return False

        # Evaluate condition
        if "> " in self.condition:
            return value > self.threshold
        elif "< " in self.condition:
            return value < self.threshold
        elif ">= " in self.condition:
            return value >= self.threshold
        elif "<= " in self.condition:
            return value <= self.threshold
        elif "== " in self.condition:
            return value == self.threshold
        elif "!= " in self.condition:
            return value != self.threshold
        else:
            logger.warning(f"Unknown condition format: {self.condition}")
            return False


class NotificationChannel(ABC):
    """Base class for notification channels."""

    @abstractmethod
    def send_notification(self, alert: Alert, context: Dict[str, Any]) -> bool:
        """Send notification for alert.

        Args:
            alert: Alert to send notification for
            context: Additional context information

        Returns:
            True if notification was sent successfully
        """
        pass


class LogNotificationChannel(NotificationChannel):
    """Log-based notification channel."""

    def __init__(self, log_level: str = "ERROR"):
        """Initialize log notification channel.

        Args:
            log_level: Log level for notifications
        """
        self.log_level = getattr(logging, log_level.upper())

    def send_notification(self, alert: Alert, context: Dict[str, Any]) -> bool:
        """Send notification via logging."""
        message = (
            f"ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.description}"
        )
        logger.log(self.log_level, message)
        return True


class EmailNotificationChannel(NotificationChannel):
    """Email notification channel."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: List[str],
        use_tls: bool = True,
    ):
        """Initialize email notification channel.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            from_email: From email address
            to_emails: List of recipient email addresses
            use_tls: Whether to use TLS
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls

    def send_notification(self, alert: Alert, context: Dict[str, Any]) -> bool:
        """Send notification via email."""
        try:
            from email.mime.multipart import MimeMultipart
            from email.mime.text import MimeText

            msg = MimeMultipart()
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.title}"

            body = self._format_email_body(alert, context)
            msg.attach(MimeText(body, "html"))

            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.from_email, self.to_emails, msg.as_string())
            server.quit()

            return True
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False

    def _format_email_body(self, alert: Alert, context: Dict[str, Any]) -> str:
        """Format email body for alert."""
        return f"""
        <html>
        <body>
        <h2>Kailash SDK Alert: {alert.title}</h2>
        <p><strong>Severity:</strong> {alert.severity.value.upper()}</p>
        <p><strong>Status:</strong> {alert.status.value}</p>
        <p><strong>Description:</strong> {alert.description}</p>
        <p><strong>Created:</strong> {alert.created_at.isoformat()}</p>

        <h3>Labels:</h3>
        <ul>
        {"".join(f"<li><strong>{k}:</strong> {v}</li>" for k, v in alert.labels.items())}
        </ul>

        <h3>Context:</h3>
        <ul>
        {"".join(f"<li><strong>{k}:</strong> {v}</li>" for k, v in context.items())}
        </ul>
        </body>
        </html>
        """


class SlackNotificationChannel(NotificationChannel):
    """Slack notification channel."""

    def __init__(self, webhook_url: str, channel: str = "#alerts"):
        """Initialize Slack notification channel.

        Args:
            webhook_url: Slack webhook URL
            channel: Slack channel to send alerts to
        """
        self.webhook_url = webhook_url
        self.channel = channel

    def send_notification(self, alert: Alert, context: Dict[str, Any]) -> bool:
        """Send notification via Slack."""
        try:
            color_map = {
                AlertSeverity.INFO: "good",
                AlertSeverity.WARNING: "warning",
                AlertSeverity.ERROR: "danger",
                AlertSeverity.CRITICAL: "danger",
            }

            payload = {
                "channel": self.channel,
                "username": "Kailash SDK Monitor",
                "icon_emoji": ":warning:",
                "attachments": [
                    {
                        "color": color_map.get(alert.severity, "danger"),
                        "title": f"{alert.severity.value.upper()}: {alert.title}",
                        "text": alert.description,
                        "fields": [
                            {
                                "title": "Status",
                                "value": alert.status.value,
                                "short": True,
                            },
                            {
                                "title": "Created",
                                "value": alert.created_at.isoformat(),
                                "short": True,
                            },
                        ]
                        + [
                            {"title": k, "value": str(v), "short": True}
                            for k, v in {**alert.labels, **context}.items()
                        ],
                        "ts": int(alert.created_at.timestamp()),
                    }
                ],
            }

            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False


class WebhookNotificationChannel(NotificationChannel):
    """Generic webhook notification channel."""

    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None):
        """Initialize webhook notification channel.

        Args:
            webhook_url: Webhook URL
            headers: Optional HTTP headers
        """
        self.webhook_url = webhook_url
        self.headers = headers or {}

    def send_notification(self, alert: Alert, context: Dict[str, Any]) -> bool:
        """Send notification via webhook."""
        try:
            payload = {
                "alert": {
                    "id": alert.id,
                    "rule_name": alert.rule_name,
                    "severity": alert.severity.value,
                    "status": alert.status.value,
                    "title": alert.title,
                    "description": alert.description,
                    "labels": alert.labels,
                    "annotations": alert.annotations,
                    "created_at": alert.created_at.isoformat(),
                    "fired_at": alert.fired_at.isoformat() if alert.fired_at else None,
                },
                "context": context,
            }

            response = requests.post(
                self.webhook_url, json=payload, headers=self.headers, timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False


class AlertManager:
    """Alert manager for handling alerting rules and notifications."""

    def __init__(self, metrics_registry: MetricsRegistry):
        """Initialize alert manager.

        Args:
            metrics_registry: Metrics registry to monitor
        """
        self.metrics_registry = metrics_registry
        self.rules: Dict[str, AlertRule] = {}
        self.alerts: Dict[str, Alert] = {}
        self.notification_channels: List[NotificationChannel] = []
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def add_rule(self, rule: AlertRule):
        """Add an alerting rule.

        Args:
            rule: AlertRule to add
        """
        with self._lock:
            self.rules[rule.name] = rule

    def remove_rule(self, rule_name: str):
        """Remove an alerting rule.

        Args:
            rule_name: Name of rule to remove
        """
        with self._lock:
            if rule_name in self.rules:
                del self.rules[rule_name]

    def add_notification_channel(self, channel: NotificationChannel):
        """Add a notification channel.

        Args:
            channel: NotificationChannel to add
        """
        with self._lock:
            self.notification_channels.append(channel)

    def start(self):
        """Start the alert manager."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._thread = threading.Thread(target=self._evaluation_loop, daemon=True)
            self._thread.start()
            logger.info("Alert manager started")

    def stop(self):
        """Stop the alert manager."""
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=5)
            logger.info("Alert manager stopped")

    def _evaluation_loop(self):
        """Main evaluation loop for alert rules."""
        while self._running:
            try:
                self._evaluate_rules()
                self._process_notifications()
                time.sleep(10)  # Evaluate every 10 seconds
            except Exception as e:
                logger.error(f"Error in alert evaluation loop: {e}")

    def _evaluate_rules(self):
        """Evaluate all alert rules."""
        with self._lock:
            for rule in self.rules.values():
                if not rule.enabled:
                    continue

                try:
                    # Find matching metrics
                    for (
                        collector_name,
                        collector,
                    ) in self.metrics_registry.get_all_collectors().items():
                        metric_series = collector.get_metric(rule.metric_name)
                        if metric_series:
                            self._evaluate_rule(rule, metric_series, collector_name)
                except Exception as e:
                    logger.error(f"Error evaluating rule {rule.name}: {e}")

    def _evaluate_rule(
        self, rule: AlertRule, metric_series: MetricSeries, collector_name: str
    ):
        """Evaluate a single rule against a metric series."""
        alert_id = f"{rule.name}_{collector_name}"

        # Check if condition is met
        condition_met = rule.evaluate(metric_series)

        if condition_met:
            # Create or update alert
            if alert_id not in self.alerts:
                alert = Alert(
                    id=alert_id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    title=f"{rule.name} ({collector_name})",
                    description=rule.description,
                    labels={
                        **rule.labels,
                        "collector": collector_name,
                        "metric": rule.metric_name,
                    },
                    annotations=rule.annotations,
                )
                self.alerts[alert_id] = alert

            # Fire the alert
            self.alerts[alert_id].fire()
        else:
            # Resolve alert if it exists and is firing
            if (
                alert_id in self.alerts
                and self.alerts[alert_id].status == AlertStatus.FIRING
            ):
                self.alerts[alert_id].resolve()

    def _process_notifications(self):
        """Process notifications for firing alerts."""
        with self._lock:
            for alert in self.alerts.values():
                if alert.status != AlertStatus.FIRING:
                    continue

                rule = self.rules.get(alert.rule_name)
                if not rule:
                    continue

                if alert.should_notify(rule.notification_interval):
                    self._send_notifications(alert)

    def _send_notifications(self, alert: Alert):
        """Send notifications for an alert."""
        context = {
            "metric_value": self._get_current_metric_value(alert),
            "notification_count": alert.notification_count + 1,
            "time_since_created": str(datetime.now(UTC) - alert.created_at),
        }

        success = False
        for channel in self.notification_channels:
            try:
                if channel.send_notification(alert, context):
                    success = True
            except Exception as e:
                logger.error(
                    f"Failed to send notification via {type(channel).__name__}: {e}"
                )

        if success:
            alert.mark_notified()

    def _get_current_metric_value(self, alert: Alert) -> Optional[Union[int, float]]:
        """Get current metric value for alert context."""
        for collector in self.metrics_registry.get_all_collectors().values():
            metric_series = collector.get_metric(alert.labels.get("metric"))
            if metric_series:
                return metric_series.get_latest_value()
        return None

    def get_active_alerts(self) -> List[Alert]:
        """Get all active (firing) alerts."""
        with self._lock:
            return [
                alert
                for alert in self.alerts.values()
                if alert.status == AlertStatus.FIRING
            ]

    def get_all_alerts(self) -> List[Alert]:
        """Get all alerts."""
        with self._lock:
            return list(self.alerts.values())

    def silence_alert(self, alert_id: str):
        """Silence an alert.

        Args:
            alert_id: Alert ID to silence
        """
        with self._lock:
            if alert_id in self.alerts:
                self.alerts[alert_id].silence()

    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert (same as silence for now).

        Args:
            alert_id: Alert ID to acknowledge
        """
        self.silence_alert(alert_id)


def create_default_alert_rules() -> List[AlertRule]:
    """Create default alert rules for common scenarios."""
    return [
        # Validation failure rate
        AlertRule(
            name="high_validation_failure_rate",
            description="Validation failure rate is above 10%",
            severity=AlertSeverity.ERROR,
            metric_name="validation_failure",
            condition="rate > 0.1",
            threshold=0.1,
            time_window=timedelta(minutes=5),
            labels={"component": "validation"},
        ),
        # Security violations
        AlertRule(
            name="security_violations_detected",
            description="Security violations detected",
            severity=AlertSeverity.CRITICAL,
            metric_name="security_violations_total",
            condition="rate > 0",
            threshold=0,
            time_window=timedelta(minutes=1),
            notification_interval=timedelta(minutes=5),
            labels={"component": "security"},
        ),
        # High response time
        AlertRule(
            name="high_response_time",
            description="Average response time is above 1 second",
            severity=AlertSeverity.WARNING,
            metric_name="response_time",
            condition="avg > 1000",
            threshold=1000,
            time_window=timedelta(minutes=5),
            labels={"component": "performance"},
        ),
        # Low cache hit rate
        AlertRule(
            name="low_cache_hit_rate",
            description="Cache hit rate is below 80%",
            severity=AlertSeverity.WARNING,
            metric_name="validation_cache_hits",
            condition="rate < 0.8",
            threshold=0.8,
            time_window=timedelta(minutes=10),
            labels={"component": "cache"},
        ),
        # High memory usage
        AlertRule(
            name="high_memory_usage",
            description="Memory usage is above 90%",
            severity=AlertSeverity.ERROR,
            metric_name="memory_usage",
            condition="> 90",
            threshold=90,
            time_window=timedelta(minutes=2),
            labels={"component": "system"},
        ),
    ]

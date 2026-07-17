"""
Performance monitoring and analytics system for Kaizen AI framework.

This module provides real-time performance monitoring with:
- MetricsCollector: Lightweight metric collection (<1ms overhead)
- AnalyticsAggregator: Real-time windowed statistics
- AlertManager: Threshold-based alerting
- PerformanceDashboard: Web-based visualization
"""

from .alert_manager import (
    AlertManager,
    EmailNotificationChannel,
    NotificationChannel,
    SlackNotificationChannel,
    WebhookNotificationChannel,
)
from .analytics_aggregator import AnalyticsAggregator, TimeWindow
from .dashboard import (
    MonitoringDependencyError,
    PerformanceDashboard,
    create_dashboard_app,
)
from .metrics_collector import MetricsCollector

__all__ = [
    "MetricsCollector",
    "AnalyticsAggregator",
    "TimeWindow",
    "AlertManager",
    "NotificationChannel",
    "EmailNotificationChannel",
    "SlackNotificationChannel",
    "WebhookNotificationChannel",
    "PerformanceDashboard",
    "create_dashboard_app",
    "MonitoringDependencyError",
    "app",
]


def __getattr__(name: str):
    """Resolve the lazily-built FastAPI ``app`` (PEP 562).

    ``app`` is exported for backward compatibility but is NOT eagerly imported —
    it requires the optional ``server`` (FastAPI) extra. Importing
    ``kaizen.monitoring`` succeeds on a bare install; accessing
    ``kaizen.monitoring.app`` without FastAPI raises the typed
    :class:`MonitoringDependencyError` naming the remedy.
    """
    if name == "app":
        from . import dashboard

        return dashboard.app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

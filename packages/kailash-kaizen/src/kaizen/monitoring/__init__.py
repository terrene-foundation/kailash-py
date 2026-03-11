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
from .dashboard import PerformanceDashboard, app
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
    "app",
]

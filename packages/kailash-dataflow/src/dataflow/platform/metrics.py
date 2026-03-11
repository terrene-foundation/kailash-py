#!/usr/bin/env python3
"""
Prometheus Metrics Integration for DataFlow

Provides production-grade metrics export for monitoring systems:
- Connection pool metrics (size, utilization, in_use)
- Workflow execution metrics (count, duration, status)
- Counter, Gauge, and Histogram support
- Prometheus-compatible format

Critical for observability in production environments with monitoring
systems like Prometheus, Datadog, or Grafana.
"""

import logging
import threading
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MetricsExporter:
    """
    Metrics exporter for DataFlow monitoring.

    Collects and exposes metrics in a format compatible with
    Prometheus and other monitoring systems.

    Example:
        >>> exporter = MetricsExporter()
        >>> exporter.register_connection_pool_metrics(
        ...     pool_size=10, in_use=3, available=7, utilization=0.3
        ... )
        >>> metrics = exporter.get_metrics()
    """

    def __init__(self):
        """Initialize metrics exporter."""
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register_connection_pool_metrics(
        self, pool_size: int, in_use: int, available: int, utilization: float
    ) -> None:
        """
        Register connection pool metrics.

        Args:
            pool_size: Total pool size
            in_use: Connections currently in use
            available: Available connections
            utilization: Pool utilization ratio (0.0-1.0)
        """
        with self._lock:
            self._metrics["connection_pool_size"] = pool_size
            self._metrics["connection_pool_in_use"] = in_use
            self._metrics["connection_pool_available"] = available
            self._metrics["connection_pool_utilization"] = utilization

    def register_workflow_execution(
        self, workflow_name: str, duration_seconds: float, status: str
    ) -> None:
        """
        Register workflow execution metrics.

        Args:
            workflow_name: Name of the workflow
            duration_seconds: Execution duration in seconds
            status: Execution status (success/failure)
        """
        with self._lock:
            # Initialize counters if needed
            if "workflow_executions_total" not in self._metrics:
                self._metrics["workflow_executions_total"] = defaultdict(int)
            if "workflow_execution_duration_seconds" not in self._metrics:
                self._metrics["workflow_execution_duration_seconds"] = defaultdict(list)

            # Increment counter
            key = f"{workflow_name}_{status}"
            self._metrics["workflow_executions_total"][key] += 1

            # Record duration
            self._metrics["workflow_execution_duration_seconds"][workflow_name].append(
                duration_seconds
            )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all registered metrics.

        Returns:
            Dictionary of metric name to value
        """
        with self._lock:
            return self._metrics.copy()


class PrometheusMetrics:
    """
    Prometheus-compatible metrics collector.

    Provides Counter, Gauge, and Histogram metric types
    compatible with Prometheus exposition format.

    Example:
        >>> metrics = PrometheusMetrics()
        >>> metrics.increment_counter("requests_total", labels={"method": "GET"})
        >>> metrics.set_gauge("active_connections", 5, labels={"pool": "main"})
        >>> metrics.observe_histogram("request_duration", 0.5, labels={"endpoint": "/api"})
    """

    def __init__(self):
        """Initialize Prometheus metrics collector."""
        self._counters: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._histograms: Dict[str, Dict[str, list]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._lock = threading.Lock()

    def increment_counter(
        self, name: str, labels: Optional[Dict[str, str]] = None, value: int = 1
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name
            labels: Optional label dictionary
            value: Increment value (default: 1)
        """
        labels_key = self._labels_to_key(labels or {})
        with self._lock:
            self._counters[name][labels_key] += value

    def set_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Set a gauge metric value.

        Args:
            name: Metric name
            value: Gauge value
            labels: Optional label dictionary
        """
        labels_key = self._labels_to_key(labels or {})
        with self._lock:
            self._gauges[name][labels_key] = value

    def observe_histogram(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a histogram observation.

        Args:
            name: Metric name
            value: Observed value
            labels: Optional label dictionary
        """
        labels_key = self._labels_to_key(labels or {})
        with self._lock:
            self._histograms[name][labels_key].append(value)

    def get_counter_value(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> int:
        """
        Get current counter value.

        Args:
            name: Metric name
            labels: Optional label dictionary

        Returns:
            Current counter value
        """
        labels_key = self._labels_to_key(labels or {})
        with self._lock:
            return self._counters[name].get(labels_key, 0)

    def get_gauge_value(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        """
        Get current gauge value.

        Args:
            name: Metric name
            labels: Optional label dictionary

        Returns:
            Current gauge value
        """
        labels_key = self._labels_to_key(labels or {})
        with self._lock:
            return self._gauges[name].get(labels_key, 0.0)

    def get_histogram_stats(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Get histogram statistics.

        Args:
            name: Metric name
            labels: Optional label dictionary

        Returns:
            Dictionary with count and sum
        """
        labels_key = self._labels_to_key(labels or {})
        with self._lock:
            observations = self._histograms[name].get(labels_key, [])
            return {"count": len(observations), "sum": sum(observations)}

    @staticmethod
    def _labels_to_key(labels: Dict[str, str]) -> str:
        """
        Convert labels dictionary to string key.

        Args:
            labels: Label dictionary

        Returns:
            String key for label combination
        """
        if not labels:
            return ""
        # Sort for consistent key generation
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


__all__ = [
    "MetricsExporter",
    "PrometheusMetrics",
]

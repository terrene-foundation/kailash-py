"""
Metrics collection and aggregation for monitoring system.

Provides detailed metrics for validation failures, security violations,
and performance monitoring with time-series data collection.
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected."""

    COUNTER = "counter"  # Incrementing values
    GAUGE = "gauge"  # Current value
    HISTOGRAM = "histogram"  # Distribution of values
    TIMER = "timer"  # Time-based measurements


class MetricSeverity(Enum):
    """Severity levels for metrics."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MetricPoint:
    """Single metric data point."""

    timestamp: datetime
    value: Union[int, float]
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricSeries:
    """Time series of metric data points."""

    name: str
    metric_type: MetricType
    description: str
    unit: str = ""
    points: deque = field(default_factory=lambda: deque(maxlen=1000))

    def add_point(
        self,
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Add a new data point to the series."""
        point = MetricPoint(
            timestamp=datetime.now(UTC),
            value=value,
            labels=labels or {},
            metadata=metadata or {},
        )
        self.points.append(point)

    def get_latest_value(self) -> Optional[Union[int, float]]:
        """Get the most recent metric value."""
        return self.points[-1].value if self.points else None

    def get_average(self, time_window: Optional[timedelta] = None) -> Optional[float]:
        """Get average value over time window."""
        if not self.points:
            return None

        if time_window:
            cutoff = datetime.now(UTC) - time_window
            relevant_points = [p for p in self.points if p.timestamp >= cutoff]
        else:
            relevant_points = list(self.points)

        if not relevant_points:
            return None

        return sum(p.value for p in relevant_points) / len(relevant_points)

    def get_max(
        self, time_window: Optional[timedelta] = None
    ) -> Optional[Union[int, float]]:
        """Get maximum value over time window."""
        if not self.points:
            return None

        if time_window:
            cutoff = datetime.now(UTC) - time_window
            relevant_points = [p for p in self.points if p.timestamp >= cutoff]
        else:
            relevant_points = list(self.points)

        if not relevant_points:
            return None

        return max(p.value for p in relevant_points)

    def get_rate(
        self, time_window: timedelta = timedelta(minutes=1)
    ) -> Optional[float]:
        """Get rate of change over time window."""
        if len(self.points) < 2:
            return None

        cutoff = datetime.now(UTC) - time_window
        relevant_points = [p for p in self.points if p.timestamp >= cutoff]

        if len(relevant_points) < 2:
            return None

        # Calculate rate as points per second
        time_span = (
            relevant_points[-1].timestamp - relevant_points[0].timestamp
        ).total_seconds()
        if time_span == 0:
            return None

        return len(relevant_points) / time_span


class MetricsCollector:
    """Base metrics collector."""

    def __init__(self, max_series: int = 100):
        """Initialize metrics collector.

        Args:
            max_series: Maximum number of metric series to track
        """
        self.max_series = max_series
        self._metrics: Dict[str, MetricSeries] = {}
        self._lock = threading.RLock()

    def create_metric(
        self, name: str, metric_type: MetricType, description: str, unit: str = ""
    ) -> MetricSeries:
        """Create a new metric series.

        Args:
            name: Metric name
            metric_type: Type of metric
            description: Description of what this metric measures
            unit: Unit of measurement

        Returns:
            MetricSeries instance
        """
        with self._lock:
            if name in self._metrics:
                return self._metrics[name]

            if len(self._metrics) >= self.max_series:
                # Remove oldest metric
                oldest_metric = min(
                    self._metrics.values(),
                    key=lambda m: (
                        m.points[0].timestamp
                        if m.points
                        else datetime.min.replace(tzinfo=UTC)
                    ),
                )
                del self._metrics[oldest_metric.name]

            metric = MetricSeries(
                name=name, metric_type=metric_type, description=description, unit=unit
            )
            self._metrics[name] = metric
            return metric

    def increment(
        self,
        name: str,
        value: Union[int, float] = 1,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Increment a counter metric."""
        with self._lock:
            if name not in self._metrics:
                self.create_metric(name, MetricType.COUNTER, f"Counter: {name}")

            current_value = self._metrics[name].get_latest_value() or 0
            self._metrics[name].add_point(current_value + value, labels)

    def set_gauge(
        self,
        name: str,
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None,
    ):
        """Set a gauge metric value."""
        with self._lock:
            if name not in self._metrics:
                self.create_metric(name, MetricType.GAUGE, f"Gauge: {name}")

            self._metrics[name].add_point(value, labels)

    def record_timer(
        self, name: str, duration_ms: float, labels: Optional[Dict[str, str]] = None
    ):
        """Record a timer metric."""
        with self._lock:
            if name not in self._metrics:
                self.create_metric(
                    name, MetricType.TIMER, f"Timer: {name}", "milliseconds"
                )

            self._metrics[name].add_point(duration_ms, labels)

    def record_histogram(
        self,
        name: str,
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None,
    ):
        """Record a histogram value."""
        with self._lock:
            if name not in self._metrics:
                self.create_metric(name, MetricType.HISTOGRAM, f"Histogram: {name}")

            self._metrics[name].add_point(value, labels)

    def get_metric(self, name: str) -> Optional[MetricSeries]:
        """Get a metric series by name."""
        with self._lock:
            return self._metrics.get(name)

    def get_all_metrics(self) -> Dict[str, MetricSeries]:
        """Get all metric series."""
        with self._lock:
            return self._metrics.copy()

    def clear_metrics(self):
        """Clear all metrics."""
        with self._lock:
            self._metrics.clear()


class ValidationMetrics(MetricsCollector):
    """Metrics collector for validation operations."""

    def __init__(self):
        """Initialize validation metrics collector."""
        super().__init__(max_series=50)

        # Initialize core validation metrics
        self.create_metric(
            "validation_total", MetricType.COUNTER, "Total validation attempts"
        )
        self.create_metric(
            "validation_success", MetricType.COUNTER, "Successful validations"
        )
        self.create_metric(
            "validation_failure", MetricType.COUNTER, "Failed validations"
        )
        self.create_metric(
            "validation_duration",
            MetricType.TIMER,
            "Validation duration",
            "milliseconds",
        )
        self.create_metric(
            "validation_cache_hits", MetricType.COUNTER, "Validation cache hits"
        )
        self.create_metric(
            "validation_cache_misses", MetricType.COUNTER, "Validation cache misses"
        )

    def record_validation_attempt(
        self, node_type: str, success: bool, duration_ms: float, cached: bool = False
    ):
        """Record a validation attempt.

        Args:
            node_type: Type of node being validated
            success: Whether validation succeeded
            duration_ms: Validation duration in milliseconds
            cached: Whether result came from cache
        """
        labels = {"node_type": node_type}

        self.increment("validation_total", labels=labels)
        self.record_timer("validation_duration", duration_ms, labels=labels)

        if success:
            self.increment("validation_success", labels=labels)
        else:
            self.increment("validation_failure", labels=labels)

        if cached:
            self.increment("validation_cache_hits", labels=labels)
        else:
            self.increment("validation_cache_misses", labels=labels)

    def get_success_rate(self, time_window: timedelta = timedelta(hours=1)) -> float:
        """Get validation success rate over time window."""
        success_metric = self.get_metric("validation_success")
        failure_metric = self.get_metric("validation_failure")

        if not success_metric or not failure_metric:
            return 0.0

        success_count = len(
            [
                p
                for p in success_metric.points
                if p.timestamp >= datetime.now(UTC) - time_window
            ]
        )
        failure_count = len(
            [
                p
                for p in failure_metric.points
                if p.timestamp >= datetime.now(UTC) - time_window
            ]
        )

        total = success_count + failure_count
        return success_count / total if total > 0 else 0.0

    def get_cache_hit_rate(self, time_window: timedelta = timedelta(hours=1)) -> float:
        """Get cache hit rate over time window."""
        hits_metric = self.get_metric("validation_cache_hits")
        misses_metric = self.get_metric("validation_cache_misses")

        if not hits_metric or not misses_metric:
            return 0.0

        hits_count = len(
            [
                p
                for p in hits_metric.points
                if p.timestamp >= datetime.now(UTC) - time_window
            ]
        )
        misses_count = len(
            [
                p
                for p in misses_metric.points
                if p.timestamp >= datetime.now(UTC) - time_window
            ]
        )

        total = hits_count + misses_count
        return hits_count / total if total > 0 else 0.0


class SecurityMetrics(MetricsCollector):
    """Metrics collector for security events."""

    def __init__(self):
        """Initialize security metrics collector."""
        super().__init__(max_series=30)

        # Initialize core security metrics
        self.create_metric(
            "security_violations_total", MetricType.COUNTER, "Total security violations"
        )
        self.create_metric(
            "sql_injection_attempts", MetricType.COUNTER, "SQL injection attempts"
        )
        self.create_metric(
            "code_injection_attempts", MetricType.COUNTER, "Code injection attempts"
        )
        self.create_metric(
            "path_traversal_attempts", MetricType.COUNTER, "Path traversal attempts"
        )
        self.create_metric(
            "credential_exposure_attempts",
            MetricType.COUNTER,
            "Credential exposure attempts",
        )
        self.create_metric(
            "blocked_connections", MetricType.COUNTER, "Blocked malicious connections"
        )

    def record_security_violation(
        self,
        violation_type: str,
        severity: MetricSeverity,
        source: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Record a security violation.

        Args:
            violation_type: Type of security violation
            severity: Severity level
            source: Source of the violation (node, connection, etc.)
            details: Additional violation details
        """
        labels = {
            "violation_type": violation_type,
            "severity": severity.value,
            "source": source,
        }

        self.increment("security_violations_total", labels=labels)

        # Increment specific violation counters
        if "sql" in violation_type.lower():
            self.increment("sql_injection_attempts", labels=labels)
        elif "code" in violation_type.lower():
            self.increment("code_injection_attempts", labels=labels)
        elif "path" in violation_type.lower():
            self.increment("path_traversal_attempts", labels=labels)
        elif "credential" in violation_type.lower():
            self.increment("credential_exposure_attempts", labels=labels)

    def record_blocked_connection(
        self, source_node: str, target_node: str, reason: str
    ):
        """Record a blocked connection.

        Args:
            source_node: Source node identifier
            target_node: Target node identifier
            reason: Reason for blocking
        """
        labels = {
            "source_node": source_node,
            "target_node": target_node,
            "reason": reason,
        }

        self.increment("blocked_connections", labels=labels)

    def get_violation_rate(self, time_window: timedelta = timedelta(hours=1)) -> float:
        """Get security violation rate per minute."""
        violations_metric = self.get_metric("security_violations_total")

        if not violations_metric:
            return 0.0

        return violations_metric.get_rate(time_window) or 0.0

    def get_critical_violations(
        self, time_window: timedelta = timedelta(hours=1)
    ) -> int:
        """Get count of critical violations in time window."""
        violations_metric = self.get_metric("security_violations_total")

        if not violations_metric:
            return 0

        cutoff = datetime.now(UTC) - time_window
        critical_points = [
            p
            for p in violations_metric.points
            if p.timestamp >= cutoff and p.labels.get("severity") == "critical"
        ]

        return len(critical_points)


class PerformanceMetrics(MetricsCollector):
    """Metrics collector for performance monitoring."""

    def __init__(self):
        """Initialize performance metrics collector."""
        super().__init__(max_series=40)

        # Initialize core performance metrics
        self.create_metric(
            "response_time", MetricType.TIMER, "Response time", "milliseconds"
        )
        self.create_metric("throughput", MetricType.GAUGE, "Requests per second", "rps")
        self.create_metric("memory_usage", MetricType.GAUGE, "Memory usage", "MB")
        self.create_metric("cpu_usage", MetricType.GAUGE, "CPU usage", "percent")
        self.create_metric("error_rate", MetricType.GAUGE, "Error rate", "percent")
        self.create_metric("slow_operations", MetricType.COUNTER, "Slow operations")

    def record_operation(self, operation: str, duration_ms: float, success: bool):
        """Record an operation performance.

        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
            success: Whether operation succeeded
        """
        labels = {"operation": operation}

        self.record_timer("response_time", duration_ms, labels=labels)

        if not success:
            self.increment("error_rate", labels=labels)

        # Record slow operations (>1 second)
        if duration_ms > 1000:
            self.increment("slow_operations", labels=labels)

    def update_system_metrics(self, memory_mb: float, cpu_percent: float, rps: float):
        """Update system-level metrics.

        Args:
            memory_mb: Memory usage in MB
            cpu_percent: CPU usage percentage
            rps: Requests per second
        """
        self.set_gauge("memory_usage", memory_mb)
        self.set_gauge("cpu_usage", cpu_percent)
        self.set_gauge("throughput", rps)

    def get_p95_response_time(
        self, time_window: timedelta = timedelta(hours=1)
    ) -> Optional[float]:
        """Get 95th percentile response time."""
        response_time_metric = self.get_metric("response_time")

        if not response_time_metric:
            return None

        cutoff = datetime.now(UTC) - time_window
        relevant_points = [
            p.value for p in response_time_metric.points if p.timestamp >= cutoff
        ]

        if not relevant_points:
            return None

        relevant_points.sort()
        index = int(0.95 * len(relevant_points))
        return relevant_points[min(index, len(relevant_points) - 1)]


class MetricsRegistry:
    """Global registry for metrics collectors."""

    def __init__(self):
        """Initialize metrics registry."""
        self._collectors: Dict[str, MetricsCollector] = {}
        self._lock = threading.RLock()

    def register_collector(self, name: str, collector: MetricsCollector):
        """Register a metrics collector.

        Args:
            name: Collector name
            collector: MetricsCollector instance
        """
        with self._lock:
            self._collectors[name] = collector

    def get_collector(self, name: str) -> Optional[MetricsCollector]:
        """Get a metrics collector by name.

        Args:
            name: Collector name

        Returns:
            MetricsCollector instance or None
        """
        with self._lock:
            return self._collectors.get(name)

    def get_all_collectors(self) -> Dict[str, MetricsCollector]:
        """Get all registered collectors."""
        with self._lock:
            return self._collectors.copy()

    def export_metrics(self, format: str = "json") -> str:
        """Export all metrics in specified format.

        Args:
            format: Export format ("json", "prometheus")

        Returns:
            Formatted metrics string
        """
        with self._lock:
            if format == "json":
                return self._export_json()
            elif format == "prometheus":
                return self._export_prometheus()
            else:
                raise ValueError(f"Unsupported format: {format}")

    def _export_json(self) -> str:
        """Export metrics as JSON."""
        export_data = {}

        for collector_name, collector in self._collectors.items():
            collector_data = {}

            for metric_name, metric_series in collector.get_all_metrics().items():
                series_data = {
                    "type": metric_series.metric_type.value,
                    "description": metric_series.description,
                    "unit": metric_series.unit,
                    "latest_value": metric_series.get_latest_value(),
                    "points": [
                        {
                            "timestamp": point.timestamp.isoformat(),
                            "value": point.value,
                            "labels": point.labels,
                        }
                        for point in list(metric_series.points)[-10:]  # Last 10 points
                    ],
                }
                collector_data[metric_name] = series_data

            export_data[collector_name] = collector_data

        return json.dumps(export_data, indent=2)

    def _export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        for collector_name, collector in self._collectors.items():
            for metric_name, metric_series in collector.get_all_metrics().items():
                # Prometheus metric name
                prom_name = f"kailash_{collector_name}_{metric_name}"

                # Help text
                lines.append(f"# HELP {prom_name} {metric_series.description}")
                lines.append(f"# TYPE {prom_name} {metric_series.metric_type.value}")

                # Latest value with labels
                latest_point = (
                    metric_series.points[-1] if metric_series.points else None
                )
                if latest_point:
                    label_str = ""
                    if latest_point.labels:
                        label_pairs = [
                            f'{k}="{v}"' for k, v in latest_point.labels.items()
                        ]
                        label_str = "{" + ",".join(label_pairs) + "}"

                    lines.append(f"{prom_name}{label_str} {latest_point.value}")

                lines.append("")  # Empty line between metrics

        return "\n".join(lines)


# Global metrics registry
_global_registry = MetricsRegistry()

# Register default collectors
_global_registry.register_collector("validation", ValidationMetrics())
_global_registry.register_collector("security", SecurityMetrics())
_global_registry.register_collector("performance", PerformanceMetrics())


def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    return _global_registry


def get_validation_metrics() -> ValidationMetrics:
    """Get the validation metrics collector."""
    return _global_registry.get_collector("validation")


def get_security_metrics() -> SecurityMetrics:
    """Get the security metrics collector."""
    return _global_registry.get_collector("security")


def get_performance_metrics() -> PerformanceMetrics:
    """Get the performance metrics collector."""
    return _global_registry.get_collector("performance")

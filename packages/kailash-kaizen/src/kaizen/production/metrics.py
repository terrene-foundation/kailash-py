"""Metrics collection for production monitoring.

Provides RED metrics (Rate, Errors, Duration) and custom business metrics
with Prometheus integration.
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MetricValue:
    """Container for a metric value with metadata."""

    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._lock = threading.Lock()
        self._values: Dict[str, float] = defaultdict(float)

    def inc(self, labels: Optional[Dict[str, str]] = None, amount: float = 1.0):
        """Increment counter."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] += amount

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._values.get(key, 0.0)

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        items = sorted(labels.items())
        return ",".join(f"{k}={v}" for k, v in items)


class Histogram:
    """Thread-safe histogram metric for tracking distributions."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._lock = threading.Lock()
        self._observations: Dict[str, List[float]] = defaultdict(list)

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Record an observation."""
        key = self._label_key(labels or {})
        with self._lock:
            self._observations[key].append(value)

    def get_stats(self, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get statistics for observations."""
        key = self._label_key(labels or {})
        with self._lock:
            values = self._observations.get(key, [])
            if not values:
                return {"count": 0, "sum": 0.0}

            return {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
            }

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        items = sorted(labels.items())
        return ",".join(f"{k}={v}" for k, v in items)


class Gauge:
    """Thread-safe gauge metric for values that go up and down."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._lock = threading.Lock()
        self._values: Dict[str, float] = {}

    def set(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Set gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            self._values[key] = value

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value."""
        key = self._label_key(labels or {})
        with self._lock:
            return self._values.get(key, 0.0)

    def _label_key(self, labels: Dict[str, str]) -> str:
        """Convert labels to a hashable key."""
        if not labels:
            return ""
        items = sorted(labels.items())
        return ",".join(f"{k}={v}" for k, v in items)


class MetricsCollector:
    """Production metrics collector with Prometheus support.

    Implements RED metrics (Rate, Errors, Duration) and supports
    custom business metrics.

    Example:
        >>> metrics = MetricsCollector()
        >>> metrics.track_request("qa_agent", "success")
        >>> metrics.track_duration("qa_agent", 0.5)
        >>> stats = metrics.get_duration_stats("qa_agent")
    """

    def __init__(self):
        """Initialize metrics collector."""
        # RED metrics
        self._request_counter = Counter(
            "kaizen_requests_total", "Total number of requests"
        )
        self._error_counter = Counter("kaizen_errors_total", "Total number of errors")
        self._duration_histogram = Histogram(
            "kaizen_request_duration_seconds", "Request duration in seconds"
        )

        # Custom metrics
        self._gauges: Dict[str, Gauge] = {}
        self._counters: Dict[str, Counter] = {}

    def track_request(
        self, agent_type: str, status: str, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track a request.

        Args:
            agent_type: Type of agent (e.g., "qa_agent")
            status: Request status (e.g., "success", "error")
            labels: Additional labels for the metric
        """
        metric_labels = {"agent_type": agent_type, "status": status}
        if labels:
            metric_labels.update(labels)

        self._request_counter.inc(labels=metric_labels)

    def track_error(
        self, agent_type: str, error_type: str, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track an error.

        Args:
            agent_type: Type of agent
            error_type: Type of error (e.g., "timeout", "validation")
            labels: Additional labels
        """
        metric_labels = {"agent_type": agent_type, "error_type": error_type}
        if labels:
            metric_labels.update(labels)

        self._error_counter.inc(labels=metric_labels)

    def track_duration(
        self, agent_type: str, duration: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Track request duration.

        Args:
            agent_type: Type of agent
            duration: Duration in seconds
            labels: Additional labels
        """
        metric_labels = {"agent_type": agent_type}
        if labels:
            metric_labels.update(labels)

        self._duration_histogram.observe(duration, labels=metric_labels)

    def get_request_count(
        self, agent_type: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        """Get request count.

        Args:
            agent_type: Type of agent
            labels: Additional labels to filter by

        Returns:
            Total request count (sum across all statuses if no status specified)
        """
        # If no specific labels, sum all requests for this agent type
        if labels is None:
            total = 0.0
            for label_key, value in self._request_counter._values.items():
                if f"agent_type={agent_type}" in label_key:
                    total += value
            return total

        # Otherwise, get specific label combination
        metric_labels = {"agent_type": agent_type}
        metric_labels.update(labels)
        return self._request_counter.get(labels=metric_labels)

    def get_error_count(
        self, agent_type: str, labels: Optional[Dict[str, str]] = None
    ) -> float:
        """Get error count.

        Args:
            agent_type: Type of agent
            labels: Additional labels to filter by

        Returns:
            Total error count (sum across all error types if no type specified)
        """
        # If no specific labels, sum all errors for this agent type
        if labels is None:
            total = 0.0
            for label_key, value in self._error_counter._values.items():
                if f"agent_type={agent_type}" in label_key:
                    total += value
            return total

        # Otherwise, get specific label combination
        metric_labels = {"agent_type": agent_type}
        metric_labels.update(labels)
        return self._error_counter.get(labels=metric_labels)

    def get_duration_stats(
        self, agent_type: str, labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, float]:
        """Get duration statistics.

        Args:
            agent_type: Type of agent
            labels: Additional labels to filter by

        Returns:
            Dict with count, sum, min, max, avg
        """
        metric_labels = {"agent_type": agent_type}
        if labels:
            metric_labels.update(labels)

        return self._duration_histogram.get_stats(labels=metric_labels)

    def define_gauge(self, name: str, description: str) -> None:
        """Define a custom gauge metric.

        Args:
            name: Metric name
            description: Metric description
        """
        if name not in self._gauges:
            self._gauges[name] = Gauge(name, description)

    def set_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Set gauge value.

        Args:
            name: Metric name
            value: Metric value
            labels: Additional labels
        """
        if name not in self._gauges:
            raise ValueError(f"Gauge {name} not defined. Call define_gauge() first.")

        self._gauges[name].set(value, labels=labels)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get gauge value.

        Args:
            name: Metric name
            labels: Additional labels

        Returns:
            Current gauge value
        """
        if name not in self._gauges:
            raise ValueError(f"Gauge {name} not defined")

        return self._gauges[name].get(labels=labels)

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format.

        Returns:
            Metrics in Prometheus exposition format
        """
        lines = []

        # Export request counter
        lines.append(
            f"# HELP {self._request_counter.name} {self._request_counter.description}"
        )
        lines.append(f"# TYPE {self._request_counter.name} counter")
        for labels_key, value in self._request_counter._values.items():
            if labels_key:
                lines.append(f"{self._request_counter.name}{{{labels_key}}} {value}")
            else:
                lines.append(f"{self._request_counter.name} {value}")

        # Export error counter
        lines.append(
            f"# HELP {self._error_counter.name} {self._error_counter.description}"
        )
        lines.append(f"# TYPE {self._error_counter.name} counter")
        for labels_key, value in self._error_counter._values.items():
            if labels_key:
                lines.append(f"{self._error_counter.name}{{{labels_key}}} {value}")
            else:
                lines.append(f"{self._error_counter.name} {value}")

        # Export duration histogram
        lines.append(
            f"# HELP {self._duration_histogram.name} {self._duration_histogram.description}"
        )
        lines.append(f"# TYPE {self._duration_histogram.name} histogram")
        for labels_key, observations in self._duration_histogram._observations.items():
            if observations:
                count = len(observations)
                total = sum(observations)
                if labels_key:
                    lines.append(
                        f"{self._duration_histogram.name}_count{{{labels_key}}} {count}"
                    )
                    lines.append(
                        f"{self._duration_histogram.name}_sum{{{labels_key}}} {total}"
                    )
                else:
                    lines.append(f"{self._duration_histogram.name}_count {count}")
                    lines.append(f"{self._duration_histogram.name}_sum {total}")

        # Export gauges
        for gauge in self._gauges.values():
            lines.append(f"# HELP {gauge.name} {gauge.description}")
            lines.append(f"# TYPE {gauge.name} gauge")
            for labels_key, value in gauge._values.items():
                if labels_key:
                    lines.append(f"{gauge.name}{{{labels_key}}} {value}")
                else:
                    lines.append(f"{gauge.name} {value}")

        return "\n".join(lines) + "\n"

    @property
    def request_rate(self) -> Counter:
        """Get request rate counter."""
        return self._request_counter

    @property
    def error_rate(self) -> Counter:
        """Get error rate counter."""
        return self._error_counter

    @property
    def request_duration(self) -> Histogram:
        """Get request duration histogram."""
        return self._duration_histogram

"""Comprehensive metrics collection for connection management.

This module provides detailed metrics collection for database connections,
query execution, pool utilization, and health monitoring. It supports
multiple metric backends and provides real-time and historical analysis.

Features:
- Connection acquisition time tracking
- Query execution latency histograms
- Pool utilization monitoring
- Health check success rates
- Error categorization and analysis
- Export to Prometheus, StatsD, CloudWatch

Example:
    >>> metrics = ConnectionMetricsCollector("production_pool")
    >>>
    >>> # Track connection acquisition
    >>> with metrics.track_acquisition() as timer:
    ...     connection = await pool.acquire()
    >>>
    >>> # Track query execution
    >>> with metrics.track_query("SELECT", "users") as timer:
    ...     result = await connection.execute(query)
"""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, ContextManager, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class ErrorCategory(Enum):
    """Categories of connection errors."""

    CONNECTION_TIMEOUT = "connection_timeout"
    CONNECTION_REFUSED = "connection_refused"
    AUTHENTICATION_FAILED = "authentication_failed"
    QUERY_TIMEOUT = "query_timeout"
    QUERY_ERROR = "query_error"
    POOL_EXHAUSTED = "pool_exhausted"
    HEALTH_CHECK_FAILED = "health_check_failed"
    UNKNOWN = "unknown"


@dataclass
class MetricPoint:
    """Single metric data point."""

    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class HistogramData:
    """Histogram data with percentiles."""

    count: int
    sum: float
    min: float
    max: float
    p50: float
    p75: float
    p90: float
    p95: float
    p99: float

    @classmethod
    def from_values(cls, values: List[float]) -> "HistogramData":
        """Create histogram data from values."""
        if not values:
            return cls(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        sorted_values = sorted(values)
        return cls(
            count=len(values),
            sum=sum(values),
            min=sorted_values[0],
            max=sorted_values[-1],
            p50=cls._percentile(sorted_values, 0.50),
            p75=cls._percentile(sorted_values, 0.75),
            p90=cls._percentile(sorted_values, 0.90),
            p95=cls._percentile(sorted_values, 0.95),
            p99=cls._percentile(sorted_values, 0.99),
        )

    @staticmethod
    def _percentile(sorted_values: List[float], percentile: float) -> float:
        """Calculate percentile from sorted values."""
        index = int(len(sorted_values) * percentile)
        return sorted_values[min(index, len(sorted_values) - 1)]


class TimerContext:
    """Context manager for timing operations."""

    def __init__(self, callback):
        self.callback = callback
        self.start_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = (time.time() - self.start_time) * 1000  # Convert to ms
        self.callback(self.duration)


class ConnectionMetricsCollector:
    """Collects comprehensive metrics for connection management."""

    def __init__(self, pool_name: str, retention_minutes: int = 60):
        """Initialize metrics collector.

        Args:
            pool_name: Name of the connection pool
            retention_minutes: How long to retain detailed metrics
        """
        self.pool_name = pool_name
        self.retention_minutes = retention_minutes

        # Counters
        self._counters: Dict[str, int] = defaultdict(int)

        # Gauges
        self._gauges: Dict[str, float] = defaultdict(float)

        # Histograms (using deques for sliding window)
        self._histograms: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=10000)  # Keep last 10k samples
        )

        # Time series data
        self._time_series: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=retention_minutes * 60)  # 1 sample per second
        )

        # Error tracking
        self._errors: Dict[ErrorCategory, int] = defaultdict(int)
        self._error_details: deque = deque(maxlen=1000)

        # Query tracking
        self._query_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_time": 0.0, "errors": 0}
        )

        self._start_time = time.time()

    # Connection metrics

    def track_acquisition(self) -> TimerContext:
        """Track connection acquisition time."""

        def record(duration_ms: float):
            self._histograms["connection_acquisition_ms"].append(duration_ms)
            self._counters["connections_acquired"] += 1
            self._record_time_series("acquisition_time_ms", duration_ms)

        return TimerContext(record)

    def track_release(self, reusable: bool = True):
        """Track connection release."""
        self._counters["connections_released"] += 1
        if reusable:
            self._counters["connections_reused"] += 1
        else:
            self._counters["connections_discarded"] += 1

    def track_creation(self) -> TimerContext:
        """Track new connection creation time."""

        def record(duration_ms: float):
            self._histograms["connection_creation_ms"].append(duration_ms)
            self._counters["connections_created"] += 1

        return TimerContext(record)

    # Query metrics

    def track_query(self, query_type: str, table: Optional[str] = None) -> TimerContext:
        """Track query execution time.

        Args:
            query_type: Type of query (SELECT, INSERT, UPDATE, DELETE, etc.)
            table: Optional table name
        """
        query_key = f"{query_type}:{table or 'unknown'}"

        def record(duration_ms: float):
            self._histograms["query_execution_ms"].append(duration_ms)
            self._histograms[f"query_{query_type.lower()}_ms"].append(duration_ms)
            self._counters[f"queries_{query_type.lower()}"] += 1
            self._counters["queries_total"] += 1

            # Update query stats
            stats = self._query_stats[query_key]
            stats["count"] += 1
            stats["total_time"] += duration_ms

            self._record_time_series("query_rate", 1.0)

        return TimerContext(record)

    def track_query_error(self, query_type: str, error: Exception):
        """Track query execution error."""
        self._counters["query_errors"] += 1
        self._counters[f"query_errors_{query_type.lower()}"] += 1

        error_category = self._categorize_error(error)
        self._errors[error_category] += 1

        # Store error details
        self._error_details.append(
            {
                "timestamp": datetime.now().isoformat(),
                "query_type": query_type,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "category": error_category.value,
            }
        )

    # Pool metrics

    def update_pool_stats(self, active: int, idle: int, total: int):
        """Update pool utilization statistics."""
        self._gauges["pool_connections_active"] = active
        self._gauges["pool_connections_idle"] = idle
        self._gauges["pool_connections_total"] = total
        self._gauges["pool_utilization"] = active / total if total > 0 else 0.0

        self._record_time_series("pool_active", active)
        self._record_time_series("pool_utilization", self._gauges["pool_utilization"])

    def track_pool_exhaustion(self):
        """Track pool exhaustion event."""
        self._counters["pool_exhaustion_events"] += 1
        self._errors[ErrorCategory.POOL_EXHAUSTED] += 1

    # Health metrics

    def track_health_check(self, success: bool, duration_ms: float):
        """Track health check result."""
        self._counters["health_checks_total"] += 1
        if success:
            self._counters["health_checks_success"] += 1
        else:
            self._counters["health_checks_failed"] += 1
            self._errors[ErrorCategory.HEALTH_CHECK_FAILED] += 1

        self._histograms["health_check_duration_ms"].append(duration_ms)

        # Calculate success rate
        total = self._counters["health_checks_total"]
        success_count = self._counters["health_checks_success"]
        self._gauges["health_check_success_rate"] = (
            success_count / total if total > 0 else 0.0
        )

    # Error categorization

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize error for tracking."""
        error_msg = str(error).lower()
        error_type = type(error).__name__.lower()

        if "timeout" in error_msg:
            if "connection" in error_msg:
                return ErrorCategory.CONNECTION_TIMEOUT
            else:
                return ErrorCategory.QUERY_TIMEOUT
        elif "refused" in error_msg or "unavailable" in error_msg:
            return ErrorCategory.CONNECTION_REFUSED
        elif "authentication" in error_msg or "password" in error_msg:
            return ErrorCategory.AUTHENTICATION_FAILED
        elif "pool" in error_msg and "exhausted" in error_msg:
            return ErrorCategory.POOL_EXHAUSTED
        elif "syntax" in error_msg or "column" in error_msg:
            return ErrorCategory.QUERY_ERROR
        else:
            return ErrorCategory.UNKNOWN

    # Time series recording

    def _record_time_series(self, metric_name: str, value: float):
        """Record time series data point."""
        self._time_series[metric_name].append(
            MetricPoint(
                timestamp=time.time(), value=value, labels={"pool": self.pool_name}
            )
        )

    # Metric retrieval

    def get_histogram(self, metric_name: str) -> Optional[HistogramData]:
        """Get histogram data for metric."""
        values = list(self._histograms.get(metric_name, []))
        if not values:
            return None
        return HistogramData.from_values(values)

    def get_time_series(
        self, metric_name: str, minutes: Optional[int] = None
    ) -> List[MetricPoint]:
        """Get time series data for metric."""
        points = list(self._time_series.get(metric_name, []))

        if minutes:
            cutoff = time.time() - (minutes * 60)
            points = [p for p in points if p.timestamp >= cutoff]

        return points

    def get_error_summary(self) -> Dict[str, Any]:
        """Get error summary statistics."""
        total_errors = sum(self._errors.values())
        return {
            "total_errors": total_errors,
            "errors_by_category": {
                category.value: count
                for category, count in self._errors.items()
                if count > 0
            },
            "error_rate": total_errors / max(1, self._counters["queries_total"]),
            "recent_errors": list(self._error_details)[-10:],  # Last 10 errors
        }

    def get_query_summary(self) -> Dict[str, Any]:
        """Get query execution summary."""
        summaries = {}

        for query_key, stats in self._query_stats.items():
            if stats["count"] == 0:
                continue

            avg_time = stats["total_time"] / stats["count"]
            summaries[query_key] = {
                "count": stats["count"],
                "avg_time_ms": avg_time,
                "total_time_ms": stats["total_time"],
                "errors": stats["errors"],
                "error_rate": stats["errors"] / stats["count"],
            }

        return summaries

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics snapshot."""
        uptime_seconds = time.time() - self._start_time

        return {
            "pool_name": self.pool_name,
            "uptime_seconds": uptime_seconds,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: self.get_histogram(name).__dict__
                for name in self._histograms
                if self.get_histogram(name)
            },
            "errors": self.get_error_summary(),
            "queries": self.get_query_summary(),
            "rates": {
                "queries_per_second": self._counters["queries_total"] / uptime_seconds,
                "errors_per_second": sum(self._errors.values()) / uptime_seconds,
                "connections_per_second": self._counters["connections_created"]
                / uptime_seconds,
            },
        }

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        # Add metadata
        lines.append("# HELP connection_pool_info Connection pool information")
        lines.append("# TYPE connection_pool_info gauge")
        lines.append(f'connection_pool_info{{pool="{self.pool_name}"}} 1')

        # Export counters
        for name, value in self._counters.items():
            metric_name = f"connection_pool_{name}"
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f'{metric_name}{{pool="{self.pool_name}"}} {value}')

        # Export gauges
        for name, value in self._gauges.items():
            metric_name = f"connection_pool_{name}"
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f'{metric_name}{{pool="{self.pool_name}"}} {value}')

        # Export histograms
        for name, values in self._histograms.items():
            if values:
                hist = HistogramData.from_values(list(values))
                metric_name = f"connection_pool_{name}"
                lines.append(f"# TYPE {metric_name} histogram")
                lines.append(
                    f'{metric_name}_count{{pool="{self.pool_name}"}} {hist.count}'
                )
                lines.append(f'{metric_name}_sum{{pool="{self.pool_name}"}} {hist.sum}')

                for percentile, value in [
                    (0.5, hist.p50),
                    (0.75, hist.p75),
                    (0.9, hist.p90),
                    (0.95, hist.p95),
                    (0.99, hist.p99),
                ]:
                    lines.append(
                        f'{metric_name}{{pool="{self.pool_name}",quantile="{percentile}"}} {value}'
                    )

        return "\n".join(lines)

    def reset(self):
        """Reset all metrics (useful for testing)."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._time_series.clear()
        self._errors.clear()
        self._error_details.clear()
        self._query_stats.clear()
        self._start_time = time.time()


class MetricsAggregator:
    """Aggregates metrics from multiple collectors."""

    def __init__(self):
        """Initialize metrics aggregator."""
        self._collectors: Dict[str, ConnectionMetricsCollector] = {}

    def register_collector(self, collector: ConnectionMetricsCollector):
        """Register a metrics collector."""
        self._collectors[collector.pool_name] = collector

    def get_global_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics from all collectors."""
        total_queries = 0
        total_errors = 0
        total_connections = 0
        all_pool_metrics = {}

        for name, collector in self._collectors.items():
            metrics = collector.get_all_metrics()
            all_pool_metrics[name] = metrics

            total_queries += metrics["counters"].get("queries_total", 0)
            total_errors += metrics["errors"]["total_errors"]
            total_connections += metrics["gauges"].get("pool_connections_total", 0)

        return {
            "total_pools": len(self._collectors),
            "total_queries": total_queries,
            "total_errors": total_errors,
            "total_connections": total_connections,
            "global_error_rate": total_errors / max(1, total_queries),
            "pools": all_pool_metrics,
        }

    def export_all_prometheus(self) -> str:
        """Export all metrics in Prometheus format."""
        outputs = []
        for collector in self._collectors.values():
            outputs.append(collector.export_prometheus())
        return "\n\n".join(outputs)

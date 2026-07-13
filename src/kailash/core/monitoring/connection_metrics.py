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
import types
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, ContextManager, Dict, List, Optional, Tuple

from kailash.utils.url_credentials import redact_pool_key

logger = logging.getLogger(__name__)

# ``prometheus_client`` is an OPTIONAL dependency (the ``monitoring`` extra —
# see ``pyproject.toml``), so it MUST NOT be a hard import for this core
# module (`rules/dependencies.md` § "Declared = Imported"). When absent, the
# real Prometheus histogram below (#1708 W1c) is silently disabled — callers
# still get their in-process percentile histograms via ``get_histogram()``.
try:
    import prometheus_client as _prometheus_client

    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — covered by structural degrade test
    _prometheus_client: types.ModuleType = types.ModuleType(  # type: ignore[no-redef]
        "prometheus_client"
    )
    _PROMETHEUS_AVAILABLE = False

# Module-level singleton: multiple ConnectionMetricsCollector instances exist
# simultaneously (one per named pool — see WorkflowConnectionPool.__init__),
# and prometheus_client raises "Duplicated timeseries in CollectorRegistry"
# if the same metric name is registered twice against the default registry.
# The ``pool`` label differentiates per-pool series on this one shared
# instrument, matching the AsyncSQLMetrics.lock_wait_time_histogram pattern
# (kailash/monitoring/asyncsql_metrics.py).
_ACQUIRE_WAIT_HISTOGRAM: "Optional[Any]" = None


def _get_acquire_wait_histogram() -> "Optional[Any]":
    """Return the shared ``kailash_pool_acquire_wait_seconds`` histogram.

    Created lazily on first use so importing this module never requires
    ``prometheus_client`` to be installed. Uses EXPLICIT second-scale bucket
    boundaries — the OTel/Prometheus client default buckets are
    generic-scale (0.005 .. 10.0 with different steps) and give useless
    p95/p99 resolution for a sub-100ms connection-acquisition metric.

    The histogram is registered against ``prometheus_client.REGISTRY`` (the
    default registry) so it flows into the unified server ``/metrics``
    scrape via ``render_prometheus_exposition()``
    (``kailash/monitoring/metrics.py``), which calls
    ``prometheus_client.generate_latest()`` with no registry argument
    (defaults to the same global ``REGISTRY``) — the same path #1708 W1b
    unified for OTel meters and prometheus_client-native instruments.
    """
    global _ACQUIRE_WAIT_HISTOGRAM
    if not _PROMETHEUS_AVAILABLE:
        return None
    if _ACQUIRE_WAIT_HISTOGRAM is not None:
        return _ACQUIRE_WAIT_HISTOGRAM

    metric_name = "kailash_pool_acquire_wait_seconds"
    try:
        _ACQUIRE_WAIT_HISTOGRAM = _prometheus_client.Histogram(
            metric_name,
            "Time spent waiting to acquire a connection from the pool",
            ["pool"],
            buckets=(
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.5,
                5.0,
                10.0,
                float("inf"),
            ),
            registry=_prometheus_client.REGISTRY,
        )
    except ValueError:
        # "Duplicated timeseries in CollectorRegistry" — this module can be
        # imported under two distinct qualified names in the SAME process
        # (``kailash.core.monitoring.connection_metrics`` vs
        # ``src.kailash.core.monitoring.connection_metrics``, exercised by
        # different test files in this repo's suite), which gives each
        # import its own module-level ``_ACQUIRE_WAIT_HISTOGRAM`` global even
        # though both share the SAME process-wide ``prometheus_client.
        # REGISTRY``. Whichever import path registers first wins; adopt its
        # already-registered Histogram instance instead of erroring, so the
        # second import path still observes into the one real timeseries.
        existing = _prometheus_client.REGISTRY._names_to_collectors.get(metric_name)
        if existing is None:
            raise
        _ACQUIRE_WAIT_HISTOGRAM = existing
    return _ACQUIRE_WAIT_HISTOGRAM


# G1 HIGH-1: the idle-connection gauge and pool-exhaustion counter follow the
# EXACT same module-level-singleton-on-the-default-REGISTRY pattern as
# ``_ACQUIRE_WAIT_HISTOGRAM`` above. Before this fix, both metrics were only
# reachable via ``ConnectionMetricsProvider.register_source(...)``
# (kailash/servers/connection_metrics_router.py), which has ZERO production
# callers (grep confirms only tests call it) — so a live WorkflowServer /
# EnterpriseWorkflowServer with an empty ``_sources`` registry emitted NO
# idle/exhaustion lines at all. Registering these as real
# ``prometheus_client`` instruments makes them flow into
# ``generate_latest()`` (and therefore the unified ``/metrics`` scrape via
# ``render_prometheus_exposition()``) unconditionally, with no wiring step
# required.
_POOL_IDLE_GAUGE: "Optional[Any]" = None
_POOL_EXHAUSTION_COUNTER: "Optional[Any]" = None


def _get_pool_idle_gauge() -> "Optional[Any]":
    """Return the shared ``kailash_pool_connections_idle`` gauge.

    Created lazily so importing this module never requires
    ``prometheus_client`` to be installed. Registered against
    ``prometheus_client.REGISTRY`` (the default registry) so it flows into
    the unified server ``/metrics`` scrape via ``render_prometheus_exposition()``
    exactly like ``_get_acquire_wait_histogram`` above.

    The ``pool`` label MUST stay bounded (cardinality note, #1708 G1
    HIGH-1): pool names are operator-assigned identifiers configured at
    startup (node id / pool metadata name) from a finite, small set — never
    a per-request or per-connection unique value. ``redact_pool_key`` is
    defense-in-depth in case a caller ever passes a connection-string-shaped
    name (``rules/observability.md`` § 6.3). A caller that constructs one
    :class:`ConnectionMetricsCollector` per request (rather than one per
    configured pool) would defeat this bound; that is a caller bug, not a
    property of this metric.
    """
    global _POOL_IDLE_GAUGE
    if not _PROMETHEUS_AVAILABLE:
        return None
    if _POOL_IDLE_GAUGE is not None:
        return _POOL_IDLE_GAUGE

    metric_name = "kailash_pool_connections_idle"
    try:
        _POOL_IDLE_GAUGE = _prometheus_client.Gauge(
            metric_name,
            "Number of idle (available, unused) connections currently held by the pool",
            ["pool"],
            registry=_prometheus_client.REGISTRY,
        )
    except ValueError:
        # See ``_get_acquire_wait_histogram`` above — this module can be
        # imported under two distinct qualified names in the same process,
        # each with its own module-level global, but sharing the one
        # process-wide ``prometheus_client.REGISTRY``.
        existing = _prometheus_client.REGISTRY._names_to_collectors.get(metric_name)
        if existing is None:
            raise
        _POOL_IDLE_GAUGE = existing
    return _POOL_IDLE_GAUGE


def _get_pool_exhaustion_counter() -> "Optional[Any]":
    """Return the shared ``kailash_pool_exhaustion_events_total`` counter.

    Same lazy-singleton-on-the-default-REGISTRY pattern as
    :func:`_get_pool_idle_gauge` / :func:`_get_acquire_wait_histogram`. See
    :func:`_get_pool_idle_gauge` for the ``pool`` label cardinality note.
    """
    global _POOL_EXHAUSTION_COUNTER
    if not _PROMETHEUS_AVAILABLE:
        return None
    if _POOL_EXHAUSTION_COUNTER is not None:
        return _POOL_EXHAUSTION_COUNTER

    metric_name = "kailash_pool_exhaustion_events_total"
    try:
        _POOL_EXHAUSTION_COUNTER = _prometheus_client.Counter(
            metric_name,
            "Total number of pool-exhaustion events (an acquire attempt found no "
            "available connection)",
            ["pool"],
            registry=_prometheus_client.REGISTRY,
        )
    except ValueError:
        existing = _prometheus_client.REGISTRY._names_to_collectors.get(metric_name)
        if existing is None:
            raise
        _POOL_EXHAUSTION_COUNTER = existing
    return _POOL_EXHAUSTION_COUNTER


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
        self.start_time: float = 0.0
        self.duration: float = 0.0

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

            # Real Prometheus histogram (#1708 W1c) — bucketed le= series,
            # distinct from the in-process percentile histogram above (which
            # only supports post-hoc summary/quantile export; see
            # export_prometheus()). pool_name is a bounded, operator-assigned
            # identifier (node id / pool metadata name), never a per-request
            # UUID, so cardinality stays low; redact_pool_key is defense in
            # depth in case a caller ever passes a connection-string-shaped
            # name (rules/observability.md § 6.3).
            #
            # WorkflowConnectionPool.acquire() runs this callback inside the
            # REAL `with self.metrics_collector.track_acquisition():` block
            # on its production acquire path (workflow_connection_pool.py) —
            # TimerContext.__exit__ calls this callback unguarded, so an
            # uncaught exception here would propagate out of the acquisition
            # itself. Telemetry MUST NOT be able to break the operation it
            # observes, so failures are logged and swallowed here — this is
            # instrumentation-boundary isolation, not silent business-logic
            # error hiding (rules/zero-tolerance.md Rule 3 hooks/cleanup
            # exception).
            try:
                histogram = _get_acquire_wait_histogram()
                if histogram is not None:
                    histogram.labels(pool=redact_pool_key(self.pool_name)).observe(
                        duration_ms / 1000.0
                    )
            except Exception:
                logger.warning(
                    "connection_metrics.acquire_wait_histogram_observe_failed",
                    exc_info=True,
                )

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

        # Real Prometheus gauge (#1708 G1 HIGH-1) — the REAL emission site
        # for ``kailash_pool_connections_idle``. Registered on the default
        # ``REGISTRY`` (see ``_get_pool_idle_gauge``) so it reaches the
        # unified ``/metrics`` scrape via ``generate_latest()`` with no
        # ``ConnectionMetricsProvider.register_source(...)`` dependency.
        # Telemetry MUST NOT be able to break the operation it observes
        # (this runs on the pool-maintenance / acquire path), so failures
        # are logged and swallowed here — instrumentation-boundary
        # isolation, not silent business-logic error hiding
        # (rules/zero-tolerance.md Rule 3 hooks/cleanup exception).
        try:
            gauge = _get_pool_idle_gauge()
            if gauge is not None:
                gauge.labels(pool=redact_pool_key(self.pool_name)).set(idle)
        except Exception:
            logger.warning(
                "connection_metrics.idle_gauge_set_failed",
                exc_info=True,
            )

    def track_pool_exhaustion(self):
        """Track pool exhaustion event."""
        self._counters["pool_exhaustion_events"] += 1
        self._errors[ErrorCategory.POOL_EXHAUSTED] += 1

        # Real Prometheus counter (#1708 G1 HIGH-1) — the REAL emission
        # site for ``kailash_pool_exhaustion_events_total``. See
        # ``update_pool_stats`` above for the try/except rationale.
        try:
            counter = _get_pool_exhaustion_counter()
            if counter is not None:
                counter.labels(pool=redact_pool_key(self.pool_name)).inc()
        except Exception:
            logger.warning(
                "connection_metrics.exhaustion_counter_inc_failed",
                exc_info=True,
            )

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

    async def get_pool_statistics(self) -> Dict[str, Any]:
        """Return pool statistics shaped for router-level scrape registration.

        Gives this collector the same ``get_pool_statistics()`` async
        contract that :class:`~kailash.servers.connection_metrics_router.
        ConnectionMetricsProvider.register_source` expects — so a collector
        instance can be registered directly (``provider.register_source(name,
        collector)``) and its idle-connection gauge / pool-exhaustion counter
        (set by :meth:`update_pool_stats` / :meth:`track_pool_exhaustion`,
        otherwise only visible via :meth:`get_all_metrics`) reach the unified
        ``/metrics`` scrape (#1708 W1c) instead of being collected but never
        exported.
        """
        uptime_seconds = max(time.time() - self._start_time, 1e-9)
        query_hist = self.get_histogram("query_execution_ms")
        avg_query_time_ms = (
            query_hist.sum / query_hist.count
            if query_hist and query_hist.count
            else 0.0
        )

        return {
            "pool_name": self.pool_name,
            "health_score": self._gauges.get("health_check_success_rate", 1.0) * 100,
            "active_connections": self._gauges.get("pool_connections_active", 0),
            "total_connections": self._gauges.get("pool_connections_total", 0),
            "idle_connections": self._gauges.get("pool_connections_idle", 0),
            "utilization": self._gauges.get("pool_utilization", 0.0),
            "queries_per_second": self._counters["queries_total"] / uptime_seconds,
            "avg_query_time_ms": avg_query_time_ms,
            "error_rate": self.get_error_summary()["error_rate"],
            "pool_exhaustion_events": self._counters.get("pool_exhaustion_events", 0),
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

        # Export percentile summaries (#1708 W1c fix). These are computed
        # post-hoc from a sliding-window sample deque with NO pre-declared
        # bucket boundaries — that is the Prometheus "summary" metric shape
        # (metric_sum + metric_count + metric{quantile="q"}), NOT "histogram"
        # (which requires metric_bucket{le="..."} series). Declaring this
        # block "# TYPE ... histogram" was invalid Prometheus exposition: a
        # real scraper parses histogram-typed series expecting `_bucket`
        # lines and finds `quantile=` labels instead. For a real bucketed
        # histogram of pool acquisition wait time, see
        # kailash_pool_acquire_wait_seconds (_get_acquire_wait_histogram()).
        for name, values in self._histograms.items():
            if values:
                hist = HistogramData.from_values(list(values))
                metric_name = f"connection_pool_{name}"
                lines.append(f"# TYPE {metric_name} summary")
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

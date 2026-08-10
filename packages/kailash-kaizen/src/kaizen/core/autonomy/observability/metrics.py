"""
Metrics collection and Prometheus export for agent performance monitoring.

This module provides the MetricsCollector for recording and exporting metrics:
- Counters: Monotonically increasing values (API calls, errors)
- Gauges: Point-in-time values (memory, active agents)
- Histograms: Value distributions (latency, request size)

Metrics are exported in Prometheus text format for scraping.

Part of Phase 4: Observability & Performance Monitoring (ADR-017)
"""

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

from kaizen.core.autonomy.observability.types import Metric

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and exports metrics in Prometheus format.

    Supports three metric types following Prometheus conventions:
    - Counter: Monotonically increasing value (e.g., total_requests)
    - Gauge: Point-in-time value that can go up/down (e.g., memory_bytes)
    - Histogram: Distribution of observations (e.g., request_duration_seconds)

    Metrics are stored in memory and can be exported for Prometheus scraping.
    Performance overhead target: <2% of execution time (ADR-017 NFR-1).

    Example:
        >>> collector = MetricsCollector()
        >>> collector.counter("api_calls_total", 1.0, labels={"provider": "openai"})
        >>> collector.gauge("memory_bytes", 1024000, labels={"agent_id": "qa-agent"})
        >>>
        >>> async with collector.timer("tool_execution_ms", labels={"tool": "search"}):
        ...     await execute_tool()
        >>>
        >>> metrics_text = await collector.export()
        >>> print(metrics_text)  # Prometheus format
    """

    def __init__(self, backend: str = "prometheus"):
        """
        Initialize metrics collector.

        Args:
            backend: Export backend ("prometheus" only for now)
        """
        self.backend = backend
        self._metrics: list[Metric] = []

        # Storage by metric type
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

        logger.debug("MetricsCollector initialized with backend=%s", backend)

    def counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """
        Increment a counter metric.

        Counters are monotonically increasing values that represent cumulative counts.
        Common uses: total API calls, total errors, total requests.

        Args:
            name: Metric name (e.g., "api_calls_total")
            value: Amount to increment (default: 1.0)
            labels: Key-value labels for dimensions (e.g., {"provider": "openai"})

        Example:
            >>> collector.counter("tool_executions_total", 1.0, {"tool": "search", "status": "success"})
        """
        key = self._metric_key(name, labels or {})
        self._counters[key] += value

        self._metrics.append(
            Metric(
                name=name,
                value=value,
                type="counter",
                timestamp=datetime.now(timezone.utc),
                labels=labels or {},
            )
        )

        logger.debug("Counter incremented: %s += %s", key, value)

    def gauge(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """
        Set a gauge metric value.

        Gauges represent point-in-time values that can increase or decrease.
        Common uses: memory usage, CPU percentage, active connections.

        Args:
            name: Metric name (e.g., "memory_bytes")
            value: Current value
            labels: Key-value labels for dimensions

        Example:
            >>> collector.gauge("active_agents", 5, {"status": "running"})
            >>> collector.gauge("memory_bytes", 1024000, {"agent_id": "qa-agent"})
        """
        key = self._metric_key(name, labels or {})
        self._gauges[key] = value

        self._metrics.append(
            Metric(
                name=name,
                value=value,
                type="gauge",
                timestamp=datetime.now(timezone.utc),
                labels=labels or {},
            )
        )

        logger.debug("Gauge set: %s = %s", key, value)

    def histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """
        Record a histogram observation.

        Histograms track the distribution of observed values.
        Common uses: request latency, response size, processing time.

        Values are aggregated into percentiles (p50, p95, p99) during export.

        Args:
            name: Metric name (e.g., "request_duration_ms")
            value: Observed value
            labels: Key-value labels for dimensions

        Example:
            >>> collector.histogram("tool_latency_ms", 125.5, {"tool": "search"})
            >>> collector.histogram("api_response_bytes", 2048, {"provider": "openai"})
        """
        key = self._metric_key(name, labels or {})
        self._histograms[key].append(value)

        self._metrics.append(
            Metric(
                name=name,
                value=value,
                type="histogram",
                timestamp=datetime.now(timezone.utc),
                labels=labels or {},
            )
        )

        logger.debug("Histogram recorded: %s = %s", key, value)

    @asynccontextmanager
    async def timer(self, name: str, labels: dict[str, str] | None = None):
        """
        Async context manager for timing operations.

        Automatically records operation duration as a histogram metric.
        Uses time.perf_counter() for high-precision timing.

        Args:
            name: Metric name (e.g., "agent_loop_duration_ms")
            labels: Key-value labels for dimensions

        Example:
            >>> async with collector.timer("tool_execution_ms", labels={"tool": "search"}):
            ...     result = await execute_tool()
            # Automatically records duration to histogram
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.histogram(name, duration_ms, labels)
            logger.debug("Timer completed: %s took %.2fms", name, duration_ms)

    @contextmanager
    def timer_sync(self, name: str, labels: dict[str, str] | None = None):
        """
        Synchronous context manager for timing operations.

        Same as timer() but for synchronous code.

        Args:
            name: Metric name
            labels: Key-value labels for dimensions

        Example:
            >>> with collector.timer_sync("file_read_ms"):
            ...     data = file.read()
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.histogram(name, duration_ms, labels)
            logger.debug("Timer completed: %s took %.2fms", name, duration_ms)

    def _metric_key(self, name: str, labels: dict[str, str]) -> str:
        """
        Generate unique key for metric + labels combination.

        Prometheus format: metric_name{label1="value1",label2="value2"}

        Args:
            name: Metric name
            labels: Label dictionary

        Returns:
            Unique key string
        """
        if not labels:
            return name

        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _split_metric_key(self, key: str) -> tuple[str, str]:
        """Split a key built by ``_metric_key`` back into name and label block.

        Needed because a SUFFIXED series (the histogram percentiles) must
        render as ``name_p50{label="value"}`` -- in Prometheus exposition
        format the suffix belongs to the metric NAME, before the label block.
        Appending it to the composed key instead produces
        ``name{label="value"}_p50``, which no scraper accepts.

        Prometheus metric names cannot contain '{', so the first brace is an
        unambiguous boundary, and the key is always produced by
        ``_metric_key`` above.

        Args:
            key: A key previously returned by ``_metric_key``

        Returns:
            (name, label_block); label_block is "" for an unlabelled metric,
            otherwise the literal ``{k="v",...}`` including both braces.
        """
        brace = key.find("{")
        if brace == -1:
            return key, ""
        return key[:brace], key[brace:]

    def _calculate_percentile(self, values: list[float], percentile: float) -> float:
        """
        Calculate percentile from sorted values.

        Uses linear interpolation for accurate percentile calculation.
        For example, p50 of [1,2,3,4,5] returns 3.0 (the median).

        Args:
            values: Sorted list of values
            percentile: Percentile (0.0 to 1.0)

        Returns:
            Value at percentile
        """
        if not values:
            return 0.0

        if len(values) == 1:
            return values[0]

        # Use linear interpolation: index = (len - 1) * percentile
        # This ensures p50 of [1,2,3,4,5] gives index 2.0 (middle value)
        index = (len(values) - 1) * percentile
        lower_index = int(index)
        upper_index = min(lower_index + 1, len(values) - 1)

        # Linear interpolation between lower and upper values
        lower_value = values[lower_index]
        upper_value = values[upper_index]
        fraction = index - lower_index

        return lower_value + (upper_value - lower_value) * fraction

    async def export(self) -> str:
        """
        Export metrics in Prometheus text format.

        Format follows Prometheus exposition format:
        - Counters: metric_name{labels} value
        - Gauges: metric_name{labels} value
        - Histograms: metric_name_p50{labels} value

        Returns:
            Prometheus-formatted metrics text

        Example output:
            api_calls_total{provider="openai"} 150
            memory_bytes{agent_id="qa-agent"} 1024000
            request_duration_ms_p50{endpoint="/execute"} 125.5
            request_duration_ms_p95{endpoint="/execute"} 250.0
            request_duration_ms_p99{endpoint="/execute"} 450.0
        """
        lines = []

        # Export counters
        for key, value in self._counters.items():
            lines.append(f"{key} {value}")

        # Export gauges
        for key, value in self._gauges.items():
            lines.append(f"{key} {value}")

        # Export histograms (p50, p95, p99 percentiles).
        #
        # The percentile suffix attaches to the metric NAME, before the label
        # block -- `latency_ms_p50{route="/x"}`, per the format documented in
        # this method's own docstring. Appending it to the composed key
        # instead yielded `latency_ms{route="/x"}_p50`, which the Prometheus
        # text parser rejects ("Invalid value: '_p50'"), so every LABELLED
        # histogram's percentiles were unscrapeable. Unlabelled histograms
        # were unaffected, which is why counters and gauges -- which append
        # no suffix -- never surfaced it.
        for key, values in self._histograms.items():
            if values:
                sorted_values = sorted(values)
                name, label_block = self._split_metric_key(key)

                p50 = self._calculate_percentile(sorted_values, 0.50)
                p95 = self._calculate_percentile(sorted_values, 0.95)
                p99 = self._calculate_percentile(sorted_values, 0.99)

                lines.append(f"{name}_p50{label_block} {p50}")
                lines.append(f"{name}_p95{label_block} {p95}")
                lines.append(f"{name}_p99{label_block} {p99}")

        export_text = "\n".join(lines)
        logger.debug("Exported %d metric lines", len(lines))

        return export_text

    def get_metric_count(self) -> int:
        """
        Get total number of recorded metric observations.

        Returns:
            Total metric observations
        """
        return len(self._metrics)

    def get_counter_value(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float:
        """
        Get current counter value.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            Current counter value (0.0 if not found)
        """
        key = self._metric_key(name, labels or {})
        return self._counters.get(key, 0.0)

    def get_gauge_value(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float | None:
        """
        Get current gauge value.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            Current gauge value (None if not found)
        """
        key = self._metric_key(name, labels or {})
        return self._gauges.get(key)

    def get_histogram_values(
        self, name: str, labels: dict[str, str] | None = None
    ) -> list[float]:
        """
        Get all histogram observations.

        Args:
            name: Metric name
            labels: Optional labels

        Returns:
            List of observed values (empty list if not found)
        """
        key = self._metric_key(name, labels or {})
        return self._histograms.get(key, []).copy()

    def reset(self) -> None:
        """
        Reset all metrics (useful for testing).

        WARNING: This clears all collected metrics. Use with caution.
        """
        self._metrics.clear()
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        logger.info("All metrics reset")


__all__ = [
    "MetricsCollector",
]

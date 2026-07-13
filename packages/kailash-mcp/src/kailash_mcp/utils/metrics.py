"""
Metrics collection for MCP servers.

Provides comprehensive monitoring of MCP server performance including:
- Tool usage statistics
- Performance metrics (latency, throughput)
- Cache performance
- Error rates
"""

import asyncio
import functools
import logging
import threading
import time
import types
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ``prometheus_client`` is an OPTIONAL dependency (the ``monitoring`` extra —
# see ``pyproject.toml``), so it MUST NOT be a hard import for this module
# (`rules/dependencies.md` § "Declared = Imported"). When absent, the real
# Prometheus histogram below (#1708 W2) is silently disabled — callers still
# get their in-process call/error counters and avg/min/max latency via
# ``get_tool_stats()``. Mirrors the guarded-import pattern established in
# ``kailash.core.monitoring.connection_metrics`` / ``kailash.monitoring.
# asyncsql_metrics`` (#1708 W1c).
try:
    import prometheus_client as _prometheus_client

    _PROMETHEUS_AVAILABLE = True
except (
    ImportError
):  # pragma: no cover — covered by test_mcp_metrics_prometheus_unavailable_degrades
    _prometheus_client: types.ModuleType = types.ModuleType(  # type: ignore[no-redef]
        "prometheus_client"
    )
    _PROMETHEUS_AVAILABLE = False

# Module-level singleton: every ``MetricsCollector`` instance (one per
# ``MCPServer`` — see ``kailash_mcp/server.py``) shares ONE
# ``mcp_tool_duration_seconds`` Histogram on the process-wide default
# ``prometheus_client.REGISTRY``. Registering per-instance would either
# raise "Duplicated timeseries in CollectorRegistry" (same metric name
# registered twice against the default registry) or, if given a private
# registry per instance, would never reach a real process's ``/metrics``
# scrape — which calls ``prometheus_client.generate_latest()`` with no
# registry argument (defaults to this same global ``REGISTRY``). Matches the
# ``_get_acquire_wait_histogram`` pattern in
# ``kailash.core.monitoring.connection_metrics`` (#1708 W1c/G1).
_TOOL_DURATION_HISTOGRAM: "Optional[Any]" = None


def _get_tool_duration_histogram() -> "Optional[Any]":
    """Return the shared ``mcp_tool_duration_seconds`` histogram.

    Created lazily on first use so importing this module never requires
    ``prometheus_client`` to be installed. Uses EXPLICIT second-scale bucket
    boundaries (`rules/observability.md` explicit-buckets requirement) — the
    prometheus_client default buckets are generic-scale (0.005 .. 10.0 with
    coarse steps) and give useless p95/p99 resolution for a tool-call
    duration metric that is typically sub-second.

    ``tool`` label cardinality: every production call site
    (``MCPServer._create_enhanced_tool`` / ``MCPServer.resource`` /
    ``MCPServer.prompt`` in ``kailash_mcp/server.py``) passes a value fixed
    at DECORATION time — ``func.__name__``, ``f"resource:{uri}"``,
    ``f"prompt:{name}"`` — a finite, developer-registered set (the tool /
    resource / prompt names a server author writes in source code), never a
    per-request or client-supplied value. No top-N admission bucketer is
    required for this label (contrast the ML ``tenant_id`` label in
    ``kailash.observability.ml``, which IS per-request/caller-supplied and
    therefore top-N bucketed with an ``"_other"`` overflow bucket).
    """
    global _TOOL_DURATION_HISTOGRAM
    if not _PROMETHEUS_AVAILABLE:
        return None
    if _TOOL_DURATION_HISTOGRAM is not None:
        return _TOOL_DURATION_HISTOGRAM

    metric_name = "mcp_tool_duration_seconds"
    try:
        _TOOL_DURATION_HISTOGRAM = _prometheus_client.Histogram(
            metric_name,
            "Duration of MCP tool / resource / prompt invocations, in seconds",
            ["tool"],
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
        # imported under two distinct qualified names in the same process
        # (e.g. ``kailash_mcp.utils.metrics`` vs
        # ``src.kailash_mcp.utils.metrics``), which gives each import its
        # own module-level ``_TOOL_DURATION_HISTOGRAM`` global even though
        # both share the SAME process-wide ``prometheus_client.REGISTRY``
        # (see ``kailash.core.monitoring.connection_metrics`` #1708 W1c for
        # the sibling scenario + regression test). Whichever import path
        # registers first wins; adopt its already-registered Histogram
        # instance instead of erroring, so the second import path still
        # observes into the one real timeseries.
        existing = _prometheus_client.REGISTRY._names_to_collectors.get(metric_name)
        if existing is None:
            raise
        _TOOL_DURATION_HISTOGRAM = existing
    return _TOOL_DURATION_HISTOGRAM


class MetricsCollector:
    """
    Comprehensive metrics collection for MCP servers.

    Tracks:
    - Tool call frequency and latency
    - Error rates and types
    - Cache performance
    - System resource usage
    """

    def __init__(
        self,
        enabled: bool = True,
        collect_performance: bool = True,
        collect_usage: bool = True,
        history_size: int = 1000,
    ):
        """
        Initialize metrics collector.

        Args:
            enabled: Whether metrics collection is enabled
            collect_performance: Whether to collect performance metrics
            collect_usage: Whether to collect usage statistics
            history_size: Number of recent events to keep in memory
        """
        self.enabled = enabled
        self.collect_performance = collect_performance
        self.collect_usage = collect_usage
        self.history_size = history_size

        # Thread safety
        self._lock = threading.RLock()

        # Usage metrics
        self._tool_calls = defaultdict(int)
        self._tool_errors = defaultdict(int)
        self._tool_latencies = defaultdict(list)

        # Performance history
        self._recent_calls = deque(maxlen=history_size)
        self._recent_errors = deque(maxlen=history_size)

        # System metrics
        self._start_time = time.time()
        self._total_calls = 0
        self._total_errors = 0

    def track_tool_call(
        self,
        tool_name: str,
        latency: float,
        success: bool = True,
        error_type: Optional[str] = None,
    ) -> None:
        """Record a tool call metric."""
        if not self.enabled:
            return

        with self._lock:
            current_time = time.time()

            # Update counters
            self._total_calls += 1
            if self.collect_usage:
                self._tool_calls[tool_name] += 1

            # Track latency
            if self.collect_performance:
                self._tool_latencies[tool_name].append(latency)
                # Keep only recent latencies to prevent memory growth
                if len(self._tool_latencies[tool_name]) > 100:
                    self._tool_latencies[tool_name] = self._tool_latencies[tool_name][
                        -100:
                    ]

            # Real Prometheus histogram (#1708 W2) — the REAL bucketed
            # le=/_sum/_count emission this metric backs, replacing the
            # removed client-side p95/p99 approximation computed over the
            # 100-sample window above (see get_tool_stats() /
            # _export_prometheus()). `latency` is already in seconds (every
            # call site computes it as `time.time() - start_time`), matching
            # the `_seconds` metric name / bucket scale — no unit conversion
            # needed. Telemetry MUST NOT be able to break the tool call it
            # observes (rules/zero-tolerance.md Rule 3 hooks/cleanup
            # exception; same instrumentation-boundary-isolation shape as
            # ConnectionMetricsCollector.track_acquisition), so failures are
            # logged and swallowed here.
            try:
                histogram = _get_tool_duration_histogram()
                if histogram is not None:
                    histogram.labels(tool=tool_name).observe(latency)
            except Exception:
                logger.warning(
                    "mcp_metrics.tool_duration_histogram_observe_failed",
                    exc_info=True,
                )

            # Track errors
            if not success:
                self._total_errors += 1
                if self.collect_usage:
                    self._tool_errors[tool_name] += 1

                if self.collect_performance:
                    self._recent_errors.append(
                        {
                            "tool": tool_name,
                            "timestamp": current_time,
                            "error_type": error_type,
                        }
                    )

            # Track recent calls
            if self.collect_performance:
                self._recent_calls.append(
                    {
                        "tool": tool_name,
                        "timestamp": current_time,
                        "latency": latency,
                        "success": success,
                    }
                )

    def track_tool(self, tool_name: Optional[str] = None):
        """
        Decorator to automatically track tool call metrics.

        Args:
            tool_name: Optional tool name override

        Returns:
            Decorated function with metrics tracking
        """

        def decorator(func: F) -> F:
            if not self.enabled:
                return func

            actual_tool_name = tool_name or func.__name__

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error_type = None

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_type = type(e).__name__
                    raise
                finally:
                    latency = time.time() - start_time
                    self.track_tool_call(actual_tool_name, latency, success, error_type)

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                success = True
                error_type = None

                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_type = type(e).__name__
                    raise
                finally:
                    latency = time.time() - start_time
                    self.track_tool_call(actual_tool_name, latency, success, error_type)

            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper  # type: ignore[return-value]
            else:
                return sync_wrapper  # type: ignore[return-value]

        return decorator

    def get_tool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all tools."""
        with self._lock:
            stats = {}

            for tool_name in set(
                list(self._tool_calls.keys()) + list(self._tool_errors.keys())
            ):
                calls = self._tool_calls[tool_name]
                errors = self._tool_errors[tool_name]
                latencies = self._tool_latencies.get(tool_name, [])

                tool_stats = {
                    "calls": calls,
                    "errors": errors,
                    "error_rate": errors / calls if calls > 0 else 0,
                }

                if latencies:
                    tool_stats.update(
                        {
                            "avg_latency": sum(latencies) / len(latencies),
                            "min_latency": min(latencies),
                            "max_latency": max(latencies),
                            # p95_latency / p99_latency REMOVED (#1708 W2) —
                            # this in-process 100-sample-window
                            # approximation was a fake summary-as-histogram
                            # (rules/observability.md explicit-buckets +
                            # G1 "no fake summary" finding). Query real
                            # percentiles from the mcp_tool_duration_seconds
                            # Histogram (see _get_tool_duration_histogram())
                            # via Prometheus `histogram_quantile()` instead.
                        }
                    )

                stats[tool_name] = tool_stats

            return stats

    def get_server_stats(self) -> Dict[str, Any]:
        """Get overall server statistics."""
        with self._lock:
            uptime = time.time() - self._start_time

            stats = {
                "uptime_seconds": uptime,
                "total_calls": self._total_calls,
                "total_errors": self._total_errors,
                "overall_error_rate": (
                    self._total_errors / self._total_calls
                    if self._total_calls > 0
                    else 0
                ),
                "calls_per_second": self._total_calls / uptime if uptime > 0 else 0,
            }

            # Recent activity
            if self.collect_performance:
                recent_window = 300  # 5 minutes
                current_time = time.time()

                recent_calls = [
                    call
                    for call in self._recent_calls
                    if current_time - call["timestamp"] <= recent_window
                ]

                if recent_calls:
                    recent_latencies = [call["latency"] for call in recent_calls]
                    recent_errors = sum(
                        1 for call in recent_calls if not call["success"]
                    )

                    # NOTE (#1708 W2 scope): `recent_p95_latency_5min` below
                    # is a DIFFERENT surface than the per-tool p95/p99
                    # removed from get_tool_stats() / _export_prometheus().
                    # This is a server-wide, in-process-only debug snapshot
                    # (dict introspection via get_server_stats() /
                    # export_metrics("dict")) — grep confirms
                    # _export_prometheus() never reads this key, so it never
                    # reaches a Prometheus text scrape and is not the
                    # fake-summary-as-histogram pattern that motivated the
                    # per-tool removal. Left as-is.
                    stats.update(
                        {
                            "recent_calls_5min": len(recent_calls),
                            "recent_errors_5min": recent_errors,
                            "recent_error_rate_5min": recent_errors / len(recent_calls),
                            "recent_avg_latency_5min": sum(recent_latencies)
                            / len(recent_latencies),
                            "recent_p95_latency_5min": self._percentile(
                                recent_latencies, 95
                            ),
                        }
                    )

            return stats

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of recent errors."""
        with self._lock:
            if not self.collect_performance:
                return {"error": "Performance collection disabled"}

            recent_window = 3600  # 1 hour
            current_time = time.time()

            recent_errors = [
                error
                for error in self._recent_errors
                if current_time - error["timestamp"] <= recent_window
            ]

            # Group by error type
            error_types = defaultdict(int)
            for error in recent_errors:
                error_types[error.get("error_type", "Unknown")] += 1

            # Group by tool
            error_tools = defaultdict(int)
            for error in recent_errors:
                error_tools[error["tool"]] += 1

            return {
                "total_recent_errors": len(recent_errors),
                "error_types": dict(error_types),
                "error_by_tool": dict(error_tools),
                "window_hours": 1,
            }

    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile value."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = k - f

        if f == len(sorted_values) - 1:
            return sorted_values[f]
        else:
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c

    def export_metrics(self, format: str = "dict") -> Any:
        """
        Export all metrics in specified format.

        Args:
            format: Export format ("dict", "json", "prometheus")

        Returns:
            Metrics in requested format
        """
        with self._lock:
            metrics = {
                "server": self.get_server_stats(),
                "tools": self.get_tool_stats(),
                "errors": self.get_error_summary(),
                "collection_config": {
                    "enabled": self.enabled,
                    "collect_performance": self.collect_performance,
                    "collect_usage": self.collect_usage,
                    "history_size": self.history_size,
                },
            }

            if format == "dict":
                return metrics
            elif format == "json":
                import json

                return json.dumps(metrics, indent=2)
            elif format == "prometheus":
                return self._export_prometheus(metrics)
            else:
                raise ValueError(f"Unsupported export format: {format}")

    def _export_prometheus(self, metrics: Dict[str, Any]) -> str:
        """Export metrics in Prometheus format.

        NOTE (#1708 W2): this hand-rolled exporter is a legacy introspection
        surface (``export_metrics(format="prometheus")``) — grep confirms
        the only production call site in ``kailash_mcp/server.py``
        (``get_server_stats()``) invokes ``export_metrics()`` with the
        default ``format="dict"``; nothing reaches ``format="prometheus"``.
        The REAL production ``/metrics`` surface for tool-call duration is
        the ``mcp_tool_duration_seconds`` Histogram registered directly on
        ``prometheus_client.REGISTRY`` by ``track_tool_call()`` — it reaches
        any process-level ``/metrics`` scrape via
        ``prometheus_client.generate_latest()`` (no registry argument = the
        same global default) independent of whether this method is ever
        called. p95/p99 lines were REMOVED here (previously
        ``mcp_tool_latency_p95`` / ``mcp_tool_latency_p99``, computed
        client-side over a 100-sample window) — query real percentiles via
        Prometheus ``histogram_quantile()`` against
        ``mcp_tool_duration_seconds_bucket`` instead.
        """
        lines = []

        # Server metrics
        server = metrics["server"]
        lines.append(f"mcp_server_uptime_seconds {server['uptime_seconds']}")
        lines.append(f"mcp_server_total_calls {server['total_calls']}")
        lines.append(f"mcp_server_total_errors {server['total_errors']}")
        lines.append(f"mcp_server_error_rate {server['overall_error_rate']}")
        lines.append(f"mcp_server_calls_per_second {server['calls_per_second']}")

        # Tool metrics
        for tool_name, tool_stats in metrics["tools"].items():
            labels = f'{{tool="{tool_name}"}}'
            lines.append(f"mcp_tool_calls{labels} {tool_stats['calls']}")
            lines.append(f"mcp_tool_errors{labels} {tool_stats['errors']}")
            lines.append(f"mcp_tool_error_rate{labels} {tool_stats['error_rate']}")

            if "avg_latency" in tool_stats:
                lines.append(
                    f"mcp_tool_latency_avg{labels} {tool_stats['avg_latency']}"
                )

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._tool_calls.clear()
            self._tool_errors.clear()
            self._tool_latencies.clear()
            self._recent_calls.clear()
            self._recent_errors.clear()
            self._start_time = time.time()
            self._total_calls = 0
            self._total_errors = 0


# Global metrics collector instance
_global_metrics = MetricsCollector()


def track_tool(tool_name: Optional[str] = None):
    """
    Convenience decorator using global metrics collector.

    Args:
        tool_name: Optional tool name override

    Returns:
        Decorated function with metrics tracking
    """
    return _global_metrics.track_tool(tool_name)


def get_metrics() -> Dict[str, Any]:
    """Get metrics from global collector."""
    return _global_metrics.export_metrics()


def reset_metrics() -> None:
    """Reset global metrics."""
    _global_metrics.reset()

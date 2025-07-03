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
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


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
                return async_wrapper
            else:
                return sync_wrapper

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
                            "p95_latency": self._percentile(latencies, 95),
                            "p99_latency": self._percentile(latencies, 99),
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
        """Export metrics in Prometheus format."""
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
                lines.append(
                    f"mcp_tool_latency_p95{labels} {tool_stats['p95_latency']}"
                )
                lines.append(
                    f"mcp_tool_latency_p99{labels} {tool_stats['p99_latency']}"
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

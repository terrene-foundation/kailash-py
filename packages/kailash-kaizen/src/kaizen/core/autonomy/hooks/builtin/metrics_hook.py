"""
Metrics collection hook for monitoring systems.

Collects Prometheus-compatible metrics for hook events with dimensional labels.

SECURITY: Supports agent ID hashing to prevent information disclosure (Finding #11 fix).
"""

import hashlib
import logging
from collections import defaultdict
from typing import ClassVar, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult
from .performance_profiler_hook import PerformanceProfilerHook

logger = logging.getLogger(__name__)


class MetricsHook(BaseHook):
    """
    Collects Prometheus-compatible metrics with dimensional labels.

    Features:
    - Native prometheus_client integration
    - Counter/Histogram/Gauge metrics
    - Dimensional labels (agent_id, event_type, operation)
    - Percentile calculation (p50/p95/p99) via PerformanceProfilerHook integration
    - HTTP /metrics endpoint support

    Example:
        >>> hook = MetricsHook()
        >>> context = HookContext(...)
        >>> result = await hook.handle(context)
        >>> metrics_text = hook.export_prometheus()
    """

    # Define which events this hook handles
    events: ClassVar[list[HookEvent]] = list(HookEvent)  # All events

    def __init__(
        self,
        registry: Optional[CollectorRegistry] = None,
        enable_percentiles: bool = True,
        profiler: Optional[PerformanceProfilerHook] = None,
        hash_agent_ids: bool = False,
    ):
        """
        Initialize metrics hook with Prometheus integration.

        Args:
            registry: Prometheus registry (creates new if None)
            enable_percentiles: Enable percentile calculation via profiler
            profiler: PerformanceProfilerHook instance (creates new if None and percentiles enabled)
            hash_agent_ids: Hash agent IDs before exposing in metrics (SECURITY FIX #11)

        Example:
            >>> # Production usage with agent ID hashing
            >>> hook = MetricsHook(hash_agent_ids=True)  # Prevents agent enumeration
        """
        super().__init__(name="metrics_hook")

        # Prometheus registry
        self.registry = registry or CollectorRegistry()

        # Percentile support via PerformanceProfilerHook
        self.enable_percentiles = enable_percentiles
        self.profiler = profiler if enable_percentiles else None
        if self.enable_percentiles and self.profiler is None:
            self.profiler = PerformanceProfilerHook()

        # Security: Hash agent IDs (SECURITY FIX #11)
        self.hash_agent_ids = hash_agent_ids

        # Define Prometheus metrics with dimensional labels
        self.event_counter = Counter(
            "kaizen_hook_events_total",
            "Total hook events by type and agent",
            ["event_type", "agent_id"],
            registry=self.registry,
        )

        self.operation_duration = Histogram(
            "kaizen_operation_duration_seconds",
            "Operation duration by type and agent",
            ["operation", "agent_id"],
            registry=self.registry,
            buckets=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.075,
                0.1,
                0.25,
                0.5,
                0.75,
                1.0,
                2.5,
                5.0,
                7.5,
                10.0,
            ),
        )

        self.active_agents = Gauge(
            "kaizen_active_agents", "Number of active agents", registry=self.registry
        )

        # Track active agents
        self._active_agent_ids: set[str] = set()

        # Backward compatibility: In-memory counters
        self.counters: dict[str, int] = defaultdict(int)
        self.agent_counters: dict[str, int] = defaultdict(int)

    def _hash_agent_id(self, agent_id: str) -> str:
        """
        Hash agent ID using SHA-256 (SECURITY FIX #11).

        Args:
            agent_id: Original agent ID

        Returns:
            First 16 characters of SHA-256 hash (sufficient for uniqueness)

        Example:
            >>> hook = MetricsHook(hash_agent_ids=True)
            >>> hashed = hook._hash_agent_id("agent-123")
            >>> print(len(hashed))  # 16 characters
            16
        """
        return hashlib.sha256(agent_id.encode()).hexdigest()[:16]

    async def handle(self, context: HookContext) -> HookResult:
        """
        Collect metrics for the event with optional agent ID hashing.

        Args:
            context: Hook execution context

        Returns:
            HookResult with metric data
        """
        try:
            event_name = context.event_type.value
            agent_id = context.agent_id

            # SECURITY FIX #11: Hash agent ID if enabled
            metrics_agent_id = (
                self._hash_agent_id(agent_id) if self.hash_agent_ids else agent_id
            )

            # Increment Prometheus counter with labels
            self.event_counter.labels(
                event_type=event_name, agent_id=metrics_agent_id
            ).inc()

            # Update active agents gauge
            self._active_agent_ids.add(metrics_agent_id)
            self.active_agents.set(len(self._active_agent_ids))

            # Backward compatibility: Update in-memory counters
            metric_name = f"kaizen_hook_{event_name}"
            self.counters[metric_name] += 1
            agent_metric = f"kaizen_agent_{metrics_agent_id}_events"
            self.agent_counters[agent_metric] += 1

            # Track duration for POST events
            duration_ms = None
            if self.enable_percentiles and self.profiler is not None:
                # Delegate to profiler for duration tracking
                profiler_result = await self.profiler.handle(context)

                if profiler_result.success and profiler_result.data:
                    duration_ms = profiler_result.data.get("duration_ms")

                    if duration_ms is not None:
                        # Record in Prometheus histogram (convert ms to seconds)
                        operation = event_name.replace("post_", "")
                        self.operation_duration.labels(
                            operation=operation, agent_id=metrics_agent_id
                        ).observe(duration_ms / 1000.0)

            return HookResult(
                success=True,
                data={
                    "metric": metric_name,
                    "count": self.counters[metric_name],
                    "agent_metric": agent_metric,
                    "agent_count": self.agent_counters[agent_metric],
                    "duration_ms": duration_ms,
                },
            )

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            return HookResult(success=False, error=str(e))

    def export_prometheus(self) -> bytes:
        """
        Export metrics in Prometheus text format.

        Returns:
            Metrics in Prometheus exposition format (bytes)

        Example:
            >>> hook = MetricsHook()
            >>> metrics_text = hook.export_prometheus()
            >>> print(metrics_text.decode('utf-8'))
        """
        return generate_latest(self.registry)

    def get_percentiles(self, operation: str) -> dict[str, float]:
        """
        Get p50/p95/p99 percentiles for operation (delegated to profiler).

        Args:
            operation: Operation name (e.g., "tool_use", "agent_loop")

        Returns:
            Dictionary with p50_ms, p95_ms, p99_ms keys

        Example:
            >>> hook = MetricsHook(enable_percentiles=True)
            >>> percentiles = hook.get_percentiles("tool_use")
            >>> print(f"p95: {percentiles['p95_ms']}ms")
        """
        if not self.enable_percentiles or self.profiler is None:
            return {}

        report = self.profiler.get_performance_report()
        if operation not in report:
            return {}

        return {
            "p50_ms": report[operation]["p50_ms"],
            "p95_ms": report[operation]["p95_ms"],
            "p99_ms": report[operation]["p99_ms"],
        }

    def get_metrics(self) -> dict[str, int]:
        """
        Get all collected metrics (backward compatibility).

        Returns:
            Dictionary of metric names to counts

        Note:
            This method is kept for backward compatibility.
            For Prometheus metrics, use export_prometheus() instead.
        """
        return {**self.counters, **self.agent_counters}

    def reset_metrics(self) -> None:
        """
        Reset all metric counters.

        Note:
            This resets in-memory counters but NOT Prometheus metrics.
            Prometheus metrics are cumulative by design.
        """
        self.counters.clear()
        self.agent_counters.clear()
        self._active_agent_ids.clear()

        if self.profiler:
            self.profiler.reset_metrics()

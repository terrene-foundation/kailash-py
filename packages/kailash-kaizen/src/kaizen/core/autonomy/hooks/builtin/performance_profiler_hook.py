"""
Performance profiling hook for latency tracking.

Tracks execution times for tools, agent loops, and specialists.
"""

from collections import defaultdict
from typing import ClassVar

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult


class PerformanceProfilerHook(BaseHook):
    """
    Tracks execution latency for performance profiling.

    Measures time between PRE and POST events to calculate durations.
    """

    # Define which events this hook handles
    events: ClassVar[list[HookEvent]] = list(HookEvent)  # All events for timing

    def __init__(self):
        """Initialize performance profiler hook"""
        super().__init__(name="performance_profiler_hook")

        # Track start times for PRE events
        self._start_times: dict[str, float] = {}

        # Latency statistics
        self.latencies: dict[str, list[float]] = defaultdict(list)

    async def handle(self, context: HookContext) -> HookResult:
        """
        Track performance metrics for the event.

        Args:
            context: Hook execution context

        Returns:
            HookResult with latency data
        """
        try:
            event_name = context.event_type.value

            # PRE events: Record start time
            if event_name.startswith("pre_"):
                operation = event_name.replace("pre_", "")
                key = f"{context.agent_id}:{operation}"
                self._start_times[key] = context.timestamp

                return HookResult(success=True, data={"operation": operation})

            # POST events: Calculate duration
            elif event_name.startswith("post_"):
                operation = event_name.replace("post_", "")
                key = f"{context.agent_id}:{operation}"

                if key in self._start_times:
                    start_time = self._start_times[key]
                    duration_ms = (context.timestamp - start_time) * 1000

                    # Store latency
                    self.latencies[operation].append(duration_ms)

                    # Clean up start time
                    del self._start_times[key]

                    return HookResult(
                        success=True,
                        data={
                            "operation": operation,
                            "duration_ms": duration_ms,
                            "avg_duration_ms": self._calculate_average(operation),
                            "p95_duration_ms": self._calculate_percentile(
                                operation, 95
                            ),
                        },
                    )

            return HookResult(success=True)

        except Exception as e:
            return HookResult(success=False, error=str(e))

    def _calculate_average(self, operation: str) -> float:
        """Calculate average latency for operation"""
        latencies = self.latencies.get(operation, [])
        if not latencies:
            return 0.0
        return sum(latencies) / len(latencies)

    def _calculate_percentile(self, operation: str, percentile: int) -> float:
        """Calculate percentile latency for operation"""
        latencies = self.latencies.get(operation, [])
        if not latencies:
            return 0.0

        sorted_latencies = sorted(latencies)
        index = int(len(sorted_latencies) * percentile / 100)
        index = min(index, len(sorted_latencies) - 1)

        return sorted_latencies[index]

    def get_performance_report(self) -> dict[str, dict[str, float]]:
        """
        Get comprehensive performance report.

        Returns:
            Dictionary with performance metrics per operation
        """
        report = {}

        for operation, latencies in self.latencies.items():
            if not latencies:
                continue

            sorted_latencies = sorted(latencies)

            report[operation] = {
                "count": len(latencies),
                "avg_ms": sum(latencies) / len(latencies),
                "min_ms": sorted_latencies[0],
                "max_ms": sorted_latencies[-1],
                "p50_ms": sorted_latencies[len(sorted_latencies) // 2],
                "p95_ms": sorted_latencies[int(len(sorted_latencies) * 0.95)],
                "p99_ms": sorted_latencies[int(len(sorted_latencies) * 0.99)],
            }

        return report

    def reset_metrics(self) -> None:
        """Reset all performance metrics"""
        self._start_times.clear()
        self.latencies.clear()

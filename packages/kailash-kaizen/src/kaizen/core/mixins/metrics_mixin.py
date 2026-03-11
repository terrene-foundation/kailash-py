"""
Metrics Mixin for BaseAgent.

Provides metrics collection for agent operations including:
- Execution counts (total, success, failure)
- Execution duration histograms
- Token usage metrics (if available)
- Custom metric support
"""

import functools
import inspect
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent


class AgentMetrics:
    """Simple metrics collector for agent operations."""

    def __init__(self, prefix: str = "agent"):
        """
        Initialize metrics collector.

        Args:
            prefix: Metric name prefix (e.g., 'agent.SimpleQAAgent')
        """
        self.prefix = prefix
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = {}

    def increment(self, name: str, value: int = 1) -> None:
        """
        Increment a counter metric.

        Args:
            name: Counter name
            value: Value to increment by (default 1)
        """
        full_name = f"{self.prefix}.{name}"
        self._counters[full_name] = self._counters.get(full_name, 0) + value

    def set_gauge(self, name: str, value: float) -> None:
        """
        Set a gauge metric.

        Args:
            name: Gauge name
            value: Current value
        """
        full_name = f"{self.prefix}.{name}"
        self._gauges[full_name] = value

    def observe(self, name: str, value: float) -> None:
        """
        Record a histogram observation.

        Args:
            name: Histogram name
            value: Observed value
        """
        full_name = f"{self.prefix}.{name}"
        if full_name not in self._histograms:
            self._histograms[full_name] = []
        self._histograms[full_name].append(value)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all collected metrics.

        Returns:
            Dictionary with counters, gauges, and histogram summaries
        """
        result = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {},
        }

        # Calculate histogram summaries
        for name, values in self._histograms.items():
            if values:
                result["histograms"][name] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                }

        return result

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()


class MetricsMixin:
    """
    Mixin that adds metrics collection to agents.

    Automatically tracks:
    - executions.total: Total execution count
    - executions.success: Successful executions
    - executions.failure: Failed executions
    - execution.duration_seconds: Execution duration histogram

    Example:
        config = BaseAgentConfig(metrics_enabled=True)
        agent = SimpleQAAgent(config)
        await agent.run(question="test")
        metrics = agent._metrics.get_metrics()
        print(metrics['counters']['agent.executions.total'])  # 1
    """

    @classmethod
    def apply(cls, agent: "BaseAgent") -> None:
        """
        Apply metrics collection to agent.

        Creates an AgentMetrics instance and wraps the run method
        with metrics collection.

        Args:
            agent: The agent instance to apply metrics to
        """
        agent_name = agent.__class__.__name__
        agent._metrics = AgentMetrics(prefix=f"agent.{agent_name}")

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)

        if is_async:

            @functools.wraps(original_run)
            async def metered_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with metrics collection."""
                agent._metrics.increment("executions.total")
                start_time = time.monotonic()

                try:
                    result = await original_run(*args, **kwargs)
                    agent._metrics.increment("executions.success")
                    return result

                except Exception:
                    agent._metrics.increment("executions.failure")
                    raise

                finally:
                    duration = time.monotonic() - start_time
                    agent._metrics.observe("execution.duration_seconds", duration)

            agent.run = metered_run_async
        else:

            @functools.wraps(original_run)
            def metered_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with metrics collection."""
                agent._metrics.increment("executions.total")
                start_time = time.monotonic()

                try:
                    result = original_run(*args, **kwargs)
                    agent._metrics.increment("executions.success")
                    return result

                except Exception:
                    agent._metrics.increment("executions.failure")
                    raise

                finally:
                    duration = time.monotonic() - start_time
                    agent._metrics.observe("execution.duration_seconds", duration)

            agent.run = metered_run_sync

    @classmethod
    def get_metrics(cls, agent: "BaseAgent") -> Dict[str, Any]:
        """
        Get metrics from agent.

        Args:
            agent: The agent instance

        Returns:
            Dictionary of collected metrics
        """
        metrics = getattr(agent, "_metrics", None)
        if metrics:
            return metrics.get_metrics()
        return {}

"""
Prometheus Metrics Collection with Hooks - Production Example

Demonstrates how to use the hooks system to collect and export metrics
in Prometheus format for monitoring agent performance and behavior.

Use cases:
- Monitor agent execution rates and latencies
- Track success/failure rates
- Collect custom business metrics
- Alert on SLO violations

Run:
    python examples/autonomy/hooks/prometheus_metrics_example.py
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.types import (
    HookContext,
    HookEvent,
    HookPriority,
    HookResult,
)
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# =============================================================================
# Metrics Collection Hook Implementation
# =============================================================================


class PrometheusMetricsHook:
    """
    Production-ready Prometheus metrics collection hook.

    Collects metrics about agent execution and exposes them in
    Prometheus format for scraping.

    Metrics collected:
    - agent_loop_duration_seconds (histogram)
    - agent_loop_total (counter)
    - agent_loop_errors_total (counter)
    - agent_active_loops (gauge)
    """

    def __init__(self):
        """Initialize metrics collectors."""
        # In production, use prometheus_client library:
        # from prometheus_client import Counter, Histogram, Gauge
        # self.loop_duration = Histogram(...)
        # self.loop_total = Counter(...)
        # self.loop_errors = Counter(...)
        # self.active_loops = Gauge(...)

        # For demo, use simple dictionaries
        self.loop_durations: List[float] = []
        self.loop_counts: Dict[str, int] = defaultdict(int)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.active_loops = 0
        self.loop_start_times: Dict[str, float] = {}

    async def record_loop_start(self, context: HookContext) -> HookResult:
        """
        Record agent loop start.

        Increments active loops gauge and stores start time for duration tracking.
        """
        trace_id = context.trace_id
        agent_id = context.agent_id

        # Increment active loops
        self.active_loops += 1

        # Store start time
        self.loop_start_times[trace_id] = time.time()

        # Increment total counter
        self.loop_counts[agent_id] += 1

        print(
            f"📊 [METRICS] Loop started: agent={agent_id} "
            f"active={self.active_loops} total={self.loop_counts[agent_id]}"
        )

        return HookResult(success=True, data={"active_loops": self.active_loops})

    async def record_loop_end(self, context: HookContext) -> HookResult:
        """
        Record agent loop completion.

        Decrements active loops, calculates duration, and records success/failure.
        """
        trace_id = context.trace_id
        agent_id = context.agent_id

        # Decrement active loops
        self.active_loops -= 1

        # Calculate duration
        if trace_id in self.loop_start_times:
            duration = time.time() - self.loop_start_times.pop(trace_id)
            self.loop_durations.append(duration)

            # In production, record to histogram:
            # self.loop_duration.labels(agent_id=agent_id).observe(duration)
        else:
            duration = 0

        # Check for errors
        result = context.data.get("result", {})
        if not result.get("success", True):
            self.error_counts[agent_id] += 1
            # In production: self.loop_errors.labels(agent_id=agent_id).inc()

        print(
            f"✅ [METRICS] Loop ended: agent={agent_id} "
            f"duration={duration*1000:.1f}ms "
            f"errors={self.error_counts[agent_id]}"
        )

        return HookResult(
            success=True,
            data={"duration_seconds": duration, "active_loops": self.active_loops},
        )

    def export_prometheus_metrics(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics
        """
        # Calculate statistics
        if self.loop_durations:
            durations_sorted = sorted(self.loop_durations)
            count = len(durations_sorted)
            p50_idx = int(count * 0.5)
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)

            p50 = durations_sorted[p50_idx]
            p95 = durations_sorted[p95_idx]
            p99 = durations_sorted[p99_idx]
            total_duration = sum(durations_sorted)
        else:
            p50 = p95 = p99 = total_duration = 0
            count = 0

        # Format as Prometheus metrics
        metrics = []

        # Histogram (duration percentiles)
        metrics.append("# HELP agent_loop_duration_seconds Agent loop duration")
        metrics.append("# TYPE agent_loop_duration_seconds histogram")
        metrics.append(f'agent_loop_duration_seconds{{quantile="0.5"}} {p50}')
        metrics.append(f'agent_loop_duration_seconds{{quantile="0.95"}} {p95}')
        metrics.append(f'agent_loop_duration_seconds{{quantile="0.99"}} {p99}')
        metrics.append(f"agent_loop_duration_seconds_sum {total_duration}")
        metrics.append(f"agent_loop_duration_seconds_count {count}")

        # Counter (total loops)
        metrics.append("\n# HELP agent_loop_total Total agent loops executed")
        metrics.append("# TYPE agent_loop_total counter")
        for agent_id, count in self.loop_counts.items():
            metrics.append(f'agent_loop_total{{agent_id="{agent_id}"}} {count}')

        # Counter (errors)
        metrics.append("\n# HELP agent_loop_errors_total Total agent loop errors")
        metrics.append("# TYPE agent_loop_errors_total counter")
        for agent_id, count in self.error_counts.items():
            metrics.append(f'agent_loop_errors_total{{agent_id="{agent_id}"}} {count}')

        # Gauge (active loops)
        metrics.append("\n# HELP agent_active_loops Currently active agent loops")
        metrics.append("# TYPE agent_active_loops gauge")
        metrics.append(f"agent_active_loops {self.active_loops}")

        return "\n".join(metrics)


# =============================================================================
# Example Agent
# =============================================================================


class QuestionAnswerSignature(Signature):
    """Simple Q&A signature."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Agent answer")


@dataclass
class AgentConfig:
    """Agent configuration."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.7


# =============================================================================
# Main Demo
# =============================================================================


async def main():
    """
    Demonstrate Prometheus metrics collection with hooks.

    Shows:
    1. Hook registration for metrics collection
    2. Automatic metrics recording on agent execution
    3. Prometheus format export
    4. Monitoring multiple agents
    """
    print("=" * 70)
    print("Prometheus Metrics Collection with Hooks - Production Example")
    print("=" * 70)

    # Step 1: Create metrics hook
    print("\n1️⃣  Creating Prometheus metrics hook...")
    metrics_hook = PrometheusMetricsHook()

    # Step 2: Register hook with manager
    print("2️⃣  Registering hooks for PRE/POST_AGENT_LOOP...")
    hook_manager = HookManager()
    hook_manager.register(
        HookEvent.PRE_AGENT_LOOP, metrics_hook.record_loop_start, HookPriority.NORMAL
    )
    hook_manager.register(
        HookEvent.POST_AGENT_LOOP, metrics_hook.record_loop_end, HookPriority.NORMAL
    )

    print("   ✅ Registered 2 metrics hooks")

    # Step 3: Create agent with metrics
    print("\n3️⃣  Creating agent with metrics collection...")
    agent = BaseAgent(
        config=AgentConfig(),
        signature=QuestionAnswerSignature(),
        hook_manager=hook_manager,
    )

    # Step 4: Run multiple agent executions to collect metrics
    print("\n4️⃣  Running agent multiple times to collect metrics...\n")

    questions = [
        "What is Prometheus?",
        "What is a histogram?",
        "What is a gauge?",
        "What is a counter?",
        "What are percentiles?",
    ]

    for i, question in enumerate(questions, 1):
        print(f"   Execution {i}/5:")
        agent.run(question=question)
        await asyncio.sleep(0.05)  # Small delay between executions

    # Step 5: Export metrics in Prometheus format
    print("\n5️⃣  Exporting metrics in Prometheus format...\n")
    print("=" * 70)
    print(metrics_hook.export_prometheus_metrics())
    print("=" * 70)

    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("=" * 70)
    print("\n💡 Key Takeaways:")
    print("   1. Hooks enable automatic metrics collection with zero code changes")
    print("   2. Metrics track duration, throughput, and error rates")
    print("   3. Prometheus format ready for scraping")
    print("   4. Production-ready: swap to prometheus_client for real metrics")
    print("\n📚 Next Steps:")
    print("   - Install Prometheus client: pip install prometheus-client")
    print("   - Expose metrics endpoint (e.g., /metrics HTTP endpoint)")
    print("   - Configure Prometheus to scrape your service")
    print("   - Set up Grafana dashboards for visualization")
    print("   - Define SLOs and alerting rules")


if __name__ == "__main__":
    asyncio.run(main())

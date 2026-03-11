"""Example 5: Performance Monitoring with Debug Agent

This example demonstrates tracking Debug Agent metrics and execution times
for monitoring and observability.

Usage:
    python examples/debug_agent/05_performance_monitoring.py
"""

import asyncio
import time
from collections import defaultdict
from statistics import mean, median, stdev

from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class PerformanceMonitor:
    """Monitor Debug Agent performance metrics."""

    def __init__(self):
        self.error_count = 0
        self.category_counts = defaultdict(int)
        self.execution_times = []
        self.solution_counts = []
        self.confidence_scores = []

    def record(self, report):
        """Record metrics from debug report."""
        self.error_count += 1
        self.category_counts[report.error_category.category] += 1
        self.execution_times.append(report.execution_time)
        self.solution_counts.append(len(report.suggested_solutions))
        self.confidence_scores.append(report.error_category.confidence)

    def get_statistics(self):
        """Calculate performance statistics."""
        return {
            "total_errors": self.error_count,
            "category_breakdown": dict(self.category_counts),
            "execution_time": {
                "mean": mean(self.execution_times),
                "median": median(self.execution_times),
                "min": min(self.execution_times),
                "max": max(self.execution_times),
                "stdev": (
                    stdev(self.execution_times) if len(self.execution_times) > 1 else 0
                ),
            },
            "solutions": {
                "mean": mean(self.solution_counts),
                "median": median(self.solution_counts),
                "total": sum(self.solution_counts),
            },
            "confidence": {
                "mean": mean(self.confidence_scores),
                "median": median(self.confidence_scores),
                "min": min(self.confidence_scores),
                "max": max(self.confidence_scores),
            },
        }

    def print_report(self):
        """Print performance report."""
        stats = self.get_statistics()

        print("=" * 80)
        print("Performance Monitoring Report")
        print("=" * 80)
        print()

        print(f"Total Errors Analyzed: {stats['total_errors']}")
        print()

        print("Category Breakdown:")
        for category, count in sorted(stats["category_breakdown"].items()):
            percentage = (count / stats["total_errors"]) * 100
            print(f"  {category:<20} {count:>3} ({percentage:>5.1f}%)")
        print()

        print("Execution Time Statistics:")
        print(f"  Mean:   {stats['execution_time']['mean']:>8.2f} ms")
        print(f"  Median: {stats['execution_time']['median']:>8.2f} ms")
        print(f"  Min:    {stats['execution_time']['min']:>8.2f} ms")
        print(f"  Max:    {stats['execution_time']['max']:>8.2f} ms")
        print(f"  StdDev: {stats['execution_time']['stdev']:>8.2f} ms")
        print()

        print("Solutions Statistics:")
        print(f"  Total:  {stats['solutions']['total']:>8}")
        print(f"  Mean:   {stats['solutions']['mean']:>8.2f}")
        print(f"  Median: {stats['solutions']['median']:>8.1f}")
        print()

        print("Confidence Statistics:")
        print(f"  Mean:   {stats['confidence']['mean']:>8.2%}")
        print(f"  Median: {stats['confidence']['median']:>8.2%}")
        print(f"  Min:    {stats['confidence']['min']:>8.2%}")
        print(f"  Max:    {stats['confidence']['max']:>8.2%}")
        print()


def create_test_errors():
    """Create various test errors."""
    return [
        ValueError("Missing required parameter 'id' in CreateNode"),
        TypeError("expected int, got str '25'"),
        ValueError("Source node 'create_user' not found in workflow"),
        ValueError("UPDATE request must contain 'filter' field"),
        ValueError("cannot manually set 'created_at' - auto-managed field"),
        RuntimeError("Event loop is closed"),
        TimeoutError("query canceled due to statement timeout"),
        ValueError("Missing required parameter 'id' in CreateNode"),  # Duplicate
        ValueError("parameter 'email' cannot be empty"),
        TypeError("Cannot connect int output to str input"),
    ]


def main():
    """Performance monitoring example."""
    print("=" * 80)
    print("Example 5: Performance Monitoring")
    print("=" * 80)
    print()

    # Initialize DataFlow
    db = DataFlow(":memory:")

    @db.model
    class User:
        id: str
        name: str
        email: str

    asyncio.run(db.initialize())

    # Initialize Debug Agent
    kb = KnowledgeBase(
        "src/dataflow/debug/patterns.yaml", "src/dataflow/debug/solutions.yaml"
    )
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    # Initialize performance monitor
    monitor = PerformanceMonitor()

    # Create test errors
    test_errors = create_test_errors()

    print(f"Analyzing {len(test_errors)} errors...")
    print()

    # Debug each error and collect metrics
    for i, error in enumerate(test_errors, 1):
        print(f"[{i:2d}/{len(test_errors)}] Analyzing: {error}")

        # Debug error
        report = agent.debug_from_string(
            str(error),
            error_type=type(error).__name__,
            max_solutions=5,
            min_relevance=0.3,
        )

        # Record metrics
        monitor.record(report)

        print(
            f"        Category: {report.error_category.category:<15} "
            f"Confidence: {report.error_category.confidence * 100:>3.0f}% "
            f"Solutions: {len(report.suggested_solutions)} "
            f"Time: {report.execution_time:>6.2f}ms"
        )

    print()

    # Print performance report
    monitor.print_report()

    # Benchmark repeated analysis
    print("=" * 80)
    print("Benchmark: Repeated Analysis (100 iterations)")
    print("=" * 80)
    print()

    test_error = ValueError("Missing required parameter 'id'")
    times = []

    print("Running benchmark...")
    for i in range(100):
        start = time.time()
        report = agent.debug_from_string(str(test_error), error_type="ValueError")
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)

        if (i + 1) % 25 == 0:
            print(f"  Completed {i + 1}/100 iterations...")

    print()
    print("Benchmark Results:")
    print(f"  Mean:   {mean(times):>8.2f} ms")
    print(f"  Median: {median(times):>8.2f} ms")
    print(f"  Min:    {min(times):>8.2f} ms")
    print(f"  Max:    {max(times):>8.2f} ms")
    print(f"  StdDev: {stdev(times):>8.2f} ms")
    print()

    # Performance targets
    print("Performance Targets:")
    print(f"  Mean < 50ms:  {'✓ PASS' if mean(times) < 50 else '✗ FAIL'}")
    print(f"  P95 < 100ms:  {'✓ PASS' if sorted(times)[94] < 100 else '✗ FAIL'}")


if __name__ == "__main__":
    main()

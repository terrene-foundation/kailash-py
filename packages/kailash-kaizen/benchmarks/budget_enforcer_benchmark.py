"""
Performance benchmark for BudgetEnforcer.

Measures latency for cost estimation, budget checking, and recording operations.
Target: <1ms for all operations.

Usage:
    python benchmarks/budget_enforcer_benchmark.py
"""

import statistics
import time

from kaizen.core.autonomy.permissions.budget_enforcer import BudgetEnforcer
from kaizen.core.autonomy.permissions.context import ExecutionContext


def benchmark_operation(name: str, operation_fn, iterations: int = 10000) -> dict:
    """
    Benchmark an operation.

    Args:
        name: Name of the operation
        operation_fn: Callable to benchmark
        iterations: Number of iterations to run

    Returns:
        Dict with benchmark results (mean, median, p95, p99)
    """
    print(f"\nBenchmarking: {name}")
    print(f"Iterations: {iterations:,}")

    latencies = []

    for _ in range(iterations):
        start = time.perf_counter()
        operation_fn()
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # Convert to ms

    # Calculate statistics
    mean = statistics.mean(latencies)
    median = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    p99 = statistics.quantiles(latencies, n=100)[98]  # 99th percentile

    results = {
        "mean": mean,
        "median": median,
        "p95": p95,
        "p99": p99,
        "min": min(latencies),
        "max": max(latencies),
    }

    # Print results
    print(f"  Mean:   {mean:.6f} ms")
    print(f"  Median: {median:.6f} ms")
    print(f"  P95:    {p95:.6f} ms")
    print(f"  P99:    {p99:.6f} ms")
    print(f"  Min:    {min(latencies):.6f} ms")
    print(f"  Max:    {max(latencies):.6f} ms")

    # Check target
    target_ms = 1.0
    if p95 < target_ms:
        print(f"  ✅ PASS (P95 < {target_ms}ms)")
    else:
        print(f"  ❌ FAIL (P95 >= {target_ms}ms)")

    return results


def main():
    """Run all benchmarks."""
    print("=" * 80)
    print("BudgetEnforcer Performance Benchmark")
    print("=" * 80)
    print("\nTarget: <1ms for all operations (P95)")

    # Setup
    context = ExecutionContext(budget_limit=10000.0)

    # Benchmark 1: Cost Estimation (Read tool)
    benchmark_operation(
        "Cost Estimation - Read Tool",
        lambda: BudgetEnforcer.estimate_cost("Read", {"path": "test.txt"}),
        iterations=10000,
    )

    # Benchmark 2: Cost Estimation (Write tool)
    benchmark_operation(
        "Cost Estimation - Write Tool",
        lambda: BudgetEnforcer.estimate_cost(
            "Write", {"path": "test.txt", "content": "data"}
        ),
        iterations=10000,
    )

    # Benchmark 3: Cost Estimation (LLM tool with large input)
    large_prompt = "x" * 4000  # ~1000 tokens
    benchmark_operation(
        "Cost Estimation - LLM Tool (1000 tokens)",
        lambda: BudgetEnforcer.estimate_cost("LLMAgentNode", {"prompt": large_prompt}),
        iterations=10000,
    )

    # Benchmark 4: Budget Check (sufficient budget)
    benchmark_operation(
        "Budget Check - Sufficient Budget",
        lambda: BudgetEnforcer.has_budget(context, estimated_cost=1.0),
        iterations=10000,
    )

    # Benchmark 5: Budget Check (unlimited budget)
    unlimited_context = ExecutionContext(budget_limit=None)
    benchmark_operation(
        "Budget Check - Unlimited Budget",
        lambda: BudgetEnforcer.has_budget(unlimited_context, estimated_cost=1.0),
        iterations=10000,
    )

    # Benchmark 6: Recording Usage
    record_context = ExecutionContext(budget_limit=100000.0)
    benchmark_operation(
        "Recording Usage - Update Budget",
        lambda: BudgetEnforcer.record_usage(record_context, "Read", cost_usd=0.001),
        iterations=10000,
    )

    # Benchmark 7: Get Remaining Budget
    benchmark_operation(
        "Get Remaining Budget",
        lambda: BudgetEnforcer.get_remaining_budget(context),
        iterations=10000,
    )

    # Benchmark 8: Extract Actual Cost (with metadata)
    result_with_cost = {"usage": {"cost_usd": 0.025}}
    benchmark_operation(
        "Extract Actual Cost - With Metadata",
        lambda: BudgetEnforcer.get_actual_cost(result_with_cost),
        iterations=10000,
    )

    # Benchmark 9: Extract Actual Cost (without metadata)
    result_without_cost = {}
    benchmark_operation(
        "Extract Actual Cost - Without Metadata",
        lambda: BudgetEnforcer.get_actual_cost(result_without_cost),
        iterations=10000,
    )

    print("\n" + "=" * 80)
    print("Benchmark Complete")
    print("=" * 80)
    print("\nAll operations should have P95 < 1ms for production readiness.")


if __name__ == "__main__":
    main()

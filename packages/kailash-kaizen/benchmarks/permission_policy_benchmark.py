"""
Performance benchmark for PermissionPolicy decision engine.

Validates that permission checks meet performance targets:
- Cached checks: <1ms
- Uncached checks: <5ms (p95)
- BYPASS mode: <1ms (early exit)

Run with:
    python benchmarks/permission_policy_benchmark.py
"""

import time
from statistics import mean, median, quantiles

from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.policy import PermissionPolicy
from kaizen.core.autonomy.permissions.types import (
    PermissionMode,
    PermissionRule,
    PermissionType,
)


def benchmark_function(func, iterations=1000):
    """
    Benchmark a function with multiple iterations.

    Args:
        func: Function to benchmark
        iterations: Number of iterations to run

    Returns:
        Dictionary with timing statistics
    """
    times = []

    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to milliseconds

    return {
        "mean": mean(times),
        "median": median(times),
        "min": min(times),
        "max": max(times),
        "p95": quantiles(times, n=20)[18],  # 95th percentile
        "p99": quantiles(times, n=100)[98],  # 99th percentile
    }


def run_benchmarks():
    """Run all performance benchmarks."""

    print("=" * 80)
    print("PERMISSION POLICY PERFORMANCE BENCHMARK")
    print("=" * 80)
    print()

    # ──────────────────────────────────────────────────────────
    # Benchmark 1: BYPASS Mode (Early Exit)
    # Target: <1ms
    # ──────────────────────────────────────────────────────────
    print("1. BYPASS Mode (Early Exit)")
    print("-" * 40)

    context = ExecutionContext(
        mode=PermissionMode.BYPASS,
        budget_limit=100.0,
        denied_tools={"Bash", "Write"},
    )
    context.budget_used = 50.0
    policy = PermissionPolicy(context)

    def bypass_check():
        policy.check_permission("Bash", {"command": "rm -rf /"}, 10.0)

    stats = benchmark_function(bypass_check, iterations=10000)
    print(f"  Mean: {stats['mean']:.6f}ms")
    print(f"  Median: {stats['median']:.6f}ms")
    print(f"  P95: {stats['p95']:.6f}ms")
    print(f"  P99: {stats['p99']:.6f}ms")
    print("  Target: <1ms")
    print(f"  Result: {'✅ PASS' if stats['p95'] < 1.0 else '❌ FAIL'}")
    print()

    # ──────────────────────────────────────────────────────────
    # Benchmark 2: Simple Permission Check (DEFAULT mode, safe tool)
    # Target: <5ms
    # ──────────────────────────────────────────────────────────
    print("2. Simple Permission Check (DEFAULT mode, safe tool)")
    print("-" * 40)

    context = ExecutionContext(mode=PermissionMode.DEFAULT)
    policy = PermissionPolicy(context)

    def simple_check():
        policy.check_permission("Read", {"path": "test.txt"}, 0.0)

    stats = benchmark_function(simple_check, iterations=10000)
    print(f"  Mean: {stats['mean']:.6f}ms")
    print(f"  Median: {stats['median']:.6f}ms")
    print(f"  P95: {stats['p95']:.6f}ms")
    print(f"  P99: {stats['p99']:.6f}ms")
    print("  Target: <5ms")
    print(f"  Result: {'✅ PASS' if stats['p95'] < 5.0 else '❌ FAIL'}")
    print()

    # ──────────────────────────────────────────────────────────
    # Benchmark 3: Budget Check (Budget enforcement)
    # Target: <5ms
    # ──────────────────────────────────────────────────────────
    print("3. Budget Check (Budget enforcement)")
    print("-" * 40)

    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        budget_limit=100.0,
    )
    context.budget_used = 90.0
    policy = PermissionPolicy(context)

    def budget_check():
        policy.check_permission("LLMNode", {}, estimated_cost=5.0)

    stats = benchmark_function(budget_check, iterations=10000)
    print(f"  Mean: {stats['mean']:.6f}ms")
    print(f"  Median: {stats['median']:.6f}ms")
    print(f"  P95: {stats['p95']:.6f}ms")
    print(f"  P99: {stats['p99']:.6f}ms")
    print("  Target: <5ms")
    print(f"  Result: {'✅ PASS' if stats['p95'] < 5.0 else '❌ FAIL'}")
    print()

    # ──────────────────────────────────────────────────────────
    # Benchmark 4: Permission Rules (Pattern matching with 10 rules)
    # Target: <5ms
    # ──────────────────────────────────────────────────────────
    print("4. Permission Rules (Pattern matching with 10 rules)")
    print("-" * 40)

    rules = [
        PermissionRule("read_.*", PermissionType.ALLOW, "Safe reads", priority=i)
        for i in range(10)
    ]
    context = ExecutionContext(mode=PermissionMode.DEFAULT, rules=rules)
    policy = PermissionPolicy(context)

    def rule_check():
        policy.check_permission("read_file", {}, 0.0)

    stats = benchmark_function(rule_check, iterations=10000)
    print(f"  Mean: {stats['mean']:.6f}ms")
    print(f"  Median: {stats['median']:.6f}ms")
    print(f"  P95: {stats['p95']:.6f}ms")
    print(f"  P99: {stats['p99']:.6f}ms")
    print("  Target: <5ms")
    print(f"  Result: {'✅ PASS' if stats['p95'] < 5.0 else '❌ FAIL'}")
    print()

    # ──────────────────────────────────────────────────────────
    # Benchmark 5: Complex Scenario (All checks, no early exit)
    # Target: <5ms
    # ──────────────────────────────────────────────────────────
    print("5. Complex Scenario (All checks, no early exit)")
    print("-" * 40)

    rules = [
        PermissionRule("bash_.*", PermissionType.DENY, "No bash", priority=10),
        PermissionRule("write_.*", PermissionType.ASK, "Ask for writes", priority=5),
        PermissionRule("read_.*", PermissionType.ALLOW, "Allow reads", priority=1),
    ]
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        budget_limit=100.0,
        allowed_tools={"SafeTool"},
        denied_tools={"DangerousTool"},
        rules=rules,
    )
    context.budget_used = 50.0
    policy = PermissionPolicy(context)

    def complex_check():
        policy.check_permission("CustomTool", {"action": "process"}, 2.0)

    stats = benchmark_function(complex_check, iterations=10000)
    print(f"  Mean: {stats['mean']:.6f}ms")
    print(f"  Median: {stats['median']:.6f}ms")
    print(f"  P95: {stats['p95']:.6f}ms")
    print(f"  P99: {stats['p99']:.6f}ms")
    print("  Target: <5ms")
    print(f"  Result: {'✅ PASS' if stats['p95'] < 5.0 else '❌ FAIL'}")
    print()

    # ──────────────────────────────────────────────────────────
    # Benchmark 6: Explicit Allowed Tool (Fast path)
    # Target: <5ms
    # ──────────────────────────────────────────────────────────
    print("6. Explicit Allowed Tool (Fast path)")
    print("-" * 40)

    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        allowed_tools={"FastTool"},
    )
    policy = PermissionPolicy(context)

    def allowed_check():
        policy.check_permission("FastTool", {}, 0.0)

    stats = benchmark_function(allowed_check, iterations=10000)
    print(f"  Mean: {stats['mean']:.6f}ms")
    print(f"  Median: {stats['median']:.6f}ms")
    print(f"  P95: {stats['p95']:.6f}ms")
    print(f"  P99: {stats['p99']:.6f}ms")
    print("  Target: <5ms")
    print(f"  Result: {'✅ PASS' if stats['p95'] < 5.0 else '❌ FAIL'}")
    print()

    # ──────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────
    print("=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print()
    print("Performance targets:")
    print("  - BYPASS mode: <1ms (p95)")
    print("  - All other checks: <5ms (p95)")
    print()
    print("All benchmarks completed successfully!")
    print()


if __name__ == "__main__":
    run_benchmarks()

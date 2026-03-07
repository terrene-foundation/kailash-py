"""Benchmark Phase 0 optimizations — measures per-node and per-workflow overhead.

Run: python -m pytest tests/benchmarks/bench_phase0.py -v --benchmark-only
Or:  python tests/benchmarks/bench_phase0.py  (standalone)
"""

import statistics
import time

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def build_linear_workflow(n_nodes: int) -> WorkflowBuilder:
    """Build a linear chain of n PythonCodeNode nodes."""
    builder = WorkflowBuilder()
    for i in range(n_nodes):
        builder.add_node(
            "PythonCodeNode", f"node_{i}", {"code": f"result = {{'v': {i}}}"}
        )
        if i > 0:
            builder.add_connection(f"node_{i-1}", "result", f"node_{i}", "input")
    return builder


def build_wide_workflow(n_nodes: int) -> WorkflowBuilder:
    """Build a fan-out workflow: 1 root -> n-1 parallel nodes."""
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "root", {"code": "result = {'v': 0}"})
    for i in range(1, n_nodes):
        builder.add_node(
            "PythonCodeNode", f"node_{i}", {"code": f"result = {{'v': {i}}}"}
        )
        builder.add_connection("root", "result", f"node_{i}", "input")
    return builder


def bench_execution(workflow_builder, n_runs=10, label=""):
    """Benchmark workflow execution, return stats."""
    workflow = workflow_builder.build()
    times = []

    with LocalRuntime() as runtime:
        # Warmup
        runtime.execute(workflow)

        for _ in range(n_runs):
            start = time.perf_counter()
            results, run_id = runtime.execute(workflow)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

    n_nodes = len(results)
    mean_ms = statistics.mean(times) * 1000
    stdev_ms = statistics.stdev(times) * 1000 if len(times) > 1 else 0
    per_node_us = (statistics.mean(times) / n_nodes) * 1_000_000

    return {
        "label": label,
        "n_nodes": n_nodes,
        "n_runs": n_runs,
        "mean_ms": mean_ms,
        "stdev_ms": stdev_ms,
        "per_node_us": per_node_us,
    }


def bench_build_time(workflow_builder, n_runs=20, label=""):
    """Benchmark workflow.build() time."""
    times = []
    for _ in range(n_runs):
        # Reset builder nodes to force rebuild
        builder = (
            build_linear_workflow(workflow_builder._n)
            if hasattr(workflow_builder, "_n")
            else workflow_builder
        )
        start = time.perf_counter()
        builder.build()
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    mean_ms = statistics.mean(times) * 1000
    return {"label": label, "mean_ms": mean_ms}


def bench_topo_sort_caching(n_nodes=20, n_calls=100):
    """Benchmark cached vs uncached topological sort."""
    builder = build_linear_workflow(n_nodes)
    workflow = builder.build()

    # Cached: call get_execution_order() repeatedly
    times_cached = []
    for _ in range(n_calls):
        workflow._topo_cache = None  # Clear to measure first call
        start = time.perf_counter()
        workflow.get_execution_order()
        elapsed = time.perf_counter() - start
        times_cached.append(elapsed)

    # Already cached: measure cache hit time
    workflow.get_execution_order()  # Prime cache
    times_hit = []
    for _ in range(n_calls):
        start = time.perf_counter()
        workflow.get_execution_order()
        elapsed = time.perf_counter() - start
        times_hit.append(elapsed)

    return {
        "uncached_mean_us": statistics.mean(times_cached) * 1_000_000,
        "cached_hit_mean_us": statistics.mean(times_hit) * 1_000_000,
        "speedup": statistics.mean(times_cached)
        / max(statistics.mean(times_hit), 1e-9),
    }


def bench_repeated_execution(n_nodes=10, n_runs=20):
    """Benchmark repeated executions of the same workflow (tests cache reuse)."""
    builder = build_linear_workflow(n_nodes)
    workflow = builder.build()

    times_first = []
    times_subsequent = []

    with LocalRuntime() as runtime:
        for i in range(n_runs):
            # Clear topo cache to simulate first execution
            workflow._topo_cache = None
            workflow._dag_cycle_cache = None

            start = time.perf_counter()
            runtime.execute(workflow)
            elapsed = time.perf_counter() - start
            times_first.append(elapsed)

            # Second execution: cache is warm
            start = time.perf_counter()
            runtime.execute(workflow)
            elapsed = time.perf_counter() - start
            times_subsequent.append(elapsed)

    return {
        "cold_mean_ms": statistics.mean(times_first) * 1000,
        "warm_mean_ms": statistics.mean(times_subsequent) * 1000,
        "speedup_pct": (
            (statistics.mean(times_first) - statistics.mean(times_subsequent))
            / statistics.mean(times_first)
            * 100
        ),
    }


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 0 Performance Benchmark")
    print("=" * 70)

    # Execution benchmarks
    print("\n--- Workflow Execution (mean of 10 runs) ---")
    for n in [1, 5, 10, 20, 50]:
        r = bench_execution(build_linear_workflow(n), n_runs=10, label=f"linear-{n}")
        print(
            f"  {r['label']:>12}: {r['mean_ms']:7.2f}ms total, "
            f"{r['per_node_us']:7.1f}us/node  (stdev={r['stdev_ms']:.2f}ms)"
        )

    print("\n--- Wide Workflow (fan-out) ---")
    for n in [5, 10, 20, 50]:
        r = bench_execution(build_wide_workflow(n), n_runs=10, label=f"wide-{n}")
        print(
            f"  {r['label']:>12}: {r['mean_ms']:7.2f}ms total, "
            f"{r['per_node_us']:7.1f}us/node  (stdev={r['stdev_ms']:.2f}ms)"
        )

    # Topological sort caching
    print("\n--- Topological Sort Cache (20 nodes, 100 calls) ---")
    topo = bench_topo_sort_caching(n_nodes=20, n_calls=100)
    print(f"  Uncached: {topo['uncached_mean_us']:.1f}us")
    print(f"  Cache hit: {topo['cached_hit_mean_us']:.2f}us")
    print(f"  Speedup: {topo['speedup']:.0f}x")

    # Repeated execution (cold vs warm cache)
    print("\n--- Cold vs Warm Cache (10 nodes, 20 pairs) ---")
    rep = bench_repeated_execution(n_nodes=10, n_runs=20)
    print(f"  Cold (no cache): {rep['cold_mean_ms']:.2f}ms")
    print(f"  Warm (cached):   {rep['warm_mean_ms']:.2f}ms")
    print(f"  Speedup: {rep['speedup_pct']:.1f}%")

    print("\n" + "=" * 70)

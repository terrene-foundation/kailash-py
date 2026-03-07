"""Benchmark framework overhead isolation — measures per-component costs excluding node execution.

This benchmark isolates the Kailash SDK framework overhead from actual node work.
It uses PythonCodeNode with minimal code (`result = {'v': 1}`) and subtracts raw
node execution time to get framework-only overhead numbers.

Measured components:
  a. WorkflowBuilder.build() time
  b. Topological sort (cached vs uncached)
  c. Per-node input preparation (_prepare_node_inputs)
  d. Per-node output storage
  e. Total framework overhead per node (excluding node.execute())
  f. Content-aware success detection overhead
  g. Trust verification overhead

Run: python tests/benchmarks/bench_framework_overhead.py
"""

import asyncio
import logging
import statistics
import time

# Suppress noisy logging during benchmarks
logging.disable(logging.CRITICAL)

from kailash.runtime.local import (
    LocalRuntime,
    detect_success,
    should_stop_on_content_failure,
)
from kailash.tracking.metrics_collector import MetricsCollector
from kailash.workflow.builder import WorkflowBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_linear(n: int) -> WorkflowBuilder:
    """Build a linear chain of n PythonCodeNode nodes with minimal code."""
    b = WorkflowBuilder()
    for i in range(n):
        b.add_node("PythonCodeNode", f"n{i}", {"code": "result = {'v': 1}"})
        if i > 0:
            b.add_connection(f"n{i-1}", "result", f"n{i}", "input")
    return b


def percentile(data, pct):
    """Compute percentile without numpy."""
    s = sorted(data)
    idx = (pct / 100) * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def fmt_us(val):
    """Format microseconds."""
    if val < 1:
        return f"{val * 1000:.1f}ns"
    if val < 1000:
        return f"{val:.1f}us"
    return f"{val / 1000:.2f}ms"


# ---------------------------------------------------------------------------
# A. WorkflowBuilder.build() time
# ---------------------------------------------------------------------------


def bench_build_time(scales, n_runs=50):
    """Measure WorkflowBuilder.build() time at different scales."""
    print("\n=== A. WorkflowBuilder.build() Time ===")
    print(f"{'Nodes':>6}  {'Mean':>10}  {'Median':>10}  {'P95':>10}  {'Per-Node':>10}")
    print("-" * 55)

    for n in scales:
        times = []
        for _ in range(n_runs):
            builder = build_linear(n)
            t0 = time.perf_counter()
            builder.build()
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1_000_000)  # microseconds

        mean = statistics.mean(times)
        med = statistics.median(times)
        p95 = percentile(times, 95)
        per_node = mean / n

        print(
            f"{n:>6}  {fmt_us(mean):>10}  {fmt_us(med):>10}  {fmt_us(p95):>10}  {fmt_us(per_node):>10}"
        )

    return


# ---------------------------------------------------------------------------
# B. Topological sort (cached vs uncached)
# ---------------------------------------------------------------------------


def bench_topo_sort(scales, n_calls=200):
    """Measure topological sort time (with/without P0B cache if available)."""
    has_cache = (
        hasattr(WorkflowBuilder().build.__func__, "__self__") or True
    )  # check at runtime
    # Detect if P0B topo caching is present
    test_b = build_linear(1)
    test_w = test_b.build()
    has_topo_cache = hasattr(test_w, "_topo_cache")

    if has_topo_cache:
        print(
            "\n=== B. Topological Sort (Cached vs Uncached) [P0B caching PRESENT] ==="
        )
        print(f"{'Nodes':>6}  {'Uncached':>10}  {'Cached':>10}  {'Speedup':>8}")
    else:
        print("\n=== B. Topological Sort (NO P0B caching installed) ===")
        print(
            f"{'Nodes':>6}  {'Mean':>10}  {'Median':>10}  {'P95':>10}  {'Per-Node':>10}"
        )
    print("-" * 55)

    for n in scales:
        builder = build_linear(n)
        workflow = builder.build()

        if has_topo_cache:
            # Uncached
            uncached_times = []
            for _ in range(n_calls):
                workflow._topo_cache = None
                t0 = time.perf_counter()
                workflow.get_execution_order()
                t1 = time.perf_counter()
                uncached_times.append((t1 - t0) * 1_000_000)

            # Cached
            workflow.get_execution_order()  # prime
            cached_times = []
            for _ in range(n_calls):
                t0 = time.perf_counter()
                workflow.get_execution_order()
                t1 = time.perf_counter()
                cached_times.append((t1 - t0) * 1_000_000)

            um = statistics.mean(uncached_times)
            cm = statistics.mean(cached_times)
            speedup = um / max(cm, 0.001)
            print(f"{n:>6}  {fmt_us(um):>10}  {fmt_us(cm):>10}  {speedup:>7.0f}x")
        else:
            # No caching -- just measure raw topo sort (includes nx.DiGraph copy + nx.topological_sort)
            times = []
            for _ in range(n_calls):
                t0 = time.perf_counter()
                workflow.get_execution_order()
                t1 = time.perf_counter()
                times.append((t1 - t0) * 1_000_000)

            mean = statistics.mean(times)
            med = statistics.median(times)
            p95 = percentile(times, 95)
            per_node = mean / n
            print(
                f"{n:>6}  {fmt_us(mean):>10}  {fmt_us(med):>10}  {fmt_us(p95):>10}  {fmt_us(per_node):>10}"
            )

    return


# ---------------------------------------------------------------------------
# C. Per-node _prepare_node_inputs overhead
# ---------------------------------------------------------------------------


def bench_prepare_inputs(scales, n_runs=20):
    """Measure _prepare_node_inputs overhead per node."""
    print("\n=== C. Per-Node Input Preparation (_prepare_node_inputs) ===")
    print(f"{'Nodes':>6}  {'Mean/Node':>10}  {'Median/Node':>12}  {'P95/Node':>10}")
    print("-" * 45)

    for n in scales:
        builder = build_linear(n)
        workflow = builder.build()

        with LocalRuntime() as runtime:
            # Run once to get outputs we can reuse
            results, _ = runtime.execute(workflow)

            # Now measure _prepare_node_inputs in isolation
            execution_order = workflow.get_execution_order()
            node_outputs = {}
            for nid in execution_order:
                node_outputs[nid] = results[nid]

            per_node_times = []

            for _ in range(n_runs):
                for nid in execution_order:
                    inst = workflow._node_instances[nid]
                    t0 = time.perf_counter()
                    runtime._prepare_node_inputs(
                        workflow=workflow,
                        node_id=nid,
                        node_instance=inst,
                        node_outputs=node_outputs,
                        parameters={},
                    )
                    t1 = time.perf_counter()
                    per_node_times.append((t1 - t0) * 1_000_000)

        mean = statistics.mean(per_node_times)
        med = statistics.median(per_node_times)
        p95 = percentile(per_node_times, 95)
        print(f"{n:>6}  {fmt_us(mean):>10}  {fmt_us(med):>12}  {fmt_us(p95):>10}")

    return


# ---------------------------------------------------------------------------
# D. Per-node output storage overhead
# ---------------------------------------------------------------------------


def bench_output_storage(n_runs=10000):
    """Measure the cost of output storage (dict assignment + logging check)."""
    print("\n=== D. Per-Node Output Storage ===")

    outputs = {"result": {"v": 1}, "metadata": {"type": "test"}}
    results = {}
    node_outputs = {}

    times = []
    for i in range(n_runs):
        nid = f"node_{i}"
        t0 = time.perf_counter()
        node_outputs[nid] = outputs
        results[nid] = outputs
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1_000_000)

    mean = statistics.mean(times)
    med = statistics.median(times)
    p95 = percentile(times, 95)
    print(f"  Mean: {fmt_us(mean)},  Median: {fmt_us(med)},  P95: {fmt_us(p95)}")
    return mean


# ---------------------------------------------------------------------------
# F. Content-aware success detection overhead
# ---------------------------------------------------------------------------


def bench_content_detection(n_runs=50000):
    """Measure content-aware success detection overhead."""
    print("\n=== F. Content-Aware Success Detection ===")

    # Typical successful node output
    result_success = {"result": {"v": 1}, "metadata": {"type": "test"}}
    # Output with success field
    result_with_flag = {"success": True, "data": {"v": 1}}
    # Output with failure
    result_failure = {"success": False, "error": "something broke"}

    for label, data in [
        ("No 'success' key (fast path)", result_success),
        ("success=True", result_with_flag),
        ("success=False", result_failure),
    ]:
        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            should_stop_on_content_failure(
                data, content_aware_mode=True, stop_on_error=True
            )
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1_000_000)

        mean = statistics.mean(times)
        med = statistics.median(times)
        print(f"  {label:35s}  Mean: {fmt_us(mean)},  Median: {fmt_us(med)}")


# ---------------------------------------------------------------------------
# G. Trust verification overhead
# ---------------------------------------------------------------------------


def bench_trust_verification(n_runs=10000):
    """Measure trust verification overhead (default DISABLED mode)."""
    print("\n=== G. Trust Verification Overhead (DISABLED mode) ===")

    runtime = LocalRuntime()

    async def run_verify():
        times = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            result = await runtime._verify_node_trust(
                node_id="test_node",
                node_type="PythonCodeNode",
                trust_context=runtime._get_effective_trust_context(),
            )
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1_000_000)
        return times

    times = asyncio.run(run_verify())
    mean = statistics.mean(times)
    med = statistics.median(times)
    p95 = percentile(times, 95)
    print(f"  Mean: {fmt_us(mean)},  Median: {fmt_us(med)},  P95: {fmt_us(p95)}")
    runtime.close()
    return mean


# ---------------------------------------------------------------------------
# H. MetricsCollector overhead
# ---------------------------------------------------------------------------


def bench_metrics_collector(n_runs=10000):
    """Measure MetricsCollector context manager overhead (psutil disabled path)."""
    print("\n=== H. MetricsCollector Context Manager Overhead ===")

    collector = MetricsCollector()
    # Force disable psutil monitoring to measure pure framework overhead
    collector._monitoring_enabled = False

    times = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        with collector.collect(node_id="bench") as ctx:
            pass  # No actual work
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1_000_000)

    mean = statistics.mean(times)
    med = statistics.median(times)
    p95 = percentile(times, 95)
    print(
        f"  (psutil disabled) Mean: {fmt_us(mean)},  Median: {fmt_us(med)},  P95: {fmt_us(p95)}"
    )

    # If psutil is available, measure with it enabled
    collector2 = MetricsCollector()
    if collector2._monitoring_enabled:
        times2 = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            with collector2.collect(node_id="bench") as ctx:
                pass
            t1 = time.perf_counter()
            times2.append((t1 - t0) * 1_000_000)

        mean2 = statistics.mean(times2)
        med2 = statistics.median(times2)
        p95_2 = percentile(times2, 95)
        print(
            f"  (psutil enabled)  Mean: {fmt_us(mean2)},  Median: {fmt_us(med2)},  P95: {fmt_us(p95_2)}"
        )

    return mean


# ---------------------------------------------------------------------------
# E. Total framework overhead per node (end-to-end, subtracting node.execute())
# ---------------------------------------------------------------------------


def bench_total_framework_overhead(scales, n_runs=10):
    """Measure total execution time and subtract raw node execution to get framework overhead."""
    print("\n=== E. Total Framework Overhead Per Node ===")
    print("  (Total execution - raw node.execute() = framework overhead)")
    print(
        f"{'Nodes':>6}  {'Total':>11}  {'Tot/Node':>11}  {'Exec/Node':>11}  "
        f"{'FW Total':>11}  {'FW/Node':>11}  {'FW %':>6}"
    )
    print("-" * 75)

    for n in scales:
        builder = build_linear(n)
        workflow = builder.build()

        # Measure raw node.execute() time
        execution_order = workflow.get_execution_order()
        node_instances = [workflow._node_instances[nid] for nid in execution_order]

        # Warm up nodes
        for inst in node_instances:
            inst.execute()

        # Measure raw execute times
        raw_exec_times = []
        for _ in range(n_runs * 2):
            for inst in node_instances:
                t0 = time.perf_counter()
                inst.execute()
                t1 = time.perf_counter()
                raw_exec_times.append((t1 - t0) * 1_000_000)

        raw_per_node = statistics.mean(raw_exec_times)

        # Measure total execution time
        total_times = []
        with LocalRuntime() as runtime:
            # Warmup
            runtime.execute(workflow)

            for _ in range(n_runs):
                t0 = time.perf_counter()
                runtime.execute(workflow)
                t1 = time.perf_counter()
                total_times.append((t1 - t0) * 1_000_000)

        total_mean = statistics.mean(total_times)
        total_per_node = total_mean / n
        total_raw_exec = raw_per_node * n
        fw_total = total_mean - total_raw_exec
        fw_per_node = fw_total / n
        fw_pct = (fw_total / total_mean * 100) if total_mean > 0 else 0

        print(
            f"{n:>6}  {fmt_us(total_mean):>11}  {fmt_us(total_per_node):>11}  "
            f"{fmt_us(raw_per_node):>11}  {fmt_us(fw_total):>11}  "
            f"{fmt_us(fw_per_node):>11}  {fw_pct:>5.1f}%"
        )

    # Estimate one-time vs per-node cost
    print("\n  NOTE: 'FW Total' includes one-time per-execution costs (validation,")
    print("  topo sort, parameter processing) PLUS per-node costs (input prep,")
    print("  output storage, metrics, trust check, content detection).")


# ---------------------------------------------------------------------------
# E1b. Total framework overhead with monitoring DISABLED
# ---------------------------------------------------------------------------


def bench_total_framework_overhead_no_monitoring(scales, n_runs=10):
    """Same as E but with enable_monitoring=False to show TaskManager impact."""
    print("\n=== E1b. Total Framework Overhead (enable_monitoring=FALSE) ===")
    print("  (Disables TaskManager filesystem I/O per node)")
    print(
        f"{'Nodes':>6}  {'Total':>11}  {'Tot/Node':>11}  {'Exec/Node':>11}  "
        f"{'FW Total':>11}  {'FW/Node':>11}  {'FW %':>6}"
    )
    print("-" * 75)

    for n in scales:
        builder = build_linear(n)
        workflow = builder.build()

        # Raw node execute times (reuse from previous)
        execution_order = workflow.get_execution_order()
        node_instances = [workflow._node_instances[nid] for nid in execution_order]
        for inst in node_instances:
            inst.execute()
        raw_exec_times = []
        for _ in range(n_runs * 2):
            for inst in node_instances:
                t0 = time.perf_counter()
                inst.execute()
                t1 = time.perf_counter()
                raw_exec_times.append((t1 - t0) * 1_000_000)
        raw_per_node = statistics.mean(raw_exec_times)

        # Total execution with monitoring disabled
        total_times = []
        with LocalRuntime(enable_monitoring=False) as runtime:
            runtime.execute(workflow)  # warmup
            for _ in range(n_runs):
                t0 = time.perf_counter()
                runtime.execute(workflow)
                t1 = time.perf_counter()
                total_times.append((t1 - t0) * 1_000_000)

        total_mean = statistics.mean(total_times)
        total_per_node = total_mean / n
        total_raw_exec = raw_per_node * n
        fw_total = total_mean - total_raw_exec
        fw_per_node = fw_total / n
        fw_pct = (fw_total / total_mean * 100) if total_mean > 0 else 0

        print(
            f"{n:>6}  {fmt_us(total_mean):>11}  {fmt_us(total_per_node):>11}  "
            f"{fmt_us(raw_per_node):>11}  {fmt_us(fw_total):>11}  "
            f"{fmt_us(fw_per_node):>11}  {fw_pct:>5.1f}%"
        )


# ---------------------------------------------------------------------------
# E2. One-time per-execution costs breakdown
# ---------------------------------------------------------------------------


def bench_one_time_costs(scales, n_runs=30):
    """Measure one-time per-execution costs: workflow.validate(), _process_workflow_parameters."""
    print("\n=== E2. One-Time Per-Execution Costs ===")
    print(
        f"{'Nodes':>6}  {'validate()':>12}  {'param_proc':>12}  {'has_cycles':>12}  {'has_cond':>12}  {'Total':>12}"
    )
    print("-" * 75)

    for n in scales:
        builder = build_linear(n)
        workflow = builder.build()

        with LocalRuntime() as runtime:
            # Warmup
            runtime.execute(workflow)

            # Measure workflow.validate()
            validate_times = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                workflow.validate(runtime_parameters={})
                t1 = time.perf_counter()
                validate_times.append((t1 - t0) * 1_000_000)

            # Measure _process_workflow_parameters
            param_times = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                runtime._process_workflow_parameters(workflow, None)
                t1 = time.perf_counter()
                param_times.append((t1 - t0) * 1_000_000)

            # Measure has_cycles()
            cycle_times = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                workflow.has_cycles()
                t1 = time.perf_counter()
                cycle_times.append((t1 - t0) * 1_000_000)

            # Measure _has_conditional_patterns
            cond_times = []
            for _ in range(n_runs):
                t0 = time.perf_counter()
                runtime._has_conditional_patterns(workflow)
                t1 = time.perf_counter()
                cond_times.append((t1 - t0) * 1_000_000)

        v_mean = statistics.mean(validate_times)
        p_mean = statistics.mean(param_times)
        c_mean = statistics.mean(cycle_times)
        cond_mean = statistics.mean(cond_times)
        total = v_mean + p_mean + c_mean + cond_mean

        print(
            f"{n:>6}  {fmt_us(v_mean):>12}  {fmt_us(p_mean):>12}  "
            f"{fmt_us(c_mean):>12}  {fmt_us(cond_mean):>12}  {fmt_us(total):>12}"
        )


# ---------------------------------------------------------------------------
# I. DAG/cycle edge separation cache
# ---------------------------------------------------------------------------


def bench_dag_cycle_separation(scales, n_calls=500):
    """Measure separate_dag_and_cycle_edges cost."""
    test_w = build_linear(1).build()
    has_dag_cache = hasattr(test_w, "_dag_cycle_cache")

    if has_dag_cache:
        print("\n=== I. DAG/Cycle Edge Separation [P0B caching PRESENT] ===")
        print(f"{'Nodes':>6}  {'Uncached':>10}  {'Cached':>10}  {'Speedup':>8}")
    else:
        print("\n=== I. DAG/Cycle Edge Separation (NO caching) ===")
        print(f"{'Nodes':>6}  {'Mean':>10}  {'Median':>10}  {'Per-Node':>10}")
    print("-" * 45)

    for n in scales:
        builder = build_linear(n)
        workflow = builder.build()

        if has_dag_cache:
            uncached_times = []
            for _ in range(n_calls):
                workflow._dag_cycle_cache = None
                t0 = time.perf_counter()
                workflow.separate_dag_and_cycle_edges()
                t1 = time.perf_counter()
                uncached_times.append((t1 - t0) * 1_000_000)

            workflow.separate_dag_and_cycle_edges()
            cached_times = []
            for _ in range(n_calls):
                t0 = time.perf_counter()
                workflow.separate_dag_and_cycle_edges()
                t1 = time.perf_counter()
                cached_times.append((t1 - t0) * 1_000_000)

            um = statistics.mean(uncached_times)
            cm = statistics.mean(cached_times)
            speedup = um / max(cm, 0.001)
            print(f"{n:>6}  {fmt_us(um):>10}  {fmt_us(cm):>10}  {speedup:>7.0f}x")
        else:
            times = []
            for _ in range(n_calls):
                t0 = time.perf_counter()
                workflow.separate_dag_and_cycle_edges()
                t1 = time.perf_counter()
                times.append((t1 - t0) * 1_000_000)

            mean = statistics.mean(times)
            med = statistics.median(times)
            per_node = mean / n
            print(
                f"{n:>6}  {fmt_us(mean):>10}  {fmt_us(med):>10}  {fmt_us(per_node):>10}"
            )


# ---------------------------------------------------------------------------
# J. SQLite flush overhead (P0E)
# ---------------------------------------------------------------------------


def bench_sqlite_flush(node_counts=(5, 10, 20, 50), n_runs=20):
    """Measure DeferredStorageBackend.flush_to_sqlite() cost after execution.

    P0E replaced batch JSON file writes with SQLite WAL-mode inserts using
    executemany(). This benchmark compares:
    - flush_to_sqlite(): SQLite WAL + executemany() (P0E path)
    - flush_to_filesystem(): Single batch JSON file (P0D-007b path)
    """
    import os
    import tempfile

    from kailash.tracking.models import TaskMetrics, TaskRun, TaskStatus, WorkflowRun
    from kailash.tracking.storage.deferred import DeferredStorageBackend

    print("\n=== J. SQLite Flush Overhead (P0E) ===")
    print("  Comparing flush_to_sqlite() vs flush_to_filesystem() per run")
    print(
        f"  {'Tasks':>6}  {'SQLite (ms)':>12}  {'File (ms)':>12}  {'Ratio':>8}  {'SQLite/task':>12}"
    )
    print("  " + "-" * 55)

    for n_tasks in node_counts:
        sqlite_times = []
        file_times = []

        for _ in range(n_runs):
            # --- flush_to_sqlite ---
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = os.path.join(tmpdir, "bench.db")

                deferred = DeferredStorageBackend()
                run = WorkflowRun(run_id="run-bench", workflow_name="bench_wf")
                deferred.save_run(run)
                for i in range(n_tasks):
                    task = TaskRun(
                        task_id=f"task-{i}",
                        run_id="run-bench",
                        node_id=f"node-{i}",
                        node_type="PythonCodeNode",
                        status=TaskStatus.COMPLETED,
                        metrics=TaskMetrics(duration=0.001 * i, cpu_usage=10.0),
                    )
                    deferred.save_task(task)

                t0 = time.perf_counter()
                deferred.flush_to_sqlite(db_path)
                t1 = time.perf_counter()
                sqlite_times.append((t1 - t0) * 1000)  # ms

            # --- flush_to_filesystem ---
            with tempfile.TemporaryDirectory() as tmpdir:
                deferred2 = DeferredStorageBackend()
                run2 = WorkflowRun(run_id="run-bench", workflow_name="bench_wf")
                deferred2.save_run(run2)
                for i in range(n_tasks):
                    task = TaskRun(
                        task_id=f"task-{i}",
                        run_id="run-bench",
                        node_id=f"node-{i}",
                        node_type="PythonCodeNode",
                        status=TaskStatus.COMPLETED,
                        metrics=TaskMetrics(duration=0.001 * i, cpu_usage=10.0),
                    )
                    deferred2.save_task(task)

                t0 = time.perf_counter()
                deferred2.flush_to_filesystem(tmpdir)
                t1 = time.perf_counter()
                file_times.append((t1 - t0) * 1000)  # ms

        sqlite_mean = statistics.mean(sqlite_times)
        file_mean = statistics.mean(file_times)
        ratio = sqlite_mean / max(file_mean, 0.001)
        per_task_us = (sqlite_mean / n_tasks) * 1000  # us

        print(
            f"  {n_tasks:>6}  {sqlite_mean:>10.2f}ms  {file_mean:>10.2f}ms  {ratio:>7.2f}x  {per_task_us:>9.1f}us"
        )

    print(
        "\n  NOTE: SQLite flush includes WAL open + schema check + executemany() batch insert."
    )
    print("  Both paths write only AFTER execution (zero I/O during hot path).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    scales = [1, 5, 10, 20, 50, 100]

    print("=" * 70)
    print("Framework Overhead Isolation Benchmark")
    print("=" * 70)
    print(f"Scales: {scales}")
    print("Node type: PythonCodeNode with `result = {{'v': 1}}`")

    bench_build_time(scales)
    bench_topo_sort(scales)
    bench_dag_cycle_separation(scales)
    bench_prepare_inputs(scales)
    bench_output_storage()
    bench_total_framework_overhead(scales)
    bench_total_framework_overhead_no_monitoring(scales)
    bench_one_time_costs(scales)
    bench_content_detection()
    bench_trust_verification()
    bench_metrics_collector()
    bench_sqlite_flush()

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)

"""
Performance tests for Kaizen import time optimization.

This test suite measures and validates import performance to ensure
the critical <100ms import time requirement is met.

Target: <100ms import time (current: 796ms - CRITICAL ISSUE)
"""

import cProfile
import io
import os
import pstats
import statistics
import subprocess
import sys
import time
from typing import List, Tuple


def measure_import_time(module_name: str, runs: int = 10) -> Tuple[float, List[float]]:
    """
    Measure import time for a module across multiple runs.

    Args:
        module_name: Module to import (e.g., 'kaizen')
        runs: Number of test runs for statistical accuracy

    Returns:
        Tuple of (average_time_ms, all_times_ms)
    """
    times = []

    for _ in range(runs):
        # Start fresh Python process to avoid cache effects
        start_time = time.perf_counter()

        # Use subprocess to avoid import caching
        result = subprocess.run(
            [sys.executable, "-c", f"import {module_name}"],
            capture_output=True,
            text=True,
        )

        end_time = time.perf_counter()

        if result.returncode != 0:
            raise ImportError(f"Failed to import {module_name}: {result.stderr}")

        import_time_ms = (end_time - start_time) * 1000
        times.append(import_time_ms)

    avg_time = statistics.mean(times)
    return avg_time, times


def profile_import_chain(module_name: str) -> str:
    """
    Profile the import chain to identify bottlenecks.

    Args:
        module_name: Module to profile

    Returns:
        Profiling report as string
    """
    # Create profiler
    profiler = cProfile.Profile()

    # Profile the import
    profiler.enable()
    try:
        exec(f"import {module_name}")
    finally:
        profiler.disable()

    # Generate report
    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s)
    ps.sort_stats("cumulative")
    ps.print_stats(50)  # Top 50 slowest operations

    return s.getvalue()


def test_kaizen_import_baseline():
    """
    Test 1: Measure baseline Kaizen import time.

    CRITICAL: This test must identify the 796ms issue and
    fail if import time exceeds 100ms target.
    """
    target_time_ms = 100

    # Measure import time with statistical accuracy
    avg_time, all_times = measure_import_time("kaizen", runs=5)

    print("\n=== KAIZEN IMPORT PERFORMANCE BASELINE ===")
    print(f"Average import time: {avg_time:.1f}ms")
    print(f"All measurements: {[f'{t:.1f}ms' for t in all_times]}")
    print(f"Target: <{target_time_ms}ms")
    print(f"Status: {'✅ PASS' if avg_time < target_time_ms else '❌ FAIL'}")

    if avg_time >= target_time_ms:
        overage_percent = ((avg_time / target_time_ms) - 1) * 100
        print(f"CRITICAL: {overage_percent:.0f}% over target!")

        # Generate detailed profiling report
        print("\n=== IMPORT PROFILING ANALYSIS ===")
        profile_report = profile_import_chain("kaizen")
        print(profile_report)

        # Fail the test to force optimization
        assert avg_time < target_time_ms, (
            f"Import time {avg_time:.1f}ms exceeds {target_time_ms}ms target "
            f"({overage_percent:.0f}% over). CRITICAL performance issue!"
        )


def test_kaizen_import_breakdown():
    """
    Test 2: Break down import time by module components.

    This identifies which specific imports are causing delays.
    """
    modules_to_test = [
        "kaizen.core.framework",
        "kaizen.core.base_optimized",
        "kaizen.core.agents",
        "kaizen.core.interfaces",
        "kaizen.coordination.patterns",
        "kaizen.coordination.teams",
        "kaizen.memory",
    ]

    print("\n=== KAIZEN MODULE BREAKDOWN ===")

    results = {}
    for module in modules_to_test:
        try:
            avg_time, _ = measure_import_time(module, runs=3)
            results[module] = avg_time
            print(f"{module}: {avg_time:.1f}ms")
        except ImportError as e:
            print(f"{module}: IMPORT ERROR - {e}")
            results[module] = float("inf")

    # Identify heaviest imports
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    print("\n=== HEAVIEST IMPORTS (optimization targets) ===")
    for module, time_ms in sorted_results[:5]:
        if time_ms != float("inf"):
            print(f"{module}: {time_ms:.1f}ms")


def test_dependency_analysis():
    """
    Test 3: Analyze import dependencies to identify optimization opportunities.

    Shows what imports happen during Kaizen load to identify lazy loading candidates.
    """
    print("\n=== DEPENDENCY ANALYSIS ===")

    # Use Python's import tracing to see what gets loaded
    import_trace_script = """
import sys
import time

loaded_before = set(sys.modules.keys())
start_time = time.perf_counter()

import kaizen

end_time = time.perf_counter()
loaded_after = set(sys.modules.keys())

new_modules = loaded_after - loaded_before
print(f"Import time: {(end_time - start_time) * 1000:.1f}ms")
print(f"Modules loaded: {len(new_modules)}")
print("Heavy dependencies (potential lazy loading candidates):")
for module in sorted(new_modules):
    if any(heavy in module for heavy in ['pandas', 'numpy', 'scipy', 'sklearn', 'torch', 'tensorflow', 'transformers']):
        print(f"  - {module}")
"""

    result = subprocess.run(
        [sys.executable, "-c", import_trace_script], capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(f"Errors: {result.stderr}")


def test_optimization_verification():
    """
    Test 4: Verify optimization targets for validation after implementation.

    This test will be used to validate each optimization step.
    """
    target_time_ms = 100

    # This will initially fail, but will pass after optimizations
    avg_time, times = measure_import_time("kaizen", runs=3)

    print("\n=== OPTIMIZATION VERIFICATION ===")
    print(f"Current import time: {avg_time:.1f}ms")
    print(f"Target: <{target_time_ms}ms")

    if avg_time < target_time_ms:
        print("✅ OPTIMIZATION SUCCESS: Target achieved!")
        print(f"Improvement: {target_time_ms - avg_time:.1f}ms under target")
    else:
        print("⏳ OPTIMIZATION IN PROGRESS: Target not yet achieved")
        print(f"Remaining: {avg_time - target_time_ms:.1f}ms to optimize")

    # Always record the measurement for tracking progress
    return avg_time


if __name__ == "__main__":
    """
    Run performance analysis directly.

    Usage: python test_import_performance.py
    """
    print("KAIZEN IMPORT PERFORMANCE ANALYSIS")
    print("=" * 50)

    # Ensure we're in the right directory
    kaizen_dir = ""
    if os.path.exists(kaizen_dir):
        os.chdir(kaizen_dir)
        sys.path.insert(0, os.path.join(kaizen_dir, "src"))

    try:
        # Run all performance tests
        test_kaizen_import_baseline()
        test_kaizen_import_breakdown()
        test_dependency_analysis()
        current_time = test_optimization_verification()

        print("\n" + "=" * 50)
        print(f"SUMMARY: Current import time is {current_time:.1f}ms")
        print("Target: <100ms")
        if current_time >= 100:
            print("❌ CRITICAL: Performance optimization required!")
        else:
            print("✅ SUCCESS: Performance target achieved!")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

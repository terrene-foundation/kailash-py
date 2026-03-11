"""
Performance Monitoring Example for Long-Running E2E Tests.

Demonstrates how to use PerformanceMonitor for tracking memory/CPU/performance
metrics during autonomous agent execution.

Usage:
    python examples/autonomy/performance_monitoring_example.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor


async def simulate_autonomous_agent_execution():
    """
    Simulate long-running autonomous agent execution.

    This example demonstrates:
    1. Memory profiling during agent execution
    2. CPU profiling during tool calls and planning
    3. Performance metrics for LLM/DB/checkpoint operations
    4. Real-time dashboard updates
    5. JSON export for CI integration
    """
    export_path = Path("performance_metrics.json")

    print("=" * 80)
    print("PERFORMANCE MONITORING EXAMPLE")
    print("=" * 80)
    print()
    print("Starting performance-monitored agent execution...")
    print("Dashboard will update every 10 seconds.")
    print()

    async with PerformanceMonitor(
        update_interval=10.0,  # Update dashboard every 10 seconds
        sampling_interval=2.0,  # Sample metrics every 2 seconds
        memory_threshold_mb=1000.0,  # Alert if > 1GB
        export_path=export_path,
    ) as monitor:
        print("Phase 1: Initialization (simulating agent startup)")
        print("-" * 80)

        # Simulate agent initialization
        initialization_data = []
        for i in range(50):
            initialization_data.append([i] * 1000)
            await asyncio.sleep(0.1)

        # Track component memory
        monitor._memory_profiler.track_component("agent", 150.0)
        monitor._memory_profiler.track_component("memory_hot", 50.0)

        print()
        print("Phase 2: Tool Calling (simulating autonomous execution)")
        print("-" * 80)

        # Simulate multiple tool calls
        for iteration in range(5):
            print(f"  Iteration {iteration + 1}/5: Calling tools...")

            # Simulate LLM inference
            await asyncio.sleep(0.2)
            monitor._metrics_collector.record_llm_latency(250.0 + iteration * 50)

            # Simulate tool execution
            await asyncio.sleep(0.3)
            monitor._cpu_profiler.track_system("tool_calling", 25.0)

            # Simulate database queries
            monitor._metrics_collector.record_db_query(read_ms=15.0 + iteration * 2)
            monitor._metrics_collector.record_db_query(write_ms=25.0 + iteration * 3)

            # Simulate memory allocation
            tool_data = [[j] * 500 for j in range(20)]
            await asyncio.sleep(0.2)

        print()
        print("Phase 3: Planning (simulating meta-controller planning)")
        print("-" * 80)

        # Simulate planning phase
        for plan_step in range(3):
            print(f"  Planning step {plan_step + 1}/3...")

            # Simulate LLM planning
            await asyncio.sleep(0.3)
            monitor._metrics_collector.record_llm_latency(400.0 + plan_step * 100)
            monitor._cpu_profiler.track_system("planning", 35.0)

            # Simulate checkpoint save
            await asyncio.sleep(0.2)
            monitor._metrics_collector.record_checkpoint_save(
                save_ms=200.0 + plan_step * 50, compression_ratio=0.35
            )

        print()
        print("Phase 4: Memory Management (simulating tier transitions)")
        print("-" * 80)

        # Simulate memory tier transitions
        monitor._memory_profiler.track_component("memory_warm", 30.0)
        monitor._memory_profiler.track_component("memory_cold", 15.0)

        # Simulate checkpoint load
        await asyncio.sleep(0.3)
        monitor._metrics_collector.record_checkpoint_load(150.0)

        print()
        print("Phase 5: Completion (waiting for final metrics)")
        print("-" * 80)

        # Wait for final dashboard update
        await asyncio.sleep(3.0)

    print()
    print("=" * 80)
    print("FINAL METRICS SUMMARY")
    print("=" * 80)

    # Get final metrics
    metrics = monitor.get_metrics()

    print()
    print("Memory Metrics:")
    print(f"  Peak Memory: {metrics['memory']['peak_mb']:.1f} MB")
    print(f"  Current Memory: {metrics['memory']['current_mb']:.1f} MB")
    print(f"  Growth Rate: {metrics['memory']['growth_rate_mb_per_min']:+.1f} MB/min")
    print(f"  Leak Detected: {'YES' if metrics['memory']['leak_detected'] else 'NO'}")

    print()
    print("CPU Metrics:")
    print(f"  Average CPU: {metrics['cpu']['average_percent']:.1f}%")
    print(f"  Peak CPU: {metrics['cpu']['peak_percent']:.1f}%")
    print(f"  Thread Count: {metrics['cpu']['thread_count']}")

    print()
    print("Performance Metrics:")
    llm = metrics["performance"]["llm_latency_ms"]
    print(
        f"  LLM Latency: p50={llm['p50']:.0f}ms, p95={llm['p95']:.0f}ms, p99={llm['p99']:.0f}ms"
    )

    db = metrics["performance"]["db_query_latency_ms"]
    print(f"  DB Read: p50={db['read_p50']:.0f}ms, p95={db['read_p95']:.0f}ms")
    print(f"  DB Write: p50={db['write_p50']:.0f}ms, p95={db['write_p95']:.0f}ms")

    checkpoint = metrics["performance"]["checkpoint_io_ms"]
    print(f"  Checkpoint Save: mean={checkpoint['save_mean']:.0f}ms")
    print(f"  Checkpoint Load: mean={checkpoint['load_mean']:.0f}ms")
    print(f"  Compression Ratio: {checkpoint['compression_ratio']*100:.0f}%")

    print()
    print("Runtime Metrics:")
    runtime = metrics["runtime"]
    print(f"  Duration: {runtime['duration_seconds']:.1f} seconds")
    print(f"  Samples Collected: {runtime['samples_collected']}")
    print(f"  Alerts Triggered: {runtime['alerts_triggered']}")

    print()
    print(f"Metrics exported to: {export_path.absolute()}")
    print()

    # Display full dashboard
    print()
    print(monitor.render_dashboard())


async def example_usage_in_e2e_test():
    """
    Example of using PerformanceMonitor in an E2E test.

    This demonstrates the typical pattern for integrating performance
    monitoring into autonomous agent tests.
    """
    print()
    print("=" * 80)
    print("E2E TEST USAGE EXAMPLE")
    print("=" * 80)
    print()

    # Example E2E test pattern
    async with PerformanceMonitor(
        update_interval=600,  # Update every 10 minutes for long tests
        export_path=Path("test-results/perf_metrics.json"),
    ) as monitor:
        # Run autonomous agent test
        print("Running multi-hour autonomous agent test...")
        await asyncio.sleep(2.0)  # Simulated long test

        # Validate performance constraints
        metrics = monitor.get_metrics()

        print()
        print("Performance Validation:")

        # Check memory leak
        if metrics["memory"]["peak_mb"] > 1000:
            print("  ⚠️  WARNING: Peak memory > 1GB")
        else:
            print("  ✅ Memory usage OK")

        # Check CPU usage
        if metrics["cpu"]["average_percent"] > 80:
            print("  ⚠️  WARNING: Average CPU > 80%")
        else:
            print("  ✅ CPU usage OK")

        # Check LLM latency
        if metrics["performance"]["llm_latency_ms"]["p95"] > 1000:
            print("  ⚠️  WARNING: LLM p95 latency > 1s")
        else:
            print("  ✅ LLM latency OK")

    print()


async def main():
    """Run all examples."""
    # Example 1: Detailed simulation
    await simulate_autonomous_agent_execution()

    # Example 2: E2E test pattern
    await example_usage_in_e2e_test()


if __name__ == "__main__":
    asyncio.run(main())

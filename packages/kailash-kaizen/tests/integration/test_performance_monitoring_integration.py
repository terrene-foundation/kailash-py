"""
Integration tests for performance monitoring (TODO-176 Week 2).

Tests PerformanceMonitor with realistic workloads simulating long-running
autonomous agent execution.

Tier 2: Integration tests - Real infrastructure, NO MOCKING
"""

import asyncio
import json
import time
from pathlib import Path

import pytest

from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor


@pytest.mark.asyncio
async def test_performance_monitor_with_simulated_workload():
    """
    Test PerformanceMonitor with simulated agent workload.

    Simulates memory-intensive and CPU-intensive operations similar to
    autonomous agent execution.
    """
    export_path = Path("/tmp/test_perf_monitor.json")

    if export_path.exists():
        export_path.unlink()

    async with PerformanceMonitor(
        update_interval=2.0,
        sampling_interval=0.5,
        memory_threshold_mb=500.0,
        export_path=export_path,
    ) as monitor:
        # Simulate memory-intensive work (loading data)
        large_data = []
        for i in range(100):
            large_data.append([i] * 1000)
            await asyncio.sleep(0.01)

        # Simulate CPU-intensive work (computation)
        result = 0
        for i in range(100000):
            result += i * i
            if i % 10000 == 0:
                await asyncio.sleep(0.01)

        # Let monitor collect a few samples
        await asyncio.sleep(1.0)

    # Validate metrics were collected
    metrics = monitor.get_metrics()

    assert metrics["runtime"]["samples_collected"] >= 2
    assert metrics["memory"]["current_mb"] > 0
    assert metrics["cpu"]["current_percent"] >= 0

    # Validate JSON export
    assert export_path.exists()

    with open(export_path) as f:
        exported_data = json.load(f)

    assert "memory" in exported_data
    assert "cpu" in exported_data
    assert "performance" in exported_data
    assert "runtime" in exported_data

    # Cleanup
    export_path.unlink()


@pytest.mark.asyncio
async def test_performance_monitor_memory_leak_detection():
    """
    Test memory leak detection with sustained memory growth.

    Simulates memory leak by continuously allocating memory without cleanup.
    """
    async with PerformanceMonitor(
        update_interval=1.0,
        sampling_interval=0.2,
        memory_threshold_mb=2000.0,  # High threshold
    ) as monitor:
        # Simulate memory leak (continuous growth)
        memory_hog = []
        for i in range(10):
            # Allocate 10 MB per iteration
            memory_hog.append([0] * (1024 * 1024))
            await asyncio.sleep(0.3)

    metrics = monitor.get_metrics()

    # Should detect growth (though may not trigger leak detection in short test)
    assert metrics["memory"]["growth_rate_mb_per_min"] > 0
    assert metrics["memory"]["peak_mb"] > metrics["memory"]["current_mb"] * 0.5


@pytest.mark.asyncio
async def test_performance_monitor_dashboard_rendering():
    """Test dashboard rendering produces valid output."""
    async with PerformanceMonitor(
        update_interval=1.0, sampling_interval=0.3
    ) as monitor:
        await asyncio.sleep(0.5)

        # Render dashboard
        dashboard = monitor.render_dashboard()

        assert isinstance(dashboard, str)
        assert len(dashboard) > 0
        assert "KAIZEN E2E PERFORMANCE MONITOR" in dashboard
        assert "MEMORY PROFILE" in dashboard
        assert "CPU PROFILE" in dashboard


@pytest.mark.asyncio
async def test_performance_monitor_component_tracking():
    """Test per-component memory tracking."""
    async with PerformanceMonitor(
        update_interval=2.0, sampling_interval=0.5
    ) as monitor:
        # Simulate component allocations
        monitor._memory_profiler.track_component("agent", 150.0)
        monitor._memory_profiler.track_component("memory_hot", 50.0)
        monitor._memory_profiler.track_component("checkpoints", 40.0)

        await asyncio.sleep(0.2)

    metrics = monitor.get_metrics()
    breakdown = metrics["memory"]["component_breakdown"]

    assert breakdown["agent"] == 150.0
    assert breakdown["memory_hot"] == 50.0
    assert breakdown["checkpoints"] == 40.0


@pytest.mark.asyncio
async def test_performance_monitor_metrics_collection():
    """Test LLM/DB/checkpoint metrics collection."""
    async with PerformanceMonitor(
        update_interval=2.0, sampling_interval=0.5
    ) as monitor:
        # Simulate LLM inferences
        monitor._metrics_collector.record_llm_latency(250.0)
        monitor._metrics_collector.record_llm_latency(300.0)
        monitor._metrics_collector.record_llm_latency(400.0)

        # Simulate DB queries
        monitor._metrics_collector.record_db_query(read_ms=15.0)
        monitor._metrics_collector.record_db_query(write_ms=25.0)

        # Simulate checkpoint I/O
        monitor._metrics_collector.record_checkpoint_save(200.0, compression_ratio=0.4)
        monitor._metrics_collector.record_checkpoint_load(150.0)

        await asyncio.sleep(0.2)

    metrics = monitor.get_metrics()
    perf = metrics["performance"]

    assert perf["llm_latency_ms"]["mean"] > 0
    assert perf["db_query_latency_ms"]["read_p50"] > 0
    assert perf["checkpoint_io_ms"]["save_mean"] > 0


@pytest.mark.asyncio
async def test_performance_monitor_concurrent_access():
    """Test concurrent metric collection is safe."""
    async with PerformanceMonitor(
        update_interval=1.0, sampling_interval=0.2
    ) as monitor:
        # Simulate concurrent access from multiple tasks
        async def simulate_work(task_id: int):
            for i in range(5):
                monitor._metrics_collector.record_llm_latency(100.0 + task_id * 10)
                await asyncio.sleep(0.1)

        tasks = [
            asyncio.create_task(simulate_work(1)),
            asyncio.create_task(simulate_work(2)),
            asyncio.create_task(simulate_work(3)),
        ]

        await asyncio.gather(*tasks)

    metrics = monitor.get_metrics()

    # Should have 15 samples (3 tasks * 5 samples each)
    assert len(monitor._metrics_collector._llm_latencies) == 15


@pytest.mark.asyncio
async def test_performance_monitor_short_duration():
    """Test monitor works correctly for short durations."""
    async with PerformanceMonitor(
        update_interval=5.0, sampling_interval=0.1  # Longer than test duration
    ) as monitor:
        await asyncio.sleep(0.3)

    metrics = monitor.get_metrics()

    # Should have at least 3 samples (0.3s / 0.1s)
    assert metrics["runtime"]["samples_collected"] >= 3
    assert metrics["runtime"]["duration_seconds"] >= 0.3


@pytest.mark.asyncio
async def test_performance_monitor_metric_structure_validation():
    """Validate complete metrics structure."""
    async with PerformanceMonitor() as monitor:
        await asyncio.sleep(0.2)

    metrics = monitor.get_metrics()

    # Validate structure
    assert "memory" in metrics
    assert "cpu" in metrics
    assert "performance" in metrics
    assert "runtime" in metrics

    # Validate memory fields
    memory = metrics["memory"]
    assert "current_mb" in memory
    assert "peak_mb" in memory
    assert "vms_mb" in memory
    assert "growth_rate_mb_per_min" in memory
    assert "leak_detected" in memory
    assert "component_breakdown" in memory
    assert "alerts" in memory

    # Validate CPU fields
    cpu = metrics["cpu"]
    assert "current_percent" in cpu
    assert "average_percent" in cpu
    assert "peak_percent" in cpu
    assert "thread_count" in cpu
    assert "system_breakdown" in cpu

    # Validate performance fields
    perf = metrics["performance"]
    assert "llm_latency_ms" in perf
    assert "db_query_latency_ms" in perf
    assert "checkpoint_io_ms" in perf

    # Validate runtime fields
    runtime = metrics["runtime"]
    assert "duration_seconds" in runtime
    assert "samples_collected" in runtime
    assert "alerts_triggered" in runtime
    assert "update_count" in runtime

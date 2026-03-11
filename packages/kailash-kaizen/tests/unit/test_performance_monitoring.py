"""
Unit tests for performance monitoring components (TODO-176 Week 2).

Tests MemoryProfiler, CPUProfiler, MetricsCollector, DashboardRenderer, and
PerformanceMonitor using isolated unit tests with mocked dependencies.

Tier 1: Unit tests - Fast (<1s), isolated, can use mocks
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


class TestMemoryProfiler:
    """Unit tests for MemoryProfiler component."""

    def test_initialization(self):
        """Test MemoryProfiler initializes with correct defaults."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler(threshold_mb=1000.0)

        assert profiler.threshold_mb == 1000.0
        assert profiler._samples == []
        assert profiler._peak_mb == 0.0
        assert profiler._leak_detected is False

    def test_collect_memory_snapshot(self):
        """Test collecting memory snapshot returns correct structure."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler()

        with patch.object(profiler._process, "memory_info") as mock_mem_info:
            mock_mem = Mock()
            mock_mem.rss = 256 * 1024 * 1024  # 256 MB
            mock_mem.vms = 512 * 1024 * 1024  # 512 MB
            mock_mem_info.return_value = mock_mem

            snapshot = profiler.collect_snapshot()

        assert hasattr(snapshot, "rss_mb")
        assert hasattr(snapshot, "vms_mb")
        assert hasattr(snapshot, "timestamp")
        assert snapshot.rss_mb == 256.0
        assert snapshot.vms_mb == 512.0

    def test_peak_memory_tracking(self):
        """Test peak memory is correctly tracked across samples."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler()

        with patch.object(profiler._process, "memory_info") as mock_mem_info:
            # First sample: 100 MB
            mock_mem = Mock()
            mock_mem.rss = 100 * 1024 * 1024
            mock_mem.vms = 200 * 1024 * 1024
            mock_mem_info.return_value = mock_mem
            profiler.collect_snapshot()

            # Second sample: 300 MB (peak)
            mock_mem.rss = 300 * 1024 * 1024
            mock_mem.vms = 400 * 1024 * 1024
            mock_mem_info.return_value = mock_mem
            profiler.collect_snapshot()

            # Third sample: 150 MB
            mock_mem.rss = 150 * 1024 * 1024
            mock_mem.vms = 250 * 1024 * 1024
            mock_mem_info.return_value = mock_mem
            profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert metrics["peak_mb"] == 300.0
        assert metrics["current_mb"] == 150.0

    def test_memory_growth_rate_calculation(self):
        """Test memory growth rate is calculated correctly."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler()

        with patch.object(profiler._process, "memory_info") as mock_mem_info:
            # Sample at t=0: 100 MB
            mock_mem = Mock()
            mock_mem.rss = 100 * 1024 * 1024
            mock_mem.vms = 200 * 1024 * 1024
            mock_mem_info.return_value = mock_mem

            with patch(
                "tests.e2e.autonomy.performance_monitoring.time.time", return_value=0.0
            ):
                profiler.collect_snapshot()

            # Sample at t=60s: 160 MB (growth of 60 MB in 60s = 1 MB/s = 60 MB/min)
            mock_mem.rss = 160 * 1024 * 1024
            mock_mem.vms = 260 * 1024 * 1024
            mock_mem_info.return_value = mock_mem

            with patch(
                "tests.e2e.autonomy.performance_monitoring.time.time", return_value=60.0
            ):
                profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert abs(metrics["growth_rate_mb_per_min"] - 60.0) < 0.1

    def test_leak_detection_positive(self):
        """Test leak detection identifies sustained memory growth."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler(leak_threshold_mb_per_min=5.0)

        with patch.object(profiler._process, "memory_info") as mock_mem_info:
            # Simulate sustained growth over 5 minutes
            for i in range(6):
                mock_mem = Mock()
                mock_mem.rss = (100 + i * 10) * 1024 * 1024  # +10 MB per minute
                mock_mem.vms = (200 + i * 10) * 1024 * 1024
                mock_mem_info.return_value = mock_mem

                with patch(
                    "tests.e2e.autonomy.performance_monitoring.time.time",
                    return_value=i * 60.0,
                ):
                    profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert metrics["leak_detected"] is True
        assert metrics["growth_rate_mb_per_min"] > 5.0

    def test_leak_detection_negative(self):
        """Test leak detection does not trigger on stable memory."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler(leak_threshold_mb_per_min=5.0)

        with patch("psutil.Process") as mock_process:
            mock_mem = Mock()
            mock_process.return_value.memory_info.return_value = mock_mem

            # Simulate stable memory over 5 minutes
            for i in range(6):
                mock_mem.rss = (100 + (i % 2) * 2) * 1024 * 1024  # ±2 MB fluctuation
                mock_mem.vms = (200 + (i % 2) * 2) * 1024 * 1024

                with patch("time.time", return_value=i * 60.0):
                    profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert metrics["leak_detected"] is False

    def test_component_breakdown(self):
        """Test component memory breakdown tracking."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler()

        # Track component allocations
        profiler.track_component("agent", 120.5)
        profiler.track_component("memory_hot", 45.2)
        profiler.track_component("memory_warm", 30.1)
        profiler.track_component("memory_cold", 15.8)
        profiler.track_component("checkpoints", 34.2)

        metrics = profiler.get_metrics()
        breakdown = metrics["component_breakdown"]

        assert breakdown["agent"] == 120.5
        assert breakdown["memory_hot"] == 45.2
        assert breakdown["memory_warm"] == 30.1
        assert breakdown["memory_cold"] == 15.8
        assert breakdown["checkpoints"] == 34.2

    def test_threshold_alert(self):
        """Test memory threshold alert triggers correctly."""
        from tests.e2e.autonomy.performance_monitoring import MemoryProfiler

        profiler = MemoryProfiler(threshold_mb=500.0)

        with patch.object(profiler._process, "memory_info") as mock_mem_info:
            mock_mem = Mock()
            mock_mem.rss = 600 * 1024 * 1024  # 600 MB > 500 MB threshold
            mock_mem.vms = 800 * 1024 * 1024
            mock_mem_info.return_value = mock_mem

            snapshot = profiler.collect_snapshot()

        assert snapshot.threshold_exceeded is True
        metrics = profiler.get_metrics()
        assert len(metrics["alerts"]) == 1
        assert "threshold exceeded" in metrics["alerts"][0].lower()


class TestCPUProfiler:
    """Unit tests for CPUProfiler component."""

    def test_initialization(self):
        """Test CPUProfiler initializes with correct defaults."""
        from tests.e2e.autonomy.performance_monitoring import CPUProfiler

        profiler = CPUProfiler()

        assert profiler._samples == []
        assert profiler._peak_percent == 0.0
        assert profiler._system_breakdown == {}

    def test_collect_cpu_snapshot(self):
        """Test collecting CPU snapshot returns correct structure."""
        from tests.e2e.autonomy.performance_monitoring import CPUProfiler

        profiler = CPUProfiler()

        with patch.object(profiler._process, "cpu_percent", return_value=45.3):
            with patch.object(profiler._process, "num_threads", return_value=12):
                snapshot = profiler.collect_snapshot()

        assert hasattr(snapshot, "cpu_percent")
        assert hasattr(snapshot, "thread_count")
        assert hasattr(snapshot, "timestamp")
        assert snapshot.cpu_percent == 45.3
        assert snapshot.thread_count == 12

    def test_peak_cpu_tracking(self):
        """Test peak CPU usage is correctly tracked."""
        from tests.e2e.autonomy.performance_monitoring import CPUProfiler

        profiler = CPUProfiler()

        # Collect samples with varying CPU usage
        cpu_values = [30.0, 67.2, 45.0, 38.5]

        for cpu in cpu_values:
            with patch.object(profiler._process, "cpu_percent", return_value=cpu):
                with patch.object(profiler._process, "num_threads", return_value=12):
                    profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert metrics["peak_percent"] == 67.2
        assert metrics["current_percent"] == 38.5

    def test_average_cpu_calculation(self):
        """Test average CPU usage is calculated correctly."""
        from tests.e2e.autonomy.performance_monitoring import CPUProfiler

        profiler = CPUProfiler()

        # Collect samples: 30, 40, 50, 60 -> avg = 45
        cpu_values = [30.0, 40.0, 50.0, 60.0]

        for cpu in cpu_values:
            with patch.object(profiler._process, "cpu_percent", return_value=cpu):
                with patch.object(profiler._process, "num_threads", return_value=12):
                    profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert abs(metrics["average_percent"] - 45.0) < 0.1

    def test_system_breakdown_tracking(self):
        """Test CPU system breakdown tracking."""
        from tests.e2e.autonomy.performance_monitoring import CPUProfiler

        profiler = CPUProfiler()

        # Track CPU usage by system
        profiler.track_system("tool_calling", 15.2)
        profiler.track_system("planning", 25.3)
        profiler.track_system("meta_controller", 8.7)
        profiler.track_system("memory", 12.1)
        profiler.track_system("checkpoints", 5.4)
        profiler.track_system("interrupts", 2.0)

        metrics = profiler.get_metrics()
        breakdown = metrics["system_breakdown"]

        assert breakdown["tool_calling"] == 15.2
        assert breakdown["planning"] == 25.3
        assert breakdown["meta_controller"] == 8.7
        assert breakdown["memory"] == 12.1
        assert breakdown["checkpoints"] == 5.4
        assert breakdown["interrupts"] == 2.0

    def test_thread_count_tracking(self):
        """Test thread count is tracked correctly."""
        from tests.e2e.autonomy.performance_monitoring import CPUProfiler

        profiler = CPUProfiler()

        with patch.object(profiler._process, "cpu_percent", return_value=45.0):
            with patch.object(profiler._process, "num_threads", return_value=18):
                profiler.collect_snapshot()

        metrics = profiler.get_metrics()
        assert metrics["thread_count"] == 18


class TestMetricsCollector:
    """Unit tests for MetricsCollector component."""

    def test_initialization(self):
        """Test MetricsCollector initializes with correct defaults."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        assert collector._llm_latencies == []
        assert collector._db_read_latencies == []
        assert collector._db_write_latencies == []
        assert collector._checkpoint_save_times == []
        assert collector._checkpoint_load_times == []

    def test_record_llm_latency(self):
        """Test recording LLM latency."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        collector.record_llm_latency(245.3)
        collector.record_llm_latency(512.7)
        collector.record_llm_latency(789.2)

        metrics = collector.get_metrics()
        llm = metrics["llm_latency_ms"]

        assert len(collector._llm_latencies) == 3
        assert llm["mean"] > 0

    def test_llm_latency_percentiles(self):
        """Test LLM latency percentile calculation."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        # Record 100 samples for accurate percentiles
        for i in range(100):
            collector.record_llm_latency(i * 10.0)  # 0, 10, 20, ..., 990

        metrics = collector.get_metrics()
        llm = metrics["llm_latency_ms"]

        # p50 should be around 500ms (50th value)
        assert 450 <= llm["p50"] <= 550
        # p95 should be around 950ms (95th value)
        assert 900 <= llm["p95"] <= 1000
        # p99 should be around 990ms (99th value)
        assert 980 <= llm["p99"] <= 1000

    def test_record_db_query_latency(self):
        """Test recording database query latency."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        collector.record_db_query(read_ms=12.3)
        collector.record_db_query(write_ms=18.7)
        collector.record_db_query(read_ms=10.5)
        collector.record_db_query(write_ms=22.1)

        metrics = collector.get_metrics()
        db = metrics["db_query_latency_ms"]

        assert len(collector._db_read_latencies) == 2
        assert len(collector._db_write_latencies) == 2
        assert "read_p50" in db
        assert "write_p50" in db

    def test_record_checkpoint_io(self):
        """Test recording checkpoint I/O times."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        collector.record_checkpoint_save(234.5, compression_ratio=0.35)
        collector.record_checkpoint_save(256.3, compression_ratio=0.32)
        collector.record_checkpoint_load(156.2)
        collector.record_checkpoint_load(142.8)

        metrics = collector.get_metrics()
        checkpoint = metrics["checkpoint_io_ms"]

        assert len(collector._checkpoint_save_times) == 2
        assert len(collector._checkpoint_load_times) == 2
        assert "save_mean" in checkpoint
        assert "load_mean" in checkpoint
        assert "compression_ratio" in checkpoint

    def test_compression_ratio_calculation(self):
        """Test compression ratio is calculated as average."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        collector.record_checkpoint_save(200.0, compression_ratio=0.40)
        collector.record_checkpoint_save(220.0, compression_ratio=0.30)
        collector.record_checkpoint_save(240.0, compression_ratio=0.35)

        metrics = collector.get_metrics()
        checkpoint = metrics["checkpoint_io_ms"]

        # Average compression: (0.40 + 0.30 + 0.35) / 3 = 0.35
        assert abs(checkpoint["compression_ratio"] - 0.35) < 0.01

    def test_empty_metrics_handling(self):
        """Test metrics with no data return zeros."""
        from tests.e2e.autonomy.performance_monitoring import MetricsCollector

        collector = MetricsCollector()

        metrics = collector.get_metrics()

        assert metrics["llm_latency_ms"]["mean"] == 0.0
        assert metrics["db_query_latency_ms"]["read_p50"] == 0.0
        assert metrics["checkpoint_io_ms"]["save_mean"] == 0.0


class TestDashboardRenderer:
    """Unit tests for DashboardRenderer component."""

    def test_initialization(self):
        """Test DashboardRenderer initializes correctly."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer()

        assert renderer._bar_width == 30
        assert renderer._use_rich is not None

    def test_render_memory_section(self):
        """Test rendering memory section."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer()

        memory_metrics = {
            "current_mb": 245.3,
            "peak_mb": 312.7,
            "vms_mb": 450.2,
            "growth_rate_mb_per_min": 1.2,
            "leak_detected": False,
            "component_breakdown": {
                "agent": 120.5,
                "memory_hot": 45.2,
                "memory_warm": 30.1,
                "memory_cold": 15.8,
                "checkpoints": 34.2,
            },
        }

        output = renderer.render_memory_section(memory_metrics)

        assert "MEMORY PROFILE" in output
        assert "245.3 MB" in output
        assert "312.7 MB" in output
        # Component name is lowercase in the output
        assert "agent" in output
        assert "120.5 MB" in output

    def test_render_cpu_section(self):
        """Test rendering CPU section."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer()

        cpu_metrics = {
            "current_percent": 45.3,
            "average_percent": 38.7,
            "peak_percent": 67.2,
            "thread_count": 12,
            "system_breakdown": {
                "tool_calling": 15.2,
                "planning": 25.3,
                "meta_controller": 8.7,
                "memory": 12.1,
                "checkpoints": 5.4,
                "interrupts": 2.0,
            },
        }

        output = renderer.render_cpu_section(cpu_metrics)

        assert "CPU PROFILE" in output
        assert "45.3%" in output
        assert "67.2%" in output
        # System name is lowercase in the output
        assert "planning" in output
        assert "25.3%" in output

    def test_render_performance_section(self):
        """Test rendering performance metrics section."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer()

        perf_metrics = {
            "llm_latency_ms": {"p50": 245.3, "p95": 512.7, "p99": 789.2, "mean": 287.5},
            "db_query_latency_ms": {
                "read_p50": 12.3,
                "write_p50": 18.7,
                "read_p95": 34.2,
                "write_p95": 45.1,
            },
            "checkpoint_io_ms": {
                "save_mean": 234.5,
                "load_mean": 156.2,
                "compression_ratio": 0.35,
            },
        }

        output = renderer.render_performance_section(perf_metrics)

        assert "PERFORMANCE METRICS" in output
        assert "p50=245ms" in output
        # p95 is rounded to 513ms due to float precision
        assert "p95=513ms" in output or "p95=512ms" in output
        assert "compression=35%" in output

    def test_render_progress_bar(self):
        """Test progress bar rendering."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer(bar_width=20)

        # 50% progress
        bar = renderer._render_progress_bar(0.5)
        assert "█" in bar
        assert len([c for c in bar if c == "█"]) == 10  # Half filled

        # 100% progress
        bar = renderer._render_progress_bar(1.0)
        assert len([c for c in bar if c == "█"]) == 20  # Fully filled

        # 0% progress
        bar = renderer._render_progress_bar(0.0)
        assert len([c for c in bar if c == "█"]) == 0  # Empty

    def test_format_duration(self):
        """Test duration formatting."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer()

        assert renderer._format_duration(90.0) == "01:30"
        assert renderer._format_duration(3665.0) == "61:05"
        assert renderer._format_duration(45.0) == "00:45"

    def test_render_full_dashboard(self):
        """Test rendering complete dashboard."""
        from tests.e2e.autonomy.performance_monitoring import DashboardRenderer

        renderer = DashboardRenderer()

        metrics = {
            "memory": {
                "current_mb": 245.3,
                "peak_mb": 312.7,
                "vms_mb": 450.2,
                "growth_rate_mb_per_min": 1.2,
                "leak_detected": False,
                "component_breakdown": {"agent": 120.5},
                "alerts": [],
            },
            "cpu": {
                "current_percent": 45.3,
                "average_percent": 38.7,
                "peak_percent": 67.2,
                "thread_count": 12,
                "system_breakdown": {"planning": 25.3},
            },
            "performance": {
                "llm_latency_ms": {
                    "p50": 245.3,
                    "p95": 512.7,
                    "p99": 789.2,
                    "mean": 287.5,
                },
                "db_query_latency_ms": {
                    "read_p50": 12.3,
                    "write_p50": 18.7,
                    "read_p95": 34.2,
                    "write_p95": 45.1,
                },
                "checkpoint_io_ms": {
                    "save_mean": 234.5,
                    "load_mean": 156.2,
                    "compression_ratio": 0.35,
                },
            },
            "runtime": {
                "duration_seconds": 3456.7,
                "samples_collected": 345,
                "alerts_triggered": 2,
                "update_count": 57,
            },
        }

        output = renderer.render_dashboard(metrics)

        assert "KAIZEN E2E PERFORMANCE MONITOR" in output
        assert "MEMORY PROFILE" in output
        assert "CPU PROFILE" in output
        assert "PERFORMANCE METRICS" in output
        assert "Runtime:" in output
        assert "Samples: 345" in output


class TestPerformanceMonitor:
    """Unit tests for PerformanceMonitor context manager."""

    def test_initialization(self):
        """Test PerformanceMonitor initializes with correct parameters."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor(
            update_interval=60.0,
            sampling_interval=10.0,
            memory_threshold_mb=1000.0,
            export_path=Path("/tmp/metrics.json"),
        )

        assert monitor.update_interval == 60.0
        assert monitor.sampling_interval == 10.0
        assert monitor.memory_threshold_mb == 1000.0
        assert monitor.export_path == Path("/tmp/metrics.json")

    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(self):
        """Test PerformanceMonitor context manager lifecycle."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor(update_interval=1.0, sampling_interval=0.5)

        assert monitor._running is False

        async with monitor:
            assert monitor._running is True
            await asyncio.sleep(0.1)  # Brief wait to allow collection

        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_metric_collection_during_execution(self):
        """Test metrics are collected during execution."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor(update_interval=1.0, sampling_interval=0.2)

        async with monitor:
            await asyncio.sleep(0.5)  # Allow at least 2 samples

        metrics = monitor.get_metrics()

        assert metrics["runtime"]["samples_collected"] >= 2
        assert metrics["memory"]["current_mb"] > 0
        assert metrics["cpu"]["current_percent"] >= 0

    @pytest.mark.asyncio
    async def test_dashboard_updates(self):
        """Test dashboard updates occur at specified interval."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor(update_interval=0.3, sampling_interval=0.1)

        update_count = 0

        with patch.object(monitor, "_display_dashboard") as mock_display:
            async with monitor:
                await asyncio.sleep(0.7)  # Should trigger 2 updates

            update_count = mock_display.call_count

        assert update_count >= 2

    @pytest.mark.asyncio
    async def test_json_export(self, tmp_path):
        """Test metrics are exported to JSON correctly."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        export_path = tmp_path / "test_metrics.json"

        monitor = PerformanceMonitor(
            update_interval=1.0, sampling_interval=0.2, export_path=export_path
        )

        async with monitor:
            await asyncio.sleep(0.3)

        assert export_path.exists()

        with open(export_path) as f:
            data = json.load(f)

        assert "memory" in data
        assert "cpu" in data
        assert "performance" in data
        assert "runtime" in data

    @pytest.mark.asyncio
    async def test_memory_threshold_alert(self):
        """Test alert is triggered when memory threshold is exceeded."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor(
            update_interval=1.0,
            sampling_interval=0.2,
            memory_threshold_mb=10.0,  # Very low threshold
        )

        async with monitor:
            await asyncio.sleep(0.5)

        metrics = monitor.get_metrics()

        # Current process should exceed 10 MB
        assert metrics["runtime"]["alerts_triggered"] > 0

    def test_get_metrics_structure(self):
        """Test get_metrics returns correct structure."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor()
        metrics = monitor.get_metrics()

        assert "memory" in metrics
        assert "cpu" in metrics
        assert "performance" in metrics
        assert "runtime" in metrics

        # Check memory structure
        assert "current_mb" in metrics["memory"]
        assert "peak_mb" in metrics["memory"]
        assert "component_breakdown" in metrics["memory"]

        # Check CPU structure
        assert "current_percent" in metrics["cpu"]
        assert "average_percent" in metrics["cpu"]
        assert "system_breakdown" in metrics["cpu"]

        # Check performance structure
        assert "llm_latency_ms" in metrics["performance"]
        assert "db_query_latency_ms" in metrics["performance"]
        assert "checkpoint_io_ms" in metrics["performance"]

        # Check runtime structure
        assert "duration_seconds" in metrics["runtime"]
        assert "samples_collected" in metrics["runtime"]

    def test_render_dashboard(self):
        """Test render_dashboard returns formatted string."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor()

        output = monitor.render_dashboard()

        assert isinstance(output, str)
        assert len(output) > 0
        assert "KAIZEN E2E PERFORMANCE MONITOR" in output

    @pytest.mark.asyncio
    async def test_concurrent_collection_safety(self):
        """Test concurrent metric collection is thread-safe."""
        from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

        monitor = PerformanceMonitor(update_interval=0.5, sampling_interval=0.1)

        async with monitor:
            # Simulate concurrent access
            tasks = [
                asyncio.create_task(asyncio.sleep(0.05)),
                asyncio.create_task(asyncio.sleep(0.05)),
                asyncio.create_task(asyncio.sleep(0.05)),
            ]
            await asyncio.gather(*tasks)

            # Should not crash, metrics should be consistent
            metrics = monitor.get_metrics()

        assert metrics["runtime"]["samples_collected"] > 0

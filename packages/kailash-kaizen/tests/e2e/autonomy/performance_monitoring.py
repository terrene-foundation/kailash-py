"""
Performance monitoring dashboard for E2E tests (TODO-176 Week 2).

Provides comprehensive memory/CPU profiling for long-running autonomous agent tests.

Features:
- Memory profiling: RSS, VMS, peak usage, leak detection
- CPU profiling: Process-level, thread-level, per-system tracking
- Performance metrics: LLM latency, DB queries, checkpoint I/O
- Real-time dashboard: Terminal UI with periodic updates
- CI integration: JSON export for continuous monitoring

Usage:
    from tests.e2e.autonomy.performance_monitoring import PerformanceMonitor

    async with PerformanceMonitor(update_interval=60) as monitor:
        # Run E2E test
        result = await agent.run_autonomous(task="...")

        # Get metrics
        metrics = monitor.get_metrics()
        print(f"Peak memory: {metrics['memory']['peak_mb']} MB")

Example integration:
    @pytest.mark.asyncio
    @pytest.mark.timeout(14400)
    async def test_multi_hour_code_review():
        async with PerformanceMonitor(
            update_interval=600,  # Update every 10 minutes
            export_path=Path("test-results/perf_code_review.json")
        ) as monitor:
            result = await agent.run_autonomous(task="...")

            # Validate performance
            metrics = monitor.get_metrics()
            assert metrics['memory']['peak_mb'] < 1000, "Memory leak detected"
            assert metrics['cpu']['average_percent'] < 80, "CPU too high"
"""

import asyncio
import json
import logging
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

# Try to import rich for better terminal output, fall back to plain text
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Single memory measurement snapshot."""

    rss_mb: float
    vms_mb: float
    timestamp: float
    threshold_exceeded: bool = False


@dataclass
class CPUSnapshot:
    """Single CPU measurement snapshot."""

    cpu_percent: float
    thread_count: int
    timestamp: float


class MemoryProfiler:
    """
    Memory profiler with leak detection and component tracking.

    Tracks RSS, VMS, peak usage, growth rate, and per-component allocations.
    """

    def __init__(
        self, threshold_mb: float = 1000.0, leak_threshold_mb_per_min: float = 5.0
    ):
        """
        Initialize memory profiler.

        Args:
            threshold_mb: Alert threshold in MB
            leak_threshold_mb_per_min: Leak detection threshold (MB/min growth)
        """
        self.threshold_mb = threshold_mb
        self.leak_threshold_mb_per_min = leak_threshold_mb_per_min

        self._samples: List[MemorySnapshot] = []
        self._peak_mb: float = 0.0
        self._leak_detected: bool = False
        self._component_breakdown: Dict[str, float] = {}
        self._alerts: List[str] = []
        self._process = psutil.Process()

    def collect_snapshot(self) -> MemorySnapshot:
        """
        Collect current memory snapshot.

        Returns:
            MemorySnapshot with current memory usage
        """
        mem_info = self._process.memory_info()
        rss_mb = mem_info.rss / (1024 * 1024)
        vms_mb = mem_info.vms / (1024 * 1024)

        threshold_exceeded = rss_mb > self.threshold_mb

        snapshot = MemorySnapshot(
            rss_mb=rss_mb,
            vms_mb=vms_mb,
            timestamp=time.time(),
            threshold_exceeded=threshold_exceeded,
        )

        self._samples.append(snapshot)

        # Update peak
        if rss_mb > self._peak_mb:
            self._peak_mb = rss_mb

        # Check threshold
        if threshold_exceeded:
            alert_msg = f"Memory threshold exceeded: {rss_mb:.1f} MB > {self.threshold_mb:.1f} MB at {datetime.now().isoformat()}"
            self._alerts.append(alert_msg)
            logger.warning(alert_msg)

        # Check for leak (need at least 5 minutes of samples)
        if len(self._samples) >= 6:  # 6 samples at 1 min intervals = 5 min
            self._detect_leak()

        return snapshot

    def track_component(self, name: str, size_mb: float) -> None:
        """
        Track memory usage by component.

        Args:
            name: Component name (e.g., "agent", "memory_hot")
            size_mb: Memory size in MB
        """
        self._component_breakdown[name] = size_mb

    def _detect_leak(self) -> None:
        """Detect memory leaks based on sustained growth."""
        if len(self._samples) < 6:
            return

        # Calculate linear regression on recent samples
        recent_samples = self._samples[-6:]  # Last 5 minutes

        # Calculate growth rate
        if len(recent_samples) >= 2:
            first_sample = recent_samples[0]
            last_sample = recent_samples[-1]

            time_diff_minutes = (last_sample.timestamp - first_sample.timestamp) / 60.0

            if time_diff_minutes > 0:
                memory_diff_mb = last_sample.rss_mb - first_sample.rss_mb
                growth_rate = memory_diff_mb / time_diff_minutes

                if growth_rate > self.leak_threshold_mb_per_min:
                    self._leak_detected = True
                    logger.warning(
                        f"Memory leak detected: growth rate {growth_rate:.2f} MB/min "
                        f"exceeds threshold {self.leak_threshold_mb_per_min:.2f} MB/min"
                    )

    def _calculate_growth_rate(self) -> float:
        """
        Calculate memory growth rate in MB/min.

        Returns:
            Growth rate in MB/min (0.0 if insufficient data)
        """
        if len(self._samples) < 2:
            return 0.0

        first_sample = self._samples[0]
        last_sample = self._samples[-1]

        time_diff_seconds = last_sample.timestamp - first_sample.timestamp

        if time_diff_seconds < 1.0:
            return 0.0

        time_diff_minutes = time_diff_seconds / 60.0
        memory_diff_mb = last_sample.rss_mb - first_sample.rss_mb

        return memory_diff_mb / time_diff_minutes

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current memory metrics.

        Returns:
            Dictionary with memory metrics
        """
        current_mb = self._samples[-1].rss_mb if self._samples else 0.0
        vms_mb = self._samples[-1].vms_mb if self._samples else 0.0

        return {
            "current_mb": current_mb,
            "peak_mb": self._peak_mb,
            "vms_mb": vms_mb,
            "growth_rate_mb_per_min": self._calculate_growth_rate(),
            "leak_detected": self._leak_detected,
            "component_breakdown": self._component_breakdown.copy(),
            "alerts": self._alerts.copy(),
        }


class CPUProfiler:
    """
    CPU profiler with per-system usage tracking.

    Tracks process-level, thread-level, and per-system CPU usage.
    """

    def __init__(self):
        """Initialize CPU profiler."""
        self._samples: List[CPUSnapshot] = []
        self._peak_percent: float = 0.0
        self._system_breakdown: Dict[str, float] = {}
        self._process = psutil.Process()

    def collect_snapshot(self) -> CPUSnapshot:
        """
        Collect current CPU snapshot.

        Returns:
            CPUSnapshot with current CPU usage
        """
        cpu_percent = self._process.cpu_percent()
        thread_count = self._process.num_threads()

        snapshot = CPUSnapshot(
            cpu_percent=cpu_percent, thread_count=thread_count, timestamp=time.time()
        )

        self._samples.append(snapshot)

        # Update peak
        if cpu_percent > self._peak_percent:
            self._peak_percent = cpu_percent

        return snapshot

    def track_system(self, name: str, cpu_percent: float) -> None:
        """
        Track CPU usage by system.

        Args:
            name: System name (e.g., "tool_calling", "planning")
            cpu_percent: CPU usage percentage
        """
        self._system_breakdown[name] = cpu_percent

    def _calculate_average(self) -> float:
        """
        Calculate average CPU usage.

        Returns:
            Average CPU percentage (0.0 if no samples)
        """
        if not self._samples:
            return 0.0

        return statistics.mean(s.cpu_percent for s in self._samples)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current CPU metrics.

        Returns:
            Dictionary with CPU metrics
        """
        current_percent = self._samples[-1].cpu_percent if self._samples else 0.0
        thread_count = self._samples[-1].thread_count if self._samples else 0

        return {
            "current_percent": current_percent,
            "average_percent": self._calculate_average(),
            "peak_percent": self._peak_percent,
            "thread_count": thread_count,
            "system_breakdown": self._system_breakdown.copy(),
        }


class MetricsCollector:
    """
    Performance metrics collector for LLM, DB, and checkpoint operations.

    Tracks latencies and calculates percentiles for performance analysis.
    """

    def __init__(self):
        """Initialize metrics collector."""
        self._llm_latencies: List[float] = []
        self._db_read_latencies: List[float] = []
        self._db_write_latencies: List[float] = []
        self._checkpoint_save_times: List[float] = []
        self._checkpoint_load_times: List[float] = []
        self._compression_ratios: List[float] = []

    def record_llm_latency(self, latency_ms: float) -> None:
        """
        Record LLM inference latency.

        Args:
            latency_ms: Latency in milliseconds
        """
        self._llm_latencies.append(latency_ms)

    def record_db_query(
        self, read_ms: Optional[float] = None, write_ms: Optional[float] = None
    ) -> None:
        """
        Record database query latency.

        Args:
            read_ms: Read query latency in milliseconds
            write_ms: Write query latency in milliseconds
        """
        if read_ms is not None:
            self._db_read_latencies.append(read_ms)
        if write_ms is not None:
            self._db_write_latencies.append(write_ms)

    def record_checkpoint_save(self, save_ms: float, compression_ratio: float) -> None:
        """
        Record checkpoint save operation.

        Args:
            save_ms: Save time in milliseconds
            compression_ratio: Compression ratio (0.0-1.0)
        """
        self._checkpoint_save_times.append(save_ms)
        self._compression_ratios.append(compression_ratio)

    def record_checkpoint_load(self, load_ms: float) -> None:
        """
        Record checkpoint load operation.

        Args:
            load_ms: Load time in milliseconds
        """
        self._checkpoint_load_times.append(load_ms)

    def _calculate_percentiles(self, data: List[float]) -> Dict[str, float]:
        """
        Calculate p50, p95, p99 percentiles.

        Args:
            data: List of values

        Returns:
            Dictionary with percentiles and mean
        """
        if not data:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}

        sorted_data = sorted(data)
        n = len(sorted_data)

        return {
            "p50": sorted_data[int(n * 0.50)] if n > 0 else 0.0,
            "p95": sorted_data[int(n * 0.95)] if n > 0 else 0.0,
            "p99": sorted_data[int(n * 0.99)] if n > 0 else 0.0,
            "mean": statistics.mean(data) if data else 0.0,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics.

        Returns:
            Dictionary with performance metrics
        """
        llm_metrics = self._calculate_percentiles(self._llm_latencies)

        db_metrics = {
            "read_p50": self._calculate_percentiles(self._db_read_latencies)["p50"],
            "write_p50": self._calculate_percentiles(self._db_write_latencies)["p50"],
            "read_p95": self._calculate_percentiles(self._db_read_latencies)["p95"],
            "write_p95": self._calculate_percentiles(self._db_write_latencies)["p95"],
        }

        checkpoint_metrics = {
            "save_mean": (
                statistics.mean(self._checkpoint_save_times)
                if self._checkpoint_save_times
                else 0.0
            ),
            "load_mean": (
                statistics.mean(self._checkpoint_load_times)
                if self._checkpoint_load_times
                else 0.0
            ),
            "compression_ratio": (
                statistics.mean(self._compression_ratios)
                if self._compression_ratios
                else 0.0
            ),
        }

        return {
            "llm_latency_ms": llm_metrics,
            "db_query_latency_ms": db_metrics,
            "checkpoint_io_ms": checkpoint_metrics,
        }


class DashboardRenderer:
    """
    Terminal dashboard renderer with rich formatting.

    Renders real-time performance dashboard with progress bars and formatting.
    """

    def __init__(self, bar_width: int = 30):
        """
        Initialize dashboard renderer.

        Args:
            bar_width: Width of progress bars in characters
        """
        self._bar_width = bar_width
        self._use_rich = RICH_AVAILABLE

        if self._use_rich:
            self._console = Console()

    def render_dashboard(self, metrics: Dict[str, Any]) -> str:
        """
        Render complete dashboard.

        Args:
            metrics: Complete metrics dictionary

        Returns:
            Formatted dashboard string
        """
        lines = []
        separator = "=" * 80

        # Header
        lines.append(separator)
        lines.append("KAIZEN E2E PERFORMANCE MONITOR")
        lines.append(separator)

        runtime = metrics["runtime"]
        lines.append(
            f"Runtime: {self._format_duration(runtime['duration_seconds'])} | "
            f"Samples: {runtime['samples_collected']} | "
            f"Updates: {runtime.get('update_count', 0)}"
        )

        if runtime["alerts_triggered"] > 0:
            lines.append(f"Alerts: {runtime['alerts_triggered']}")

        lines.append("")

        # Memory section
        lines.append(self.render_memory_section(metrics["memory"]))
        lines.append("")

        # CPU section
        lines.append(self.render_cpu_section(metrics["cpu"]))
        lines.append("")

        # Performance section
        lines.append(self.render_performance_section(metrics["performance"]))
        lines.append("")

        lines.append(separator)

        return "\n".join(lines)

    def render_memory_section(self, memory: Dict[str, Any]) -> str:
        """
        Render memory profile section.

        Args:
            memory: Memory metrics

        Returns:
            Formatted memory section
        """
        lines = []
        lines.append("MEMORY PROFILE")
        lines.append("-" * 80)

        lines.append(
            f"  Current: {memory['current_mb']:.1f} MB | "
            f"Peak: {memory['peak_mb']:.1f} MB | "
            f"VMS: {memory['vms_mb']:.1f} MB"
        )

        leak_status = "YES" if memory["leak_detected"] else "NO"
        leak_emoji = "⚠️" if memory["leak_detected"] else "✅"

        lines.append(
            f"  Growth Rate: {memory['growth_rate_mb_per_min']:+.1f} MB/min | "
            f"Leak: {leak_emoji} {leak_status}"
        )

        # Component breakdown
        if memory["component_breakdown"]:
            lines.append("")
            lines.append("  Component Breakdown:")

            total_mb = sum(memory["component_breakdown"].values())

            for component, size_mb in sorted(
                memory["component_breakdown"].items(), key=lambda x: x[1], reverse=True
            ):
                percentage = (size_mb / total_mb * 100) if total_mb > 0 else 0
                bar = self._render_progress_bar(
                    size_mb / total_mb if total_mb > 0 else 0
                )

                lines.append(
                    f"    {component:15s} {size_mb:6.1f} MB ({percentage:4.1f}%)  {bar}"
                )

        return "\n".join(lines)

    def render_cpu_section(self, cpu: Dict[str, Any]) -> str:
        """
        Render CPU profile section.

        Args:
            cpu: CPU metrics

        Returns:
            Formatted CPU section
        """
        lines = []
        lines.append("CPU PROFILE")
        lines.append("-" * 80)

        lines.append(
            f"  Current: {cpu['current_percent']:.1f}% | "
            f"Average: {cpu['average_percent']:.1f}% | "
            f"Peak: {cpu['peak_percent']:.1f}% | "
            f"Threads: {cpu['thread_count']}"
        )

        # System breakdown
        if cpu["system_breakdown"]:
            lines.append("")
            lines.append("  System Breakdown:")

            for system, percent in sorted(
                cpu["system_breakdown"].items(), key=lambda x: x[1], reverse=True
            ):
                bar = self._render_progress_bar(percent / 100.0)

                lines.append(f"    {system:20s} {percent:5.1f}% {bar}")

        return "\n".join(lines)

    def render_performance_section(self, performance: Dict[str, Any]) -> str:
        """
        Render performance metrics section.

        Args:
            performance: Performance metrics

        Returns:
            Formatted performance section
        """
        lines = []
        lines.append("PERFORMANCE METRICS")
        lines.append("-" * 80)

        llm = performance["llm_latency_ms"]
        db = performance["db_query_latency_ms"]
        checkpoint = performance["checkpoint_io_ms"]

        lines.append(
            f"  LLM Latency:     "
            f"p50={llm['p50']:.0f}ms | "
            f"p95={llm['p95']:.0f}ms | "
            f"p99={llm['p99']:.0f}ms"
        )

        lines.append(
            f"  DB Read:         "
            f"p50={db['read_p50']:.0f}ms  | "
            f"p95={db['read_p95']:.0f}ms"
        )

        lines.append(
            f"  DB Write:        "
            f"p50={db['write_p50']:.0f}ms  | "
            f"p95={db['write_p95']:.0f}ms"
        )

        lines.append(
            f"  Checkpoint Save: "
            f"mean={checkpoint['save_mean']:.0f}ms | "
            f"compression={checkpoint['compression_ratio']*100:.0f}%"
        )

        lines.append(f"  Checkpoint Load: " f"mean={checkpoint['load_mean']:.0f}ms")

        return "\n".join(lines)

    def _render_progress_bar(self, progress: float) -> str:
        """
        Render progress bar.

        Args:
            progress: Progress value (0.0-1.0)

        Returns:
            Progress bar string
        """
        filled = int(progress * self._bar_width)
        empty = self._bar_width - filled

        return f"[{'█' * filled}{' ' * empty}]"

    def _format_duration(self, seconds: float) -> str:
        """
        Format duration as MM:SS.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"


class PerformanceMonitor:
    """
    Context manager for comprehensive performance monitoring during E2E tests.

    Integrates memory profiling, CPU profiling, performance metrics collection,
    and real-time dashboard rendering with JSON export.

    Example:
        async with PerformanceMonitor(update_interval=60) as monitor:
            # Run E2E test
            result = await agent.run_autonomous(task="...")

            # Get metrics
            metrics = monitor.get_metrics()
            assert metrics['memory']['peak_mb'] < 1000
    """

    def __init__(
        self,
        update_interval: float = 60.0,
        sampling_interval: float = 10.0,
        memory_threshold_mb: float = 1000.0,
        export_path: Optional[Path] = None,
    ):
        """
        Initialize performance monitor.

        Args:
            update_interval: Dashboard update interval in seconds
            sampling_interval: Metric sampling interval in seconds
            memory_threshold_mb: Memory alert threshold in MB
            export_path: Path to export JSON metrics (optional)
        """
        self.update_interval = update_interval
        self.sampling_interval = sampling_interval
        self.memory_threshold_mb = memory_threshold_mb
        self.export_path = export_path

        self._memory_profiler = MemoryProfiler(threshold_mb=memory_threshold_mb)
        self._cpu_profiler = CPUProfiler()
        self._metrics_collector = MetricsCollector()
        self._dashboard_renderer = DashboardRenderer()

        self._running = False
        self._start_time: float = 0.0
        self._sample_count: int = 0
        self._update_count: int = 0
        self._alert_count: int = 0

        self._collection_task: Optional[asyncio.Task] = None
        self._dashboard_task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        """Start monitoring."""
        self._running = True
        self._start_time = time.time()

        # Start background collection and dashboard tasks
        self._collection_task = asyncio.create_task(self._collection_loop())
        self._dashboard_task = asyncio.create_task(self._dashboard_loop())

        logger.info("Performance monitoring started")
        return self

    async def __aexit__(self, *args):
        """Stop monitoring and export metrics."""
        self._running = False

        # Wait for tasks to complete
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        if self._dashboard_task:
            self._dashboard_task.cancel()
            try:
                await self._dashboard_task
            except asyncio.CancelledError:
                pass

        # Export metrics if path specified
        if self.export_path:
            self._export_metrics()

        # Display final summary
        self._display_dashboard()

        logger.info("Performance monitoring stopped")

    async def _collection_loop(self):
        """Background task for metric collection."""
        while self._running:
            try:
                # Collect snapshots
                self._memory_profiler.collect_snapshot()
                self._cpu_profiler.collect_snapshot()

                self._sample_count += 1

                # Count alerts
                memory_metrics = self._memory_profiler.get_metrics()
                self._alert_count = len(memory_metrics["alerts"])

                await asyncio.sleep(self.sampling_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")

    async def _dashboard_loop(self):
        """Background task for dashboard updates."""
        while self._running:
            try:
                await asyncio.sleep(self.update_interval)

                self._display_dashboard()
                self._update_count += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in dashboard loop: {e}")

    def _display_dashboard(self):
        """Display current dashboard."""
        metrics = self.get_metrics()
        dashboard = self._dashboard_renderer.render_dashboard(metrics)
        print("\n" + dashboard + "\n")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics snapshot.

        Returns:
            Complete metrics dictionary with memory, CPU, performance, and runtime
        """
        duration = time.time() - self._start_time if self._start_time > 0 else 0.0

        return {
            "memory": self._memory_profiler.get_metrics(),
            "cpu": self._cpu_profiler.get_metrics(),
            "performance": self._metrics_collector.get_metrics(),
            "runtime": {
                "duration_seconds": duration,
                "samples_collected": self._sample_count,
                "alerts_triggered": self._alert_count,
                "update_count": self._update_count,
            },
        }

    def render_dashboard(self) -> str:
        """
        Render current dashboard as string.

        Returns:
            Formatted dashboard string
        """
        metrics = self.get_metrics()
        return self._dashboard_renderer.render_dashboard(metrics)

    def _export_metrics(self):
        """Export metrics to JSON file."""
        if not self.export_path:
            return

        metrics = self.get_metrics()

        # Ensure parent directory exists
        self.export_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.export_path, "w") as f:
            json.dump(metrics, f, indent=2)

        logger.info(f"Metrics exported to {self.export_path}")


# Convenience exports
__all__ = [
    "PerformanceMonitor",
    "MemoryProfiler",
    "CPUProfiler",
    "MetricsCollector",
    "DashboardRenderer",
]

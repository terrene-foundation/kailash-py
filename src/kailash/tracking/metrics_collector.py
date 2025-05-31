"""Enhanced metrics collection for task tracking.

This module provides comprehensive performance metrics collection during node execution,
including CPU usage, memory consumption, I/O operations, and custom metrics.

Design Purpose:
- Enable real-time performance monitoring during node execution
- Integrate seamlessly with TaskManager and visualization components
- Support both synchronous and asynchronous execution contexts

Upstream Dependencies:
- Runtime engines (local.py, parallel.py, docker.py) use this to collect metrics
- TaskManager uses this to store performance data

Downstream Consumers:
- Visualization components use collected metrics for performance graphs
- Export utilities include metrics in workflow reports
"""

import asyncio
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@dataclass
class PerformanceMetrics:
    """Container for comprehensive performance metrics.

    Attributes:
        duration: Execution time in seconds
        cpu_percent: Average CPU usage percentage
        memory_mb: Peak memory usage in MB
        memory_delta_mb: Memory increase during execution
        io_read_bytes: Total bytes read during execution
        io_write_bytes: Total bytes written during execution
        io_read_count: Number of read operations
        io_write_count: Number of write operations
        thread_count: Number of threads used
        context_switches: Number of context switches
        custom: Dictionary of custom metrics
    """

    duration: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_delta_mb: float = 0.0
    io_read_bytes: int = 0
    io_write_bytes: int = 0
    io_read_count: int = 0
    io_write_count: int = 0
    thread_count: int = 1
    context_switches: int = 0
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_task_metrics(self) -> Dict[str, Any]:
        """Convert to TaskMetrics compatible format."""
        return {
            "duration": self.duration,
            "memory_usage_mb": self.memory_mb,
            "cpu_usage": self.cpu_percent,
            "custom_metrics": {
                "memory_delta_mb": self.memory_delta_mb,
                "io_read_bytes": self.io_read_bytes,
                "io_write_bytes": self.io_write_bytes,
                "io_read_count": self.io_read_count,
                "io_write_count": self.io_write_count,
                "thread_count": self.thread_count,
                "context_switches": self.context_switches,
                **self.custom,
            },
        }


class MetricsCollector:
    """Collects performance metrics during task execution.

    This class provides context managers for collecting detailed performance
    metrics during node execution, with support for both process-level and
    system-level monitoring.

    Usage::

        collector = MetricsCollector()
        with collector.collect() as metrics:
            # Execute node code here
            pass
        performance_data = metrics.result()
    """

    def __init__(self, sampling_interval: float = 0.1):
        """Initialize metrics collector.

        Args:
            sampling_interval: How often to sample metrics (seconds)
        """
        self.sampling_interval = sampling_interval
        self._monitoring_enabled = PSUTIL_AVAILABLE

        if not self._monitoring_enabled:
            import warnings

            warnings.warn(
                "psutil not available. Performance metrics will be limited to duration only. "
                "Install psutil for comprehensive metrics: pip install psutil"
            )

    @contextmanager
    def collect(self, node_id: Optional[str] = None):
        """Context manager for collecting metrics during execution.

        Args:
            node_id: Optional node identifier for tracking

        Yields:
            MetricsContext: Context object with result() method
        """
        context = MetricsContext(
            node_id=node_id,
            sampling_interval=self.sampling_interval,
            monitoring_enabled=self._monitoring_enabled,
        )

        try:
            context.start()
            yield context
        finally:
            context.stop()

    async def collect_async(self, coro, node_id: Optional[str] = None):
        """Collect metrics for async execution.

        Args:
            coro: Coroutine to execute
            node_id: Optional node identifier

        Returns:
            Tuple of (result, metrics)
        """
        context = MetricsContext(
            node_id=node_id,
            sampling_interval=self.sampling_interval,
            monitoring_enabled=self._monitoring_enabled,
        )

        try:
            context.start()
            result = await coro
            return result, context.result()
        finally:
            context.stop()


class MetricsContext:
    """Context for collecting metrics during a specific execution."""

    def __init__(
        self, node_id: Optional[str], sampling_interval: float, monitoring_enabled: bool
    ):
        self.node_id = node_id
        self.sampling_interval = sampling_interval
        self.monitoring_enabled = monitoring_enabled

        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.process: Optional[Any] = None
        self.initial_io: Optional[Any] = None
        self.initial_memory: Optional[float] = None
        self.peak_memory: float = 0.0
        self.cpu_samples: list = []
        self.monitoring_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()

    def start(self):
        """Start metrics collection."""
        self.start_time = time.time()

        if self.monitoring_enabled:
            try:
                self.process = psutil.Process()
                self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
                self.peak_memory = self.initial_memory

                # Get initial I/O counters if available
                if hasattr(self.process, "io_counters"):
                    try:
                        self.initial_io = self.process.io_counters()
                    except (psutil.AccessDenied, AttributeError):
                        self.initial_io = None

                # Start monitoring thread
                self._stop_monitoring.clear()
                self.monitoring_thread = threading.Thread(
                    target=self._monitor_resources
                )
                self.monitoring_thread.daemon = True
                self.monitoring_thread.start()

            except Exception:
                # Fallback if process monitoring fails
                self.monitoring_enabled = False

    def stop(self):
        """Stop metrics collection."""
        self.end_time = time.time()

        if self.monitoring_enabled and self.monitoring_thread:
            self._stop_monitoring.set()
            self.monitoring_thread.join(timeout=1.0)

    def _monitor_resources(self):
        """Monitor resources in background thread."""
        while not self._stop_monitoring.is_set():
            try:
                # Sample CPU usage
                cpu = self.process.cpu_percent(interval=None)
                if cpu > 0:  # Filter out initial 0 readings
                    self.cpu_samples.append(cpu)

                # Track peak memory
                memory = self.process.memory_info().rss / 1024 / 1024  # MB
                self.peak_memory = max(self.peak_memory, memory)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break

            self._stop_monitoring.wait(self.sampling_interval)

    def result(self) -> PerformanceMetrics:
        """Get collected metrics."""
        metrics = PerformanceMetrics()

        # Calculate duration
        if self.start_time and self.end_time:
            metrics.duration = self.end_time - self.start_time

        if self.monitoring_enabled and self.process:
            try:
                # CPU usage (average of samples)
                if self.cpu_samples:
                    metrics.cpu_percent = sum(self.cpu_samples) / len(self.cpu_samples)

                # Memory metrics
                metrics.memory_mb = self.peak_memory
                if self.initial_memory:
                    current_memory = self.process.memory_info().rss / 1024 / 1024
                    metrics.memory_delta_mb = current_memory - self.initial_memory

                # I/O metrics
                if self.initial_io and hasattr(self.process, "io_counters"):
                    try:
                        current_io = self.process.io_counters()
                        metrics.io_read_bytes = (
                            current_io.read_bytes - self.initial_io.read_bytes
                        )
                        metrics.io_write_bytes = (
                            current_io.write_bytes - self.initial_io.write_bytes
                        )
                        metrics.io_read_count = (
                            current_io.read_count - self.initial_io.read_count
                        )
                        metrics.io_write_count = (
                            current_io.write_count - self.initial_io.write_count
                        )
                    except (psutil.AccessDenied, AttributeError):
                        pass

                # Thread and context switch info
                try:
                    metrics.thread_count = self.process.num_threads()
                    if hasattr(self.process, "num_ctx_switches"):
                        ctx = self.process.num_ctx_switches()
                        metrics.context_switches = ctx.voluntary + ctx.involuntary
                except (psutil.AccessDenied, AttributeError):
                    pass

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return metrics

    def add_custom_metric(self, name: str, value: Any):
        """Add a custom metric."""
        if not hasattr(self, "_custom_metrics"):
            self._custom_metrics = {}
        self._custom_metrics[name] = value

    def get_custom_metrics(self) -> Dict[str, Any]:
        """Get custom metrics."""
        return getattr(self, "_custom_metrics", {})


# Global collector instance for convenience
default_collector = MetricsCollector()


def collect_metrics(func: Optional[Callable] = None, *, node_id: Optional[str] = None):
    """Decorator for collecting metrics on function execution.

    Can be used as @collect_metrics or @collect_metrics(node_id="my_node")

    Args:
        func: Function to wrap
        node_id: Optional node identifier

    Returns:
        Wrapped function that returns (result, metrics) tuple
    """

    def decorator(f):
        if asyncio.iscoroutinefunction(f):

            async def async_wrapper(*args, **kwargs):
                result, metrics = await default_collector.collect_async(
                    f(*args, **kwargs), node_id=node_id
                )
                return result, metrics

            return async_wrapper
        else:

            def sync_wrapper(*args, **kwargs):
                with default_collector.collect(node_id=node_id) as context:
                    result = f(*args, **kwargs)
                return result, context.result()

            return sync_wrapper

    if func is None:
        # Called with arguments: @collect_metrics(node_id="...")
        return decorator
    else:
        # Called without arguments: @collect_metrics
        return decorator(func)

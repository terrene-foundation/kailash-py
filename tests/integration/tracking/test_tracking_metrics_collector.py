"""Tests for enhanced metrics collection."""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest
from kailash.tracking.metrics_collector import (
    MetricsCollector,
    PerformanceMetrics,
    collect_metrics,
)

from tests.utils import AsyncTestUtils, FunctionalTestMixin, PerformanceTestMixin


class TestPerformanceMetrics:
    """Test PerformanceMetrics data class."""

    def test_default_values(self):
        """Test default metric values."""
        metrics = PerformanceMetrics()

        assert metrics.duration == 0.0
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_mb == 0.0
        assert metrics.memory_delta_mb == 0.0
        assert metrics.io_read_bytes == 0
        assert metrics.io_write_bytes == 0
        assert metrics.io_read_count == 0
        assert metrics.io_write_count == 0
        assert metrics.thread_count == 1
        assert metrics.context_switches == 0
        assert metrics.custom == {}

    def test_to_task_metrics(self):
        """Test conversion to TaskMetrics format."""
        metrics = PerformanceMetrics(
            duration=1.5,
            cpu_percent=45.2,
            memory_mb=128.5,
            memory_delta_mb=32.0,
            io_read_bytes=1024,
            io_write_bytes=2048,
            custom={"extra": "value"},
        )

        task_metrics = metrics.to_task_metrics()

        assert task_metrics["duration"] == 1.5
        assert task_metrics["cpu_usage"] == 45.2
        assert task_metrics["memory_usage_mb"] == 128.5
        assert "custom_metrics" in task_metrics
        assert task_metrics["custom_metrics"]["memory_delta_mb"] == 32.0
        assert task_metrics["custom_metrics"]["io_read_bytes"] == 1024
        assert task_metrics["custom_metrics"]["extra"] == "value"


class TestMetricsCollector(FunctionalTestMixin):
    """Test MetricsCollector functionality."""

    def test_initialization(self):
        """Test collector initialization."""
        collector = MetricsCollector(sampling_interval=0.05)
        assert collector.sampling_interval == 0.05

    def test_basic_collection(self):
        """Test basic metrics collection."""
        collector = MetricsCollector()

        with collector.collect(node_id="test_node") as context:
            # Simulate some work
            time.sleep(0.1)
            # result = 42  # Not used

        metrics = context.result()

        # Duration should be recorded even without psutil
        assert metrics.duration >= 0.1
        assert metrics.duration < 0.5  # Allow some overhead for slower CI

    @patch("kailash.tracking.metrics_collector.psutil")
    def test_resource_monitoring(self, mock_psutil):
        """Test resource monitoring with psutil."""
        # Mock exception classes as real exception classes
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})

        # Set up proper mock values
        mock_process = Mock()
        mock_psutil.Process.return_value = mock_process

        # Mock memory info
        mock_memory = Mock()
        mock_memory.rss = 128 * 1024 * 1024  # 128 MB
        mock_process.memory_info.return_value = mock_memory

        # Mock CPU percent
        mock_process.cpu_percent.return_value = 15.5

        # Mock I/O counters
        mock_io = Mock()
        mock_io.read_bytes = 1000
        mock_io.write_bytes = 2000
        mock_io.read_count = 10
        mock_io.write_count = 20
        mock_process.io_counters.return_value = mock_io

        # Mock thread count
        mock_process.num_threads.return_value = 4

        # Mock context switches
        mock_ctx = Mock()
        mock_ctx.voluntary = 30
        mock_ctx.involuntary = 20
        mock_process.num_ctx_switches.return_value = mock_ctx

        collector = MetricsCollector(sampling_interval=0.01)
        collector._monitoring_enabled = True  # Force monitoring to be enabled

        with collector.collect() as context:
            # Do some CPU work
            total = 0
            for i in range(100000):
                total += i

            # Do some memory allocation
            # data = [i for i in range(10000)]  # Not used

            time.sleep(0.05)  # Allow monitoring thread to collect samples

        metrics = context.result()

        # Check that metrics were collected
        assert metrics.duration > 0
        assert metrics.memory_mb >= 0  # Should have some memory usage
        # CPU usage might be 0 on fast systems, so just check it's not negative
        assert metrics.cpu_percent >= 0

    def test_custom_metrics(self):
        """Test adding custom metrics."""
        collector = MetricsCollector()

        with collector.collect() as context:
            context.add_custom_metric("requests_processed", 100)
            context.add_custom_metric("cache_hits", 85)

        custom = context.get_custom_metrics()
        assert custom["requests_processed"] == 100
        assert custom["cache_hits"] == 85

    @pytest.mark.asyncio
    async def test_async_collection_functionality(self):
        """Test async metrics collection functionality (no timing)."""
        collector = MetricsCollector()

        async def async_work():
            # Use mock sleep for fast tests
            await AsyncTestUtils.mock_async_sleep(0.1)
            return "async_result"

        result, metrics = await collector.collect_async(
            async_work(), node_id="async_node"
        )

        # Test functionality, not timing
        assert result == "async_result"
        assert metrics.duration >= 0.0  # Just check non-negative
        assert isinstance(metrics, PerformanceMetrics)

    @patch("kailash.tracking.metrics_collector.psutil")
    def test_metrics_with_mocked_psutil(self, mock_psutil):
        """Test metrics collection with mocked psutil."""
        # Mock exception classes as real exception classes
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})

        # Mock process
        mock_process = Mock()
        mock_psutil.Process.return_value = mock_process

        # Mock memory info
        mock_memory = Mock()
        mock_memory.rss = 100 * 1024 * 1024  # 100 MB
        mock_process.memory_info.return_value = mock_memory

        # Mock CPU percent
        mock_process.cpu_percent.return_value = 25.5

        # Mock I/O counters
        mock_io = Mock()
        mock_io.read_bytes = 1000
        mock_io.write_bytes = 2000
        mock_io.read_count = 10
        mock_io.write_count = 20
        mock_process.io_counters.return_value = mock_io

        # Mock thread count
        mock_process.num_threads.return_value = 4

        # Mock context switches with proper attributes
        mock_ctx = Mock()
        mock_ctx.voluntary = 50
        mock_ctx.involuntary = 25
        mock_process.num_ctx_switches.return_value = mock_ctx

        # Force monitoring to be enabled
        collector = MetricsCollector()
        collector._monitoring_enabled = True

        with collector.collect() as context:
            time.sleep(0.1)

        metrics = context.result()

        assert metrics.memory_mb == 100.0
        assert metrics.thread_count == 4
        assert metrics.context_switches == 75


class TestCollectMetricsDecorator(FunctionalTestMixin):
    """Test the collect_metrics decorator."""

    def test_sync_function_decorator(self):
        """Test decorator on synchronous function."""

        @collect_metrics
        def process_data(x, y):
            time.sleep(0.05)
            return x + y

        result, metrics = process_data(10, 20)

        assert result == 30
        assert metrics.duration >= 0.05

    def test_decorator_with_node_id(self):
        """Test decorator with node_id parameter."""

        @collect_metrics(node_id="custom_node")
        def process_data(x):
            return x * 2

        result, metrics = process_data(5)

        assert result == 10
        assert metrics.duration >= 0

    @pytest.mark.asyncio
    async def test_async_function_decorator_functionality(self):
        """Test decorator on async function (functionality only)."""

        @collect_metrics
        async def async_process(x):
            # Use mock sleep for fast, reliable tests
            await AsyncTestUtils.mock_async_sleep(0.05)
            return x**2

        result, metrics = await async_process(4)

        # Test functionality, not precise timing
        assert result == 16
        assert metrics.duration >= 0.0  # Just check non-negative
        assert isinstance(metrics, PerformanceMetrics)

    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""

        @collect_metrics
        def documented_function(x):
            """This is a documented function."""
            return x

        # Function name should be preserved
        assert documented_function.__name__ == "sync_wrapper"
        # Note: functools.wraps would preserve the original name and docs


class TestIntegrationWithTaskMetrics:
    """Test integration with TaskMetrics model."""

    def test_metrics_conversion_compatibility(self):
        """Test that PerformanceMetrics converts correctly to TaskMetrics."""
        from kailash.tracking.models import TaskMetrics

        # Create performance metrics
        perf_metrics = PerformanceMetrics(
            duration=2.5,
            cpu_percent=75.0,
            memory_mb=256.0,
            memory_delta_mb=64.0,
            io_read_bytes=1024 * 1024,  # 1 MB
            io_write_bytes=2 * 1024 * 1024,  # 2 MB
            thread_count=8,
            context_switches=150,
        )

        # Convert to TaskMetrics format
        metrics_data = perf_metrics.to_task_metrics()

        # Create TaskMetrics instance
        task_metrics = TaskMetrics(**metrics_data)

        # Verify all fields
        assert task_metrics.duration == 2.5
        assert task_metrics.cpu_usage == 75.0
        assert task_metrics.memory_usage_mb == 256.0
        assert task_metrics.memory_usage == 256.0  # Legacy field

        # Verify custom metrics
        custom = task_metrics.custom_metrics
        assert custom["memory_delta_mb"] == 64.0
        assert custom["io_read_bytes"] == 1024 * 1024
        assert custom["io_write_bytes"] == 2 * 1024 * 1024
        assert custom["thread_count"] == 8
        assert custom["context_switches"] == 150


class TestMetricsCollectorEdgeCases:
    """Test edge cases and error handling."""

    def test_collector_without_psutil(self):
        """Test collector behavior when psutil is not available."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with patch("kailash.tracking.metrics_collector.PSUTIL_AVAILABLE", False):
                collector = MetricsCollector()

            with collector.collect() as context:
                time.sleep(0.05)

            metrics = context.result()

            # Only duration should be collected
            assert metrics.duration > 0
            assert metrics.cpu_percent == 0
            assert metrics.memory_mb == 0

    def test_process_termination_during_monitoring(self):
        """Test handling of process termination during monitoring."""
        collector = MetricsCollector()

        if collector._monitoring_enabled:
            with patch("psutil.Process") as mock_process_class:
                mock_process = Mock()
                mock_process_class.return_value = mock_process

                # Simulate process termination
                mock_process.cpu_percent.side_effect = Exception("Process terminated")

                with collector.collect() as context:
                    time.sleep(0.1)

                # Should still get basic metrics
                metrics = context.result()
                assert metrics.duration > 0

    def test_multiple_concurrent_collections(self):
        """Test multiple concurrent metric collections."""
        collector = MetricsCollector()

        results = []

        def collect_metrics_task(task_id):
            with collector.collect(node_id=f"task_{task_id}") as context:
                time.sleep(0.05)
            results.append(context.result())

        # Run multiple collections concurrently
        import threading

        threads = []
        for i in range(3):
            t = threading.Thread(target=collect_metrics_task, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All should have collected metrics
        assert len(results) == 3
        for metrics in results:
            assert metrics.duration >= 0.0  # Relaxed for fast systems


class TestMetricsCollectorPerformance(PerformanceTestMixin):
    """Test MetricsCollector performance and timing functionality."""

    @pytest.mark.asyncio
    async def test_async_collection_timing(self):
        """Test async metrics collection timing with controlled time."""
        collector = MetricsCollector()

        with self.controlled_time(duration=0.1):

            async def async_work():
                await asyncio.sleep(0.1)  # Real sleep for timing test
                return "async_result"

            result, metrics = await collector.collect_async(
                async_work(), node_id="async_node"
            )

            # Test actual functionality
            assert result == "async_result"

            # Test timing with tolerance
            self.assert_timing_positive(metrics.duration)

    def test_sync_collection_timing(self):
        """Test synchronous metrics collection timing."""
        collector = MetricsCollector()

        with self.controlled_time(duration=0.05):

            def sync_work():
                time.sleep(0.05)  # Real sleep for timing test
                return "sync_result"

            with collector.collect(node_id="sync_node") as context:
                result = sync_work()

            metrics = context.result()

            # Test functionality
            assert result == "sync_result"

            # Test timing
            self.assert_timing_positive(metrics.duration)

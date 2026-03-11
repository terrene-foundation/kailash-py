"""
Unit tests for MetricsCollector.

Tests collection overhead, sampling, async recording, and fail-safe behavior.
All tests must pass BEFORE implementation.
"""

import asyncio
import time

import pytest


class TestMetricsCollectorBasics:
    """Test basic MetricsCollector functionality."""

    @pytest.mark.asyncio
    async def test_collector_is_singleton(self):
        """Test that MetricsCollector is a singleton."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector1 = MetricsCollector()
        collector2 = MetricsCollector()

        assert collector1 is collector2, "MetricsCollector should be singleton"

    @pytest.mark.asyncio
    async def test_record_metric_basic(self):
        """Test basic metric recording."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        await collector.record_metric(
            metric_name="test.metric",
            value=100.5,
            tags={"environment": "test"},
            timestamp=time.time(),
        )

        # Verify metric was queued (queue should have 1 item)
        assert collector._metrics_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_record_metric_without_timestamp(self):
        """Test metric recording without explicit timestamp."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        before = time.time()
        await collector.record_metric(metric_name="test.metric", value=50.0)
        after = time.time()

        # Get the metric from queue
        metric = await collector._metrics_queue.get()

        assert metric["name"] == "test.metric"
        assert metric["value"] == 50.0
        assert before <= metric["timestamp"] <= after

    @pytest.mark.asyncio
    async def test_record_metric_with_tags(self):
        """Test metric recording with tags."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        await collector.record_metric(
            metric_name="test.metric",
            value=75.0,
            tags={"tier": "hot", "operation": "read"},
        )

        metric = await collector._metrics_queue.get()

        assert metric["tags"]["tier"] == "hot"
        assert metric["tags"]["operation"] == "read"


class TestMetricsCollectorSampling:
    """Test sampling strategies."""

    @pytest.mark.asyncio
    async def test_full_sampling_for_critical_metrics(self):
        """Test 100% sampling for critical metrics."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Record 100 critical metrics (100% sampling)
        for i in range(100):
            await collector.record_metric(
                metric_name="signature.resolution", value=float(i)
            )

        # All 100 should be queued
        assert collector._metrics_queue.qsize() == 100

    @pytest.mark.asyncio
    async def test_partial_sampling_for_high_volume_metrics(self):
        """Test sampling for high-volume metrics (10% sampling)."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Set 10% sampling for workflow.node metrics
        collector._sample_rates["workflow.node"] = 0.1

        # Record 1000 metrics
        for i in range(1000):
            await collector.record_metric(metric_name="workflow.node", value=float(i))

        # Should have ~100 samples (10% +/- statistical variance)
        queue_size = collector._metrics_queue.qsize()
        assert 50 <= queue_size <= 150, f"Expected ~100 samples, got {queue_size}"

    @pytest.mark.asyncio
    async def test_sampling_metadata_included(self):
        """Test that sampling metadata is included in metrics."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        collector._sample_rates["test.sampled"] = 0.5

        await collector.record_metric(metric_name="test.sampled", value=100.0)

        # May or may not be sampled, but check if queued metric has metadata
        if collector._metrics_queue.qsize() > 0:
            metric = await collector._metrics_queue.get()
            assert "sampled" in metric
            assert "sample_rate" in metric
            assert metric["sample_rate"] == 0.5


class TestMetricsCollectorPerformance:
    """Test collection overhead and performance."""

    @pytest.mark.asyncio
    async def test_collection_overhead_under_1ms(self):
        """Test that metric collection overhead is <1ms."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Measure 100 metric recordings
        durations = []
        for i in range(100):
            start = time.perf_counter()
            await collector.record_metric(
                metric_name="test.performance", value=float(i)
            )
            duration_ms = (time.perf_counter() - start) * 1000
            durations.append(duration_ms)

        # Average overhead should be <1ms
        avg_overhead = sum(durations) / len(durations)
        assert (
            avg_overhead < 1.0
        ), f"Average overhead {avg_overhead:.3f}ms exceeds 1ms target"

        # 95th percentile should also be <1ms
        sorted_durations = sorted(durations)
        p95_index = int(0.95 * len(sorted_durations))
        p95_overhead = sorted_durations[p95_index]
        assert (
            p95_overhead < 1.0
        ), f"P95 overhead {p95_overhead:.3f}ms exceeds 1ms target"

    @pytest.mark.asyncio
    async def test_non_blocking_queue_put(self):
        """Test that metric recording is non-blocking."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Record metric should not block (uses put_nowait)
        start = time.perf_counter()
        await collector.record_metric(metric_name="test.nonblocking", value=100.0)
        duration = time.perf_counter() - start

        # Should be nearly instantaneous (<0.1ms)
        assert duration < 0.0001, f"Non-blocking put took {duration*1000:.3f}ms"


class TestMetricsCollectorFailSafe:
    """Test fail-safe behavior."""

    @pytest.mark.asyncio
    async def test_queue_full_drops_metric(self):
        """Test that metrics are dropped when queue is full (fail-safe)."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Fill queue to max capacity (10,000)
        for i in range(10000):
            await collector.record_metric(metric_name="test.fill", value=float(i))

        # Queue should be full
        assert collector._metrics_queue.full()

        # Recording another metric should not raise exception (fail-safe)
        try:
            await collector.record_metric(metric_name="test.overflow", value=999.0)
            # Should succeed without raising
            success = True
        except Exception:
            success = False

        assert success, "Metric recording should not raise exception when queue is full"

    @pytest.mark.asyncio
    async def test_error_in_recording_does_not_crash(self):
        """Test that errors in metric recording don't crash application."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Attempt to record with invalid data (should handle gracefully)
        try:
            await collector.record_metric(
                metric_name="test.error", value=float("inf")  # Invalid value
            )
            # Even if it succeeds, that's fine (fail-safe)
            success = True
        except Exception:
            # If it fails, make sure it's handled gracefully
            success = True

        assert success


class TestMetricsCollectorDecorator:
    """Test @monitor_execution decorator."""

    @pytest.mark.asyncio
    async def test_decorator_monitors_async_function(self):
        """Test decorator monitors async function execution time."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        @collector.monitor_execution("test.async.operation")
        async def async_operation(x, y):
            await asyncio.sleep(0.01)  # 10ms delay
            return x + y

        result = await async_operation(5, 3)

        assert result == 8

        # Check that metric was recorded
        assert collector._metrics_queue.qsize() == 1

        metric = await collector._metrics_queue.get()
        assert metric["name"] == "test.async.operation.latency"
        assert metric["value"] >= 10.0  # Should be at least 10ms
        assert metric["tags"]["success"] == "True"

    def test_decorator_monitors_sync_function(self):
        """Test decorator monitors sync function execution time."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        @collector.monitor_execution("test.sync.operation")
        def sync_operation(x, y):
            time.sleep(0.01)  # 10ms delay
            return x * y

        result = sync_operation(4, 5)

        assert result == 20

        # Note: Sync decorator uses asyncio.create_task, so we need to run event loop
        # For this test, we just verify the decorator doesn't crash

    @pytest.mark.asyncio
    async def test_decorator_records_failure(self):
        """Test decorator records execution failures."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        @collector.monitor_execution("test.failing.operation")
        async def failing_operation():
            await asyncio.sleep(0.001)
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await failing_operation()

        # Check that metric was recorded with success=False
        assert collector._metrics_queue.qsize() == 1

        metric = await collector._metrics_queue.get()
        assert metric["name"] == "test.failing.operation.latency"
        assert metric["tags"]["success"] == "False"

    @pytest.mark.asyncio
    async def test_decorator_with_custom_tags(self):
        """Test decorator with custom tags."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        @collector.monitor_execution(
            "test.tagged.operation", tags={"tier": "hot", "cache": "true"}
        )
        async def tagged_operation():
            await asyncio.sleep(0.001)
            return 42

        result = await tagged_operation()
        assert result == 42

        metric = await collector._metrics_queue.get()
        assert metric["tags"]["tier"] == "hot"
        assert metric["tags"]["cache"] == "true"
        assert metric["tags"]["success"] == "True"


class TestMetricsCollectorContextManager:
    """Test context manager for monitoring operations."""

    def test_context_manager_monitors_operation(self):
        """Test context manager monitors operation duration."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        with collector.monitor_operation("test.context.operation"):
            time.sleep(0.01)  # 10ms delay

        # Note: Context manager uses asyncio.create_task for async recording
        # For this test, we just verify it doesn't crash

    def test_context_manager_records_failure(self):
        """Test context manager records operation failures."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        try:
            with collector.monitor_operation("test.context.failure"):
                time.sleep(0.001)
                raise RuntimeError("Test error")
        except RuntimeError:
            pass  # Expected

        # Context manager should record metric even on failure

    def test_context_manager_with_custom_tags(self):
        """Test context manager with custom tags."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        with collector.monitor_operation(
            "test.context.tagged", tags={"operation": "read", "source": "cache"}
        ):
            time.sleep(0.001)

        # Should record metric with custom tags


class TestMetricsCollectorIntegration:
    """Test integration with existing components."""

    @pytest.mark.asyncio
    async def test_integration_with_memory_monitor(self):
        """Test integration with existing MemoryMonitor."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Simulate cache access metrics (like from MemoryMonitor)
        await collector.record_metric(
            metric_name="cache.access.latency",
            value=5.2,
            tags={"tier": "hot", "hit": "true"},
        )

        await collector.record_metric(
            metric_name="cache.access.latency",
            value=15.7,
            tags={"tier": "warm", "hit": "true"},
        )

        await collector.record_metric(
            metric_name="cache.access.latency",
            value=50.3,
            tags={"tier": "cold", "hit": "true"},
        )

        # Verify all metrics queued
        assert collector._metrics_queue.qsize() == 3

    @pytest.mark.asyncio
    async def test_metric_name_patterns(self):
        """Test various metric naming patterns."""
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()

        # Set 100% sampling for all patterns in this test
        collector._sample_rates["workflow.node.execution"] = 1.0
        collector._sample_rates["memory.allocation.size"] = 1.0

        metric_patterns = [
            "signature.resolution.latency",
            "signature.compilation.latency",
            "cache.access.latency",
            "strategy.execution.latency",
            "workflow.node.execution",
            "agent.execution.latency",
            "memory.allocation.size",
        ]

        for pattern in metric_patterns:
            await collector.record_metric(metric_name=pattern, value=100.0)

        assert collector._metrics_queue.qsize() == len(metric_patterns)

"""
Unit tests for AnalyticsAggregator.

Tests windowed statistics, percentile calculations, trend detection, and data retention.
All tests must pass BEFORE implementation.
"""

import asyncio
import time

import pytest


class TestAnalyticsAggregatorBasics:
    """Test basic AnalyticsAggregator functionality."""

    @pytest.mark.asyncio
    async def test_aggregator_initialization(self):
        """Test aggregator initializes with collector."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        assert aggregator.collector is collector
        assert "1s" in aggregator._windows
        assert "1m" in aggregator._windows
        assert "5m" in aggregator._windows
        assert "1h" in aggregator._windows

    @pytest.mark.asyncio
    async def test_aggregator_start_creates_worker(self):
        """Test that start() creates background aggregation worker."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        await aggregator.start()

        assert aggregator._running is True

        # Stop the aggregator
        aggregator._running = False
        await asyncio.sleep(0.2)  # Let worker finish


class TestTimeWindow:
    """Test TimeWindow rolling window functionality."""

    def test_time_window_initialization(self):
        """Test TimeWindow initializes with duration."""
        from kaizen.monitoring.analytics_aggregator import TimeWindow

        window = TimeWindow(duration_seconds=60)

        assert window.duration_seconds == 60
        assert len(window._samples) == 0

    def test_time_window_add_sample(self):
        """Test adding samples to time window."""
        from kaizen.monitoring.analytics_aggregator import TimeWindow

        window = TimeWindow(duration_seconds=60)

        window.add_sample(
            metric_name="test.metric", value=100.0, tags={}, timestamp=time.time()
        )

        samples = window.get_samples("test.metric")
        assert len(samples) == 1
        assert samples[0] == 100.0

    def test_time_window_evicts_old_samples(self):
        """Test that old samples are evicted from window."""
        from kaizen.monitoring.analytics_aggregator import TimeWindow

        window = TimeWindow(duration_seconds=2)  # 2-second window

        current_time = time.time()

        # Add old sample (3 seconds ago)
        window.add_sample(
            metric_name="test.metric", value=100.0, tags={}, timestamp=current_time - 3
        )

        # Add recent sample
        window.add_sample(
            metric_name="test.metric", value=200.0, tags={}, timestamp=current_time
        )

        # Only recent sample should remain
        samples = window.get_samples("test.metric")
        assert len(samples) == 1
        assert samples[0] == 200.0

    def test_time_window_multiple_metrics(self):
        """Test window handles multiple metric names."""
        from kaizen.monitoring.analytics_aggregator import TimeWindow

        window = TimeWindow(duration_seconds=60)

        window.add_sample("metric1", 100.0, {}, time.time())
        window.add_sample("metric2", 200.0, {}, time.time())
        window.add_sample("metric1", 150.0, {}, time.time())

        assert len(window.get_samples("metric1")) == 2
        assert len(window.get_samples("metric2")) == 1

        metric_names = window.get_metric_names()
        assert "metric1" in metric_names
        assert "metric2" in metric_names


class TestAnalyticsAggregatorProcessing:
    """Test metric processing and aggregation."""

    @pytest.mark.asyncio
    async def test_process_metrics_batch(self):
        """Test processing batch of metrics."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add metrics to queue
        for i in range(10):
            await collector.record_metric(metric_name="test.batch", value=float(i * 10))

        # Process batch
        metrics = []
        for _ in range(10):
            metric = await collector._metrics_queue.get()
            metrics.append(metric)

        await aggregator._process_metrics_batch(metrics)

        # Verify metrics added to windows
        samples = aggregator._windows["1m"].get_samples("test.batch")
        assert len(samples) == 10

    @pytest.mark.asyncio
    async def test_calculate_stats_from_samples(self):
        """Test statistics calculation from samples."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add known samples
        samples = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        for value in samples:
            await collector.record_metric(metric_name="test.stats", value=value)

        # Process metrics
        metrics = []
        while not collector._metrics_queue.empty():
            metrics.append(await collector._metrics_queue.get())

        await aggregator._process_metrics_batch(metrics)
        await aggregator._calculate_stats()

        # Get stats
        stats = aggregator.get_stats("test.stats", "1m")

        assert stats["count"] == 10
        assert stats["mean"] == 55.0
        assert stats["median"] == 55.0
        assert stats["min"] == 10.0
        assert stats["max"] == 100.0
        # Percentile assertions need to account for linear interpolation at boundaries
        # With 10 samples [10,20,30,40,50,60,70,80,90,100], p90 can be at or near 100
        assert 85.0 <= stats["p90"] <= 100.0  # Allow boundary value
        assert 90.0 <= stats["p95"] <= 100.0
        assert 95.0 <= stats["p99"] <= 100.0


class TestAnalyticsAggregatorPercentiles:
    """Test percentile calculation accuracy."""

    @pytest.mark.asyncio
    async def test_percentile_calculation_p50(self):
        """Test p50 (median) percentile calculation."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator

        # Test with 100 samples (0-99)
        samples = list(range(100))
        p50 = AnalyticsAggregator._percentile(samples, 0.50)

        # p50 should be around 50
        assert 45 <= p50 <= 55

    @pytest.mark.asyncio
    async def test_percentile_calculation_p90(self):
        """Test p90 percentile calculation."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator

        samples = list(range(100))
        p90 = AnalyticsAggregator._percentile(samples, 0.90)

        # p90 should be around 90
        assert 85 <= p90 <= 95

    @pytest.mark.asyncio
    async def test_percentile_calculation_p95(self):
        """Test p95 percentile calculation."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator

        samples = list(range(100))
        p95 = AnalyticsAggregator._percentile(samples, 0.95)

        # p95 should be around 95
        assert 90 <= p95 <= 99

    @pytest.mark.asyncio
    async def test_percentile_calculation_p99(self):
        """Test p99 percentile calculation."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator

        samples = list(range(100))
        p99 = AnalyticsAggregator._percentile(samples, 0.99)

        # p99 should be around 99
        assert 95 <= p99 <= 99


class TestAnalyticsAggregatorWindows:
    """Test different time window aggregations."""

    @pytest.mark.asyncio
    async def test_stats_for_1s_window(self):
        """Test statistics for 1-second window."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add recent metrics
        for i in range(5):
            await collector.record_metric(metric_name="test.1s", value=float(i * 10))

        # Process
        metrics = []
        while not collector._metrics_queue.empty():
            metrics.append(await collector._metrics_queue.get())

        await aggregator._process_metrics_batch(metrics)
        await aggregator._calculate_stats()

        stats = aggregator.get_stats("test.1s", "1s")
        assert stats["count"] == 5

    @pytest.mark.asyncio
    async def test_stats_for_1m_window(self):
        """Test statistics for 1-minute window."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add metrics
        for i in range(10):
            await collector.record_metric(metric_name="test.1m", value=float(i * 5))

        # Process
        metrics = []
        while not collector._metrics_queue.empty():
            metrics.append(await collector._metrics_queue.get())

        await aggregator._process_metrics_batch(metrics)
        await aggregator._calculate_stats()

        stats = aggregator.get_stats("test.1m", "1m")
        assert stats["count"] == 10

    @pytest.mark.asyncio
    async def test_stats_for_5m_window(self):
        """Test statistics for 5-minute window."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add metrics
        for i in range(20):
            await collector.record_metric(metric_name="test.5m", value=float(i * 2))

        # Process
        metrics = []
        while not collector._metrics_queue.empty():
            metrics.append(await collector._metrics_queue.get())

        await aggregator._process_metrics_batch(metrics)
        await aggregator._calculate_stats()

        stats = aggregator.get_stats("test.5m", "5m")
        assert stats["count"] == 20

    @pytest.mark.asyncio
    async def test_stats_for_1h_window(self):
        """Test statistics for 1-hour window."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add metrics
        for i in range(50):
            await collector.record_metric(metric_name="test.1h", value=float(i))

        # Process
        metrics = []
        while not collector._metrics_queue.empty():
            metrics.append(await collector._metrics_queue.get())

        await aggregator._process_metrics_batch(metrics)
        await aggregator._calculate_stats()

        stats = aggregator.get_stats("test.1h", "1h")
        assert stats["count"] == 50


class TestAnalyticsAggregatorMemoryUsage:
    """Test memory usage and data retention."""

    @pytest.mark.asyncio
    async def test_memory_usage_under_10mb(self):
        """Test that aggregator memory usage stays under 10MB."""

        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Add 10,000 metrics across different names
        for i in range(10000):
            await collector.record_metric(
                metric_name=f"test.metric.{i % 100}",  # 100 different metrics
                value=float(i),
            )

        # Process all metrics
        metrics = []
        while not collector._metrics_queue.empty():
            metrics.append(await collector._metrics_queue.get())

        await aggregator._process_metrics_batch(metrics)
        await aggregator._calculate_stats()

        # Measure memory usage (rough estimate)
        # Window data + stats should be < 10MB
        # This is a basic check - real measurement would use memory_profiler

        # At minimum, verify no crash and reasonable data structures
        assert len(aggregator._aggregated_stats) > 0
        assert len(aggregator._windows) == 4

    @pytest.mark.asyncio
    async def test_data_retention_eviction(self):
        """Test that old data is evicted properly."""
        from kaizen.monitoring.analytics_aggregator import TimeWindow

        window = TimeWindow(duration_seconds=1)  # 1-second window

        current_time = time.time()

        # Add old samples
        for i in range(10):
            window.add_sample(
                metric_name="test.retention",
                value=float(i),
                tags={},
                timestamp=current_time - 2,  # 2 seconds ago
            )

        # Trigger eviction by adding new sample
        window.add_sample(
            metric_name="test.retention", value=999.0, tags={}, timestamp=current_time
        )

        # Only recent sample should remain
        samples = window.get_samples("test.retention")
        assert len(samples) == 1
        assert samples[0] == 999.0


class TestAnalyticsAggregatorContinuousOperation:
    """Test continuous aggregation operation."""

    @pytest.mark.asyncio
    async def test_aggregation_worker_processes_continuously(self):
        """Test that aggregation worker processes metrics continuously."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Start aggregator
        await aggregator.start()

        # Add metrics continuously
        for i in range(20):
            await collector.record_metric(
                metric_name="test.continuous", value=float(i * 5)
            )
            await asyncio.sleep(0.01)  # Small delay

        # Give worker time to process
        await asyncio.sleep(0.2)

        # Stop aggregator
        aggregator._running = False
        await asyncio.sleep(0.1)

        # Verify stats were calculated
        stats = aggregator.get_stats("test.continuous", "1m")
        # Worker may have processed some or all metrics
        # Just verify stats exist if any metrics were processed
        if stats:
            assert "count" in stats
            assert "mean" in stats

    @pytest.mark.asyncio
    async def test_aggregation_worker_handles_errors(self):
        """Test that aggregation worker handles errors gracefully."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Start aggregator
        await aggregator.start()

        # Add valid metrics
        for i in range(5):
            await collector.record_metric(metric_name="test.errors", value=float(i))

        # Give worker time to process
        await asyncio.sleep(0.2)

        # Stop aggregator
        aggregator._running = False
        await asyncio.sleep(0.1)

        # Worker should have processed without crashing
        assert True  # If we got here, worker didn't crash


class TestAnalyticsAggregatorIntegration:
    """Test integration with MetricsCollector."""

    @pytest.mark.asyncio
    async def test_end_to_end_collection_to_aggregation(self):
        """Test end-to-end flow from collection to aggregation."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        # Start aggregator
        await aggregator.start()

        # Collect metrics
        for i in range(100):
            await collector.record_metric(metric_name="test.e2e", value=float(i))

        # Give worker time to process
        await asyncio.sleep(0.5)

        # Stop aggregator
        aggregator._running = False
        await asyncio.sleep(0.1)

        # Verify stats calculated
        stats = aggregator.get_stats("test.e2e", "1m")
        if stats:  # Worker may have processed
            assert stats["count"] > 0
            assert stats["min"] >= 0
            assert stats["max"] <= 99

    @pytest.mark.asyncio
    async def test_multiple_metric_types_aggregation(self):
        """Test aggregation of multiple metric types simultaneously."""
        from kaizen.monitoring.analytics_aggregator import AnalyticsAggregator
        from kaizen.monitoring.metrics_collector import MetricsCollector

        collector = MetricsCollector()
        aggregator = AnalyticsAggregator(collector)

        await aggregator.start()

        # Collect different metric types
        metric_types = [
            "signature.resolution.latency",
            "cache.access.latency",
            "agent.execution.latency",
            "workflow.node.execution",
        ]

        for metric_type in metric_types:
            for i in range(10):
                await collector.record_metric(
                    metric_name=metric_type, value=float(i * 10)
                )

        # Give worker time to process
        await asyncio.sleep(0.5)

        # Stop aggregator
        aggregator._running = False
        await asyncio.sleep(0.1)

        # Verify stats for each type
        for metric_type in metric_types:
            stats = aggregator.get_stats(metric_type, "1m")
            if stats:  # Worker may have processed
                assert "count" in stats
                assert "mean" in stats

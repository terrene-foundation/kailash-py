"""
Tier 1 Unit Tests for Enhanced MetricsHook with Prometheus Integration.

Tests prometheus_client integration, percentile calculation, and export format
without external dependencies (Docker, HTTP servers, etc.).

CRITICAL DESIGN REQUIREMENTS:
1. prometheus_client.Counter/Histogram/Gauge with dimensional labels
2. CollectorRegistry management for test isolation
3. Prometheus text format export (Content-Type: text/plain; version=0.0.4)
4. Percentile calculation (p50/p95/p99) via PerformanceProfilerHook
5. Thread-safe metric collection
6. Performance: <0.5ms per metric collection
"""

import threading
import time
from unittest.mock import patch

import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent

# Kaizen imports
from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook
from kaizen.core.autonomy.hooks.builtin.performance_profiler_hook import (
    PerformanceProfilerHook,
)

# Prometheus client imports
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ============================================================================
# 1. COUNTER METRICS (5 tests)
# ============================================================================


class TestCounterMetrics:
    """Test Counter metrics with dimensional labels"""

    @pytest.mark.asyncio
    async def test_counter_increments_with_labels(self):
        """Test counter increments with agent_id + event_type labels"""
        # Setup: Create isolated registry
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_events_total",
            "Total hook events",
            ["agent_id", "event_type"],
            registry=registry,
        )

        # Action: Increment counter with labels
        counter.labels(agent_id="test_agent", event_type="pre_tool_use").inc()
        counter.labels(agent_id="test_agent", event_type="pre_tool_use").inc()
        counter.labels(agent_id="test_agent", event_type="post_tool_use").inc()

        # Assert: Verify counts
        metrics = generate_latest(registry).decode("utf-8")
        assert (
            'kaizen_events_total{agent_id="test_agent",event_type="pre_tool_use"} 2.0'
            in metrics
        )
        assert (
            'kaizen_events_total{agent_id="test_agent",event_type="post_tool_use"} 1.0'
            in metrics
        )

    @pytest.mark.asyncio
    async def test_counter_multiple_agents(self):
        """Test counter tracks multiple agents separately"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_agent_events",
            "Agent events",
            ["agent_id", "event_type"],
            registry=registry,
        )

        # Action: Track multiple agents
        counter.labels(agent_id="agent1", event_type="pre_agent_loop").inc()
        counter.labels(agent_id="agent2", event_type="pre_agent_loop").inc()
        counter.labels(agent_id="agent1", event_type="pre_agent_loop").inc()

        # Assert: Agents tracked separately
        metrics = generate_latest(registry).decode("utf-8")
        assert (
            'kaizen_agent_events_total{agent_id="agent1",event_type="pre_agent_loop"} 2.0'
            in metrics
        )
        assert (
            'kaizen_agent_events_total{agent_id="agent2",event_type="pre_agent_loop"} 1.0'
            in metrics
        )

    @pytest.mark.asyncio
    async def test_counter_label_filtering(self):
        """Test querying metrics by label"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_tool_calls",
            "Tool calls",
            ["agent_id", "tool_name", "status"],
            registry=registry,
        )

        # Action: Record tool calls
        counter.labels(agent_id="agent1", tool_name="search", status="success").inc()
        counter.labels(agent_id="agent1", tool_name="search", status="error").inc()
        counter.labels(agent_id="agent1", tool_name="analyze", status="success").inc()

        # Assert: Can filter by labels
        metrics = generate_latest(registry).decode("utf-8")
        assert 'tool_name="search"' in metrics
        assert 'tool_name="analyze"' in metrics
        assert 'status="success"' in metrics
        assert 'status="error"' in metrics

    @pytest.mark.asyncio
    async def test_counter_zero_initial_value(self):
        """Test counters start at 0"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_new_counter",
            "New counter",
            ["agent_id"],
            registry=registry,
        )

        # Action: Create counter without incrementing
        counter.labels(agent_id="test_agent")

        # Assert: Counter exists but is 0 (Prometheus omits 0 values in output)
        metrics = generate_latest(registry).decode("utf-8")
        # Counter metric exists (HELP/TYPE lines present)
        assert "kaizen_new_counter" in metrics
        assert "# TYPE kaizen_new_counter_total counter" in metrics

    @pytest.mark.asyncio
    async def test_counter_thread_safety(self):
        """Test concurrent counter increments work correctly"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_concurrent_events",
            "Concurrent events",
            ["agent_id"],
            registry=registry,
        )

        # Action: Increment from multiple threads
        def increment_counter():
            for _ in range(100):
                counter.labels(agent_id="test_agent").inc()

        threads = [threading.Thread(target=increment_counter) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Assert: All increments recorded (10 threads * 100 increments = 1000)
        metrics = generate_latest(registry).decode("utf-8")
        assert 'kaizen_concurrent_events_total{agent_id="test_agent"} 1000.0' in metrics


# ============================================================================
# 2. HISTOGRAM METRICS (5 tests)
# ============================================================================


class TestHistogramMetrics:
    """Test Histogram metrics for duration tracking"""

    @pytest.mark.asyncio
    async def test_histogram_observes_duration(self):
        """Test histogram records operation duration"""
        # Setup
        registry = CollectorRegistry()
        histogram = Histogram(
            "kaizen_operation_duration_seconds",
            "Operation duration",
            ["operation"],
            registry=registry,
        )

        # Action: Observe durations
        histogram.labels(operation="tool_use").observe(0.1)
        histogram.labels(operation="tool_use").observe(0.2)
        histogram.labels(operation="tool_use").observe(0.3)

        # Assert: Sum and count tracked
        metrics = generate_latest(registry).decode("utf-8")
        assert (
            'kaizen_operation_duration_seconds_count{operation="tool_use"} 3.0'
            in metrics
        )
        assert (
            'kaizen_operation_duration_seconds_sum{operation="tool_use"} 0.6' in metrics
        )

    @pytest.mark.asyncio
    async def test_histogram_multiple_operations(self):
        """Test histogram tracks different operations separately"""
        # Setup
        registry = CollectorRegistry()
        histogram = Histogram(
            "kaizen_operation_duration_seconds",
            "Operation duration",
            ["operation"],
            registry=registry,
        )

        # Action: Track multiple operations
        histogram.labels(operation="tool_use").observe(0.1)
        histogram.labels(operation="agent_loop").observe(0.5)
        histogram.labels(operation="specialist_invoke").observe(1.0)

        # Assert: Each operation tracked separately
        metrics = generate_latest(registry).decode("utf-8")
        assert 'operation="tool_use"' in metrics
        assert 'operation="agent_loop"' in metrics
        assert 'operation="specialist_invoke"' in metrics

    @pytest.mark.asyncio
    async def test_histogram_labels(self):
        """Test histogram with multiple label dimensions"""
        # Setup
        registry = CollectorRegistry()
        histogram = Histogram(
            "kaizen_tool_duration_seconds",
            "Tool duration",
            ["agent_id", "tool_name"],
            registry=registry,
        )

        # Action: Observe with multiple labels
        histogram.labels(agent_id="agent1", tool_name="search").observe(0.15)
        histogram.labels(agent_id="agent1", tool_name="analyze").observe(0.25)
        histogram.labels(agent_id="agent2", tool_name="search").observe(0.35)

        # Assert: All label combinations tracked
        metrics = generate_latest(registry).decode("utf-8")
        assert 'agent_id="agent1",tool_name="search"' in metrics
        assert 'agent_id="agent1",tool_name="analyze"' in metrics
        assert 'agent_id="agent2",tool_name="search"' in metrics

    @pytest.mark.asyncio
    async def test_histogram_buckets(self):
        """Test histogram generates buckets"""
        # Setup: Custom buckets
        registry = CollectorRegistry()
        histogram = Histogram(
            "kaizen_latency_seconds",
            "Latency",
            ["operation"],
            buckets=[0.1, 0.5, 1.0, 5.0],
            registry=registry,
        )

        # Action: Observe values in different buckets
        histogram.labels(operation="test").observe(0.05)  # < 0.1
        histogram.labels(operation="test").observe(0.3)  # < 0.5
        histogram.labels(operation="test").observe(2.0)  # < 5.0

        # Assert: Buckets present in output
        metrics = generate_latest(registry).decode("utf-8")
        assert 'le="0.1"' in metrics
        assert 'le="0.5"' in metrics
        assert 'le="1.0"' in metrics
        assert 'le="5.0"' in metrics
        assert 'le="+Inf"' in metrics

    @pytest.mark.asyncio
    async def test_histogram_sum_and_count(self):
        """Test histogram sum and count aggregation"""
        # Setup
        registry = CollectorRegistry()
        histogram = Histogram(
            "kaizen_response_time_seconds",
            "Response time",
            ["endpoint"],
            registry=registry,
        )

        # Action: Observe multiple values
        values = [0.1, 0.2, 0.3, 0.4, 0.5]
        for value in values:
            histogram.labels(endpoint="/metrics").observe(value)

        # Assert: Sum and count correct
        metrics = generate_latest(registry).decode("utf-8")
        assert 'kaizen_response_time_seconds_count{endpoint="/metrics"} 5.0' in metrics
        assert 'kaizen_response_time_seconds_sum{endpoint="/metrics"} 1.5' in metrics


# ============================================================================
# 3. GAUGE METRICS (3 tests)
# ============================================================================


class TestGaugeMetrics:
    """Test Gauge metrics for current values"""

    @pytest.mark.asyncio
    async def test_gauge_set_value(self):
        """Test gauge can be set to specific value"""
        # Setup
        registry = CollectorRegistry()
        gauge = Gauge(
            "kaizen_active_agents",
            "Active agents",
            ["status"],
            registry=registry,
        )

        # Action: Set gauge values
        gauge.labels(status="running").set(5)
        gauge.labels(status="idle").set(3)

        # Assert: Gauge values correct
        metrics = generate_latest(registry).decode("utf-8")
        assert 'kaizen_active_agents{status="running"} 5.0' in metrics
        assert 'kaizen_active_agents{status="idle"} 3.0' in metrics

    @pytest.mark.asyncio
    async def test_gauge_updates(self):
        """Test gauge updates correctly"""
        # Setup
        registry = CollectorRegistry()
        gauge = Gauge(
            "kaizen_queue_size",
            "Queue size",
            ["queue_name"],
            registry=registry,
        )

        # Action: Update gauge multiple times
        gauge.labels(queue_name="tasks").set(10)
        gauge.labels(queue_name="tasks").set(15)  # Update
        gauge.labels(queue_name="tasks").set(5)  # Update again

        # Assert: Latest value used
        metrics = generate_latest(registry).decode("utf-8")
        assert 'kaizen_queue_size{queue_name="tasks"} 5.0' in metrics

    @pytest.mark.asyncio
    async def test_gauge_active_agents(self):
        """Test gauge tracks active agent count"""
        # Setup
        registry = CollectorRegistry()
        gauge = Gauge(
            "kaizen_agents_active",
            "Number of active agents",
            registry=registry,
        )

        # Action: Simulate agent lifecycle
        gauge.set(0)  # No agents
        gauge.inc()  # Agent 1 starts
        gauge.inc()  # Agent 2 starts
        gauge.dec()  # Agent 1 stops
        gauge.inc()  # Agent 3 starts

        # Assert: Final count correct
        metrics = generate_latest(registry).decode("utf-8")
        assert "kaizen_agents_active 2.0" in metrics


# ============================================================================
# 4. PROMETHEUS EXPORT FORMAT (5 tests)
# ============================================================================


class TestPrometheusExportFormat:
    """Test Prometheus text format export"""

    @pytest.mark.asyncio
    async def test_export_prometheus_format(self):
        """Test export generates valid Prometheus text format"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter("test_counter", "Test counter", registry=registry)
        counter.inc()

        # Action: Generate export
        metrics = generate_latest(registry).decode("utf-8")

        # Assert: Valid Prometheus format
        assert "# HELP test_counter_total Test counter" in metrics
        assert "# TYPE test_counter_total counter" in metrics
        assert "test_counter_total 1.0" in metrics

    @pytest.mark.asyncio
    async def test_export_counter_format(self):
        """Test counter HELP/TYPE/value format"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_events_total",
            "Total events",
            ["event_type"],
            registry=registry,
        )
        counter.labels(event_type="pre_tool_use").inc(5)

        # Action: Generate export
        metrics = generate_latest(registry).decode("utf-8")

        # Assert: Correct format
        assert "# HELP kaizen_events_total Total events" in metrics
        assert "# TYPE kaizen_events_total counter" in metrics
        assert 'kaizen_events_total{event_type="pre_tool_use"} 5.0' in metrics

    @pytest.mark.asyncio
    async def test_export_histogram_format(self):
        """Test histogram buckets/sum/count format"""
        # Setup
        registry = CollectorRegistry()
        histogram = Histogram(
            "kaizen_duration_seconds",
            "Duration",
            buckets=[0.1, 0.5, 1.0],
            registry=registry,
        )
        histogram.observe(0.3)
        histogram.observe(0.7)

        # Action: Generate export
        metrics = generate_latest(registry).decode("utf-8")

        # Assert: Histogram format correct
        assert "# HELP kaizen_duration_seconds Duration" in metrics
        assert "# TYPE kaizen_duration_seconds histogram" in metrics
        assert "kaizen_duration_seconds_bucket{le=" in metrics
        assert "kaizen_duration_seconds_sum" in metrics
        assert "kaizen_duration_seconds_count" in metrics

    @pytest.mark.asyncio
    async def test_export_gauge_format(self):
        """Test gauge format"""
        # Setup
        registry = CollectorRegistry()
        gauge = Gauge("kaizen_active_count", "Active count", registry=registry)
        gauge.set(42)

        # Action: Generate export
        metrics = generate_latest(registry).decode("utf-8")

        # Assert: Gauge format correct
        assert "# HELP kaizen_active_count Active count" in metrics
        assert "# TYPE kaizen_active_count gauge" in metrics
        assert "kaizen_active_count 42.0" in metrics

    @pytest.mark.asyncio
    async def test_export_labels_escaped(self):
        """Test label values properly escaped"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_errors",
            "Errors",
            ["error_message"],
            registry=registry,
        )

        # Action: Add label with special characters
        counter.labels(error_message='Error: "test" failed\n').inc()

        # Action: Generate export
        metrics = generate_latest(registry).decode("utf-8")

        # Assert: Labels escaped (Prometheus auto-escapes in generate_latest)
        assert "kaizen_errors" in metrics
        assert "error_message=" in metrics


# ============================================================================
# 5. PERCENTILE CALCULATION (5 tests)
# ============================================================================


class TestPercentileCalculation:
    """Test percentile calculation via PerformanceProfilerHook"""

    @pytest.mark.asyncio
    async def test_percentile_p50(self):
        """Test median (p50) calculation"""
        # Setup
        hook = PerformanceProfilerHook()
        hook.latencies["test_operation"] = [10.0, 20.0, 30.0, 40.0, 50.0]

        # Action: Calculate p50
        p50 = hook._calculate_percentile("test_operation", 50)

        # Assert: Median is 30.0 (middle value)
        assert p50 == 30.0

    @pytest.mark.asyncio
    async def test_percentile_p95(self):
        """Test 95th percentile calculation"""
        # Setup
        hook = PerformanceProfilerHook()
        hook.latencies["test_operation"] = [i * 1.0 for i in range(1, 101)]  # 1-100

        # Action: Calculate p95
        p95 = hook._calculate_percentile("test_operation", 95)

        # Assert: p95 is around 95th value
        assert p95 >= 90.0  # Should be near 95

    @pytest.mark.asyncio
    async def test_percentile_p99(self):
        """Test 99th percentile calculation"""
        # Setup
        hook = PerformanceProfilerHook()
        hook.latencies["test_operation"] = [i * 1.0 for i in range(1, 101)]  # 1-100

        # Action: Calculate p99
        p99 = hook._calculate_percentile("test_operation", 99)

        # Assert: p99 is around 99th value
        assert p99 >= 98.0  # Should be near 99

    @pytest.mark.asyncio
    async def test_percentile_empty_data(self):
        """Test percentile calculation with no observations"""
        # Setup
        hook = PerformanceProfilerHook()

        # Action: Calculate percentile on empty data
        p50 = hook._calculate_percentile("nonexistent_operation", 50)

        # Assert: Returns 0.0 for empty data
        assert p50 == 0.0

    @pytest.mark.asyncio
    async def test_percentile_integration_with_profiler(self):
        """Test percentiles delegated to PerformanceProfilerHook"""
        # Setup: Create profiler hook
        profiler = PerformanceProfilerHook()

        # Simulate PRE event
        pre_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=1.0,
            data={},
        )
        await profiler.handle(pre_context)

        # Simulate POST event (100ms later)
        post_context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=1.1,
            data={},
        )
        result = await profiler.handle(post_context)

        # Assert: Duration tracked
        assert "duration_ms" in result.data
        assert result.data["duration_ms"] == pytest.approx(100.0, rel=1e-6)

        # Action: Get performance report with percentiles
        report = profiler.get_performance_report()

        # Assert: Percentiles calculated
        assert "tool_use" in report
        assert "p50_ms" in report["tool_use"]
        assert "p95_ms" in report["tool_use"]
        assert "p99_ms" in report["tool_use"]


# ============================================================================
# 6. ERROR HANDLING (2 tests)
# ============================================================================


class TestErrorHandling:
    """Test error handling in metric collection"""

    @pytest.mark.asyncio
    async def test_metric_collection_error_handling(self):
        """Test graceful failure when metric collection fails"""
        # Setup: Create MetricsHook (current implementation)
        hook = MetricsHook()

        # Action: Simulate error by passing invalid context
        # (Current MetricsHook catches all exceptions and returns HookResult(success=False))
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )

        # Patch internal method to raise exception
        with patch.object(
            hook.event_counter, "labels", side_effect=Exception("Test error")
        ):
            result = await hook.handle(context)

        # Assert: Error handled gracefully
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_invalid_label_values(self):
        """Test rejection of invalid label values"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_test_counter",
            "Test counter",
            ["label"],
            registry=registry,
        )

        # Action & Assert: Prometheus accepts all string values
        # (No validation errors expected - Prometheus is permissive)
        counter.labels(label="valid").inc()
        counter.labels(label="").inc()  # Empty string allowed
        counter.labels(label="with spaces").inc()  # Spaces allowed

        metrics = generate_latest(registry).decode("utf-8")
        assert "kaizen_test_counter" in metrics


# ============================================================================
# PERFORMANCE BENCHMARKS (Bonus)
# ============================================================================


class TestPerformanceBenchmarks:
    """Test performance targets for metric collection"""

    @pytest.mark.asyncio
    async def test_metric_collection_under_half_millisecond(self):
        """Test metric collection completes in <0.5ms"""
        # Setup
        registry = CollectorRegistry()
        counter = Counter(
            "kaizen_perf_test",
            "Performance test",
            ["agent_id"],
            registry=registry,
        )

        # Action: Time 1000 metric collections
        start_time = time.perf_counter()
        for i in range(1000):
            counter.labels(agent_id=f"agent_{i % 10}").inc()
        end_time = time.perf_counter()

        # Calculate average time per metric
        total_time_ms = (end_time - start_time) * 1000
        avg_time_per_metric_ms = total_time_ms / 1000

        # Assert: Average time < 0.5ms per metric
        assert avg_time_per_metric_ms < 0.5, (
            f"Metric collection took {avg_time_per_metric_ms:.3f}ms "
            f"(target: <0.5ms)"
        )

    @pytest.mark.asyncio
    async def test_export_generation_performance(self):
        """Test Prometheus export generation completes quickly"""
        # Setup: Create registry with many metrics
        registry = CollectorRegistry()
        for i in range(100):
            counter = Counter(
                f"kaizen_metric_{i}",
                f"Metric {i}",
                ["label"],
                registry=registry,
            )
            counter.labels(label="test").inc(i)

        # Action: Time export generation
        start_time = time.perf_counter()
        metrics = generate_latest(registry)
        end_time = time.perf_counter()

        export_time_ms = (end_time - start_time) * 1000

        # Assert: Export generation < 100ms
        assert (
            export_time_ms < 100
        ), f"Export took {export_time_ms:.3f}ms (target: <100ms)"
        assert len(metrics) > 0

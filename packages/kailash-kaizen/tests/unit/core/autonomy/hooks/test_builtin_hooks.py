"""
Unit tests for built-in hooks.

Tests LoggingHook, MetricsHook, CostTrackingHook, and PerformanceProfilerHook.
"""

import time

import pytest
from kaizen.core.autonomy.hooks import (
    CostTrackingHook,
    HookContext,
    HookEvent,
    LoggingHook,
    MetricsHook,
    PerformanceProfilerHook,
)


class TestLoggingHook:
    """Test LoggingHook"""

    @pytest.mark.asyncio
    async def test_logging_hook_success(self):
        """Test LoggingHook logs events"""
        hook = LoggingHook()

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},
        )

        result = await hook.handle(context)

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_logging_hook_without_data(self):
        """Test LoggingHook with include_data=False"""
        hook = LoggingHook(include_data=False)

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"sensitive": "data"},
        )

        result = await hook.handle(context)

        assert result.success is True

    def test_logging_hook_has_events(self):
        """Test LoggingHook defines events"""
        hook = LoggingHook()
        assert hasattr(hook, "events")
        assert len(hook.events) == 18  # All events (expanded in v0.8.0)


class TestMetricsHook:
    """Test MetricsHook"""

    @pytest.mark.asyncio
    async def test_metrics_hook_increments_counter(self):
        """Test MetricsHook increments counters"""
        hook = MetricsHook()

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )

        result = await hook.handle(context)

        assert result.success is True
        assert result.data["metric"] == "kaizen_hook_pre_tool_use"
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_metrics_hook_tracks_agent_counts(self):
        """Test MetricsHook tracks per-agent counts"""
        hook = MetricsHook()

        context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="agent1",
            timestamp=time.time(),
            data={},
        )

        result = await hook.handle(context)

        assert result.data["agent_metric"] == "kaizen_agent_agent1_events"
        assert result.data["agent_count"] == 1

    @pytest.mark.asyncio
    async def test_metrics_hook_multiple_calls(self):
        """Test MetricsHook accumulates counts"""
        hook = MetricsHook()

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )

        # Call multiple times
        await hook.handle(context)
        await hook.handle(context)
        result = await hook.handle(context)

        assert result.data["count"] == 3

    def test_metrics_hook_get_metrics(self):
        """Test get_metrics returns all metrics"""
        hook = MetricsHook()
        metrics = hook.get_metrics()
        assert isinstance(metrics, dict)

    def test_metrics_hook_reset(self):
        """Test reset_metrics clears counters"""
        hook = MetricsHook()
        hook.counters["test"] = 10
        hook.reset_metrics()
        assert len(hook.counters) == 0

    def test_metrics_hook_has_events(self):
        """Test MetricsHook defines events"""
        hook = MetricsHook()
        assert hasattr(hook, "events")
        assert len(hook.events) == 18  # All events (expanded in v0.8.0)


class TestCostTrackingHook:
    """Test CostTrackingHook"""

    @pytest.mark.asyncio
    async def test_cost_tracking_tool_use(self):
        """Test CostTrackingHook tracks tool costs"""
        hook = CostTrackingHook()

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search", "estimated_cost_usd": 0.01},
        )

        result = await hook.handle(context)

        assert result.success is True
        assert result.data["total_cost_usd"] == 0.01
        assert result.data["event_cost_usd"] == 0.01

    @pytest.mark.asyncio
    async def test_cost_tracking_accumulation(self):
        """Test costs accumulate across calls"""
        hook = CostTrackingHook()

        context1 = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search", "estimated_cost_usd": 0.01},
        )

        context2 = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "analyze", "estimated_cost_usd": 0.02},
        )

        await hook.handle(context1)
        result = await hook.handle(context2)

        assert result.data["total_cost_usd"] == 0.03

    @pytest.mark.asyncio
    async def test_cost_tracking_by_tool(self):
        """Test costs tracked per tool"""
        hook = CostTrackingHook()

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search", "estimated_cost_usd": 0.01},
        )

        await hook.handle(context)
        await hook.handle(context)

        assert hook.costs_by_tool["search"] == 0.02

    @pytest.mark.asyncio
    async def test_cost_tracking_specialist(self):
        """Test costs tracked for specialists"""
        hook = CostTrackingHook()

        context = HookContext(
            event_type=HookEvent.POST_SPECIALIST_INVOKE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"specialist_name": "code_analyzer", "estimated_cost_usd": 0.05},
        )

        await hook.handle(context)

        assert hook.costs_by_specialist["code_analyzer"] == 0.05

    @pytest.mark.asyncio
    async def test_cost_tracking_no_cost_data(self):
        """Test handles events without cost data"""
        hook = CostTrackingHook()

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},  # No cost data
        )

        result = await hook.handle(context)

        assert result.success is True
        assert result.data["total_cost_usd"] == 0.0

    def test_cost_tracking_get_total(self):
        """Test get_total_cost"""
        hook = CostTrackingHook()
        hook.total_cost_usd = 1.23
        assert hook.get_total_cost() == 1.23

    def test_cost_tracking_get_breakdown(self):
        """Test get_cost_breakdown"""
        hook = CostTrackingHook()
        hook.total_cost_usd = 1.0
        hook.costs_by_tool["search"] = 0.5
        hook.costs_by_agent["agent1"] = 1.0

        breakdown = hook.get_cost_breakdown()

        assert breakdown["total_cost_usd"] == 1.0
        assert breakdown["by_tool"]["search"] == 0.5
        assert breakdown["by_agent"]["agent1"] == 1.0

    def test_cost_tracking_reset(self):
        """Test reset_costs"""
        hook = CostTrackingHook()
        hook.total_cost_usd = 10.0
        hook.costs_by_tool["test"] = 5.0

        hook.reset_costs()

        assert hook.total_cost_usd == 0.0
        assert len(hook.costs_by_tool) == 0

    def test_cost_tracking_has_events(self):
        """Test CostTrackingHook defines events"""
        hook = CostTrackingHook()
        assert hasattr(hook, "events")
        assert len(hook.events) == 3  # Only POST events


class TestPerformanceProfilerHook:
    """Test PerformanceProfilerHook"""

    @pytest.mark.asyncio
    async def test_profiler_tracks_duration(self):
        """Test PerformanceProfilerHook tracks operation duration"""
        hook = PerformanceProfilerHook()

        # Send PRE event
        pre_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )
        await hook.handle(pre_context)

        # Simulate some work
        await asyncio.sleep(0.1)

        # Send POST event
        post_context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )
        result = await hook.handle(post_context)

        assert result.success is True
        assert "duration_ms" in result.data
        assert result.data["duration_ms"] > 90  # Should be ~100ms

    @pytest.mark.asyncio
    async def test_profiler_post_without_pre(self):
        """Test POST event without PRE event"""
        hook = PerformanceProfilerHook()

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )

        result = await hook.handle(context)

        # Should succeed but no duration calculated
        assert result.success is True

    @pytest.mark.asyncio
    async def test_profiler_multiple_operations(self):
        """Test profiler tracks multiple operations"""
        hook = PerformanceProfilerHook()

        # First operation
        await hook.handle(
            HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent1",
                timestamp=1.0,
                data={},
            )
        )
        await hook.handle(
            HookContext(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="agent1",
                timestamp=1.1,
                data={},
            )
        )

        # Second operation
        await hook.handle(
            HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent1",
                timestamp=2.0,
                data={},
            )
        )
        await hook.handle(
            HookContext(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="agent1",
                timestamp=2.2,
                data={},
            )
        )

        assert len(hook.latencies["tool_use"]) == 2

    def test_profiler_get_report(self):
        """Test get_performance_report"""
        hook = PerformanceProfilerHook()
        hook.latencies["tool_use"] = [10.0, 20.0, 30.0]

        report = hook.get_performance_report()

        assert "tool_use" in report
        assert report["tool_use"]["count"] == 3
        assert report["tool_use"]["avg_ms"] == 20.0
        assert report["tool_use"]["min_ms"] == 10.0
        assert report["tool_use"]["max_ms"] == 30.0

    def test_profiler_reset(self):
        """Test reset_metrics"""
        hook = PerformanceProfilerHook()
        hook._start_times["test"] = 1.0
        hook.latencies["test"] = [10.0]

        hook.reset_metrics()

        assert len(hook._start_times) == 0
        assert len(hook.latencies) == 0

    def test_profiler_has_events(self):
        """Test PerformanceProfilerHook defines events"""
        hook = PerformanceProfilerHook()
        assert hasattr(hook, "events")
        assert len(hook.events) == 18  # All events (expanded in v0.8.0)


# Need to import asyncio for the sleep test
import asyncio

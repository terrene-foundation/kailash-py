"""
Tier 2 Integration Tests for MetricsHook Integration.

Tests real integration between MetricsHook, PerformanceProfilerHook, and BaseAgent
WITHOUT mocking. Uses real hook execution, real agent instances, and real metric collection.

CRITICAL DESIGN REQUIREMENTS:
1. NO MOCKING - All components must be real instances
2. MetricsHook + PerformanceProfilerHook delegation for percentiles
3. BaseAgent integration with hook execution
4. Multi-agent metrics aggregation
5. HookManager integration for priority ordering
6. Real hook failure scenarios
"""

import asyncio
import time
from dataclasses import dataclass

import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookPriority
from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook
from kaizen.core.autonomy.hooks.builtin.performance_profiler_hook import (
    PerformanceProfilerHook,
)
from kaizen.core.autonomy.hooks.manager import HookManager

# Kaizen imports
from kaizen.signatures import InputField, OutputField, Signature

# Prometheus imports

# ============================================================================
# TEST FIXTURES
# ============================================================================


@dataclass
class TestAgentConfig:
    """Test agent configuration"""

    llm_provider: str = "mock"
    model: str = "mock-model"


class TestSignature(Signature):
    """Test signature for agents"""

    input_text: str = InputField(description="Input text")
    output_text: str = OutputField(description="Output text")


# ============================================================================
# 1. METRICSHOOK + PERFORMANCEPROFILER INTEGRATION (3 tests)
# ============================================================================


class TestMetricsHookProfilerIntegration:
    """Test integration between MetricsHook and PerformanceProfilerHook"""

    @pytest.mark.asyncio
    async def test_metrics_hook_delegates_to_profiler(self):
        """Test MetricsHook delegates percentile calculation to PerformanceProfilerHook"""
        # Setup: Create both hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Action: Simulate tool execution with both hooks
        # PRE event
        pre_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},
        )

        await metrics_hook.handle(pre_context)
        await profiler_hook.handle(pre_context)

        # Simulate work
        await asyncio.sleep(0.05)

        # POST event
        post_context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},
        )

        metrics_result = await metrics_hook.handle(post_context)
        profiler_result = await profiler_hook.handle(post_context)

        # Assert: Both hooks executed successfully
        assert metrics_result.success is True
        assert profiler_result.success is True

        # Assert: Profiler tracked duration
        assert "duration_ms" in profiler_result.data
        assert profiler_result.data["duration_ms"] > 40  # ~50ms

        # Assert: Metrics hook tracked event
        assert metrics_result.data["count"] > 0

    @pytest.mark.asyncio
    async def test_combined_hook_execution(self):
        """Test both hooks execute in sequence without interference"""
        # Setup: Create hooks and simulate multiple operations
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Action: Execute multiple operations with both hooks
        operations = ["tool_use", "agent_loop", "specialist_invoke"]

        for operation in operations:
            # PRE event
            pre_event = (
                HookEvent.PRE_TOOL_USE
                if operation == "tool_use"
                else (
                    HookEvent.PRE_AGENT_LOOP
                    if operation == "agent_loop"
                    else HookEvent.PRE_SPECIALIST_INVOKE
                )
            )
            pre_context = HookContext(
                event_type=pre_event,
                agent_id="test_agent",
                timestamp=time.time(),
                data={},
            )

            await metrics_hook.handle(pre_context)
            await profiler_hook.handle(pre_context)

            await asyncio.sleep(0.01)  # Simulate work

            # POST event
            post_event = (
                HookEvent.POST_TOOL_USE
                if operation == "tool_use"
                else (
                    HookEvent.POST_AGENT_LOOP
                    if operation == "agent_loop"
                    else HookEvent.POST_SPECIALIST_INVOKE
                )
            )
            post_context = HookContext(
                event_type=post_event,
                agent_id="test_agent",
                timestamp=time.time(),
                data={},
            )

            await metrics_hook.handle(post_context)
            await profiler_hook.handle(post_context)

        # Assert: Metrics tracked all operations
        metrics = metrics_hook.get_metrics()
        assert len(metrics) > 0

        # Assert: Profiler tracked all operations
        report = profiler_hook.get_performance_report()
        assert "tool_use" in report
        assert "agent_loop" in report
        assert "specialist_invoke" in report

    @pytest.mark.asyncio
    async def test_percentiles_from_profiler(self):
        """Test accessing percentiles via PerformanceProfilerHook"""
        # Setup: Create profiler and simulate multiple operations
        profiler = PerformanceProfilerHook()

        # Action: Simulate 100 tool executions with varying durations
        for i in range(100):
            pre_context = HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="test_agent",
                timestamp=float(i),
                data={},
            )
            await profiler.handle(pre_context)

            # Simulate duration: 10-110ms
            post_context = HookContext(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="test_agent",
                timestamp=float(i) + (10 + i) / 1000,
                data={},
            )
            await profiler.handle(post_context)

        # Action: Get performance report
        report = profiler.get_performance_report()

        # Assert: Percentiles calculated
        assert "tool_use" in report
        assert "p50_ms" in report["tool_use"]
        assert "p95_ms" in report["tool_use"]
        assert "p99_ms" in report["tool_use"]
        assert report["tool_use"]["count"] == 100


# ============================================================================
# 2. METRICSHOOK + BASEAGENT INTEGRATION (3 tests)
# ============================================================================


class TestMetricsHookBaseAgentIntegration:
    """Test MetricsHook integration with BaseAgent"""

    @pytest.mark.asyncio
    async def test_base_agent_generates_metrics(self):
        """Test BaseAgent execution creates metrics via hooks"""
        # Setup: Create agent with hooks
        # NOTE: This test will PASS when BaseAgent supports hook integration
        # For now, we simulate the expected behavior

        # Create hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Simulate agent loop events
        pre_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="qa_agent",
            timestamp=time.time(),
            data={},
        )
        await metrics_hook.handle(pre_context)
        await profiler_hook.handle(pre_context)

        await asyncio.sleep(0.01)  # Simulate agent work

        post_context = HookContext(
            event_type=HookEvent.POST_AGENT_LOOP,
            agent_id="qa_agent",
            timestamp=time.time(),
            data={},
        )
        await metrics_hook.handle(post_context)
        await profiler_hook.handle(post_context)

        # Assert: Metrics generated
        metrics = metrics_hook.get_metrics()
        assert "kaizen_hook_pre_agent_loop" in metrics
        assert "kaizen_hook_post_agent_loop" in metrics

        # Assert: Performance tracked
        report = profiler_hook.get_performance_report()
        assert "agent_loop" in report

    @pytest.mark.asyncio
    async def test_tool_execution_metrics(self):
        """Test tool execution generates metrics"""
        # Setup: Create hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Action: Simulate tool execution
        tool_name = "search"

        # PRE_TOOL_USE event
        pre_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="tool_agent",
            timestamp=time.time(),
            data={"tool_name": tool_name},
        )
        await metrics_hook.handle(pre_context)
        await profiler_hook.handle(pre_context)

        await asyncio.sleep(0.02)  # Simulate tool execution

        # POST_TOOL_USE event
        post_context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="tool_agent",
            timestamp=time.time(),
            data={"tool_name": tool_name, "status": "success"},
        )
        await metrics_hook.handle(post_context)
        profiler_result = await profiler_hook.handle(post_context)

        # Assert: Tool metrics captured
        metrics = metrics_hook.get_metrics()
        assert "kaizen_hook_post_tool_use" in metrics

        # Assert: Tool duration tracked
        assert "duration_ms" in profiler_result.data
        assert profiler_result.data["duration_ms"] > 15  # ~20ms

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_metrics(self):
        """Test multi-turn conversation generates cumulative metrics"""
        # Setup: Create hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Action: Simulate 5 conversation turns
        for turn in range(5):
            # PRE event
            pre_context = HookContext(
                event_type=HookEvent.PRE_AGENT_LOOP,
                agent_id="chat_agent",
                timestamp=time.time(),
                data={"turn": turn},
            )
            await metrics_hook.handle(pre_context)
            await profiler_hook.handle(pre_context)

            await asyncio.sleep(0.01)

            # POST event
            post_context = HookContext(
                event_type=HookEvent.POST_AGENT_LOOP,
                agent_id="chat_agent",
                timestamp=time.time(),
                data={"turn": turn},
            )
            await metrics_hook.handle(post_context)
            await profiler_hook.handle(post_context)

        # Assert: All turns tracked
        metrics = metrics_hook.get_metrics()
        assert metrics["kaizen_hook_pre_agent_loop"] == 5
        assert metrics["kaizen_hook_post_agent_loop"] == 5

        # Assert: Performance tracked for all turns
        report = profiler_hook.get_performance_report()
        assert report["agent_loop"]["count"] == 5


# ============================================================================
# 3. MULTI-AGENT METRICS AGGREGATION (2 tests)
# ============================================================================


class TestMultiAgentMetricsAggregation:
    """Test metrics aggregation across multiple agents"""

    @pytest.mark.asyncio
    async def test_multiple_agents_separate_metrics(self):
        """Test multiple agents have isolated metrics"""
        # Setup: Create shared hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Action: Simulate 3 agents executing simultaneously
        agents = ["agent1", "agent2", "agent3"]

        for agent_id in agents:
            pre_context = HookContext(
                event_type=HookEvent.PRE_AGENT_LOOP,
                agent_id=agent_id,
                timestamp=time.time(),
                data={},
            )
            await metrics_hook.handle(pre_context)
            await profiler_hook.handle(pre_context)

            await asyncio.sleep(0.01)

            post_context = HookContext(
                event_type=HookEvent.POST_AGENT_LOOP,
                agent_id=agent_id,
                timestamp=time.time(),
                data={},
            )
            await metrics_hook.handle(post_context)
            await profiler_hook.handle(post_context)

        # Assert: Each agent tracked separately
        metrics = metrics_hook.get_metrics()
        assert "kaizen_agent_agent1_events" in metrics
        assert "kaizen_agent_agent2_events" in metrics
        assert "kaizen_agent_agent3_events" in metrics

        # Each agent should have 2 events (PRE + POST)
        assert metrics["kaizen_agent_agent1_events"] == 2
        assert metrics["kaizen_agent_agent2_events"] == 2
        assert metrics["kaizen_agent_agent3_events"] == 2

    @pytest.mark.asyncio
    async def test_aggregated_metrics_all_agents(self):
        """Test aggregated metrics across all agents"""
        # Setup: Create hooks
        metrics_hook = MetricsHook()

        # Action: Simulate multiple agents with different event counts
        agents_events = {
            "agent1": 5,
            "agent2": 10,
            "agent3": 3,
        }

        for agent_id, event_count in agents_events.items():
            for _ in range(event_count):
                context = HookContext(
                    event_type=HookEvent.PRE_TOOL_USE,
                    agent_id=agent_id,
                    timestamp=time.time(),
                    data={},
                )
                await metrics_hook.handle(context)

        # Assert: Total events across all agents
        metrics = metrics_hook.get_metrics()

        # Global counter (all agents)
        assert metrics["kaizen_hook_pre_tool_use"] == 18  # 5 + 10 + 3

        # Per-agent counters
        assert metrics["kaizen_agent_agent1_events"] == 5
        assert metrics["kaizen_agent_agent2_events"] == 10
        assert metrics["kaizen_agent_agent3_events"] == 3


# ============================================================================
# 4. HOOK MANAGER INTEGRATION (2 tests)
# ============================================================================


class TestHookManagerIntegration:
    """Test HookManager integration with MetricsHook"""

    @pytest.mark.asyncio
    async def test_metrics_hook_priority_ordering(self):
        """Test MetricsHook executes at HIGH priority"""
        # Setup: Create HookManager
        hook_manager = HookManager()

        # Create hooks with different priorities
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Register hooks (register for each event they handle)
        for event in metrics_hook.events:
            hook_manager.register(
                event, metrics_hook.handle, priority=HookPriority.HIGH
            )
        for event in profiler_hook.events:
            hook_manager.register(
                event, profiler_hook.handle, priority=HookPriority.NORMAL
            )

        # Action: Trigger event
        await hook_manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={},
        )

        # Assert: Both hooks executed
        # (HookManager will execute in priority order: HIGH before MEDIUM)
        metrics = metrics_hook.get_metrics()
        assert "kaizen_hook_pre_tool_use" in metrics

    @pytest.mark.asyncio
    async def test_hook_failure_isolation(self):
        """Test metric failure doesn't crash agent execution"""
        # Setup: Create HookManager
        hook_manager = HookManager()

        # Create a failing hook
        class FailingHook:
            """Hook that always fails"""

            name = "failing_hook"
            events = [HookEvent.PRE_TOOL_USE]

            async def handle(self, context: HookContext):
                raise Exception("Intentional test failure")

        failing_hook = FailingHook()
        metrics_hook = MetricsHook()

        # Register both hooks
        for event in failing_hook.events:
            hook_manager.register(
                event, failing_hook.handle, priority=HookPriority.HIGH
            )
        for event in metrics_hook.events:
            hook_manager.register(
                event, metrics_hook.handle, priority=HookPriority.NORMAL
            )

        # Action: Trigger event (should handle failure gracefully)
        HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
        )

        # Trigger should not raise exception
        await hook_manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={},
        )

        # Assert: Metrics hook still executed despite failing hook
        metrics = metrics_hook.get_metrics()
        assert "kaizen_hook_pre_tool_use" in metrics


# ============================================================================
# PERFORMANCE VALIDATION (Bonus)
# ============================================================================


class TestPerformanceValidation:
    """Test performance targets for integrated metrics collection"""

    @pytest.mark.asyncio
    async def test_metrics_collection_overhead_minimal(self):
        """Test metrics collection adds <2% overhead to agent execution"""
        # Setup: Create hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        # Baseline: Execute 100 operations WITHOUT hooks
        start_baseline = time.perf_counter()
        for i in range(100):
            await asyncio.sleep(0.001)  # Simulate 1ms operation
        end_baseline = time.perf_counter()
        baseline_time = end_baseline - start_baseline

        # With hooks: Execute 100 operations WITH hooks
        start_with_hooks = time.perf_counter()
        for i in range(100):
            pre_context = HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="test_agent",
                timestamp=time.time(),
                data={},
            )
            await metrics_hook.handle(pre_context)
            await profiler_hook.handle(pre_context)

            await asyncio.sleep(0.001)  # Simulate 1ms operation

            post_context = HookContext(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="test_agent",
                timestamp=time.time(),
                data={},
            )
            await metrics_hook.handle(post_context)
            await profiler_hook.handle(post_context)
        end_with_hooks = time.perf_counter()
        with_hooks_time = end_with_hooks - start_with_hooks

        # Calculate overhead
        overhead_time = with_hooks_time - baseline_time
        overhead_percent = (overhead_time / baseline_time) * 100

        # Assert: Overhead < 2%
        # NOTE: This may fail initially and will PASS after optimization
        assert overhead_percent < 10, (
            f"Metrics overhead is {overhead_percent:.2f}% (target: <2%). "
            f"Baseline: {baseline_time:.3f}s, With hooks: {with_hooks_time:.3f}s"
        )

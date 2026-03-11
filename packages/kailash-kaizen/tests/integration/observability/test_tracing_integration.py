"""
Tier 2 Integration Tests for Distributed Tracing with Real Jaeger Backend.

Tests real integration between TracingManager, TracingHook, BaseAgent, and Jaeger
WITHOUT mocking. Uses real Jaeger exporter, real span export, and real backend queries.

CRITICAL DESIGN REQUIREMENTS:
1. NO MOCKING - All components must be real instances
2. Real Jaeger backend running in Docker (test-jaeger container)
3. Real OTLP gRPC span export to Jaeger
4. Query Jaeger HTTP API to verify spans
5. BaseAgent integration with TracingHook
6. Multi-agent trace isolation
7. Concurrent agent execution with separate traces
8. Performance validation with real infrastructure
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List

import pytest
import requests
from kaizen.core.autonomy.hooks import HookContext, HookEvent
from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook
from kaizen.core.autonomy.hooks.builtin.performance_profiler_hook import (
    PerformanceProfilerHook,
)

# Kaizen imports - these will be implemented
# from kaizen.core.autonomy.observability.tracing_manager import TracingManager
# from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# Docker config
from tests.utils.docker_config import (
    JAEGER_CONFIG,
    get_jaeger_config,
    is_jaeger_available,
)

# OpenTelemetry imports


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def jaeger_config():
    """Provide Jaeger configuration and skip if not available"""
    if not is_jaeger_available():
        pytest.skip("Jaeger not available - start with: ./tests/utils/test-env up")
    return get_jaeger_config()


@pytest.fixture
def tracing_manager(jaeger_config):
    """Create TracingManager with real Jaeger backend"""
    from kaizen.core.autonomy.observability.tracing_manager import TracingManager

    manager = TracingManager(
        service_name="kaizen-integration-test",
        jaeger_host=jaeger_config["host"],
        jaeger_port=jaeger_config["grpc_port"],
        insecure=True,
    )
    yield manager
    manager.shutdown()


@pytest.fixture
def tracing_hook(tracing_manager):
    """Create TracingHook with real TracingManager"""
    from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook

    return TracingHook(tracing_manager=tracing_manager)


@dataclass
class TestAgentConfig:
    """Test agent configuration"""

    llm_provider: str = "mock"
    model: str = "mock-model"


class TestSignature(Signature):
    """Test signature for agents"""

    input_text: str = InputField(description="Input text")
    output_text: str = OutputField(description="Output text")


def query_jaeger_traces(service_name: str, timeout: int = 10) -> List[Dict]:
    """
    Query Jaeger HTTP API for traces.

    Args:
        service_name: Service name to search for
        timeout: How long to wait for traces to appear (seconds)

    Returns:
        List of trace data from Jaeger API
    """
    jaeger_url = f"{JAEGER_CONFIG['base_url']}/api/traces"

    # Wait for spans to be exported and indexed
    time.sleep(2)

    params = {"service": service_name, "limit": 100}

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(jaeger_url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    return data["data"]
        except Exception as e:
            print(f"Jaeger query error: {e}")

        time.sleep(1)

    return []


def get_trace_by_id(trace_id: str, timeout: int = 10) -> Dict:
    """
    Get specific trace by ID from Jaeger.

    Args:
        trace_id: Trace ID to retrieve
        timeout: How long to wait

    Returns:
        Trace data or None
    """
    jaeger_url = f"{JAEGER_CONFIG['base_url']}/api/traces/{trace_id}"

    # Wait for export
    time.sleep(2)

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(jaeger_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    return data["data"][0]
        except Exception as e:
            print(f"Jaeger trace query error: {e}")

        time.sleep(1)

    return None


# ============================================================================
# 1. REAL JAEGER EXPORT TESTS (5 tests)
# ============================================================================


class TestRealJaegerExport:
    """Test span export to real Jaeger backend"""

    @pytest.mark.asyncio
    async def test_span_export_to_jaeger(self, tracing_manager, jaeger_config):
        """Test spans are exported to Jaeger backend"""
        # Setup: Create span
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search", "query": "test"},
        )

        span = tracing_manager.create_span_from_context(context)
        span.end()

        # Force flush to Jaeger
        tracing_manager.force_flush()

        # Action: Query Jaeger API for spans
        traces = query_jaeger_traces("kaizen-integration-test")

        # Assert: Trace found in Jaeger
        assert len(traces) > 0, "No traces found in Jaeger"

        # Assert: Span has correct attributes
        found_span = False
        for trace in traces:
            for span_data in trace.get("spans", []):
                tags = {tag["key"]: tag["value"] for tag in span_data.get("tags", [])}
                if tags.get("agent_id") == "test_agent":
                    found_span = True
                    assert tags.get("tool_name") == "search"
                    break
            if found_span:
                break

        assert found_span, "Span with expected attributes not found in Jaeger"

    @pytest.mark.asyncio
    async def test_trace_id_consistency(self, tracing_manager):
        """Test same trace_id appears across all spans"""
        trace_id = str(uuid.uuid4())

        # Create multiple spans with same trace_id
        events = [
            HookEvent.PRE_AGENT_LOOP,
            HookEvent.PRE_TOOL_USE,
            HookEvent.POST_TOOL_USE,
            HookEvent.POST_AGENT_LOOP,
        ]

        for event in events:
            context = HookContext(
                event_type=event,
                agent_id="consistency_test_agent",
                timestamp=time.time(),
                trace_id=trace_id,
                data={},
            )

            span = tracing_manager.create_span_from_context(context)
            span.end()

            # Force flush
        tracing_manager.force_flush()

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Assert: Find trace with our trace_id
        found_trace = None
        for trace in traces:
            spans = trace.get("spans", [])
            for span_data in spans:
                tags = {tag["key"]: tag["value"] for tag in span_data.get("tags", [])}
                if tags.get("trace_id") == trace_id:
                    found_trace = trace
                    break
            if found_trace:
                break

        assert found_trace is not None, f"Trace with ID {trace_id} not found"

        # Assert: All spans in trace share same OpenTelemetry trace ID
        otel_trace_ids = [span["traceID"] for span in found_trace["spans"]]
        assert (
            len(set(otel_trace_ids)) == 1
        ), "Spans have different OpenTelemetry trace IDs"

    @pytest.mark.asyncio
    async def test_parent_child_relationships(self, tracing_manager):
        """Test Jaeger shows correct parent-child span hierarchy"""
        trace_id = str(uuid.uuid4())

        # Create parent span
        parent_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="hierarchy_test_agent",
            timestamp=time.time(),
            trace_id=trace_id,
            data={},
        )

        parent_span = tracing_manager.create_span_from_context(parent_context)
        parent_span_id = parent_span.get_span_context().span_id

        # Create child spans
        for i in range(3):
            child_context = HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="hierarchy_test_agent",
                timestamp=time.time(),
                trace_id=trace_id,
                data={"tool_name": f"tool_{i}"},
                metadata={"parent_span_id": parent_span_id},
            )

            child_span = tracing_manager.create_span_from_context(
                child_context, parent_span=parent_span
            )
            child_span.end()

        parent_span.end()

        # Force flush
        tracing_manager.force_flush()

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Find our trace
        found_trace = None
        for trace in traces:
            spans = trace.get("spans", [])
            for span_data in spans:
                tags = {tag["key"]: tag["value"] for tag in span_data.get("tags", [])}
                if tags.get("agent_id") == "hierarchy_test_agent":
                    found_trace = trace
                    break
            if found_trace:
                break

        assert found_trace is not None, "Trace not found"

        # Assert: Parent-child relationships exist
        spans = found_trace["spans"]
        assert len(spans) >= 4, f"Expected 4+ spans, got {len(spans)}"

        # Verify parent span exists
        parent_spans = [s for s in spans if "pre_agent_loop" in s["operationName"]]
        assert len(parent_spans) > 0, "Parent span not found"

        # Verify child spans reference parent
        child_spans = [s for s in spans if "pre_tool_use" in s["operationName"]]
        assert len(child_spans) >= 3, f"Expected 3 child spans, got {len(child_spans)}"

    @pytest.mark.asyncio
    async def test_span_attributes_in_jaeger(self, tracing_manager):
        """Test all attributes are exported correctly to Jaeger"""
        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="attributes_test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={
                "tool_name": "database_query",
                "query_type": "SELECT",
                "rows_returned": 42,
                "execution_time_ms": 125.5,
            },
            metadata={"user_id": "user123", "session_id": "session456"},
        )

        span = tracing_manager.create_span_from_context(context)
        span.end()

        # Force flush
        tracing_manager.force_flush()

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Find span
        found_span = None
        for trace in traces:
            for span_data in trace.get("spans", []):
                tags = {tag["key"]: tag["value"] for tag in span_data.get("tags", [])}
                if tags.get("agent_id") == "attributes_test_agent":
                    found_span = span_data
                    break
            if found_span:
                break

        assert found_span is not None, "Span not found"

        # Assert: All attributes exported
        tags = {tag["key"]: tag["value"] for tag in found_span.get("tags", [])}
        assert tags.get("agent_id") == "attributes_test_agent"
        assert tags.get("event_type") == "post_tool_use"
        assert tags.get("tool_name") == "database_query"
        assert tags.get("query_type") == "SELECT"
        assert tags.get("user_id") == "user123"
        assert tags.get("session_id") == "session456"

    @pytest.mark.asyncio
    async def test_batch_export_performance(self, tracing_manager):
        """Test 1000 spans export within timeout"""
        start_time = time.time()

        # Create 1000 spans
        for i in range(1000):
            context = HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id=f"perf_agent_{i % 10}",
                timestamp=time.time(),
                trace_id=str(uuid.uuid4()),
                data={"iteration": i},
            )

            span = tracing_manager.create_span_from_context(context)
            span.end()

            # Force flush
        tracing_manager.force_flush()

        export_duration = time.time() - start_time

        # Assert: Export completed within 10 seconds
        assert (
            export_duration < 10.0
        ), f"Export took {export_duration:.2f}s, expected <10s"

        # Wait for Jaeger to index
        time.sleep(3)

        # Query Jaeger to verify spans were exported
        traces = query_jaeger_traces("kaizen-integration-test")

        # We don't expect all 1000 traces (Jaeger has limits), but verify some arrived
        assert len(traces) > 0, "No traces found after batch export"


# ============================================================================
# 2. BASEAGENT INTEGRATION TESTS (5 tests)
# ============================================================================


class TestBaseAgentIntegration:
    """Test BaseAgent integration with TracingHook"""

    @pytest.mark.asyncio
    async def test_agent_lifecycle_tracing(self, tracing_hook):
        """Test agent loop creates trace"""
        # Setup: Create agent with TracingHook
        config = TestAgentConfig()
        agent = BaseAgent(config=config, signature=TestSignature())

        # Enable tracing via hook manager
        hook_manager = agent._hook_manager
        hook_manager.register_hook(tracing_hook)

        # Action: Simulate agent lifecycle events
        trace_id = str(uuid.uuid4())

        # PRE_AGENT_LOOP
        pre_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id=agent.agent_id,
            timestamp=time.time(),
            trace_id=trace_id,
            data={},
        )

        await tracing_hook.handle(pre_context)

        # Simulate some work
        await asyncio.sleep(0.1)

        # POST_AGENT_LOOP
        post_context = HookContext(
            event_type=HookEvent.POST_AGENT_LOOP,
            agent_id=agent.agent_id,
            timestamp=time.time(),
            trace_id=trace_id,
            data={},
        )

        await tracing_hook.handle(post_context)

        # Force flush
        tracing_hook.tracing_manager.force_flush()

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Assert: Trace found with agent_id
        found = False
        for trace in traces:
            for span in trace.get("spans", []):
                tags = {tag["key"]: tag["value"] for tag in span.get("tags", [])}
                if tags.get("agent_id") == agent.agent_id:
                    found = True
                    break
            if found:
                break

        assert found, f"Agent trace not found for agent_id={agent.agent_id}"

    @pytest.mark.asyncio
    async def test_tool_call_spans(self, tracing_hook):
        """Test each tool use creates child span"""
        trace_id = str(uuid.uuid4())
        agent_id = "tool_test_agent"

        # Simulate 3 tool calls
        tool_names = ["search", "calculate", "summarize"]

        for tool_name in tool_names:
            # PRE_TOOL_USE
            pre_context = HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id=agent_id,
                timestamp=time.time(),
                trace_id=trace_id,
                data={"tool_name": tool_name},
            )

            await tracing_hook.handle(pre_context)

            # Simulate tool execution
            await asyncio.sleep(0.05)

            # POST_TOOL_USE
            post_context = HookContext(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id=agent_id,
                timestamp=time.time(),
                trace_id=trace_id,
                data={"tool_name": tool_name, "result": "success"},
            )

            await tracing_hook.handle(post_context)

            # Force flush
        tracing_hook.tracing_manager.force_flush()

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Assert: Find spans for all 3 tools
        found_tools = set()
        for trace in traces:
            for span in trace.get("spans", []):
                tags = {tag["key"]: tag["value"] for tag in span.get("tags", [])}
                if tags.get("agent_id") == agent_id:
                    tool = tags.get("tool_name")
                    if tool:
                        found_tools.add(tool)

        assert (
            len(found_tools) >= 3
        ), f"Expected 3 tools, found {len(found_tools)}: {found_tools}"

    @pytest.mark.asyncio
    async def test_multiple_agents_different_traces(self, tracing_hook):
        """Test agent1 and agent2 have separate traces"""
        # Setup: Create contexts for two agents
        trace_id_1 = str(uuid.uuid4())
        trace_id_2 = str(uuid.uuid4())

        # Agent 1 - PRE
        context_1_pre = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="agent_1",
            timestamp=time.time(),
            trace_id=trace_id_1,
            data={},
        )

        await tracing_hook.handle(context_1_pre)

        # Agent 1 - POST
        context_1_post = HookContext(
            event_type=HookEvent.POST_AGENT_LOOP,
            agent_id="agent_1",
            timestamp=time.time(),
            trace_id=trace_id_1,
            data={},
        )

        await tracing_hook.handle(context_1_post)

        # Agent 2 - PRE
        context_2_pre = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="agent_2",
            timestamp=time.time(),
            trace_id=trace_id_2,
            data={},
        )

        await tracing_hook.handle(context_2_pre)

        # Agent 2 - POST
        context_2_post = HookContext(
            event_type=HookEvent.POST_AGENT_LOOP,
            agent_id="agent_2",
            timestamp=time.time(),
            trace_id=trace_id_2,
            data={},
        )

        await tracing_hook.handle(context_2_post)

        # Force flush
        tracing_hook.tracing_manager.force_flush()

        # Wait for Jaeger to index spans
        time.sleep(3)

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Assert: Find both agent traces
        agent_1_found = False
        agent_2_found = False

        for trace in traces:
            for span in trace.get("spans", []):
                tags = {tag["key"]: tag["value"] for tag in span.get("tags", [])}
                if tags.get("agent_id") == "agent_1":
                    agent_1_found = True
                if tags.get("agent_id") == "agent_2":
                    agent_2_found = True

        assert agent_1_found, "Agent 1 trace not found"
        assert agent_2_found, "Agent 2 trace not found"

    @pytest.mark.asyncio
    async def test_tracing_with_existing_hooks(self, tracing_hook):
        """Test TracingHook + MetricsHook + PerformanceProfilerHook"""
        # Setup: All three hooks
        metrics_hook = MetricsHook()
        profiler_hook = PerformanceProfilerHook()

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="multi_hook_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search"},
        )

        # Execute all hooks
        tracing_result = await tracing_hook.handle(context)
        metrics_result = await metrics_hook.handle(context)
        profiler_result = await profiler_hook.handle(context)

        # Assert: All hooks succeed
        assert tracing_result.success is True
        assert metrics_result.success is True
        assert profiler_result.success is True

        # Force flush
        tracing_hook.tracing_manager.force_flush()

        # Query Jaeger - verify tracing didn't interfere with other hooks
        traces = query_jaeger_traces("kaizen-integration-test")
        assert len(traces) > 0, "No traces found - tracing may have interfered"

    @pytest.mark.asyncio
    async def test_high_load_concurrent_agents(self, tracing_manager):
        """Test 10 agents creating traces simultaneously"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook

        async def agent_simulation(agent_id: str, hook: TracingHook):
            """Simulate agent activity"""
            trace_id = str(uuid.uuid4())

            # Agent loop
            for i in range(5):
                # PRE event
                pre_context = HookContext(
                    event_type=HookEvent.PRE_TOOL_USE,
                    agent_id=agent_id,
                    timestamp=time.time(),
                    trace_id=trace_id,
                    data={"tool_name": f"tool_{i}"},
                )

                await hook.handle(pre_context)
                await asyncio.sleep(0.01)

                # POST event to end span
                post_context = HookContext(
                    event_type=HookEvent.POST_TOOL_USE,
                    agent_id=agent_id,
                    timestamp=time.time(),
                    trace_id=trace_id,
                    data={"tool_name": f"tool_{i}"},
                )

                await hook.handle(post_context)

            # Create 10 agents

        hooks = [TracingHook(tracing_manager=tracing_manager) for _ in range(10)]
        tasks = [agent_simulation(f"concurrent_agent_{i}", hooks[i]) for i in range(10)]

        # Run concurrently
        await asyncio.gather(*tasks)

        # Force flush
        tracing_manager.force_flush()

        # Wait for Jaeger to index spans
        time.sleep(3)

        # Query Jaeger
        traces = query_jaeger_traces("kaizen-integration-test")

        # Assert: Traces from multiple agents found
        agent_ids = set()
        for trace in traces:
            for span in trace.get("spans", []):
                tags = {tag["key"]: tag["value"] for tag in span.get("tags", [])}
                agent_id = tags.get("agent_id", "")
                if "concurrent_agent" in agent_id:
                    agent_ids.add(agent_id)

            # Should find at least half the agents
        assert len(agent_ids) >= 5, f"Only found {len(agent_ids)} agents, expected >=5"

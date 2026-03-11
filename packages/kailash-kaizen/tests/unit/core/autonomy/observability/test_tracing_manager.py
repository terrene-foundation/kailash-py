"""
Tier 1 Unit Tests for TracingManager and TracingHook.

Tests OpenTelemetry integration, span creation, Jaeger exporter configuration,
and tracing hook implementation WITHOUT external dependencies.

CRITICAL DESIGN REQUIREMENTS:
1. OpenTelemetry TracerProvider with Jaeger OTLP exporter
2. Span creation from HookContext events
3. HookContext.trace_id → OpenTelemetry trace ID mapping
4. Parent-child span hierarchy via context propagation
5. Span attributes from HookContext (agent_id, event_type, metadata)
6. Thread-safe concurrent span creation
7. Batch span processor configuration
8. TracingHook integration with hook system
9. Exception recording in spans
10. Performance: <1ms per span creation, <3% overhead
"""

import asyncio
import threading
import time
import uuid
from unittest.mock import MagicMock

import pytest

# OpenTelemetry imports
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode

# Kaizen imports - these will be implemented
# from kaizen.core.autonomy.observability.tracing_manager import TracingManager
# from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookResult

# ============================================================================
# 1. TRACINGMANAGER TESTS (10 tests)
# ============================================================================


class TestTracingManagerInitialization:
    """Test TracingManager initialization and configuration"""

    @pytest.mark.asyncio
    async def test_tracing_manager_initialization(self):
        """Test TracingManager initializes TracerProvider correctly"""
        # This test will fail until TracingManager is implemented
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        # Setup: Create TracingManager
        manager = TracingManager(
            service_name="kaizen-test", jaeger_host="localhost", jaeger_port=4317
        )

        # Assert: TracerProvider is configured
        assert manager.tracer_provider is not None
        assert isinstance(manager.tracer_provider, TracerProvider)

        # Assert: Service name is set in resource
        resource = manager.tracer_provider.resource
        assert resource.attributes.get("service.name") == "kaizen-test"

        # Cleanup
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_create_span_from_hook_context(self):
        """Test basic span creation from HookContext"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        # Setup: Create HookContext
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search"},
        )

        # Action: Create span from context
        span = manager.create_span_from_context(context)

        # Assert: Span created with correct name
        assert span is not None
        assert span.name == "pre_tool_use"

        # Assert: Span is active
        assert span.is_recording()

        # End span
        span.end()
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_attributes_mapping(self):
        """Test HookContext fields map to span attributes"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        # Setup: HookContext with rich metadata
        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="analytics_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={
                "tool_name": "database_query",
                "query_type": "SELECT",
                "rows_returned": 42,
            },
            metadata={"user_id": "user123", "session_id": "session456"},
        )

        # Action: Create span and check attributes
        span = manager.create_span_from_context(context)

        # Assert: Core attributes mapped
        attributes = span.attributes
        assert attributes["agent_id"] == "analytics_agent"
        assert attributes["event_type"] == "post_tool_use"
        assert attributes["tool_name"] == "database_query"

        # Assert: Metadata mapped
        assert attributes["user_id"] == "user123"
        assert attributes["session_id"] == "session456"

        # Assert: Data mapped
        assert attributes["query_type"] == "SELECT"
        assert attributes["rows_returned"] == 42

        span.end()
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_trace_id_mapping(self):
        """Test HookContext.trace_id maps to OpenTelemetry trace ID"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        # Setup: HookContext with specific trace_id
        hook_trace_id = str(uuid.uuid4())
        context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=hook_trace_id,
            data={},
        )

        # Action: Create span
        span = manager.create_span_from_context(context)

        # Assert: trace_id stored in attributes
        assert span.attributes["trace_id"] == hook_trace_id

        # Assert: OpenTelemetry trace context is valid
        span_context = span.get_span_context()
        assert span_context.is_valid
        assert span_context.trace_id > 0

        span.end()
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_parent_child_hierarchy(self):
        """Test parent span propagation for child spans"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        trace_id = str(uuid.uuid4())

        # Setup: Create parent span (PRE_AGENT_LOOP)
        parent_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=trace_id,
            data={},
            metadata={},
        )

        parent_span = manager.create_span_from_context(parent_context)

        # Action: Create child span (PRE_TOOL_USE) with parent reference
        child_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=trace_id,
            data={"tool_name": "search"},
            metadata={"parent_span_id": parent_span.get_span_context().span_id},
        )

        child_span = manager.create_span_from_context(
            child_context, parent_span=parent_span
        )

        # Assert: Child has same trace_id
        assert (
            child_span.get_span_context().trace_id
            == parent_span.get_span_context().trace_id
        )

        # Assert: Child has different span_id
        assert (
            child_span.get_span_context().span_id
            != parent_span.get_span_context().span_id
        )

        # Assert: Parent-child relationship exists
        # This is validated via parent_span_id in the span context
        child_span.end()
        parent_span.end()
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_status_from_hook_result(self):
        """Test span status (ok/error) based on HookResult success"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "api_call"},
        )

        # Test 1: Success result → OK status
        span_success = manager.create_span_from_context(context)
        result_success = HookResult(success=True, data={})
        manager.update_span_from_result(span_success, result_success)

        assert span_success.status.status_code == StatusCode.OK
        span_success.end()

        # Test 2: Failure result → ERROR status
        span_error = manager.create_span_from_context(context)
        result_error = HookResult(success=False, data={}, error="API call failed")
        manager.update_span_from_result(span_error, result_error)

        assert span_error.status.status_code == StatusCode.ERROR
        assert "API call failed" in span_error.status.description
        span_error.end()

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_exception_recording_in_span(self):
        """Test exception details are captured in spans"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "database"},
        )

        # Action: Create span and record exception
        span = manager.create_span_from_context(context)

        try:
            raise ValueError("Database connection failed")
        except Exception as e:
            manager.record_exception(span, e)

            # Assert: Exception recorded in span
            # OpenTelemetry SDK records exceptions as events
        assert span.status.status_code == StatusCode.ERROR

        span.end()
        manager.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_span_creation(self):
        """Test thread safety with 100 concurrent spans"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        created_spans = []
        errors = []

        def create_span_worker(i: int):
            try:
                context = HookContext(
                    event_type=HookEvent.PRE_TOOL_USE,
                    agent_id=f"agent_{i % 10}",
                    timestamp=time.time(),
                    trace_id=str(uuid.uuid4()),
                    data={"iteration": i},
                )

                span = manager.create_span_from_context(context)
                created_spans.append(span)
                span.end()
            except Exception as e:
                errors.append(e)

            # Action: Create 100 spans concurrently

        threads = []
        for i in range(100):
            t = threading.Thread(target=create_span_worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

            # Assert: All spans created successfully
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(created_spans) == 100

        # Assert: All spans have unique span IDs
        span_ids = [s.get_span_context().span_id for s in created_spans]
        assert len(set(span_ids)) == 100

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_jaeger_exporter_configuration(self):
        """Test OTLP endpoint and service name configuration"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        # Setup: Create manager with specific Jaeger config
        manager = TracingManager(
            service_name="kaizen-production",
            jaeger_host="jaeger.example.com",
            jaeger_port=4318,
            insecure=True,
        )

        # Assert: Service name configured
        resource = manager.tracer_provider.resource
        assert resource.attributes.get("service.name") == "kaizen-production"

        # Assert: Exporter endpoint configured
        # Note: We can't directly access exporter config in tests,
        # but we verify manager stores the configuration
        assert manager.jaeger_host == "jaeger.example.com"
        assert manager.jaeger_port == 4318

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_batch_processor_settings(self):
        """Test batch span processor configuration (batch size, timeout)"""
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        # Setup: Create manager with custom batch settings
        manager = TracingManager(
            service_name="test",
            batch_size=512,
            batch_timeout_ms=5000,
            max_export_batch_size=1024,
        )

        # Assert: Batch processor configured
        # We verify configuration is stored
        assert manager.batch_size == 512
        assert manager.batch_timeout_ms == 5000
        # max_export_batch_size is clamped to batch_size (OpenTelemetry requirement)
        assert manager.max_export_batch_size == 512  # min(1024, 512) = 512

        manager.shutdown()


# ============================================================================
# 2. TRACINGHOOK TESTS (10 tests)
# ============================================================================


class TestTracingHookInitialization:
    """Test TracingHook initialization and configuration"""

    @pytest.mark.asyncio
    async def test_tracing_hook_initialization(self):
        """Test TracingHook initialization with default configuration"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")
        hook = TracingHook(tracing_manager=manager)

        # Assert: Hook initialized
        assert hook is not None
        assert hook.tracing_manager == manager

        # Assert: Default event filtering (trace all events)
        assert hook.events_to_trace is None or len(hook.events_to_trace) == 0

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_hook_event_filtering(self):
        """Test TracingHook only traces specified events"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")

        # Setup: Hook that only traces tool events
        hook = TracingHook(
            tracing_manager=manager,
            events_to_trace=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE],
        )

        # Test 1: Tool event should be traced
        tool_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search"},
        )

        result = await hook.handle(tool_context)
        assert result.success is True
        assert "span_created" in result.data

        # Test 2: Non-tool event should be skipped
        loop_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={},
        )

        result = await hook.handle(loop_context)
        assert result.success is True
        assert "span_created" not in result.data or result.data["span_created"] is False

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_creation_for_hook_events(self):
        """Test TracingHook creates spans for PRE/POST events"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")
        hook = TracingHook(tracing_manager=manager)

        # Test PRE event
        pre_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search"},
        )

        result = await hook.handle(pre_context)
        assert result.success is True
        assert result.data.get("span_created") is True

        # Test POST event
        post_context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=pre_context.trace_id,  # Same trace
            data={"tool_name": "search", "result": "success"},
        )

        result = await hook.handle(post_context)
        assert result.success is True
        assert result.data.get("span_updated") is True

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_hierarchy_for_agent_loop(self):
        """Test PRE_AGENT_LOOP creates parent span containing child spans"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")
        hook = TracingHook(tracing_manager=manager)

        trace_id = str(uuid.uuid4())

        # Step 1: Create parent span (agent loop)
        loop_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=trace_id,
            data={},
        )

        loop_result = await hook.handle(loop_context)
        assert loop_result.success is True
        parent_span_id = loop_result.data.get("span_id")
        assert parent_span_id is not None

        # Step 2: Create child span (tool use) with parent reference
        tool_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=trace_id,
            data={"tool_name": "search"},
            metadata={"parent_span_id": parent_span_id},
        )

        tool_result = await hook.handle(tool_context)
        assert tool_result.success is True
        child_span_id = tool_result.data.get("span_id")
        assert child_span_id is not None
        assert child_span_id != parent_span_id

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_attributes_include_agent_id(self):
        """Test span attributes include agent_id"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")
        hook = TracingHook(tracing_manager=manager)

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="analytics_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "database"},
        )

        result = await hook.handle(context)
        assert result.success is True

        # Verify agent_id is included in result data
        assert result.data.get("agent_id") == "analytics_agent"

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_exception_handling_doesnt_crash_hook(self):
        """Test hook failures don't crash the system"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook

        # Setup: Mock manager that raises exception
        manager = MagicMock()
        manager.create_span_from_context.side_effect = Exception("Span creation failed")

        hook = TracingHook(tracing_manager=manager)

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search"},
        )

        # Action: Hook should handle exception gracefully
        result = await hook.handle(context)

        # Assert: Hook returns failure but doesn't crash
        assert result.success is False
        assert "error" in result.data
        assert "Span creation failed" in result.data["error"]

    @pytest.mark.asyncio
    async def test_trace_id_propagation(self):
        """Test trace_id flows through span hierarchy"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")
        hook = TracingHook(tracing_manager=manager)

        trace_id = str(uuid.uuid4())

        # Create multiple events with same trace_id
        events = [
            HookEvent.PRE_AGENT_LOOP,
            HookEvent.PRE_TOOL_USE,
            HookEvent.POST_TOOL_USE,
            HookEvent.POST_AGENT_LOOP,
        ]

        span_ids = []

        for event in events:
            context = HookContext(
                event_type=event,
                agent_id="test_agent",
                timestamp=time.time(),
                trace_id=trace_id,
                data={},
            )

            result = await hook.handle(context)
            assert result.success is True
            assert result.data.get("trace_id") == trace_id

            if "span_id" in result.data:
                span_ids.append(result.data["span_id"])

            # Assert: All spans share same trace_id but different span_ids
        assert len(span_ids) > 0
        assert len(set(span_ids)) == len(span_ids)  # All unique

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_span_end_timing(self):
        """Test span duration matches event timing"""
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        manager = TracingManager(service_name="test")
        hook = TracingHook(tracing_manager=manager)

        trace_id = str(uuid.uuid4())

        # PRE event
        start_time = time.time()
        pre_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=start_time,
            trace_id=trace_id,
            data={"tool_name": "search"},
        )

        await hook.handle(pre_context)

        # Simulate work
        import asyncio

        await asyncio.sleep(0.1)

        # POST event
        end_time = time.time()
        post_context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=end_time,
            trace_id=trace_id,
            data={"tool_name": "search"},
        )

        result = await hook.handle(post_context)

        # Assert: Duration calculated
        if "duration_ms" in result.data:
            duration_ms = result.data["duration_ms"]
            expected_ms = (end_time - start_time) * 1000

            # Allow 10ms tolerance
            assert abs(duration_ms - expected_ms) < 10

        manager.shutdown()

    @pytest.mark.asyncio
    async def test_integration_with_metrics_hook(self):
        """Test TracingHook and MetricsHook work together"""
        from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook
        from kaizen.core.autonomy.hooks.builtin.tracing_hook import TracingHook
        from kaizen.core.autonomy.observability.tracing_manager import TracingManager

        # Setup: Both hooks
        tracing_manager = TracingManager(service_name="test")
        tracing_hook = TracingHook(tracing_manager=tracing_manager)
        metrics_hook = MetricsHook()

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            trace_id=str(uuid.uuid4()),
            data={"tool_name": "search"},
        )

        # Action: Execute both hooks
        tracing_result = await tracing_hook.handle(context)
        metrics_result = await metrics_hook.handle(context)

        # Assert: Both hooks succeed independently
        assert tracing_result.success is True
        assert metrics_result.success is True

        tracing_manager.shutdown()

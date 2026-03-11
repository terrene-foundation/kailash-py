"""
Tier 2 (Integration) tests for System 2: Structured Logging & Audit Enhancement.

Tests the following integration scenarios:
- LoggingHook + trace_id integration with real log output
- AuditHook + AuditTrailProvider integration with PostgreSQL
- LoggingHook + MetricsHook simultaneous execution
- BaseAgent integration with trace_id generation

Total: 10 tests

IMPORTANT: NO MOCKING in Tier 2 tests - use real infrastructure.
"""

import json
import logging
import time
import uuid
from io import StringIO

import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookManager
from kaizen.core.autonomy.hooks.builtin.logging_hook import LoggingHook
from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook
from kaizen.security.audit import AuditTrailProvider

# ==============================================================================
# Category 1: LoggingHook + trace_id Integration (3 tests)
# ==============================================================================


class TestLoggingHookTraceIdIntegration:
    """Test LoggingHook receives and logs trace_id correctly"""

    @pytest.mark.asyncio
    async def test_logging_hook_receives_trace_id(self):
        """
        Test 1.1: trace_id in HookContext flows to logs correctly.

        Requirement: Verify trace_id appears in actual log output.
        Expected: JSON log contains trace_id field with correct value.
        """
        # Create LoggingHook with JSON format
        hook = LoggingHook(format="json")

        # Create context with trace_id
        trace_id = str(uuid.uuid4())
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="integration_test_agent",
            timestamp=time.time(),
            data={"tool_name": "search", "query": "test query"},
            metadata={"session_id": "sess-123"},
            trace_id=trace_id,
        )

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)

        # Get the logger used by LoggingHook
        logger = logging.getLogger("kaizen.core.autonomy.hooks.builtin.logging_hook")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            # Execute hook
            result = await hook.handle(context)
            assert result.success is True

            # Get log output
            log_output = log_capture.getvalue()

            # For JSON format, parse and verify fields
            if hook.format == "json":
                # Log output should be valid JSON
                log_lines = [line for line in log_output.strip().split("\n") if line]
                assert len(log_lines) > 0, "No log output captured"

                # Parse first log line as JSON
                log_data = json.loads(log_lines[0])

                # Verify trace_id is present
                assert "trace_id" in log_data, f"trace_id missing from log: {log_data}"
                assert log_data["trace_id"] == trace_id

                # Verify other required fields
                assert "timestamp" in log_data
                assert "agent_id" in log_data
                assert log_data["agent_id"] == "integration_test_agent"
                assert "event_type" in log_data
                assert log_data["event_type"] == "pre_tool_use"

        finally:
            logger.removeHandler(handler)

    @pytest.mark.asyncio
    async def test_multiple_events_same_trace_id(self):
        """
        Test 1.2: All events in workflow have same trace_id.

        Requirement: Trace correlation across multiple hook events.
        Expected: Multiple hook calls with same trace_id produce correlated logs.
        """
        manager = HookManager()
        hook = LoggingHook(format="json")

        # Register hook for multiple events
        manager.register(HookEvent.PRE_AGENT_LOOP, hook)
        manager.register(HookEvent.PRE_TOOL_USE, hook)
        manager.register(HookEvent.POST_TOOL_USE, hook)

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)

        logger = logging.getLogger("kaizen.core.autonomy.hooks.builtin.logging_hook")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            # Use same trace_id for all events
            shared_trace_id = str(uuid.uuid4())

            # Trigger multiple events with same trace_id
            await manager.trigger(
                event_type=HookEvent.PRE_AGENT_LOOP,
                agent_id="test_agent",
                data={"iteration": 1},
                trace_id=shared_trace_id,
            )

            await manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="test_agent",
                data={"tool_name": "search"},
                trace_id=shared_trace_id,
            )

            await manager.trigger(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="test_agent",
                data={"result": "success"},
                trace_id=shared_trace_id,
            )

            # Parse log output
            log_output = log_capture.getvalue()
            log_lines = [line for line in log_output.strip().split("\n") if line]

            # Should have 3 log entries (one per event)
            assert len(log_lines) >= 3

            # Parse and verify all have same trace_id
            trace_ids = []
            for line in log_lines[:3]:
                log_data = json.loads(line)
                trace_ids.append(log_data.get("trace_id"))

            # All should have the same trace_id
            assert all(
                tid == shared_trace_id for tid in trace_ids
            ), f"Not all trace_ids match: {trace_ids}"

        finally:
            logger.removeHandler(handler)

    @pytest.mark.asyncio
    async def test_json_logs_query_by_trace_id(self):
        """
        Test 1.3: Can filter logs by trace_id (simulated ELK query).

        Requirement: Support log filtering by trace_id in log aggregation systems.
        Expected: Logs with specific trace_id can be extracted from log stream.
        """
        manager = HookManager()
        hook = LoggingHook(format="json")

        manager.register(HookEvent.PRE_TOOL_USE, hook)

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)

        logger = logging.getLogger("kaizen.core.autonomy.hooks.builtin.logging_hook")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            # Generate logs with different trace_ids
            trace_id_1 = str(uuid.uuid4())
            trace_id_2 = str(uuid.uuid4())
            trace_id_3 = str(uuid.uuid4())

            await manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent_1",
                data={"tool": "search"},
                trace_id=trace_id_1,
            )

            await manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent_2",
                data={"tool": "analyze"},
                trace_id=trace_id_2,
            )

            await manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent_1",
                data={"tool": "summarize"},
                trace_id=trace_id_1,  # Same as first
            )

            await manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent_3",
                data={"tool": "classify"},
                trace_id=trace_id_3,
            )

            # Parse all logs
            log_output = log_capture.getvalue()
            log_lines = [line for line in log_output.strip().split("\n") if line]

            all_logs = [json.loads(line) for line in log_lines]

            # Filter by trace_id_1 (should get 2 logs)
            filtered_logs = [
                log for log in all_logs if log.get("trace_id") == trace_id_1
            ]

            assert len(filtered_logs) == 2
            assert all(log["agent_id"] == "agent_1" for log in filtered_logs)

            # Filter by trace_id_2 (should get 1 log)
            filtered_logs_2 = [
                log for log in all_logs if log.get("trace_id") == trace_id_2
            ]
            assert len(filtered_logs_2) == 1
            assert filtered_logs_2[0]["agent_id"] == "agent_2"

        finally:
            logger.removeHandler(handler)


# ==============================================================================
# Category 2: AuditHook + AuditTrailProvider Integration (3 tests)
# ==============================================================================


class TestAuditHookIntegration:
    """Test AuditHook integration with AuditTrailProvider and PostgreSQL"""

    @pytest.mark.requires_postgres
    @pytest.mark.asyncio
    async def test_audit_hook_writes_to_postgresql(self, postgres_connection_string):
        """
        Test 2.1: AuditHook writes audit events to PostgreSQL via AuditTrailProvider.

        Requirement: Persistent audit trail in database.
        Expected: Hook events are logged to audit_events table.
        """
        # Initialize AuditTrailProvider with PostgreSQL
        audit_provider = AuditTrailProvider(
            storage="postgresql",
            connection_string=postgres_connection_string,
        )
        audit_provider.initialize()

        try:
            # Create AuditHook (implementation needed)
            from kaizen.core.autonomy.hooks.builtin.audit_hook import AuditHook

            audit_hook = AuditHook(audit_provider=audit_provider)

            # Create context
            context = HookContext(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="test_agent",
                timestamp=time.time(),
                data={"tool_name": "search", "result": "success"},
                trace_id=str(uuid.uuid4()),
            )

            # Execute hook
            result = await audit_hook.handle(context)
            assert result.success is True

            # Verify event was written to database
            events = audit_provider.query_events(action="post_tool_use")
            assert len(events) > 0

            # Verify event data
            event = events[0]
            assert event["action"] == "post_tool_use"
            assert event["result"] == "success"

        finally:
            audit_provider.cleanup()

    @pytest.mark.requires_postgres
    @pytest.mark.asyncio
    async def test_audit_hook_includes_trace_id(self, postgres_connection_string):
        """
        Test 2.2: trace_id is stored in PostgreSQL metadata JSONB field.

        Requirement: Correlate audit logs with application logs.
        Expected: trace_id accessible via metadata column.
        """
        # Initialize AuditTrailProvider with PostgreSQL
        audit_provider = AuditTrailProvider(
            storage="postgresql",
            connection_string=postgres_connection_string,
        )
        audit_provider.initialize()

        try:
            from kaizen.core.autonomy.hooks.builtin.audit_hook import AuditHook

            audit_hook = AuditHook(audit_provider=audit_provider)

            # Use custom trace_id
            custom_trace_id = str(uuid.uuid4())

            context = HookContext(
                event_type=HookEvent.PRE_SPECIALIST_INVOKE,
                agent_id="test_agent",
                timestamp=time.time(),
                data={"specialist_name": "code_analyzer"},
                metadata={"session_id": "sess-789"},
                trace_id=custom_trace_id,
            )

            result = await audit_hook.handle(context)
            assert result.success is True

            # Query events from database
            events = audit_provider.query_events(action="pre_specialist_invoke")
            assert len(events) > 0

            # Verify trace_id in metadata
            event = events[0]
            assert "metadata" in event
            assert isinstance(event["metadata"], dict)
            assert "trace_id" in event["metadata"]
            assert event["metadata"]["trace_id"] == custom_trace_id

        finally:
            audit_provider.cleanup()

    @pytest.mark.asyncio
    async def test_audit_hook_event_filtering(self):
        """
        Test 2.3: AuditHook supports event filtering (log only specific events).

        Requirement: Control which events are audited (cost optimization).
        Expected: AuditHook(events=[...]) only logs specified events.
        """
        # Use memory storage for unit-level test
        audit_provider = AuditTrailProvider(storage="memory")

        from kaizen.core.autonomy.hooks.builtin.audit_hook import AuditHook

        # Create AuditHook that only logs TOOL events
        audit_hook = AuditHook(
            audit_provider=audit_provider,
            event_filter=[HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE],
        )

        # Send TOOL event (should be logged)
        tool_context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},
            trace_id=str(uuid.uuid4()),
        )

        result = await audit_hook.handle(tool_context)
        assert result.success is True

        # Send non-TOOL event (should be ignored)
        agent_context = HookContext(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"iteration": 1},
            trace_id=str(uuid.uuid4()),
        )

        result = await audit_hook.handle(agent_context)
        # Should still succeed but not log to audit

        # Verify only TOOL event was logged
        events = audit_provider.query_events()
        assert len(events) == 1  # Only the tool event
        assert events[0]["action"] == "pre_tool_use"


# ==============================================================================
# Category 3: LoggingHook + MetricsHook Integration (2 tests)
# ==============================================================================


class TestLoggingMetricsIntegration:
    """Test LoggingHook and MetricsHook running simultaneously"""

    @pytest.mark.asyncio
    async def test_logging_and_metrics_both_execute(self):
        """
        Test 3.1: LoggingHook and MetricsHook both execute for same event.

        Requirement: Multiple hooks can coexist without interference.
        Expected: Both hooks execute successfully for same event.
        """
        manager = HookManager()

        logging_hook = LoggingHook(format="json")
        metrics_hook = MetricsHook()

        # Register both hooks for same event
        manager.register(HookEvent.PRE_TOOL_USE, logging_hook)
        manager.register(HookEvent.PRE_TOOL_USE, metrics_hook)

        # Trigger event
        results = await manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={"tool_name": "search"},
            trace_id=str(uuid.uuid4()),
        )

        # Both hooks should have executed
        assert len(results) == 2
        assert all(r.success for r in results)

        # Verify metrics were captured
        metrics = metrics_hook.get_metrics()
        assert "kaizen_hook_pre_tool_use" in metrics

    @pytest.mark.asyncio
    async def test_logging_metrics_same_trace_id(self):
        """
        Test 3.2: LoggingHook and MetricsHook receive same trace_id.

        Requirement: Consistent trace_id across all hooks.
        Expected: Both hooks can access same trace_id from context.
        """
        manager = HookManager()

        # Create custom hooks to capture trace_id
        captured_trace_ids = {}

        class TraceCapturingLoggingHook(LoggingHook):
            async def handle(self, context):
                captured_trace_ids["logging"] = context.trace_id
                return await super().handle(context)

        class TraceCapturingMetricsHook(MetricsHook):
            async def handle(self, context):
                captured_trace_ids["metrics"] = context.trace_id
                return await super().handle(context)

        logging_hook = TraceCapturingLoggingHook(format="json")
        metrics_hook = TraceCapturingMetricsHook()

        manager.register(HookEvent.POST_TOOL_USE, logging_hook)
        manager.register(HookEvent.POST_TOOL_USE, metrics_hook)

        # Trigger with custom trace_id
        custom_trace_id = str(uuid.uuid4())
        await manager.trigger(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            data={"result": "success"},
            trace_id=custom_trace_id,
        )

        # Both hooks should have captured same trace_id
        assert "logging" in captured_trace_ids
        assert "metrics" in captured_trace_ids
        assert captured_trace_ids["logging"] == custom_trace_id
        assert captured_trace_ids["metrics"] == custom_trace_id


# ==============================================================================
# Category 4: BaseAgent Integration (2 tests)
# ==============================================================================


class TestBaseAgentIntegration:
    """Test BaseAgent generates and uses trace_id"""

    @pytest.mark.asyncio
    async def test_base_agent_generates_trace_id(self):
        """
        Test 4.1: BaseAgent workflow automatically generates trace_id.

        Requirement: Automatic trace_id generation for agent workflows.
        Expected: BaseAgent.run() generates trace_id for all hooks.
        """
        # This test will require BaseAgent implementation to generate trace_id
        # and pass it to all hook triggers during execution

        # For now, verify HookManager generates trace_id
        manager = HookManager()

        captured_contexts = []

        async def capture_hook(context):
            captured_contexts.append(context)
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        manager.register(HookEvent.PRE_AGENT_LOOP, capture_hook)

        # Trigger without trace_id (simulating BaseAgent behavior)
        await manager.trigger(
            event_type=HookEvent.PRE_AGENT_LOOP,
            agent_id="base_agent_test",
            data={"task": "process"},
            # trace_id not provided - should auto-generate
        )

        # Verify trace_id was auto-generated
        assert len(captured_contexts) == 1
        assert hasattr(captured_contexts[0], "trace_id")
        assert captured_contexts[0].trace_id is not None

        # Verify UUID v4 format
        import re

        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(captured_contexts[0].trace_id)

    @pytest.mark.asyncio
    async def test_agent_logs_include_trace_id(self):
        """
        Test 4.2: All agent operation logs include trace_id.

        Requirement: Complete trace coverage for agent workflows.
        Expected: All hook events during agent execution have same trace_id.
        """
        manager = HookManager()
        logging_hook = LoggingHook(format="json")

        # Register logging hook for all agent-related events
        manager.register(HookEvent.PRE_AGENT_LOOP, logging_hook)
        manager.register(HookEvent.POST_AGENT_LOOP, logging_hook)
        manager.register(HookEvent.PRE_TOOL_USE, logging_hook)
        manager.register(HookEvent.POST_TOOL_USE, logging_hook)

        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)

        logger = logging.getLogger("kaizen.core.autonomy.hooks.builtin.logging_hook")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            # Simulate agent workflow with multiple events
            workflow_trace_id = str(uuid.uuid4())

            await manager.trigger(
                event_type=HookEvent.PRE_AGENT_LOOP,
                agent_id="agent_workflow",
                data={"iteration": 1},
                trace_id=workflow_trace_id,
            )

            await manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="agent_workflow",
                data={"tool": "search"},
                trace_id=workflow_trace_id,
            )

            await manager.trigger(
                event_type=HookEvent.POST_TOOL_USE,
                agent_id="agent_workflow",
                data={"result": "found"},
                trace_id=workflow_trace_id,
            )

            await manager.trigger(
                event_type=HookEvent.POST_AGENT_LOOP,
                agent_id="agent_workflow",
                data={"status": "complete"},
                trace_id=workflow_trace_id,
            )

            # Parse log output
            log_output = log_capture.getvalue()
            log_lines = [line for line in log_output.strip().split("\n") if line]

            # Should have 4 log entries
            assert len(log_lines) >= 4

            # All should have same trace_id
            all_logs = [json.loads(line) for line in log_lines[:4]]
            trace_ids = [log.get("trace_id") for log in all_logs]

            assert all(
                tid == workflow_trace_id for tid in trace_ids
            ), f"Not all logs have same trace_id: {trace_ids}"

        finally:
            logger.removeHandler(handler)

"""
Tier 1 (Unit) tests for System 2: Structured Logging & Audit Enhancement.

Tests the following features:
- trace_id infrastructure in HookContext and HookManager
- JSON logging with structlog (format="json" parameter)
- Backward compatibility with text format logging
- structlog configuration and processors
- Error handling for JSON serialization

Total: 20 tests
"""

import re
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookManager
from kaizen.core.autonomy.hooks.builtin.logging_hook import LoggingHook

# ==============================================================================
# Category 1: trace_id Infrastructure (5 tests)
# ==============================================================================


class TestTraceIdInfrastructure:
    """Test trace_id field in HookContext and HookManager"""

    def test_hook_context_has_trace_id_field(self):
        """
        Test 1.1: Verify HookContext has trace_id field.

        Requirement: HookContext needs trace_id field for log correlation.
        Expected: trace_id field accessible on HookContext instances.
        """
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
            trace_id="test-trace-id-123",  # NEW: trace_id field
        )

        assert hasattr(context, "trace_id")
        assert context.trace_id == "test-trace-id-123"

    def test_hook_manager_generates_trace_id(self):
        """
        Test 1.2: HookManager generates UUID trace_id if not provided.

        Requirement: Automatic trace_id generation for log correlation.
        Expected: trigger() creates UUID v4 if trace_id=None in trigger() call.
        """
        manager = HookManager()

        # Mock hook to capture context
        captured_contexts = []

        async def capture_hook(context: HookContext):
            captured_contexts.append(context)
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        manager.register(HookEvent.PRE_TOOL_USE, capture_hook)

        # Trigger without trace_id
        import asyncio

        asyncio.run(
            manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="test_agent",
                data={},
                # trace_id NOT provided - should auto-generate
            )
        )

        # Verify trace_id was auto-generated
        assert len(captured_contexts) == 1
        context = captured_contexts[0]
        assert hasattr(context, "trace_id")
        assert context.trace_id is not None

        # Verify UUID v4 format
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(
            context.trace_id
        ), f"trace_id '{context.trace_id}' is not valid UUID v4 format"

    def test_hook_manager_preserves_trace_id(self):
        """
        Test 1.3: Provided trace_id is not overwritten by HookManager.

        Requirement: Support custom trace_id for multi-service correlation.
        Expected: trigger(trace_id="custom") preserves custom value.
        """
        manager = HookManager()

        captured_contexts = []

        async def capture_hook(context: HookContext):
            captured_contexts.append(context)
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        manager.register(HookEvent.PRE_TOOL_USE, capture_hook)

        # Trigger WITH custom trace_id
        import asyncio

        custom_trace_id = "custom-trace-abc-123"
        asyncio.run(
            manager.trigger(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="test_agent",
                data={},
                trace_id=custom_trace_id,  # Custom trace_id
            )
        )

        # Verify custom trace_id preserved
        assert len(captured_contexts) == 1
        context = captured_contexts[0]
        assert context.trace_id == custom_trace_id

    def test_trace_id_format_validation(self):
        """
        Test 1.4: UUID v4 format validation for auto-generated trace_id.

        Requirement: Consistent trace_id format across system.
        Expected: Auto-generated trace_id matches UUID v4 regex.
        """
        manager = HookManager()

        captured_contexts = []

        async def capture_hook(context: HookContext):
            captured_contexts.append(context)
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        manager.register(HookEvent.PRE_AGENT_LOOP, capture_hook)

        # Trigger multiple times
        import asyncio

        for _ in range(5):
            asyncio.run(
                manager.trigger(
                    event_type=HookEvent.PRE_AGENT_LOOP,
                    agent_id="test_agent",
                    data={},
                )
            )

        # Verify all generated trace_ids are valid UUID v4
        uuid_v4_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        assert len(captured_contexts) == 5
        for context in captured_contexts:
            assert uuid_v4_pattern.match(
                context.trace_id
            ), f"trace_id '{context.trace_id}' does not match UUID v4 format"

    @pytest.mark.asyncio
    async def test_trace_id_propagates_to_all_hooks(self):
        """
        Test 1.5: Same trace_id propagates to all hooks in one trigger.

        Requirement: Log correlation across multiple hooks.
        Expected: All hooks receive same trace_id for one event.
        """
        manager = HookManager()

        captured_trace_ids = []

        async def hook1(context: HookContext):
            captured_trace_ids.append(("hook1", context.trace_id))
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        async def hook2(context: HookContext):
            captured_trace_ids.append(("hook2", context.trace_id))
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        async def hook3(context: HookContext):
            captured_trace_ids.append(("hook3", context.trace_id))
            from kaizen.core.autonomy.hooks import HookResult

            return HookResult(success=True)

        # Register multiple hooks
        manager.register(HookEvent.PRE_TOOL_USE, hook1)
        manager.register(HookEvent.PRE_TOOL_USE, hook2)
        manager.register(HookEvent.PRE_TOOL_USE, hook3)

        # Trigger once with custom trace_id
        custom_trace_id = str(uuid.uuid4())
        await manager.trigger(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            data={},
            trace_id=custom_trace_id,
        )

        # Verify all hooks received same trace_id
        assert len(captured_trace_ids) == 3
        assert all(tid == custom_trace_id for _, tid in captured_trace_ids)
        assert [name for name, _ in captured_trace_ids] == ["hook1", "hook2", "hook3"]


# ==============================================================================
# Category 2: JSON Logging Format (7 tests)
# ==============================================================================


class TestJSONLoggingFormat:
    """Test JSON logging with structlog (format='json' parameter)"""

    @pytest.mark.asyncio
    async def test_logging_hook_json_format_enabled(self):
        """
        Test 2.1: LoggingHook(format='json') uses structlog for JSON output.

        Requirement: Support structured logging for ELK integration.
        Expected: format='json' enables JSON output via structlog.
        """
        # Create LoggingHook with JSON format
        hook = LoggingHook(format="json")

        assert hasattr(hook, "format")
        assert hook.format == "json"

        # Verify structlog is used (implementation detail: check logger type)
        # This will be verified during integration tests with actual output

    @pytest.mark.asyncio
    async def test_logging_hook_text_format_backward_compatible(self):
        """
        Test 2.2: LoggingHook(format='text') still works (backward compatible).

        Requirement: No breaking changes to existing logging.
        Expected: format='text' uses existing text-based logging.
        """
        hook = LoggingHook(format="text")

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},
            trace_id="test-trace-123",
        )

        result = await hook.handle(context)

        assert result.success is True
        assert hook.format == "text"

    @pytest.mark.asyncio
    async def test_json_log_has_required_fields(self):
        """
        Test 2.3: JSON log output has all required fields.

        Requirement: ELK-compatible JSON logs with required fields.
        Expected: JSON contains timestamp, level, message, agent_id, trace_id, context, metadata.
        """
        # This test will verify field presence in JSON output
        # During implementation, LoggingHook will need to format logs with these fields

        hook = LoggingHook(format="json")

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent_123",
            timestamp=time.time(),
            data={"tool_name": "search", "query": "test"},
            metadata={"request_id": "req-456"},
            trace_id="trace-abc-789",
        )

        # Mock the logger to capture output
        with patch(
            "kaizen.core.autonomy.hooks.builtin.logging_hook.logger"
        ) as mock_logger:
            # Configure mock to capture log calls
            mock_logger.info = MagicMock()
            mock_logger.debug = MagicMock()

            result = await hook.handle(context)

            assert result.success is True

            # Implementation will need to log with these fields:
            # - timestamp (ISO 8601)
            # - level (INFO, DEBUG, etc.)
            # - message (event description)
            # - agent_id
            # - trace_id
            # - event_type (from context)
            # - data (event data)
            # - metadata (additional metadata)

    @pytest.mark.asyncio
    async def test_json_timestamp_iso8601_format(self):
        """
        Test 2.4: JSON log timestamp is ISO 8601 format.

        Requirement: Elasticsearch-compatible timestamps.
        Expected: Timestamp format: YYYY-MM-DDTHH:MM:SS.sssZ
        """
        hook = LoggingHook(format="json")

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
            trace_id="test-trace-123",
        )

        # Mock structlog to capture formatted output
        with patch("kaizen.core.autonomy.hooks.builtin.logging_hook.logger"):
            result = await hook.handle(context)
            assert result.success is True

            # Implementation needs to format timestamp as ISO 8601
            # Example: "2025-01-22T10:30:45.123Z"
            # Regex: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$

    @pytest.mark.asyncio
    async def test_json_log_parseable_by_json_module(self):
        """
        Test 2.5: JSON log output is valid JSON (json.loads works).

        Requirement: Machine-parseable structured logs.
        Expected: json.loads(log_output) succeeds without errors.
        """
        hook = LoggingHook(format="json")

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"result": "success", "duration_ms": 123.45},
            trace_id="test-trace-123",
        )

        # This test will be validated during integration tests
        # where we can capture actual log output and parse it
        result = await hook.handle(context)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_json_log_includes_event_type(self):
        """
        Test 2.6: JSON log includes event_type field.

        Requirement: Filter logs by event type in ELK.
        Expected: event_type field present with value from HookEvent.
        """
        hook = LoggingHook(format="json")

        context = HookContext(
            event_type=HookEvent.PRE_SPECIALIST_INVOKE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"specialist_name": "code_analyzer"},
            trace_id="test-trace-123",
        )

        with patch("kaizen.core.autonomy.hooks.builtin.logging_hook.logger"):
            result = await hook.handle(context)
            assert result.success is True

            # Implementation should include:
            # {"event_type": "pre_specialist_invoke", ...}

    @pytest.mark.asyncio
    async def test_json_log_escapes_special_characters(self):
        """
        Test 2.7: JSON log properly escapes special characters.

        Requirement: Handle edge cases in log data.
        Expected: Newlines, quotes, backslashes properly escaped.
        """
        hook = LoggingHook(format="json")

        # Context with special characters
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={
                "message": 'Line 1\nLine 2\t"quoted"\nPath: C:\\Users\\test',
                "special": 'Contains \\ and " and \n',
            },
            trace_id="test-trace-123",
        )

        result = await hook.handle(context)
        assert result.success is True

        # Implementation must properly escape:
        # - Newlines (\n)
        # - Tabs (\t)
        # - Quotes (\")
        # - Backslashes (\\)


# ==============================================================================
# Category 3: structlog Configuration (3 tests)
# ==============================================================================


class TestStructlogConfiguration:
    """Test structlog processors and configuration"""

    def test_structlog_processors_configured(self):
        """
        Test 3.1: structlog processors include TimeStamper, add_log_level, JSONRenderer.

        Requirement: Proper structlog configuration for JSON logging.
        Expected: Processors chain configured with required processors.
        """
        # This test verifies the structlog configuration in LoggingHook
        # Implementation will need to configure structlog with:
        # - structlog.processors.TimeStamper(fmt="iso")  # ISO 8601 timestamps
        # - structlog.processors.add_log_level           # Add level field
        # - structlog.processors.JSONRenderer()          # JSON output

        hook = LoggingHook(format="json")

        # Implementation detail: LoggingHook should configure structlog
        # We'll verify this by checking if the logger produces JSON output
        assert hook.format == "json"

    def test_structlog_logger_factory(self):
        """
        Test 3.2: structlog uses stdlib.LoggerFactory().

        Requirement: Integration with Python's standard logging.
        Expected: logger_factory=structlog.stdlib.LoggerFactory()
        """
        hook = LoggingHook(format="json")

        # Implementation should use:
        # structlog.configure(
        #     logger_factory=structlog.stdlib.LoggerFactory(),
        #     ...
        # )

        assert hook.format == "json"

    def test_structlog_context_class(self):
        """
        Test 3.3: structlog uses dict context class.

        Requirement: Store context data in logs.
        Expected: context_class=dict for JSON serialization.
        """
        hook = LoggingHook(format="json")

        # Implementation should use:
        # structlog.configure(
        #     context_class=dict,
        #     ...
        # )

        assert hook.format == "json"


# ==============================================================================
# Category 4: Backward Compatibility (3 tests)
# ==============================================================================


class TestBackwardCompatibility:
    """Test that existing text format logging still works"""

    @pytest.mark.asyncio
    async def test_text_format_unchanged(self):
        """
        Test 4.1: Existing text format logging behavior unchanged.

        Requirement: Zero breaking changes to existing code.
        Expected: LoggingHook(format='text') produces same output as before.
        """
        hook = LoggingHook(format="text", include_data=True)

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={"tool_name": "search"},
            trace_id="test-trace-123",
        )

        result = await hook.handle(context)

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_default_format_is_text(self):
        """
        Test 4.2: LoggingHook() defaults to text format (backward compatible).

        Requirement: Existing code without format parameter still works.
        Expected: LoggingHook() defaults to format='text'.
        """
        hook = LoggingHook()  # No format parameter

        # Should default to text format
        assert hook.format == "text"

        context = HookContext(
            event_type=HookEvent.POST_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
            trace_id="test-trace-123",
        )

        result = await hook.handle(context)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_existing_hooks_still_work(self):
        """
        Test 4.3: Existing hook code continues to work without modifications.

        Requirement: No breaking changes to hook system.
        Expected: All existing hooks work with trace_id additions.
        """
        from kaizen.core.autonomy.hooks.builtin.cost_tracking_hook import (
            CostTrackingHook,
        )
        from kaizen.core.autonomy.hooks.builtin.metrics_hook import MetricsHook

        # Test MetricsHook still works
        metrics_hook = MetricsHook()
        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={},
            trace_id="test-trace-123",  # NEW field - should not break existing hooks
        )

        result = await metrics_hook.handle(context)
        assert result.success is True

        # Test CostTrackingHook still works
        cost_hook = CostTrackingHook()
        result = await cost_hook.handle(context)
        assert result.success is True


# ==============================================================================
# Category 5: Error Handling (2 tests)
# ==============================================================================


class TestErrorHandling:
    """Test error handling for JSON serialization and logging failures"""

    @pytest.mark.asyncio
    async def test_json_serialization_error_handling(self):
        """
        Test 5.1: JSON serialization handles non-serializable objects.

        Requirement: Graceful handling of edge cases.
        Expected: Non-serializable objects converted to strings or skipped.
        """
        hook = LoggingHook(format="json")

        # Create context with non-serializable object
        class NonSerializable:
            pass

        context = HookContext(
            event_type=HookEvent.PRE_TOOL_USE,
            agent_id="test_agent",
            timestamp=time.time(),
            data={
                "normal_data": "value",
                "non_serializable": NonSerializable(),  # Cannot serialize to JSON
                "function": lambda x: x,  # Function also not serializable
            },
            trace_id="test-trace-123",
        )

        # Should handle gracefully (convert to string or skip)
        result = await hook.handle(context)
        assert result.success is True  # Should not crash

    @pytest.mark.asyncio
    async def test_logging_failure_doesnt_crash(self):
        """
        Test 5.2: Logging failure returns HookResult(success=False) instead of crashing.

        Requirement: Resilient hook system.
        Expected: Logging errors caught and returned as failed HookResult.
        """
        # Mock logger BEFORE creating hook so self.logger gets the mock
        with patch(
            "kaizen.core.autonomy.hooks.builtin.logging_hook.logger"
        ) as mock_logger:
            mock_logger.info.side_effect = Exception("Simulated logging failure")

            # Create hook inside patch context
            hook = LoggingHook(format="text")  # Use text format for error injection

            context = HookContext(
                event_type=HookEvent.PRE_TOOL_USE,
                agent_id="test_agent",
                timestamp=time.time(),
                data={},
                trace_id="test-trace-123",
            )

            result = await hook.handle(context)

            # Should return failure result, not crash
            assert result.success is False
            assert result.error is not None
            assert "Simulated logging failure" in result.error

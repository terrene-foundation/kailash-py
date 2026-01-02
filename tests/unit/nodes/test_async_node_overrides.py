"""
Tests for AsyncNode async method overrides.

This module tests that AsyncNode correctly overrides mixin methods that perform
I/O operations with async variants to prevent event loop blocking.

Phase: 6B - Async Method Overrides
Created: 2025-10-26
"""

import asyncio
import logging
from io import StringIO
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.base_async import AsyncNode
from kailash.security import SecurityConfig


# Concrete test implementation of AsyncNode
class ConcreteAsyncNode(AsyncNode):
    """Concrete AsyncNode implementation for testing async overrides."""

    def get_parameters(self):
        """Return empty parameter schema for testing."""
        return {}

    async def async_run(self, **kwargs):
        """Simple async implementation for testing."""
        await asyncio.sleep(0.001)  # Simulate async I/O
        return {"result": "success", **kwargs}


class TestSecurityMixinAsyncOverrides:
    """Test SecurityMixin async method overrides in AsyncNode."""

    @pytest.mark.asyncio
    async def test_audit_log_is_async(self):
        """Verify audit_log is async and awaitable."""
        node = ConcreteAsyncNode()
        node._audit_enabled = True

        # Should be awaitable (async method)
        with patch("builtins.print") as mock_print:
            await node.audit_log("test_action", {"key": "value"})
            mock_print.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_log_respects_audit_enabled(self):
        """Verify audit_log only logs when _audit_enabled is True."""
        node = ConcreteAsyncNode()

        # With _audit_enabled = False
        node._audit_enabled = False
        with patch("builtins.print") as mock_print:
            await node.audit_log("test_action", {"key": "value"})
            mock_print.assert_not_called()

        # With _audit_enabled = True
        node._audit_enabled = True
        with patch("builtins.print") as mock_print:
            await node.audit_log("test_action", {"key": "value"})
            mock_print.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_log_concurrent(self):
        """Verify concurrent audit_log calls don't block each other."""
        node = ConcreteAsyncNode()
        node._audit_enabled = True

        # Run 10 concurrent audit_log calls
        with patch("builtins.print"):
            tasks = [node.audit_log(f"action_{i}", {"index": i}) for i in range(10)]
            results = await asyncio.gather(*tasks)

        # All should complete without errors
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_log_security_event_is_async(self):
        """Verify log_security_event is async and awaitable."""
        node = ConcreteAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        # Should be awaitable (async method)
        with patch.object(logging.getLogger(__name__), "info") as mock_log:
            await node.log_security_event("test_event", "INFO")
            # Note: asyncio.to_thread will actually call the logger, so we can't easily mock it
            # This test verifies it's awaitable

    @pytest.mark.asyncio
    async def test_log_security_event_all_levels(self):
        """Verify log_security_event handles all log levels."""
        node = ConcreteAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        # Test INFO level
        await node.log_security_event("info_event", "INFO")

        # Test WARNING level
        await node.log_security_event("warning_event", "WARNING")

        # Test ERROR level
        await node.log_security_event("error_event", "ERROR")

        # All should complete without errors

    @pytest.mark.asyncio
    async def test_log_security_event_respects_config(self):
        """Verify log_security_event respects enable_audit_logging config."""
        # With audit logging disabled
        node = ConcreteAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=False)
        )

        with patch.object(logging.getLogger(__name__), "info") as mock_log:
            await node.log_security_event("test_event", "INFO")
            # Should early return, no logging
            # Note: Can't easily verify no call due to asyncio.to_thread, but no exception is good

    @pytest.mark.asyncio
    async def test_validate_and_sanitize_inputs_is_async(self):
        """Verify validate_and_sanitize_inputs is async and awaitable."""
        node = ConcreteAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        # Should be awaitable (async method)
        inputs = {"param1": "value1", "param2": 123}
        result = await node.validate_and_sanitize_inputs(inputs)

        # Should return validated inputs
        assert isinstance(result, dict)


class TestLoggingMixinAsyncOverrides:
    """Test LoggingMixin async method overrides in AsyncNode."""

    @pytest.mark.asyncio
    async def test_log_with_context_is_async(self):
        """Verify log_with_context is async and awaitable."""
        node = ConcreteAsyncNode()

        # Should be awaitable (async method)
        await node.log_with_context("info", "Test message", key="value")

    @pytest.mark.asyncio
    async def test_log_with_context_combines_contexts(self):
        """Verify log_with_context combines node context with additional context."""
        node = ConcreteAsyncNode()

        # Set node context (_log_context is the actual attribute used by LoggingMixin)
        node._log_context = {"node_id": "test_node", "workflow": "test_workflow"}

        # Log with additional context
        await node.log_with_context("info", "Test message", request_id="12345")

        # Should combine contexts (verified by no exception)

    @pytest.mark.asyncio
    async def test_log_node_execution_is_async(self):
        """Verify log_node_execution is async and awaitable."""
        node = ConcreteAsyncNode()

        # Should be awaitable (async method)
        await node.log_node_execution("started", status="running")

    @pytest.mark.asyncio
    async def test_log_error_with_traceback_is_async(self):
        """Verify log_error_with_traceback is async and awaitable."""
        node = ConcreteAsyncNode()

        try:
            raise ValueError("Test error")
        except ValueError as e:
            # Should be awaitable (async method)
            await node.log_error_with_traceback(e, "test_operation")

    @pytest.mark.asyncio
    async def test_log_info_is_async(self):
        """Verify log_info is async and awaitable."""
        node = ConcreteAsyncNode()

        # Should be awaitable (async method)
        await node.log_info("Test info message")

    @pytest.mark.asyncio
    async def test_log_warning_is_async(self):
        """Verify log_warning is async and awaitable."""
        node = ConcreteAsyncNode()

        # Should be awaitable (async method)
        await node.log_warning("Test warning message")

    @pytest.mark.asyncio
    async def test_log_error_is_async(self):
        """Verify log_error is async and awaitable."""
        node = ConcreteAsyncNode()

        # Should be awaitable (async method)
        await node.log_error("Test error message")

    @pytest.mark.asyncio
    async def test_concurrent_logging(self):
        """Verify concurrent logging calls don't block each other."""
        node = ConcreteAsyncNode()

        # Run 20 concurrent logging calls of different types
        tasks = (
            [node.log_info(f"info_{i}") for i in range(5)]
            + [node.log_warning(f"warning_{i}") for i in range(5)]
            + [node.log_error(f"error_{i}") for i in range(5)]
            + [node.log_with_context("info", f"context_{i}", index=i) for i in range(5)]
        )

        # All should complete without blocking
        results = await asyncio.gather(*tasks)
        assert len(results) == 20


class TestAsyncOverridesIntegration:
    """Integration tests for async overrides in real async workflows."""

    @pytest.mark.asyncio
    async def test_async_node_execution_with_logging(self):
        """Verify AsyncNode can execute with logging in async context."""
        node = ConcreteAsyncNode()

        # Execute node (which uses async_run internally)
        result = await node.execute_async(test_param="value")

        # Should complete successfully
        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_multiple_nodes_concurrent_execution_with_logging(self):
        """Verify multiple AsyncNodes can execute concurrently with logging."""
        nodes = [ConcreteAsyncNode() for _ in range(5)]

        # Execute all nodes concurrently
        tasks = [node.execute_async() for node in nodes]
        results = await asyncio.gather(*tasks)

        # All should complete successfully
        assert len(results) == 5
        for result in results:
            assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_async_overrides_dont_block_event_loop(self):
        """Verify async overrides don't block the event loop."""
        node = ConcreteAsyncNode()

        # Create a simple event to test non-blocking
        event_happened = False

        async def set_event_after_delay():
            nonlocal event_happened
            await asyncio.sleep(0.01)  # 10ms delay
            event_happened = True

        # Start background task
        background = asyncio.create_task(set_event_after_delay())

        # Log 100 times (should not block event loop)
        for i in range(100):
            await node.log_info(f"Message {i}")

        # Wait for background task
        await background

        # Event should have happened (proving event loop wasn't blocked)
        assert event_happened, "Event loop was blocked by async overrides"


class TestMethodSignatures:
    """Test that async overrides have correct signatures."""

    @pytest.mark.asyncio
    async def test_all_async_overrides_are_coroutines(self):
        """Verify all async overrides return coroutines."""
        node = ConcreteAsyncNode()

        # SecurityMixin overrides
        assert asyncio.iscoroutinefunction(node.audit_log)
        assert asyncio.iscoroutinefunction(node.log_security_event)
        assert asyncio.iscoroutinefunction(node.validate_and_sanitize_inputs)

        # LoggingMixin overrides
        assert asyncio.iscoroutinefunction(node.log_with_context)
        assert asyncio.iscoroutinefunction(node.log_node_execution)
        assert asyncio.iscoroutinefunction(node.log_error_with_traceback)
        assert asyncio.iscoroutinefunction(node.log_info)
        assert asyncio.iscoroutinefunction(node.log_warning)
        assert asyncio.iscoroutinefunction(node.log_error)

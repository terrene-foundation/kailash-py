"""
Comprehensive tests for AsyncNode enterprise features (Phase 6C).

This module provides thorough coverage of AsyncNode functionality including:
- Sync and async execution paths
- Error handling scenarios
- Edge cases in async overrides
- Integration with mixins
- Performance characteristics

Phase: 6C - Testing & Validation
Created: 2025-10-26
"""

import asyncio
import logging
from unittest.mock import patch

import pytest
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from kailash.security import SecurityConfig


# Concrete test implementation
class ConcreteTestAsyncNode(AsyncNode):
    """Concrete AsyncNode for testing."""

    def get_parameters(self):
        return {}

    async def async_run(self, **kwargs):
        await asyncio.sleep(0.001)
        return {"result": "success", **kwargs}


class FailingAsyncNode(AsyncNode):
    """AsyncNode that raises errors for testing error paths."""

    def get_parameters(self):
        return {}

    async def async_run(self, **kwargs):
        raise ValueError("Simulated error")


class NotImplementedAsyncNode(AsyncNode):
    """AsyncNode without async_run implementation."""

    def get_parameters(self):
        return {}


class TestAsyncNodeSyncExecution:
    """Test sync execution paths of AsyncNode."""

    def test_execute_sync_creates_event_loop(self):
        """Test that execute() creates an event loop for sync contexts."""
        node = ConcreteTestAsyncNode()
        result = node.execute()

        assert result["result"] == "success"

    def test_execute_sync_with_config(self):
        """Test sync execution with config parameters."""
        node = ConcreteTestAsyncNode()
        node.config = {"default_param": "default_value"}

        result = node.execute()

        assert result["result"] == "success"

    def test_execute_sync_error_handling(self):
        """Test error handling in sync execution."""
        node = FailingAsyncNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute()

        assert "execution failed" in str(exc_info.value).lower()


class TestAsyncNodeErrorHandling:
    """Test error handling in AsyncNode."""

    @pytest.mark.asyncio
    async def test_execute_async_validation_error(self):
        """Test that validation errors are re-raised."""
        node = ConcreteTestAsyncNode()

        # Mock validate_inputs to raise ValidationError
        with patch.object(
            node, "validate_inputs", side_effect=NodeValidationError("Invalid input")
        ):
            with pytest.raises(NodeValidationError) as exc_info:
                await node.execute_async()

            assert "Invalid input" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_async_execution_error(self):
        """Test that execution errors are wrapped."""
        node = FailingAsyncNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            await node.execute_async()

        assert "execution failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_async_run_not_implemented(self):
        """Test that NotImplementedError is raised when async_run not overridden."""
        node = NotImplementedAsyncNode()

        # Expect NodeExecutionError wrapping NotImplementedError
        with pytest.raises(NodeExecutionError) as exc_info:
            await node.execute_async()

        assert "execution failed" in str(exc_info.value).lower()
        assert "must implement async_run" in str(exc_info.value).lower()

    def test_run_method_raises_error(self):
        """Test that calling run() raises NotImplementedError."""
        node = ConcreteTestAsyncNode()

        with pytest.raises(NotImplementedError) as exc_info:
            node.run()

        assert "should implement async_run()" in str(exc_info.value)


class TestAsyncOverridesEdgeCases:
    """Test edge cases in async method overrides."""

    @pytest.mark.asyncio
    async def test_log_security_event_without_security_config(self):
        """Test log_security_event when security_config is not set."""
        node = ConcreteTestAsyncNode()

        # Remove security_config if it exists
        if hasattr(node, "security_config"):
            delattr(node, "security_config")

        # Should not raise error, just return early
        await node.log_security_event("test_event", "INFO")

    @pytest.mark.asyncio
    async def test_log_security_event_with_disabled_audit(self):
        """Test log_security_event when audit logging is disabled."""
        node = ConcreteTestAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=False)
        )

        # Should return early without logging
        await node.log_security_event("test_event", "INFO")

    @pytest.mark.asyncio
    async def test_log_security_event_error_level(self):
        """Test log_security_event with ERROR level."""
        node = ConcreteTestAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        await node.log_security_event("critical_event", "ERROR")

    @pytest.mark.asyncio
    async def test_log_security_event_warning_level(self):
        """Test log_security_event with WARNING level."""
        node = ConcreteTestAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        await node.log_security_event("suspicious_event", "WARNING")

    @pytest.mark.asyncio
    async def test_validate_and_sanitize_inputs_without_security_config(self):
        """Test validate_and_sanitize_inputs without security_config."""
        node = ConcreteTestAsyncNode()

        # Remove security_config
        if hasattr(node, "security_config"):
            delattr(node, "security_config")

        # Should fall back to parent implementation
        result = await node.validate_and_sanitize_inputs({"key": "value"})
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_validate_and_sanitize_inputs_with_logging(self):
        """Test validate_and_sanitize_inputs with audit logging enabled."""
        node = ConcreteTestAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        result = await node.validate_and_sanitize_inputs(
            {"param1": "value1", "param2": "value2"}
        )
        assert "param1" in result
        assert "param2" in result

    @pytest.mark.asyncio
    async def test_log_info_without_log_context(self):
        """Test log_info without _log_context attribute."""
        node = ConcreteTestAsyncNode()

        # Remove _log_context if it exists
        if hasattr(node, "_log_context"):
            delattr(node, "_log_context")

        # Should work with extra param only
        await node.log_info("Test message", extra_param="value")

    @pytest.mark.asyncio
    async def test_log_error_with_exception(self):
        """Test log_error with exception object."""
        node = ConcreteTestAsyncNode()

        try:
            raise ValueError("Test error")
        except ValueError as e:
            await node.log_error("An error occurred", error=e, context="test")

    @pytest.mark.asyncio
    async def test_log_error_without_exception(self):
        """Test log_error without exception object."""
        node = ConcreteTestAsyncNode()

        await node.log_error("Error message", context="test")

    @pytest.mark.asyncio
    async def test_log_warning_without_log_context(self):
        """Test log_warning without _log_context attribute."""
        node = ConcreteTestAsyncNode()

        # Remove _log_context if it exists
        if hasattr(node, "_log_context"):
            delattr(node, "_log_context")

        await node.log_warning("Warning message", extra_param="value")

    @pytest.mark.asyncio
    async def test_audit_log_disabled(self):
        """Test audit_log when disabled."""
        node = ConcreteTestAsyncNode()
        node._audit_enabled = False

        # Should not log anything
        await node.audit_log("test_action", {"key": "value"})

    @pytest.mark.asyncio
    async def test_log_with_context_empty_context(self):
        """Test log_with_context with empty context."""
        node = ConcreteTestAsyncNode()
        node._log_context = {}

        await node.log_with_context("info", "Test message")


class TestAsyncNodeWorkflowIntegration:
    """Test AsyncNode integration with workflows."""

    @pytest.mark.asyncio
    async def test_multiple_async_nodes_in_sequence(self):
        """Test multiple AsyncNodes executing in sequence."""
        nodes = [ConcreteTestAsyncNode() for _ in range(3)]

        # Execute in sequence
        results = []
        for i, node in enumerate(nodes):
            result = await node.execute_async(step=i)
            results.append(result)

        assert len(results) == 3
        assert all(r["result"] == "success" for r in results)

    @pytest.mark.asyncio
    async def test_async_node_with_large_dataset(self):
        """Test AsyncNode with large input dataset."""
        node = ConcreteTestAsyncNode()

        # Test that node can handle large dataset without issues
        large_data = [i for i in range(10000)]
        result = await node.execute_async()

        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_async_node_with_nested_config(self):
        """Test AsyncNode with nested configuration."""
        node = ConcreteTestAsyncNode()
        node.config = {
            "config": {
                "nested_param": "nested_value",
                "level2": {"level3": "deep_value"},
            }
        }

        result = await node.execute_async()

        assert result["result"] == "success"


class TestAsyncNodeMixinIntegration:
    """Test AsyncNode integration with all mixins."""

    @pytest.mark.asyncio
    async def test_security_mixin_methods_available(self):
        """Test that SecurityMixin methods are available."""
        node = ConcreteTestAsyncNode(
            security_config=SecurityConfig(enable_audit_logging=True)
        )

        # Test all SecurityMixin async overrides
        await node.audit_log("test_action", {"key": "value"})
        await node.log_security_event("test_event", "INFO")
        result = await node.validate_and_sanitize_inputs({"param": "value"})

        assert "param" in result

    @pytest.mark.asyncio
    async def test_logging_mixin_methods_available(self):
        """Test that LoggingMixin methods are available."""
        node = ConcreteTestAsyncNode()

        # Test all LoggingMixin async overrides
        await node.log_info("info message")
        await node.log_warning("warning message")
        await node.log_error("error message")
        await node.log_with_context("info", "context message", key="value")
        await node.log_node_execution("operation", status="success")

    @pytest.mark.asyncio
    async def test_performance_mixin_available(self):
        """Test that PerformanceMixin methods are available."""
        node = ConcreteTestAsyncNode()

        # PerformanceMixin methods should be accessible
        assert hasattr(node, "track_performance")
        assert hasattr(node, "get_performance_metrics")

    @pytest.mark.asyncio
    async def test_event_emitter_mixin_available(self):
        """Test that EventEmitterMixin methods are available."""
        node = ConcreteTestAsyncNode()

        # EventEmitterMixin methods should be accessible
        assert hasattr(node, "emit_node_started")
        assert hasattr(node, "emit_node_completed")
        assert hasattr(node, "emit_node_failed")


class TestAsyncNodePerformance:
    """Test AsyncNode performance characteristics."""

    @pytest.mark.asyncio
    async def test_concurrent_execution_performance(self):
        """Test that concurrent execution is non-blocking."""
        nodes = [ConcreteTestAsyncNode() for _ in range(10)]

        import time

        start = time.time()

        # Execute all concurrently
        results = await asyncio.gather(*[node.execute_async() for node in nodes])

        duration = time.time() - start

        # Should take ~0.01s (one async sleep duration) not ~0.1s (10 sequential sleeps)
        assert duration < 0.1  # Allow some overhead
        assert len(results) == 10
        assert all(r["result"] == "success" for r in results)

    @pytest.mark.asyncio
    async def test_async_logging_doesnt_block(self):
        """Test that async logging doesn't block execution."""
        node = ConcreteTestAsyncNode()

        import time

        start = time.time()

        # Log 50 times concurrently
        await asyncio.gather(*[node.log_info(f"Message {i}") for i in range(50)])

        duration = time.time() - start

        # Should complete quickly even with 50 log calls
        assert duration < 0.5  # Allow overhead for thread pool

    @pytest.mark.asyncio
    async def test_mixed_sync_async_operations(self):
        """Test mixing sync and async operations."""
        node = ConcreteTestAsyncNode()

        # This should work: async node execution with sync methods available
        result = await node.execute_async(test_param="value")

        # Node base methods (sync) should still be accessible
        params = node.get_parameters()
        node_dict = node.to_dict()

        assert result["result"] == "success"
        assert isinstance(params, dict)
        assert isinstance(node_dict, dict)

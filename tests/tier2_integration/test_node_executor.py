"""Unit tests for NodeExecutor protocol and implementations."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from kailash.nodes.transaction.node_executor import (
    MockNodeExecutor,
    NodeExecutor,
    RegistryNodeExecutor,
)


# ---------------------------------------------------------------------------
# MockNodeExecutor tests
# ---------------------------------------------------------------------------


class TestMockNodeExecutor:
    """Tests for MockNodeExecutor."""

    @pytest.fixture
    def executor(self):
        return MockNodeExecutor()

    @pytest.mark.asyncio
    async def test_default_response(self, executor):
        """Calling execute without set_response returns the default dict."""
        result = await executor.execute("SomeNode", {"key": "val"})
        assert result == {"status": "success", "node_type": "SomeNode"}

    @pytest.mark.asyncio
    async def test_set_response(self, executor):
        """set_response overrides the return value for a given node type."""
        executor.set_response("ValidationNode", {"status": "success", "valid": True})
        result = await executor.execute("ValidationNode", {"data": "x"})
        assert result == {"status": "success", "valid": True}

    @pytest.mark.asyncio
    async def test_set_failure(self, executor):
        """set_failure causes the executor to raise on that node type."""
        executor.set_failure("PaymentNode", RuntimeError("declined"))
        with pytest.raises(RuntimeError, match="declined"):
            await executor.execute("PaymentNode", {})

    @pytest.mark.asyncio
    async def test_call_history_recorded(self, executor):
        """Every call is recorded in the call history."""
        await executor.execute("A", {"x": 1}, timeout=10.0)
        await executor.execute("B", {"y": 2})
        assert len(executor.calls) == 2
        assert executor.calls[0] == {
            "node_type": "A",
            "params": {"x": 1},
            "timeout": 10.0,
        }
        assert executor.calls[1]["node_type"] == "B"

    @pytest.mark.asyncio
    async def test_call_history_is_copy(self, executor):
        """The calls property returns a copy, not the internal list."""
        await executor.execute("X", {})
        calls = executor.calls
        calls.clear()
        assert len(executor.calls) == 1  # internal list unaffected

    @pytest.mark.asyncio
    async def test_reset(self, executor):
        """reset clears responses, failures, and call history."""
        executor.set_response("A", {"ok": True})
        executor.set_failure("B", ValueError("boom"))
        await executor.execute("A", {})
        executor.reset()

        assert executor.calls == []
        # A should now return default response
        result = await executor.execute("A", {})
        assert result == {"status": "success", "node_type": "A"}
        # B should no longer raise
        result = await executor.execute("B", {})
        assert result == {"status": "success", "node_type": "B"}

    @pytest.mark.asyncio
    async def test_failure_still_records_call(self, executor):
        """Even when a call raises, it is recorded in history."""
        executor.set_failure("Fail", ValueError("err"))
        with pytest.raises(ValueError):
            await executor.execute("Fail", {"p": 1})
        assert len(executor.calls) == 1
        assert executor.calls[0]["node_type"] == "Fail"

    def test_implements_protocol(self, executor):
        """MockNodeExecutor satisfies the NodeExecutor runtime protocol."""
        assert isinstance(executor, NodeExecutor)


# ---------------------------------------------------------------------------
# RegistryNodeExecutor tests (with a mocked registry)
# ---------------------------------------------------------------------------


class TestRegistryNodeExecutor:
    """Tests for RegistryNodeExecutor with a fake registry."""

    def _make_sync_node_class(self, return_value):
        """Create a fake sync node class that returns *return_value* from run()."""
        node = MagicMock()
        node.run.return_value = return_value
        # Ensure async_run is not a coroutine function so the executor falls
        # back to the sync path.
        if hasattr(node, "async_run"):
            del node.async_run

        cls = MagicMock(return_value=node)
        return cls, node

    def _make_async_node_class(self, return_value):
        """Create a fake async node class that returns *return_value* from async_run()."""
        node = MagicMock()

        async def _async_run(**params):
            return return_value

        node.async_run = _async_run
        node.run = MagicMock()

        cls = MagicMock(return_value=node)
        return cls, node

    @pytest.mark.asyncio
    async def test_sync_node_execution(self):
        """RegistryNodeExecutor dispatches to run() for sync nodes."""
        expected = {"status": "success", "count": 42}
        cls, node = self._make_sync_node_class(expected)

        registry = MagicMock()
        registry.get.return_value = cls

        executor = RegistryNodeExecutor(registry=registry)
        result = await executor.execute("TestSyncNode", {"input": "data"})

        registry.get.assert_called_once_with("TestSyncNode")
        cls.assert_called_once_with(name="saga_TestSyncNode")
        assert result == expected

    @pytest.mark.asyncio
    async def test_async_node_execution(self):
        """RegistryNodeExecutor dispatches to async_run() for async nodes."""
        expected = {"status": "success", "processed": True}
        cls, node = self._make_async_node_class(expected)

        registry = MagicMock()
        registry.get.return_value = cls

        executor = RegistryNodeExecutor(registry=registry)
        result = await executor.execute("TestAsyncNode", {"query": "select *"})

        registry.get.assert_called_once_with("TestAsyncNode")
        assert result == expected

    @pytest.mark.asyncio
    async def test_result_normalised_to_dict(self):
        """Non-dict return values are wrapped in {'result': ...}."""
        cls, node = self._make_sync_node_class("plain string")

        registry = MagicMock()
        registry.get.return_value = cls

        executor = RegistryNodeExecutor(registry=registry)
        result = await executor.execute("StringNode", {})
        assert result == {"result": "plain string"}

    @pytest.mark.asyncio
    async def test_registry_error_propagates(self):
        """If the registry cannot find the node, the error propagates."""
        from kailash.sdk_exceptions import NodeConfigurationError

        registry = MagicMock()
        registry.get.side_effect = NodeConfigurationError("Node 'Nope' not found")

        executor = RegistryNodeExecutor(registry=registry)
        with pytest.raises(NodeConfigurationError, match="not found"):
            await executor.execute("Nope", {})

    def test_implements_protocol(self):
        """RegistryNodeExecutor satisfies the NodeExecutor runtime protocol."""
        executor = RegistryNodeExecutor()
        assert isinstance(executor, NodeExecutor)

    @pytest.mark.asyncio
    async def test_default_registry_is_node_registry(self):
        """When no registry is provided, NodeRegistry is used by default."""
        import kailash.nodes.transaction.node_executor as _ne_mod

        executor = RegistryNodeExecutor()
        assert executor._registry is _ne_mod.NodeRegistry

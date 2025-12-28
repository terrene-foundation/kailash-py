"""Test sync/async node separation."""

import asyncio
from unittest.mock import patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError


class SyncTestNode(Node):
    """Test sync node implementation."""

    def get_parameters(self):
        return {
            "input_value": NodeParameter(
                name="input_value", type=str, required=True, description="Test input"
            )
        }

    def run(self, **kwargs):
        return {"result": f"sync_{kwargs['input_value']}"}


class AsyncTestNode(AsyncNode):
    """Test async node implementation."""

    def get_parameters(self):
        return {
            "input_value": NodeParameter(
                name="input_value", type=str, required=True, description="Test input"
            )
        }

    async def async_run(self, **kwargs):
        await asyncio.sleep(0.001)  # Simulate async operation
        return {"result": f"async_{kwargs['input_value']}"}


class TestSyncAsyncSeparation:
    """Test sync/async node separation functionality."""

    def test_sync_node_execution(self):
        """Test sync node executes synchronously."""
        node = SyncTestNode()
        result = node.execute(input_value="test")
        assert result["result"] == "sync_test"

    @pytest.mark.asyncio
    async def test_async_node_execution(self):
        """Test async node executes asynchronously."""
        node = AsyncTestNode()
        result = await node.execute_async(input_value="test")
        assert result["result"] == "async_test"

    def test_sync_node_execute_compat(self):
        """Test sync node execute compatibility method."""
        node = SyncTestNode()
        result = node.execute(input_value="test")
        assert result["result"] == "sync_test"

    def test_async_node_sync_wrapper(self):
        """Test async node can be called synchronously."""
        node = AsyncTestNode()
        result = node.execute(input_value="test")
        assert result["result"] == "async_test"

    def test_sync_node_has_no_async_methods(self):
        """Test sync node doesn't have async methods by default."""
        node = SyncTestNode()
        # Should have run() method
        assert hasattr(node, "run")
        # Should not have async_run() method
        assert not hasattr(node, "async_run")

    def test_async_node_has_async_methods(self):
        """Test async node has async methods."""
        node = AsyncTestNode()
        # Should have async_run() method
        assert hasattr(node, "async_run")
        # Should have execute_async() method
        assert hasattr(node, "execute_async")

    def test_sync_node_inheritance(self):
        """Test sync node inherits from Node."""
        node = SyncTestNode()
        assert isinstance(node, Node)
        assert not isinstance(node, AsyncNode)

    def test_async_node_inheritance(self):
        """Test async node inherits from AsyncNode."""
        node = AsyncTestNode()
        assert isinstance(node, AsyncNode)
        # AsyncNode should also inherit from Node
        assert isinstance(node, Node)

    def test_parameter_caching_works_for_sync(self):
        """Test parameter caching works for sync nodes."""
        node = SyncTestNode()

        # First execution
        result1 = node.execute(input_value="cache_test")

        # Second execution with same params (should use cache)
        result2 = node.execute(input_value="cache_test")

        assert result1 == result2
        assert result1["result"] == "sync_cache_test"

    @pytest.mark.asyncio
    async def test_parameter_caching_works_for_async(self):
        """Test parameter caching works for async nodes."""
        node = AsyncTestNode()

        # First execution
        result1 = await node.execute_async(input_value="cache_test")

        # Second execution with same params (should use cache)
        result2 = await node.execute_async(input_value="cache_test")

        assert result1 == result2
        assert result1["result"] == "async_cache_test"

    def test_clear_api_contract(self):
        """Test nodes have clear API contracts."""
        sync_node = SyncTestNode()
        async_node = AsyncTestNode()

        # Both should have execute() method
        assert hasattr(sync_node, "execute")
        assert hasattr(async_node, "execute")

        # Both should have get_parameters() method
        assert hasattr(sync_node, "get_parameters")
        assert hasattr(async_node, "get_parameters")

        # Only async node should have execute_async()
        assert not hasattr(sync_node, "execute_async")
        assert hasattr(async_node, "execute_async")


class TestMigrationCompatibility:
    """Test migration compatibility features."""

    def test_old_async_detection_removed(self):
        """Test old async auto-detection is removed."""
        # This test ensures we don't accidentally re-introduce auto-detection
        node = SyncTestNode()

        # Node should not try to detect if methods are async
        # (This would be tested by checking internal implementation,
        # but for now we just ensure execution works predictably)
        result = node.execute(input_value="test")
        assert result["result"] == "sync_test"

    @pytest.mark.asyncio
    async def test_async_node_error_handling(self):
        """Test async node error handling works correctly."""

        class ErrorAsyncNode(AsyncNode):
            def get_parameters(self):
                return {}

            async def async_run(self, **kwargs):
                raise ValueError("Test error")

        node = ErrorAsyncNode()

        with pytest.raises(NodeExecutionError):
            await node.execute_async()

    def test_sync_node_error_handling(self):
        """Test sync node error handling works correctly."""

        class ErrorSyncNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                raise ValueError("Test error")

        node = ErrorSyncNode()

        with pytest.raises(NodeExecutionError):
            node.execute()


class TestPerformanceImplications:
    """Test performance implications of the separation."""

    def test_sync_node_no_async_overhead(self):
        """Test sync nodes have no async overhead."""
        import time

        node = SyncTestNode()

        # Time multiple executions
        start_time = time.time()
        for _ in range(100):
            node.execute(input_value="perf_test")
        elapsed = time.time() - start_time

        # Should be fast (less than 100ms for 100 executions)
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_async_node_concurrent_execution(self):
        """Test async nodes can run concurrently."""
        node = AsyncTestNode()

        # Run multiple async executions concurrently
        start_time = asyncio.get_event_loop().time()

        tasks = [node.execute_async(input_value=f"concurrent_{i}") for i in range(10)]

        results = await asyncio.gather(*tasks)
        elapsed = asyncio.get_event_loop().time() - start_time

        # Should be faster than sequential execution
        # (10 * 0.001s sleep should be ~0.001s concurrent vs ~0.01s sequential)
        assert elapsed < 0.01
        assert len(results) == 10

        # Check all results are correct
        for i, result in enumerate(results):
            assert result["result"] == f"async_concurrent_{i}"

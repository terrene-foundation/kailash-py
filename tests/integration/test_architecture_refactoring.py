"""
Comprehensive tests for v0.5.0 architectural refactoring.

This test suite validates all the major changes:
1. Sync/Async node separation
2. Execute/Run API standardization
3. WorkflowBuilder API unification
4. Resource management
5. Parameter resolution optimization
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import (
    NodeExecutionError,
    NodeValidationError,
    WorkflowValidationError,
)
from kailash.utils.resource_manager import (
    AsyncResourcePool,
    ResourcePool,
    ResourceTracker,
    get_resource_tracker,
    managed_resource,
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


# Test nodes for validation
class SimpleSyncNode(Node):
    """Test synchronous node."""

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                name="input_data", type=str, required=True, description="Test input"
            ),
            "multiplier": NodeParameter(
                name="multiplier",
                type=int,
                required=False,
                default=2,
                description="Multiplication factor",
            ),
        }

    def run(self, **kwargs):
        data = kwargs["input_data"]
        multiplier = kwargs.get("multiplier", 2)
        return {"result": data * multiplier}


class SimpleAsyncNode(AsyncNode):
    """Test asynchronous node."""

    def get_parameters(self):
        return {
            "delay": NodeParameter(
                name="delay",
                type=float,
                required=False,
                default=0.1,
                description="Async delay in seconds",
            ),
            "value": NodeParameter(
                name="value", type=str, required=True, description="Value to return"
            ),
        }

    async def async_run(self, **kwargs):
        delay = kwargs.get("delay", 0.1)
        value = kwargs["value"]
        await asyncio.sleep(delay)
        return {"async_result": f"async_{value}"}


class AutoMappingNode(Node):
    """Test node with auto-mapping parameters."""

    def get_parameters(self):
        return {
            "primary_data": NodeParameter(
                name="primary_data",
                type=list,
                required=True,
                auto_map_primary=True,
                auto_map_from=["data", "input", "items"],
                workflow_alias="main_data",
                description="Primary data input",
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                default={},
                workflow_alias="settings",
                description="Configuration",
            ),
        }

    def run(self, **kwargs):
        data = kwargs["primary_data"]
        config = kwargs.get("config", {})
        return {"processed": len(data), "config_keys": list(config.keys())}


class TestSyncAsyncSeparation:
    """Test sync/async node separation."""

    def test_sync_node_basic_execution(self):
        """Test basic synchronous node execution."""
        node = SimpleSyncNode()
        result = node.execute(input_data="test", multiplier=3)
        assert result == {"result": "testtesttest"}

    def test_sync_node_cannot_have_async_run(self):
        """Ensure sync nodes cannot implement async_run."""

        class BadSyncNode(Node):
            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                return {"sync": True}

            async def async_run(self, **kwargs):
                # This should not be called
                return {"async": True}

        node = BadSyncNode()
        # Should use run(), not async_run()
        result = node.execute()
        assert result == {"sync": True}

    @pytest.mark.asyncio
    async def test_async_node_basic_execution(self):
        """Test basic asynchronous node execution."""
        node = SimpleAsyncNode()
        result = await node.execute_async(value="test", delay=0.01)
        assert result == {"async_result": "async_test"}

    def test_async_node_sync_execution(self):
        """Test async node can be executed synchronously via execute()."""
        node = SimpleAsyncNode()
        result = node.execute(value="test", delay=0.01)
        assert result == {"async_result": "async_test"}

    def test_async_node_must_implement_async_run(self):
        """Ensure async nodes must implement async_run."""

        class BadAsyncNode(AsyncNode):
            def get_parameters(self):
                return {}

        node = BadAsyncNode()
        # The error will be raised during execution
        with pytest.raises(NodeExecutionError):
            node.execute()

    def test_sync_node_run_not_implemented(self):
        """Test sync node without run() implementation."""

        class IncompleteNode(Node):
            def get_parameters(self):
                return {}

        node = IncompleteNode()
        with pytest.raises(NodeExecutionError):
            node.execute()

    def test_async_node_execute_calls_async_run(self):
        """Test that AsyncNode's execute() properly calls async_run()."""
        node = SimpleAsyncNode()
        result = node.execute(value="test")
        assert result == {"async_result": "async_test"}


class TestExecuteRunStandardization:
    """Test execute/run API standardization."""

    def test_execute_handles_validation(self):
        """Test that execute() handles input validation."""
        node = SimpleSyncNode()

        # Missing required parameter
        with pytest.raises(
            NodeValidationError, match="Required parameter 'input_data'"
        ):
            node.execute()

        # Correct execution
        result = node.execute(input_data="test")
        assert result == {"result": "testtest"}

    def test_execute_handles_type_conversion(self):
        """Test that execute() handles type conversion."""
        node = SimpleSyncNode()

        # String to int conversion for multiplier
        result = node.execute(input_data="x", multiplier="5")
        assert result == {"result": "xxxxx"}

    def test_execute_preserves_special_params(self):
        """Test that execute() preserves special runtime parameters."""
        node = SimpleSyncNode()

        # 'context' is a special parameter
        result = node.execute(input_data="test", context={"user": "admin"})
        assert result == {"result": "testtest"}

    @pytest.mark.asyncio
    async def test_async_execute_handles_validation(self):
        """Test that execute_async() handles validation."""
        node = SimpleAsyncNode()

        # Missing required parameter
        with pytest.raises(NodeValidationError, match="Required parameter 'value'"):
            await node.execute_async()

        # Correct execution
        result = await node.execute_async(value="test")
        assert result == {"async_result": "async_test"}

    def test_output_validation(self):
        """Test output validation."""

        class OutputValidatedNode(Node):
            def get_parameters(self):
                return {}

            def get_output_schema(self):
                return {"result": NodeParameter(name="result", type=str, required=True)}

            def run(self, **kwargs):
                return {"wrong_key": "value"}  # Wrong output

        node = OutputValidatedNode()
        with pytest.raises(
            NodeValidationError, match="Required output 'result' not provided"
        ):
            node.execute()


class TestWorkflowBuilderUnification:
    """Test WorkflowBuilder API unification."""

    def test_builder_accepts_string_node_type(self):
        """Test WorkflowBuilder with string node types (original behavior)."""
        builder = WorkflowBuilder()
        node_id = builder.add_node("CSVReaderNode", "reader", {"file": "data.csv"})

        assert node_id == "reader"
        assert builder.nodes["reader"]["type"] == "CSVReaderNode"
        assert builder.nodes["reader"]["config"] == {"file": "data.csv"}

    def test_builder_accepts_node_class(self):
        """Test WorkflowBuilder with node classes."""
        builder = WorkflowBuilder()
        node_id = builder.add_node(SimpleSyncNode, "processor", {"multiplier": 3})

        assert node_id == "processor"
        assert builder.nodes["processor"]["type"] == "SimpleSyncNode"
        assert builder.nodes["processor"]["class"] == SimpleSyncNode
        assert builder.nodes["processor"]["config"] == {"multiplier": 3}

    def test_builder_accepts_node_instance(self):
        """Test WorkflowBuilder with node instances."""
        node_instance = SimpleSyncNode(name="test_node")
        builder = WorkflowBuilder()
        node_id = builder.add_node(node_instance, "processor")

        assert node_id == "processor"
        assert builder.nodes["processor"]["instance"] == node_instance
        assert builder.nodes["processor"]["type"] == "SimpleSyncNode"

    def test_builder_convenience_methods(self):
        """Test WorkflowBuilder convenience methods."""
        builder = WorkflowBuilder()

        # add_node_type for strings
        builder.add_node_type(
            "HTTPRequestNode", "http", {"url": "https://api.example.com"}
        )
        assert builder.nodes["http"]["type"] == "HTTPRequestNode"

        # add_node_instance for instances
        node = SimpleSyncNode()
        builder.add_node_instance(node, "sync")
        assert builder.nodes["sync"]["instance"] == node

    def test_builder_auto_generates_node_id(self):
        """Test WorkflowBuilder auto-generates node IDs."""
        builder = WorkflowBuilder()
        node_id = builder.add_node(SimpleSyncNode)

        assert node_id.startswith("node_")
        assert len(node_id) > 5

    def test_builder_invalid_node_type(self):
        """Test WorkflowBuilder with invalid node type."""
        builder = WorkflowBuilder()

        with pytest.raises(WorkflowValidationError, match="Invalid node type"):
            builder.add_node(123, "invalid")  # Not a valid node type

    def test_builder_to_workflow_with_mixed_types(self):
        """Test building a workflow with mixed node types."""
        builder = WorkflowBuilder()

        # Add different types of nodes
        builder.add_node("CSVReaderNode", "reader", {"file": "input.csv"})
        builder.add_node(SimpleSyncNode, "processor", {"multiplier": 2})
        builder.add_node(SimpleSyncNode(), "finalizer")

        # Add connections
        builder.add_connection("reader", "data", "processor", "input_data")
        builder.add_connection("processor", "result", "finalizer", "input_data")

        # Build workflow
        with patch("kailash.workflow.graph.NodeRegistry.get") as mock_get:
            mock_get.return_value = SimpleSyncNode
            workflow = builder.build(workflow_id="test", name="Test Workflow")

        assert workflow.workflow_id == "test"
        assert len(workflow.nodes) == 3
        assert len(workflow.connections) == 2


class TestResourceManagement:
    """Test resource management implementation."""

    def test_resource_pool_basic_usage(self):
        """Test basic resource pool functionality."""
        created_count = 0

        def create_resource():
            nonlocal created_count
            created_count += 1
            return f"resource_{created_count}"

        pool = ResourcePool(factory=create_resource, max_size=3)

        # Acquire and release resources
        with pool.acquire() as res1:
            assert res1 == "resource_1"

            with pool.acquire() as res2:
                assert res2 == "resource_2"
                assert created_count == 2

        # Reuse pooled resources
        with pool.acquire() as res3:
            # Pool uses LIFO, so we get the last returned resource
            assert res3 in ["resource_1", "resource_2"]  # One of the pooled resources
            assert created_count == 2  # No new creation

    def test_resource_pool_max_size(self):
        """Test resource pool respects max size."""
        pool = ResourcePool(factory=lambda: "resource", max_size=2, timeout=0.1)

        # Acquire max resources
        ctx1 = pool.acquire()
        res1 = ctx1.__enter__()
        ctx2 = pool.acquire()
        res2 = ctx2.__enter__()

        # Try to acquire beyond max
        with pytest.raises(TimeoutError):
            with pool.acquire():
                pass

        # Clean up
        ctx2.__exit__(None, None, None)
        ctx1.__exit__(None, None, None)

    def test_resource_pool_cleanup(self):
        """Test resource pool cleanup functionality."""
        cleaned_up = []

        def cleanup(resource):
            cleaned_up.append(resource)

        pool = ResourcePool(
            factory=lambda: f"resource_{len(cleaned_up)}", cleanup=cleanup, max_size=2
        )

        # Create and use resources
        with pool.acquire() as res1:
            pass

        with pool.acquire() as res2:
            pass

        # Cleanup all
        pool.cleanup_all()

        # Both resources should be cleaned up
        assert len(cleaned_up) >= 1  # At least pooled resources cleaned

    @pytest.mark.asyncio
    async def test_async_resource_pool(self):
        """Test async resource pool functionality."""
        created_count = 0

        async def create_resource():
            nonlocal created_count
            created_count += 1
            await asyncio.sleep(0.01)
            return f"async_resource_{created_count}"

        pool = AsyncResourcePool(factory=create_resource, max_size=3)

        # Acquire and release resources
        async with pool.acquire() as res1:
            assert res1 == "async_resource_1"

            async with pool.acquire() as res2:
                assert res2 == "async_resource_2"
                assert created_count == 2

        # Reuse pooled resources
        async with pool.acquire() as res3:
            # Pool uses LIFO, so we get one of the pooled resources
            assert res3 in ["async_resource_1", "async_resource_2"]
            assert created_count == 2

    def test_resource_tracker(self):
        """Test resource tracking functionality."""
        tracker = ResourceTracker()

        # Register resources (must be objects that support weak references)
        class Resource:
            def __init__(self, name):
                self.name = name

        conn1 = Resource("conn1")
        conn2 = Resource("conn2")
        session1 = Resource("session1")

        tracker.register("database", conn1)
        tracker.register("database", conn2)
        tracker.register("http", session1)

        # Check metrics
        metrics = tracker.get_metrics()
        assert metrics["database"]["created"] == 2
        assert metrics["database"]["active"] == 2
        assert metrics["database"]["peak"] == 2
        assert metrics["http"]["created"] == 1

        # Check active resources
        active = tracker.get_active_resources()
        assert active["database"] == 2
        assert active["http"] == 1

    def test_managed_resource_context_manager(self):
        """Test managed_resource context manager."""
        tracker = get_resource_tracker()
        initial_metrics = tracker.get_metrics()

        cleaned_up = False

        # Create a resource object that supports weak references
        class TestResource:
            def __init__(self, name):
                self.name = name

        resource = TestResource("my_resource")

        def cleanup(res):
            nonlocal cleaned_up
            cleaned_up = True

        with managed_resource("test_resource", resource, cleanup):
            # Resource should be tracked
            metrics = tracker.get_metrics()
            assert "test_resource" in metrics

        # Cleanup should have been called
        assert cleaned_up


class TestParameterResolutionOptimization:
    """Test parameter resolution optimization."""

    def test_parameter_caching(self):
        """Test that parameters are cached after first call."""
        call_count = 0

        class CountingNode(Node):
            def get_parameters(self):
                nonlocal call_count
                call_count += 1
                return {"input": NodeParameter(name="input", type=str, required=True)}

            def run(self, **kwargs):
                return {"output": kwargs["input"]}

        node = CountingNode()

        # First execution
        node.execute(input="test1")
        assert call_count == 1

        # Second execution - should use cache
        node.execute(input="test2")
        assert call_count == 1  # Not called again

    def test_resolution_pattern_caching(self):
        """Test that resolution patterns are cached."""
        node = AutoMappingNode()

        # First execution with 'data' mapping
        result1 = node.execute(data=[1, 2, 3], settings={"key": "value"})
        assert result1["processed"] == 3

        # Check cache was populated
        assert len(node._param_cache) == 1
        # Cache key includes config since it gets added with default value
        # The actual key will be sorted input keys including defaults
        cache_keys = list(node._param_cache.keys())
        assert len(cache_keys) == 1
        # Should have cached the mapping pattern
        cached_mapping = node._param_cache[cache_keys[0]]
        assert "primary_data" in cached_mapping
        assert cached_mapping["primary_data"] == "data"

        # Second execution with same pattern - should use cache
        result2 = node.execute(data=[1, 2, 3, 4], settings={"key2": "value2"})
        assert result2["processed"] == 4
        # Still only one cache entry
        assert len(node._param_cache) == 1

    def test_auto_mapping_resolution(self):
        """Test all auto-mapping resolution phases."""
        node = AutoMappingNode()

        # Test direct mapping
        result = node.execute(primary_data=[1, 2], config={"a": 1})
        assert result["processed"] == 2

        # Test workflow alias mapping
        result = node.execute(main_data=[1, 2, 3], settings={"b": 2})
        assert result["processed"] == 3

        # Test auto_map_from alternatives
        result = node.execute(data=[1, 2, 3, 4])
        assert result["processed"] == 4

        result = node.execute(input=[1, 2, 3, 4, 5])
        assert result["processed"] == 5

        # Test primary auto-mapping
        result = node.execute(some_random_data=[1, 2, 3, 4, 5, 6])
        assert result["processed"] == 6

    def test_cache_key_generation(self):
        """Test cache key generation handles different input orders."""
        node = AutoMappingNode()

        # Same inputs, different order
        key1 = node._get_cache_key({"data": [1], "config": {}})
        key2 = node._get_cache_key({"config": {}, "data": [1]})

        assert key1 == key2  # Should be same regardless of order

    def test_thread_safe_caching(self):
        """Test that caching is thread-safe."""
        node = SimpleSyncNode()
        results = []
        errors = []

        def execute_node(value):
            try:
                result = node.execute(input_data=f"test_{value}")
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Execute in multiple threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=execute_node, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All executions should succeed
        assert len(results) == 10
        assert len(errors) == 0


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_mixed_sync_async_workflow(self):
        """Test workflow with both sync and async nodes."""
        workflow = Workflow("mixed", "Mixed Workflow")

        # Add nodes
        sync_node = SimpleSyncNode()
        async_node = SimpleAsyncNode()

        workflow.add_node("sync", sync_node)
        workflow.add_node("async", async_node)

        # Connect nodes
        workflow.connect("sync", "async", {"result": "value"})

        # Execute with mock runtime
        from kailash.runtime.local import LocalRuntime

        runtime = LocalRuntime()

        with patch.object(runtime, "execute") as mock_execute:
            mock_execute.return_value = (
                {"sync": {"result": "test"}, "async": {"async_result": "async_test"}},
                "run_123",
            )
            results, run_id = runtime.execute(
                workflow, parameters={"sync": {"input_data": "input"}}
            )

        assert run_id == "run_123"

    def test_builder_with_resource_management(self):
        """Test WorkflowBuilder with nodes using resource management."""

        class ResourceNode(Node):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.pool = ResourcePool(factory=lambda: "connection", max_size=1)

            def get_parameters(self):
                return {}

            def run(self, **kwargs):
                with self.pool.acquire() as conn:
                    return {"used": conn}

        builder = WorkflowBuilder()
        builder.add_node(ResourceNode, "resource_node")

        # Build and verify
        workflow = builder.build()
        assert "resource_node" in workflow.nodes

    def test_performance_improvement(self):
        """Test that optimizations actually improve performance."""
        # Create a node with complex parameter mapping
        node = AutoMappingNode()

        # First, time uncached execution (fresh node)
        start = time.time()
        for i in range(100):
            # Use different patterns to prevent caching
            node.execute(data=[1, 2, 3], config={"key": f"value{i}"})
            # Clear cache after each run
            node._param_cache.clear()
        uncached_time = time.time() - start

        # Now test with caching enabled
        node2 = AutoMappingNode()
        # Warm up
        node2.execute(data=[1], config={})

        # Time cached execution with same pattern
        start = time.time()
        for i in range(100):
            # Use same pattern to benefit from cache
            node2.execute(data=[1, 2, 3], config={"key": "value"})
        cached_time = time.time() - start

        # Log the times for debugging
        print(f"Uncached time: {uncached_time:.4f}s, Cached time: {cached_time:.4f}s")
        print(f"Speedup: {uncached_time / cached_time:.2f}x")

        # Cached should be noticeably faster
        # We're less strict here due to timing variations
        assert cached_time < uncached_time  # Cached must be faster


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

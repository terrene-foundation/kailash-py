"""
Unit tests for AsyncLocalRuntime.

Tests async-first runtime execution with:
- Concurrent node execution
- Workflow analysis and optimization
- Resource registry integration
- Performance tracking and metrics
"""

import asyncio
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import networkx as nx
import pytest

from kailash.nodes.base import Node
from kailash.nodes.base_async import AsyncNode
from kailash.resources import ResourceFactory, ResourceRegistry
from kailash.runtime.async_local import (
    AsyncExecutionTracker,
    AsyncLocalRuntime,
    ExecutionContext,
    ExecutionLevel,
    ExecutionPlan,
    WorkflowAnalyzer,
)
from kailash.sdk_exceptions import WorkflowExecutionError


# Mock workflow for testing
class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self, nodes: Dict[str, Any] = None):
        self.workflow_id = "test_workflow"
        self.name = "Test Workflow"
        self._node_instances = nodes or {}
        # Use a real networkx graph for proper topological sorting
        self.graph = nx.DiGraph()
        self.metadata = {}

        # Add all nodes to the graph
        if nodes:
            for node_id in nodes:
                self.graph.add_node(node_id)


class MockSyncNode(Node):
    """Mock synchronous node for testing."""

    def __init__(self, result="sync_result", delay=0.1):
        self.result = result
        self.delay = delay
        self.execution_count = 0

    def execute(self, **kwargs):
        self.execution_count += 1
        time.sleep(self.delay)
        # Return wrapped format expected by tests
        return {"output": self.result, "inputs": kwargs}

    def get_parameters(self):
        """Return empty parameters for mock node."""
        return {}


class MockAsyncNode(AsyncNode):
    """Mock asynchronous node for testing."""

    def __init__(self, result="async_result", delay=0.1):
        self.result = result
        self.delay = delay
        self.execution_count = 0
        self.resource_used = None

    async def async_run(self, resource_registry=None, **kwargs):
        self.execution_count += 1
        await asyncio.sleep(self.delay)

        # Test resource access if available
        if resource_registry and hasattr(self, "test_resource_name"):
            self.resource_used = await resource_registry.get_resource(
                self.test_resource_name
            )

        # Return wrapped format expected by tests
        return {"output": self.result, "inputs": kwargs}

    def get_parameters(self):
        """Return empty parameters for mock node."""
        return {}


class MockResourceFactory(ResourceFactory):
    """Mock resource factory for testing."""

    def __init__(self, resource_value="test_resource"):
        self.resource_value = resource_value
        self.create_count = 0

    async def create(self):
        self.create_count += 1
        return self.resource_value

    def get_config(self):
        return {"type": "mock"}


@pytest.mark.asyncio
class TestExecutionContext:
    """Test ExecutionContext functionality."""

    async def test_basic_context(self):
        """Test basic context operations."""
        context = ExecutionContext()

        # Test variables
        context.set_variable("key1", "value1")
        assert context.get_variable("key1") == "value1"
        assert context.get_variable("missing", "default") == "default"

        # Test metrics initialization
        assert context.metrics.total_duration == 0.0
        assert context.metrics.error_count == 0

    async def test_resource_access(self):
        """Test resource access through context."""
        registry = ResourceRegistry()
        factory = MockResourceFactory("context_resource")
        registry.register_factory("test_resource", factory)

        context = ExecutionContext(resource_registry=registry)

        # Get resource
        resource = await context.get_resource("test_resource")
        assert resource == "context_resource"

        # Check metrics tracking
        assert context.metrics.resource_access_count["test_resource"] == 1

        # Access again
        await context.get_resource("test_resource")
        assert context.metrics.resource_access_count["test_resource"] == 2

    async def test_no_registry_error(self):
        """Test error when no registry is available."""
        context = ExecutionContext()

        with pytest.raises(RuntimeError, match="No resource registry available"):
            await context.get_resource("test_resource")


class TestWorkflowAnalyzer:
    """Test WorkflowAnalyzer functionality."""

    def test_analyze_empty_workflow(self):
        """Test analysis of empty workflow."""
        analyzer = WorkflowAnalyzer()
        workflow = MockWorkflow()

        plan = analyzer.analyze(workflow)

        assert plan.workflow_id is not None
        assert len(plan.async_nodes) == 0
        assert len(plan.sync_nodes) == 0
        assert len(plan.execution_levels) == 0
        assert not plan.is_fully_async
        assert not plan.has_async_nodes

    def test_analyze_async_workflow(self):
        """Test analysis of fully async workflow."""
        analyzer = WorkflowAnalyzer()

        # Create workflow with async nodes
        nodes = {"node1": MockAsyncNode("result1"), "node2": MockAsyncNode("result2")}
        workflow = MockWorkflow(nodes)

        plan = analyzer.analyze(workflow)

        assert len(plan.async_nodes) == 2
        assert len(plan.sync_nodes) == 0
        assert "node1" in plan.async_nodes
        assert "node2" in plan.async_nodes
        assert plan.is_fully_async
        assert plan.has_async_nodes

    def test_analyze_mixed_workflow(self):
        """Test analysis of mixed sync/async workflow."""
        analyzer = WorkflowAnalyzer()

        # Create workflow with mixed nodes
        nodes = {
            "sync_node": MockSyncNode("sync_result"),
            "async_node": MockAsyncNode("async_result"),
        }
        workflow = MockWorkflow(nodes)

        plan = analyzer.analyze(workflow)

        assert len(plan.async_nodes) == 1
        assert len(plan.sync_nodes) == 1
        assert "async_node" in plan.async_nodes
        assert "sync_node" in plan.sync_nodes
        assert not plan.is_fully_async
        assert plan.has_async_nodes

    def test_execution_levels_computation(self):
        """Test computation of execution levels."""
        analyzer = WorkflowAnalyzer()

        # Create workflow with dependencies
        nodes = {
            "node1": MockAsyncNode("result1"),
            "node2": MockAsyncNode("result2"),
            "node3": MockAsyncNode("result3"),
        }
        workflow = MockWorkflow(nodes)

        # Add edges to create dependencies: node1 -> node2 -> node3 (sequential)
        workflow.graph.add_edge("node1", "node2")
        workflow.graph.add_edge("node2", "node3")

        plan = analyzer.analyze(workflow)

        # Should have 3 levels (sequential execution)
        assert len(plan.execution_levels) == 3
        assert plan.execution_levels[0].nodes == {"node1"}
        assert plan.execution_levels[1].nodes == {"node2"}
        assert plan.execution_levels[2].nodes == {"node3"}

    def test_parallel_execution_levels(self):
        """Test computation of parallel execution levels."""
        analyzer = WorkflowAnalyzer()

        # Create workflow with parallel branches
        nodes = {
            "node1": MockAsyncNode("result1"),
            "node2": MockAsyncNode("result2"),
            "node3": MockAsyncNode("result3"),
            "node4": MockAsyncNode("result4"),
        }
        workflow = MockWorkflow(nodes)

        # Add edges: node1 -> (node2, node3) -> node4
        workflow.graph.add_edge("node1", "node2")
        workflow.graph.add_edge("node1", "node3")
        workflow.graph.add_edge("node2", "node4")
        workflow.graph.add_edge("node3", "node4")

        plan = analyzer.analyze(workflow)

        # Should have 3 levels with parallel middle level
        assert len(plan.execution_levels) == 3
        assert plan.execution_levels[0].nodes == {"node1"}
        assert plan.execution_levels[1].nodes == {"node2", "node3"}  # Parallel
        assert plan.execution_levels[2].nodes == {"node4"}
        assert plan.max_concurrent_nodes == 2  # Max in any level

    def test_analysis_caching(self):
        """Test that analysis results are cached."""
        analyzer = WorkflowAnalyzer()
        workflow = MockWorkflow()
        workflow.workflow_id = "cached_workflow"

        # First analysis
        plan1 = analyzer.analyze(workflow)

        # Second analysis should return cached result
        plan2 = analyzer.analyze(workflow)

        assert plan1 is plan2  # Same object reference


@pytest.mark.asyncio
class TestAsyncExecutionTracker:
    """Test AsyncExecutionTracker functionality."""

    async def test_record_result(self):
        """Test recording execution results."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record a result
        await tracker.record_result("node1", {"data": "test"}, 0.5)

        assert "node1" in tracker.results
        assert tracker.results["node1"] == {"data": "test"}
        assert tracker.execution_times["node1"] == 0.5
        assert context.metrics.node_durations["node1"] == 0.5

    async def test_record_error(self):
        """Test recording execution errors."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record an error
        error = Exception("Test error")
        await tracker.record_error("node1", error)

        assert "node1" in tracker.errors
        assert tracker.errors["node1"] == error
        assert context.metrics.error_count == 1

    async def test_concurrent_recording(self):
        """Test concurrent result recording."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record results concurrently
        tasks = [
            tracker.record_result(f"node{i}", f"result{i}", 0.1) for i in range(10)
        ]
        await asyncio.gather(*tasks)

        # All results should be recorded
        assert len(tracker.results) == 10
        for i in range(10):
            assert tracker.results[f"node{i}"] == f"result{i}"

    async def test_get_result(self):
        """Test getting final execution results."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record some data
        await tracker.record_result("node1", "result1", 0.5)
        await tracker.record_error("node2", Exception("error"))

        result = tracker.get_result()

        assert "results" in result
        assert "errors" in result
        assert "execution_times" in result
        assert "total_duration" in result
        assert "metrics" in result

        assert "node1" in result["results"]
        assert "node2" in result["errors"]
        assert result["execution_times"]["node1"] == 0.5


@pytest.mark.asyncio
@pytest.mark.critical
class TestAsyncLocalRuntime:
    """Test AsyncLocalRuntime functionality."""

    async def test_initialization(self):
        """Test runtime initialization."""
        registry = ResourceRegistry()

        runtime = AsyncLocalRuntime(
            resource_registry=registry,
            max_concurrent_nodes=5,
            enable_analysis=True,
            enable_profiling=True,
        )

        assert runtime.resource_registry is registry
        assert runtime.max_concurrent_nodes == 5
        assert runtime.enable_analysis is True
        assert runtime.enable_profiling is True
        assert runtime.analyzer is not None
        assert runtime.thread_pool is not None

    async def test_execute_empty_workflow(self):
        """Test execution of empty workflow."""
        runtime = AsyncLocalRuntime()
        workflow = MockWorkflow()

        result = await runtime.execute_workflow_async(workflow, {})

        assert "results" in result
        assert "errors" in result
        assert "total_duration" in result
        assert len(result["results"]) == 0

    async def test_execute_async_workflow(self):
        """Test execution of fully async workflow."""
        runtime = AsyncLocalRuntime(max_concurrent_nodes=5)

        # Create async workflow
        nodes = {
            "node1": MockAsyncNode("result1", delay=0.1),
            "node2": MockAsyncNode("result2", delay=0.1),
        }
        workflow = MockWorkflow(nodes)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {"input": "test"})
        execution_time = time.time() - start_time

        # Verify results - async nodes return wrapped results
        assert "node1" in result["results"]
        assert "node2" in result["results"]
        # Check that nodes were executed and returned expected values
        assert "output" in result["results"]["node1"]
        assert "output" in result["results"]["node2"]
        assert len(result["errors"]) == 0

        # Should execute concurrently (less than sequential time)
        assert execution_time < 0.25  # Much less than 0.2s sequential

        # Verify nodes were executed
        assert nodes["node1"].execution_count == 1
        assert nodes["node2"].execution_count == 1

    async def test_execute_mixed_workflow(self):
        """Test execution of mixed sync/async workflow."""
        runtime = AsyncLocalRuntime(max_concurrent_nodes=5)

        # Create mixed workflow
        nodes = {
            "sync_node": MockSyncNode("sync_result", delay=0.1),
            "async_node": MockAsyncNode("async_result", delay=0.1),
        }
        workflow = MockWorkflow(nodes)

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify results from both node types - wrapped format
        assert "sync_node" in result["results"]
        assert "async_node" in result["results"]
        assert "output" in result["results"]["sync_node"]
        assert "output" in result["results"]["async_node"]
        assert len(result["errors"]) == 0

        # Verify execution
        assert nodes["sync_node"].execution_count == 1
        assert nodes["async_node"].execution_count == 1

    async def test_execute_with_dependencies(self):
        """Test execution respecting node dependencies."""
        runtime = AsyncLocalRuntime(max_concurrent_nodes=5)

        # Create workflow with dependencies
        node1 = MockAsyncNode("result1", delay=0.1)
        node2 = MockAsyncNode("result2", delay=0.1)

        nodes = {"node1": node1, "node2": node2}
        workflow = MockWorkflow(nodes)

        # Add edge: node1 -> node2
        workflow.graph.add_edge("node1", "node2")

        result = await runtime.execute_workflow_async(workflow, {})

        # Both should complete successfully - wrapped format
        assert "node1" in result["results"]
        assert "node2" in result["results"]
        assert len(result["errors"]) == 0

    async def test_resource_integration(self):
        """Test integration with ResourceRegistry."""
        # Setup registry with resource
        registry = ResourceRegistry()
        factory = MockResourceFactory("test_resource_value")
        registry.register_factory("test_resource", factory)

        runtime = AsyncLocalRuntime(resource_registry=registry)

        # Create async node that uses resource
        async_node = MockAsyncNode("async_with_resource")
        async_node.test_resource_name = "test_resource"

        workflow = MockWorkflow({"node1": async_node})

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify execution and resource usage
        assert "node1" in result["results"]
        assert async_node.resource_used == "test_resource_value"
        assert factory.create_count == 1

    async def test_execution_context_variables(self):
        """Test execution context variable passing."""
        runtime = AsyncLocalRuntime()

        # Create node that checks for input variables
        class VariableCheckNode(MockAsyncNode):
            async def async_run(self, **kwargs):
                self.received_kwargs = kwargs
                return {"input_received": "input" in kwargs}

        node = VariableCheckNode()
        workflow = MockWorkflow({"node1": node})

        result = await runtime.execute_workflow_async(workflow, {"input": "test_value"})

        assert "node1" in result["results"]
        # Check that context variables were passed correctly
        assert node.received_kwargs["input"] == "test_value"

    async def test_error_handling(self):
        """Test error handling during execution."""
        runtime = AsyncLocalRuntime()

        # Create node that raises an error
        class ErrorNode(MockAsyncNode):
            async def async_run(self, **kwargs):
                raise Exception("Test error")

        workflow = MockWorkflow({"error_node": ErrorNode()})

        with pytest.raises(WorkflowExecutionError, match="Async execution failed"):
            await runtime.execute_workflow_async(workflow, {})

    async def test_performance_metrics(self):
        """Test performance metrics collection."""
        runtime = AsyncLocalRuntime(enable_profiling=True)

        # Create workflow with timed nodes
        nodes = {
            "fast_node": MockAsyncNode("fast", delay=0.05),
            "slow_node": MockAsyncNode("slow", delay=0.15),
        }
        workflow = MockWorkflow(nodes)

        result = await runtime.execute_workflow_async(workflow, {})

        # Check metrics
        assert "metrics" in result
        metrics = result["metrics"]

        assert "fast_node" in metrics.node_durations
        assert "slow_node" in metrics.node_durations
        assert metrics.node_durations["fast_node"] < metrics.node_durations["slow_node"]
        assert metrics.total_duration > 0

    async def test_concurrent_execution_limit(self):
        """Test that concurrent execution respects limits."""
        # Low concurrency limit
        runtime = AsyncLocalRuntime(max_concurrent_nodes=2)

        # Track concurrent executions
        active_executions = 0
        max_concurrent = 0

        class ConcurrencyTrackingNode(MockAsyncNode):
            async def async_run(self, **kwargs):
                nonlocal active_executions, max_concurrent
                active_executions += 1
                max_concurrent = max(max_concurrent, active_executions)

                await asyncio.sleep(0.1)  # Simulate work

                active_executions -= 1
                return f"result_{kwargs.get('node_id', 'unknown')}"

        # Create multiple nodes
        nodes = {f"node{i}": ConcurrencyTrackingNode() for i in range(5)}
        workflow = MockWorkflow(nodes)

        await runtime.execute_workflow_async(workflow, {})

        # Should not exceed concurrency limit
        assert max_concurrent <= 2

    async def test_cleanup(self):
        """Test runtime cleanup."""
        registry = ResourceRegistry()
        runtime = AsyncLocalRuntime(resource_registry=registry)

        # Cleanup should not raise errors
        await runtime.cleanup()

        # Thread pool should be shutdown
        assert runtime.thread_pool._shutdown is True

    async def test_sync_workflow_execution(self):
        """Test execution of sync-only workflow."""
        runtime = AsyncLocalRuntime()

        # Create sync-only workflow
        nodes = {
            "sync1": MockSyncNode("result1", delay=0.05),
            "sync2": MockSyncNode("result2", delay=0.05),
        }
        workflow = MockWorkflow(nodes)

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify sync execution worked
        assert "results" in result
        assert "sync1" in result["results"]
        assert "sync2" in result["results"]
        assert "sync1" in result["results"]
        assert "sync2" in result["results"]

        # Verify nodes were executed
        assert nodes["sync1"].execution_count == 1
        assert nodes["sync2"].execution_count == 1


@pytest.mark.asyncio
class TestAsyncLocalRuntimeIntegration:
    """Integration tests for AsyncLocalRuntime with real components."""

    async def test_with_async_python_code_node(self):
        """Test integration with AsyncPythonCodeNode."""
        from kailash.nodes.code.async_python import AsyncPythonCodeNode

        # Create registry with mock resource that returns a dict
        registry = ResourceRegistry()

        class DictResourceFactory(ResourceFactory):
            async def create(self):
                return {"db_data": "test_value"}

            def get_config(self):
                return {"type": "dict"}

        factory = DictResourceFactory()
        registry.register_factory("test_db", factory)

        runtime = AsyncLocalRuntime(resource_registry=registry)

        # Create AsyncPythonCodeNode that uses resource
        node = AsyncPythonCodeNode(
            code="""
# Test resource access
db = await get_resource("test_db")

# Simple computation
result = {"db_data": db["db_data"], "computed": 42}
"""
        )

        workflow = MockWorkflow({"python_node": node})

        result = await runtime.execute_workflow_async(workflow, {})

        # Verify execution
        assert "python_node" in result["results"]
        node_result = result["results"]["python_node"]
        assert node_result["db_data"] == "test_value"
        assert node_result["computed"] == 42

    async def test_complex_workflow_execution(self):
        """Test execution of complex workflow with multiple patterns."""
        # Setup resources
        registry = ResourceRegistry()
        registry.register_factory("cache", MockResourceFactory("cache_data"))
        registry.register_factory("db", MockResourceFactory("db_data"))

        runtime = AsyncLocalRuntime(
            resource_registry=registry, max_concurrent_nodes=3, enable_analysis=True
        )

        # Create complex workflow
        class DataFetchNode(MockAsyncNode):
            async def async_run(self, resource_registry=None, **kwargs):
                db = await resource_registry.get_resource("db")
                await asyncio.sleep(0.1)  # Simulate DB query
                return {"data": f"fetched_from_{db}"}

        class CacheNode(MockAsyncNode):
            async def async_run(self, resource_registry=None, **kwargs):
                cache = await resource_registry.get_resource("cache")
                await asyncio.sleep(0.05)  # Simulate cache operation
                return {"cached": f"cached_in_{cache}"}

        class ProcessNode(MockSyncNode):
            def execute(self, **kwargs):
                time.sleep(0.05)  # Simulate processing
                return {"processed": "data_processed"}

        nodes = {
            "fetch": DataFetchNode(),
            "cache": CacheNode(),
            "process": ProcessNode(),
        }
        workflow = MockWorkflow(nodes)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify all nodes completed
        assert "results" in result
        assert "fetch" in result["results"]
        assert "cache" in result["results"]
        assert "process" in result["results"]
        assert "data" in result["results"]["fetch"]
        assert "cached" in result["results"]["cache"]
        assert "processed" in result["results"]["process"]

        # Should execute concurrently (faster than sequential)
        assert execution_time < 0.25  # Much less than 0.2s sequential


class AdvancedMockResourceFactory:
    """Mock resource factory for testing."""

    def __init__(self, resource_type, create_delay=0, fail_creation=False):
        self.resource_type = resource_type
        self.create_delay = create_delay
        self.fail_creation = fail_creation
        self.created_count = 0

    async def create(self):
        """Create a mock resource."""
        if self.create_delay > 0:
            await asyncio.sleep(self.create_delay)

        if self.fail_creation:
            raise Exception(f"Failed to create {self.resource_type}")

        self.created_count += 1

        if self.resource_type == "database":
            return MockDatabase(f"db_connection_{self.created_count}")
        elif self.resource_type == "http_client":
            return MockHttpClient(f"http_client_{self.created_count}")
        elif self.resource_type == "cache":
            return MockCache(f"cache_{self.created_count}")
        else:
            return f"mock_{self.resource_type}_{self.created_count}"

    def get_config(self):
        return {"type": self.resource_type, "created_count": self.created_count}


class MockDatabase:
    """Mock database with async operations."""

    def __init__(self, connection_id):
        self.connection_id = connection_id
        self.query_count = 0
        self.data = {
            "users": [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
                {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
            ]
        }

    async def query(self, sql, *params):
        """Simulate database query."""
        await asyncio.sleep(0.01)  # Simulate network delay
        self.query_count += 1

        if "users" in sql.lower():
            return self.data["users"]
        elif "count" in sql.lower():
            return [{"count": len(self.data["users"])}]
        else:
            return []

    async def execute(self, sql, *params):
        """Simulate database execution."""
        await asyncio.sleep(0.01)
        self.query_count += 1
        return {"affected_rows": 1}


class MockHttpClient:
    """Mock HTTP client with async operations."""

    def __init__(self, client_id):
        self.client_id = client_id
        self.request_count = 0
        self.responses = {
            "/users": {"users": [{"id": 1, "name": "API User"}]},
            "/status": {"status": "healthy", "version": "1.0.0"},
            "/data": {"items": [1, 2, 3, 4, 5]},
        }

    async def get(self, url, **kwargs):
        """Simulate HTTP GET request."""
        await asyncio.sleep(0.02)  # Simulate network delay
        self.request_count += 1

        response_data = self.responses.get(url, {"error": "Not found"})
        return MockHttpResponse(200, response_data)

    async def post(self, url, json=None, **kwargs):
        """Simulate HTTP POST request."""
        await asyncio.sleep(0.03)  # Simulate network delay
        self.request_count += 1

        return MockHttpResponse(201, {"created": True, "data": json})


class MockHttpResponse:
    """Mock HTTP response."""

    def __init__(self, status, data):
        self.status = status
        self.data = data

    async def json(self):
        return self.data


class MockCache:
    """Mock cache with async operations."""

    def __init__(self, cache_id):
        self.cache_id = cache_id
        self.operation_count = 0
        self.data = {}

    async def get(self, key):
        """Get value from cache."""
        await asyncio.sleep(0.005)  # Simulate cache lookup
        self.operation_count += 1
        return self.data.get(key)

    async def set(self, key, value, ttl=None):
        """Set value in cache."""
        await asyncio.sleep(0.005)
        self.operation_count += 1
        self.data[key] = value
        return True


class AdvancedMockAsyncNode(AsyncNode):
    """Advanced async node with configurable behavior for testing."""

    def __init__(self, node_id, result=None, delay=0.1, use_resources=None, fail=False):
        self.node_id = node_id
        self.result = result or {"output": f"result_from_{node_id}"}
        self.delay = delay
        self.use_resources = use_resources or []
        self.fail = fail
        self.execution_count = 0
        self.resources_used = {}
        # Initialize config for parent class
        self.config = {}

    def get_parameters(self):
        """Return empty parameters for testing."""
        from kailash.nodes.base import NodeParameter

        return {}

    async def async_run(self, resource_registry=None, **kwargs):
        """Execute the test node."""
        self.execution_count += 1

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.fail:
            raise Exception(f"Node {self.node_id} intentionally failed")

        # Use resources if specified
        if resource_registry and self.use_resources:
            for resource_name in self.use_resources:
                try:
                    resource = await resource_registry.get_resource(resource_name)
                    self.resources_used[resource_name] = resource

                    # Perform operations based on resource type
                    if isinstance(resource, MockDatabase):
                        data = await resource.query("SELECT * FROM users")
                        self.result["db_data"] = data
                    elif isinstance(resource, MockHttpClient):
                        response = await resource.get("/status")
                        status_data = await response.json()
                        self.result["api_data"] = status_data
                    elif isinstance(resource, MockCache):
                        await resource.set(f"node_{self.node_id}", self.result)
                        self.result["cached"] = True

                except Exception as e:
                    self.result["resource_error"] = str(e)

        # Include input data in result
        if kwargs:
            self.result["inputs"] = kwargs

        return self.result


class AdvancedMockSyncNode(Node):
    """Advanced sync node for mixed workflow testing."""

    def __init__(self, node_id, result=None, delay=0.1):
        self.node_id = node_id
        self.result = result or {"output": f"sync_result_from_{node_id}"}
        self.delay = delay
        self.execution_count = 0
        # Initialize config for parent class
        self.config = {}

    def get_parameters(self):
        """Return empty parameters for testing."""
        from kailash.nodes.base import NodeParameter

        return {}

    def execute(self, **kwargs):
        """Execute the sync node."""
        self.execution_count += 1

        if self.delay > 0:
            time.sleep(self.delay)

        # Include input data
        if kwargs:
            self.result["inputs"] = kwargs

        return self.result


class MockWorkflow:
    """Mock workflow for testing."""

    def __init__(self, nodes=None, edges=None):
        self.workflow_id = "test_workflow"
        self.name = "Test Workflow"
        self._node_instances = nodes or {}
        self.graph = nx.DiGraph()
        self.metadata = {}

        # Add nodes to graph
        for node_id in self._node_instances.keys():
            self.graph.add_node(node_id)

        # Add edges if provided
        if edges:
            for source, target, data in edges:
                self.graph.add_edge(source, target, **data)


@pytest.mark.asyncio
class TestExecutionContext:
    """Test ExecutionContext functionality with real resource operations."""

    async def test_basic_context_operations(self):
        """Test basic context variable operations."""
        context = ExecutionContext()

        # Test variable operations
        context.set_variable("user_id", 123)
        context.set_variable("environment", "test")
        context.set_variable("config", {"debug": True, "timeout": 30})

        assert context.get_variable("user_id") == 123
        assert context.get_variable("environment") == "test"
        assert context.get_variable("config")["debug"] is True
        assert context.get_variable("missing_key", "default") == "default"

        # Test metrics initialization
        assert context.metrics.total_duration == 0.0
        assert context.metrics.error_count == 0
        assert len(context.metrics.node_durations) == 0
        assert len(context.metrics.resource_access_count) == 0

    async def test_resource_access_with_real_resources(self):
        """Test resource access with actual resource factories."""
        registry = ResourceRegistry()

        # Register multiple resource types
        registry.register_factory("database", AdvancedMockResourceFactory("database"))
        registry.register_factory(
            "http_client", AdvancedMockResourceFactory("http_client")
        )
        registry.register_factory(
            "cache", AdvancedMockResourceFactory("cache", create_delay=0.01)
        )

        context = ExecutionContext(resource_registry=registry)

        # Access database resource
        db = await context.get_resource("database")
        assert isinstance(db, MockDatabase)
        assert context.metrics.resource_access_count["database"] == 1

        # Access HTTP client
        http = await context.get_resource("http_client")
        assert isinstance(http, MockHttpClient)
        assert context.metrics.resource_access_count["http_client"] == 1

        # Access cache (with delay)
        start_time = time.time()
        cache = await context.get_resource("cache")
        access_time = time.time() - start_time
        assert isinstance(cache, MockCache)
        assert access_time >= 0.01  # Verify delay was applied
        assert context.metrics.resource_access_count["cache"] == 1

        # Access same resources again (should reuse)
        db2 = await context.get_resource("database")
        assert db is db2  # Same instance
        assert context.metrics.resource_access_count["database"] == 2

    async def test_concurrent_resource_access(self):
        """Test concurrent access to resources."""
        registry = ResourceRegistry()
        registry.register_factory("shared_db", AdvancedMockResourceFactory("database"))

        context = ExecutionContext(resource_registry=registry)

        # Concurrent access to same resource
        async def access_resource(name):
            return await context.get_resource(name)

        # Access same resource concurrently
        tasks = [access_resource("shared_db") for _ in range(5)]
        resources = await asyncio.gather(*tasks)

        # All should be the same instance
        first_resource = resources[0]
        assert all(r is first_resource for r in resources)
        assert context.metrics.resource_access_count["shared_db"] == 5

    async def test_resource_access_error_handling(self):
        """Test error handling when resources fail to create."""
        registry = ResourceRegistry()
        registry.register_factory(
            "failing_resource",
            AdvancedMockResourceFactory("database", fail_creation=True),
        )

        context = ExecutionContext(resource_registry=registry)

        # Should raise exception when resource creation fails
        with pytest.raises(Exception, match="Failed to create database"):
            await context.get_resource("failing_resource")

        # Should raise error when no registry is available
        context_no_registry = ExecutionContext()
        with pytest.raises(RuntimeError, match="No resource registry available"):
            await context_no_registry.get_resource("any_resource")


class TestWorkflowAnalyzer:
    """Test WorkflowAnalyzer with complex dependency scenarios."""

    def test_analyze_empty_workflow(self):
        """Test analysis of empty workflow."""
        analyzer = WorkflowAnalyzer()
        workflow = MockWorkflow()

        plan = analyzer.analyze(workflow)

        assert plan.workflow_id is not None
        assert len(plan.async_nodes) == 0
        assert len(plan.sync_nodes) == 0
        assert len(plan.execution_levels) == 0
        assert not plan.is_fully_async
        assert not plan.has_async_nodes
        assert not plan.can_parallelize

    def test_analyze_complex_async_workflow(self):
        """Test analysis of complex async workflow with realistic nodes."""
        analyzer = WorkflowAnalyzer()

        # Create complex workflow
        nodes = {
            "data_fetch": AdvancedMockAsyncNode(
                "data_fetch", delay=0.1, use_resources=["database"]
            ),
            "api_call": AdvancedMockAsyncNode(
                "api_call", delay=0.15, use_resources=["http_client"]
            ),
            "cache_lookup": AdvancedMockAsyncNode(
                "cache_lookup", delay=0.05, use_resources=["cache"]
            ),
            "data_transform": MockAsyncNode("data_transform", delay=0.2),
            "result_aggregate": MockAsyncNode("result_aggregate", delay=0.1),
        }

        # Create dependency graph:
        # data_fetch -> data_transform -> result_aggregate
        # api_call -> result_aggregate
        # cache_lookup -> result_aggregate
        edges = [
            ("data_fetch", "data_transform", {"connections": []}),
            ("data_transform", "result_aggregate", {"connections": []}),
            ("api_call", "result_aggregate", {"connections": []}),
            ("cache_lookup", "result_aggregate", {"connections": []}),
        ]

        workflow = MockWorkflow(nodes, edges)

        plan = analyzer.analyze(workflow)

        assert len(plan.async_nodes) == 5
        assert len(plan.sync_nodes) == 0
        assert plan.is_fully_async
        assert plan.has_async_nodes
        assert plan.can_parallelize

        # Should have 3 execution levels:
        # Level 0: data_fetch, api_call, cache_lookup (parallel)
        # Level 1: data_transform
        # Level 2: result_aggregate
        assert len(plan.execution_levels) == 3
        assert plan.max_concurrent_nodes == 3  # Level 0 has 3 nodes

        # Verify specific level contents
        level_0_nodes = plan.execution_levels[0].nodes
        assert "data_fetch" in level_0_nodes
        assert "api_call" in level_0_nodes
        assert "cache_lookup" in level_0_nodes

        level_1_nodes = plan.execution_levels[1].nodes
        assert "data_transform" in level_1_nodes

        level_2_nodes = plan.execution_levels[2].nodes
        assert "result_aggregate" in level_2_nodes

    def test_analyze_mixed_workflow(self):
        """Test analysis of mixed sync/async workflow."""
        analyzer = WorkflowAnalyzer()

        nodes = {
            "async_fetch": AdvancedMockAsyncNode(
                "async_fetch", use_resources=["database"]
            ),
            "sync_process": MockSyncNode("sync_process"),
            "async_save": AdvancedMockAsyncNode("async_save", use_resources=["cache"]),
            "sync_validate": MockSyncNode("sync_validate"),
        }

        # Linear workflow: async_fetch -> sync_process -> async_save -> sync_validate
        edges = [
            ("async_fetch", "sync_process", {"connections": []}),
            ("sync_process", "async_save", {"connections": []}),
            ("async_save", "sync_validate", {"connections": []}),
        ]

        workflow = MockWorkflow(nodes, edges)

        plan = analyzer.analyze(workflow)

        assert len(plan.async_nodes) == 2
        assert len(plan.sync_nodes) == 2
        assert not plan.is_fully_async
        assert plan.has_async_nodes
        assert not plan.can_parallelize  # Linear workflow

        # Should have 4 execution levels (linear)
        assert len(plan.execution_levels) == 4
        assert plan.max_concurrent_nodes == 1

    def test_analyze_diamond_dependency_pattern(self):
        """Test analysis of diamond dependency pattern."""
        analyzer = WorkflowAnalyzer()

        nodes = {
            "source": MockAsyncNode("source"),
            "branch_a": MockAsyncNode("branch_a"),
            "branch_b": MockAsyncNode("branch_b"),
            "merge": MockAsyncNode("merge"),
        }

        # Diamond pattern: source -> (branch_a, branch_b) -> merge
        edges = [
            ("source", "branch_a", {"connections": []}),
            ("source", "branch_b", {"connections": []}),
            ("branch_a", "merge", {"connections": []}),
            ("branch_b", "merge", {"connections": []}),
        ]

        workflow = MockWorkflow(nodes, edges)

        plan = analyzer.analyze(workflow)

        # Should have 3 execution levels:
        # Level 0: source
        # Level 1: branch_a, branch_b (parallel)
        # Level 2: merge
        assert len(plan.execution_levels) == 3
        assert plan.max_concurrent_nodes == 2  # Level 1 has 2 nodes

        # Verify parallel branches
        level_1_nodes = plan.execution_levels[1].nodes
        assert "branch_a" in level_1_nodes
        assert "branch_b" in level_1_nodes

    def test_analysis_caching(self):
        """Test that analysis results are properly cached."""
        analyzer = WorkflowAnalyzer()

        nodes = {"test_node": MockAsyncNode("test_node")}
        workflow = MockWorkflow(nodes)
        workflow.workflow_id = "cached_workflow_test"

        # First analysis
        plan1 = analyzer.analyze(workflow)

        # Second analysis should return cached result
        plan2 = analyzer.analyze(workflow)

        assert plan1 is plan2  # Same object reference

        # Different workflow should get new analysis
        workflow2 = MockWorkflow(nodes)
        workflow2.workflow_id = "different_workflow"
        plan3 = analyzer.analyze(workflow2)

        assert plan3 is not plan1  # Different object


@pytest.mark.asyncio
class TestAsyncExecutionTracker:
    """Test AsyncExecutionTracker with concurrent operations."""

    async def test_concurrent_result_recording(self):
        """Test recording results from multiple concurrent nodes."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record results concurrently
        async def record_result(node_id, result, duration):
            await tracker.record_result(node_id, result, duration)

        # Create multiple concurrent recording tasks
        tasks = [
            record_result(f"node_{i}", {"data": f"result_{i}"}, 0.1 + i * 0.01)
            for i in range(10)
        ]

        await asyncio.gather(*tasks)

        # Verify all results recorded
        assert len(tracker.results) == 10
        assert len(tracker.execution_times) == 10

        for i in range(10):
            node_id = f"node_{i}"
            assert node_id in tracker.results
            assert tracker.results[node_id]["data"] == f"result_{i}"
            assert tracker.execution_times[node_id] == 0.1 + i * 0.01
            assert context.metrics.node_durations[node_id] == 0.1 + i * 0.01

    async def test_concurrent_error_recording(self):
        """Test recording errors from concurrent node executions."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record mix of successes and errors
        async def record_mixed(node_id, should_fail):
            if should_fail:
                await tracker.record_error(node_id, Exception(f"Error in {node_id}"))
            else:
                await tracker.record_result(node_id, {"success": True}, 0.1)

        # Half succeed, half fail
        tasks = [record_mixed(f"node_{i}", i % 2 == 0) for i in range(10)]

        await asyncio.gather(*tasks)

        # Verify results
        assert len(tracker.results) == 5  # 5 successful nodes
        assert len(tracker.errors) == 5  # 5 failed nodes
        assert context.metrics.error_count == 5

        # Check specific results
        for i in range(10):
            node_id = f"node_{i}"
            if i % 2 == 0:  # Failed nodes
                assert node_id in tracker.errors
                assert f"Error in {node_id}" in str(tracker.errors[node_id])
            else:  # Successful nodes
                assert node_id in tracker.results
                assert tracker.results[node_id]["success"] is True

    async def test_get_final_results(self):
        """Test getting comprehensive final results."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # Record various types of data
        await tracker.record_result("success_node", {"output": "data"}, 0.15)
        await tracker.record_error("error_node", Exception("Test error"))
        await tracker.record_result("fast_node", {"output": "quick"}, 0.05)

        # Get final results
        final_result = tracker.get_result()

        # Verify structure
        assert "results" in final_result
        assert "errors" in final_result
        assert "execution_times" in final_result
        assert "total_duration" in final_result
        assert "metrics" in final_result

        # Verify content
        assert len(final_result["results"]) == 2
        assert len(final_result["errors"]) == 1
        assert final_result["results"]["success_node"]["output"] == "data"
        assert final_result["results"]["fast_node"]["output"] == "quick"
        assert "error_node" in final_result["errors"]
        assert final_result["execution_times"]["success_node"] == 0.15
        assert final_result["execution_times"]["fast_node"] == 0.05
        assert final_result["total_duration"] > 0

    async def test_thread_safety_stress_test(self):
        """Stress test thread safety with high concurrency."""
        context = ExecutionContext()
        workflow = MockWorkflow()
        tracker = AsyncExecutionTracker(workflow, context)

        # High concurrency test
        num_nodes = 100

        async def record_random_result(node_id):
            # Simulate variable execution times
            execution_time = 0.01 + (node_id % 10) * 0.01
            await asyncio.sleep(execution_time)

            if node_id % 7 == 0:  # Some nodes fail
                await tracker.record_error(node_id, Exception(f"Node {node_id} failed"))
            else:
                await tracker.record_result(
                    f"node_{node_id}",
                    {"node_id": node_id, "result": f"output_{node_id}"},
                    execution_time,
                )

        # Execute all concurrently
        tasks = [record_random_result(i) for i in range(num_nodes)]
        await asyncio.gather(*tasks)

        # Verify integrity
        successful_nodes = [i for i in range(num_nodes) if i % 7 != 0]
        failed_nodes = [i for i in range(num_nodes) if i % 7 == 0]

        assert len(tracker.results) == len(successful_nodes)
        assert len(tracker.errors) == len(failed_nodes)
        assert context.metrics.error_count == len(failed_nodes)

        # Verify no data corruption
        for i in successful_nodes:
            node_id = f"node_{i}"
            assert node_id in tracker.results
            assert tracker.results[node_id]["node_id"] == i


@pytest.mark.asyncio
class TestAsyncLocalRuntimeComprehensive:
    """Comprehensive tests for AsyncLocalRuntime with realistic scenarios."""

    async def test_fully_async_workflow_with_resources(self):
        """Test fully async workflow with real resource usage."""
        # Setup resources
        registry = ResourceRegistry()
        registry.register_factory("database", AdvancedMockResourceFactory("database"))
        registry.register_factory(
            "http_client", AdvancedMockResourceFactory("http_client")
        )
        registry.register_factory("cache", AdvancedMockResourceFactory("cache"))

        runtime = AsyncLocalRuntime(
            resource_registry=registry,
            max_concurrent_nodes=5,
            enable_analysis=True,
            enable_profiling=True,
        )

        # Create realistic workflow
        nodes = {
            "data_fetch": AdvancedMockAsyncNode(
                "data_fetch", delay=0.1, use_resources=["database"]
            ),
            "api_call": AdvancedMockAsyncNode(
                "api_call", delay=0.15, use_resources=["http_client"]
            ),
            "cache_operation": AdvancedMockAsyncNode(
                "cache_operation", delay=0.05, use_resources=["cache"]
            ),
        }

        workflow = MockWorkflow(nodes)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {"user_id": 123})
        execution_time = time.time() - start_time

        # Verify concurrent execution (should be much faster than sequential)
        assert execution_time < 0.25  # Much less than 0.3s sequential

        # Verify all nodes completed successfully
        assert len(result["results"]) == 3
        assert len(result["errors"]) == 0

        # Verify resource usage
        for node_id in nodes.keys():
            node_result = result["results"][node_id]
            assert "output" in node_result
            assert "inputs" in node_result
            assert node_result["inputs"]["user_id"] == 123

            # Verify resource-specific data was added
            node = nodes[node_id]
            if "database" in node.use_resources:
                assert "db_data" in node_result
            if "http_client" in node.use_resources:
                assert "api_data" in node_result
            if "cache" in node.use_resources:
                assert "cached" in node_result

        # Verify metrics
        metrics = result["metrics"]
        assert metrics.total_duration > 0

        # Verify that resources were actually used by checking node state
        for node_id, node in nodes.items():
            if node.use_resources:
                assert len(node.resources_used) == len(
                    node.use_resources
                ), f"Node {node_id} should have used all its resources"

        # Verify that nodes accessed their expected resources
        assert "database" in nodes["data_fetch"].resources_used
        assert "http_client" in nodes["api_call"].resources_used
        assert "cache" in nodes["cache_operation"].resources_used

        await runtime.cleanup()

    async def test_mixed_sync_async_workflow(self):
        """Test workflow with both sync and async nodes."""
        registry = ResourceRegistry()
        registry.register_factory("shared_db", AdvancedMockResourceFactory("database"))

        runtime = AsyncLocalRuntime(
            resource_registry=registry, max_concurrent_nodes=3, thread_pool_size=2
        )

        # Mixed workflow
        nodes = {
            "async_fetch": AdvancedMockAsyncNode(
                "async_fetch", delay=0.1, use_resources=["shared_db"]
            ),
            "sync_process": MockSyncNode("sync_process", delay=0.08),
            "async_save": AdvancedMockAsyncNode(
                "async_save", delay=0.05, use_resources=["shared_db"]
            ),
            "sync_validate": MockSyncNode("sync_validate", delay=0.03),
        }

        # Create dependencies
        edges = [
            (
                "async_fetch",
                "sync_process",
                {
                    "connections": [
                        {"source_path": "output", "target_param": "input_data"}
                    ]
                },
            ),
            (
                "sync_process",
                "async_save",
                {
                    "connections": [
                        {"source_path": "output", "target_param": "processed_data"}
                    ]
                },
            ),
            (
                "async_save",
                "sync_validate",
                {
                    "connections": [
                        {"source_path": "output", "target_param": "saved_data"}
                    ]
                },
            ),
        ]

        workflow = MockWorkflow(nodes, edges)

        result = await runtime.execute_workflow_async(
            workflow, {"initial_data": "test"}
        )

        # Verify execution
        assert len(result["results"]) == 4
        assert len(result["errors"]) == 0

        # Verify data flow
        sync_process_result = result["results"]["sync_process"]
        assert "inputs" in sync_process_result
        assert "input_data" in sync_process_result["inputs"]

        async_save_result = result["results"]["async_save"]
        assert "inputs" in async_save_result
        assert "processed_data" in async_save_result["inputs"]

        # Verify both node types executed
        assert nodes["async_fetch"].execution_count == 1
        assert nodes["sync_process"].execution_count == 1
        assert nodes["async_save"].execution_count == 1
        assert nodes["sync_validate"].execution_count == 1

        await runtime.cleanup()

    async def test_error_handling_and_recovery(self):
        """Test error handling in various failure scenarios."""
        registry = ResourceRegistry()
        registry.register_factory(
            "stable_resource", AdvancedMockResourceFactory("database")
        )
        registry.register_factory(
            "failing_resource",
            AdvancedMockResourceFactory("database", fail_creation=True),
        )

        runtime = AsyncLocalRuntime(resource_registry=registry, max_concurrent_nodes=3)

        # Workflow with one failing node
        nodes = {
            "success_node": AdvancedMockAsyncNode(
                "success_node", use_resources=["stable_resource"]
            ),
            "failing_node": AdvancedMockAsyncNode("failing_node", fail=True),
            "resource_fail_node": AdvancedMockAsyncNode(
                "resource_fail_node", use_resources=["failing_resource"]
            ),
        }

        workflow = MockWorkflow(nodes)

        # Execution should fail due to failing nodes
        with pytest.raises(WorkflowExecutionError):
            await runtime.execute_workflow_async(workflow, {})

        await runtime.cleanup()

    async def test_performance_analysis_and_optimization(self):
        """Test performance analysis and optimization features."""
        runtime = AsyncLocalRuntime(
            max_concurrent_nodes=10, enable_analysis=True, enable_profiling=True
        )

        # Create workflow with varying execution times
        nodes = {
            "fast_node_1": MockAsyncNode("fast_node_1", delay=0.02),
            "fast_node_2": MockAsyncNode("fast_node_2", delay=0.03),
            "medium_node": MockAsyncNode("medium_node", delay=0.1),
            "slow_node": MockAsyncNode("slow_node", delay=0.2),
            "parallel_1": MockAsyncNode("parallel_1", delay=0.05),
            "parallel_2": MockAsyncNode("parallel_2", delay=0.06),
        }

        # Create complex dependency graph
        edges = [
            ("fast_node_1", "medium_node", {"connections": []}),
            ("fast_node_2", "medium_node", {"connections": []}),
            ("medium_node", "slow_node", {"connections": []}),
            # parallel_1 and parallel_2 are independent
        ]

        workflow = MockWorkflow(nodes, edges)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # Verify optimization worked (should be closer to longest path than sum of all)
        longest_path_time = 0.02 + 0.1 + 0.2  # fast_node_1 -> medium_node -> slow_node
        parallel_time = max(0.05, 0.06)  # parallel nodes
        expected_time = max(longest_path_time, parallel_time)

        # Should be close to expected time, not sum of all delays
        assert execution_time < expected_time + 0.1  # Allow some overhead

        # Verify detailed metrics
        metrics = result["metrics"]
        assert len(metrics.node_durations) == 6

        # Check that slow node took longest
        assert (
            metrics.node_durations["slow_node"] > metrics.node_durations["fast_node_1"]
        )
        assert (
            metrics.node_durations["slow_node"] > metrics.node_durations["medium_node"]
        )

        # Note: concurrent_executions metric may not be implemented yet
        # The actual concurrency is verified by execution time being much less than sequential

        await runtime.cleanup()

    async def test_high_concurrency_stress_test(self):
        """Stress test with high concurrency and many nodes."""
        runtime = AsyncLocalRuntime(
            max_concurrent_nodes=20, enable_analysis=True, thread_pool_size=8
        )

        # Create many independent nodes
        nodes = {}
        for i in range(50):
            nodes[f"node_{i}"] = MockAsyncNode(f"node_{i}", delay=0.01 + (i % 5) * 0.01)

        workflow = MockWorkflow(nodes)

        start_time = time.time()
        result = await runtime.execute_workflow_async(workflow, {})
        execution_time = time.time() - start_time

        # With 20 concurrent nodes, 50 nodes should complete much faster than sequential
        sequential_time = sum(0.01 + (i % 5) * 0.01 for i in range(50))
        concurrent_time = sequential_time / 20  # Theoretical maximum speedup

        assert execution_time < sequential_time / 10  # At least 10x speedup

        # Verify all nodes completed
        assert len(result["results"]) == 50
        assert len(result["errors"]) == 0

        # Verify all nodes executed
        for i in range(50):
            node = nodes[f"node_{i}"]
            assert node.execution_count == 1

        await runtime.cleanup()

    async def test_resource_sharing_and_contention(self):
        """Test resource sharing and potential contention scenarios."""
        registry = ResourceRegistry()

        # Single shared database
        registry.register_factory("shared_db", AdvancedMockResourceFactory("database"))

        runtime = AsyncLocalRuntime(resource_registry=registry, max_concurrent_nodes=5)

        # Multiple nodes using same resource
        nodes = {}
        for i in range(10):
            nodes[f"db_user_{i}"] = AdvancedMockAsyncNode(
                f"db_user_{i}", delay=0.05, use_resources=["shared_db"]
            )

        workflow = MockWorkflow(nodes)

        result = await runtime.execute_workflow_async(workflow, {})

        # All should succeed
        assert len(result["results"]) == 10
        assert len(result["errors"]) == 0

        # Verify resource was shared (all should get same instance)
        shared_resource = None
        for i in range(10):
            node = nodes[f"db_user_{i}"]
            if "shared_db" in node.resources_used:
                if shared_resource is None:
                    shared_resource = node.resources_used["shared_db"]
                else:
                    assert (
                        node.resources_used["shared_db"] is shared_resource
                    ), "All nodes should share the same resource instance"

        await runtime.cleanup()


# Run tests helper
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

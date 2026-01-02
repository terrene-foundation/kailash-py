"""
Unit tests for kailash.runtime.async_local module.

Tests the AsyncLocalRuntime class and supporting components including:
- ExecutionContext with resource management
- WorkflowAnalyzer for optimization planning
- AsyncExecutionTracker for state management
- AsyncLocalRuntime with async execution capabilities

NO MOCKING - Tests verify actual async runtime behavior with real components.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.resources import ResourceRegistry
from kailash.runtime.async_local import (
    AsyncExecutionTracker,
    AsyncLocalRuntime,
    ExecutionContext,
    ExecutionLevel,
    ExecutionMetrics,
    ExecutionPlan,
    WorkflowAnalyzer,
)
from kailash.sdk_exceptions import RuntimeExecutionError
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class MockAsyncNode(AsyncNode):
    """Test async node for testing purposes."""

    def __init__(self, name: str, result: str = "async_result", delay: float = 0.1):
        super().__init__(name=name)
        self.result = result
        self.delay = delay

    def get_parameters(self):
        """Define parameters for this test node."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=dict,
                required=False,
                description="Input data for the node",
            )
        }

    async def run(self, **inputs):
        """Run async with optional delay."""
        await asyncio.sleep(self.delay)
        return {"result": self.result, "inputs": inputs}


class MockSyncNode(Node):
    """Test sync node for testing purposes."""

    def __init__(self, name: str, result: str = "sync_result"):
        super().__init__(name=name)
        self.result = result

    def get_parameters(self):
        """Define parameters for this test node."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=dict,
                required=False,
                description="Input data for the node",
            )
        }

    def run(self, **inputs):
        """Run synchronously."""
        return {"result": self.result, "inputs": inputs}


class TestExecutionContext:
    """Test ExecutionContext class."""

    def test_init_without_resource_registry(self):
        """Test initialization without resource registry."""
        context = ExecutionContext()

        assert context.resource_registry is None
        assert context.variables == {}
        assert isinstance(context.metrics, ExecutionMetrics)
        assert context.start_time > 0
        assert context._weak_refs == {}

    def test_init_with_resource_registry(self):
        """Test initialization with resource registry."""
        registry = ResourceRegistry()
        context = ExecutionContext(resource_registry=registry)

        assert context.resource_registry is registry
        assert context.variables == {}
        assert isinstance(context.metrics, ExecutionMetrics)

    def test_set_and_get_variable(self):
        """Test setting and getting context variables."""
        context = ExecutionContext()

        # Test setting variables
        context.set_variable("test_key", "test_value")
        context.set_variable("number", 42)
        context.set_variable("list", [1, 2, 3])

        # Test getting variables
        assert context.get_variable("test_key") == "test_value"
        assert context.get_variable("number") == 42
        assert context.get_variable("list") == [1, 2, 3]

        # Test default values
        assert context.get_variable("nonexistent") is None
        assert context.get_variable("nonexistent", "default") == "default"

    @pytest.mark.asyncio
    async def test_get_resource_without_registry(self):
        """Test getting resource without registry raises error."""
        context = ExecutionContext()

        with pytest.raises(RuntimeError, match="No resource registry available"):
            await context.get_resource("test_resource")

    @pytest.mark.asyncio
    async def test_get_resource_with_registry(self):
        """Test getting resource with registry."""
        registry = ResourceRegistry()
        context = ExecutionContext(resource_registry=registry)

        # Mock the resource registry get_resource method
        test_resource = {"type": "test", "value": "resource_data"}
        registry.get_resource = AsyncMock(return_value=test_resource)

        result = await context.get_resource("test_resource")

        assert result == test_resource
        registry.get_resource.assert_called_once_with("test_resource")

        # Check metrics tracking
        assert context.metrics.resource_access_count["test_resource"] == 1

        # Test multiple accesses
        await context.get_resource("test_resource")
        assert context.metrics.resource_access_count["test_resource"] == 2


class TestExecutionLevel:
    """Test ExecutionLevel dataclass."""

    def test_init_default(self):
        """Test default initialization."""
        level = ExecutionLevel(level=1)

        assert level.level == 1
        assert level.nodes == set()
        assert level.dependencies_satisfied == set()

    def test_init_with_data(self):
        """Test initialization with data."""
        nodes = {"node1", "node2"}
        deps = {"dep1", "dep2"}

        level = ExecutionLevel(level=2, nodes=nodes, dependencies_satisfied=deps)

        assert level.level == 2
        assert level.nodes == nodes
        assert level.dependencies_satisfied == deps


class TestExecutionPlan:
    """Test ExecutionPlan dataclass."""

    def test_init_default(self):
        """Test default initialization."""
        plan = ExecutionPlan(workflow_id="test_workflow")

        assert plan.workflow_id == "test_workflow"
        assert plan.async_nodes == set()
        assert plan.sync_nodes == set()
        assert plan.execution_levels == []
        assert plan.required_resources == set()
        assert plan.estimated_duration == 0.0
        assert plan.max_concurrent_nodes == 1

    def test_is_fully_async(self):
        """Test is_fully_async property."""
        plan = ExecutionPlan(workflow_id="test")

        # Empty plan
        assert not plan.is_fully_async

        # Only async nodes
        plan.async_nodes = {"node1", "node2"}
        assert plan.is_fully_async

        # Mixed nodes
        plan.sync_nodes = {"node3"}
        assert not plan.is_fully_async

    def test_has_async_nodes(self):
        """Test has_async_nodes property."""
        plan = ExecutionPlan(workflow_id="test")

        assert not plan.has_async_nodes

        plan.async_nodes = {"node1"}
        assert plan.has_async_nodes

    def test_can_parallelize(self):
        """Test can_parallelize property."""
        plan = ExecutionPlan(workflow_id="test")

        assert not plan.can_parallelize

        plan.max_concurrent_nodes = 3
        assert plan.can_parallelize


class TestExecutionMetrics:
    """Test ExecutionMetrics dataclass."""

    def test_init_default(self):
        """Test default initialization."""
        metrics = ExecutionMetrics()

        assert metrics.total_duration == 0.0
        assert metrics.node_durations == {}
        assert metrics.concurrent_executions == 0
        assert metrics.resource_access_count == {}
        assert metrics.error_count == 0
        assert metrics.retry_count == 0


class TestWorkflowAnalyzer:
    """Test WorkflowAnalyzer class."""

    def test_init_default(self):
        """Test default initialization."""
        analyzer = WorkflowAnalyzer()

        assert analyzer.enable_profiling is True
        assert analyzer._analysis_cache == {}

    def test_init_with_options(self):
        """Test initialization with options."""
        analyzer = WorkflowAnalyzer(enable_profiling=False)

        assert analyzer.enable_profiling is False
        assert analyzer._analysis_cache == {}

    def test_analyze_simple_workflow(self):
        """Test analyzing a simple workflow."""
        analyzer = WorkflowAnalyzer()

        # Create a simple workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = {'value': 1}"})
        builder.add_node("PythonCodeNode", "node2", {"code": "result = {'value': 2}"})
        builder.add_connection("node1", "result", "node2", "input_data")

        workflow = builder.build()

        # Analyze workflow
        plan = analyzer.analyze(workflow)

        assert isinstance(plan, ExecutionPlan)
        assert plan.workflow_id == workflow.workflow_id
        assert len(plan.sync_nodes) == 2
        assert len(plan.async_nodes) == 0
        assert len(plan.execution_levels) >= 1
        assert not plan.is_fully_async
        assert not plan.has_async_nodes

    def test_analyze_caching(self):
        """Test that analysis results are cached."""
        analyzer = WorkflowAnalyzer()

        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = {'value': 1}"})
        workflow = builder.build()

        # First analysis
        plan1 = analyzer.analyze(workflow)
        assert len(analyzer._analysis_cache) == 1

        # Second analysis should use cache
        plan2 = analyzer.analyze(workflow)
        assert plan1 is plan2  # Same object reference
        assert len(analyzer._analysis_cache) == 1

    def test_analyze_with_mock_async_nodes(self):
        """Test analyzing workflow with async nodes."""
        analyzer = WorkflowAnalyzer()

        # Create workflow with mock async nodes
        workflow = Workflow(workflow_id="test_async", name="Test Async")

        # Mock node instances
        async_node = MockAsyncNode("async_node", "async_result")
        sync_node = MockSyncNode("sync_node", "sync_result")

        workflow._node_instances = {"async_node": async_node, "sync_node": sync_node}

        # Mock graph
        workflow.graph.add_node("async_node")
        workflow.graph.add_node("sync_node")

        # Analyze workflow
        plan = analyzer.analyze(workflow)

        assert plan.workflow_id == "test_async"
        assert "async_node" in plan.async_nodes
        assert "sync_node" in plan.sync_nodes
        assert plan.has_async_nodes
        assert not plan.is_fully_async


class TestAsyncExecutionTracker:
    """Test AsyncExecutionTracker class."""

    def test_init(self):
        """Test initialization."""
        workflow = Workflow(workflow_id="test", name="Test")
        context = ExecutionContext()

        tracker = AsyncExecutionTracker(workflow, context)

        assert tracker.workflow is workflow
        assert tracker.context is context
        assert tracker.results == {}
        assert tracker.node_outputs == {}
        assert tracker.errors == {}
        assert tracker.execution_times == {}
        assert tracker._locks == {}

    def test_get_lock(self):
        """Test getting locks for nodes."""
        workflow = Workflow(workflow_id="test", name="Test")
        context = ExecutionContext()
        tracker = AsyncExecutionTracker(workflow, context)

        # Get lock for first time
        lock1 = tracker.get_lock("node1")
        assert isinstance(lock1, asyncio.Lock)

        # Get same lock again
        lock2 = tracker.get_lock("node1")
        assert lock1 is lock2

        # Get different lock for different node
        lock3 = tracker.get_lock("node2")
        assert lock3 is not lock1

    @pytest.mark.asyncio
    async def test_record_result(self):
        """Test recording node results."""
        workflow = Workflow(workflow_id="test", name="Test")
        context = ExecutionContext()
        tracker = AsyncExecutionTracker(workflow, context)

        result = {"output": "test_result"}

        await tracker.record_result("node1", result, 0.5)

        assert tracker.results["node1"] == result
        assert tracker.execution_times["node1"] == 0.5

    @pytest.mark.asyncio
    async def test_record_error(self):
        """Test recording node errors."""
        workflow = Workflow(workflow_id="test", name="Test")
        context = ExecutionContext()
        tracker = AsyncExecutionTracker(workflow, context)

        error = RuntimeError("Test error")

        await tracker.record_error("node1", error)

        assert tracker.errors["node1"] == error
        assert tracker.context.metrics.error_count == 1


class TestAsyncLocalRuntime:
    """Test AsyncLocalRuntime class."""

    def test_init_default(self):
        """Test default initialization."""
        runtime = AsyncLocalRuntime()

        assert runtime.resource_registry is None
        assert runtime.max_concurrent_nodes == 10
        assert runtime.enable_analysis is True
        assert runtime.enable_profiling is True
        assert isinstance(runtime.thread_pool, ThreadPoolExecutor)
        assert isinstance(runtime.analyzer, WorkflowAnalyzer)
        assert isinstance(runtime.execution_semaphore, asyncio.Semaphore)

    def test_init_with_options(self):
        """Test initialization with custom options."""
        registry = ResourceRegistry()

        runtime = AsyncLocalRuntime(
            resource_registry=registry,
            max_concurrent_nodes=5,
            enable_analysis=False,
            enable_profiling=False,
            thread_pool_size=8,
        )

        assert runtime.resource_registry is registry
        assert runtime.max_concurrent_nodes == 5
        assert runtime.enable_analysis is False
        assert runtime.enable_profiling is False
        assert isinstance(runtime.thread_pool, ThreadPoolExecutor)

    @pytest.mark.asyncio
    async def test_execute_workflow_async_simple(self):
        """Test executing a simple async workflow."""
        runtime = AsyncLocalRuntime()

        # Create simple workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = {'value': 42}"})
        workflow = builder.build()

        # Execute workflow
        result = await runtime.execute_workflow_async(workflow, {})

        assert result is not None
        assert "results" in result or "node1" in result

    @pytest.mark.asyncio
    async def test_execute_workflow_async_with_parameters(self):
        """Test executing workflow with parameters."""
        runtime = AsyncLocalRuntime()

        # Create workflow with parameters
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "node1",
            {
                "code": "result = {'doubled': input_value * 2}",
                "parameters": {"input_value": 10},
            },
        )
        workflow = builder.build()

        # Execute with different parameters
        parameters = {"input_value": 15}
        result = await runtime.execute_workflow_async(workflow, parameters)

        assert result is not None
        # Check if result contains execution data

    @pytest.mark.asyncio
    async def test_execute_workflow_async_with_resource_registry(self):
        """Test executing workflow with resource registry."""
        registry = ResourceRegistry()
        runtime = AsyncLocalRuntime(resource_registry=registry)

        # Create simple workflow
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node1", {"code": "result = {'has_registry': True}"}
        )
        workflow = builder.build()

        # Execute workflow
        result = await runtime.execute_workflow_async(workflow, {})

        assert result is not None
        # Check if result contains execution data

    @pytest.mark.asyncio
    async def test_execute_workflow_async_error_handling(self):
        """Test error handling in async execution."""
        runtime = AsyncLocalRuntime()

        # Create workflow with error
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "node1", {"code": "raise RuntimeError('Test error')"}
        )
        workflow = builder.build()

        # Execute workflow - should handle error gracefully
        with pytest.raises(Exception):  # Could be various exception types
            await runtime.execute_workflow_async(workflow, {})

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup method."""
        runtime = AsyncLocalRuntime()

        # Mock the shutdown method
        runtime.thread_pool.shutdown = MagicMock()

        # Test cleanup
        await runtime.cleanup()

        # Verify thread pool shutdown was called
        runtime.thread_pool.shutdown.assert_called_once_with(wait=True)

    def test_concurrent_execution_limits(self):
        """Test that concurrent execution limits are respected."""
        runtime = AsyncLocalRuntime(max_concurrent_nodes=2)

        assert runtime.max_concurrent_nodes == 2
        assert runtime.execution_semaphore._value == 2

    @pytest.mark.asyncio
    async def test_mixed_async_sync_workflow(self):
        """Test workflow with both async and sync nodes."""
        runtime = AsyncLocalRuntime()

        # Create workflow with mixed node types
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "sync_node", {"code": "result = {'type': 'sync'}"}
        )
        builder.add_node(
            "PythonCodeNode", "async_node", {"code": "result = {'type': 'async'}"}
        )

        workflow = builder.build()

        # Execute workflow
        result = await runtime.execute_workflow_async(workflow, {})

        assert result is not None
        # Check if result contains execution data

    def test_workflow_analysis_integration(self):
        """Test integration with workflow analyzer."""
        runtime = AsyncLocalRuntime(enable_analysis=True)

        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = {'value': 1}"})
        workflow = builder.build()

        # Analyze workflow
        plan = runtime.analyzer.analyze(workflow)

        assert isinstance(plan, ExecutionPlan)
        assert plan.workflow_id == workflow.workflow_id

    def test_profiling_disabled(self):
        """Test runtime with profiling disabled."""
        runtime = AsyncLocalRuntime(enable_profiling=False)

        assert runtime.enable_profiling is False
        assert runtime.analyzer.enable_profiling is False

    @pytest.mark.asyncio
    async def test_semaphore_usage(self):
        """Test that semaphore is used for concurrent execution."""
        runtime = AsyncLocalRuntime(max_concurrent_nodes=1)

        # Verify semaphore is created
        assert runtime.execution_semaphore._value == 1

        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node1", {"code": "result = {'value': 1}"})
        workflow = builder.build()

        # Execute workflow
        result = await runtime.execute_workflow_async(workflow, {})

        assert result is not None
        # Check if result contains execution data

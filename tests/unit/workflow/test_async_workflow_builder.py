"""
Comprehensive unit tests for AsyncWorkflowBuilder.

Tests cover core functionality, patterns, resource management, and error handling.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from kailash.resources.registry import ResourceFactory, ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.async_builder import (
    AsyncWorkflowBuilder,
    ErrorHandler,
    RetryPolicy,
)
from kailash.workflow.async_patterns import AsyncPatterns


class MockResourceFactory(ResourceFactory):
    """Mock resource factory for testing."""

    def __init__(self, resource_type="mock", **config):
        self.resource_type = resource_type
        self.config = config

    async def create(self):
        mock = AsyncMock()
        mock.type = self.resource_type

        # Add common methods based on type
        if self.resource_type == "database":
            mock.acquire = MagicMock()
            mock.acquire().__aenter__ = AsyncMock(return_value=mock)
            mock.acquire().__aexit__ = AsyncMock()
            mock.fetch = AsyncMock(
                return_value=[{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
            )
            mock.fetchrow = AsyncMock(return_value={"id": 1, "name": "Item 1"})
            mock.fetchval = AsyncMock(return_value=1)
        elif self.resource_type == "http":
            mock.get = AsyncMock()
            mock.post = AsyncMock()
            mock.request = AsyncMock()

            # Mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {}
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_response.text = AsyncMock(return_value="success")
            mock.get.return_value = mock_response
            mock.post.return_value = mock_response
            mock.request.return_value = mock_response
        elif self.resource_type == "cache":
            mock.get = AsyncMock(return_value=None)
            mock.set = AsyncMock()
            mock.setex = AsyncMock()
            mock.ping = AsyncMock(return_value=True)

        return mock

    def get_config(self):
        return {"type": self.resource_type, **self.config}


class TestAsyncWorkflowBuilder:
    """Test core AsyncWorkflowBuilder functionality."""

    def test_builder_initialization(self):
        """Test basic builder initialization."""
        builder = AsyncWorkflowBuilder("test_workflow", description="Test workflow")

        assert builder.name == "test_workflow"
        assert builder.description == "Test workflow"
        assert isinstance(builder._resource_registry, ResourceRegistry)
        assert builder._workflow_metadata["async_workflow"] is True
        assert builder._workflow_metadata["name"] == "test_workflow"

    def test_builder_auto_name(self):
        """Test automatic name generation."""
        builder = AsyncWorkflowBuilder()

        assert builder.name.startswith("async_workflow_")
        assert len(builder.name.split("_")[-1]) == 8  # UUID hex part

    def test_add_async_code_basic(self):
        """Test adding basic async code node."""
        builder = AsyncWorkflowBuilder()

        result = builder.add_async_code(
            "test_node", "result = {'value': 42}", timeout=60, description="Test node"
        )

        # Should return self for fluent interface
        assert result is builder

        # Check node was added
        assert "test_node" in builder.nodes

        # Check metadata
        metadata = builder.get_node_metadata("test_node")
        assert metadata["description"] == "Test node"

    def test_add_async_code_with_resources(self):
        """Test adding async code with resource requirements."""
        builder = AsyncWorkflowBuilder()

        builder.add_async_code(
            "db_node",
            "db = await get_resource('main_db')",
            required_resources=["main_db"],
            description="Database node",
        )

        assert "main_db" in builder._resource_requirements
        metadata = builder.get_node_metadata("db_node")
        assert "main_db" in metadata["required_resources"]

    def test_add_async_code_with_retry_policy(self):
        """Test adding async code with retry policy."""
        retry_policy = RetryPolicy(max_attempts=5, initial_delay=0.5)
        builder = AsyncWorkflowBuilder()

        builder.add_async_code(
            "retry_node", "result = {'attempt': 1}", retry_policy=retry_policy
        )

        assert "retry_node" in builder._retry_policies
        metadata = builder.get_node_metadata("retry_node")
        assert metadata["retry_policy"]["max_attempts"] == 5

    def test_add_async_code_with_error_handler(self):
        """Test adding async code with error handler."""
        error_handler = ErrorHandler("fallback", fallback_value={"error": True})
        builder = AsyncWorkflowBuilder()

        builder.add_async_code(
            "error_node", "raise ValueError('test')", error_handler=error_handler
        )

        assert "error_node" in builder._error_handlers
        metadata = builder.get_node_metadata("error_node")
        assert metadata["error_handler"]["type"] == "fallback"

    def test_code_validation_valid(self):
        """Test code validation with valid code."""
        builder = AsyncWorkflowBuilder()

        # These should not raise
        builder._validate_async_code("result = {'value': 42}")
        builder._validate_async_code("await asyncio.sleep(1)")
        builder._validate_async_code(
            """
async def helper():
    await asyncio.sleep(1)
    return 42

result = await helper()
"""
        )

    def test_code_validation_invalid(self):
        """Test code validation with invalid code."""
        builder = AsyncWorkflowBuilder()

        # Syntax error should raise
        with pytest.raises(ValueError, match="Invalid Python code"):
            builder._validate_async_code("result = {")

    def test_function_validation_valid(self):
        """Test function validation with valid function."""
        builder = AsyncWorkflowBuilder()

        # Valid sync function
        builder._validate_async_function(
            """
def process_item(item):
    return item * 2
"""
        )

        # Valid async function
        builder._validate_async_function(
            """
async def process_item(item):
    await asyncio.sleep(0.1)
    return item * 2
"""
        )

    def test_function_validation_invalid(self):
        """Test function validation with invalid function."""
        builder = AsyncWorkflowBuilder()

        # Missing process_item function
        with pytest.raises(ValueError, match="must define 'def process_item"):
            builder._validate_async_function("def other_function(): pass")

    def test_resource_management(self):
        """Test resource requirement tracking."""
        builder = AsyncWorkflowBuilder()
        factory = MockResourceFactory("database")

        builder.require_resource("test_db", factory, description="Test database")

        assert "test_db" in builder._resource_requirements
        assert "test_db" in builder._workflow_metadata["resources"]
        assert (
            builder._workflow_metadata["resources"]["test_db"]["description"]
            == "Test database"
        )

    def test_with_database(self):
        """Test database resource helper."""
        builder = AsyncWorkflowBuilder()

        result = builder.with_database(
            name="main_db", host="localhost", database="testdb", user="testuser"
        )

        assert result is builder  # Fluent interface
        assert "main_db" in builder._resource_requirements
        assert "main_db" in builder._workflow_metadata["resources"]

    def test_with_http_client(self):
        """Test HTTP client resource helper."""
        builder = AsyncWorkflowBuilder()

        result = builder.with_http_client(
            name="api_client",
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer token"},
        )

        assert result is builder
        assert "api_client" in builder._resource_requirements

    def test_with_cache(self):
        """Test cache resource helper."""
        builder = AsyncWorkflowBuilder()

        result = builder.with_cache(
            name="redis_cache", backend="redis", host="localhost", port=6379
        )

        assert result is builder
        assert "redis_cache" in builder._resource_requirements

    def test_with_cache_invalid_backend(self):
        """Test cache with invalid backend."""
        builder = AsyncWorkflowBuilder()

        with pytest.raises(ValueError, match="Unsupported cache backend"):
            builder.with_cache(backend="memcached")

    def test_build_workflow(self):
        """Test building workflow with metadata."""
        builder = AsyncWorkflowBuilder("test_workflow")

        builder.add_async_code("node1", "result = {'value': 1}")
        builder.add_async_code("node2", "result = {'value': input_value * 2}")
        builder.add_connection("node1", "value", "node2", "input_value")

        workflow = builder.build()

        assert hasattr(workflow, "metadata")
        assert workflow.metadata["async_workflow"] is True
        assert workflow.metadata["name"] == "test_workflow"
        assert "node1" in workflow.nodes
        assert "node2" in workflow.nodes
        assert hasattr(workflow, "resource_registry")

    def test_list_required_resources(self):
        """Test listing required resources."""
        builder = AsyncWorkflowBuilder()

        builder.with_database("db1")
        builder.with_http_client("http1")
        builder.add_async_code("node1", "pass", required_resources=["custom_resource"])

        resources = builder.list_required_resources()
        assert "db1" in resources
        assert "http1" in resources
        assert "custom_resource" in resources


class TestParallelMapPattern:
    """Test parallel map functionality."""

    @pytest.mark.asyncio
    async def test_parallel_map_basic(self):
        """Test basic parallel map functionality."""
        builder = AsyncWorkflowBuilder()

        # Add input generator
        builder.add_async_code("generate", "result = {'items': list(range(5))}")

        # Add parallel map
        builder.add_parallel_map(
            "process",
            """
async def process_item(item):
    await asyncio.sleep(0.01)  # Simulate work
    return item * item
""",
            max_workers=3,
        )

        builder.add_connection("generate", "items", "process", "items")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        print(
            f"DEBUG: Result structure: {list(result.keys()) if isinstance(result, dict) else type(result)}"
        )
        if isinstance(result, dict) and "results" in result:
            print(f"DEBUG: Node results: {list(result['results'].keys())}")

        # Check result structure - AsyncLocalRuntime may have different format
        if "results" in result:
            assert "generate" in result["results"]
            assert "process" in result["results"]

            output = result["results"]["process"]
            assert "results" in output
            assert output["results"] == [0, 1, 4, 9, 16]
            assert output["statistics"]["successful"] == 5
            assert output["statistics"]["failed"] == 0
        else:
            # Fallback for different result structure
            assert result["status"] == "success"
            output = result["results"]["process"]
            assert output["results"] == [0, 1, 4, 9, 16]
            assert output["statistics"]["successful"] == 5
            assert output["statistics"]["failed"] == 0

    @pytest.mark.asyncio
    async def test_parallel_map_with_errors(self):
        """Test parallel map with some failures."""
        builder = AsyncWorkflowBuilder()

        builder.add_async_code(
            "generate", "result = {'items': [1, 2, 0, 4, 5]}"
        )  # 0 will cause division error

        builder.add_parallel_map(
            "process",
            """
async def process_item(item):
    if item == 0:
        raise ValueError("Cannot process zero")
    return 10 / item
""",
            continue_on_error=True,
        )

        builder.add_connection("generate", "items", "process", "items")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "process" in result["results"]

        output = result["results"]["process"]
        assert len(output["results"]) == 4  # 4 successful
        assert output["statistics"]["failed"] == 1
        assert len(output["errors"]) == 1

    @pytest.mark.asyncio
    async def test_parallel_map_batch_processing(self):
        """Test parallel map with batch processing."""
        builder = AsyncWorkflowBuilder()

        builder.add_async_code("generate", "result = {'items': list(range(10))}")

        builder.add_parallel_map(
            "process",
            """
async def process_item(item):
    return item * 2
""",
            batch_size=3,
            max_workers=2,
        )

        builder.add_connection("generate", "items", "process", "items")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "process" in result["results"]

        output = result["results"]["process"]
        assert output["results"] == [i * 2 for i in range(10)]


class TestScatterGatherPattern:
    """Test scatter-gather pattern."""

    @pytest.mark.asyncio
    async def test_scatter_gather_basic(self):
        """Test basic scatter-gather functionality."""
        builder = AsyncWorkflowBuilder()

        builder.add_async_code("generate", "result = {'items': list(range(20))}")

        builder.add_scatter_gather(
            "scatter",
            "worker",
            "gather",
            """
def process_item(item):
    return {"original": item, "squared": item * item}
""",
            worker_count=4,
        )

        builder.add_connection("generate", "items", "scatter", "items")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result

        # Since scatter-gather uses parallel_map, check for that output format
        scatter_output = result["results"]["scatter"]
        assert "results" in scatter_output
        assert "statistics" in scatter_output
        assert scatter_output["statistics"]["total"] == 20
        assert scatter_output["statistics"]["successful"] == 20
        assert len(scatter_output["results"]) == 20

    @pytest.mark.asyncio
    async def test_scatter_gather_empty_input(self):
        """Test scatter-gather with empty input."""
        builder = AsyncWorkflowBuilder()

        builder.add_async_code("generate", "result = {'items': []}")

        builder.add_scatter_gather(
            "scatter",
            "worker",
            "gather",
            "def process_item(item): return item",
            worker_count=2,
        )

        builder.add_connection("generate", "items", "scatter", "items")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "scatter" in result["results"]

        # Since scatter-gather uses parallel_map, check for that output format
        scatter_output = result["results"]["scatter"]
        assert "results" in scatter_output
        assert "statistics" in scatter_output
        assert scatter_output["statistics"]["total"] == 0
        assert scatter_output["statistics"]["successful"] == 0
        assert len(scatter_output["results"]) == 0


class TestResourceNodePattern:
    """Test resource node functionality."""

    @pytest.mark.asyncio
    async def test_resource_node_database(self):
        """Test resource node with database."""
        registry = ResourceRegistry()
        builder = AsyncWorkflowBuilder(resource_registry=registry)

        # Register mock database
        db_factory = MockResourceFactory("database")
        registry.register_factory("test_db", db_factory)

        builder.add_resource_node(
            "fetch_data", "test_db", "fetch", {"query": "SELECT * FROM items"}
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=registry)

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "fetch_data" in result["results"]

        output = result["results"]["fetch_data"]
        assert output["resource"] == "test_db"
        assert output["operation"] == "fetch"

    @pytest.mark.asyncio
    async def test_resource_node_http(self):
        """Test resource node with HTTP client."""
        registry = ResourceRegistry()
        builder = AsyncWorkflowBuilder(resource_registry=registry)

        # Register mock HTTP client
        http_factory = MockResourceFactory("http")
        registry.register_factory("api_client", http_factory)

        builder.add_resource_node("api_call", "api_client", "get", {"url": "/users"})

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=registry)

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "api_call" in result["results"]

        output = result["results"]["api_call"]
        assert output["resource"] == "api_client"
        assert output["operation"] == "get"


class TestAsyncPatterns:
    """Test async pattern implementations."""

    @pytest.mark.asyncio
    async def test_retry_pattern_success(self):
        """Test retry pattern with eventual success."""
        builder = AsyncWorkflowBuilder()

        # Add a counter to track attempts
        builder.add_async_code("setup", "result = {'attempt_count': 0}")

        AsyncPatterns.retry_with_backoff(
            builder,
            "retry_node",
            """
# Simulate failing first 2 times
attempt_count += 1
if attempt_count < 3:
    raise ValueError(f"Attempt {attempt_count} failed")
result = {"attempts": attempt_count, "success": True}
""",
            max_retries=5,
            initial_backoff=0.01,
        )

        builder.add_connection("setup", "attempt_count", "retry_node", "attempt_count")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "retry_node" in result["results"]

        output = result["results"]["retry_node"]
        assert output["success"] is True
        assert output["total_attempts"] == 3

    @pytest.mark.asyncio
    async def test_rate_limiting_pattern(self):
        """Test rate limiting pattern."""
        builder = AsyncWorkflowBuilder()

        AsyncPatterns.rate_limited(
            builder,
            "rate_limited_node",
            """
import time
start_time = time.time()
# Simulate some work
await asyncio.sleep(0.01)
result = {"processed_at": start_time}
""",
            requests_per_second=100,  # High rate for testing
            burst_size=5,
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "rate_limited_node" in result["results"]

        output = result["results"]["rate_limited_node"]
        assert "_rate_limit_info" in output
        assert "tokens_remaining" in output["_rate_limit_info"]

    @pytest.mark.asyncio
    async def test_timeout_with_fallback_success(self):
        """Test timeout with fallback - primary succeeds."""
        builder = AsyncWorkflowBuilder()

        AsyncPatterns.timeout_with_fallback(
            builder,
            "primary",
            "fallback",
            """
# Primary operation (fast)
await asyncio.sleep(0.01)
result = {"value": "primary_result"}
""",
            """
# Fallback operation
result = {"value": "fallback_result"}
""",
            timeout_seconds=1.0,
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "fallback" in result["results"]

        output = result["results"]["fallback"]
        assert output["_source"] == "primary"
        assert output["value"] == "primary_result"

    @pytest.mark.asyncio
    async def test_timeout_with_fallback_timeout(self):
        """Test timeout with fallback - primary times out."""
        builder = AsyncWorkflowBuilder()

        AsyncPatterns.timeout_with_fallback(
            builder,
            "primary",
            "fallback",
            """
# Primary operation (slow)
await asyncio.sleep(2.0)
result = {"value": "primary_result"}
""",
            """
# Fallback operation
result = {"value": "fallback_result"}
""",
            timeout_seconds=0.1,
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "fallback" in result["results"]

        output = result["results"]["fallback"]
        assert output["_source"] == "fallback"
        assert output["value"] == "fallback_result"
        assert output["_primary_timeout"] is True

    @pytest.mark.asyncio
    async def test_batch_processor_pattern(self):
        """Test batch processor pattern."""
        builder = AsyncWorkflowBuilder()

        builder.add_async_code("generate", "result = {'items': list(range(10))}")

        AsyncPatterns.batch_processor(
            builder,
            "batch_process",
            """
# Process batch of items
batch_results = []
for item in items:
    batch_results.append(item * 2)
""",
            batch_size=5,
            flush_interval=0.1,
        )

        builder.add_connection("generate", "items", "batch_process", "items")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "batch_process" in result["results"]

        output = result["results"]["batch_process"]
        # Batch processor processes in batches of 5, so first batch gets 5 items
        assert output["processed_count"] == 5
        assert output["remaining_in_batch"] == 5  # The other 5 items are still waiting
        assert output["flush_reason"] == "batch_full"

    @pytest.mark.asyncio
    async def test_circuit_breaker_pattern(self):
        """Test circuit breaker pattern."""
        builder = AsyncWorkflowBuilder()

        AsyncPatterns.circuit_breaker(
            builder,
            "protected_operation",
            """
# Operation that succeeds
result = {"value": "success", "operation_completed": True}
""",
            failure_threshold=3,
            reset_timeout=1.0,
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "protected_operation" in result["results"]

        output = result["results"]["protected_operation"]
        assert output["operation_completed"] is True
        assert "_circuit_breaker_info" in output

    @pytest.mark.asyncio
    async def test_parallel_fetch_pattern(self):
        """Test parallel fetch pattern."""
        builder = AsyncWorkflowBuilder()

        AsyncPatterns.parallel_fetch(
            builder,
            "multi_fetch",
            {
                "users": 'result = {"users": [{"id": 1, "name": "Alice"}]}',
                "orders": 'result = {"orders": [{"id": 101, "user_id": 1}]}',
                "products": 'result = {"products": [{"id": 201, "name": "Widget"}]}',
            },
            timeout_per_operation=1.0,
            continue_on_error=True,
        )

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result
        assert "multi_fetch" in result["results"]

        output = result["results"]["multi_fetch"]
        assert len(output["successful"]) == 3
        assert "users" in output["successful"]
        assert "orders" in output["successful"]
        assert "products" in output["successful"]

    @pytest.mark.asyncio
    async def test_cache_aside_pattern(self):
        """Test cache aside pattern."""
        registry = ResourceRegistry()
        builder = AsyncWorkflowBuilder(resource_registry=registry)

        # Register mock cache
        cache_factory = MockResourceFactory("cache")
        registry.register_factory("cache", cache_factory)

        builder.add_async_code("setup", "result = {'item_id': 123}")

        AsyncPatterns.cache_aside(
            builder,
            "cache_check",
            "data_fetch",
            "cache_store",
            """
# Fetch data operation
result = {"id": item_id, "name": f"Item {item_id}", "value": 42}
""",
            cache_resource="cache",
            cache_key_template="item_{item_id}",
            ttl_seconds=300,
        )

        builder.add_connection("setup", "item_id", "cache_check", "item_id")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=registry)

        result = await runtime.execute_workflow_async(workflow, {})

        # Check for results - AsyncLocalRuntime returns different format
        assert "results" in result

        # Check that data was fetched (cache miss scenario)
        cache_result = result["results"]["cache_check"]
        assert cache_result["found_in_cache"] is False

        final_result = result["results"]["cache_store"]
        assert final_result["data"]["id"] == 123


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_resource_access(self):
        """Test handling of invalid resource access."""
        from kailash.sdk_exceptions import WorkflowExecutionError

        builder = AsyncWorkflowBuilder()

        builder.add_resource_node("invalid_resource", "nonexistent_resource", "fetch")

        workflow = builder.build()
        runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())

        # Expecting WorkflowExecutionError for invalid resource access
        with pytest.raises(WorkflowExecutionError) as exc_info:
            await runtime.execute_workflow_async(workflow, {})

        assert "nonexistent_resource" in str(exc_info.value)

    def test_fluent_interface_chaining(self):
        """Test fluent interface method chaining."""
        workflow = (
            AsyncWorkflowBuilder("chained_workflow")
            .with_database("db")
            .with_http_client("api")
            .with_cache("cache")
            .add_async_code("node1", "result = {'step': 1}")
            .add_async_code("node2", "result = {'step': 2}")
            .add_connection("node1", "step", "node2", "prev_step")
            .build()
        )

        assert workflow.metadata["name"] == "chained_workflow"
        assert "node1" in workflow.nodes
        assert "node2" in workflow.nodes
        assert len(workflow.connections) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

# Testing Async Workflows

This guide covers testing patterns for async workflows, including proper mock setup and common pitfalls.

## Mock Workflow Setup

When creating mock workflows for testing async runtime components, you must use proper networkx graphs:

### ✅ Correct Pattern

```python
import networkx as nx
from typing import Any, Dict

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
```

### ❌ Incorrect Pattern (Will Fail)

```python
from unittest.mock import MagicMock

class MockWorkflow:
    def __init__(self, nodes: Dict[str, Any] = None):
        self._node_instances = nodes or {}
        self.graph = MagicMock()  # This won't work!
        # MagicMock doesn't implement nx.topological_sort properly
```

## Adding Dependencies

When testing workflows with dependencies, add edges to the graph:

```python
# Create workflow with dependencies
nodes = {
    "node1": MockAsyncNode("result1"),
    "node2": MockAsyncNode("result2"),
    "node3": MockAsyncNode("result3")
}
workflow = MockWorkflow(nodes)

# Add edges to create dependencies: node1 -> node2 -> node3
workflow.graph.add_connection("node1", "node2")
workflow.graph.add_connection("node2", "node3")
```

## Mock Node Implementation

Mock nodes must implement the required abstract methods:

```python
from kailash.nodes.base import Node
from kailash.nodes.base_async import AsyncNode

class MockSyncNode(Node):
    """Mock synchronous node for testing."""

    def __init__(self, result="sync_result", delay=0.1):
        self.result = result
        self.delay = delay
        self.execution_count = 0

    def execute(self, **kwargs):
        self.execution_count += 1
        time.sleep(self.delay)
        return self.result

    def get_parameters(self):
        """Required: Return empty parameters for mock node."""
        return {}

class MockAsyncNode(AsyncNode):
    """Mock asynchronous node for testing."""

    def __init__(self, result="async_result", delay=0.1):
        self.result = result
        self.delay = delay
        self.execution_count = 0

    async def async_run(self, resource_registry=None, **kwargs):
        self.execution_count += 1
        await asyncio.sleep(self.delay)
        return self.result

    def get_parameters(self):
        """Required: Return empty parameters for mock node."""
        return {}
```

## Testing Async Fixtures

Use `pytest_asyncio` for async fixtures:

```python
import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def resource_registry():
    """Create resource registry for testing."""
    registry = ResourceRegistry()
    # Setup resources
    yield registry
    # Cleanup
    await registry.cleanup()

@pytest_asyncio.fixture
async def production_gateway(resource_registry):
    """Create gateway with proper cleanup."""
    gateway = EnhancedDurableAPIGateway(
        resource_registry=resource_registry,
        enable_durability=True
    )
    yield gateway
    # Important: Call shutdown to cleanup async tasks
    await gateway.shutdown()
```

## Gateway Shutdown Pattern

When testing gateways that create background tasks, ensure proper cleanup:

```python
class EnhancedDurableAPIGateway:
    def __init__(self):
        self._cleanup_tasks: List[asyncio.Task] = []

    async def _cleanup_request(self, request_id: str, delay: int = 3600):
        """Clean up request after delay."""
        try:
            await asyncio.sleep(delay)
            if request_id in self._active_requests:
                del self._active_requests[request_id]
        except asyncio.CancelledError:
            # Task was cancelled during shutdown
            pass

    async def shutdown(self):
        """Shutdown gateway and cleanup resources."""
        # Cancel all cleanup tasks
        for task in self._cleanup_tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self._cleanup_tasks:
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        # Clear resources
        self._cleanup_tasks.clear()
        self._active_requests.clear()

        # Call parent cleanup if exists
        if hasattr(super(), 'close'):
            await super().close()
```

## Common Testing Issues

### 1. Async Task Cleanup Errors

**Problem**: "Task was destroyed but it is pending" errors during test teardown.

**Solution**: Implement proper shutdown methods that cancel background tasks.

### 2. Mock Graph Issues

**Problem**: `nx.topological_sort` fails with MagicMock graphs.

**Solution**: Use real `nx.DiGraph()` instances in mock workflows.

### 3. Missing Abstract Methods

**Problem**: "Can't instantiate abstract class" errors.

**Solution**: Implement all required abstract methods like `get_parameters()`.

### 4. Fixture Declaration

**Problem**: Async fixtures not properly recognized.

**Solution**: Use `@pytest_asyncio.fixture` instead of `@pytest.fixture`.

## Test Markers

Mark tests appropriately for conditional execution:

```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_docker
class TestAsyncRuntimeRealWorld:
    """Integration tests requiring Docker services."""

    async def test_database_etl_pipeline(self):
        # Test will be skipped if Docker is not available
        pass
```

## Testing Memory Storage LRU

When testing LRU eviction, ensure data sizes trigger eviction:

```python
async def test_lru_eviction():
    storage = MemoryStorage(max_size_mb=1)  # 1MB limit

    await storage.save("key1", b"data1")  # 5 bytes
    await storage.save("key2", b"data2")  # 5 bytes

    # Access key1 to make it most recently used
    await storage.load("key1")

    # Add large data to trigger eviction
    # Must exceed 1MB when combined with existing data
    large_data = b"x" * (1024 * 1024 - 5)  # Just under 1MB
    await storage.save("key3", large_data)

    # key2 should be evicted (least recently used)
    assert await storage.load("key1") is not None
    assert await storage.load("key2") is None  # Evicted
    assert await storage.load("key3") is not None
```

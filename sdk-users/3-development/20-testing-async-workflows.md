# Testing Async Workflows Guide

*Comprehensive testing strategies for async workflows*

## Overview

Testing async workflows requires special considerations for concurrency, timing, and resource management. This guide provides patterns and best practices for thorough async workflow testing.

## Prerequisites

- Completed [Async Testing Framework](13-async-testing-framework.md)
- Understanding of [Async Workflow Builder](07-async-workflow-builder.md)
- Familiarity with pytest-asyncio

## Testing Async Workflows

### Basic Async Test Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
import pytest
import asyncio
from kailash.workflow.async_builder import AsyncWorkflowBuilder
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.testing import AsyncWorkflowTestCase

@pytest.mark.asyncio
class TestAsyncWorkflows(AsyncWorkflowTestCase):
    async def setUp(self):
        await super().setUp()
        self.runtime = AsyncLocalRuntime()

    async def test_simple_async_workflow(self):
        """Test basic async workflow execution."""
        # Build workflow
        workflow = (
            AsyncWorkflowBuilder("test_workflow")
            .add_async_code("fetch_data", """
import asyncio
await asyncio.sleep(0.1)  # Simulate async operation
result = {"data": [1, 2, 3]}
""")
            .build()
        )

        # Execute and verify
        result = await self.execute_workflow(workflow)
        self.assert_workflow_success(result)
        assert result.outputs["fetch_data"]["data"] == [1, 2, 3]
```

### Testing Concurrent Operations

```python
async def test_concurrent_node_execution(self):
    """Test nodes executing concurrently."""
    workflow = (
        AsyncWorkflowBuilder("concurrent_test")
        .add_async_code("task1", """
import asyncio
start_time = time.time()
await asyncio.sleep(1)
result = {"task": "task1", "duration": time.time() - start_time}
""")
        .add_async_code("task2", """
import asyncio
start_time = time.time()
await asyncio.sleep(1)
result = {"task": "task2", "duration": time.time() - start_time}
""")
        .with_parallel_execution()  # Enable parallel execution
        .build()
    )

    start = time.time()
    result = await self.execute_workflow(workflow)
    total_time = time.time() - start

    # Both tasks should complete in ~1 second (parallel)
    assert total_time < 1.5  # Not 2 seconds (sequential)
    assert result.outputs["task1"]["duration"] >= 1
    assert result.outputs["task2"]["duration"] >= 1
```

### Testing Resource Management

```python
async def test_resource_cleanup(self):
    """Test proper resource cleanup in async workflows."""
    # Track resource lifecycle
    resources_created = []
    resources_cleaned = []

    async def create_resource(name):
        resources_created.append(name)
        return f"resource_{name}"

    async def cleanup_resource(name):
        resources_cleaned.append(name)

    # Workflow using resources
    workflow = (
        AsyncWorkflowBuilder("resource_test")
        .add_async_code("use_resources", """
# Create resources
db = await create_resource("database")
cache = await create_resource("cache")

try:
    # Use resources
    result = {"db": db, "cache": cache}
finally:
    # Cleanup
    await cleanup_resource("database")
    await cleanup_resource("cache")
""")
        .build()
    )

    # Inject resource functions
    self.runtime.register_function(create_resource)
    self.runtime.register_function(cleanup_resource)

    # Execute workflow
    result = await self.execute_workflow(workflow)

    # Verify cleanup
    assert len(resources_created) == 2
    assert len(resources_cleaned) == 2
    assert set(resources_created) == set(resources_cleaned)
```

## Testing Error Handling

### Async Error Propagation

```python
async def test_async_error_handling(self):
    """Test error handling in async workflows."""
    workflow = (
        AsyncWorkflowBuilder("error_test")
        .add_async_code("failing_task", """
import asyncio
await asyncio.sleep(0.1)
raise ValueError("Simulated async error")
""")
        .add_async_code("recovery_task", """
# This should not execute
result = {"should_not_see": True}
""")
        .add_connection("failing_task", "result", "recovery_task", "input")
        .build()
    )

    # Workflow should fail
    with pytest.raises(ValueError, match="Simulated async error"):
        await self.execute_workflow(workflow)

    # Verify partial execution
    assert self.get_node_execution_count("failing_task") == 1
    assert self.get_node_execution_count("recovery_task") == 0
```

### Timeout Testing

```python
async def test_workflow_timeout(self):
    """Test workflow timeout handling."""
    workflow = (
        AsyncWorkflowBuilder("timeout_test")
        .add_async_code("slow_task", """
import asyncio
await asyncio.sleep(10)  # Longer than timeout
result = {"completed": True}
""")
        .with_timeout(1.0)  # 1 second timeout
        .build()
    )

    # Should timeout
    with pytest.raises(asyncio.TimeoutError):
        await self.execute_workflow(workflow)
```

## Testing Complex Patterns

### Testing Retry Logic

```python
async def test_async_retry_pattern(self):
    """Test retry logic in async workflows."""
    attempt_count = 0

    async def flaky_operation():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ConnectionError("Temporary failure")
        return {"success": True, "attempts": attempt_count}

    workflow = (
        AsyncWorkflowBuilder("retry_test")
        .add_async_code("retry_operation", """
max_retries = 3
retry_delay = 0.1

for attempt in range(max_retries):
    try:
        result = await flaky_operation()
        break
    except ConnectionError as e:
        if attempt == max_retries - 1:
            raise
        await asyncio.sleep(retry_delay * (2 ** attempt))
""")
        .build()
    )

    self.runtime.register_function(flaky_operation)

    result = await self.execute_workflow(workflow)
    assert result.outputs["retry_operation"]["success"] == True
    assert result.outputs["retry_operation"]["attempts"] == 3
```

### Testing Event-Driven Patterns

```python
async def test_event_driven_workflow(self):
    """Test event-driven async patterns."""
    events_received = []

    workflow = (
        AsyncWorkflowBuilder("event_workflow")
        .add_async_code("event_listener", """
# Set up event listener
event_queue = asyncio.Queue()

async def process_events():
    events = []
    while True:
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
            events.append(event)
            if event.get("type") == "stop":
                break
        except asyncio.TimeoutError:
            break
    return events

# Start processing
result = {"events": await process_events()}
""")
        .build()
    )

    # Simulate events
    async def send_events():
        await asyncio.sleep(0.1)
        await event_queue.put({"type": "data", "value": 1})
        await event_queue.put({"type": "data", "value": 2})
        await event_queue.put({"type": "stop"})

    # Run workflow with events
    await asyncio.gather(
        self.execute_workflow(workflow),
        send_events()
    )
```

## Performance Testing

### Load Testing Async Workflows

```python
async def test_workflow_under_load(self):
    """Test workflow performance under load."""
    workflow = (
        AsyncWorkflowBuilder("load_test")
        .add_async_code("process_item", """
# Simulate processing
await asyncio.sleep(0.01)
result = {"processed": item_id, "timestamp": time.time()}
""")
        .build()
    )

    # Execute many workflows concurrently
    tasks = []
    start_time = time.time()

    for i in range(100):
        task = self.execute_workflow(
            workflow,
            parameters={"process_item": {"item_id": i}}
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time

    # Verify performance
    assert all(r.success for r in results)
    assert total_time < 2.0  # Should complete quickly with concurrency

    # Calculate throughput
    throughput = len(results) / total_time
    assert throughput > 50  # At least 50 workflows/second
```

### Memory Usage Testing

```python
async def test_memory_efficiency(self):
    """Test workflow memory usage."""
    import tracemalloc

    tracemalloc.start()

    # Large data workflow
    workflow = (
        AsyncWorkflowBuilder("memory_test")
        .add_async_code("generate_data", """
# Generate large dataset
import numpy as np
data = np.random.rand(1000, 1000)  # ~8MB
result = {"shape": data.shape, "mean": float(data.mean())}
# Data should be garbage collected
""")
        .build()
    )

    # Track memory
    initial_memory = tracemalloc.get_traced_memory()[0]

    # Execute multiple times
    for _ in range(10):
        await self.execute_workflow(workflow)

    final_memory = tracemalloc.get_traced_memory()[0]
    memory_increase = final_memory - initial_memory

    # Memory should not grow significantly
    assert memory_increase < 10 * 1024 * 1024  # Less than 10MB increase

    tracemalloc.stop()
```

## Testing Best Practices

### 1. Isolate Async Tests

```python
@pytest.fixture
async def isolated_runtime():
    """Create isolated runtime for each test."""
    runtime = AsyncLocalRuntime()
    yield runtime
    await runtime.shutdown()  # Cleanup

async def test_with_isolation(isolated_runtime):
    """Test using isolated runtime."""
    workflow = create_test_workflow()
    result = await isolated_runtime.execute(workflow.build())
    assert result.success
```

### 2. Mock External Services

```python
async def test_with_mocked_services(self):
    """Test with mocked external services."""
    # Mock HTTP client
    from unittest.mock import AsyncMock
    mock_http = AsyncMock()
    mock_http.get.return_value = {"status": 200, "data": "test"}

    await self.create_test_resource("http", lambda: mock_http, mock=True)

    workflow = (
        AsyncWorkflowBuilder("api_test")
        .add_async_code("fetch_api", """
http = await get_resource("http")
response = await http.get("/api/data")
result = {"api_data": response["data"]}
""")
        .build()
    )

    result = await self.execute_workflow(workflow)
    assert result.outputs["fetch_api"]["api_data"] == "test"
    mock_http.get.assert_called_once()
```

### 3. Test Cleanup

```python
async def test_with_cleanup(self):
    """Ensure proper cleanup after tests."""
    cleanup_called = False

    async def cleanup_function():
        nonlocal cleanup_called
        cleanup_called = True

    try:
        workflow = create_test_workflow()
        result = await self.execute_workflow(workflow)
        assert result.success
    finally:
        await cleanup_function()
        assert cleanup_called
```

## Debugging Async Tests

### Enable Debug Logging

```python
import logging

# Enable async debugging
logging.getLogger("kailash.async").setLevel(logging.DEBUG)
logging.getLogger("asyncio").setLevel(logging.DEBUG)

# Trace async execution
async def test_with_tracing(self):
    """Test with execution tracing."""
    self.enable_tracing()

    workflow = create_complex_workflow()
    result = await self.execute_workflow(workflow)

    # Analyze trace
    trace = self.get_execution_trace()
    print(f"Execution steps: {len(trace)}")
    for step in trace:
        print(f"  {step['timestamp']}: {step['event']}")
```

### Async Deadlock Detection

```python
async def test_deadlock_detection(self):
    """Test detection of async deadlocks."""
    with pytest.raises(DeadlockError):
        workflow = (
            AsyncWorkflowBuilder("deadlock_test")
            .add_async_code("task1", """
# Wait for task2 result
result = await wait_for_result("task2")
""")
            .add_async_code("task2", """
# Wait for task1 result - circular dependency!
result = await wait_for_result("task1")
""")
            .with_deadlock_detection(timeout=5.0)
            .build()
        )

        await self.execute_workflow(workflow)
```

## Related Guides

**Prerequisites:**
- [Async Testing Framework](13-async-testing-framework.md) - Testing basics
- [Async Workflow Builder](07-async-workflow-builder.md) - Async patterns

**Advanced Topics:**
- [Testing Production Quality](12-testing-production-quality.md) - General testing
- [Production Hardening](16-production-hardening.md) - Production concerns

---

**Build reliable async workflows with comprehensive testing strategies!**

# Unified Async Runtime Developer Guide

*High-performance async workflow execution with concurrent processing*

## Overview

The Unified Async Runtime (AsyncLocalRuntime) brings first-class async support to Kailash workflows. It automatically optimizes your workflows for concurrent execution while maintaining full backwards compatibility with existing sync workflows.

> ✅ **Production Ready**: Extensively tested with 23 comprehensive tests across unit, integration, and user flow scenarios. Validated with real PostgreSQL, Redis, Ollama, and HTTP services.

## Key Features

- **Automatic Concurrency**: Analyzes workflows and runs independent nodes in parallel
- **Mixed Sync/Async Support**: Seamlessly handles both sync and async nodes
- **Performance Monitoring**: Built-in metrics and profiling capabilities
- **Resource Integration**: Full support for ResourceRegistry and shared resources
- **2-10x Performance**: Significant speedup for workflows with parallel branches

## Quick Start

### Basic Usage

```python
from kailash.runtime.async_local import AsyncLocalRuntime
import asyncio

# Create async runtime
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=10,
    enable_analysis=True
)

# Execute any workflow
async def run_workflow():
    results, run_id = await runtime.execute_workflow_async(workflow, {"input": "data"})
    print(f"Run ID: {run_id}")
    print(f"Results: {results}")
    return results

# Run with asyncio
asyncio.run(run_workflow())
```

### With Resource Management

```python
from kailash.resources import ResourceRegistry, DatabasePoolFactory
from kailash.runtime.async_local import AsyncLocalRuntime

# Setup shared resources
registry = ResourceRegistry()
registry.register_factory(
    "main_db",
    DatabasePoolFactory(
        host="localhost",
        database="myapp",
        user="postgres",
        password="your_password"
    )
)

# Create runtime with resource support
runtime = AsyncLocalRuntime(
    resource_registry=registry,
    max_concurrent_nodes=10,
    enable_analysis=True
)

# Execute workflow - nodes can access resources via get_resource()
results, run_id = await runtime.execute_workflow_async(workflow, inputs)
```

## Return Structure

**AsyncLocalRuntime now returns a tuple** `(results, run_id)` for consistency with LocalRuntime (v0.9.31+):

```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()

# NEW (v0.9.31+): Returns tuple
results, run_id = await runtime.execute_workflow_async(workflow, inputs={"param": "value"})

# Access results:
print(results["node_id"]["result"])  # Node output
print(run_id)                        # Execution ID

# Example results structure:
# {
#     "node_id": {"result": {...}},  # Node outputs
#     "another_node": {"result": {...}}
# }
```

This consistent return structure ensures that both sync and async runtimes work identically, making it easy to switch between them without code changes.

## Configuration Options

### Runtime Settings

```python
runtime = AsyncLocalRuntime(
    # Concurrency control
    max_concurrent_nodes=10,      # Max parallel node execution
    thread_pool_size=4,           # Workers for sync nodes

    # Feature toggles
    enable_analysis=True,         # Workflow optimization
    enable_profiling=True,        # Performance metrics

    # Resource management
    resource_registry=registry    # Shared resource access
)
```

### Performance Tuning

**For High Throughput:**
```python
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=20,      # More parallelism
    thread_pool_size=8,           # More sync workers
    enable_analysis=True          # Optimization enabled
)
```

**For Resource-Constrained Environments:**
```python
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=4,       # Limited parallelism
    thread_pool_size=2,           # Fewer workers
    enable_profiling=False        # Reduce overhead
)
```

**For Development/Debugging:**
```python
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=1,       # Sequential execution
    enable_profiling=True,        # Detailed metrics
    enable_analysis=True          # Analysis logging
)
```

## Workflow Patterns

### 1. Automatic Concurrency

The runtime analyzes your workflow and runs independent nodes concurrently:

```python
from kailash.workflow.builder import WorkflowBuilder

# This workflow will run process1 and process2 in parallel
workflow = WorkflowBuilder()

# Input node
workflow.add_node("PythonCodeNode", "input", {
    "code": "result = {'data': [1, 2, 3, 4, 5]}"
})

# Two parallel processors (note: inputs must be in result dict)
workflow.add_node("PythonCodeNode", "process1", {
    "code": """
# Access input via 'input_data' parameter
doubled = [x * 2 for x in input_data]
result = {'processed': doubled}
"""
})

workflow.add_node("PythonCodeNode", "process2", {
    "code": """
# Access input via 'input_data' parameter
squared = [x ** 2 for x in input_data]
result = {'processed': squared}
"""
})

# Connect parallel branches
workflow.add_connection("input", "result.data", "process1", "input_data")
workflow.add_connection("input", "result.data", "process2", "input_data")

# Both processors run simultaneously
async def execute():
    start_time = time.time()
    results, run_id = await runtime.execute_workflow_async(workflow.build(), {})
    print(f"Parallel execution took {time.time() - start_time:.2f}s")
    return results

asyncio.run(execute())
```

### 2. Mixed Sync/Async Support

Works seamlessly with both sync and async nodes:

```python
from kailash.nodes.code import AsyncPythonCodeNode, PythonCodeNode

workflow = WorkflowBuilder()

# Async node for I/O operations
workflow.add_node("AsyncPythonCodeNode", "fetch", {
    "code": """
# Async database query
db = await get_resource("main_db")
async with db.acquire() as conn:
    data = await conn.fetch("SELECT * FROM users")
result = {"users": [dict(row) for row in data]}
"""
})

# Sync node for CPU-bound processing
workflow.add_node("PythonCodeNode", "process", {
    "code": """
# Sync processing (users comes from parameter)
processed = [{"name": user["name"].upper()} for user in users]
result = {"processed": processed}
"""
})

# Connect nodes
workflow.add_connection("fetch", "result.users", "process", "users")

# Runtime handles both node types automatically
results, run_id = await runtime.execute_workflow_async(workflow.build(), {})
```

### 3. Data Pipeline Pattern

```python
# Parallel data processing pipeline
workflow = WorkflowBuilder()

# Source data
workflow.add_node("PythonCodeNode", "source", {
    "code": """
# Simulate CSV data
data = [
    {"name": "John Doe", "email": "john@example.com"},
    {"name": "Jane Smith", "email": "jane@example.com"},
    {"name": "", "email": "invalid"},
    {"name": "Bob Johnson", "email": "bob@example.com"}
]
result = {"data": data}
"""
})

# Clean data
workflow.add_node("PythonCodeNode", "clean", {
    "code": """
# Clean data (input_data comes from parameter)
cleaned = []
for row in input_data:
    if row.get('name') and row.get('email'):
        cleaned.append({
            'name': row['name'].strip(),
            'email': row['email'].lower(),
            'status': 'active'
        })
result = {"cleaned": cleaned}
"""
})

# Validate emails
workflow.add_node("AsyncPythonCodeNode", "validate", {
    "code": """
import re

# Validate emails (cleaned_data comes from parameter)
pattern = r'^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$'
valid_data = []
for row in cleaned_data:
    if re.match(pattern, row['email']):
        valid_data.append(row)

result = {"validated": valid_data, "valid_count": len(valid_data)}
"""
})

# Connect pipeline
workflow.add_connection("source", "result.data", "clean", "input_data")
workflow.add_connection("clean", "result.cleaned", "validate", "cleaned_data")

# Execute pipeline
results, run_id = await runtime.execute_workflow_async(workflow.build(), {})
print(f"Validated {results['validate']['result']['valid_count']} records")
```

### 4. API Aggregation Pattern

```python
# Concurrent API calls
workflow = WorkflowBuilder()

# User ID input
workflow.add_node("PythonCodeNode", "input", {
    "code": "result = {'user_id': 123}"
})

# Parallel API calls (simulate with data)
workflow.add_node("PythonCodeNode", "user_api", {
    "code": """
# Simulate user API response
user_data = {
    "id": user_id,
    "name": "John Doe",
    "email": "john@example.com"
}
result = {"user": user_data}
"""
})

workflow.add_node("PythonCodeNode", "orders_api", {
    "code": """
# Simulate orders API response
orders = [
    {"id": 1, "user_id": user_id, "total": 99.99},
    {"id": 2, "user_id": user_id, "total": 149.99}
]
result = {"orders": orders}
"""
})

workflow.add_node("PythonCodeNode", "preferences_api", {
    "code": """
# Simulate preferences API response
preferences = {
    "user_id": user_id,
    "theme": "dark",
    "notifications": True
}
result = {"preferences": preferences}
"""
})

# Aggregate results
workflow.add_node("PythonCodeNode", "aggregate", {
    "code": """
# Combine all data (parameters: user, orders, preferences)
combined = {
    "user_info": user,
    "order_history": orders,
    "user_preferences": preferences,
    "profile_complete": len(user.get('email', '')) > 0
}
result = {"profile": combined}
"""
})

# Connect nodes
workflow.add_connection("input", "result.user_id", "user_api", "user_id")
workflow.add_connection("input", "result.user_id", "orders_api", "user_id")
workflow.add_connection("input", "result.user_id", "preferences_api", "user_id")
workflow.add_connection("user_api", "result.user", "aggregate", "user")
workflow.add_connection("orders_api", "result.orders", "aggregate", "orders")
workflow.add_connection("preferences_api", "result.preferences", "aggregate", "preferences")

# All API calls run concurrently, then aggregate
results, run_id = await runtime.execute_workflow_async(workflow.build(), {})
```

## Error Handling

### Graceful Failure Handling

```python
# Workflow with error recovery
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "risky_operation", {
    "code": """
import random

# Simulate operation that might fail
if random.random() > 0.5:
    # Success case
    data = {"value": 42, "status": "success"}
else:
    # This will cause an error
    raise Exception("Operation failed randomly")

result = {"data": data}
"""
})

# Execute with error handling
try:
    results, run_id = await runtime.execute_workflow_async(workflow.build(), {})
    print(f"Workflow succeeded with run ID: {run_id}")
    print(f"Results: {results}")

except Exception as e:
    print(f"Workflow execution failed: {e}")
    # The runtime raises exceptions for workflow failures
    # Check the exception message for details
```

### Monitoring Execution

```python
import logging

# Enable logging for execution details
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kailash.runtime")

try:
    results, run_id = await runtime.execute_workflow_async(workflow, inputs)
    logger.info(f"Workflow {run_id} completed successfully")
    logger.info(f"Executed {len(results)} nodes")

except Exception as e:
    logger.error(f"Workflow execution failed: {e}")
    raise
```

## Performance Optimization

### Resource Usage Monitoring

```python
# Monitor workflow execution
import time

start_time = time.time()
results, run_id = await runtime.execute_workflow_async(workflow, inputs)
execution_time = time.time() - start_time

print(f"Execution completed in {execution_time:.2f}s")
print(f"Nodes executed: {len(results)}")

# Check individual node results
for node_id, node_output in results.items():
    if isinstance(node_output, dict) and "result" in node_output:
        print(f"Node {node_id}: {node_output['result']}")
```

### Concurrent Execution Tuning

```python
import time
import asyncio

# Find optimal concurrency
async def benchmark_concurrency():
    workflows = [create_test_workflow() for _ in range(10)]

    # Test different concurrency levels
    for max_concurrent in [1, 2, 5, 10, 20]:
        runtime = AsyncLocalRuntime(max_concurrent_nodes=max_concurrent)

        start_time = time.time()
        tasks = [
            runtime.execute_workflow_async(wf, {})
            for wf in workflows
        ]
        results = await asyncio.gather(*tasks)
        execution_time = time.time() - start_time

        print(f"Concurrency {max_concurrent}: {execution_time:.2f}s")
        print(f"  Completed {len(results)} workflows")

        await runtime.cleanup()

# Run benchmark
await benchmark_concurrency()
```

## Best Practices

### 1. Resource Management

```python
# Always cleanup resources
runtime = AsyncLocalRuntime(resource_registry=registry)

try:
    results, run_id = await runtime.execute_workflow_async(workflow, inputs)
    logger.info(f"Workflow {run_id} completed successfully")
finally:
    await runtime.cleanup()  # Important for production
```

### 2. Error Monitoring

```python
import logging

logger = logging.getLogger("app")

# Comprehensive error checking
try:
    results, run_id = await runtime.execute_workflow_async(workflow, inputs)

    # Log metrics for monitoring
    logger.info("Workflow execution metrics", extra={
        "run_id": run_id,
        "node_count": len(results),
        "workflow_name": "my_workflow"
    })

except Exception as e:
    logger.error(f"Workflow execution failed", extra={
        "error": str(e),
        "workflow_name": "my_workflow"
    })
    raise
```

### 3. PythonCodeNode Best Practices

```python
# Always wrap outputs in 'result' dict
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Input parameters are automatically available
processed_value = input_value * 2

# Always return result dict
result = {"output": processed_value}
"""
})

# Connect using dot notation
workflow.add_connection("source", "result.data", "processor", "input_value")
```

## Migration from LocalRuntime

### Simple Migration

Both runtimes now return the same structure, making migration seamless:

**Before (LocalRuntime):**
```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters=inputs)
```

**After (AsyncLocalRuntime):**
```python
from kailash.runtime.async_local import AsyncLocalRuntime
import asyncio

runtime = AsyncLocalRuntime()

async def execute():
    results, run_id = await runtime.execute_workflow_async(workflow, inputs)
    return results  # Same structure as LocalRuntime!

results = asyncio.run(execute())
```

The only differences are:
1. Async/await syntax
2. Parameter name: `parameters` → `inputs`

### Advanced Migration

**Before:**
```python
runtime = LocalRuntime(
    debug=True,
    max_concurrency=5
)
```

**After:**
```python
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=5,     # Similar to max_concurrency
    enable_analysis=True,       # Optimization enabled
    enable_profiling=True       # Similar to debug
)
```

**Key Notes:**
- Both runtimes support conditional execution (SwitchNode)
- AsyncLocalRuntime automatically detects and handles conditional workflows
- Return structure is identical for both runtimes

## Troubleshooting

### Common Issues

**1. Slow Performance:**
```python
import time
import logging

# Enable logging
logging.basicConfig(level=logging.DEBUG)

# Measure execution time
start = time.time()
results, run_id = await runtime.execute_workflow_async(workflow, inputs)
duration = time.time() - start

print(f"Execution took {duration:.2f}s for {len(results)} nodes")

# Try increasing concurrency
runtime = AsyncLocalRuntime(max_concurrent_nodes=20)
```

**2. Resource Connection Issues:**
```python
# Enable debug logging
import logging
logging.getLogger("kailash.resources").setLevel(logging.DEBUG)
logging.getLogger("kailash.runtime").setLevel(logging.DEBUG)

# Check execution
results, run_id = await runtime.execute_workflow_async(workflow, inputs)
print(f"Completed {len(results)} nodes")
```

**3. Memory Issues:**
```python
# Reduce concurrency
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=2,     # Lower concurrency
    thread_pool_size=2          # Fewer workers
)
```

### Debug Mode

```python
# Full debug configuration
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=1,     # Sequential execution
    enable_analysis=True,       # Detailed analysis
    enable_profiling=True       # Full metrics
)

# Enable all logging
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("kailash").setLevel(logging.DEBUG)

results, run_id = await runtime.execute_workflow_async(workflow, inputs)
print(f"Debug run {run_id}: {len(results)} nodes executed")
```

## Enhanced AsyncNode Support (v0.6.6+)

The AsyncNode base class has been significantly enhanced to handle complex event loop scenarios without "RuntimeError: no running event loop" issues:

### Thread-Safe Async Execution

```python
from kailash.nodes.monitoring import TransactionMetricsNode
from kailash.nodes.base import Node

# Custom node for async processing
class MyAsyncNode(Node):
    def run(self, **kwargs):
        # Your processing logic here
        return {"result": "processing complete"}

# Works in any context - main thread, worker threads, existing event loops
node = MyAsyncNode()
result = node.execute(operation="my_operation")  # Thread-safe
```

### Event Loop Detection & Handling

The enhanced AsyncNode automatically:

1. **No Event Loop**: Creates new loop with `asyncio.run()`
2. **Event Loop Running**: Uses ThreadPoolExecutor with isolated loop
3. **Threaded Contexts**: Proper thread-safe execution
4. **Windows Compatibility**: ProactorEventLoopPolicy support

### Performance Benefits

```python
# Before v0.6.6: Event loop errors in threaded contexts
# RuntimeError: no running event loop

# After v0.6.6: Seamless execution everywhere
from kailash.nodes.monitoring import TransactionMetricsNode
import concurrent.futures

# Works perfectly in thread pools
with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = []
    for i in range(10):
        metrics = TransactionMetricsNode()
        future = executor.submit(
            metrics.execute,
            operation="start_transaction",
            transaction_id=f"txn_{i}"
        )
        futures.append(future)

    # All executions succeed without event loop errors
    results = [f.result() for f in futures]
```

### Monitoring Node Integration

All monitoring nodes benefit from these improvements:

```python
from kailash.nodes.monitoring import (
    TransactionMetricsNode,
    DeadlockDetectorNode,
    RaceConditionDetectorNode,
    TransactionMonitorNode,
    PerformanceAnomalyNode
)

# All work seamlessly in any execution context
nodes = [
    TransactionMetricsNode(),
    DeadlockDetectorNode(),
    RaceConditionDetectorNode(),
    TransactionMonitorNode(),
    PerformanceAnomalyNode()
]

# Execute appropriate operations without event loop conflicts
operations = {
    "TransactionMetricsNode": "get_metrics",
    "DeadlockDetectorNode": "start_monitoring",
    "RaceConditionDetectorNode": "start_monitoring",
    "TransactionMonitorNode": "start_monitoring",
    "PerformanceAnomalyNode": "start_monitoring"
}

for node in nodes:
    node_type = type(node).__name__
    operation = operations[node_type]
    result = node.execute(operation=operation)
    assert result["status"] == "success"
```

## Related Documentation

- [AsyncWorkflowBuilder Guide](08-async-workflow-builder.md) - Building async-first workflows
- [Resource Registry Guide](09-resource-registry-guide.md) - Managing shared resources
- [Performance Optimization](04-production-overview.md) - Production tuning
- [Migration Guide](../migration-guides/async-migration.md) - Detailed migration steps

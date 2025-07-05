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
    result = await runtime.execute_workflow_async(workflow, {"input": "data"})
    print(f"Completed in {result.get('total_duration', 0):.2f} seconds")
    print(f"Results: {result['results']}")

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
result = await runtime.execute_workflow_async(workflow, inputs)
```

## Result Format

The AsyncLocalRuntime returns a different format than the standard LocalRuntime:

```python
{
    "results": {
        "node_id": {"result": {...}},  # Node outputs
        # ... more nodes
    },
    "errors": {
        "failed_node": "Error message",  # Any node errors
        # ... more errors
    },
    "total_duration": 1.23,  # Total execution time
    "workflow_id": "uuid-here",  # Unique execution ID
    "metrics": {  # If profiling enabled
        "node_durations": {...},
        "resource_access_count": {...}
    }
}
```

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
workflow.connect("input", "result.data", mapping={"process1": "input_data"})
workflow.connect("input", "result.data", mapping={"process2": "input_data"})

# Both processors run simultaneously
async def execute():
    start_time = time.time()
    result = await runtime.execute_workflow_async(workflow.build(), {})
    print(f"Parallel execution took {time.time() - start_time:.2f}s")
    return result

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
workflow.connect("fetch", "result.users", mapping={"process": "users"})

# Runtime handles both node types automatically
result = await runtime.execute_workflow_async(workflow.build(), {})
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
workflow.connect("source", "result.data", mapping={"clean": "input_data"})
workflow.connect("clean", "result.cleaned", mapping={"validate": "cleaned_data"})

# Execute pipeline
result = await runtime.execute_workflow_async(workflow.build(), {})
print(f"Validated {result['results']['validate']['result']['valid_count']} records")
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
workflow.connect("input", "result.user_id", mapping={"user_api": "user_id"})
workflow.connect("input", "result.user_id", mapping={"orders_api": "user_id"})
workflow.connect("input", "result.user_id", mapping={"preferences_api": "user_id"})
workflow.connect("user_api", "result.user", mapping={"aggregate": "user"})
workflow.connect("orders_api", "result.orders", mapping={"aggregate": "orders"})
workflow.connect("preferences_api", "result.preferences", mapping={"aggregate": "preferences"})

# All API calls run concurrently, then aggregate
result = await runtime.execute_workflow_async(workflow.build(), {})
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
    result = await runtime.execute_workflow_async(workflow.build(), {})

    # Check for errors
    if result["errors"]:
        print("Workflow had errors:")
        for node_id, error in result["errors"].items():
            print(f"  {node_id}: {error}")
    else:
        print("Workflow succeeded")

except Exception as e:
    print(f"Workflow execution failed: {e}")
```

### Monitoring Errors

```python
result = await runtime.execute_workflow_async(workflow, inputs)

# Check for errors
if result["errors"]:
    print("Workflow had errors:")
    for node_id, error in result["errors"].items():
        print(f"  {node_id}: {error}")

# Check metrics for performance issues
if "metrics" in result and hasattr(result["metrics"], "node_durations"):
    slow_nodes = {
        node_id: duration
        for node_id, duration in result["metrics"].node_durations.items()
        if duration > 1.0  # Nodes taking > 1 second
    }

    if slow_nodes:
        print("Slow nodes detected:")
        for node_id, duration in slow_nodes.items():
            print(f"  {node_id}: {duration:.2f}s")
```

## Performance Optimization

### Resource Usage Monitoring

```python
# Monitor resource usage
result = await runtime.execute_workflow_async(workflow, inputs)

if "metrics" in result and hasattr(result["metrics"], "resource_access_count"):
    resource_usage = result["metrics"].resource_access_count
    for resource_name, access_count in resource_usage.items():
        print(f"{resource_name}: {access_count} accesses")

    # Optimize based on usage patterns
    if resource_usage.get("database", 0) > 10:
        print("High database usage - consider connection pooling")

    if resource_usage.get("api_client", 0) > 5:
        print("Multiple API calls - consider batching or caching")
```

### Concurrent Execution Tuning

```python
# Find optimal concurrency
async def benchmark_concurrency():
    workflows = [create_test_workflow() for _ in range(10)]

    # Test different concurrency levels
    for max_concurrent in [1, 2, 5, 10, 20]:
        runtime = AsyncLocalRuntime(max_concurrent_nodes=max_concurrent)

        start_time = time.time()
        results = await asyncio.gather(*[
            runtime.execute_workflow_async(wf, {})
            for wf in workflows
        ])
        execution_time = time.time() - start_time

        print(f"Concurrency {max_concurrent}: {execution_time:.2f}s")

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
    result = await runtime.execute_workflow_async(workflow, inputs)
finally:
    await runtime.cleanup()  # Important for production
```

### 2. Error Monitoring

```python
# Comprehensive error checking
result = await runtime.execute_workflow_async(workflow, inputs)

# Log metrics for monitoring
logger.info("Workflow execution metrics:", extra={
    "duration": result.get("total_duration", 0),
    "node_count": len(result["results"]),
    "error_count": len(result["errors"]),
    "workflow_id": result.get("workflow_id", "unknown")
})

# Alert on errors
if result["errors"]:
    for node_id, error in result["errors"].items():
        logger.error(f"Node {node_id} failed: {error}")
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
workflow.connect("source", "result.data", mapping={"processor": "input_value"})
```

## Migration from LocalRuntime

### Simple Migration

**Before:**
```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters=inputs)
```

**After:**
```python
from kailash.runtime.async_local import AsyncLocalRuntime
import asyncio

runtime = AsyncLocalRuntime()

async def execute():
    result = await runtime.execute_workflow_async(workflow, inputs)
    return result["results"]  # Results are under 'results' key

results = asyncio.run(execute())
```

### Advanced Migration

**Before:**
```python
runtime = LocalRuntime(
    debug=True,
    enable_cycles=True,
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
# Note: Cyclic workflows not supported in AsyncLocalRuntime
```

## Troubleshooting

### Common Issues

**1. Slow Performance:**
```python
# Check node execution times
result = await runtime.execute_workflow_async(workflow, inputs)

if "metrics" in result and hasattr(result["metrics"], "node_durations"):
    for node_id, duration in result["metrics"].node_durations.items():
        if duration > 2.0:
            print(f"Slow node: {node_id} took {duration:.2f}s")

# Try increasing concurrency
runtime = AsyncLocalRuntime(max_concurrent_nodes=20)
```

**2. Resource Connection Issues:**
```python
# Enable debug logging
import logging
logging.getLogger("kailash.resources").setLevel(logging.DEBUG)

# Check resource access in metrics
result = await runtime.execute_workflow_async(workflow, inputs)
if "metrics" in result:
    print(f"Resource usage: {getattr(result['metrics'], 'resource_access_count', {})}")
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

result = await runtime.execute_workflow_async(workflow, inputs)
```

## Related Documentation

- [AsyncWorkflowBuilder Guide](08-async-workflow-builder.md) - Building async-first workflows
- [Resource Registry Guide](09-resource-registry-guide.md) - Managing shared resources
- [Performance Optimization](04-production-overview.md) - Production tuning
- [Migration Guide](../migration-guides/async-migration.md) - Detailed migration steps

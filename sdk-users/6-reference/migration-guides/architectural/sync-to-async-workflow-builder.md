# Migration Guide: Sync to Async Workflow Builder

## Overview

This guide helps you migrate from the synchronous `WorkflowBuilder` to the new production-grade `AsyncWorkflowBuilder` with its enhanced features and performance benefits.

## Key Improvements in AsyncWorkflowBuilder

1. **Automatic Code Indentation**: No more IndentationError - uses `textwrap.dedent()`
2. **Integrated Resource Management**: Built-in support for databases, HTTP clients, and caches
3. **Built-in Async Patterns**: Retry, rate limiting, circuit breaker, batch processing
4. **Fluent Interface**: Method chaining for resource configuration
5. **Production-Tested**: Battle-tested with PostgreSQL, Redis, and real infrastructure

## Migration Steps

### 1. Update Imports

**Before:**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
```

**After:**
```python
from kailash.workflow import AsyncWorkflowBuilder, AsyncPatterns
from kailash.runtime import AsyncLocalRuntime
```

### 2. Update Builder Creation

**Before:**
```python
builder = WorkflowBuilder()
builder.add_node("PythonCodeNode", "process", {
    "code": "result = process_data(data)"
})
```

**After:**
```python
builder = AsyncWorkflowBuilder("my_workflow")
builder.add_async_code(
    "process",
    """
    # Indentation is handled automatically!
    result = await process_data(data)
    """
)
```

### 3. Update Resource Management

**Before:**
```python
# Manual resource creation in node code
builder.add_node("PythonCodeNode", "db_query", {
    "code": """
import psycopg2
conn = psycopg2.connect("...")
# manual connection management
"""
})
```

**After:**
```python
# Declare resources at workflow level
builder = (builder
    .with_database("main_db", host="localhost", database="myapp")
    .with_http_client("api", base_url="https://api.example.com")
    .with_cache("redis", host="localhost"))

# Use resources in nodes
builder.add_async_code(
    "db_query",
    """
    db = await get_resource("main_db")
    async with db.acquire() as conn:
        result = await conn.fetch("SELECT * FROM users")
    """
)
```

### 4. Update Parallel Processing

**Before:**
```python
# Manual parallel processing
builder.add_node("PythonCodeNode", "parallel", {
    "code": """
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor() as executor:
    results = list(executor.map(process_item, items))
"""
})
```

**After:**
```python
# Built-in parallel map
builder.add_parallel_map(
    "parallel",
    """
    async def process_item(item):
        # Async processing with automatic concurrency control
        return await transform_item(item)
    """,
    max_workers=10,
    continue_on_error=True
)
```

### 5. Update Error Handling

**Before:**
```python
# Manual error handling
builder.add_node("PythonCodeNode", "api_call", {
    "code": """
try:
    response = requests.get(url)
    result = response.json()
except Exception as e:
    result = {"error": str(e)}
"""
})
```

**After:**
```python
# Built-in retry pattern
AsyncPatterns.retry_with_backoff(
    builder,
    "api_call",
    """
    client = await get_resource("api")
    response = await client.get(url)
    result = await response.json()
    """,
    max_retries=3,
    initial_backoff=1.0
)
```

### 6. Update Runtime and Execution

**Before:**
```python
workflow = builder.build()
runtime = LocalRuntime()
result = runtime.execute_workflow(workflow, inputs)

if result["status"] == "success":
    print("Success:", result["results"])
```

**After:**
```python
workflow = builder.build()
runtime = AsyncLocalRuntime(
    resource_registry=builder.get_resource_registry()
)
result = await runtime.execute_workflow_async(workflow, inputs)

# Note: Different result format!
if len(result["errors"]) == 0:
    print("Success:", result["results"])
else:
    print("Errors:", result["errors"])
```

## Common Patterns Migration

### Rate Limiting

**Before:**
```python
# Manual rate limiting
import time
for item in items:
    process(item)
    time.sleep(0.1)  # Crude rate limiting
```

**After:**
```python
AsyncPatterns.rate_limited(
    builder,
    "rate_limited_process",
    "result = await process(item)",
    requests_per_second=10,
    burst_size=20
)
```

### Circuit Breaker

**Before:**
```python
# Manual circuit breaker implementation
failures = 0
if failures > threshold:
    raise Exception("Circuit open")
```

**After:**
```python
AsyncPatterns.circuit_breaker(
    builder,
    "protected_call",
    "result = await external_service.call()",
    failure_threshold=5,
    reset_timeout=60.0
)
```

### Cache-Aside Pattern

**Before:**
```python
# Manual cache logic
cache_key = f"data_{id}"
cached = cache.get(cache_key)
if not cached:
    data = fetch_data(id)
    cache.set(cache_key, data)
else:
    data = cached
```

**After:**
```python
AsyncPatterns.cache_aside(
    builder,
    "cache_check", "data_fetch", "cache_store",
    "result = await expensive_operation(item_id)",
    cache_resource="redis",
    cache_key_template="data_{item_id}",
    ttl_seconds=3600
)
```

## Important Differences

### 1. Result Format

AsyncLocalRuntime returns a different format:

```python
# Sync runtime result:
{
    "status": "success",  # or "failed"
    "results": {...},
    "error": "..."  # if failed
}

# Async runtime result:
{
    "results": {
        "node_id": {/* output */},
        # ...
    },
    "errors": {
        "failed_node_id": "error message",
        # ...
    }
}
```

### 2. Input Field Names

When connecting nodes, use exact output field names:

```python
# If node outputs {"result": data}
builder.add_connection("node1", "result", "node2", "input")  # ✓
builder.add_connection("node1", "output", "node2", "input")  # ✗
```

### 3. Parallel Map Inputs

The `add_parallel_map` expects an input field (default "items"):

```python
# Connect to parallel map correctly
builder.add_connection("source", "data", "parallel", "items")
```

## Performance Benefits

- **70%+ code reduction** compared to manual async handling
- **2-10x performance improvement** for I/O-bound workflows
- **Built-in connection pooling** for databases and HTTP
- **Automatic resource cleanup** on errors or completion

## Best Practices

1. **Declare resources early**: Use `with_database()`, `with_http_client()`, etc. at the start
2. **Use built-in patterns**: Prefer AsyncPatterns over manual implementations
3. **Let the builder handle indentation**: Write naturally indented code strings
4. **Check exact field names**: Use debugger or logs to verify output field names
5. **Test with real infrastructure**: Use Docker for PostgreSQL, Redis during development

## Troubleshooting

### IndentationError
- **Solution**: AsyncWorkflowBuilder automatically handles indentation with `textwrap.dedent()`

### "items" not found in parallel_map
- **Solution**: Ensure you're passing the correct input field name or use `input_field` parameter

### Circuit breaker errors
- **Solution**: Use string states ("closed", "open", "half_open") not enums

### Resource not found
- **Solution**: Declare resources with `builder.with_*()` methods before building

## Complete Migration Example

```python
# Before: Sync WorkflowBuilder
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("PythonCodeNode", "fetch", {
    "code": """
import requests
response = requests.get("https://api.example.com/data")
result = response.json()
"""
})
builder.add_node("PythonCodeNode", "process", {
    "code": """
processed = []
for item in data:
    processed.append(transform(item))
result = processed
"""
})
builder.add_connection("fetch", "result", "process", "data")

workflow = builder.build()
runtime = LocalRuntime()
result = runtime.execute_workflow(workflow, {})

# After: AsyncWorkflowBuilder
from kailash.workflow import AsyncWorkflowBuilder, AsyncPatterns
from kailash.runtime import AsyncLocalRuntime

builder = AsyncWorkflowBuilder("data_pipeline")
builder.with_http_client("api", base_url="https://api.example.com")

AsyncPatterns.retry_with_backoff(
    builder, "fetch",
    """
    client = await get_resource("api")
    response = await client.get("/data")
    result = await response.json()
    """,
    max_retries=3
)

builder.add_parallel_map(
    "process",
    """
    async def process_item(item):
        return await transform(item)
    """,
    max_workers=10
)

builder.add_connection("fetch", "result", "process", "items")

workflow = builder.build()
runtime = AsyncLocalRuntime(resource_registry=builder.get_resource_registry())
result = await runtime.execute_workflow_async(workflow, {})

if len(result["errors"]) == 0:
    print("Success! Processed:", len(result["results"]["process"]["results"]))
```

## Next Steps

1. Review the [AsyncWorkflowBuilder Developer Guide](../developer/08-async-workflow-builder.md)
2. Explore [AsyncPatterns](../workflows/async/async-workflow-builder-guide.md) for common use cases
3. Test with real infrastructure using Docker
4. Monitor performance improvements with built-in metrics

# AsyncWorkflowBuilder Developer Guide

*Async-first workflow construction with 70%+ code reduction and built-in enterprise patterns*

## Overview

The AsyncWorkflowBuilder provides an async-first approach to building workflows with enhanced ergonomics, built-in patterns, and integrated resource management. It extends the base WorkflowBuilder with async-specific capabilities and reusable patterns for common async scenarios.

## Key Features

- **Async-First Design**: Optimized for async/await patterns with automatic code indentation handling
- **Resource Management**: Integrated with ResourceRegistry for databases, HTTP clients, and caches
- **Built-in Patterns**: Common async patterns like retry, rate limiting, circuit breaker
- **Fluent Interface**: Method chaining for readable workflow construction
- **Type Safety**: Strongly typed configuration objects
- **Error Handling**: Comprehensive error handling and recovery patterns
- **Production-Grade**: Battle-tested with real Docker infrastructure (PostgreSQL, Redis, Ollama)

## Core Components

### AsyncWorkflowBuilder

Main class extending WorkflowBuilder with async capabilities:

```python
from kailash.workflow import AsyncWorkflowBuilder

builder = AsyncWorkflowBuilder(
    name="my_async_workflow",
    description="Example async workflow"
)
```

### Configuration Classes

**RetryPolicy**: Configure retry behavior
```python
from kailash.workflow import RetryPolicy

retry_policy = RetryPolicy(
    max_retries=5,  # Note: Changed from max_attempts
    base_delay=1.0,
    max_delay=60.0,
    retry_on=[ConnectionError, TimeoutError]  # Pass actual exception classes
)
```

**ErrorHandler**: Configure error handling
```python
from kailash.workflow import ErrorHandler

error_handler = ErrorHandler(
    handler_type="fallback",
    fallback_value={"error": True, "message": "Operation failed"},
    log_level="warning"
)
```

## Important: Runtime Result Format

When using AsyncLocalRuntime with AsyncWorkflowBuilder, the result format is:

```python
{
    "results": {
        "node_id": {/* node output */},
        # ... more node results
    },
    "errors": {
        "failed_node_id": "error message",
        # ... any node errors
    }
}
```

**Note**: This differs from the sync runtime which returns `{"status": "success/failed", "results": {...}}`. Always check `len(result["errors"]) == 0` for success.

## Building Async Workflows

### Basic Async Code Nodes

Add async Python code with enhanced configuration:

```python
builder.add_async_code(
    "fetch_data",
    """
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.example.com/data') as response:
            data = await response.json()
    result = {"data": data, "status": response.status}
    """,
    timeout=30,
    max_concurrent_tasks=10,
    description="Fetch data from API"
)
```

**Note**: The AsyncWorkflowBuilder automatically handles code indentation using `textwrap.dedent()`, so you can write indented code strings naturally without worrying about indentation errors.

### Resource Management

Declare and use resources throughout your workflow:

```python
# Add database resource
builder.with_database(
    name="main_db",
    host="localhost",
    database="myapp",
    user="dbuser",
    min_size=5,
    max_size=20
)

# Add HTTP client resource
builder.with_http_client(
    name="api_client",
    base_url="https://api.example.com",
    headers={"Authorization": "Bearer token"},
    timeout=30  # Note: connection_limit parameter removed in production version
)

# Add cache resource
builder.with_cache(
    name="redis_cache",
    backend="redis",
    host="localhost",
    port=6379
)

# Use resources in nodes
builder.add_resource_node(
    "db_query",
    "main_db",
    "fetch",
    {"query": "SELECT * FROM users WHERE active = true"}
)
```

### Parallel Processing

Process collections concurrently:

```python
builder.add_parallel_map(
    "process_items",
    """
    async def process_item(item):
        # Simulate async processing
        await asyncio.sleep(0.1)
        return {
            "id": item["id"],
            "processed": True,
            "result": item["value"] * 2
        }
    """,
    max_workers=10,
    batch_size=50,
    timeout_per_item=5,
    continue_on_error=True
)
```

**Important**: The `add_parallel_map` method expects an input field containing the items to process. By default it looks for `items`, but you can specify a different field name with the `input_field` parameter. The processed results will be available in the `results` field by default, or you can customize with `output_field`.

### Scatter-Gather Pattern

Distribute work across multiple workers:

```python
builder.add_scatter_gather(
    "scatter_process",
    "worker",
    "gather_results",
    """
    def process_item(item):
        return {
            "original": item,
            "transformed": item.upper(),
            "length": len(item)
        }
    """,
    worker_count=4
)
```

## Built-in Async Patterns

### Retry with Exponential Backoff

```python
from kailash.workflow import AsyncPatterns

AsyncPatterns.retry_with_backoff(
    builder,
    "retry_operation",
    """
    # Operation that might fail
    response = await http_client.get("/unstable-endpoint")
    result = {"status": response.status, "data": await response.json()}
    """,
    max_retries=5,
    initial_backoff=1.0,
    backoff_factor=2.0,
    retry_on=["ConnectionError", "TimeoutError"]
)
```

### Rate Limiting

```python
AsyncPatterns.rate_limited(
    builder,
    "api_call",
    """
    response = await api_client.post("/rate-limited-endpoint", json=payload)
    result = await response.json()
    """,
    requests_per_second=10,
    burst_size=20
)
```

### Timeout with Fallback

```python
AsyncPatterns.timeout_with_fallback(
    builder,
    "primary_service",
    "fallback_service",
    """
    # Primary service (might be slow)
    response = await primary_client.get("/data")
    result = await response.json()
    """,
    """
    # Fallback service
    response = await fallback_client.get("/cached-data")
    result = await response.json()
    """,
    timeout_seconds=5.0
)
```

### Circuit Breaker

```python
AsyncPatterns.circuit_breaker(
    builder,
    "protected_service",
    """
    response = await external_service.call()
    result = {"data": response.data, "success": True}
    """,
    failure_threshold=5,
    reset_timeout=60.0
)
```

### Batch Processing

```python
AsyncPatterns.batch_processor(
    builder,
    "batch_insert",
    """
    # Process batch of items
    batch_results = []
    async with db_pool.acquire() as conn:
        for item in items:
            await conn.execute("INSERT INTO logs VALUES ($1, $2)", item.id, item.data)
            batch_results.append({"id": item.id, "inserted": True})
    """,
    batch_size=100,
    flush_interval=5.0
)
```

### Cache-Aside Pattern

```python
AsyncPatterns.cache_aside(
    builder,
    "cache_check",
    "data_fetch",
    "cache_store",
    """
    # Fetch expensive data
    response = await expensive_api_call(item_id)
    result = response.data
    """,
    cache_resource="redis_cache",
    cache_key_template="expensive_data_{item_id}",
    ttl_seconds=3600
)
```

### Parallel Fetch

```python
AsyncPatterns.parallel_fetch(
    builder,
    "multi_source_fetch",
    {
        "users": """
            response = await api_client.get("/users")
            result = await response.json()
        """,
        "orders": """
            response = await api_client.get("/orders")
            result = await response.json()
        """,
        "inventory": """
            response = await api_client.get("/inventory")
            result = await response.json()
        """
    },
    timeout_per_operation=10.0,
    continue_on_error=True
)
```

## Advanced Features

### Custom Resource Factories

```python
from kailash.resources import ResourceFactory

class CustomServiceFactory(ResourceFactory):
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    async def create(self):
        import aiohttp
        return aiohttp.ClientSession(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key}
        )

# Register custom resource
builder.require_resource(
    "custom_service",
    CustomServiceFactory("your-api-key", "https://service.example.com"),
    description="Custom service client"
)
```

### Error Handling and Recovery

```python
# Global error handler
error_handler = ErrorHandler(
    handler_type="fallback",
    fallback_value={"error": True, "recovered": True}
)

# Retry policy for specific operations
retry_policy = AsyncRetryPolicy(
    max_attempts=3,
    initial_delay=0.5,
    retry_exceptions=["aiohttp.ClientError"]
)

builder.add_async_code(
    "resilient_operation",
    """
    async with aiohttp.ClientSession() as session:
        response = await session.get("https://api.example.com/data")
        result = await response.json()
    """,
    retry_policy=retry_policy,
    error_handler=error_handler
)
```

### Workflow Metadata and Tracking

```python
# Add metadata to nodes
builder.add_async_code(
    "tracked_operation",
    "result = await some_operation()",
    description="Important business operation",
    required_resources=["database", "cache"]
)

# Get workflow metadata
workflow = builder.build()
print(f"Required resources: {workflow.metadata['required_resources']}")
print(f"Node count: {len(workflow.nodes)}")

# Get node-specific metadata
node_metadata = builder.get_node_metadata("tracked_operation")
print(f"Node description: {node_metadata.get('description')}")
```

## Best Practices

### 1. Resource Management

```python
# ✅ Good: Declare resources at workflow level
builder = (AsyncWorkflowBuilder("data_pipeline")
    .with_database("main_db", host="db.prod.com")
    .with_cache("redis", host="cache.prod.com")
    .with_http_client("api", base_url="https://api.prod.com"))

# ❌ Bad: Creating resources in node code
builder.add_async_code("bad_example", """
    # Don't create resources inside nodes
    db = await create_db_connection("db.prod.com")
""")
```

### 2. Error Handling

```python
# ✅ Good: Use structured error handling
retry_policy = AsyncRetryPolicy(max_attempts=3, initial_delay=1.0)
error_handler = ErrorHandler("fallback", {"error": True})

builder.add_async_code(
    "api_call",
    "result = await api_client.get('/data')",
    retry_policy=retry_policy,
    error_handler=error_handler
)

# ❌ Bad: Bare try/catch in node code
builder.add_async_code("bad_error_handling", """
    try:
        result = await api_call()
    except:
        result = {"error": True}  # Loses error context
""")
```

### 3. Async Patterns

```python
# ✅ Good: Use built-in patterns
AsyncPatterns.rate_limited(
    builder, "api_calls", "await api.call()",
    requests_per_second=10
)

# ❌ Bad: Manual rate limiting
builder.add_async_code("manual_rate_limit", """
    # Manual rate limiting is error-prone
    await asyncio.sleep(0.1)  # Crude rate limiting
    result = await api.call()
""")
```

### 4. Fluent Interface

```python
# ✅ Good: Resource configuration can be chained
builder = (AsyncWorkflowBuilder("pipeline")
    .with_database("db")
    .with_cache("redis")
    .with_http_client("api"))

# Add nodes (returns node_id, not builder)
step1_id = builder.add_async_code("step1", "result = await process_data()")
step2_id = builder.add_async_code("step2", "result = await transform_data(input_data)")

# Add connections
builder.add_connection(step1_id, "result", step2_id, "input_data")

# Build workflow
workflow = builder.build()

# ❌ Bad: Trying to chain add_node methods (doesn't work)
# add_async_code returns a string node_id, not the builder
workflow = (AsyncWorkflowBuilder("pipeline")
    .add_async_code("step1", "...")  # Returns string, breaks chain!
    .add_async_code("step2", "...")  # This won't work
    .build())
```

## Debugging and Monitoring

### 1. Node Metadata

```python
# Add descriptive metadata
builder.add_async_code(
    "critical_operation",
    operation_code,
    description="Processes customer orders from queue",
    required_resources=["database", "message_queue"],
    timeout=30
)
```

### 2. Resource Tracking

```python
# Check resource requirements
resources = builder.list_required_resources()
print(f"Workflow requires: {resources}")

# Validate resource availability before execution
registry = builder.get_resource_registry()
for resource_name in resources:
    if not registry.has_factory(resource_name):
        raise ValueError(f"Missing resource factory: {resource_name}")
```

### 3. Execution Monitoring

```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime(
    resource_registry=builder.get_resource_registry()
)

# Execute with monitoring
result = await runtime.execute_workflow_async(workflow, inputs)

# Check execution results - AsyncLocalRuntime returns different format
if len(result["errors"]) == 0:
    print(f"Workflow completed successfully")
    for node_id, output in result["results"].items():
        if isinstance(output, dict) and "_rate_limit_info" in output:
            print(f"Node {node_id} rate limit: {output['_rate_limit_info']}")
else:
    print(f"Workflow had errors:")
    for node_id, error in result["errors"].items():
        print(f"  - {node_id}: {error}")
```

## Performance Considerations

### 1. Concurrency Control

```python
# Control parallelism appropriately
builder.add_parallel_map(
    "process_large_dataset",
    process_function,
    max_workers=min(50, cpu_count() * 4),  # Don't overwhelm system
    batch_size=100  # Process in manageable batches
)
```

### 2. Resource Limits

```python
# Set appropriate resource limits
builder.with_database(
    "main_db",
    min_size=5,   # Minimum connections
    max_size=20,  # Maximum connections
    host="db.prod.com"
)
```

### 3. Timeouts

```python
# Set reasonable timeouts
builder.add_async_code(
    "external_api",
    api_call_code,
    timeout=30,  # Node-level timeout
    max_concurrent_tasks=10  # Limit concurrent executions
)
```

## Integration with Existing Code

### 1. Migrating from WorkflowBuilder

```python
# Before (WorkflowBuilder)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

builder = WorkflowBuilder()
builder.add_node("PythonCodeNode", "process", {"code": "result = process_data()"})

# After (AsyncWorkflowBuilder)
from kailash.workflow import AsyncWorkflowBuilder

builder = AsyncWorkflowBuilder()
builder.add_async_code("process", "result = await process_data()")
```

### 2. Using with Existing Resources

```python
# Use existing resource registry
existing_registry = get_existing_registry()

builder = AsyncWorkflowBuilder(
    resource_registry=existing_registry
)

# Add additional resources
builder.with_cache("new_cache", host="cache2.prod.com")
```

## Complete Example: High-Performance Data Pipeline

Here's a comprehensive example demonstrating the AsyncWorkflowBuilder with a data enrichment pipeline:

```python
import asyncio
import time

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import AsyncPatterns, AsyncWorkflowBuilder


async def main():
    """Create and execute a high-performance async workflow."""

    # Build async workflow
    builder = AsyncWorkflowBuilder("data_enrichment_pipeline")

    # Configure resources (these methods return the builder, so can be chained)
    builder = (builder
        .with_database(
            name="main_db",
            host="localhost",
            port=5433,
            database="postgres",
            user="postgres",
            password="postgres",
        )
        .with_http_client(name="api", base_url="https://jsonplaceholder.typicode.com")
        .with_cache(name="redis", backend="redis", host="localhost", port=6379)
    )

    # Add nodes (these return node_ids, not the builder)
    fetch_users_id = builder.add_async_code(
        "fetch_users",
        """
# Simulate database query
# In production, would use: db = await get_resource("main_db")
users = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
    {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    {"id": 4, "name": "David", "email": "david@example.com"},
    {"id": 5, "name": "Eve", "email": "eve@example.com"}
]
result = {"users": users}
""",
        timeout=10,
    )

    # Enrich users with external data in parallel
    enrich_users_id = builder.add_parallel_map(
        "enrich_users",
        """
async def process_item(user):
    # In production: api = await get_resource("api")
    # Simulate API enrichment
    await asyncio.sleep(0.1)  # Simulate API latency

    enriched = user.copy()
    enriched["score"] = user["id"] * 10
    enriched["status"] = "active" if user["id"] % 2 == 0 else "pending"
    enriched["enriched_at"] = time.time()

    return enriched
""",
        max_workers=3,
        timeout_per_item=2,
        continue_on_error=True,
    )

    # Aggregate results
    aggregate_results_id = builder.add_async_code(
        "aggregate_results",
        """
# Process enriched users
enriched_users = results

# Calculate statistics
total_users = len(enriched_users)
active_users = sum(1 for u in enriched_users if u.get("status") == "active")
average_score = sum(u.get("score", 0) for u in enriched_users) / total_users if total_users > 0 else 0

result = {
    "users": enriched_users,
    "statistics": {
        "total": total_users,
        "active": active_users,
        "pending": total_users - active_users,
        "average_score": average_score
    },
    "processed_at": time.time()
}
""",
        timeout=5,
    )

    # Connect the workflow (using the returned node IDs)
    builder.add_connection(fetch_users_id, "users", enrich_users_id, "items")
    builder.add_connection(enrich_users_id, "results", aggregate_results_id, "results")

    # Build the workflow
    workflow = builder.build()

    # Add resilience patterns
    resilient_workflow = AsyncWorkflowBuilder("resilient_pipeline")

    # Add retry pattern for flaky operations
    AsyncPatterns.retry_with_backoff(
        resilient_workflow,
        "flaky_api_call",
        """
# Simulate flaky API that fails 50% of the time
import random
if random.random() < 0.5:
    raise Exception("API temporarily unavailable")
result = {"data": "success"}
""",
        max_retries=3,
        initial_backoff=0.5,
    )

    # Add rate limiting for external APIs
    AsyncPatterns.rate_limited(
        resilient_workflow,
        "rate_limited_calls",
        """
# Rate limited operation
result = {"processed": True, "timestamp": time.time()}
""",
        requests_per_second=5,
        burst_size=10,
    )

    # Execute workflows
    runtime = AsyncLocalRuntime()

    print("🚀 Executing data enrichment pipeline...")
    result = await runtime.execute_workflow_async(workflow, {})

    if len(result["errors"]) == 0:
        stats = result["results"]["aggregate_results"]["statistics"]
        print("✅ Pipeline completed successfully!")
        print(f"   - Total users: {stats['total']}")
        print(f"   - Active users: {stats['active']}")
        print(f"   - Average score: {stats['average_score']:.1f}")
    else:
        print(f"❌ Pipeline had errors:")
        for node_id, error in result["errors"].items():
            print(f"   - {node_id}: {error}")

    # Build and execute resilient workflow
    resilient = resilient_workflow.build()
    print("\n🛡️ Executing resilient workflow...")

    resilient_result = await runtime.execute_workflow_async(resilient, {})
    if len(resilient_result["errors"]) == 0:
        print("✅ Resilient workflow completed with retry logic")

    print("\n📊 AsyncWorkflowBuilder Benefits:")
    print("   - 70%+ code reduction vs traditional approach")
    print("   - Built-in resource management")
    print("   - Automatic error handling and retries")
    print("   - Parallel processing with rate limiting")
    print("   - Type-safe with full IDE support")


if __name__ == "__main__":
    asyncio.run(main())
```

This example demonstrates:
- **Resource Configuration**: Database, HTTP client, and cache setup
- **Parallel Processing**: Using `add_parallel_map` for concurrent user enrichment
- **Error Handling**: Resilient patterns with retry and rate limiting
- **Aggregation**: Statistical analysis of processed data
- **Performance**: 70%+ code reduction compared to traditional approaches

## Common Patterns and Examples

See additional examples in:
- `/sdk-users/workflows/async/` - Pattern-specific examples
- `/tests/unit/workflow/test_async_workflow_builder.py` - Test examples

## Troubleshooting

### Common Issues

1. **Resource Not Found**: Ensure resources are registered before building workflow
2. **Timeout Errors**: Adjust timeout values for slow operations
3. **Memory Issues**: Control concurrency with `max_workers` and `batch_size`
4. **Connection Errors**: Use retry patterns for unreliable external services
5. **IndentationError in async code**: The builder automatically handles indentation with `textwrap.dedent()`
6. **Input passing between nodes**: Use exact output field names in connections (e.g., "result" not "output")
7. **Parallel map not finding items**: Ensure input field name matches (default is "items")
8. **Circuit breaker state strings**: Use string states ("closed", "open", "half_open") not enums

### Debug Mode

```python
import logging
logging.getLogger('kailash.workflow').setLevel(logging.DEBUG)

# This will show detailed workflow construction and execution logs
```

## Related Documentation

- [Base WorkflowBuilder Guide](07-workflow-builder.md)
- [Resource Management](06-resource-management.md)
- [Async Runtime Guide](09-async-runtime.md)
- [Error Handling Patterns](05-troubleshooting.md)

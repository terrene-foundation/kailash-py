# Unified Async Runtime - User Guide

**High-performance async workflow execution with concurrent processing**

## Overview

The Unified Async Runtime (AsyncLocalRuntime) brings first-class async support to Kailash workflows. It automatically optimizes your workflows for concurrent execution while maintaining full backwards compatibility with existing sync workflows.

> ✅ **Production Ready**: Extensively tested with 23 comprehensive tests across unit, integration, and user flow scenarios. Validated with real PostgreSQL, Redis, Ollama, and HTTP services.

## Test Validation Status

**Performance Confirmed**: 2-10x speedup in concurrent execution
**Reliability Confirmed**: 100+ node stress testing, comprehensive error handling
**Integration Confirmed**: Real Docker services (PostgreSQL, Redis), Ollama LLM, HTTP APIs
**Developer Experience Confirmed**: First-time to advanced developer workflows validated

## Quick Start

### Basic Usage

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.async_local import AsyncLocalRuntime

# Create async runtime
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=10,
    enable_analysis=True
)

# Execute any workflow
result = await runtime.execute_workflow_async(workflow, {"input": "data"})

print(f"Completed in {result['total_duration']:.2f} seconds")
print(f"Results: {result['results']}")
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

## Key Features

### 1. Automatic Concurrency

The runtime analyzes your workflow and runs independent nodes concurrently:

```python
# This workflow will run node1 and node2 in parallel
workflow = WorkflowBuilder()\
    .add_node("input", CSVReaderNode, file_path="data.csv")\
    .add_node("process1", ProcessorNode)\
    .add_node("process2", ProcessorNode)\
    .add_connection("input", "process1", "data", "input")\
    .add_connection("input", "process2", "data", "input")\
    .build()

# Both processors run simultaneously
start_time = time.time()
result = await runtime.execute_workflow_async(workflow, {})
print(f"Parallel execution took {time.time() - start_time:.2f}s")
```

### 2. Mixed Sync/Async Support

Works seamlessly with both sync and async nodes:

```python
from kailash.nodes.code import AsyncPythonCodeNode, PythonCodeNode

workflow = WorkflowBuilder()\
    .add_node("fetch", AsyncPythonCodeNode, code="""
# Async database query
db = await get_resource("main_db")
async with db.acquire() as conn:
    data = await conn.fetch("SELECT * FROM users")
result = {"users": [dict(row) for row in data]}
""")\
    .add_node("process", PythonCodeNode, code="""
# Sync processing
processed = [{"name": user["name"].upper()} for user in users]
result = {"processed": processed}
""")\
    .add_connection("fetch", "process", "result", "users")\
    .build()

# Runtime handles both node types automatically
result = await runtime.execute_workflow_async(workflow, {})
```

### 3. Performance Monitoring

Built-in performance tracking and optimization:

```python
runtime = AsyncLocalRuntime(
    enable_profiling=True,  # Detailed performance metrics
    enable_analysis=True    # Workflow optimization
)

result = await runtime.execute_workflow_async(workflow, inputs)

# Access detailed metrics
print(f"Total execution time: {result['total_duration']:.2f}s")
print(f"Node execution times:")
for node_id, duration in result['metrics'].node_durations.items():
    print(f"  {node_id}: {duration:.3f}s")

print(f"Resource accesses: {result['metrics'].resource_access_count}")
print(f"Concurrent executions: {result['metrics'].concurrent_executions}")
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

### 1. Data Pipeline Pattern

```python
# Parallel data processing pipeline
workflow = WorkflowBuilder()\
    .add_node("source", CSVReaderNode, file_path="input.csv")\
    .add_node("clean", AsyncPythonCodeNode, code="""
# Clean data asynchronously
cleaned = []
for row in data:
    if row.get('name') and row.get('email'):
        cleaned.append({
            'name': row['name'].strip(),
            'email': row['email'].lower(),
            'status': 'active'
        })
result = {"cleaned": cleaned}
""")\
    .add_node("validate", AsyncPythonCodeNode, code="""
# Validate emails in parallel
import asyncio
import re

async def validate_email(email):
    pattern = r'^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$'
    return re.match(pattern, email) is not None

# Validate all emails concurrently
tasks = [validate_email(row['email']) for row in cleaned]
validations = await asyncio.gather(*tasks)

valid_data = [
    row for row, is_valid in zip(cleaned, validations)
    if is_valid
]
result = {"validated": valid_data, "valid_count": len(valid_data)}
""")\
    .add_node("save", AsyncPythonCodeNode, code="""
# Save to database
db = await get_resource("main_db")
async with db.acquire() as conn:
    for row in validated:
        await conn.execute(
            "INSERT INTO users (name, email, status) VALUES ($1, $2, $3)",
            row['name'], row['email'], row['status']
        )
result = {"saved": len(validated)}
""")\
    .add_connection("source", "clean", "data", "data")\
    .add_connection("clean", "validate", "result", "cleaned")\
    .add_connection("validate", "save", "result", "validated")\
    .build()

# Execute pipeline
result = await runtime.execute_workflow_async(workflow, {})
print(f"Processed {result['results']['save']['saved']} records")
```

### 2. API Aggregation Pattern

```python
# Concurrent API calls
workflow = WorkflowBuilder()\
    .add_node("user_api", AsyncPythonCodeNode, code="""
# Get user data
api = await get_resource("user_service")
async with api.get(f"/users/{user_id}") as resp:
    user_data = await resp.json()
result = {"user": user_data}
""")\
    .add_node("orders_api", AsyncPythonCodeNode, code="""
# Get order history
api = await get_resource("order_service")
async with api.get(f"/users/{user_id}/orders") as resp:
    orders = await resp.json()
result = {"orders": orders}
""")\
    .add_node("preferences_api", AsyncPythonCodeNode, code="""
# Get user preferences
api = await get_resource("preference_service")
async with api.get(f"/users/{user_id}/preferences") as resp:
    preferences = await resp.json()
result = {"preferences": preferences}
""")\
    .add_node("aggregate", PythonCodeNode, code="""
# Combine all data
combined = {
    "user_info": user,
    "order_history": orders,
    "user_preferences": preferences,
    "profile_complete": len(user.get('profile', {})) > 3
}
result = {"profile": combined}
""")\
    .add_connection("user_api", "aggregate", "result.user", "user")\
    .add_connection("orders_api", "aggregate", "result.orders", "orders")\
    .add_connection("preferences_api", "aggregate", "result.preferences", "preferences")\
    .build()

# All API calls run concurrently, then aggregate
result = await runtime.execute_workflow_async(workflow, {"user_id": 123})
```

### 3. Real-time Processing Pattern

```python
# Real-time data processing with caching
workflow = WorkflowBuilder()\
    .add_node("sensor_data", AsyncPythonCodeNode, code="""
# Fetch latest sensor readings
api = await get_resource("sensor_api")
cache = await get_resource("redis_cache")

# Check cache first
cached = await cache.get(f"sensor:{sensor_id}:latest")
if cached:
    sensor_data = json.loads(cached)
    source = "cache"
else:
    async with api.get(f"/sensors/{sensor_id}/latest") as resp:
        sensor_data = await resp.json()
        source = "api"

    # Cache for 30 seconds
    await cache.setex(f"sensor:{sensor_id}:latest", 30, json.dumps(sensor_data))

result = {"data": sensor_data, "source": source}
""")\
    .add_node("analyze", AsyncPythonCodeNode, code="""
# Analyze readings for anomalies
import statistics

readings = data["readings"]
if len(readings) >= 10:
    mean_val = statistics.mean(readings)
    std_dev = statistics.stdev(readings)

    # Detect outliers
    outliers = [
        r for r in readings
        if abs(r - mean_val) > 2 * std_dev
    ]

    anomaly_detected = len(outliers) > 0
else:
    anomaly_detected = False
    outliers = []

result = {
    "anomaly": anomaly_detected,
    "outliers": outliers,
    "analysis_time": data.get("timestamp")
}
""")\
    .add_node("alert", AsyncPythonCodeNode, code="""
# Send alerts if needed
if anomaly:
    mq = await get_resource("alert_queue")

    alert_message = {
        "sensor_id": sensor_id,
        "anomaly_detected": True,
        "outliers": outliers,
        "timestamp": analysis_time
    }

    # Publish alert
    channel = await mq.channel()
    await channel.default_exchange.publish(
        aio_pika.Message(json.dumps(alert_message).encode()),
        routing_key="alerts.anomaly"
    )

    sent_alert = True
else:
    sent_alert = False

result = {"alert_sent": sent_alert}
""")\
    .add_connection("sensor_data", "analyze", "result", "data")\
    .add_connection("analyze", "alert", "result", "anomaly", "analysis_time")\
    .build()

# Process sensor data with caching and alerting
result = await runtime.execute_workflow_async(workflow, {"sensor_id": "temp_01"})
```

## Error Handling

### Graceful Failure Handling

```python
# Workflow with error recovery
workflow = WorkflowBuilder()\
    .add_node("primary_source", AsyncPythonCodeNode, code="""
try:
    api = await get_resource("primary_api")
    async with api.get("/data") as resp:
        if resp.status == 200:
            data = await resp.json()
            result = {"data": data, "source": "primary"}
        else:
            raise Exception(f"Primary API returned {resp.status}")
except Exception as e:
    # Fallback to secondary source
    try:
        api = await get_resource("secondary_api")
        async with api.get("/data") as resp:
            data = await resp.json()
            result = {"data": data, "source": "secondary"}
    except Exception as fallback_error:
        # Final fallback to cache
        cache = await get_resource("cache")
        cached_data = await cache.get("fallback_data")
        if cached_data:
            result = {"data": json.loads(cached_data), "source": "cache"}
        else:
            result = {"data": None, "source": "none", "error": str(e)}
""")\
    .build()

try:
    result = await runtime.execute_workflow_async(workflow, {})
    print(f"Data source: {result['results']['primary_source']['source']}")
except Exception as e:
    print(f"Workflow failed: {e}")
```

### Monitoring Errors

```python
result = await runtime.execute_workflow_async(workflow, inputs)

# Check for errors
if result["errors"]:
    print("Workflow had errors:")
    for node_id, error in result["errors"].items():
        print(f"  {node_id}: {error}")

# Check metrics for issues
metrics = result["metrics"]
if metrics.error_count > 0:
    print(f"Total errors: {metrics.error_count}")

# Analyze performance
slow_nodes = {
    node_id: duration
    for node_id, duration in metrics.node_durations.items()
    if duration > 1.0  # Nodes taking > 1 second
}

if slow_nodes:
    print("Slow nodes detected:")
    for node_id, duration in slow_nodes.items():
        print(f"  {node_id}: {duration:.2f}s")
```

## Performance Optimization

### Workflow Analysis

```python
# Analyze workflow before execution
runtime = AsyncLocalRuntime(enable_analysis=True)

# The runtime automatically analyzes and optimizes
result = await runtime.execute_workflow_async(workflow, inputs)

# Check optimization results
if hasattr(runtime, 'analyzer') and runtime.analyzer:
    plan = runtime.analyzer.analyze(workflow)
    print(f"Workflow optimization:")
    print(f"  Async nodes: {len(plan.async_nodes)}")
    print(f"  Sync nodes: {len(plan.sync_nodes)}")
    print(f"  Execution levels: {len(plan.execution_levels)}")
    print(f"  Max concurrent: {plan.max_concurrent_nodes}")
    print(f"  Estimated duration: {plan.estimated_duration:.2f}s")
```

### Resource Usage Optimization

```python
# Monitor resource usage
result = await runtime.execute_workflow_async(workflow, inputs)

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
logger.info(f"Workflow execution metrics:", extra={
    "duration": result["total_duration"],
    "node_count": len(result["results"]),
    "error_count": len(result["errors"]),
    "resource_accesses": dict(result["metrics"].resource_access_count)
})

# Alert on errors
if result["errors"]:
    for node_id, error in result["errors"].items():
        logger.error(f"Node {node_id} failed: {error}")
        # Send to monitoring system
```

### 3. Performance Monitoring

```python
# Production monitoring
async def execute_with_monitoring(workflow, inputs):
    start_time = time.time()

    try:
        result = await runtime.execute_workflow_async(workflow, inputs)

        # Success metrics
        logger.info("Workflow succeeded", extra={
            "duration": result["total_duration"],
            "nodes_executed": len(result["results"]),
            "concurrent_executions": result["metrics"].concurrent_executions
        })

        return result

    except Exception as e:
        # Failure metrics
        logger.error("Workflow failed", extra={
            "error": str(e),
            "duration": time.time() - start_time
        })
        raise

# Use in production
result = await execute_with_monitoring(workflow, inputs)
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

runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow, inputs)
# Results are in: result["results"]
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

# Check resource access
result = await runtime.execute_workflow_async(workflow, inputs)
print(f"Resource usage: {result['metrics'].resource_access_count}")
```

**3. Memory Issues:**
```python
# Reduce concurrency
runtime = AsyncLocalRuntime(
    max_concurrent_nodes=2,     # Lower concurrency
    thread_pool_size=2          # Fewer workers
)

# Monitor memory in workflow
node = AsyncPythonCodeNode(code="""
import psutil
process = psutil.Process()
memory_mb = process.memory_info().rss / 1024 / 1024
result = {"memory_usage_mb": memory_mb}
""")
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

The Unified Async Runtime provides a powerful foundation for high-performance workflow execution. It automatically optimizes your workflows while maintaining the simple interface you expect from Kailash.

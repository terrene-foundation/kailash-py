# AsyncWorkflowBuilder User Guide

## Quick Start

The AsyncWorkflowBuilder makes it easy to create high-performance async workflows with built-in patterns and resource management.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.workflow import AsyncWorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# Create and execute an async workflow
builder = AsyncWorkflowBuilder("my_workflow")

# Add nodes
builder.add_async_code(
    "fetch",
    "result = await fetch_data()"
)

builder.add_async_code(
    "process",
    "result = await process_data(input_data)"
)

# Connect nodes
builder.add_connection("fetch", "result", "process", "input_data")

# Build and execute
workflow = builder.build()
runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow, {})

# Check results - AsyncLocalRuntime format
if len(result["errors"]) == 0:
    print("Success:", result["results"])
else:
    print("Errors:", result["errors"])
```

## Common Use Cases

### 1. API Data Pipeline

```python
from kailash.workflow import AsyncWorkflowBuilder, AsyncPatterns

# Build a resilient API data processing pipeline
builder = AsyncWorkflowBuilder("api_pipeline")

# Configure resources (fluent interface for chaining)
builder = (builder
    .with_http_client("api", base_url="https://api.example.com")
    .with_database("db", host="localhost", database="myapp")
    .with_cache("cache", host="localhost"))

# Note: AsyncWorkflowBuilder automatically handles code indentation,
# so you can write naturally indented code strings

# Fetch data with rate limiting
AsyncPatterns.rate_limited(
    builder,
    "fetch_users",
    """
    response = await api.get("/users", params={"page": page_num})
    result = await response.json()
    """,
    requests_per_second=5
)

# Process users in parallel
builder.add_parallel_map(
    "process_users",
    """
    async def process_item(user):
        # Enrich user data
        profile_response = await api.get(f"/users/{user['id']}/profile")
        profile = await profile_response.json()

        return {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "profile": profile
        }
    """,
    max_workers=10,
    continue_on_error=True
)

# Store with batch processing
AsyncPatterns.batch_processor(
    builder,
    "store_users",
    """
    async with db.acquire() as conn:
        for user in items:
            await conn.execute(
                "INSERT INTO users (id, name, email, profile) VALUES ($1, $2, $3, $4)",
                user["id"], user["name"], user["email"], json.dumps(user["profile"])
            )
        batch_results = [{"stored": True, "id": user["id"]} for user in items]
    """,
    batch_size=50
)

# Connect the pipeline
builder.add_connection("fetch_users", "result", "process_users", "items")
builder.add_connection("process_users", "results", "store_users", "items")

workflow = builder.build()
```

### 2. Multi-Source Data Aggregation

```python
# Fetch data from multiple sources in parallel
builder = AsyncWorkflowBuilder("data_aggregation")

AsyncPatterns.parallel_fetch(
    builder,
    "multi_fetch",
    {
        "customers": """
            response = await crm_api.get("/customers")
            result = await response.json()
        """,
        "orders": """
            response = await orders_api.get("/orders")
            result = await response.json()
        """,
        "inventory": """
            response = await inventory_api.get("/products")
            result = await response.json()
        """,
        "analytics": """
            response = await analytics_api.get("/metrics")
            result = await response.json()
        """
    },
    timeout_per_operation=30.0,
    continue_on_error=True
)

# Combine and analyze data
builder.add_async_code(
    "analyze",
    """
    # Extract successful results
    customers = successful.get("customers", [])
    orders = successful.get("orders", [])
    inventory = successful.get("inventory", [])
    analytics = successful.get("analytics", {})

    # Perform analysis
    customer_orders = {}
    for order in orders:
        customer_id = order["customer_id"]
        if customer_id not in customer_orders:
            customer_orders[customer_id] = []
        customer_orders[customer_id].append(order)

    # Generate insights
    insights = {
        "total_customers": len(customers),
        "total_orders": len(orders),
        "avg_orders_per_customer": len(orders) / len(customers) if customers else 0,
        "top_customers": sorted(
            customer_orders.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]
    }

    result = {
        "insights": insights,
        "data_sources": list(successful.keys()),
        "failed_sources": list(failed.keys()) if failed else []
    }
    """
)

builder.add_connection("multi_fetch", "successful", "analyze", "successful")
builder.add_connection("multi_fetch", "failed", "analyze", "failed")
```

### 3. File Processing Pipeline

```python
import os
from pathlib import Path

builder = AsyncWorkflowBuilder("file_processor")

# Configure resources
builder = (builder
    .with_database("db")
    .with_cache("cache"))

# Scan directory for files
builder.add_async_code(
    "scan_files",
    """
    import os
    from pathlib import Path

    directory = Path(input_directory)
    files = []

    for file_path in directory.rglob("*.csv"):
        if file_path.is_file():
            files.append({
                "path": str(file_path),
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "modified": file_path.stat().st_mtime
            })

    result = {"files": files, "total_files": len(files)}
    """
)

# Process files in parallel with progress tracking
builder.add_parallel_map(
    "process_files",
    """
    async def process_item(file_info):
        import pandas as pd
        import asyncio

        # Read CSV file
        df = pd.read_csv(file_info["path"])

        # Simulate processing time
        await asyncio.sleep(0.1)

        # Basic validation and stats
        stats = {
            "file": file_info["name"],
            "rows": len(df),
            "columns": len(df.columns),
            "missing_values": df.isnull().sum().sum(),
            "memory_usage": df.memory_usage(deep=True).sum()
        }

        # Store processed data reference
        processed_path = f"/processed/{file_info['name']}"
        df.to_parquet(processed_path)

        return {
            "original_file": file_info["path"],
            "processed_file": processed_path,
            "stats": stats,
            "success": True
        }
    """,
    max_workers=5,
    continue_on_error=True,
    timeout_per_item=300  # 5 minutes per file
)

# Store results with error handling
builder.add_async_code(
    "store_results",
    """
    import json

    # Separate successful and failed processing
    successful_files = [r for r in results if r.get("success")]
    failed_files = [r for r in errors if r.get("error")]

    # Store processing results
    async with db.acquire() as conn:
        for file_result in successful_files:
            await conn.execute("""
                INSERT INTO file_processing_log
                (file_path, processed_path, stats, processed_at)
                VALUES ($1, $2, $3, NOW())
            """,
            file_result["original_file"],
            file_result["processed_file"],
            json.dumps(file_result["stats"])
        )

    result = {
        "processed_count": len(successful_files),
        "failed_count": len(failed_files),
        "total_rows": sum(f["stats"]["rows"] for f in successful_files),
        "processing_summary": {
            "successful_files": [f["original_file"] for f in successful_files],
            "failed_files": [f["item"] for f in failed_files]
        }
    }
    """
)

# Connect the pipeline
builder.add_connection("scan_files", "files", "process_files", "items")
builder.add_connection("process_files", "results", "store_results", "results")
builder.add_connection("process_files", "errors", "store_results", "errors")
```

### 4. Resilient External Service Integration

```python
# Build a fault-tolerant service integration
builder = AsyncWorkflowBuilder("service_integration")

# Configure resources
builder = (builder
    .with_http_client("primary_api", base_url="https://primary.service.com")
    .with_http_client("backup_api", base_url="https://backup.service.com")
    .with_cache("cache"))

# Primary service with circuit breaker
AsyncPatterns.circuit_breaker(
    builder,
    "primary_service",
    """
    response = await primary_api.post("/process", json=request_data)
    if response.status != 200:
        raise Exception(f"Service error: {response.status}")
    result = await response.json()
    """,
    failure_threshold=5,
    reset_timeout=60.0
)

# Backup service as fallback
AsyncPatterns.timeout_with_fallback(
    builder,
    "try_primary",
    "use_backup",
    """
    # Try primary service first
    if primary_result.get("success", False):
        result = primary_result
    else:
        raise Exception("Primary service unavailable")
    """,
    """
    # Use backup service
    response = await backup_api.post("/process", json=request_data)
    result = await response.json()
    result["_used_backup"] = True
    """,
    timeout_seconds=10.0
)

# Cache successful results
AsyncPatterns.cache_aside(
    builder,
    "cache_check",
    "fetch_fresh",
    "cache_store",
    """
    # Fetch fresh data if not cached
    if not backup_result.get("_used_backup"):
        result = backup_result
    else:
        # For backup results, try to refresh from primary
        try:
            response = await primary_api.get(f"/data/{item_id}")
            result = await response.json()
        except:
            result = backup_result  # Fall back to backup data
    """,
    cache_key_template="service_data_{item_id}",
    ttl_seconds=1800  # 30 minutes
)

# Connect services
builder.add_connection("primary_service", None, "try_primary", "primary_result")
builder.add_connection("use_backup", None, "cache_check", "backup_result")
```

## Resource Management Patterns

### Database Operations

```python
builder = AsyncWorkflowBuilder("db_operations")

# Configure database with connection pooling
builder.with_database(
    "main_db",
    host="prod-db.company.com",
    database="analytics",
    user="app_user",
    password="secure_password",
    min_size=5,
    max_size=20
)

# Use database in operations
builder.add_resource_node(
    "query_users",
    "main_db",
    "fetch",
    {"query": "SELECT * FROM users WHERE created_at > $1", "params": ["2024-01-01"]}
)

# Or use in async code
builder.add_async_code(
    "complex_query",
    """
    async with db.acquire() as conn:
        # Complex transaction
        async with conn.transaction():
            users = await conn.fetch("SELECT * FROM users WHERE active = true")
            for user in users:
                await conn.execute(
                    "UPDATE user_stats SET last_seen = NOW() WHERE user_id = $1",
                    user["id"]
                )

        result = {"updated_users": len(users)}
    """,
    required_resources=["main_db"]
)
```

### HTTP Client Configuration

```python
# Configure HTTP client with authentication
builder.with_http_client(
    "authenticated_api",
    base_url="https://api.service.com",
    headers={
        "Authorization": "Bearer your-token",
        "User-Agent": "MyApp/1.0"
    },
    timeout=30,
    connection_limit=50
)

# Use in API calls
builder.add_async_code(
    "api_call",
    """
    # Client is pre-configured with auth and base URL
    response = await authenticated_api.get("/users", params={"limit": 100})

    if response.status == 200:
        data = await response.json()
        result = {"users": data["users"], "total": data["total"]}
    else:
        raise Exception(f"API error: {response.status}")
    """,
    required_resources=["authenticated_api"]
)
```

## Error Handling Strategies

### Comprehensive Error Recovery

```python
from kailash.workflow import AsyncRetryPolicy, ErrorHandler

# Configure retry behavior
retry_policy = AsyncRetryPolicy(
    max_attempts=3,
    initial_delay=1.0,
    backoff_factor=2.0,
    retry_exceptions=["aiohttp.ClientError", "asyncio.TimeoutError"]
)

# Configure fallback handling
error_handler = ErrorHandler(
    handler_type="fallback",
    fallback_value={"success": False, "recovered": True, "data": None}
)

# Apply to critical operations
builder.add_async_code(
    "critical_operation",
    """
    # Critical business operation
    response = await external_service.process_payment(payment_data)
    result = {
        "transaction_id": response["id"],
        "status": response["status"],
        "amount": response["amount"]
    }
    """,
    retry_policy=retry_policy,
    error_handler=error_handler,
    timeout=60
)
```

### Custom Error Recovery

```python
# Custom error handling within operations
builder.add_async_code(
    "robust_operation",
    """
    import logging

    success_count = 0
    errors = []

    for attempt in range(3):
        try:
            response = await risky_operation()
            success_count += 1
            break  # Success
        except Exception as e:
            error_info = {
                "attempt": attempt + 1,
                "error": str(e),
                "timestamp": time.time()
            }
            errors.append(error_info)
            logging.warning(f"Attempt {attempt + 1} failed: {e}")

            if attempt < 2:  # Not final attempt
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    result = {
        "success": success_count > 0,
        "attempts": len(errors) + success_count,
        "errors": errors if errors else None
    }
    """
)
```

## Performance Optimization

### Controlling Concurrency

```python
# Optimize for different workload types

# CPU-intensive tasks - limit workers
builder.add_parallel_map(
    "cpu_intensive",
    cpu_bound_function,
    max_workers=4,  # Don't exceed CPU cores
    batch_size=10
)

# I/O-intensive tasks - more workers
builder.add_parallel_map(
    "io_intensive",
    io_bound_function,
    max_workers=50,  # Higher concurrency for I/O
    batch_size=100
)

# Memory-intensive tasks - smaller batches
builder.add_parallel_map(
    "memory_intensive",
    memory_bound_function,
    max_workers=5,
    batch_size=5,  # Smaller batches to control memory
    timeout_per_item=120
)
```

### Resource Optimization

```python
# Optimize database connections
builder.with_database(
    "analytics_db",
    host="analytics.db.com",
    min_size=2,   # Minimum connections
    max_size=10,  # Maximum connections
    command_timeout=60,
    server_settings={
        "application_name": "analytics_pipeline",
        "tcp_keepalives_idle": "600"
    }
)

# Optimize HTTP connections
builder.with_http_client(
    "api_client",
    base_url="https://api.example.com",
    connection_limit=20,  # Connection pool size
    timeout=30,
    headers={"Connection": "keep-alive"}
)
```

## Testing Async Workflows

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_async_workflow():
    # Create workflow
    builder = AsyncWorkflowBuilder("test_workflow")
    builder.add_async_code(
        "test_node",
        "result = {'processed': True, 'value': input_value * 2}"
    )

    workflow = builder.build()

    # Execute with test data
    runtime = AsyncLocalRuntime()
    result = await runtime.execute_workflow_async(
        workflow,
        {"input_value": 21}
    )

    # Verify results
    assert result["status"] == "success"
    assert result["results"]["test_node"]["processed"] is True
    assert result["results"]["test_node"]["value"] == 42
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_resource_integration():
    # Mock external resources
    mock_registry = ResourceRegistry()
    mock_db = AsyncMock()
    mock_registry.register_instance("test_db", mock_db)

    # Create workflow with resources
    builder = AsyncWorkflowBuilder(resource_registry=mock_registry)
    builder.add_resource_node(
        "db_operation",
        "test_db",
        "fetch",
        {"query": "SELECT 1"}
    )

    workflow = builder.build()
    runtime = AsyncLocalRuntime(resource_registry=mock_registry)

    # Configure mock behavior
    mock_db.fetch.return_value = [{"result": 1}]

    # Execute and verify
    result = await runtime.execute_workflow_async(workflow, {})
    assert result["status"] == "success"
    mock_db.fetch.assert_called_once()
```

## Production Deployment

### Configuration Management

```python
import os
from dataclasses import dataclass

@dataclass
class WorkflowConfig:
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_name: str = os.getenv("DB_NAME", "app")
    api_base_url: str = os.getenv("API_BASE_URL", "https://api.example.com")
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    max_workers: int = int(os.getenv("MAX_WORKERS", "10"))

def create_production_workflow(config: WorkflowConfig):
    builder = AsyncWorkflowBuilder("production_pipeline")

    # Configure resources (chainable)
    builder = (builder
        .with_database("db", host=config.db_host, database=config.db_name)
        .with_http_client("api", base_url=config.api_base_url)
        .with_cache("cache", host=config.redis_host))

    # Add nodes (returns node_id)
    builder.add_parallel_map("process", process_function, max_workers=config.max_workers)

    return builder.build()
```

### Monitoring and Logging

```python
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add monitoring to workflows
builder.add_async_code(
    "monitored_operation",
    """
    import time
    import logging

    start_time = time.time()
    logger = logging.getLogger(__name__)

    try:
        # Your operation here
        response = await some_operation()

        # Log success metrics
        duration = time.time() - start_time
        logger.info(f"Operation completed in {duration:.2f}s")

        result = {
            "success": True,
            "duration": duration,
            "data": response
        }

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Operation failed after {duration:.2f}s: {e}")
        raise
    """
)
```

## Common Patterns and Best Practices

### 1. Always Use Resource Management

```python
# ✅ Good - Resources managed by workflow
builder = AsyncWorkflowBuilder("pipeline")
builder = (builder
    .with_database("db")
    .with_http_client("api"))

# ❌ Bad - Resources created in node code
builder.add_async_code("bad", """
    db = await create_db_connection()  # Don't do this
""")
```

### 2. Handle Errors Gracefully

```python
# ✅ Good - Structured error handling
AsyncPatterns.retry_with_backoff(
    builder, "operation", operation_code,
    max_retries=3, initial_backoff=1.0
)

# ❌ Bad - Ignoring errors
builder.add_async_code("bad", """
    try:
        result = await operation()
    except:
        pass  # Don't ignore errors
""")
```

### 3. Use Appropriate Concurrency

```python
# ✅ Good - Controlled concurrency
builder.add_parallel_map(
    "process",
    function_code,
    max_workers=10,  # Reasonable limit
    continue_on_error=True
)

# ❌ Bad - Unlimited concurrency
builder.add_parallel_map(
    "process",
    function_code,
    max_workers=1000  # Will overwhelm system
)
```

### 4. Use Builder Pattern Correctly

```python
# ✅ Good - Correct builder usage
builder = AsyncWorkflowBuilder("pipeline")

# Chain resource configuration
builder = builder.with_database("db")

# Add nodes (returns node_ids)
step1_id = builder.add_async_code("step1", code1)
step2_id = builder.add_async_code("step2", code2)

# Connect nodes
builder.add_connection(step1_id, "output", step2_id, "input")

# Build workflow
workflow = builder.build()
```

## Advanced Connection Patterns

### Multiple Connections Between Same Nodes

AsyncWorkflowBuilder supports multiple connections between the same pair of nodes, automatically merging connection mappings:

```python
# Multiple outputs from health monitoring
builder.add_async_code("health_monitor", """
result = {
    "alerts": ["CPU High", "Memory Warning"],
    "needs_alerting": True,
    "metrics": {"cpu": 95, "memory": 88},
    "status": "critical"
}
""")

builder.add_async_code("alert_processor", """
# All connected variables are available
alerts = globals().get('alerts', [])
needs_alerting = globals().get('needs_alerting', False)
metrics = globals().get('metrics', {})

result = {
    "processed_alerts": len(alerts),
    "alerting_enabled": needs_alerting,
    "critical_metrics": [k for k, v in metrics.items() if v > 90]
}
""")

# Multiple connections to same target node - automatically merged
builder.add_connection("health_monitor", "result.alerts", "alert_processor", "alerts")
builder.add_connection("health_monitor", "result.needs_alerting", "alert_processor", "needs_alerting")
builder.add_connection("health_monitor", "result.metrics", "alert_processor", "metrics")
```

### Complex Data Path Mapping

Use dot notation to map specific parts of complex outputs:

```python
builder.add_async_code("data_fetcher", """
result = {
    "user_data": {"id": 123, "profile": {"name": "Alice", "role": "admin"}},
    "permissions": {"read": True, "write": True, "admin": False},
    "session": {"token": "abc123", "expires": 3600}
}
""")

# Map nested data paths to different target inputs
builder.add_connection("data_fetcher", "result.user_data.profile", "processor", "user_profile")
builder.add_connection("data_fetcher", "result.permissions", "processor", "user_permissions")
builder.add_connection("data_fetcher", "result.session.token", "processor", "auth_token")
```

### Fan-out and Fan-in Patterns

```python
# Fan-out: One source to multiple targets
builder.add_connection("source", "result.data", "processor_a", "input")
builder.add_connection("source", "result.data", "processor_b", "input")
builder.add_connection("source", "result.metadata", "monitor", "stats")

# Fan-in: Multiple sources to one target
builder.add_connection("processor_a", "result", "aggregator", "data_a")
builder.add_connection("processor_b", "result", "aggregator", "data_b")
builder.add_connection("processor_c", "result", "aggregator", "data_c")
```

### Connection Best Practices

1. **Use descriptive variable names** in target nodes
2. **Group related connections** by functionality
3. **Validate all required inputs** are connected
4. **Use meaningful output paths** with dot notation
5. **Test complex connection patterns** with unit tests
6. **Multiple connections supported** - AsyncWorkflowBuilder automatically merges mappings

Example of production-ready connection pattern:

```python
# Production monitoring workflow with multiple connections
builder.add_async_code("collect_metrics", collect_metrics_code)
builder.add_async_code("evaluate_health", health_evaluation_code)
builder.add_async_code("send_alerts", alert_sending_code)

# Pipeline connections
builder.add_connection("collect_metrics", "result", "evaluate_health", "metrics")

# Multiple alert connections (the pattern that was previously broken)
builder.add_connection("evaluate_health", "result.alerts", "send_alerts", "alerts")
builder.add_connection("evaluate_health", "result.needs_alerting", "send_alerts", "needs_alerting")
builder.add_connection("evaluate_health", "result.severity", "send_alerts", "severity_level")
```

## Next Steps

- Explore more patterns in `/sdk-users/workflows/async/`
- Check out production examples in `/sdk-users/workflows/by-industry/`
- Learn about deployment in the [Deployment Guide](../deployment/async-deployment.md)
- Read about monitoring in the [Observability Guide](../observability/async-monitoring.md)

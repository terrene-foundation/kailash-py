# Enhanced Gateway Integration Developer Guide

## Overview

The Enhanced Gateway Integration extends Kailash's DurableAPIGateway with advanced resource management capabilities, enabling seamless integration of non-serializable objects (databases, HTTP clients, caches) into async workflows through JSON-serializable resource references.

## Key Features

- **Resource References**: Pass complex objects through JSON API using resource references
- **Secret Management**: Secure credential handling with encryption
- **Async Workflow Support**: Full support for AsyncWorkflowBuilder patterns
- **Resource Lifecycle**: Automatic resource creation, pooling, and cleanup
- **Health Monitoring**: Built-in health checks for all resources

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Client SDK     │────▶│ Enhanced Gateway │────▶│ Async Runtime   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                           │
                               ▼                           ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │ Resource Registry│     │ Resource Pool   │
                        └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │ Secret Manager   │
                        └──────────────────┘
```

## Core Components

### 1. EnhancedDurableAPIGateway

The main gateway class that extends DurableAPIGateway:

```python
from kailash.api.gateway import EnhancedDurableAPIGateway, SecretManager
from kailash.resources import ResourceRegistry

# Create gateway
gateway = EnhancedDurableAPIGateway(
    resource_registry=ResourceRegistry(),
    secret_manager=SecretManager(),
    enable_durability=True,  # Enable checkpoint persistence
    title="Production Gateway",
    description="Enterprise workflow orchestration"
)
```

### 2. Resource References

Resource references allow passing non-serializable objects through JSON:

```python
from kailash.api.gateway import ResourceReference

# Database resource
db_ref = ResourceReference(
    type="database",
    config={
        "host": "localhost",
        "port": 5432,
        "database": "production"
    },
    credentials_ref="db_creds"  # Reference to stored secret
)

# HTTP client resource
http_ref = ResourceReference(
    type="http_client",
    config={
        "base_url": "https://api.example.com",
        "timeout": 30,
        "headers": {"User-Agent": "KailashSDK/1.0"}
    },
    credentials_ref="api_key"
)

# Cache resource
cache_ref = ResourceReference(
    type="cache",
    config={
        "host": "localhost",
        "port": 6379,
        "db": 0
    }
)
```

### 3. Secret Management

Secure credential storage with encryption:

```python
# Store secrets
await gateway.secret_manager.store_secret(
    "db_creds",
    {"user": "dbuser", "password": "secure_password"},
    encrypt=True  # Encrypt at rest
)

await gateway.secret_manager.store_secret(
    "api_key",
    {"api_key": "sk-1234567890"},
    encrypt=True
)

# Secrets are automatically resolved when resources are created
```

### 4. Workflow Registration

Register workflows with resource requirements:

```python
from kailash.workflow import AsyncWorkflowBuilder

# Build workflow with resources
workflow = (
    AsyncWorkflowBuilder("data_pipeline")
    .add_async_code("extract", """
db = await get_resource("source_db")
async with db.acquire() as conn:
    data = await conn.fetch("SELECT * FROM users")
    result = {"users": [dict(row) for row in data]}
""", required_resources=["source_db"])
    .add_async_code("transform", """
# Transform data
transformed = []
for user in users:
    transformed.append({
        "id": user["id"],
        "name": user["name"].upper(),
        "active": user["status"] == "active"
    })
result = {"transformed": transformed}
""")
    .add_async_code("load", """
cache = await get_resource("result_cache")
import json
for user in transformed:
    key = f"user:{user['id']}"
    await cache.setex(key, 3600, json.dumps(user))
result = {"loaded": len(transformed)}
""", required_resources=["result_cache"])
    .add_connection("extract", "users", "transform", "users")
    .add_connection("transform", "transformed", "load", "transformed")
    .build()
)

# Register with gateway
gateway.register_workflow(
    "data_pipeline",
    workflow,
    required_resources=["source_db", "result_cache"],
    description="ETL pipeline for user data"
)
```

## Usage Patterns

### 1. Basic Workflow Execution

```python
from kailash.api.gateway import WorkflowRequest

# Create request with resources
request = WorkflowRequest(
    parameters={"limit": 100},
    resources={
        "source_db": ResourceReference(
            type="database",
            config={
                "host": "db.example.com",
                "port": 5432,
                "database": "users"
            },
            credentials_ref="db_creds"
        ),
        "result_cache": ResourceReference(
            type="cache",
            config={
                "host": "cache.example.com",
                "port": 6379
            }
        )
    },
    context={
        "user": "data_engineer",
        "environment": "production"
    }
)

# Execute workflow
response = await gateway.execute_workflow("data_pipeline", request)

if response.status == "completed":
    print(f"Loaded {response.result['load']['loaded']} users")
else:
    print(f"Error: {response.error}")
```

### 2. Resource Sharing

Resources are automatically pooled and shared across workflows:

```python
# First workflow creates the resource pool
request1 = WorkflowRequest(
    resources={
        "shared_db": ResourceReference(
            type="database",
            config={"host": "localhost", "database": "app"},
            credentials_ref="db_creds"
        )
    }
)

# Subsequent workflows reuse the same pool
request2 = WorkflowRequest(
    resources={
        "shared_db": "@shared_db"  # Reference existing resource
    }
)
```

### 3. Multi-Resource Workflows

```python
workflow = (
    AsyncWorkflowBuilder("api_aggregator")
    .add_async_code("fetch_data", """
# Use multiple resources concurrently
import asyncio

async def fetch_users():
    db = await get_resource("user_db")
    async with db.acquire() as conn:
        return await conn.fetch("SELECT id, name FROM users")

async def fetch_orders():
    api = await get_resource("order_api")
    response = await api.get("/orders?limit=100")
    return await response.json()

async def cache_result(key, data):
    cache = await get_resource("cache")
    import json
    await cache.setex(key, 300, json.dumps(data))

# Fetch concurrently
users, orders = await asyncio.gather(
    fetch_users(),
    fetch_orders()
)

# Cache results
await asyncio.gather(
    cache_result("users:latest", [dict(u) for u in users]),
    cache_result("orders:latest", orders)
)

result = {
    "user_count": len(users),
    "order_count": len(orders)
}
""", required_resources=["user_db", "order_api", "cache"])
    .build()
)
```

### 4. Client SDK Usage

Use the enhanced client SDK for easy interaction:

```python
from kailash.client import KailashClient

# Create client
async with KailashClient("http://gateway.example.com") as client:
    # Use resource helpers
    db_resource = client.database(
        host="localhost",
        database="myapp",
        credentials_ref="db_creds"
    )

    cache_resource = client.cache(
        host="localhost",
        port=6379
    )

    # Execute workflow
    result = await client.execute_workflow(
        "data_pipeline",
        parameters={"process_date": "2024-01-15"},
        resources={
            "db": db_resource,
            "cache": cache_resource
        }
    )

    if result.is_success:
        print(f"Processed: {result.result}")
```

## Advanced Features

### 1. Resource Health Checks

```python
# Define health check for custom resource
async def database_health_check(pool):
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False

# Register with health check
registry.register_factory(
    "main_db",
    DatabasePoolFactory(**config),
    health_check=database_health_check
)

# Check gateway health
health = await gateway.health_check()
print(f"Gateway status: {health['status']}")
print(f"Resources: {health['resources']}")
```

### 2. Custom Resource Types

Extend the resource resolver for custom types:

```python
from kailash.gateway.resource_resolver import ResourceResolver

class CustomResourceResolver(ResourceResolver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolvers["message_queue"] = self._resolve_message_queue

    async def _resolve_message_queue(self, config, credentials):
        # Create custom resource
        from my_queue import QueueClient

        client = QueueClient(
            broker=config["broker"],
            credentials=credentials
        )

        # Register in resource registry
        self.resource_registry.register_factory(
            f"mq_{config['queue_name']}",
            lambda: client
        )

        return client
```

### 3. Workflow Context and Metadata

```python
# Access context in workflows
workflow = (
    AsyncWorkflowBuilder("context_aware")
    .add_async_code("process", """
# Access execution context
from kailash.runtime.context import get_current_context
context = get_current_context()

user = context.get_variable("user")
environment = context.get_variable("environment")

# Use context for conditional logic
if environment == "production":
    cache_ttl = 3600
else:
    cache_ttl = 60

result = {
    "processed_by": user,
    "cache_ttl": cache_ttl
}
""")
    .build()
)
```

## Error Handling

### 1. Resource Resolution Errors

```python
try:
    response = await gateway.execute_workflow("pipeline", request)
except WorkflowNotFoundError:
    print("Workflow not registered")
except ValueError as e:
    if "Resource" in str(e):
        print(f"Resource error: {e}")
    else:
        raise
```

### 2. Secret Resolution Errors

```python
from kailash.api.gateway import SecretNotFoundError

try:
    secret = await secret_manager.get_secret("missing_key")
except SecretNotFoundError:
    # Handle missing secret
    print("Secret not found, using defaults")
```

### 3. Workflow Execution Errors

```python
response = await gateway.execute_workflow("risky_workflow", request)

if response.status == "failed":
    print(f"Workflow failed: {response.error}")
    # Access partial results if available
    if response.result:
        completed_steps = [k for k, v in response.result.items() if v]
        print(f"Completed steps: {completed_steps}")
```

## Performance Optimization

### 1. Resource Pooling

```python
# Configure connection pools
db_ref = ResourceReference(
    type="database",
    config={
        "host": "localhost",
        "database": "app",
        "min_size": 10,      # Minimum pool size
        "max_size": 50,      # Maximum pool size
        "max_queries": 5000, # Queries per connection
        "max_inactive_connection_lifetime": 300
    }
)

# HTTP client pooling
http_ref = ResourceReference(
    type="http_client",
    config={
        "connection_limit": 100,     # Total connections
        "connection_limit_per_host": 30,  # Per host limit
        "keepalive_timeout": 30
    }
)
```

### 2. Caching Strategies

```python
# Use secret caching
secret_manager = SecretManager(
    cache_ttl=300  # Cache secrets for 5 minutes
)

# Cache workflow results
workflow = (
    AsyncWorkflowBuilder("cached_pipeline")
    .add_async_code("check_cache", """
cache = await get_resource("cache")
import json

cache_key = f"pipeline:{input_key}"
cached = await cache.get(cache_key)

if cached:
    result = {"data": json.loads(cached), "cache_hit": True}
else:
    result = {"data": None, "cache_hit": False}
""", required_resources=["cache"])
    .add_async_code("process", """
if cache_hit:
    result = {"processed": data}
else:
    # Heavy processing here
    processed = expensive_operation(input_key)

    # Cache for next time
    cache = await get_resource("cache")
    await cache.setex(
        f"pipeline:{input_key}",
        3600,
        json.dumps(processed)
    )

    result = {"processed": processed}
""", required_resources=["cache"])
    .build()
)
```

### 3. Concurrent Execution

```python
# Execute multiple workflows concurrently
import asyncio

async def run_batch(gateway, workflow_id, items):
    tasks = []
    for item in items:
        request = WorkflowRequest(
            parameters={"item": item},
            resources={"db": "@shared_db"}
        )
        task = gateway.execute_workflow(workflow_id, request)
        tasks.append(task)

    # Process all concurrently
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.status == "completed")
    print(f"Processed {success_count}/{len(items)} successfully")

    return results
```

## Testing

### 1. Unit Testing Workflows

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_data_pipeline():
    # Mock resources
    mock_db = AsyncMock()
    mock_db.acquire.return_value.__aenter__.return_value.fetch.return_value = [
        {"id": 1, "name": "test"}
    ]

    # Create test gateway
    gateway = EnhancedDurableAPIGateway()

    # Register test workflow
    gateway.register_workflow("test_pipeline", workflow)

    # Mock resource resolution
    with patch.object(gateway._resource_resolver, 'resolve', return_value=mock_db):
        response = await gateway.execute_workflow(
            "test_pipeline",
            WorkflowRequest(resources={"db": mock_ref})
        )

    assert response.status == "completed"
```

### 2. Integration Testing

```python
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_real_database_workflow(gateway, postgres_connection):
    """Test with real PostgreSQL."""
    request = WorkflowRequest(
        resources={
            "db": ResourceReference(
                type="database",
                config={
                    "host": "localhost",
                    "port": 5432,
                    "database": "test"
                }
            )
        }
    )

    response = await gateway.execute_workflow("db_workflow", request)
    assert response.status == "completed"
```

## Best Practices

1. **Resource Naming**: Use descriptive, consistent names for resources
   ```python
   # Good
   "user_db", "order_cache", "payment_api"

   # Bad
   "db1", "cache", "api"
   ```

2. **Secret Management**: Never hardcode credentials
   ```python
   # Good
   ResourceReference(
       type="database",
       config={"host": "localhost"},
       credentials_ref="db_creds"
   )

   # Bad
   ResourceReference(
       type="database",
       config={
           "host": "localhost",
           "user": "admin",  # Don't do this!
           "password": "password123"  # Never!
       }
   )
   ```

3. **Error Handling**: Always handle resource failures gracefully
   ```python
   try:
       db = await get_resource("db")
       data = await db.fetch(query)
   except Exception as e:
       # Log error
       logger.error(f"Database query failed: {e}")
       # Return partial result
       result = {"error": str(e), "data": []}
   ```

4. **Resource Cleanup**: Use context managers for resources
   ```python
   db = await get_resource("db")
   async with db.acquire() as conn:
       # Connection automatically returned to pool
       result = await conn.fetch(query)
   ```

5. **Monitoring**: Add instrumentation to workflows
   ```python
   .add_async_code("monitored_step", """
   import time
   start = time.time()

   # Do work
   result = await process_data()

   # Record metrics
   duration = time.time() - start
   logger.info(f"Step completed in {duration:.2f}s")

   result["metrics"] = {
       "duration": duration,
       "record_count": len(result["data"])
   }
   """)
   ```

## Migration Guide

### From Standard Gateway

```python
# Before: Standard DurableAPIGateway
gateway = DurableAPIGateway()
workflow = create_workflow_with_hardcoded_resources()
gateway.register_workflow("pipeline", workflow)

# After: Enhanced Gateway
gateway = EnhancedDurableAPIGateway(
    resource_registry=ResourceRegistry(),
    secret_manager=SecretManager()
)

# Resources now passed at execution time
request = WorkflowRequest(
    resources={
        "db": ResourceReference(...),
        "cache": ResourceReference(...)
    }
)
response = await gateway.execute_workflow("pipeline", request)
```

### From Direct Resource Usage

```python
# Before: Direct resource creation in workflow
workflow = (
    AsyncWorkflowBuilder("old_way")
    .add_async_code("process", """
import asyncpg
# Hardcoded connection
conn = await asyncpg.connect(
    host="localhost",
    user="user",
    password="pass"
)
""")
)

# After: Resource injection
workflow = (
    AsyncWorkflowBuilder("new_way")
    .add_async_code("process", """
# Resource injected by gateway
db = await get_resource("db")
async with db.acquire() as conn:
    # Use connection from pool
    data = await conn.fetch(query)
""", required_resources=["db"])
)
```

## Troubleshooting

### Common Issues

1. **Resource Not Found**
   ```
   Error: Resource 'db' not registered
   ```
   - Ensure resource is passed in WorkflowRequest
   - Check resource name matches workflow requirement

2. **Secret Resolution Failed**
   ```
   Error: Secret 'api_key' not found
   ```
   - Verify secret was stored with correct name
   - Check secret backend configuration

3. **Connection Pool Exhausted**
   ```
   Error: Pool.acquire() timeout
   ```
   - Increase pool size in resource config
   - Ensure connections are properly released
   - Check for connection leaks

4. **Workflow Timeout**
   ```
   Error: Workflow execution timeout
   ```
   - Increase workflow timeout setting
   - Optimize long-running operations
   - Consider breaking into smaller workflows

### Debug Mode

Enable debug logging:

```python
import logging

# Enable gateway debug logs
logging.getLogger("kailash.gateway").setLevel(logging.DEBUG)

# Trace resource resolution
logging.getLogger("kailash.resources").setLevel(logging.DEBUG)

# Monitor workflow execution
gateway = EnhancedDurableAPIGateway()
gateway.workflows["pipeline"].metadata["debug"] = True
```

## Next Steps

1. Review the [User Guide](enhanced-gateway-user-guide.md) for practical examples
2. Explore [Advanced Patterns](../patterns/gateway-patterns.md)
3. Check [API Reference](../../api/gateway.md) for detailed documentation
4. See [Example Workflows](../workflows/) for production patterns

# Enhanced Gateway Integration Guide

*Enterprise gateway with resource management and async workflow support*

## Overview

The Enhanced Gateway architecture leverages Kailash's redesigned server classes (`EnterpriseWorkflowServer`) with advanced resource management capabilities, enabling seamless integration of non-serializable objects (databases, HTTP clients, caches) into async workflows through JSON-serializable resource references.

**NEW: Nexus Multi-Channel Integration** - This guide focuses on single-channel API gateway patterns. For unified API + CLI + MCP orchestration, see [Nexus Patterns](../enterprise/nexus-patterns.md).

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Completed [Workflows](02-workflows.md) - Workflow basics
- Understanding of [Async Workflow Builder](07-async-workflow-builder.md)
- Familiarity with [Resource Registry](08-resource-registry-guide.md)

## Key Features

- **Resource References**: Pass complex objects through JSON API
- **Secret Management**: Secure credential handling with encryption
- **Async Workflow Support**: Full AsyncWorkflowBuilder integration
- **Resource Lifecycle**: Automatic pooling and cleanup
- **Health Monitoring**: Built-in resource health checks

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

### EnhancedDurableAPIGateway

The main gateway class extending DurableAPIGateway:

```python
from kailash.servers.gateway import create_gateway
from kailash.gateway.security import SecretManager
from kailash.resources.registry import ResourceRegistry

# Create enhanced gateway with redesigned architecture
gateway = create_gateway(
    title="Production Gateway",
    description="Enterprise workflow orchestration",
    server_type="enterprise",  # Uses EnterpriseWorkflowServer

    # Resource management
    resource_registry=ResourceRegistry(),
    secret_manager=SecretManager(),

    # Enhanced features
    enable_durability=True,
    enable_resource_management=True,
    enable_async_execution=True
)

# Start the gateway
gateway.run(host="0.0.0.0", port=8000)
```

### Resource References

Resource references allow passing non-serializable objects through JSON:

```python
from kailash.gateway.resource_resolver import ResourceReference

# Database resource reference
db_ref = ResourceReference(
    type="database",
    config={
        "host": "localhost",
        "port": 5432,
        "database": "production",
        "pool_size": 10
    },
    credentials_ref="db_creds"  # Reference to stored secret
)

# HTTP client resource reference
http_ref = ResourceReference(
    type="http_client",
    config={
        "base_url": "https://api.example.com",
        "timeout": 30,
        "headers": {"User-Agent": "KailashSDK/1.0"}
    },
    credentials_ref="api_key"
)

# Cache resource reference
cache_ref = ResourceReference(
    type="cache",
    config={
        "host": "localhost",
        "port": 6379,
        "db": 0,
        "decode_responses": True
    }
)
```

### Secret Management

Secure credential storage with encryption:

```python
# Store secrets securely
await gateway.secret_manager.store_secret(
    "db_creds",
    {
        "user": "dbuser",
        "password": "secure_password"
    },
    encrypt=True  # Encrypt at rest
)

await gateway.secret_manager.store_secret(
    "api_key",
    {
        "api_key": "sk-1234567890",
        "api_secret": "secret_value"
    },
    encrypt=True
)

# Secrets are automatically resolved when resources are created
```

## Workflow Integration

### Registering Workflows

Register workflows with resource requirements:

```python
from kailash.workflow import AsyncWorkflowBuilder

# Build workflow with resources
workflow = (
    AsyncWorkflowBuilder("data_pipeline")
    .add_async_code("extract", """
# Get database resource
db = await get_resource("source_db")

# Use with async context manager
async with db.acquire() as conn:
    data = await conn.fetch("SELECT * FROM users WHERE active = true")
    result = {"users": [dict(row) for row in data]}
""", required_resources=["source_db"])

    .add_async_code("transform", """
# Transform user data
transformed = []
for user in users:
    transformed.append({
        "id": user["id"],
        "name": user["name"].upper(),
        "email": user["email"].lower(),
        "active": True
    })
result = {"transformed": transformed}
""")

    .add_async_code("load", """
# Get cache resource
cache = await get_resource("result_cache")

# Store transformed data
import json
for user in transformed:
    key = f"user:{user['id']}"
    value = json.dumps(user)
    await cache.setex(key, 3600, value)

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

### Executing Workflows

Execute workflows with resource specifications:

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

# Check results
if response.status == "completed":
    print(f"Loaded {response.result['load']['loaded']} users")
    print(f"Execution time: {response.execution_time}s")
else:
    print(f"Error: {response.error}")
```

## Resource Management Patterns

### Resource Pooling

Resources are automatically pooled and shared:

```python
# First workflow creates the resource pool
request1 = WorkflowRequest(
    resources={
        "shared_db": ResourceReference(
            type="database",
            config={
                "host": "localhost",
                "database": "app",
                "min_pool_size": 5,
                "max_pool_size": 20
            },
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

# The gateway manages pool lifecycle automatically
```

### Multi-Resource Workflows

Use multiple resources in a single workflow:

```python
workflow = (
    AsyncWorkflowBuilder("api_aggregator")
    .add_async_code("fetch_all", """
import asyncio

# Define async fetch functions
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

# Fetch data concurrently
users, orders = await asyncio.gather(
    fetch_users(),
    fetch_orders()
)

# Cache results concurrently
await asyncio.gather(
    cache_result("users:latest", [dict(u) for u in users]),
    cache_result("orders:latest", orders)
)

result = {
    "user_count": len(users),
    "order_count": len(orders),
    "cached": True
}
""", required_resources=["user_db", "order_api", "cache"])
    .build()
)
```

### Resource Health Monitoring

The gateway monitors resource health:

```python
# Get resource health status
health_status = await gateway.get_resource_health()

# Example response:
{
    "resources": {
        "user_db": {
            "status": "healthy",
            "last_check": "2024-01-01T10:00:00Z",
            "metrics": {
                "pool_size": 10,
                "active_connections": 3,
                "avg_response_time_ms": 12.5
            }
        },
        "cache": {
            "status": "healthy",
            "last_check": "2024-01-01T10:00:05Z",
            "metrics": {
                "memory_usage_mb": 256,
                "hit_rate": 0.95,
                "avg_response_time_ms": 0.8
            }
        }
    },
    "overall_status": "healthy"
}
```

## Client SDK Usage

Use the enhanced client SDK for easy interaction:

```python
from kailash.client import KailashClient

# Create client
async with KailashClient("http://gateway.example.com") as client:
    # Configure resources
    db_resource = client.database(
        host="localhost",
        database="myapp",
        credentials_ref="db_creds"
    )

    cache_resource = client.cache(
        host="localhost",
        port=6379
    )

    api_resource = client.http_client(
        base_url="https://api.example.com",
        credentials_ref="api_key"
    )

    # Execute workflow with resources
    result = await client.execute_workflow(
        "data_pipeline",
        parameters={"process_date": "2024-01-15"},
        resources={
            "source_db": db_resource,
            "result_cache": cache_resource,
            "external_api": api_resource
        }
    )

    # Check status
    if result.success:
        print(f"Processed {result.data['count']} records")
```

## Security Best Practices

### Credential Management

```python
# Store credentials securely
await gateway.secret_manager.store_secret(
    "prod_db_creds",
    {
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"]
    },
    encrypt=True,
    rotation_days=90  # Auto-rotate after 90 days
)

# Use credential references in resources
db_ref = ResourceReference(
    type="database",
    config={
        "host": "prod-db.example.com",
        "database": "production"
    },
    credentials_ref="prod_db_creds"  # Reference, not inline
)
```

### Access Control

```python
# Configure access control
gateway.configure_access_control({
    "workflows": {
        "data_pipeline": {
            "allowed_users": ["data_engineer", "admin"],
            "allowed_roles": ["data_team"],
            "rate_limit": "100/hour"
        }
    },
    "resources": {
        "production_db": {
            "allowed_workflows": ["data_pipeline", "analytics"],
            "require_approval": True
        }
    }
})
```

## Monitoring and Observability

### Metrics Collection

```python
# Enable metrics collection
gateway.enable_metrics({
    "prometheus": {
        "enabled": True,
        "port": 9090
    },
    "custom_metrics": [
        "workflow_execution_time",
        "resource_pool_usage",
        "api_request_count"
    ]
})

# Access metrics
metrics = await gateway.get_metrics()
```

### Logging Configuration

```python
# Configure structured logging
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable detailed gateway logging
gateway.set_log_level("DEBUG")
```

## Troubleshooting

### Common Issues

**Resource Not Found:**
```python
# Check resource registration
registered = await gateway.list_registered_resources()
print(f"Registered resources: {registered}")

# Verify resource reference
if "my_resource" not in request.resources:
    print("Resource not included in request")
```

**Connection Pool Exhausted:**
```python
# Check pool status
health = await gateway.get_resource_health()
db_health = health["resources"]["database"]

if db_health["metrics"]["active_connections"] >= db_health["metrics"]["pool_size"]:
    print("Connection pool exhausted - increase pool size")
```

**Secret Resolution Failed:**
```python
# Verify secret exists
secrets = await gateway.secret_manager.list_secrets()
if "my_secret" not in secrets:
    print("Secret not found - store it first")
```

## Best Practices

### 1. Resource Naming

```python
# Use descriptive, consistent names
good_names = {
    "user_db": "Primary user database",
    "order_api": "Order service API",
    "session_cache": "User session cache"
}

# Avoid generic names
bad_names = ["db", "api", "cache"]
```

### 2. Error Handling

```python
# Handle resource errors gracefully
try:
    response = await gateway.execute_workflow("pipeline", request)
except WorkflowNotFoundError:
    logger.error("Workflow not registered")
except ResourceError as e:
    logger.error(f"Resource error: {e}")
    # Implement fallback logic
```

### 3. Resource Cleanup

```python
# Resources are automatically cleaned up, but you can force cleanup
await gateway.cleanup_resources(["temp_db", "test_cache"])

# Shutdown gateway properly
await gateway.shutdown()
```

## Related Guides

**Prerequisites:**
- [Async Workflow Builder](07-async-workflow-builder.md) - Async patterns
- [Resource Registry](08-resource-registry-guide.md) - Resource management

**Advanced Topics:**
- [Production](04-production.md) - Production deployment
- [Connection Pool](14-connection-pool-guide.md) - Database pooling

---

**Build enterprise-grade applications with Enhanced Gateway's resource management and async workflow capabilities!**

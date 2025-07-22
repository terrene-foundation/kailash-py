# Resource Registry Developer Guide

*Managing shared resources in async workflows*

## Overview

The Resource Registry lets you share database connections, HTTP clients, and other resources across multiple workflow executions. Instead of creating new connections every time, you register them once and reuse them efficiently.

> ✅ **Production Ready**: Fully tested with real PostgreSQL, Redis, HTTP services. Validated with 35+ unit tests covering all resource types, health checks, circuit breakers, and concurrent access patterns.

## Quick Start

### 1. Basic Database Example

```python
from kailash.resources import ResourceRegistry, DatabasePoolFactory
from kailash.nodes.code import AsyncPythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create registry
registry = ResourceRegistry()

# Register database
registry.register_factory(
    "main_db",
    DatabasePoolFactory(
        host="localhost",
        database="myapp",
        user="postgres",
        password="your_password"
    )
)

# Use in workflow
node = AsyncPythonCodeNode(
    name="db_query",
    code='''
# Get database from registry
db = await get_resource("main_db")

# Query data
async with db.acquire() as conn:
    users = await conn.fetch("SELECT * FROM users LIMIT 10")

result = {"users": [dict(row) for row in users]}
'''
)

# Execute with registry
runtime = LocalRuntime()
output = await node.execute_async(resource_registry=registry)
print(f"Found {len(output['users'])} users")
```

### 2. Multiple Resources Example

```python
from kailash.resources import HttpClientFactory, CacheFactory

# Register multiple resources
registry.register_factory(
    "api_client",
    HttpClientFactory(base_url="https://api.example.com")
)

registry.register_factory(
    "cache",
    CacheFactory(backend="redis", host="localhost")
)

# Use all resources together
node = AsyncPythonCodeNode(
    name="multi_resource",
    code='''
import asyncio
import json

# Get all resources
db = await get_resource("main_db")
api = await get_resource("api_client")
cache = await get_resource("cache")

# Check cache first
user_id = 123
cache_key = f"user:{user_id}"
cached_user = await cache.get(cache_key)

if cached_user:
    user_data = json.loads(cached_user)
    source = "cache"
else:
    # Get from database and API concurrently
    db_task = db.fetch("SELECT * FROM users WHERE id = $1", user_id)
    api_task = api.get(f"/users/{user_id}/profile")

    db_result, api_response = await asyncio.gather(db_task, api_task)

    user_data = {
        "basic_info": dict(db_result[0]) if db_result else None,
        "profile": await api_response.json()
    }

    # Cache for 5 minutes
    await cache.setex(cache_key, 300, json.dumps(user_data))
    source = "database+api"

result = {"user": user_data, "source": source}
'''
)

output = await node.execute_async(resource_registry=registry)
```

## Resource Types

### Database Connections

**PostgreSQL:**
```python
registry.register_factory(
    "postgres_db",
    DatabasePoolFactory(
        backend="postgresql",
        host="db.example.com",
        port=5432,
        database="production",
        user="app_user",
        password=os.environ["DB_PASSWORD"],
        min_size=5,
        max_size=20
    )
)
```

**MySQL:**
```python
registry.register_factory(
    "mysql_db",
    DatabasePoolFactory(
        backend="mysql",
        host="mysql.example.com",
        database="myapp",
        user="app_user",
        password=os.environ["MYSQL_PASSWORD"]
    )
)
```

**SQLite:**
```python
registry.register_factory(
    "sqlite_db",
    DatabasePoolFactory(
        backend="sqlite",
        database="/path/to/database.db"
    )
)
```

### HTTP Clients

**aiohttp (default):**
```python
registry.register_factory(
    "main_api",
    HttpClientFactory(
        base_url="https://api.example.com",
        timeout=30,
        headers={"User-Agent": "MyApp/1.0"}
    )
)
```

**httpx:**
```python
registry.register_factory(
    "fast_api",
    HttpClientFactory(
        backend="httpx",
        base_url="https://fast-api.example.com",
        timeout=10
    )
)
```

### Cache Systems

**Redis:**
```python
registry.register_factory(
    "redis_cache",
    CacheFactory(
        backend="redis",
        host="cache.example.com",
        port=6379,
        db=0
    )
)
```

**In-Memory Cache:**
```python
registry.register_factory(
    "memory_cache",
    CacheFactory(backend="memory")
)
```

### Message Queues

**RabbitMQ:**
```python
registry.register_factory(
    "message_queue",
    MessageQueueFactory(
        backend="rabbitmq",
        host="mq.example.com",
        username="app_user",
        password=os.environ["MQ_PASSWORD"]
    )
)
```

## Using Resources in Code

### Basic Resource Access

```python
# In AsyncPythonCodeNode code:
code = '''
# Get any registered resource
db = await get_resource("database_name")
api = await get_resource("api_client_name")
cache = await get_resource("cache_name")
'''
```

### Database Operations

```python
code = '''
db = await get_resource("main_db")

# Single query
async with db.acquire() as conn:
    user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", 123)
    result = {"user": dict(user)}

# Transaction
async with db.acquire() as conn:
    async with conn.transaction():
        await conn.execute("INSERT INTO orders ...")
        order_id = await conn.fetchval("SELECT lastval()")
        await conn.execute("INSERT INTO order_items ...")

    result = {"order_id": order_id}
'''
```

### HTTP API Calls

```python
code = '''
api = await get_resource("external_api")

# GET request
async with api.get("/users/123") as response:
    if response.status == 200:
        user_data = await response.json()
    else:
        user_data = {"error": "User not found"}

# POST request
async with api.post("/orders", json={"user_id": 123, "items": [...]}) as response:
    order_result = await response.json()

result = {"user": user_data, "order": order_result}
'''
```

### Cache Operations

```python
code = '''
cache = await get_resource("redis_cache")

# Get from cache
cached_value = await cache.get("my_key")

if cached_value:
    result = json.loads(cached_value)
else:
    # Generate data
    result = {"computed": True, "timestamp": time.time()}

    # Cache for 1 hour
    await cache.setex("my_key", 3600, json.dumps(result))
'''
```

## Error Handling

### Resource Failures

```python
code = '''
try:
    db = await get_resource("main_db")
    # Use database
except Exception as db_error:
    # Fallback to cache or alternative
    try:
        cache = await get_resource("backup_cache")
        result = await cache.get("fallback_data")
    except Exception as cache_error:
        result = {"error": "All services unavailable"}
'''
```

### Connection Issues

```python
code = '''
api = await get_resource("external_api")

try:
    async with api.get("/data", timeout=5) as response:
        if response.status == 200:
            result = await response.json()
        else:
            result = {"error": f"API returned {response.status}"}
except asyncio.TimeoutError:
    result = {"error": "API timeout"}
except Exception as e:
    result = {"error": f"API error: {str(e)}"}
'''
```

## Health Monitoring

Resources automatically monitor their health and recreate connections when needed:

```python
from kailash.resources.health import HealthStatus

async def custom_health_check(db_pool):
    """Custom health check for database."""
    try:
        async with db_pool.acquire() as conn:
            # Check if we can run a simple query
            await conn.fetchval('SELECT 1')
            # Check connection pool status
            if db_pool.get_size() > 0:
                return HealthStatus.healthy("Database is responsive")
            else:
                return HealthStatus.degraded("Low connection count")
    except Exception as e:
        return HealthStatus.unhealthy(f"Database error: {e}")

# Register with health check
registry.register_factory(
    "monitored_db",
    DatabasePoolFactory(...),
    health_check=custom_health_check
)
```

## Performance Tips

### 1. Connection Pooling

Always use connection pools for databases:

```python
# Good - connection pool shared across workflows
registry.register_factory(
    "shared_db",
    DatabasePoolFactory(
        min_size=5,    # Always keep 5 connections
        max_size=20    # Scale up to 20 under load
    )
)
```

### 2. Resource Reuse

Register resources once, use them everywhere:

```python
# Setup once (in main application)
def setup_resources():
    registry = ResourceRegistry()

    # All workflows share these resources
    registry.register_factory("db", DatabasePoolFactory(...))
    registry.register_factory("api", HttpClientFactory(...))
    registry.register_factory("cache", CacheFactory(...))

    return registry

# Use in multiple workflows
registry = setup_resources()

# Workflow 1
user_workflow = AsyncPythonCodeNode(code="db = await get_resource('db'); ...; result = db")
await user_workflow.execute_async(resource_registry=registry)

# Workflow 2 - reuses same connections
order_workflow = AsyncPythonCodeNode(code="db = await get_resource('db'); ...; result = db")
await order_workflow.execute_async(resource_registry=registry)
```

### 3. Concurrent Operations

Leverage async for concurrent resource access:

```python
code = '''
import asyncio

# Get multiple resources
db = await get_resource("main_db")
cache = await get_resource("redis_cache")
api = await get_resource("external_api")

# Run operations concurrently
async def get_user_data(user_id):
    async with db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

async def get_user_preferences(user_id):
    return await cache.get(f"prefs:{user_id}")

async def get_user_activity(user_id):
    async with api.get(f"/users/{user_id}/activity") as resp:
        return await resp.json()

# Execute all concurrently
user_data, preferences, activity = await asyncio.gather(
    get_user_data(123),
    get_user_preferences(123),
    get_user_activity(123)
)

result = {
    "user": dict(user_data) if user_data else None,
    "preferences": preferences,
    "activity": activity
}
'''
```

## Common Patterns

### 1. Cache-Aside Pattern

```python
code = '''
import json

cache = await get_resource("cache")
db = await get_resource("db")

async def get_user_with_cache(user_id):
    # Try cache first
    cache_key = f"user:{user_id}"
    cached = await cache.get(cache_key)

    if cached:
        return json.loads(cached)

    # Cache miss - get from database
    async with db.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    if user:
        user_dict = dict(user)
        # Cache for 30 minutes
        await cache.setex(cache_key, 1800, json.dumps(user_dict))
        return user_dict

    return None

result = {"user": await get_user_with_cache(123)}
'''
```

### 2. Circuit Breaker Pattern

Resources automatically implement circuit breakers:

```python
# Registry handles circuit breaking automatically
registry.register_factory(
    "unreliable_api",
    HttpClientFactory(base_url="https://unreliable-service.com"),
    metadata={"circuit_breaker_threshold": 3}  # Open after 3 failures
)

code = '''
try:
    api = await get_resource("unreliable_api")
    # Use API normally
except ResourceNotFoundError as e:
    if "Circuit breaker open" in str(e):
        # Service is down, use fallback
        result = {"error": "Service temporarily unavailable"}
    else:
        raise
'''
```

### 3. Distributed Transaction Pattern

```python
code = '''
# Get database and message queue
db = await get_resource("main_db")
mq = await get_resource("event_queue")

# Distributed transaction
async with db.acquire() as conn:
    async with conn.transaction():
        # 1. Database operation
        await conn.execute(
            "INSERT INTO orders (user_id, total) VALUES ($1, $2)",
            user_id, total_amount
        )
        order_id = await conn.fetchval("SELECT lastval()")

        # 2. Publish event (part of same transaction context)
        channel = await mq.channel()
        await channel.default_exchange.publish(
            aio_pika.Message(
                json.dumps({
                    "event": "order_created",
                    "order_id": order_id,
                    "user_id": user_id
                }).encode()
            ),
            routing_key="orders"
        )

        # Both succeed or both fail
        result = {"order_id": order_id, "event_published": True}
'''
```

## Configuration Management

### Environment-Based Setup

```python
import os
from kailash.resources import ResourceRegistry, DatabasePoolFactory, HttpClientFactory

def create_production_registry():
    """Create registry with production configuration."""
    registry = ResourceRegistry(enable_metrics=True)

    # Database
    registry.register_factory(
        "main_db",
        DatabasePoolFactory(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "5432")),
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            min_size=int(os.environ.get("DB_MIN_CONNECTIONS", "5")),
            max_size=int(os.environ.get("DB_MAX_CONNECTIONS", "20"))
        )
    )

    # API Client
    registry.register_factory(
        "external_api",
        HttpClientFactory(
            base_url=os.environ["API_BASE_URL"],
            timeout=int(os.environ.get("API_TIMEOUT", "30")),
            headers={"Authorization": f"Bearer {os.environ['API_TOKEN']}"}
        )
    )

    return registry

def create_development_registry():
    """Create registry with development configuration."""
    registry = ResourceRegistry(enable_metrics=False)

    # Local database
    registry.register_factory(
        "main_db",
        DatabasePoolFactory(
            host="localhost",
            database="myapp_dev",
            user="postgres",
            password="dev_password"
        )
    )

    return registry

# Use appropriate registry
if os.environ.get("ENVIRONMENT") == "production":
    registry = create_production_registry()
else:
    registry = create_development_registry()
```

## Testing with Resources

### Mock Resources for Testing

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from kailash.resources import ResourceFactory

class MockDatabaseFactory(ResourceFactory):
    """Mock database for testing."""

    def __init__(self):
        self.query_results = {}

    async def create(self):
        mock_db = MagicMock()

        # Mock acquire context manager
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock()
        mock_conn.fetch = AsyncMock()
        mock_conn.execute = AsyncMock()

        # Configure responses
        mock_conn.fetchrow.side_effect = lambda q, *args: self.query_results.get(q)

        mock_db.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_db.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        return mock_db

    def get_config(self):
        return {"type": "mock_database"}

@pytest.mark.asyncio
async def test_user_workflow():
    """Test workflow with mock resources."""
    # Create test registry
    test_registry = ResourceRegistry()

    # Add mock database
    mock_db_factory = MockDatabaseFactory()
    mock_db_factory.query_results["SELECT * FROM users WHERE id = $1"] = {
        "id": 123, "name": "Test User", "email": "test@example.com"
    }

    test_registry.register_factory("main_db", mock_db_factory)

    # Test the workflow
    node = AsyncPythonCodeNode(
        name="test_node",
        code='''
db = await get_resource("main_db")
async with db.acquire() as conn:
    user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", 123)

result = {"user": dict(user) if user else None}
'''
    )

    output = await node.execute_async(resource_registry=test_registry)

    assert output["user"]["name"] == "Test User"
    assert output["user"]["email"] == "test@example.com"
```

## Monitoring and Metrics

### Built-in Metrics

```python
# Enable metrics collection
registry = ResourceRegistry(enable_metrics=True)

# After running workflows
metrics = registry.get_metrics()

for resource_name, stats in metrics["resources"].items():
    print(f"Resource: {resource_name}")
    print(f"  Created: {stats['created']} times")
    print(f"  Accessed: {stats['accessed']} times")
    print(f"  Health failures: {stats['health_failures']}")
    print(f"  Recreations: {stats['recreations']}")
```

### Custom Monitoring

```python
import logging
import time

# Enable detailed logging
logging.getLogger("kailash.resources").setLevel(logging.DEBUG)

# Custom metrics collection
class MonitoredRegistry(ResourceRegistry):
    def __init__(self):
        super().__init__(enable_metrics=True)
        self.custom_metrics = {}

    async def get_resource(self, name: str):
        start_time = time.time()
        try:
            resource = await super().get_resource(name)
            # Record success
            self.custom_metrics[name] = {
                "last_access": time.time(),
                "access_time": time.time() - start_time
            }
            return resource
        except Exception as e:
            # Record failure
            self.custom_metrics[name] = {
                "last_error": str(e),
                "error_time": time.time()
            }
            raise
```

## Troubleshooting

### Common Issues

**1. Resource Not Found:**
```python
# Error: ResourceNotFoundError: No factory registered for resource: my_db
# Solution: Check resource name spelling and ensure it's registered
registry.register_factory("my_db", DatabasePoolFactory(...))  # Correct name
```

**2. Connection Failures:**
```python
# Error: Connection refused / timeout
# Solution: Check network, credentials, and health checks
async def debug_health(resource):
    try:
        # Test the resource manually
        return await resource.ping()
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

registry.register_factory("db", factory, health_check=debug_health)
```

**3. Resource Cleanup:**
```python
# Always cleanup resources when done
try:
    # Use resources
    pass
finally:
    await registry.cleanup()  # Cleanup all resources
```

### Debug Mode

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("kailash.resources")
logger.setLevel(logging.DEBUG)

# This will show:
# - Resource creation and cleanup
# - Health check results
# - Circuit breaker state changes
# - Performance metrics
```

## Best Practices Summary

1. **Register Once, Use Everywhere**: Set up all resources at application startup
2. **Use Connection Pools**: Always configure appropriate pool sizes for databases
3. **Handle Failures Gracefully**: Implement fallback strategies for resource failures
4. **Monitor Health**: Use health checks for critical resources
5. **Clean Up**: Always call `registry.cleanup()` when shutting down
6. **Environment Configuration**: Use environment variables for different deployments
7. **Test with Mocks**: Use mock resources for unit testing
8. **Log Everything**: Enable logging for production monitoring

## Related Documentation

- [AsyncWorkflowBuilder Guide](08-async-workflow-builder.md) - Using resources with async workflows
- [Async Runtime Guide](11-unified-async-runtime-guide.md) - Runtime resource integration
- [Connection Pool Guide](15-connection-pool.md) - Advanced database pooling
- [Error Handling Guide](05-troubleshooting.md) - Handling resource failures

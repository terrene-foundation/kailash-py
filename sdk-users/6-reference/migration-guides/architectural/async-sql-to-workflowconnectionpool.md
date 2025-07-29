# Migration Guide: AsyncSQLDatabaseNode to WorkflowConnectionPool

**Last Updated**: 2025-01-20
**Target Audience**: Developers using AsyncSQLDatabaseNode in production

## Overview

This guide helps you migrate from `AsyncSQLDatabaseNode` to `WorkflowConnectionPool` for improved performance, fault tolerance, and connection management in production environments.

## Why Migrate?

### AsyncSQLDatabaseNode Limitations
- Single connection per node instance
- No automatic connection pooling
- Limited fault tolerance
- No health monitoring
- Manual connection management

### WorkflowConnectionPool Benefits
- **Connection Pooling**: Min/max pool sizes with automatic management
- **Health Monitoring**: Automatic connection health checks and recycling
- **Fault Tolerance**: Actor-based architecture with supervisor recovery
- **Performance**: 40+ queries per connection efficiency
- **Pre-warming**: Pattern-based connection preparation
- **Metrics**: Comprehensive statistics and monitoring

## Migration Decision Matrix

| Current Usage | Should Migrate? | Priority |
|---------------|----------------|----------|
| Production app with >10 concurrent users | ✅ Yes | High |
| Long-running services | ✅ Yes | High |
| Apps with connection limits | ✅ Yes | High |
| Simple data pipelines | ⚠️ Consider | Medium |
| Development/testing | ❌ No | Low |
| One-off scripts | ❌ No | Low |

## Step-by-Step Migration

### Step 1: Identify Current Usage

```python
# Current AsyncSQLDatabaseNode usage (workflow-based)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Single connection approach using workflow
workflow = WorkflowBuilder()
workflow.add_node("AsyncSQLDatabaseNode", "db_node", {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "myapp",
    "user": "postgres",
    "password": "password",
    "query": "SELECT * FROM orders WHERE status = :status",
    "parameters": {"status": "pending"},
    "fetch_mode": "all"
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build())
result = results["db_node"]["result"]
```

### Step 2: Replace with WorkflowConnectionPool

```python
# New WorkflowConnectionPool approach using workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with connection pool
workflow = WorkflowBuilder()
workflow.add_node("WorkflowConnectionPool", "main_pool", {
    "name": "main_pool",
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "myapp",
    "user": "postgres",
    "password": "password",
    "min_connections": 5,
    "max_connections": 20,
    "health_threshold": 70,
    "pre_warm": True,
    "operation": "initialize"
})

# Initialize once at startup
runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build())
```

### Step 3: Update Query Execution Pattern

#### Before (AsyncSQLDatabaseNode with workflow)
```python
# Query execution using workflow
async def get_pending_orders():
    workflow = WorkflowBuilder()
    workflow.add_node("AsyncSQLDatabaseNode", "query_orders", {
        "query": "SELECT * FROM orders WHERE status = :status",
        "parameters": {"status": "pending"},
        "fetch_mode": "all"
    })

    runtime = LocalRuntime()
    results, run_id = await runtime.execute_async(workflow.build())
    return results["query_orders"]["result"]["data"]
```

#### After (WorkflowConnectionPool)
```python
# Connection pool pattern
async def get_pending_orders():
    # Acquire connection
    conn = await pool.process({"operation": "acquire"})
    conn_id = conn["connection_id"]

    try:
        # Execute query
        result = await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "SELECT * FROM orders WHERE status = $1",
            "params": ["pending"],
            "fetch_mode": "all"
        })
        return result["data"]
    finally:
        # Always release connection
        await pool.process({
            "operation": "release",
            "connection_id": conn_id
        })
```

### Step 4: Handle Transactions

```python
async def transfer_funds(from_account, to_account, amount):
    conn = await pool.process({"operation": "acquire"})
    conn_id = conn["connection_id"]

    try:
        # Start transaction
        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "BEGIN",
            "fetch_mode": "one"
        })

        # Debit source account
        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
            "params": [amount, from_account],
            "fetch_mode": "one"
        })

        # Credit destination account
        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
            "params": [amount, to_account],
            "fetch_mode": "one"
        })

        # Commit transaction
        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "COMMIT",
            "fetch_mode": "one"
        })

    except Exception as e:
        # Rollback on error
        await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "ROLLBACK",
            "fetch_mode": "one"
        })
        raise
    finally:
        await pool.process({
            "operation": "release",
            "connection_id": conn_id
        })
```

### Step 5: Monitor Pool Health

```python
# Get pool statistics
async def monitor_pool():
    stats = await pool.process({"operation": "stats"})

    print(f"Pool: {stats['pool_name']}")
    print(f"Active connections: {stats['current_state']['active_connections']}")
    print(f"Available connections: {stats['current_state']['available_connections']}")
    print(f"Total queries: {stats['queries']['executed']}")
    print(f"Error rate: {stats['queries']['error_rate']:.2%}")
    print(f"Pool efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f} queries/connection")

    # Check health scores
    for conn_id, score in stats['current_state']['health_scores'].items():
        if score < 70:
            print(f"Warning: Connection {conn_id} health degraded: {score}")
```

## Common Patterns

### 1. Workflow Integration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with connection pool
workflow = WorkflowBuilder()

# Add pool as a node
workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "name": "order_pool",
    "database_type": "postgresql",
    "host": "localhost",
    "min_connections": 5,
    "max_connections": 20
})

# Initialize pool at workflow start
workflow.add_node("PythonCodeNode", "init_pool", {
    "code": "result = {'operation': 'initialize'}"
})
workflow.add_connection("init_pool", "db_pool", "result", "inputs")

# Use pool in processing
workflow.add_node("PythonCodeNode", "process_orders", {
    "code": """
async def process():
    # Acquire connection
    conn = await workflow.get_node('db_pool').process({'operation': 'acquire'})
    conn_id = conn['connection_id']

    try:
        # Your processing logic here
        pass
    finally:
        await workflow.get_node('db_pool').process({
            'operation': 'release',
            'connection_id': conn_id
        })
"""
})
```

### 2. Error Handling

```python
async def robust_query_execution(query, params=None):
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            conn = await pool.process({"operation": "acquire"})
            conn_id = conn["connection_id"]

            try:
                result = await pool.process({
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": query,
                    "params": params,
                    "fetch_mode": "all"
                })
                return result["data"]
            finally:
                await pool.process({
                    "operation": "release",
                    "connection_id": conn_id
                })

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise
            await asyncio.sleep(0.1 * retry_count)  # Exponential backoff
```

### 3. Context Manager Pattern

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_connection(pool):
    """Context manager for connection acquisition/release."""
    conn = await pool.process({"operation": "acquire"})
    conn_id = conn["connection_id"]

    try:
        yield conn_id
    finally:
        await pool.process({
            "operation": "release",
            "connection_id": conn_id
        })

# Usage
async def get_user(user_id):
    async with get_db_connection(pool) as conn_id:
        result = await pool.process({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "SELECT * FROM users WHERE id = $1",
            "params": [user_id],
            "fetch_mode": "one"
        })
        return result["data"]
```

## Configuration Best Practices

### 1. Pool Sizing

```python
# Calculate pool size based on expected load
# Formula: max_connections = (concurrent_users * queries_per_user) / reuse_factor

# Low traffic app
workflow = WorkflowBuilder()
workflow.add_node("WorkflowConnectionPool", "low_traffic_pool", {
    "name": "low_traffic",
    "min_connections": 2,
    "max_connections": 10
    # ... other config
})

# Medium traffic app
workflow.add_node("WorkflowConnectionPool", "medium_traffic_pool", {
    "name": "medium_traffic",
    "min_connections": 5,
    "max_connections": 25
    # ... other config
})

# High traffic app
workflow.add_node("WorkflowConnectionPool", "high_traffic_pool", {
    "name": "high_traffic",
    "min_connections": 10,
    "max_connections": 50,
    "health_threshold": 60  # More aggressive recycling
    # ... other config
})
```

### 2. Health Monitoring

```python
# Configure health monitoring
workflow.add_node("WorkflowConnectionPool", "monitored_pool", {
    "name": "monitored_pool",
    # ... connection config ...
    "health_threshold": 70,  # Recycle connections below 70% health
    "pre_warm": True       # Pre-warm connections based on patterns
})

# Custom health check query (if needed)
pool.health_check_query = "SELECT 1"  # Lightweight query
pool.health_check_interval = 30.0     # Check every 30 seconds
```

## Performance Comparison

| Metric | AsyncSQLDatabaseNode | WorkflowConnectionPool |
|--------|---------------------|------------------------|
| Concurrent queries | Limited by connection | Up to max_connections |
| Connection overhead | Per query | Amortized |
| Failure recovery | Manual | Automatic |
| Query throughput | ~100/sec | ~1000+/sec |
| Memory usage | Low | Medium (pool overhead) |

## Troubleshooting

### Issue: Connection Pool Exhaustion
```python
# Symptom: Queries hang waiting for connections
# Solution: Increase max_connections or optimize query time

# Monitor pool usage
stats = await pool.process({"operation": "stats"})
if stats["current_state"]["available_connections"] == 0:
    print("Warning: Connection pool exhausted!")
```

### Issue: Connection Health Degradation
```python
# Symptom: Increasing error rates
# Solution: Lower health_threshold for more aggressive recycling

pool.health_threshold = 60  # Recycle at 60% health instead of 70%
```

### Issue: Memory Usage
```python
# Symptom: High memory consumption
# Solution: Reduce max_connections or connection lifetime

pool.max_connections = 20  # Reduce from 50
pool.max_lifetime = 3600  # Recycle connections after 1 hour
```

## Rollback Plan

If you need to rollback to AsyncSQLDatabaseNode:

1. Keep both implementations during transition
2. Use feature flags to switch between them
3. Monitor metrics to compare performance
4. Gradually migrate traffic

```python
# Feature flag approach with workflows
USE_CONNECTION_POOL = os.getenv("USE_CONNECTION_POOL", "false").lower() == "true"

workflow = WorkflowBuilder()

if USE_CONNECTION_POOL:
    # Use WorkflowConnectionPool pattern
    workflow.add_node("WorkflowConnectionPool", "db_pool", {
        "name": "main_pool",
        "database_type": "postgresql",
        "min_connections": 10,
        "max_connections": 50
    })
else:
    # Use AsyncSQLDatabaseNode pattern
    workflow.add_node("AsyncSQLDatabaseNode", "db_node", {
        "database_type": "postgresql",
        "host": "localhost",
        "database": "myapp"
    })
```

## Next Steps

1. Review your current AsyncSQLDatabaseNode usage
2. Identify high-traffic or critical paths
3. Start migration with non-critical workflows
4. Monitor pool statistics and adjust configuration
5. Gradually migrate all database operations
6. Remove AsyncSQLDatabaseNode once stable

## See Also

- [Production-Grade Connection Pool Guide](../developer/connection-pool-guide.md)
- [Performance Patterns](../patterns/06-performance-patterns.md)
- [Production Guide](../developer/04-production.md)

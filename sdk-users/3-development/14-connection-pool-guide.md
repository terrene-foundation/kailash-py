# Production-Grade Connection Pool Guide

*Enterprise database connection management for Kailash SDK*

## Overview

The `WorkflowConnectionPool` provides production-grade database connection management with automatic lifecycle handling, health monitoring, and intelligent optimization. It solves common connection management problems while providing enterprise features like adaptive sizing and query routing.

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Completed [Workflows](02-workflows.md) - Workflow basics
- Understanding of database connections
- Basic knowledge of connection pooling concepts

## Why Use WorkflowConnectionPool?

### Problems with Traditional Connection Management

```python
# ❌ Common problems without proper pooling:

# Problem 1: Connection leaks
def get_user(user_id):
    conn = psycopg2.connect(...)  # Connection created
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()
    # Connection never closed! Resource leak!

# Problem 2: Poor performance
def process_batch(items):
    for item in items:
        conn = psycopg2.connect(...)  # New connection for each item!
        # ... process item
        conn.close()  # Connection overhead for every operation

# Problem 3: No health monitoring
conn = get_connection()
# Connection might be stale, closed, or unhealthy
cursor = conn.cursor()  # Fails unexpectedly!
```

### WorkflowConnectionPool Solutions

```python
# ✅ WorkflowConnectionPool handles everything:

workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "database_type": "postgresql",
    "host": "localhost",
    "min_connections": 5,
    "max_connections": 20,
    "health_check_interval": 30.0
})

# Automatic lifecycle management
# Health monitoring and self-healing
# Optimal performance with connection reuse
# Intelligent routing and optimization
```

## Basic Usage

### Setting Up Connection Pool

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add connection pool
workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "myapp",
    "user": "appuser",
    "password": "secret",
    "min_connections": 2,
    "max_connections": 10
})

# Initialize pool
workflow.add_node("PythonCodeNode", "init", {
    "code": 'result = {"operation": "initialize"}'
})

# Connect initialization
workflow.add_connection("init", "result", "db_pool", "request")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Executing Queries

```python
# Simple query execution
workflow.add_node("PythonCodeNode", "get_users", {
    "code": '''
# Acquire connection
acquire_result = {"operation": "acquire"}

# Execute query
query_result = {
    "operation": "execute",
    "connection_id": None,  # Will be set by pool
    "query": "SELECT id, name, email FROM users WHERE active = %s",
    "params": (True,),
    "fetch_mode": "all"
}

# Release connection
release_result = {
    "operation": "release",
    "connection_id": None  # Will be set by pool
}

# Return all operations
result = {
    "steps": [acquire_result, query_result, release_result]
}
'''
})

# Connect to pool
workflow.add_connection("get_users", "result", "db_pool", "request")
```

## Connection Pool Operations

### 1. Initialize

```python
# Initialize the pool
init_request = {"operation": "initialize"}

# Response:
{
    "status": "initialized",
    "pool_size": 5,
    "min_connections": 2,
    "max_connections": 10
}
```

### 2. Acquire Connection

```python
# Get a connection from pool
acquire_request = {"operation": "acquire"}

# Response:
{
    "connection_id": "conn_abc123",
    "acquired_at": "2024-01-01T10:00:00Z",
    "health_score": 95.0
}
```

### 3. Execute Query

```python
# Execute a query
execute_request = {
    "operation": "execute",
    "connection_id": "conn_abc123",
    "query": "SELECT * FROM products WHERE price > %s",
    "params": (100,),
    "fetch_mode": "all"  # Options: "all", "one", "many"
}

# Response:
{
    "result": [
        {"id": 1, "name": "Product A", "price": 150},
        {"id": 2, "name": "Product B", "price": 200}
    ],
    "row_count": 2,
    "execution_time_ms": 12.5
}
```

### 4. Release Connection

```python
# Return connection to pool
release_request = {
    "operation": "release",
    "connection_id": "conn_abc123"
}

# Response:
{
    "status": "released",
    "connection_id": "conn_abc123",
    "usage_duration_ms": 150
}
```

### 5. Get Statistics

```python
# Get pool statistics
stats_request = {"operation": "stats"}

# Response:
{
    "current_state": {
        "total_connections": 5,
        "active_connections": 2,
        "available_connections": 3,
        "health_scores": {
            "conn_abc123": 95.0,
            "conn_def456": 88.0
        }
    },
    "performance": {
        "avg_acquisition_time_ms": 1.2,
        "p99_acquisition_time_ms": 5.8,
        "total_queries_executed": 1523,
        "avg_query_time_ms": 15.3
    }
}
```

## Common Patterns

### Transaction Handling

```python
workflow.add_node("PythonCodeNode", "transfer_funds", {
    "code": '''
# Transaction steps
steps = [
    {"operation": "acquire"},
    {"operation": "execute", "query": "BEGIN"},
    {
        "operation": "execute",
        "query": "UPDATE accounts SET balance = balance - %s WHERE id = %s",
        "params": (amount, from_account)
    },
    {
        "operation": "execute",
        "query": "UPDATE accounts SET balance = balance + %s WHERE id = %s",
        "params": (amount, to_account)
    },
    {"operation": "execute", "query": "COMMIT"},
    {"operation": "release"}
]

# Handle rollback on error
try:
    result = {"steps": steps}
except Exception as e:
    # Add rollback step
    steps.append({"operation": "execute", "query": "ROLLBACK"})
    steps.append({"operation": "release"})
    raise

result = {"steps": steps}
'''
})
```

### Batch Operations

```python
workflow.add_node("PythonCodeNode", "batch_insert", {
    "code": '''
# Prepare batch operations
steps = [{"operation": "acquire"}]

# Add batch inserts
for record in records:
    steps.append({
        "operation": "execute",
        "query": """
            INSERT INTO events (user_id, event_type, data, created_at)
            VALUES (%s, %s, %s, NOW())
        """,
        "params": (
            record["user_id"],
            record["event_type"],
            json.dumps(record["data"])
        )
    })

# Release connection
steps.append({"operation": "release"})

result = {"steps": steps}
'''
})
```

### Concurrent Queries

```python
# Execute multiple queries in parallel
workflow.add_node("PythonCodeNode", "analytics", {
    "code": '''
# Define queries to run in parallel
queries = [
    {
        "name": "total_users",
        "query": "SELECT COUNT(*) as count FROM users"
    },
    {
        "name": "active_sessions",
        "query": "SELECT COUNT(*) as count FROM sessions WHERE active = true"
    },
    {
        "name": "daily_revenue",
        "query": "SELECT SUM(amount) as total FROM orders WHERE date = CURRENT_DATE"
    }
]

# Each query gets its own connection
results = {}
for query_info in queries:
    steps = [
        {"operation": "acquire"},
        {
            "operation": "execute",
            "query": query_info["query"],
            "fetch_mode": "one"
        },
        {"operation": "release"}
    ]
    # Store steps for parallel execution
    results[query_info["name"]] = {"steps": steps}

result = results
'''
})
```

## Advanced Features

### Health Monitoring

The pool continuously monitors connection health:

```python
# Configure health monitoring
workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "database_type": "postgresql",
    "host": "localhost",
    "health_check_interval": 30.0,  # Check every 30 seconds
    "health_check_query": "SELECT 1",  # Simple health check
    "health_threshold": 50  # Min health score (0-100)
})

# Health scores are calculated based on:
# - Query success rate
# - Response times
# - Connection age
# - Error frequency
```

### Adaptive Pool Sizing

Enable dynamic pool sizing based on workload:

```python
workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "database_type": "postgresql",
    "host": "localhost",
    "min_connections": 2,
    "max_connections": 20,
    "adaptive_sizing": True,  # Enable adaptive sizing
    "adaptation_interval": 60.0  # Adjust every 60 seconds
})

# Pool automatically adjusts size based on:
# - Current workload
# - Historical patterns
# - Query wait times
# - Resource availability
```

### Connection Lifecycle

Connections are automatically managed:

```python
workflow.add_node("WorkflowConnectionPool", "db_pool", {
    "database_type": "postgresql",
    "host": "localhost",
    "max_lifetime": 3600.0,  # Recycle after 1 hour
    "max_idle_time": 600.0,  # Recycle if idle for 10 minutes
    "recycle_on_error": True  # Recycle on connection errors
})

# Connections are recycled when:
# - Health score drops below threshold
# - Connection exceeds max lifetime
# - Connection has been idle too long
# - Errors indicate connection problems
```

## Configuration Reference

### Full Configuration Options

```python
WorkflowConnectionPool(
    # Database Configuration
    database_type="postgresql",      # postgresql, mysql, sqlite
    connection_string=None,          # Alternative to individual params
    host="localhost",
    port=5432,
    database="myapp",
    user="dbuser",
    password="dbpass",

    # Pool Settings
    min_connections=2,               # Minimum pool size
    max_connections=10,              # Maximum pool size
    connection_timeout=30.0,         # Timeout for acquiring connection

    # Health Monitoring
    health_check_interval=30.0,      # Seconds between health checks
    health_check_query="SELECT 1",   # Query for health check
    health_threshold=50,             # Minimum health score (0-100)

    # Connection Lifecycle
    max_lifetime=3600.0,             # Max connection age (seconds)
    max_idle_time=600.0,             # Max idle time (seconds)
    recycle_on_error=True,           # Recycle on errors

    # Advanced Features
    adaptive_sizing=False,           # Enable dynamic sizing
    enable_query_routing=False,      # Enable read/write splitting
    pre_warm=True,                   # Pre-warm connections

    # Database Specific
    pool_size=None,                  # Override for specific databases
    pool_recycle=None,               # MySQL-specific recycle time
)
```

## Best Practices

### 1. Always Release Connections

```python
# ✅ Good - Always release
steps = [
    {"operation": "acquire"},
    {"operation": "execute", "query": "..."},
    {"operation": "release"}  # Always include!
]

# ❌ Bad - Connection leak
steps = [
    {"operation": "acquire"},
    {"operation": "execute", "query": "..."}
    # Missing release!
]
```

### 2. Use Transactions for Multiple Updates

```python
# ✅ Good - Atomic transaction
steps = [
    {"operation": "acquire"},
    {"operation": "execute", "query": "BEGIN"},
    # Multiple updates...
    {"operation": "execute", "query": "COMMIT"},
    {"operation": "release"}
]

# ❌ Bad - Non-atomic updates
# Each update in separate connection
```

### 3. Monitor Pool Health

```python
# Regularly check pool statistics
workflow.add_node("PythonCodeNode", "monitor", {
    "code": '''
stats = {"operation": "stats"}
result = stats

# Check for issues
if stats["current_state"]["available_connections"] == 0:
    # Pool exhausted - investigate!
    pass
'''
})
```

### 4. Configure for Your Workload

```python
# High-traffic application
high_traffic_config = {
    "min_connections": 10,
    "max_connections": 50,
    "adaptive_sizing": True
}

# Low-traffic application
low_traffic_config = {
    "min_connections": 1,
    "max_connections": 5,
    "max_idle_time": 300.0  # Recycle idle connections faster
}
```

## Troubleshooting

### Connection Pool Exhausted

```python
# Problem: "No available connections"
# Solution: Increase max_connections or check for leaks

# Check current state
stats_request = {"operation": "stats"}
# Look for active_connections == max_connections
```

### Slow Query Performance

```python
# Problem: Queries taking too long
# Solution: Check health scores and connection age

# Low health scores indicate connection issues
# Old connections might need recycling
```

### Connection Errors

```python
# Problem: "Connection refused" or timeout errors
# Solution: Verify database is accessible

# Test with simple connection
import psycopg2
conn = psycopg2.connect(
    host="localhost",
    database="myapp",
    user="dbuser",
    password="dbpass"
)
```

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Workflow basics

**Advanced Topics:**
- [Resource Registry](08-resource-registry-guide.md) - Resource management
- [Production](04-production.md) - Production deployment

---

**Manage database connections efficiently with WorkflowConnectionPool for reliable, high-performance applications!**

# Production-Grade Connection Pool Guide

## Introduction

Managing database connections efficiently is crucial for application performance and reliability. The Kailash SDK provides a production-grade connection pool that handles the complexities of connection lifecycle, health monitoring, and resource optimization automatically.

**Phase 2 Enhancement**: Now includes intelligent query routing, adaptive pool sizing, and pattern learning for self-optimizing database operations. See the [Query Routing Guide](./17-intelligent-query-routing.md) for advanced features.

**Phase 3 Enhancement**: Adds production-grade connection management with circuit breaker protection, comprehensive metrics collection, query pipelining for high throughput, and real-time monitoring dashboards.

## Why Use WorkflowConnectionPool?

Traditional connection management often leads to:
- ❌ Connection leaks that exhaust database resources
- ❌ Poor performance due to connection creation overhead
- ❌ Failed queries on stale connections
- ❌ Manual connection validation and recycling
- ❌ Difficult debugging of connection issues

WorkflowConnectionPool solves these with:
- ✅ Automatic lifecycle management tied to workflows
- ✅ Connection pre-warming for optimal performance
- ✅ Continuous health monitoring and self-healing
- ✅ Built-in metrics and observability
- ✅ Intelligent connection recycling
- ✅ **NEW**: Adaptive pool sizing based on workload
- ✅ **NEW**: Query routing for read/write splitting
- ✅ **NEW**: Pattern learning for predictive optimization
- ✅ **Phase 3**: Circuit breaker protection against failures
- ✅ **Phase 3**: Comprehensive metrics with Prometheus export
- ✅ **Phase 3**: Query pipelining for batch performance
- ✅ **Phase 3**: Real-time monitoring dashboards

## Overview

The `WorkflowConnectionPool` node provides enterprise-grade database connection management with features inspired by modern distributed systems. Unlike traditional thread-based connection pools, this implementation uses an actor-based model for better isolation, fault tolerance, and scalability.

## Key Features

- **Workflow-Scoped Lifecycle**: Connections are tied to workflow execution, preventing resource leaks
- **Actor-Based Isolation**: Each connection runs as an independent actor with message passing
- **Health Monitoring**: Continuous health checks with predictive maintenance
- **Intelligent Routing**: Query-aware connection selection and optimization
- **Pattern-Based Pre-warming**: Learns from workflow patterns to optimize startup
- **Comprehensive Metrics**: Detailed monitoring and performance tracking

## Getting Started

### Basic Database Operations

Here's how to perform common database operations:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime

# Create a workflow for database operations
workflow = WorkflowBuilder()

# Add the connection pool
workflow.add_node("db", "WorkflowConnectionPool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    user="appuser",
    password="secret"
)

# Initialize the pool
workflow.add_node("setup", "PythonCodeNode",
    code='return {"operation": "initialize"}'
)

# Get a user by ID
workflow.add_node("get_user", "PythonCodeNode", code="""
    # First acquire a connection
    conn_request = {"operation": "acquire"}
    # Connection ID will be provided by the pool

    # Then execute query
    query_request = {
        "operation": "execute",
        "connection_id": None,  # Will be set by pool
        "query": "SELECT * FROM users WHERE id = %s",
        "params": (user_id,),
        "fetch_mode": "one"
    }

    # Finally release the connection
    release_request = {
        "operation": "release",
        "connection_id": None  # Will be set by pool
    }

    return {
        "acquire": conn_request,
        "query": query_request,
        "release": release_request
    }
""")

# Connect the nodes
workflow.add_connection("setup", "result", "db", "input")
workflow.add_connection("db", "result", "get_user", "input")

# Execute
runtime = LocalRuntime()
result = runtime.execute(workflow, parameters={"user_id": 123})
```

### Common Patterns

#### 1. Simple Query Execution

```python
# Single query pattern
workflow.add_node("simple_query", "PythonCodeNode", code="""
    steps = [
        {"operation": "acquire"},
        {
            "operation": "execute",
            "query": "SELECT COUNT(*) as total FROM orders",
            "fetch_mode": "one"
        },
        {"operation": "release"}
    ]
    return {"steps": steps}
""")
```

#### 2. Transaction Handling

```python
# Transaction pattern
workflow.add_node("transfer_funds", "PythonCodeNode", code="""
    steps = [
        {"operation": "acquire"},
        {
            "operation": "execute",
            "query": "BEGIN"
        },
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
        {
            "operation": "execute",
            "query": "COMMIT"
        },
        {"operation": "release"}
    ]
    return {"steps": steps}
""")
```

#### 3. Batch Operations

```python
# Batch insert pattern
workflow.add_node("batch_insert", "PythonCodeNode", code="""
    steps = [{"operation": "acquire"}]

    # Add multiple insert operations
    for record in records:
        steps.append({
            "operation": "execute",
            "query": "INSERT INTO events (type, data, created_at) VALUES (%s, %s, NOW())",
            "params": (record["type"], json.dumps(record["data"]))
        })

    steps.append({"operation": "release"})
    return {"steps": steps}
""")
```

## Quick Start

### Basic Usage

```python
from kailash.workflow import Workflow
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

# Create workflow
workflow = WorkflowBuilder()

# Add connection pool
workflow.add_node("db_pool", WorkflowConnectionPool(),
    database_type="postgresql",
    host="localhost",
    database="myapp",
    user="dbuser",
    password="dbpass",
    min_connections=2,
    max_connections=10
)

# Initialize pool
workflow.add_node("init", "PythonCodeNode",
    code='return {"operation": "initialize"}'
)

# Acquire connection
workflow.add_node("get_conn", "PythonCodeNode",
    code='return {"operation": "acquire"}'
)

# Execute query
workflow.add_node("query", "PythonCodeNode", code="""
    return {
        "operation": "execute",
        "connection_id": inputs["connection_id"],
        "query": "SELECT * FROM users WHERE active = true",
        "fetch_mode": "all"
    }
""")

# Connect nodes
workflow.add_connection("init", "result", "db_pool", "input")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
workflow.add_connection("get_conn", "result", "db_pool", "input")
workflow.add_connection("db_pool", "query", "query")
workflow.add_connection("query", "result", "db_pool", "input")
```

### Connection Pool Operations

The pool supports these operations:

1. **initialize**: Set up the connection pool
2. **acquire**: Get a connection from the pool
3. **release**: Return a connection to the pool
4. **execute**: Run a query on a connection
5. **stats**: Get pool statistics

## Configuration

### Pool Parameters

```python
WorkflowConnectionPool(
    # Database Configuration
    database_type="postgresql",      # postgresql, mysql, sqlite
    connection_string=None,          # Full connection string (optional)
    host="localhost",
    port=5432,
    database="myapp",
    user="dbuser",
    password="dbpass",

    # Pool Settings
    min_connections=2,              # Minimum connections to maintain
    max_connections=10,             # Maximum connections allowed
    health_threshold=50,            # Min health score (0-100)
    pre_warm=True,                  # Enable pattern-based pre-warming

    # Phase 2 Features (NEW)
    adaptive_sizing=False,          # Enable dynamic pool sizing
    enable_query_routing=False,     # Enable pattern tracking for routing

    # Health Monitoring
    health_check_interval=30.0,     # Seconds between health checks
    health_check_query="SELECT 1",  # Query for health checks

    # Connection Lifecycle
    max_lifetime=3600.0,            # Max connection age (seconds)
    max_idle_time=600.0,            # Max idle before recycling
)
```

### Database-Specific Configuration

#### PostgreSQL
```python
config = {
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "myapp",
    "user": "postgres",
    "password": "secret",
    # PostgreSQL supports native pooling
    "pool_size": 10,
    "max_pool_size": 20
}
```

#### MySQL
```python
config = {
    "database_type": "mysql",
    "host": "localhost",
    "port": 3306,
    "database": "myapp",
    "user": "root",
    "password": "secret",
    # MySQL specific
    "pool_recycle": 3600  # Recycle connections after 1 hour
}
```

#### SQLite
```python
config = {
    "database_type": "sqlite",
    "database": "/path/to/database.db",
    # SQLite doesn't have true pooling
    # But we still manage connection lifecycle
}
```

## Advanced Features

### 1. Health Monitoring

The pool continuously monitors connection health:

```python
# Get pool statistics including health
stats = await pool.process({"operation": "stats"})

# Example output:
{
    "current_state": {
        "total_connections": 5,
        "active_connections": 2,
        "available_connections": 3,
        "health_scores": {
            "conn_abc123": 85.0,
            "conn_def456": 92.0,
            ...
        }
    },
    "performance": {
        "avg_acquisition_time_ms": 1.2,
        "p99_acquisition_time_ms": 5.8
    }
}
```

### 2. Workflow Integration

The pool integrates with workflow lifecycle:

```python
# Pool automatically pre-warms based on workflow type
await pool.on_workflow_start("wf_123", "data_processing")

# Automatic cleanup when workflow completes
await pool.on_workflow_complete("wf_123")
```

### 3. Connection Recycling

Connections are automatically recycled when:
- Health score drops below threshold
- Connection exceeds max lifetime
- Connection has been idle too long
- Errors indicate connection problems

### 4. Concurrent Query Execution

```python
# Execute multiple queries in parallel
async def run_analytics(pool):
    # Acquire multiple connections
    tasks = []

    for query in analytics_queries:
        task = asyncio.create_task(
            execute_query(pool, query)
        )
        tasks.append(task)

    # Wait for all queries
    results = await asyncio.gather(*tasks)
    return results

async def execute_query(pool, query):
    # Acquire connection
    conn = await pool.process({"operation": "acquire"})

    try:
        # Execute query
        result = await pool.process({
            "operation": "execute",
            "connection_id": conn["connection_id"],
            "query": query
        })
        return result
    finally:
        # Always release
        await pool.process({
            "operation": "release",
            "connection_id": conn["connection_id"]
        })
```

## Performance Optimization

### 1. Connection Pool Sizing

```python
# Formula for pool sizing
# min_connections = baseline concurrent queries
# max_connections = peak concurrent queries + 20% buffer

# Example for API service
estimated_rps = 100  # Requests per second
avg_query_time = 0.05  # 50ms average query time
concurrent_queries = estimated_rps * avg_query_time  # 5

config = {
    "min_connections": 5,
    "max_connections": 10,  # 2x min for burst capacity
    "health_check_interval": 30.0
}
```

### 2. Query Optimization Tips

```python
# Use connection pooling stats to identify slow queries
workflow.add_node("monitor_performance", "PythonCodeNode", code="""
    # Get pool statistics
    stats = {"operation": "stats"}

    # Identify issues
    warnings = []

    if stats["performance"]["avg_acquisition_time_ms"] > 10:
        warnings.append("Connection acquisition is slow - consider increasing pool size")

    if stats["queries"]["error_rate"] > 0.01:
        warnings.append("High error rate - check query syntax and database health")

    if stats["connections"]["recycled"] > stats["connections"]["created"] * 0.5:
        warnings.append("High recycling rate - connections may be unhealthy")

    return {"warnings": warnings, "stats": stats}
""")
```

### 3. Concurrent Query Execution

```python
# Pattern for concurrent queries
workflow.add_node("concurrent_reports", "PythonCodeNode", code="""
    import asyncio

    # Define report queries
    reports = [
        {"name": "sales_report", "query": "SELECT ... FROM sales ..."},
        {"name": "inventory_report", "query": "SELECT ... FROM inventory ..."},
        {"name": "customer_report", "query": "SELECT ... FROM customers ..."}
    ]

    # Execute concurrently
    async def run_report(report):
        # Each gets its own connection
        conn = await acquire_connection()
        try:
            result = await execute_query(conn, report["query"])
            return {"name": report["name"], "data": result}
        finally:
            await release_connection(conn)

    # Run all reports in parallel
    tasks = [run_report(r) for r in reports]
    results = await asyncio.gather(*tasks)

    return {"reports": results}
""")
```

### 4. Connection Pre-warming

The pool learns from workflow patterns:

```python
# First run: Pool starts with min_connections
# Pool observes that workflow uses 5 connections

# Next run: Pool pre-warms 5 connections at start
# This eliminates connection creation latency
```

## Phase 2: Intelligent Features

### 1. Query Router Integration

For advanced query optimization, use the QueryRouterNode:

```python
from kailash.nodes.data.query_router import QueryRouterNode

# Create pool with Phase 2 features
pool = WorkflowConnectionPool(
    name="smart_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=50,
    adaptive_sizing=True,          # Enable dynamic sizing
    enable_query_routing=True      # Enable pattern tracking
)

# Add query router for intelligent routing
router = QueryRouterNode(
    name="query_router",
    connection_pool="smart_pool",
    enable_read_write_split=True,  # Route reads to any connection
    cache_size=1000,               # Cache prepared statements
    pattern_learning=True          # Learn from patterns
)

# Use router instead of direct pool access
result = await router.process({
    "query": "SELECT * FROM users WHERE active = ?",
    "parameters": [True]
})
# No manual connection management needed!
```

### 2. Adaptive Pool Sizing

Enable automatic scaling based on workload:

```python
pool = WorkflowConnectionPool(
    name="adaptive_pool",
    min_connections=3,      # Start small
    max_connections=50,     # Allow scaling up
    adaptive_sizing=True    # Enable auto-scaling
)

# Pool automatically adjusts based on:
# - Current utilization rate
# - Query arrival rate
# - Response times
# - System resources
```

### 3. Pattern Learning

The pool can learn from your workload patterns:

```python
# With pattern tracking enabled
pool = WorkflowConnectionPool(
    enable_query_routing=True  # Enables pattern tracking
)

# After running for a while, get insights
if pool.query_pattern_tracker:
    patterns = pool.query_pattern_tracker.get_frequent_patterns()
    forecast = pool.query_pattern_tracker.get_workload_forecast()

    print(f"Peak hours: {forecast['peak_hours']}")
    print(f"Recommended pool size: {forecast['recommended_pool_size']}")
```

### 4. Performance Benefits

Phase 2 features provide:
- **30-50% reduction** in query latency through caching
- **70-80% connection utilization** through adaptive sizing
- **Zero connection exhaustion** with predictive scaling
- **Automatic read/write splitting** for better throughput

### 3. Monitoring Best Practices

```python
# Regular monitoring
async def monitor_pool_health(pool):
    while True:
        stats = await pool.process({"operation": "stats"})

        # Check key metrics
        if stats["performance"]["avg_acquisition_time_ms"] > 10:
            logger.warning("High connection acquisition time")

        if stats["current_state"]["active_connections"] == stats["max_connections"]:
            logger.warning("Connection pool at capacity")

        await asyncio.sleep(30)
```

## Error Handling

### Connection Failures

```python
try:
    result = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": "SELECT * FROM users"
    })
except NodeExecutionError as e:
    if "Connection in FAILED state" in str(e):
        # Connection failed, pool will recycle it
        # Retry with new connection
        new_conn = await pool.process({"operation": "acquire"})
        result = await retry_query(new_conn)
```

### Pool Exhaustion

```python
# Set timeout for acquisition
async def acquire_with_timeout(pool, timeout=5.0):
    try:
        return await asyncio.wait_for(
            pool.process({"operation": "acquire"}),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise Exception("Connection pool exhausted")
```

## Best Practices

### 1. Always Release Connections

```python
# Good: Use try/finally
conn = await pool.process({"operation": "acquire"})
try:
    result = await pool.process({
        "operation": "execute",
        "connection_id": conn["connection_id"],
        "query": query
    })
finally:
    await pool.process({
        "operation": "release",
        "connection_id": conn["connection_id"]
    })

# Better: Create a context manager
@asynccontextmanager
async def get_connection(pool):
    conn = await pool.process({"operation": "acquire"})
    try:
        yield conn["connection_id"]
    finally:
        await pool.process({
            "operation": "release",
            "connection_id": conn["connection_id"]
        })

# Usage
async with get_connection(pool) as conn_id:
    result = await pool.process({
        "operation": "execute",
        "connection_id": conn_id,
        "query": "SELECT * FROM users"
    })
```

### 2. Size Pool Appropriately

```python
# Formula: max_connections = expected_concurrent_queries + buffer
# Example: API with 50 concurrent requests, 20% buffer
max_connections = 50 * 1.2  # 60 connections

# But consider database limits
# PostgreSQL default max_connections = 100
# Leave room for other applications
```

### 3. Monitor Pool Health

```python
# Add monitoring node to workflow
workflow.add_node("monitor", "PythonCodeNode", code="""
    stats = inputs["stats"]

    # Alert on issues
    if stats["connections"]["failed"] > 5:
        alert("High connection failure rate")

    if stats["performance"]["p99_acquisition_time_ms"] > 100:
        alert("Slow connection acquisition")

    return {"monitoring_complete": True}
""")
```

## Troubleshooting

### Common Issues and Solutions

#### 1. "Connection pool exhausted"

**Symptoms**: Timeouts when acquiring connections

**Solutions**:
```python
# Increase pool size
config = {
    "max_connections": 20  # Increase from default
}

# Or reduce connection hold time
# Ensure queries are optimized and connections released quickly
```

#### 2. "Connection health degraded"

**Symptoms**: Connections being recycled frequently

**Solutions**:
```python
# Adjust health check settings
config = {
    "health_threshold": 40,  # Lower threshold (default 50)
    "health_check_interval": 60.0,  # Less frequent checks
    "health_check_query": "SELECT 1"  # Ensure query is lightweight
}
```

#### 3. High latency

**Symptoms**: Slow query execution

**Solutions**:
```python
# Enable connection pre-warming
config = {
    "pre_warm": True,
    "min_connections": 5  # Pre-create connections
}

# Add query timeouts
query_config = {
    "operation": "execute",
    "query": "SELECT ...",
    "timeout": 5.0  # 5 second timeout
}
```

### Monitoring Checklist

Regular monitoring ensures optimal performance:

- [ ] Check average acquisition time (target: <5ms)
- [ ] Monitor connection health scores (target: >80)
- [ ] Track query error rates (target: <1%)
- [ ] Review connection recycling rate (target: <10%)
- [ ] Verify pool utilization (target: 50-80%)

## Troubleshooting

### Common Issues

1. **"Connection pool exhausted"**
   - Increase `max_connections`
   - Check for connection leaks (not releasing)
   - Review query execution time

2. **"Connection in FAILED state"**
   - Check database connectivity
   - Review health check query
   - Check database logs

3. **High acquisition time**
   - Pool may be undersized
   - Long-running queries holding connections
   - Network latency issues

### Debug Mode

```python
# Enable debug logging
import logging
logging.getLogger("kailash.nodes.data.workflow_connection_pool").setLevel(logging.DEBUG)

# This will show:
# - Connection lifecycle events
# - Health check results
# - Pool statistics
# - Recycling decisions
```

## Migration from Traditional Pools

### From Django/SQLAlchemy

```python
# Old Django approach
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT * FROM users")

# New Kailash approach
pool = WorkflowConnectionPool(**config)
conn = await pool.process({"operation": "acquire"})
result = await pool.process({
    "operation": "execute",
    "connection_id": conn["connection_id"],
    "query": "SELECT * FROM users"
})
```

### Benefits of Migration

1. **Better isolation**: Actor model prevents connection corruption
2. **Automatic health management**: No manual connection validation
3. **Workflow integration**: Automatic cleanup and lifecycle
4. **Superior monitoring**: Built-in metrics and health tracking

## Future Enhancements

Coming in future versions:

1. **Query Router Node**: Automatic read/write splitting
2. **Cache Integration**: Query result caching
3. **Prepared Statements**: Automatic statement preparation
4. **Multi-Region Support**: Geographic query routing
5. **AI-Powered Optimization**: ML-based pool sizing

## Real-World Scenarios

### Scenario 1: E-Commerce Order Processing

```python
# E-commerce workflow with connection pooling
ecommerce_workflow = WorkflowBuilder()

# Connection pool for order database
ecommerce_workflow.add_node("order_db", "WorkflowConnectionPool",
    database_type="postgresql",
    host="orders.db.internal",
    database="orders",
    user="order_service",
    password=os.environ["ORDER_DB_PASSWORD"],
    min_connections=5,
    max_connections=20
)

# Process new order
ecommerce_workflow.add_node("process_order", "PythonCodeNode", code="""
    order_data = inputs["order"]

    # Validate inventory
    inventory_check = {
        "operation": "execute",
        "query": '''
            SELECT product_id, available_quantity
            FROM inventory
            WHERE product_id = ANY(%s)
            FOR UPDATE
        ''',
        "params": (order_data["product_ids"],)
    }

    # Create order record
    create_order = {
        "operation": "execute",
        "query": '''
            INSERT INTO orders (customer_id, total_amount, status, items)
            VALUES (%s, %s, 'pending', %s)
            RETURNING id, created_at
        ''',
        "params": (
            order_data["customer_id"],
            order_data["total_amount"],
            json.dumps(order_data["items"])
        )
    }

    # Update inventory
    update_inventory = {
        "operation": "execute",
        "query": '''
            UPDATE inventory
            SET available_quantity = available_quantity - %s
            WHERE product_id = %s
        ''',
        "params": []  # Will be filled per item
    }

    return {
        "inventory_check": inventory_check,
        "create_order": create_order,
        "update_inventory": update_inventory
    }
""")
```

### Scenario 2: Real-Time Analytics Dashboard

```python
# Analytics workflow with concurrent queries
analytics_workflow = WorkflowBuilder()

# Pool optimized for read-heavy workload
analytics_workflow.add_node("analytics_db", "WorkflowConnectionPool",
    database_type="postgresql",
    host="analytics.db.internal",
    database="analytics",
    user="analytics_reader",
    password=os.environ["ANALYTICS_DB_PASSWORD"],
    min_connections=10,
    max_connections=30,
    health_check_interval=15.0  # More frequent checks for critical dashboard
)

# Dashboard queries
analytics_workflow.add_node("dashboard_metrics", "PythonCodeNode", code="""
    # Define multiple analytics queries
    queries = {
        "active_users": {
            "operation": "execute",
            "query": '''
                SELECT COUNT(DISTINCT user_id) as count
                FROM user_activity
                WHERE timestamp > NOW() - INTERVAL '5 minutes'
            ''',
            "fetch_mode": "one"
        },
        "revenue_today": {
            "operation": "execute",
            "query": '''
                SELECT SUM(amount) as total
                FROM transactions
                WHERE created_at >= CURRENT_DATE
                AND status = 'completed'
            ''',
            "fetch_mode": "one"
        },
        "top_products": {
            "operation": "execute",
            "query": '''
                SELECT product_name, SUM(quantity) as units_sold
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.created_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY product_name
                ORDER BY units_sold DESC
                LIMIT 10
            ''',
            "fetch_mode": "all"
        },
        "error_rate": {
            "operation": "execute",
            "query": '''
                SELECT
                    COUNT(CASE WHEN status = 'error' THEN 1 END)::float /
                    COUNT(*)::float as error_rate
                FROM api_requests
                WHERE timestamp > NOW() - INTERVAL '1 hour'
            ''',
            "fetch_mode": "one"
        }
    }

    return {"queries": queries}
""")
```

### Scenario 3: Data Migration with Progress Tracking

```python
# Data migration workflow
migration_workflow = WorkflowBuilder()

# Source database pool
migration_workflow.add_node("source_db", "WorkflowConnectionPool",
    database_type="mysql",
    host="legacy.db.internal",
    database="legacy_app",
    user="migrator",
    password=os.environ["LEGACY_DB_PASSWORD"],
    min_connections=5,
    max_connections=10
)

# Target database pool
migration_workflow.add_node("target_db", "WorkflowConnectionPool",
    database_type="postgresql",
    host="new.db.internal",
    database="modern_app",
    user="migrator",
    password=os.environ["NEW_DB_PASSWORD"],
    min_connections=5,
    max_connections=15
)

# Migration logic
migration_workflow.add_node("migrate_users", "PythonCodeNode", code="""
    batch_size = 1000
    offset = 0
    migrated_count = 0

    migration_steps = []

    while True:
        # Read batch from source
        read_batch = {
            "operation": "execute",
            "query": f'''
                SELECT id, email, name, created_at, metadata
                FROM users
                ORDER BY id
                LIMIT {batch_size} OFFSET {offset}
            ''',
            "fetch_mode": "all",
            "target": "source"
        }

        # Transform and write to target
        write_batch = {
            "operation": "execute",
            "query": '''
                INSERT INTO users (legacy_id, email, full_name, created_at, attributes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (legacy_id) DO UPDATE
                SET email = EXCLUDED.email,
                    full_name = EXCLUDED.full_name,
                    attributes = EXCLUDED.attributes,
                    updated_at = NOW()
            ''',
            "params": [],  # Will be filled with transformed data
            "target": "target"
        }

        migration_steps.append({
            "read": read_batch,
            "write": write_batch,
            "offset": offset
        })

        offset += batch_size

        # Check if we've processed all records
        if len(batch_data) < batch_size:
            break

    return {"migration_plan": migration_steps}
""")
```

## Complete Example

Here's a production-ready example:

```python
from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

async def create_analytics_workflow():
    workflow = WorkflowBuilder()

    # Configure pool for production
    workflow.add_node("db_pool", WorkflowConnectionPool(),
        database_type="postgresql",
        host="db.production.internal",
        database="analytics",
        user="analytics_user",
        password=os.environ["DB_PASSWORD"],
        min_connections=5,
        max_connections=20,
        health_threshold=60,
        pre_warm=True
    )

    # Initialize with monitoring
    workflow.add_node("init", "PythonCodeNode", code="""
        import logging
        logger = logging.getLogger("analytics")

        result = {"operation": "initialize"}
        logger.info("Initializing connection pool")

        return result
    """)

    # Complex analytics query
    workflow.add_node("analytics", "PythonCodeNode", code="""
        queries = [
            {
                "name": "daily_metrics",
                "query": '''
                    WITH daily_stats AS (
                        SELECT DATE(created_at) as date,
                               COUNT(*) as transactions,
                               SUM(amount) as revenue
                        FROM orders
                        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                        GROUP BY DATE(created_at)
                    )
                    SELECT * FROM daily_stats ORDER BY date DESC
                '''
            },
            {
                "name": "user_cohorts",
                "query": '''
                    SELECT DATE_TRUNC('month', created_at) as cohort,
                           COUNT(DISTINCT user_id) as users,
                           AVG(lifetime_value) as avg_ltv
                    FROM users
                    GROUP BY cohort
                    ORDER BY cohort DESC
                    LIMIT 12
                '''
            }
        ]

        return {"queries": queries}
    """)

    # Execute with error handling
    workflow.add_node("execute_safe", "PythonCodeNode", code="""
        results = {}

        for query_info in inputs["queries"]:
            conn = None
            try:
                # Acquire connection
                conn_result = {"operation": "acquire"}
                conn_id = None  # Will be set by pool

                # Execute query
                exec_result = {
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": query_info["query"],
                    "fetch_mode": "all"
                }

                results[query_info["name"]] = {
                    "success": True,
                    "data": exec_result
                }

            except Exception as e:
                results[query_info["name"]] = {
                    "success": False,
                    "error": str(e)
                }

            finally:
                if conn:
                    # Release connection
                    release_result = {
                        "operation": "release",
                        "connection_id": conn_id
                    }

        return {"results": results}
    """)

    # Monitor and alert
    workflow.add_node("monitor", "PythonCodeNode", code="""
        # Get pool stats
        stats_request = {"operation": "stats"}

        # Check health and alert if needed
        # This would integrate with your monitoring system

        return {"monitoring_complete": True}
    """)

    # Connect workflow
    workflow.add_connection("init", "result", "db_pool", "input")
    workflow.add_connection("db_pool", "result", "analytics", "input")
    workflow.add_connection("analytics", "result", "execute_safe", "input")
    workflow.add_connection("execute_safe", "result", "monitor", "input")

    return workflow

# Run the workflow
async def main():
    workflow = await create_analytics_workflow()
    runtime = LocalRuntime(enable_async=True)

    # Notify pool of workflow start
    pool_node = workflow.get_node("db_pool")
    await pool_node.on_workflow_start("analytics_123", "analytics")

    try:
        result = await runtime.execute(workflow.build())
        print("Analytics completed:", result)
    finally:
        # Ensure cleanup
        await pool_node.on_workflow_complete("analytics_123")

# Run
if __name__ == "__main__":
    asyncio.run(main())
```

## Best Practices Summary

1. **Always release connections** - Use try/finally blocks
2. **Right-size your pool** - Monitor and adjust based on load
3. **Enable pre-warming** - For predictable workloads
4. **Monitor health scores** - Catch issues early
5. **Use appropriate fetch modes** - 'one' for single rows, 'all' for sets
6. **Handle errors gracefully** - Implement retry logic
7. **Track metrics** - Use built-in statistics for optimization

### Phase 2 Best Practices

8. **Use QueryRouterNode for production** - Automatic connection management and caching
9. **Enable adaptive sizing** - Let the pool self-optimize based on load
10. **Monitor cache hit rates** - Target >80% for repeated queries
11. **Enable pattern learning** - Get insights into workload patterns
12. **Use read/write splitting** - Improve throughput for read-heavy workloads

## Phase 3: Production-Grade Enhancements

### Circuit Breaker Protection

Protect your database from cascade failures with automatic circuit breaker patterns:

```python
from kailash.core.resilience.circuit_breaker import CircuitBreakerManager, CircuitBreakerConfig

# Setup circuit breaker for your connection pool
cb_manager = CircuitBreakerManager()
cb_config = CircuitBreakerConfig(
    failure_threshold=5,        # Open circuit after 5 failures
    recovery_timeout=30,        # Wait 30s before half-open attempt
    error_rate_threshold=0.5,   # Open at 50% error rate
    min_calls=10               # Minimum calls before calculating rate
)

circuit_breaker = cb_manager.get_or_create("db_pool", cb_config)

# Use with your database operations
async def protected_db_operation():
    return pool.process({
        "operation": "execute",
        "query": "SELECT * FROM critical_table"
    })

# Circuit breaker automatically handles failures
try:
    result = await circuit_breaker.call(protected_db_operation)
except Exception as e:
    if "Circuit breaker is OPEN" in str(e):
        # System is protecting itself - use fallback
        result = await get_cached_data()
```

### Comprehensive Metrics Collection

Get deep insights into connection pool performance:

```python
from kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector

# Create metrics collector for your pool
metrics = ConnectionMetricsCollector("production_pool")

# Track query performance automatically
with metrics.track_query("SELECT", "users"):
    result = pool.process({"operation": "execute", "query": "..."})

# Get detailed metrics
all_metrics = metrics.get_all_metrics()
print(f"Throughput: {all_metrics['rates']['queries_per_second']:.1f} qps")
print(f"P95 latency: {all_metrics['percentiles']['query_execution_ms']['p95']:.1f}ms")
print(f"Error rate: {all_metrics['rates']['error_rate']:.1%}")

# Export to Prometheus for monitoring
prometheus_metrics = metrics.export_prometheus()
```

### Query Pipelining for High Performance

Batch multiple queries for maximum throughput:

```python
from kailash.nodes.data.query_pipeline import QueryPipelineNode

# Create high-performance pipeline
pipeline = QueryPipelineNode(
    name="batch_processor",
    connection_string="postgresql://user:pass@localhost:5432/db",
    batch_size=100,             # Process 100 queries per batch
    flush_interval=2.0,         # Auto-flush every 2 seconds
    max_queue_size=5000,        # Queue up to 5000 queries
    execution_strategy="parallel"  # Execute batches in parallel
)

# Add queries (non-blocking)
for user_id in range(10000):
    pipeline.add_query(
        f"UPDATE user_stats SET last_active = NOW() WHERE id = {user_id}",
        query_type="UPDATE"
    )

# Execute with automatic batching
result = pipeline.run()
print(f"Processed {result['queries_executed']} queries")
print(f"Throughput: {result['queries_per_second']:.1f} qps")
```

### Real-time Monitoring Dashboard

Monitor your connection pools in real-time:

```python
from kailash.nodes.monitoring.connection_dashboard import ConnectionDashboardNode

# Create monitoring dashboard
dashboard = ConnectionDashboardNode(
    name="pool_dashboard",
    metrics_collector=metrics,
    circuit_breaker=circuit_breaker,
    websocket_port=8765,
    enable_prometheus_export=True,
    refresh_interval=5.0
)

# Start dashboard (non-blocking)
info = dashboard.run()
print(f"Dashboard: {info['dashboard_url']}")
print(f"Metrics: {info['prometheus_url']}")

# Dashboard shows:
# - Real-time connection utilization
# - Query performance histograms
# - Circuit breaker status
# - Error rates and trends
# - Throughput monitoring
```

## Next Steps

- **NEW**: Explore [Intelligent Query Routing Guide](./17-intelligent-query-routing.md) for Phase 2 features
- **NEW**: Review [Migration Guide](../migration-guides/phase2-intelligent-routing-migration.md) to upgrade existing code
- **Phase 3**: Check [Production Guide](./04-production.md) for complete Phase 3 implementation
- Explore [Query Optimization Guide](./query-optimization.md)
- Learn about [Transaction Management](./transaction-management.md)
- Understand [Database Security Best Practices](./database-security.md)
- Review [Performance Monitoring](./performance-monitoring.md)

This production-grade connection pool provides the reliability, performance, and observability needed for enterprise applications while maintaining the simplicity of Kailash's workflow-based approach.

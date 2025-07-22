# Intelligent Query Routing Guide

*Smart database query optimization and routing*

## Overview

Intelligent Query Routing provides self-optimizing database connection management with automatic query classification, optimal routing decisions, and performance optimization through caching and pattern learning.

## Prerequisites

- Completed [Connection Pool Guide](14-connection-pool-guide.md)
- Understanding of database query patterns
- Basic knowledge of connection pooling

## Core Features

### Query Classification

The router automatically classifies queries for optimal routing:

```python
from kailash.nodes.data.query_router import QueryRouterNode
from kailash.nodes.data import WorkflowConnectionPool

# Create pool with routing enabled
pool = WorkflowConnectionPool(
    name="smart_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=20,
    enable_query_routing=True  # Enable pattern tracking
)

# Create query router
router = QueryRouterNode(
    name="query_router",
    connection_pool="smart_pool",
    enable_read_write_split=True,  # Route reads to any connection
    cache_size=1000,               # Cache prepared statements
    pattern_learning=True          # Learn from patterns
)
```

### Query Types

Queries are automatically classified:

```python
# Simple read - routed to least loaded connection
result = await router.execute({
    "query": "SELECT * FROM users WHERE id = $1",
    "parameters": [123]
})
# Classification: READ_SIMPLE

# Complex read - considers query cost
result = await router.execute({
    "query": """
        SELECT u.*, COUNT(o.id) as order_count
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id
        HAVING COUNT(o.id) > 5
    """,
    "parameters": []
})
# Classification: READ_COMPLEX

# Write query - routed to primary connection
result = await router.execute({
    "query": "INSERT INTO users (name, email) VALUES ($1, $2)",
    "parameters": ["John", "john@example.com"]
})
# Classification: WRITE_SIMPLE
```

**Query Classifications:**
- `READ_SIMPLE`: Single table SELECT
- `READ_COMPLEX`: JOINs, aggregations, subqueries
- `WRITE_SIMPLE`: Single row INSERT/UPDATE/DELETE
- `WRITE_BULK`: Multi-row operations
- `DDL`: Schema modifications (CREATE, ALTER, DROP)
- `TRANSACTION`: Transaction control (BEGIN, COMMIT, ROLLBACK)

## Transaction Handling

### Transaction Affinity

The router maintains connection affinity for transactions:

```python
# Start transaction - gets dedicated connection
result = await router.execute({
    "query": "BEGIN",
    "session_id": "user_session_123"
})

# All queries in transaction use same connection
await router.execute({
    "query": "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
    "parameters": [100, 1],
    "session_id": "user_session_123"
})

await router.execute({
    "query": "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
    "parameters": [100, 2],
    "session_id": "user_session_123"
})

# Commit transaction
await router.execute({
    "query": "COMMIT",
    "session_id": "user_session_123"
})
# Connection released back to pool
```

### Distributed Transactions

```python
# Configure for distributed transactions
router = QueryRouterNode(
    name="distributed_router",
    connection_pool="smart_pool",
    enable_distributed_transactions=True,
    transaction_timeout=300  # 5 minutes
)

# Use two-phase commit
await router.execute({
    "query": "PREPARE TRANSACTION 'tx_123'",
    "session_id": "distributed_tx"
})

# Coordinate across multiple databases
await router.execute({
    "query": "COMMIT PREPARED 'tx_123'",
    "session_id": "distributed_tx"
})
```

## Performance Optimization

### Prepared Statement Caching

The router caches prepared statements:

```python
# First execution - statement prepared
result1 = await router.execute({
    "query": "SELECT * FROM products WHERE category = $1 AND price < $2",
    "parameters": ["electronics", 1000]
})
# Cache miss - ~5ms

# Subsequent executions use cached statement
result2 = await router.execute({
    "query": "SELECT * FROM products WHERE category = $1 AND price < $2",
    "parameters": ["books", 50]
})
# Cache hit - ~1ms (80% faster)

# Monitor cache performance
metrics = await router.get_metrics()
print(f"Cache hit rate: {metrics['cache_stats']['hit_rate']:.2%}")
print(f"Cached statements: {metrics['cache_stats']['size']}")
```

### Query Plan Caching

```python
# Enable query plan caching
router = QueryRouterNode(
    name="plan_cached_router",
    connection_pool="smart_pool",
    enable_plan_cache=True,
    plan_cache_size=500
)

# Complex queries benefit most
complex_query = """
    WITH monthly_sales AS (
        SELECT DATE_TRUNC('month', order_date) as month,
               SUM(total) as revenue
        FROM orders
        WHERE order_date >= $1
        GROUP BY 1
    )
    SELECT * FROM monthly_sales
    ORDER BY month DESC
"""

# First execution - plan generated
await router.execute({
    "query": complex_query,
    "parameters": ["2024-01-01"]
})

# Subsequent executions reuse plan
# Significant performance improvement for complex queries
```

## Adaptive Routing

### Load-Based Routing

The router considers connection load:

```python
# Configure load-aware routing
router = QueryRouterNode(
    name="load_aware_router",
    connection_pool="smart_pool",
    routing_strategy="least_loaded",  # Options: round_robin, least_loaded, weighted
    load_threshold=0.8  # Consider connection overloaded at 80%
)

# Router automatically distributes queries
# to least loaded connections
```

### Pattern Learning

The router learns from query patterns:

```python
# Enable pattern learning
router = QueryRouterNode(
    name="learning_router",
    connection_pool="smart_pool",
    pattern_learning=True,
    learning_window_minutes=60  # Learn from last hour
)

# Router learns:
# - Peak query times
# - Common query patterns
# - Resource requirements
# - Optimal routing decisions

# Access learned patterns
patterns = await router.get_learned_patterns()
print(f"Peak hours: {patterns['peak_hours']}")
print(f"Common queries: {patterns['top_queries'][:5]}")
```

### Predictive Optimization

```python
# Router predicts resource needs
predictions = await router.get_predictions()

# Example output:
{
    "next_hour": {
        "expected_queries": 15000,
        "recommended_connections": 12,
        "peak_time": "14:30"
    },
    "optimization_suggestions": [
        "Increase pool size before 14:00",
        "Pre-warm connections for user_queries pattern",
        "Consider caching results for top 10 queries"
    ]
}
```

## Advanced Patterns

### Read Replica Routing

```python
# Configure with read replicas
router = QueryRouterNode(
    name="replica_router",
    primary_pool="primary_db",
    read_replicas=["replica1_db", "replica2_db"],
    replica_lag_threshold=1000  # Max acceptable lag in ms
)

# Reads automatically routed to replicas
result = await router.execute({
    "query": "SELECT * FROM products",
    "prefer_replica": True
})

# Writes always go to primary
result = await router.execute({
    "query": "UPDATE products SET stock = stock - 1 WHERE id = $1",
    "parameters": [123]
})
```

### Query Prioritization

```python
# High-priority queries get better connections
result = await router.execute({
    "query": "SELECT * FROM critical_data",
    "priority": "high",  # high, normal, low
    "timeout": 5000      # 5 second timeout
})

# Background queries use spare capacity
result = await router.execute({
    "query": "SELECT * FROM analytics_data",
    "priority": "low",
    "max_wait": 30000  # Wait up to 30 seconds
})
```

### Custom Routing Rules

```python
# Define custom routing rules
router.add_routing_rule({
    "name": "analytics_queries",
    "pattern": "SELECT .* FROM analytics_.*",
    "route_to": "analytics_pool",
    "cache_results": True,
    "cache_ttl": 3600  # 1 hour
})

router.add_routing_rule({
    "name": "user_queries",
    "pattern": "SELECT .* FROM users WHERE id = .*",
    "prefer_cached_connection": True,
    "timeout": 1000  # Fast timeout for user queries
})
```

## Monitoring and Metrics

### Performance Metrics

```python
# Get comprehensive metrics
metrics = await router.get_metrics()

print("Query Routing Metrics:")
print(f"Total queries: {metrics['total_queries']}")
print(f"Avg routing time: {metrics['avg_routing_time_us']}μs")
print(f"Cache hit rate: {metrics['cache_hit_rate']:.2%}")

print("\nQuery Type Distribution:")
for query_type, count in metrics['queries_by_type'].items():
    print(f"  {query_type}: {count}")

print("\nConnection Usage:")
for conn_id, stats in metrics['connection_stats'].items():
    print(f"  {conn_id}: {stats['queries']} queries, "
          f"{stats['avg_response_ms']:.1f}ms avg")
```

### Health Monitoring

```python
# Monitor router health
health = await router.check_health()

if health['status'] != 'healthy':
    print(f"Router issues: {health['issues']}")

# Set up alerts
if health['metrics']['error_rate'] > 0.01:
    send_alert("High error rate in query router")
```

## Best Practices

### 1. Session Management

```python
# Use consistent session IDs for related queries
session_id = f"user_{user_id}_{timestamp}"

# All queries for a user flow use same session
for query in user_queries:
    await router.execute({
        "query": query,
        "session_id": session_id
    })
```

### 2. Query Hints

```python
# Provide hints for better routing
result = await router.execute({
    "query": "SELECT * FROM large_table",
    "hints": {
        "expected_rows": 1000000,
        "expected_time_ms": 5000,
        "can_use_stale_connection": True
    }
})
```

### 3. Error Handling

```python
# Handle routing failures gracefully
try:
    result = await router.execute({
        "query": "SELECT * FROM users",
        "require_fresh_connection": True
    })
except RoutingError as e:
    # Fall back to direct pool access
    result = await pool.execute({
        "operation": "execute",
        "query": "SELECT * FROM users"
    })
```

## Troubleshooting

### High Cache Misses

```python
# Analyze cache performance
cache_stats = await router.get_cache_statistics()

# Identify queries not being cached
for query in cache_stats['missed_queries'][:10]:
    print(f"Missed: {query['pattern']}")
    print(f"  Reason: {query['miss_reason']}")

# Adjust cache size if needed
router.resize_cache(2000)
```

### Routing Delays

```python
# Enable detailed routing logs
router.set_debug_level("TRACE")

# Analyze routing decisions
trace = await router.get_routing_trace("slow_query_id")
print(f"Routing steps: {trace['steps']}")
print(f"Total time: {trace['total_time_us']}μs")
```

## Related Guides

**Prerequisites:**
- [Connection Pool Guide](14-connection-pool-guide.md) - Basic pooling
- [Production Hardening](16-production-hardening.md) - Resilience features

**Advanced Topics:**
- [Performance Optimization](../performance/) - Query optimization
- [Monitoring](../monitoring/) - Metrics and alerting

---

**Optimize database performance with intelligent query routing and adaptive connection management!**

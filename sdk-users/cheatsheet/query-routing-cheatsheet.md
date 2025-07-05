# Query Routing & Adaptive Pooling Cheatsheet

## Quick Setup

```python
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.nodes.data.query_router import QueryRouterNode

# Intelligent pool
pool = WorkflowConnectionPool(
    name="smart_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    user="dbuser",
    password="secret",
    min_connections=3,
    max_connections=30,
    adaptive_sizing=True,       # ← Dynamic scaling
    enable_query_routing=True   # ← Pattern tracking
)

# Query router
router = QueryRouterNode(
    name="router",
    connection_pool="smart_pool",
    enable_read_write_split=True,
    cache_size=1000,
    pattern_learning=True
)
```

## Common Patterns

### Simple Query
```python
# Router handles everything
result = await router.execute({
    "query": "SELECT * FROM users WHERE status = ?",
    "parameters": ["active"]
})
```

### Transaction
```python
# Start
await router.execute({
    "query": "BEGIN",
    "session_id": "order_123"
})

# Operations use same connection
await router.execute({
    "query": "UPDATE inventory SET stock = stock - ?",
    "parameters": [1],
    "session_id": "order_123"
})

# Commit
await router.execute({
    "query": "COMMIT",
    "session_id": "order_123"
})
```

### Bulk Operations
```python
# Classified as WRITE_BULK, routed accordingly
await router.execute({
    "query": """
        INSERT INTO events (type, data)
        VALUES ('click', '{}'), ('view', '{}'), ('purchase', '{}')
    """,
    "parameters": []
})
```

## Query Classification

| Query Type | Examples | Routing |
|------------|----------|---------|
| READ_SIMPLE | `SELECT * FROM users WHERE id = ?` | Any healthy connection |
| READ_COMPLEX | `SELECT ... JOIN ... GROUP BY` | Prefer less loaded connections |
| WRITE_SIMPLE | `INSERT INTO ... VALUES (?)` | Primary connections only |
| WRITE_BULK | `INSERT ... VALUES (...), (...)` | Primary, consider dedicated |
| DDL | `CREATE TABLE`, `ALTER TABLE` | Primary, exclusive |
| TRANSACTION | `BEGIN`, `COMMIT`, `ROLLBACK` | Sticky to connection |

## Monitoring

### Pool Statistics
```python
stats = await pool.execute({"operation": "stats"})
print(f"Connections: {stats['current_state']['total_connections']}")
print(f"Utilization: {stats['current_state']['active_connections']}")
print(f"Health: {stats['health']['success_rate']:.1%}")
```

### Router Metrics
```python
metrics = await router.get_metrics()
print(f"Cache hit rate: {metrics['cache_stats']['hit_rate']:.1%}")
print(f"Queries routed: {metrics['router_metrics']['queries_routed']}")
print(f"Avg routing time: {metrics['router_metrics']['avg_routing_time_ms']:.1f}ms")
```

### Adaptive Scaling History
```python
if pool.adaptive_controller:
    for adj in pool.adaptive_controller.get_adjustment_history()[-5:]:
        print(f"{adj['action']}: {adj['from_size']} → {adj['to_size']}")
```

## Configuration Quick Reference

### Pool Parameters
```python
WorkflowConnectionPool(
    # Connection
    database_type="postgresql",      # postgresql, mysql, sqlite
    host="localhost",
    port=5432,
    database="mydb",
    user="user",
    password="pass",

    # Pool sizing
    min_connections=2,               # Minimum pool size
    max_connections=50,              # Maximum pool size

    # Phase 2 features
    adaptive_sizing=True,            # Enable dynamic sizing
    enable_query_routing=True,       # Enable pattern tracking
    health_threshold=60,             # Min health score (0-100)
    pre_warm=True                    # Pre-warm on workflow start
)
```

### Router Parameters
```python
QueryRouterNode(
    connection_pool="pool_name",     # Required: pool to use
    enable_read_write_split=True,    # Route reads to replicas
    cache_size=1000,                 # Prepared statement cache
    pattern_learning=True,           # Learn query patterns
    health_threshold=50.0            # Min health for routing
)
```

## Performance Tips

### 1. Use Parameters
```python
# ❌ Bad - new query each time
query = f"SELECT * FROM users WHERE id = {user_id}"

# ✅ Good - cached prepared statement
query = "SELECT * FROM users WHERE id = ?"
parameters = [user_id]
```

### 2. Session IDs for Related Queries
```python
session = f"report_{uuid.uuid4()}"
# All queries in report use same connection
for table in tables:
    await router.execute({
        "query": f"SELECT COUNT(*) FROM {table}",
        "session_id": session
    })
```

### 3. Workload-Specific Tuning
```python
# Read-heavy
router = QueryRouterNode(
    enable_read_write_split=True,
    cache_size=5000  # Large cache
)

# Write-heavy
router = QueryRouterNode(
    enable_read_write_split=False,  # All to primary
    cache_size=500   # Smaller cache
)
```

## Troubleshooting

| Issue | Check | Fix |
|-------|-------|-----|
| Slow queries | Router metrics → routing time | Increase health_threshold |
| Low cache hits | Cache stats → hit rate | Use parameterized queries |
| Pool not scaling | Pool stats → total connections | Check adaptive_sizing=True |
| Connection errors | Pool health → success rate | Lower health_threshold |

## Debug Mode

```python
import logging

# Enable debug logs
logging.getLogger("kailash.nodes.data.query_router").setLevel(logging.DEBUG)
logging.getLogger("kailash.core.actors.adaptive_pool_controller").setLevel(logging.DEBUG)

# Get detailed status
detailed = await pool.execute({"operation": "get_pool_statistics"})
print(json.dumps(detailed, indent=2))
```

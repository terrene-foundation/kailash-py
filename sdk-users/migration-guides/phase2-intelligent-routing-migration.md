# Migration Guide: Phase 2 Intelligent Query Routing

This guide helps you migrate from basic connection pooling to the Phase 2 intelligent features.

## Overview

Phase 2 adds intelligent query routing, adaptive pool sizing, and pattern learning to the existing WorkflowConnectionPool. These features are opt-in and backward compatible.

## Quick Migration

### Before (Phase 1 Only)
```python
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

# Basic pool
pool = WorkflowConnectionPool(
    name="db_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=20
)

# Direct query execution
conn_result = await pool.process({"operation": "acquire"})
conn_id = conn_result["connection_id"]

result = await pool.process({
    "operation": "execute",
    "connection_id": conn_id,
    "query": "SELECT * FROM users WHERE active = ?",
    "params": [True]
})

await pool.process({
    "operation": "release",
    "connection_id": conn_id
})
```

### After (With Phase 2 Features)
```python
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool
from kailash.nodes.data.query_router import QueryRouterNode

# Enhanced pool with intelligent features
pool = WorkflowConnectionPool(
    name="db_pool",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    min_connections=5,
    max_connections=20,
    adaptive_sizing=True,          # NEW: Dynamic pool sizing
    enable_query_routing=True      # NEW: Pattern tracking
)

# Query router for intelligent routing
router = QueryRouterNode(
    name="query_router",
    connection_pool="db_pool",
    enable_read_write_split=True,  # NEW: Route reads to any connection
    cache_size=1000,               # NEW: Cache prepared statements
    pattern_learning=True          # NEW: Learn from patterns
)

# Simplified query execution with routing
result = await router.process({
    "query": "SELECT * FROM users WHERE active = ?",
    "parameters": [True]
})
# No manual connection management needed!
```

## Feature-by-Feature Migration

### 1. Enable Adaptive Pool Sizing

Add to your existing pool configuration:
```python
pool = WorkflowConnectionPool(
    # ... existing config ...
    adaptive_sizing=True,  # Add this
    min_connections=3,     # Can start smaller
    max_connections=50     # Can scale higher
)
```

Benefits:
- Automatically scales connections based on load
- Reduces idle connections during quiet periods
- Prevents connection exhaustion during peaks

### 2. Add Query Router

Replace direct pool usage with router:
```python
# Register both with runtime
runtime.register_node("db_pool", pool)
runtime.register_node("router", router)

# Old way
conn = await pool.acquire()
result = await pool.execute(conn, query)
await pool.release(conn)

# New way - router handles everything
result = await router.process({
    "query": query,
    "parameters": params
})
```

Benefits:
- Automatic connection management
- Query classification and optimal routing
- Prepared statement caching
- Transaction support with session_id

### 3. Enable Pattern Learning

For workloads with patterns:
```python
pool = WorkflowConnectionPool(
    # ... existing config ...
    enable_query_routing=True  # Enables pattern tracking
)

router = QueryRouterNode(
    # ... existing config ...
    pattern_learning=True      # Enables pattern-based optimization
)
```

Benefits:
- Learns query sequences
- Predicts future queries
- Optimizes pre-warming
- Provides workload insights

## Migration Strategies

### Gradual Migration

1. **Phase 1**: Enable adaptive sizing only
   ```python
   pool = WorkflowConnectionPool(
       # ... existing config ...
       adaptive_sizing=True
   )
   ```
   Monitor for 1 week to ensure stability.

2. **Phase 2**: Add query router for new code
   ```python
   # Keep existing code using pool directly
   # New code uses router
   router = QueryRouterNode(
       connection_pool="db_pool",
       enable_read_write_split=False  # Start conservative
   )
   ```

3. **Phase 3**: Enable all features
   ```python
   # Enable read/write split
   router.enable_read_write_split = True

   # Enable pattern learning
   pool.enable_query_routing = True
   router.pattern_learning = True
   ```

### Big Bang Migration

For smaller applications, migrate all at once:

```python
# Old pool configuration
old_pool = WorkflowConnectionPool(
    name="db_pool",
    database_type="postgresql",
    # ... connection details ...
    min_connections=10,
    max_connections=20
)

# New configuration with all features
new_pool = WorkflowConnectionPool(
    name="db_pool",
    database_type="postgresql",
    # ... same connection details ...
    min_connections=5,       # Can start lower
    max_connections=50,      # Can scale higher
    adaptive_sizing=True,
    enable_query_routing=True,
    health_threshold=70      # More aggressive health checks
)

router = QueryRouterNode(
    name="smart_router",
    connection_pool="db_pool",
    enable_read_write_split=True,
    cache_size=2000,
    pattern_learning=True
)
```

## Configuration Reference

### WorkflowConnectionPool New Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `adaptive_sizing` | bool | False | Enable dynamic pool sizing |
| `enable_query_routing` | bool | False | Enable pattern tracking for routing |

### QueryRouterNode Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection_pool` | str | required | Name of pool node to use |
| `enable_read_write_split` | bool | True | Route reads to any healthy connection |
| `cache_size` | int | 1000 | Max prepared statements to cache |
| `pattern_learning` | bool | True | Learn from query patterns |
| `health_threshold` | float | 50.0 | Min health score for routing |

## Common Migration Issues

### Issue 1: Connections Not Scaling
**Symptom**: Pool stays at min_connections despite load

**Solution**: Check resource constraints
```python
# Ensure max_connections is reasonable
pool = WorkflowConnectionPool(
    max_connections=50,  # Not too low
    adaptive_sizing=True
)

# Check database limits
# PostgreSQL: SHOW max_connections;
# Adaptive controller uses 80% of DB limit
```

### Issue 2: Cache Hit Rate Low
**Symptom**: Router metrics show < 50% cache hit rate

**Solution**:
1. Increase cache size
2. Ensure queries use parameters
```python
# Bad - different query each time
query = f"SELECT * FROM users WHERE id = {user_id}"

# Good - same query, different parameters
query = "SELECT * FROM users WHERE id = ?"
parameters = [user_id]
```

### Issue 3: Pattern Learning Not Working
**Symptom**: No patterns detected after days of operation

**Solution**: Enable on both pool and router
```python
pool = WorkflowConnectionPool(
    enable_query_routing=True  # Required on pool
)

router = QueryRouterNode(
    pattern_learning=True      # Required on router
)
```

## Monitoring Migration Success

### Key Metrics to Track

1. **Connection Pool Efficiency**
   ```python
   stats = await pool.process({"operation": "stats"})
   print(f"Utilization: {stats['current_state']['active_connections'] / stats['current_state']['total_connections']}")
   ```

2. **Query Router Performance**
   ```python
   metrics = await router.get_metrics()
   print(f"Cache hit rate: {metrics['cache_stats']['hit_rate']:.2%}")
   print(f"Avg routing time: {metrics['router_metrics']['avg_routing_time_ms']}ms")
   ```

3. **Adaptive Scaling History**
   ```python
   if pool.adaptive_controller:
       history = pool.adaptive_controller.get_adjustment_history()
       for adj in history[-5:]:
           print(f"{adj['timestamp']}: {adj['from_size']} → {adj['to_size']}")
   ```

### Success Criteria

After migration, you should see:
- ✅ Connection utilization: 70-80% (was: varies widely)
- ✅ Average query latency: 30-50% reduction
- ✅ Cache hit rate: > 70% for repeated queries
- ✅ Connection errors: < 0.1% (was: varies)
- ✅ Peak load handling: No connection exhaustion

## Rollback Plan

If issues arise, you can disable features individually:

```python
# Disable adaptive sizing
pool.adaptive_sizing_enabled = False
if pool.adaptive_controller:
    await pool.adaptive_controller.stop()

# Disable pattern learning
pool.enable_query_routing = False
router.pattern_learning = False

# Disable read/write split
router.enable_read_write_split = False

# Or switch back to direct pool usage
# Just use pool.process() instead of router.process()
```

## Getting Help

- Check logs for routing decisions: `logger.getLogger("kailash.nodes.data.query_router")`
- Enable debug logging for adaptive controller
- Review the [troubleshooting guide](../developer/17-intelligent-query-routing.md#troubleshooting)
- Check metrics regularly during migration

## Summary

The Phase 2 migration provides:
- **Better Performance**: Through intelligent routing and caching
- **Resource Efficiency**: Through adaptive sizing
- **Operational Insights**: Through pattern learning
- **Simplified Code**: No manual connection management

Start with adaptive sizing, add the router, then enable all features for maximum benefit.

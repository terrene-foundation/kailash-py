# CountNode - Efficient Count Queries

## Overview

**CountNode** performs efficient `SELECT COUNT(*) FROM table WHERE filters` queries without fetching actual records. It is automatically generated for all SQL models (PostgreSQL, MySQL, SQLite) and provides a dramatic performance improvement over the `ListNode` + `len()` workaround.

**Performance**: 10-50x faster than ListNode (1-5ms vs 20-50ms)

## Key Features

- **High Performance**: Uses database-native `COUNT(*)` instead of fetching records
- **No Data Transfer**: Returns only the count value, no record data
- **Filter Support**: Full MongoDB-style filter support (same as ListNode)
- **Cross-Database**: Works identically on PostgreSQL, MySQL, and SQLite
- **Zero Overhead**: Minimal memory usage (<1KB per operation)
- **Auto-Generated**: Created automatically for all `@db.model` classes

## Basic Usage

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    email: str
    name: str
    active: bool

# Count all records
workflow = WorkflowBuilder()
workflow.add_node("UserCountNode", "count_all", {})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print(results["count_all"]["count"])  # 1523
```

## Count with Filters

```python
# Count active users only
workflow.add_node("UserCountNode", "count_active", {
    "filter": {"active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print(results["count_active"]["count"])  # 842

# Count with complex filters (MongoDB-style)
workflow.add_node("UserCountNode", "count_complex", {
    "filter": {
        "active": True,
        "email": {"$like": "%@example.com"}
    }
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print(results["count_complex"]["count"])  # 127
```

## Parameter Reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `filter` | dict | No | `{}` | MongoDB-style filter criteria |

**Supported Filter Operators**:
- **Exact match**: `{"status": "active"}`
- **Comparison**: `{"age": {"$gte": 18}}` ($gt, $gte, $lt, $lte, $ne)
- **Pattern match**: `{"name": {"$like": "%Alice%"}}`
- **In list**: `{"role": {"$in": ["admin", "owner"]}}`
- **Not in list**: `{"status": {"$nin": ["banned", "deleted"]}}`

## Return Structure

```python
{
    "count": int  # Number of matching records
}
```

**Example**:
```python
results = {
    "count_users": {
        "count": 1523
    }
}
```

## Performance Comparison

### Slow: ListNode Workaround (Deprecated)

```python
# ❌ SLOW - Fetches all records to count (20-50ms)
workflow.add_node("UserListNode", "count_users", {"limit": 10000})
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = len(results["count_users"])  # Fetched 10,000 records!
```

**Problems**:
- Transfers all record data over network (100KB - 10MB)
- Loads all records into memory (1-10MB)
- Slow query execution (20-50ms)
- Wastes database resources

### Fast: CountNode (Recommended)

```python
# ✅ FAST - Uses COUNT(*) query (1-5ms)
workflow.add_node("UserCountNode", "count_users", {})
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = results["count_users"]["count"]  # Only count value
```

**Benefits**:
- Transfers only count value (8 bytes)
- Zero memory overhead (<1KB)
- Fast query execution (1-5ms)
- Efficient database resource usage

### Performance Metrics

| Metric | ListNode + len() | CountNode | Speedup |
|--------|------------------|-----------|---------|
| Query Time | 20-50ms | 1-5ms | **10-50x** |
| Memory Usage | 1-10MB | <1KB | **1000-10000x** |
| Network Transfer | 100KB-10MB | 8 bytes | **10000-1000000x** |

## Common Patterns

### Pattern 1: Session Statistics

```python
# Count active sessions for each user
workflow.add_node("SessionCountNode", "count_sessions", {
    "filter": {"user_id": user_id, "active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
if results["count_sessions"]["count"] > 5:
    print(f"Warning: {results['count_sessions']['count']} active sessions")
```

**Use Case**: Session limits, rate limiting, concurrency control

### Pattern 2: Availability Check

```python
# Check if any products are in stock
workflow.add_node("ProductCountNode", "check_stock", {
    "filter": {"in_stock": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
if results["check_stock"]["count"] == 0:
    send_alert("Out of stock!")
```

**Use Case**: Inventory alerts, resource availability, queue monitoring

### Pattern 3: Metrics Dashboard

```python
# Build real-time dashboard metrics
workflow.add_node("OrderCountNode", "total_orders", {})
workflow.add_node("OrderCountNode", "pending_orders", {
    "filter": {"status": "pending"}
})
workflow.add_node("OrderCountNode", "completed_orders", {
    "filter": {"status": "completed"}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
metrics = {
    "total": results["total_orders"]["count"],
    "pending": results["pending_orders"]["count"],
    "completed": results["completed_orders"]["count"],
    "completion_rate": results["completed_orders"]["count"] / results["total_orders"]["count"]
}
```

**Use Case**: Dashboards, analytics, status summaries, KPIs

### Pattern 4: Conditional Workflow Logic

```python
# Check if user exists before creating
workflow.add_node("UserCountNode", "check_exists", {
    "filter": {"email": email}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
if results["check_exists"]["count"] > 0:
    # User exists - use UpdateNode
    workflow2.add_node("UserUpdateNode", "update", {...})
else:
    # User doesn't exist - use CreateNode
    workflow2.add_node("UserCreateNode", "create", {...})
```

**Use Case**: Existence checks, conditional creation, deduplication

### Pattern 5: Pagination Metadata

```python
# Get total count for pagination
workflow.add_node("UserCountNode", "total_count", {
    "filter": {"status": "active"}
})
workflow.add_node("UserListNode", "page_data", {
    "filter": {"status": "active"},
    "limit": 20,
    "offset": 0
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
total_pages = math.ceil(results["total_count"]["count"] / 20)
```

**Use Case**: Pagination, infinite scroll, progress indicators

## Database Behavior

### All SQL Databases (PostgreSQL, MySQL, SQLite)

**Query Generated**:
```sql
SELECT COUNT(*) FROM table WHERE filters
```

**Characteristics**:
- Atomic and consistent
- Uses table statistics for estimates (PostgreSQL)
- Supports indexes on filter columns
- No transaction isolation issues

**Index Usage**:
```sql
-- Without index: Full table scan (slow for large tables)
SELECT COUNT(*) FROM users WHERE active = true;

-- With index: Index-only scan (fast)
CREATE INDEX idx_users_active ON users(active);
SELECT COUNT(*) FROM users WHERE active = true;  -- Uses index
```

## Performance Optimization

### Create Indexes on Frequently Filtered Columns

```sql
-- PostgreSQL
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_active ON users(active);
CREATE INDEX idx_users_created_at ON users(created_at);

-- MySQL
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_active ON users(active);
CREATE INDEX idx_users_created_at ON users(created_at);

-- SQLite
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_active ON users(active);
CREATE INDEX idx_users_created_at ON users(created_at);
```

**Impact**:
- **Without index**: 50-200ms for 1M rows
- **With index**: 1-10ms for 1M rows
- **Speedup**: 10-50x improvement

### Use Composite Indexes for Multiple Filters

```sql
-- Composite index for common filter combination
CREATE INDEX idx_users_status_active ON users(status, active);

-- Query uses composite index (very fast)
workflow.add_node("UserCountNode", "count", {
    "filter": {"status": "active", "active": True}
})
```

### Avoid COUNT(*) with Large OFFSET

```python
# ❌ SLOW - COUNT(*) doesn't need OFFSET
workflow.add_node("UserListNode", "list", {"limit": 20, "offset": 1000000})
count = len(results["list"])  # Very slow!

# ✅ FAST - Use CountNode directly
workflow.add_node("UserCountNode", "count", {"filter": {"status": "active"}})
```

## Troubleshooting

### Slow Count Queries

**Symptom**: CountNode takes >100ms

**Cause**: Missing index on filter columns

**Solution**:
```sql
-- Add index on frequently filtered columns
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_active ON users(active);
```

**Verification**:
```sql
-- PostgreSQL: Check if index is used
EXPLAIN SELECT COUNT(*) FROM users WHERE active = true;

-- MySQL: Check if index is used
EXPLAIN SELECT COUNT(*) FROM users WHERE active = true;

-- SQLite: Check if index is used
EXPLAIN QUERY PLAN SELECT COUNT(*) FROM users WHERE active = true;
```

### Count Returns 0 Unexpectedly

**Symptom**: CountNode returns 0 when records exist

**Cause**: Filter criteria doesn't match actual data

**Debug Steps**:
1. Use ListNode with same filter to inspect records
   ```python
   # Debug: See what records match
   workflow.add_node("UserListNode", "debug", {
       "filter": {"status": "active"},
       "limit": 10
   })
   ```
2. Check for typos in filter field names
3. Verify field values in database match filter

**Solution**: Correct filter criteria or check database data

### Performance Degradation Over Time

**Symptom**: CountNode gets slower as table grows

**Cause**: Table statistics outdated or missing indexes

**Solution**:
```sql
-- PostgreSQL: Update statistics
ANALYZE users;

-- MySQL: Optimize table
OPTIMIZE TABLE users;

-- SQLite: Analyze table
ANALYZE users;
```

## When to Use CountNode

**Use CountNode when**:
- ✅ You only need the count, not the records
- ✅ You're building dashboards or metrics
- ✅ You're checking existence (`count > 0`)
- ✅ You need pagination metadata
- ✅ You're monitoring queue sizes

**Use ListNode when**:
- ✅ You need both count AND records
- ✅ You need to inspect actual data
- ✅ Count is <100 and you'll process records anyway

## See Also

- [ListNode - Query Records](./list-node.md)
- [CRUD Operations Guide](../development/crud.md)
- [Filtering Guide](../development/filtering.md)
- [Performance Optimization](../deployment/performance.md)

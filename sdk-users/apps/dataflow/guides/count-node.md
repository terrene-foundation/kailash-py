# CountNode Guide - Efficient Count Queries

## Table of Contents
1. [What is CountNode?](#what-is-countnode)
2. [Basic Usage](#basic-usage)
3. [Count with Filters](#count-with-filters)
4. [Parameter Reference](#parameter-reference)
5. [Performance Comparison](#performance-comparison)
6. [Common Patterns](#common-patterns)
7. [Database Behavior](#database-behavior)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

## What is CountNode?

**CountNode** performs efficient `SELECT COUNT(*) FROM table WHERE filters` queries without fetching actual records. It's automatically generated for all SQL models (PostgreSQL, MySQL, SQLite) and provides significantly better performance than fetching and counting records.

### Key Features

- **High performance**: 10-50x faster than ListNode workaround (1-5ms vs 20-50ms)
- **No data transfer**: Only count value returned, no records fetched
- **Filter support**: Supports MongoDB-style filters (same as ListNode)
- **Cross-database**: Works identically on PostgreSQL, MySQL, and SQLite
- **Zero overhead**: Minimal memory usage (<1KB)
- **Auto-generated**: Created automatically for every @db.model

### When to Use CountNode

**Use CountNode when you need to**:
- ✅ Count total records in a table
- ✅ Count records matching specific criteria
- ✅ Check if any records exist (count > 0)
- ✅ Display pagination metadata (total pages, has_next)
- ✅ Build dashboard metrics and statistics
- ✅ Validate data before expensive operations

**Don't use CountNode when**:
- ❌ You need the actual records (use ListNode instead)
- ❌ You need to process individual records
- ❌ Count is incidental to other operations

## Basic Usage

### Count All Records

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

await db.initialize()

# Count all users
workflow = WorkflowBuilder()
workflow.add_node("UserCountNode", "count_all", {})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

total_users = results["count_all"]["count"]
print(f"Total users: {total_users}")
# Output: Total users: 1523
```

### Understanding the Return Value

CountNode returns a dict with a single key:

```python
{
    "count": int  # Number of matching records
}
```

Access the count value:

```python
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = results["node_id"]["count"]
```

## Count with Filters

### Simple Filter

```python
# Count active users
workflow.add_node("UserCountNode", "count_active", {
    "filter": {"active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
active_users = results["count_active"]["count"]
print(f"Active users: {active_users}")
# Output: Active users: 842
```

### Complex Filters

CountNode supports the same MongoDB-style filters as ListNode:

```python
# Count with compound filter
workflow.add_node("UserCountNode", "count_complex", {
    "filter": {
        "active": True,
        "email": {"$like": "%@example.com"}
    }
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = results["count_complex"]["count"]
print(f"Active example.com users: {count}")
# Output: Active example.com users: 127
```

### Supported Filter Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Equal to | `{"age": {"$eq": 25}}` |
| `$ne` | Not equal to | `{"status": {"$ne": "deleted"}}` |
| `$gt` | Greater than | `{"age": {"$gt": 18}}` |
| `$gte` | Greater than or equal | `{"age": {"$gte": 18}}` |
| `$lt` | Less than | `{"age": {"$lt": 65}}` |
| `$lte` | Less than or equal | `{"age": {"$lte": 65}}` |
| `$in` | In array | `{"status": {"$in": ["active", "pending"]}}` |
| `$nin` | Not in array | `{"role": {"$nin": ["admin", "owner"]}}` |
| `$like` | SQL LIKE pattern | `{"email": {"$like": "%@gmail.com"}}` |
| `$ilike` | Case-insensitive LIKE | `{"name": {"$ilike": "%alice%"}}` |

### Multiple Filters (AND Logic)

```python
# All filters combined with AND
workflow.add_node("UserCountNode", "count_filtered", {
    "filter": {
        "active": True,
        "age": {"$gte": 18},
        "email": {"$like": "%@example.com"}
    }
})
# SQL: WHERE active = true AND age >= 18 AND email LIKE '%@example.com'
```

## Parameter Reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `filter` | dict | No | `{}` | MongoDB-style filter criteria |

### Filter Parameter Details

**Empty filter (default)**:
```python
workflow.add_node("UserCountNode", "count", {})
# OR
workflow.add_node("UserCountNode", "count", {"filter": {}})
# Both count ALL records
```

**Single field filter**:
```python
workflow.add_node("UserCountNode", "count", {
    "filter": {"active": True}
})
```

**Multiple field filter**:
```python
workflow.add_node("UserCountNode", "count", {
    "filter": {
        "active": True,
        "role": "admin"
    }
})
```

**Operator-based filter**:
```python
workflow.add_node("UserCountNode", "count", {
    "filter": {
        "age": {"$gte": 18, "$lt": 65}
    }
})
```

## Performance Comparison

### ListNode Workaround (Deprecated)

**Before CountNode** (pre-v0.8.0), counting required fetching all records:

```python
# ❌ SLOW: Fetches all records to count (20-50ms)
workflow.add_node("UserListNode", "count_users", {"limit": 10000})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = len(results["count_users"])
# Fetched 10,000 records just to get count!
```

**Problems with ListNode workaround**:
- 10-50x slower (20-50ms vs 1-5ms)
- High memory usage (1-10MB vs <1KB)
- Large network transfer (100KB-10MB vs 8 bytes)
- Requires arbitrary limit (what if table has > 10,000 records?)

### CountNode (Recommended)

```python
# ✅ FAST: Uses COUNT(*) query (1-5ms)
workflow.add_node("UserCountNode", "count_users", {})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = results["count_users"]["count"]
# Only count value transferred (8 bytes)
```

**Benefits**:
- Query time: 1-5ms (vs. 20-50ms)
- Memory usage: <1KB (vs. 1-10MB)
- Network transfer: 8 bytes (vs. 100KB-10MB)
- No arbitrary limits
- Accurate for any table size

### Performance Metrics

| Metric | ListNode Workaround | CountNode | Improvement |
|--------|---------------------|-----------|-------------|
| Query time (small table <1K) | ~20ms | ~1ms | 20x faster |
| Query time (medium table 10K) | ~50ms | ~2ms | 25x faster |
| Query time (large table 100K) | ~500ms | ~5ms | 100x faster |
| Memory usage | 1-10MB | <1KB | 1000-10000x less |
| Network transfer | 100KB-10MB | 8 bytes | 10000-1000000x less |

**Real-world example** (10,000 user table):
- ListNode: 50ms query + 5MB memory + 2MB network
- CountNode: 2ms query + <1KB memory + 8 bytes network
- **Result**: 25x faster, 5000x less memory, 250000x less network

## Common Patterns

### Pattern 1: Pagination Metadata

Calculate total pages and has_next/has_prev:

```python
# Get count for pagination
workflow.add_node("UserCountNode", "total_count", {
    "filter": {"active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
total = results["total_count"]["count"]

# Calculate pagination
page = 2
limit = 20
total_pages = (total + limit - 1) // limit
has_next = page < total_pages
has_prev = page > 1

print(f"Page {page} of {total_pages}")
print(f"Total: {total} records")
print(f"Has next: {has_next}, Has prev: {has_prev}")
```

### Pattern 2: Existence Check

Check if any records exist (more efficient than fetching):

```python
# Check if any products are in stock
workflow.add_node("ProductCountNode", "check_stock", {
    "filter": {"in_stock": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
if results["check_stock"]["count"] == 0:
    send_alert("Out of stock!")
else:
    print(f"{results['check_stock']['count']} products in stock")
```

### Pattern 3: Dashboard Metrics

Build real-time dashboard with multiple counts:

```python
# Count orders by status
workflow.add_node("OrderCountNode", "total_orders", {})
workflow.add_node("OrderCountNode", "pending_orders", {
    "filter": {"status": "pending"}
})
workflow.add_node("OrderCountNode", "completed_orders", {
    "filter": {"status": "completed"}
})
workflow.add_node("OrderCountNode", "failed_orders", {
    "filter": {"status": "failed"}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

metrics = {
    "total": results["total_orders"]["count"],
    "pending": results["pending_orders"]["count"],
    "completed": results["completed_orders"]["count"],
    "failed": results["failed_orders"]["count"]
}

print(f"Dashboard: {metrics}")
# Output: Dashboard: {'total': 5432, 'pending': 127, 'completed': 5234, 'failed': 71}
```

### Pattern 4: Session Statistics

Count active sessions per user:

```python
# Count active sessions for user
workflow.add_node("SessionCountNode", "count_sessions", {
    "filter": {
        "user_id": user_id,
        "active": True
    }
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
session_count = results["count_sessions"]["count"]

if session_count > 5:
    print(f"Warning: {session_count} active sessions")
    # Optionally revoke oldest sessions
```

### Pattern 5: Conditional Processing

Count before expensive operations:

```python
# Check if processing is needed
workflow.add_node("TaskCountNode", "pending_count", {
    "filter": {"status": "pending"}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
pending = results["pending_count"]["count"]

if pending == 0:
    print("No pending tasks, skipping batch job")
else:
    print(f"Processing {pending} pending tasks...")
    # Run expensive batch processing
```

### Pattern 6: Availability Monitoring

Monitor resource availability:

```python
# Monitor available licenses
workflow.add_node("LicenseCountNode", "available_licenses", {
    "filter": {"assigned": False}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
available = results["available_licenses"]["count"]

if available < 10:
    send_alert(f"Low license availability: {available} remaining")
```

## Database Behavior

### PostgreSQL

```sql
-- Generated SQL
SELECT COUNT(*) FROM users WHERE active = true;
```

**Features**:
- Uses standard `SELECT COUNT(*)`
- Atomic and consistent
- Supports indexes on filter columns
- Can use covering indexes for fast counts

### MySQL

```sql
-- Generated SQL
SELECT COUNT(*) FROM users WHERE active = true;
```

**Features**:
- Uses standard `SELECT COUNT(*)`
- Atomic and consistent
- Supports indexes on filter columns
- InnoDB: Exact count, may scan index

### SQLite

```sql
-- Generated SQL
SELECT COUNT(*) FROM users WHERE active = true;
```

**Features**:
- Uses standard `SELECT COUNT(*)`
- Atomic and consistent
- Supports indexes on filter columns
- Fast for small-medium tables

### Cross-Database Consistency

All three databases:
- ✅ Use standard SQL `SELECT COUNT(*)`
- ✅ Support indexed filter columns for performance
- ✅ Return same result structure
- ✅ Atomic read operation

### Performance Optimization Tips

**Create indexes on frequently filtered columns**:

```sql
-- PostgreSQL
CREATE INDEX idx_users_active ON users(active);
CREATE INDEX idx_users_status ON users(status);

-- With index: COUNT(*) uses index scan (fast)
-- Without index: COUNT(*) uses sequential scan (slow)
```

**Performance with indexes**:
- Small table (<1K): ~1ms (with or without index)
- Medium table (10K): ~2ms (with index), ~50ms (without)
- Large table (100K): ~5ms (with index), ~500ms (without)

## Troubleshooting

### Issue: Slow Count Queries

**Symptom**: Count queries taking 50-500ms instead of 1-5ms.

**Cause**: Missing indexes on filter columns.

**Solution**: Create indexes on frequently filtered columns:

```sql
-- PostgreSQL
CREATE INDEX idx_users_active ON users(active);
CREATE INDEX idx_users_status_created ON users(status, created_at);

-- Verify index usage
EXPLAIN SELECT COUNT(*) FROM users WHERE active = true;
-- Should show "Index Scan" or "Index Only Scan"
```

**Python verification**:

```python
# Check if index is being used (PostgreSQL)
workflow.add_node("SQLNode", "explain", {
    "query": "EXPLAIN SELECT COUNT(*) FROM users WHERE active = true"
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print(results["explain"])
# Should contain "Index" in query plan
```

### Issue: Count Returns 0 Unexpectedly

**Symptom**: Count returns 0 but you expect records to exist.

**Cause**: Filter criteria doesn't match actual data.

**Debug Steps**:

1. **Verify filter criteria matches data**:
```python
# Use ListNode with same filter to inspect records
workflow.add_node("UserListNode", "debug_list", {
    "filter": {"active": True},
    "limit": 5
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print("Sample records:", results["debug_list"])
# Check if records match your expected filter
```

2. **Check for type mismatches**:
```python
# ❌ WRONG - type mismatch
workflow.add_node("UserCountNode", "count", {
    "filter": {"active": "true"}  # String instead of boolean!
})

# ✅ CORRECT - proper type
workflow.add_node("UserCountNode", "count", {
    "filter": {"active": True}  # Boolean
})
```

3. **Check for NULL values**:
```python
# NULL values don't match filters
# ❌ Filter: {"status": "active"} won't match NULL status
# ✅ Use: {"status": {"$ne": None}} to exclude NULLs explicitly
```

### Issue: Count Doesn't Match ListNode Length

**Symptom**: CountNode returns different value than len(ListNode results).

**Cause**: ListNode has `limit` parameter, CountNode counts all matching records.

**Example**:

```python
# ListNode with limit
workflow.add_node("UserListNode", "list", {
    "filter": {"active": True},
    "limit": 20
})

# CountNode with same filter
workflow.add_node("UserCountNode", "count", {
    "filter": {"active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

print(len(results["list"]))  # 20 (limited)
print(results["count"]["count"])  # 842 (total matching)
# Different values - this is expected!
```

**Solution**: Use CountNode for total, ListNode for paginated records:

```python
# Correct usage
total = results["count"]["count"]  # 842 total
records = results["list"]  # 20 records (current page)
```

### Issue: Filter Not Working as Expected

**Symptom**: Filter seems to be ignored or returns unexpected count.

**Cause**: Incorrect filter syntax or operator usage.

**Common mistakes**:

```python
# ❌ WRONG - Missing operator
workflow.add_node("UserCountNode", "count", {
    "filter": {"age": 25}  # Implicit $eq
})
# This works, but explicit is better

# ✅ CORRECT - Explicit operator
workflow.add_node("UserCountNode", "count", {
    "filter": {"age": {"$eq": 25}}
})

# ❌ WRONG - Invalid operator
workflow.add_node("UserCountNode", "count", {
    "filter": {"email": {"$contains": "example.com"}}  # Not supported
})

# ✅ CORRECT - Use $like for contains
workflow.add_node("UserCountNode", "count", {
    "filter": {"email": {"$like": "%example.com%"}}
})
```

## Best Practices

1. **Always use CountNode for counting** (never ListNode workaround):

```python
# ✅ BEST PRACTICE
workflow.add_node("UserCountNode", "count", {})

# ❌ DON'T DO THIS
workflow.add_node("UserListNode", "count", {"limit": 10000})
count = len(results["count"])
```

2. **Create indexes on frequently counted columns**:

```sql
-- If you often count by status
CREATE INDEX idx_orders_status ON orders(status);

-- If you often count by date range
CREATE INDEX idx_orders_created ON orders(created_at);

-- Composite index for multiple filters
CREATE INDEX idx_orders_status_date ON orders(status, created_at);
```

3. **Use CountNode for existence checks** (more efficient than ListNode):

```python
# ✅ BEST PRACTICE
workflow.add_node("ProductCountNode", "check", {
    "filter": {"sku": product_sku}
})
exists = results["check"]["count"] > 0

# ❌ LESS EFFICIENT
workflow.add_node("ProductListNode", "check", {
    "filter": {"sku": product_sku},
    "limit": 1
})
exists = len(results["check"]) > 0
```

4. **Combine CountNode with ListNode for pagination**:

```python
# Get count and page records in same workflow
workflow.add_node("UserCountNode", "total", {
    "filter": {"active": True}
})
workflow.add_node("UserListNode", "records", {
    "filter": {"active": True},
    "limit": 20,
    "offset": (page - 1) * 20
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

total = results["total"]["count"]
records = results["records"]
total_pages = (total + 20 - 1) // 20
```

5. **Cache counts for frequently accessed metrics**:

```python
# Cache dashboard metrics (if they don't need real-time accuracy)
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=1)
def get_cached_metrics(cache_key):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCountNode", "total", {})
    workflow.add_node("OrderCountNode", "pending", {"filter": {"status": "pending"}})

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    return {
        "users": results["total"]["count"],
        "pending_orders": results["pending"]["count"]
    }

# Refresh cache every 5 minutes
cache_key = datetime.now().strftime("%Y-%m-%d-%H-%M") // 5
metrics = get_cached_metrics(cache_key)
```

6. **Use specific filters to reduce count scope**:

```python
# ✅ BEST PRACTICE - Specific filter
workflow.add_node("OrderCountNode", "recent", {
    "filter": {
        "status": "pending",
        "created_at": {"$gte": datetime.now() - timedelta(days=7)}
    }
})

# ❌ LESS EFFICIENT - Count all, filter in application
workflow.add_node("OrderCountNode", "all", {})
# Then filter in Python (inefficient)
```

## Related Documentation

- **ListNode Guide**: For fetching actual records with filters
- **Error Handling Guide**: `sdk-users/apps/dataflow/guides/error-handling.md`
- **Node Reference**: `sdk-users/apps/dataflow/docs/reference/nodes.md`
- **Performance Guide**: `sdk-users/apps/dataflow/docs/advanced/performance.md`

## Version History

- **v0.8.0**: Added CountNode for all SQL models (PostgreSQL, MySQL, SQLite)
- **Pre-v0.8.0**: Counting required ListNode workaround (10-50x slower)

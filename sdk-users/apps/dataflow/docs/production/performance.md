# DataFlow Performance Guide

Comprehensive guide to optimizing DataFlow applications for production performance.

## Overview

Performance optimization in DataFlow involves multiple layers: query optimization, connection pooling, caching, indexing, and workflow design. This guide covers all aspects.

## Query Optimization

### Index Strategy

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
@db.model
class Order:
    id: int
    user_id: int
    product_id: int
    status: str
    created_at: datetime
    total: float

    __dataflow__ = {
        'indexes': [
            # Single column indexes
            ['user_id'],
            ['product_id'],
            ['status'],
            ['created_at'],

            # Composite indexes for common queries
            ['user_id', 'status', 'created_at'],  # User order history
            ['product_id', 'status'],              # Product sales
            ['status', 'created_at'],              # Order processing

            # Partial index for active orders only
            {
                'fields': ['user_id', 'created_at'],
                'where': "status IN ('pending', 'processing')",
                'name': 'idx_active_orders'
            }
        ]
    }
```

### Query Analysis

```python
workflow = WorkflowBuilder()

# Enable query profiling
workflow.add_node("QueryProfilerNode", "enable_profiling", {
    "profile": True,
    "explain": True,
    "analyze": True
})

# Potentially slow query
workflow.add_node("OrderListNode", "get_orders", {
    "filter": {
        "user_id": user_id,
        "status": "completed",
        "created_at": {"$gte": start_date}
    },
    "order_by": ["-created_at"],
    "limit": 100
})

# Analyze query performance
workflow.add_node("QueryAnalyzerNode", "analyze", {
    "query_id": ":get_orders_query_id",
    "suggest_indexes": True,
    "identify_issues": True
})
```

### Query Optimization Patterns

```python
# Bad: N+1 query problem
for user in users:
    orders = get_orders(user.id)  # Executes N queries

# Good: Batch query with prefetch
workflow.add_node("UserListNode", "get_users_with_orders", {
    "prefetch": ["orders"],  # Single query with JOIN
    "filter": {"active": True}
})

# Bad: Fetching unnecessary columns
workflow.add_node("ProductListNode", "get_all_fields", {})

# Good: Select only needed fields
workflow.add_node("ProductListNode", "get_specific_fields", {
    "select": ["id", "name", "price"],  # Reduces data transfer
    "filter": {"category": "electronics"}
})

# Bad: Multiple queries
user = get_user(user_id)
orders = get_orders(user_id)
addresses = get_addresses(user_id)

# Good: Single aggregated query
workflow.add_node("UserAggregateNode", "get_user_data", {
    "user_id": user_id,
    "include": ["orders", "addresses"],
    "aggregate": True
})
```

## Connection Pool Optimization

### Dynamic Pool Sizing

```python
import os
from concurrent.futures import ThreadPoolExecutor

class DynamicPoolManager:
    """Dynamically adjust pool size based on load."""

    def __init__(self, db):
        self.db = db
        self.base_pool_size = os.cpu_count() * 4
        self.max_pool_size = os.cpu_count() * 10
        self.monitor_interval = 60  # seconds

    def calculate_optimal_pool_size(self):
        """Calculate pool size based on metrics."""
        stats = self.db.get_pool_stats()

        # Pool utilization
        utilization = stats['active'] / stats['size']

        # Wait time
        avg_wait = stats.get('avg_wait_time', 0)

        if utilization > 0.8 and avg_wait > 0.1:
            # Increase pool size
            new_size = min(
                int(stats['size'] * 1.5),
                self.max_pool_size
            )
        elif utilization < 0.3:
            # Decrease pool size
            new_size = max(
                int(stats['size'] * 0.7),
                self.base_pool_size
            )
        else:
            new_size = stats['size']

        return new_size

    def adjust_pool(self):
        """Adjust pool size dynamically."""
        new_size = self.calculate_optimal_pool_size()
        current_size = self.db.config.pool_size

        if new_size != current_size:
            self.db.adjust_pool_size(new_size)
            logger.info(f"Adjusted pool size: {current_size} -> {new_size}")
```

### Connection Pool Monitoring

```python
workflow.add_node("PoolMonitorNode", "monitor_connections", {
    "metrics": [
        "pool_size",
        "active_connections",
        "idle_connections",
        "wait_queue_length",
        "avg_wait_time",
        "connection_errors",
        "connection_timeouts"
    ],
    "alert_thresholds": {
        "utilization": 0.9,      # 90% pool usage
        "wait_time": 1.0,        # 1 second wait
        "error_rate": 0.01       # 1% error rate
    },
    "interval": "30s"
})
```

## Caching Strategy

### Multi-Level Caching

```python
from kailash_dataflow import CacheConfig

# Configure multi-level cache
cache_config = CacheConfig(
    # L1: In-memory cache (fast, limited size)
    l1_enabled=True,
    l1_max_size=1000,  # objects
    l1_ttl=300,        # 5 minutes

    # L2: Redis cache (larger, distributed)
    l2_enabled=True,
    l2_backend="redis",
    l2_ttl=3600,       # 1 hour

    # L3: Database materialized views
    l3_enabled=True,
    l3_refresh_interval=86400  # 24 hours
)

db = DataFlow(cache_config=cache_config)
```

### Query Result Caching

```python
@db.model
class Product:
    id: int
    name: str
    price: float
    category: str

    __dataflow__ = {
        'cache': {
            'enabled': True,
            'key_pattern': 'product:{id}',
            'ttl': 3600,
            'invalidate_on': ['update', 'delete'],
            'warm_cache_on_start': True
        }
    }

# Cached query with custom key
workflow.add_node("CachedQueryNode", "get_top_products", {
    "query": "ProductListNode",
    "params": {
        "filter": {"category": category},
        "order_by": ["-sales_count"],
        "limit": 10
    },
    "cache": {
        "key": f"top_products:{category}",
        "ttl": 600,  # 10 minutes
        "tags": ["products", category]  # For bulk invalidation
    }
})
```

### Cache Warming

```python
workflow = WorkflowBuilder()

# Schedule cache warming
workflow.add_node("SchedulerNode", "warm_cache_schedule", {
    "schedule": "0 6 * * *",  # 6 AM daily
    "target": "warm_cache"
})

workflow.add_node("CacheWarmerNode", "warm_cache", {
    "strategies": [
        {
            "name": "popular_products",
            "query": "SELECT * FROM products WHERE popular = true",
            "cache_key_pattern": "product:{id}"
        },
        {
            "name": "user_dashboards",
            "query": "SELECT * FROM user_dashboard_data WHERE active = true",
            "cache_key_pattern": "dashboard:{user_id}"
        }
    ],
    "parallel_workers": 4,
    "batch_size": 100
})
```

## Bulk Operations

### Efficient Bulk Inserts

```python
# Inefficient: Individual inserts
for item in items:
    workflow.add_node("ProductCreateNode", f"create_{item['id']}", item)

# Efficient: Bulk insert
workflow.add_node("ProductBulkCreateNode", "bulk_insert", {
    "data": items,
    "batch_size": 1000,
    "on_conflict": "update",  # or "ignore"
    "parallel_batches": 4,
    "use_copy": True  # PostgreSQL COPY for maximum speed
})
```

### Bulk Updates with Conditions

```python
workflow.add_node("BulkUpdateNode", "update_prices", {
    "model": "Product",
    "fields": [
        {
            "filter": {"category": "electronics"},
            "data": {"discount": 0.1}
        },
        {
            "filter": {"category": "clothing", "season": "winter"},
            "data": {"discount": 0.3}
        }
    ],
    "use_case_statement": True,  # Single query with CASE
    "return_affected": True
})
```

## Workflow Optimization

### Parallel Execution

```python
workflow = WorkflowBuilder()

# Sequential (slow)
workflow.add_node("UserReadNode", "get_user", {"id": user_id})
workflow.add_node("OrderListNode", "get_orders", {"user_id": user_id})
workflow.add_node("AddressListNode", "get_addresses", {"user_id": user_id})

# Parallel (fast)
workflow.add_node("ParallelNode", "fetch_user_data", {
    "nodes": [
        {"type": "UserReadNode", "id": "user", "params": {"id": user_id}},
        {"type": "OrderListNode", "id": "orders", "params": {"user_id": user_id}},
        {"type": "AddressListNode", "id": "addresses", "params": {"user_id": user_id}}
    ],
    "timeout": 5.0,
    "fail_fast": False  # Continue even if one fails
})

# Merge results
workflow.add_node("MergeNode", "combine_results", {
    "sources": ["fetch_user_data.user", "fetch_user_data.orders", "fetch_user_data.addresses"],
    "merge_strategy": "nested"
})
```

### Batch Processing

```python
# Process large dataset in batches
workflow.add_node("BatchProcessorNode", "process_orders", {
    "source_query": "SELECT * FROM orders WHERE status = 'pending'",
    "batch_size": 1000,
    "processor": "order_processor",
    "parallel_batches": 4,
    "progress_tracking": True,
    "checkpoint_interval": 10000,  # Save progress every 10k records
    "resume_on_failure": True
})

workflow.add_node("PythonCodeNode", "order_processor", {
    "code": """
# Process batch of orders
orders = get_input_data("batch")
results = []

for order in orders:
    # Process each order
    processed = process_order(order)
    results.append(processed)

# Return results for bulk update
result = {"processed_orders": results}
"""
})
```

## Database-Specific Optimizations

### PostgreSQL Performance

```python
# PostgreSQL-specific optimizations
if db.dialect == "postgresql":
    # Use advisory locks for distributed processing
    workflow.add_node("AdvisoryLockNode", "acquire_lock", {
        "lock_id": 12345,
        "lock_type": "exclusive",
        "timeout": 5.0
    })

    # Optimize for bulk operations
    workflow.add_node("PGCopyNode", "bulk_load", {
        "table": "events",
        "data_file": "events.csv",
        "format": "CSV",
        "header": True,
        "delimiter": ",",
        "null_string": "\\N"
    })

    # Table partitioning for time-series data
    workflow.add_node("PartitionMaintenanceNode", "manage_partitions", {
        "table": "metrics",
        "partition_by": "created_at",
        "interval": "monthly",
        "retention": "12 months",
        "create_future": 3  # Create 3 months ahead
    })
```

### MySQL Performance

```python
# MySQL-specific optimizations
if db.dialect == "mysql":
    # Optimize for InnoDB
    workflow.add_node("MySQLOptimizeNode", "optimize_tables", {
        "tables": ["orders", "order_items"],
        "analyze": True,
        "defragment": True
    })

    # Use INSERT IGNORE for high-volume inserts
    workflow.add_node("MySQLBulkInsertNode", "fast_insert", {
        "table": "events",
        "data": events,
        "ignore_duplicates": True,
        "disable_keys": True,  # Rebuild indexes after
        "batch_size": 10000
    })
```

## Monitoring and Profiling

### Performance Metrics

```python
workflow.add_node("PerformanceMonitorNode", "collect_metrics", {
    "metrics": {
        "queries": {
            "total_count": True,
            "slow_queries": {"threshold": 1.0},
            "query_time_histogram": True,
            "queries_per_second": True
        },
        "connections": {
            "pool_utilization": True,
            "connection_wait_time": True,
            "connection_lifetime": True
        },
        "cache": {
            "hit_rate": True,
            "eviction_rate": True,
            "memory_usage": True
        },
        "resources": {
            "cpu_usage": True,
            "memory_usage": True,
            "disk_io": True,
            "network_io": True
        }
    },
    "export_to": ["prometheus", "cloudwatch"],
    "interval": "10s"
})
```

### Query Profiling

```python
# Profile specific workflow
with db.profiler() as profiler:
    workflow = WorkflowBuilder()
    # ... workflow definition ...
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    # Get profiling results
    profile = profiler.get_results()

    print(f"Total time: {profile['total_time']}s")
    print(f"Database time: {profile['db_time']}s")
    print(f"Slowest queries:")
    for query in profile['slow_queries'][:5]:
        print(f"  - {query['time']}s: {query['sql'][:50]}...")
```

## Production Checklist

### Pre-Production Performance Audit

```python
workflow.add_node("PerformanceAuditNode", "audit", {
    "checks": [
        "missing_indexes",
        "n_plus_one_queries",
        "large_result_sets",
        "missing_pagination",
        "uncached_expensive_queries",
        "connection_pool_size",
        "slow_query_threshold",
        "bulk_operation_usage",
        "parallel_execution_opportunities"
    ],
    "generate_report": True,
    "fail_on_critical": True
})
```

### Performance Testing

```python
def load_test_workflow():
    """Load test the application."""
    import locust

    class DataFlowUser(locust.HttpUser):
        wait_time = locust.between(1, 3)

        @locust.task(3)
        def read_products(self):
            self.client.get("/api/products")

        @locust.task(1)
        def create_order(self):
            self.client.post("/api/orders", json={
                "product_id": 1,
                "quantity": 1
            })

    # Run load test
    os.system("locust -f load_test.py --host=http://localhost:8000")
```

## Best Practices

1. **Index Strategically**: Create indexes for WHERE, ORDER BY, and JOIN columns
2. **Use Connection Pooling**: Always use appropriate pool sizes
3. **Cache Aggressively**: Cache expensive queries and frequently accessed data
4. **Batch Operations**: Use bulk operations for multiple records
5. **Monitor Continuously**: Track performance metrics in production
6. **Profile Regularly**: Identify and fix slow queries proactively
7. **Optimize Workflows**: Use parallel execution where possible
8. **Test Performance**: Load test before production deployment

## Next Steps

- **Monitoring**: [Monitoring Guide](../advanced/monitoring.md)
- **Troubleshooting**: [Troubleshooting Guide](troubleshooting.md)
- **Scaling**: [Scaling Guide](../advanced/scaling.md)

Performance optimization is an ongoing process. Continuously monitor and improve your DataFlow applications.

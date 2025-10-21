# DataFlow Database Optimization Guide

Advanced techniques for optimizing database performance in DataFlow applications.

## Query Optimization

### Index Strategy

```python
from kailash.workflow.builder import WorkflowBuilder
@db.model
class Order:
    id: int
    user_id: int
    product_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    total: float

    __dataflow__ = {
        'indexes': [
            # Primary lookup patterns
            ['user_id', 'status', 'created_at'],  # User order history
            ['product_id', 'created_at'],          # Product analytics

            # Covering indexes (include all needed columns)
            {
                'fields': ['status', 'created_at'],
                'include': ['user_id', 'total'],  # No table lookup needed
                'name': 'idx_status_covering'
            },

            # Partial indexes (subset of rows)
            {
                'fields': ['user_id'],
                'where': "status = 'pending'",
                'name': 'idx_pending_orders'
            },

            # Expression indexes
            {
                'expression': 'EXTRACT(YEAR FROM created_at)',
                'name': 'idx_order_year'
            }
        ]
    }
```

### Query Plan Analysis

```python
workflow = WorkflowBuilder()

# Analyze query execution plan
workflow.add_node("QueryPlanAnalyzerNode", "analyze_plan", {
    "query": """
        SELECT o.*, u.name, p.title
        FROM orders o
        JOIN users u ON o.user_id = u.id
        JOIN products p ON o.product_id = p.id
        WHERE o.status = 'completed'
        AND o.created_at >= :start_date
        ORDER BY o.created_at DESC
        LIMIT 100
    """,
    "analyze_options": {
        "buffers": True,      # Show buffer usage
        "timing": True,       # Show actual timings
        "verbose": True,      # Detailed output
        "format": "json"      # Machine-readable format
    }
})

# Suggest optimizations
workflow.add_node("QueryOptimizerNode", "optimize", {
    "plan": ":analyze_plan",
    "suggest": [
        "missing_indexes",
        "join_order",
        "filter_pushdown",
        "materialized_views"
    ]
})
```

### Query Rewriting

```python
# Subquery optimization
# Bad: Correlated subquery
bad_query = """
SELECT * FROM users u
WHERE (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) > 10
"""

# Good: Join with aggregation
workflow.add_node("QueryRewriterNode", "rewrite_subquery", {
    "original_query": bad_query,
    "optimization": "decorrelate",
    "rewritten": """
        SELECT u.* FROM users u
        JOIN (
            SELECT user_id, COUNT(*) as order_count
            FROM orders
            GROUP BY user_id
            HAVING COUNT(*) > 10
        ) o ON u.id = o.user_id
    """
})

# EXISTS optimization
workflow.add_node("ExistsOptimizationNode", "optimize_exists", {
    "original": """
        SELECT * FROM products p
        WHERE EXISTS (
            SELECT 1 FROM order_items oi
            WHERE oi.product_id = p.id
            AND oi.created_at > NOW() - INTERVAL '30 days'
        )
    """,
    "use_semi_join": True  # More efficient than EXISTS
})
```

## Statistics and Maintenance

### Table Statistics

```python
# Update table statistics
workflow.add_node("StatisticsUpdateNode", "update_stats", {
    "tables": ["orders", "order_items", "products"],
    "sample_rate": 100,  # Percentage
    "columns": "all",    # Or specific columns
    "schedule": "daily"
})

# Analyze statistics quality
workflow.add_node("StatisticsAnalyzerNode", "check_stats", {
    "check": [
        "outdated_statistics",
        "missing_statistics",
        "skewed_distributions",
        "correlation_issues"
    ],
    "alert_threshold": {
        "staleness_days": 7,
        "row_change_percent": 20
    }
})
```

### Vacuum and Maintenance

```python
# PostgreSQL vacuum strategy
if db.dialect == "postgresql":
    workflow.add_node("VacuumStrategyNode", "configure_vacuum", {
        "tables": {
            "high_update_table": {
                "autovacuum_vacuum_scale_factor": 0.05,  # 5% dead tuples
                "autovacuum_analyze_scale_factor": 0.05,
                "autovacuum_vacuum_cost_delay": 10
            },
            "append_only_table": {
                "autovacuum_enabled": False,  # Manual vacuum
                "manual_vacuum_schedule": "weekly"
            }
        }
    })

    # Monitor bloat
    workflow.add_node("BloatMonitorNode", "check_bloat", {
        "thresholds": {
            "table_bloat_ratio": 2.0,    # 2x actual size
            "index_bloat_ratio": 3.0,    # 3x actual size
            "min_wasted_bytes": 1048576  # 1MB
        },
        "actions": {
            "high_bloat": "schedule_vacuum_full",
            "medium_bloat": "increase_vacuum_frequency"
        }
    })
```

## Partitioning

### Time-Based Partitioning

```python
@db.model
class Event:
    id: int
    timestamp: datetime
    event_type: str
    data: dict

    __dataflow__ = {
        'partitioning': {
            'strategy': 'range',
            'key': 'timestamp',
            'interval': 'monthly',
            'retention': {
                'keep_months': 12,
                'archive_months': 24,
                'delete_after': 36
            },
            'automatic': {
                'create_ahead': 3,  # Create 3 months ahead
                'maintenance_schedule': 'daily'
            }
        }
    }

# Partition maintenance
workflow.add_node("PartitionMaintenanceNode", "maintain_partitions", {
    "operations": [
        {
            "type": "create_future",
            "months_ahead": 3
        },
        {
            "type": "compress_old",
            "older_than_months": 6,
            "compression": "zstd"
        },
        {
            "type": "archive",
            "older_than_months": 12,
            "destination": "s3://archive/events/"
        },
        {
            "type": "drop",
            "older_than_months": 36
        }
    ]
})
```

### List Partitioning

```python
@db.model
class Customer:
    id: int
    region: str
    name: str

    __dataflow__ = {
        'partitioning': {
            'strategy': 'list',
            'key': 'region',
            'partitions': {
                'us_customers': ['us-east', 'us-west'],
                'eu_customers': ['eu-west', 'eu-central'],
                'asia_customers': ['asia-pacific', 'asia-south']
            }
        }
    }
```

## Materialized Views

### Creating Materialized Views

```python
workflow.add_node("MaterializedViewNode", "create_dashboard_view", {
    "name": "user_dashboard_stats",
    "query": """
        SELECT
            u.id as user_id,
            u.name,
            COUNT(DISTINCT o.id) as total_orders,
            SUM(o.total) as lifetime_value,
            AVG(o.total) as avg_order_value,
            MAX(o.created_at) as last_order_date
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id, u.name
    """,
    "indexes": ['user_id'],
    "refresh": {
        "method": "concurrent",  # Don't lock during refresh
        "schedule": "0 */4 * * *"  # Every 4 hours
    }
})

# Incremental refresh
workflow.add_node("IncrementalMaterializedViewNode", "create_incremental", {
    "name": "daily_sales_summary",
    "base_query": """
        SELECT
            DATE(created_at) as sale_date,
            product_id,
            COUNT(*) as units_sold,
            SUM(total) as revenue
        FROM orders
        WHERE created_at >= :last_refresh
        GROUP BY DATE(created_at), product_id
    """,
    "merge_strategy": "upsert",
    "refresh_tracking": True
})
```

## Query Caching

### Result Set Caching

```python
# Configure query result caching
cache_config = {
    "enabled": True,
    "backend": "redis",
    "serialization": "msgpack",  # Faster than JSON
    "compression": "lz4",         # Fast compression
    "key_strategy": "query_hash",
    "namespace": "dataflow:queries"
}

# Implement intelligent caching
workflow.add_node("SmartCacheNode", "cache_strategy", {
    "rules": [
        {
            "pattern": "SELECT.*FROM products.*",
            "ttl": 3600,  # 1 hour
            "invalidate_on": ["products.update", "products.delete"]
        },
        {
            "pattern": ".*GROUP BY.*DATE.*",
            "ttl": 86400,  # 24 hours for aggregated data
            "cache_warmer": True
        },
        {
            "pattern": ".*user_id = :current_user.*",
            "ttl": 300,  # 5 minutes for user-specific
            "key_includes": ["user_id"]
        }
    ]
})
```

### Cache Warming

```python
workflow.add_node("CacheWarmerNode", "warm_critical_queries", {
    "queries": [
        {
            "name": "homepage_stats",
            "query": "SELECT * FROM homepage_statistics",
            "schedule": "*/15 * * * *"  # Every 15 minutes
        },
        {
            "name": "popular_products",
            "query": """
                SELECT p.*, ps.view_count, ps.sale_count
                FROM products p
                JOIN product_stats ps ON p.id = ps.product_id
                WHERE ps.view_count > 1000
                ORDER BY ps.sale_count DESC
                LIMIT 100
            """,
            "schedule": "0 * * * *"  # Hourly
        }
    ],
    "parallel_warming": True,
    "priority": "low"  # Don't impact production
})
```

## Connection Optimization

### Prepared Statements

```python
# Enable prepared statement caching
workflow.add_node("PreparedStatementNode", "configure_prepared", {
    "cache_size": 500,
    "track_usage": True,
    "eviction_policy": "lru",
    "deallocate_unused": {
        "enabled": True,
        "threshold": 3600  # 1 hour unused
    }
})

# Monitor prepared statement performance
workflow.add_node("PreparedStatementMonitor", "monitor", {
    "metrics": [
        "cache_hit_rate",
        "execution_time_saved",
        "memory_usage"
    ],
    "alert_on": {
        "hit_rate_below": 0.8,
        "memory_above_mb": 100
    }
})
```

### Connection Pooling Optimization

```python
# Dynamic pool sizing based on workload
class AdaptivePoolManager:
    def __init__(self, db):
        self.db = db
        self.history = []

    def analyze_workload(self):
        """Analyze connection usage patterns."""
        stats = self.db.get_pool_stats()

        # Time-based analysis
        hour = datetime.now().hour
        day_of_week = datetime.now().weekday()

        # Workload patterns
        if hour >= 9 and hour <= 17 and day_of_week < 5:
            # Business hours
            return "peak"
        elif hour >= 0 and hour <= 6:
            # Overnight
            return "maintenance"
        else:
            return "normal"

    def optimize_pool(self):
        """Adjust pool based on workload."""
        workload = self.analyze_workload()

        configs = {
            "peak": {
                "pool_size": 100,
                "pool_max_overflow": 50,
                "pool_timeout": 10
            },
            "normal": {
                "pool_size": 50,
                "pool_max_overflow": 25,
                "pool_timeout": 30
            },
            "maintenance": {
                "pool_size": 20,
                "pool_max_overflow": 10,
                "pool_timeout": 60
            }
        }

        self.db.reconfigure_pool(**configs[workload])
```

## Lock Optimization

### Lock Monitoring

```python
workflow.add_node("LockMonitorNode", "monitor_locks", {
    "track": [
        "lock_waits",
        "deadlocks",
        "long_held_locks",
        "lock_escalations"
    ],
    "thresholds": {
        "wait_time_ms": 1000,
        "hold_time_s": 5
    },
    "capture": {
        "blocking_queries": True,
        "wait_graphs": True,
        "query_plans": True
    }
})
```

### Optimistic Locking

```python
@db.model
class Product:
    id: int
    name: str
    price: float
    version: int = 1

    __dataflow__ = {
        'optimistic_lock': 'version',
        'retry_on_conflict': 3
    }

# Use optimistic locking in workflow
workflow.add_node("OptimisticUpdateNode", "update_product", {
    "model": "Product",
    "id": product_id,
    "fields": {"price": new_price},
    "conflict_resolution": "retry",  # or "merge", "fail"
    "max_retries": 3
})
```

## Hardware Optimization

### SSD Optimization

```python
# PostgreSQL SSD optimization
if db.dialect == "postgresql" and storage_type == "ssd":
    workflow.add_node("SSDOptimizationNode", "optimize_for_ssd", {
        "settings": {
            "random_page_cost": 1.1,  # Nearly sequential
            "effective_io_concurrency": 200,  # SSDs handle many requests
            "wal_buffers": "64MB",
            "checkpoint_completion_target": 0.9,
            "max_wal_size": "4GB"
        }
    })
```

### Memory Configuration

```python
# Calculate optimal memory settings
def calculate_memory_config(total_ram_gb):
    """Calculate database memory configuration."""
    return {
        "shared_buffers": f"{int(total_ram_gb * 0.25)}GB",  # 25% of RAM
        "effective_cache_size": f"{int(total_ram_gb * 0.75)}GB",  # 75% of RAM
        "work_mem": f"{int(total_ram_gb * 1024 * 0.01)}MB",  # 1% per query
        "maintenance_work_mem": f"{int(total_ram_gb * 1024 * 0.05)}MB"  # 5% for maintenance
    }

# Apply configuration
workflow.add_node("MemoryConfigNode", "configure_memory", {
    "auto_detect": True,
    "reserve_os_memory": "2GB",
    "connection_overhead": "10MB"
})
```

## Monitoring and Alerts

### Performance Monitoring

```python
workflow.add_node("DatabasePerformanceMonitor", "comprehensive_monitoring", {
    "metrics": {
        "query_performance": {
            "slow_query_log": True,
            "threshold_ms": 100,
            "explain_slow_queries": True
        },
        "index_usage": {
            "unused_indexes": True,
            "index_scan_ratio": True,
            "index_bloat": True
        },
        "table_statistics": {
            "row_estimates": True,
            "dead_tuples": True,
            "last_vacuum": True
        },
        "lock_statistics": {
            "lock_waits": True,
            "deadlock_count": True,
            "longest_transaction": True
        }
    },
    "alerts": {
        "slow_query_spike": {
            "threshold": "5x baseline",
            "window": "5m"
        },
        "index_bloat": {
            "threshold": "3x optimal",
            "action": "schedule_reindex"
        }
    }
})
```

## Best Practices

1. **Profile First**: Always measure before optimizing
2. **Index Wisely**: Too many indexes slow writes
3. **Partition Large Tables**: Improves query performance and maintenance
4. **Use Appropriate Data Types**: Smaller types = better performance
5. **Vacuum Regularly**: Prevent table bloat
6. **Monitor Continuously**: Track trends, not just current state
7. **Test Changes**: Always test optimizations in staging first
8. **Document Everything**: Track what optimizations were applied and why

## Next Steps

- **Performance Guide**: [Performance Guide](../production/performance.md)
- **Monitoring Guide**: [Monitoring Guide](monitoring.md)
- **Troubleshooting Guide**: [Troubleshooting Guide](../production/troubleshooting.md)

Database optimization is an iterative process. Continuously monitor, analyze, and improve based on actual workload patterns.

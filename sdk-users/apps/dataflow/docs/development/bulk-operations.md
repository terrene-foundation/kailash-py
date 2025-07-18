# DataFlow Bulk Operations

High-performance bulk operations for processing thousands of records efficiently.

## Overview

DataFlow provides specialized bulk operation nodes that are optimized for high-throughput data processing. These nodes automatically handle:

- **Database-specific optimizations** (PostgreSQL COPY, MySQL batch INSERT, etc.)
- **Automatic chunking** for memory efficiency
- **Progress tracking** and monitoring
- **Error recovery** and cleanup
- **Concurrent processing** when possible

## Generated Bulk Nodes

For each model, DataFlow automatically generates bulk operation nodes:

```python
@db.model
class Product:
    name: str
    price: float
    category: str
    stock: int

# DataFlow automatically creates:
# ProductBulkCreateNode     - High-performance bulk insert
# ProductBulkUpdateNode     - Bulk update with conditions
# ProductBulkDeleteNode     - Safe bulk deletion
# ProductBulkUpsertNode     - Insert or update operations
```

## Bulk Create Operations

### Basic Bulk Insert

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Prepare data
products = [
    {"name": "Product 1", "price": 19.99, "category": "electronics", "stock": 100},
    {"name": "Product 2", "price": 29.99, "category": "electronics", "stock": 50},
    # ... thousands more
]

workflow = WorkflowBuilder()

# Bulk insert products
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "data": products,
    "batch_size": 1000,           # Process 1000 records at a time
    "conflict_resolution": "skip"  # Skip duplicates
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Check results
imported = results["import_products"]["data"]
print(f"Imported {imported['records_processed']} products")
print(f"Success: {imported['success_count']}, Failed: {imported['failure_count']}")
```

### Advanced Bulk Insert

```python
# Advanced bulk insert with validation and monitoring
workflow.add_node("ProductBulkCreateNode", "import_products_advanced", {
    "data": products,

    # Performance settings
    "batch_size": 5000,
    "parallel_batches": 4,        # Process 4 batches concurrently
    "use_copy": True,             # Use PostgreSQL COPY (faster)

    # Validation
    "validate_data": True,
    "validation_rules": {
        "price": {"min": 0.01, "max": 10000.00},
        "stock": {"min": 0, "max": 999999}
    },

    # Conflict resolution
    "conflict_resolution": "update",
    "conflict_fields": ["name", "category"],

    # Error handling
    "error_strategy": "continue",  # Continue on individual record failures
    "max_errors": 100,             # Stop if more than 100 errors

    # Monitoring
    "progress_callback": True,
    "progress_interval": 1000,

    # Cleanup
    "auto_cleanup": True,
    "cleanup_on_failure": True
})
```

### Bulk Insert with Relationships

```python
# Insert users and their profiles in bulk
users_data = [
    {
        "name": "John Doe",
        "email": "john@example.com",
        "profile": {
            "bio": "Software developer",
            "location": "New York"
        }
    },
    # ... more users
]

workflow.add_node("UserBulkCreateNode", "create_users", {
    "data": users_data,
    "include_relationships": ["profile"],
    "relationship_strategy": "nested_create"
})
```

## Bulk Update Operations

### Conditional Bulk Updates

```python
# Update all electronics products with a discount
workflow.add_node("ProductBulkUpdateNode", "discount_electronics", {
    "filter": {"category": "electronics"},
    "updates": {
        "price": "price * 0.9",    # 10% discount
        "updated_at": ":current_timestamp"
    },
    "batch_size": 2000
})

# Update specific products by ID
workflow.add_node("ProductBulkUpdateNode", "update_specific_products", {
    "updates": [
        {"id": 1, "price": 15.99, "stock": 200},
        {"id": 2, "price": 25.99, "stock": 150},
        {"id": 3, "stock": 0}  # Out of stock
    ],
    "batch_size": 1000
})
```

### Bulk Update with Conditions

```python
# Complex conditional updates
workflow.add_node("ProductBulkUpdateNode", "restock_products", {
    "filter": {
        "stock": {"$lt": 10},        # Low stock
        "active": True,              # Only active products
        "category": {"$in": ["electronics", "clothing"]}
    },
    "updates": {
        "stock": "stock + 100",      # Add 100 units
        "restock_date": ":current_date",
        "status": "restocked"
    },
    "batch_size": 1000,
    "return_updated": True           # Return updated records
})
```

### Atomic Bulk Updates

```python
# Atomic operations for concurrent safety
workflow.add_node("ProductBulkUpdateNode", "atomic_stock_update", {
    "updates": [
        {"id": 1, "atomic_ops": {"stock": {"$inc": -5}}},  # Decrement by 5
        {"id": 2, "atomic_ops": {"stock": {"$inc": -3}}},  # Decrement by 3
        {"id": 3, "atomic_ops": {"views": {"$inc": 1}}}   # Increment views
    ],
    "ensure_atomic": True
})
```

## Bulk Delete Operations

### Conditional Bulk Delete

```python
# Delete old, inactive products
workflow.add_node("ProductBulkDeleteNode", "cleanup_old_products", {
    "filter": {
        "active": False,
        "created_at": {"$lt": "2022-01-01"},
        "stock": 0
    },
    "batch_size": 1000,
    "soft_delete": True,            # Soft delete (set deleted_at)
    "cascade": ["reviews", "ratings"]  # Delete related records
})

# Delete specific products by ID
workflow.add_node("ProductBulkDeleteNode", "delete_specific_products", {
    "ids": [1, 2, 3, 4, 5],
    "hard_delete": True,            # Permanently delete
    "batch_size": 100
})
```

### Safe Bulk Delete

```python
# Safe deletion with confirmation
workflow.add_node("ProductBulkDeleteNode", "safe_delete_products", {
    "filter": {"category": "discontinued"},

    # Safety checks
    "dry_run": True,                # First run to see what would be deleted
    "max_delete_count": 10000,      # Safety limit
    "confirm_delete": True,         # Require confirmation

    # Backup before delete
    "backup_before_delete": True,
    "backup_location": "/tmp/deleted_products.json",

    # Cleanup
    "cleanup_related": True,
    "cleanup_files": True
})
```

## Bulk Upsert Operations

### Insert or Update

```python
# Upsert products (insert new, update existing)
workflow.add_node("ProductBulkUpsertNode", "upsert_products", {
    "data": products,
    "unique_fields": ["name", "category"],  # Fields to check for duplicates
    "update_fields": ["price", "stock", "updated_at"],  # Fields to update
    "insert_fields": ["name", "category", "price", "stock"],  # Fields for new records
    "batch_size": 2000
})
```

### Conditional Upsert

```python
# Upsert with conditions
workflow.add_node("ProductBulkUpsertNode", "conditional_upsert", {
    "data": products,
    "unique_fields": ["sku"],
    "upsert_conditions": {
        "update_if": {"updated_at": {"$lt": ":current_timestamp"}},
        "insert_if": {"active": True}
    },
    "conflict_resolution": "update"
})
```

## Performance Optimization

### Database-Specific Optimizations

```python
# PostgreSQL optimizations
workflow.add_node("ProductBulkCreateNode", "postgres_optimized", {
    "data": products,
    "batch_size": 10000,
    "use_copy": True,               # Use COPY command
    "copy_options": {
        "delimiter": "\t",
        "null_string": "\\N",
        "format": "csv"
    },
    "disable_triggers": True,       # Disable triggers for speed
    "disable_indexes": False        # Keep indexes (usually faster)
})

# MySQL optimizations
workflow.add_node("ProductBulkCreateNode", "mysql_optimized", {
    "data": products,
    "batch_size": 5000,
    "use_load_data": True,          # Use LOAD DATA INFILE
    "mysql_options": {
        "local_infile": True,
        "ignore_lines": 1,
        "fields_terminated_by": ","
    },
    "disable_foreign_keys": True,   # Temporarily disable FK checks
    "disable_autocommit": True      # Manual transaction control
})
```

### Memory Optimization

```python
# Memory-efficient bulk operations
workflow.add_node("ProductBulkCreateNode", "memory_efficient", {
    "data": products,
    "batch_size": 1000,
    "streaming": True,              # Stream data instead of loading all in memory
    "memory_limit": "1GB",          # Maximum memory usage
    "spill_to_disk": True,          # Use disk if memory exceeded
    "compression": True,            # Compress data in memory
    "gc_interval": 100              # Run garbage collection every 100 batches
})
```

### Parallel Processing

```python
# Parallel bulk operations
workflow.add_node("ProductBulkCreateNode", "parallel_processing", {
    "data": products,
    "batch_size": 2000,
    "parallel_batches": 8,          # Process 8 batches concurrently
    "max_workers": 4,               # Maximum worker threads
    "connection_pool_size": 10,     # Connections per worker
    "load_balancing": "round_robin" # Distribute load evenly
})
```

## Error Handling and Recovery

### Error Strategies

```python
# Comprehensive error handling
workflow.add_node("ProductBulkCreateNode", "error_resilient", {
    "data": products,
    "batch_size": 1000,

    # Error handling
    "error_strategy": "continue",   # continue, stop, retry_batch
    "max_errors": 1000,             # Stop if too many errors
    "error_log_level": "warning",

    # Retry logic
    "retry_failed_records": True,
    "max_retries": 3,
    "retry_delay": 1.0,             # Seconds between retries
    "retry_backoff": "exponential",

    # Failed record handling
    "failed_records_file": "/tmp/failed_products.json",
    "failed_records_callback": "handle_failed_records"
})
```

### Recovery and Cleanup

```python
# Recovery from partial failures
workflow.add_node("ProductBulkCreateNode", "recoverable_operation", {
    "data": products,
    "batch_size": 1000,

    # Recovery settings
    "resumable": True,              # Can resume from checkpoint
    "checkpoint_interval": 5000,    # Checkpoint every 5000 records
    "checkpoint_file": "/tmp/bulk_checkpoint.json",

    # Cleanup settings
    "auto_cleanup": True,
    "cleanup_on_failure": True,
    "cleanup_temp_files": True,
    "cleanup_connections": True
})
```

## Progress Monitoring

### Progress Tracking

```python
# Real-time progress monitoring
workflow.add_node("ProductBulkCreateNode", "monitored_operation", {
    "data": products,
    "batch_size": 1000,

    # Progress settings
    "progress_callback": True,
    "progress_interval": 1000,      # Update every 1000 records
    "progress_format": "percentage", # percentage, count, both

    # Monitoring
    "monitor_memory": True,
    "monitor_cpu": True,
    "monitor_disk_io": True,
    "monitor_network": True,

    # Metrics
    "collect_metrics": True,
    "metrics_interval": 5000,
    "metrics_file": "/tmp/bulk_metrics.json"
})
```

### Performance Metrics

```python
# Detailed performance metrics
workflow.add_node("ProductBulkCreateNode", "performance_tracked", {
    "data": products,
    "batch_size": 1000,

    # Performance tracking
    "track_execution_time": True,
    "track_memory_usage": True,
    "track_io_operations": True,
    "track_batch_performance": True,

    # Benchmarking
    "benchmark_mode": True,
    "benchmark_iterations": 3,
    "benchmark_warmup": 1000,

    # Reporting
    "performance_report": True,
    "report_format": "json",
    "report_file": "/tmp/performance_report.json"
})
```

## Advanced Use Cases

### Data Migration

```python
# Large-scale data migration
workflow.add_node("ProductBulkCreateNode", "migrate_products", {
    "data": products,
    "batch_size": 10000,

    # Migration settings
    "migration_mode": True,
    "preserve_ids": True,           # Keep original IDs
    "skip_validation": True,        # Skip validation for speed
    "disable_triggers": True,       # Disable triggers

    # Data transformation
    "transform_data": True,
    "transformation_rules": {
        "price": "price * 1.1",     # 10% price increase
        "category": "category.lower()",  # Lowercase category
        "created_at": "coalesce(created_at, now())"
    },

    # Verification
    "verify_migration": True,
    "verification_sample": 1000,
    "verification_fields": ["name", "price", "category"]
})
```

### Real-time Data Processing

```python
# Real-time bulk processing
workflow.add_node("ProductBulkCreateNode", "realtime_processing", {
    "data": products,
    "batch_size": 100,

    # Real-time settings
    "streaming": True,
    "stream_buffer_size": 1000,
    "stream_timeout": 5.0,

    # Processing
    "process_immediately": True,
    "max_latency": 1.0,             # Process within 1 second
    "priority": "high",

    # Integration
    "publish_events": True,
    "event_topic": "product_updates",
    "event_format": "json"
})
```

### Data Synchronization

```python
# Synchronize data between systems
workflow.add_node("ProductBulkUpsertNode", "sync_products", {
    "data": external_products,
    "unique_fields": ["external_id"],

    # Synchronization settings
    "sync_mode": "incremental",     # full, incremental, delta
    "conflict_resolution": "source_wins",
    "last_sync_timestamp": "2024-01-01T00:00:00Z",

    # Change detection
    "detect_changes": True,
    "change_detection_fields": ["price", "stock", "description"],
    "ignore_fields": ["internal_notes", "created_at"],

    # Audit
    "audit_sync": True,
    "audit_table": "product_sync_audit",
    "audit_level": "changes_only"
})
```

## Testing Bulk Operations

### Unit Tests

```python
def test_bulk_create():
    """Test bulk product creation."""
    products = [
        {"name": f"Product {i}", "price": i * 10.0, "category": "test"}
        for i in range(1, 101)
    ]

    workflow = WorkflowBuilder()
    workflow.add_node("ProductBulkCreateNode", "test_bulk_create", {
        "data": products,
        "batch_size": 25
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["test_bulk_create"]["data"]["success_count"] == 100
    assert results["test_bulk_create"]["data"]["failure_count"] == 0
```

### Performance Tests

```python
def test_bulk_performance():
    """Test bulk operation performance."""
    import time

    # Large dataset
    products = [
        {"name": f"Product {i}", "price": i * 10.0, "category": "perf_test"}
        for i in range(1, 10001)  # 10,000 products
    ]

    workflow = WorkflowBuilder()
    workflow.add_node("ProductBulkCreateNode", "perf_test", {
        "data": products,
        "batch_size": 1000,
        "track_execution_time": True
    })

    start_time = time.time()
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    end_time = time.time()

    execution_time = end_time - start_time
    records_per_second = len(products) / execution_time

    assert execution_time < 10.0  # Should complete in under 10 seconds
    assert records_per_second > 1000  # Should process at least 1000 records/second
```

## Best Practices

### 1. Choose Appropriate Batch Sizes

```python
# Small datasets (< 1,000 records)
batch_size = 100

# Medium datasets (1,000 - 100,000 records)
batch_size = 1000

# Large datasets (> 100,000 records)
batch_size = 5000

# Very large datasets (> 1,000,000 records)
batch_size = 10000
```

### 2. Use Database-Specific Optimizations

```python
# PostgreSQL: Use COPY for large imports
workflow.add_node("ProductBulkCreateNode", "postgres_import", {
    "data": products,
    "use_copy": True,
    "batch_size": 10000
})

# MySQL: Use LOAD DATA INFILE
workflow.add_node("ProductBulkCreateNode", "mysql_import", {
    "data": products,
    "use_load_data": True,
    "batch_size": 5000
})
```

### 3. Monitor and Handle Errors

```python
# Always handle errors gracefully
workflow.add_node("ProductBulkCreateNode", "safe_import", {
    "data": products,
    "error_strategy": "continue",
    "max_errors": 100,
    "failed_records_file": "/tmp/failed_records.json"
})
```

### 4. Use Appropriate Data Types

```python
# Use appropriate data types for performance
@db.model
class Product:
    name: str                    # VARCHAR for text
    price: Decimal              # DECIMAL for currency
    stock: int                  # INTEGER for counts
    active: bool                # BOOLEAN for flags
    created_at: datetime        # TIMESTAMP for dates
    metadata: dict              # JSON for flexible data
```

### 5. Optimize for Your Use Case

```python
# Data import: Prioritize speed
workflow.add_node("ProductBulkCreateNode", "data_import", {
    "data": products,
    "batch_size": 10000,
    "disable_triggers": True,
    "skip_validation": True
})

# Real-time updates: Prioritize consistency
workflow.add_node("ProductBulkUpdateNode", "realtime_updates", {
    "data": products,
    "batch_size": 100,
    "ensure_atomic": True,
    "validate_data": True
})
```

## Performance Benchmarks

### Typical Performance Numbers

- **Small datasets (< 1,000 records)**: 1,000-5,000 records/second
- **Medium datasets (1,000-100,000 records)**: 5,000-20,000 records/second
- **Large datasets (> 100,000 records)**: 20,000-100,000 records/second

### Optimization Impact

- **Database-specific optimizations**: 2-10x improvement
- **Proper batch sizing**: 2-5x improvement
- **Parallel processing**: 2-4x improvement
- **Memory optimization**: 1.5-3x improvement

## Next Steps

- **Query Building**: [Query Builder Guide](../advanced/query-builder.md)
- **Performance Tuning**: [Performance Guide](../production/performance.md)
- **Monitoring**: [Monitoring Guide](../advanced/monitoring.md)
- **Production Deployment**: [Deployment Guide](../production/deployment.md)

DataFlow bulk operations provide the performance and reliability needed for modern data-intensive applications while maintaining simplicity and type safety.

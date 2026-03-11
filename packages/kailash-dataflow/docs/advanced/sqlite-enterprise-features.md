# SQLite Enterprise Features

DataFlow provides enterprise-grade SQLite capabilities that rival PostgreSQL in functionality while leveraging SQLite's unique advantages. This document covers the advanced SQLite features available in DataFlow.

## Overview

The SQLite Enterprise Adapter (`SQLiteEnterpriseAdapter`) provides:

- **Advanced Indexing**: Partial, expression, and covering indexes with usage tracking
- **WAL Mode**: Concurrent reads with intelligent checkpoint management
- **Connection Pooling**: Intelligent connection management with performance monitoring
- **Transaction Isolation**: Full isolation level control with savepoints
- **Performance Monitoring**: Real-time metrics and optimization recommendations
- **Query Optimization**: Query plan analysis and index recommendations
- **Database Maintenance**: Automated vacuum and fragmentation detection

## Quick Start

```python
from dataflow import DataFlow

# Use enterprise SQLite features
db = DataFlow(
    "sqlite:///enterprise.db",
    enable_wal=True,                    # Enable WAL mode for concurrency
    enable_connection_pooling=True,     # Enable connection pooling
    enable_performance_monitoring=True, # Enable performance tracking
    cache_size_mb=64,                  # 64MB cache
    max_connections=20,                # Connection pool size
    pragma_overrides={
        "synchronous": "NORMAL",        # Balance safety and performance
        "temp_store": "MEMORY"          # Use memory for temp tables
    }
)

@db.model
class User:
    email: str
    name: str
    status: str = "active"
    subscription_tier: str = "free"

@db.model
class Order:
    user_id: int
    product_name: str
    amount: float
    status: str = "pending"
```

## Advanced Indexing Support

### Partial Indexes

SQLite partial indexes are ideal for selective conditions:

```python
# Create partial index for active users only
await db.adapter.create_index(
    "users",
    ["status"],
    index_name="idx_active_users",
    partial_condition="status = 'active'"
)

# Query will use the partial index efficiently
active_users = await db.execute_query("""
    SELECT * FROM users WHERE status = 'active'
""")
```

### Expression Indexes

Index computed expressions for better performance:

```python
# Create expression index for case-insensitive email searches
await db.adapter.create_index(
    "users",
    ["LOWER(email)"],
    index_name="idx_email_lower"
)

# Query using the expression index
user = await db.execute_query("""
    SELECT * FROM users WHERE LOWER(email) = LOWER(?)
""", ["User@Example.com"])
```

### Composite Indexes

Multi-column indexes for complex queries:

```python
# Create composite index for order queries
await db.adapter.create_index(
    "orders",
    ["status", "created_at", "user_id"],
    index_name="idx_orders_composite"
)

# Efficient query using composite index
recent_orders = await db.execute_query("""
    SELECT * FROM orders
    WHERE status = 'completed'
    AND created_at > ?
    ORDER BY created_at DESC
""", ["2023-01-01"])
```

### Index Usage Monitoring

Track index effectiveness:

```python
# Get index usage statistics
stats = db.adapter.get_index_usage_statistics()

for index_name, usage_info in stats.items():
    print(f"Index: {index_name}")
    print(f"Usage Count: {usage_info['usage_count']}")
    print(f"Recommendation: {usage_info.get('recommendation', 'N/A')}")
```

## WAL Mode and Concurrency

### Enable WAL Mode

WAL (Write-Ahead Logging) mode enables concurrent reads:

```python
db = DataFlow(
    "sqlite:///concurrent.db",
    enable_wal=True,
    wal_autocheckpoint=1000,      # Checkpoint every 1000 pages
    wal_checkpoint_mode="PASSIVE" # Checkpoint mode
)
```

### WAL Performance Monitoring

Monitor WAL file growth and checkpoint efficiency:

```python
# Get WAL-specific metrics
from dataflow.performance.sqlite_monitor import SQLitePerformanceMonitor

monitor = SQLitePerformanceMonitor(db.adapter)
await monitor.start_monitoring()

# Get performance report including WAL metrics
report = monitor.get_performance_report()
wal_status = report.get("wal_status", {})

print(f"WAL Size: {wal_status.get('wal_size_mb', 0):.2f}MB")
print(f"Checkpoint Frequency: {wal_status.get('checkpoint_frequency_per_hour', 0):.1f}/hour")
```

### Manual WAL Checkpoints

Control WAL checkpointing manually:

```python
# Perform WAL checkpoint
success = await db.adapter._perform_wal_checkpoint("RESTART")
if success:
    print("WAL checkpoint completed successfully")

# Get checkpoint statistics
async with db.adapter._get_connection() as conn:
    cursor = await conn.execute("PRAGMA wal_checkpoint")
    result = await cursor.fetchone()
    busy, log_pages, checkpointed = result

    print(f"Log pages: {log_pages}, Checkpointed: {checkpointed}")
```

## Connection Pooling

### Pool Configuration

Configure intelligent connection pooling:

```python
db = DataFlow(
    "sqlite:///pooled.db",
    enable_connection_pooling=True,
    max_connections=20,              # Maximum pool size
    connection_pool_timeout=10.0,    # Pool acquisition timeout
    busy_timeout=30000               # SQLite busy timeout (30s)
)
```

### Pool Monitoring

Monitor connection pool performance:

```python
# Get connection pool statistics
pool_stats = db.adapter.connection_pool_stats

print(f"Active Connections: {pool_stats.active_connections}")
print(f"Idle Connections: {pool_stats.idle_connections}")
print(f"Average Connection Time: {pool_stats.avg_connection_time_ms:.2f}ms")
print(f"Connection Reuse Rate: {pool_stats.connection_reuse_rate:.2%}")
```

## Transaction Isolation and Savepoints

### Transaction Isolation Levels

SQLite supports three isolation levels:

```python
# DEFERRED (default) - start as reader, upgrade to writer if needed
async with db.adapter.transaction("DEFERRED") as tx:
    result = await tx.execute("SELECT * FROM users WHERE id = ?", [user_id])
    if result:
        await tx.execute("UPDATE users SET last_seen = ? WHERE id = ?",
                        [datetime.now(), user_id])

# IMMEDIATE - acquire writer lock immediately
async with db.adapter.transaction("IMMEDIATE") as tx:
    await tx.execute("INSERT INTO orders (user_id, amount) VALUES (?, ?)",
                    [user_id, amount])

# EXCLUSIVE - exclusive access to database
async with db.adapter.transaction("EXCLUSIVE") as tx:
    # Batch operations with exclusive access
    for item in batch_items:
        await tx.execute("INSERT INTO items (data) VALUES (?)", [item])
```

### Savepoints

Use savepoints for partial rollbacks:

```python
async with db.adapter.transaction() as tx:
    # Insert user
    await tx.execute("INSERT INTO users (email, name) VALUES (?, ?)",
                    [email, name])

    # Create savepoint before risky operation
    await tx.savepoint("before_profile")

    try:
        # Attempt to create profile
        await tx.execute("INSERT INTO profiles (user_id, data) VALUES (?, ?)",
                        [user_id, complex_data])

        # Release savepoint if successful
        await tx.release_savepoint("before_profile")

    except Exception as e:
        # Rollback to savepoint, keeping user creation
        await tx.rollback_to_savepoint("before_profile")
        print(f"Profile creation failed: {e}")
        # Transaction continues, user is still created
```

## Performance Monitoring

### Real-time Monitoring

Enable comprehensive performance monitoring:

```python
from dataflow.performance.sqlite_monitor import SQLitePerformanceMonitor

# Initialize monitor
monitor = SQLitePerformanceMonitor(
    db.adapter,
    monitoring_interval=60,           # Monitor every 60 seconds
    max_query_history=1000,          # Keep 1000 query records
    enable_continuous_monitoring=True # Run background monitoring
)

# Start monitoring
await monitor.start_monitoring()

# Monitor will automatically:
# - Track query performance
# - Monitor WAL file growth
# - Detect fragmentation
# - Generate optimization recommendations
```

### Query Performance Tracking

Track individual query performance:

```python
# Execute query with performance tracking
import time
start_time = time.time()

result = await db.execute_query("""
    SELECT u.name, COUNT(o.id) as order_count
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    WHERE u.status = 'active'
    GROUP BY u.id, u.name
    ORDER BY order_count DESC
""")

execution_time = (time.time() - start_time) * 1000

# Track the query performance
await monitor.track_query_performance(
    query="SELECT u.name, COUNT(o.id) FROM users u LEFT JOIN orders o...",
    execution_time_ms=execution_time,
    result_count=len(result)
)
```

### Performance Reports

Generate comprehensive performance reports:

```python
# Get detailed performance report
report = monitor.get_performance_report()

print(f"Total Queries Tracked: {report['performance_summary']['total_queries_tracked']}")
print(f"Average Query Time: {report['performance_summary']['average_query_time_ms']:.2f}ms")
print(f"Slow Queries: {report['performance_summary']['slow_queries']}")

# Check database health
health = report['database_health']
print(f"Database Size: {health['size_mb']:.2f}MB")
print(f"Fragmentation Status: {health['fragmentation_status']}")

# View optimization recommendations
for rec in report['optimization_recommendations']:
    print(f"Recommendation: {rec}")
```

## Query Optimization

### Query Plan Analysis

Analyze query execution plans:

```python
# Analyze query plan
plan = await db.adapter.analyze_query_plan("""
    SELECT * FROM orders
    WHERE user_id = ? AND status = 'pending'
    ORDER BY created_at DESC
""", [user_id])

print(f"Query Plan Steps: {len(plan['plan_steps'])}")
print(f"Uses Indexes: {plan['uses_indexes']}")
print(f"Full Table Scans: {plan['full_table_scans']}")

# View recommendations
for rec in plan['recommendations']:
    print(f"Optimization: {rec}")
```

### SQLite-Specific Optimizer

Use the SQLite query optimizer for comprehensive analysis:

```python
from dataflow.optimization.sqlite_optimizer import SQLiteQueryOptimizer

optimizer = SQLiteQueryOptimizer(database_path=db.adapter.database_path)

# Mock some optimization opportunities and current PRAGMA settings
current_pragmas = {
    "cache_size": "-32768",  # 32MB
    "journal_mode": "WAL",
    "mmap_size": "268435456"  # 256MB
}

database_stats = {
    "db_size_mb": 150.0,
    "fragmentation_ratio": 0.15,
    "wal_size_mb": 5.2
}

# Get comprehensive optimization analysis
optimization_result = optimizer.analyze_sqlite_optimization_opportunities(
    opportunities=[],        # Would come from workflow analyzer
    optimized_queries=[],    # Would come from query optimizer
    current_pragmas=current_pragmas,
    database_stats=database_stats
)

# Generate optimization report
report = optimizer.generate_sqlite_optimization_report(optimization_result)
print(report)
```

## Database Maintenance and Optimization

### Fragmentation Analysis

Monitor and analyze database fragmentation:

```python
# Get database size and fragmentation info
size_info = await db.adapter.get_database_size_info()

print(f"Database Size: {size_info['db_size_mb']:.2f}MB")
print(f"WAL Size: {size_info['wal_size_mb']:.2f}MB")
print(f"Total Pages: {size_info['page_count']}")
print(f"Free Pages: {size_info['free_pages']}")
print(f"Fragmentation: {size_info['fragmentation_ratio']:.1%}")

if size_info['fragmentation_ratio'] > 0.25:
    print("High fragmentation detected - VACUUM recommended")
```

### Database Optimization

Perform comprehensive database optimization:

```python
# Run full database optimization
optimization_result = await db.adapter.optimize_database(full_optimization=True)

if optimization_result['success']:
    print("Database optimization completed successfully")

    for operation in optimization_result['operations_performed']:
        print(f"✓ {operation}")

    # Check performance improvements
    improvements = optimization_result['performance_improvement']
    if 'database_size_reduction_percent' in improvements:
        reduction = improvements['database_size_reduction_percent']
        print(f"Database size reduced by {reduction:.1f}%")

    # View recommendations
    for rec in optimization_result['recommendations']:
        print(f"Recommendation: {rec}")
else:
    print(f"Optimization failed: {optimization_result.get('error', 'Unknown error')}")
```

### Vacuum Operations

Control vacuum operations:

```python
# Check if vacuum is needed
metrics = await db.adapter.get_performance_metrics()
if metrics.vacuum_needed:
    print(f"VACUUM recommended - {metrics.free_pages} free pages")

    # Perform vacuum
    vacuum_success = await db.adapter._perform_vacuum()
    if vacuum_success:
        print("VACUUM completed successfully")

        # Check results
        new_metrics = await db.adapter.get_performance_metrics()
        print(f"Pages after vacuum: {new_metrics.total_pages}")
        print(f"Free pages after vacuum: {new_metrics.free_pages}")
```

## PRAGMA Optimization

### Automatic PRAGMA Tuning

The enterprise adapter automatically optimizes PRAGMA settings:

```python
# View current PRAGMA settings
pragmas_to_check = [
    "cache_size", "journal_mode", "synchronous",
    "mmap_size", "temp_store", "auto_vacuum"
]

for pragma in pragmas_to_check:
    result = await db.execute_query(f"PRAGMA {pragma}")
    print(f"{pragma}: {result[0][pragma]}")
```

### Custom PRAGMA Settings

Override PRAGMA settings for specific needs:

```python
db = DataFlow(
    "sqlite:///custom.db",
    pragma_overrides={
        "cache_size": "-131072",      # 128MB cache
        "mmap_size": "1073741824",    # 1GB memory mapping
        "synchronous": "FULL",        # Maximum safety
        "secure_delete": "ON",        # Secure deletion
        "case_sensitive_like": "ON",  # Case-sensitive LIKE operations
    }
)
```

### PRAGMA Recommendations

Get PRAGMA optimization recommendations:

```python
recommendations = db.adapter.get_optimization_recommendations()

for rec in recommendations:
    print(f"PRAGMA Recommendation: {rec}")

# Example output:
# - Increase cache size for better performance: current=32MB, recommended=64MB+
# - Enable memory-mapped I/O for better performance: mmap_size=268435456 (256MB)
```

## Best Practices

### For High-Performance Applications

```python
# Optimized configuration for high-performance scenarios
db = DataFlow(
    "sqlite:///high_performance.db",
    enable_wal=True,                    # Concurrent reads
    enable_connection_pooling=True,     # Connection reuse
    enable_performance_monitoring=True, # Track performance
    cache_size_mb=128,                 # Large cache
    max_connections=50,                # Large pool
    page_size=8192,                    # Larger pages for I/O efficiency
    auto_vacuum="INCREMENTAL",         # Prevent bloat
    pragma_overrides={
        "synchronous": "NORMAL",        # Balance safety/performance
        "mmap_size": "1073741824",     # 1GB memory mapping
        "temp_store": "MEMORY",        # Fast temp operations
        "optimize": "1"                # Enable query optimizer
    }
)
```

### For Multi-User Applications

```python
# Configuration for concurrent access
db = DataFlow(
    "sqlite:///multi_user.db",
    enable_wal=True,                   # Essential for concurrency
    isolation_level="IMMEDIATE",       # Reduce lock contention
    busy_timeout=30000,               # 30s busy timeout
    wal_autocheckpoint=500,           # Frequent checkpoints
    max_connections=20,               # Reasonable pool size
    pragma_overrides={
        "synchronous": "NORMAL",       # Good balance
        "cache_size": "-65536"        # 64MB cache
    }
)
```

### For Data Analytics

```python
# Configuration for analytical workloads
db = DataFlow(
    "sqlite:///analytics.db",
    enable_wal=True,
    cache_size_mb=256,                # Large cache for complex queries
    page_size=8192,                   # Efficient I/O for large datasets
    temp_store="MEMORY",              # Fast temporary operations
    pragma_overrides={
        "mmap_size": "2147483648",    # 2GB memory mapping
        "synchronous": "NORMAL",      # Performance over absolute safety
        "query_optimizer": "1"        # Enable all optimizations
    }
)

# Create indexes optimized for analytical queries
await db.adapter.create_index("events", ["date", "event_type"])
await db.adapter.create_index("events", ["user_id", "date"])

# Partial index for active events only
await db.adapter.create_index(
    "events",
    ["event_type"],
    partial_condition="processed = 0"
)
```

## Monitoring and Alerting

### Set Up Alerts

Configure performance monitoring with alerts:

```python
monitor = SQLitePerformanceMonitor(
    db.adapter,
    monitoring_interval=30,  # Check every 30 seconds
    enable_continuous_monitoring=True
)

# Configure alert thresholds
monitor.alert_thresholds.update({
    "slow_query_ms": 500,           # Alert on queries > 500ms
    "fragmentation_ratio": 0.20,    # Alert on > 20% fragmentation
    "wal_size_mb": 50,              # Alert on WAL > 50MB
    "connection_pool_wait_ms": 100   # Alert on pool waits > 100ms
})

await monitor.start_monitoring()

# Monitor will log warnings when thresholds are exceeded
```

### Export Performance Data

Export performance data for external analysis:

```python
# Export to JSON file
success = monitor.export_performance_data("performance_data.json")

# Or get structured data
performance_data = {
    "timestamp": datetime.now().isoformat(),
    "database_metrics": await db.adapter.get_performance_metrics(),
    "query_stats": monitor.query_metrics,
    "recommendations": monitor.optimization_recommendations
}

# Send to monitoring system
await send_to_monitoring_system(performance_data)
```

## Troubleshooting

### Common Issues and Solutions

**High WAL file size:**
```python
# Check WAL size and perform checkpoint
metrics = await db.adapter.get_performance_metrics()
if metrics.wal_size_mb > 100:  # 100MB threshold
    await db.adapter._perform_wal_checkpoint("RESTART")
```

**Database fragmentation:**
```python
# Check fragmentation and run VACUUM if needed
size_info = await db.adapter.get_database_size_info()
if size_info['fragmentation_ratio'] > 0.25:
    await db.adapter._perform_vacuum()
```

**Slow queries:**
```python
# Analyze slow queries and get recommendations
plan = await db.adapter.analyze_query_plan(slow_query, params)
for rec in plan['recommendations']:
    print(f"Optimization suggestion: {rec}")
```

**Connection pool exhaustion:**
```python
# Monitor pool usage and adjust if needed
stats = db.adapter.connection_pool_stats
if stats.avg_connection_time_ms > 1000:  # 1 second wait
    # Consider increasing max_connections or optimizing queries
    print("Consider increasing connection pool size")
```

## Migration from Basic SQLite

To migrate from basic SQLite to enterprise features:

1. **Update connection string:**
```python
# Before
db = DataFlow("sqlite:///app.db")

# After
db = DataFlow(
    "sqlite:///app.db",
    enable_wal=True,
    enable_connection_pooling=True,
    enable_performance_monitoring=True
)
```

2. **Add performance monitoring:**
```python
from dataflow.performance.sqlite_monitor import SQLitePerformanceMonitor

monitor = SQLitePerformanceMonitor(db.adapter)
await monitor.start_monitoring()
```

3. **Optimize existing indexes:**
```python
# Review existing indexes
stats = db.adapter.get_index_usage_statistics()

# Add partial indexes for selective queries
await db.adapter.create_index(
    "users",
    ["status"],
    partial_condition="status = 'active'"
)
```

4. **Enable WAL mode (requires database restart):**
```python
# WAL mode is enabled automatically with enable_wal=True
# Existing connections should be closed before switching
```

The SQLite Enterprise features provide production-ready database capabilities while maintaining SQLite's simplicity and zero-configuration benefits. These features enable SQLite to scale to enterprise workloads with proper monitoring, optimization, and maintenance capabilities.

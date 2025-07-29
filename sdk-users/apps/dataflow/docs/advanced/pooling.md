# DataFlow Connection Pooling

Advanced guide to connection pooling and resource management in DataFlow.

## Overview

DataFlow provides sophisticated connection pooling to maximize database performance while minimizing resource usage. Connection pooling is critical for production applications handling concurrent requests.

## Default Configuration

### Basic Pool Settings

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash_dataflow import DataFlow, DataFlowConfig

# Default configuration
db = DataFlow()  # Uses sensible defaults

# Custom configuration
config = DataFlowConfig(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=20,              # Number of persistent connections
    pool_max_overflow=30,      # Maximum overflow connections
    pool_recycle=3600,         # Recycle connections after 1 hour
    pool_pre_ping=True,        # Test connections before use
    pool_timeout=30.0          # Connection timeout in seconds
)

db = DataFlow(config=config)
```

### Per-Database Defaults

```python
# PostgreSQL optimized settings
postgres_config = DataFlowConfig(
    database_url="postgresql://...",
    pool_size=20,
    pool_max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    statement_cache_size=1200  # PostgreSQL prepared statements
)

# MySQL optimized settings
mysql_config = DataFlowConfig(
    database_url="mysql://...",
    pool_size=30,              # MySQL handles more connections
    pool_max_overflow=50,
    pool_recycle=7200,         # MySQL connections last longer
    pool_pre_ping=True,
    isolation_level="READ_COMMITTED"
)

# SQLite settings (no pooling needed)
sqlite_config = DataFlowConfig(
    database_url="sqlite:///./data.db",
    pool_size=1,               # SQLite is single-threaded
    pool_max_overflow=0,
    check_same_thread=False
)
```

## Advanced Pool Configuration

### Dynamic Pool Sizing

```python
# Adjust pool size based on environment
import os

def get_pool_config():
    """Calculate pool size based on deployment environment."""
    cpu_count = os.cpu_count() or 4

    if os.getenv("ENVIRONMENT") == "production":
        return DataFlowConfig(
            pool_size=cpu_count * 4,        # 4 connections per CPU
            pool_max_overflow=cpu_count * 6,
            pool_recycle=1800,              # 30 minutes in production
            pool_pre_ping=True
        )
    else:
        return DataFlowConfig(
            pool_size=5,
            pool_max_overflow=10,
            pool_recycle=3600
        )

db = DataFlow(config=get_pool_config())
```

### Connection Lifecycle Hooks

```python
@db.on_connect
def configure_connection(connection, connection_record):
    """Configure each new connection."""
    # PostgreSQL: Set search path
    if db.dialect == "postgresql":
        connection.execute("SET search_path TO myapp, public")

    # MySQL: Set timezone
    elif db.dialect == "mysql":
        connection.execute("SET time_zone = '+00:00'")

    # Set application name for monitoring
    connection.execute(f"SET application_name = 'dataflow-{os.getpid()}'")

@db.on_checkout
def on_checkout(connection, connection_record, connection_proxy):
    """Called when connection is checked out from pool."""
    # Track connection usage
    connection_record.info['checkout_time'] = time.time()

    # Set transaction isolation if needed
    if hasattr(connection_proxy, '_isolation_level'):
        connection.execute(
            f"SET TRANSACTION ISOLATION LEVEL {connection_proxy._isolation_level}"
        )

@db.on_checkin
def on_checkin(connection, connection_record):
    """Called when connection is returned to pool."""
    # Calculate usage time
    checkout_time = connection_record.info.get('checkout_time', 0)
    usage_time = time.time() - checkout_time

    # Log slow connection usage
    if usage_time > 5.0:
        logger.warning(f"Connection held for {usage_time:.2f} seconds")
```

## Pool Monitoring

### Real-Time Metrics

```python
# Monitor pool health
workflow = WorkflowBuilder()

workflow.add_node("PoolMetricsNode", "get_metrics", {
    "metrics": [
        "active_connections",
        "idle_connections",
        "overflow_connections",
        "wait_time_avg",
        "wait_time_max",
        "connection_errors"
    ]
})

workflow.add_node("PythonCodeNode", "analyze_metrics", {
    "code": """
metrics = get_input_data("get_metrics")

# Check pool health
pool_usage = metrics["active_connections"] / metrics["pool_size"]
if pool_usage > 0.8:
    result = {
        "alert": "high_pool_usage",
        "usage_percent": pool_usage * 100,
        "recommendation": "increase_pool_size"
    }
elif metrics["wait_time_max"] > 1.0:
    result = {
        "alert": "slow_connection_acquisition",
        "wait_time": metrics["wait_time_max"],
        "recommendation": "increase_pool_size"
    }
else:
    result = {"status": "healthy"}
"""
})
```

### Pool Statistics

```python
# Get detailed pool statistics
stats = db.get_pool_stats()

print(f"Pool Size: {stats['size']}")
print(f"Checked Out: {stats['checked_out']}")
print(f"Overflow: {stats['overflow']}")
print(f"Total: {stats['total']}")
print(f"Wait Queue: {stats['wait_queue']}")

# Enable detailed logging
import logging
logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)
```

## Performance Optimization

### Connection Strategies

```python
# 1. Read Replica Pool
read_pool_config = DataFlowConfig(
    database_url="postgresql://read-replica.db/myapp",
    pool_size=40,         # More connections for read-heavy workloads
    pool_max_overflow=60,
    pool_recycle=7200    # Read replicas are more stable
)

# 2. Write Master Pool
write_pool_config = DataFlowConfig(
    database_url="postgresql://master.db/myapp",
    pool_size=10,         # Fewer connections to reduce master load
    pool_max_overflow=15,
    pool_recycle=1800    # More frequent recycling for consistency
)

# 3. Analytics Pool (long queries)
analytics_pool_config = DataFlowConfig(
    database_url="postgresql://analytics.db/myapp",
    pool_size=5,          # Few connections, long-running queries
    pool_timeout=300.0,   # 5 minute timeout for analytics
    pool_recycle=0       # No recycling for long queries
)
```

### Workflow Pool Management

```python
# Optimize pool usage in workflows
workflow = WorkflowBuilder()

# Use connection pooling efficiently
workflow.add_node("TransactionContextNode", "start_batch", {
    "connection_pool": "batch_pool",  # Use dedicated pool
    "timeout": 60.0
})

# Batch operations to reduce connection usage
workflow.add_node("UserBulkCreateNode", "batch_create", {
    "data": users_list,
    "batch_size": 1000,  # Process in batches
    "use_connection": ":batch_connection"  # Reuse connection
})

# Release connection promptly
workflow.add_node("ConnectionReleaseNode", "release", {
    "connection": ":batch_connection"
})
```

## Troubleshooting

### Pool Exhaustion

```python
# Handle pool exhaustion gracefully
@db.error_handler
def handle_pool_timeout(error, context):
    """Handle connection pool timeouts."""
    if isinstance(error, PoolTimeoutError):
        # Log detailed information
        logger.error(f"Pool exhausted: {db.get_pool_stats()}")

        # Try emergency overflow
        if context.get("retry_count", 0) < 3:
            return {
                "action": "retry",
                "delay": 1.0,
                "use_overflow": True
            }
        else:
            # Queue for later processing
            return {
                "action": "queue",
                "priority": "low",
                "reason": "pool_exhausted"
            }
```

### Connection Leaks

```python
# Detect and fix connection leaks
workflow.add_node("ConnectionLeakDetectorNode", "detect_leaks", {
    "check_interval": 60,  # Check every minute
    "leak_threshold": 300,  # Connections older than 5 minutes
    "action": "log_and_recycle"
})

# Monitor long-running connections
workflow.add_node("PythonCodeNode", "monitor_connections", {
    "code": """
active_connections = db.get_active_connections()
for conn in active_connections:
    if conn.age > 300:  # 5 minutes
        logger.warning(f"Long-running connection: {conn.info}")
        if conn.age > 600:  # 10 minutes
            # Force recycle
            conn.invalidate()
"""
})
```

### Database-Specific Issues

```python
# PostgreSQL: Handle prepared statement overflow
if db.dialect == "postgresql":
    config.statement_cache_size = 2000  # Increase cache

    @db.on_connect
    def configure_pg(connection, record):
        # Disable prepared statements if needed
        connection.execute("SET plan_cache_mode = 'force_generic_plan'")

# MySQL: Handle connection timeout
if db.dialect == "mysql":
    config.pool_recycle = 3500  # Below MySQL timeout (3600)

    @db.on_connect
    def configure_mysql(connection, record):
        # Set interactive timeout
        connection.execute("SET SESSION interactive_timeout = 28800")
```

## Best Practices

### 1. Size Pool Appropriately

```python
# Calculate optimal pool size
def calculate_pool_size():
    """
    Formula: pool_size = (core_count * 2) + effective_spindle_count
    For SSDs, effective_spindle_count = 1
    """
    import os

    cpu_cores = os.cpu_count() or 4
    ssd_spindles = 1  # Assuming SSD storage

    # Base calculation
    pool_size = (cpu_cores * 2) + ssd_spindles

    # Adjust for workload
    if os.getenv("WORKLOAD_TYPE") == "read_heavy":
        pool_size = int(pool_size * 1.5)
    elif os.getenv("WORKLOAD_TYPE") == "write_heavy":
        pool_size = int(pool_size * 0.75)

    return max(pool_size, 10)  # Minimum 10 connections
```

### 2. Monitor Pool Health

```python
# Continuous pool monitoring
workflow.add_node("SchedulerNode", "monitor_schedule", {
    "interval": "1m",
    "target": "check_pool_health"
})

workflow.add_node("PythonCodeNode", "check_pool_health", {
    "code": """
stats = db.get_pool_stats()
metrics = {
    "pool_efficiency": stats["checked_out"] / stats["size"],
    "overflow_usage": stats["overflow"] / stats["overflow_max"],
    "wait_queue_depth": stats["wait_queue"]
}

# Alert on issues
if metrics["pool_efficiency"] > 0.9:
    send_alert("Pool near capacity", metrics)
elif metrics["wait_queue_depth"] > 5:
    send_alert("Connection queue building", metrics)
"""
})
```

### 3. Use Connection Context

```python
# Always use connection context managers
workflow.add_node("PythonCodeNode", "safe_connection_use", {
    "code": """
# Good: Automatic connection management
with db.connection() as conn:
    result = conn.execute("SELECT * FROM users")
    # Connection automatically returned to pool

# Bad: Manual connection management
# conn = db.get_connection()
# result = conn.execute("SELECT * FROM users")
# # Risk: Forgetting to return connection
"""
})
```

### 4. Test Pool Configuration

```python
# Load test pool configuration
def test_pool_performance():
    """Test pool under load."""
    import concurrent.futures
    import time

    def worker(worker_id):
        start = time.time()
        workflow = WorkflowBuilder()
        workflow.add_node("UserListNode", "query", {
            "filter": {"active": True},
            "limit": 100
        })
        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        return time.time() - start

    # Simulate concurrent load
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(worker, i) for i in range(100)]
        times = [f.result() for f in futures]

    print(f"Average response time: {sum(times) / len(times):.3f}s")
    print(f"Max response time: {max(times):.3f}s")
    print(f"Pool stats: {db.get_pool_stats()}")
```

## Next Steps

- **Read/Write Splitting**: [Read/Write Split Guide](read-write-split.md)
- **Performance Tuning**: [Performance Guide](../production/performance.md)
- **Monitoring**: [Monitoring Guide](monitoring.md)

Proper connection pooling is essential for high-performance DataFlow applications. Configure pools based on your workload and monitor continuously.

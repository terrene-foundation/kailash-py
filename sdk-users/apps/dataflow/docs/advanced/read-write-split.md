# DataFlow Read/Write Splitting

Advanced guide to implementing read/write splitting for database scalability.

## Overview

Read/write splitting directs read queries to replica databases and write queries to the primary database. This pattern significantly improves performance for read-heavy applications.

## Basic Configuration

### Simple Read/Write Split

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash_dataflow import DataFlow, DataFlowConfig

# Primary (write) database
write_config = DataFlowConfig(
    database_url="postgresql://primary.db.com/myapp",
    pool_size=10,
    pool_max_overflow=15
)

# Read replica databases
read_config = DataFlowConfig(
    database_url="postgresql://replica.db.com/myapp",
    pool_size=30,  # More connections for read traffic
    pool_max_overflow=50
)

# Initialize with read/write split
db = DataFlow(
    write_config=write_config,
    read_config=read_config,
    read_preference="replica"  # Default to replica for reads
)
```

### Multiple Read Replicas

```python
# Configure multiple read replicas with load balancing
read_replicas = [
    {
        "url": "postgresql://replica1.db.com/myapp",
        "weight": 2,  # Gets 2x traffic
        "region": "us-east-1"
    },
    {
        "url": "postgresql://replica2.db.com/myapp",
        "weight": 1,
        "region": "us-west-2"
    },
    {
        "url": "postgresql://replica3.db.com/myapp",
        "weight": 1,
        "region": "eu-west-1"
    }
]

db = DataFlow(
    write_url="postgresql://primary.db.com/myapp",
    read_replicas=read_replicas,
    load_balance_strategy="weighted_round_robin",
    replica_selection="nearest"  # Use geographically closest
)
```

## Workflow Integration

### Automatic Read/Write Routing

```python
workflow = WorkflowBuilder()

# Read operations automatically use replicas
workflow.add_node("UserListNode", "list_users", {
    "filter": {"active": True},
    "limit": 100
    # Automatically routed to read replica
})

# Write operations use primary
workflow.add_node("UserCreateNode", "create_user", {
    "name": "New User",
    "email": "user@example.com"
    # Automatically routed to primary
})

# Force primary for read-after-write consistency
workflow.add_node("UserReadNode", "read_created", {
    "id": ":user_id",
    "force_primary": True  # Read from primary
})
```

### Explicit Database Selection

```python
# Explicitly specify database
workflow.add_node("UserListNode", "analytics_query", {
    "filter": {"created_at": {"$gte": "2024-01-01"}},
    "database": "analytics_replica",  # Use specific replica
    "timeout": 300.0  # Long timeout for analytics
})

# Use primary for critical reads
workflow.add_node("AccountReadNode", "get_balance", {
    "id": account_id,
    "database": "primary",  # Financial data from primary
    "lock_for_update": True
})
```

## Consistency Patterns

### Read-After-Write Consistency

```python
workflow = WorkflowBuilder()

# Track write timestamp
workflow.add_node("UserUpdateNode", "update_user", {
    "id": user_id,
    "data": {"status": "active"},
    "track_write_time": True  # Store write timestamp
})

# Ensure read consistency
workflow.add_node("ConsistencyNode", "ensure_consistency", {
    "write_timestamp": ":write_timestamp",
    "max_lag": 1.0  # Maximum 1 second lag
})

# Read with consistency check
workflow.add_node("UserReadNode", "read_user", {
    "id": user_id,
    "min_timestamp": ":write_timestamp",  # Wait for replication
    "fallback_to_primary": True
})
```

### Session Consistency

```python
# Maintain consistency within a session
@db.session_handler
class ConsistentSession:
    def __init__(self):
        self.last_write_time = None
        self.sticky_primary = False

    def on_write(self, operation, timestamp):
        """Track writes in session."""
        self.last_write_time = timestamp
        if operation in ["create", "update", "delete"]:
            self.sticky_primary = True  # Stick to primary

    def get_read_preference(self):
        """Determine where to read from."""
        if self.sticky_primary:
            return "primary"
        elif self.last_write_time:
            # Check replica lag
            if time.time() - self.last_write_time < 2.0:
                return "primary"  # Recent write, use primary
        return "replica"

# Use in workflow
workflow.add_node("SessionAwareReadNode", "read_data", {
    "table": "users",
    "session_consistency": True
})
```

## Monitoring and Health Checks

### Replica Lag Monitoring

```python
workflow = WorkflowBuilder()

# Monitor replication lag
workflow.add_node("ReplicaLagMonitorNode", "check_lag", {
    "replicas": ["replica1", "replica2", "replica3"],
    "warning_threshold": 1.0,   # 1 second warning
    "critical_threshold": 5.0   # 5 second critical
})

workflow.add_node("PythonCodeNode", "handle_lag", {
    "code": """
lag_data = get_input_data("check_lag")

for replica, lag in lag_data.items():
    if lag > 5.0:
        # Remove replica from rotation
        db.disable_replica(replica)
        alert_ops(f"Replica {replica} lag critical: {lag}s")
    elif lag > 1.0:
        # Reduce replica weight
        db.adjust_replica_weight(replica, 0.5)
        logger.warning(f"Replica {replica} lag warning: {lag}s")
"""
})
```

### Automatic Failover

```python
# Configure automatic failover
db = DataFlow(
    write_url="postgresql://primary.db.com/myapp",
    read_replicas=read_replicas,
    health_check_interval=10,  # Check every 10 seconds
    failover_policy={
        "max_failures": 3,
        "failure_window": 60,  # Within 1 minute
        "recovery_time": 300   # Wait 5 minutes before retry
    }
)

# Health check implementation
@db.health_check
def check_replica_health(replica_url):
    """Custom health check for replicas."""
    try:
        with db.connect(replica_url) as conn:
            # Check basic connectivity
            result = conn.execute("SELECT 1")

            # Check replication status
            lag = conn.execute("""
                SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))
                AS lag_seconds
            """).scalar()

            return {
                "healthy": lag < 10.0,  # Less than 10 seconds lag
                "lag": lag,
                "timestamp": time.time()
            }
    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
            "timestamp": time.time()
        }
```

## Advanced Patterns

### Geographic Distribution

```python
# Region-aware read routing
workflow.add_node("GeoAwareRouterNode", "setup_routing", {
    "user_region": ":user_region",
    "replica_regions": {
        "replica1": "us-east-1",
        "replica2": "us-west-2",
        "replica3": "eu-west-1"
    },
    "fallback_strategy": "nearest_available"
})

workflow.add_node("UserListNode", "region_read", {
    "filter": {"region": ":user_region"},
    "preferred_replica": ":selected_replica"
})
```

### Query-Based Routing

```python
# Route queries based on complexity
@db.query_router
def smart_query_router(query, params):
    """Route queries based on analysis."""
    # Analyze query
    if "COUNT(*)" in query or "SUM(" in query:
        # Analytics queries to dedicated replica
        return "analytics_replica"
    elif "FOR UPDATE" in query or "LOCK" in query:
        # Locking queries to primary
        return "primary"
    elif "JOIN" in query and query.count("JOIN") > 3:
        # Complex queries to powerful replica
        return "powerful_replica"
    else:
        # Default read routing
        return "auto"

# Use in workflow
workflow.add_node("CustomQueryNode", "complex_query", {
    "query": """
        SELECT u.*, COUNT(o.id) as order_count
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id
        HAVING COUNT(o.id) > 10
    """,
    "use_query_router": True
})
```

### Split by Table

```python
# Configure per-table routing rules
table_routing = {
    # Financial tables always use primary
    "accounts": "primary",
    "transactions": "primary",
    "audit_logs": "primary",

    # Read-heavy tables use replicas
    "products": "replica",
    "categories": "replica",
    "reviews": "replica",

    # Analytics tables use dedicated replica
    "user_analytics": "analytics_replica",
    "product_metrics": "analytics_replica"
}

db = DataFlow(
    write_url=primary_url,
    read_replicas=replicas,
    table_routing=table_routing
)
```

## Performance Optimization

### Connection Pooling per Database

```python
# Optimize pools for each database role
primary_pool = DataFlowConfig(
    pool_size=15,      # Smaller pool for primary
    pool_timeout=5.0,  # Quick timeout
    pool_recycle=1800  # 30 minutes
)

replica_pool = DataFlowConfig(
    pool_size=50,      # Larger pool for read traffic
    pool_timeout=10.0, # More lenient timeout
    pool_recycle=7200  # 2 hours
)

analytics_pool = DataFlowConfig(
    pool_size=10,       # Few connections
    pool_timeout=300.0, # Long timeout for analytics
    pool_recycle=0      # No recycling
)
```

### Query Result Caching

```python
# Cache read results from replicas
workflow.add_node("CachedReadNode", "cached_list", {
    "node_type": "UserListNode",
    "cache_key": "active_users",
    "cache_ttl": 300,  # 5 minutes
    "cache_on_replica": True,
    "invalidate_on_write": True
})
```

## Testing Read/Write Split

### Unit Testing

```python
# Test read/write routing
def test_read_write_routing():
    # Mock databases
    with db.test_mode() as test_db:
        test_db.mock_primary("primary_db")
        test_db.mock_replica("replica_db")

        # Test write goes to primary
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", {"name": "Test"})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        assert test_db.get_query_log("primary_db").count("INSERT") == 1
        assert test_db.get_query_log("replica_db").count("INSERT") == 0

        # Test read goes to replica
        workflow = WorkflowBuilder()
        workflow.add_node("UserListNode", "list", {})

        results, _ = runtime.execute(workflow.build())

        assert test_db.get_query_log("replica_db").count("SELECT") == 1
        assert test_db.get_query_log("primary_db").count("SELECT") == 0
```

### Load Testing

```python
# Test under load
def load_test_split():
    import concurrent.futures
    import time

    def read_worker():
        workflow = WorkflowBuilder()
        workflow.add_node("UserListNode", "read", {"limit": 100})
        runtime = LocalRuntime()
        start = time.time()
        runtime.execute(workflow.build())
        return time.time() - start

    def write_worker():
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "write", {
            "name": f"User-{time.time()}",
            "email": f"user-{time.time()}@test.com"
        })
        runtime = LocalRuntime()
        start = time.time()
        runtime.execute(workflow.build())
        return time.time() - start

    # Run mixed workload
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        # 90% reads, 10% writes
        read_futures = [executor.submit(read_worker) for _ in range(900)]
        write_futures = [executor.submit(write_worker) for _ in range(100)]

        read_times = [f.result() for f in read_futures]
        write_times = [f.result() for f in write_futures]

    print(f"Average read time: {sum(read_times) / len(read_times):.3f}s")
    print(f"Average write time: {sum(write_times) / len(write_times):.3f}s")
    print(f"Primary connections: {db.get_primary_stats()}")
    print(f"Replica connections: {db.get_replica_stats()}")
```

## Best Practices

1. **Monitor Replication Lag**: Always track and handle replica lag
2. **Use Appropriate Consistency**: Choose consistency level based on use case
3. **Test Failover**: Regularly test replica failover scenarios
4. **Cache Aggressively**: Cache read results to reduce replica load
5. **Profile Query Patterns**: Route queries based on actual patterns

## Next Steps

- **Multi-Tenant**: [Multi-Tenant Guide](multi-tenant.md)
- **Performance**: [Performance Guide](../production/performance.md)
- **Monitoring**: [Monitoring Guide](monitoring.md)

Read/write splitting is essential for scaling DataFlow applications. Implement carefully with proper monitoring and consistency guarantees.

# AsyncSQL Advanced Patterns - Deep Dive

*Comprehensive guide to AsyncSQLDatabaseNode's advanced features including health monitoring, custom type handling, batch operations, and enterprise patterns*

> **Note**: This document covers both built-in AsyncSQLDatabaseNode features and implementation patterns:
> - **[Built-in]**: Features directly available in AsyncSQLDatabaseNode
> - **[Pattern]**: Implementation patterns using existing SDK capabilities
> - **[Custom Implementation]**: Code you need to write yourself

## 🚀 Table of Contents

1. [Health Monitoring & Pool Management](#health-monitoring--pool-management)
2. [Advanced Type Handling](#advanced-type-handling)
3. [Batch Operations & Performance](#batch-operations--performance)
4. [Custom Result Formatters](#custom-result-formatters)
5. [Query Timeout & Cancellation](#query-timeout--cancellation)
6. [Advanced Transaction Patterns](#advanced-transaction-patterns)
7. [Connection String Security](#connection-string-security)
8. [Error Recovery Patterns](#error-recovery-patterns)
9. [Monitoring & Metrics](#monitoring--metrics)
10. [Integration Patterns](#integration-patterns)

## Health Monitoring & Pool Management [Pattern]

### Automatic Health Checks
```python
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# Configure node with health monitoring
# Health checks use pool-level command_timeout for timeout protection
node = AsyncSQLDatabaseNode(
    name="monitored_db",
    database_type="postgresql",
    host="db.production.internal",
    database="prod_app",
    command_timeout=60.0,  # Pool-level timeout for all queries (including health checks)
    enable_health_checks=True,  # Enable automatic health monitoring
    share_pool=True
)

# Health checks run automatically using "SELECT 1" query
# Pool-level command_timeout provides timeout protection
# No need for per-query timeout parameters

# Monitor pool health
health_status = await node.get_pool_health()
print(f"Pool healthy: {health_status['healthy']}")
print(f"Active connections: {health_status['active_connections']}")
print(f"Idle connections: {health_status['idle_connections']}")
print(f"Failed checks: {health_status['failed_health_checks']}")
```

### Dynamic Pool Resizing
```python
# Adaptive pool configuration
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    pool_size=5,           # Start with 5 connections
    max_pool_size=50,      # Can grow to 50 under load
    pool_resize_interval=60,  # Check every minute
    pool_resize_factor=1.5,   # Grow by 50% when needed
    pool_idle_timeout=300     # Close idle connections after 5 min
)

# Manual pool adjustment
await node.resize_pool(new_size=20)  # Immediately resize
await node.shrink_pool()  # Remove idle connections
```

## Advanced Type Handling [Built-in]

### Custom Type Serializers
```python
from decimal import Decimal
from uuid import UUID
import numpy as np

# Register custom type handlers
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    custom_type_handlers={
        UUID: lambda x: str(x),
        Decimal: lambda x: float(x),
        np.ndarray: lambda x: x.tolist(),
        bytes: lambda x: base64.b64encode(x).decode('utf-8')
    }
)

# Complex data type handling
await node.async_run(
    query="""
        INSERT INTO analytics (
            id, metrics, binary_data, computation_result
        ) VALUES (
            :id::uuid,
            :metrics::jsonb,
            :binary_data::bytea,
            :result::numeric[]
        )
    """,
    params={
        "id": UUID("550e8400-e29b-41d4-a716-446655440000"),
        "metrics": {"cpu": 0.75, "memory": 0.82},
        "binary_data": b"\x00\x01\x02\x03",
        "result": np.array([1.5, 2.7, 3.9])
    }
)
```

### PostgreSQL-Specific Array Handling
```python
# Advanced array operations
await node.async_run(
    query="""
        WITH user_groups AS (
            SELECT unnest(:groups::text[]) as group_name
        )
        SELECT u.*, array_agg(g.permission) as permissions
        FROM users u
        JOIN user_groups ug ON true
        JOIN group_permissions g ON g.group_name = ug.group_name
        WHERE u.id = ANY(:user_ids::integer[])
        GROUP BY u.id
    """,
    params={
        "groups": ["admin", "editor", "viewer"],
        "user_ids": [1, 2, 3, 4, 5]
    }
)

# Array containment checks
await node.async_run(
    query="""
        SELECT * FROM products
        WHERE tags @> :required_tags::text[]
        AND NOT (tags && :excluded_tags::text[])
    """,
    params={
        "required_tags": ["electronics", "sale"],
        "excluded_tags": ["discontinued", "recalled"]
    }
)
```

## Batch Operations & Performance

### Efficient Batch Processing [Mixed: execute_many_async is built-in, others are patterns]
```python
# High-performance batch inserts
batch_data = [
    {"name": f"User {i}", "email": f"user{i}@example.com", "score": i * 10}
    for i in range(10000)
]

# Method 1: Built-in execute_many_async (recommended)
result = await node.execute_many_async(
    query="INSERT INTO users (name, email, score) VALUES (:name, :email, :score)",
    params_list=batch_data
)
print(f"Inserted {result['result']['affected_rows']} rows")

# Method 2: COPY for maximum performance (PostgreSQL)
await node.copy_from_records(
    table="users",
    records=batch_data,
    columns=["name", "email", "score"],
    format="binary"  # Fastest format
)

# Method 3: Multi-row insert with UNNEST (PostgreSQL)
await node.async_run(
    query="""
        INSERT INTO users (name, email, score)
        SELECT * FROM unnest(
            :names::text[],
            :emails::text[],
            :scores::integer[]
        )
    """,
    params={
        "names": [r["name"] for r in batch_data],
        "emails": [r["email"] for r in batch_data],
        "scores": [r["score"] for r in batch_data]
    }
)
```

### Streaming Large Results [Pattern]
```python
# Stream results for memory efficiency
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="analytics",
    cursor_size=1000  # Fetch 1000 rows at a time
)

# Async iterator for large datasets
async def process_large_dataset():
    total_processed = 0

    async for batch in node.stream_query(
        query="SELECT * FROM events WHERE created_at > :start_date",
        params={"start_date": "2024-01-01"},
        batch_size=1000
    ):
        # Process batch without loading entire result set
        for row in batch:
            await process_event(row)
            total_processed += 1

        print(f"Processed {total_processed} events...")

        # Optional: Add backpressure control
        if total_processed % 10000 == 0:
            await asyncio.sleep(0.1)  # Brief pause
```

## Custom Result Formatters [Pattern]

### Dataframe Integration
```python
# Configure result formatting
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="analytics",
    result_format="dataframe",  # Return pandas DataFrame
    dataframe_config={
        "parse_dates": ["created_at", "updated_at"],
        "index_col": "id",
        "dtype": {"score": "float32", "count": "int32"}
    }
)

# Direct DataFrame results
result = await node.async_run(
    query="SELECT * FROM metrics WHERE date >= :start_date",
    params={"start_date": "2024-01-01"}
)

df = result["result"]["dataframe"]
# Now you can use pandas operations directly
monthly_avg = df.groupby(pd.Grouper(freq='M'))['value'].mean()
```

### Custom Result Transformers
```python
# Register custom result transformer
def pivot_transformer(rows: list[dict]) -> dict:
    """Transform rows into pivoted structure."""
    result = {}
    for row in rows:
        category = row.pop('category')
        if category not in result:
            result[category] = []
        result[category].append(row)
    return result

node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    result_transformer=pivot_transformer
)

# Results automatically transformed
result = await node.async_run(
    query="SELECT category, name, value FROM products"
)
# result["result"]["data"] is now pivoted by category
```

## Query Timeout & Cancellation [Built-in]

### Pool-Level Timeout Control
```python
# Configure pool-level timeout for all queries
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    connection_timeout=5.0,    # Connection establishment timeout
    command_timeout=30.0,      # Pool-level timeout applied to ALL queries
    pool_timeout=10.0,         # Timeout for acquiring connection from pool
)

# All queries inherit the pool-level command_timeout
# For longer-running queries, configure appropriate command_timeout at node creation
result = await node.async_run(
    query="SELECT * FROM generate_large_report(:params)",
    params={"year": 2024}
    # No per-query timeout parameter - use pool-level command_timeout
)

# Cancellable operations
async def cancellable_query():
    task = asyncio.create_task(
        node.async_run(
            query="SELECT pg_sleep(60)",  # Long running query
            cancellable=True
        )
    )

    # Cancel after 5 seconds
    await asyncio.sleep(5)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        print("Query cancelled successfully")
```

### Statement Timeout (PostgreSQL)
```python
# Set statement timeout at session level
await node.async_run(
    query="SET statement_timeout = '5min'",
    transaction_mode="none"  # Session setting
)

# Or use it in queries
await node.async_run(
    query="""
        SET LOCAL statement_timeout = '30s';
        SELECT * FROM complex_view WHERE conditions = :params;
    """,
    params={"conditions": "complex"},
    allow_multi_statements=True  # Required for SET + SELECT
)
```

## Advanced Transaction Patterns [Built-in]

### Savepoints and Nested Transactions
```python
# PostgreSQL savepoint support
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    transaction_mode="manual"
)

await node.begin_transaction()

try:
    # Main transaction operations
    await node.async_run(
        query="UPDATE accounts SET balance = balance - :amount WHERE id = :id",
        params={"amount": 100, "id": 1}
    )

    # Create savepoint
    await node.create_savepoint("before_risky_operation")

    try:
        # Risky operation
        await node.async_run(
            query="INSERT INTO audit_log (data) VALUES (:data)",
            params={"data": complex_audit_data}
        )
    except Exception:
        # Rollback to savepoint, continue transaction
        await node.rollback_to_savepoint("before_risky_operation")
        # Log failure but continue
        await node.async_run(
            query="INSERT INTO error_log (error) VALUES (:error)",
            params={"error": "Audit log failed"}
        )

    await node.commit()

except Exception:
    await node.rollback()
    raise
```

### Distributed Transaction Coordinator
```python
# Coordinate transactions across multiple databases
async def transfer_across_databases(amount: float, from_account: int, to_account: int):
    source_db = AsyncSQLDatabaseNode(
        name="source_db",
        database_type="postgresql",
        connection_string=SOURCE_DB_URL,
        transaction_mode="manual"
    )

    target_db = AsyncSQLDatabaseNode(
        name="target_db",
        database_type="postgresql",
        connection_string=TARGET_DB_URL,
        transaction_mode="manual"
    )

    # Two-phase commit preparation
    await source_db.begin_transaction()
    await target_db.begin_transaction()

    try:
        # Phase 1: Prepare
        await source_db.async_run(
            query="UPDATE accounts SET balance = balance - :amount WHERE id = :id RETURNING balance",
            params={"amount": amount, "id": from_account}
        )

        await target_db.async_run(
            query="UPDATE accounts SET balance = balance + :amount WHERE id = :id",
            params={"amount": amount, "id": to_account}
        )

        # Phase 2: Commit both
        await asyncio.gather(
            source_db.commit(),
            target_db.commit()
        )

    except Exception as e:
        # Rollback both on any failure
        await asyncio.gather(
            source_db.rollback(),
            target_db.rollback(),
            return_exceptions=True  # Don't fail on rollback errors
        )
        raise
```

## Connection String Security [Built-in]

### Secure Configuration Patterns
```python
# Method 1: Environment variables
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    connection_string="${DATABASE_URL}",  # Resolved from environment
    validate_connection_string=True  # Security validation
)

# Method 2: Secrets manager integration
from kailash.security.secrets import SecretManager

secret_manager = SecretManager("aws")  # or "azure", "gcp", "vault"
db_config = await secret_manager.get_secret("prod/database/config")

node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    **db_config,  # Unpack secure config
    ssl_mode="require",  # Force SSL
    ssl_cert=await secret_manager.get_secret("prod/database/ssl_cert"),
    ssl_key=await secret_manager.get_secret("prod/database/ssl_key")
)

# Method 3: Rotate credentials
async def rotate_db_credentials():
    new_password = await secret_manager.rotate_password("prod/database/password")

    # Update node configuration
    await node.update_connection(
        password=new_password,
        reconnect=True  # Force reconnection with new credentials
    )
```

### Connection String Validation
```python
# Built-in security validation
try:
    node = AsyncSQLDatabaseNode(
        database_type="postgresql",
        connection_string=user_provided_string,
        validate_connection_string=True,  # Default
        allowed_hosts=["*.internal", "localhost"],  # Whitelist
        forbidden_parameters=["sslmode=disable"]  # Blacklist
    )
except NodeValidationError as e:
    # Handle malicious connection strings
    logger.error(f"Invalid connection string: {e}")
```

## Error Recovery Patterns

### Circuit Breaker Pattern [Custom Implementation]
```python
# Since SDK doesn't have built-in circuit breaker, here's a practical implementation
class CircuitBreakerState:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open

async def db_with_circuit_breaker(node: AsyncSQLDatabaseNode, query: str, params: dict, breaker: CircuitBreakerState):
    """Execute query with circuit breaker pattern."""
    # Check if circuit is open
    if breaker.state == "open":
        if datetime.now() - breaker.last_failure_time > timedelta(seconds=breaker.recovery_timeout):
            breaker.state = "half_open"
        else:
            raise NodeExecutionError("Circuit breaker is OPEN - database unavailable")

    try:
        result = await node.async_run(query=query, params=params)
        # Success - reset on half_open or reduce failure count
        if breaker.state == "half_open":
            breaker.state = "closed"
            breaker.failure_count = 0
        elif breaker.failure_count > 0:
            breaker.failure_count -= 1
        return result

    except NodeExecutionError as e:
        breaker.failure_count += 1
        breaker.last_failure_time = datetime.now()

        if breaker.failure_count >= breaker.failure_threshold:
            breaker.state = "open"
            logger.error(f"Circuit breaker OPENED after {breaker.failure_count} failures")

        raise

# Usage in workflow
workflow = WorkflowBuilder()

# Add state management node
workflow.add_node("PythonCodeNode", "circuit_breaker_query", {
    "code": """
from datetime import datetime, timedelta

# Initialize or get breaker state
if not hasattr(context, 'db_breaker'):
    context.db_breaker = {
        'failure_count': 0,
        'failure_threshold': 5,
        'recovery_timeout': 60,
        'last_failure_time': None,
        'state': 'closed'
    }

breaker = context.db_breaker

# Check circuit state
if breaker['state'] == 'open':
    if breaker['last_failure_time'] and (datetime.now() - breaker['last_failure_time']).seconds > breaker['recovery_timeout']:
        breaker['state'] = 'half_open'
    else:
        result = {'success': False, 'error': 'Circuit breaker OPEN', 'use_cache': True}

# If not open, proceed to next node
if breaker['state'] != 'open':
    result = {'proceed': True, 'breaker_state': breaker['state']}
"""
})
```

### Retry with Exponential Backoff and Jitter [Built-in]
```python
from kailash.nodes.data.async_sql import RetryConfig

# Advanced retry configuration
retry_config = RetryConfig(
    max_retries=5,
    initial_delay=0.1,      # Start with 100ms
    max_delay=30.0,         # Cap at 30 seconds
    exponential_base=2.0,   # Double each time
    jitter=True,            # Add randomness
    jitter_factor=0.1,      # ±10% random variation
    retryable_errors=[
        "connection_refused",
        "connection_reset",
        "pool_timeout",
        "deadlock_detected",
        "serialization_failure"  # For SERIALIZABLE isolation
    ],
    retry_on_timeout=True
)

node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    retry_config=retry_config
)

# Custom retry logic for specific errors
async def execute_with_custom_retry(query: str, params: dict):
    for attempt in range(3):
        try:
            return await node.async_run(query=query, params=params)
        except NodeExecutionError as e:
            if "deadlock detected" in str(e) and attempt < 2:
                # Add increasing delay for deadlocks
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise
```

## Monitoring & Metrics [Pattern]

### Performance Metrics Collection
```python
from kailash.monitoring.metrics import MetricsCollector

# Enable metrics collection
metrics = MetricsCollector()

node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    metrics_collector=metrics,
    collect_query_stats=True,  # Track individual queries
    slow_query_threshold=1.0   # Log queries > 1 second
)

# Query with metric tags
result = await node.async_run(
    query="SELECT * FROM reports WHERE month = :month",
    params={"month": "2024-01"},
    metric_tags={
        "operation": "monthly_report",
        "client": "dashboard",
        "priority": "high"
    }
)

# Retrieve metrics
stats = metrics.get_stats("async_sql")
print(f"Total queries: {stats['query_count']}")
print(f"Average duration: {stats['avg_duration_ms']}ms")
print(f"95th percentile: {stats['p95_duration_ms']}ms")
print(f"Slow queries: {stats['slow_query_count']}")
print(f"Connection pool efficiency: {stats['pool_hit_rate']:.2%}")
```

### Query Plan Analysis (PostgreSQL)
```python
# Automatic EXPLAIN ANALYZE for slow queries
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    auto_explain=True,
    auto_explain_threshold=5.0,  # Explain queries > 5 seconds
    explain_options={
        "analyze": True,
        "buffers": True,
        "verbose": True,
        "settings": True
    }
)

# Manual query plan analysis
plan = await node.explain_query(
    query="SELECT * FROM large_table WHERE status = :status",
    params={"status": "active"},
    analyze=True  # Actually run the query
)

print(f"Execution time: {plan['execution_time_ms']}ms")
print(f"Planning time: {plan['planning_time_ms']}ms")
print(f"Index used: {plan['uses_index']}")
print(f"Sequential scan: {plan['has_seq_scan']}")
```

## Integration Patterns

### Workflow Integration with Dependencies
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build complex data pipeline
workflow = WorkflowBuilder()

# Step 1: Validate data exists
workflow.add_node("AsyncSQLDatabaseNode", "validate", {
    "database_type": "postgresql",
    "connection_name": "analytics_db",
    "query": "SELECT COUNT(*) as count FROM staging_data WHERE date = :date",
    "params": {"date": "2024-01-01"},
    "fetch_mode": "one"
})

# Step 2: Run transformation (only if data exists)
workflow.add_node("ConditionalNode", "check_data", {
    "condition": "input.result.data.count > 0"
})

# Step 3: Heavy transformation with pool-level timeout
workflow.add_node("AsyncSQLDatabaseNode", "transform", {
    "database_type": "postgresql",
    "connection_name": "analytics_db",
    "query": "CALL process_daily_aggregates(:date)",
    "params": {"date": "2024-01-01"},
    "command_timeout": 1800.0,  # 30 minutes - pool-level timeout for long-running operations
    "transaction_mode": "none"  # Stored proc handles its own transactions
})

# Connect nodes
workflow.add_connection("validate", "output", "check_data", "input")
workflow.add_connection("check_data", "true_output", "transform", "input")

# Execute with monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Multi-Database Query Federation
```python
# Query across multiple databases
class FederatedQueryNode(AsyncNode):
    """Execute queries across multiple databases and join results."""

    async def async_run(self, **kwargs):
        # Database configurations
        databases = kwargs.get("databases", {})
        queries = kwargs.get("queries", {})
        join_key = kwargs.get("join_key", "id")

        # Execute queries in parallel
        tasks = []
        for db_name, db_config in databases.items():
            node = AsyncSQLDatabaseNode(
                name=f"{db_name}_node",
                **db_config
            )
            tasks.append(
                node.async_run(
                    query=queries[db_name]["query"],
                    params=queries[db_name].get("params", {})
                )
            )

        # Gather results
        results = await asyncio.gather(*tasks)

        # Join results in memory
        joined_data = self._join_results(results, join_key)

        return {"result": {"data": joined_data}}

# Use in workflow
workflow.add_node("FederatedQueryNode", "federated_query", {
    "databases": {
        "users_db": {
            "database_type": "postgresql",
            "connection_name": "users_database"
        },
        "orders_db": {
            "database_type": "mysql",
            "connection_name": "orders_database"
        },
        "analytics_db": {
            "database_type": "postgresql",
            "connection_name": "analytics_database"
        }
    },
    "queries": {
        "users_db": {
            "query": "SELECT id, name, email FROM users WHERE active = true"
        },
        "orders_db": {
            "query": "SELECT user_id as id, COUNT(*) as order_count FROM orders GROUP BY user_id"
        },
        "analytics_db": {
            "query": "SELECT user_id as id, SUM(revenue) as total_revenue FROM transactions GROUP BY user_id"
        }
    },
    "join_key": "id"
})
```

## 🎯 Best Practices Summary

### Performance
- Use connection pooling with `share_pool=True`
- Implement health checks for production systems
- Use batch operations for bulk data
- Stream large result sets instead of loading all
- Enable query plan analysis for optimization

### Security
- Always validate connection strings
- Use environment variables or secrets managers
- Enable SSL/TLS for production databases
- Implement query validation
- Use parameterized queries exclusively

### Reliability
- Configure appropriate retry logic
- Implement circuit breakers for external databases
- Use savepoints for complex transactions
- Monitor slow queries and connection pool health
- Set reasonable timeouts at multiple levels

### Maintainability
- Use descriptive node names
- Document complex queries
- Implement custom result transformers for common patterns
- Use metric tags for observability
- Keep transaction scope minimal

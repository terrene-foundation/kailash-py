# AsyncSQL Enterprise Patterns

*Production-grade database patterns with transactions, concurrency control, and connection management*

## 🚀 Basic Setup

### Standard AsyncSQL Configuration
```python
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# Production configuration
async_db = AsyncSQLDatabaseNode(
    name="enterprise_db",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="production_db",
    user="app_user",
    password="secure_password",
    transaction_mode="auto",  # auto, manual, none
    share_pool=True,         # Enable connection sharing
    validate_queries=True,   # Security validation
    allow_admin=False,       # Restrict admin operations
    command_timeout=60.0     # Pool-level timeout for all queries (default: 60s)
)
```

## 🔄 Transaction Management

### Auto Transaction Mode (Default)
```python
# Each query automatically wrapped in transaction
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    transaction_mode="auto"  # Default
)

# Automatic rollback on error
try:
    await node.async_run(
        query="INSERT INTO orders (customer_id, total) VALUES (:customer_id, :total)",
        params={"customer_id": 123, "total": 99.99}
    )
    # Auto-committed on success
except Exception:
    # Auto-rolled back on error
    pass
```

### Manual Transaction Control
```python
# Explicit transaction management
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    transaction_mode="manual"
)

# Multi-step transaction
await node.begin_transaction()
try:
    # Transfer funds example
    await node.async_run(
        query="UPDATE accounts SET balance = balance - :amount WHERE id = :from_account",
        params={"amount": 100.00, "from_account": 1}
    )

    await node.async_run(
        query="UPDATE accounts SET balance = balance + :amount WHERE id = :to_account",
        params={"amount": 100.00, "to_account": 2}
    )

    # Log transaction
    await node.async_run(
        query="INSERT INTO transactions (from_account, to_account, amount) VALUES (:from_id, :to_id, :amount)",
        params={"from_id": 1, "to_id": 2, "amount": 100.00}
    )

    await node.commit()

except Exception as e:
    await node.rollback()
    raise
```

### No Transaction Mode (Read-Only)
```python
# No transaction wrapping for read-only operations
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    transaction_mode="none"
)

# Fast read operations
result = await node.async_run(
    query="SELECT * FROM users WHERE active = :active",
    params={"active": True},
    fetch_mode="all"
)
```

## 🔒 Optimistic Locking

### Basic Version Control
```python
from kailash.nodes.data.optimistic_locking import OptimisticLockingNode, ConflictResolution

# Initialize lock manager
lock_manager = OptimisticLockingNode(
    version_field="version",
    max_retries=3,
    default_conflict_resolution=ConflictResolution.RETRY
)

# Read with version tracking
user = await lock_manager.execute(
    action="read_with_version",
    table_name="users",
    record_id=123,
    connection=db_connection
)

# Update with conflict detection
update_result = await lock_manager.execute(
    action="update_with_version",
    table_name="users",
    record_id=123,
    update_data={"name": "John Updated", "email": "john@updated.com"},
    expected_version=user["version"],
    connection=db_connection
)

if update_result["lock_status"] == "success":
    print(f"Updated successfully. New version: {update_result['new_version']}")
else:
    print(f"Update failed: {update_result['lock_status']}")
```

### Conflict Resolution Strategies
```python
# FAIL_FAST - Immediate failure on conflict
lock_manager = OptimisticLockingNode(
    default_conflict_resolution=ConflictResolution.FAIL_FAST
)

# RETRY - Automatic retry with backoff
lock_manager = OptimisticLockingNode(
    default_conflict_resolution=ConflictResolution.RETRY,
    max_retries=5,
    retry_delay=0.2,
    retry_backoff_multiplier=2.0
)

# MERGE - Attempt to merge non-conflicting changes
lock_manager = OptimisticLockingNode(
    default_conflict_resolution=ConflictResolution.MERGE
)

# LAST_WRITER_WINS - Override (use with caution)
lock_manager = OptimisticLockingNode(
    default_conflict_resolution=ConflictResolution.LAST_WRITER_WINS
)
```

## 🎯 Advanced Parameter Handling

### PostgreSQL Array Operations
```python
# PostgreSQL ANY() with arrays
await node.async_run(
    query="SELECT * FROM users WHERE id = ANY(:user_ids)",
    params={"user_ids": [1, 2, 3, 4, 5]},  # Auto-converted
    fetch_mode="all"
)

# Array parameter insertion
await node.async_run(
    query="INSERT INTO user_tags (user_id, tags) VALUES (:user_id, :tags)",
    params={
        "user_id": 123,
        "tags": ["premium", "verified", "active"]  # Array handling
    }
)
```

### Complex Data Types
```python
# JSON parameter handling
await node.async_run(
    query="INSERT INTO events (user_id, event_data) VALUES (:user_id, :data)",
    params={
        "user_id": 123,
        "data": {
            "action": "login",
            "timestamp": "2024-01-01T10:00:00Z",
            "metadata": {"ip": "192.168.1.1", "user_agent": "Chrome/91.0"}
        }  # Automatically JSON serialized
    }
)

# Date/datetime handling
from datetime import date, datetime

await node.async_run(
    query="SELECT * FROM orders WHERE created_date >= :start_date AND created_at <= :end_time",
    params={
        "start_date": date(2024, 1, 1),      # Auto date conversion
        "end_time": datetime.now()           # Auto datetime conversion
    }
)
```

## 🏊‍♂️ Connection Pool Sharing

### Shared Pool Configuration
```python
# Multiple nodes sharing the same pool
reader_node = AsyncSQLDatabaseNode(
    name="data_reader",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    share_pool=True  # Default
)

writer_node = AsyncSQLDatabaseNode(
    name="data_writer",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    share_pool=True  # Shares pool with reader_node
)

# Different pools for different databases
analytics_node = AsyncSQLDatabaseNode(
    name="analytics_reader",
    database_type="postgresql",
    host="analytics-db.internal",
    database="analytics",
    share_pool=True  # Separate pool for analytics DB
)
```

## ⚡ Retry Logic & Error Handling

### Custom Retry Configuration
```python
from kailash.nodes.data.async_sql import RetryConfig

# Advanced retry settings
retry_config = RetryConfig(
    max_retries=5,
    initial_delay=0.5,
    max_delay=10.0,
    exponential_base=2.0,
    jitter=True  # Random delay variation
)

node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    retry_config=retry_config
)

# Automatically retries on:
# - Connection failures
# - DNS resolution errors
# - Network timeouts
# - Temporary database locks
# - Connection pool exhaustion
```

### Error Handling Patterns
```python
# Comprehensive error handling
try:
    result = await node.async_run(
        query="SELECT * FROM users WHERE id = :user_id",
        params={"user_id": 123},
        fetch_mode="one"
    )

    if result["result"]["data"] is None:
        # Handle no results
        print("User not found")
    else:
        user_data = result["result"]["data"]
        print(f"Found user: {user_data['name']}")

except NodeExecutionError as e:
    # Handle execution errors
    if "connection" in str(e).lower():
        print("Database connection issue")
    elif "timeout" in str(e).lower():
        print("Query timeout")
    else:
        print(f"Database error: {e}")

except Exception as e:
    # Handle unexpected errors
    print(f"Unexpected error: {e}")
```

## 🔐 Security Patterns

### Query Validation
```python
# Secure production configuration
secure_node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="production",
    validate_queries=True,   # Enable security validation
    allow_admin=False       # Disable admin operations
)

# Admin operations require explicit permission
admin_node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="production",
    validate_queries=True,
    allow_admin=True  # Required for CREATE, DROP, etc.
)

# Temporary table creation (admin operation)
await admin_node.async_run(
    query="CREATE TEMPORARY TABLE temp_analysis AS SELECT * FROM users WHERE active = :active",
    params={"active": True}
)
```

## 📊 Performance Monitoring

### Lock Contention Metrics
```python
# Monitor optimistic locking performance
metrics = lock_manager.get_metrics()

print(f"Total operations: {metrics['total_operations']}")
print(f"Success rate: {metrics['successful_operations'] / metrics['total_operations']:.2%}")
print(f"Version conflicts: {metrics['version_conflicts']}")
print(f"Average retries: {metrics['avg_retry_count']:.1f}")

# Analyze conflict patterns
conflicts = lock_manager.get_conflict_history(limit=10)
for conflict in conflicts:
    print(f"Conflict: {conflict['table_name']} record {conflict['record_id']} at {conflict['timestamp']}")
```

## 🏢 Enterprise Integration

### Combined AsyncSQL + Optimistic Locking
```python
# Enterprise workflow with full concurrency control
async_node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="enterprise_db",
    transaction_mode="manual"
)

lock_manager = OptimisticLockingNode(
    max_retries=5,
    default_conflict_resolution=ConflictResolution.RETRY
)

# Workflow execution
await async_node.connect()
connection = async_node._adapter

# Begin transaction
transaction = await connection.begin_transaction()

try:
    # Read with version
    account = await lock_manager.execute(
        action="read_with_version",
        table_name="accounts",
        record_id=account_id,
        connection=connection,
        transaction=transaction
    )

    # Business logic
    new_balance = account["data"]["balance"] + deposit_amount

    # Update with version check
    result = await lock_manager.execute(
        action="update_with_version",
        table_name="accounts",
        record_id=account_id,
        update_data={"balance": new_balance},
        expected_version=account["version"],
        connection=connection,
        transaction=transaction
    )

    await connection.commit_transaction(transaction)

except Exception as e:
    await connection.rollback_transaction(transaction)
    raise
```

## 🔧 PostgreSQL Parameter Type Inference (v0.6.6+)

### Handling JSONB and Complex Type Contexts
```python
# PostgreSQL sometimes can't infer parameter types in complex contexts
# Use parameter_types to provide explicit type hints

node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp"
)

# JSONB build_object requires explicit type hints
await node.async_run(
    query="""
        INSERT INTO audit_logs (action, details, created_by)
        VALUES (
            :action,
            jsonb_build_object(
                'role_id', :role_id,
                'granted_by', :granted_by,
                'permissions', :permissions::jsonb
            ),
            :created_by
        )
    """,
    params={
        "action": "role_assigned",
        "role_id": "admin",
        "granted_by": "system",
        "permissions": '["read", "write", "delete"]',
        "created_by": "system"
    },
    parameter_types={
        "action": "text",
        "role_id": "text",
        "granted_by": "text",
        "permissions": "jsonb",
        "created_by": "text"
    }
)

# COALESCE with NULL values
await node.async_run(
    query="""
        UPDATE users
        SET preferences = jsonb_set(
            COALESCE(preferences, '{}'),
            '{notifications}',
            :settings::jsonb
        )
        WHERE user_id = :user_id
    """,
    params={
        "settings": '{"email": true, "sms": false}',
        "user_id": "user123"
    },
    parameter_types={
        "settings": "jsonb",
        "user_id": "text"
    }
)

# Configuration-based type hints
node = AsyncSQLDatabaseNode(
    database_type="postgresql",
    host="localhost",
    database="myapp",
    parameter_types={
        "metadata": "jsonb",
        "role_id": "uuid",
        "created_at": "timestamptz"
    }
)
```

### Common PostgreSQL Types for parameter_types
```python
parameter_types = {
    # Text types
    "name": "text",
    "id": "varchar",

    # Numeric types
    "count": "integer",
    "amount": "numeric",
    "price": "decimal",

    # JSON types
    "data": "jsonb",
    "config": "json",

    # Date/time types
    "created": "timestamp",
    "updated": "timestamptz",
    "birth_date": "date",

    # Network types
    "ip_address": "inet",
    "mac": "macaddr",

    # UUID
    "user_id": "uuid",

    # Arrays
    "tags": "text[]",
    "numbers": "integer[]"
}
```

## 🎯 Best Practices

### Performance
- Use connection pool sharing (`share_pool=True`)
- Choose appropriate transaction mode for use case
- Index version fields for optimistic locking
- Monitor retry metrics to identify hotspots

### Security
- Always use parameterized queries
- Enable query validation in production
- Restrict admin operations unless required
- Use proper connection credentials and SSL

### Reliability
- Configure appropriate retry logic
- Handle specific error types gracefully
- Use manual transactions for multi-step operations
- Monitor connection pool health

### Concurrency
- Use optimistic locking for concurrent updates
- Choose appropriate conflict resolution strategy
- Monitor version conflict rates
- Consider batch operations for bulk updates

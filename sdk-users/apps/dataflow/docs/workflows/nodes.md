# DataFlow Workflow Integration

Complete guide to integrating DataFlow database operations into Kailash workflows.

## Overview

DataFlow transforms database operations into workflow nodes, providing seamless integration with Kailash's workflow engine. This enables:

- **Declarative database operations** as workflow nodes
- **Automatic transaction management** across workflow boundaries
- **Data flow between nodes** with type safety
- **Parallel execution** of independent operations
- **Built-in error handling** and recovery

## Generated Workflow Nodes

For each model, DataFlow automatically generates workflow nodes:

```python
from kailash_dataflow import DataFlow

db = DataFlow()

@db.model
class User:
    name: str
    email: str
    age: int
    active: bool = True

# DataFlow automatically generates these workflow nodes:
# - UserCreateNode
# - UserReadNode
# - UserUpdateNode
# - UserDeleteNode
# - UserListNode
# - UserBulkCreateNode
# - UserBulkUpdateNode
# - UserBulkDeleteNode
# - UserBulkUpsertNode
```

## Basic Workflow Integration

### Single Node Operations

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add database operation as node
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Access results
user = results["create_user"]["data"]
print(f"Created user: {user['name']} with ID {user['id']}")
```

### Connected Operations

```python
# Create workflow with connected nodes
workflow = WorkflowBuilder()

# Step 1: Create user
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice Smith",
    "email": "alice@example.com",
    "age": 28
})

# Step 2: Create profile for user
workflow.add_node("ProfileCreateNode", "create_profile", {
    # IMPORTANT: Do NOT use template syntax in node config
    # user_id will be provided via connection below
    "bio": "Software developer",
    "location": "New York"
})

# Step 3: Send welcome email
workflow.add_node("EmailNotificationNode", "send_welcome", {
    # email, name, and profile_id provided via connections
    "template": "welcome"
})

# Connect nodes with data flow (4-parameter signature)
workflow.add_connection("create_user", "id", "create_profile", "user_id")
workflow.add_connection("create_user", "email", "send_welcome", "to")
workflow.add_connection("create_user", "name", "send_welcome", "name")
workflow.add_connection("create_profile", "id", "send_welcome", "profile_id")
```

### Parameter Validation Patterns

```python
# ❌ WRONG: Never use ${} syntax in node parameters
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": "${create_customer.id}",  # This will fail validation
    "total": 100.0
})

# ✅ CORRECT: Use workflow connections for dynamic values
workflow.add_node("OrderCreateNode", "create_order", {
    "total": 100.0  # customer_id provided via connection
})
workflow.add_connection("create_customer", "id", "create_order", "customer_id")

# ✅ CORRECT: Use {{}} for Nexus parameter placeholders (Nexus integration only)
nexus_workflow.add_node("ProductCreateNode", "create", {
    "name": "{{product_name}}",    # Nexus will replace at runtime
    "price": "{{product_price}}"   # Only for Nexus channels
})

# ✅ CORRECT: Use native Python types for datetime
workflow.add_node("OrderCreateNode", "create_order", {
    "due_date": datetime.now(),     # Native datetime object
    # NOT: datetime.now().isoformat() - string will fail validation
})
```

## Advanced Workflow Patterns

### Parallel Database Operations

```python
# Execute multiple database operations in parallel
workflow = WorkflowBuilder()

# Parallel user creation
workflow.add_node("UserCreateNode", "create_user_1", {
    "name": "User 1",
    "email": "user1@example.com"
})

workflow.add_node("UserCreateNode", "create_user_2", {
    "name": "User 2",
    "email": "user2@example.com"
})

workflow.add_node("UserCreateNode", "create_user_3", {
    "name": "User 3",
    "email": "user3@example.com"
})

# Aggregate results using workflow-based approach
workflow.add_node("PythonCodeNode", "aggregate_users", {
    "code": """
# Aggregate created user IDs from connected inputs
user_ids = []

# Collect user IDs from all connected user creation results
for input_key in ['user1', 'user2', 'user3']:
    if input_key in input_data:
        user_data = input_data[input_key]
        if isinstance(user_data, dict) and 'data' in user_data:
            user_ids.append(user_data['data']['id'])

result = {"user_ids": user_ids, "total_users": len(user_ids)}
"""
})

# Connect aggregation to all user creation nodes (4-parameter signature)
workflow.add_connection("create_user_1", "result", "aggregate_users", "user1")
workflow.add_connection("create_user_2", "result", "aggregate_users", "user2")
workflow.add_connection("create_user_3", "result", "aggregate_users", "user3")
```

### Conditional Operations

```python
# Conditional database operations based on data
workflow = WorkflowBuilder()

# Check if user exists
workflow.add_node("UserReadNode", "check_user", {
    "email": "user@example.com",
    "return_null_if_not_found": True
})

# Conditional create or update
workflow.add_node("SwitchNode", "user_exists_switch", {
    "condition": "user_data is not None",
    "true_path": "update_existing_user",
    "false_path": "create_new_user"
})

# Create new user
workflow.add_node("UserCreateNode", "create_new_user", {
    "name": "New User",
    "email": "user@example.com",
    "age": 25
})

# Update existing user
workflow.add_node("UserUpdateNode", "update_existing_user", {
    "name": "Updated User",
    "age": 26
    # id will be provided via connection
})

# Connect conditional flow
workflow.add_connection("check_user", "data", "user_exists_switch", "user_data")
workflow.add_connection("check_user", "id", "update_existing_user", "id")
workflow.add_connection("user_exists_switch", "true_output", "update_existing_user", "input")
workflow.add_connection("user_exists_switch", "false_output", "create_new_user", "input")
```

### Bulk Operations in Workflows

```python
# Large-scale data processing workflow
workflow = WorkflowBuilder()

# Step 1: Extract data from external source
workflow.add_node("HTTPRequestNode", "fetch_products", {
    "url": "https://api.example.com/products",
    "method": "GET",
    "headers": {"Authorization": "Bearer TOKEN"}
})

# Step 2: Transform data
workflow.add_node("PythonCodeNode", "transform_products", {
    "code": """
import json
# Access data from connected HTTP request node
products_data = input_data.get('response', '{}')
products = json.loads(products_data) if isinstance(products_data, str) else products_data

# Transform to our schema
transformed = []
for product in products:
    transformed.append({
        "name": product["title"],
        "price": float(product["price"]),
        "category": product["category"].lower(),
        "stock": int(product["inventory"])
    })

result = {"products": transformed}
"""
})

# Step 3: Bulk insert products
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "data": ":products",
    "batch_size": 1000,
    "conflict_resolution": "update"
})

# Step 4: Update search index
workflow.add_node("SearchIndexUpdateNode", "update_search", {
    "index": "products",
    "documents": ":imported_products"
})

# Connect workflow
workflow.add_connection("fetch_products", "result", "transform_products", "input")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
workflow.add_connection("import_products", "update_search", "data", "imported_products")
```

## Transaction Management

### Automatic Transaction Boundaries

```python
# Workflow automatically handles transactions
workflow = WorkflowBuilder()

# All these operations are in one transaction
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})

workflow.add_node("AccountCreateNode", "create_account", {
    "user_id": ":user_id",
    "balance": 100.00
})

workflow.add_node("TransactionCreateNode", "create_transaction", {
    "account_id": ":account_id",
    "amount": 100.00,
    "type": "deposit"
})

# If any operation fails, all are rolled back
workflow.add_connection("create_user", "create_account", "id", "user_id")
workflow.add_connection("create_account", "create_transaction", "id", "account_id")
```

### Explicit Transaction Control

```python
# Explicit transaction management
workflow = WorkflowBuilder()

# Start transaction
workflow.add_node("TransactionScopeNode", "start_transaction", {
    "isolation_level": "READ_COMMITTED",
    "timeout": 30,
    "rollback_on_error": True
})

# Database operations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Jane Doe",
    "email": "jane@example.com"
})

workflow.add_node("ProfileCreateNode", "create_profile", {
    "user_id": ":user_id",
    "bio": "Test user"
})

# Commit transaction
workflow.add_node("TransactionCommitNode", "commit_transaction", {
    "cleanup": True
})

# Or rollback on error
workflow.add_node("TransactionRollbackNode", "rollback_transaction", {
    "cleanup": True
})

# Connect transaction flow
workflow.add_connection("start_transaction", "result", "create_user", "input")
workflow.add_connection("create_user", "create_profile", "id", "user_id")
workflow.add_connection("create_profile", "result", "commit_transaction", "input")
```

### Nested Transactions

```python
# Nested transaction (savepoints)
workflow = WorkflowBuilder()

# Main transaction
workflow.add_node("TransactionScopeNode", "main_transaction", {
    "isolation_level": "SERIALIZABLE",
    "timeout": 60,
    "rollback_on_error": True
})

# Create user (always commit)
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "test@example.com"
})

# Savepoint for optional operations
workflow.add_node("TransactionSavepointNode", "savepoint_profile", {
    "name": "profile_savepoint"
})

# Create profile (might fail)
workflow.add_node("ProfileCreateNode", "create_profile", {
    "user_id": ":user_id",
    "bio": "This might fail"
})

# Rollback to savepoint on error
workflow.add_node("TransactionRollbackToSavepointNode", "rollback_profile", {
    "savepoint": "profile_savepoint",
    "on_error": True
})

# Commit main transaction
workflow.add_node("TransactionCommitNode", "commit_main", {})

# Connect nested transaction flow
workflow.add_connection("main_transaction", "result", "create_user", "input")
workflow.add_connection("create_user", "result", "savepoint_profile", "input")
workflow.add_connection("savepoint_profile", "result", "create_profile", "input")
workflow.add_connection("create_profile", "result", "commit_main", "input")
```

## Error Handling and Recovery

### Automatic Error Recovery

```python
# Built-in error recovery
workflow = WorkflowBuilder()

# Operation with automatic retry
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",

    # Automatic retry on failure
    "retry": {
        "max_attempts": 3,
        "backoff": "exponential",
        "retry_on": ["connection_error", "timeout"]
    },

    # Fallback behavior
    "on_error": {
        "action": "log_and_continue",
        "fallback_data": {"created": False, "error": "creation_failed"}
    }
})
```

### Custom Error Handling

```python
# Custom error handling workflow
workflow = WorkflowBuilder()

# Main operation
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "test@example.com"
})

# Error handler
workflow.add_node("PythonCodeNode", "handle_error", {
    "code": """
error_info = get_input_data("create_user")
if error_info.get("error"):
    # Log error
    print(f"User creation failed: {error_info['error']}")

    # Send notification
    result = {
        "error_handled": True,
        "notification_sent": True,
        "retry_needed": error_info["error"] == "temporary_failure"
    }
else:
    result = {"error_handled": False}
"""
})

# Conditional retry
workflow.add_node("UserCreateNode", "retry_create_user", {
    "name": "Test User",
    "email": "test@example.com",
    "retry_attempt": True
})

# Connect error handling
workflow.add_connection("create_user", "result", "handle_error", "input")
workflow.add_connection("handle_error", "result", "retry_create_user", "input")
```

## Data Flow Patterns

### Data Transformation

```python
# Data transformation workflow
workflow = WorkflowBuilder()

# Fetch raw data
workflow.add_node("UserListNode", "get_users", {
    "filter": {"active": True},
    "fields": ["id", "name", "email", "created_at"]
})

# Transform data
workflow.add_node("PythonCodeNode", "transform_users", {
    "code": """
users = get_input_data("get_users")["data"]
transformed = []

for user in users:
    transformed.append({
        "user_id": user["id"],
        "display_name": user["name"].title(),
        "email_domain": user["email"].split("@")[1],
        "account_age_days": (datetime.now() - user["created_at"]).days
    })

result = {"transformed_users": transformed}
"""
})

# Store transformed data
workflow.add_node("UserAnalyticsBulkCreateNode", "store_analytics", {
    "data": ":transformed_users",
    "batch_size": 100
})

# Connect transformation pipeline
workflow.add_connection("get_users", "result", "transform_users", "input")
workflow.add_connection("transform_users", "store_analytics", "transformed_users")
```

### Data Aggregation

```python
# Data aggregation workflow
workflow = WorkflowBuilder()

# Get user orders
workflow.add_node("OrderListNode", "get_orders", {
    "filter": {"status": "completed"},
    "include": ["user"],
    "fields": ["user_id", "total", "created_at"]
})

# Aggregate by user
workflow.add_node("PythonCodeNode", "aggregate_orders", {
    "code": """
orders = get_input_data("get_orders")["data"]
user_stats = {}

for order in orders:
    user_id = order["user_id"]
    if user_id not in user_stats:
        user_stats[user_id] = {
            "total_orders": 0,
            "total_amount": 0.0,
            "first_order": order["created_at"],
            "last_order": order["created_at"]
        }

    stats = user_stats[user_id]
    stats["total_orders"] += 1
    stats["total_amount"] += order["total"]
    stats["first_order"] = min(stats["first_order"], order["created_at"])
    stats["last_order"] = max(stats["last_order"], order["created_at"])

result = {"user_stats": user_stats}
"""
})

# Update user statistics
workflow.add_node("UserBulkUpdateNode", "update_user_stats", {
    "fields": ":user_updates",
    "batch_size": 100
})

# Connect aggregation pipeline
workflow.add_connection("get_orders", "result", "aggregate_orders", "input")
workflow.add_connection("aggregate_orders", "update_user_stats", "user_stats", "user_updates")
```

## Performance Optimization

### Parallel Database Operations

```python
# Parallel processing for performance
workflow = WorkflowBuilder()

# Fetch data in parallel
workflow.add_node("UserListNode", "get_active_users", {
    "filter": {"active": True},
    "limit": 1000
})

workflow.add_node("OrderListNode", "get_recent_orders", {
    "filter": {"created_at": {"$gte": "2024-01-01"}},
    "limit": 1000
})

workflow.add_node("ProductListNode", "get_popular_products", {
    "filter": {"views": {"$gte": 100}},
    "limit": 100
})

# Process data in parallel
workflow.add_node("PythonCodeNode", "process_users", {
    "code": """
users = get_input_data("get_active_users")["data"]
result = {"processed_users": len(users)}
"""
})

workflow.add_node("PythonCodeNode", "process_orders", {
    "code": """
orders = get_input_data("get_recent_orders")["data"]
result = {"processed_orders": len(orders)}
"""
})

workflow.add_node("PythonCodeNode", "process_products", {
    "code": """
products = get_input_data("get_popular_products")["data"]
result = {"processed_products": len(products)}
"""
})

# Aggregate results
workflow.add_node("PythonCodeNode", "aggregate_results", {
    "code": """
user_result = get_input_data("process_users")
order_result = get_input_data("process_orders")
product_result = get_input_data("process_products")

result = {
    "summary": {
        "users": user_result["processed_users"],
        "orders": order_result["processed_orders"],
        "products": product_result["processed_products"]
    }
}
"""
})

# Connect parallel processing
workflow.add_connection("get_active_users", "result", "process_users", "input")
workflow.add_connection("get_recent_orders", "result", "process_orders", "input")
workflow.add_connection("get_popular_products", "result", "process_products", "input")

workflow.add_connection("process_users", "result", "aggregate_results", "input")
workflow.add_connection("process_orders", "result", "aggregate_results", "input")
workflow.add_connection("process_products", "result", "aggregate_results", "input")
```

### Batch Processing

```python
# Efficient batch processing
workflow = WorkflowBuilder()

# Process large dataset in batches
workflow.add_node("UserListNode", "get_users_batch", {
    "filter": {"active": True},
    "batch_size": 1000,
    "streaming": True  # Process in streaming mode
})

# Process each batch
workflow.add_node("PythonCodeNode", "process_user_batch", {
    "code": """
users = get_input_data("get_users_batch")["data"]
processed = []

for user in users:
    # Process each user
    processed.append({
        "user_id": user["id"],
        "processed_at": datetime.now().isoformat(),
        "status": "processed"
    })

result = {"processed_users": processed}
"""
})

# Store processed results
workflow.add_node("UserProcessingLogBulkCreateNode", "store_processing_log", {
    "data": ":processed_users",
    "batch_size": 500
})

# Connect batch processing
workflow.add_connection("get_users_batch", "result", "process_user_batch", "input")
workflow.add_connection("process_user_batch", "store_processing_log", "processed_users")
```

## Monitoring and Observability

### Built-in Monitoring

```python
# Workflow with monitoring
workflow = WorkflowBuilder()

# Database operation with monitoring
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "test@example.com",

    # Monitoring settings
    "monitoring": {
        "track_execution_time": True,
        "track_memory_usage": True,
        "log_queries": True,
        "alert_on_slow_query": True,
        "slow_query_threshold": 1.0
    }
})

# Performance metrics collection
workflow.add_node("MetricsCollectorNode", "collect_metrics", {
    "metrics": [
        "database_query_time",
        "memory_usage",
        "connection_pool_size"
    ],
    "interval": 10  # Collect every 10 seconds
})
```

### Custom Metrics

```python
# Custom metrics collection
workflow = WorkflowBuilder()

# Database operation
workflow.add_node("UserBulkCreateNode", "create_users", {
    "data": user_data,
    "batch_size": 1000
})

# Custom metrics
workflow.add_node("PythonCodeNode", "track_metrics", {
    "code": """
import time
import psutil

result_data = get_input_data("create_users")
execution_time = result_data.get("execution_time", 0)
records_processed = result_data.get("records_processed", 0)

# Calculate metrics
records_per_second = records_processed / execution_time if execution_time > 0 else 0
memory_usage = psutil.virtual_memory().percent

# Store metrics
result = {
    "metrics": {
        "execution_time": execution_time,
        "records_processed": records_processed,
        "records_per_second": records_per_second,
        "memory_usage": memory_usage,
        "timestamp": time.time()
    }
}
"""
})

# Store metrics in database
workflow.add_node("MetricsBulkCreateNode", "store_metrics", {
    "data": ":metrics",
    "batch_size": 100
})

# Connect monitoring
workflow.add_connection("create_users", "result", "track_metrics", "input")
workflow.add_connection("track_metrics", "store_metrics", "metrics")
```

## Testing Workflow Integration

### Unit Tests

```python
def test_user_creation_workflow():
    """Test user creation workflow."""
    workflow = WorkflowBuilder()

    # Create user
    workflow.add_node("UserCreateNode", "create_user", {
        "name": "Test User",
        "email": "test@example.com",
        "age": 25
    })

    # Verify creation
    workflow.add_node("UserReadNode", "verify_user", {
        "id": ":user_id"
    })

    # Connect nodes
    workflow.add_connection("create_user", "verify_user", "id", "user_id")

    # Execute workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Verify results
    assert results["create_user"]["data"]["name"] == "Test User"
    assert results["verify_user"]["data"]["email"] == "test@example.com"
```

### Integration Tests

```python
def test_complex_workflow():
    """Test complex workflow with multiple operations."""
    workflow = WorkflowBuilder()

    # Create user
    workflow.add_node("UserCreateNode", "create_user", {
        "name": "John Doe",
        "email": "john@example.com"
    })

    # Create profile
    workflow.add_node("ProfileCreateNode", "create_profile", {
        "user_id": ":user_id",
        "bio": "Test bio"
    })

    # Create orders
    workflow.add_node("OrderBulkCreateNode", "create_orders", {
        "data": [
            {"user_id": ":user_id", "total": 100.0},
            {"user_id": ":user_id", "total": 200.0}
        ]
    })

    # Connect workflow
    workflow.add_connection("create_user", "create_profile", "id", "user_id")
    workflow.add_connection("create_user", "create_orders", "id", "user_id")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Verify complete workflow
    assert results["create_user"]["data"]["name"] == "John Doe"
    assert results["create_profile"]["data"]["bio"] == "Test bio"
    assert results["create_orders"]["data"]["success_count"] == 2
```

## Specialized DataFlow Nodes

### Transaction Management Nodes

DataFlow provides specialized nodes for managing database transactions:

#### TransactionScopeNode

Manages transaction scope with isolation levels and automatic rollback:

```python
workflow.add_node("TransactionScopeNode", "start_transaction", {
    "isolation_level": "READ_COMMITTED",  # READ_UNCOMMITTED, READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE
    "timeout": 30,  # Transaction timeout in seconds
    "rollback_on_error": True  # Automatically rollback on any error
})
```

#### TransactionCommitNode

Commits the current transaction:

```python
workflow.add_node("TransactionCommitNode", "commit", {
    # No parameters required - commits active transaction
})
```

#### TransactionRollbackNode

Rolls back the current transaction:

```python
workflow.add_node("TransactionRollbackNode", "rollback", {
    # No parameters required - rolls back active transaction
})
```

### Schema Management Nodes

DataFlow provides nodes for managing database schema changes:

#### SchemaModificationNode

Performs schema modifications on database tables:

```python
# Add column
workflow.add_node("SchemaModificationNode", "add_column", {
    "table": "users",
    "operation": "add_column",
    "column_name": "phone_number",
    "column_type": "varchar(20)",
    "nullable": True
})

# Drop column
workflow.add_node("SchemaModificationNode", "drop_column", {
    "table": "users",
    "operation": "drop_column",
    "column_name": "deprecated_field"
})
```

#### MigrationNode

Tracks database migrations to ensure schema changes are applied consistently:

```python
# Track migration
workflow.add_node("MigrationNode", "track_migration", {
    "migration_name": "add_user_phone_number",
    "status": "pending"  # pending, completed, failed
})

# Update migration status
workflow.add_node("MigrationNode", "complete_migration", {
    "migration_name": "add_user_phone_number",
    "status": "completed"
})
```

### Complete Schema Migration Example

```python
workflow = WorkflowBuilder()

# Start transaction for safe migration
workflow.add_node("TransactionScopeNode", "start_migration", {
    "isolation_level": "SERIALIZABLE",
    "rollback_on_error": True
})

# Track migration
workflow.add_node("MigrationNode", "track", {
    "migration_name": "add_user_preferences",
    "status": "pending"
})

# Apply schema change
workflow.add_node("SchemaModificationNode", "add_preferences", {
    "table": "users",
    "operation": "add_column",
    "column_name": "preferences",
    "column_type": "jsonb",
    "nullable": True
})

# Update migration status
workflow.add_node("MigrationNode", "complete", {
    "migration_name": "add_user_preferences",
    "status": "completed"
})

# Commit transaction
workflow.add_node("TransactionCommitNode", "commit_migration", {})

# Connect workflow
workflow.add_connection("start_migration", "result", "track", "input")
workflow.add_connection("track", "result", "add_preferences", "input")
workflow.add_connection("add_preferences", "result", "complete", "input")
workflow.add_connection("complete", "result", "commit_migration", "input")
```

## Best Practices

### 1. Node Naming and Organization

```python
# Good: Descriptive node names
workflow.add_node("UserCreateNode", "create_new_customer", {...})
workflow.add_node("OrderCreateNode", "create_customer_order", {...})

# Avoid: Generic names
workflow.add_node("UserCreateNode", "node1", {...})
workflow.add_node("OrderCreateNode", "node2", {...})
```

### 2. Data Flow Design

```python
# Good: Clear data flow
workflow.add_connection("create_user", "create_profile", "id", "user_id")
workflow.add_connection("create_profile", "send_welcome_email", "id", "profile_id")

# Avoid: Complex data mapping
workflow.add_connection("node1", "node2", "data.user.id", "input.user_id")
```

### 3. Error Handling Strategy

```python
# Good: Comprehensive error handling
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",
    "retry": {"max_attempts": 3},
    "on_error": {"action": "log_and_continue"}
})

# Avoid: No error handling
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})
```

### 4. Performance Considerations

```python
# Good: Batch operations for large datasets
workflow.add_node("UserBulkCreateNode", "import_users", {
    "data": user_list,
    "batch_size": 1000
})

# Avoid: Individual operations for large datasets
for user in user_list:
    workflow.add_node("UserCreateNode", f"create_user_{user['id']}", user)
```

### 5. Transaction Management

```python
# Good: Appropriate transaction boundaries
workflow.add_node("TransactionScopeNode", "start_transaction", {
    "rollback_on_error": True
})
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("ProfileCreateNode", "create_profile", {...})
workflow.add_node("TransactionCommitNode", "commit_transaction", {})

# Avoid: Overly broad transactions
workflow.add_node("TransactionScopeNode", "start_transaction", {
    "rollback_on_error": True
})
# ... 50 different operations ...
workflow.add_node("TransactionCommitNode", "commit_transaction", {})
```

## Next Steps

- **Bulk Operations**: [Bulk Operations Guide](../development/bulk-operations.md)
- **Query Building**: [Query Builder Guide](../advanced/query-builder.md)
- **Performance Tuning**: [Performance Guide](../production/performance.md)
- **Production Deployment**: [Deployment Guide](../production/deployment.md)

DataFlow workflow integration provides a powerful way to build complex data processing pipelines while maintaining type safety, performance, and reliability.

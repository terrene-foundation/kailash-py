# DataFlow CRUD Operations

Complete guide to Create, Read, Update, Delete operations in DataFlow workflows.

## Overview

DataFlow automatically generates CRUD nodes for every model you define, making database operations simple and consistent.

## Model Setup

First, define your model:

```python
from kailash_dataflow import DataFlow
from datetime import datetime
from typing import Optional

db = DataFlow()

@db.model
class User:
    name: str
    email: str
    age: int
    active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None
```

For this model, DataFlow automatically generates:
- `UserCreateNode` - Create new users
- `UserReadNode` - Read single user by ID
- `UserUpdateNode` - Update existing users
- `UserDeleteNode` - Delete users
- `UserListNode` - Query multiple users

## Create Operations

### Single Record Creation

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Create a single user
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Access created user
user = results["create_user"]["data"]
print(f"Created user {user['name']} with ID {user['id']}")
```

### Create with Relationships

```python
# Create user first
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice Smith",
    "email": "alice@example.com",
    "age": 28
})

# Create order for the user
workflow.add_node("OrderCreateNode", "create_order", {
    "user_id": ":user_id",  # Reference from previous node
    "total": 99.99,
    "status": "pending"
})

# Connect nodes (4-parameter signature: from_node, from_output, to_node, to_input)
workflow.add_connection("create_user", "id", "create_order", "user_id")
```

### Create with Validation

```python
# Create with validation
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Bob Johnson",
    "email": "bob@example.com",
    "age": 25,
    "validation": {
        "required": ["name", "email"],
        "email_format": True,
        "age_range": {"min": 18, "max": 100}
    }
})
```

## Read Operations

### Read Single Record

```python
# Read user by ID
workflow.add_node("UserReadNode", "get_user", {
    "record_id": 1
})

# Read user by email (if indexed)
workflow.add_node("UserReadNode", "get_user_by_email", {
    "email": "john@example.com"
})

# Read with specific fields
workflow.add_node("UserReadNode", "get_user_fields", {
    "record_id": 1,
    "fields": ["name", "email", "created_at"]
})
```

### Read with Relationships

```python
# Read user with related orders
workflow.add_node("UserReadNode", "get_user_with_orders", {
    "record_id": 1,
    "include": ["orders"]
})

# Read with nested relationships
workflow.add_node("UserReadNode", "get_user_detailed", {
    "record_id": 1,
    "include": ["orders", "orders.items", "profile"]
})
```

### Conditional Read

```python
# Read if exists, otherwise create
workflow.add_node("UserReadNode", "get_or_create_user", {
    "email": "user@example.com",
    "create_if_not_found": {
        "name": "New User",
        "email": "user@example.com",
        "age": 25
    }
})
```

## Update Operations

### Single Record Update

```python
# Update user by ID
workflow.add_node("UserUpdateNode", "update_user", {
    "record_id": 1,
    "name": "John Smith",
    "age": 31
})

# Update with conditions
workflow.add_node("UserUpdateNode", "update_user_conditional", {
    "conditions": {"id": 1, "active": True},
    "updates": {
        "name": "John Smith",
        "updated_at": ":current_timestamp"
    }
})
```

### Partial Updates

```python
# Update only specific fields
workflow.add_node("UserUpdateNode", "update_user_partial", {
    "record_id": 1,
    "updates": {
        "age": 32,
        "updated_at": ":current_timestamp"
    },
    "partial": True
})
```

### Conditional Updates

```python
# Update with version checking (optimistic locking)
workflow.add_node("UserUpdateNode", "update_user_versioned", {
    "record_id": 1,
    "version": 5,  # Current version
    "updates": {
        "name": "Updated Name",
        "version": 6
    }
})

# Update with custom conditions
workflow.add_node("UserUpdateNode", "update_active_users", {
    "conditions": {"active": True, "last_login": {"$gt": "2024-01-01"}},
    "updates": {
        "updated_at": ":current_timestamp"
    }
})
```

### Atomic Updates

```python
# Atomic increment
workflow.add_node("UserUpdateNode", "increment_login_count", {
    "record_id": 1,
    "atomic_operations": {
        "login_count": {"$inc": 1},
        "last_login": {"$set": ":current_timestamp"}
    }
})
```

## Delete Operations

### Single Record Delete

```python
# Hard delete
workflow.add_node("UserDeleteNode", "delete_user", {
    "record_id": 1,
    "hard_delete": True
})

# Soft delete (if enabled in model)
workflow.add_node("UserDeleteNode", "soft_delete_user", {
    "record_id": 1,
    "soft_delete": True
})
```

### Conditional Delete

```python
# Delete with conditions
workflow.add_node("UserDeleteNode", "delete_inactive_users", {
    "conditions": {
        "active": False,
        "last_login": {"$lt": "2023-01-01"}
    },
    "confirm": True
})
```

### Delete with Cleanup

```python
# Delete user and related data
workflow.add_node("UserDeleteNode", "delete_user_complete", {
    "record_id": 1,
    "cascade": ["orders", "profile", "sessions"],
    "cleanup_files": True
})
```

## List Operations

### Basic Listing

```python
# List all users
workflow.add_node("UserListNode", "list_all_users", {
    "limit": 100
})

# List with filters
workflow.add_node("UserListNode", "list_active_users", {
    "filter": {"active": True},
    "order_by": ["-created_at"],
    "limit": 50
})
```

### Advanced Filtering

```python
# Complex filters
workflow.add_node("UserListNode", "list_users_filtered", {
    "filter": {
        "age": {"$gte": 18, "$lte": 65},
        "email": {"$regex": ".*@company.com"},
        "created_at": {"$gte": "2024-01-01"},
        "active": True
    },
    "order_by": ["name", "-created_at"],
    "offset": 0,
    "limit": 25
})
```

### Pagination

```python
# Page-based pagination
workflow.add_node("UserListNode", "list_users_page", {
    "filter": {"active": True},
    "page": 2,
    "page_size": 20,
    "order_by": ["name"]
})

# Cursor-based pagination
workflow.add_node("UserListNode", "list_users_cursor", {
    "filter": {"active": True},
    "cursor": "eyJpZCI6MTAwfQ==",  # Base64 encoded cursor
    "limit": 20,
    "order_by": ["id"]
})
```

### Aggregation

```python
# Count records
workflow.add_node("UserListNode", "count_users", {
    "filter": {"active": True},
    "count_only": True
})

# Group by field
workflow.add_node("UserListNode", "users_by_age_group", {
    "group_by": "age_group",
    "aggregations": {
        "count": {"$count": "*"},
        "avg_age": {"$avg": "age"}
    }
})
```

## Advanced CRUD Patterns

### Upsert Operations

```python
# Insert or update
workflow.add_node("UserUpsertNode", "upsert_user", {
    "email": "user@example.com",  # Unique key
    "data": {
        "name": "Updated Name",
        "age": 30,
        "active": True
    },
    "on_conflict": "update"  # or "ignore"
})
```

### Batch Operations

```python
# Batch read
workflow.add_node("UserBatchReadNode", "get_users_batch", {
    "ids": [1, 2, 3, 4, 5],
    "fields": ["name", "email"]
})

# Batch update
workflow.add_node("UserBatchUpdateNode", "update_users_batch", {
    "updates": [
        {"id": 1, "name": "John Updated"},
        {"id": 2, "name": "Jane Updated"},
        {"id": 3, "age": 35}
    ]
})
```

### Transactional Operations

```python
# Transaction context
workflow.add_node("TransactionContextNode", "start_transaction", {
    "isolation_level": "READ_COMMITTED"
})

# Multiple operations in transaction
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "test@example.com"
})

workflow.add_node("UserUpdateNode", "update_related", {
    "id": 1,
    "updates": {"related_user_id": ":new_user_id"}
})

# Commit transaction
workflow.add_node("TransactionCommitNode", "commit_transaction", {})

# Connect transaction flow
workflow.add_connection("start_transaction", "result", "create_user", "input")
workflow.add_connection("create_user", "update_related", "id", "new_user_id")
workflow.add_connection("update_related", "result", "commit_transaction", "input")
```

## Error Handling

### Validation Errors

```python
# Handle validation errors
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "invalid-email",
    "age": 15,
    "on_validation_error": {
        "action": "log_and_continue",
        "fallback_data": {
            "email": "default@example.com",
            "age": 18
        }
    }
})
```

### Conflict Resolution

```python
# Handle unique constraint violations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "existing@example.com",
    "on_conflict": {
        "action": "update",
        "fields": ["name", "updated_at"]
    }
})
```

### Retry Logic

```python
# Automatic retry on temporary failures
workflow.add_node("UserUpdateNode", "update_user", {
    "id": 1,
    "updates": {"name": "Updated Name"},
    "retry": {
        "max_attempts": 3,
        "backoff": "exponential",
        "retry_on": ["connection_error", "timeout"]
    }
})
```

## Performance Optimization

### Field Selection

```python
# Only select needed fields
workflow.add_node("UserListNode", "list_users_minimal", {
    "fields": ["id", "name", "email"],
    "filter": {"active": True}
})
```

### Index Hints

```python
# Use specific index
workflow.add_node("UserListNode", "list_users_indexed", {
    "filter": {"age": {"$gte": 18}},
    "use_index": "idx_age",
    "order_by": ["age"]
})
```

### Query Optimization

```python
# Optimized query
workflow.add_node("UserListNode", "list_users_optimized", {
    "filter": {"active": True},
    "select_for_update": False,
    "prefetch_related": ["profile"],
    "explain": True  # Get query plan
})
```

## Monitoring and Metrics

### Performance Tracking

```python
# Track query performance
workflow.add_node("UserListNode", "list_users_monitored", {
    "filter": {"active": True},
    "monitoring": {
        "track_execution_time": True,
        "track_memory_usage": True,
        "slow_query_threshold": 1.0
    }
})
```

### Audit Logging

```python
# Enable audit logging
workflow.add_node("UserUpdateNode", "update_user_audited", {
    "id": 1,
    "updates": {"name": "New Name"},
    "audit": {
        "enabled": True,
        "user_id": ":current_user_id",
        "action": "update_user",
        "metadata": {"reason": "profile_update"}
    }
})
```

## Best Practices

### 1. Use Appropriate Operations

```python
# Good: Use specific operations
workflow.add_node("UserReadNode", "get_user", {"id": 1})
workflow.add_node("UserUpdateNode", "update_user", {"id": 1, "name": "New Name"})

# Avoid: Generic operations for specific use cases
workflow.add_node("UserListNode", "get_user", {"filter": {"id": 1}, "limit": 1})
```

### 2. Validate Input Data

```python
# Always validate input
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30,
    "validation": {
        "required": ["name", "email"],
        "email_format": True,
        "age_range": {"min": 0, "max": 150}
    }
})
```

### 3. Use Transactions for Related Operations

```python
# Group related operations in transactions
workflow.add_node("TransactionContextNode", "start_tx", {})
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("ProfileCreateNode", "create_profile", {...})
workflow.add_node("TransactionCommitNode", "commit_tx", {})
```

### 4. Handle Errors Gracefully

```python
# Provide fallback behavior
workflow.add_node("UserUpdateNode", "update_user", {
    "id": 1,
    "updates": {"name": "New Name"},
    "on_error": {
        "action": "log_and_continue",
        "fallback_value": {"success": False, "error": "update_failed"}
    }
})
```

### 5. Optimize for Common Use Cases

```python
# Create indexes for common queries
@db.model
class User:
    name: str
    email: str
    age: int
    active: bool = True

    __indexes__ = [
        {'name': 'idx_active_users', 'fields': ['active']},
        {'name': 'idx_email', 'fields': ['email'], 'unique': True},
        {'name': 'idx_age_range', 'fields': ['age']}
    ]
```

## Testing CRUD Operations

### Unit Tests

```python
# Test create operation
def test_create_user():
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create_user", {
        "name": "Test User",
        "email": "test@example.com",
        "age": 25
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["create_user"]["data"]["name"] == "Test User"
    assert results["create_user"]["data"]["email"] == "test@example.com"
```

### Integration Tests

```python
# Test full CRUD lifecycle
def test_user_crud_lifecycle():
    workflow = WorkflowBuilder()

    # Create
    workflow.add_node("UserCreateNode", "create_user", {
        "name": "Test User",
        "email": "test@example.com",
        "age": 25
    })

    # Read
    workflow.add_node("UserReadNode", "read_user", {
        "id": ":user_id"
    })

    # Update
    workflow.add_node("UserUpdateNode", "update_user", {
        "id": ":user_id",
        "name": "Updated User"
    })

    # Delete
    workflow.add_node("UserDeleteNode", "delete_user", {
        "id": ":user_id"
    })

    # Connect operations
    workflow.add_connection("create_user", "read_user", "id", "user_id")
    workflow.add_connection("read_user", "update_user", "id", "user_id")
    workflow.add_connection("update_user", "delete_user", "id", "user_id")

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Verify lifecycle
    assert results["create_user"]["data"]["name"] == "Test User"
    assert results["read_user"]["data"]["name"] == "Test User"
    assert results["update_user"]["data"]["name"] == "Updated User"
    assert results["delete_user"]["success"] == True
```

## Next Steps

- **Bulk Operations**: [Bulk Operations Guide](bulk-operations.md)
- **Workflow Integration**: [Workflow Guide](../workflows/nodes.md)
- **Query Building**: [Query Builder Guide](../advanced/query-builder.md)
- **Performance Optimization**: [Performance Guide](../production/performance.md)

DataFlow CRUD operations provide a consistent, type-safe way to interact with your database while maintaining the flexibility and performance needed for modern applications.

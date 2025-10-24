# DataFlow CRUD Operations

Complete guide to Create, Read, Update, Delete operations in DataFlow workflows.

## ⚠️ CRITICAL: CreateNode vs UpdateNode Pattern Differences

**DataFlow's auto-generated nodes use DIFFERENT parameter patterns depending on the operation.** This is the #1 source of confusion for new developers.

### Quick Comparison Table

| Operation | Pattern | Example Parameters |
|-----------|---------|-------------------|
| **CreateNode** | Flat individual fields | `{"name": "Alice", "email": "alice@example.com"}` |
| **UpdateNode** | Nested filter + fields | `{"filter": {"id": 1}, "fields": {"name": "Alice Updated"}}` |
| **BulkUpdateNode** | Nested filter + fields | `{"filter": {"active": True}, "fields": {"status": "verified"}}` |

### Why Different Patterns?

- **CreateNode**: Creates NEW records, so you provide field values directly (flat structure)
- **UpdateNode**: Modifies EXISTING records, so you need TWO things:
  1. `filter`: Which records to update
  2. `fields`: What to change

### Common Mistake #1: Using CreateNode Pattern on UpdateNode

```python
# ❌ WRONG: Flat fields on UpdateNode (looks like CreateNode)
workflow.add_node("UserUpdateNode", "update", {
    "id": 1,              # This is the CreateNode pattern!
    "name": "Alice Updated"
})
# Error: "UpdateNode requires 'filter' and 'fields' parameters"

# ✅ CORRECT: Nested structure for UpdateNode
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},           # Which record(s)
    "fields": {"name": "Alice Updated"}  # What to change
})
```

### Common Mistake #2: Wrapping CreateNode Fields in 'data'

```python
# ❌ WRONG: Unnecessary 'data' wrapper
workflow.add_node("UserCreateNode", "create", {
    "data": {
        "name": "Alice",
        "email": "alice@example.com"
    }
})
# Error: "CreateNode expects flat field parameters"

# ✅ CORRECT: Flat fields for CreateNode
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})
```

### Auto-Managed Fields

⚠️ **IMPORTANT**: DataFlow automatically manages these fields:
- `created_at` - Set automatically on create
- `updated_at` - Updated automatically on update

**Do NOT include them in your parameters!**

```python
# ❌ WRONG
fields = {
    "name": "Alice",
    "updated_at": datetime.now()  # Remove this!
}

# ✅ CORRECT
fields = {
    "name": "Alice"
    # updated_at is set automatically
}
```

## Working with Datetime Fields (v0.6.4+)

DataFlow automatically converts ISO 8601 datetime strings to Python datetime objects for all datetime fields. This enables seamless integration with PythonCodeNode, external APIs, and data import workflows.

### Supported ISO 8601 Formats

DataFlow recognizes and converts these ISO 8601 datetime formats:

- **Basic**: `2024-01-01T12:00:00`
- **With microseconds**: `2024-01-01T12:00:00.123456`
- **With timezone Z (UTC)**: `2024-01-01T12:00:00Z`
- **With timezone offset**: `2024-01-01T12:00:00+05:30`

### Example: PythonCodeNode Integration

The most common use case is integrating with PythonCodeNode for dynamic timestamp generation:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# PythonCodeNode generates ISO 8601 timestamp
workflow.add_node("PythonCodeNode", "generate_timestamp", {
    "code": """
from datetime import datetime
result = {"registration_date": datetime.now().isoformat()}
    """
})

# CreateNode automatically converts ISO string to datetime
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com",
    "registration_date": "{{generate_timestamp.registration_date}}"  # ISO string → datetime
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Database stores as proper TIMESTAMP type
user = results["create_user"]["data"]
print(f"User registered at: {user['registration_date']}")  # datetime object
```

### Example: UpdateNode with Dynamic Timestamps

```python
# Generate current timestamp in PythonCodeNode
workflow.add_node("PythonCodeNode", "generate_last_login", {
    "code": """
from datetime import datetime
result = {"last_login": datetime.now().isoformat()}
    """
})

# UpdateNode automatically converts the ISO string
workflow.add_node("UserUpdateNode", "update_last_login", {
    "filter": {"id": 1},
    "fields": {
        "last_login": "{{generate_last_login.last_login}}"  # ISO string → datetime
        # updated_at is automatic - don't include it!
    }
})
```

### Example: External API Integration

```python
# Fetch data from external API that returns ISO timestamps
workflow.add_node("PythonCodeNode", "fetch_api_data", {
    "code": """
import requests

response = requests.get("https://api.example.com/users")
users = response.json()  # Contains ISO datetime strings

# API response example:
# [{"name": "Bob", "email": "bob@example.com", "joined_at": "2024-01-15T10:30:00Z"}]

result = {"users": users}
    """
})

# CreateNode automatically converts all datetime strings
workflow.add_node("UserBulkCreateNode", "import_users", {
    "data": "{{fetch_api_data.users}}",  # All ISO strings → datetime
    "batch_size": 100
})
```

### Example: CSV Import with Dates

```python
# Parse CSV file with date columns
workflow.add_node("PythonCodeNode", "parse_csv", {
    "code": """
import csv
from datetime import datetime

users = []
with open('users.csv') as f:
    for row in csv.DictReader(f):
        users.append({
            "name": row["name"],
            "email": row["email"],
            "joined_at": datetime.fromisoformat(row["joined_date"]).isoformat()
        })

result = {"users": users}
    """
})

# BulkCreateNode converts all datetime strings
workflow.add_node("UserBulkCreateNode", "import_csv", {
    "data": "{{parse_csv.users}}",  # ISO strings → datetime
    "batch_size": 1000
})
```

### Backward Compatibility

Existing code passing datetime objects continues to work without any changes:

```python
from datetime import datetime

# Method 1: Direct datetime object (still works)
workflow.add_node("UserCreateNode", "create_user_1", {
    "name": "Bob",
    "email": "bob@example.com",
    "registration_date": datetime.now()  # datetime object
})

# Method 2: ISO 8601 string (now also works)
workflow.add_node("UserCreateNode", "create_user_2", {
    "name": "Charlie",
    "email": "charlie@example.com",
    "registration_date": "2024-01-15T10:30:00"  # ISO string → datetime
})

# Method 3: From PythonCodeNode (recommended)
workflow.add_node("PythonCodeNode", "gen_timestamp", {
    "code": "from datetime import datetime; result = {'ts': datetime.now().isoformat()}"
})
workflow.add_node("UserCreateNode", "create_user_3", {
    "name": "Diana",
    "email": "diana@example.com",
    "registration_date": "{{gen_timestamp.ts}}"  # ISO string → datetime
})
```

### Applies To All CRUD Nodes

Datetime auto-conversion works across all CRUD operations:

- ✅ **CreateNode** - Single record creation
- ✅ **UpdateNode** - Single record updates
- ✅ **BulkCreateNode** - Bulk record creation
- ✅ **BulkUpdateNode** - Bulk record updates
- ✅ **BulkUpsertNode** - Bulk upsert operations

### How It Works

The datetime conversion happens automatically during node execution:

1. **Detection**: DataFlow inspects your model's type annotations to identify `datetime` and `Optional[datetime]` fields
2. **Conversion**: For each datetime field, if the value is a string matching ISO 8601 format, it's converted to a Python `datetime` object
3. **Validation**: Invalid datetime strings raise clear validation errors
4. **Storage**: Converted datetime objects are stored as proper TIMESTAMP types in the database

### Error Handling

If an invalid datetime string is provided:

```python
# Invalid datetime format
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test",
    "registration_date": "invalid-date"  # ❌ Will raise validation error
})
# Error: "Invalid datetime format for field 'registration_date'"
```

### Best Practices

1. **Use PythonCodeNode for Dynamic Timestamps**
   ```python
   # ✅ Recommended - clear and maintainable
   workflow.add_node("PythonCodeNode", "gen_ts", {
       "code": "from datetime import datetime; result = {'ts': datetime.now().isoformat()}"
   })
   workflow.add_node("UserCreateNode", "create", {
       "created_at": "{{gen_ts.ts}}"
   })
   ```

2. **Convert External Data to ISO 8601**
   ```python
   # ✅ Convert to ISO format for automatic handling
   workflow.add_node("PythonCodeNode", "normalize_data", {
       "code": """
   from datetime import datetime

   # Parse various date formats and convert to ISO
   result = {"normalized_date": datetime.strptime(input_date, '%m/%d/%Y').isoformat()}
       """
   })
   ```

3. **Use Timezone-Aware Timestamps**
   ```python
   # ✅ Include timezone information for clarity
   workflow.add_node("PythonCodeNode", "gen_ts_tz", {
       "code": """
   from datetime import datetime, timezone
   result = {"ts": datetime.now(timezone.utc).isoformat()}  # Includes 'Z'
       """
   })
   ```

---

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
    "id": 1  # Use 'id' for primary key
})

# Read user by conditions (more flexible)
workflow.add_node("UserReadNode", "get_user_by_email", {
    "filter": {"email": "john@example.com"}
})

# Read with specific fields
workflow.add_node("UserReadNode", "get_user_fields", {
    "filter": {"id": 1},
    "fields": ["name", "email", "created_at"]
})
```

### Read with Relationships

```python
# Read user with related orders
workflow.add_node("UserReadNode", "get_user_with_orders", {
    "filter": {"id": 1},
    "include": ["orders"]
})

# Read with nested relationships
workflow.add_node("UserReadNode", "get_user_detailed", {
    "filter": {"id": 1},
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
    "filter": {"id": 1},  # Which record to update
    "fields": {            # What to change
        "name": "John Smith",
        "age": 31
    }
})

# Update with multiple conditions
workflow.add_node("UserUpdateNode", "update_user_conditional", {
    "filter": {"id": 1, "active": True},  # Multiple filter conditions
    "fields": {
        "name": "John Smith"
        # updated_at is automatic - don't include it!
    }
})
```

### Partial Updates

```python
# Update only specific fields (all updates are partial by default)
workflow.add_node("UserUpdateNode", "update_user_partial", {
    "filter": {"id": 1},
    "fields": {
        "age": 32
        # Only age is updated, other fields untouched
        # updated_at is automatic
    }
})
```

### Conditional Updates

```python
# Update with version checking (optimistic locking)
workflow.add_node("UserUpdateNode", "update_user_versioned", {
    "filter": {"id": 1, "version": 5},  # Current version in filter
    "fields": {
        "name": "Updated Name",
        "version": 6
    }
})

# Update with custom filter conditions
workflow.add_node("UserUpdateNode", "update_active_users", {
    "filter": {"active": True, "last_login": {"$gt": "2024-01-01"}},
    "fields": {
        "status": "verified"
        # updated_at is automatic
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

### Dynamic Updates with PythonCodeNode (Core SDK v0.9.28+)

**NEW**: Core SDK v0.9.28 enables PythonCodeNode to export multiple variables, making dynamic updates more natural.

**Example: Dynamic field updates with business logic**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

workflow = WorkflowBuilder()

# Prepare dynamic update data with business logic
workflow.add_node("PythonCodeNode", "prepare_update", {
    "code": """
import json

# Prepare filter
filter_data = {"id": summary_id}

# Apply business logic to prepare fields
summary_markdown = generate_markdown(raw_text)
topics_json = json.dumps(extract_topics(raw_text))
edited_by_user = True
    """
})

# UpdateNode receives individual fields via connections
workflow.add_node("ConversationSummaryUpdateNode", "update", {})

# Clean, direct connections (no nested paths!)
workflow.add_connection("prepare_update", "filter_data", "update", "filter")
workflow.add_connection("prepare_update", "summary_markdown", "update", "summary_markdown")
workflow.add_connection("prepare_update", "topics_json", "update", "topics_json")
workflow.add_connection("prepare_update", "edited_by_user", "update", "edited_by_user")

runtime = AsyncLocalRuntime()
result = await runtime.execute_workflow_async(workflow.build(), {
    "summary_id": "summary-123",
    "raw_text": "Conversation text..."
})
```

**Benefits:**
- Natural variable naming (no nested `result` dict)
- Matches developer mental model
- Full DataFlow benefits (no SQL needed!)
- Clean connections (no nested paths like `result.filter`)

**Backward Compatibility:** Old pattern with `result = {"filter": {...}, "fields": {...}}` still works 100%.

## Delete Operations

### Single Record Delete

```python
# Hard delete (permanently removes record)
workflow.add_node("UserDeleteNode", "delete_user", {
    "filter": {"id": 1},  # Which record to delete
    "hard_delete": True
})

# Soft delete (if enabled in model - sets deleted_at)
workflow.add_node("UserDeleteNode", "soft_delete_user", {
    "filter": {"id": 1},
    "soft_delete": True
})
```

### Conditional Delete

```python
# Delete with conditions (use BulkDeleteNode for multiple records)
workflow.add_node("UserBulkDeleteNode", "delete_inactive_users", {
    "filter": {
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
    "filter": {"id": 1},
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

## Critical Limitations & Warnings

### PostgreSQL Array Types
```python
# ❌ AVOID - PostgreSQL List[str] fields cause parameter type issues
@db.model
class BlogPost:
    title: str
    tags: List[str] = []  # CAUSES ERRORS - avoid array types

# ✅ WORKAROUND - Use JSON field or separate table
@db.model
class BlogPost:
    title: str
    tags_json: Dict[str, Any] = {}  # Store as JSON object
```

### JSON Field Behavior
```python
# ❌ WRONG - JSON fields are returned as strings, not parsed objects
result = results["create_config"]
config = result["config"]["database"]["host"]  # FAILS - config is a string

# ✅ CORRECT - Handle JSON as string or parse if needed
result = results["create_config"]
config_str = result["config"]  # This is a string representation
if isinstance(config_str, str):
    import json
    config = json.loads(config_str)  # Parse if needed
```

### Result Access Patterns
```python
# Results can vary between direct access and wrapper access
result = results[node_id]

# Check both patterns:
if isinstance(result, dict) and "output" in result:
    data = result["output"]  # Wrapper format
else:
    data = result  # Direct format
```

## Best Practices

### 1. Use Appropriate Operations

```python
# Good: Use specific operations
workflow.add_node("UserReadNode", "get_user", {"record_id": 1})
workflow.add_node("UserUpdateNode", "update_user", {"record_id": 1, "name": "New Name"})

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

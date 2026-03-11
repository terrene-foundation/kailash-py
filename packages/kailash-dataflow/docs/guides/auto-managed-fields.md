# Auto-Managed Fields in DataFlow: Timestamps and System Fields

## What Is This

DataFlow automatically manages certain fields in your models without requiring manual intervention. The most common auto-managed fields are **timestamps** (`created_at`, `updated_at`) which are handled automatically by the framework.

**Key Rule**: NEVER manually include `created_at` or `updated_at` in CreateNode, UpdateNode, or any other operations. DataFlow manages these fields automatically.

## Why This Matters

Including auto-managed fields in your operations causes validation errors:

```python
# ❌ WRONG - Causes VAL-005 validation error
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-10-30T12:00:00",  # Error: created_at is auto-managed
    "updated_at": "2025-10-30T12:00:00"   # Error: updated_at is auto-managed
})

# Error: ValidationError: Fields 'created_at', 'updated_at' are auto-managed and cannot be manually set
```

DataFlow handles timestamp management at the database layer, ensuring consistency and preventing manipulation.

## How Auto-Management Works

### Automatic Timestamp Fields

When you define a model, DataFlow automatically adds and manages these fields:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str
    email: str
    # created_at: datetime  # ❌ DON'T define - added automatically
    # updated_at: datetime  # ❌ DON'T define - added automatically

# DataFlow automatically adds:
# - created_at: datetime - Set on CREATE, never changed
# - updated_at: datetime - Set on CREATE, updated on every UPDATE
```

### ✅ Correct CREATE Operation

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
    # ✅ OMIT created_at and updated_at
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Results automatically include timestamps
user = results["create"]
print(user)
# {
#     "id": "user-123",
#     "name": "Alice",
#     "email": "alice@example.com",
#     "created_at": "2025-10-30T12:00:00.123456",  # ✅ Added automatically
#     "updated_at": "2025-10-30T12:00:00.123456"   # ✅ Added automatically
# }
```

### ✅ Correct UPDATE Operation

```python
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
    # ✅ OMIT updated_at - DataFlow updates it automatically
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Results show updated_at changed automatically
user = results["update"]
print(user)
# {
#     "id": "user-123",
#     "name": "Alice Updated",
#     "email": "alice@example.com",
#     "created_at": "2025-10-30T12:00:00.123456",  # ✅ Unchanged
#     "updated_at": "2025-10-30T12:15:30.789012"   # ✅ Updated automatically
# }
```

## Timestamp Behavior

### CREATE Operations

**What happens**:
1. You provide only model-specific fields (`id`, `name`, `email`, etc.)
2. DataFlow automatically adds `created_at` with current timestamp
3. DataFlow automatically adds `updated_at` with current timestamp (same as `created_at`)

```python
# Input (what you provide)
{
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
}

# Output (what DataFlow returns)
{
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "created_at": "2025-10-30T12:00:00.123456",  # ✅ Auto-added
    "updated_at": "2025-10-30T12:00:00.123456"   # ✅ Auto-added (same as created_at)
}
```

### UPDATE Operations

**What happens**:
1. You provide only fields to update (`name`, `email`, etc.)
2. DataFlow leaves `created_at` unchanged
3. DataFlow automatically updates `updated_at` with current timestamp

```python
# Input (what you provide)
{
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
}

# Output (what DataFlow returns)
{
    "id": "user-123",
    "name": "Alice Updated",
    "email": "alice@example.com",
    "created_at": "2025-10-30T12:00:00.123456",  # ✅ Unchanged
    "updated_at": "2025-10-30T12:15:30.789012"   # ✅ Updated automatically
}
```

### LIST/READ Operations

Timestamps are automatically included in all query results:

```python
workflow.add_node("UserListNode", "list", {
    "filters": {"status": "active"},
    "limit": 20
})

results, _ = runtime.execute(workflow.build())

# All records include timestamps
for user in results["list"]:
    print(f"User {user['name']}")
    print(f"  Created: {user['created_at']}")
    print(f"  Updated: {user['updated_at']}")
```

## Common Mistakes and Fixes

### Mistake 1: Including created_at in CREATE

```python
# ❌ WRONG
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-10-30T12:00:00"  # Error!
})

# ✅ CORRECT
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # Omit created_at - handled automatically
})
```

### Mistake 2: Including updated_at in UPDATE

```python
# ❌ WRONG
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {
        "name": "Alice Updated",
        "updated_at": "2025-10-30T12:00:00"  # Error!
    }
})

# ✅ CORRECT
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
    # Omit updated_at - handled automatically
})
```

### Mistake 3: Defining timestamps in model

```python
# ❌ WRONG
from datetime import datetime

@db.model
class User:
    id: str
    name: str
    created_at: datetime  # Error: Auto-managed field shouldn't be defined
    updated_at: datetime  # Error: Auto-managed field shouldn't be defined

# ✅ CORRECT
@db.model
class User:
    id: str
    name: str
    # Omit created_at and updated_at - added automatically
```

### Mistake 4: Filtering by exact timestamp

```python
# ⚠️ FRAGILE - Exact timestamp matches are unreliable
workflow.add_node("UserListNode", "list", {
    "filters": {"created_at": "2025-10-30T12:00:00.123456"}
})

# ✅ BETTER - Use range queries
workflow.add_node("UserListNode", "list", {
    "filters": {
        "created_at__gte": "2025-10-30T00:00:00",  # Greater than or equal
        "created_at__lt": "2025-10-31T00:00:00"    # Less than
    }
})
```

## Advanced: Custom Timestamp Fields

If you need additional timestamp fields beyond `created_at` and `updated_at`, define them as regular fields and manage manually:

```python
from datetime import datetime

@db.model
class Post:
    id: str
    title: str
    content: str
    published_at: datetime  # ✅ OK: Custom timestamp, not auto-managed
    scheduled_at: datetime  # ✅ OK: Custom timestamp, not auto-managed
    # created_at: datetime  # ❌ Auto-managed - don't define
    # updated_at: datetime  # ❌ Auto-managed - don't define

# Manual management of custom timestamps
import datetime as dt

workflow.add_node("PostCreateNode", "create", {
    "id": "post-123",
    "title": "My Post",
    "content": "Hello, world!",
    "published_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "scheduled_at": None  # Not yet scheduled
    # Omit created_at, updated_at - auto-managed
})
```

## Timezone Handling

DataFlow stores all timestamps in **UTC** and returns them as **ISO 8601** strings with timezone information:

```python
# Timestamp format: YYYY-MM-DDTHH:MM:SS.ffffff+00:00
"created_at": "2025-10-30T12:00:00.123456+00:00"

# Always UTC (offset +00:00)
# Microsecond precision (.123456)
# ISO 8601 format
```

### Converting to Local Timezone

```python
from datetime import datetime
import pytz

# Get user from DataFlow
user = results["create"]

# Parse ISO 8601 timestamp
created_at = datetime.fromisoformat(user["created_at"])

# Convert to local timezone (e.g., US/Pacific)
pacific = pytz.timezone('US/Pacific')
local_time = created_at.astimezone(pacific)

print(f"Created at (UTC): {created_at}")
print(f"Created at (Pacific): {local_time}")
```

## Database-Level Implementation

DataFlow implements auto-managed fields at the database level using triggers and default values:

### PostgreSQL

```sql
-- DataFlow creates tables with automatic timestamp columns
CREATE TABLE users (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    email VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update updated_at automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### MySQL

```sql
-- DataFlow creates tables with automatic timestamp columns
CREATE TABLE users (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### SQLite

```sql
-- DataFlow creates tables with automatic timestamp columns
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    created_at TEXT DEFAULT (datetime('now', 'utc')),
    updated_at TEXT DEFAULT (datetime('now', 'utc'))
);

-- Trigger to update updated_at automatically
CREATE TRIGGER update_users_updated_at
    AFTER UPDATE ON users
    FOR EACH ROW
BEGIN
    UPDATE users SET updated_at = datetime('now', 'utc')
    WHERE id = NEW.id;
END;
```

## Querying by Timestamps

### Filter by Creation Time

```python
# Users created today
from datetime import datetime, timedelta, timezone

today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
tomorrow = today + timedelta(days=1)

workflow.add_node("UserListNode", "list", {
    "filters": {
        "created_at__gte": today.isoformat(),
        "created_at__lt": tomorrow.isoformat()
    }
})
```

### Filter by Update Time

```python
# Users updated in last hour
one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

workflow.add_node("UserListNode", "list", {
    "filters": {
        "updated_at__gte": one_hour_ago.isoformat()
    }
})
```

### Order by Timestamps

```python
# Most recently created users first
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "-created_at",  # ✅ Descending order (newest first)
    "limit": 10
})

# Least recently updated users first
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "updated_at",  # ✅ Ascending order (oldest first)
    "limit": 10
})
```

## Bulk Operations

Auto-managed fields work correctly in bulk operations:

### BulkCreateNode

```python
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "records": [
        {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        {"id": "user-2", "name": "Bob", "email": "bob@example.com"},
        {"id": "user-3", "name": "Charlie", "email": "charlie@example.com"}
    ]
    # Omit created_at, updated_at - handled automatically for ALL records
})

results, _ = runtime.execute(workflow.build())

# All records have timestamps
for user in results["bulk_create"]:
    print(f"Created {user['name']} at {user['created_at']}")
```

### BulkUpdateNode

```python
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "records": [
        {"id": "user-1", "name": "Alice Updated"},
        {"id": "user-2", "name": "Bob Updated"}
    ]
    # Omit updated_at - handled automatically for ALL records
})

results, _ = runtime.execute(workflow.build())

# All records have updated_at changed
for user in results["bulk_update"]:
    print(f"Updated {user['name']} at {user['updated_at']}")
```

## Migration from Other ORMs

### From SQLAlchemy

```python
# SQLAlchemy pattern
from sqlalchemy import Column, String, DateTime
from datetime import datetime

class User(Base):
    id = Column(String, primary_key=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)  # ❌ Old pattern
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # ❌ Old pattern

# DataFlow pattern
@db.model
class User:
    id: str
    name: str
    # ✅ Omit created_at, updated_at - handled automatically
```

### From Django ORM

```python
# Django pattern
from django.db import models

class User(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)  # ❌ Old pattern
    updated_at = models.DateTimeField(auto_now=True)      # ❌ Old pattern

# DataFlow pattern
@db.model
class User:
    id: str
    name: str
    # ✅ Omit created_at, updated_at - handled automatically
```

## Validation Error Reference

**Error Code**: VAL-005
**Error Message**: "Fields 'created_at', 'updated_at' are auto-managed and cannot be manually set"
**Cause**: Attempting to manually set auto-managed timestamp fields
**Solution**: Remove `created_at` and `updated_at` from operation parameters

**Example Error**:

```python
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-10-30T12:00:00"  # ❌ Causes VAL-005
})

# Triggers error:
# ValidationError: Field 'created_at' is auto-managed and cannot be manually set.
# Remove 'created_at' from parameters - DataFlow manages it automatically.
```

**Fix**:

```python
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # ✅ Omit created_at - handled automatically
})
```

## Best Practices

1. **Never define created_at or updated_at in models**
   ```python
   # ✅ CORRECT
   @db.model
   class User:
       id: str
       name: str
       # Omit timestamp fields
   ```

2. **Never include timestamps in CREATE/UPDATE operations**
   ```python
   # ✅ CORRECT
   workflow.add_node("UserCreateNode", "create", {
       "id": "user-123",
       "name": "Alice"
       # Omit created_at, updated_at
   })
   ```

3. **Use range queries for timestamp filtering**
   ```python
   # ✅ CORRECT
   workflow.add_node("UserListNode", "list", {
       "filters": {
           "created_at__gte": start_date,
           "created_at__lt": end_date
       }
   })
   ```

4. **Always use UTC for timestamp comparisons**
   ```python
   # ✅ CORRECT
   from datetime import datetime, timezone

   now = datetime.now(timezone.utc)
   ```

5. **Store timestamps as ISO 8601 strings for portability**
   ```python
   # ✅ CORRECT
   timestamp = datetime.now(timezone.utc).isoformat()
   ```

## Complete Example

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from datetime import datetime, timezone, timedelta

# Initialize DataFlow
db = DataFlow("postgresql://localhost/mydb")

# Define model (no timestamp fields)
@db.model
class User:
    id: str
    name: str
    email: str
    status: str

# Create user (omit timestamps)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "status": "active"
    # ✅ Omit created_at, updated_at
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Timestamps automatically included
user = results["create"]
print(f"User created at: {user['created_at']}")
print(f"User updated at: {user['updated_at']}")

# Update user (omit updated_at)
workflow2 = WorkflowBuilder()
workflow2.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"status": "inactive"}
    # ✅ Omit updated_at
})

results2, _ = runtime.execute(workflow2.build())
user_updated = results2["update"]
print(f"User created at: {user_updated['created_at']}")  # Unchanged
print(f"User updated at: {user_updated['updated_at']}")  # Changed automatically

# Query recently updated users
one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

workflow3 = WorkflowBuilder()
workflow3.add_node("UserListNode", "list", {
    "filters": {
        "updated_at__gte": one_hour_ago.isoformat()
    },
    "order_by": "-updated_at",
    "limit": 10
})

results3, _ = runtime.execute(workflow3.build())
for user in results3["list"]:
    print(f"User {user['name']} updated at {user['updated_at']}")
```

## Troubleshooting

### Error: "Field 'created_at' is auto-managed"

**Cause**: Manually including `created_at` in operation

**Fix**: Remove `created_at` from parameters

```python
# ❌ Before
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-10-30T12:00:00"
})

# ✅ After
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
})
```

### Timestamps not showing in results

**Cause**: Using raw SQL queries instead of DataFlow nodes

**Fix**: Use DataFlow generated nodes for automatic timestamp management

```python
# ✅ Use DataFlow nodes, not raw SQL
workflow.add_node("UserCreateNode", "create", {...})
```

### Timestamp timezone confusion

**Cause**: Not accounting for UTC storage

**Fix**: Always convert to UTC before comparison

```python
# ✅ Use UTC
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
```

## Related Guides

- [Primary Keys](primary-keys.md) - The `id` field requirement
- [Flat Fields Pattern](flat-fields.md) - No nested objects in model definitions
- [Common Patterns](common-patterns.md) - Best practices and anti-patterns
- [Migration from SQLAlchemy](from-sqlalchemy.md) - Converting existing ORM models

## Summary

- **Never define created_at or updated_at in models** - DataFlow adds them automatically
- **Never include timestamps in operations** - CREATE, UPDATE, and bulk operations
- **Timestamps are UTC ISO 8601 strings** - Consistent format across all databases
- **Use range queries for filtering** - Avoid exact timestamp matches
- **Database-level management** - Triggers ensure consistency

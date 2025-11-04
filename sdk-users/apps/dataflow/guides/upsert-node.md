# UpsertNode Guide - Insert or Update in One Operation

## Table of Contents
1. [What is UpsertNode?](#what-is-upsertnode)
2. [Basic Usage](#basic-usage)
3. [Custom Conflict Fields (v0.8.0+)](#custom-conflict-fields-v080)
4. [Parameter Reference](#parameter-reference)
5. [Return Structure](#return-structure)
6. [Common Patterns](#common-patterns)
7. [Database Behavior](#database-behavior)
8. [Troubleshooting](#troubleshooting)

## What is UpsertNode?

**UpsertNode** performs "upsert" operations (INSERT if record doesn't exist, UPDATE if it does) in a single atomic operation. This eliminates the need for separate "check if exists, then insert or update" logic, reducing database round-trips and race conditions.

### Key Features

- **Atomic operation**: Single database query for INSERT or UPDATE
- **Conflict detection**: Specify which fields determine uniqueness (v0.8.0+)
- **Cross-database**: Works identically on PostgreSQL, MySQL, and SQLite
- **Natural keys**: Use any unique field(s), not just `id`
- **Return metadata**: Tells you whether INSERT or UPDATE occurred

### When to Use UpsertNode

**Use UpsertNode when you want to**:
- ✅ Ensure a record exists with specific values (idempotent operations)
- ✅ Update if exists, insert if not (single atomic operation)
- ✅ Use natural keys (email, SKU, username) instead of database IDs
- ✅ Avoid race conditions between "check exists" and "insert/update"

**Don't use UpsertNode when**:
- ❌ You always insert new records (use CreateNode instead)
- ❌ You always update existing records (use UpdateNode instead)
- ❌ You need conditional logic beyond conflict detection

## Basic Usage

### Simple Upsert by ID

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    email: str
    name: str

await db.initialize()

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"id": "user-123"},
    "update": {"name": "Alice Updated"},
    "create": {
        "id": "user-123",
        "email": "alice@example.com",
        "name": "Alice"
    }
})

# Execute
runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

# Check what happened
if results["upsert"]["created"]:
    print("Inserted new user")
else:
    print("Updated existing user")

print(results["upsert"]["record"])
```

### Understanding the Parameters

**`where`**: Fields to identify the record
**`update`**: Fields to update if record exists
**`create`**: All fields to insert if record doesn't exist

**Behavior**:
1. Look for existing record matching `where` criteria
2. If found: Update fields specified in `update`
3. If not found: Insert all fields from `create`

## Custom Conflict Fields (v0.8.0+)

Starting in v0.8.0, you can specify which fields determine uniqueness using the `conflict_on` parameter. This is essential for natural keys and composite unique constraints.

### Single Field Conflict

Use any unique field (email, SKU, username) for conflict detection:

```python
@db.model
class User:
    id: str
    email: str  # Unique field
    name: str

# Upsert based on email (not id)
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],  # Conflict detection on email
    "update": {"name": "Alice Updated"},
    "create": {
        "id": "user-123",
        "email": "alice@example.com",
        "name": "Alice"
    }
})

# First run: INSERT (email doesn't exist)
# Second run: UPDATE (email exists, update name)
```

**Why `conflict_on` matters**:
- Default behavior: Conflict detection uses all fields in `where`
- With `conflict_on`: Conflict detection uses only specified fields
- Use when your unique constraint differs from lookup fields

### Composite Key Conflict

For tables with multi-column unique constraints:

```python
@db.model
class OrderItem:
    id: str
    order_id: str
    product_id: str
    quantity: int

# Composite unique constraint: (order_id, product_id)
workflow.add_node("OrderItemUpsertNode", "upsert", {
    "where": {"order_id": "order-123", "product_id": "prod-456"},
    "conflict_on": ["order_id", "product_id"],  # Composite key
    "update": {"quantity": 10},
    "create": {
        "id": "item-789",
        "order_id": "order-123",
        "product_id": "prod-456",
        "quantity": 5
    }
})
```

**Behavior**:
- If `(order-123, prod-456)` exists: Update quantity to 10
- If not: Insert new OrderItem with quantity 5

### Product SKU Example

Real-world example: Product catalog where SKU is the natural key:

```python
@db.model
class Product:
    id: str
    sku: str      # Natural key (unique)
    name: str
    price: float

# Upsert by SKU (not database ID)
workflow.add_node("ProductUpsertNode", "upsert", {
    "where": {"sku": "WIDGET-2024"},
    "conflict_on": ["sku"],
    "update": {"price": 99.99},  # Update price if exists
    "create": {
        "id": "prod-001",
        "sku": "WIDGET-2024",
        "name": "Super Widget",
        "price": 49.99
    }
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

if results["upsert"]["created"]:
    print(f"Created new product: {results['upsert']['record']['name']}")
else:
    print(f"Updated price to ${results['upsert']['record']['price']}")
```

## Parameter Reference

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `where` | dict | Yes | - | Fields to identify the record |
| `update` | dict | No | `{}` | Fields to update if record exists |
| `create` | dict | No | `{}` | All fields to insert if record doesn't exist |
| `conflict_on` | list | No | `where` keys | Fields for conflict detection (v0.8.0+) |

### When to Use `conflict_on`

**Use `conflict_on` when**:
- ✅ You have a natural key (email, username, SKU)
- ✅ You have composite unique constraints
- ✅ Conflict detection should use different fields than lookup

**Omit `conflict_on` when**:
- ✅ Conflict detection should use all `where` fields (default behavior)
- ✅ Using simple `id` lookup (backward compatible)

## Return Structure

```python
{
    "created": bool,    # True if INSERT, False if UPDATE
    "action": str,      # "created" or "updated"
    "record": dict      # The final record after upsert
}
```

### Example Return Values

**After INSERT**:
```python
{
    "created": True,
    "action": "created",
    "record": {
        "id": "user-123",
        "email": "alice@example.com",
        "name": "Alice"
    }
}
```

**After UPDATE**:
```python
{
    "created": False,
    "action": "updated",
    "record": {
        "id": "user-123",
        "email": "alice@example.com",
        "name": "Alice Updated"
    }
}
```

## Common Patterns

### Pattern 1: Email-Based User Upsert

Ensure user exists with updated data:

```python
workflow.add_node("UserUpsertNode", "ensure_user", {
    "where": {"email": user_email},
    "conflict_on": ["email"],
    "update": {
        "last_login": datetime.now().isoformat(),
        "name": user_name
    },
    "create": {
        "id": user_id,
        "email": user_email,
        "name": user_name,
        "created_at": datetime.now().isoformat()
    }
})
```

**Use case**: User login - update last_login if exists, create if first login.

### Pattern 2: Inventory Update

Update quantity or create new inventory record:

```python
workflow.add_node("InventoryUpsertNode", "sync_inventory", {
    "where": {
        "warehouse_id": warehouse_id,
        "product_id": product_id
    },
    "conflict_on": ["warehouse_id", "product_id"],
    "update": {"quantity": new_quantity},
    "create": {
        "id": inventory_id,
        "warehouse_id": warehouse_id,
        "product_id": product_id,
        "quantity": new_quantity
    }
})
```

**Use case**: Inventory sync - update if product exists in warehouse, create if new.

### Pattern 3: Idempotent API Requests

Ensure request is only processed once:

```python
workflow.add_node("RequestUpsertNode", "track_request", {
    "where": {"request_id": request_id},
    "conflict_on": ["request_id"],
    "update": {},  # Don't update if exists (idempotent)
    "create": {
        "id": id,
        "request_id": request_id,
        "data": request_data,
        "processed_at": datetime.now().isoformat()
    }
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

if results["track_request"]["created"]:
    # Process the request
    process_request(request_data)
else:
    # Request already processed
    return {"status": "duplicate", "message": "Request already processed"}
```

**Use case**: Idempotent webhooks - prevent duplicate processing.

### Pattern 4: Session Management

Update existing session or create new:

```python
workflow.add_node("SessionUpsertNode", "manage_session", {
    "where": {"session_token": token},
    "conflict_on": ["session_token"],
    "update": {
        "last_activity": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
    },
    "create": {
        "id": session_id,
        "session_token": token,
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
    }
})
```

**Use case**: Session renewal - extend expiration if exists, create if new.

### Pattern 5: Configuration Sync

Sync configuration from external source:

```python
# Sync multiple configurations
for config in external_configs:
    workflow.add_node("ConfigUpsertNode", f"sync_{config['key']}", {
        "where": {"key": config["key"]},
        "conflict_on": ["key"],
        "update": {
            "value": config["value"],
            "updated_at": datetime.now().isoformat()
        },
        "create": {
            "id": generate_id(),
            "key": config["key"],
            "value": config["value"],
            "created_at": datetime.now().isoformat()
        }
    })
```

**Use case**: Configuration import - update if exists, create if new.

## Database Behavior

### PostgreSQL

```sql
-- Generated SQL
INSERT INTO users (id, email, name)
VALUES ('user-123', 'alice@example.com', 'Alice')
ON CONFLICT (email) DO UPDATE SET
    name = EXCLUDED.name;
```

**Features**:
- Uses `INSERT ... ON CONFLICT ... DO UPDATE SET`
- Atomic and thread-safe
- Detects INSERT vs UPDATE via `xmax` flag
- Requires unique index/constraint on conflict fields

### MySQL

```sql
-- Generated SQL
INSERT INTO users (id, email, name)
VALUES ('user-123', 'alice@example.com', 'Alice')
ON DUPLICATE KEY UPDATE
    name = VALUES(name);
```

**Features**:
- Uses `INSERT ... ON DUPLICATE KEY UPDATE`
- Atomic and thread-safe
- Pre-check query to detect INSERT vs UPDATE
- Requires unique index/constraint on conflict fields

### SQLite

```sql
-- Generated SQL
INSERT INTO users (id, email, name)
VALUES ('user-123', 'alice@example.com', 'Alice')
ON CONFLICT (email) DO UPDATE SET
    name = excluded.name;
```

**Features**:
- Uses `INSERT ... ON CONFLICT ... DO UPDATE SET`
- Atomic within transaction
- Pre-check query to detect INSERT vs UPDATE
- Requires unique index/constraint on conflict fields

### Cross-Database Consistency

All three databases:
- ✅ NULL values in conflict fields don't trigger conflicts (SQL standard)
- ✅ Require unique index/constraint on conflict fields
- ✅ String IDs fully supported
- ✅ Return same result structure

## Troubleshooting

### Error: "No unique index/constraint on conflict fields"

**Cause**: Database requires unique index for upsert operations.

**Solution**: Create unique index on conflict_on fields:

```python
# PostgreSQL
CREATE UNIQUE INDEX idx_users_email ON users(email);

# Or in model definition (requires auto-migration)
@db.model
class User:
    id: str
    email: str
    name: str

    __dataflow__ = {
        'indexes': [
            {'fields': ['email'], 'unique': True}
        ]
    }
```

### Error: "Multiple records updated"

**Cause**: `conflict_on` fields don't uniquely identify records.

**Solution**: Ensure conflict_on fields have unique constraint:

```python
# ❌ WRONG - status is not unique
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"status": "active"},
    "conflict_on": ["status"],  # Multiple users can be active!
    ...
})

# ✅ CORRECT - email is unique
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],  # Only one user per email
    ...
})
```

### Error: "Conflict not detected"

**Cause**: NULL values in conflict fields (NULL != NULL in SQL).

**Check**: Do conflict_on fields have NULL values?

```python
# ❌ WRONG - email is NULL, won't match
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": None},
    "conflict_on": ["email"],
    ...
})

# ✅ CORRECT - Use non-NULL unique field
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],
    ...
})
```

### Issue: Upsert Always Inserts (Never Updates)

**Cause**: Conflict detection not matching existing records.

**Debug Steps**:

1. **Check conflict_on matches database unique constraint**:
```python
# Database has unique constraint on (order_id, product_id)
# ❌ WRONG - conflict_on doesn't match
workflow.add_node("OrderItemUpsertNode", "upsert", {
    "where": {"order_id": "order-123", "product_id": "prod-456"},
    "conflict_on": ["order_id"],  # Only checks order_id!
    ...
})

# ✅ CORRECT - conflict_on matches constraint
workflow.add_node("OrderItemUpsertNode", "upsert", {
    "where": {"order_id": "order-123", "product_id": "prod-456"},
    "conflict_on": ["order_id", "product_id"],  # Matches constraint
    ...
})
```

2. **Verify unique constraint exists**:
```sql
-- PostgreSQL
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'order_items';

-- Should show UNIQUE constraint on (order_id, product_id)
```

3. **Check field values match exactly**:
```python
# Values must match exactly (case-sensitive)
# ❌ WRONG - case mismatch
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "Alice@Example.com"},  # Different case
    "conflict_on": ["email"],
    ...
})

# ✅ CORRECT - exact match
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},  # Exact match
    "conflict_on": ["email"],
    ...
})
```

### Issue: Update Fields Not Applying

**Cause**: Update fields not specified in `update` parameter.

**Solution**: Include all fields you want to update:

```python
# ❌ WRONG - name not in update
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],
    "update": {"last_login": datetime.now().isoformat()},  # Only updates last_login
    "create": {"id": "user-123", "email": "alice@example.com", "name": "Alice"}
})
# Result: If user exists, name is NOT updated

# ✅ CORRECT - name in update
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],
    "update": {
        "name": "Alice Updated",  # Now updates name
        "last_login": datetime.now().isoformat()
    },
    "create": {"id": "user-123", "email": "alice@example.com", "name": "Alice"}
})
```

## Best Practices

1. **Always specify `conflict_on` for natural keys**:
```python
# ✅ BEST PRACTICE
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": email},
    "conflict_on": ["email"],  # Explicit conflict detection
    ...
})
```

2. **Create unique indexes before upserting**:
```sql
CREATE UNIQUE INDEX idx_users_email ON users(email);
```

3. **Check `created` flag for conditional logic**:
```python
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

if results["upsert"]["created"]:
    # First time user - send welcome email
    send_welcome_email(results["upsert"]["record"]["email"])
else:
    # Returning user - log activity
    log_user_activity(results["upsert"]["record"]["id"])
```

4. **Use idempotent patterns for webhooks**:
```python
# Ensure webhook is only processed once
workflow.add_node("WebhookUpsertNode", "track", {
    "where": {"webhook_id": webhook_id},
    "conflict_on": ["webhook_id"],
    "update": {},  # Empty update = idempotent
    "create": {"id": id, "webhook_id": webhook_id, "data": data}
})

if not results["track"]["created"]:
    return {"status": "duplicate"}  # Already processed
```

5. **Include timestamps for audit trails**:
```python
workflow.add_node("ConfigUpsertNode", "sync", {
    "where": {"key": key},
    "conflict_on": ["key"],
    "update": {
        "value": value,
        "updated_at": datetime.now().isoformat()
    },
    "create": {
        "id": id,
        "key": key,
        "value": value,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
})
```

## Related Documentation

- **CreateNode Guide**: For always inserting new records
- **UpdateNode Guide**: For always updating existing records
- **Error Handling Guide**: `sdk-users/apps/dataflow/guides/error-handling.md`
- **Node Reference**: `sdk-users/apps/dataflow/docs/reference/nodes.md`

## Version History

- **v0.8.0**: Added `conflict_on` parameter for custom conflict fields
- **v0.4.6**: Initial UpsertNode release with basic conflict detection

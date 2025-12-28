# CreateNode vs UpdateNode: Complete Guide

**Critical**: CreateNode and UpdateNode have **completely different parameter patterns**. Applying CreateNode patterns to UpdateNode (or vice versa) is the #1 cause of DataFlow debugging sessions lasting 1-2 hours.

---

## Quick Decision Tree

```
Need to create new records?
├─ YES → Use CreateNode (flat fields)
│   └─ Multiple records at once? → Use BulkCreateNode
│
└─ NO → Need to update existing records?
    ├─ YES → Use UpdateNode (filter + fields structure)
    │   └─ Multiple records? → Use BulkUpdateNode
    │
    └─ Not sure if record exists?
        └─ Use UpsertNode (where + update + create)
```

---

## Side-by-Side Comparison

| Aspect | CreateNode | UpdateNode |
|--------|------------|------------|
| **Purpose** | Insert new records | Modify existing records |
| **Parameter Structure** | **Flat fields** (`{"name": "Alice"}`) | **Nested structure** (`{"filter": {...}, "fields": {...}}`) |
| **Primary Key** | **Required** - must provide `id` | **Optional** - only in filter to identify record |
| **Auto-managed Fields** | **Never include** (`created_at`, `updated_at`) | **Can update** manually if needed |
| **Validation** | Checks all required fields present | Checks filter identifies records |
| **Return Value** | `{"record": {...}}` - the created record | `{"record": {...}, "updated_count": N}` |
| **Common Mistake** | Including `created_at`/`updated_at` | Using flat fields instead of nested |
| **Time to Debug** | 30-60 minutes (field conflicts) | 1-2 hours (pattern mismatch) |

---

## CreateNode: Flat Field Pattern

### Basic Usage

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str
    email: str

# ✅ CORRECT - Flat fields
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",          # REQUIRED
    "name": "Alice",           # Flat field
    "email": "alice@example.com"  # Flat field
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

print(results["create_user"]["record"])
# {'id': 'user-123', 'name': 'Alice', 'email': 'alice@example.com', 'created_at': '2024-...'}
```

### Common Mistakes with CreateNode

#### ❌ WRONG: Including Auto-Managed Fields

```python
# ❌ WILL FAIL - Don't include created_at/updated_at
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "created_at": datetime.now(),  # ❌ ERROR: Auto-managed field
    "updated_at": datetime.now()   # ❌ ERROR: Auto-managed field
})

# Error: "created_at is auto-managed and should not be provided"
```

**Why?** DataFlow automatically manages `created_at`, `updated_at`, `created_by`, `updated_by` fields. Including them causes validation errors.

**Fix**: Remove auto-managed fields entirely.

```python
# ✅ CORRECT
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
    # created_at/updated_at added automatically
})
```

#### ❌ WRONG: Missing Primary Key

```python
# ❌ WILL FAIL - Primary key 'id' required
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
    # Missing 'id' field
})

# Error: "Missing required parameter 'id'"
```

**Why?** DataFlow requires `id` as the primary key. Not `user_id`, not `pk`, exactly `id`.

**Fix**: Always include `id` field.

```python
# ✅ CORRECT
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",  # Primary key required
    "name": "Alice",
    "email": "alice@example.com"
})
```

#### ❌ WRONG: Using Nested Structure

```python
# ❌ WILL FAIL - Nested structure is for UpdateNode
workflow.add_node("UserCreateNode", "create_user", {
    "data": {  # ❌ Don't nest in CreateNode
        "id": "user-123",
        "name": "Alice"
    }
})

# Error: "Missing required parameter 'id'"
```

**Why?** CreateNode expects **flat fields**, not nested structures. Nesting is for UpdateNode.

**Fix**: Use flat field structure.

```python
# ✅ CORRECT
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",  # Flat
    "name": "Alice"    # Flat
})
```

#### ❌ WRONG: Using UpdateNode Parameter Pattern

```python
# ❌ WILL FAIL - This is UpdateNode pattern
workflow.add_node("UserCreateNode", "create_user", {
    "filter": {"id": "user-123"},  # ❌ Wrong pattern
    "fields": {"name": "Alice"}    # ❌ Wrong pattern
})

# Error: "Missing required parameter 'id'"
```

**Why?** `filter`/`fields` structure is for **UpdateNode**, not CreateNode.

**Fix**: Use flat fields for CreateNode.

```python
# ✅ CORRECT
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",
    "name": "Alice"
})
```

---

## UpdateNode: Filter + Fields Pattern

### Basic Usage

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str
    email: str

# ✅ CORRECT - Nested filter + fields structure
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {  # Which record(s) to update
        "id": "user-123"
    },
    "fields": {  # What to change
        "name": "Alice Updated",
        "email": "alice-new@example.com"
    }
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

print(results["update_user"]["record"])
# {'id': 'user-123', 'name': 'Alice Updated', 'email': 'alice-new@example.com', ...}
print(results["update_user"]["updated_count"])
# 1
```

### Common Mistakes with UpdateNode

#### ❌ WRONG: Using Flat Fields

```python
# ❌ WILL FAIL - Flat fields are for CreateNode
workflow.add_node("UserUpdateNode", "update_user", {
    "id": "user-123",      # ❌ Wrong: Not flat
    "name": "Alice",       # ❌ Wrong: Not flat
    "email": "alice@example.com"  # ❌ Wrong: Not flat
})

# Error: "Missing required parameter 'filter'"
```

**Why?** UpdateNode requires **nested structure** with `filter` and `fields` keys.

**Fix**: Use nested filter + fields structure.

```python
# ✅ CORRECT
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},  # Nested
    "fields": {                     # Nested
        "name": "Alice",
        "email": "alice@example.com"
    }
})
```

#### ❌ WRONG: Including `id` in `fields`

```python
# ❌ WILL FAIL - Can't update primary key
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},
    "fields": {
        "id": "user-456",  # ❌ Can't change primary key
        "name": "Alice"
    }
})

# Error: "Cannot update primary key 'id'"
```

**Why?** Primary keys are immutable in DataFlow. Use filter to identify, never change.

**Fix**: Remove `id` from fields, only use in filter.

```python
# ✅ CORRECT
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},  # Identify record
    "fields": {
        "name": "Alice"  # Update fields only
    }
})
```

#### ❌ WRONG: Empty Filter

```python
# ❌ DANGEROUS - Will update ALL records
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {},  # ❌ Empty filter = all records
    "fields": {"name": "Alice"}
})

# Updates every user's name to "Alice" (probably not intended!)
```

**Why?** Empty filter matches **all records**. This is rarely intended.

**Fix**: Always specify filter criteria.

```python
# ✅ CORRECT - Specific filter
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},  # Specific record
    "fields": {"name": "Alice"}
})

# ✅ CORRECT - Multiple records intentionally
workflow.add_node("UserUpdateNode", "update_inactive", {
    "filter": {"status": "active"},  # Intentional bulk update
    "fields": {"status": "inactive"}
})
```

#### ❌ WRONG: Applying CreateNode Pattern

```python
# ❌ WILL FAIL - This is CreateNode pattern
workflow.add_node("UserUpdateNode", "update_user", {
    "name": "Alice",  # ❌ Flat fields don't work here
    "email": "alice@example.com"
})

# Error: "Missing required parameter 'filter'"
```

**Why?** UpdateNode expects `filter`/`fields` structure, not flat fields.

**Fix**: Use proper UpdateNode structure.

```python
# ✅ CORRECT
workflow.add_node("UserUpdateNode", "update_user", {
    "filter": {"id": "user-123"},
    "fields": {
        "name": "Alice",
        "email": "alice@example.com"
    }
})
```

---

## When to Use Each Node Type

### Use CreateNode When...

✅ **Creating new records** - Inserting new rows into database
✅ **You have all field values** - Complete record data available
✅ **Primary key is known** - ID generated or provided
✅ **Single insert operation** - One record at a time

**Example Scenarios**:
- User registration
- New order creation
- Adding new product
- Creating session record

```python
# User registration
workflow.add_node("UserCreateNode", "register", {
    "id": generate_uuid(),
    "name": user_name,
    "email": user_email,
    "password_hash": hash_password(password)
})
```

### Use UpdateNode When...

✅ **Modifying existing records** - Changing field values
✅ **Record already exists** - Must have been created first
✅ **Partial updates allowed** - Only specify fields to change
✅ **Conditional updates** - Filter determines which records

**Example Scenarios**:
- Updating user profile
- Changing order status
- Modifying product price
- Updating session timestamp

```python
# Update user profile
workflow.add_node("UserUpdateNode", "update_profile", {
    "filter": {"id": user_id},
    "fields": {
        "name": new_name,
        "phone": new_phone
    }
    # email unchanged
})
```

### Use UpsertNode When...

✅ **Not sure if record exists** - Create or update based on existence
✅ **Idempotent operations** - Same call always achieves same result
✅ **Natural key updates** - Using email/SKU instead of id
✅ **Avoiding race conditions** - Atomic check-and-create/update

**Example Scenarios**:
- API request deduplication
- External data sync
- Shopping cart updates
- Inventory synchronization

```python
# Upsert user by email (natural key)
workflow.add_node("UserUpsertNode", "sync_user", {
    "where": {"email": user_email},
    "conflict_on": ["email"],
    "update": {"name": user_name, "last_login": datetime.now()},
    "create": {"id": generate_uuid(), "email": user_email, "name": user_name}
})
```

---

## Complete Working Examples

### Example 1: User Registration and Profile Update

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
import uuid

db = DataFlow("postgresql://localhost/myapp")

@db.model
class User:
    id: str
    name: str
    email: str
    phone: str | None = None

# Workflow: Register new user, then update phone
workflow = WorkflowBuilder()

# Step 1: Create user (flat fields)
workflow.add_node("UserCreateNode", "register", {
    "id": str(uuid.uuid4()),
    "name": "Alice Smith",
    "email": "alice@example.com"
    # phone = None (optional field)
})

# Step 2: Update phone number (filter + fields)
workflow.add_node("UserUpdateNode", "add_phone", {
    "filter": {"email": "alice@example.com"},  # Find by email
    "fields": {"phone": "+1-555-0123"}         # Add phone
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

print("Created:", results["register"]["record"])
print("Updated:", results["add_phone"]["record"])
```

### Example 2: E-commerce Order Processing

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from datetime import datetime

db = DataFlow("sqlite:///orders.db")

@db.model
class Order:
    id: str
    customer_id: str
    status: str
    total: float
    shipped_at: datetime | None = None

# Workflow: Create order → Process → Ship
workflow = WorkflowBuilder()

# Create new order (CreateNode - flat)
workflow.add_node("OrderCreateNode", "create_order", {
    "id": "order-001",
    "customer_id": "cust-123",
    "status": "pending",
    "total": 99.99
})

# Mark as processing (UpdateNode - filter + fields)
workflow.add_node("OrderUpdateNode", "process_order", {
    "filter": {"id": "order-001"},
    "fields": {"status": "processing"}
})

# Mark as shipped (UpdateNode - filter + fields)
workflow.add_node("OrderUpdateNode", "ship_order", {
    "filter": {"id": "order-001"},
    "fields": {
        "status": "shipped",
        "shipped_at": datetime.now()
    }
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

print("Order created:", results["create_order"]["record"]["status"])
print("Order processed:", results["process_order"]["record"]["status"])
print("Order shipped:", results["ship_order"]["record"]["status"])
```

### Example 3: Bulk Operations

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow("postgresql://localhost/myapp")

@db.model
class Product:
    id: str
    name: str
    price: float
    category: str

# Workflow: Create multiple products, update category prices
workflow = WorkflowBuilder()

# Bulk create products (flat fields in list)
workflow.add_node("ProductBulkCreateNode", "add_products", {
    "records": [
        {"id": "prod-1", "name": "Widget A", "price": 10.0, "category": "widgets"},
        {"id": "prod-2", "name": "Widget B", "price": 15.0, "category": "widgets"},
        {"id": "prod-3", "name": "Gadget A", "price": 20.0, "category": "gadgets"}
    ]
})

# Bulk update all widgets (filter + fields)
workflow.add_node("ProductBulkUpdateNode", "discount_widgets", {
    "filter": {"category": "widgets"},
    "fields": {"price": 8.0}  # Apply discount
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

print("Created:", results["add_products"]["created_count"], "products")
print("Discounted:", results["discount_widgets"]["updated_count"], "widgets")
```

---

## Parameter Structure Visual Reference

### CreateNode Structure
```python
{
    "id": "value",           # ← Primary key (required)
    "field1": "value1",      # ← Direct field (flat)
    "field2": "value2",      # ← Direct field (flat)
    "field3": "value3"       # ← Direct field (flat)
}
```

**Key Points**:
- All fields at root level (flat)
- `id` field required
- No `filter`, no `fields` keys
- No auto-managed fields (`created_at`, `updated_at`)

### UpdateNode Structure
```python
{
    "filter": {              # ← Which records to update
        "id": "value"        #    (or any other field)
    },
    "fields": {              # ← What to change
        "field1": "new_value1",
        "field2": "new_value2"
    }
}
```

**Key Points**:
- Two-level nested structure
- `filter` identifies records
- `fields` specifies changes
- Can't update `id` in `fields`
- Can use any field(s) in `filter`

### UpsertNode Structure
```python
{
    "where": {               # ← Find record
        "id": "value"
    },
    "conflict_on": ["email"], # ← Conflict detection field(s)
    "update": {              # ← If exists, update these
        "field1": "value1"
    },
    "create": {              # ← If not exists, create with these
        "id": "value",
        "field1": "value1",
        "field2": "value2"
    }
}
```

**Key Points**:
- Three-level structure
- `where` finds record
- `conflict_on` specifies unique fields
- `update` for existing records
- `create` for new records
- Atomic operation

---

## Connection Patterns

### Chaining Create → Update

```python
workflow = WorkflowBuilder()

# Create user
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# Update same user (use created record's ID)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {},      # Will be filled via connection
    "fields": {"name": "Alice Updated"}
})

# Connect created ID to update filter
workflow.add_connection("create", "record.id", "update", "filter.id")

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

### Conditional Update After Read

```python
from kailash.nodes.logic import SwitchNode

workflow = WorkflowBuilder()

# Read user
workflow.add_node("UserReadNode", "read", {
    "filter": {"id": "user-123"}
})

# Check if active
workflow.add_node("SwitchNode", "check_active", {
    "condition": "record['status'] == 'active'"
})
workflow.add_connection("read", "record", "check_active", "record")

# Update only if active
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"last_active": "2024-01-01"}
})
workflow.add_connection("check_active", "true_output", "update", "trigger")

runtime = LocalRuntime(conditional_execution="skip_branches")
results, _ = runtime.execute(workflow.build())
```

---

## Error Messages and Fixes

### Error: "Missing required parameter 'id'"
**Scenario**: Using CreateNode
**Cause**: Forgot to include primary key
**Fix**: Add `"id": "value"` to parameters

```python
# ❌ Error
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})

# ✅ Fixed
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})
```

### Error: "Missing required parameter 'filter'"
**Scenario**: Using UpdateNode
**Cause**: Using flat fields instead of filter + fields structure
**Fix**: Nest parameters under `filter` and `fields`

```python
# ❌ Error
workflow.add_node("UserUpdateNode", "update", {"id": "user-123", "name": "Alice"})

# ✅ Fixed
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice"}
})
```

### Error: "created_at is auto-managed"
**Scenario**: Using CreateNode with timestamp fields
**Cause**: Including auto-managed fields in parameters
**Fix**: Remove `created_at`, `updated_at`, `created_by`, `updated_by`

```python
# ❌ Error
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": datetime.now()  # Auto-managed
})

# ✅ Fixed
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # created_at added automatically
})
```

### Error: "Cannot update primary key 'id'"
**Scenario**: Using UpdateNode with id in fields
**Cause**: Trying to change primary key value
**Fix**: Remove `id` from fields, use only in filter

```python
# ❌ Error
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"email": "alice@example.com"},
    "fields": {"id": "new-id", "name": "Alice"}  # Can't change ID
})

# ✅ Fixed
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"email": "alice@example.com"},
    "fields": {"name": "Alice"}  # No ID in fields
})
```

---

## Quick Reference Card

**Print this out and keep near your workspace!**

```
┌─────────────────────────────────────────────────────────────┐
│                 DataFlow Node Quick Reference                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CreateNode                                                  │
│  ├─ Pattern: Flat fields                                     │
│  ├─ Example: {"id": "123", "name": "Alice"}                 │
│  └─ Use: Creating new records                                │
│                                                              │
│  UpdateNode                                                  │
│  ├─ Pattern: filter + fields                                 │
│  ├─ Example: {"filter": {"id": "123"}, "fields": {...}}    │
│  └─ Use: Modifying existing records                          │
│                                                              │
│  UpsertNode                                                  │
│  ├─ Pattern: where + conflict_on + update + create          │
│  ├─ Example: {"where": {...}, "update": {...}, "create...} │
│  └─ Use: Create if not exists, update if exists             │
│                                                              │
│  Common Mistakes                                             │
│  ✗ Using flat fields in UpdateNode                          │
│  ✗ Using filter/fields in CreateNode                        │
│  ✗ Including created_at/updated_at                          │
│  ✗ Missing 'id' in CreateNode                               │
│  ✗ Updating 'id' in UpdateNode fields                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary

**CreateNode = Flat Fields**
- Direct field assignment
- Primary key required
- No auto-managed fields
- Simple, straightforward

**UpdateNode = Filter + Fields**
- Two-level nested structure
- Filter identifies records
- Fields specify changes
- More flexible, more complex

**UpsertNode = Where + Update + Create**
- Three-level nested structure
- Atomic insert-or-update
- Conflict detection
- Idempotent operations

**Remember**: The #1 cause of DataFlow confusion is mixing these patterns. When in doubt, refer back to this guide!

---

**Last Updated**: 2025-10-29
**Version**: 1.0
**Tested**: All examples validated with PostgreSQL, MySQL, and SQLite

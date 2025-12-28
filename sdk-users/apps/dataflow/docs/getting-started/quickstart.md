# DataFlow Quick Start Guide

Get up and running with DataFlow in 5 minutes! This guide shows you how to build database workflows with **automatic node generation** and zero configuration.

## 🚀 The DataFlow "Wow Factor"

**One decorator generates 9 workflow nodes automatically:**

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero-config database setup
db = DataFlow("postgresql://user:password@localhost/database")

# ONE decorator generates 9 nodes automatically
@db.model
class User:
    name: str
    email: str
    active: bool = True

# Generated automatically:
# - UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode
# - UserListNode, UserBulkCreateNode, UserBulkUpdateNode,
# - UserBulkDeleteNode, UserBulkUpsertNode

# Use in Core SDK workflows immediately
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice Smith",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Created user: {results['create_user']}")
```

**You'll see this interactive preview:**
```
🔄 DataFlow Auto-Migration Preview

Schema Changes Detected:
┌─────────────────┬──────────────────┬────────────────┬──────────────┐
│ Table           │ Operation        │ Details        │ Safety Level │
├─────────────────┼──────────────────┼────────────────┼──────────────┤
│ user            │ ADD_COLUMN       │ phone (TEXT)   │ ✅ SAFE      │
│ user            │ ADD_COLUMN       │ is_active      │ ✅ SAFE      │
│                 │                  │ (BOOLEAN)      │              │
└─────────────────┴──────────────────┴────────────────┴──────────────┘

Apply these changes? [y/N]: y
✅ Migration completed successfully!
```

**No manual migrations. No SQL scripts. Just code and go!**

## Installation

```bash
pip install kailash-dataflow
```

## Your First DataFlow App

### 1. Zero Configuration Setup

Create a new file `app.py`:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize DataFlow - SQLite database auto-created
db = DataFlow()
```

That's it! You now have a fully functional database connection with:
- ✅ Automatic SQLite database creation
- ✅ Connection pooling
- ✅ **Revolutionary auto-migration system**
- ✅ Visual schema change previews
- ✅ Rollback capabilities

### 2. Define Your First Model

Add a model to your app:

```python
@db.model
class User:
    """User model with auto-generated nodes and auto-migration."""
    name: str
    email: str
    active: bool = True
```

This single decorator creates:
- **9 database nodes automatically**
- **Automatic schema migration when fields change**
- **Visual preview of all database changes**

**Generated nodes:**
- `UserCreateNode` - Create a user
- `UserReadNode` - Get user by ID
- `UserUpdateNode` - Update a user
- `UserDeleteNode` - Delete a user
- `UserListNode` - Query users
- `UserBulkCreateNode` - Create multiple users
- `UserBulkUpdateNode` - Update multiple users
- `UserBulkDeleteNode` - Delete multiple users
- `UserBulkUpsertNode` - Insert or update users

### 3. Use the Generated Nodes

Now use the auto-generated nodes in a workflow:

```python
# Build a workflow
workflow = WorkflowBuilder()

# Create a user
workflow.add_node("UserCreateNode", "create_alice", {
    "name": "Alice Smith",
    "email": "alice@example.com"
})

# List all active users
workflow.add_node("UserListNode", "list_active", {
    "filter": {"active": True},
    "sort": [{"field": "name", "direction": "asc"}]
})

# Connect the nodes
workflow.add_connection("create_alice", "result", "list_active", "input")

# Execute the workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Check results
print(f"Created user: {results['create_alice']['record']}")
print(f"Active users: {results['list_active']['records']}")
```

### 4. Complete Example

Here's the complete quick start app:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize DataFlow
db = DataFlow()

# Define model
@db.model
class User:
    name: str
    email: str
    active: bool = True

# Create workflow
workflow = WorkflowBuilder()

# Add nodes for database operations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice Smith",
    "email": "alice@example.com"
})

workflow.add_node("UserListNode", "list_users", {
    "filter": {"active": True}
})

workflow.add_connection("create_user", "result", "list_users", "input")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Display results
print(f"Workflow completed: {run_id}")
print(f"Created: {results['create_user']['record']}")
print(f"All users: {results['list_users']['records']}")
```

## ✨ Auto-Migration in Action

### Schema Evolution Example

```python
# Start with basic model
@db.model
class Product:
    name: str
    price: float

await db.initialize()  # Creates initial schema

# Evolve your model - add features as you code
@db.model
class Product:
    name: str
    price: float
    description: str = None      # NEW: product description
    category: str = None         # NEW: categorization
    specifications: dict = None  # NEW: JSONB specifications
    in_stock: bool = True        # NEW: inventory flag
    created_at: datetime = None  # NEW: timestamp

# Auto-migration shows you exactly what will change
await db.auto_migrate()
```

**Migration preview shows:**
- ✅ Safe operations (no data loss)
- ⚠️ Risky operations (with warnings)
- 🚨 Dangerous operations (require confirmation)
- 📊 Estimated execution time
- 🔄 Rollback plan available

### Production-Safe Migrations

```python
# Production deployment with safety checks
success, migrations = await db.auto_migrate(
    dry_run=True,              # Preview only
    max_risk_level="MEDIUM",   # Block dangerous operations
    backup_before_migration=True,  # Auto-backup
    rollback_on_error=True     # Auto-rollback failures
)

if success:
    print(f"Applied {len(migrations)} migrations safely")
```

## Advanced Features in 30 Seconds

### Bulk Operations

```python
# Import 1000 users efficiently
workflow.add_node("UserBulkCreateNode", "import_users", {
    "data": [
        {"name": f"User {i}", "email": f"user{i}@example.com"}
        for i in range(1000)
    ],
    "batch_size": 100  # Process in batches
})
```

### Complex Queries

```python
# Find users with advanced filters
workflow.add_node("UserListNode", "search_users", {
    "filter": {
        "name": {"$regex": "^A.*"},  # Names starting with A
        "created_at": {"$gte": "2025-01-01"},
        "active": True
    },
    "sort": [{"field": "created_at", "direction": "desc"}],
    "limit": 10,
    "offset": 0
})
```

### Relationships

```python
@db.model
class Post:
    title: str
    content: str
    user_id: int
    published: bool = False

# Query with relationships
workflow.add_node("PostListNode", "user_posts", {
    "filter": {"user_id": 123, "published": True}
})
```

## Production Configuration

When ready for production, add configuration:

```python
# Production database with secure password
db = DataFlow(
    database_url="postgresql://admin:SecureP@ss#123$@prod-db:5432/myapp",
    pool_size=20,
    echo=False  # Disable SQL logging
)

# DataFlow automatically handles special characters in passwords (v0.9.4+)
# Enhanced parameter type casting in v0.4.0+
# No manual URL encoding required!

# Enable enterprise features
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

    __dataflow__ = {
        'multi_tenant': True,     # Adds tenant isolation
        'soft_delete': True,      # Adds deleted_at field
        'audit_log': True         # Tracks all changes
    }
```

## Next Steps

You've just built a complete database application with **automatic schema management**! Here's what to explore next:

1. **[Auto-Migration System](../workflows/auto-migration.md)** - Master the revolutionary migration system
2. **[Core Concepts](concepts.md)** - Understand DataFlow's architecture
3. **[Model Definition](../development/models.md)** - Advanced model features
4. **[Bulk Operations](../development/bulk-operations.md)** - High-performance data handling
5. **[Multi-Database Support](../features/multi-database.md)** - PostgreSQL and SQLite (full parity), MySQL coming soon
6. **[Progressive Configuration](../features/progressive-config.md)** - Scale from prototype to enterprise

## Common Patterns

### CRUD Operations
```python
# Create
workflow.add_node("UserCreateNode", "create", {"name": "Bob", "email": "bob@example.com"})

# Read
workflow.add_node("UserReadNode", "read", {"record_id": 123})

# Update
workflow.add_node("UserUpdateNode", "update", {"record_id": 123, "name": "Bob Smith"})

# Delete
workflow.add_node("UserDeleteNode", "delete", {"record_id": 123})
```

### Pagination
```python
workflow.add_node("UserListNode", "page_1", {
    "limit": 20,
    "offset": 0,
    "sort": [{"field": "created_at", "direction": "desc"}]
})
```

### Complex Filtering
```python
workflow.add_node("UserListNode", "stats", {
    "filter": {"active": True},
    "sort": [{"field": "created_at", "direction": "desc"}],
    "limit": 100
})
```

## 💡 DataFlow Tips

- 🚀 **Start Simple**: Use zero-config SQLite for prototyping
- 🔄 **Embrace Auto-Migration**: Let DataFlow manage your schema evolution
- 📊 **Preview First**: Always use `dry_run=True` in production
- 📈 **Scale Gradually**: Add features as you need them
- 🔍 **Use Filters**: MongoDB-style query operators for complex queries
- ⚡ **Bulk for Speed**: Use bulk nodes for operations on multiple records
- 🛡️ **Enable Security**: Add multi-tenant and audit features for production
- 🔄 **Plan Rollbacks**: DataFlow generates rollback plans automatically
- 🎆 **Update Regularly**: v0.4.0+ includes major stability improvements
- 📋 **Use TEXT Fields**: No more 255-character limits (fixed in v0.4.0)

---

**Congratulations!** You've discovered DataFlow's revolutionary auto-migration system. **Your database now evolves automatically as you code** - from simple prototypes to enterprise applications without manual schema management.

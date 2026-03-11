# DataFlow Quick Start Guide

Get up and running with DataFlow in 5 minutes! This guide shows you how to build a complete database-backed application.

> ✅ **v0.6.0 Release**: Full support for PostgreSQL, MySQL, SQLite (SQL), MongoDB (Document), and pgvector (Vector Search)

## Prerequisites

**Database Options** (choose one):
- **SQLite**: Built-in, zero-config (perfect for getting started!)
- **PostgreSQL**: Production-grade, advanced features
- **MySQL**: Web hosting, existing infrastructure
- **MongoDB**: Document database, flexible schema

**Quick Setup**:
```bash
# SQLite - No setup needed!

# PostgreSQL (optional)
brew install postgresql && brew services start postgresql
createdb mydataflowapp

# MySQL (optional)
brew install mysql && brew services start mysql
mysql -u root -e "CREATE DATABASE mydataflowapp"

# MongoDB (optional)
brew install mongodb-community && brew services start mongodb-community
```

## Installation

```bash
pip install kailash-dataflow
```

## Your First DataFlow App

### 1. Zero-Config Setup (SQLite)

Create a new file `app.py`:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero-config - starts with SQLite in-memory
db = DataFlow()

# Or use SQLite file
# db = DataFlow("sqlite:///app.db")

# Or PostgreSQL for production
# db = DataFlow("postgresql://user:password@localhost/mydataflowapp")

# Or MySQL for web hosting
# db = DataFlow("mysql://user:password@localhost/mydataflowapp")
```

That's it! You now have a fully functional database connection with:
- ✅ Database connection (SQLite by default, or PostgreSQL/MySQL/MongoDB)
- ✅ Connection pooling
- ✅ Schema management
- ✅ Auto-migration support

### 2. Define Your First Model

Add a model to your app:

```python
@db.model
class User:
    """User model with auto-generated nodes."""
    name: str
    email: str
    active: bool = True
```

This single decorator creates 9 database nodes automatically:
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
workflow.add_connection("create_alice", "list_active")

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

# Initialize DataFlow with PostgreSQL or SQLite
db = DataFlow("postgresql://user:password@localhost/mydataflowapp")
# OR: db = DataFlow("sqlite:///mydataflowapp.db")

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

workflow.add_connection("create_user", "list_users")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Display results
print(f"Workflow completed: {run_id}")
print(f"Created: {results['create_user']['record']}")
print(f"All users: {results['list_users']['records']}")
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
# Production database (PostgreSQL recommended)
db = DataFlow(
    database_url="postgresql://user:pass@localhost/myapp",
    pool_size=20,
    echo=False  # Disable SQL logging
)

# Development database (SQLite)
db = DataFlow(
    database_url="sqlite:///myapp.db",
    pool_size=5,  # Lower pool size for SQLite
    echo=False
)

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

You've just built a complete database application! Here's what to explore next:

1. **[Core Concepts](concepts.md)** - Understand DataFlow's architecture
2. **[Model Definition](../development/models.md)** - Advanced model features
3. **[Bulk Operations](../development/bulk-operations.md)** - High-performance data handling
4. **[Multi-Database Support](../features/multi-database.md)** - Use PostgreSQL or MySQL
5. **[Progressive Configuration](../features/progressive-config.md)** - Scale from prototype to enterprise

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

## Tips

- 🚀 **Database Choice**: PostgreSQL (production), MySQL (web hosting), SQLite (dev/testing)
- 📄 **Document Data**: Use MongoDB adapter for flexible schema, catalogs, content management
- 🔍 **Semantic Search**: Use PostgreSQL pgvector for RAG, similarity search, recommendations
- 📈 **Scale Gradually**: Add features as you need them
- 🔍 **Use Filters**: MongoDB-style query operators for SQL databases
- ⚡ **Bulk for Speed**: Use bulk nodes for operations on multiple records
- 🛡️ **Enable Security**: Add multi-tenant and audit features for production
- ⚠️ **Note**: Real schema discovery (`discover_schema(use_real_inspection=True)`) is PostgreSQL-only

---

**Congratulations!** You've learned the basics of DataFlow. The framework grows with your needs - from simple prototypes to enterprise applications without changing your code.

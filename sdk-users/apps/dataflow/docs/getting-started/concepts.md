# DataFlow Core Concepts

Understanding DataFlow's core concepts will help you build better applications and leverage the framework's full power.

## Architecture Overview

DataFlow is built on three core principles:

1. **Zero Configuration** - Works out of the box
2. **Progressive Disclosure** - Complexity scales with your needs
3. **Workflow Native** - First-class integration with Kailash workflows

```
┌─────────────────────────────────────────────────────────┐
│                    Your Application                      │
├─────────────────────────────────────────────────────────┤
│                     DataFlow API                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Models    │  │    Nodes    │  │ Configuration│    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
├─────────────────────────────────────────────────────────┤
│                  Database Adapters                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐         │
│  │PostgreSQL│    │  MySQL   │    │  SQLite  │         │
│  └──────────┘    └──────────┘    └──────────┘         │
└─────────────────────────────────────────────────────────┘
```

## Key Concepts

### 1. Models

Models define your database schema using Python type hints:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
@db.model
class User:
    name: str              # Required field
    email: str            # Required field
    active: bool = True   # Optional with default
    created_at: datetime = None  # Auto-populated
```

**Key Features:**
- Type hints define column types
- Default values define optional fields
- Special fields (id, created_at, updated_at) auto-added
- Relationships defined through foreign keys

### 2. Auto-Generated Nodes

Every model automatically generates 9 workflow nodes:

| Node | Purpose | Example |
|------|---------|---------|
| `{Model}CreateNode` | Create single record | `UserCreateNode` |
| `{Model}ReadNode` | Get by ID | `UserReadNode` |
| `{Model}UpdateNode` | Update single record | `UserUpdateNode` |
| `{Model}DeleteNode` | Delete single record | `UserDeleteNode` |
| `{Model}ListNode` | Query with filters | `UserListNode` |
| `{Model}BulkCreateNode` | Create multiple | `UserBulkCreateNode` |
| `{Model}BulkUpdateNode` | Update multiple | `UserBulkUpdateNode` |
| `{Model}BulkDeleteNode` | Delete multiple | `UserBulkDeleteNode` |
| `{Model}BulkUpsertNode` | Insert or update | `UserBulkUpsertNode` |

### 3. Workflow Integration

DataFlow nodes are native Kailash workflow nodes:

```python
workflow = WorkflowBuilder()

# Chain database operations
workflow.add_node("UserCreateNode", "create", {...})
workflow.add_node("PostBulkCreateNode", "create_posts", {...})
workflow.add_node("UserUpdateNode", "activate", {...})

# Connect in sequence
workflow.add_connection("create", "result", "create_posts", "input")
workflow.add_connection("create_posts", "result", "activate", "input")

# Execute as one transaction
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 4. Progressive Configuration

Start simple, add complexity as needed:

```python
# Zero-config (SQLite)
db = DataFlow()

# Basic (specify database)
db = DataFlow("postgresql://localhost/myapp")

# Intermediate (add pooling)
db = DataFlow(
    database_url="postgresql://localhost/myapp",
    pool_size=20,
    monitoring=True
)

# Advanced (enterprise features)
db = DataFlow(
    database_url="postgresql://localhost/myapp",
    pool_size=50,
    multi_tenant=True,
    audit_logging=True,
    encryption_enabled=True
)
```

### 5. Query Language

DataFlow uses MongoDB-style query operators:

```python
# Comparison operators
filter = {
    "age": {"$gte": 18},          # Greater than or equal
    "status": {"$in": ["active", "pending"]},  # In list
    "email": {"$regex": ".*@company.com"}      # Regex match
}

# Logical operators
filter = {
    "$or": [
        {"role": "admin"},
        {"permissions": {"$contains": "write"}}
    ]
}

# Nested queries
filter = {
    "profile.city": "New York",
    "profile.verified": True
}
```

### 6. Transactions

DataFlow supports ACID transactions across nodes:

```python
# Automatic transaction per workflow
workflow = WorkflowBuilder()
workflow.add_node("OrderCreateNode", "order", {...})
workflow.add_node("InventoryUpdateNode", "inventory", {...})
workflow.add_node("PaymentCreateNode", "payment", {...})

# All succeed or all fail
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 7. Multi-Database Support

Write once, run on any database:

```python
# Development
db = DataFlow("sqlite:///dev.db")

# Testing
db = DataFlow("mysql://localhost/test")

# Production
db = DataFlow("postgresql://prod-server/app")

# Same code works on all databases
@db.model
class Product:
    name: str
    price: float
    metadata: dict  # JSON in PostgreSQL/MySQL, TEXT in SQLite
```

## Design Patterns

### Repository Pattern

DataFlow nodes implement the repository pattern:

```python
# Instead of:
# user_repo.create(data)
# user_repo.find_by_id(id)
# user_repo.update(id, data)

# Use nodes:
workflow.add_node("UserCreateNode", "create", data)
workflow.add_node("UserReadNode", "read", {"id": id})
workflow.add_node("UserUpdateNode", "update", {"id": id, **data})
```

### Unit of Work Pattern

Workflows provide unit of work:

```python
# All database operations in one workflow share a transaction
workflow = WorkflowBuilder()

# Multiple operations
workflow.add_node("UserCreateNode", "user", {...})
workflow.add_node("ProfileCreateNode", "profile", {...})
workflow.add_node("NotificationCreateNode", "notify", {...})

# Execute as atomic unit
runtime.execute(workflow.build())
```

### Query Builder Pattern

List nodes provide fluent query building:

```python
workflow.add_node("OrderListNode", "orders", {
    "filter": {"status": "pending"},
    "sort": [{"field": "created_at", "direction": "desc"}],
    "limit": 10,
    "include": ["customer", "items"]
})
```

## Performance Concepts

### Connection Pooling

Automatic connection management:

```python
db = DataFlow(
    pool_size=20,           # Base connections
    pool_max_overflow=30,   # Extra when needed
    pool_recycle=3600      # Recycle after 1 hour
)
```

### Batch Processing

Process large datasets efficiently:

```python
# Process 10,000 records in batches
workflow.add_node("UserBulkCreateNode", "import", {
    "data": large_user_list,
    "batch_size": 1000,     # 10 batches
    "return_ids": False     # Skip returning for speed
})
```

### Query Optimization

DataFlow automatically optimizes queries:

```python
# This complex workflow...
workflow.add_node("UserListNode", "users", {"filter": {"active": True}})
workflow.add_node("PostListNode", "posts", {"filter": {"user_id": "$users.id"}})
workflow.add_node("CommentListNode", "comments", {"filter": {"post_id": "$posts.id"}})

# ...is optimized to a single SQL query with JOINs
```

## Security Concepts

### Multi-Tenancy

Automatic tenant isolation:

```python
@db.model
class Document:
    title: str
    content: str

    __dataflow__ = {
        'multi_tenant': True  # Adds tenant_id, filters automatically
    }

# Queries automatically filtered by tenant
workflow.add_node("DocumentListNode", "docs", {
    # No need to specify tenant_id - it's automatic
    "filter": {"published": True}
})
```

### Audit Logging

Track all changes:

```python
@db.model
class SensitiveData:
    content: str

    __dataflow__ = {
        'audit_log': True  # All changes tracked
    }

# Query audit log
workflow.add_node("AuditLogNode", "history", {
    "model": "SensitiveData",
    "record_id": 123
})
```

## Best Practices

### 1. Start with Models
Define your data structure first:

```python
@db.model
class Customer:
    name: str
    email: str
    tier: str = "free"
```

### 2. Use Appropriate Nodes
- Single operations: Use CRUD nodes
- Multiple records: Use bulk nodes
- Complex queries: Use list nodes with filters

### 3. Leverage Workflows
Chain related operations:

```python
workflow.add_node("CustomerCreateNode", "customer", {...})
workflow.add_node("WelcomeEmailNode", "email", {...})
workflow.add_connection("customer", "result", "email", "input")
```

### 4. Progressive Enhancement
Start simple, add features as needed:

```python
# Start
@db.model
class Order:
    total: float

# Add features later
__dataflow__ = {
    'soft_delete': True,
    'audit_log': True
}
```

### 5. Monitor Performance
Enable monitoring in production:

```python
db = DataFlow(
    monitoring=True,
    slow_query_threshold=100  # Log queries over 100ms
)
```

## Common Pitfalls

### 1. Over-Engineering
❌ Don't start with all features enabled
✅ Start simple, add as needed

### 2. Ignoring Bulk Operations
❌ Don't use loops with single operations
✅ Use bulk nodes for multiple records

### 3. Complex Nested Queries
❌ Don't nest too many workflow nodes
✅ Use query optimization or custom SQL

### 4. Forgetting Indexes
❌ Don't ignore slow queries
✅ Add indexes for common filters

## Next Steps

Now that you understand the core concepts:

1. **[Model Definition](../development/models.md)** - Deep dive into models
2. **[Node Reference](../api/nodes.md)** - Complete node documentation
3. **[Query Patterns](../development/queries.md)** - Advanced querying
4. **[Performance Guide](../production/performance.md)** - Optimization tips

---

**Remember:** DataFlow is designed to grow with you. Start with the basics and add complexity only when you need it.

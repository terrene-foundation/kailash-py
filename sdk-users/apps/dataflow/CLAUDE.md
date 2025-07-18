# DataFlow - Quick Reference for Claude Code

## 🚀 Zero-Config Database Framework

**DataFlow** provides zero-configuration database operations with enterprise power. Every model automatically generates 9 workflow nodes for complete CRUD operations.

## ⚡ Essential Patterns

### Pattern 1: Zero-Config Basic Setup
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero configuration - SQLite auto-created
db = DataFlow()

@db.model
class User:
    name: str
    email: str
    active: bool = True

# Generated nodes available immediately:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode, UserListNode
# UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserListNode", "list", {
    "filter": {"active": True}
})
workflow.add_connection("create", "result", "list", "input")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Pattern 2: Production Database Configuration
```python
# Environment-based (recommended)
# Set DATABASE_URL=postgresql://user:pass@localhost/db
db = DataFlow()

# Direct configuration
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=20,
    pool_max_overflow=30,
    pool_recycle=3600,
    monitoring=True
)
```

### Pattern 3: Enterprise Multi-Tenant Setup
```python
@db.model
class Order:
    customer_id: int
    total: float
    status: str = "pending"
    
    __dataflow__ = {
        'multi_tenant': True,     # Adds tenant_id field
        'soft_delete': True,      # Adds deleted_at field
        'audit_log': True,        # Tracks all changes
        'versioned': True         # Adds version field
    }
```

### Pattern 4: High-Performance Bulk Operations
```python
# Bulk create - handles 10,000+ records/sec
workflow.add_node("UserBulkCreateNode", "import", {
    "data": [
        {"name": "User1", "email": "user1@example.com"},
        {"name": "User2", "email": "user2@example.com"},
        # ... thousands more
    ],
    "batch_size": 1000,
    "conflict_resolution": "upsert"
})

# Bulk update with conditions
workflow.add_node("UserBulkUpdateNode", "activate", {
    "filter": {"active": False},
    "update": {"active": True},
    "limit": 5000
})
```

### Pattern 5: MongoDB-Style Queries
```python
workflow.add_node("UserListNode", "search", {
    "filter": {
        "age": {"$gte": 18, "$lt": 65},
        "status": {"$in": ["active", "pending"]},
        "email": {"$regex": ".*@company.com"},
        "created_at": {"$gte": "2024-01-01"}
    },
    "sort": [{"created_at": -1}],
    "limit": 100,
    "include": ["profile", "orders"]
})
```

### Pattern 6: Transaction Management
```python
# Automatic transaction per workflow
workflow = WorkflowBuilder()
workflow.add_node("OrderCreateNode", "order", {
    "customer_id": 123,
    "total": 250.00
})
workflow.add_node("InventoryUpdateNode", "inventory", {
    "product_id": 456,
    "quantity": -1
})
workflow.add_node("PaymentCreateNode", "payment", {
    "amount": 250.00,
    "method": "card"
})

# All succeed or all fail - automatic ACID transaction
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🎯 Auto-Generated Nodes (Per Model)

Every `@db.model` class automatically generates these 9 nodes:

| Node | Purpose | Performance | Example |
|------|---------|-------------|---------|
| `{Model}CreateNode` | Single insert | <1ms | `UserCreateNode` |
| `{Model}ReadNode` | Get by ID | <1ms | `UserReadNode` |
| `{Model}UpdateNode` | Single update | <1ms | `UserUpdateNode` |
| `{Model}DeleteNode` | Single delete | <1ms | `UserDeleteNode` |
| `{Model}ListNode` | Query with filters | <10ms | `UserListNode` |
| `{Model}BulkCreateNode` | Bulk insert | 1000+/sec | `UserBulkCreateNode` |
| `{Model}BulkUpdateNode` | Bulk update | 5000+/sec | `UserBulkUpdateNode` |
| `{Model}BulkDeleteNode` | Bulk delete | 10000+/sec | `UserBulkDeleteNode` |
| `{Model}BulkUpsertNode` | Insert or update | 3000+/sec | `UserBulkUpsertNode` |

## 🔧 Common Node Parameters

### Create Node
```python
workflow.add_node("UserCreateNode", "create", {
    "name": "John Doe",
    "email": "john@example.com",
    "active": True,
    "return_id": True  # Returns created record ID
})
```

### Read Node
```python
workflow.add_node("UserReadNode", "read", {
    "id": 123,
    "include": ["profile", "orders"]  # Include related data
})
```

### Update Node
```python
workflow.add_node("UserUpdateNode", "update", {
    "id": 123,
    "name": "John Updated",
    "email": "john.updated@example.com",
    "version": 1  # Optimistic locking
})
```

### List Node (Most Powerful)
```python
workflow.add_node("UserListNode", "search", {
    "filter": {
        "active": True,
        "created_at": {"$gte": "2024-01-01"}
    },
    "sort": [{"created_at": -1}],
    "limit": 50,
    "offset": 0,
    "include": ["profile"],
    "select": ["id", "name", "email"]  # Specific fields only
})
```

## 🏗️ Integration Patterns

### DataFlow + Nexus Integration
```python
from dataflow import DataFlow
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Initialize DataFlow
db = DataFlow()

@db.model
class Product:
    name: str
    price: float
    category: str

# Create workflow using DataFlow nodes
workflow = WorkflowBuilder()
workflow.add_node("ProductCreateNode", "create", {
    "name": "{{name}}",
    "price": "{{price}}",
    "category": "{{category}}"
})

# Register with Nexus for multi-channel access
app = Nexus()
app.register("create_product", workflow.build())
app.start()

# Now available on:
# - API: POST /workflows/create_product
# - CLI: nexus run create_product --name "Test" --price 100
# - MCP: create_product tool for AI agents
```

### Gateway API Auto-Generation
```python
from kailash.servers.gateway import create_gateway

# Auto-generate REST API from DataFlow models
gateway = create_gateway(
    title="Product API",
    server_type="enterprise",
    dataflow_integration=db,
    auto_generate_endpoints=True
)

# Automatically creates:
# GET /api/products - List products
# POST /api/products - Create product
# GET /api/products/{id} - Get product
# PUT /api/products/{id} - Update product
# DELETE /api/products/{id} - Delete product
```

## 📊 Performance Optimization

### Connection Pooling
```python
db = DataFlow(
    database_url="postgresql://localhost/db",
    pool_size=20,              # Base connections
    pool_max_overflow=30,      # Extra connections when needed
    pool_recycle=3600,         # Recycle connections after 1 hour
    pool_pre_ping=True         # Test connections before use
)
```

### Query Caching
```python
workflow.add_node("UserListNode", "cached_search", {
    "filter": {"active": True},
    "cache_key": "active_users",
    "cache_ttl": 300,  # 5 minutes
    "cache_backend": "redis"
})
```

### Read/Write Splitting
```python
workflow.add_node("UserReadNode", "profile", {
    "id": 123,
    "read_preference": "secondary"  # Use read replica
})
```

## 🛡️ Security & Compliance

### Multi-Tenancy
```python
@db.model
class Document:
    title: str
    content: str
    
    __dataflow__ = {
        'multi_tenant': True  # Automatic tenant isolation
    }

# Queries automatically filtered by tenant
workflow.add_node("DocumentListNode", "docs", {
    "filter": {"published": True}
    # tenant_id automatically added
})
```

### Encryption
```python
@db.model
class SensitiveData:
    user_id: int
    encrypted_field: str
    
    __dataflow__ = {
        'encryption': {
            'fields': ['encrypted_field'],
            'algorithm': 'AES-256-GCM'
        }
    }
```

### Audit Logging
```python
@db.model
class AuditableModel:
    name: str
    
    __dataflow__ = {
        'audit_log': True  # All changes tracked
    }

# Query audit history
workflow.add_node("AuditLogNode", "history", {
    "model": "AuditableModel",
    "record_id": 123,
    "action_type": "update"
})
```

## ⚠️ Critical Rules

### ✅ ALWAYS DO
- Use `@db.model` decorator for automatic node generation
- Leverage bulk operations for >100 records
- Use the generated node names exactly: `{Model}CreateNode`, `{Model}ListNode`, etc.
- Configure connection pooling for production
- Use `workflow.build()` before execution

### ❌ NEVER DO
- Import DataFlow nodes directly - they're auto-generated
- Use raw SQL queries - use the generated nodes
- Create custom database sessions
- Skip connection pooling in production
- Use single operations in loops - use bulk operations

## 🔍 Troubleshooting

### Common Issues
1. **Node not found**: Ensure model is decorated with `@db.model`
2. **Connection errors**: Check DATABASE_URL and connection pooling
3. **Performance issues**: Use bulk operations and proper indexing
4. **Transaction failures**: Check for deadlocks and long-running transactions

### Debug Mode
```python
db = DataFlow(
    echo=True,  # Log all SQL queries
    monitoring=True,  # Enable performance monitoring
    slow_query_threshold=100  # Log queries over 100ms
)
```

## 📚 Documentation Navigation

### Quick Reference
- **[Complete Documentation](docs/README.md)** - Full navigation
- **[Quick Start](docs/getting-started/quickstart.md)** - 5-minute tutorial
- **[Core Concepts](docs/getting-started/concepts.md)** - Architecture overview

### Development
- **[Model Definition](docs/development/models.md)** - Define database models
- **[Generated Nodes](docs/development/nodes.md)** - Understand auto-generated nodes
- **[Bulk Operations](docs/development/bulk-operations.md)** - High-performance operations

### Enterprise
- **[Multi-Tenancy](docs/enterprise/multi-tenant.md)** - Tenant isolation
- **[Security](docs/enterprise/security.md)** - Encryption and compliance
- **[Performance](docs/enterprise/performance.md)** - Scale optimization

### Integration
- **[Nexus Integration](docs/integration/nexus.md)** - Multi-channel platform
- **[Gateway APIs](docs/integration/gateway.md)** - Auto-generated REST APIs

---

**DataFlow: From prototype to production without changing a line of code.** 🚀

*Zero configuration, maximum power, enterprise ready.*
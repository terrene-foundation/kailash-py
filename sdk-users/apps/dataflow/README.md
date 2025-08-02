# DataFlow - Zero-Config Database Platform

DataFlow provides MongoDB-style queries across any database with enterprise-grade caching and automatic API generation. This guide is for users who have installed DataFlow via PyPI.

## Installation

```bash
# Install DataFlow directly
pip install kailash-dataflow

# Or as part of Kailash SDK
pip install kailash[dataflow]
```

## 🏗️ DataFlow vs Traditional ORMs

DataFlow is not a traditional ORM. It's a **workflow-native database framework** designed for enterprise applications with distributed transactions, multi-tenancy, and caching built-in.

### Architecture Comparison

| Feature | Traditional ORM | DataFlow |
|---------|----------------|----------|
| **Model Usage** | Direct instantiation (`User()`) | Workflow-native (`UserCreateNode`) |
| **Database Operations** | Method calls (`user.save()`) | Workflow nodes (`UserCreateNode`) |
| **Transaction Handling** | Manual transaction management | Distributed transaction support |
| **Caching** | External cache integration | Built-in enterprise caching |
| **Multi-tenancy** | Custom implementation | Automatic tenant isolation |
| **Performance** | N+1 queries common | Optimized bulk operations |
| **Scalability** | Vertical scaling focus | Horizontal scaling built-in |

### Why Workflow-Native?

**Traditional ORM Limitations:**
```python
# Traditional ORM - doesn't scale well
user = User(name="John", email="john@example.com")
user.save()  # Individual database calls
# Issues: N+1 queries, no caching, no multi-tenancy
```

**DataFlow Advantages:**
```python
# DataFlow - built for enterprise scale
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})
# Benefits: Automatic caching, bulk operations, tenant isolation
```

### Enterprise Benefits

1. **Distributed Transactions**: Automatic transaction coordination across services
2. **Multi-Tenancy**: Built-in tenant isolation and data partitioning
3. **Performance Caching**: Enterprise-grade caching with invalidation strategies
4. **Bulk Operations**: Optimized for high-throughput scenarios (10k+ ops/sec)
5. **Monitoring**: Built-in metrics, deadlock detection, performance monitoring
6. **Security**: Automatic SQL injection prevention, audit trails

### Model Instantiation Not Supported

DataFlow models are **schemas, not objects**. This is intentional:

```python
# ❌ This won't work (by design)
user = User(name="John")  # Models are not instantiable

# ✅ This is the correct pattern
workflow.add_node("UserCreateNode", "create", {
    "name": "John",
    "email": "john@example.com"
})
```

**Why?** Model instantiation bypasses:
- Automatic caching
- Tenant isolation
- Transaction coordination
- Performance optimization
- Security validation

## Quick Start

### Option 1: Traditional Model Definition

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero-configuration startup
db = DataFlow()

# Define a model - automatically generates 9 node types
@db.model
class User:
    name: str
    email: str
    age: int
    department: str
    active: bool = True

# Use generated nodes in workflows
workflow = WorkflowBuilder()

# Create a user
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",
    "age": 25,
    "department": "engineering"
})

# List users with filters
workflow.add_node("UserListNode", "list_users", {
    "filter": {"age": {"$gt": 18}},
    "limit": 10
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Option 2: Dynamic Model Registration (NEW)

Perfect for connecting to existing databases or LLM agent scenarios:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Connect to existing database safely
db = DataFlow(
    database_url="postgresql://user:pass@localhost/existing_db",
    existing_schema_mode=True  # Safe mode - no schema changes
)

# Discover and register existing tables as models
schema = db.discover_schema(use_real_inspection=True)
result = db.register_schema_as_models(tables=['users', 'orders'])

# Use generated nodes immediately (no @db.model needed)
workflow = WorkflowBuilder()
user_nodes = result['generated_nodes']['users']

workflow.add_node(user_nodes['list'], "get_users", {
    "filter": {"active": True},
    "limit": 10
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Key Features

### 🔧 Zero Configuration
Start with a single line: `app = DataFlow()` - no database setup, no schema definitions, no configuration files.

### 🔍 Dynamic Schema Discovery & Model Registration
Connect to existing databases without @db.model decorators. Perfect for LLM agents and dynamic database exploration.

### 🔄 Cross-Session Model Persistence
Models registered by one user/session are available to others via the model registry.

### 🛡️ Safe Existing Database Mode
Connect to production databases safely with `existing_schema_mode=True` - prevents any schema modifications.

### 🗄️ Universal Database Support
MongoDB-style queries work across PostgreSQL, MySQL, SQLite with automatic SQL generation and optimization.

### ⚡ Redis-Powered Caching
Enterprise-grade caching with intelligent invalidation patterns and 99.9% hit rates.

### 🚀 Automatic API Generation
REST APIs, OpenAPI documentation, and health checks generated automatically from your queries.

## Generated Node Types

Each `@db.model` automatically generates 9 node types:

### Basic CRUD Nodes
```python
# Create a single record
workflow.add_node("UserCreateNode", "create", {
    "name": "John",
    "age": 25,
    "department": "engineering"
})

# Read a single record
workflow.add_node("UserReadNode", "read", {
    "conditions": {"id": 123}
})

# Update a record
workflow.add_node("UserUpdateNode", "update", {
    "conditions": {"id": 123},
    "updates": {"age": 26}
})

# Delete a record
workflow.add_node("UserDeleteNode", "delete", {
    "conditions": {"id": 123}
})
```

### List and Query Nodes
```python
# List with MongoDB-style filters
workflow.add_node("UserListNode", "list", {
    "filter": {
        "age": {"$gt": 18, "$lt": 65},           # age > 18 AND age < 65
        "name": {"$regex": "^John"},              # name LIKE 'John%'
        "department": {"$in": ["eng", "sales"]},  # department IN ('eng', 'sales')
        "status": {"$ne": "inactive"}             # status != 'inactive'
    },
    "order_by": ["-created_at"],  # Sort by created_at descending
    "limit": 10,
    "offset": 0
})
```

### Bulk Operations
```python
# Bulk create
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "data": [
        {"name": "Alice", "age": 30, "department": "sales"},
        {"name": "Bob", "age": 35, "department": "engineering"}
    ],
    "batch_size": 1000
})

# Bulk update
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"department": "engineering"},
    "update": {"$inc": {"age": 1}}  # Increment age by 1
})

# Bulk delete
workflow.add_node("UserBulkDeleteNode", "bulk_delete", {
    "filter": {"status": "inactive"},
    "soft_delete": True
})

# Bulk upsert (insert or update)
workflow.add_node("UserBulkUpsertNode", "bulk_upsert", {
    "data": [
        {"email": "alice@example.com", "name": "Alice Updated"},
        {"email": "new@example.com", "name": "New User"}
    ],
    "match_fields": ["email"]
})
```

## Dynamic Model Registration (NEW)

### Working with Existing Databases

Connect to existing databases without needing @db.model decorators. Perfect for LLM agents, data exploration, and legacy database integration.

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Connect safely to existing database
db = DataFlow(
    database_url="postgresql://user:pass@localhost/existing_db",
    auto_migrate=False,              # Don't modify existing schema
    existing_schema_mode=True        # Extra safety - prevents ALL modifications
)

# Discover existing database structure
schema = db.discover_schema(use_real_inspection=True)
print(f"Found {len(schema)} tables: {list(schema.keys())}")

# Register discovered tables as DataFlow models
result = db.register_schema_as_models(tables=['customers', 'orders'])

print(f"Registered {result['success_count']} models")
print(f"Generated nodes: {result['generated_nodes']}")

# Now you can use the models in workflows
workflow = WorkflowBuilder()
customer_nodes = result['generated_nodes']['customers']

workflow.add_node(customer_nodes['list'], "get_customers", {
    "filter": {"status": "active"},
    "limit": 10
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Cross-Session Model Sharing

Models registered by one user/session are automatically available to others via the model registry.

```python
# === SESSION 1: Data Engineer discovers and registers models ===
db_engineer = DataFlow(
    database_url="postgresql://user:pass@localhost/company_db",
    existing_schema_mode=True
)

# Engineer discovers and registers models for the team
schema = db_engineer.discover_schema(use_real_inspection=True)
result = db_engineer.register_schema_as_models(
    tables=['users', 'products', 'orders']
)
print(f"Team models registered: {result['registered_models']}")

# === SESSION 2: Developer uses registered models ===
db_developer = DataFlow(
    database_url="postgresql://user:pass@localhost/company_db",
    existing_schema_mode=True
)

# Developer reconstructs models from registry (no @db.model needed)
models = db_developer.reconstruct_models_from_registry()
print(f"Available models: {models['reconstructed_models']}")

# Developer can now build workflows immediately
workflow = WorkflowBuilder()
user_nodes = models['generated_nodes']['users']

workflow.add_node(user_nodes['list'], "active_users", {
    "filter": {"active": True},
    "order_by": ["-created_at"],
    "limit": 20
})
```

### LLM Agent Database Exploration

Perfect for AI agents that need to explore and understand database structures dynamically.

```python
# LLM Agent workflow for database exploration
db_agent = DataFlow(
    database_url="postgresql://user:pass@localhost/unknown_db",
    existing_schema_mode=True  # Safe exploration mode
)

# Agent discovers database structure
schema = db_agent.discover_schema(use_real_inspection=True)
interesting_tables = [t for t in schema.keys() 
                     if not t.startswith('dataflow_')]  # Skip system tables

# Agent registers tables it wants to work with
result = db_agent.register_schema_as_models(tables=interesting_tables[:5])

# Agent builds exploration workflow
workflow = WorkflowBuilder()

for model_name in result['registered_models']:
    nodes = result['generated_nodes'][model_name]
    
    # Sample a few records from each table
    workflow.add_node(nodes['list'], f"sample_{model_name}", {
        "limit": 3,
        "order_by": []
    })

# Execute exploration
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Agent can now analyze the data structure and content
for node_id, result in results.items():
    if node_id.startswith('sample_'):
        table_name = node_id.replace('sample_', '')
        data = result.get('result', [])
        print(f"Table {table_name}: {len(data)} sample records")
```

### Safe Database Connection Modes

DataFlow provides multiple safety levels for connecting to existing databases:

```python
# Development Mode - Full auto-migration
db_dev = DataFlow(
    database_url="postgresql://user:pass@localhost/dev_db",
    auto_migrate=True,           # Create/modify tables as needed
    existing_schema_mode=False   # Allow schema changes
)

# Production Mode - Read existing schema only
db_prod = DataFlow(
    database_url="postgresql://user:pass@localhost/prod_db",
    auto_migrate=False,          # No automatic migrations
    existing_schema_mode=True    # Prevent ALL schema modifications
)

# Even if you accidentally define a new model, no tables will be created
@db_prod.model  
class NewModel:
    name: str
    value: int

# Model is registered locally but NO table created in database
assert 'NewModel' in db_prod.list_models()  # ✓ Local registration
schema = db_prod.discover_schema(use_real_inspection=True)
assert 'new_models' not in schema  # ✓ No table in database
```

### Key API Methods

DataFlow provides powerful methods for dynamic database operations:

```python
# Schema Discovery
schema = db.discover_schema(use_real_inspection=True)
# Returns: Dict[str, Dict] - Complete table structure with columns, types, constraints

# Dynamic Model Registration  
result = db.register_schema_as_models(tables=['users', 'orders'])
# Returns: {
#   'registered_models': ['User', 'Order'],
#   'generated_nodes': {
#     'User': {'create': 'UserCreateNode', 'list': 'UserListNode', ...},
#     'Order': {'create': 'OrderCreateNode', 'list': 'OrderListNode', ...}
#   },
#   'success_count': 2,
#   'error_count': 0
# }

# Cross-Session Model Reconstruction
models = db.reconstruct_models_from_registry()
# Returns: {
#   'reconstructed_models': ['User', 'Order'],
#   'generated_nodes': {...},
#   'success_count': 2
# }

# Model Persistence Control
db = DataFlow(
    database_url="...",
    enable_model_persistence=True,  # Default: saves models to registry
    existing_schema_mode=True       # Safety: prevents schema changes
)
```

## Advanced Features

### Multi-Database Operations
```python
# Configure multiple databases
db = DataFlow(
    database_url="postgresql://user:pass@localhost/main",
    analytics_db="postgresql://user:pass@localhost/analytics"
)

# Special characters in passwords are now fully supported (v0.9.4+)
db = DataFlow(
    database_url="postgresql://admin:MySecret#123$@localhost:5432/production",
    read_replica="postgresql://readonly:Complex@Pass!@replica:5432/production"
)

# Models can specify their database
@db.model
class User:
    name: str
    email: str
    __dataflow__ = {"database": "primary"}

@db.model
class Event:
    user_id: int
    action: str
    __dataflow__ = {"database": "analytics"}
```

### Enterprise Features
```python
# Enable multi-tenancy
@db.model
class Order:
    customer_id: int
    total: float
    __dataflow__ = {
        'multi_tenant': True,      # Adds tenant_id field
        'soft_delete': True,       # Adds deleted_at field
        'audit_log': True,         # Tracks all changes
        'versioned': True          # Optimistic locking
    }

# Use in workflows with automatic tenant isolation
workflow.add_node("OrderCreateNode", "create", {
    "customer_id": 123,
    "total": 250.00,
    "tenant_id": "tenant_abc"  # Automatic isolation
})
```

### Transaction Management
```python
# Distributed transactions
workflow.add_node("TransactionManagerNode", "payment_flow", {
    "transaction_type": "saga",
    "steps": [
        {"node": "PaymentCreateNode", "compensation": "PaymentRollbackNode"},
        {"node": "OrderUpdateNode", "compensation": "OrderRevertNode"},
        {"node": "InventoryUpdateNode", "compensation": "InventoryRestoreNode"}
    ],
    "timeout": 30
})
```

## Production Examples

### E-commerce Order Processing
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class Order:
    customer_id: int
    total: float
    status: str = "pending"

@db.model
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    price: float

# Complex order processing workflow
workflow = WorkflowBuilder()

# Create order
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": 123,
    "total": 0,
    "status": "pending"
})

# Add order items in bulk
workflow.add_node("OrderItemBulkCreateNode", "add_items", {
    "data": [
        {"product_id": 1, "quantity": 2, "price": 50.00},
        {"product_id": 2, "quantity": 1, "price": 100.00}
    ]
})

# Calculate and update total
workflow.add_node("OrderUpdateNode", "update_total", {
    "updates": {"total": 200.00, "status": "confirmed"}
})

# Connect nodes
workflow.add_connection("create_order", "id", "add_items", "order_id")
workflow.add_connection("create_order", "id", "update_total", "order_id")
workflow.add_connection("add_items", "result", "update_total", "input")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Analytics Dashboard
```python
# Create analytics workflow
analytics_workflow = WorkflowBuilder()

# Get today's sales
analytics_workflow.add_node("OrderListNode", "today_sales", {
    "filter": {
        "created_at": {"$gte": "2025-01-17T00:00:00"},
        "status": "completed"
    }
})

# Get top products
analytics_workflow.add_node("OrderItemListNode", "top_products", {
    "aggregate": [
        {"$group": {"_id": "$product_id", "sold": {"$sum": "$quantity"}}},
        {"$sort": {"sold": -1}},
        {"$limit": 10}
    ]
})

# Execute analytics
results, run_id = runtime.execute(analytics_workflow.build())
print(f"Today's orders: {len(results['today_sales']['result'])}")
print(f"Top products: {results['top_products']['result']}")
```

## Performance & Optimization

- **31.8M operations/second** baseline performance
- **99.9% cache hit rate** with intelligent invalidation
- **Connection pooling** with 10,000+ concurrent connections
- **Automatic query optimization** with SQL generation

### Performance Monitoring
```python
# Built-in performance monitoring with workflow
workflow.add_node("PerformanceMonitorNode", "monitor", {
    "operation": "complex_query",
    "track_metrics": True
})

workflow.add_node("UserListNode", "large_query", {
    "filter": {"status": "active"},
    "aggregate": [
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ]
})

# Execute with monitoring
results, run_id = runtime.execute(workflow.build())
# Performance metrics available in results['monitor']['metrics']
```

## Enterprise Features

### Security & Compliance
```python
# GDPR/CCPA compliance built-in with workflows
workflow.add_node("GDPRComplianceNode", "gdpr_handler", {
    "user_id": 123,
    "request_type": "export",  # or "delete"
    "include_audit_trail": True
})

# Data export workflow
workflow.add_node("UserDataExportNode", "export_data", {
    "user_id": 123,
    "format": "json",
    "include_deleted": True
})

# Data anonymization workflow
workflow.add_node("UserDataAnonymizeNode", "anonymize_data", {
    "user_id": 123,
    "retention_policy": "strict",
    "cascade_delete": True
})

# Audit trail is automatically enabled with multi_tenant: True
```

### Health Monitoring
```python
# Automatic health checks with workflow
workflow.add_node("HealthCheckNode", "health_monitor", {
    "check_database": True,
    "check_cache": True,
    "check_connections": True
})

results, run_id = runtime.execute(workflow.build())
health = results["health_monitor"]["result"]
# {
#   "status": "healthy",
#   "database": "connected",
#   "cache": "connected",
#   "queries_per_second": 31800000
# }
```

## Database Connection

### Connection String Support

DataFlow supports robust database connection string parsing with full support for special characters in passwords (enhanced in v0.9.4):

```python
# Supports complex passwords with special characters
connection_examples = [
    "postgresql://admin:MySecret#123$@localhost:5432/mydb",
    "postgresql://user:P@ssw0rd!@db.example.com:5432/production", 
    "mysql://service:Complex$ecret?@mysql.internal:3306/analytics",
    "postgresql://readonly:temp#pass@replica.host:5432/reports"
]

# All these connection strings work seamlessly
for conn_str in connection_examples:
    db = DataFlow(database_url=conn_str)
    # DataFlow automatically handles URL encoding/decoding
```

### Connection String Format

```python
# Standard format
scheme://[username[:password]@]host[:port]/database[?param1=value1&param2=value2]

# Examples
postgresql://username:password@localhost:5432/database_name
mysql://user:pass@host:3306/db_name?charset=utf8mb4
sqlite:///path/to/database.db
```

### Password Special Characters

DataFlow now handles these special characters in passwords automatically:
- `#` (hash/pound) - commonly used in passwords
- `$` (dollar sign) - shell variable syntax  
- `@` (at symbol) - email-like passwords
- `?` (question mark) - query parameter conflicts
- And many more URL-sensitive characters

**Before v0.9.4:** Required manual URL encoding
```python
# Old workaround (no longer needed)
password = "MySecret%23123%24"  # %23 = #, %24 = $
```

**Since v0.9.4:** Works automatically
```python
# Just use the password directly
db = DataFlow(database_url="postgresql://admin:MySecret#123$@localhost/db")
```

## Deployment

### Docker
```dockerfile
FROM python:3.11-slim
RUN pip install kailash-dataflow
COPY app.py .
EXPOSE 8000
CMD ["python", "app.py"]
```

### Environment Variables
```bash
export DATAFLOW_DATABASE_URL="postgresql://..."
export DATAFLOW_REDIS_URL="redis://..."
export DATAFLOW_LOG_LEVEL="INFO"
export DATAFLOW_ENABLE_METRICS="true"
```

## Migration from Raw SQL/ORM

### From Raw SQL
```python
# Before: Raw SQL
cursor.execute("""
    SELECT department, COUNT(*) as count
    FROM users
    WHERE age > %s
    GROUP BY department
    ORDER BY count DESC
""", (18,))

# After: DataFlow
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "dept_stats", {
    "filter": {"age": {"$gt": 18}},
    "aggregate": [
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
})
```

### From SQLAlchemy ORM
```python
# Before: SQLAlchemy
users = session.query(User).filter(
    User.age > 18,
    User.department.in_(['eng', 'sales'])
).order_by(User.created_at.desc()).limit(10).all()

# After: DataFlow
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "filtered_users", {
    "filter": {
        "age": {"$gt": 18},
        "department": {"$in": ["eng", "sales"]}
    },
    "order_by": ["-created_at"],
    "limit": 10
})
```

## Additional Documentation

### Guides
- [User Guide](docs/USER_GUIDE.md) - Comprehensive DataFlow guide
- [Quick Start Guide](docs/quickstart.md) - Get started in minutes
- [Query Patterns](docs/query-patterns.md) - Advanced query techniques
- [Database Optimization](docs/database-optimization.md) - Performance tuning
- [Multi-Tenant Architecture](docs/multi-tenant.md) - Enterprise patterns
- [Production Deployment](docs/deployment.md) - Deployment best practices

### Examples
- [Basic CRUD Operations](examples/01_basic_crud.py) - Simple database operations
- [Advanced Features](examples/02_advanced_features.py) - Complex queries and caching
- [Enterprise Integration](examples/03_enterprise_integration.py) - Multi-tenant and security

## Next Steps

- Explore the documentation and examples above
- Read the [API documentation](https://pypi.org/project/kailash-dataflow/)
- Join the [community](https://github.com/terrene-foundation/kailash-py)

DataFlow transforms database operations from complex, database-specific code into simple, intuitive queries that work everywhere. Start building production-ready data services in minutes!

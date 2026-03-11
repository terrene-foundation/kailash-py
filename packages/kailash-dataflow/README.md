# Kailash DataFlow

**Multi-Database Framework** - Django simplicity meets enterprise-grade production quality with PostgreSQL, MySQL, SQLite, and MongoDB support.

> ✅ **Database Support**: DataFlow supports PostgreSQL (full features), MySQL (100% feature parity since v0.5.6), SQLite (near-complete parity), and MongoDB (document database with flexible schema).
>
> ✅ **v0.7.6+ Improvements**: String IDs preserved, multi-instance isolation, deferred schema operations, Optional field handling, dict/list serialization fixes

## ⚠️ Common Mistakes (Read This First!)

| Mistake                                            | Impact                    | Correct Approach                                                                  |
| -------------------------------------------------- | ------------------------- | --------------------------------------------------------------------------------- |
| **Using `user_id` or `model_id` instead of `id`**  | 10-20 min debugging       | **CRITICAL**: Primary key MUST be named `id` (not `user_id`, `agent_id`, etc.)    |
| **Applying CreateNode pattern to UpdateNode**      | 1-2 hours debugging       | CreateNode uses flat fields, UpdateNode uses `{"filter": {...}, "fields": {...}}` |
| **Including `created_at`/`updated_at` in updates** | Validation errors         | DataFlow auto-manages these fields - NEVER include them manually                  |
| **Wrong node naming**                              | Node not found errors     | Use `ModelOperationNode` pattern (e.g., `UserCreateNode`, not `User_Create`)      |
| **Missing `db_instance` parameter**                | Generic validation errors | ALL DataFlow nodes require `db_instance` and `model_name` parameters              |

### Critical Rules

```python
# ✅ CORRECT: Primary key MUST be named 'id'
@db.model
class User:
    id: str  # ✅ MUST use 'id' - not 'user_id', 'model_id', etc.
    name: str

# ❌ WRONG: Custom primary key names cause errors
@db.model
class User:
    user_id: str  # ❌ FAILS - DataFlow requires 'id'
    name: str

# ✅ CORRECT: Different patterns for Create vs Update
# CreateNode: Flat individual fields
workflow.add_node("UserCreateNode", "create", {
    "db_instance": "my_db",
    "model_name": "User",
    "id": "user_001",  # Individual fields at top level
    "name": "Alice",
    "email": "alice@example.com"
})

# UpdateNode: Nested filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "db_instance": "my_db",
    "model_name": "User",
    "filter": {"id": "user_001"},  # Which records to update
    "fields": {"name": "Alice Updated"}  # What to change
    # ⚠️ Do NOT include created_at or updated_at - auto-managed!
})
```

## 🚀 Quick Start

### Prerequisites

- PostgreSQL 12+ OR MySQL 5.7+ (recommended for production), SQLite 3.x (development/testing), OR MongoDB 4.0+ (document database)
- Python 3.12+

### Installation

```bash
pip install kailash-dataflow
# or
pip install kailash[dataflow]
```

### Basic Usage

```python
from dataflow import DataFlow

# PostgreSQL (production) or SQLite (development)
db = DataFlow("postgresql://user:pass@localhost/dbname")
# db = DataFlow("sqlite:///app.db")  # SQLite alternative

# Define your model
@db.model
class User:
    id: str  # String IDs now preserved! (v0.4.7+)
    name: str
    email: str

# DataFlow automatically creates:
# ✅ Database schema with migrations (PostgreSQL)
# ✅ 9 workflow nodes per model (CRUD + bulk ops)
# ✅ Real SQL operations with injection protection
# ✅ Connection pooling and transaction management
# ✅ MongoDB-style query builder
# ✅ Concurrent access protection with locking
# ✅ Schema state management with rollback
```

## 🎯 What Makes DataFlow Different?

### Multi-Database Support

```python
# Production PostgreSQL
db = DataFlow("postgresql://user:pass@localhost/dbname")

# Production MySQL (100% feature parity since v0.5.6)
db = DataFlow("mysql://user:pass@localhost/dbname")

# Development SQLite
db = DataFlow("sqlite:///app.db")

# Document Database MongoDB
db = DataFlow("mongodb://localhost:27017/dbname")

# Environment-based configuration
# DATABASE_URL=postgresql://... or mysql://... or sqlite:///... or mongodb://...
db = DataFlow()  # Reads from DATABASE_URL

# Advanced features (all SQL databases)
db = DataFlow(
    "postgresql://...",  # or "mysql://..." or "sqlite:///..."
    pool_size=50,
    auto_migrate=True,
    monitoring=True
)
```

### Real Database Operations (Currently Available)

```python
# Traditional ORMs: Imperative code
User.objects.create(name="Alice")  # Django
user = User(name="Alice"); session.add(user)  # SQLAlchemy

# DataFlow: Workflow-native database operations
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserListNode", "find_users", {
    "limit": 10,
    "offset": 0
})

# Real SQL is executed: INSERT INTO users (name, email) VALUES ($1, $2)
```

### MongoDB-Style Query Builder (NEW!)

```python
# Get QueryBuilder from any model
builder = User.query_builder()

# MongoDB-style operators
builder.where("age", "$gte", 18)
builder.where("status", "$in", ["active", "premium"])
builder.where("email", "$regex", "^[a-z]+@company\.com$")
builder.order_by("created_at", "DESC")
builder.limit(10)

# Generates optimized SQL for your database
sql, params = builder.build_select()
# PostgreSQL: SELECT * FROM "users" WHERE "age" >= $1 AND "status" IN ($2, $3) AND "email" ~ $4 ORDER BY "created_at" DESC LIMIT 10

# Works seamlessly with ListNode
workflow.add_node("UserListNode", "search", {
    "filter": {
        "age": {"$gte": 18},
        "status": {"$in": ["active", "premium"]},
        "email": {"$regex": "^admin"}
    }
})
```

### Database Support Status

```python
# PostgreSQL: Full feature support
db = DataFlow(database_url="postgresql://user:pass@localhost/db")

# SQLite: Near-complete parity (missing only schema discovery)
db = DataFlow(database_url="sqlite:///app.db")

# Both support full workflow execution
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # ✅ Works with both databases

# Only limitation: Real schema discovery (PostgreSQL only)
schema = db.discover_schema(use_real_inspection=True)  # PostgreSQL only
```

### Database Operations as Workflow Nodes

```python
# Traditional ORMs: Imperative code
user = User.objects.create(name="Alice")  # Django
user = User(name="Alice"); session.add(user)  # SQLAlchemy

# DataFlow: Workflow-native (11 nodes per model!)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserListNode", "find_users", {
    "filter": {"name": {"$like": "A%"}}
})
```

### Enterprise Configuration

```python
# Multi-tenancy configuration (query modification planned)
db = DataFlow(multi_tenant=True)

# Real SQL generation with security
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=20,
    pool_max_overflow=30,
    monitoring=True,
    echo=False  # No SQL logging in production
)

# All generated nodes use parameterized queries for security
# INSERT INTO users (name, email) VALUES ($1, $2)  -- Safe from SQL injection
```

## 🔧 Context-Aware Improvements (v0.4.7+)

### String ID Preservation

```python
# String IDs are now preserved without forced integer conversion
@db.model
class Session:
    id: str  # Explicitly string - no more PostgreSQL type errors!
    user_id: str
    token: str

# String IDs work correctly in all operations
workflow.add_node("SessionCreateNode", "create", {
    "id": "sess-uuid-12345",  # Preserved as string
    "user_id": "user-uuid-67890",
    "token": "token-abc-def"
})
```

### Multi-Instance Isolation

```python
# Each DataFlow instance maintains separate context
dev_db = DataFlow("sqlite:///dev.db")
prod_db = DataFlow("postgresql://prod...")

# Models registered to specific instances
@dev_db.model
class User:
    name: str

@prod_db.model
class User:  # Same name, different instance - works!
    name: str
    email: str

# Nodes bound to correct instance automatically
```

### Deferred Schema Operations

- **Synchronous registration**: Models register immediately with @db.model
- **Async table creation**: Tables created on first use, not registration
- **Better performance**: No blocking during model definition phase

## 🚦 Implementation Status

### ✅ Currently Available (Production-Ready)

- **Database Schema Generation**: Complete CREATE TABLE for PostgreSQL, MySQL, SQLite
- **Auto-Migration System**: PostgreSQL-only, production-ready automatic schema synchronization
- **Real Database Operations**: All 11 CRUD + bulk nodes execute actual SQL
- **SQL Security**: Parameterized queries prevent SQL injection
- **Connection Management**: Connection pooling, DDL execution, error handling
- **Workflow Integration**: Full compatibility with WorkflowBuilder/LocalRuntime
- **Configuration System**: Zero-config to enterprise patterns
- **MongoDB-Style Query Builder**: Complete with all operators ($eq, $gt, $in, $regex, etc.)
- **Concurrent Access Protection**: Migration locking and atomic operations
- **Schema State Management**: Change detection, caching, and rollback capabilities
- **String ID Preservation**: String/UUID IDs preserved without forced conversion (v0.4.7+)
- **Multi-Instance Isolation**: Separate contexts for different DataFlow instances (v0.4.7+)
- **Deferred Schema Operations**: Better performance with lazy table creation (v0.4.7+)
- **Vector Similarity Search**: PostgreSQL pgvector support for semantic search, RAG, and AI applications (v0.6.0+)
- **MongoDB Document Database**: Complete NoSQL support with flexible schema, aggregation pipelines, and 8 specialized workflow nodes (v0.6.0+)

### ⚠️ Current Limitations

- **Schema Discovery**: Real database introspection (`discover_schema(use_real_inspection=True)`) is currently supported for PostgreSQL and SQLite only
- **Complex Migrations**: Some SQLite migration operations limited by ALTER TABLE syntax
- **Production Use**: Thorough testing recommended for production deployments

### 🔄 Planned Features (Roadmap)

- **Redis Query Caching**: `User.cached_query()` with automatic invalidation
- **Multi-Database Runtime**: SQLite/MySQL execution support
- **Advanced Multi-Tenancy**: Automatic query modification for tenant isolation

## 📚 Documentation

### Getting Started

- **[5-Minute Tutorial](docs/getting-started/quickstart.md)** - Build your first app
- **[Core Concepts](docs/getting-started/concepts.md)** - Understand DataFlow
- **[Examples](examples/)** - Complete applications

### Development

- **[Models](docs/development/models.md)** - Define your schema
- **[CRUD Operations](docs/development/crud.md)** - Basic operations
- **[Relationships](docs/development/relationships.md)** - Model associations

### Production

- **[Deployment](docs/production/deployment.md)** - Go to production
- **[Performance](docs/production/performance.md)** - Optimization guide
- **[Monitoring](docs/advanced/monitoring.md)** - Observability

## 💡 Real-World Examples

### E-Commerce Platform

```python
# Define your models
@db.model
class Product:
    id: int
    name: str
    price: float
    stock: int

@db.model
class Order:
    id: int
    user_id: int
    total: float
    status: str

# Use in workflows
workflow = WorkflowBuilder()

# Check inventory
workflow.add_node("ProductGetNode", "check_stock", {
    "id": "{product_id}"
})

# Create order with transaction
workflow.add_node("TransactionContextNode", "tx_start")
workflow.add_node("OrderCreateNode", "create_order", {
    "user_id": "{user_id}",
    "total": "{total}"
})
workflow.add_node("ProductUpdateNode", "update_stock", {
    "id": "{product_id}",
    "stock": "{new_stock}"
})
```

### Multi-Tenant SaaS (Current Implementation)

```python
# Enable multi-tenancy configuration
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    multi_tenant=True
)

# Multi-tenant models get tenant_id field automatically
@db.model
class User:
    name: str
    email: str
    # tenant_id: str automatically added

# Use in workflows with real database operations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@acme-corp.com"
})
workflow.add_node("UserListNode", "list_users", {
    "limit": 10,
    "filter": {}
})
```

### High-Performance ETL (Current Implementation)

```python
# Bulk operations with real database execution
workflow.add_node("UserBulkCreateNode", "import_users", {
    "data": users_data,  # List of user records
    "batch_size": 1000,
    "conflict_resolution": "skip"
})

# Real bulk INSERT operations executed
# Uses parameterized queries for security
# Processes data in configurable batches

# List operations with filters
workflow.add_node("UserListNode", "active_users", {
    "limit": 1000,
    "offset": 0,
    "order_by": ["created_at"],
    "filter": {"active": True}
})
```

### RAG Application with Vector Search (v0.6.0+)

```python
from dataflow import DataFlow
from dataflow.adapters import PostgreSQLVectorAdapter
from dataflow.nodes.vector_nodes import VectorSearchNode

# Initialize with pgvector support
adapter = PostgreSQLVectorAdapter(
    "postgresql://localhost/vectordb",
    vector_dimensions=1536,  # OpenAI embeddings
    default_distance="cosine"
)
db = DataFlow(adapter=adapter)

# Define knowledge base with vector embeddings
@db.model
class KnowledgeBase:
    id: str
    topic: str
    content: str
    embedding: list[float]  # Vector column

await db.initialize()

# Semantic search for RAG
query_embedding = await embedding_model.embed("How do I authenticate users?")

workflow = WorkflowBuilder()
workflow.add_node("VectorSearchNode", "search", {
    "table_name": "knowledge_base",
    "query_vector": query_embedding,
    "k": 5,  # Top 5 relevant documents
    "distance": "cosine"
})

results = await runtime.execute_workflow_async(workflow.build())
relevant_docs = results["search"]["results"]

# Use retrieved context for LLM generation
# See examples/pgvector_rag_example.py for complete RAG pipeline
```

### MongoDB Document Database (v0.6.0+)

```python
from dataflow import DataFlow
from dataflow.adapters import MongoDBAdapter
from dataflow.nodes.mongodb_nodes import DocumentInsertNode, AggregateNode

# Initialize MongoDB adapter (flexible schema, no models needed!)
adapter = MongoDBAdapter("mongodb://localhost:27017/ecommerce")
db = DataFlow(adapter=adapter)
await db.initialize()

# Direct document operations - no schema constraints
user_id = await adapter.insert_one("users", {
    "name": "Alice",
    "email": "alice@example.com",
    "profile": {
        "age": 30,
        "city": "NYC"
    },
    "tags": ["developer", "python"],
    # Any fields! Flexible schema
})

# MongoDB query language
users = await adapter.find(
    "users",
    filter={"age": {"$gte": 25}, "tags": {"$in": ["python"]}},
    sort=[("name", 1)],
    limit=10
)

# Aggregation pipelines for analytics
workflow = WorkflowBuilder()
workflow.add_node("AggregateNode", "sales_by_category", {
    "collection": "orders",
    "pipeline": [
        {"$match": {"status": "completed"}},
        {"$group": {
            "_id": "$category",
            "total_sales": {"$sum": "$amount"},
            "order_count": {"$sum": 1}
        }},
        {"$sort": {"total_sales": -1}},
        {"$limit": 10}
    ]
})

results = await runtime.execute_workflow_async(workflow.build())
# See examples/mongodb_crud_example.py for complete CRUD workflow
```

## 🏗️ Architecture

DataFlow seamlessly integrates with Kailash's workflow architecture:

```
┌─────────────────────────────────────────────────────┐
│                 Your Application                     │
├─────────────────────────────────────────────────────┤
│                    DataFlow                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │  Models  │  │   Nodes  │  │ Migrations│         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
│       └──────────────┴──────────────┘               │
│                Core Features                         │
│  QueryBuilder │ QueryCache │ Monitoring │ Multi-tenant │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │MongoDB-  │  │Redis     │  │Pattern   │         │
│  │style     │  │Caching   │  │Invalidate│         │
│  └──────────┘  └──────────┘  └──────────┘         │
├─────────────────────────────────────────────────────┤
│               Kailash SDK                           │
│         Workflows │ Nodes │ Runtime                 │
└─────────────────────────────────────────────────────┘
```

## 🧪 Testing

DataFlow includes comprehensive testing support:

```python
# Test with in-memory database
def test_user_creation():
    db = DataFlow(testing=True)

    @db.model
    class User:
        id: int
        name: str

    # Automatic test isolation
    user = db.test_create(User, name="Test User")
    assert user.name == "Test User"
```

## 🤝 Contributing

We welcome contributions! DataFlow follows Kailash SDK patterns:

1. Use SDK components and patterns
2. Maintain zero-config philosophy
3. Write comprehensive tests
4. Update documentation

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📊 Performance & Testing Status

### Current Performance

- **Real SQL execution** with parameterized queries (PostgreSQL, SQLite)
- **Real NoSQL execution** with MongoDB query language
- **Connection pooling** with configurable pool sizes
- **Bulk operations** with batching for large datasets
- **11 nodes auto-generated per model** (7 CRUD + 4 Bulk)
- **95% unit test pass rate** (615/648 tests passing)

### Recent Test Improvements

- **100% NO MOCKING compliance** in Tier 2-3 tests
- **Real infrastructure testing** with PostgreSQL
- **167 test files** covering all scenarios
- **3-tier testing strategy** (Unit/Integration/E2E)
- **Fixed critical bugs**: checksum tracking, field type serialization

### Testing Requirements

- PostgreSQL 12+ required for SQL integration testing
- MongoDB 4.0+ required for NoSQL integration testing
- Performance benchmarks available for PostgreSQL and MongoDB
- Advanced caching and query optimization features in development

## ⚡ Why DataFlow?

- **Real Database Operations**: Actual SQL execution, not mocks
- **Workflow-Native**: Database ops as first-class nodes
- **Production-Ready**: PostgreSQL support with connection pooling
- **Progressive**: Simple to start, enterprise features available
- **100% Kailash**: Built on proven SDK components

---

**Built with Kailash SDK** | [Parent Project](../../README.md) | [SDK Docs](../../sdk-users/)

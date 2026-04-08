# Kailash DataFlow

**Multi-Database Data Operations Framework** — Django simplicity meets enterprise-grade production quality with PostgreSQL, MySQL, SQLite, and MongoDB support, plus external data source integration via the Data Fabric Engine.

> ✅ **Database Support**: DataFlow supports PostgreSQL (full features), MySQL (100% feature parity since v0.5.6), SQLite (near-complete parity), and MongoDB (document database with flexible schema).

## 🚨 2.0.0 Breaking Changes — Read Before Upgrading

DataFlow 2.0.0 is the result of a full Phase 5-9 wiring sweep that closed 9 CRITICAL security findings and ~11,800 lines of non-functional code. The fabric subsystem in particular has material breaking changes. Full details in [CHANGELOG.md](CHANGELOG.md); the operational highlights:

- **Fabric cache is now pluggable** — `PipelineExecutor` delegates storage to `FabricCacheBackend` (`InMemoryFabricCacheBackend` or `RedisFabricCacheBackend`). Dev-mode deployments keep working unchanged; production Redis deployments MUST pass `redis_url=` when constructing the runtime.
- **Fabric cache keys include `tenant_id`** — every product with `multi_tenant=True` requires an explicit tenant extractor. Reads without a tenant now raise `FabricTenantRequiredError` instead of silently defaulting to a global cache slot. See `docs/fabric/` for migration guidance.
- **`FabricRuntime.product_info / invalidate / invalidate_all` are now async** — wrap existing call sites in `await` or `asyncio.run(...)`. Sync wrappers have been removed so the Redis backend can participate without deadlocking.
- **Express cache keys are tenant-scoped** — `db.express.list("User", filter={...})` against a `multi_tenant=True` model now requires `tenant_id` context; missing tenant raises `TenantRequiredError`.
- **`@classify("field", PII, REDACT)` actually redacts on read** — the decorator was a no-op before 2.0.0. Every existing read of a classified field will now return `[REDACTED]` for callers whose clearance level doesn't include the field. Set per-request clearance via `set_current_clearance(CONFIDENTIAL)`.
- **Trust executor runs on every query** — `TrustAwareQueryExecutor`, `DataFlowAuditStore`, and `TenantTrustManager` were exposed on `db.*` but unused until 2.0.0. Queries now emit audit events and enforce tenant boundaries. Disable per-model by setting `enable_trust=False` on `DataFlow.__init__`.
- **`rules/security.md` §No secrets in logs** — Redis/Postgres/Mongo URLs are now masked via `dataflow.utils.masking.mask_url`; downstream consumers importing `fabric.cache._mask_url` still work via a backward-compatible re-export.
- **Prometheus metrics at `/fabric/metrics`** — 13 metric families exposed via the FabricMetrics singleton. Requires the `fabric` optional extra for `prometheus-client`; without the extra the endpoint returns a plain-text explanation and counters become loud no-ops.

**Migration checklist before upgrading**:

- [ ] Audit every `db.express` read of a `multi_tenant=True` model for an explicit `tenant_id` context.
- [ ] Audit every `FabricRuntime.invalidate(...)` / `.product_info(...)` call site and wrap in `await`.
- [ ] Install the fabric extra if you scrape `/fabric/metrics`: `pip install 'kailash-dataflow[fabric]'`.
- [ ] Set a per-request clearance via `set_current_clearance(...)` before any query that should see PII fields.
- [ ] If you rely on the pre-2.0 silent-default behavior for missing tenants, revisit — that path is now a hard error.

See [CHANGELOG.md](CHANGELOG.md) § 2.0.0 for the full list, commit SHAs, and test coverage.

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
```

#### Optional Extras (Data Fabric Engine)

```bash
pip install kailash-dataflow[fabric]        # REST, file, core fabric support + Prometheus metrics (httpx, watchdog, msgpack, prometheus-client)
pip install kailash-dataflow[cloud]          # Cloud storage adapters (S3, GCS, Azure)
pip install kailash-dataflow[streaming]      # Streaming adapters (Kafka, WebSocket)
pip install kailash-dataflow[fabric-all]     # All fabric dependencies (fabric + cloud + excel + streaming)
```

The `fabric` extra is required if you want to scrape `/fabric/metrics` for Prometheus observability. Without it, the endpoint returns a plain-text explanation and fabric counters silently no-op.

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

## Connection Pool Configuration

DataFlow auto-detects safe pool sizes from your database's `max_connections`. No configuration needed for most deployments.

```python
# Auto-scaling (recommended) — pool size computed from max_connections
db = DataFlow("postgresql://user:pass@localhost/mydb")

# Explicit override (PgBouncer, shared databases)
db = DataFlow("postgresql://...", pool_size=3)

# Check pool health at runtime
stats = db.pool_stats()
# {"active": 5, "idle": 12, "max": 17, "utilization": 0.19}
```

### Environment Variables

| Variable                      | Purpose                         | Default     |
| ----------------------------- | ------------------------------- | ----------- |
| `DATAFLOW_POOL_SIZE`          | Override auto-scaled pool size  | Auto-detect |
| `DATAFLOW_WORKER_COUNT`       | Worker count for pool division  | Auto-detect |
| `DATAFLOW_STARTUP_VALIDATION` | Validate pool config at startup | `true`      |

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
# Pool auto-scales from max_connections — no pool_size needed
db = DataFlow(
    "postgresql://...",  # or "mysql://..." or "sqlite:///..."
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
# Pool auto-scales from max_connections; override only for PgBouncer/shared DBs
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
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

## Data Fabric Engine

DataFlow now supports external data sources and derived data products. The fabric engine extends DataFlow from database operations to unified data operations — connect any data source, define declarative products, and serve them with auto-generated endpoints.

### Core API

Three new methods on the `DataFlow` instance:

```python
from dataflow import DataFlow
from dataflow.fabric import RestSourceConfig, BearerAuth, StalenessPolicy

db = DataFlow("postgresql://user:pass@localhost/mydb")

# 1. Register an external data source
db.source("crm", RestSourceConfig(
    url="https://api.example.com",
    auth=BearerAuth(token_env="CRM_API_TOKEN"),
    poll_interval=60,
))

# 2. Define a data product (decorator)
@db.product("dashboard", depends_on=["User", "crm"])
async def dashboard(ctx):
    users = await ctx.express.list("User")
    deals = await ctx.source("crm").fetch("deals")
    return {"users": len(users), "deals": len(deals)}

# 3. Start the fabric runtime
await db.start(host="127.0.0.1", port=8000)
```

### Product Modes

| Mode              | Behavior                                                                                     |
| ----------------- | -------------------------------------------------------------------------------------------- |
| **materialized**  | Pre-computed and cached. Auto-refreshes on source changes. Best for dashboards and reports.  |
| **parameterized** | Computed per-request with parameters. Cached by parameter combination with configurable TTL. |
| **virtual**       | Computed on every request, never cached. Best for real-time or user-specific data.           |

```python
@db.product("stats", mode="materialized", depends_on=["Order"])
async def stats(ctx):
    return await ctx.express.count("Order")

@db.product("search", mode="parameterized", depends_on=["Product"])
async def search(ctx, q: str = "", limit: int = 10):
    return await ctx.express.list("Product", {"name": {"$like": f"%{q}%"}}, limit=limit)

@db.product("live", mode="virtual", depends_on=["Sensor"])
async def live(ctx):
    return await ctx.express.list("Sensor", {"active": True})
```

### Source Types

| Source Type | Config Class           | Description                                                         |
| ----------- | ---------------------- | ------------------------------------------------------------------- |
| REST        | `RestSourceConfig`     | HTTP APIs with ETag caching, auth, webhook support, SSRF protection |
| File        | `FileSourceConfig`     | Local files with filesystem watching (watchdog)                     |
| Cloud       | `CloudSourceConfig`    | S3, GCS, Azure Blob storage with prefix filtering                   |
| Database    | `DatabaseSourceConfig` | External databases (read-only by default)                           |
| Stream      | `StreamSourceConfig`   | Kafka topics and WebSocket streams                                  |

### `db.start()` Parameters

```python
await db.start(
    fail_fast=True,            # Raise on source health check failure
    dev_mode=False,            # Skip pre-warming, use in-memory cache
    nexus=None,                # Attach to existing Nexus instance for auth
    coordination=None,         # "redis" or "postgresql" (auto-detects)
    host="127.0.0.1",         # Bind address for fabric endpoints
    port=8000,                 # Port for fabric endpoints
    enable_writes=False,       # Enable write pass-through endpoints
    tenant_extractor=None,     # Multi-tenant request handler
)
```

### Observability

The fabric runtime exposes built-in observability:

- **Health endpoints**: Source health status with circuit breaker state
- **Pipeline traces**: Execution traces for each product refresh
- **Prometheus metrics**: Request counts, latencies, cache hit rates
- **SSE (Server-Sent Events)**: Real-time product update notifications

### Key Features

- **Pipeline executor** with change detection and configurable debounce
- **Leader election** for multi-worker coordination (Redis or in-memory)
- **Circuit breaker** per source with configurable staleness policies
- **Webhook receiver** with HMAC validation and nonce deduplication (Redis or in-memory)
- **Auto-generated REST endpoints** for all registered products
- **Write pass-through** with event-driven product refresh
- **SSRF protection** with DNS rebinding defense on REST sources

### Migration Guide

All existing DataFlow code continues to work unchanged. Fabric features are opt-in — you only need to install the extras and use the new API methods (`db.source()`, `@db.product()`, `await db.start()`) when you want external data source integration. Existing models, workflows, and express operations are unaffected.

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

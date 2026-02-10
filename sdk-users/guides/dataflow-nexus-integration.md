# DataFlow + Nexus Integration Guide

## Overview

This guide provides tested and verified configurations for integrating DataFlow (v0.11.0+) with Nexus across different use cases. All configurations reflect the current DataFlow architecture where `auto_migrate=True` (the default) works correctly in Docker, FastAPI, and CLI environments thanks to the SyncDDLExecutor.

## The Integration Challenge

When DataFlow models are registered, they create workflows that can interfere with Nexus's initialization process if `auto_discovery` is enabled:

1. **Infinite Blocking**: If Nexus uses `auto_discovery=True`, it can cause infinite blocking when DataFlow models are imported. The default is `auto_discovery=False`, so this only occurs if you explicitly opt in.

## The Solution

The integration is straightforward as of DataFlow v0.11.0:

- **Nexus**: Keep `auto_discovery=False` (the default) to prevent blocking
- **DataFlow**: Use `auto_migrate=True` (the default) -- it works correctly everywhere now

## Tested Configuration Patterns

### 1. Production API Server (High Traffic)

```python
import os
from nexus import Nexus
from dataflow import DataFlow

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,    # Default, prevents blocking
)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,       # Default: works in Docker/FastAPI via SyncDDLExecutor
    pool_size=50,            # High for concurrent requests
    monitoring=True,         # Enable performance monitoring
    cache_enabled=True,      # Enable query caching
)

@db.model
class User:
    id: str
    email: str
    name: Optional[str] = None
```

**What you get**:

- Fast startup with automatic schema creation
- All CRUD operations work
- Query caching and monitoring enabled
- Connection pooling with 50 connections

---

### 2. AI Chatbot / RAG Application

```python
import os
from nexus import Nexus
from dataflow import DataFlow

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,
)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,       # Default
    cache_enabled=True,      # Critical for fast context retrieval
    cache_ttl=3600,          # Long TTL for conversations
)

@db.model
class Conversation:
    id: str
    user_id: str
    context: str  # Cached for fast retrieval

@db.model
class Message:
    id: str
    conversation_id: str
    role: str  # 'user' or 'assistant'
    content: str
```

**Why this works**:

- Fast response times with caching
- Conversation context persisted in database with cache layer
- Automatic schema creation on startup

---

### 3. Enterprise Admin Dashboard

```python
import os
from nexus import Nexus
from dataflow import DataFlow

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,
)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,       # Default: automatic schema management
    audit_logging=True,      # Audit trail for admin actions
    monitoring=True,         # Performance monitoring
)

@db.model
class AdminUser:
    id: str
    email: str
    role: str
    permissions: Optional[str] = None
```

**What you get**:

- Full automatic migration with fast startup
- Audit logging for compliance
- Performance monitoring for dashboards

---

### 4. Microservices (Kubernetes)

```python
import os
from nexus import Nexus
from dataflow import DataFlow

# Ultra-lightweight for container orchestration
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,
    enable_durability=False,  # Stateless for horizontal scaling
)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,       # Default
    pool_size=5,             # Small per instance (scale via replicas)
    monitoring=False,        # Use K8s-level metrics instead
    cache_enabled=False,     # Use Redis separately
)

@db.model
class OrderItem:
    id: str
    product_id: str
    quantity: int
    price: float
```

**Optimizations**:

- Minimal resource usage per pod
- Fast pod scaling
- Stateless design with external cache

---

### 5. Data Migration / ETL Tool

```python
import os
from dataflow import DataFlow

# ETL tools typically don't need Nexus, just DataFlow
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,             # Default: automatic schema management
    migration_lock_timeout=60,     # Longer timeout for large migrations
)

@db.model
class SourceData:
    id: str
    legacy_id: Optional[str] = None
    data: str

@db.model
class TargetData:
    id: str
    source_id: str
    transformed_data: str
```

---

### 6. Development Environment

```python
from nexus import Nexus
from dataflow import DataFlow

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,
)

db = DataFlow(
    database_url="sqlite:///dev.db",  # Local SQLite for development
    auto_migrate=True,                # Default: creates tables automatically
    echo=True,                        # See SQL for debugging
    debug=True,                       # Enable debug mode
)

@db.model
class TestModel:
    id: str
    name: str
    debug_data: Optional[str] = None
```

**Developer benefits**:

- Fast restarts with automatic schema management
- SQL echo for debugging
- Local SQLite database

---

### 7. Multi-Tenant SaaS Platform

```python
import os
from nexus import Nexus
from dataflow import DataFlow

# Initialize DataFlow once at startup
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,       # Default
    multi_tenant=True,       # Enable multi-tenancy
)

@db.model
class TenantData:
    id: str
    tenant_id: str  # Used by multi_tenant mode
    data: str

# Create Nexus per tenant request
def create_tenant_app(tenant_id: str):
    app = Nexus(
        api_port=8000,
        mcp_port=3001,
        auto_discovery=False,
    )
    # Set tenant context
    # db.set_tenant(tenant_id)
    return app
```

**Architecture**:

- One DataFlow instance shared
- Lightweight Nexus per tenant
- Fast tenant switching

---

### 8. CI/CD Testing Pipeline

```python
from dataflow import DataFlow

db = DataFlow(
    database_url="sqlite:///:memory:",  # In-memory for tests
    auto_migrate=True,                  # Default: creates tables automatically
    tdd_mode=True,                      # Test optimizations
    test_mode=True,                     # Explicit test mode
)

@db.model
class TestEntity:
    id: str
    test_value: str
    test_flag: bool = False
```

**Test benefits**:

- Ultra-fast test execution
- Complete test isolation
- No persistent state

---

## Decision Matrix

| Use Case            | Auto-Migrate  | Key DataFlow Settings                   | Key Nexus Settings        |
| ------------------- | ------------- | --------------------------------------- | ------------------------- |
| **API Server**      | Yes (default) | `pool_size=50`, `monitoring=True`       | Default                   |
| **Chatbot**         | Yes (default) | `cache_enabled=True`, `cache_ttl=3600`  | Default                   |
| **Admin Dashboard** | Yes (default) | `audit_logging=True`, `monitoring=True` | Default                   |
| **Microservices**   | Yes (default) | `pool_size=5`, `cache_enabled=False`    | `enable_durability=False` |
| **ETL Tool**        | Yes (default) | `migration_lock_timeout=60`             | N/A                       |
| **Development**     | Yes (default) | `echo=True`, `debug=True`               | Default                   |
| **Multi-Tenant**    | Yes (default) | `multi_tenant=True`                     | Default                   |
| **CI/CD Tests**     | Yes (default) | `tdd_mode=True`, `test_mode=True`       | N/A                       |

## Key Takeaways

### Standard Configuration (Recommended)

```python
import os
from nexus import Nexus
from dataflow import DataFlow

# Nexus: auto_discovery=False is the default
app = Nexus(auto_discovery=False)

# DataFlow: auto_migrate=True is the default, works everywhere
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
)
```

This is all you need for most applications. DataFlow v0.11.0 uses SyncDDLExecutor for DDL operations, so `auto_migrate=True` works correctly in Docker, FastAPI, and all other environments without startup delays.

### When to Customize

Customize DataFlow settings when you need:

- **High concurrency**: Increase `pool_size` (default is auto-detected from environment)
- **Debugging**: Set `echo=True` and `debug=True`
- **Multi-tenancy**: Set `multi_tenant=True`
- **Compliance**: Set `audit_logging=True`
- **Performance tuning**: Adjust `cache_ttl`, `slow_query_threshold`, `monitoring`
- **Testing**: Set `tdd_mode=True` and/or `test_mode=True`

### What You Get with Default Configuration

- All 11 CRUD operations per model (Create, Read, Update, Delete, List, Count, Upsert, BulkCreate, BulkUpdate, BulkDelete, BulkUpsert)
- Transactions
- Connection pooling
- Query caching
- Automatic schema creation and migration
- All Nexus channels (API, CLI, MCP)

## Migration from Older Code

If you have existing code written for older DataFlow versions:

```python
# OLD (pre-v0.11.0 pattern with incorrect/renamed parameters)
from nexus.core import Nexus                    # Old import path
from dataflow.core.engine import DataFlow       # Old import path
app = Nexus()
db = DataFlow(
    enable_model_persistence=False,             # No longer needed for fast startup
    auto_migrate=False,                         # Was disabled to avoid startup delays
    skip_migration=True,                        # Does not exist as a parameter
    connection_pool_size=50,                    # Wrong parameter name
    enable_metrics=True,                        # Wrong parameter name
    enable_audit_log=True,                      # Wrong parameter name
)

# NEW (v0.11.0+)
import os
from nexus import Nexus                         # Correct import
from dataflow import DataFlow                   # Correct import
app = Nexus(auto_discovery=False)               # Explicit is better than implicit
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=True,                          # Default, now fast everywhere
    pool_size=50,                               # Correct parameter name
    monitoring=True,                            # Correct parameter name
    audit_logging=True,                         # Correct parameter name
)
```

### Parameter Name Reference

| Old/Wrong Name            | Correct Name (v0.11.0)                                                              |
| ------------------------- | ----------------------------------------------------------------------------------- |
| `connection_pool_size`    | `pool_size`                                                                         |
| `enable_metrics`          | `monitoring`                                                                        |
| `enable_audit_log`        | `audit_logging`                                                                     |
| `skip_migration`          | `migration_enabled=False` (or just use `auto_migrate=False`)                        |
| `enable_caching`          | `cache_enabled` (both work, `enable_caching` is an alias)                           |
| `enable_schema_discovery` | Not a constructor parameter; use `existing_schema_mode=True` for existing databases |

## Troubleshooting

### Issue: Server hangs on startup

**Solution**: Ensure `auto_discovery=False` in Nexus (this is the default, so only an issue if you set it to True)

### Issue: Tables not created

**Solution**: Ensure `auto_migrate=True` (this is the default). Check that your `database_url` is correct and the database server is reachable.

### Issue: Models not found after restart

**Expected behavior**: Models defined with `@db.model` must be imported on each application startup. This is standard Python -- the decorator registers the model when the module is loaded.

### Issue: Slow queries

**Solution**: Enable monitoring with `monitoring=True` and check `slow_query_threshold` (default 1.0 seconds). Enable caching with `cache_enabled=True`.

## Full Featured Configuration

For applications that need every feature DataFlow and Nexus offer:

```python
import os
from nexus import Nexus
from dataflow import DataFlow

# Step 1: Initialize DataFlow with full features
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],

    # Schema management (defaults)
    auto_migrate=True,                # Automatic schema creation/migration

    # Performance
    pool_size=50,                     # Connection pool size
    cache_enabled=True,               # Query caching
    cache_ttl=3600,                   # Cache TTL in seconds
    monitoring=True,                  # Performance monitoring
    slow_query_threshold=1.0,         # Slow query detection (seconds)

    # Enterprise features
    audit_logging=True,               # Audit trail
    multi_tenant=True,                # Multi-tenancy
    encryption_key=os.environ.get("ENCRYPTION_KEY"),  # Data encryption
)

# Step 2: Register models
@db.model
class User:
    id: str
    email: str
    full_name: Optional[str] = None

@db.model
class Session:
    id: str
    user_id: str
    token: str

# Step 3: Create Nexus
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,
    enable_auth=True,
    enable_monitoring=True,
    enable_durability=True,
    cors_origins=["https://app.example.com"],
)

# Step 4: Register workflows manually
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"email": "${email}"})
app.register("create_user", workflow.build())
```

### Full Features You Get:

**DataFlow Features:**

- Automatic schema creation and migration
- Connection pooling (configurable size)
- Query caching with TTL
- Performance monitoring with slow query detection
- Multi-tenant data isolation
- Audit logging for compliance
- Data encryption

**Nexus Features:**

- Multi-channel (API + CLI + MCP)
- Authentication and authorization
- Rate limiting and monitoring
- Request durability
- CORS configuration

## Configuration Comparison

| Feature                | Minimal Config     | Full Featured     |
| ---------------------- | ------------------ | ----------------- |
| **Auto-Migrate**       | Yes (default)      | Yes (default)     |
| **CRUD Operations**    | All 11 nodes       | All 11 nodes      |
| **Connection Pooling** | Yes (default size) | Yes (custom size) |
| **Query Caching**      | Yes (default)      | Yes (custom TTL)  |
| **Monitoring**         | No                 | Yes               |
| **Audit Logging**      | No                 | Yes               |
| **Multi-Tenancy**      | No                 | Yes               |
| **Encryption**         | No                 | Yes               |

## Summary

The DataFlow + Nexus integration in v0.11.0 is simple:

1. **Default configuration works for most cases**: `DataFlow(database_url=...)` with `Nexus()` is all you need
2. **`auto_migrate=True` (default) works everywhere**: Docker, FastAPI, CLI -- no startup delays
3. **`auto_discovery=False` (default) prevents blocking**: No need to explicitly set this unless upgrading from very old code
4. **Customize only what you need**: Add `pool_size`, `monitoring`, `audit_logging`, etc. as your requirements grow

Most production APIs should start with the default configuration and add features incrementally.

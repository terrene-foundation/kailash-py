# DataFlow + Nexus: Integration Guide

> **Updated for DataFlow v0.11.0+**: The startup delay tradeoff described in earlier versions of this guide no longer exists. As of v0.11.0, `auto_migrate=True` (the default) works correctly in all environments including Docker and FastAPI, using `SyncDDLExecutor` for synchronous DDL operations. You get full functionality with fast startup.

## Recommended Configuration (v0.11.0+)

With DataFlow v0.11.0+, you get all features with fast startup - no tradeoff needed:

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# ============================================
# RECOMMENDED CONFIGURATION (v0.11.0+)
# ============================================
# Startup time: <2 seconds - full features included
# auto_migrate=True (default) handles everything via SyncDDLExecutor

# Step 1: Initialize DataFlow with default settings
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",

    # auto_migrate=True is the default - works in Docker, FastAPI, CLI
    # No need for enable_model_persistence, skip_migration, etc.

    # Performance features
    enable_caching=True,              # Query caching
    enable_metrics=True,              # Performance metrics
    connection_pool_size=50,          # Connection pooling

    # Enterprise features (optional)
    multi_tenant=True,                # Multi-tenancy

    # Monitoring
    monitoring=True,                  # Performance monitoring
    slow_query_threshold=1.0          # Slow query detection
)

# Step 2: Register your models (fast with v0.11.0+)
@db.model
class User:
    id: str
    email: str
    full_name: Optional[str] = None
    created_at: Optional[str] = None
    active: bool = True

@db.model
class Session:
    id: str
    user_id: str
    token: str
    created_at: str
    expires_at: str

@db.model
class Conversation:
    id: str
    session_id: str
    user_id: str
    title: Optional[str] = None

# Step 3: Create Nexus (auto_discovery=False is the default since v1.1.1)
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,    # Default since Nexus v1.1.1

    # Enable all Nexus features
    enable_auth=True,        # Authentication
    enable_monitoring=True,  # Monitoring
    enable_durability=True,  # Request durability
    rate_limit=100,         # Rate limiting
    enable_http_transport=True,  # HTTP transport
    enable_sse_transport=True,   # SSE transport
    enable_discovery=True        # MCP discovery
)

# Step 4: Register workflows manually
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "email": "{{email}}",
    "full_name": "{{full_name}}"
})
app.register("create_user", workflow.build())
```

### What You Get with Default Configuration (v0.11.0+)

#### ALL DataFlow Features:

- **Model Registry**: Track all models across applications
- **Auto-Migration**: Automatic table creation and updates (via SyncDDLExecutor)
- **Migration History**: Complete migration audit trail
- **Schema Discovery**: Import models from existing databases
- **Foreign Key Analysis**: Automatic relationship detection
- **Risk Assessment**: Migration risk scoring
- **Staging Environment**: Test migrations safely
- **Migration Locks**: Prevent concurrent migrations
- **Rollback Support**: Undo migrations if needed
- **Multi-Tenancy**: Automatic tenant isolation
- **Audit Logging**: Complete operation history
- **Query Caching**: With automatic invalidation
- **Performance Metrics**: Detailed query analytics

#### ALL Nexus Features:

- **Multi-Channel**: API + CLI + MCP simultaneously
- **Authentication**: OAuth2, JWT, API keys
- **Authorization**: Role-based access control
- **Rate Limiting**: Per-user/global limits
- **Monitoring**: Prometheus/Grafana integration
- **Health Checks**: Automatic health endpoints
- **Request Durability**: Survive crashes
- **Session Management**: Cross-channel sessions
- **Event Streaming**: Real-time updates
- **MCP Discovery**: AI agents discover capabilities

### Typical Startup Times (v0.11.0+)

With DataFlow v0.11.0+, startup is fast regardless of how many models you have:

| Models    | Startup Time | Notes                                   |
| --------- | ------------ | --------------------------------------- |
| 1 model   | <2s          | SyncDDLExecutor handles DDL efficiently |
| 3 models  | <2s          | Same fast initialization                |
| 5 models  | <3s          | Scales well with model count            |
| 10 models | <5s          | Still fast for large applications       |

## Read-Only Configuration (Existing Databases)

If you are connecting to an existing database and do not want schema changes:

```python
# Read-only mode - no schema modifications
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False
)

db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    auto_migrate=False,              # Do not create or modify tables
    enable_caching=True,             # Keep caching
    enable_metrics=True,             # Keep metrics
    connection_pool_size=50          # Keep pooling
)

@db.model
class User:
    id: str
    email: str
    # ...more fields
```

## All Features Available with Default Config

With `auto_migrate=True` (the default), you get everything with no tradeoff:

| Feature                | Default Config (v0.11.0+) |
| ---------------------- | ------------------------- |
| **Startup Time**       | <2-5s                     |
| **Auto-Migration**     | Included                  |
| **Schema Discovery**   | Included                  |
| **CRUD Operations**    | Included                  |
| **Connection Pooling** | Included                  |
| **Caching**            | Included                  |
| **Metrics**            | Included                  |
| **All 11 Nodes/Model** | Included                  |
| **Multi-Channel**      | Included                  |

## Real-World Examples

### 1. Production API Server

```python
# Default config works for production (v0.11.0+)
db = DataFlow(database_url="postgresql://user:pass@localhost/db")
# Startup: <2s, full auto-migration via SyncDDLExecutor
```

### 2. Enterprise Admin Dashboard

```python
# Same default config - no special settings needed
db = DataFlow(database_url="postgresql://user:pass@localhost/db")
# Startup: <2s, full features
```

### 3. Microservices

```python
# Default config scales well for microservices
db = DataFlow(database_url="postgresql://user:pass@localhost/db")
# Startup: <2s
```

### 4. Development Environment

```python
# SQLite for development, same default config
db = DataFlow(database_url="sqlite:///dev.db", echo=True)
# Startup: <1s
```

### 5. Read-Only Existing Database

```python
# Only case where you change from defaults
db = DataFlow(database_url="postgresql://user:pass@localhost/db", auto_migrate=False)
# Startup: <1s, no schema changes
```

## Summary

- **DataFlow v0.11.0+ eliminates the fast-vs-full tradeoff** - you get both
- **Default `auto_migrate=True` works everywhere** (Docker, FastAPI, CLI) via SyncDDLExecutor
- **Only set `auto_migrate=False`** when connecting to existing databases you must not modify
- **Nexus `auto_discovery=False`** is the default since v1.1.1 - no special config needed

# DataFlow + Nexus: Full Functionality vs Fast Startup Guide

## The Trade-off

You have two main choices when integrating DataFlow with Nexus:

1. **FAST STARTUP (<2 seconds)**: Limited features, optimized for production APIs
2. **FULL FUNCTIONALITY (10-30 seconds)**: All features enabled, slower startup

## FULL FUNCTIONALITY Configuration

If you want ALL features of DataFlow and Nexus, here's the configuration:

```python
from nexus import Nexus
from dataflow.core.engine import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# ============================================
# FULL FUNCTIONALITY CONFIGURATION
# ============================================
# Startup time: 10-30 seconds typical
# You get: EVERYTHING

# Step 1: Initialize DataFlow FIRST with ALL features
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",

    # FULL FEATURES - These cause the slower startup
    enable_model_persistence=True,    # ✅ Model persistence enabled (adds ~5s per model)
    auto_migrate=True,                # ✅ Auto-migration (adds ~2-5s)
    skip_migration=False,             # ✅ Migration tracking
    enable_schema_discovery=True,     # ✅ Schema introspection

    # Performance features (still fast)
    enable_caching=True,              # ✅ Query caching
    enable_metrics=True,              # ✅ Performance metrics
    connection_pool_size=50,          # ✅ Connection pooling

    # Enterprise features (optional, add more time)
    enable_audit_log=True,            # ✅ Audit trail (adds ~2s)
    multi_tenant=True,                # ✅ Multi-tenancy (adds ~2s)

    # Monitoring
    monitoring=True,                  # ✅ Performance monitoring
    slow_query_threshold=1.0          # ✅ Slow query detection
)

# Step 2: Register your models (each adds ~2-5s with persistence)
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

# Step 3: Create Nexus AFTER DataFlow is initialized
# IMPORTANT: Still use auto_discovery=False to avoid re-import issues
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False,    # Still keep False even with full features

    # Enable all Nexus features
    enable_auth=True,        # ✅ Authentication
    enable_monitoring=True,  # ✅ Monitoring
    enable_durability=True,  # ✅ Request durability
    rate_limit=100,         # ✅ Rate limiting
    enable_http_transport=True,  # ✅ HTTP transport
    enable_sse_transport=True,   # ✅ SSE transport
    enable_discovery=True        # ✅ MCP discovery
)

# Step 4: Register workflows manually
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "email": "{{email}}",
    "full_name": "{{full_name}}"
})
app.register("create_user", workflow.build())
```

### What You Get with Full Functionality

#### ✅ ALL DataFlow Features:
- **Model Registry**: Track all models across applications
- **Model Persistence**: Models survive restarts
- **Model Versioning**: Track schema changes over time
- **Auto-Migration**: Automatic table creation and updates
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

#### ✅ ALL Nexus Features:
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

### Typical Startup Times with Full Features

| Models | Startup Time | Breakdown |
|--------|-------------|-----------|
| 1 model | ~10-12s | DataFlow: 8s, Model: 2s, Nexus: 1s |
| 3 models | ~15-20s | DataFlow: 8s, Models: 6s, Nexus: 1s |
| 5 models | ~20-30s | DataFlow: 8s, Models: 10s, Nexus: 1s |
| 10 models | ~30-45s | DataFlow: 8s, Models: 20s, Nexus: 1s |

## FAST Configuration (Production APIs)

For comparison, here's the fast configuration most production APIs should use:

```python
# ============================================
# FAST CONFIGURATION
# ============================================
# Startup time: <2 seconds
# You lose: Persistence, migrations, discovery

# Step 1: Create Nexus first
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False  # CRITICAL: Prevents blocking
)

# Step 2: Create DataFlow with minimal features
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",

    # FAST SETTINGS - Skip slow features
    enable_model_persistence=False,  # ❌ Skip model persistence for fast startup
    auto_migrate=False,              # ❌ No auto-migration
    skip_migration=True,             # ❌ No migration tracking

    # Keep performance features
    enable_caching=True,             # ✅ Still have caching
    enable_metrics=True,             # ✅ Still have metrics
    connection_pool_size=50          # ✅ Still have pooling
)

# Models register instantly!
@db.model
class User:
    id: str
    email: str
    # ...more fields
```

## When to Use Each Configuration

### Use FULL FUNCTIONALITY when:
- **Admin Dashboards**: Need model introspection and management
- **Development Tools**: Need to discover and modify schemas
- **ETL/Migration Tools**: Core functionality requires migrations
- **One-time Startup**: Services that start once and run long
- **Schema Management**: Need version control for database schemas

### Use FAST CONFIGURATION when:
- **Production APIs**: Need fast restarts for deployments
- **Microservices**: Need quick scaling in Kubernetes
- **Serverless**: Need minimal cold start times
- **High Availability**: Can't afford 30s downtime
- **CI/CD Tests**: Need fast test execution

## Alternative: Lazy Initialization Pattern

If you need both fast startup AND full features, use lazy initialization:

```python
import threading
from nexus import Nexus
from dataflow import DataFlow

# Start server immediately
app = Nexus(auto_discovery=False)
print("✅ Server ready!")  # <1 second

# Initialize DataFlow in background
def init_dataflow_async():
    global db
    db = DataFlow(
        enable_model_persistence=True,  # Full features
        auto_migrate=True
    )

    @db.model
    class User:
        # ... model definition
        pass

    print("✅ DataFlow ready!")  # After 10-30s

# Start background initialization
thread = threading.Thread(target=init_dataflow_async)
thread.start()

# Server is already accepting requests!
app.start()
```

## Decision Tree

```
Do you need model persistence across restarts?
├─ YES → Do you need fast startup (<5s)?
│   ├─ YES → Use Lazy Initialization Pattern
│   └─ NO → Use Full Functionality Configuration
└─ NO → Do you need auto-migrations?
    ├─ YES → Use Full Functionality (accept slow startup)
    └─ NO → Use Fast Configuration (<2s startup)
```

## Configuration Comparison Table

| Feature | Fast Config | Full Config | Time Impact |
|---------|------------|-------------|-------------|
| **Startup Time** | <2s ✅ | 10-30s ❌ | - |
| **Model Persistence** | ❌ | ✅ | +2s/model |
| **Auto-Migration** | ❌ | ✅ | +5s |
| **Migration History** | ❌ | ✅ | +2s |
| **Schema Discovery** | ❌ | ✅ | +3s |
| **CRUD Operations** | ✅ | ✅ | No impact |
| **Connection Pooling** | ✅ | ✅ | No impact |
| **Caching** | ✅ | ✅ | No impact |
| **Metrics** | ✅ | ✅ | No impact |
| **All 9 Nodes/Model** | ✅ | ✅ | No impact |
| **Multi-Channel** | ✅ | ✅ | No impact |

## Real-World Recommendations

### 1. Production API Server
```python
# Use FAST config - APIs need quick restarts
db = DataFlow(enable_model_persistence=False, auto_migrate=False)
# Startup: <2s
```

### 2. Enterprise Admin Dashboard
```python
# Use FULL config - Accept slow startup for features
db = DataFlow(enable_model_persistence=True, auto_migrate=True)
# Startup: 10-30s
```

### 3. Microservices
```python
# Use FAST config - Need quick scaling
db = DataFlow(enable_model_persistence=False, auto_migrate=False)
# Startup: <1.5s
```

### 4. Development Environment
```python
# Use FAST config - Need quick iteration
db = DataFlow(enable_model_persistence=False, auto_migrate=False, echo=True)
# Startup: <2s
```

### 5. ETL/Migration Tool
```python
# Use FULL config - Migration is core functionality
db = DataFlow(enable_model_persistence=True, auto_migrate=True)
# Startup: 10-30s (acceptable for batch jobs)
```

## Summary

- **Most production APIs should use FAST configuration** (<2s startup)
- **Only use FULL configuration when you actually need** persistence, migrations, or discovery
- **The 10-30s startup time is the price** for full enterprise features
- **Consider lazy initialization** if you need both fast startup and full features
- **Always set `auto_discovery=False` in Nexus** regardless of configuration

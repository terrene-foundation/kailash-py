# Unified Runtime Guide

The LocalRuntime has been enhanced to provide a unified execution engine with automatic enterprise capabilities through composable integration with existing SDK nodes.

## 🚀 Quick Start

### Basic Usage (100% Backward Compatible)
```python
from kailash.runtime.local import LocalRuntime

# Basic usage - works exactly as before
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# With debug mode
runtime = LocalRuntime(debug=True)
results, run_id = runtime.execute(workflow)

# With cycles enabled
runtime = LocalRuntime(enable_cycles=True)
results, run_id = runtime.execute(workflow)
```

### Enterprise Features
```python
from kailash.runtime.local import LocalRuntime
from kailash.access_control import UserContext

# Create user context for multi-tenant isolation
user_context = UserContext(
    user_id="analyst_01",
    tenant_id="acme_corp",
    email="analyst@acme.com",
    roles=["data_analyst", "viewer"],
    attributes={"department": "finance", "clearance": "high"}
)

# Enterprise runtime with all features
runtime = LocalRuntime(
    # Performance & Execution
    enable_async=True,           # Auto-detect and run async nodes
    max_concurrency=20,          # Parallel execution limit
    enable_monitoring=True,      # Automatic performance tracking

    # Security & Compliance
    enable_security=True,        # Access control enforcement
    enable_audit=True,           # Compliance audit logging
    user_context=user_context,   # Multi-tenant isolation

    # Resource Management
    resource_limits={
        "memory_mb": 4096,       # Memory limit
        "cpu_cores": 4,          # CPU limit
        "timeout_seconds": 300   # Execution timeout
    }
)

# Execute with automatic enterprise integration
results, run_id = runtime.execute(workflow, task_manager, parameters)
```

## 🎯 Key Features

### 1. **Automatic Enterprise Node Integration**
When you enable enterprise features, the runtime automatically integrates with existing SDK nodes:

- `enable_audit=True` → Automatically uses `AuditLogNode` for compliance logging
- `enable_security=True` → Automatically uses `AccessControlManager` for permissions
- `enable_monitoring=True` → Automatically uses `TaskManager` and `MetricsCollector`

No manual node construction or wiring required!

### 2. **Async Execution Support**
```python
# Async-optimized runtime
runtime = LocalRuntime(enable_async=True, max_concurrency=10)

# Automatically detects async nodes and runs them concurrently
results, run_id = runtime.execute(workflow)

# Or use async interface directly
results, run_id = await runtime.execute_async(workflow)
```

### 3. **Progressive Feature Adoption**
Start simple and add features as needed:

```python
# Stage 1: Basic development
runtime = LocalRuntime()

# Stage 2: Add monitoring
runtime = LocalRuntime(enable_monitoring=True)

# Stage 3: Add compliance
runtime = LocalRuntime(
    enable_monitoring=True,
    enable_audit=True,
    user_context=user_context
)

# Stage 4: Full enterprise
runtime = LocalRuntime(
    enable_monitoring=True,
    enable_audit=True,
    enable_security=True,
    enable_async=True,
    user_context=user_context,
    resource_limits={...}
)
```

## 📊 Comparison: Before vs After

### Before (Manual Enterprise Setup)
```python
# Complex manual setup required
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.access_control import AccessControlManager
from kailash.tracking import TaskManager

# Manual node construction
audit_node = AuditLogNode()
acm = AccessControlManager()
task_manager = TaskManager()

# Manual wiring and execution
audit_result = audit_node.execute(...)
access_result = acm.check_access(...)

# Then run workflow
runtime = LocalRuntime()
results = runtime.execute(workflow, task_manager=task_manager)
```

### After (Unified Runtime)
```python
# Simple configuration-based approach
runtime = LocalRuntime(
    enable_audit=True,      # AuditLogNode automatic
    enable_security=True,   # AccessControlManager automatic
    enable_monitoring=True, # TaskManager automatic
    user_context=user_ctx   # Multi-tenant automatic
)

# Everything integrated automatically
results, run_id = runtime.execute(workflow)
```

## 🔧 Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `debug` | bool | False | Enable debug logging |
| `enable_cycles` | bool | True | Support for cyclic workflows |
| `enable_async` | bool | True | Auto-detect and run async nodes |
| `max_concurrency` | int | 10 | Maximum parallel operations |
| `user_context` | UserContext | None | User/tenant isolation |
| `enable_monitoring` | bool | True | Performance tracking |
| `enable_security` | bool | False | Access control checks |
| `enable_audit` | bool | False | Compliance logging |
| `resource_limits` | dict | {} | Resource constraints |

## 🏢 Enterprise Use Cases

### Multi-Tenant SaaS Application
```python
# Each tenant gets isolated execution
def create_tenant_runtime(tenant_id: str, user: User):
    return LocalRuntime(
        enable_security=True,
        enable_audit=True,
        user_context=UserContext(
            user_id=user.id,
            tenant_id=tenant_id,
            email=user.email,
            roles=user.roles
        )
    )
```

### Compliance-Critical Processing
```python
# Financial/Healthcare compliance
runtime = LocalRuntime(
    enable_audit=True,           # Every action logged
    enable_security=True,        # Access control enforced
    enable_monitoring=True,      # Performance tracked
    user_context=compliance_user
)
```

### High-Performance Data Pipeline
```python
# Optimized for throughput
runtime = LocalRuntime(
    enable_async=True,
    max_concurrency=50,
    enable_monitoring=True,
    resource_limits={
        "memory_mb": 16384,
        "cpu_cores": 16
    }
)
```

## ⚠️ Important Notes

1. **Backward Compatibility**: All existing code continues to work without changes
2. **AsyncLocalRuntime**: Still available as a compatibility wrapper
3. **Enterprise Nodes**: Can still be used independently when needed
4. **Resource Limits**: Enforced at the workflow level, not individual nodes
5. **Security**: When enabled, requires proper UserContext configuration

## 🎯 Best Practices

1. **Start Simple**: Use basic `LocalRuntime()` for development
2. **Add Features Progressively**: Enable features as requirements grow
3. **Use UserContext**: Always provide user context for enterprise features
4. **Monitor Performance**: Enable monitoring for production workloads
5. **Audit Critical Workflows**: Enable audit for compliance requirements

## 📚 Related Documentation

- [Architecture Decision: ADR-048 Unified Runtime](../../# contrib (removed)/architecture/adr/0048-unified-runtime-architecture.md)
- [Test Impact Analysis: ADR-049](../../# contrib (removed)/architecture/adr/0049-test-impact-analysis-unified-runtime.md)
- [Enterprise Node Catalog](../nodes/comprehensive-node-catalog.md#enterprise-nodes)
- [Access Control Guide](./09-access-control-patterns.md)

---

**Next**: [19-advanced-patterns.md](./19-advanced-patterns.md) | **Previous**: [17-middleware-database-guide.md](./17-middleware-database-guide.md)

# Multi-Tenant Architecture

DataFlow provides comprehensive multi-tenant support with automatic data isolation, security, and performance optimization.

## Overview

Multi-tenancy in DataFlow ensures complete data isolation between tenants while sharing the same application infrastructure. It supports multiple isolation strategies suitable for different scale and security requirements.

## Quick Start

Enable multi-tenancy on any model:

```python
from kailash.workflow.builder import WorkflowBuilder
from dataflow import DataFlow

db = DataFlow()

@db.model
class Document:
    title: str
    content: str

    __dataflow__ = {
        'multi_tenant': True
    }
```

This automatically:
- Adds `tenant_id` field to the model
- Filters all queries by current tenant
- Validates tenant access on all operations
- Prevents cross-tenant data access

## Tenant Isolation Strategies

### 1. Row-Level Isolation (Default)

All tenants share the same tables with row-level filtering:

```python
db = DataFlow(
    multi_tenant_strategy="row_level",
    tenant_id_field="tenant_id"
)

@db.model
class Order:
    customer_id: int
    total: float

    __dataflow__ = {
        'multi_tenant': True
    }

# All queries automatically filtered
workflow.add_node("OrderListNode", "orders", {
    "filter": {"status": "pending"}
    # tenant_id filter added automatically
})
```

### 2. Schema Isolation

Each tenant gets a separate schema (PostgreSQL/MySQL):

```python
db = DataFlow(
    multi_tenant_strategy="schema",
    tenant_schema_prefix="tenant_"
)

# Tenant "acme" uses schema "tenant_acme"
# Tenant "globex" uses schema "tenant_globex"
```

### 3. Database Isolation

Each tenant gets a separate database (highest isolation):

```python
db = DataFlow(
    multi_tenant_strategy="database",
    tenant_database_map={
        "acme": "postgresql://localhost/acme_db",
        "globex": "postgresql://localhost/globex_db",
        "default": "postgresql://localhost/shared_db"
    }
)
```

## Setting Tenant Context

### Request-Based Context

```python
from dataflow.context import set_tenant

# In your web framework middleware
def tenant_middleware(request):
    # Extract tenant from subdomain
    tenant_id = request.host.split('.')[0]

    # Or from header
    tenant_id = request.headers.get('X-Tenant-ID')

    # Set for this request
    set_tenant(tenant_id)
```

### Workflow-Based Context

```python
# Set tenant for entire workflow
workflow = WorkflowBuilder()
workflow.set_context({"tenant_id": "acme"})

# All nodes in workflow use this tenant
workflow.add_node("UserCreateNode", "create", {
    "name": "John Doe",
    "email": "john@acme.com"
    # tenant_id="acme" added automatically
})
```

### Explicit Tenant

```python
# Override tenant for specific operation
workflow.add_node("UserListNode", "admin_view", {
    "filter": {"active": True},
    "tenant_id": "globex",  # Explicit tenant
    "admin_override": True  # Requires permission
})
```

## Tenant Management

### Creating Tenants

```python
@db.model
class Tenant:
    name: str
    subdomain: str = Field(unique=True)
    plan: str = "free"
    active: bool = True
    settings: dict = {}
    created_at: datetime = None

# Create new tenant
workflow.add_node("TenantCreateNode", "new_tenant", {
    "name": "Acme Corporation",
    "subdomain": "acme",
    "plan": "enterprise"
})

# Initialize tenant schema/database
workflow.add_node("TenantInitNode", "init", {
    "tenant_id": "$new_tenant.id",
    "create_schema": True,
    "seed_data": True
})
```

### Tenant Configuration

```python
@db.model
class TenantConfig:
    tenant_id: str = Field(primary_key=True)

    # Feature flags
    features: dict = {
        "advanced_analytics": False,
        "api_access": True,
        "max_users": 10
    }

    # Limits
    storage_limit_gb: int = 10
    api_rate_limit: int = 1000  # per hour

    # Customization
    branding: dict = {}
    custom_domain: str = None
```

## Cross-Tenant Operations

### Admin Access

```python
from dataflow.permissions import require_role

@require_role("super_admin")
def cross_tenant_report():
    workflow = WorkflowBuilder()

    # Query across all tenants
    workflow.add_node("UserListNode", "all_users", {
        "filter": {"created_at": {"$gte": "2025-01-01"}},
        "cross_tenant": True,  # Requires permission
        "include_tenant": True  # Add tenant info to results
    })

    return workflow
```

### Tenant Switching

```python
from dataflow.context import switch_tenant, current_tenant

# Temporarily switch tenant
with switch_tenant("globex"):
    # Operations run as globex tenant
    workflow = WorkflowBuilder()
    workflow.add_node("OrderListNode", "orders", {})
    results = runtime.execute(workflow.build())

# Back to original tenant
print(f"Current tenant: {current_tenant()}")
```

## Performance Optimization

### Tenant-Specific Indexes

```python
@db.model
class Event:
    tenant_id: str  # Added automatically
    user_id: int
    event_type: str
    occurred_at: datetime

    __indexes__ = [
        # Composite index with tenant_id first
        {"fields": ["tenant_id", "user_id", "occurred_at"]},
        {"fields": ["tenant_id", "event_type", "occurred_at"]}
    ]

    __dataflow__ = {
        'multi_tenant': True,
        'partition_by': 'tenant_id'  # PostgreSQL partitioning
    }
```

### Connection Pooling

```python
# Per-tenant connection pools
db = DataFlow(
    multi_tenant_strategy="schema",
    connection_pool_config={
        "pool_size_per_tenant": 5,
        "max_tenants_cached": 100,
        "eviction_policy": "LRU"
    }
)
```

### Query Optimization

```python
# Optimize for tenant-specific queries
@db.model
class Product:
    name: str
    category: str
    price: float

    __dataflow__ = {
        'multi_tenant': True,
        'tenant_shard_key': 'tenant_id',  # For sharding
        'cache_by_tenant': True
    }
```

## Security

### Data Isolation Validation

```python
# Automatic validation prevents cross-tenant access
try:
    workflow.add_node("OrderUpdateNode", "update", {
        "id": 123,  # Order from different tenant
        "status": "shipped"
    })
except TenantAccessError:
    # Prevented cross-tenant update
    pass
```

### Audit Trail

```python
@db.model
class SensitiveData:
    content: str

    __dataflow__ = {
        'multi_tenant': True,
        'audit_log': True,
        'audit_include_tenant': True  # Log tenant in audit
    }

# Query audit log for tenant
workflow.add_node("AuditLogNode", "tenant_audit", {
    "model": "SensitiveData",
    "tenant_id": current_tenant(),
    "date_range": {"start": "2025-01-01", "end": "2025-01-31"}
})
```

### Encryption Per Tenant

```python
db = DataFlow(
    multi_tenant_encryption={
        "enabled": True,
        "key_per_tenant": True,
        "key_rotation_days": 90
    }
)

@db.model
class PaymentMethod:
    card_number: str = Field(encrypted=True)
    # Encrypted with tenant-specific key
```

## Migration and Onboarding

### Tenant Onboarding Workflow

```python
def onboard_tenant(tenant_data):
    workflow = WorkflowBuilder()

    # 1. Create tenant record
    workflow.add_node("TenantCreateNode", "tenant", tenant_data)

    # 2. Initialize schema/database
    workflow.add_node("SchemaInitNode", "schema", {
        "tenant_id": "$tenant.id",
        "strategy": "schema"
    })

    # 3. Run migrations
    workflow.add_node("MigrationNode", "migrate", {
        "tenant_id": "$tenant.id",
        "target": "latest"
    })

    # 4. Seed default data
    workflow.add_node("DataSeedNode", "seed", {
        "tenant_id": "$tenant.id",
        "seed_type": "default"
    })

    # 5. Create admin user
    workflow.add_node("UserCreateNode", "admin", {
        "tenant_id": "$tenant.id",
        "email": tenant_data["admin_email"],
        "role": "admin"
    })

    return runtime.execute(workflow.build())
```

### Tenant Migration

```python
# Migrate tenant between strategies
workflow.add_node("TenantMigrationNode", "migrate", {
    "tenant_id": "acme",
    "from_strategy": "row_level",
    "to_strategy": "schema",
    "verify_data": True,
    "rollback_on_error": True
})
```

## Monitoring

### Tenant Metrics

```python
workflow.add_node("TenantMetricsNode", "metrics", {
    "tenant_id": current_tenant(),
    "metrics": [
        "storage_used",
        "api_calls_count",
        "active_users",
        "database_connections"
    ],
    "period": "last_30_days"
})
```

### Usage Tracking

```python
@db.model
class TenantUsage:
    tenant_id: str
    date: date
    api_calls: int = 0
    storage_bytes: int = 0
    active_users: int = 0

    __indexes__ = [
        {"fields": ["tenant_id", "date"], "unique": True}
    ]
```

## Best Practices

### 1. Choose the Right Strategy

| Strategy | Use When | Pros | Cons |
|----------|----------|------|------|
| Row-level | <1000 tenants | Simple, low overhead | Careful index design needed |
| Schema | 100-10K tenants | Good isolation, easy backup | Schema management complexity |
| Database | <100 tenants | Complete isolation | Higher resource usage |

### 2. Design for Tenant Scale

```python
# Good: Tenant ID first in composite indexes
__indexes__ = [
    {"fields": ["tenant_id", "created_at", "status"]}
]

# Bad: Tenant ID not first
__indexes__ = [
    {"fields": ["created_at", "tenant_id", "status"]}
]
```

### 3. Handle Tenant Limits

```python
from dataflow.limits import check_tenant_limit

@check_tenant_limit("max_users")
def create_user(user_data):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "user", user_data)
    return workflow
```

### 4. Plan for Growth

```python
# Start with row-level, prepare for schema
db = DataFlow(
    multi_tenant_strategy="row_level",
    migration_ready=True,  # Prepare for strategy change
    tenant_id_index_all=True  # Index everything by tenant
)
```

## Common Patterns

### SaaS Application

```python
# Freemium SaaS with tenant tiers
@db.model
class Account:
    # Tenant info
    company_name: str
    subdomain: str = Field(unique=True)

    # Billing
    plan: str = "free"  # free, pro, enterprise
    stripe_customer_id: str = None
    trial_ends_at: datetime = None

    # Limits based on plan
    max_users: int = 5
    max_projects: int = 10
    storage_gb: int = 1

    __dataflow__ = {
        'multi_tenant': True,
        'tenant_root': True  # This is the tenant definition
    }
```

### Enterprise Platform

```python
# Enterprise with strict isolation
db = DataFlow(
    multi_tenant_strategy="database",
    tenant_compliance={
        "data_residency": True,  # Keep data in tenant's region
        "encryption_at_rest": True,
        "audit_retention_years": 7
    }
)

@db.model
class ComplianceRecord:
    data_type: str
    classification: str  # public, internal, confidential, restricted
    retention_days: int

    __dataflow__ = {
        'multi_tenant': True,
        'encrypt_fields': ['content'],
        'audit_all_access': True
    }
```

---

**Next**: See [Security & Encryption](security.md) for additional security features.

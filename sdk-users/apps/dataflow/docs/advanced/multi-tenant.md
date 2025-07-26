# DataFlow Multi-Tenant Architecture

Comprehensive guide to building multi-tenant applications with DataFlow.

## Overview

DataFlow provides first-class support for multi-tenant architectures, enabling you to build SaaS applications that serve multiple customers with data isolation, security, and scalability.

## Multi-Tenant Strategies

### 1. Database Per Tenant

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash_dataflow import DataFlow, TenantManager

# Configure tenant manager
tenant_manager = TenantManager(
    strategy="database_per_tenant",
    master_db_url="postgresql://master.db/tenant_registry",
    tenant_db_pattern="postgresql://db.com/{tenant_id}_db"
)

# Initialize DataFlow with tenant support
db = DataFlow(tenant_manager=tenant_manager)

# Models automatically tenant-scoped
@db.model
class Order:
    id: int
    tenant_id: str  # Automatically injected
    customer_id: int
    total: float
    status: str
```

### 2. Schema Per Tenant

```python
# PostgreSQL schema-based isolation
tenant_manager = TenantManager(
    strategy="schema_per_tenant",
    database_url="postgresql://db.com/saas_app",
    schema_pattern="{tenant_id}_schema",
    search_path_update=True  # Auto-update search_path
)

# Workflow with tenant context
workflow = WorkflowBuilder()

workflow.add_node("TenantContextNode", "set_tenant", {
    "tenant_id": ":tenant_id",
    "validate": True  # Ensure tenant exists
})

workflow.add_node("OrderListNode", "list_orders", {
    # Automatically uses tenant schema
    "filter": {"status": "pending"}
})
```

### 3. Row-Level Isolation

```python
# Shared tables with tenant_id column
tenant_manager = TenantManager(
    strategy="row_level",
    database_url="postgresql://db.com/app",
    tenant_column="tenant_id",
    enforce_filter=True  # Always filter by tenant_id
)

@db.model
class Product:
    id: int
    tenant_id: str
    name: str
    price: float

    __dataflow__ = {
        'indexes': [
            {'fields': ['tenant_id', 'id']},  # Composite index
            {'fields': ['tenant_id', 'name']}
        ],
        'row_level_security': True  # Enable RLS
    }
```

## Tenant Provisioning

### Automated Tenant Setup

```python
workflow = WorkflowBuilder()

# Create new tenant
workflow.add_node("TenantCreateNode", "create_tenant", {
    "tenant_data": {
        "id": "acme_corp",
        "name": "ACME Corporation",
        "plan": "enterprise",
        "region": "us-east-1"
    }
})

# Provision tenant resources
workflow.add_node("TenantProvisionNode", "provision", {
    "tenant_id": ":tenant_id",
    "resources": [
        "database",      # Create tenant database/schema
        "tables",        # Create tenant tables
        "indexes",       # Create optimized indexes
        "seed_data",     # Load initial data
        "cache",         # Setup Redis namespace
        "storage"        # Setup S3 bucket/prefix
    ]
})

# Configure tenant settings
workflow.add_node("TenantConfigNode", "configure", {
    "tenant_id": ":tenant_id",
    "settings": {
        "max_users": 1000,
        "storage_quota": "100GB",
        "api_rate_limit": 10000,
        "features": ["advanced_analytics", "api_access"]
    }
})
```

### Tenant Migration

```python
# Migrate tenant data between strategies
workflow.add_node("TenantMigrationNode", "migrate_tenant", {
    "tenant_id": "acme_corp",
    "from_strategy": "row_level",
    "to_strategy": "schema_per_tenant",
    "migration_options": {
        "parallel_copy": True,
        "verify_data": True,
        "zero_downtime": True,
        "rollback_on_error": True
    }
})
```

## Security and Isolation

### Automatic Tenant Filtering

```python
# All queries automatically filtered by tenant
@db.enforce_tenant_isolation
class SecureWorkflow:
    def execute(self, tenant_id):
        workflow = WorkflowBuilder()

        # Set tenant context
        workflow.add_node("TenantContextNode", "set_context", {
            "tenant_id": tenant_id,
            "strict": True  # Fail if tenant not found
        })

        # All subsequent queries scoped to tenant
        workflow.add_node("UserListNode", "list_users", {})
        workflow.add_node("OrderListNode", "list_orders", {})

        # Cross-tenant query blocked
        workflow.add_node("CrossTenantQueryNode", "analytics", {
            "allowed": False  # Throws security exception
        })
```

### Row-Level Security

```python
# PostgreSQL RLS for additional security
workflow.add_node("RLSConfigNode", "setup_rls", {
    "tables": ["users", "orders", "products"],
    "policy": """
        CREATE POLICY tenant_isolation ON {table}
        FOR ALL TO {role}
        USING (tenant_id = current_setting('app.current_tenant'))
    """
})

# Enable RLS in session
workflow.add_node("SessionConfigNode", "set_session", {
    "parameters": {
        "app.current_tenant": ":tenant_id"
    }
})
```

## Performance Optimization

### Tenant-Aware Caching

```python
# Redis with tenant namespacing
cache_config = {
    "strategy": "redis",
    "key_pattern": "tenant:{tenant_id}:{key}",
    "ttl_by_tenant": {
        "free": 300,      # 5 minutes for free tier
        "pro": 3600,      # 1 hour for pro
        "enterprise": 0   # No expiry for enterprise
    }
}

workflow.add_node("CachedReadNode", "get_products", {
    "cache_key": "products:active",
    "cache_config": cache_config,
    "node": "ProductListNode",
    "node_params": {"filter": {"active": True}}
})
```

### Tenant-Specific Connection Pools

```python
# Allocate resources by tenant tier
def get_tenant_pool_config(tenant):
    """Get pool configuration based on tenant tier."""
    tier_configs = {
        "free": {
            "pool_size": 2,
            "pool_max_overflow": 3,
            "statement_timeout": 5000  # 5 second timeout
        },
        "pro": {
            "pool_size": 10,
            "pool_max_overflow": 20,
            "statement_timeout": 30000  # 30 seconds
        },
        "enterprise": {
            "pool_size": 50,
            "pool_max_overflow": 100,
            "statement_timeout": 0  # No timeout
        }
    }

    return DataFlowConfig(**tier_configs.get(tenant.tier, tier_configs["free"]))
```

## Monitoring and Analytics

### Tenant Metrics

```python
workflow = WorkflowBuilder()

# Collect tenant metrics
workflow.add_node("TenantMetricsNode", "collect_metrics", {
    "metrics": [
        "storage_usage",
        "api_calls",
        "active_users",
        "database_connections",
        "query_performance"
    ],
    "aggregation": "hourly"
})

# Analyze tenant health
workflow.add_node("PythonCodeNode", "analyze_health", {
    "code": """
metrics = get_input_data("collect_metrics")

for tenant_id, data in metrics.items():
    # Check resource usage
    if data["storage_usage"] > data["storage_quota"] * 0.9:
        alert_tenant(tenant_id, "storage_warning")

    # Check performance
    if data["avg_query_time"] > 1.0:  # 1 second
        analyze_slow_queries(tenant_id)

    # Check limits
    if data["api_calls"] > data["api_limit"] * 0.8:
        implement_rate_limiting(tenant_id)
"""
})
```

### Cross-Tenant Analytics

```python
# Admin-only cross-tenant queries
@db.require_admin
def cross_tenant_analytics():
    workflow = WorkflowBuilder()

    # Bypass tenant isolation for analytics
    workflow.add_node("AdminContextNode", "admin_mode", {
        "bypass_tenant_filter": True,
        "audit_log": True  # Log admin access
    })

    # Aggregate across tenants
    workflow.add_node("CrossTenantQueryNode", "usage_stats", {
        "query": """
            SELECT
                tenant_id,
                COUNT(*) as total_users,
                SUM(storage_used) as total_storage,
                AVG(api_calls) as avg_api_calls
            FROM tenant_metrics
            GROUP BY tenant_id
        """
    })
```

## Tenant Lifecycle Management

### Tenant Onboarding

```python
workflow = WorkflowBuilder()

# Complete tenant onboarding
workflow.add_node("TenantOnboardingNode", "onboard", {
    "steps": [
        {
            "name": "create_account",
            "handler": "create_tenant_account"
        },
        {
            "name": "provision_resources",
            "handler": "provision_tenant_resources"
        },
        {
            "name": "configure_domain",
            "handler": "setup_custom_domain"
        },
        {
            "name": "import_data",
            "handler": "import_initial_data"
        },
        {
            "name": "send_welcome",
            "handler": "send_welcome_email"
        }
    ],
    "rollback_on_failure": True
})
```

### Tenant Suspension/Deletion

```python
# Suspend tenant
workflow.add_node("TenantSuspendNode", "suspend", {
    "tenant_id": ":tenant_id",
    "reason": "payment_overdue",
    "actions": [
        "disable_api_access",
        "disable_ui_access",
        "pause_background_jobs",
        "notify_tenant"
    ],
    "grace_period_days": 7
})

# Delete tenant (with data export)
workflow.add_node("TenantDeleteNode", "delete", {
    "tenant_id": ":tenant_id",
    "pre_delete_actions": [
        "export_all_data",
        "generate_audit_report",
        "notify_data_retention"
    ],
    "retention_days": 30,  # Keep backups for 30 days
    "purge_immediately": False
})
```

## Testing Multi-Tenant Features

### Isolation Testing

```python
def test_tenant_isolation():
    """Ensure tenants cannot access each other's data."""
    # Create test tenants
    tenant_a = create_test_tenant("tenant_a")
    tenant_b = create_test_tenant("tenant_b")

    # Create data for tenant A
    with db.tenant_context(tenant_a):
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", {
            "name": "User A",
            "email": "a@test.com"
        })
        runtime = LocalRuntime()
        runtime.execute(workflow.build())

    # Try to access from tenant B
    with db.tenant_context(tenant_b):
        workflow = WorkflowBuilder()
        workflow.add_node("UserListNode", "list", {})
        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        # Should not see tenant A's data
        assert len(results["list"]["data"]) == 0
```

### Performance Testing

```python
def test_tenant_performance():
    """Test performance with multiple tenants."""
    import concurrent.futures

    # Create multiple tenants
    tenants = [create_test_tenant(f"tenant_{i}") for i in range(10)]

    def tenant_workload(tenant_id):
        with db.tenant_context(tenant_id):
            # Run typical workflow
            workflow = create_test_workflow()
            runtime = LocalRuntime()
            return runtime.execute(workflow.build())

    # Run concurrent tenant workloads
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(tenant_workload, tenant.id)
            for tenant in tenants
            for _ in range(10)  # 10 requests per tenant
        ]

        results = [f.result() for f in futures]

    # Verify isolation and performance
    verify_results(results)
```

## Best Practices

1. **Choose the Right Strategy**:
   - Database per tenant: Maximum isolation, higher cost
   - Schema per tenant: Good isolation, moderate cost
   - Row-level: Lowest cost, careful security needed

2. **Plan for Scale**: Design for 10x your expected tenant count

3. **Monitor Everything**: Track per-tenant metrics and enforce limits

4. **Test Isolation**: Regularly verify tenant isolation

5. **Automate Lifecycle**: Fully automate tenant provisioning/deletion

## Next Steps

- **Security**: [Security Guide](security.md)
- **Performance**: [Performance Guide](../production/performance.md)
- **Monitoring**: [Monitoring Guide](monitoring.md)

Multi-tenant architecture is complex but essential for SaaS applications. DataFlow provides the tools to implement it correctly and securely.

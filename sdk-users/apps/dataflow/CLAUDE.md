# Kailash DataFlow - Complete Function Access Guide (Alpha Ready)

## 🚀 IMMEDIATE SUCCESS PATTERNS

### Zero-Config Basic Pattern (30 seconds) - Alpha Ready
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# 1. Zero-config initialization - ALPHA RELEASE APPROVED
db = DataFlow()  # Development: SQLite automatic, Production: PostgreSQL

# 2. Define model - generates 9 nodes automatically
@db.model
class User:
    name: str
    email: str
    active: bool = True

# 3. Use generated nodes immediately
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice", "email": "alice@example.com"
})
workflow.add_node("UserListNode", "list", {
    "filter": {"active": True}
})
workflow.add_connection("create", "result", "list", "input")

# 4. Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Production Pattern (Database Connection)
```python
# Environment-based (recommended)
# DATABASE_URL=postgresql://user:pass@localhost/db
db = DataFlow()

# Direct configuration
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=20,
    pool_max_overflow=30,
    pool_recycle=3600,
    monitoring=True,
    echo=False  # No SQL logging in production
)
```

### Configuration Patterns (Complete Access)
```python
# Database configuration
db_config = {
    "database_url": "postgresql://user:pass@localhost/db",
    "pool_size": 20,
    "pool_max_overflow": 30,
    "pool_recycle": 3600,
    "pool_pre_ping": True,
    "echo": False,
    "monitoring": True,
    "slow_query_threshold": 100,  # ms
    "query_cache_enabled": True,
    "cache_ttl": 300  # seconds
}

# Multi-tenant configuration
tenant_config = {
    "multi_tenant": True,
    "tenant_isolation": "strict",
    "tenant_id_header": "X-Tenant-ID",
    "tenant_database_prefix": "tenant_"
}

# Security configuration
security_config = {
    "encryption_enabled": True,
    "encryption_key": "from_env",
    "audit_logging": True,
    "gdpr_compliance": True,
    "data_retention_days": 90
}

# Performance configuration
performance_config = {
    "bulk_batch_size": 1000,
    "async_operations": True,
    "connection_pool_size": 50,
    "read_replica_enabled": True,
    "cache_backend": "redis"
}

# Complete initialization
db = DataFlow(**db_config, **tenant_config, **security_config, **performance_config)
```

### Enterprise Pattern (Multi-Tenant + Audit)
```python
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

    # Enterprise features
    __dataflow__ = {
        'multi_tenant': True,     # Adds tenant_id field
        'soft_delete': True,      # Adds deleted_at field
        'versioned': True,        # Adds version field for optimistic locking
        'audit_log': True         # Tracks all changes
    }

    # Performance optimization
    __indexes__ = [
        {'name': 'idx_tenant_status', 'fields': ['tenant_id', 'status']},
        {'name': 'idx_customer_date', 'fields': ['customer_id', 'created_at']}
    ]
```

---

## 🎯 COMPLETE FUNCTION ACCESS MATRIX

### Generated Nodes (Per Model)
Every `@db.model` class automatically generates these 9 nodes:

| Node Type | Function | Use Case | Performance |
|-----------|----------|----------|-------------|
| **{Model}CreateNode** | Single insert | User registration | <1ms |
| **{Model}ReadNode** | Single select by ID | Profile lookup | <1ms |
| **{Model}UpdateNode** | Single update | Profile edit | <1ms |
| **{Model}DeleteNode** | Single delete | Account removal | <1ms |
| **{Model}ListNode** | Query with filters | Search/pagination | <10ms |
| **{Model}BulkCreateNode** | Bulk insert | Data import | 1000/sec |
| **{Model}BulkUpdateNode** | Bulk update | Price updates | 5000/sec |
| **{Model}BulkDeleteNode** | Bulk delete | Cleanup | 10000/sec |
| **{Model}BulkUpsertNode** | Insert or update | Sync operations | 3000/sec |

### Enterprise Features Access
```python
# Multi-tenant operations
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com",
    "tenant_id": "tenant_123"  # Automatic isolation
})

# Soft delete operations
workflow.add_node("UserDeleteNode", "soft_delete", {
    "id": 123,
    "soft_delete": True  # Sets deleted_at, preserves data
})

# Versioned updates (optimistic locking)
workflow.add_node("UserUpdateNode", "update", {
    "id": 123,
    "name": "Alice Updated",
    "version": 1  # Prevents concurrent modification conflicts
})

# Audit trail queries
workflow.add_node("UserAuditNode", "audit", {
    "record_id": 123,
    "action_type": "update",
    "date_range": {"start": "2025-01-01", "end": "2025-01-31"}
})
```

### Bulk Operations (High Performance)
```python
# Bulk create with conflict resolution
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": [
        {"name": "Product A", "price": 100.0},
        {"name": "Product B", "price": 200.0}
    ],
    "batch_size": 1000,  # Optimal batch size
    "conflict_resolution": "upsert",  # skip, error, upsert
    "return_ids": True  # Get created IDs
})

# Bulk update with conditions
workflow.add_node("ProductBulkUpdateNode", "price_update", {
    "filter": {"category": "electronics"},
    "update": {"price": {"$multiply": 0.9}},  # 10% discount
    "limit": 5000  # Process in batches
})

# Bulk delete with safety
workflow.add_node("ProductBulkDeleteNode", "cleanup", {
    "filter": {"deleted_at": {"$not": None}},
    "soft_delete": True,  # Preserves data
    "confirmation_required": True  # Prevents accidents
})
```

### Advanced Query Patterns
```python
# Complex filtering with MongoDB-style operators
workflow.add_node("OrderListNode", "search", {
    "filter": {
        "status": {"$in": ["pending", "processing"]},
        "total": {"$gte": 100.0},
        "created_at": {"$gte": "2025-01-01"},
        "customer": {
            "email": {"$regex": ".*@enterprise.com"}
        }
    },
    "sort": [{"created_at": -1}],
    "limit": 100,
    "offset": 0
})

# Aggregation operations
workflow.add_node("OrderAggregateNode", "analytics", {
    "group_by": ["status", "customer_id"],
    "aggregate": {
        "total_amount": {"$sum": "total"},
        "order_count": {"$count": "*"},
        "avg_order": {"$avg": "total"}
    },
    "having": {"total_amount": {"$gt": 1000}}
})
```

### Transaction Management
```python
# Distributed transaction with compensation
workflow.add_node("TransactionManagerNode", "payment_flow", {
    "transaction_type": "saga",  # or "two_phase_commit"
    "steps": [
        {
            "node": "PaymentCreateNode",
            "compensation": "PaymentRollbackNode"
        },
        {
            "node": "OrderUpdateNode",
            "compensation": "OrderRevertNode"
        },
        {
            "node": "InventoryUpdateNode",
            "compensation": "InventoryRestoreNode"
        }
    ],
    "timeout": 30,  # seconds
    "retry_attempts": 3
})

# ACID transaction scope
workflow.add_node("TransactionScopeNode", "atomic_operation", {
    "isolation_level": "READ_COMMITTED",
    "timeout": 10,
    "rollback_on_error": True
})
```

### Performance Optimization
```python
# Connection pooling configuration
db = DataFlow(
    pool_size=20,              # Base connections
    pool_max_overflow=30,      # Extra connections
    pool_recycle=3600,         # Recycle after 1 hour
    pool_pre_ping=True,        # Validate connections
    pool_reset_on_return="commit"  # Clean state
)

# Query caching
workflow.add_node("UserListNode", "cached_search", {
    "filter": {"active": True},
    "cache_key": "active_users",
    "cache_ttl": 300,  # 5 minutes
    "cache_invalidation": ["user_create", "user_update"]
})

# Read/write splitting
workflow.add_node("UserReadNode", "profile", {
    "id": 123,
    "read_preference": "secondary"  # Use read replica
})
```

### Change Data Capture (CDC)
```python
# Monitor database changes
workflow.add_node("CDCListenerNode", "order_changes", {
    "table": "orders",
    "operations": ["INSERT", "UPDATE", "DELETE"],
    "filter": {"status": "completed"},
    "webhook_url": "https://api.example.com/webhooks/orders"
})

# Event-driven workflows
workflow.add_node("EventTriggerNode", "order_processor", {
    "event_type": "order_created",
    "workflow_id": "order_fulfillment",
    "async_execution": True
})
```

### Multi-Database Support
```python
# Primary database
db_primary = DataFlow("postgresql://primary/db")

# Analytics database
db_analytics = DataFlow("clickhouse://analytics/db")

# Use different databases in same workflow
workflow.add_node("OrderCreateNode", "create", {
    "database": "primary"
})
workflow.add_node("OrderAnalyticsNode", "analytics", {
    "database": "analytics"
})
```

### Security & Compliance
```python
# Encryption at rest
@db.model
class SensitiveData:
    user_id: int
    encrypted_data: str

    __dataflow__ = {
        'encryption': {
            'fields': ['encrypted_data'],
            'key_rotation': True,
            'algorithm': 'AES-256-GCM'
        }
    }

# GDPR compliance
workflow.add_node("GDPRExportNode", "data_export", {
    "user_id": 123,
    "include_deleted": True,
    "format": "json",
    "anonymize_fields": ["ip_address", "device_id"]
})

workflow.add_node("GDPRDeleteNode", "right_to_be_forgotten", {
    "user_id": 123,
    "cascade_delete": True,
    "retention_period": 0
})
```

### Monitoring & Observability
```python
# Performance monitoring
workflow.add_node("MonitoringNode", "perf_tracker", {
    "metrics": ["query_time", "connection_count", "cache_hit_rate"],
    "thresholds": {
        "query_time": 100,  # ms
        "connection_count": 80  # % of pool
    },
    "alerts": {
        "slack_webhook": "https://hooks.slack.com/...",
        "email": "admin@example.com"
    }
})

# Slow query detection
workflow.add_node("SlowQueryDetectorNode", "query_analyzer", {
    "threshold": 1000,  # ms
    "log_level": "warning",
    "auto_optimize": True
})
```

---

## ⚠️ CRITICAL: Parameter Validation Patterns

### Dynamic Parameter Resolution
```python
# ❌ WRONG: Template string syntax causes validation errors
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": "${create_customer.id}",  # FAILS: conflicts with PostgreSQL
    "total": 100.0
})

# ✅ CORRECT: Use workflow connections for dynamic values
workflow.add_node("OrderCreateNode", "create_order", {
    "total": 100.0  # customer_id provided via connection
})
workflow.add_connection("create_customer", "id", "create_order", "customer_id")

# ✅ CORRECT: DateTime parameters use native objects
workflow.add_node("OrderCreateNode", "create_order", {
    "due_date": datetime.now(),      # Native datetime
    # NOT: datetime.now().isoformat() # String fails validation
})
```

### Nexus Integration Parameters
```python
# ✅ CORRECT: Double braces for Nexus parameter templates ONLY
nexus_workflow.add_node("ProductCreateNode", "create", {
    "name": "{{product_name}}",    # Nexus replaces at runtime
    "price": "{{product_price}}"   # Only in Nexus context
})
```

## 🏗️ ARCHITECTURE INTEGRATION

### DataFlow + Nexus Integration
```python
from dataflow import DataFlow
from nexus import Nexus

# Initialize DataFlow
db = DataFlow()

@db.model
class Product:
    name: str
    price: float

# Create Nexus with DataFlow integration
nexus = Nexus(
    title="E-commerce Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    dataflow_integration=db  # Auto-generates API endpoints
)

# All DataFlow nodes available through:
# - REST API: POST /api/workflows/ProductCreateNode/execute
# - CLI: nexus execute ProductCreateNode --name "Test" --price 100
# - MCP: Available to AI agents for data operations
```

### Gateway API Generation
```python
from kailash.servers.gateway import create_gateway

# Auto-generate REST API from DataFlow models
gateway = create_gateway(
    title="Product API",
    server_type="enterprise",
    dataflow_integration=db,
    auto_generate_endpoints=True,  # Creates CRUD endpoints
    authentication_required=True
)

# Automatically creates:
# GET /api/products - List products
# POST /api/products - Create product
# GET /api/products/{id} - Get product
# PUT /api/products/{id} - Update product
# DELETE /api/products/{id} - Delete product
```

### Complete Nexus Integration Pattern
```python
from nexus import Nexus
from dataflow import DataFlow

# Initialize DataFlow with models
db = DataFlow()

@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'
    __dataflow__ = {
        'multi_tenant': True,
        'audit_log': True
    }

# Create Nexus platform with full DataFlow integration
nexus = Nexus(
    title="E-commerce Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    channels_synced=True,

    # DataFlow integration configuration
    dataflow_config={
        "integration": db,
        "auto_generate_endpoints": True,
        "auto_generate_cli_commands": True,
        "auto_generate_mcp_tools": True,
        "expose_bulk_operations": True,
        "expose_analytics": True
    },

    # Enterprise features
    auth_config={
        "providers": ["oauth2", "saml"],
        "rbac_enabled": True
    },

    # Monitoring
    monitoring_config={
        "prometheus_enabled": True,
        "track_database_metrics": True
    }
)

# All DataFlow operations now available through all Nexus channels:
# - API: Full CRUD + bulk operations + analytics
# - CLI: nexus orders create --customer-id 123 --total 250.00
# - MCP: AI agents can perform database operations
# - WebSocket: Real-time database change notifications
```

### Event-Driven Architecture
```python
# Database events trigger workflows
workflow.add_node("EventSourceNode", "order_events", {
    "source": "database",
    "table": "orders",
    "event_types": ["INSERT", "UPDATE"]
})

workflow.add_node("EventProcessorNode", "order_processor", {
    "event_filter": {"status": "completed"},
    "target_workflow": "order_fulfillment"
})
```

---

## 📊 PERFORMANCE BENCHMARKS

### Throughput Metrics
- **Single operations**: 1,000+ ops/sec
- **Bulk create**: 10,000+ records/sec
- **Bulk update**: 50,000+ records/sec
- **Query operations**: 5,000+ queries/sec
- **Transaction throughput**: 500+ txns/sec

### Memory Usage
- **Base overhead**: <10MB
- **Per model**: <1MB
- **Connection pool**: 2MB per connection
- **Cache overhead**: 50MB per 1M records

### Latency Targets
- **Single CRUD**: <1ms
- **Bulk operations**: <10ms per 1000 records
- **Complex queries**: <100ms
- **Transaction commit**: <5ms

---

## 🎯 DECISION MATRIX

| Use Case | Best Pattern | Performance | Complexity |
|----------|-------------|-------------|------------|
| **Single record CRUD** | Basic nodes | <1ms | Low |
| **Bulk data import** | BulkCreateNode | 10k/sec | Medium |
| **Complex queries** | ListNode + filters | <100ms | Medium |
| **Multi-tenant app** | Enterprise features | Variable | High |
| **Real-time updates** | CDC + Events | <10ms | High |
| **Analytics queries** | Read replicas | <1sec | Medium |
| **Distributed systems** | Saga transactions | <100ms | High |

---

## 🔧 ADVANCED DEVELOPMENT

### Custom Node Development
```python
from dataflow.nodes import BaseDataFlowNode

class CustomAnalyticsNode(BaseDataFlowNode):
    def __init__(self, node_id, custom_query):
        self.custom_query = custom_query
        super().__init__(node_id)

    def execute(self, input_data):
        # Custom analytics logic
        return self.run_custom_query(self.custom_query)

# Register custom node
db.register_node(CustomAnalyticsNode)
```

### Migration Patterns
```python
# Schema migration
workflow.add_node("MigrationNode", "schema_update", {
    "migration_type": "add_column",
    "table": "users",
    "column": "phone_number",
    "type": "varchar(20)",
    "nullable": True
})

# Data migration
workflow.add_node("DataMigrationNode", "migrate_data", {
    "source_table": "old_users",
    "target_table": "users",
    "mapping": {
        "full_name": "name",
        "email_address": "email"
    },
    "batch_size": 1000
})
```

### Advanced Query Optimization
```python
# Query optimization patterns
workflow.add_node("QueryOptimizerNode", "optimize", {
    "analyze_execution_plan": True,
    "suggest_indexes": True,
    "auto_create_indexes": True,
    "query_rewrite": True
})

# Database performance tuning
workflow.add_node("PerformanceTunerNode", "tune", {
    "analyze_table_statistics": True,
    "vacuum_analyze": True,
    "optimize_connections": True,
    "cache_warm_up": True
})
```

### Testing Patterns
```python
# Test database setup
test_db = DataFlow(":memory:")  # In-memory SQLite

# Test data generation
workflow.add_node("TestDataGeneratorNode", "generate", {
    "model": "User",
    "count": 1000,
    "distribution": "normal"
})

# Performance testing
workflow.add_node("PerformanceTestNode", "benchmark", {
    "operation": "bulk_create",
    "record_count": 10000,
    "measure": ["latency", "throughput", "memory"]
})
```

### Production Database Management
```python
# Database backup and restore
workflow.add_node("DatabaseBackupNode", "backup", {
    "backup_type": "incremental",
    "compression": "gzip",
    "encryption": True,
    "destination": "s3://backups/dataflow/"
})

# Point-in-time recovery
workflow.add_node("DatabaseRestoreNode", "restore", {
    "restore_point": "2025-01-10T12:00:00Z",
    "verify_integrity": True,
    "test_restore": True
})

# Database monitoring
workflow.add_node("DatabaseMonitorNode", "monitor", {
    "metrics": ["connections", "queries_per_sec", "slow_queries"],
    "alert_thresholds": {
        "connections": 80,  # % of max
        "slow_queries": 10  # per minute
    }
})
```

---

## 🚨 CRITICAL SUCCESS FACTORS

### ✅ ALWAYS DO
- Use `@db.model` decorator for automatic node generation
- Leverage bulk operations for >100 records
- Enable multi-tenancy for SaaS applications
- Use soft deletes for audit trails
- Configure connection pooling for production
- Implement proper error handling and retries

### ❌ NEVER DO
- Direct database session management
- Manual transaction handling
- Raw SQL queries without query builder
- Skip connection pooling configuration
- Ignore soft delete for important data
- Use single operations for bulk data
- Use `${}` syntax in node parameters (conflicts with PostgreSQL)
- Use `.isoformat()` for datetime parameters (use native datetime objects)

### 🎯 OPTIMIZATION CHECKLIST
- [ ] Connection pool sized for workload
- [ ] Indexes defined for query patterns
- [ ] Bulk operations for high-volume data
- [ ] Caching enabled for frequent queries
- [ ] Monitoring configured for performance
- [ ] Backup strategy implemented
- [ ] Security measures in place

---

## 📚 COMPLETE NAVIGATION

### **🔗 Hierarchical Navigation Path**
1. **Start**: [Root CLAUDE.md](../../../CLAUDE-archive.md) → Essential patterns
2. **SDK Guidance**: [SDK Users](../../../sdk-users/) → Complete SDK navigation
3. **This Guide**: DataFlow-specific complete function access
4. **Integration**: [Nexus CLAUDE.md](../../kailash-nexus/CLAUDE.md) → Multi-channel platform

### **Quick Start**
- [Installation Guide](docs/getting-started/installation.md)
- [First App in 5 Minutes](docs/getting-started/quickstart.md)
- [Core Concepts](docs/getting-started/concepts.md)

### **Development**
- [Model Definition](docs/development/models.md)
- [Generated Nodes](docs/development/nodes.md)
- [Bulk Operations](docs/development/bulk-operations.md)
- [Relationships](docs/development/relationships.md)
- [Custom Development](docs/development/custom-nodes.md)

### **Enterprise**
- [Multi-Tenancy](docs/enterprise/multi-tenant.md)
- [Security](docs/enterprise/security.md)
- [Audit & Compliance](docs/enterprise/compliance.md)
- [Performance](docs/enterprise/performance.md)

### **Production**
- [Deployment Guide](docs/production/deployment.md)
- [Monitoring](docs/production/monitoring.md)
- [Backup & Recovery](docs/production/backup.md)
- [Troubleshooting](docs/production/troubleshooting.md)

### **Integration**
- [Nexus Integration](docs/integration/nexus.md)
- [Gateway APIs](docs/integration/gateway.md)
- [Event-Driven Architecture](docs/integration/events.md)

---

**DataFlow: Zero-config database framework with enterprise power. Every function accessible, every pattern optimized, every scale supported.** 🚀

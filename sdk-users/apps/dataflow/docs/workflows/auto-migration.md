# DataFlow Auto-Migration System

**Revolutionary database schema management with visual confirmation and zero-downtime migrations.**

## 🎯 Overview

DataFlow's auto-migration system automatically detects schema changes when you modify your models and provides intelligent migration paths with visual confirmation, safety analysis, and rollback capabilities.

### Key Features

- **Visual Migration Preview**: See exactly what changes will be applied before execution
- **Interactive Confirmation**: Review and approve migrations with detailed explanations
- **PostgreSQL Optimized**: Advanced ALTER syntax, JSONB metadata, and performance optimizations
- **Automatic Rollback Analysis**: Intelligent safety assessment for every migration
- **Schema Comparison Engine**: Precise diff generation between model definitions and database state
- **Concurrent Access Protection**: Migration locking and queue management for multi-process environments
- **Production Safety**: Dry-run mode, data loss prevention, and transaction rollback
- **Existing Database Protection**: Safe mode prevents destructive migrations (Bug 006 fix)
- **Migration History Tracking**: Checksum-based duplicate prevention (Bug 006 fix)

## 🚀 Quick Start

### Basic Auto-Migration Pattern

```python
from dataflow import DataFlow

db = DataFlow()

# Define your initial model
@db.model
class User:
    name: str
    email: str
    created_at: datetime = None

# Initialize database (creates tables)
await db.initialize()

# Later, evolve your model by adding fields
@db.model
class User:
    name: str
    email: str
    phone: str = None        # NEW FIELD - triggers auto-migration
    is_active: bool = True   # NEW FIELD - triggers auto-migration
    created_at: datetime = None
    updated_at: datetime = None  # NEW FIELD - triggers auto-migration

# Auto-migration detects changes and provides visual confirmation
await db.auto_migrate()  # Interactive preview + confirmation
```

### ⚠️ Working with Existing Databases (Bug 006 Fix)

```python
# CRITICAL: For existing databases, use safe mode to prevent destructive migrations
db = DataFlow(
    database_url="postgresql://...",
    auto_migrate=False,  # Disable automatic migrations
    existing_schema_mode=True  # Enable safe mode for existing databases
)

# Manually trigger migrations with safety checks
success, migrations = await db.auto_migrate(
    dry_run=True,  # Preview first
    max_risk_level="LOW",  # Extra cautious
    data_loss_protection=True
)
```

### Visual Migration Preview

When you run `auto_migrate()`, you'll see:

```
🔄 DataFlow Auto-Migration Preview

Schema Changes Detected:
┌─────────────────┬──────────────────┬────────────────┬──────────────┐
│ Table           │ Operation        │ Details        │ Safety Level │
├─────────────────┼──────────────────┼────────────────┼──────────────┤
│ user            │ ADD_COLUMN       │ phone (TEXT)   │ ✅ SAFE      │
│ user            │ ADD_COLUMN       │ is_active      │ ✅ SAFE      │
│                 │                  │ (BOOLEAN)      │              │
│ user            │ ADD_COLUMN       │ updated_at     │ ✅ SAFE      │
│                 │                  │ (TIMESTAMP)    │              │
└─────────────────┴──────────────────┴────────────────┴──────────────┘

Generated SQL:
  ALTER TABLE user ADD COLUMN phone TEXT NULL;
  ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT true;
  ALTER TABLE user ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

✅ Migration Safety Assessment:
  • All operations are backward compatible
  • No data loss risk detected
  • Estimated execution time: <100ms
  • Rollback plan: Available (3 steps)

Apply these changes? [y/N]: y
```

## 📋 Migration Modes

### Interactive Mode (Default)

```python
# Interactive with visual confirmation
success, migrations = await db.auto_migrate()
# Shows preview table, asks for confirmation

# Interactive with detailed analysis
success, migrations = await db.auto_migrate(
    interactive=True,
    show_sql=True,          # Display generated SQL
    show_rollback_plan=True, # Show rollback steps
    safety_analysis=True    # Show detailed safety assessment
)
```

### Dry-Run Mode (Preview Only)

```python
# Preview changes without applying
success, migrations = await db.auto_migrate(dry_run=True)

print("Detected migrations:")
for migration in migrations:
    print(f"  - {migration.description}")
    print(f"    Safety: {migration.safety_level}")
    print(f"    SQL: {migration.sql_up}")
```

### Auto-Confirm Mode (Production)

```python
# Automatic application for CI/CD
success, migrations = await db.auto_migrate(
    auto_confirm=True,      # Skip interactive confirmation
    safety_check=True,      # Still perform safety analysis
    max_risk_level="MEDIUM" # Reject HIGH risk migrations
)

if not success:
    print("Migration failed safety checks")
    # Handle failure
```

### Selective Migration

```python
# Apply specific migrations only
success, migrations = await db.auto_migrate(
    include_tables=["user", "order"],  # Only these tables
    exclude_operations=["DROP_COLUMN"] # Skip dangerous operations
)
```

## 🔧 Advanced Configuration

### Migration System Configuration

```python
from dataflow.migrations import AutoMigrationSystem

# Custom migration system configuration
migration_config = {
    "dialect": "postgresql",           # Database-specific optimizations
    "interactive": True,               # Enable interactive mode
    "safety_checks": True,             # Perform safety analysis
    "max_risk_level": "MEDIUM",        # Reject HIGH risk migrations
    "backup_before_migration": True,   # Auto-backup before changes
    "rollback_on_error": True,         # Auto-rollback on failure
    "concurrent_access_protection": True, # Enable migration locking
    "migration_timeout": 300,          # 5 minute timeout
    "batch_size": 1000,                # For bulk operations
}

db = DataFlow(migration_config=migration_config)
```

### PostgreSQL-Specific Features

```python
@db.model
class Product:
    name: str
    specs: dict         # Becomes JSONB in PostgreSQL
    tags: list          # Becomes JSONB array in PostgreSQL
    price: Decimal      # Becomes DECIMAL(10,2) with precision
    location: str       # Can use PostGIS types if enabled

    __dataflow__ = {
        'postgresql': {
            'jsonb_gin_indexes': ['specs', 'tags'],  # Auto-create GIN indexes
            'text_search': ['name'],                 # Full-text search indexes
            'partial_indexes': [                     # Conditional indexes
                {
                    'fields': ['price'],
                    'condition': 'price > 0'
                }
            ]
        }
    }
```

## 🛡️ Safety & Risk Management

### Safety Levels

The auto-migration system classifies every operation by risk level:

#### ✅ SAFE Operations
- Add nullable columns
- Add columns with default values
- Create new tables
- Create indexes
- Add constraints (non-breaking)

```python
# Example SAFE migrations
@db.model
class User:
    name: str
    email: str
    phone: str = None           # SAFE: nullable column
    is_active: bool = True      # SAFE: has default value
    created_at: datetime = None # SAFE: nullable timestamp
```

#### ⚠️ MEDIUM Risk Operations
- Modify column types (compatible changes)
- Add NOT NULL columns to populated tables
- Drop indexes
- Rename tables/columns (with data migration)

```python
# Example MEDIUM risk migrations
@db.model
class User:
    name: str
    email: str = Field(max_length=255)  # MEDIUM: length constraint
    age: int                            # MEDIUM: NOT NULL on existing table
```

#### 🚨 HIGH Risk Operations
- Drop columns (data loss)
- Drop tables (data loss)
- Incompatible type changes
- Drop constraints with dependencies

```python
# HIGH risk operations require explicit confirmation
@db.model
class User:
    name: str
    # email field removed - HIGH RISK: data loss
    new_email: str  # Requires manual data migration
```

### Risk Mitigation Strategies

```python
# Configure safety thresholds
await db.auto_migrate(
    max_risk_level="MEDIUM",        # Reject HIGH risk operations
    require_confirmation=True,       # Always ask for HIGH/MEDIUM risk
    data_loss_protection=True,       # Extra checks for data loss
    create_backup=True,             # Backup before risky operations
    rollback_on_failure=True        # Auto-rollback on error
)
```

## 🔄 Rollback System

### Automatic Rollback Analysis

Every migration includes a rollback plan:

```python
# View rollback plan before applying
success, migrations = await db.auto_migrate(dry_run=True)

for migration in migrations:
    print(f"Migration: {migration.description}")
    print(f"Rollback plan: {len(migration.rollback_steps)} steps")

    for step in migration.rollback_steps:
        print(f"  - {step.operation_type}: {step.sql}")
        print(f"    Risk: {step.risk_level}")
        print(f"    Duration: {step.estimated_duration_ms}ms")
```

### Manual Rollback

```python
# Rollback specific migration
migration_version = "migration_20250131_120000"
success = await db.rollback_migration(migration_version)

if success:
    print("Rollback completed successfully")
else:
    print("Rollback failed - check logs")

# Rollback to specific point in time
success = await db.rollback_to_version("migration_20250130_100000")
```

### Rollback Safety Checks

```python
# Check if rollback is possible
rollback_analysis = await db.analyze_rollback("migration_20250131_120000")

print(f"Rollback possible: {rollback_analysis.fully_reversible}")
print(f"Data loss warning: {rollback_analysis.data_loss_warning}")
print(f"Irreversible operations: {rollback_analysis.irreversible_operations}")
```

## 🏗️ Schema Evolution Patterns

### Additive Changes (Safe)

```python
# Start with basic model
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

# Evolve by adding fields (always safe)
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'
    notes: str = None              # Added: nullable field
    priority: int = 1              # Added: with default
    tags: list = None              # Added: JSONB array
    metadata: dict = None          # Added: JSONB object
    created_at: datetime = None    # Added: timestamp
```

### Backward Compatible Evolution

```python
# Step 1: Add new field alongside old
@db.model
class User:
    name: str
    email: str                     # Old field
    email_address: str = None      # New field (transitional)
    created_at: datetime = None

# Step 2: Migrate data (separate process)
# ... data migration logic ...

# Step 3: Remove old field
@db.model
class User:
    name: str
    email_address: str             # Now the primary field
    created_at: datetime = None
```

### Complex Schema Transformations

```python
# For complex changes, use explicit migration steps
from dataflow.migrations import MigrationPlan

migration_plan = MigrationPlan([
    # Step 1: Add new structure
    {
        "operation": "add_table",
        "table": "user_profiles",
        "columns": [
            {"name": "user_id", "type": "INTEGER", "references": "users.id"},
            {"name": "profile_data", "type": "JSONB"}
        ]
    },
    # Step 2: Migrate data
    {
        "operation": "migrate_data",
        "source": "users.profile_json",
        "target": "user_profiles.profile_data"
    },
    # Step 3: Clean up
    {
        "operation": "drop_column",
        "table": "users",
        "column": "profile_json"
    }
])

success = await db.apply_migration_plan(migration_plan)
```

## 🔧 Concurrent Access Protection

### Migration Locking

```python
# Automatic migration locking for multi-process environments
async with db.migration_lock("users_schema"):
    success, migrations = await db.auto_migrate()
    if success:
        print("Migration applied successfully")
```

### Queue Management

```python
# Queue migrations for high-concurrency scenarios
migration_id = await db.queue_migration({
    "target_schema": updated_schema,
    "priority": 1,  # Higher priority = processed first
    "timeout": 300  # 5 minute timeout
})

# Check queue status
status = await db.get_migration_status(migration_id)
print(f"Migration status: {status.status}")
print(f"Queue position: {status.position}")
```

## 📊 Migration Monitoring

### Performance Metrics

```python
# Enable migration monitoring
db = DataFlow(
    migration_config={
        "monitoring": True,
        "performance_tracking": True,
        "slow_migration_threshold": 5000,  # 5 seconds
    }
)

# Get migration performance data
metrics = await db.get_migration_metrics()
print(f"Average migration time: {metrics.avg_duration_ms}ms")
print(f"Success rate: {metrics.success_rate}%")
print(f"Rollback rate: {metrics.rollback_rate}%")
```

### Migration History

```python
# View migration history
history = await db.get_migration_history(limit=10)

for record in history:
    print(f"Migration: {record.name}")
    print(f"Applied: {record.applied_at}")
    print(f"Status: {record.status}")
    print(f"Operations: {len(record.operations)}")
    print("---")
```

## 🚀 Production Best Practices

### CI/CD Integration

```python
# In your deployment pipeline
import os

# Production migration script
async def deploy_migrations():
    db = DataFlow()

    # Check for pending migrations
    pending = await db.get_pending_migrations()

    if not pending:
        print("No migrations to apply")
        return True

    # Apply with production safety settings
    success, applied = await db.auto_migrate(
        auto_confirm=True,              # No interactive prompts
        max_risk_level="MEDIUM",        # Block HIGH risk operations
        backup_before_migration=True,   # Always backup
        rollback_on_error=True,         # Auto-rollback failures
        timeout=600                     # 10 minute timeout
    )

    if success:
        print(f"Applied {len(applied)} migrations successfully")
        return True
    else:
        print("Migration failed - check logs")
        return False

# Use in your deployment
if __name__ == "__main__":
    success = await deploy_migrations()
    exit(0 if success else 1)
```

### Monitoring & Alerting

```python
# Set up migration monitoring
db = DataFlow(
    migration_config={
        "monitoring": {
            "enabled": True,
            "webhook_url": "https://your-monitoring.com/webhooks/migrations",
            "alert_on_failure": True,
            "alert_on_rollback": True,
            "performance_threshold": 10000,  # Alert if >10s
        }
    }
)
```

### Blue-Green Deployments

```python
# Blue-green deployment with migrations
async def blue_green_migration():
    # Apply to staging first
    staging_db = DataFlow(database_url=STAGING_URL)
    success = await staging_db.auto_migrate(auto_confirm=True)

    if not success:
        raise Exception("Staging migration failed")

    # Run validation tests
    await run_integration_tests(staging_db)

    # Apply to production
    prod_db = DataFlow(database_url=PRODUCTION_URL)
    success = await prod_db.auto_migrate(auto_confirm=True)

    if not success:
        # Rollback staging
        await staging_db.rollback_last_migration()
        raise Exception("Production migration failed")

    return True
```

## 🔍 Troubleshooting

### Common Issues

#### Migration Conflicts
```python
# Resolve migration conflicts
try:
    success, migrations = await db.auto_migrate()
except MigrationConflictError as e:
    print(f"Conflict detected: {e.message}")
    print("Manual resolution required")

    # View conflicting changes
    conflicts = e.conflicts
    for conflict in conflicts:
        print(f"Table: {conflict.table}")
        print(f"Conflict: {conflict.description}")
        print(f"Resolution options: {conflict.resolution_options}")
```

#### Performance Issues
```python
# Debug slow migrations
migration_metrics = await db.analyze_migration_performance()

print(f"Slowest operations:")
for op in migration_metrics.slow_operations:
    print(f"  {op.operation}: {op.duration_ms}ms")
    print(f"  Suggestion: {op.optimization_suggestion}")
```

#### Data Loss Prevention
```python
# Extra safety for production
success, migrations = await db.auto_migrate(
    data_loss_protection=True,      # Block any data loss risk
    require_explicit_confirm=True,  # Require manual approval
    create_backup=True,             # Always backup first
    validate_after_migration=True   # Verify schema matches models
)
```

## 📈 Advanced Features

### Custom Migration Strategies

```python
from dataflow.migrations import MigrationStrategy

class CustomMigrationStrategy(MigrationStrategy):
    def should_apply_migration(self, migration):
        # Custom logic for migration approval
        if migration.risk_level == "HIGH":
            return self.require_manual_approval(migration)
        return True

    def optimize_migration(self, migration):
        # Custom optimization logic
        if migration.table_size > 1000000:  # Large table
            migration.batch_size = 100
            migration.use_concurrent_index_creation = True
        return migration

# Use custom strategy
db = DataFlow(migration_strategy=CustomMigrationStrategy())
```

### Integration with External Tools

```python
# Integrate with schema versioning tools
await db.auto_migrate(
    version_control=True,           # Track in git
    schema_registry_url="http://registry.example.com",
    generate_documentation=True,    # Auto-generate docs
    notify_team=True               # Send notifications
)
```

## 🎯 Migration Workflow Examples

### E-commerce Platform Evolution

```python
# Phase 1: Basic e-commerce models
@db.model
class Product:
    name: str
    price: float
    description: str = None

@db.model
class Order:
    product_id: int
    quantity: int
    total: float

# Phase 2: Add inventory management
@db.model
class Product:
    name: str
    price: float
    description: str = None
    inventory_count: int = 0        # NEW: inventory tracking
    sku: str = None                 # NEW: SKU field
    category: str = None            # NEW: categorization

@db.model
class Order:
    product_id: int
    quantity: int
    total: float
    status: str = 'pending'         # NEW: order status
    tracking_number: str = None     # NEW: shipping tracking

# Phase 3: Add advanced features
@db.model
class Product:
    name: str
    price: float
    description: str = None
    inventory_count: int = 0
    sku: str = None
    category: str = None
    specifications: dict = None      # NEW: JSONB specs
    images: list = None             # NEW: JSONB image array
    is_featured: bool = False       # NEW: featured flag

@db.model
class Order:
    product_id: int
    quantity: int
    total: float
    status: str = 'pending'
    tracking_number: str = None
    shipping_address: dict = None    # NEW: JSONB address
    billing_address: dict = None     # NEW: JSONB address
    metadata: dict = None           # NEW: flexible metadata

# Each phase triggers automatic migrations with visual confirmation
await db.auto_migrate()  # Interactive preview for each evolution
```

## 🔗 Integration with DataFlow Features

### Auto-Generated Nodes Update

When migrations are applied, DataFlow automatically updates the generated nodes:

```python
# After adding 'phone' field to User model
# These nodes are automatically updated:

workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com",
    "phone": "+1-555-0123"  # New field available
})

workflow.add_node("UserListNode", "search", {
    "filter": {
        "phone": {"$exists": True}  # New field in queries
    }
})

workflow.add_node("UserUpdateNode", "update", {
    "id": 123,
    "phone": "+1-555-9999"  # New field in updates
})
```

### Workflow Integration

```python
# Migration-aware workflows
workflow = WorkflowBuilder()

# Check if migration is needed
workflow.add_node("MigrationCheckNode", "check", {
    "models": ["User", "Order", "Product"]
})

# Apply migrations if needed
workflow.add_node("AutoMigrationNode", "migrate", {
    "auto_confirm": False,    # Require confirmation
    "safety_level": "MEDIUM"  # Safety threshold
})

# Continue with business logic
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})

# Connect migration check to business logic
workflow.add_connection("check", "migrations_needed", "migrate", "input")
workflow.add_connection("migrate", "success", "create_user", "input")
```

---

## 🎯 Next Steps

- **[Model Development](../development/models.md)**: Learn advanced model patterns
- **[Bulk Operations](../development/bulk-operations.md)**: High-performance data operations
- **[Production Deployment](../production/deployment.md)**: Production migration strategies
- **[Nexus Integration](../integration/nexus.md)**: Multi-channel platform deployment

---

**DataFlow Auto-Migration: Revolutionary schema management with visual confirmation, safety analysis, and zero-downtime deployments.** 🚀

*Transform your database evolution from manual, error-prone processes to automated, safe, and intelligent migrations.*

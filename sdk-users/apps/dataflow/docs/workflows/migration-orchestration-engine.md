# DataFlow Migration Orchestration Engine

**Central coordination system for safe database schema evolution with comprehensive migration management.**

## 🎯 Overview

The Migration Orchestration Engine is DataFlow's central system for coordinating database schema changes, providing intelligent migration planning, execution, and rollback capabilities with enterprise-grade safety controls.

### Key Components

1. **Migration Orchestration Engine** - Central coordination system
2. **Column Datatype Migration Engine** - Safe type conversions and column modifications
3. **Gold Standards Compliance** - DataFlow pattern integration and validation
4. **11 Migration Scenarios** - Comprehensive coverage of schema evolution patterns

## 🚀 Quick Start

### Basic Migration Orchestration

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# PostgreSQL connection required for DataFlow execution
db = DataFlow(database_url="postgresql://user:password@localhost:5432/mydb")

# Define initial model
@db.model
class User:
    name: str
    email: str
    created_at: datetime = None

# Evolution: Add new fields (triggers Migration Orchestration Engine)
@db.model
class User:
    name: str
    email: str
    phone: str = None        # NEW: triggers migration orchestration
    is_active: bool = True   # NEW: triggers migration orchestration
    created_at: datetime = None
    updated_at: datetime = None  # NEW: triggers migration orchestration

# Migration Orchestration Engine automatically detects changes
# and coordinates safe migration execution
```

## 🏗️ Migration Orchestration Engine Architecture

### Core Components

#### 1. Schema Diff Engine
```python
# Automatically compares current schema with model definitions
schema = db.discover_schema(use_real_inspection=True)
current_models = db.list_models()

# Migration Orchestration Engine detects differences
migrations_needed = db.detect_schema_changes()
```

#### 2. Migration Planning System
```python
# Plans migration execution order and safety analysis
migration_plan = db.create_migration_plan(
    safety_level="MEDIUM",      # Risk threshold
    batch_operations=True,      # Optimize for performance
    transaction_scope="PER_TABLE"  # Transaction boundaries
)
```

#### 3. Execution Coordinator
```python
# Coordinates migration execution across multiple models
success, results = await db.execute_migration_plan(
    migration_plan,
    dry_run=False,              # Execute migrations
    rollback_on_failure=True,   # Auto-rollback on errors
    progress_callback=lambda status: print(f"Migration: {status}")
)
```

## 📋 11 Migration Scenarios

The Migration Orchestration Engine handles all schema evolution patterns:

### SAFE Operations (Auto-Approved)

#### Scenario 1: Add Nullable Column
```python
@db.model
class Product:
    name: str
    price: float
    description: str = None  # SAFE: Nullable column
```

#### Scenario 2: Add Column with Default
```python
@db.model
class Product:
    name: str
    price: float
    active: bool = True      # SAFE: Has default value
    category: str = "general"  # SAFE: Has default value
```

#### Scenario 3: Create New Table
```python
@db.model
class Order:  # SAFE: New table creation
    customer_id: int
    total: float
    status: str = "pending"
```

#### Scenario 4: Add Database Index
```python
@db.model
class Customer:
    name: str
    email: str
    __dataflow__ = {
        'indexes': [
            {'fields': ['email'], 'unique': True},  # SAFE: Add index
        ]
    }
```

#### Scenario 5: PostgreSQL JSONB Columns
```python
@db.model
class Configuration:
    name: str
    settings: dict  # SAFE: PostgreSQL JSONB column
    metadata: list  # SAFE: PostgreSQL JSONB array
```

### MEDIUM Risk Operations (Review Required)

#### Scenario 6: Expand Column Length
```python
@db.model
class Article:
    title: str      # MEDIUM: Expanding VARCHAR length
    content: str
    summary: str = None
```

#### Scenario 7: Add NOT NULL with Default
```python
@db.model
class Settings:
    name: str
    value: str
    enabled: bool = True    # MEDIUM: NOT NULL but has default
    priority: int = 0       # MEDIUM: NOT NULL but has default
```

#### Scenario 8: Compatible Type Change
```python
@db.model
class Measurement:
    name: str
    value: float    # MEDIUM: int -> float (compatible)
```

#### Scenario 9: Add Foreign Key
```python
@db.model
class Employee:
    name: str
    department_id: int  # MEDIUM: FK constraint
    __dataflow__ = {
        'foreign_keys': [
            {'field': 'department_id', 'references': 'departments.id'}
        ]
    }
```

#### Scenario 10: Rename Column (Backward Compatible)
```python
@db.model
class Contact:
    name: str
    email_addr: str = None     # Keep old name temporarily
    email_address: str = None  # MEDIUM: New name (with data migration)
```

### HIGH Risk Operations (Manual Approval Required)

#### Scenario 11: Column Drop Simulation
```python
# HIGH RISK operations require explicit approval
# Migration Orchestration Engine blocks these by default
migration_plan = db.create_migration_plan(
    max_risk_level="HIGH",  # Allow HIGH risk operations
    require_explicit_approval=True,
    create_backup=True      # Always backup before HIGH risk
)
```

## 🔧 Column Datatype Migration Engine

### Safe Type Conversions

```python
class DataTypeMigrationEngine:
    """Handles safe column type transformations"""

    SAFE_CONVERSIONS = {
        'int -> float': 'SAFE',
        'varchar(n) -> varchar(m)': 'SAFE' if 'm > n' else 'MEDIUM',
        'text -> jsonb': 'MEDIUM',
        'varchar -> text': 'SAFE'
    }

    UNSAFE_CONVERSIONS = {
        'float -> int': 'HIGH',     # Precision loss
        'varchar(m) -> varchar(n)': 'HIGH' if 'n < m' else 'SAFE',
        'jsonb -> text': 'HIGH'     # Structure loss
    }

# Usage in migration
migration_engine = DataTypeMigrationEngine()
conversion_safety = migration_engine.assess_type_change(
    from_type='INTEGER',
    to_type='NUMERIC(10,2)',
    data_sample=existing_data
)
```

### PostgreSQL-Specific Type Migrations

```python
@db.model
class Product:
    name: str
    specs: dict         # Migrates to JSONB with GIN index
    tags: list          # Migrates to JSONB array
    price: Decimal      # Migrates to NUMERIC(10,2)

    __dataflow__ = {
        'postgresql': {
            'type_migrations': {
                'specs': {
                    'from': 'TEXT',
                    'to': 'JSONB',
                    'migration_strategy': 'parse_json'
                },
                'price': {
                    'from': 'INTEGER',
                    'to': 'NUMERIC(10,2)',
                    'migration_strategy': 'scale_precision'
                }
            }
        }
    }
```

## 🛡️ Gold Standards Compliance

### DataFlow Pattern Integration

```python
# Migration Orchestration Engine enforces DataFlow patterns
@db.model
class Order:
    customer_id: int
    total: float

    # Gold Standards Compliance automatically applied
    __dataflow__ = {
        'multi_tenant': True,      # Adds tenant_id field
        'soft_delete': True,       # Adds deleted_at field
        'audit_log': True,         # Tracks all changes
        'versioned': True          # Optimistic locking
    }

# Migration Orchestration Engine ensures:
# - All tenant_id fields are properly indexed
# - Audit triggers are created
# - Version columns have proper constraints
# - Soft delete logic is preserved
```

### Connection Pooling Integration

```python
# Migration Orchestration Engine respects connection pooling
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=20,              # Connection pool maintained during migrations
    migration_config={
        'use_dedicated_connection': True,  # Separate connection for migrations
        'pool_isolation': True,            # Isolate migration transactions
        'concurrent_access_protection': True
    }
)
```

## 🚀 Advanced Usage Patterns

### Production Migration Workflow

```python
async def production_migration_workflow():
    """Production-safe migration orchestration"""

    # Initialize with production safety settings
    db = DataFlow(
        database_url="postgresql://user:pass@prod:5432/app",
        migration_config={
            'max_risk_level': 'MEDIUM',
            'backup_before_migration': True,
            'rollback_on_error': True,
            'concurrent_access_protection': True,
            'migration_timeout': 300
        }
    )

    # Step 1: Analyze pending migrations
    pending = await db.get_pending_migrations()
    print(f"Pending migrations: {len(pending)}")

    # Step 2: Create migration plan
    plan = db.create_migration_plan(
        migrations=pending,
        optimize_for='SAFETY',  # vs 'SPEED'
        batch_operations=True
    )

    # Step 3: Dry run validation
    dry_run_result = await db.execute_migration_plan(
        plan, dry_run=True
    )

    if not dry_run_result.success:
        raise Exception(f"Dry run failed: {dry_run_result.errors}")

    # Step 4: Execute with monitoring
    result = await db.execute_migration_plan(
        plan,
        progress_callback=lambda status: log_migration_progress(status),
        rollback_on_failure=True
    )

    return result
```

### Multi-Environment Migration Sync

```python
async def sync_migrations_across_environments():
    """Synchronize migrations across dev/staging/prod"""

    environments = {
        'dev': DataFlow(database_url=DEV_DB_URL),
        'staging': DataFlow(database_url=STAGING_DB_URL),
        'prod': DataFlow(database_url=PROD_DB_URL)
    }

    # Generate migration plan from development
    dev_db = environments['dev']
    migration_plan = dev_db.create_migration_plan()

    # Apply to staging first
    staging_result = await environments['staging'].execute_migration_plan(
        migration_plan, auto_confirm=True
    )

    if staging_result.success:
        # Run validation tests on staging
        await run_integration_tests(environments['staging'])

        # Apply to production
        prod_result = await environments['prod'].execute_migration_plan(
            migration_plan,
            max_risk_level='MEDIUM',
            backup_before_migration=True
        )

        return prod_result

    return staging_result
```

### Custom Migration Strategies

```python
from dataflow.migrations import MigrationStrategy

class ZeroDowntimeMigrationStrategy(MigrationStrategy):
    """Custom strategy for zero-downtime migrations"""

    def plan_migration(self, changes):
        """Plan migration with zero-downtime approach"""
        plan = []

        for change in changes:
            if change.operation == 'RENAME_COLUMN':
                # Zero-downtime column rename
                plan.extend([
                    {'operation': 'ADD_COLUMN', 'new_name': change.new_name},
                    {'operation': 'COPY_DATA', 'from': change.old_name, 'to': change.new_name},
                    {'operation': 'UPDATE_APPLICATION'}, # Deploy app changes
                    {'operation': 'DROP_COLUMN', 'name': change.old_name}
                ])
            else:
                plan.append(change)

        return plan

    def should_batch_operations(self, operations):
        """Determine if operations can be batched"""
        # Don't batch operations that might lock tables
        return not any(op.operation in ['ADD_INDEX', 'DROP_COLUMN']
                      for op in operations)

# Use custom strategy
db = DataFlow(
    database_url="postgresql://...",
    migration_strategy=ZeroDowntimeMigrationStrategy()
)
```

## 📊 Migration Monitoring & Metrics

### Performance Tracking

```python
# Enable migration performance monitoring
db = DataFlow(
    database_url="postgresql://...",
    migration_config={
        'monitoring': {
            'enabled': True,
            'track_performance': True,
            'slow_migration_threshold': 5000,  # 5 seconds
            'webhook_url': 'https://monitoring.example.com/migrations'
        }
    }
)

# Get migration metrics
metrics = await db.get_migration_metrics()
print(f"Average migration time: {metrics.avg_duration_ms}ms")
print(f"Success rate: {metrics.success_rate}%")
print(f"Rollback rate: {metrics.rollback_rate}%")
```

### Migration History & Audit

```python
# View complete migration history
history = await db.get_migration_history(
    limit=50,
    filter_by_status='COMPLETED',
    include_rollbacks=True
)

for migration in history:
    print(f"Migration: {migration.name}")
    print(f"Applied: {migration.applied_at}")
    print(f"Duration: {migration.duration_ms}ms")
    print(f"Risk Level: {migration.risk_level}")
    print(f"Operations: {len(migration.operations)}")
    print("---")
```

## 🔗 DataFlow Integration

### Workflow Integration

```python
# Migration-aware workflows
workflow = WorkflowBuilder()

# Check migration status
workflow.add_node("MigrationStatusNode", "check_migrations", {
    "models": ["User", "Order", "Product"],
    "auto_apply": False
})

# Apply migrations if needed
workflow.add_node("MigrationOrchestrationNode", "apply_migrations", {
    "max_risk_level": "MEDIUM",
    "backup_before_migration": True,
    "rollback_on_failure": True
})

# Continue with business logic after migrations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})

# Connect migration check to business logic
workflow.add_connection("check_migrations", "status", "apply_migrations", "input")
workflow.add_connection("apply_migrations", "success", "create_user", "input")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🎯 Best Practices

### 1. Migration Safety
- Always use PostgreSQL for DataFlow execution
- Set appropriate `max_risk_level` for your environment
- Enable `backup_before_migration` for production
- Use `dry_run=True` to validate migrations first

### 2. Performance Optimization
- Batch compatible operations together
- Use dedicated migration connections for large changes
- Monitor migration performance with tracking enabled
- Schedule large migrations during maintenance windows

### 3. Team Collaboration
- Use migration plan files for code review
- Document custom migration strategies
- Set up migration monitoring and alerting
- Test migrations in staging environments first

### 4. Error Recovery
- Always enable `rollback_on_failure`
- Test rollback procedures regularly
- Keep migration history for audit purposes
- Monitor for incomplete migrations

---

## 🎯 Next Steps

- **[Auto-Migration System](auto-migration.md)**: Interactive migration workflows
- **[Production Deployment](../production/deployment.md)**: Production migration strategies
- **[Database Optimization](../advanced/database-optimization.md)**: Performance tuning
- **[Multi-Tenant Architecture](../advanced/multi-tenant.md)**: Enterprise patterns

---

**DataFlow Migration Orchestration Engine: Enterprise-grade database schema evolution with comprehensive safety controls and intelligent automation.** 🚀

*Transform your database migrations from manual, error-prone processes to automated, safe, and intelligent schema evolution.*

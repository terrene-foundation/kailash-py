---
name: dataflow-migrations-quick
description: "DataFlow automatic migrations and schema changes. Use when DataFlow migration, auto_migrate, schema changes, add column, or migration basics."
---

# DataFlow Migrations Quick Start

Automatic schema migrations with safety controls for development and production.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-models`](#), [`dataflow-existing-database`](#)
> Related Subagents: `dataflow-specialist` (complex migrations, production safety)

> **DataFlow v0.10.15 Update**: `auto_migrate=True` now works correctly in Docker/FastAPI environments using `SyncDDLExecutor` (psycopg2/sqlite3 for synchronous DDL). The previous workaround of using `auto_migrate=False` + `create_tables_async()` is **OBSOLETE**.
>
> **Note**: `existing_schema_mode` and `enable_model_persistence` parameters still exist for specific use cases but are rarely needed. The simple `auto_migrate=True` (default) handles most scenarios.

## Quick Reference

- **Development**: `auto_migrate=True` (default) - safe, preserves data
- **Docker/FastAPI**: `auto_migrate=True` - works correctly as of v0.10.15+
- **Production**: `auto_migrate=True` - same pattern for all environments
- **Enterprise**: Full migration system with risk assessment for complex operations
- **Safety**: auto_migrate ALWAYS preserves existing data, adds new columns safely

## Core Pattern

```python
from dataflow import DataFlow

# Development - automatic migrations
db_dev = DataFlow(
    database_url="sqlite:///dev.db",
    auto_migrate=True  # Default - safe for development
)

@db_dev.model
class User:
    name: str
    email: str

# Add field later - auto-migrates safely
@db_dev.model
class User:
    name: str
    email: str
    age: int = 0  # New field with default - safe migration
```

## Migration Modes

### Development Mode (auto_migrate=True)

```python
db = DataFlow(auto_migrate=True)

@db.model
class Product:
    name: str
    price: float

# Later: Add field - auto-migrates
@db.model
class Product:
    name: str
    price: float
    category: str = "general"  # New field added automatically
```

**Safety**: Verified - no data loss on repeat runs

### Production Mode (v0.10.15+)

```python
# Same configuration works for all environments
db = DataFlow(
    database_url="postgresql://...",
    auto_migrate=True  # Safe - preserves data, adds columns automatically
)

# For complex migrations (type changes, renames), use Enterprise Mode
```

### Enterprise Mode

```python
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine
from dataflow.migrations.not_null_handler import NotNullColumnHandler

# Assess risk before changes
risk_engine = RiskAssessmentEngine(connection_manager)
assessment = await risk_engine.assess_operation_risk(
    operation_type="add_not_null_column",
    table_name="users",
    column_name="status"
)

# Execute with safety checks
handler = NotNullColumnHandler(connection_manager)
plan = await handler.plan_not_null_addition("users", column_def)
result = await handler.execute_not_null_addition(plan)
```

## Common Migrations

### Add Nullable Column

```python
@db.model
class User:
    name: str
    email: str
    phone: str = None  # Nullable - safe to add
```

### Add NOT NULL Column

```python
@db.model
class User:
    name: str
    email: str
    status: str = "active"  # Default required for NOT NULL
```

### Remove Column

```python
# Use Column Removal Manager
from dataflow.migrations.column_removal_manager import ColumnRemovalManager

remover = ColumnRemovalManager(connection_manager)
removal_plan = await remover.plan_column_removal("users", "old_field")
result = await remover.execute_column_removal(removal_plan)
```

## Common Mistakes

### Mistake 1: No Default for NOT NULL

```python
# WRONG - No default for required field
@db.model
class User:
    name: str
    email: str
    status: str  # No default - migration fails!
```

**Fix: Provide Default**

```python
@db.model
class User:
    name: str
    email: str
    status: str = "active"  # Default for existing rows
```

### Mistake 2: Using Obsolete Workaround Pattern

```python
# OBSOLETE - This workaround was needed before v0.10.15
# Now auto_migrate=True works in Docker/FastAPI!
db_prod = DataFlow(
    database_url="postgresql://prod/db",
    auto_migrate=False,  # No longer needed!
)
# ... then manually calling create_tables_async() in FastAPI lifespan
```

**Fix: Use Simple Configuration (v0.10.15)**

```python
# CORRECT - auto_migrate=True now works in Docker/FastAPI
db_prod = DataFlow(
    database_url="postgresql://prod/db",
    auto_migrate=True  # Default - safe: preserves data, adds new columns only
)
# SyncDDLExecutor handles table creation synchronously (no event loop issues)
```

## Related Patterns

- **For models**: See [`dataflow-models`](#)
- **For existing databases**: See [`dataflow-existing-database`](#)

## Documentation References

### Primary Sources
- **NOT NULL Handler**: [`sdk-users/apps/dataflow/docs/development/not-null-column-addition.md`](../../../../sdk-users/apps/dataflow/docs/development/not-null-column-addition.md)
- **Column Removal**: [`sdk-users/apps/dataflow/docs/development/column-removal-system.md`](../../../../sdk-users/apps/dataflow/docs/development/column-removal-system.md)
- **Auto Migration**: [`sdk-users/apps/dataflow/docs/workflows/auto-migration.md`](../../../../sdk-users/apps/dataflow/docs/workflows/auto-migration.md)

### Related Documentation
- **DataFlow CLAUDE**: [`sdk-users/apps/dataflow/CLAUDE.md`](../../../../sdk-users/apps/dataflow/CLAUDE.md#L316-L360)
- **Migration Orchestration**: [`sdk-users/apps/dataflow/docs/workflows/migration-orchestration-engine.md`](../../../../sdk-users/apps/dataflow/docs/workflows/migration-orchestration-engine.md)

## Quick Tips

- `auto_migrate=True` is safe for ALL environments (v0.10.15+)
- Works correctly in Docker/FastAPI via `SyncDDLExecutor`
- Always provide defaults for NOT NULL columns
- Enterprise migration system for complex operations (type changes, renames)
- Test migrations on staging before production
- No more need for `create_tables_async()` workaround

## Keywords for Auto-Trigger

<!-- Trigger Keywords: DataFlow migration, auto_migrate, schema changes, add column, migration basics, schema migration, database migration, alter table, migration safety -->

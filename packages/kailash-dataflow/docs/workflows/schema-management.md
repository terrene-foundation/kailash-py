# DataFlow Schema Management

Comprehensive guide to managing database schema changes in DataFlow workflows.

## Overview

DataFlow provides specialized nodes for managing database schema modifications and migrations. These nodes enable you to perform schema changes as part of your workflows, ensuring consistency and traceability.

## Schema Modification Node

The `SchemaModificationNode` allows you to perform various schema operations on your database tables.

### Basic Usage

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Add a new column to an existing table
workflow.add_node("SchemaModificationNode", "add_column", {
    "table": "orders",
    "operation": "add_column",
    "column_name": "notes",
    "column_type": "text",
    "nullable": True
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Supported Operations

#### Add Column

```python
workflow.add_node("SchemaModificationNode", "add_field", {
    "table": "users",
    "operation": "add_column",
    "column_name": "phone_number",
    "column_type": "varchar(20)",
    "nullable": True
})
```

#### Drop Column

```python
workflow.add_node("SchemaModificationNode", "remove_field", {
    "table": "users",
    "operation": "drop_column",
    "column_name": "deprecated_field"
})
```

### Advanced Schema Modifications

```python
# Add column with default value
workflow.add_node("SchemaModificationNode", "add_status", {
    "table": "orders",
    "operation": "add_column",
    "column_name": "processing_status",
    "column_type": "varchar(50)",
    "nullable": False,
    "default_value": "pending"
})

# Add column with constraints
workflow.add_node("SchemaModificationNode", "add_email", {
    "table": "contacts",
    "operation": "add_column",
    "column_name": "email",
    "column_type": "varchar(255)",
    "nullable": False,
    "unique": True
})
```

## Migration Management

The `MigrationNode` helps track and manage database migrations, ensuring that schema changes are applied in a controlled manner.

### Basic Migration Tracking

```python
workflow = WorkflowBuilder()

# Track a new migration
workflow.add_node("MigrationNode", "track_migration", {
    "migration_name": "add_user_phone_number",
    "status": "pending"
})

# Apply schema change
workflow.add_node("SchemaModificationNode", "apply_change", {
    "table": "users",
    "operation": "add_column",
    "column_name": "phone_number",
    "column_type": "varchar(20)",
    "nullable": True
})

# Update migration status
workflow.add_node("MigrationNode", "complete_migration", {
    "migration_name": "add_user_phone_number",
    "status": "completed"
})

# Connect nodes
workflow.add_connection("track_migration", "apply_change")
workflow.add_connection("apply_change", "complete_migration")
```

### Migration Workflow Pattern

```python
# Complete migration workflow
workflow = WorkflowBuilder()

# 1. Check if migration already applied
workflow.add_node("MigrationNode", "check_migration", {
    "migration_name": "user_table_v2",
    "action": "check_status"
})

# 2. Conditional execution based on migration status
workflow.add_node("SwitchNode", "migration_decision", {
    "input": ":migration_status",
    "cases": {
        "pending": "apply_migration",
        "completed": "skip_migration"
    }
})

# 3. Apply migration
workflow.add_node("SchemaModificationNode", "apply_migration", {
    "table": "users",
    "operation": "add_column",
    "column_name": "last_login",
    "column_type": "timestamp",
    "nullable": True
})

# 4. Update migration record
workflow.add_node("MigrationNode", "update_status", {
    "migration_name": "user_table_v2",
    "status": "completed"
})

# 5. Skip node for already applied migrations
workflow.add_node("PythonCodeNode", "skip_migration", {
    "code": "result = {'message': 'Migration already applied'}"
})

# Connect workflow
workflow.add_connection("check_migration", "migration_decision", "status")
workflow.add_connection("migration_decision", "apply_migration")
workflow.add_connection("migration_decision", "skip_migration")
workflow.add_connection("apply_migration", "update_status")
```

## Schema Evolution Patterns

### Backward Compatible Changes

```python
# Safe schema changes that don't break existing code
workflow = WorkflowBuilder()

# Add nullable column - safe
workflow.add_node("SchemaModificationNode", "add_optional_field", {
    "table": "products",
    "operation": "add_column",
    "column_name": "description",
    "column_type": "text",
    "nullable": True
})

# Add column with default - safe
workflow.add_node("SchemaModificationNode", "add_with_default", {
    "table": "products",
    "operation": "add_column",
    "column_name": "is_active",
    "column_type": "boolean",
    "nullable": False,
    "default_value": True
})
```

### Complex Schema Changes

```python
# Rename column (requires data migration)
workflow = WorkflowBuilder()

# 1. Add new column
workflow.add_node("SchemaModificationNode", "add_new_column", {
    "table": "users",
    "operation": "add_column",
    "column_name": "email_address",
    "column_type": "varchar(255)",
    "nullable": True
})

# 2. Copy data from old to new column
workflow.add_node("DataMigrationNode", "copy_data", {
    "source_table": "users",
    "target_table": "users",
    "field_mapping": {
        "email": "email_address"
    }
})

# 3. Drop old column
workflow.add_node("SchemaModificationNode", "drop_old_column", {
    "table": "users",
    "operation": "drop_column",
    "column_name": "email"
})

# Connect in sequence
workflow.add_connection("add_new_column", "copy_data")
workflow.add_connection("copy_data", "drop_old_column")
```

## Integration with DataFlow Models

When using DataFlow's model system, schema changes should be coordinated with model updates:

```python
from dataflow import DataFlow

db = DataFlow()

# Original model
@db.model
class User:
    name: str
    email: str

# After schema modification, update model
@db.model
class User:
    name: str
    email: str
    phone_number: Optional[str] = None  # Added field
```

## Best Practices

### 1. Always Use Migrations

```python
# Good: Track all schema changes
workflow.add_node("MigrationNode", "track", {
    "migration_name": "add_user_preferences",
    "status": "pending"
})
workflow.add_node("SchemaModificationNode", "modify", {...})
workflow.add_node("MigrationNode", "complete", {
    "migration_name": "add_user_preferences",
    "status": "completed"
})

# Bad: Direct schema modification without tracking
# workflow.add_node("SchemaModificationNode", "modify", {...})
```

### 2. Test Migrations

```python
# Test migration in transaction
workflow.add_node("TransactionScopeNode", "test_migration", {
    "rollback_on_error": True
})

workflow.add_node("SchemaModificationNode", "test_change", {
    "table": "test_users",
    "operation": "add_column",
    "column_name": "test_field",
    "column_type": "varchar(50)"
})

# Verify migration worked
workflow.add_node("ValidationNode", "verify", {
    "check_column_exists": True,
    "table": "test_users",
    "column": "test_field"
})
```

### 3. Version Your Schema

```python
# Track schema versions
workflow.add_node("MigrationNode", "version_schema", {
    "migration_name": "schema_v2.1.0",
    "status": "pending",
    "metadata": {
        "version": "2.1.0",
        "description": "Add user preferences table",
        "breaking_change": False
    }
})
```

### 4. Handle Rollbacks

```python
# Reversible migration pattern
workflow.add_node("MigrationNode", "check_rollback", {
    "migration_name": "add_preferences",
    "action": "check_rollback_needed"
})

workflow.add_node("SwitchNode", "rollback_decision", {
    "input": ":needs_rollback",
    "cases": {
        "true": "rollback_migration",
        "false": "proceed_migration"
    }
})

# Rollback path
workflow.add_node("SchemaModificationNode", "rollback_migration", {
    "table": "users",
    "operation": "drop_column",
    "column_name": "preferences"
})

# Forward path
workflow.add_node("SchemaModificationNode", "proceed_migration", {
    "table": "users",
    "operation": "add_column",
    "column_name": "preferences",
    "column_type": "jsonb"
})
```

## Production Considerations

### Zero-Downtime Migrations

```python
# Phase 1: Add new structure
workflow.add_node("SchemaModificationNode", "phase1_add", {
    "table": "orders",
    "operation": "add_column",
    "column_name": "total_amount",
    "column_type": "decimal(10,2)",
    "nullable": True
})

# Phase 2: Backfill data
workflow.add_node("DataBackfillNode", "phase2_backfill", {
    "table": "orders",
    "update_field": "total_amount",
    "calculation": "subtotal + tax + shipping",
    "batch_size": 1000
})

# Phase 3: Add constraints after backfill
workflow.add_node("SchemaModificationNode", "phase3_constraint", {
    "table": "orders",
    "operation": "add_constraint",
    "constraint_type": "not_null",
    "column_name": "total_amount"
})
```

### Monitor Migration Impact

```python
workflow.add_node("MonitoringNode", "pre_migration_metrics", {
    "capture_metrics": ["query_performance", "table_size", "index_usage"]
})

workflow.add_node("SchemaModificationNode", "perform_migration", {...})

workflow.add_node("MonitoringNode", "post_migration_metrics", {
    "capture_metrics": ["query_performance", "table_size", "index_usage"],
    "compare_with": "pre_migration_metrics",
    "alert_on_degradation": True
})
```

## Next Steps

- **Transaction Management**: [Transaction Guide](transactions.md)
- **Data Migration**: [Data Migration Patterns](../advanced/data-migration.md)
- **Performance**: [Schema Optimization](../production/performance.md)

Proper schema management is crucial for maintaining database integrity and supporting application evolution. Always test migrations thoroughly and have a rollback plan.

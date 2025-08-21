# DataFlow Column Removal System

**Safe column removal with dependency analysis, transaction safety, and comprehensive rollback capabilities.**

## ⚠️ IMPORTANT: Context-Aware Operations (v0.4.0+)

DataFlow's column removal system now includes context-aware table creation and string ID preservation:

- **String IDs preserved**: No forced integer conversion during column operations
- **Multi-instance isolation**: Each DataFlow instance maintains separate context
- **Deferred schema operations**: Table modifications are deferred until workflow execution

```python
# String ID models work seamlessly with column removal
@db.model
class User:
    id: str  # Preserved throughout column operations
    name: str
    # deprecated_field: str  # Safe to remove
```

## Overview

The DataFlow Column Removal System provides enterprise-grade column removal functionality with:

- **Dependency Analysis**: Comprehensive detection of all column dependencies
- **Multi-Stage Removal**: Correct ordering of dependency removal operations
- **Transaction Safety**: Savepoint-based rollback with ACID compliance
- **Data Preservation**: Configurable backup strategies before removal
- **Risk Assessment**: Safety validation with blocking dependency detection

## Architecture

### Core Components

```
ColumnRemovalManager
├── DependencyAnalyzer       # Phase 1: Dependency detection
├── BackupHandlers          # Data preservation strategies
├── RemovalStageExecutors   # Multi-stage removal process
└── TransactionManager      # Savepoint-based safety
```

### Integration Points

- **DependencyAnalyzer**: Reuses existing dependency analysis engine
- **MigrationConnectionManager**: Leverages connection pooling and retry logic
- **AutoMigrationSystem**: Integrates with existing migration workflows

## Usage Patterns

### Basic Column Removal

```python
from dataflow.migrations.column_removal_manager import (
    ColumnRemovalManager, BackupStrategy
)

# Initialize manager
removal_manager = ColumnRemovalManager(connection_manager)

# Plan removal
plan = await removal_manager.plan_column_removal(
    table="users",
    column="temp_field",
    backup_strategy=BackupStrategy.COLUMN_ONLY
)

# Validate safety
validation = await removal_manager.validate_removal_safety(plan)
if not validation.is_safe:
    print(f"Blocking dependencies: {len(validation.blocking_dependencies)}")
    return

# Execute removal
result = await removal_manager.execute_safe_removal(plan)
print(f"Removal completed: {result.result.value}")
```

### Advanced Removal with Custom Configuration

```python
# Custom removal plan
plan = await removal_manager.plan_column_removal(
    table="orders",
    column="legacy_status",
    backup_strategy=BackupStrategy.TABLE_SNAPSHOT,
    dry_run=False  # Set to True for testing
)

# Configure safety settings
plan.confirmation_required = True
plan.stop_on_warning = True
plan.validate_after_each_stage = True
plan.stage_timeout = 600  # 10 minutes per stage

# Execute with full monitoring
result = await removal_manager.execute_safe_removal(plan)

# Check results
if result.result == RemovalResult.SUCCESS:
    print(f"Removed column in {result.execution_time:.2f}s")
    print(f"Backup preserved: {result.backup_preserved}")
else:
    print(f"Removal failed: {result.error_message}")
    print("Recovery instructions:")
    for instruction in result.recovery_instructions:
        print(f"  - {instruction}")
```

## Safety Features

### Risk Assessment

The system provides comprehensive risk assessment:

```python
validation = await removal_manager.validate_removal_safety(plan)

print(f"Risk Level: {validation.risk_level.value}")
print(f"Is Safe: {validation.is_safe}")
print(f"Requires Confirmation: {validation.requires_confirmation}")

# Review blocking dependencies
for dep in validation.blocking_dependencies:
    print(f"CRITICAL: {dep.object_name} ({dep.dependency_type.value})")

# Review warnings and recommendations
for warning in validation.warnings:
    print(f"WARNING: {warning}")

for rec in validation.recommendations:
    print(f"RECOMMENDATION: {rec}")
```

### Backup Strategies

#### Column-Only Backup
```python
# Backs up just the column data with primary keys
plan.backup_strategy = BackupStrategy.COLUMN_ONLY

# Creates: users__email_backup_<timestamp>
# Contains: id, email (where email IS NOT NULL)
```

#### Table Snapshot Backup
```python
# Backs up the entire table state
plan.backup_strategy = BackupStrategy.TABLE_SNAPSHOT

# Creates: users_backup_<timestamp>
# Contains: Complete table copy for full restoration
```

#### No Backup (Risky)
```python
# Skip backup creation (not recommended for production)
plan.backup_strategy = BackupStrategy.NONE
```

### Transaction Safety

The system uses PostgreSQL savepoints for transaction safety:

```python
# Automatic savepoint management
async with connection.transaction():
    savepoint = f"column_removal_{timestamp}"
    await connection.execute(f"SAVEPOINT {savepoint}")

    try:
        # Execute removal stages
        await execute_removal_stages(plan)
        await connection.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception:
        # Automatic rollback to savepoint
        await connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        raise
```

## Removal Process

### Stage Execution Order

The system enforces correct dependency removal ordering:

1. **Backup Creation**: Data preservation before any changes
2. **Dependent Objects**: Remove triggers, views, functions
3. **Constraint Removal**: Drop FK constraints, check constraints
4. **Index Removal**: Remove single and composite indexes
5. **Column Removal**: Drop the actual column
6. **Cleanup**: Clean up temporary resources
7. **Validation**: Verify removal completed successfully

### Stage Details

#### 1. Backup Creation
```sql
-- Column-only backup with primary key
CREATE TABLE users__email_backup_1640995200 AS
SELECT id, email FROM users WHERE email IS NOT NULL;

-- Table snapshot backup
CREATE TABLE users_backup_1640995200 AS
SELECT * FROM users;
```

#### 2. Dependent Objects Removal
```sql
-- Drop triggers that reference the column
DROP TRIGGER IF EXISTS email_validation_trigger ON users;

-- Drop views that reference the column (CASCADE)
DROP VIEW IF EXISTS user_contacts_view CASCADE;

-- Functions are typically warned about, not dropped
-- (Manual review recommended)
```

#### 3. Constraint Removal
```sql
-- Drop foreign key constraints
ALTER TABLE user_profiles
DROP CONSTRAINT IF EXISTS fk_user_profiles_user_email;

-- Drop check constraints
ALTER TABLE users
DROP CONSTRAINT IF EXISTS chk_email_format;
```

#### 4. Index Removal
```sql
-- Drop single-column indexes
DROP INDEX IF EXISTS idx_users_email;

-- Drop composite indexes (with performance warning)
DROP INDEX IF EXISTS idx_users_email_status;
```

#### 5. Column Removal
```sql
-- The actual column drop
ALTER TABLE users DROP COLUMN IF EXISTS email;
```

## Error Handling

### Automatic Rollback

The system provides automatic rollback on any failure:

```python
result = await removal_manager.execute_safe_removal(plan)

if result.rollback_executed:
    print("Removal failed - all changes rolled back")
    print(f"Error: {result.error_message}")

    # Review what stages completed
    for stage_result in result.stages_completed:
        status = "SUCCESS" if stage_result.success else "FAILED"
        print(f"{stage_result.stage.value}: {status}")
```

### Recovery Instructions

```python
if result.result != RemovalResult.SUCCESS:
    print("Recovery Instructions:")
    for instruction in result.recovery_instructions:
        print(f"  • {instruction}")

    if result.manual_cleanup_required:
        print("Manual Cleanup Required:")
        for cleanup in result.manual_cleanup_required:
            print(f"  • {cleanup}")
```

### Dry Run Testing

```python
# Test removal without making changes
plan.dry_run = True
result = await removal_manager.execute_safe_removal(plan)

print(f"Dry run completed in {result.execution_time:.2f}s")
print(f"Would affect {len(result.stages_completed)} stages")

# All changes automatically rolled back
```

## Dependency Analysis Integration

The removal system leverages the comprehensive dependency analysis engine:

```python
# Dependencies are automatically detected
dependencies = plan.dependencies

# Review each dependency
for dep in dependencies:
    print(f"{dep.object_name} ({dep.dependency_type.value})")
    print(f"  Risk Level: {dep.risk_level.value}")

    if dep.details:
        for key, value in dep.details.items():
            print(f"  {key}: {value}")
```

### Dependency Types Handled

- **Foreign Keys**: Both incoming (CRITICAL) and outgoing (HIGH)
- **Indexes**: Single-column (LOW) and composite (MEDIUM)
- **Check Constraints**: Column-specific validation (LOW-MEDIUM)
- **Triggers**: INSERT/UPDATE/DELETE events (MEDIUM)
- **Views**: Dependent views dropped with CASCADE (HIGH)
- **Functions**: Manual review warnings (MEDIUM)

## Production Usage

### Safety Checklist

Before production column removal:

1. ✅ **Validate Safety**: Ensure `validation.is_safe == True`
2. ✅ **Review Dependencies**: Check all blocking dependencies
3. ✅ **Test with Dry Run**: Verify stages execute correctly
4. ✅ **Backup Strategy**: Choose appropriate backup approach
5. ✅ **Maintenance Window**: Schedule during low-traffic period
6. ✅ **Monitoring**: Have database monitoring ready
7. ✅ **Recovery Plan**: Understand rollback and recovery options

### Performance Considerations

```python
# Configure timeouts for large tables
plan.stage_timeout = 1800  # 30 minutes for large operations
plan.batch_size = 50000   # Adjust for table size

# Monitor execution time
estimated = validation.estimated_duration
print(f"Estimated duration: {estimated:.1f} seconds")
```

### Error Monitoring

```python
# Monitor removal progress
result = await removal_manager.execute_safe_removal(plan)

# Log detailed stage information
for stage_result in result.stages_completed:
    logger.info(f"Stage {stage_result.stage.value}: {stage_result.duration:.2f}s")

    if stage_result.warnings:
        for warning in stage_result.warnings:
            logger.warning(f"Stage warning: {warning}")

    if stage_result.errors:
        for error in stage_result.errors:
            logger.error(f"Stage error: {error}")
```

## Limitations and Considerations

### Current Limitations

1. **PostgreSQL Only**: Currently designed for PostgreSQL databases
2. **Single Column**: Handles one column at a time (not multi-column)
3. **Function Dependencies**: Requires manual review/update
4. **Complex Views**: May need manual recreation after removal
5. **Partitioned Tables**: Special handling may be required

### Best Practices

1. **Test First**: Always use dry run in development
2. **Off-Peak Hours**: Schedule during maintenance windows
3. **Monitor Dependencies**: Review all dependencies before removal
4. **Backup Verification**: Verify backups before proceeding
5. **Rollback Plan**: Have manual rollback procedures ready

### Future Enhancements

- **Multi-Column Removal**: Handle multiple columns atomically
- **MySQL Support**: Extend to MySQL databases
- **Function Analysis**: Parse function code for column references
- **Partition Support**: Handle partitioned table constraints
- **Incremental Rollback**: Partial rollback to specific stages

## Integration Examples

### With DataFlow Migration System

```python
from dataflow.migration.auto_migration_system import AutoMigrationSystem
from dataflow.migrations.column_removal_manager import ColumnRemovalManager

async def safe_column_removal_migration():
    """Example integration with DataFlow migration system."""

    # Initialize managers
    migration_system = AutoMigrationSystem(dataflow_instance)
    removal_manager = ColumnRemovalManager(migration_system.connection_manager)

    # Plan removal
    plan = await removal_manager.plan_column_removal("users", "legacy_field")

    # Validate safety
    validation = await removal_manager.validate_removal_safety(plan)
    if not validation.is_safe:
        raise Exception(f"Unsafe removal: {validation.blocking_dependencies}")

    # Execute within migration transaction
    async with migration_system.get_migration_transaction() as tx:
        result = await removal_manager.execute_safe_removal(plan, tx.connection)

        if result.result != RemovalResult.SUCCESS:
            raise Exception(f"Removal failed: {result.error_message}")

        return result
```

### With Nexus Platform

```python
from nexus.cli.commands import NexusCommand
from dataflow.migrations.column_removal_manager import ColumnRemovalManager

class RemoveColumnCommand(NexusCommand):
    """Nexus CLI command for safe column removal."""

    async def execute(self, table: str, column: str, confirm: bool = False):
        removal_manager = ColumnRemovalManager(self.connection_manager)

        # Plan and validate
        plan = await removal_manager.plan_column_removal(table, column)
        validation = await removal_manager.validate_removal_safety(plan)

        # Display safety information
        self.console.print(f"Risk Level: {validation.risk_level.value}")

        if validation.blocking_dependencies:
            self.console.print("[red]CRITICAL Dependencies Found:[/red]")
            for dep in validation.blocking_dependencies:
                self.console.print(f"  • {dep.object_name} ({dep.dependency_type.value})")
            return

        # Require confirmation for risky operations
        if validation.requires_confirmation and not confirm:
            self.console.print("Use --confirm to proceed with this removal")
            return

        # Execute removal
        result = await removal_manager.execute_safe_removal(plan)

        if result.result == RemovalResult.SUCCESS:
            self.console.print(f"[green]✓[/green] Column removed successfully in {result.execution_time:.2f}s")
        else:
            self.console.print(f"[red]✗[/red] Removal failed: {result.error_message}")
```

This comprehensive column removal system provides enterprise-grade safety and functionality for DataFlow applications requiring reliable database schema evolution capabilities.

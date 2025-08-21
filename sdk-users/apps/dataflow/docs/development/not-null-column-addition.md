# NOT NULL Column Addition Workflow

**Complete guide to safely adding NOT NULL columns to populated tables in DataFlow**

This guide covers the comprehensive workflow for adding NOT NULL columns to tables that already contain data, using DataFlow's advanced migration system with multiple default value strategies, constraint validation, and performance optimization.

## ⚠️ IMPORTANT: String ID Preservation (v0.4.0+)

DataFlow now preserves string IDs throughout all migration operations. No special handling is needed for models with string primary keys:

```python
# Models with string IDs work seamlessly in migrations
@db.model
class User:
    id: str  # String IDs preserved during migrations
    name: str
    # Adding NOT NULL column to this table now works correctly
```

## Overview

Adding NOT NULL columns to populated tables is one of the most critical and risky migration operations in database management. DataFlow provides a sophisticated system that:

- **Supports 6 default value strategies** for different scenarios
- **Validates all constraints** before execution (foreign keys, check constraints, unique constraints, triggers)
- **Provides performance estimation** and batching for large tables
- **Includes rollback capabilities** for safe operations
- **Monitors execution** with comprehensive logging and metrics

## Quick Start

```python
from dataflow.migrations.not_null_handler import (
    NotNullColumnHandler, ColumnDefinition, DefaultValueType
)

# Initialize with your connection manager
handler = NotNullColumnHandler(connection_manager)

# Define the column to add
column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# Plan, validate, and execute
plan = await handler.plan_not_null_addition("users", column)
validation = await handler.validate_addition_safety(plan)

if validation.is_safe:
    result = await handler.execute_not_null_addition(plan)
    print(f"Addition completed: {result.result}")
else:
    print(f"Validation failed: {validation.issues}")
```

## Default Value Strategies

### 1. Static Default Values

**Best for:** Simple, constant values that apply to all rows.

```python
# Basic static string default
column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# Static integer default
priority_column = ColumnDefinition(
    name="priority",
    data_type="INTEGER",
    default_value=1,
    default_type=DefaultValueType.STATIC
)

# Static boolean default
active_column = ColumnDefinition(
    name="is_active",
    data_type="BOOLEAN",
    default_value=True,
    default_type=DefaultValueType.STATIC
)
```

**Performance:** Fastest option, single DDL operation.
**Use when:** Default value is the same for all rows.

### 2. Function-Based Defaults

**Best for:** System-generated values like timestamps, UUIDs.

```python
# Current timestamp
timestamp_column = ColumnDefinition(
    name="updated_at",
    data_type="TIMESTAMP",
    default_expression="CURRENT_TIMESTAMP",
    default_type=DefaultValueType.FUNCTION
)

# UUID generation
uuid_column = ColumnDefinition(
    name="uuid",
    data_type="UUID",
    default_expression="gen_random_uuid()",
    default_type=DefaultValueType.FUNCTION
)
```

**Performance:** Very fast, single DDL operation.
**Use when:** Need system-generated values.

### 3. Computed Defaults

**Best for:** Values calculated from existing column data.

```python
# Conditional logic based on existing data
computed_column = ColumnDefinition(
    name="user_tier",
    data_type="VARCHAR(10)",
    default_expression="CASE WHEN account_value > 10000 THEN 'premium' ELSE 'standard' END",
    default_type=DefaultValueType.COMPUTED
)

# Complex calculations
score_column = ColumnDefinition(
    name="score",
    data_type="INTEGER",
    default_expression="(views * 2) + (likes * 5) + (shares * 10)",
    default_type=DefaultValueType.COMPUTED
)
```

**Performance:** Slower, requires batched updates and table scan.
**Use when:** Default value depends on existing row data.

### 4. Conditional Defaults

**Best for:** Multiple conditions with different outcomes.

```python
from dataflow.migrations.default_strategies import DefaultValueStrategyManager

manager = DefaultValueStrategyManager()

# Multiple conditions
conditions = [
    ("age < 18", "minor"),
    ("age < 65", "adult"),
    ("age >= 65", "senior")
]

conditional_strategy = manager.conditional_default(conditions)

column = ColumnDefinition(
    name="age_group",
    data_type="VARCHAR(10)",
    default_type=DefaultValueType.CONDITIONAL
)
# Set conditional_rules attribute for the column
column.conditional_rules = conditions
```

**Performance:** Moderate, batched execution required.
**Use when:** Multiple business rules determine the default value.

### 5. Sequence Defaults

**Best for:** Unique integer values, especially for ID columns.

```python
# First create the sequence
await connection.execute("CREATE SEQUENCE user_number_seq")

sequence_column = ColumnDefinition(
    name="user_number",
    data_type="INTEGER",
    default_type=DefaultValueType.SEQUENCE
)
# Set sequence_name attribute
column.sequence_name = "user_number_seq"
```

**Performance:** Fast, single DDL operation.
**Use when:** Need unique sequential integers.

### 6. Foreign Key Defaults

**Best for:** Columns that reference other tables.

```python
# Static foreign key reference
fk_column = ColumnDefinition(
    name="category_id",
    data_type="INTEGER",
    default_value=1,  # ID that exists in categories table
    default_type=DefaultValueType.FOREIGN_KEY,
    foreign_key_reference="categories.id"
)

# Dynamic foreign key lookup
dynamic_fk_column = ColumnDefinition(
    name="default_category_id",
    data_type="INTEGER",
    default_type=DefaultValueType.FOREIGN_KEY,
    foreign_key_reference="categories.id"
)
# Set lookup condition
dynamic_fk_column.fk_lookup_condition = "name = 'default'"
```

**Performance:** Static FK is fast; dynamic lookup requires batching.
**Use when:** Column references another table.

## Strategy Selection Helper

The `DefaultValueStrategyManager` can recommend the optimal strategy:

```python
from dataflow.migrations.default_strategies import DefaultValueStrategyManager

manager = DefaultValueStrategyManager()

# For unique integer columns
column = ColumnDefinition("user_id", "INTEGER", unique=True)
table_info = {"row_count": 50000}

strategy_type, reason = manager.recommend_strategy(column, table_info)
# Returns: (DefaultValueType.SEQUENCE, "Unique integers best handled with sequences")

# For timestamp columns
timestamp_col = ColumnDefinition("created_at", "TIMESTAMP")
strategy_type, reason = manager.recommend_strategy(timestamp_col, table_info)
# Returns: (DefaultValueType.FUNCTION, "CURRENT_TIMESTAMP is optimal for timestamp columns")
```

## Constraint Validation

DataFlow validates all database constraints before executing migrations:

```python
from dataflow.migrations.constraint_validator import ConstraintValidator

validator = ConstraintValidator(connection_manager)

# Comprehensive constraint validation
validation = await validator.validate_all_constraints(
    table_name="users",
    column=column_definition,
    default_value="test_value"
)

if not validation.is_safe:
    print("Constraint Issues:")
    for issue in validation.issues:
        print(f"  - {issue}")

    print("Warnings:")
    for warning in validation.warnings:
        print(f"  - {warning}")
```

### Foreign Key Validation

```python
# Validate that default value exists in referenced table
from dataflow.migrations.constraint_validator import ForeignKeyConstraint

fk_constraint = ForeignKeyConstraint(
    name="users_category_fk",
    source_columns=["category_id"],
    target_table="categories",
    target_columns=["id"]
)

# Check if default value 1 exists in categories.id
is_valid = await validator.validate_foreign_key_references(
    default_value=1,
    fk_constraint=fk_constraint,
    connection=connection
)
```

### Check Constraint Validation

```python
# Validate against existing check constraints
check_constraints = await validator._get_all_constraints_info(
    "users", connection
)["check_constraints"]

# Validates that default value satisfies all check constraints
is_valid = await validator.validate_check_constraints(
    default_value=25,
    check_constraints=check_constraints,
    connection=connection
)
```

## Performance Considerations

### Small Tables (< 1,000 rows)
```python
# Use static defaults - fastest option
column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# Execution time: < 100ms
```

### Medium Tables (1,000 - 100,000 rows)
```python
# Static and function defaults still work well
# Computed defaults may require batching

plan = await handler.plan_not_null_addition(table_name, column)
print(f"Estimated execution time: {plan.estimated_duration:.2f} seconds")
print(f"Execution strategy: {plan.execution_strategy}")
```

### Large Tables (> 100,000 rows)
```python
# Use batching for computed defaults
computed_column = ColumnDefinition(
    name="category",
    data_type="VARCHAR(20)",
    default_expression="CASE WHEN amount > 1000 THEN 'premium' ELSE 'standard' END",
    default_type=DefaultValueType.COMPUTED
)

plan = await handler.plan_not_null_addition(large_table, computed_column)

# Plan will automatically set:
# - execution_strategy = "batched_update"
# - batch_size = 10000 (or optimized size)
# - timeout_seconds = appropriate for data volume
```

### Performance Monitoring

```python
# Execute with performance monitoring
import time

start_time = time.time()
result = await handler.execute_not_null_addition(plan)
execution_time = time.time() - start_time

print(f"Planned duration: {plan.estimated_duration:.2f}s")
print(f"Actual duration: {execution_time:.2f}s")
print(f"Performance ratio: {execution_time / plan.estimated_duration:.2f}x")

if result.performance_metrics:
    print(f"Rows processed: {result.affected_rows}")
    print(f"Batch count: {result.performance_metrics.get('batch_count', 'N/A')}")
```

## Error Handling and Rollback

### Automatic Rollback on Failure

```python
try:
    result = await handler.execute_not_null_addition(plan)

    if result.result == AdditionResult.SUCCESS:
        print("Column added successfully")
    else:
        print(f"Addition failed: {result.error_message}")
        if result.rollback_executed:
            print("Automatic rollback completed")

except Exception as e:
    print(f"Unexpected error: {e}")
    # Manual rollback if needed
    rollback_result = await handler.rollback_not_null_addition(plan)
    print(f"Manual rollback: {rollback_result.result}")
```

### Manual Rollback

```python
# Add column
result = await handler.execute_not_null_addition(plan)

# Later, if rollback is needed
rollback_result = await handler.rollback_not_null_addition(plan)

if rollback_result.rollback_executed:
    print("Column removed successfully")
else:
    print(f"Rollback failed: {rollback_result.error_message}")
```

### Validation Before Execution

```python
# Always validate before executing
validation = await handler.validate_addition_safety(plan)

if not validation.is_safe:
    print("Migration is not safe to execute:")
    for issue in validation.issues:
        print(f"  ISSUE: {issue}")
    return

if validation.warnings:
    print("Migration has warnings:")
    for warning in validation.warnings:
        print(f"  WARNING: {warning}")

    # Decide whether to proceed
    user_input = input("Proceed anyway? (y/N): ")
    if user_input.lower() != 'y':
        return

# Safe to execute
result = await handler.execute_not_null_addition(plan)
```

## Best Practices

### 1. Always Plan First
```python
# GOOD: Plan first to understand impact
plan = await handler.plan_not_null_addition(table_name, column)
print(f"Will affect {plan.affected_rows} rows")
print(f"Estimated time: {plan.estimated_duration:.1f} seconds")

# Then validate
validation = await handler.validate_addition_safety(plan)
```

### 2. Validate Constraints
```python
# GOOD: Comprehensive constraint validation
validator = ConstraintValidator(connection_manager)
constraint_validation = await validator.validate_all_constraints(
    table_name, column, default_value
)

# Check both safety validation AND constraint validation
overall_safe = (
    validation.is_safe and
    constraint_validation.is_safe
)
```

### 3. Use Appropriate Strategies
```python
# GOOD: Use static defaults for simple cases
status_column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# GOOD: Use functions for system values
created_column = ColumnDefinition(
    name="created_at",
    data_type="TIMESTAMP",
    default_expression="CURRENT_TIMESTAMP",
    default_type=DefaultValueType.FUNCTION
)

# BAD: Don't use computed defaults for simple static values
# This is inefficient for large tables
bad_column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_expression="'active'",  # Should use STATIC instead
    default_type=DefaultValueType.COMPUTED
)
```

### 4. Test with Small Data First
```python
# GOOD: Test the logic with small sample first
test_table = "users_test_small"

# Create test table with 100 rows
await connection.execute(f"""
    CREATE TABLE {test_table} AS
    SELECT * FROM users LIMIT 100
""")

# Test the migration
test_result = await handler.execute_not_null_addition(test_table, column)

if test_result.result == AdditionResult.SUCCESS:
    # Now safe to run on full table
    prod_result = await handler.execute_not_null_addition("users", column)
```

### 5. Monitor Large Operations
```python
# GOOD: Monitor long-running operations
if plan.estimated_duration > 30:  # More than 30 seconds
    print("Long operation detected - monitoring enabled")
    plan.performance_monitoring = True

    result = await handler.execute_not_null_addition(plan)

    if result.performance_metrics:
        print(f"Batches processed: {result.performance_metrics['batch_count']}")
        print(f"Average batch time: {result.performance_metrics['avg_batch_time']:.2f}s")
```

## Troubleshooting

### Common Issues

**Issue: "Column already exists"**
```python
# Solution: Check existing schema first
existing_columns = await connection.fetch("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = $1
""", table_name)

column_names = [row['column_name'] for row in existing_columns]
if column.name in column_names:
    print(f"Column {column.name} already exists")
    # Either choose different name or handle appropriately
```

**Issue: "Foreign key reference invalid"**
```python
# Solution: Validate foreign key references
if column.foreign_key_reference:
    ref_table, ref_column = column.foreign_key_reference.split('.')

    # Check if referenced value exists
    exists = await connection.fetchval(f"""
        SELECT EXISTS(SELECT 1 FROM {ref_table} WHERE {ref_column} = $1)
    """, column.default_value)

    if not exists:
        print(f"Referenced value {column.default_value} does not exist in {ref_table}.{ref_column}")
```

**Issue: "Check constraint violation"**
```python
# Solution: Test default value against constraints
# Get existing check constraints
constraints = await connection.fetch("""
    SELECT constraint_name, check_clause
    FROM information_schema.check_constraints cc
    JOIN information_schema.table_constraints tc ON cc.constraint_name = tc.constraint_name
    WHERE tc.table_name = $1
""", table_name)

for constraint in constraints:
    print(f"Constraint: {constraint['constraint_name']}")
    print(f"Condition: {constraint['check_clause']}")
    # Manually verify default value satisfies constraint
```

**Issue: "Performance timeout"**
```python
# Solution: Adjust batch size or timeout
plan.batch_size = 5000  # Smaller batches
plan.timeout_seconds = 1800  # 30 minutes

# Or split into smaller operations
if plan.affected_rows > 1000000:
    print("Very large table - consider manual chunking")
    # Implement custom chunking logic
```

### Performance Debugging

```python
# Enable detailed logging
import logging
logging.getLogger('dataflow.migrations').setLevel(logging.DEBUG)

# Check execution plan details
print(f"Table: {plan.table_name}")
print(f"Strategy: {plan.execution_strategy}")
print(f"Batch size: {plan.batch_size}")
print(f"Estimated time: {plan.estimated_duration:.2f}s")
print(f"Row count: {plan.affected_rows}")

# Profile actual execution
result = await handler.execute_not_null_addition(plan)
print(f"Actual time: {result.execution_time:.2f}s")
print(f"Rows affected: {result.affected_rows}")
```

## Complete Example

Here's a complete example showing the full workflow:

```python
import asyncio
from dataflow.migrations.not_null_handler import (
    NotNullColumnHandler, ColumnDefinition, DefaultValueType, AdditionResult
)
from dataflow.migrations.constraint_validator import ConstraintValidator

async def add_user_status_column(connection_manager, table_name):
    """Complete example of adding a status column to users table."""

    # Step 1: Initialize components
    handler = NotNullColumnHandler(connection_manager)
    validator = ConstraintValidator(connection_manager)

    # Step 2: Define the column
    column = ColumnDefinition(
        name="account_status",
        data_type="VARCHAR(20)",
        default_value="active",
        default_type=DefaultValueType.STATIC,
        check_constraints=["account_status IN ('active', 'inactive', 'suspended')"]
    )

    try:
        # Step 3: Plan the addition
        print("Planning NOT NULL column addition...")
        plan = await handler.plan_not_null_addition(table_name, column)

        print(f"Execution plan:")
        print(f"  Strategy: {plan.execution_strategy}")
        print(f"  Affected rows: {plan.affected_rows}")
        print(f"  Estimated time: {plan.estimated_duration:.2f} seconds")
        print(f"  Batch size: {plan.batch_size}")

        # Step 4: Validate constraints
        print("Validating constraints...")
        constraint_validation = await validator.validate_all_constraints(
            table_name, column, "active"
        )

        if not constraint_validation.is_safe:
            print("Constraint validation failed:")
            for issue in constraint_validation.issues:
                print(f"  - {issue}")
            return False

        if constraint_validation.warnings:
            print("Constraint warnings:")
            for warning in constraint_validation.warnings:
                print(f"  - {warning}")

        # Step 5: Validate safety
        print("Validating migration safety...")
        safety_validation = await handler.validate_addition_safety(plan)

        if not safety_validation.is_safe:
            print("Safety validation failed:")
            for issue in safety_validation.issues:
                print(f"  - {issue}")
            return False

        if safety_validation.warnings:
            print("Safety warnings:")
            for warning in safety_validation.warnings:
                print(f"  - {warning}")

        # Step 6: Execute the addition
        print("Executing NOT NULL column addition...")
        result = await handler.execute_not_null_addition(plan)

        if result.result == AdditionResult.SUCCESS:
            print(f"SUCCESS: Column added in {result.execution_time:.2f} seconds")
            print(f"  Rows affected: {result.affected_rows}")
            return True
        else:
            print(f"FAILED: {result.error_message}")
            if result.rollback_executed:
                print("  Automatic rollback completed")
            return False

    except Exception as e:
        print(f"ERROR: {e}")

        # Attempt rollback
        try:
            rollback_result = await handler.rollback_not_null_addition(plan)
            if rollback_result.rollback_executed:
                print("Emergency rollback completed")
        except:
            print("Emergency rollback failed - manual intervention may be required")

        return False

# Usage
async def main():
    # Your connection manager setup
    connection_manager = YourConnectionManager(database_url)

    success = await add_user_status_column(connection_manager, "users")

    if success:
        print("Migration completed successfully")
    else:
        print("Migration failed")

# Run the migration
asyncio.run(main())
```

## Related Documentation

- [DataFlow Models](models.md) - Model definition and generation
- [Query Patterns](query-patterns.md) - Working with generated nodes
- [Bulk Operations](bulk-operations.md) - High-performance data operations
- [Schema Management](../workflows/schema-management.md) - Schema evolution workflows
- [Migration Orchestration](../workflows/migration-orchestration-engine.md) - Advanced migration patterns

## Summary

DataFlow's NOT NULL column addition system provides:

- **6 flexible default value strategies** for different business requirements
- **Comprehensive constraint validation** to prevent data integrity issues
- **Performance optimization** with automatic batching for large tables
- **Safe execution** with rollback capabilities and extensive validation
- **Monitoring and logging** for production operations

Always plan, validate, and test your migrations before running them on production data. Use appropriate strategies for your specific use case and table size.

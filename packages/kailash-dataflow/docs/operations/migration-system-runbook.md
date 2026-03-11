# DataFlow Migration System Operations Runbook

## Table of Contents
1. [System Overview](#system-overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Migration Execution Procedures](#migration-execution-procedures)
4. [Performance Baseline Operations](#performance-baseline-operations)
5. [Staging Environment Management](#staging-environment-management)
6. [Risk Assessment and Mitigation](#risk-assessment-and-mitigation)
7. [Rollback Procedures](#rollback-procedures)
8. [Monitoring and Alerting](#monitoring-and-alerting)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Emergency Procedures](#emergency-procedures)

## System Overview

The DataFlow Migration System provides comprehensive database schema evolution capabilities with built-in safety mechanisms, performance validation, and rollback support.

### Key Components

- **Dependency Analyzer** (TODO-137): Analyzes column and table dependencies
- **Foreign Key Analyzer** (TODO-138): Manages FK constraints during migrations
- **Table Rename Analyzer** (TODO-139): Coordinates table rename operations
- **Risk Assessment Engine** (TODO-140): Evaluates migration risk levels
- **Staging Environment Manager** (TODO-141): Creates isolated test environments
- **Concurrent Access Manager** (TODO-142): Handles migration locking and concurrency
- **Performance Baseline System** (TODO-33): Measures and validates performance

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Migration Pipeline                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  1. Dependency Analysis  ──>  2. Risk Assessment         │
│           │                           │                  │
│           ▼                           ▼                  │
│  3. Staging Creation     ──>  4. Performance Baseline    │
│           │                           │                  │
│           ▼                           ▼                  │
│  5. Migration Execution  ──>  6. Validation & Rollback   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Pre-Migration Checklist

### 1. Database Health Check

```python
# Check database connection
from dataflow import DataFlow

db = DataFlow(
    "postgresql://user:password@localhost:5432/production",
    auto_migrate=False,
    existing_schema_mode=True
)

# Verify connection
async def health_check():
    conn = await db._get_async_database_connection()
    result = await conn.fetchrow("SELECT version()")
    print(f"Database version: {result}")
    await conn.close()
```

### 2. Backup Verification

- [ ] Full database backup completed
- [ ] Backup integrity verified
- [ ] Recovery time objective (RTO) confirmed
- [ ] Recovery point objective (RPO) confirmed

### 3. Resource Availability

```bash
# Check disk space
df -h /var/lib/postgresql

# Check memory
free -h

# Check active connections
psql -c "SELECT count(*) FROM pg_stat_activity;"
```

### 4. Migration Lock Status

```python
from dataflow.migrations.concurrent_access_manager import MigrationLockManager

lock_manager = MigrationLockManager(connection_manager)
status = await lock_manager.check_lock_status("public")
print(f"Lock status: {status.is_locked}")
```

## Migration Execution Procedures

### Standard Migration Process

#### Step 1: Dependency Analysis

```python
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer

analyzer = DependencyAnalyzer(connection_manager)

# Analyze column dependencies
report = await analyzer.analyze_column_dependencies(
    "customers",
    "legacy_status"
)

print(f"Total dependencies: {report.get_total_dependency_count()}")
print(f"Critical dependencies: {len(report.get_critical_dependencies())}")
```

#### Step 2: Risk Assessment

```python
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine

risk_engine = RiskAssessmentEngine()

# Create operation context
operation = {
    "table": "customers",
    "operation_type": "drop_column",
    "is_production": True,
    "has_backup": True
}

risk_assessment = risk_engine.calculate_migration_risk_score(
    operation,
    dependency_report
)

print(f"Risk level: {risk_assessment.risk_level.value}")
print(f"Overall score: {risk_assessment.overall_score}")
```

#### Step 3: Create Staging Environment

```python
from dataflow.migrations.staging_environment_manager import (
    StagingEnvironmentManager,
    StagingEnvironmentConfig,
    ProductionDatabase
)

config = StagingEnvironmentConfig(
    default_data_sample_size=0.1,  # 10% data sample
    max_staging_environments=2,
    performance_baselines_enabled=True
)

manager = StagingEnvironmentManager(config)

prod_db = ProductionDatabase(
    host="localhost",
    port=5432,
    database="production",
    user="prod_user",
    password="prod_password"
)

staging_env = await manager.create_staging_environment(
    prod_db,
    data_sample_size=0.1
)

print(f"Staging created: {staging_env.staging_id}")
```

#### Step 4: Performance Baseline

```python
# Measure production baselines
prod_baselines = await manager.measure_performance_baselines(
    staging_env.staging_id,
    tables_filter=["customers", "orders"],
    query_types=["SELECT", "UPDATE"]
)

# Validate staging performance
validation = await manager.validate_staging_performance(
    staging_env.staging_id,
    prod_baselines
)

if validation.validation_status == "DEGRADATION_DETECTED":
    print("WARNING: Performance degradation detected")
    for rec in validation.recommendations:
        print(f"  - {rec}")
```

#### Step 5: Execute Migration

```python
from dataflow.migrations.concurrent_access_manager import (
    MigrationLockManager,
    AtomicMigrationExecutor,
    MigrationOperation
)

# Acquire migration lock
lock_manager = MigrationLockManager(connection_manager)
async with lock_manager.migration_lock("public", timeout=30):

    # Define migration operations
    operations = [
        MigrationOperation(
            type="DROP_COLUMN",
            table_name="customers",
            sql="ALTER TABLE customers DROP COLUMN legacy_status",
            rollback_sql="ALTER TABLE customers ADD COLUMN legacy_status VARCHAR(20)"
        )
    ]

    # Execute atomically
    executor = AtomicMigrationExecutor(connection_manager)
    result = await executor.execute_atomic_migration(operations)

    if result.success:
        print(f"Migration completed in {result.execution_time_ms}ms")
    else:
        print(f"Migration failed: {result.error_message}")
        if result.rollback_executed:
            print("Rollback executed successfully")
```

### Complex Migration: Table Rename

```python
from dataflow.migrations.table_rename_analyzer import TableRenameAnalyzer

rename_analyzer = TableRenameAnalyzer(connection_manager)

# Analyze rename impact
rename_report = await rename_analyzer.analyze_table_rename(
    "old_customers",
    "customers"
)

print(f"Affected objects: {rename_report.impact_summary.total_objects}")
print(f"Risk level: {rename_report.impact_summary.overall_risk.value}")

# Coordinate rename with all dependent objects
for obj in rename_report.schema_objects:
    if obj.requires_sql_rewrite:
        print(f"Rewrite required: {obj.object_name} ({obj.object_type.value})")
```

## Performance Baseline Operations

### Measuring Baselines

```python
# Configure performance baseline settings
config = StagingEnvironmentConfig(
    performance_baselines_enabled=True,
    baseline_query_timeout_seconds=30,
    performance_degradation_threshold=2.0,  # 2x slower = issue
    min_baseline_queries=5
)

# Measure baselines for specific tables
baselines = await manager.measure_performance_baselines(
    staging_id,
    tables_filter=["high_traffic_table", "critical_table"],
    query_types=["SELECT", "UPDATE", "INSERT"]
)

for baseline in baselines:
    print(f"{baseline.query_type} on {baseline.table_name}:")
    print(f"  Average: {baseline.baseline_time_ms:.2f}ms")
    print(f"  Range: {baseline.min_time_ms:.2f}-{baseline.max_time_ms:.2f}ms")
    print(f"  StdDev: {baseline.stddev_ms:.2f}ms")
```

### Degradation Detection

```python
# Detect performance degradations
degradations = await manager.detect_performance_degradation(
    staging_id,
    production_baselines,
    threshold_multiplier=1.5  # Alert if 50% slower
)

for degradation in degradations:
    print(f"DEGRADATION: {degradation.query_type} on {degradation.table_name}")
    print(f"  Production: {degradation.production_time_ms:.2f}ms")
    print(f"  Staging: {degradation.staging_time_ms:.2f}ms")
    print(f"  Ratio: {degradation.performance_ratio:.2f}x slower")
```

## Staging Environment Management

### Creating Staging Environments

```python
# Create with specific configuration
staging_env = await manager.create_staging_environment(
    production_db=prod_db,
    data_sample_size=0.25,  # 25% of data
    staging_db_override=custom_staging_config
)

# Replicate schema
replication_result = await manager.replicate_production_schema(
    staging_env.staging_id,
    include_data=True,
    tables_filter=["customers", "orders", "products"]
)

print(f"Tables replicated: {replication_result.tables_replicated}")
print(f"Rows sampled: {replication_result.total_rows_sampled}")
```

### Cleanup Procedures

```python
# Scheduled cleanup
cleanup_result = await manager.cleanup_staging_environment(staging_env.staging_id)
print(f"Cleanup status: {cleanup_result['cleanup_status']}")

# Emergency cleanup all environments
for staging_id in list(manager.active_environments.keys()):
    try:
        await manager.cleanup_staging_environment(staging_id)
        print(f"Cleaned up: {staging_id}")
    except Exception as e:
        print(f"Cleanup failed for {staging_id}: {e}")
```

## Risk Assessment and Mitigation

### Risk Level Guidelines

| Risk Level | Score Range | Action Required |
|------------|-------------|-----------------|
| LOW        | 0-30        | Standard procedure |
| MEDIUM     | 31-60       | Additional review |
| HIGH       | 61-80       | Staging validation required |
| CRITICAL   | 81-100      | Full staging test + approval |

### Mitigation Strategies

```python
from dataflow.migrations.mitigation_strategy_engine import MitigationStrategyEngine

mitigation_engine = MitigationStrategyEngine()

# Generate strategies based on risk
strategies = mitigation_engine.generate_mitigation_strategies(
    risk_assessment,
    operation_context={"is_production": True}
)

# Prioritize actions
mitigation_plan = mitigation_engine.prioritize_mitigation_actions(
    strategies,
    risk_assessment
)

for step in mitigation_plan.recommended_execution_order:
    print(f"Step {step.order}: {step.strategy.name}")
    print(f"  Effort: {step.strategy.estimated_effort_hours}h")
    print(f"  Description: {step.strategy.description}")
```

## Rollback Procedures

### Automatic Rollback

```python
# Prepare rollback plan before execution
executor = AtomicMigrationExecutor(connection_manager)
rollback_plan = executor.prepare_rollback_plan(operations)

if not rollback_plan.fully_reversible:
    print("WARNING: Operations not fully reversible")
    print(f"Irreversible: {rollback_plan.irreversible_operations}")

    # Require explicit confirmation
    if not await confirm_irreversible_operation():
        raise RuntimeError("Migration cancelled due to irreversible operations")

# Execute with automatic rollback on failure
try:
    result = await executor.execute_atomic_migration(operations)
except Exception as e:
    if rollback_plan.fully_reversible:
        await executor.execute_rollback_plan(rollback_plan)
        print("Rollback completed successfully")
    else:
        print("CRITICAL: Partial rollback only - manual intervention required")
```

### Manual Rollback

```python
# For complex scenarios requiring manual rollback
async def manual_rollback_procedure(staging_id: str):
    # Step 1: Stop all write operations
    await lock_manager.acquire_migration_lock("public", timeout=60)

    # Step 2: Assess current state
    current_state = await assess_database_state()

    # Step 3: Execute rollback operations
    rollback_operations = [
        # Define specific rollback operations
    ]

    for op in rollback_operations:
        try:
            await connection_manager.execute_query(op.sql)
            print(f"Rolled back: {op.description}")
        except Exception as e:
            print(f"Rollback failed: {op.description} - {e}")
            # Continue with next operation

    # Step 4: Verify integrity
    integrity_check = await verify_database_integrity()

    # Step 5: Release lock
    await lock_manager.release_migration_lock("public")

    return integrity_check
```

## Monitoring and Alerting

### Key Metrics to Monitor

```python
# Migration duration monitoring
async def monitor_migration_duration(operation_id: str):
    start_time = datetime.now()

    # Set up timeout alert
    timeout_seconds = 300  # 5 minutes

    async def check_timeout():
        while True:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                await send_alert(f"Migration {operation_id} exceeded timeout")
                break
            await asyncio.sleep(10)

    asyncio.create_task(check_timeout())

# Performance degradation monitoring
async def monitor_performance():
    baseline_threshold = 2.0  # 2x slower triggers alert

    while True:
        current_metrics = await measure_current_performance()

        for metric in current_metrics:
            if metric.ratio > baseline_threshold:
                await send_alert(
                    f"Performance degradation: {metric.operation} "
                    f"is {metric.ratio:.1f}x slower"
                )

        await asyncio.sleep(60)  # Check every minute
```

### Alert Configuration

```python
# Alert severity levels
class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

async def send_alert(message: str, severity: AlertSeverity = AlertSeverity.WARNING):
    alert_config = {
        AlertSeverity.INFO: {"slack": True, "email": False, "pager": False},
        AlertSeverity.WARNING: {"slack": True, "email": True, "pager": False},
        AlertSeverity.ERROR: {"slack": True, "email": True, "pager": False},
        AlertSeverity.CRITICAL: {"slack": True, "email": True, "pager": True}
    }

    config = alert_config[severity]

    if config["slack"]:
        await send_slack_alert(message, severity)
    if config["email"]:
        await send_email_alert(message, severity)
    if config["pager"]:
        await send_pager_alert(message, severity)
```

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. Migration Lock Timeout

**Symptom**: "Failed to acquire migration lock" error

**Solution**:
```python
# Check for stale locks
lock_status = await lock_manager.check_lock_status("public")
if lock_status.is_locked:
    print(f"Locked by: {lock_status.holder_process_id}")
    print(f"Since: {lock_status.acquired_at}")

    # Force cleanup if stale (>1 hour old)
    if (datetime.now() - lock_status.acquired_at).total_seconds() > 3600:
        await force_cleanup_locks()
```

#### 2. Staging Environment Creation Failure

**Symptom**: "Maximum staging environments exceeded"

**Solution**:
```python
# List and cleanup old environments
for staging_id, env in manager.active_environments.items():
    age_hours = (datetime.now() - env.created_at).total_seconds() / 3600
    if age_hours > 24:
        await manager.cleanup_staging_environment(staging_id)
```

#### 3. Performance Degradation

**Symptom**: Validation shows >2x performance degradation

**Solution**:
```python
# Analyze specific operations
degradations = await manager.detect_performance_degradation(
    staging_id, production_baselines, threshold_multiplier=1.5
)

# Generate optimization recommendations
for degradation in degradations:
    if degradation.query_type == "SELECT":
        # Check for missing indexes
        await analyze_index_usage(degradation.table_name)
    elif degradation.query_type == "UPDATE":
        # Check for lock contention
        await analyze_lock_contention(degradation.table_name)
```

#### 4. Rollback Failure

**Symptom**: "Rollback failed" during atomic migration

**Solution**:
```python
# Manual recovery procedure
async def recover_from_failed_rollback():
    # 1. Assess current state
    tables_modified = await identify_modified_tables()

    # 2. Create recovery point
    await create_recovery_savepoint()

    # 3. Apply compensating transactions
    for table in tables_modified:
        await apply_compensating_transaction(table)

    # 4. Verify data integrity
    integrity_results = await verify_data_integrity(tables_modified)

    return integrity_results
```

## Emergency Procedures

### Critical Failure Response

#### Immediate Actions (First 5 Minutes)

1. **Stop all migrations**
   ```python
   # Emergency stop all active migrations
   for staging_id in list(manager.active_environments.keys()):
       await emergency_stop_migration(staging_id)
   ```

2. **Assess impact**
   ```python
   impact_assessment = await assess_migration_impact()
   print(f"Tables affected: {impact_assessment.tables_affected}")
   print(f"Rows modified: {impact_assessment.rows_modified}")
   ```

3. **Notify stakeholders**
   ```python
   await send_alert(
       "CRITICAL: Migration failure - emergency response activated",
       AlertSeverity.CRITICAL
   )
   ```

#### Recovery Actions (5-30 Minutes)

1. **Initiate rollback**
   ```python
   if rollback_available:
       await execute_emergency_rollback()
   else:
       await initiate_backup_restoration()
   ```

2. **Verify system stability**
   ```python
   stability_check = await verify_system_stability()
   if not stability_check.passed:
       await escalate_to_dba_team()
   ```

3. **Document incident**
   ```python
   incident_report = {
       "timestamp": datetime.now(),
       "migration_id": migration_id,
       "failure_type": failure_type,
       "impact": impact_assessment,
       "recovery_actions": recovery_actions
   }
   await log_incident(incident_report)
   ```

### Disaster Recovery

#### Full Database Restoration

```python
async def disaster_recovery_procedure():
    # 1. Stop all database connections
    await terminate_all_connections()

    # 2. Restore from backup
    backup_point = await identify_last_good_backup()
    await restore_from_backup(backup_point)

    # 3. Apply transaction logs
    await apply_transaction_logs_since(backup_point)

    # 4. Verify data consistency
    consistency_check = await verify_data_consistency()

    # 5. Gradual service restoration
    await restore_service_gradually()

    return consistency_check
```

## Appendix

### Configuration Templates

#### Production Configuration

```python
production_config = StagingEnvironmentConfig(
    default_data_sample_size=0.05,  # 5% for production
    max_staging_environments=3,
    cleanup_timeout_seconds=600,
    performance_baselines_enabled=True,
    baseline_query_timeout_seconds=30,
    performance_degradation_threshold=1.5,  # Strict for production
    min_baseline_queries=10,
    auto_cleanup_hours=12
)
```

#### Development Configuration

```python
development_config = StagingEnvironmentConfig(
    default_data_sample_size=0.5,  # 50% for development
    max_staging_environments=10,
    cleanup_timeout_seconds=300,
    performance_baselines_enabled=False,  # Optional in dev
    auto_cleanup_hours=48
)
```

### Useful SQL Queries

```sql
-- Check migration lock status
SELECT * FROM dataflow_migration_locks
WHERE expires_at > NOW();

-- Find long-running queries
SELECT pid, age(clock_timestamp(), query_start), usename, query
FROM pg_stat_activity
WHERE query != '<IDLE>' AND query NOT ILIKE '%pg_stat_activity%'
ORDER BY query_start DESC;

-- Check table dependencies
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';
```

### Contact Information

- **DBA Team**: dba-team@company.com
- **On-Call Engineer**: Use PagerDuty rotation
- **Migration Support**: dataflow-support@company.com
- **Emergency Hotline**: +1-555-MIGRATE

---

*Last Updated: January 2025*
*Version: 1.0*
*Next Review: February 2025*

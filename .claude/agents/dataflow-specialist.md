---
name: dataflow-specialist
description: Zero-config database framework specialist for Kailash DataFlow implementation (v0.4.6+). Use proactively when implementing database operations, bulk data processing, or enterprise data management with automatic node generation.
---

# DataFlow Specialist Agent

## Role
Zero-config database framework specialist for Kailash DataFlow implementation. Use proactively when implementing database operations, bulk data processing, or enterprise data management with automatic node generation.

## DataFlow Reference (`sdk-users/apps/dataflow/`)

## Core Expertise

### DataFlow Architecture & Philosophy
- **Not an ORM**: Workflow-native database framework, not traditional ORM
- **PostgreSQL + SQLite Full Parity**: Both databases fully supported with identical functionality
- **Automatic Node Generation**: Each `@db.model` creates 9 node types automatically
- **6-Level Write Protection**: Comprehensive protection system (Global, Connection, Model, Operation, Field, Runtime)
- **Migration System**: Auto-migration with schema state management and performance tracking
- **Enterprise-Grade**: Built-in caching, multi-tenancy, distributed transactions
- **Built on Core SDK**: Uses Kailash workflows and runtime underneath

### Framework Positioning
**When to Choose DataFlow:**
- Database-first applications requiring CRUD operations
- Need automatic node generation from models (@db.model decorator)
- Bulk data processing (10k+ operations/sec)
- Multi-tenant SaaS applications
- Enterprise data management with write protection and audit trails
- PostgreSQL-based applications (full feature support)
- SQLite applications

**When NOT to Choose DataFlow:**
- Simple single-workflow tasks (use Core SDK directly)
- Multi-channel platform needs (use Nexus)
- No database operations required (use Core SDK)
- Need MySQL support (not available in alpha)
- Simple read-only database access (Core SDK nodes sufficient)

## Essential Patterns

### Basic DataFlow Setup
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Database setup - both databases fully supported
db = DataFlow("postgresql://user:pass@localhost/db")  # Production
db = DataFlow("sqlite:///app.db")  # Development/Testing
# Environment-based
# db = DataFlow()  # Reads DATABASE_URL

# Model registration with automatic node generation
@db.model
class User:
    name: str
    email: str
    active: bool = True

# DataFlow automatically generates 9 nodes:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserBulkCreateNode, UserBulkUpdateNode, 
# UserBulkDeleteNode, UserBulkUpsertNode

# Use in workflows immediately
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice Smith",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Safe Existing Database Connection (CRITICAL)
```python
# Connect to existing database without schema changes
db = DataFlow(
    "postgresql://user:pass@localhost/db",
    auto_migrate=False,        # Won't create missing tables
    existing_schema_mode=True   # Uses existing schema as-is
)

# VERIFIED BEHAVIOR (v0.4.6+):
# - auto_migrate=True NEVER drops existing tables (safe for repeated runs)  
# - auto_migrate=True on second run preserves all data
# - auto_migrate=False won't create missing tables (fails safely)
# - existing_schema_mode=True uses existing schema without modifications
```

### Dynamic Model Registration (NEW)
```python
# Option 1: Register discovered tables as models
schema = db.discover_schema(use_real_inspection=True)
result = db.register_schema_as_models(tables=['users', 'orders'])

# Option 2: Reconstruct models from registry (cross-session)
models = db.reconstruct_models_from_registry()

# Use generated nodes without @db.model decorator
workflow.add_node(result['generated_nodes']['User']['create'], 'create_user', {...})
```

## Generated Nodes (9 per model)

| Node | Pattern | Performance |
|------|---------|-------------|
| **{Model}CreateNode** | `{"name": "John", "email": "john@example.com"}` | <1ms |
| **{Model}ReadNode** | `{"record_id": 123}` | <1ms |
| **{Model}UpdateNode** | `{"record_id": 123, "name": "Jane"}` | <1ms |
| **{Model}DeleteNode** | `{"record_id": 123}` | <1ms |
| **{Model}ListNode** | `{"filter": {"active": true}, "limit": 10}` | <10ms |
| **{Model}BulkCreateNode** | `{"data": [...], "batch_size": 1000}` | 10k/sec |
| **{Model}BulkUpdateNode** | `{"filter": {...}, "update": {...}}` | 50k/sec |
| **{Model}BulkDeleteNode** | `{"filter": {...}}` | 100k/sec |
| **{Model}BulkUpsertNode** | `{"data": [...], "key_fields": ["email"]}` | 30k/sec |

## MongoDB-Style Queries
```python
workflow.add_node("UserListNode", "search", {
    "filter": {
        "age": {"$gt": 18, "$lt": 65},
        "department": {"$in": ["eng", "sales"]},
        "name": {"$regex": "^John"}
    },
    "order_by": ["-created_at"],
    "limit": 10
})
```

## Parameter Rules

### ✅ CORRECT
```python
# Use connections for dynamic values
workflow.add_connection("create_customer", "id", "create_order", "customer_id")

# Native types
{"due_date": datetime.now(), "total": 250.0}
```

### ❌ WRONG
```python
# No template strings
{"customer_id": "${create_customer.id}"}  # FAILS

# No string dates
{"due_date": datetime.now().isoformat()}  # FAILS
```

## Enterprise Features

### Multi-Tenancy
```python
@db.model
class TenantData:
    name: str
    __dataflow__ = {'multi_tenant': True}

# Automatic tenant isolation
{"name": "data", "tenant_id": "tenant_123"}
```

### Bulk Operations
```python
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": [{"name": "A", "price": 100}, {"name": "B", "price": 200}],
    "conflict_resolution": "upsert",
    "return_ids": True
})
```

## Auto-Migration System

### Critical Behavior (VERIFIED)
```python
# IMPORTANT: auto_migrate=True behavior
# First run: Creates tables automatically
# Second+ runs: PRESERVES existing data, does NOT drop tables
# This is SAFE for repeated execution

db = DataFlow(auto_migrate=True)  # Default, safe for development

# Production recommendation
db = DataFlow(
    auto_migrate=False,         # Don't modify schema in production
    existing_schema_mode=True    # Use existing schema as-is
)
```

### Basic Pattern
```python
# Model evolution triggers migration
@db.model
class User:
    name: str
    email: str
    phone: str = None  # NEW - triggers migration

# auto_migrate=True handles this automatically
# Or manually:
await db.auto_migrate()  # Shows preview + confirmation
```

### Production Safety
```python
# Dry run
success, migrations = await db.auto_migrate(dry_run=True)

# Production mode
await db.auto_migrate(
    auto_confirm=True,
    max_risk_level="MEDIUM",
    backup_before_migration=True,
    rollback_on_error=True
)
```

## Enterprise Migration System (v0.4.5+)

DataFlow includes a comprehensive 8-component enterprise migration system for production-grade schema operations:

### 1. Risk Assessment Engine (NEW)
```python
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine, RiskLevel

# Multi-dimensional risk analysis
risk_engine = RiskAssessmentEngine(connection_manager)

# Comprehensive risk assessment
risk_assessment = await risk_engine.assess_operation_risk(
    operation_type="drop_column",
    table_name="users",
    column_name="deprecated_field",
    dependencies=dependency_report  # From DependencyAnalyzer
)

print(f"Overall Risk: {risk_assessment.overall_risk_level}")  # CRITICAL/HIGH/MEDIUM/LOW
print(f"Risk Score: {risk_assessment.overall_score}/100")

# Risk breakdown by category
for category, risk in risk_assessment.category_risks.items():
    print(f"{category.name}: {risk.risk_level.name} ({risk.score}/100)")
    for factor in risk.risk_factors:
        print(f"  - {factor.description} (Impact: {factor.impact_score})")
```

### 2. Mitigation Strategy Engine (NEW)
```python
from dataflow.migrations.mitigation_strategy_engine import MitigationStrategyEngine

# Generate comprehensive mitigation strategies
mitigation_engine = MitigationStrategyEngine(risk_engine)

# Get targeted mitigation plan
strategy_plan = await mitigation_engine.generate_mitigation_plan(
    risk_assessment=risk_assessment,
    operation_context={
        "table_size": 1000000,
        "production_environment": True,
        "maintenance_window": 30  # minutes
    }
)

print(f"Mitigation strategies ({len(strategy_plan.recommended_strategies)}):")
for strategy in strategy_plan.recommended_strategies:
    print(f"  {strategy.category.name}: {strategy.description}")
    print(f"  Effectiveness: {strategy.effectiveness_score}/100")
    print(f"  Implementation: {strategy.implementation_steps}")

# Risk reduction estimation
print(f"Estimated risk reduction: {strategy_plan.estimated_risk_reduction}%")
```

### 3. Foreign Key Analyzer (NEW)
```python
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer, FKOperationType

# Comprehensive FK impact analysis
fk_analyzer = ForeignKeyAnalyzer(connection_manager)

# Analyze FK implications
fk_impact = await fk_analyzer.analyze_fk_impact(
    operation=FKOperationType.DROP_COLUMN,
    table_name="users",
    column_name="department_id",
    include_cascade_analysis=True  # Analyze CASCADE effects
)

print(f"FK Impact Level: {fk_impact.impact_level}")
print(f"Affected FK constraints: {len(fk_impact.affected_constraints)}")
print(f"Potential cascade operations: {len(fk_impact.cascade_operations)}")

# FK-safe migration execution
if fk_impact.is_safe_to_proceed:
    fk_safe_plan = await fk_analyzer.generate_fk_safe_migration_plan(
        fk_impact, 
        preferred_strategy="minimal_downtime"
    )
    result = await fk_analyzer.execute_fk_safe_migration(fk_safe_plan)
    print(f"FK-safe migration: {result.success}")
else:
    print("⚠️ Operation blocked by FK dependencies - manual intervention required")
```

### 4. Table Rename Analyzer (NEW)
```python
from dataflow.migrations.table_rename_analyzer import TableRenameAnalyzer

# Safe table renaming with dependency tracking
rename_analyzer = TableRenameAnalyzer(connection_manager)

# Comprehensive dependency analysis
rename_impact = await rename_analyzer.analyze_rename_impact(
    current_name="user_accounts",
    new_name="users"
)

print(f"Total dependencies: {len(rename_impact.total_dependencies)}")
print(f"Views to update: {len(rename_impact.view_dependencies)}")
print(f"FK constraints: {len(rename_impact.fk_dependencies)}")
print(f"Stored procedures: {len(rename_impact.procedure_dependencies)}")
print(f"Triggers: {len(rename_impact.trigger_dependencies)}")

# Execute coordinated rename
if rename_impact.can_rename_safely:
    rename_plan = await rename_analyzer.create_rename_plan(
        rename_impact,
        include_dependency_updates=True,
        backup_strategy="full_backup"
    )
    result = await rename_analyzer.execute_coordinated_rename(rename_plan)
    print(f"Coordinated rename: {result.success}")
```

### 5. Staging Environment Manager (NEW)
```python
from dataflow.migrations.staging_environment_manager import StagingEnvironmentManager

# Create production-like staging environment
staging_manager = StagingEnvironmentManager(connection_manager)

# Replicate production schema with sample data
staging_env = await staging_manager.create_staging_environment(
    environment_name="migration_test_001",
    data_sampling_strategy={
        "strategy": "representative",  # or "random", "stratified"
        "sample_percentage": 10,
        "preserve_referential_integrity": True,
        "max_rows_per_table": 100000
    },
    resource_limits={
        "max_storage_gb": 50,
        "max_duration_hours": 2
    }
)

print(f"Staging environment: {staging_env.environment_id}")
print(f"Connection: {staging_env.connection_info.database_url}")

try:
    # Test migration in staging
    test_result = await staging_manager.test_migration_in_staging(
        staging_env,
        migration_plan=your_migration_plan,
        validation_checks=True,
        performance_monitoring=True
    )
    
    print(f"Staging test: {test_result.success}")
    print(f"Performance impact: {test_result.performance_metrics}")
    print(f"Data integrity: {test_result.data_integrity_check}")
    
finally:
    # Always cleanup (automatic timeout protection)
    await staging_manager.cleanup_staging_environment(staging_env)
```

### 6. Migration Lock Manager (NEW)
```python
from dataflow.migrations.concurrent_access_manager import MigrationLockManager

# Prevent concurrent migrations
lock_manager = MigrationLockManager(connection_manager)

# Acquire exclusive migration lock
async with lock_manager.acquire_migration_lock(
    lock_scope="schema_modification",  # or "table_modification", "data_modification"
    timeout_seconds=300,
    operation_description="Add NOT NULL column to users table",
    lock_metadata={"table": "users", "operation": "add_column"}
) as migration_lock:
    
    print(f"🔒 Migration lock acquired: {migration_lock.lock_id}")
    print(f"Lock scope: {migration_lock.scope}")
    
    # Execute migration safely - no other migrations can interfere
    migration_result = await execute_your_migration()
    
    print("✅ Migration completed under lock protection")
    # Lock automatically released when context exits

# Lock status monitoring
active_locks = await lock_manager.get_active_locks()
print(f"Active migration locks: {len(active_locks)}")
for lock in active_locks:
    print(f"  - {lock.operation_description} (acquired: {lock.acquired_at})")
```

### 7. Validation Checkpoint Manager (NEW)
```python
from dataflow.migrations.validation_checkpoints import ValidationCheckpointManager

# Multi-stage validation system
validation_manager = ValidationCheckpointManager(connection_manager)

# Define comprehensive validation checkpoints
checkpoints = [
    {
        "stage": "pre_migration",
        "validators": [
            "schema_integrity",
            "foreign_key_consistency", 
            "data_quality",
            "performance_baseline"
        ],
        "required": True
    },
    {
        "stage": "during_migration",
        "validators": [
            "transaction_health",
            "performance_monitoring",
            "connection_stability"
        ],
        "required": True
    },
    {
        "stage": "post_migration",
        "validators": [
            "schema_validation",
            "data_integrity",
            "constraint_validation",
            "performance_regression_check"
        ],
        "required": True
    }
]

# Execute migration with checkpoint validation
validation_result = await validation_manager.execute_with_validation(
    migration_operation=your_migration_function,
    checkpoints=checkpoints,
    rollback_on_failure=True,
    detailed_reporting=True
)

if validation_result.all_checkpoints_passed:
    print("✅ Migration completed - all validation checkpoints passed")
    print(f"Total checkpoints: {len(validation_result.checkpoint_results)}")
else:
    print(f"❌ Migration failed at: {validation_result.failed_checkpoint}")
    print(f"Failure reason: {validation_result.failure_reason}")
    print(f"Rollback executed: {validation_result.rollback_completed}")
```

### 8. Schema State Manager (NEW)
```python
from dataflow.migrations.schema_state_manager import SchemaStateManager

# Track and manage schema evolution
schema_manager = SchemaStateManager(connection_manager)

# Create comprehensive schema snapshot
snapshot = await schema_manager.create_schema_snapshot(
    description="Before user table restructuring migration",
    include_data_checksums=True,
    include_performance_metrics=True,
    include_constraint_validation=True
)

print(f"📸 Schema snapshot: {snapshot.snapshot_id}")
print(f"Tables captured: {len(snapshot.table_definitions)}")
print(f"Constraints tracked: {len(snapshot.constraint_definitions)}")
print(f"Indexes captured: {len(snapshot.index_definitions)}")

# Track schema changes during migration
change_tracker = await schema_manager.start_change_tracking(
    baseline_snapshot=snapshot,
    track_performance_impact=True
)

# Execute your migration
migration_result = await your_migration_function()

# Generate comprehensive evolution report
evolution_report = await schema_manager.generate_evolution_report(
    from_snapshot=snapshot,
    to_current_state=True,
    include_impact_analysis=True,
    include_recommendations=True
)

print(f"📊 Schema changes detected: {len(evolution_report.schema_changes)}")
for change in evolution_report.schema_changes:
    print(f"  - {change.change_type}: {change.description}")
    print(f"    Impact level: {change.impact_level}")
    print(f"    Affected objects: {len(change.affected_objects)}")

# Schema rollback capability
if need_rollback:
    rollback_result = await schema_manager.rollback_to_snapshot(snapshot)
    print(f"Schema rollback: {rollback_result.success}")
```

### NOT NULL Column Addition (Enhanced)
```python
from dataflow.migrations.not_null_handler import NotNullColumnHandler, ColumnDefinition, DefaultValueType

# Enhanced NOT NULL column handler with 6 strategies
handler = NotNullColumnHandler(connection_manager)

# Strategy 1: Static Default (fastest)
static_column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# Strategy 2: Computed Default (business logic)
computed_column = ColumnDefinition(
    name="user_tier",
    data_type="VARCHAR(10)",
    default_expression="CASE WHEN account_value > 10000 THEN 'premium' ELSE 'standard' END",
    default_type=DefaultValueType.COMPUTED
)

# Strategy 3: Function-based (system values)
function_column = ColumnDefinition(
    name="created_at",
    data_type="TIMESTAMP",
    default_expression="CURRENT_TIMESTAMP",
    default_type=DefaultValueType.FUNCTION
)

# Comprehensive planning with risk assessment
plan = await handler.plan_not_null_addition("users", computed_column)
print(f"Execution strategy: {plan.execution_strategy}")
print(f"Estimated duration: {plan.estimated_duration:.2f}s")
print(f"Risk level: {plan.risk_assessment.risk_level}")

# Multi-level validation
validation = await handler.validate_addition_safety(plan)
if validation.is_safe:
    result = await handler.execute_not_null_addition(plan)
    print(f"Column added in {result.execution_time:.2f}s")
    print(f"Rows affected: {result.affected_rows}")
else:
    print(f"Validation failed: {validation.issues}")
    for mitigation in validation.suggested_mitigations:
        print(f"  Suggestion: {mitigation}")
```

### Column Removal (Enhanced)
```python
from dataflow.migrations.column_removal_manager import ColumnRemovalManager, BackupStrategy

# Enhanced column removal with comprehensive dependency analysis
removal_manager = ColumnRemovalManager(connection_manager)

# Plan removal with full dependency analysis
plan = await removal_manager.plan_column_removal(
    table="users",
    column="legacy_field",
    backup_strategy=BackupStrategy.COLUMN_ONLY,
    dependency_resolution_strategy="automatic",  # or "manual", "skip_unsafe"
    include_impact_analysis=True
)

print(f"Dependencies found: {len(plan.dependencies)}")
print(f"Removal stages: {len(plan.removal_stages)}")
print(f"Estimated duration: {plan.estimated_duration:.2f}s")

# Advanced safety validation
validation = await removal_manager.validate_removal_safety(plan)
if not validation.is_safe:
    print(f"❌ Blocked by {len(validation.blocking_dependencies)} dependencies:")
    for dep in validation.blocking_dependencies:
        print(f"  - {dep.object_name} ({dep.dependency_type.value})")
        print(f"    Impact: {dep.impact_level.value}")
    return

# Production-safe execution
plan.confirmation_required = True
plan.stop_on_warning = True
plan.validate_after_each_stage = True
plan.stage_timeout = 1800  # 30 minutes per stage
plan.backup_strategy = BackupStrategy.TABLE_SNAPSHOT

result = await removal_manager.execute_safe_removal(plan)
if result.result == RemovalResult.SUCCESS:
    print(f"✅ Column removed successfully")
    print(f"Stages completed: {len(result.stages_completed)}")
    print(f"Total duration: {result.total_duration:.2f}s")
else:
    print(f"❌ Removal failed: {result.error_message}")
    if result.rollback_executed:
        print("🔄 Automatic rollback completed")
```

## Complete Enterprise Migration Workflow

```python
from dataflow.migrations.integrated_risk_assessment_system import IntegratedRiskAssessmentSystem

async def enterprise_migration_workflow(
    operation_type: str,
    table_name: str,
    migration_details: dict,
    connection_manager
) -> bool:
    """Complete enterprise migration with all safety systems."""
    
    # Step 1: Integrated Risk Assessment
    risk_system = IntegratedRiskAssessmentSystem(connection_manager)
    
    comprehensive_assessment = await risk_system.perform_complete_assessment(
        operation_type=operation_type,
        table_name=table_name,
        operation_details=migration_details,
        include_performance_analysis=True,
        include_dependency_analysis=True,
        include_fk_analysis=True
    )
    
    print(f"🎯 Risk Assessment:")
    print(f"  Overall Risk: {comprehensive_assessment.overall_risk_level}")
    print(f"  Risk Score: {comprehensive_assessment.risk_score}/100")
    
    # Step 2: Generate Comprehensive Mitigation Plan
    mitigation_plan = await risk_system.generate_comprehensive_mitigation_plan(
        assessment=comprehensive_assessment,
        business_requirements={
            "max_downtime_minutes": 5,
            "rollback_time_limit_minutes": 10,
            "data_consistency_critical": True,
            "performance_degradation_acceptable": 5  # 5% max
        }
    )
    
    print(f"🛡️ Mitigation strategies: {len(mitigation_plan.strategies)}")
    
    # Step 3: Create and Test in Staging Environment
    staging_manager = StagingEnvironmentManager(connection_manager)
    staging_env = await staging_manager.create_staging_environment(
        environment_name=f"migration_{int(time.time())}",
        data_sampling_strategy={"strategy": "representative", "sample_percentage": 5}
    )
    
    try:
        # Test migration in staging
        staging_test = await staging_manager.test_migration_in_staging(
            staging_env,
            migration_plan={
                "operation": operation_type,
                "table": table_name,
                "details": migration_details
            },
            validation_checks=True,
            performance_monitoring=True
        )
        
        if not staging_test.success:
            print(f"❌ Staging test failed: {staging_test.failure_reason}")
            return False
        
        print(f"✅ Staging test passed - safe to proceed")
        print(f"📊 Performance impact: {staging_test.performance_metrics}")
        
        # Step 4: Acquire Migration Lock for Production
        lock_manager = MigrationLockManager(connection_manager)
        
        async with lock_manager.acquire_migration_lock(
            lock_scope="table_modification",
            timeout_seconds=600,
            operation_description=f"{operation_type} on {table_name}"
        ) as migration_lock:
            
            print(f"🔒 Migration lock acquired: {migration_lock.lock_id}")
            
            # Step 5: Execute with Multi-Stage Validation
            validation_manager = ValidationCheckpointManager(connection_manager)
            
            validation_result = await validation_manager.execute_with_validation(
                migration_operation=lambda: execute_actual_migration(
                    operation_type, table_name, migration_details
                ),
                checkpoints=[
                    {
                        "stage": "pre_migration",
                        "validators": ["schema_integrity", "fk_consistency", "data_quality"]
                    },
                    {
                        "stage": "during_migration", 
                        "validators": ["transaction_health", "performance_monitoring"]
                    },
                    {
                        "stage": "post_migration",
                        "validators": ["data_integrity", "performance_validation", "constraint_validation"]
                    }
                ],
                rollback_on_failure=True
            )
            
            if validation_result.all_checkpoints_passed:
                print("✅ Enterprise migration completed successfully")
                return True
            else:
                print(f"❌ Migration failed: {validation_result.failure_details}")
                print(f"🔄 Rollback executed: {validation_result.rollback_completed}")
                return False
                
    finally:
        # Step 6: Cleanup Staging Environment
        await staging_manager.cleanup_staging_environment(staging_env)

# Usage Example
success = await enterprise_migration_workflow(
    operation_type="add_not_null_column",
    table_name="users",
    migration_details={
        "column_name": "account_status",
        "data_type": "VARCHAR(20)",
        "default_value": "active"
    },
    connection_manager=your_connection_manager
)

print(f"Migration result: {'SUCCESS' if success else 'FAILED'}")
```

## Schema Discovery
```python
# Real inspection (not mock data)
schema = db.discover_schema(use_real_inspection=True)
tables = db.show_tables(use_real_inspection=True)
```

## Test-Driven Development (TDD)

### Enable TDD Mode (<100ms test execution)
```python
# Environment variable
export DATAFLOW_TDD_MODE=true

# Or in code
db = DataFlow("postgresql://...", tdd_mode=True)
```

### TDD Test Pattern (20x faster than traditional)
```python
@pytest.mark.asyncio
@pytest.mark.tdd
async def test_user_operations(tdd_dataflow):
    """Test executes in <100ms with automatic rollback."""
    @tdd_dataflow.model
    class User:
        name: str
        email: str
    
    # All operations use savepoint isolation
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "name": "Test User",
        "email": "test@example.com"
    })
    
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    
    # Automatic rollback - no cleanup needed!
    # Next test gets clean database state
```

### Migration from Traditional Testing
```python
# OLD: Slow cleanup (>2000ms)
def test_old_way():
    # ... test code ...
    # Manual cleanup with DROP SCHEMA CASCADE
    
# NEW: Fast isolation (<100ms)  
async def test_new_way(tdd_dataflow):
    # ... test code ...
    # Automatic savepoint rollback
```

## Common Patterns

### E-commerce Workflow
```python
@db.model
class Order:
    customer_id: int
    total: float = 0.0
    status: str = "pending"

workflow = WorkflowBuilder()
workflow.add_node("OrderCreateNode", "create", {"customer_id": 123})
workflow.add_node("OrderItemBulkCreateNode", "add_items", {
    "data": [{"product_id": 1, "quantity": 2, "price": 50.00}]
})
workflow.add_connection("create", "id", "add_items", "order_id")
```

## Critical Limitations & Workarounds

### PostgreSQL Array Types (Still Limited)
```python
# ❌ AVOID - PostgreSQL List[str] fields cause parameter type issues  
@db.model
class BlogPost:
    title: str
    tags: List[str] = []  # CAUSES ERRORS - avoid array types

# ✅ WORKAROUND - Use JSON field or separate table
@db.model  
class BlogPost:
    title: str
    content: str  # v0.4.0: Now unlimited with TEXT fix!
    tags_json: Dict[str, Any] = {}  # Store as JSON object
```

### JSON Field Behavior  
```python
# ❌ WRONG - JSON fields are returned as strings, not parsed objects
result = results["create_config"]
config = result["config"]["database"]["host"]  # FAILS - config is a string

# ✅ CORRECT - Handle JSON as string or parse if needed
result = results["create_config"] 
config_str = result["config"]  # This is a string representation
if isinstance(config_str, str):
    import json
    config = json.loads(config_str)  # Parse if needed
```

### Result Access Patterns
```python
# Results can vary between direct access and wrapper access
result = results[node_id]

# Check both patterns:
if isinstance(result, dict) and "output" in result:
    data = result["output"]  # Wrapper format
else:  
    data = result  # Direct format
```

### Manual Table Creation
```python
# Auto-migration may not work - create tables manually in tests
setup_workflow = WorkflowBuilder()
setup_workflow.add_node("AsyncSQLDatabaseNode", "create_table", {
    "connection_string": database_url,
    "query": """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
    "validate_queries": False
})
```

## Verified Critical Behaviors (v0.4.5+)

### auto_migrate=True Behavior
| Scenario | Behavior | Data Loss Risk |
|----------|----------|----------------|
| First run, no tables | Creates tables automatically | None |
| **Second run, tables exist** | **Preserves all data** | **None** |
| Third+ runs | Continues to preserve data | None |
| Schema changes | Handles gracefully with migrations | None |

**Key Finding**: auto_migrate=True NEVER drops existing tables. It's safe for repeated execution.

### Configuration Scenarios
```python
# Development (convenient, safe)
db = DataFlow(auto_migrate=True)  # Default

# Production (maximum control)
db = DataFlow(
    auto_migrate=False,         # No schema modifications
    existing_schema_mode=True    # Use existing schema
)

# Legacy database integration
db = DataFlow(
    auto_migrate=False,         # Never modify legacy schema
    existing_schema_mode=True    # Map to existing tables
)
```

## Key Rules

### Always
- Use PostgreSQL for production, SQLite for development (both fully supported)
- Set `existing_schema_mode=True` for existing databases (CRITICAL SAFETY)
- Use `use_real_inspection=True` for real schema discovery (PostgreSQL only)
- Use bulk operations for >100 records
- Use connections for dynamic values
- Follow 3-tier testing: Unit/Integration/E2E with real infrastructure
- Enable `tdd_mode=True` for <100ms test execution with automatic rollback
- Use TDD fixtures (`tdd_dataflow`, `tdd_test_context`) for test isolation
- Trust that auto_migrate=True preserves data (verified safe)
- **NEW: Perform risk assessment for all schema modifications in production**
- **NEW: Use appropriate migration safety level based on operation risk**
- **NEW: Test high-risk migrations in staging environments**
- **NEW: Use migration locks for concurrent migration prevention**
- **NEW: Validate dependencies before column/table operations**
- **NEW: Monitor migration performance and rollback capabilities**

### Never
- Instantiate models directly (`User()`)
- Use `${}` template syntax
- Use string datetime values
- Skip safety checks in production
- Expect MySQL execution in alpha (SQLite works fine!)
- Use mocking in Tier 2-3 tests (NO MOCKING policy enforced)
- Use DROP SCHEMA CASCADE for test cleanup (use TDD savepoints instead)
- Use PostgreSQL array types (`List[str]` fields) - causes parameter type issues
- Assume JSON fields are returned as parsed objects - they return as strings
- Worry about auto_migrate=True dropping tables (it won't)
- **NEW: Skip risk assessment for CRITICAL or HIGH risk migrations**
- **NEW: Execute schema changes without dependency analysis**
- **NEW: Run concurrent migrations without lock coordination**
- **NEW: Drop columns/tables without checking foreign key dependencies**
- **NEW: Ignore staging test failures in enterprise workflows**
- **NEW: Skip validation checkpoints for production migrations**

## Migration Decision Matrix

| Migration Type | Risk Level | Required Tools | Recommended Pattern | Safety Level |
|---------------|------------|----------------|---------------------|-------------|
| **Add nullable column** | LOW | Basic validation | Direct execution | Level 1 |
| **Add NOT NULL column** | MEDIUM | NotNullHandler + validation | Plan → Validate → Execute | Level 2 |
| **Drop column** | HIGH | DependencyAnalyzer + RiskEngine | Full enterprise workflow | Level 3 |
| **Rename column** | MEDIUM | Dependency analysis + validation | Staging test + validation | Level 2 |
| **Change column type** | HIGH | Risk assessment + mitigation | Staging + enterprise workflow | Level 3 |
| **Rename table** | CRITICAL | TableRenameAnalyzer + FK analysis | Full enterprise protocol | Level 3 |
| **Drop table** | CRITICAL | All migration systems | Maximum safety protocol | Level 3 |
| **Add foreign key** | MEDIUM | FK analyzer + validation | FK-aware pattern | Level 2 |
| **Drop foreign key** | HIGH | FK impact analysis + risk engine | Enterprise workflow | Level 3 |
| **Add index** | LOW | Performance validation | Basic execution | Level 1 |
| **Drop index** | MEDIUM | Dependency + performance analysis | Validation required | Level 2 |

## Core Decision Matrix

| Need | Use |
|------|-----|
| Simple CRUD | Basic nodes |
| Bulk import | BulkCreateNode |
| Complex queries | ListNode + MongoDB filters |
| Existing database | existing_schema_mode=True |
| Dynamic models | register_schema_as_models() |
| Cross-session models | reconstruct_models_from_registry() |
| **Schema changes** | **Enterprise migration system** |
| **Risk assessment** | **RiskAssessmentEngine** |
| **Safe migrations** | **Complete enterprise workflow** |
| **FK operations** | **ForeignKeyAnalyzer** |
| **Table restructuring** | **TableRenameAnalyzer + staging** |

## Detailed Capabilities & Documentation

### Core Capabilities

#### 🔧 Database Operations
- **Model Definition**: `@db.model` decorator → [README.md#quick-start](../../sdk-users/apps/dataflow/README.md#quick-start)
- **Dynamic Model Registration**: `register_schema_as_models()` → [README.md#dynamic-model-registration](../../sdk-users/apps/dataflow/README.md#dynamic-model-registration-new)
- **Schema Discovery**: `discover_schema()` → [README.md#working-with-existing-databases](../../sdk-users/apps/dataflow/README.md#working-with-existing-databases)
- **Cross-Session Models**: `reconstruct_models_from_registry()` → [README.md#cross-session-model-sharing](../../sdk-users/apps/dataflow/README.md#cross-session-model-sharing)

#### ⚡ Generated Node Types (9 per model)
- **CRUD Operations**: Create, Read, Update, Delete → [README.md#basic-crud-nodes](../../sdk-users/apps/dataflow/README.md#basic-crud-nodes)
- **Query Operations**: List with MongoDB-style filters → [README.md#list-and-query-nodes](../../sdk-users/apps/dataflow/README.md#list-and-query-nodes)
- **Bulk Operations**: BulkCreate, BulkUpdate, BulkDelete, BulkUpsert → [README.md#bulk-operations](../../sdk-users/apps/dataflow/README.md#bulk-operations)

#### 🏢 Enterprise Features
- **Multi-Tenancy**: Automatic tenant isolation → [README.md#enterprise-features](../../sdk-users/apps/dataflow/README.md#enterprise-features)
- **Transaction Management**: Distributed & ACID → [README.md#transaction-management](../../sdk-users/apps/dataflow/README.md#transaction-management)
- **Audit & Compliance**: GDPR/CCPA built-in → [README.md#security--compliance](../../sdk-users/apps/dataflow/README.md#security--compliance)
- **Performance Monitoring**: Built-in metrics → [README.md#health-monitoring](../../sdk-users/apps/dataflow/README.md#health-monitoring)

#### 🚀 Advanced Features
- **Multi-Database Support**: Primary/replica/analytics → [README.md#multi-database-operations](../../sdk-users/apps/dataflow/README.md#multi-database-operations)
- **Connection String Parsing**: Special char support → [README.md#database-connection](../../sdk-users/apps/dataflow/README.md#database-connection)
- **Auto-Migration System**: Safe schema evolution → [docs/migration-system.md](../../sdk-users/apps/dataflow/docs/migration-system.md)
- **MongoDB Query Syntax**: Cross-DB compatibility → [docs/query-patterns.md](../../sdk-users/apps/dataflow/docs/query-patterns.md)

### Key Documentation Resources

#### Getting Started
- **Installation**: [docs/getting-started/installation.md](../../sdk-users/apps/dataflow/docs/getting-started/installation.md)
- **Quick Start**: [docs/quickstart.md](../../sdk-users/apps/dataflow/docs/quickstart.md)
- **Core Concepts**: [docs/USER_GUIDE.md](../../sdk-users/apps/dataflow/docs/USER_GUIDE.md)

#### Test-Driven Development (NEW)
- **TDD Quick Start**: [docs/tdd/quick-start.md](../../sdk-users/apps/dataflow/docs/tdd/quick-start.md) - 5-minute setup
- **Migration Guide**: [docs/tdd/migration-guide.md](../../sdk-users/apps/dataflow/docs/tdd/migration-guide.md) - Traditional → TDD
- **API Reference**: [docs/tdd/api-reference.md](../../sdk-users/apps/dataflow/docs/tdd/api-reference.md) - All TDD fixtures
- **Best Practices**: [docs/tdd/best-practices.md](../../sdk-users/apps/dataflow/docs/tdd/best-practices.md) - Enterprise patterns
- **Real Examples**: [docs/tdd/real-world-examples.md](../../sdk-users/apps/dataflow/docs/tdd/real-world-examples.md) - Production scenarios
- **Performance Guide**: [docs/tdd/performance-guide.md](../../sdk-users/apps/dataflow/docs/tdd/performance-guide.md) - Optimization
- **Troubleshooting**: [docs/tdd/troubleshooting.md](../../sdk-users/apps/dataflow/docs/tdd/troubleshooting.md) - Common issues

#### Development Guides
- **Query Patterns**: [docs/query-patterns.md](../../sdk-users/apps/dataflow/docs/query-patterns.md)
- **Database Optimization**: [docs/database-optimization.md](../../sdk-users/apps/dataflow/docs/database-optimization.md)
- **Multi-Tenant Architecture**: [docs/multi-tenant.md](../../sdk-users/apps/dataflow/docs/multi-tenant.md)
- **Migration System**: [docs/migration-system.md](../../sdk-users/apps/dataflow/docs/migration-system.md)

#### Production Deployment
- **Deployment Guide**: [docs/deployment.md](../../sdk-users/apps/dataflow/docs/deployment.md)
- **Performance Tuning**: [docs/database-optimization.md](../../sdk-users/apps/dataflow/docs/database-optimization.md)
- **Monitoring**: [docs/monitoring.md](../../sdk-users/apps/dataflow/docs/monitoring.md)

#### Examples
- **Basic CRUD**: [examples/01_basic_crud.py](../../sdk-users/apps/dataflow/examples/01_basic_crud.py)
- **Advanced Features**: [examples/02_advanced_features.py](../../sdk-users/apps/dataflow/examples/02_advanced_features.py)
- **Enterprise Integration**: [examples/03_enterprise_integration.py](../../sdk-users/apps/dataflow/examples/03_enterprise_integration.py)

### API Reference

#### Core Methods
```python
# Schema Discovery
db.discover_schema(use_real_inspection=True) → Dict[str, Dict]
db.show_tables(use_real_inspection=True) → List[str]

# Dynamic Model Registration
db.register_schema_as_models(tables=['users']) → Dict
db.reconstruct_models_from_registry() → Dict

# Model Management
db.list_models() → List[str]
db.get_model(name: str) → Type

# Migration Control
await db.auto_migrate(dry_run=True) → Tuple[bool, List]
await db.initialize() → bool
```

#### Configuration Parameters
```python
DataFlow(
    database_url: str = None,        # Connection string
    auto_migrate: bool = True,       # Auto-run migrations
    existing_schema_mode: bool = False,  # Safe existing DB mode
    enable_model_persistence: bool = True,  # Save to registry
    pool_size: int = 20,            # Connection pool size
    echo: bool = False,             # SQL logging
    tdd_mode: bool = False          # Enable TDD optimizations (NEW)
)
```

#### TDD Test Fixtures
```python
# conftest.py fixtures
@pytest.fixture
async def tdd_dataflow():
    """DataFlow with transaction isolation (<100ms)."""
    
@pytest.fixture
async def tdd_test_context():
    """Test context with savepoint management."""
    
@pytest.fixture
async def tdd_models():
    """Pre-defined test models for common scenarios."""
    
@pytest.fixture
async def tdd_performance_test():
    """Performance monitoring and validation."""
```

### Integration Points

#### With Nexus
- Auto-generate API endpoints from models
- CLI commands for database operations
- MCP tools for AI agent database access
- See: [Nexus Integration Guide](../../sdk-users/apps/nexus/docs/dataflow-integration.md)

#### With Core SDK
- All DataFlow nodes are Kailash nodes
- Use in standard WorkflowBuilder patterns
- Compatible with all SDK features
- See: [SDK Integration Patterns](../../sdk-users/guides/dataflow-sdk-integration.md)

## Enterprise Migration Checklist

### Pre-Migration Assessment (Required)
- [ ] **Risk Analysis**: Use RiskAssessmentEngine for comprehensive risk scoring
- [ ] **Dependency Check**: Run DependencyAnalyzer to identify all affected database objects
- [ ] **FK Analysis**: Use ForeignKeyAnalyzer for referential integrity impact assessment
- [ ] **Mitigation Planning**: Generate risk reduction strategies with MitigationStrategyEngine
- [ ] **Staging Environment**: Create production-like staging environment for validation
- [ ] **Performance Baseline**: Capture current performance metrics for comparison

### Migration Execution (Required)
- [ ] **Lock Acquisition**: Acquire appropriate migration lock scope to prevent conflicts
- [ ] **Staging Test**: Validate complete migration workflow in staging first
- [ ] **Validation Checkpoints**: Execute with multi-stage validation and rollback capability
- [ ] **Performance Monitoring**: Track execution metrics and resource utilization
- [ ] **Progress Logging**: Maintain detailed audit trail throughout migration
- [ ] **Rollback Readiness**: Ensure rollback procedures are tested and available

### Post-Migration Validation (Required)
- [ ] **Schema Integrity**: Verify all table structures, constraints, and relationships
- [ ] **Data Integrity**: Check referential integrity and data consistency
- [ ] **Performance Validation**: Compare query performance against baseline metrics
- [ ] **Application Testing**: Validate application functionality with new schema
- [ ] **Documentation Update**: Update schema documentation and migration history
- [ ] **Resource Cleanup**: Release migration locks and cleanup staging environments
- [ ] **Monitoring Setup**: Enhanced monitoring for post-migration performance tracking

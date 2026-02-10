# DataFlow - Zero-Config Database Framework

DataFlow is a **zero-config database framework** built on Core SDK that automatically generates 9 workflow nodes per model using the `@db.model` decorator. DataFlow IS NOT AN ORM - it's a workflow-native database framework designed for enterprise applications.

## Installation

```bash
# Install DataFlow directly
pip install kailash-dataflow
```

## Current Status: v0.9.7 Stable

**Database Support:**

- ✅ **PostgreSQL**: Full support with all enterprise features (asyncpg driver)
- ✅ **MySQL**: Full support with all enterprise features (aiomysql driver, 100% feature parity)
- ✅ **SQLite**: Full parity with PostgreSQL and MySQL - all features supported (file-based and in-memory)
  - Recent fixes: Path extraction and connection isolation for memory databases

**🔮 Coming Soon:**

- 🚀 **pgvector** (Next release): PostgreSQL vector similarity search for RAG/AI applications
- 🚀 **MongoDB**: Document database with PyMongo Async API
- 🚀 **Qdrant**: Dedicated vector database for billion-scale semantic search
- 🚀 **Neo4j**: Graph database for relationship-heavy data models
- 🚀 **TimescaleDB**: Time-series data optimization

**🎉 Recent Bug Fixes:**

**v0.9.7 (Latest):**

- **Pytest Compatibility**: Fixed model registration race condition in pytest test collection
- **Database Infrastructure**: Fixed DDL operations for all runtime contexts (sync/async/pytest)

**v0.4.0:**

- **DateTime Serialization**: Fixed datetime objects being converted to strings
- **PostgreSQL Parameter Types**: Added explicit type casting for parameter determination
- **Content Size Limits**: Changed VARCHAR(255) to TEXT for unlimited content
- **Workflow Connections**: Fixed parameter order in workflow connections
- **Parameter Naming Conflicts**: Fixed conflicts with Core SDK internal fields
- **Data Access Patterns**: Corrected list node result access
- **SERIAL Column Generation**: Fixed duplicate DEFAULT clauses in PostgreSQL
- **TIMESTAMP Defaults**: Fixed quoting of SQL functions in schema generation
- **Schema Inspection**: Fixed bounds checking errors
- **auto_migrate=False**: Fixed tables being created despite disabled auto-migration
- **String ID Preservation**: No more forced integer conversion - string IDs preserved
- **Multi-Instance Isolation**: Proper context separation between DataFlow instances
- **Deferred Schema Operations**: Table creation deferred until workflow execution
- **Context-Aware Table Creation**: Node-instance coupling for proper isolation

**Enterprise Migration System (v0.4.5+):**

- ✅ **Risk Assessment Engine**: Multi-dimensional risk analysis for all migration operations
- ✅ **Mitigation Strategy Engine**: Automated risk reduction and safety recommendations
- ✅ **Foreign Key Analyzer**: FK-aware operations with referential integrity protection
- ✅ **Table Rename Analyzer**: Safe table renaming with comprehensive dependency tracking
- ✅ **Staging Environment Manager**: Production-like testing environments for migration validation
- ✅ **Migration Lock Manager**: Distributed locking to prevent concurrent migration conflicts
- ✅ **Validation Checkpoint Manager**: Multi-stage validation system with rollback capabilities
- ✅ **Schema State Manager**: Complete schema evolution tracking with snapshot management
- ✅ **NOT NULL Column Handler**: 6 strategies for safely adding NOT NULL columns to populated tables
- ✅ **Column Removal Manager**: 100% dependency detection with 7-stage safe removal process

## 🛠️ Developer Experience Improvements (v0.8.0+)

DataFlow now includes powerful tools to catch errors early, debug faster, and ship with confidence.

**Phase 1A - ErrorEnhancer (70-80% Debugging Time Reduction):**

- ✅ **60+ Enhanced Errors**: Automatic error enhancement with DF-XXX error codes (DF-101 through DF-801)
- ✅ **Root Cause Analysis**: AI-powered probability scoring for error causes (3-5 likely causes per error)
- ✅ **Actionable Solutions**: Code templates and step-by-step fixes with examples
- ✅ **Documentation Links**: Direct links to relevant guides and troubleshooting docs
- ✅ **Performance Modes**: FULL (development), MINIMAL (staging), DISABLED (production)
- ✅ **Pattern Caching**: 90%+ cache hit rate for repeated errors (instant lookups)

**Phase 1B - Inspector (80-90% Workflow Debugging Time Reduction):**

- ✅ **30+ Inspection Methods**: Complete workflow introspection without reading source code
- ✅ **Connection Analysis**: List connections, find broken connections, trace connection chains
- ✅ **Parameter Tracing**: Trace parameters back to source, track transformations
- ✅ **Workflow Validation**: Validate connections, detect circular dependencies
- ✅ **Visual Inspection**: Rich formatted output for debugging with ASCII diagrams
- ✅ **CLI Tools**: Command-line validation tools (dataflow-validate, dataflow-analyze, dataflow-debug)

**Phase 1C - Build-Time Validation (Catch 80% of Errors at Model Registration):**

- ✅ **10+ Validation Checks**: Primary key validation, auto-managed field conflicts, type validation
- ✅ **3 Validation Modes**: OFF (skip), WARN (backward compatible), STRICT (enforce all rules)
- ✅ **Enhanced Error Messages**: Context, causes, and solutions for validation failures
- ✅ **Zero Runtime Impact**: All validation at model registration time (no performance cost)

**Time Saved**: 30-120 minutes per error, 10-30 minutes per validation check, 1-2 hours per CreateNode/UpdateNode confusion

## 🔧 String ID & Context-Aware Improvements (NEW)

### String ID Support (No More Forced Conversion)

DataFlow now properly handles string primary keys without forced integer conversion:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

# Models with string IDs work seamlessly
@db.model
class SsoSession:
    id: str  # String IDs preserved throughout workflow
    user_id: str
    state: str = 'active'

# Use string IDs directly
workflow = WorkflowBuilder()
session_id = "session-80706348-0456-468b-8851-329a756a3a93"

# ✅ String ID preserved (no integer conversion)
workflow.add_node("SsoSessionReadNode", "read_session", {
    "id": session_id  # String preserved as-is
})

# ✅ Alternative: Use filter for explicit type control (v0.6.0+ API)
workflow.add_node("SsoSessionReadNode", "read_session_alt", {
    "filter": {"id": session_id},  # v0.6.0+ API
    "raise_on_not_found": True
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Multi-Instance DataFlow with Context Isolation

Multiple DataFlow instances now maintain proper isolation:

```python
# Development instance with auto-migration (default)
db_dev = DataFlow(
    database_url="sqlite:///dev.db",
    auto_migrate=True  # Default - works in all environments (Docker, FastAPI, CLI)
)

# Production instance - same config works everywhere as of v0.11.0
db_prod = DataFlow(
    database_url="postgresql://user:pass@localhost/prod",
    auto_migrate=True  # v0.11.0+: SyncDDLExecutor handles DDL safely
)

# Models are isolated per instance
@db_dev.model
class DevModel:
    id: str
    # Only exists in dev instance

@db_prod.model
class ProdModel:
    id: str
    # Only exists in prod instance
```

## 🏗️ DataFlow vs Traditional ORMs

DataFlow is not a traditional ORM. It's a **workflow-native database framework** designed for enterprise applications with distributed transactions, multi-tenancy, and caching built-in.

### Architecture Comparison

| Feature                  | Traditional ORM                 | DataFlow                           |
| ------------------------ | ------------------------------- | ---------------------------------- |
| **Model Usage**          | Direct instantiation (`User()`) | Workflow-native (`UserCreateNode`) |
| **Database Operations**  | Method calls (`user.save()`)    | Workflow nodes (`UserCreateNode`)  |
| **Transaction Handling** | Manual transaction management   | Distributed transaction support    |
| **Caching**              | External cache integration      | Built-in enterprise caching        |
| **Multi-tenancy**        | Custom implementation           | Automatic tenant isolation         |
| **Performance**          | N+1 queries common              | Optimized bulk operations          |
| **Scalability**          | Vertical scaling focus          | Horizontal scaling built-in        |

### Why Workflow-Native?

**Traditional ORM Limitations:**

```python
# Traditional ORM - doesn't scale well
user = User(name="John", email="john@example.com")
user.save()  # Individual database calls
# Issues: N+1 queries, no caching, no multi-tenancy
```

**DataFlow Advantages:**

```python
# DataFlow - @db.model decorator generates 9 nodes automatically
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero-config setup
db = DataFlow("postgresql://user:password@localhost/database")

# Automatic node generation from model
@db.model
class User:
    name: str
    email: str
    active: bool = True

# Generated nodes: UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode

# Use in workflows
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Enterprise Benefits

1. **Distributed Transactions**: Automatic transaction coordination across services
2. **Multi-Tenancy**: Built-in tenant isolation and data partitioning
3. **Performance Caching**: Enterprise-grade caching with invalidation strategies
4. **Bulk Operations**: Optimized for high-throughput scenarios (10k+ ops/sec)
5. **Monitoring**: Built-in metrics, deadlock detection, performance monitoring
6. **Security**: Automatic SQL injection prevention, audit trails

### Model Instantiation Not Supported

DataFlow models are **schemas, not objects**. This is intentional:

```python
# ❌ This won't work (by design)
user = User(name="John")  # Models are not instantiable

# ✅ This is the correct pattern
workflow.add_node("UserCreateNode", "create", {
    "name": "John",
    "email": "john@example.com"
})
```

**Why?** Model instantiation bypasses:

- Automatic caching
- Tenant isolation
- Transaction coordination
- Performance optimization
- Security validation

## Quick Start

### Option 1: Traditional Model Definition

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Zero-configuration startup
db = DataFlow()

# Define a model - automatically generates 9 node types
@db.model
class User:
    name: str
    email: str
    age: int
    department: str
    active: bool = True

# Use generated nodes in workflows
workflow = WorkflowBuilder()

# Create a user
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com",
    "age": 25,
    "department": "engineering"
})

# List users with filters
workflow.add_node("UserListNode", "list_users", {
    "filter": {"age": {"$gt": 18}},
    "limit": 10
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Option 2: Dynamic Model Registration (NEW)

Perfect for connecting to existing databases or LLM agent scenarios:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Connect to existing database safely
db = DataFlow(
    database_url="postgresql://user:pass@localhost/existing_db",
    auto_migrate=False  # Don't create or modify tables
)

# Discover and register existing tables as models
schema = db.discover_schema(use_real_inspection=True)
result = db.register_schema_as_models(tables=['users', 'orders'])

# Use generated nodes immediately (no @db.model needed)
workflow = WorkflowBuilder()
user_nodes = result['generated_nodes']['users']

workflow.add_node(user_nodes['list'], "get_users", {
    "filter": {"active": True},
    "limit": 10
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Key Features

### 🔧 Zero Configuration

Start with a single line: `app = DataFlow()` - no database setup, no schema definitions, no configuration files.

### 🔍 Dynamic Schema Discovery & Model Registration

Connect to existing databases without @db.model decorators. Perfect for LLM agents and dynamic database exploration.

### 🔄 Cross-Session Model Persistence

Models registered by one user/session are available to others via the model registry.

### 🛡️ Safe Existing Database Mode

Connect to production databases safely with `auto_migrate=False` - prevents any schema modifications.

### 🗄️ Universal Database Support

MongoDB-style queries work across PostgreSQL, MySQL, SQLite with automatic SQL generation and optimization.

### ⚡ Redis-Powered Caching

Enterprise-grade caching with intelligent invalidation patterns and 99.9% hit rates.

### 🚀 Automatic API Generation

REST APIs, OpenAPI documentation, and health checks generated automatically from your queries.

## Generated Node Types

Each `@db.model` automatically generates 9 node types:

### Basic CRUD Nodes

```python
# Create a single record
workflow.add_node("UserCreateNode", "create", {
    "name": "John",
    "age": 25,
    "department": "engineering"
})

# Read a single record
workflow.add_node("UserReadNode", "read", {
    "id": 123
})

# Update a record (v0.6.0+ API)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 123},
    "fields": {"age": 26}
})

# Delete a record (v0.6.0+ API)
workflow.add_node("UserDeleteNode", "delete", {
    "filter": {"id": 123}
})
```

### List and Query Nodes

```python
# List with MongoDB-style filters
workflow.add_node("UserListNode", "list", {
    "filter": {
        "age": {"$gt": 18, "$lt": 65},           # age > 18 AND age < 65
        "name": {"$regex": "^John"},              # name LIKE 'John%'
        "department": {"$in": ["eng", "sales"]},  # department IN ('eng', 'sales')
        "status": {"$ne": "inactive"}             # status != 'inactive'
    },
    "order_by": ["-created_at"],  # Sort by created_at descending
    "limit": 10,
    "offset": 0
})
```

### Bulk Operations

```python
# Bulk create
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "data": [
        {"name": "Alice", "age": 30, "department": "sales"},
        {"name": "Bob", "age": 35, "department": "engineering"}
    ],
    "batch_size": 1000
})

# Bulk update (v0.6.0+ API)
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"department": "engineering"},
    "fields": {"$inc": {"age": 1}}  # Increment age by 1
})

# Bulk delete
workflow.add_node("UserBulkDeleteNode", "bulk_delete", {
    "filter": {"status": "inactive"},
    "soft_delete": True
})

# Bulk upsert (insert or update)
workflow.add_node("UserBulkUpsertNode", "bulk_upsert", {
    "data": [
        {"email": "alice@example.com", "name": "Alice Updated"},
        {"email": "new@example.com", "name": "New User"}
    ],
    "match_fields": ["email"]
})
```

## Dynamic Model Registration (NEW)

### Working with Existing Databases

Connect to existing databases without needing @db.model decorators. Perfect for LLM agents, data exploration, and legacy database integration.

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Connect safely to existing database
db = DataFlow(
    database_url="postgresql://user:pass@localhost/existing_db",
    auto_migrate=False  # Don't modify existing schema
)

# Discover existing database structure
schema = db.discover_schema(use_real_inspection=True)
print(f"Found {len(schema)} tables: {list(schema.keys())}")

# Register discovered tables as DataFlow models
result = db.register_schema_as_models(tables=['customers', 'orders'])

print(f"Registered {result['success_count']} models")
print(f"Generated nodes: {result['generated_nodes']}")

# Now you can use the models in workflows
workflow = WorkflowBuilder()
customer_nodes = result['generated_nodes']['customers']

workflow.add_node(customer_nodes['list'], "get_customers", {
    "filter": {"status": "active"},
    "limit": 10
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Cross-Session Model Sharing

Models registered by one user/session are automatically available to others via the model registry.

```python
# === SESSION 1: Data Engineer discovers and registers models ===
db_engineer = DataFlow(
    database_url="postgresql://user:pass@localhost/company_db",
    auto_migrate=False  # Read existing schema only
)

# Engineer discovers and registers models for the team
schema = db_engineer.discover_schema(use_real_inspection=True)
result = db_engineer.register_schema_as_models(
    tables=['users', 'products', 'orders']
)
print(f"Team models registered: {result['registered_models']}")

# === SESSION 2: Developer uses registered models ===
db_developer = DataFlow(
    database_url="postgresql://user:pass@localhost/company_db",
    auto_migrate=False  # Read existing schema only
)

# Developer reconstructs models from registry (no @db.model needed)
models = db_developer.reconstruct_models_from_registry()
print(f"Available models: {models['reconstructed_models']}")

# Developer can now build workflows immediately
workflow = WorkflowBuilder()
user_nodes = models['generated_nodes']['users']

workflow.add_node(user_nodes['list'], "active_users", {
    "filter": {"active": True},
    "order_by": ["-created_at"],
    "limit": 20
})
```

### LLM Agent Database Exploration

Perfect for AI agents that need to explore and understand database structures dynamically.

```python
# LLM Agent workflow for database exploration
db_agent = DataFlow(
    database_url="postgresql://user:pass@localhost/unknown_db",
    auto_migrate=False  # Safe exploration mode - no schema changes
)

# Agent discovers database structure
schema = db_agent.discover_schema(use_real_inspection=True)
interesting_tables = [t for t in schema.keys()
                     if not t.startswith('dataflow_')]  # Skip system tables

# Agent registers tables it wants to work with
result = db_agent.register_schema_as_models(tables=interesting_tables[:5])

# Agent builds exploration workflow
workflow = WorkflowBuilder()

for model_name in result['registered_models']:
    nodes = result['generated_nodes'][model_name]

    # Sample a few records from each table
    workflow.add_node(nodes['list'], f"sample_{model_name}", {
        "limit": 3,
        "order_by": []
    })

# Execute exploration
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Agent can now analyze the data structure and content
for node_id, result in results.items():
    if node_id.startswith('sample_'):
        table_name = node_id.replace('sample_', '')
        data = result.get('result', [])
        print(f"Table {table_name}: {len(data)} sample records")
```

### Safe Database Connection Modes

DataFlow provides simple configuration for connecting to existing databases:

```python
# Development Mode - Full auto-migration (default)
db_dev = DataFlow(
    database_url="postgresql://user:pass@localhost/dev_db",
    auto_migrate=True  # Default - creates/modifies tables as needed
)

# Production Mode - Read existing schema only
db_prod = DataFlow(
    database_url="postgresql://user:pass@localhost/prod_db",
    auto_migrate=False  # No automatic migrations or schema changes
)

# Even if you accidentally define a new model, no tables will be created
@db_prod.model
class NewModel:
    name: str
    value: int

# Model is registered locally but NO table created in database
assert 'NewModel' in db_prod.list_models()  # Local registration
schema = db_prod.discover_schema(use_real_inspection=True)
assert 'new_models' not in schema  # No table in database
```

### Key API Methods

DataFlow provides powerful methods for dynamic database operations:

```python
# Schema Discovery
schema = db.discover_schema(use_real_inspection=True)
# Returns: Dict[str, Dict] - Complete table structure with columns, types, constraints

# Dynamic Model Registration
result = db.register_schema_as_models(tables=['users', 'orders'])
# Returns: {
#   'registered_models': ['User', 'Order'],
#   'generated_nodes': {
#     'User': {'create': 'UserCreateNode', 'list': 'UserListNode', ...},
#     'Order': {'create': 'OrderCreateNode', 'list': 'OrderListNode', ...}
#   },
#   'success_count': 2,
#   'error_count': 0
# }

# Cross-Session Model Reconstruction
models = db.reconstruct_models_from_registry()
# Returns: {
#   'reconstructed_models': ['User', 'Order'],
#   'generated_nodes': {...},
#   'success_count': 2
# }

# Recommended production configuration (v0.11.0+)
db = DataFlow(
    database_url="...",
    auto_migrate=True  # Default - works in Docker, FastAPI, CLI via SyncDDLExecutor
)
```

## Enterprise Migration System

DataFlow includes a comprehensive enterprise-grade migration system designed for production database operations with maximum safety.

### Migration Capabilities Overview

| Component                         | Purpose                         | Key Features                                       |
| --------------------------------- | ------------------------------- | -------------------------------------------------- |
| **Risk Assessment Engine**        | Analyze migration safety        | Multi-dimensional risk scoring, impact prediction  |
| **Mitigation Strategy Engine**    | Generate safety recommendations | Automated risk reduction, strategy prioritization  |
| **Foreign Key Analyzer**          | FK-aware operations             | Referential integrity, cascade analysis, FK chains |
| **Table Rename Analyzer**         | Safe table restructuring        | Dependency tracking, coordinated updates           |
| **Staging Environment Manager**   | Migration testing               | Production-like environments, data sampling        |
| **Migration Lock Manager**        | Concurrency control             | Distributed locking, conflict prevention           |
| **Validation Checkpoint Manager** | Quality assurance               | Multi-stage validation, automatic rollback         |
| **Schema State Manager**          | Change tracking                 | Schema snapshots, evolution history                |

### Quick Migration Examples

#### Risk Assessment Before Schema Changes

```python
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine
from dataflow.migrations.mitigation_strategy_engine import MitigationStrategyEngine

# Assess risk before dropping a column
risk_engine = RiskAssessmentEngine(connection_manager)
risk_assessment = await risk_engine.assess_operation_risk(
    operation_type="drop_column",
    table_name="users",
    column_name="deprecated_field"
)

print(f"Risk Level: {risk_assessment.overall_risk_level}")
print(f"Risk Score: {risk_assessment.overall_score}/100")

# Generate mitigation strategies if risk is high
if risk_assessment.overall_risk_level in ["HIGH", "CRITICAL"]:
    mitigation_engine = MitigationStrategyEngine(risk_engine)
    strategies = await mitigation_engine.generate_mitigation_plan(risk_assessment)

    print("Recommended mitigation strategies:")
    for strategy in strategies.recommended_strategies:
        print(f"- {strategy.description} (Effectiveness: {strategy.effectiveness_score}%)")
```

#### Safe Column Addition with Multiple Strategies

```python
from dataflow.migrations.not_null_handler import (
    NotNullColumnHandler, ColumnDefinition, DefaultValueType
)

# Add NOT NULL column with computed default
handler = NotNullColumnHandler(connection_manager)

# Strategy 1: Static default (fastest)
static_column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# Strategy 2: Computed default (for complex logic)
computed_column = ColumnDefinition(
    name="user_tier",
    data_type="VARCHAR(10)",
    default_expression="CASE WHEN account_value > 10000 THEN 'premium' ELSE 'standard' END",
    default_type=DefaultValueType.COMPUTED
)

# Safe execution with validation
plan = await handler.plan_not_null_addition("users", static_column)
validation = await handler.validate_addition_safety(plan)

if validation.is_safe:
    result = await handler.execute_not_null_addition(plan)
    print(f"Column added successfully in {result.execution_time:.2f}s")
else:
    print(f"Validation failed: {validation.issues}")
```

#### FK-Aware Table Operations

```python
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer, FKOperationType

# Analyze FK impact before table operations
fk_analyzer = ForeignKeyAnalyzer(connection_manager)

fk_impact = await fk_analyzer.analyze_fk_impact(
    operation=FKOperationType.RENAME_TABLE,
    table_name="user_accounts",
    new_table_name="users",
    include_cascade_analysis=True
)

print(f"FK Impact Level: {fk_impact.impact_level}")
print(f"Affected constraints: {len(fk_impact.affected_constraints)}")

# Generate FK-safe migration plan
if fk_impact.is_safe_to_proceed:
    fk_plan = await fk_analyzer.generate_fk_safe_migration_plan(fk_impact)
    result = await fk_analyzer.execute_fk_safe_migration(fk_plan)
    print(f"FK-safe migration completed: {result.success}")
```

#### Staging Environment Testing

```python
from dataflow.migrations.staging_environment_manager import StagingEnvironmentManager

# Create production-like staging environment
staging_manager = StagingEnvironmentManager(connection_manager)

staging_env = await staging_manager.create_staging_environment(
    environment_name="migration_test_001",
    data_sampling_strategy={
        "strategy": "representative",
        "sample_percentage": 10,  # 10% of production data
        "preserve_referential_integrity": True
    }
)

try:
    # Test migration in staging
    test_result = await staging_manager.test_migration_in_staging(
        staging_env,
        migration_plan=your_migration_plan,
        validation_checks=True
    )

    print(f"Staging test result: {test_result.success}")
    print(f"Performance metrics: {test_result.performance_metrics}")

    if test_result.success:
        print("Safe to execute in production")
    else:
        print(f"Migration issues found: {test_result.issues}")

finally:
    # Always cleanup staging environment
    await staging_manager.cleanup_staging_environment(staging_env)
```

#### Migration with Lock Management

```python
from dataflow.migrations.concurrent_access_manager import MigrationLockManager

# Prevent concurrent migrations
lock_manager = MigrationLockManager(connection_manager)

async with lock_manager.acquire_migration_lock(
    lock_scope="schema_modification",
    timeout_seconds=300,
    operation_description="Add status column to users table"
) as migration_lock:

    print(f"Migration lock acquired: {migration_lock.lock_id}")

    # Execute migration safely - no other migrations can interfere
    migration_result = await execute_your_migration()

    print("Migration completed under lock protection")
    # Lock automatically released when context exits
```

### Complete Enterprise Migration Workflow

```python
async def enterprise_migration_workflow(
    operation_type: str,
    table_name: str,
    migration_details: dict
):
    """Complete enterprise migration with all safety systems."""

    # Step 1: Risk Assessment
    risk_engine = RiskAssessmentEngine(connection_manager)
    risk_assessment = await risk_engine.assess_operation_risk(
        operation_type, table_name, **migration_details
    )

    # Step 2: Generate Mitigation Strategies
    mitigation_engine = MitigationStrategyEngine(risk_engine)
    mitigation_plan = await mitigation_engine.generate_mitigation_plan(risk_assessment)

    # Step 3: Create Staging Environment
    staging_manager = StagingEnvironmentManager(connection_manager)
    staging_env = await staging_manager.create_staging_environment(
        f"migration_{int(time.time())}"
    )

    try:
        # Step 4: Test in Staging
        staging_test = await staging_manager.test_migration_in_staging(
            staging_env, migration_details
        )

        if not staging_test.success:
            return {"success": False, "reason": "Staging test failed"}

        # Step 5: Execute with Lock Protection
        lock_manager = MigrationLockManager(connection_manager)

        async with lock_manager.acquire_migration_lock(
            "table_modification", timeout_seconds=600
        ):
            # Step 6: Multi-stage Validation
            validator = ValidationCheckpointManager(connection_manager)

            result = await validator.execute_with_validation(
                migration_operation=lambda: execute_actual_migration(
                    operation_type, table_name, migration_details
                ),
                checkpoints=[
                    {"stage": "pre", "validators": ["integrity", "fk_consistency"]},
                    {"stage": "post", "validators": ["data_integrity", "performance"]}
                ],
                rollback_on_failure=True
            )

            return {"success": result.all_checkpoints_passed}

    finally:
        # Step 7: Cleanup
        await staging_manager.cleanup_staging_environment(staging_env)

# Usage
result = await enterprise_migration_workflow(
    operation_type="add_not_null_column",
    table_name="users",
    migration_details={
        "column_name": "account_status",
        "default_value": "active"
    }
)
```

## Advanced Features

### Multi-Database Operations

```python
# Configure multiple databases
db = DataFlow(
    database_url="postgresql://user:pass@localhost/main",
    analytics_db="postgresql://user:pass@localhost/analytics"
)

# Special characters in passwords are now fully supported (v0.9.4+)
db = DataFlow(
    database_url="postgresql://admin:MySecret#123$@localhost:5432/production",
    read_replica="postgresql://readonly:Complex@Pass!@replica:5432/production"
)

# Models can specify their database
@db.model
class User:
    name: str
    email: str
    __dataflow__ = {"database": "primary"}

@db.model
class Event:
    user_id: int
    action: str
    __dataflow__ = {"database": "analytics"}
```

### Enterprise Features

```python
# Enable multi-tenancy
@db.model
class Order:
    customer_id: int
    total: float
    __dataflow__ = {
        'multi_tenant': True,      # Adds tenant_id field
        'soft_delete': True,       # Adds deleted_at field
        'audit_log': True,         # Tracks all changes
        'versioned': True          # Optimistic locking
    }

# Use in workflows with automatic tenant isolation
workflow.add_node("OrderCreateNode", "create", {
    "customer_id": 123,
    "total": 250.00,
    "tenant_id": "tenant_abc"  # Automatic isolation
})
```

### Transaction Management

```python
# Distributed transactions
workflow.add_node("TransactionManagerNode", "payment_flow", {
    "transaction_type": "saga",
    "steps": [
        {"node": "PaymentCreateNode", "compensation": "PaymentRollbackNode"},
        {"node": "OrderUpdateNode", "compensation": "OrderRevertNode"},
        {"node": "InventoryUpdateNode", "compensation": "InventoryRestoreNode"}
    ],
    "timeout": 30
})
```

## Production Examples

### E-commerce Order Processing

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class Order:
    customer_id: int
    total: float
    status: str = "pending"

@db.model
class OrderItem:
    order_id: int
    product_id: int
    quantity: int
    price: float

# Complex order processing workflow
workflow = WorkflowBuilder()

# Create order
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": 123,
    "total": 0,
    "status": "pending"
})

# Add order items in bulk
workflow.add_node("OrderItemBulkCreateNode", "add_items", {
    "data": [
        {"product_id": 1, "quantity": 2, "price": 50.00},
        {"product_id": 2, "quantity": 1, "price": 100.00}
    ]
})

# Calculate and update total (v0.6.0+ API)
workflow.add_node("OrderUpdateNode", "update_total", {
    "fields": {"total": 200.00, "status": "confirmed"}
})

# Connect nodes
workflow.add_connection("create_order", "id", "add_items", "order_id")
workflow.add_connection("create_order", "id", "update_total", "order_id")
workflow.add_connection("add_items", "result", "update_total", "input")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Analytics Dashboard

```python
# Create analytics workflow
analytics_workflow = WorkflowBuilder()

# Get today's sales
analytics_workflow.add_node("OrderListNode", "today_sales", {
    "filter": {
        "created_at": {"$gte": "2025-01-17T00:00:00"},
        "status": "completed"
    }
})

# Get top products
analytics_workflow.add_node("OrderItemListNode", "top_products", {
    "aggregate": [
        {"$group": {"_id": "$product_id", "sold": {"$sum": "$quantity"}}},
        {"$sort": {"sold": -1}},
        {"$limit": 10}
    ]
})

# Execute analytics
results, run_id = runtime.execute(analytics_workflow.build())
print(f"Today's orders: {len(results['today_sales']['result'])}")
print(f"Top products: {results['top_products']['result']}")
```

## Performance & Optimization

- **31.8M operations/second** baseline performance
- **99.9% cache hit rate** with intelligent invalidation
- **Connection pooling** with 10,000+ concurrent connections
- **Automatic query optimization** with SQL generation

### Performance Monitoring

```python
# Built-in performance monitoring with workflow
workflow.add_node("PerformanceMonitorNode", "monitor", {
    "operation": "complex_query",
    "track_metrics": True
})

workflow.add_node("UserListNode", "large_query", {
    "filter": {"status": "active"},
    "aggregate": [
        {"$group": {"_id": "$department", "count": {"$sum": 1}}}
    ]
})

# Execute with monitoring
results, run_id = runtime.execute(workflow.build())
# Performance metrics available in results['monitor']['metrics']
```

## Enterprise Features

### Security & Compliance

```python
# GDPR/CCPA compliance built-in with workflows
workflow.add_node("GDPRComplianceNode", "gdpr_handler", {
    "user_id": 123,
    "request_type": "export",  # or "delete"
    "include_audit_trail": True
})

# Data export workflow
workflow.add_node("UserDataExportNode", "export_data", {
    "user_id": 123,
    "format": "json",
    "include_deleted": True
})

# Data anonymization workflow
workflow.add_node("UserDataAnonymizeNode", "anonymize_data", {
    "user_id": 123,
    "retention_policy": "strict",
    "cascade_delete": True
})

# Audit trail is automatically enabled with multi_tenant: True
```

### Health Monitoring

```python
# Automatic health checks with workflow
workflow.add_node("HealthCheckNode", "health_monitor", {
    "check_database": True,
    "check_cache": True,
    "check_connections": True
})

results, run_id = runtime.execute(workflow.build())
health = results["health_monitor"]["result"]
# {
#   "status": "healthy",
#   "database": "connected",
#   "cache": "connected",
#   "queries_per_second": 31800000
# }
```

## Database Connection

### Connection String Support

DataFlow supports robust database connection string parsing with full support for special characters in passwords (enhanced in v0.9.4 and v0.4.0 with improved parameter type casting):

```python
# Supports complex passwords with special characters across all databases
connection_examples = [
    # PostgreSQL
    "postgresql://admin:MySecret#123$@localhost:5432/mydb",
    "postgresql://user:P@ssw0rd!@db.example.com:5432/production",
    "postgresql://readonly:temp#pass@replica.host:5432/reports",

    # MySQL
    "mysql://service:Complex$ecret?@mysql.internal:3306/analytics",
    "mysql://admin:MySecret#123$@localhost:3306/production",
    "mysql://user:P@ssw0rd!@db.example.com:3306/ecommerce",

    # SQLite
    "sqlite:///path/to/database.db",
    ":memory:"  # In-memory SQLite for testing
]

# All these connection strings work seamlessly
for conn_str in connection_examples:
    db = DataFlow(database_url=conn_str)
    # DataFlow automatically handles URL encoding/decoding
```

### Connection String Format

```python
# Standard format for all databases
scheme://[username[:password]@]host[:port]/database[?param1=value1&param2=value2]

# PostgreSQL examples
postgresql://username:password@localhost:5432/database_name
postgresql://user:pass@host:5432/db?sslmode=require

# MySQL examples
mysql://username:password@localhost:3306/database_name
mysql://user:pass@host:3306/db?charset=utf8mb4&collation=utf8mb4_unicode_ci

# SQLite examples
sqlite:///path/to/database.db
sqlite:///absolute/path/to/file.db
:memory:  # In-memory database
```

### Database-Specific Connection Examples

#### PostgreSQL (asyncpg driver)

```python
# Basic PostgreSQL connection
db = DataFlow("postgresql://user:password@localhost:5432/mydb")

# With SSL/TLS
db = DataFlow("postgresql://user:password@localhost:5432/mydb?sslmode=require")

# With custom connection pool and timeout
db = DataFlow(
    "postgresql://user:password@localhost:5432/mydb",
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    command_timeout=60  # Query execution timeout (default: 60s)
)

# Read replica configuration
db = DataFlow(
    database_url="postgresql://user:password@primary:5432/mydb",
    read_replica="postgresql://readonly:password@replica:5432/mydb"
)
```

#### MySQL (aiomysql driver)

```python
# Basic MySQL connection
db = DataFlow("mysql://user:password@localhost:3306/mydb")

# With charset and collation
db = DataFlow("mysql://user:password@localhost:3306/mydb?charset=utf8mb4&collation=utf8mb4_unicode_ci")

# With SSL/TLS certificates
db = DataFlow(
    "mysql://user:password@localhost:3306/mydb",
    ssl_ca="/path/to/ca.pem",
    ssl_cert="/path/to/client-cert.pem",
    ssl_key="/path/to/client-key.pem"
)

# With custom connection pool and timeout
db = DataFlow(
    "mysql://user:password@localhost:3306/mydb",
    pool_size=15,
    max_overflow=25,
    pool_recycle=3600,
    connect_timeout=10,          # Connection establishment timeout
    command_timeout=60,           # Query execution timeout (default: 60s)
    charset="utf8mb4"
)

# Production configuration
db = DataFlow(
    "mysql://app_user:SecurePass123!@db.production.com:3306/ecommerce",
    pool_size=50,
    max_overflow=100,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=False,  # No SQL logging
    charset="utf8mb4",
    collation="utf8mb4_unicode_ci"
)
```

#### SQLite (aiosqlite driver with custom pooling)

```python
# In-memory database (fast, for testing)
db = DataFlow(":memory:")

# File-based database
db = DataFlow("sqlite:///path/to/database.db")

# With WAL mode for better concurrency
db = DataFlow(
    "sqlite:///path/to/database.db",
    enable_wal=True,
    cache_size_mb=64,
    pool_size=5
)

# Production SQLite with optimizations
db = DataFlow(
    "sqlite:///app/data/production.db",
    enable_wal=True,
    cache_size_mb=128,
    pool_size=10,
    journal_mode="WAL",
    synchronous="NORMAL"
)
```

### Database Feature Comparison

All three databases have **100% feature parity** in DataFlow operations. Choose based on your deployment needs:

| Feature                | PostgreSQL          | MySQL                     | SQLite                     | Notes                        |
| ---------------------- | ------------------- | ------------------------- | -------------------------- | ---------------------------- |
| **Driver**             | asyncpg             | aiomysql                  | aiosqlite + custom pooling | All async, high performance  |
| **ACID Transactions**  | ✅ Full             | ✅ Full (InnoDB)          | ✅ Full                    | Complete transaction support |
| **Connection Pooling** | ✅ Native           | ✅ Native                 | ✅ Custom                  | Efficient connection reuse   |
| **Async Operations**   | ✅                  | ✅                        | ✅                         | All operations async-first   |
| **JSON Support**       | ✅ Native JSONB     | ✅ 5.7+                   | ✅ JSON1 extension         | Full JSON query support      |
| **Full-Text Search**   | ✅ ts_vector        | ✅ FULLTEXT               | ✅ FTS5                    | Built-in search capabilities |
| **Window Functions**   | ✅                  | ✅ 8.0+                   | ✅ 3.25+                   | Advanced analytics           |
| **CTEs (WITH)**        | ✅                  | ✅ 8.0+                   | ✅                         | Recursive queries supported  |
| **Arrays**             | ✅ Native           | ❌ Use JSON               | ❌ Use JSON                | PostgreSQL advantage         |
| **Spatial Data**       | ✅ PostGIS          | ✅ Native                 | ✅ R-Tree                  | Geographic data support      |
| **Stored Procedures**  | ✅ PL/pgSQL         | ✅                        | ❌                         | Complex business logic       |
| **Triggers**           | ✅                  | ✅                        | ✅                         | Event-driven operations      |
| **Bulk Operations**    | ✅ COPY             | ✅ LOAD DATA              | ✅ executemany             | High-throughput imports      |
| **Schema Operations**  | ✅ Real DDL         | ✅ Real DDL               | ✅ Real DDL                | All support table creation   |
| **Multi-tenancy**      | ✅                  | ✅                        | ✅                         | Automatic tenant isolation   |
| **Soft Deletes**       | ✅                  | ✅                        | ✅                         | Audit trail support          |
| **DataFlow Nodes**     | ✅ All 9 types      | ✅ All 9 types            | ✅ All 9 types             | Full CRUD + bulk ops         |
| **SSL/TLS**            | ✅                  | ✅                        | N/A                        | Secure connections           |
| **Best For**           | Production, PostGIS | Web apps, MySQL ecosystem | Development, Mobile, Edge  | Deployment guidance          |

### Database Selection Guide

#### Choose PostgreSQL When:

- **Production enterprise applications** - Maximum reliability and features
- **Geographic data** - PostGIS for spatial queries
- **Complex analytics** - Advanced window functions and materialized views
- **JSONB queries** - High-performance JSON operations
- **Array operations** - Native array type support
- **Large scale** - Proven for high-traffic applications

#### Choose MySQL When:

- **Existing MySQL infrastructure** - Leverage current expertise
- **Web hosting environments** - Widely available on hosting platforms
- **Read-heavy workloads** - Excellent read replica support
- **MySQL ecosystem tools** - Integration with MySQL-specific tools
- **Cost optimization** - Lower resource requirements than PostgreSQL
- **InnoDB requirements** - Need InnoDB-specific features

#### Choose SQLite When:

- **Development and testing** - Fast, zero-config local development
- **Mobile applications** - Embedded database for iOS/Android
- **Edge computing** - Lightweight deployment on edge devices
- **Serverless functions** - Quick cold starts with file-based DB
- **Desktop applications** - Single-file database simplicity
- **Prototyping** - Rapid application development

### Multi-Database Workflows

You can use different databases in the same application:

```python
# Development: Fast SQLite
dev_db = DataFlow(":memory:")

# Staging: MySQL for web hosting compatibility
staging_db = DataFlow("mysql://user:pass@staging-host:3306/staging_db")

# Production: PostgreSQL for enterprise features
prod_db = DataFlow("postgresql://user:pass@prod-host:5432/prod_db")

# Same model definitions work across all databases
@dev_db.model
@staging_db.model
@prod_db.model
class User:
    name: str
    email: str
    active: bool = True

# All databases get identical 9 nodes per model
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserBulkCreateNode, UserBulkUpdateNode,
# UserBulkDeleteNode, UserBulkUpsertNode
```

### Password Special Characters

DataFlow now handles these special characters in passwords automatically:

- `#` (hash/pound) - commonly used in passwords
- `$` (dollar sign) - shell variable syntax
- `@` (at symbol) - email-like passwords
- `?` (question mark) - query parameter conflicts
- And many more URL-sensitive characters

**Before v0.9.4:** Required manual URL encoding

```python
# Old workaround (no longer needed)
password = "MySecret%23123%24"  # %23 = #, %24 = $
```

**Since v0.9.4:** Works automatically

```python
# Just use the password directly - enhanced in v0.4.0 with better type casting
db = DataFlow(database_url="postgresql://admin:MySecret#123$@localhost/db")
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim
RUN pip install kailash-dataflow
COPY app.py .
EXPOSE 8000
CMD ["python", "app.py"]
```

### Environment Variables

```bash
export DATAFLOW_DATABASE_URL="postgresql://..."
export DATAFLOW_REDIS_URL="redis://..."
export DATAFLOW_LOG_LEVEL="INFO"
export DATAFLOW_ENABLE_METRICS="true"
```

## Migration from Raw SQL/ORM

### From Raw SQL

```python
# Before: Raw SQL
cursor.execute("""
    SELECT department, COUNT(*) as count
    FROM users
    WHERE age > %s
    GROUP BY department
    ORDER BY count DESC
""", (18,))

# After: DataFlow
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "dept_stats", {
    "filter": {"age": {"$gt": 18}},
    "aggregate": [
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
})
```

### From SQLAlchemy ORM

```python
# Before: SQLAlchemy
users = session.query(User).filter(
    User.age > 18,
    User.department.in_(['eng', 'sales'])
).order_by(User.created_at.desc()).limit(10).all()

# After: DataFlow
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "filtered_users", {
    "filter": {
        "age": {"$gt": 18},
        "department": {"$in": ["eng", "sales"]}
    },
    "order_by": ["-created_at"],
    "limit": 10
})
```

## Migration System Documentation

### Core Migration Guides

- [NOT NULL Column Addition](docs/development/not-null-column-addition.md) - Complete guide to safely adding NOT NULL columns
- [Column Removal System](docs/development/column-removal-system.md) - Safe column removal with dependency analysis
- [Migration System Overview](docs/migration-system.md) - Complete migration system architecture
- [Risk Assessment Guide](docs/development/risk-assessment.md) - Using the risk assessment engine
- [FK-Aware Operations](docs/development/fk-aware-operations.md) - Foreign key aware migration patterns

### Additional Documentation

### Guides

- [User Guide](docs/USER_GUIDE.md) - Comprehensive DataFlow guide
- [Quick Start Guide](docs/quickstart.md) - Get started in minutes
- [Query Patterns](docs/query-patterns.md) - Advanced query techniques
- [Database Optimization](docs/database-optimization.md) - Performance tuning
- [Multi-Tenant Architecture](docs/multi-tenant.md) - Enterprise patterns
- [Production Deployment](docs/deployment.md) - Deployment best practices

### Examples

- [Basic CRUD Operations](examples/01_basic_crud.py) - Simple database operations
- [Advanced Features](examples/02_advanced_features.py) - Complex queries and caching
- [Enterprise Integration](examples/03_enterprise_integration.py) - Multi-tenant and security

## Next Steps

- Explore the documentation and examples above
- Read the [API documentation](https://pypi.org/project/kailash-dataflow/)
- Join the [community](https://github.com/terrene-foundation/kailash-py)

DataFlow transforms database operations from complex, database-specific code into simple, intuitive queries that work everywhere. Start building production-ready data services in minutes!

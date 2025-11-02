---
name: dataflow
description: "Kailash DataFlow - zero-config database framework with automatic model-to-node generation. Use when asking about 'database operations', 'DataFlow', 'database models', 'CRUD operations', 'bulk operations', 'database queries', 'database migrations', 'multi-tenancy', 'multi-instance', 'database transactions', 'PostgreSQL', 'MySQL', 'SQLite', 'MongoDB', 'pgvector', 'vector search', 'document database', 'RAG', 'semantic search', 'existing database', 'database performance', 'database deployment', 'database testing', or 'TDD with databases'. DataFlow is NOT an ORM - it generates 11 workflow nodes per SQL model, 8 nodes for MongoDB, and 3 nodes for vector operations."
---

# Kailash DataFlow - Zero-Config Database Framework

DataFlow is a zero-config database framework built on Kailash Core SDK that automatically generates workflow nodes from database models.

## Overview

DataFlow transforms database models into workflow nodes automatically, providing:

- **Automatic Node Generation**: 11 nodes per model (@db.model decorator)
- **Multi-Database Support**: PostgreSQL, MySQL, SQLite (SQL) + MongoDB (Document) + pgvector (Vector Search)
- **Enterprise Features**: Multi-tenancy, multi-instance isolation, transactions
- **Zero Configuration**: String IDs preserved, deferred schema operations
- **Integration Ready**: Works with Nexus for multi-channel deployment
- **Specialized Adapters**: SQL (11 nodes/model), Document (8 nodes), Vector (3 nodes)

## ⚠️ Critical Updates & Bug Fixes

### v0.7.11 Bulk Operations Parameter Handling (LATEST - 2025-10-31)

**Bug Fix:**
- ✅ **Parameter Conflict Resolution**: Fixed `TypeError: got multiple values for keyword argument 'model_name'` in all 4 bulk operations when workflows have global input parameters

**What Was Fixed:**
Bulk operations (BulkCreate, BulkUpdate, BulkDelete, BulkUpsert) now correctly filter `model_name` and `db_instance` from kwargs before passing to internal methods, preventing parameter conflicts when global workflow inputs are present.

**Impact:**
- All bulk operations work correctly with Nexus/AsyncLocalRuntime global parameters
- No breaking changes - existing workflows continue working unchanged

**Upgrade Command:**
```bash
pip install --upgrade kailash-dataflow>=0.7.11
```

---

### v0.7.9 CountNode + PostgreSQL ARRAY + Auto-Query Caching (2025-10-30)

**New Features:**
- ✅ **CountNode**: 11th auto-generated node for efficient COUNT(*) queries (10-50x faster than ListNode)
- ✅ **PostgreSQL Native Arrays**: TEXT[], INTEGER[], REAL[] support with 2-10x performance gain
- ✅ **Auto-Query Caching**: Redis auto-detection with in-memory LRU fallback for 5-10x throughput

**CountNode Usage:**
```python
workflow.add_node("UserCountNode", "count_users", {"filter": {"active": True}})
# Returns: {"count": 42} in 1-5ms vs 20-50ms with ListNode
```

**PostgreSQL ARRAY Usage:**
```python
@db.model
class AgentMemory:
    tags: List[str]  # Becomes TEXT[] on PostgreSQL
    __dataflow__ = {'use_native_arrays': True}  # Opt-in
```

**Auto-Query Caching:**
- Redis auto-detection on startup
- Automatic in-memory LRU fallback if Redis unavailable
- 5-10x throughput improvement for repeated queries

**Upgrade Command:**
```bash
pip install --upgrade kailash-dataflow>=0.7.9
```

---

### v0.7.3 Schema Cache + Migration Fixes (2025-10-26)

**Performance Improvement:**
- ✅ **Schema Cache**: Thread-safe table existence cache for 91-99% performance improvement
- ✅ **Cache Metrics**: Observable metrics for monitoring cache performance
- ✅ **Automatic Management**: Configurable TTL, size limits, LRU eviction

**Bug Fixes:**
- ✅ **Async-Safe Migration**: Fixed migration recording in FastAPI/async contexts
- ✅ **Error Messages**: Enhanced error messages with contextual help

---

### v0.7.0 Bulk Operations Fixes (2025-10-24)

**8 Critical bugs fixed in bulk operations:**

1. **BUG-001**: BulkUpsertNode silent INSERT failure (CRITICAL) - Fixed in v0.7.0
2. **BUG-002**: Parameter serialization (conflict_fields) - Fixed in v0.7.0
3. **BUG-003**: BulkCreateNode count reporting - Fixed in v0.7.0
4. **BUG-004**: BulkUpsertNode UPDATE not working - Fixed in v0.7.0
5. **BUG-005**: BulkDeleteNode $in operator not converting to SQL IN - Fixed in v0.7.0
6. **BUG-006**: BulkUpdateNode $in operator not converting to SQL IN - Fixed in v0.7.0
7. **BUG-007**: Empty $in list causes SQL syntax error - Fixed in v0.7.0
8. **BUG-008**: Empty $nin list not handled - Fixed in v0.7.0

**Key Fixes:**
- ✅ **UPDATE Operations**: BulkUpsertNode now correctly updates existing records using PostgreSQL `xmax` detection
- ✅ **MongoDB Operators**: All bulk operations support `$in`, `$nin`, `$gt`, `$gte`, `$lt`, `$lte`, `$ne`
- ✅ **Empty List Handling**: `{"id": {"$in": []}}` now works correctly (matches nothing)
- ✅ **Code Quality**: 160 lines eliminated via shared helper function

**Test Coverage**: 57/57 tests passing (100%)

**Upgrade Command:**
```bash
pip install --upgrade kailash-dataflow>=0.7.0
```

---

### v0.6.2-v0.6.3 Truthiness Bug Pattern (FIXED)
Two critical bugs caused by Python truthiness checks on empty dicts:

**v0.6.2 - ListNode Filter Operators:**
- **Bug:** `if filter_dict:` at nodes.py:1810 evaluated to False for empty dict {}
- **Impact:** ALL MongoDB-style filter operators ($ne, $nin, $in, $not) were broken
- **Fix:** Changed to `if "filter" in kwargs:`
- **Result:** All filter operators now work correctly

**v0.6.3 - BulkDeleteNode Safe Mode:**
- **Bug:** `not filter_conditions` at bulk_delete.py:177 evaluated to True for empty dict {}
- **Impact:** Safe mode incorrectly rejected valid empty filter operations
- **Fix:** Changed to `"filter" not in validated_inputs`
- **Result:** Consistent validation logic

### Pattern to Avoid
❌ **NEVER use truthiness checks on filter/data parameters:**
```python
if filter_dict:  # BAD - empty dict {} is falsy!
if not filter_dict:  # BAD - empty dict {} is falsy!
```

✅ **ALWAYS use key existence checks:**
```python
if "filter" in kwargs:  # GOOD
if "filter" not in validated_inputs:  # GOOD
```

### Affected Versions
- ❌ v0.5.4 - v0.6.1: Broken filter operators
- ✅ v0.6.2+: All filter operators work correctly
- ✅ v0.6.3+: BulkDelete safe mode fixed
- ✅ v0.7.0+: All bulk operations fully functional with MongoDB operators

## 🛠️ Developer Experience Tools (v0.8.0)

### Build-Time Validation: Catch Errors Early
**Validation Modes**: OFF, WARN (default), STRICT

Catch 80% of configuration errors at model registration time (not runtime):

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

# Default: Warn mode (backward compatible)
@db.model
class User:
    id: int  # Validates: primary key named 'id'
    name: str
    email: str

# Strict mode: Raises errors on validation failures
@db.model(strict=True)
class Product:
    id: int
    name: str
    price: float

# Skip validation (advanced users)
@db.model(skip_validation=True)
class Advanced:
    custom_pk: int  # Custom primary key allowed
```

**Validation Checks**:
- **VAL-002**: Missing primary key (error)
- **VAL-003**: Primary key not named 'id' (warning)
- **VAL-004**: Composite primary key (warning)
- **VAL-005**: Auto-managed field conflicts (created_at, updated_at)
- **VAL-006**: DateTime without timezone
- **VAL-007**: String/Text without length
- **VAL-008**: camelCase field names (should be snake_case)
- **VAL-009**: SQL reserved words as field names
- **VAL-010**: Missing delete cascade in relationships

**When to Use Each Mode**:
- **OFF**: Legacy code migration, custom implementations
- **WARN** (default): Development, catches issues without blocking
- **STRICT**: Production deployments, enforce standards

---

### ErrorEnhancer: Actionable Error Messages

Automatic error enhancement with context, root causes, and solutions:

```python
from dataflow import DataFlow
from dataflow.core.error_enhancer import ErrorEnhancer

db = DataFlow("postgresql://...")

# ErrorEnhancer automatically integrated into DataFlow engine
# Enhanced errors show:
# - Error code (DF-101, DF-102, etc.)
# - Context (node, parameters, workflow state)
# - Root causes with probability scores
# - Actionable solutions with code templates
# - Documentation links

try:
    # Missing parameter error
    workflow.add_node("UserCreateNode", "create", {})
except Exception as e:
    # ErrorEnhancer automatically catches and enriches
    # Shows: DF-101 with specific fixes
    pass
```

**Key Features**:
- **40+ Error Codes**: DF-101 (missing parameter) through DF-805 (runtime errors)
- **Pattern Matching**: Automatic error detection and classification
- **Contextual Solutions**: Code templates with variable substitution
- **Color-Coded Output**: Emojis and formatting for readability
- **Documentation Links**: Direct links to relevant guides

**Common Errors Covered**:
- DF-101: Missing required parameter
- DF-102: Type mismatch (expected dict, got str)
- DF-103: Auto-managed field conflict (created_at, updated_at)
- DF-104: Wrong node pattern (CreateNode vs UpdateNode)
- DF-105: Primary key 'id' missing/wrong name
- DF-201: Invalid connection - source output not found
- DF-301: Migration failed - table already exists

**See**: `sdk-users/apps/dataflow/troubleshooting/top-10-errors.md`

---

### Inspector API: Self-Service Debugging

Introspection API for workflows, nodes, connections, and parameters:

```python
from dataflow.platform.inspector import Inspector

inspector = Inspector(dataflow_instance)
inspector.workflow_obj = workflow.build()

# Connection Analysis
connections = inspector.connections()  # List all connections
broken = inspector.find_broken_connections()  # Find issues
validation = inspector.validate_connections()  # Check validity

# Parameter Tracing
trace = inspector.trace_parameter("create_user", "data")
print(f"Source: {trace.source_node}")
dependencies = inspector.parameter_dependencies("create_user")

# Node Analysis
deps = inspector.node_dependencies("create_user")  # Upstream
dependents = inspector.node_dependents("create_user")  # Downstream
order = inspector.execution_order()  # Topological sort

# Workflow Validation
report = inspector.workflow_validation_report()
if not report['is_valid']:
    print(f"Errors: {report['errors']}")
    print(f"Warnings: {report['warnings']}")
    print(f"Suggestions: {report['suggestions']}")

# High-Level Overview
summary = inspector.workflow_summary()
metrics = inspector.workflow_metrics()
```

**Inspector Methods** (18 total):
- **Connection Analysis** (5): connections(), connection_chain(), connection_graph(), validate_connections(), find_broken_connections()
- **Parameter Tracing** (5): trace_parameter(), parameter_flow(), find_parameter_source(), parameter_dependencies(), parameter_consumers()
- **Node Analysis** (5): node_dependencies(), node_dependents(), execution_order(), node_schema(), compare_nodes()
- **Workflow Analysis** (3): workflow_summary(), workflow_metrics(), workflow_validation_report()

**Use Cases**:
- Diagnose "missing parameter" errors
- Find broken connections
- Trace parameter flow through workflows
- Validate workflows before execution
- Generate workflow documentation
- Debug complex workflows

**Performance**: <1ms per method call (cached operations)

---

### CLI Tools: Industry-Standard Workflow Validation

Command-line tools matching pytest/mypy patterns for workflow validation and debugging:

```bash
# Validate workflow structure and connections
dataflow-validate workflow.py --output text
dataflow-validate workflow.py --fix  # Auto-fix common issues
dataflow-validate workflow.py --output json > report.json

# Analyze workflow metrics and complexity
dataflow-analyze workflow.py --verbosity 2
dataflow-analyze workflow.py --format json

# Generate reports and documentation
dataflow-generate workflow.py report --output-dir ./reports
dataflow-generate workflow.py diagram  # ASCII workflow diagram
dataflow-generate workflow.py docs --output-dir ./docs

# Debug workflows with breakpoints
dataflow-debug workflow.py --breakpoint create_user
dataflow-debug workflow.py --inspect-node create_user
dataflow-debug workflow.py --step  # Step-by-step execution

# Profile performance and detect bottlenecks
dataflow-perf workflow.py --bottlenecks
dataflow-perf workflow.py --recommend
dataflow-perf workflow.py --format json > perf.json
```

**CLI Commands** (5 total):
- **dataflow-validate**: Validate workflow structure, connections, and parameters with --fix flag
- **dataflow-analyze**: Workflow metrics, complexity analysis, and execution order
- **dataflow-generate**: Generate reports, diagrams (ASCII), and documentation
- **dataflow-debug**: Interactive debugging with breakpoints and node inspection
- **dataflow-perf**: Performance profiling, bottleneck detection, and recommendations

**Use Cases**:
- CI/CD integration for workflow validation
- Pre-deployment validation checks
- Performance profiling and optimization
- Documentation generation
- Interactive debugging sessions

**Performance**: Industry-standard CLI tool performance (<100ms startup)

---

### Common Pitfalls Guide
**New**: Comprehensive guides for common DataFlow mistakes

**CreateNode vs UpdateNode** (saves 1-2 hours):
- Side-by-side comparison
- Decision tree for node selection
- 10+ working examples
- Common mistakes and fixes
- **See**: `sdk-users/apps/dataflow/guides/create-vs-update.md`

**Top 10 Errors** (saves 30-120 minutes per error):
- Quick fix guide for 90% of issues
- Error code reference (DF-101 through DF-805)
- Diagnosis decision tree
- Prevention checklist
- Inspector commands for debugging
- **See**: `sdk-users/apps/dataflow/troubleshooting/top-10-errors.md`

---

## Quick Start

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize DataFlow
db = DataFlow(connection_string="postgresql://user:pass@localhost/db")

# Define model (generates 11 nodes automatically)
@db.model
class User:
    id: str  # String IDs preserved
    name: str
    email: str

# Use generated nodes in workflows
workflow = WorkflowBuilder()
workflow.add_node("User_Create", "create_user", {
    "data": {"name": "John", "email": "john@example.com"}
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
user_id = results["create_user"]["result"]  # Access pattern
```

## Reference Documentation

### Getting Started
- **[dataflow-quickstart](dataflow-quickstart.md)** - Quick start guide and core concepts
- **[dataflow-installation](dataflow-installation.md)** - Installation and setup
- **[dataflow-models](dataflow-models.md)** - Defining models with @db.model decorator
- **[dataflow-connection-config](dataflow-connection-config.md)** - Database connection configuration

### Core Operations
- **[dataflow-crud-operations](dataflow-crud-operations.md)** - Create, Read, Update, Delete operations
- **[dataflow-queries](dataflow-queries.md)** - Query patterns and filtering
- **[dataflow-bulk-operations](dataflow-bulk-operations.md)** - Batch operations for performance
- **[dataflow-transactions](dataflow-transactions.md)** - Transaction management
- **[dataflow-connection-isolation](dataflow-connection-isolation.md)** - ⚠️ CRITICAL: Connection isolation and ACID guarantees
- **[dataflow-result-access](dataflow-result-access.md)** - Accessing results from nodes

### Advanced Features
- **[dataflow-multi-instance](dataflow-multi-instance.md)** - Multiple database instances
- **[dataflow-multi-tenancy](dataflow-multi-tenancy.md)** - Multi-tenant architectures
- **[dataflow-existing-database](dataflow-existing-database.md)** - Working with existing databases
- **[dataflow-migrations-quick](dataflow-migrations-quick.md)** - Database migrations
- **[dataflow-custom-nodes](dataflow-custom-nodes.md)** - Creating custom database nodes
- **[dataflow-performance](dataflow-performance.md)** - Performance optimization

### Integration & Deployment
- **[dataflow-nexus-integration](dataflow-nexus-integration.md)** - Deploying with Nexus platform
- **[dataflow-deployment](dataflow-deployment.md)** - Production deployment patterns
- **[dataflow-dialects](dataflow-dialects.md)** - Supported database dialects
- **[dataflow-monitoring](dataflow-monitoring.md)** - Monitoring and observability

### Testing & Quality
- **[dataflow-tdd-mode](dataflow-tdd-mode.md)** - Test-driven development with DataFlow
- **[dataflow-tdd-api](dataflow-tdd-api.md)** - Testing API for DataFlow
- **[dataflow-tdd-best-practices](dataflow-tdd-best-practices.md)** - Testing best practices
- **[dataflow-compliance](dataflow-compliance.md)** - Compliance and standards

### Troubleshooting & Debugging
- **[create-vs-update guide](../../../sdk-users/apps/dataflow/guides/create-vs-update.md)** - CreateNode vs UpdateNode comprehensive guide
- **[top-10-errors](../../../sdk-users/apps/dataflow/troubleshooting/top-10-errors.md)** - Quick fix guide for 90% of issues
- **[dataflow-gotchas](dataflow-gotchas.md)** - Common pitfalls and solutions
- **ErrorEnhancer**: Automatic error enhancement (integrated in DataFlow engine)
- **Inspector API**: Self-service debugging (18 introspection methods)
- **CLI Tools**: Industry-standard command-line validation and debugging tools (5 commands)

## Key Concepts

### Not an ORM
DataFlow is **NOT an ORM**. It's a workflow framework that:
- Generates workflow nodes from models
- Operates within Kailash's workflow execution model
- Uses string-based result access patterns
- Integrates seamlessly with other workflow nodes

### Automatic Node Generation
Each `@db.model` class generates **11 nodes**:
1. `{Model}_Create` - Create single record
2. `{Model}_Read` - Read by ID
3. `{Model}_Update` - Update record
4. `{Model}_Delete` - Delete record
5. `{Model}_List` - List with filters
6. `{Model}_Upsert` - Insert or update (atomic)
7. `{Model}_Count` - Efficient COUNT(*) queries
8. `{Model}_BulkCreate` - Bulk insert
9. `{Model}_BulkUpdate` - Bulk update
10. `{Model}_BulkDelete` - Bulk delete
11. `{Model}_BulkUpsert` - Bulk upsert

### Critical Rules
- ✅ String IDs preserved (no UUID conversion)
- ✅ Deferred schema operations (safe for Docker/FastAPI)
- ✅ Multi-instance isolation (one DataFlow per database)
- ✅ Result access: `results["node_id"]["result"]`
- ❌ NEVER use direct SQL when DataFlow nodes exist
- ❌ NEVER use SQLAlchemy/Django ORM alongside DataFlow

### Database Support
- **SQL Databases**: PostgreSQL, MySQL, SQLite (11 nodes per @db.model)
- **Document Database**: MongoDB with flexible schema (8 specialized nodes)
- **Vector Search**: PostgreSQL pgvector for RAG/AI (3 vector nodes)
- **100% Feature Parity**: SQL databases support identical workflows

## When to Use This Skill

Use DataFlow when you need to:
- Perform database operations in workflows
- Generate CRUD APIs automatically (with Nexus)
- Implement multi-tenant systems
- Work with existing databases
- Build database-first applications
- Handle bulk data operations
- Implement enterprise data management

## Integration Patterns

### With Nexus (Multi-Channel)
```python
from dataflow import DataFlow
from nexus import Nexus

db = DataFlow(connection_string="...")
@db.model
class User:
    id: str
    name: str

# Auto-generates API + CLI + MCP
nexus = Nexus(db.get_workflows())
nexus.run()  # Instant multi-channel platform
```

### With Core SDK (Custom Workflows)
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow(connection_string="...")
# Use db-generated nodes in custom workflows
workflow = WorkflowBuilder()
workflow.add_node("User_Create", "user1", {...})
```

## Version Compatibility

- **Current Version**: 0.7.11 (Bulk operations parameter handling fix)
- **Core SDK Version**: 0.9.25+
- **Python**: 3.8+
- **v0.7.11**: Bulk operations parameter conflict fix (model_name/db_instance filtering)
- **v0.7.9**: CountNode (11th node) + PostgreSQL native arrays + auto-query caching
- **v0.7.3**: Schema cache (91-99% faster) + async-safe migrations
- **v0.7.0**: Bulk operations fixes (8 critical bugs)
- **v0.6.3**: BulkDeleteNode safe mode validation fix
- **v0.6.2**: ListNode filter operators fix ($ne, $nin, $in, $not)
- **v0.6.0**: MongoDB document database + PostgreSQL pgvector support
- **Architecture**: BaseAdapter hierarchy with SQL, Document, and Vector adapters

## Multi-Database Support Matrix

### SQL Databases (DatabaseAdapter)
- **PostgreSQL**: Full support with advanced features (asyncpg driver, pgvector extension, native arrays)
- **MySQL**: Full support with 100% feature parity (aiomysql driver)
- **SQLite**: Full support for development/testing/mobile (aiosqlite + custom pooling)
- **Nodes Generated**: 11 per @db.model (Create, Read, Update, Delete, List, Upsert, Count, BulkCreate, BulkUpdate, BulkDelete, BulkUpsert)

### Document Databases (MongoDBAdapter)
- **MongoDB**: Complete NoSQL support (Motor async driver)
- **Features**: Flexible schema, aggregation pipelines, text search, geospatial queries
- **Workflow Nodes**: 8 specialized nodes (DocumentInsert, DocumentFind, DocumentUpdate, DocumentDelete, BulkDocumentInsert, Aggregate, CreateIndex, DocumentCount)
- **Use Cases**: E-commerce catalogs, content management, user profiles, event logs

### Vector Databases (PostgreSQLVectorAdapter)
- **PostgreSQL pgvector**: Semantic similarity search for RAG/AI (pgvector extension)
- **Features**: Cosine/L2/inner product distance, HNSW/IVFFlat indexes
- **Workflow Nodes**: 3 vector nodes (VectorSearch, VectorInsert, VectorUpdate)
- **Use Cases**: RAG applications, semantic search, recommendation engines

### Architecture
- **BaseAdapter**: Minimal interface for all adapter types (adapter_type, database_type, health_check)
- **DatabaseAdapter**: SQL-specific (inherits BaseAdapter)
- **MongoDBAdapter**: Document database (inherits BaseAdapter)
- **PostgreSQLVectorAdapter**: Vector operations (inherits DatabaseAdapter)

### Planned Extensions
- **TimescaleDB**: Time-series data optimization (PostgreSQL extension)
- **Qdrant/Milvus**: Dedicated vector databases with advanced filtering
- **Redis**: Caching and key-value operations
- **Neo4j**: Graph database with Cypher queries

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core workflow patterns
- **[03-nexus](../nexus/SKILL.md)** - Multi-channel deployment
- **[04-kaizen](../kaizen/SKILL.md)** - AI agent integration
- **[17-gold-standards](../../17-gold-standards/SKILL.md)** - Best practices

## Support

For DataFlow-specific questions, invoke:
- `dataflow-specialist` - DataFlow implementation and patterns
- `testing-specialist` - DataFlow testing strategies (NO MOCKING policy)
- `framework-advisor` - Choose between Core SDK and DataFlow

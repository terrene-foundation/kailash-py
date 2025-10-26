---
name: dataflow
description: "Kailash DataFlow - zero-config database framework with automatic model-to-node generation. Use when asking about 'database operations', 'DataFlow', 'database models', 'CRUD operations', 'bulk operations', 'database queries', 'database migrations', 'multi-tenancy', 'multi-instance', 'database transactions', 'PostgreSQL', 'MySQL', 'SQLite', 'MongoDB', 'pgvector', 'vector search', 'document database', 'RAG', 'semantic search', 'existing database', 'database performance', 'database deployment', 'database testing', or 'TDD with databases'. DataFlow is NOT an ORM - it generates 9 workflow nodes per SQL model, 8 nodes for MongoDB, and 3 nodes for vector operations."
---

# Kailash DataFlow - Zero-Config Database Framework

DataFlow is a zero-config database framework built on Kailash Core SDK that automatically generates workflow nodes from database models.

## Overview

DataFlow transforms database models into workflow nodes automatically, providing:

- **Automatic Node Generation**: 9 nodes per model (@db.model decorator)
- **Multi-Database Support**: PostgreSQL, MySQL, SQLite (SQL) + MongoDB (Document) + pgvector (Vector Search)
- **Enterprise Features**: Multi-tenancy, multi-instance isolation, transactions
- **Zero Configuration**: String IDs preserved, deferred schema operations
- **Integration Ready**: Works with Nexus for multi-channel deployment
- **Specialized Adapters**: SQL (9 nodes/model), Document (8 nodes), Vector (3 nodes)

## ⚠️ Critical Updates & Bug Fixes

### v0.7.3 Schema Cache + Migration Fixes (LATEST - 2025-10-26)

**Performance Improvement:**
- ✅ **Schema Cache**: Thread-safe table existence cache for 91-99% performance improvement
- ✅ **Cache Metrics**: Observable metrics for monitoring cache performance
- ✅ **Automatic Management**: Configurable TTL, size limits, LRU eviction

**Bug Fixes:**
- ✅ **Async-Safe Migration**: Fixed migration recording in FastAPI/async contexts
- ✅ **Error Messages**: Enhanced error messages with contextual help

**Performance Impact:**
- First operation: ~1500ms (cache miss - migration check)
- Cached operations: ~1ms (cache hit)
- Multi-operation workflows: 91-99% faster

**Upgrade Command:**
```bash
pip install --upgrade kailash-dataflow>=0.7.3
```

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

## Quick Start

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Initialize DataFlow
db = DataFlow(connection_string="postgresql://user:pass@localhost/db")

# Define model (generates 9 nodes automatically)
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

### Troubleshooting
- **[dataflow-gotchas](dataflow-gotchas.md)** - Common pitfalls and solutions

## Key Concepts

### Not an ORM
DataFlow is **NOT an ORM**. It's a workflow framework that:
- Generates workflow nodes from models
- Operates within Kailash's workflow execution model
- Uses string-based result access patterns
- Integrates seamlessly with other workflow nodes

### Automatic Node Generation
Each `@db.model` class generates **9 nodes**:
1. `{Model}_Create` - Create single record
2. `{Model}_Read` - Read by ID
3. `{Model}_Update` - Update record
4. `{Model}_Delete` - Delete record
5. `{Model}_List` - List with filters
6. `{Model}_BulkCreate` - Bulk insert
7. `{Model}_BulkUpdate` - Bulk update
8. `{Model}_BulkDelete` - Bulk delete
9. `{Model}_Count` - Count records

### Critical Rules
- ✅ String IDs preserved (no UUID conversion)
- ✅ Deferred schema operations (safe for Docker/FastAPI)
- ✅ Multi-instance isolation (one DataFlow per database)
- ✅ Result access: `results["node_id"]["result"]`
- ❌ NEVER use direct SQL when DataFlow nodes exist
- ❌ NEVER use SQLAlchemy/Django ORM alongside DataFlow

### Database Support
- **SQL Databases**: PostgreSQL, MySQL, SQLite (9 nodes per @db.model)
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

- **Current Version**: 0.7.3 (Schema cache + migration fixes)
- **Core SDK Version**: 0.9.25+
- **Python**: 3.8+
- **v0.7.3**: Schema cache (91-99% faster) + async-safe migrations
- **v0.7.0**: Bulk operations fixes (8 critical bugs)
- **v0.6.3**: BulkDeleteNode safe mode validation fix
- **v0.6.2**: ListNode filter operators fix ($ne, $nin, $in, $not)
- **v0.6.0**: MongoDB document database + PostgreSQL pgvector support
- **Architecture**: BaseAdapter hierarchy with SQL, Document, and Vector adapters

## Multi-Database Support Matrix

### SQL Databases (DatabaseAdapter)
- **PostgreSQL**: Full support with advanced features (asyncpg driver, pgvector extension)
- **MySQL**: Full support with 100% feature parity (aiomysql driver)
- **SQLite**: Full support for development/testing/mobile (aiosqlite + custom pooling)
- **Nodes Generated**: 9 per @db.model (Create, Read, Update, Delete, List, BulkCreate, BulkUpdate, BulkDelete, Count)

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

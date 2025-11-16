---
name: dataflow
description: "Kailash DataFlow - zero-config database framework with automatic model-to-node generation. Use when asking about 'database operations', 'DataFlow', 'database models', 'CRUD operations', 'bulk operations', 'database queries', 'database migrations', 'multi-tenancy', 'multi-instance', 'database transactions', 'PostgreSQL', 'MySQL', 'SQLite', 'MongoDB', 'pgvector', 'vector search', 'document database', 'RAG', 'semantic search', 'existing database', 'database performance', 'database deployment', 'database testing', or 'TDD with databases'. DataFlow is NOT an ORM - it generates 11 workflow nodes per SQL model, 8 nodes for MongoDB, and 3 nodes for vector operations."
---

# Kailash DataFlow - Zero-Config Database Framework

DataFlow is a zero-config database framework built on Kailash Core SDK that automatically generates workflow nodes from database models.

## Features

DataFlow transforms database models into workflow nodes automatically, providing:

- **Automatic Node Generation**: 11 nodes per SQL model via @db.model decorator (Create, Read, Update, Delete, List, Upsert, Count, BulkCreate, BulkUpdate, BulkDelete, BulkUpsert)
- **Multi-Database Support**: PostgreSQL, MySQL, SQLite (SQL) + MongoDB (Document) + pgvector (Vector Search)
- **Enterprise Features**: Multi-tenancy, multi-instance isolation, ACID transactions
- **String ID Preservation**: No automatic UUID conversion
- **Deferred Schema Operations**: Safe for Docker/FastAPI deployments
- **Integration Ready**: Works seamlessly with Nexus for multi-channel deployment
- **Developer Experience Tools**: Build-time validation, error enhancement, inspector API, CLI tools
- **Performance Optimization**: Query caching, connection pooling, native PostgreSQL arrays
- **NOT an ORM**: Generates workflow nodes that integrate with Kailash execution model

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
- **[dataflow-connection-isolation](dataflow-connection-isolation.md)** - Connection isolation and ACID guarantees
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

### Developer Tools
- **[create-vs-update guide](../../../sdk-users/apps/dataflow/guides/create-vs-update.md)** - CreateNode vs UpdateNode comprehensive guide
- **[top-10-errors](../../../sdk-users/apps/dataflow/troubleshooting/top-10-errors.md)** - Quick fix guide for 90% of issues
- **[dataflow-gotchas](dataflow-gotchas.md)** - Common pitfalls and solutions

## Key Concepts

### Not an ORM
DataFlow is **NOT an ORM**. It's a workflow framework that:
- Generates workflow nodes from models
- Operates within Kailash's workflow execution model
- Uses string-based result access patterns
- Integrates seamlessly with other workflow nodes

### Automatic Node Generation
Each `@db.model` class generates **11 SQL nodes** or **8 MongoDB nodes**:

**SQL Nodes (11 per model)**:
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

**MongoDB Nodes (8 per model)**:
- DocumentInsert, DocumentFind, DocumentUpdate, DocumentDelete
- BulkDocumentInsert, Aggregate, CreateIndex, DocumentCount

**Vector Nodes (3 for pgvector)**:
- VectorSearch, VectorInsert, VectorUpdate

### Build-Time Validation
Catch 80% of configuration errors at model registration time:

**Validation Modes**: OFF, WARN (default), STRICT
- VAL-002: Missing primary key
- VAL-003: Primary key not named 'id' (warning)
- VAL-004: Composite primary key (warning)
- VAL-006: DateTime without timezone
- VAL-007: String/Text without length
- VAL-009: SQL reserved words as field names

### Developer Experience Tools

**ErrorEnhancer**: Automatic error enrichment with:
- 40+ error codes (DF-101 through DF-805)
- Contextual solutions with code templates
- Color-coded output with documentation links
- Pattern matching for automatic classification

**Inspector API**: Self-service debugging with 18 introspection methods:
- Connection analysis (5 methods)
- Parameter tracing (5 methods)
- Node analysis (5 methods)
- Workflow validation (3 methods)

**CLI Tools**: Industry-standard command-line tools:
- `dataflow-validate` - Workflow validation with --fix flag
- `dataflow-analyze` - Metrics and complexity analysis
- `dataflow-generate` - Reports, diagrams, documentation
- `dataflow-debug` - Interactive debugging
- `dataflow-perf` - Performance profiling

### Database Support Matrix

**SQL Databases** (11 nodes per model):
- PostgreSQL: Full support with advanced features (asyncpg, pgvector, native arrays)
- MySQL: Full support with 100% feature parity (aiomysql)
- SQLite: Full support for development/testing/mobile (aiosqlite)

**Document Database** (8 nodes):
- MongoDB: Complete NoSQL support with flexible schema (Motor async driver)

**Vector Database** (3 nodes):
- PostgreSQL pgvector: Semantic similarity search for RAG/AI

## Critical Rules

- ✅ String IDs preserved (no UUID conversion)
- ✅ Deferred schema operations (safe for Docker/FastAPI)
- ✅ Multi-instance isolation (one DataFlow per database)
- ✅ Result access: `results["node_id"]["result"]`
- ✅ Use build-time validation (WARN or STRICT mode)
- ❌ NEVER use direct SQL when DataFlow nodes exist
- ❌ NEVER use SQLAlchemy/Django ORM alongside DataFlow
- ❌ NEVER use attribute access: `results["node_id"].result`

## When to Use This Skill

Use DataFlow when you need to:
- Perform database operations in workflows
- Generate CRUD APIs automatically (with Nexus)
- Implement multi-tenant systems
- Work with existing databases
- Build database-first applications
- Handle bulk data operations
- Implement enterprise data management
- Create RAG applications with vector search

## Integration Patterns

### With Nexus (Multi-Channel CRUD API)
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

### With Kaizen (Data-Driven Agents)
```python
from kaizen.core.base_agent import BaseAgent
from dataflow import DataFlow

class DataAgent(BaseAgent):
    def __init__(self, config, db: DataFlow):
        self.db = db
        super().__init__(config=config, signature=MySignature())
```

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

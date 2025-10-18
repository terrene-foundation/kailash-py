---
name: dataflow
description: "Kailash DataFlow - zero-config database framework with automatic model-to-node generation. Use when asking about 'database operations', 'DataFlow', 'database models', 'CRUD operations', 'bulk operations', 'database queries', 'database migrations', 'multi-tenancy', 'multi-instance', 'database transactions', 'PostgreSQL', 'SQLite', 'existing database', 'database performance', 'database deployment', 'database testing', or 'TDD with databases'. DataFlow is NOT an ORM - it generates 9 workflow nodes per model automatically."
---

# Kailash DataFlow - Zero-Config Database Framework

DataFlow is a zero-config database framework built on Kailash Core SDK that automatically generates workflow nodes from database models.

## Overview

DataFlow transforms database models into workflow nodes automatically, providing:

- **Automatic Node Generation**: 9 nodes per model (@db.model decorator)
- **Multi-Database Support**: PostgreSQL, SQLite, and more dialects
- **Enterprise Features**: Multi-tenancy, multi-instance isolation, transactions
- **Zero Configuration**: String IDs preserved, deferred schema operations
- **Integration Ready**: Works with Nexus for multi-channel deployment

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
- **PostgreSQL**: Full support with advanced features
- **SQLite**: Full support for development/testing
- **MySQL**: Supported via dialects
- **Other**: Check dialect compatibility

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

- **Current Version**: 0.5.4+
- **Core SDK Version**: 0.9.25+
- **Python**: 3.8+

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

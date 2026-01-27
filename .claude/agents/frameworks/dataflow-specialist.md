---
name: dataflow-specialist
description: Zero-config database framework specialist for Kailash DataFlow implementation (v0.10.15+). Use proactively when implementing database operations, bulk data processing, or enterprise data management with automatic node generation.
---

# DataFlow Specialist Agent

## Role
Zero-config database framework specialist for Kailash DataFlow implementation (v0.10.15+). Use proactively when implementing database operations, bulk data processing, or enterprise data management with automatic node generation.

> **v0.10.15 Update**: `auto_migrate=True` now works correctly in Docker/FastAPI environments using `SyncDDLExecutor` (psycopg2/sqlite3 for synchronous DDL operations). No event loop issues!
>
> **Note**: `existing_schema_mode` and `enable_model_persistence` parameters still exist but are rarely needed. The simple `auto_migrate=True` (default) handles most use cases.

## Skills Quick Reference

**IMPORTANT**: For common DataFlow queries, use Agent Skills for instant answers.

### Quick Start
- "DataFlow setup?" -> [`dataflow-quickstart`](../../skills/02-dataflow/dataflow-quickstart.md)
- "Basic CRUD?" -> [`dataflow-crud-operations`](../../skills/02-dataflow/dataflow-crud-operations.md)
- "Model definition?" -> [`dataflow-models`](../../skills/02-dataflow/dataflow-models.md)

### Common Operations
- "Query patterns?" -> [`dataflow-queries`](../../skills/02-dataflow/dataflow-queries.md)
- "Bulk operations?" -> [`dataflow-bulk-operations`](../../skills/02-dataflow/dataflow-bulk-operations.md)
- "Transactions?" -> [`dataflow-transactions`](../../skills/02-dataflow/dataflow-transactions.md)
- "Connection isolation?" -> [`dataflow-connection-isolation`](../../skills/02-dataflow/dataflow-connection-isolation.md)
- "Fast CRUD? db.express?" -> [`dataflow-express`](../../skills/02-dataflow/dataflow-express.md) (~23x FASTER)

### Advanced Topics
- "Async lifecycle (DF-501)?" -> [`dataflow-async-lifecycle`](../../skills/02-dataflow/dataflow-async-lifecycle.md)
- "CLI commands?" -> [`dataflow-cli-commands`](../../skills/02-dataflow/dataflow-cli-commands.md)
- "PostgreSQL arrays?" -> [`dataflow-native-arrays`](../../skills/02-dataflow/dataflow-native-arrays.md)
- "Schema cache?" -> [`dataflow-schema-cache`](../../skills/02-dataflow/dataflow-schema-cache.md)
- "Enterprise migrations?" -> [`dataflow-enterprise-migrations`](../../skills/02-dataflow/dataflow-enterprise-migrations.md)
- "Troubleshooting?" -> [`dataflow-troubleshooting`](../../skills/02-dataflow/dataflow-troubleshooting.md)

### Integration
- "With Nexus?" -> [`dataflow-nexus-integration`](../../skills/02-dataflow/dataflow-nexus-integration.md)
- "Migration guide?" -> [`dataflow-migrations-quick`](../../skills/02-dataflow/dataflow-migrations-quick.md)

## Primary Responsibilities

### Use This Subagent When:
- **Enterprise Migrations**: Complex schema migrations with risk assessment
- **Multi-Tenant Architecture**: Designing tenant isolation strategies
- **Performance Optimization**: Database-level tuning beyond basic queries
- **Custom Integrations**: Integrating DataFlow with external systems

### Use Skills Instead When:
- Basic CRUD operations -> Use `dataflow-crud-operations` Skill
- Simple queries -> Use `dataflow-queries` Skill
- Model setup -> Use `dataflow-models` Skill
- Nexus integration -> Use `dataflow-nexus-integration` Skill
- Fast db.express operations -> Use `dataflow-express` Skill

## DataFlow Quick Config Reference

> **DataFlow v0.10.15+**: `auto_migrate=True` now works correctly in Docker/FastAPI environments using `SyncDDLExecutor`. The deprecated parameters (`enable_model_persistence`, `skip_registry`, `skip_migration`, `existing_schema_mode`) have been removed.

| Use Case | Config | Notes |
|----------|--------|-------|
| **Development** | `auto_migrate=True` (default) | Safe, automatic schema creation |
| **Production** | `auto_migrate=True` | Same config works in Docker/FastAPI |
| **With Nexus** | `auto_migrate=True` + `Nexus(auto_discovery=False)` | Deferred schema operations |

### Test Mode (v0.7.10+)
| Use Case | Config |
|----------|--------|
| Auto-detection | `db = DataFlow("postgresql://...")` |
| Explicit enable | `db = DataFlow("postgresql://...", test_mode=True)` |
| Global enable | `DataFlow.enable_test_mode()` |

### Logging (v0.10.12+)
| Preset | Use Case |
|--------|----------|
| `LoggingConfig.production()` | Clean logs, WARNING+ |
| `LoggingConfig.development()` | Verbose, DEBUG |
| `LoggingConfig.quiet()` | ERROR only |

## CRITICAL LEARNINGS - Top 5 Gotchas

### 1. NEVER Manually Set Timestamp Fields (DF-104)

DataFlow automatically manages `created_at` and `updated_at`. Setting them causes:
```
DatabaseError: multiple assignments to same column "updated_at"
```

```python
# WRONG
data["updated_at"] = datetime.now()  # CAUSES DF-104!

# CORRECT
data.pop("updated_at", None)
data.pop("created_at", None)
# DataFlow handles timestamps automatically
```

### 2. Primary Key MUST Be Named `id`

```python
# WRONG
@db.model
class User:
    user_id: str  # FAILS - DataFlow requires 'id'

# CORRECT
@db.model
class User:
    id: str  # Must be exactly 'id'
```

### 3. CreateNode vs UpdateNode Parameter Patterns

```python
# CreateNode: FLAT fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-001",
    "name": "Alice"
})

# UpdateNode: NESTED filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-001"},
    "fields": {"name": "Alice Updated"}
})
```

### 4. Template Syntax is `${}` NOT `{{}}`

```python
# WRONG - causes validation errors
"id": "{{input.user_id}}"

# CORRECT
"id": "${input.user_id}"
```

### 5. Result Keys by Node Type

| Node Type | Result Key | Access Pattern |
|-----------|------------|----------------|
| ListNode | `records` | `results["list"]["records"]` |
| CountNode | `count` | `results["count"]["count"]` |
| ReadNode | (direct) | `results["read"]` -> dict or None |
| UpsertNode | `record`, `created` | `results["upsert"]["record"]` |

## Core Expertise Summary

### DataFlow Architecture
- **Not an ORM**: Workflow-native database framework
- **PostgreSQL + MySQL + SQLite**: Full parity across databases
- **11 Nodes Per Model** (v0.8.0+):
  - CRUD: CreateNode, ReadNode, UpdateNode, DeleteNode
  - Query: ListNode, CountNode
  - Advanced: UpsertNode
  - Bulk: BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode

### Key Features
- **ExpressDataFlow** (v0.10.6+): ~23x faster CRUD via `db.express`
- **Schema Cache** (v0.7.3+): 91-99% performance improvement
- **ErrorEnhancer** (v0.8.0+): Rich DF-XXX error codes
- **Debug Agent** (v0.8.0+): 50+ patterns, 60+ solutions
- **Inspector** (v0.8.0+): Workflow introspection and debugging
- **PostgreSQL Native Arrays** (v0.8.0+): 2-10x faster with TEXT[], INTEGER[], REAL[]

### Framework Positioning
**Choose DataFlow When:**
- Database-first applications requiring CRUD
- Need automatic node generation (@db.model)
- Bulk data processing (10k+ ops/sec)
- Multi-tenant SaaS applications
- Enterprise data management

**Don't Choose DataFlow When:**
- Simple single-workflow tasks (use Core SDK)
- Multi-channel platform needs (use Nexus)
- No database operations required

## Enterprise Migration Overview

DataFlow includes an 8-component enterprise migration system. See [`dataflow-enterprise-migrations`](../../skills/02-dataflow/dataflow-enterprise-migrations.md) for complete details.

### Migration Decision Matrix

| Migration Type | Risk Level | Required Tools |
|---------------|------------|----------------|
| Add nullable column | LOW | Basic validation |
| Add NOT NULL column | MEDIUM | NotNullHandler |
| Drop column | HIGH | DependencyAnalyzer + RiskEngine |
| Rename table | CRITICAL | TableRenameAnalyzer + FK analysis |
| Drop table | CRITICAL | All migration systems |

### Core Decision Matrix

| Need | Use |
|------|-----|
| Simple CRUD | Basic nodes |
| Bulk import | BulkCreateNode |
| Complex queries | ListNode + MongoDB filters |
| Existing database | `auto_migrate=True` (v0.10.15+ auto-detects) |
| Schema changes | Enterprise migration system |
| Risk assessment | RiskAssessmentEngine |

## Key Rules

### Always
- Use PostgreSQL for production, SQLite for development
- Use `auto_migrate=True` (works in Docker/FastAPI as of v0.10.15+)
- Use bulk operations for >100 records
- Use connections for dynamic values
- Follow 3-tier testing with real infrastructure
- Perform risk assessment for production schema changes
- Test high-risk migrations in staging environments

### Never
- Manually set `created_at` or `updated_at` fields
- Instantiate models directly (`User()`)
- Use `{{}}` template syntax (use `${}`)
- Use mocking in Tier 2-3 tests
- Skip risk assessment for HIGH/CRITICAL migrations
- Execute schema changes without dependency analysis

## Documentation Quick Links

### Primary Documentation
- [DataFlow README](../../sdk-users/apps/dataflow/README.md)
- [Complete Documentation](../../sdk-users/apps/dataflow/docs/)

### Nexus Integration (v0.10.15+)
```python
# Production-ready pattern (auto_migrate=True now works in Docker/FastAPI)
db = DataFlow(
    database_url="postgresql://...",
    auto_migrate=True,  # v0.10.15+: Works in Docker/FastAPI via SyncDDLExecutor
)

app = Nexus(api_port=8000, auto_discovery=False)  # Deferred schema operations
```

See: [`dataflow-nexus-integration`](../../skills/02-dataflow/dataflow-nexus-integration.md)

### Core SDK Integration
- All DataFlow nodes are Kailash nodes
- Use in standard WorkflowBuilder patterns
- Compatible with all SDK features

## Skill Files for Deep Dives

| Topic | Skill File |
|-------|------------|
| Async Lifecycle (DF-501) | [`dataflow-async-lifecycle`](../../skills/02-dataflow/dataflow-async-lifecycle.md) |
| CLI Commands | [`dataflow-cli-commands`](../../skills/02-dataflow/dataflow-cli-commands.md) |
| PostgreSQL Arrays | [`dataflow-native-arrays`](../../skills/02-dataflow/dataflow-native-arrays.md) |
| Schema Cache | [`dataflow-schema-cache`](../../skills/02-dataflow/dataflow-schema-cache.md) |
| Enterprise Migrations | [`dataflow-enterprise-migrations`](../../skills/02-dataflow/dataflow-enterprise-migrations.md) |
| Troubleshooting | [`dataflow-troubleshooting`](../../skills/02-dataflow/dataflow-troubleshooting.md) |
| Debug Agent | [`dataflow-debug-agent`](../../skills/02-dataflow/dataflow-debug-agent.md) |
| Inspector | [`dataflow-inspector`](../../skills/02-dataflow/dataflow-inspector.md) |
| Strict Mode | [`dataflow-strict-mode`](../../skills/02-dataflow/dataflow-strict-mode.md) |
| Express API | [`dataflow-express`](../../skills/02-dataflow/dataflow-express.md) |
| TDD Mode | [`dataflow-tdd-mode`](../../skills/02-dataflow/dataflow-tdd-mode.md) |

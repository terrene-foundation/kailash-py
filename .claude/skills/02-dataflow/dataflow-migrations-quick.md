---
name: dataflow-migrations-quick
description: "DataFlow automatic migrations and schema changes. Use when DataFlow migration, auto_migrate, schema changes, add column, or migration basics."
---

# DataFlow Migrations Quick Start

Automatic schema migrations with safety controls for development and production.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-models`](#), [`dataflow-existing-database`](#)
> Related Subagents: `dataflow-specialist` (complex migrations, production safety)

> **DataFlow v0.11.0 Update**: `auto_migrate=True` now works correctly in Docker/async environments using `SyncDDLExecutor` (psycopg2/sqlite3 for synchronous DDL). The previous workaround of using `auto_migrate=False` + `create_tables_async()` is **OBSOLETE**.

## Quick Reference

- **Development**: `auto_migrate=True` (default) - safe, preserves data
- **Docker/async**: `auto_migrate=True` - works correctly as of v0.10.15+
- **Production**: `auto_migrate=True` - same pattern for all environments
- **Enterprise**: Full migration system with risk assessment for complex operations
- **Safety**: auto_migrate ALWAYS preserves existing data, adds new columns safely

## Core Pattern

```python
from dataflow import DataFlow

db_dev = DataFlow(
    database_url="sqlite:///dev.db",
    auto_migrate=True  # Default - safe for development
)

@db_dev.model
class User:
    name: str
    email: str

# Add field later - auto-migrates safely
@db_dev.model
class User:
    name: str
    email: str
    age: int = 0  # New field with default - safe migration
```

## Quick Tips

- `auto_migrate=True` is safe for ALL environments (v0.10.15+)
- Works correctly in Docker/async via `SyncDDLExecutor`
- Always provide defaults for NOT NULL columns
- Enterprise migration system for complex operations (type changes, renames)
- Test migrations on staging before production
- No more need for `create_tables_async()` workaround

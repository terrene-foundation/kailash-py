# /db - DataFlow Quick Reference

## Purpose

Load the DataFlow skill for zero-config database operations with automatic model-to-node generation.

## Quick Reference

| Command | Action |
|---------|--------|
| `/db` | Load DataFlow patterns and database basics |
| `/db model` | Show @db.model decorator patterns |
| `/db crud` | Show CRUD operation patterns |
| `/db bulk` | Show bulk operation patterns |

## What You Get

- @db.model decorator patterns
- Auto-generated nodes (11 per SQL model, 8 for MongoDB)
- CRUD, bulk operations, transactions
- Multi-tenancy and multi-instance patterns
- PostgreSQL, SQLite, MongoDB support

## Quick Pattern

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: int = field(primary_key=True)
    name: str
    created_at: datetime = field(auto_now_add=True)  # Auto-managed

# Creates 11 nodes automatically: CreateUser, ReadUser, UpdateUser, etc.
```

## Critical Gotchas

| Rule | Why |
|------|-----|
| Primary key MUST be named `id` | DataFlow convention requirement |
| NEVER manually set `created_at`/`updated_at` | Auto-managed fields |
| CreateNode uses FLAT params | Not nested under `data` |
| UpdateNode uses `filter` + `fields` | Different from CreateNode pattern |
| DataFlow is NOT an ORM | It generates workflow nodes |

## Usage Examples

```bash
# Load DataFlow basics
/db

# Get @db.model decorator patterns
/db model

# See CRUD operation patterns
/db crud

# Learn bulk operation patterns
/db bulk
```

## Related Commands

- `/sdk` - Core SDK patterns
- `/api` - Nexus multi-channel deployment
- `/ai` - Kaizen AI agents
- `/test` - Testing strategies
- `/validate` - Gold standards compliance

## Skill Reference

This command loads: `.claude/skills/02-dataflow/SKILL.md`

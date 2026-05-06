---
name: enterprise-infrastructure
description: "Kailash enterprise infra: progressive infrastructure, dialect-portable SQL, store factory, task queues, worker registry, idempotency."
---

# Enterprise Infrastructure - Skills

Comprehensive guide to Kailash's progressive infrastructure model for scaling from single-process SQLite to multi-worker PostgreSQL/MySQL deployments.

## Features

The enterprise infrastructure layer provides:

- **Progressive Infrastructure Model**: Level 0 (SQLite, in-process) to Level 2 (multi-worker, shared database + queue)
- **QueryDialect Strategy Pattern**: Dialect-portable SQL across PostgreSQL, MySQL 8.0+, and SQLite
- **ConnectionManager**: Async connection pooling with dialect-aware placeholder translation
- **StoreFactory**: Singleton factory for creating store backends from `KAILASH_DATABASE_URL`
- **SQL Task Queue**: Database-backed task queue using `FOR UPDATE SKIP LOCKED`
- **Worker Registry**: Heartbeat monitoring and dead worker reaping
- **IdempotentExecutor**: Exactly-once workflow execution via claim-execute-store pattern
- **Schema Versioning**: `kailash_meta` table with downgrade protection

## Quick Start

```python
# Level 0: Zero config (default)
from kailash.runtime import LocalRuntime
runtime = LocalRuntime()  # SQLite stores, in-process

# Level 1: Set KAILASH_DATABASE_URL=postgresql://user:pass@localhost/kailash
# Auto-detects PG, all stores use shared ConnectionManager

# Level 2: Set KAILASH_QUEUE_URL=redis://localhost:6379/0
# OR KAILASH_QUEUE_URL=postgresql://user:pass@localhost/kailash
```

The user's workflow code is identical at all levels.

## Reference Documentation

### Core Patterns

- **[progressive-infrastructure](progressive-infrastructure.md)** - Level 0/1/2 model, StoreFactory, env vars, schema versioning
- **[dialect-portable-sql](dialect-portable-sql.md)** - QueryDialect strategy, `?` placeholders, `_validate_identifier()`
- **[connection-manager-patterns](connection-manager-patterns.md)** - ConnectionManager lifecycle, transactions, driver behavior

### Operations

- **[task-queue-patterns](task-queue-patterns.md)** - SQL task queue, SKIP LOCKED, Redis vs SQL, worker registry
- **[idempotency-patterns](idempotency-patterns.md)** - IdempotentExecutor, claim-execute-store, TTL expiry

## Key Concepts

### Progressive Levels

| Level | Config                 | Runtime                   | Persistence                    |
| ----- | ---------------------- | ------------------------- | ------------------------------ |
| 0     | None                   | In-process, LocalRuntime  | SQLite + in-memory             |
| 1     | `KAILASH_DATABASE_URL` | In-process, shared DB     | PostgreSQL/MySQL/SQLite        |
| 2     | `KAILASH_QUEUE_URL`    | Multi-worker + task queue | Shared DB + Redis or SQL queue |

### Environment Variables

| Variable               | Purpose                             | Default         |
| ---------------------- | ----------------------------------- | --------------- |
| `KAILASH_DATABASE_URL` | Infrastructure stores               | None (Level 0)  |
| `DATABASE_URL`         | Fallback for `KAILASH_DATABASE_URL` | None            |
| `KAILASH_QUEUE_URL`    | Task queue broker                   | None (no queue) |

### Source Code Layout

| Package                                           | Purpose                                                    |
| ------------------------------------------------- | ---------------------------------------------------------- |

## Critical Rules

- Use `?` canonical placeholders in all SQL -- ConnectionManager translates automatically
- Validate all SQL identifiers with `_validate_identifier()` before interpolation
- Use `dialect.upsert()` instead of check-then-act (TOCTOU race)
- Use `async with conn.transaction() as tx:` for multi-statement operations
- Bound in-memory stores: OrderedDict with LRU eviction, max 10,000 entries
- Lazy imports for database drivers (aiosqlite, asyncpg, aiomysql)
- No `AUTOINCREMENT` in shared DDL (SQLite-specific)
- Share a single ConnectionManager via StoreFactory (never create separate instances per store)

## When to Use This Skill

Use this skill when you need to:

- Scale from Level 0 (SQLite) to Level 1 (PostgreSQL) or Level 2 (multi-worker)
- Write dialect-portable SQL that works across PostgreSQL, MySQL, and SQLite
- Set up the StoreFactory for infrastructure store backends
- Implement task queue processing with SQL or Redis
- Add idempotency guarantees to workflow execution
- Manage worker registration and heartbeat monitoring
- Understand schema versioning and migration patterns

## Related Skills

- **[01-core-sdk](../01-core-sdk/SKILL.md)** - Core SDK workflow patterns (infrastructure backs execution)
- **[02-dataflow](../02-dataflow/SKILL.md)** - DataFlow for user data (infrastructure for runtime stores)
- **[03-nexus](../03-nexus/SKILL.md)** - Multi-channel platform deployment
- **[07-development-guides](../07-development-guides/SKILL.md)** - Testing and development patterns

## Support

For complex infrastructure questions, invoke:

- `infrastructure-specialist` - Progressive infrastructure, dialect portability, store factory
- `testing-specialist` - Infrastructure testing with real databases
- `security-reviewer` - SQL injection prevention, transaction safety

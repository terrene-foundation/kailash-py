# Final Decisions — Enterprise Infrastructure

**Date**: 2026-03-17
**Supersedes**: PostgreSQL-only approach in 01-project-brief.md, SQLAlchemy Core approach in 02-multi-database-strategy.md

## Binding Decisions

### D1: QueryDialect, not SQLAlchemy Core

Use a thin QueryDialect abstraction (strategy pattern) sitting above raw async drivers (asyncpg, aiomysql, aiosqlite). Aligns with kailash-rs's QueryDialect pattern. SQLAlchemy is used only for engine/pool management, NOT for query building.

### D2: Env Vars

- `KAILASH_DATABASE_URL` — infrastructure stores. Falls back to `DATABASE_URL`, then SQLite.
- `KAILASH_QUEUE_URL` — task queue. `redis://` for Redis, `postgresql://` or `mysql://` for SQL queue. No default (Level 0 has no queue).
- `DATABASE_URL` — DataFlow user data (unchanged, existing convention).

### D3: File Organization

New `src/kailash/db/` package: `dialect.py`, `connection.py`, `registry.py`, `migration.py`.

### D4: Level 3 Deferred

Cluster coordination (leader election, distributed locks, global ordering) deferred to v1.1+. Levels 1 and 2 ship in v1.0.0.

### D5: Existing SQLite Backends Untouched

Level 0 defaults (SqliteEventStoreBackend, PersistentDLQ, DiskStorage, InMemoryStateStorage) remain as-is. New dialect-portable backends are additive.

### D6: Schema Versioning via kailash_meta Table

`CREATE TABLE IF NOT EXISTS kailash_meta (key TEXT PRIMARY KEY, value TEXT)`. Version stamped on first initialization. No Alembic in v1.0.0.

### D7: Worker Deserialization via Workflow.to_dict()/from_dict()

Existing serialization methods are sufficient. Replace custom `_serialize_workflow` with `workflow.to_dict()`.

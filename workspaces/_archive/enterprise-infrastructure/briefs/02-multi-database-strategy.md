# Supplementary Brief: Multi-Database Strategy

> From kailash-rs team discussion, 2026-03-17. Overrides the PostgreSQL-only approach in 01-project-brief.md.

## Decision

**Do NOT build PostgreSQL-specific store backends.** Build database-portable backends using SQLAlchemy Core that work across PostgreSQL, MySQL 8.0+, and SQLite from the same code.

## Rationale

kailash-rs uses sqlx's Any driver for multi-database support. The Python equivalent is **SQLAlchemy Core** (not ORM), which is already in kailash-py's `database` optional extra.

The original brief proposed psycopg3 for sync stores and asyncpg for async stores. This is wrong because:

1. It locks infrastructure stores to PostgreSQL only
2. It requires maintaining two different PG driver integrations
3. It ignores MySQL 8.0+ which supports the same features (SKIP LOCKED, JSON, upserts)
4. It contradicts the "progressive infrastructure" vision (Level 0 SQLite should share code with Level 1 PG)

## Architecture Change

### Before (brief's proposal)

```
EventStore → SqliteEventStoreBackend (shipped)
           → PostgresEventStoreBackend (new, psycopg3)

CheckpointStore → DiskStorage (shipped)
                → PostgresCheckpointStorage (new, psycopg3)

DLQ → PersistentDLQ (SQLite, shipped)
    → PostgresDLQ (new, psycopg3)
```

3 SQLite backends + 3 PostgreSQL backends = 6 implementations to maintain.

### After (multi-database approach)

```
EventStore → SqliteEventStoreBackend (shipped, keep for Level 0)
           → SqlAlchemyEventStoreBackend (new, works on PG + MySQL + SQLite)

CheckpointStore → DiskStorage (shipped, keep for Level 0)
                → SqlAlchemyCheckpointStorage (new, works on PG + MySQL + SQLite)

DLQ → PersistentDLQ (SQLite, shipped, keep for Level 0)
    → SqlAlchemyDLQ (new, works on PG + MySQL + SQLite)
```

3 SQLite backends (keep) + 3 SQLAlchemy backends (new) = still 6, but the SQLAlchemy backends cover 3 databases each.

### Dialect-Specific Features

| Feature                          | PostgreSQL               | MySQL 8.0+                | SQLite                            |
| -------------------------------- | ------------------------ | ------------------------- | --------------------------------- |
| SKIP LOCKED (task queue)         | `FOR UPDATE SKIP LOCKED` | `FOR UPDATE SKIP LOCKED`  | `BEGIN IMMEDIATE` (single-writer) |
| Advisory locks (leader election) | `pg_advisory_lock()`     | `GET_LOCK()`              | File lock                         |
| JSON column                      | `JSONB`                  | `JSON`                    | `TEXT` (json serialized)          |
| Upsert                           | `ON CONFLICT DO UPDATE`  | `ON DUPLICATE KEY UPDATE` | `ON CONFLICT DO UPDATE`           |

SQLAlchemy handles most of these automatically. For SKIP LOCKED, use `sqlalchemy.sql.expression.with_for_update(skip_locked=True)` — SQLAlchemy compiles it to the correct dialect.

## Implementation Impact

The brief's 18 TODOs (PY-EI-001 through PY-EI-018) should be restructured:

- **PY-EI-001 through PY-EI-005**: Rename from "Postgres*" to "SqlAlchemy*". One implementation covers PG + MySQL + SQLite.
- **PY-EI-006 (schema migration)**: Use Alembic (SQLAlchemy's migration tool) instead of custom migration framework.
- **PY-EI-009 (PG SKIP LOCKED task queue)**: Rename to "SQL task queue" — SKIP LOCKED works on MySQL too.

## Dependency Impact

```toml
# Already in kailash[database]:
database = [
    "aiosqlite>=0.19.0",
    "sqlalchemy>=2.0.0",
]

# For PostgreSQL:
postgres = [
    "asyncpg>=0.30.0",
]

# For MySQL:
mysql = [
    "aiomysql>=0.2.0",
]
```

No new dependencies. SQLAlchemy is already an optional dep. asyncpg and aiomysql are already optional deps. Users install what they need:

```bash
pip install kailash[database]              # SQLite only
pip install kailash[database,postgres]     # + PostgreSQL
pip install kailash[database,mysql]        # + MySQL
```

## Success Criteria (Updated)

1. `DATABASE_URL=sqlite:///kailash.db` → all stores use SQLite (Level 0 equivalent)
2. `DATABASE_URL=postgresql+asyncpg://...` → all stores use PostgreSQL
3. `DATABASE_URL=mysql+aiomysql://...` → all stores use MySQL
4. Same application code at all levels, all databases
5. Dialect-specific optimizations (SKIP LOCKED, advisory locks) applied automatically when available

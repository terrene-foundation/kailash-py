---
name: dataflow-dialects
description: "PostgreSQL vs SQLite differences in DataFlow. Use when asking 'dataflow postgres', 'dataflow sqlite', or 'database dialects'."
---

# DataFlow Database Dialects

> **Skill Metadata**
> Category: `dataflow`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`

## SQLite (Default)

```python
from dataflow import DataFlow

# Automatic - no setup required
db = DataFlow("sqlite:///app.db")

# Pros: Zero config, perfect for development
# Cons: Single-writer, no concurrent writes
```

## PostgreSQL (Recommended for Production)

```python
db = DataFlow("postgresql://user:pass@localhost/mydb")

# Pros: Multi-instance safe, full ACID, concurrent writes
# Cons: Requires PostgreSQL server
```

## Key Differences

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| **Concurrency** | Single writer | Multi-writer |
| **Multi-Instance** | ❌ Not safe | ✅ Safe |
| **Setup** | Zero config | Requires server |
| **Performance** | Fast for reads | Better for writes |
| **Use Case** | Development, CLI | Production, APIs |

## Switching Dialects

```python
# Development (SQLite)
if os.getenv("ENV") == "development":
    db = DataFlow("sqlite:///dev.db")
else:
    # Production (PostgreSQL)
    db = DataFlow(os.getenv("DATABASE_URL"))
```

## Documentation

- **Database Support**: [`sdk-users/apps/dataflow/02-database-support.md`](../../../../sdk-users/apps/dataflow/02-database-support.md)

<!-- Trigger Keywords: dataflow postgres, dataflow sqlite, database dialects, dataflow databases -->

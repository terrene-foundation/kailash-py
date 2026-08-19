---
name: dataflow-read-replicas
description: "Read/write splitting with DataFlow read replicas. Use when asking about 'read replica', 'read_url', 'write splitting', 'use_primary', 'dual pool', 'read/write separation', or 'database scaling'."
---

# DataFlow Read Replicas

Automatic read/write splitting with separate connection pools for primary and replica databases.

## Quick Reference

| Feature       | Details                                         |
| ------------- | ----------------------------------------------- |
| Enable        | `DataFlow(url, read_url="...")`                 |
| Force primary | `use_primary=True` on any read operation        |
| Pool sizing   | `read_pool_size=N` (separate from primary pool) |
| Health check  | `db.health_check()` reports both pools          |

## Configuration

```python
db = DataFlow(
    "postgresql://primary:5432/mydb",
    read_url="postgresql://replica:5432/mydb",
    read_pool_size=10,  # Optional: separate pool size for reads
)
```

When `read_url` is provided, DataFlow creates two connection managers:

- **Primary**: Used for all write operations and explicit `use_primary=True` reads
- **Replica**: Used for all read operations by default

When no `read_url` is supplied, the primary connection manager handles all operations.

## Usage

```python
# Reads go to replica automatically
user = await db.express.read("User", "u1")
users = await db.express.list("User", {"active": True})
count = await db.express.count("User")

# Force read from primary (for write-after-read consistency)
user = await db.express.read("User", "u1", use_primary=True)
users = await db.express.list("User", {"active": True}, use_primary=True)
count = await db.express.count("User", use_primary=True)

# Writes always go to primary
await db.express.create("User", {"name": "Alice"})
await db.express.update("User", "u1", {"name": "Bob"})
```

## When to Use `use_primary=True`

Use `use_primary=True` when you need write-after-read consistency:

```python
# Create user on primary
result = await db.express.create("User", {"name": "Alice"})

# Read back immediately -- replica may not have it yet
user = await db.express.read("User", result["id"], use_primary=True)
```

Replication lag varies by database setup (typically <1s for streaming replication, but can be longer under load).

## Health Check

```python
health = await db.health_check()
# health["read_replica"] = {
#     "url": "postgresql://***:***@replica:5432/mydb",
#     "status": "healthy"
# }
```

## Source Code

- the dataflow package (`src/dataflow/core/engine.py`) -- Read replica init (TSG-105)
- the dataflow package (`src/dataflow/features/express.py`) -- `use_primary` parameter on reads

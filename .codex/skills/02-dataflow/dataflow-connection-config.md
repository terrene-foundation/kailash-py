---
name: dataflow-connection-config
description: "DataFlow database connection configuration for SQL (PostgreSQL, MySQL, SQLite), MongoDB, and pgvector. Use when DataFlow connection, database URL, connection string, special characters in password, or connection setup."
---

# DataFlow Connection Configuration

Configure database connections with full support for special characters in passwords and connection pooling.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> Related Skills: [`dataflow-quickstart`](#), [`dataflow-models`](#), [`dataflow-existing-database`](#)
> Related Subagents: `dataflow-specialist` (connection troubleshooting, pooling optimization)

## Quick Reference

- **Format**: `scheme://[user[:pass]@]host[:port]/database`
- **Special Chars**: Fully supported in passwords
- **SQL Databases**: PostgreSQL, MySQL, SQLite (11 nodes per @db.model)
- **Document Database**: MongoDB (8 specialized nodes, flexible schema)
- **Vector Search**: PostgreSQL pgvector (3 vector nodes for RAG/semantic search)
- **Pooling**: Automatic, configurable

## Core Pattern

```python
from dataflow import DataFlow

# PostgreSQL with special characters (pool auto-scales from max_connections)
db = DataFlow(
    database_url="postgresql://admin:MySecret#123$@localhost:5432/mydb",
)

# SQLite (development)
db_dev = DataFlow(
    database_url="sqlite:///dev.db"
)

# Environment variable (recommended)
import os
db_prod = DataFlow(
    database_url=os.getenv("DATABASE_URL")
)
```

## Common Use Cases

- **Production**: PostgreSQL with connection pooling
- **Development**: SQLite for fast iteration
- **Testing**: In-memory SQLite
- **Multi-Environment**: Different configs per environment
- **Special Passwords**: Passwords with #, $, @, ? characters

## Connection String Format

### PostgreSQL

```python
# Full format
"postgresql://username:password@host:port/database?param=value"

# Examples
"postgresql://user:pass@localhost:5432/mydb"
"postgresql://readonly:secret@replica.host:5432/analytics"
"postgresql://admin:Complex$Pass!@10.0.1.5:5432/production"
```

### SQLite

```python
# File-based
"sqlite:///path/to/database.db"
"sqlite:////absolute/path/database.db"

# In-memory (testing)
"sqlite:///:memory:"
":memory:"  # Shorthand
```

## Key Parameters

```python
db = DataFlow(
    # Connection
    database_url="postgresql://...",

    # Connection pooling — auto-scales by default (recommended)
    # pool_size auto-detects from database max_connections
    # pool_max_overflow auto-computed as max(2, pool_size // 2)
    pool_recycle=3600,         # Recycle after 1 hour

    # Override auto-scaling only when needed:
    # pool_size=25,            # Explicit override (e.g., PgBouncer)
    # pool_max_overflow=12,    # Explicit overflow limit

    # Timeouts
    connect_timeout=10,        # Connection timeout (seconds)
    command_timeout=30,        # Query timeout

    # Behavior
    echo=False,                # SQL logging (debug only)
    auto_migrate=True,         # Auto schema updates (default)
)
```

## Connection Pool Configuration

DataFlow auto-scales pool sizes from `max_connections`. No configuration needed for most deployments.

### How Auto-Scaling Works

1. **Explicit `pool_size`** → used as-is (highest priority)
2. **`DATAFLOW_POOL_SIZE` env var** → used if set
3. **Auto-detect**: probes `SHOW max_connections` on PostgreSQL → `pool_size = (max_conn * 0.7) / workers`
4. **Fallback**: `min(5, cpu_count)` if probe fails

### When to Override

| Scenario               | Action                                              |
| ---------------------- | --------------------------------------------------- |
| **PgBouncer**          | Set `pool_size=3` (pooler manages connections)      |
| **Known worker count** | Set `DATAFLOW_WORKER_COUNT=N` for accurate division |
| **Shared database**    | Lower `pool_size` to leave room for other apps      |
| **Development**        | Leave default — SQLite doesn't need pooling         |

### Diagnostic Flow

```python
# 1. Check startup logs for pool configuration
#    [DataFlow] Pool auto-scaled: pool_size=17, max_overflow=8 (db_max=100, workers=4)

# 2. Real-time utilization
stats = db.pool_stats()
# {"active": 5, "idle": 12, "max": 17, "overflow": 0, "max_overflow": 8, "utilization": 0.19}

# 3. Health check includes pool status
health = db.health_check()
# health["pool"]["utilization"] — 0.0 to 1.0

# 4. Lightweight health check (doesn't consume main pool)
result = await db.execute_raw_lightweight("SELECT 1")
```

### Environment Variables

| Variable                         | Purpose                        | Default     |
| -------------------------------- | ------------------------------ | ----------- |
| `DATAFLOW_POOL_SIZE`             | Override auto-scaled pool size | Auto-detect |
| `DATAFLOW_WORKER_COUNT`          | Worker count for pool division | Auto-detect |
| `DATAFLOW_STARTUP_VALIDATION`    | Validate pool at startup       | `true`      |
| `DATAFLOW_POOL_MONITOR_INTERVAL` | Monitor check interval (secs)  | `10`        |

## Common Mistakes

### Mistake 1: URL Encoding Passwords

```python
# Wrong (old workaround, no longer needed)
password = "MySecret%23123%24"  # Manual encoding
db = DataFlow(f"postgresql://user:{password}@host/db")
```

**Fix: Use Password Directly**

```python
# Correct - automatic handling
db = DataFlow("postgresql://user:MySecret#123$@host/db")
```

### Mistake 2: Hardcoding Pool Size

```python
# Wrong — hardcoded pool_size ignores deployment topology
db = DataFlow(
    database_url="postgresql://...",
    pool_size=50,           # May exhaust max_connections in multi-worker deployments
    pool_max_overflow=100   # pool_size * 2 triples connection footprint!
)
```

**Fix: Let Auto-Scaling Handle It**

```python
# Correct — auto-scales from database max_connections
db = DataFlow(
    database_url="postgresql://...",
    # pool_size auto-detected, max_overflow = max(2, pool_size // 2)
)
```

## Related Patterns

- **For existing databases**: See [`dataflow-existing-database`](#)
- **For multi-instance**: See [`dataflow-multi-instance`](#)
- **For performance**: See [`dataflow-performance`](#)

## When to Escalate to Subagent

Use `dataflow-specialist` when:

- Connection pool exhaustion
- Timeout issues
- SSL/TLS configuration
- Read/write splitting
- Multi-database setup

## Documentation References

### Primary Sources

### Related Documentation

## Examples

### Example 1: Multi-Environment Setup

```python
import os

# Development
if os.getenv("ENV") == "development":
    db = DataFlow("sqlite:///dev.db", auto_migrate=True)

# Staging
elif os.getenv("ENV") == "staging":
    db = DataFlow(
        database_url=os.getenv("DATABASE_URL"),
        auto_migrate=True
        # pool_size auto-scaled from max_connections
    )

# Production
else:
    db = DataFlow(
        database_url=os.getenv("DATABASE_URL"),
        auto_migrate=False,  # Don't modify existing schema
        # pool_size auto-scaled; override with DATAFLOW_POOL_SIZE env var if needed
    )
```

### Example 2: Connection with Complex Password

```python
# Password with special characters
db = DataFlow(
    database_url="postgresql://admin:P@ssw0rd!#$@db.example.com:5432/prod",
    pool_size=20,
    pool_pre_ping=True,
    connect_timeout=10
)
```

## Troubleshooting

| Issue                          | Cause                                  | Solution                                                                            |
| ------------------------------ | -------------------------------------- | ----------------------------------------------------------------------------------- |
| Connection refused             | Wrong host/port                        | Verify connection string                                                            |
| Password authentication failed | Special chars in password              | Use latest DataFlow                                                                 |
| Pool exhausted                 | Too many workers or pool_size override | Remove explicit pool_size (let auto-scaling handle it) or set DATAFLOW_WORKER_COUNT |
| Connection timeout             | Network/firewall                       | Check connect_timeout                                                               |

## Quick Tips

- Use environment variables for credentials
- Special characters work with no encoding required
- SQLite for development, PostgreSQL for production
- pool_size auto-scales from max_connections (leave default)
- Enable pool_pre_ping for reliability
- Test connection before deployment

## Keywords for Auto-Trigger

<!-- Trigger Keywords: DataFlow connection, database URL, connection string, PostgreSQL connection, SQLite connection, special characters password, connection pool, database setup, connection configuration -->

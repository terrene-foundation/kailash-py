# Multi-Database Support

DataFlow provides seamless support for PostgreSQL, MySQL, and SQLite with automatic dialect detection, type mapping, and feature compatibility.

## Overview

Write your code once and run it on any supported database:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
# Development - SQLite
db = DataFlow("sqlite:///dev.db")

# Testing - MySQL
db = DataFlow("mysql://user:pass@localhost/test")

# Production - PostgreSQL
db = DataFlow("postgresql://user:pass@localhost/prod")

# Same model works everywhere
@db.model
class Product:
    name: str
    price: float
    metadata: dict  # Automatically mapped to correct type
```

## Supported Databases

### PostgreSQL
- **Versions**: 12+
- **Driver**: psycopg2, asyncpg
- **Best for**: Production, complex queries, JSON operations

### MySQL
- **Versions**: 5.7+, 8.0+
- **Driver**: pymysql, mysqlclient, aiomysql
- **Best for**: Web applications, existing MySQL infrastructure

### SQLite
- **Versions**: 3.25+
- **Driver**: Built-in, aiosqlite
- **Best for**: Development, testing, embedded applications

## Automatic Dialect Detection

DataFlow automatically detects the database from the connection URL:

```python
# PostgreSQL URLs
"postgresql://user:pass@localhost/db"
"postgres://user:pass@localhost/db"
"postgresql+asyncpg://user:pass@localhost/db"

# MySQL URLs
"mysql://user:pass@localhost/db"
"mysql+pymysql://user:pass@localhost/db"
"mysql+aiomysql://user:pass@localhost/db"

# SQLite URLs
"sqlite:///path/to/database.db"
"sqlite:///:memory:"  # In-memory database
"sqlite+aiosqlite:///path/to/db.sqlite"
```

## Type Mapping

DataFlow automatically maps types between databases:

| Python Type | PostgreSQL | MySQL | SQLite |
|-------------|------------|-------|--------|
| `str` | VARCHAR | VARCHAR | TEXT |
| `int` | INTEGER | INT | INTEGER |
| `float` | DOUBLE PRECISION | DOUBLE | REAL |
| `bool` | BOOLEAN | BOOLEAN | INTEGER |
| `datetime` | TIMESTAMP | DATETIME | TEXT |
| `date` | DATE | DATE | TEXT |
| `time` | TIME | TIME | TEXT |
| `bytes` | BYTEA | BLOB | BLOB |
| `dict` | JSONB | JSON | TEXT |
| `list` | JSONB | JSON | TEXT |
| `uuid.UUID` | UUID | VARCHAR(36) | TEXT |
| `decimal.Decimal` | DECIMAL | DECIMAL | REAL |

## Feature Compatibility

Not all databases support all features. DataFlow handles this gracefully:

### Feature Matrix

| Feature | PostgreSQL | MySQL | SQLite |
|---------|------------|-------|--------|
| Transactions | ✅ | ✅ | ✅ |
| Foreign Keys | ✅ | ✅ | ✅ |
| JSON Type | ✅ | ✅ | ✅ |
| UUID Type | ✅ | ❌ | ❌ |
| Arrays | ✅ | ❌ | ❌ |
| UPSERT | ✅ | ✅ | ✅ |
| RETURNING | ✅ | ❌ | ✅ |
| Window Functions | ✅ | ✅ | ✅ |
| Materialized Views | ✅ | ❌ | ❌ |
| Partial Indexes | ✅ | ❌ | ✅ |
| GIN/GiST Indexes | ✅ | ❌ | ❌ |
| Full Text Search | ✅ | ✅ | ✅ |
| Stored Procedures | ✅ | ✅ | ❌ |

### Checking Feature Support

```python
from dataflow.database import get_database_adapter, DatabaseFeature

# Get adapter for your database
adapter = get_database_adapter("postgresql")

# Check features
if adapter.supports_feature(DatabaseFeature.JSON_TYPE):
    print("JSON operations are optimized")

if adapter.supports_feature(DatabaseFeature.ARRAY_TYPE):
    print("Can use array columns")

if adapter.supports_feature(DatabaseFeature.RETURNING):
    print("Can get created IDs in one query")
```

## Database-Specific SQL Generation

DataFlow generates optimal SQL for each database:

### UPSERT Operations

```python
# PostgreSQL - ON CONFLICT
INSERT INTO users (email, name)
VALUES ($1, $2)
ON CONFLICT (email)
DO UPDATE SET name = EXCLUDED.name;

# MySQL - ON DUPLICATE KEY
INSERT INTO users (email, name)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE name = VALUES(name);

# SQLite - ON CONFLICT (3.24+)
INSERT INTO users (email, name)
VALUES (?, ?)
ON CONFLICT (email)
DO UPDATE SET name = excluded.name;
```

### JSON Operations

```python
# Model with JSON field
@db.model
class Config:
    name: str
    settings: dict  # JSON field

# PostgreSQL - JSONB operations
workflow.add_node("ConfigListNode", "search", {
    "filter": {
        "settings->theme": "dark",  # JSON path query
        "settings->notifications->email": True
    }
})

# MySQL - JSON functions
# Automatically uses JSON_EXTRACT

# SQLite - JSON1 extension
# Automatically uses json_extract()
```

### Auto-Increment Fields

```python
# PostgreSQL - SERIAL
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255)
);

# MySQL - AUTO_INCREMENT
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255)
);

# SQLite - AUTOINCREMENT
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
);
```

## Connection Configuration

### PostgreSQL

```python
db = DataFlow(
    "postgresql://user:pass@localhost/myapp",
    pool_size=20,
    pool_max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,  # Verify connections
    connect_args={
        "server_settings": {"jit": "off"},
        "command_timeout": 60,
        "options": "-c lock_timeout=10s"
    }
)
```

### MySQL

```python
db = DataFlow(
    "mysql://user:pass@localhost/myapp?charset=utf8mb4",
    pool_size=20,
    pool_recycle=3600,
    connect_args={
        "sql_mode": "TRADITIONAL",
        "init_command": "SET default_storage_engine=INNODB",
        "charset": "utf8mb4",
        "use_unicode": True
    }
)
```

### SQLite

```python
db = DataFlow(
    "sqlite:///myapp.db",
    connect_args={
        "check_same_thread": False,  # For multi-threading
        "timeout": 10,
        "isolation_level": None,  # Autocommit mode
    }
)

# In-memory database for testing
test_db = DataFlow("sqlite:///:memory:")
```

## Performance Optimization

### PostgreSQL Optimizations

```python
# Use COPY for bulk inserts
workflow.add_node("UserBulkCreateNode", "import", {
    "data": large_dataset,
    "use_copy": True,  # 10x faster for large datasets
    "batch_size": 10000
})

# Index types
@db.model
class Document:
    content: str
    tags: list

    __indexes__ = [
        {"fields": ["content"], "type": "gin", "opclass": "gin_trgm_ops"},  # Full text
        {"fields": ["tags"], "type": "gin"},  # Array operations
    ]
```

### MySQL Optimizations

```python
# Batch with INSERT IGNORE
workflow.add_node("UserBulkCreateNode", "import", {
    "data": users,
    "ignore_conflicts": True,  # INSERT IGNORE
    "batch_size": 1000
})

# Storage engine
@db.model
class HighPerformance:
    data: str

    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_row_format": "COMPRESSED"
    }
```

### SQLite Optimizations

```python
# WAL mode for better concurrency
db = DataFlow(
    "sqlite:///myapp.db",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True
)

# Pragma optimizations
db.execute_sql("PRAGMA journal_mode=WAL")
db.execute_sql("PRAGMA synchronous=NORMAL")
db.execute_sql("PRAGMA cache_size=10000")
```

## Migration Between Databases

DataFlow makes it easy to migrate between databases:

```python
# Export from SQLite
source_db = DataFlow("sqlite:///dev.db")
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "export", {"limit": None})
results, _ = LocalRuntime().execute(workflow.build())
users = results["export"]["records"]

# Import to PostgreSQL
target_db = DataFlow("postgresql://localhost/prod")
workflow = WorkflowBuilder()
workflow.add_node("UserBulkCreateNode", "import", {
    "data": users,
    "batch_size": 1000
})
LocalRuntime().execute(workflow.build())
```

## Testing with Multiple Databases

```python
import pytest
from dataflow import DataFlow

@pytest.fixture(params=[
    "sqlite:///:memory:",
    "postgresql://test@localhost/test",
    "mysql://test@localhost/test"
])
def db(request):
    """Test with all databases."""
    database = DataFlow(request.param)
    yield database
    database.drop_all()

def test_model_operations(db):
    """Test works on all databases."""
    @db.model
    class User:
        name: str
        email: str

    # Test CRUD operations
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "name": "Test", "email": "test@example.com"
    })
    results, _ = LocalRuntime().execute(workflow.build())
    assert results["create"]["record"]["name"] == "Test"
```

## Best Practices

### 1. Use Environment Variables

```python
import os

# Automatically uses correct database
db = DataFlow(os.getenv("DATABASE_URL"))
```

### 2. Feature Detection

```python
# Check before using advanced features
if db.supports_feature(DatabaseFeature.JSON_TYPE):
    # Use JSON operations
else:
    # Use text serialization
```

### 3. Abstract Database-Specific Code

```python
class DatabaseHelper:
    @staticmethod
    def get_random_function(db):
        if db.dialect == "postgresql":
            return "RANDOM()"
        elif db.dialect == "mysql":
            return "RAND()"
        else:  # sqlite
            return "RANDOM()"
```

### 4. Connection Pool Sizing

```python
# PostgreSQL/MySQL production
db = DataFlow(
    url,
    pool_size=20,        # Base connections
    pool_max_overflow=30 # Burst capacity
)

# SQLite (single connection)
db = DataFlow(
    "sqlite:///app.db",
    pool_size=1  # SQLite doesn't support multiple writers
)
```

## Troubleshooting

### PostgreSQL Issues

```python
# Connection refused
# Check: PostgreSQL running? Port 5432 open? User permissions?

# SSL required
db = DataFlow("postgresql://user:pass@host/db?sslmode=require")

# Encoding issues
db = DataFlow("postgresql://user:pass@host/db?client_encoding=utf8")
```

### MySQL Issues

```python
# Access denied
# Check: User privileges? Password? Host allowed?

# Timezone issues
db = DataFlow(
    "mysql://user:pass@host/db",
    connect_args={"time_zone": "+00:00"}
)

# Max packet size
db.execute_sql("SET GLOBAL max_allowed_packet=67108864")  # 64MB
```

### SQLite Issues

```python
# Database locked
# Use WAL mode for better concurrency
db.execute_sql("PRAGMA journal_mode=WAL")

# Memory issues with large databases
# Use disk-based temp storage
db.execute_sql("PRAGMA temp_store=FILE")
```

## Advanced Usage

### Cross-Database Queries

```python
# Federated queries between databases
pg_db = DataFlow("postgresql://localhost/main")
sqlite_db = DataFlow("sqlite:///cache.db")

# Export from PostgreSQL
workflow1 = WorkflowBuilder()
workflow1.add_node("UserListNode", "users", {"filter": {"active": True}})
users, _ = LocalRuntime().execute(workflow1.build())

# Import to SQLite cache
workflow2 = WorkflowBuilder()
workflow2.add_node("UserBulkCreateNode", "cache", {
    "data": users["users"]["records"]
})
LocalRuntime().execute(workflow2.build())
```

### Database-Specific Optimizations

```python
# PostgreSQL - Use advisory locks
workflow.add_node("PythonCodeNode", "lock", {
    "code": """
import asyncpg
async def execute(params):
    conn = params['connection']
    await conn.execute('SELECT pg_advisory_lock($1)', 12345)
    # Do work
    await conn.execute('SELECT pg_advisory_unlock($1)', 12345)
    return {"locked": True}
"""
})

# MySQL - Use hints
workflow.add_node("CustomSQLNode", "optimized", {
    "sql": "SELECT /*+ INDEX(users idx_email) */ * FROM users WHERE email = %s"
})
```

---

**Summary**: DataFlow's multi-database support lets you develop with SQLite, test with MySQL, and deploy to PostgreSQL without changing your code. Automatic type mapping, feature detection, and optimized SQL generation ensure optimal performance on each platform.

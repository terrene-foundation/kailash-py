# Kailash DataFlow — Core (DataFlow Class, Engine, Exceptions, Trust, Fabric)

Version: 2.3.1
Package: `kailash-dataflow`
Parent domain: DataFlow (split from `dataflow.md` per specs-authority Rule 8)
Scope: DataFlow class + constructor + connection URL + lazy/runtime detection, DataFlowEngine builder, exceptions, write events, Data Fabric Engine, derived models, retention engine, trust plane integration, versioning

Sibling files: `dataflow-express.md` (async/sync Express API, bulk, file import, validation on write), `dataflow-models.md` (`@db.model`, fields, classification/masking, multi-tenancy, schema management), `dataflow-cache.md` (cache layer, dialect system, record ID coercion, transactions, connection pooling)

---

## 1. DataFlow Class

### 1.1 Import

```python
from dataflow import DataFlow
# or
from dataflow.core.engine import DataFlow
```

### 1.2 Constructor

```python
DataFlow(
    database_url: Optional[str] = None,
    config: Optional[DataFlowConfig] = None,
    pool_size: Optional[int] = None,
    pool_max_overflow: Optional[int] = None,
    pool_recycle: int = 3600,
    echo: bool = False,
    multi_tenant: bool = False,
    encryption_key: Optional[str] = None,
    audit_logging: bool = False,
    cache_enabled: bool = True,
    cache_ttl: int = 3600,
    monitoring: Optional[bool] = None,
    slow_query_threshold: float = 1.0,
    debug: bool = False,
    migration_enabled: bool = True,
    auto_migrate: bool = True,
    existing_schema_mode: bool = False,
    enable_model_persistence: bool = True,
    tdd_mode: bool = False,
    test_context: Optional[Any] = None,
    test_mode: Optional[bool] = None,
    test_mode_aggressive_cleanup: bool = True,
    migration_lock_timeout: int = 30,
    enable_connection_pooling: bool = True,
    pools: Optional[Dict[str, Dict[str, Any]]] = None,
    max_overflow: Optional[int] = None,
    enable_caching: Optional[bool] = None,
    validate_on_write: bool = True,
    log_level: Optional[int] = None,
    log_config: Optional[LoggingConfig] = None,
    read_url: Optional[str] = None,
    read_pool_size: Optional[int] = None,
    redis_url: Optional[str] = None,
    trust_enforcement_mode: Optional[str] = None,
    trust_audit_enabled: Optional[bool] = None,
    trust_audit_signing_key: Optional[bytes] = None,
    trust_audit_verify_key: Optional[bytes] = None,
    **kwargs,
)
```

**Parameter reference:**

| Parameter                      | Type                       | Default | Purpose                                                                                                                       |
| ------------------------------ | -------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `database_url`                 | `Optional[str]`            | `None`  | Database connection URL. Falls back to `DATABASE_URL` env var. `None` with no config triggers `DataFlowConfig.from_env()`.    |
| `config`                       | `Optional[DataFlowConfig]` | `None`  | Full configuration object. Individual parameters override matching config fields.                                             |
| `pool_size`                    | `Optional[int]`            | `None`  | Connection pool size. `None` defers to `DatabaseConfig.get_pool_size()`.                                                      |
| `pool_max_overflow`            | `Optional[int]`            | `None`  | Maximum overflow connections beyond `pool_size`.                                                                              |
| `pool_recycle`                 | `int`                      | `3600`  | Seconds before recycling idle connections.                                                                                    |
| `echo`                         | `bool`                     | `False` | Echo SQL statements to log.                                                                                                   |
| `multi_tenant`                 | `bool`                     | `False` | Enable multi-tenant data isolation. When `True`, every Express operation requires a tenant context.                           |
| `encryption_key`               | `Optional[str]`            | `None`  | Encryption key for sensitive data.                                                                                            |
| `audit_logging`                | `bool`                     | `False` | Enable audit trail persistence.                                                                                               |
| `cache_enabled`                | `bool`                     | `True`  | Enable query result caching in Express.                                                                                       |
| `cache_ttl`                    | `int`                      | `3600`  | Default cache TTL in seconds.                                                                                                 |
| `monitoring`                   | `Optional[bool]`           | `None`  | Enable performance monitoring. `None` = disabled.                                                                             |
| `slow_query_threshold`         | `float`                    | `1.0`   | Seconds above which a query is logged as slow.                                                                                |
| `debug`                        | `bool`                     | `False` | Enable debug logging.                                                                                                         |
| `migration_enabled`            | `bool`                     | `True`  | Enable automatic database migrations.                                                                                         |
| `auto_migrate`                 | `bool`                     | `True`  | Automatically run migrations on model registration.                                                                           |
| `existing_schema_mode`         | `bool`                     | `False` | Safe mode for existing databases -- validates compatibility without modifying schema.                                         |
| `enable_model_persistence`     | `bool`                     | `True`  | Enable persistent model registry for multi-application support.                                                               |
| `tdd_mode`                     | `bool`                     | `False` | Enable TDD mode for testing. Also settable via `DATAFLOW_TDD_MODE` env var.                                                   |
| `test_mode`                    | `Optional[bool]`           | `None`  | `None` = auto-detect (checks for pytest env), `True` = enable, `False` = disable.                                             |
| `test_mode_aggressive_cleanup` | `bool`                     | `True`  | Enable aggressive pool cleanup in test mode.                                                                                  |
| `migration_lock_timeout`       | `int`                      | `30`    | Migration lock timeout in seconds for concurrent safety. Minimum 1 second.                                                    |
| `enable_connection_pooling`    | `bool`                     | `True`  | Enable connection pooling.                                                                                                    |
| `validate_on_write`            | `bool`                     | `True`  | Run `@field_validator` rules before every Express write operation.                                                            |
| `log_level`                    | `Optional[int]`            | `None`  | Override log level (e.g. `logging.DEBUG`).                                                                                    |
| `log_config`                   | `Optional[LoggingConfig]`  | `None`  | Full logging configuration for category-specific control.                                                                     |
| `read_url`                     | `Optional[str]`            | `None`  | Read replica URL for read/write splitting (TSG-105).                                                                          |
| `read_pool_size`               | `Optional[int]`            | `None`  | Separate pool size for the read replica.                                                                                      |
| `redis_url`                    | `Optional[str]`            | `None`  | Redis URL for Express cache backend. Falls back to `REDIS_URL` env var. When absent or unreachable, uses in-memory LRU cache. |
| `trust_enforcement_mode`       | `Optional[str]`            | `None`  | Trust plane enforcement: `"disabled"` (default), `"permissive"`, `"enforcing"`.                                               |
| `trust_audit_enabled`          | `Optional[bool]`           | `None`  | Enable trust audit store.                                                                                                     |
| `trust_audit_signing_key`      | `Optional[bytes]`          | `None`  | Ed25519 signing key for audit entries.                                                                                        |
| `trust_audit_verify_key`       | `Optional[bytes]`          | `None`  | Ed25519 verification key for audit entries.                                                                                   |
| `enable_caching`               | `Optional[bool]`           | `None`  | Alias for `cache_enabled`.                                                                                                    |
| `max_overflow`                 | `Optional[int]`            | `None`  | Alias for `pool_max_overflow`.                                                                                                |

**Known `**kwargs`:\*\*

| Key                     | Type   | Purpose                                                                      |
| ----------------------- | ------ | ---------------------------------------------------------------------------- |
| `batch_size`            | `int`  | Default batch size for bulk operations.                                      |
| `cache_max_size`        | `int`  | Maximum cache entries (default: 1000).                                       |
| `max_retries`           | `int`  | Maximum retry count.                                                         |
| `encryption_enabled`    | `bool` | Enable encryption.                                                           |
| `schema_cache_enabled`  | `bool` | Enable/disable schema cache (ADR-001).                                       |
| `schema_cache_ttl`      | `int`  | Schema cache TTL in seconds.                                                 |
| `schema_cache_max_size` | `int`  | Maximum schema cache entries.                                                |
| `use_namespaced_nodes`  | `bool` | Enable namespaced node names for multi-instance isolation (default: `True`). |

Unknown kwargs emit a `UserWarning` with diagnostic suggestions (DF-CFG-001).

### 1.3 Connection URL Format

DataFlow accepts standard database connection URLs:

| Database           | Format                                            | Example                                          |
| ------------------ | ------------------------------------------------- | ------------------------------------------------ |
| PostgreSQL         | `postgresql://user:pass@host:port/dbname`         | `postgresql://admin:secret@localhost:5432/myapp` |
| PostgreSQL (async) | `postgresql+asyncpg://user:pass@host:port/dbname` | Same driver prefix variants                      |
| MySQL              | `mysql://user:pass@host:port/dbname`              | `mysql://root:pass@localhost:3306/myapp`         |
| SQLite (file)      | `sqlite:///path/to/db.sqlite`                     | `sqlite:///data/app.db`                          |
| SQLite (memory)    | `sqlite:///:memory:`                              | `sqlite:///:memory:`                             |
| MongoDB            | `mongodb://user:pass@host:port/dbname`            | `mongodb://localhost:27017/myapp`                |

**Database type detection** is performed by `ConnectionParser.detect_database_type()` using scheme prefix matching. SQLAlchemy-style driver suffixes (e.g., `+asyncpg`, `+pymysql`) are supported.

**Special characters in passwords** (such as `#`, `$`, `@`, `:`) are automatically URL-encoded via the shared `preencode_password_special_chars` helper before parsing. Credential decoding routes through `decode_userinfo_or_raise` which rejects null bytes after percent-decoding (prevents MySQL auth-bypass via `%00`).

**Zero-config mode**: When `database_url` is `None` and no other parameters are provided, DataFlow reads configuration from environment variables via `DataFlowConfig.from_env()`.

### 1.4 Lazy Connection

DataFlow uses lazy connection initialization. The constructor (`__init__`) stores configuration only -- no pool probe, no migration, no database connection. The first database-touching operation triggers `_ensure_connected()`, which:

1. Creates the connection pool
2. Validates pool configuration and reachability
3. Initializes the migration system
4. Wires the audit backend (if enabled)
5. Initializes the cache integration

#### Operations That Trigger Connection

| Operation                                         | Triggers `_ensure_connected()`? | Notes                                                                                                                                                                |
| ------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `db.express.create/read/update/delete/list/count` | YES                             | Accessing `db.express` or `db.express_sync` triggers connection before the first CRUD call.                                                                          |
| `@db.model` registration                          | NO                              | Model registration queues the model for deferred table creation. The actual DDL runs inside `_ensure_connected()` when the first database-touching operation occurs. |
| `db.start()`                                      | YES                             | Explicit fabric runtime start calls `_ensure_connected()` as part of initialization.                                                                                 |
| `await db.initialize()`                           | YES                             | Async initialization explicitly calls `_ensure_connected()` before validating database connectivity.                                                                 |
| `db.create_tables()`                              | YES                             | Batch table creation calls `_ensure_connected()`.                                                                                                                    |
| `db.health_check()`                               | YES                             | Health check requires an active connection.                                                                                                                          |
| `db.execute_lightweight_query()`                  | YES                             | Lightweight queries (e.g., health probes) trigger connection.                                                                                                        |
| `db.audit_query()`                                | YES                             | Audit queries require an active connection.                                                                                                                          |

**Design rationale:** Lazy connection means `DataFlow("sqlite:///app.db")` returns instantly with zero I/O. This allows `@db.model` decorators to register models at import time without blocking module loading. Connection is deferred until the application actually needs the database, which also means misconfigured connection URLs fail at first use, not at import time.

### 1.5 Runtime Detection

DataFlow detects whether it is running in an async or sync context at construction time:

- **Async context** (running event loop detected): uses `AsyncLocalRuntime`
- **Sync context** (no running event loop): uses `LocalRuntime`

All subsystems share a single runtime via `acquire()`/`release()` ref-counting to prevent orphan runtimes and pool exhaustion.

---

## 14. DataFlowEngine (Builder Pattern)

`DataFlowEngine` wraps `DataFlow` with enterprise features (validation layers, classification policies, query performance monitoring):

```python
from dataflow import DataFlowEngine

engine = await (
    DataFlowEngine.builder("postgresql://localhost/mydb")
    .slow_query_threshold(0.5)
    .classification_policy(policy)
    .validate_on_write(True)
    .build()
)

# Access underlying DataFlow
engine.dataflow.express.create("User", {...})
health = await engine.health_check()
await engine.close()
```

### 14.1 Builder Methods

| Method                           | Purpose                                         |
| -------------------------------- | ----------------------------------------------- |
| `.validation(layer)`             | Set a `ValidationLayer` protocol implementation |
| `.classification_policy(policy)` | Set a `DataClassificationPolicy`                |
| `.slow_query_threshold(seconds)` | Slow query detection threshold (default: 1.0s)  |
| `.validate_on_write(enabled)`    | Enable auto-validation before writes            |
| `.source(name, config)`          | Register an external data source                |
| `.fabric(**kwargs)`              | Configure fabric runtime parameters             |
| `.config(**kwargs)`              | Pass additional kwargs to `DataFlow`            |
| `.build()`                       | Build the engine (async)                        |

### 14.2 QueryEngine

Tracks query execution times:

```python
stats = engine.query_engine.stats()
# {"total_queries": int, "slow_queries": int, "avg_ms": float, "p95_ms": float, "max_ms": float}

slow = engine.query_engine.slow_queries(last_n_seconds=3600)
# List[QueryStats]
```

### 14.3 HealthStatus

```python
health = await engine.health_check()
# HealthStatus(healthy=bool, database_connected=bool, pool_size=int,
#              active_connections=int, slow_queries_last_hour=int, details={...})
```

---

## 15. Exceptions

| Exception                    | Purpose                                                                    |
| ---------------------------- | -------------------------------------------------------------------------- |
| `DataFlowError`              | Base exception for all DataFlow errors                                     |
| `DataFlowConfigurationError` | Configuration errors                                                       |
| `DataFlowModelError`         | Model definition errors                                                    |
| `DataFlowNodeError`          | Node operation errors                                                      |
| `DataFlowRuntimeError`       | Runtime execution errors                                                   |
| `DataFlowMigrationError`     | Migration errors                                                           |
| `DataFlowConnectionError`    | Connection errors                                                          |
| `ModelValidationError`       | STRICT mode validation failure (contains `errors` list)                    |
| `DataFlowValidationWarning`  | WARN mode validation warning (subclass of `UserWarning`)                   |
| `EnhancedDataFlowError`      | Rich error with `error_code`, `context`, `causes`, `solutions`, `docs_url` |
| `InvalidIdentifierError`     | SQL identifier validation failure                                          |
| `TenantRequiredError`        | Missing tenant in multi-tenant mode                                        |
| `InvalidTenantIdError`       | Tenant ID fails safety regex                                               |

---

## 17. Events

DataFlow emits write events via an internal event bus (TSG-201). Write operations (`create`, `update`, `delete`, `upsert`, `bulk_*`) call `_emit_write_event(model, operation, record_id)`. These events can be consumed by:

- Derived model refresh triggers
- Data Fabric change detection
- External event consumers

---

## 18. Data Fabric Engine

The Data Fabric Engine enables DataFlow to operate as a data integration platform that connects heterogeneous data sources:

### 18.1 Source Registration

```python
db = DataFlow("sqlite:///app.db")
db.source("crm", RestSourceConfig(url="https://api.example.com"))
db.source("config", FileSourceConfig(path="./config.yaml"))
```

Or via the builder:

```python
engine = await (
    DataFlowEngine.builder("sqlite:///app.db")
    .source("crm", RestSourceConfig(url="https://api.example.com"))
    .build()
)
```

### 18.2 Product Registration

Products are derived outputs computed from registered sources and stored models, using the `@db.product()` decorator pattern.

### 18.3 Fabric-Only Mode

When `database_url=None` is explicitly passed with no config, DataFlow enters fabric-only mode where it acts as a data integration engine without a backing database.

---

## 19. Derived Models

```python
@db.derived_model(
    sources=["Order", "LineItem"],
    refresh="on_write",
    debounce_ms=100.0,
)
class OrderSummary:
    id: str
    order_count: int
    total_revenue: float

    @staticmethod
    def compute(sources: Dict[str, List[Dict]]) -> List[Dict]:
        orders = sources["Order"]
        items = sources["LineItem"]
        # ... compute aggregation
        return [{"id": "summary", "order_count": len(orders), "total_revenue": total}]
```

Derived models receive full `@db.model` treatment (table creation, CRUD nodes) and are automatically refreshed when source models change.

---

## 20. Retention Engine

Registered via `__dataflow__["retention"]` in model config:

```python
@db.model
class AuditLog:
    __dataflow__ = {
        "retention": {
            "policy": "delete",    # or "archive"
            "after_days": 90,
            "cutoff_field": "created_at",
        },
    }
    id: int
    action: str
    created_at: datetime
```

Execute retention:

```python
results = await db.retention.run()              # Execute retention policies
results = await db.retention.run(dry_run=True)   # Preview without deleting
status = db.retention.status()                   # Show registered policies
```

---

## 21. Trust Plane Integration

When enabled, Express operations integrate with the CARE/EATP trust plane:

```python
db = DataFlow(
    "postgresql://...",
    trust_enforcement_mode="enforcing",
    trust_audit_enabled=True,
)
```

### 21.1 Enforcement Modes

| Mode           | Behavior                                              |
| -------------- | ----------------------------------------------------- |
| `"disabled"`   | No trust checks (default)                             |
| `"permissive"` | Trust checks run but failures are logged, not blocked |
| `"enforcing"`  | Trust checks run and failures block the operation     |

### 21.2 Trust Components

- `TrustAwareQueryExecutor` (`db._trust_executor`): Checks read/write access, records audit events
- `DataFlowAuditStore` (`db._audit_store`): Persists audit entries with optional Ed25519 signing
- `TenantTrustManager` (`dataflow.trust.multi_tenant.TenantTrustManager`): Available as a standalone class for cross-tenant delegation verification. NOT attached as a `db.*` facade — no framework hot-path invokes it today (orphan-detection MUST 3). Consumers who need cross-tenant verification instantiate it directly; when a production call site lands in express.py, the facade will be wired in the same PR.

### 21.3 Agent Context

```python
from dataflow.core.agent_context import set_agent_id, set_clearance

set_agent_id("agent-42")
set_clearance(DataClassification.PII)
```

---

## 22. Version

```python
from dataflow import __version__
assert __version__ == "2.0.7"
```

Both `pyproject.toml` and `__init__.py` must report the same version (zero-tolerance Rule 5).

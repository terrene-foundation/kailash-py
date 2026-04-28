# Kailash DataFlow — Core (DataFlow Class, Engine, Exceptions, Trust, Fabric)

Version: 2.4.0
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
    auto_migrate: Union[bool, str] = True,  # True | False | "warn"
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
| `auto_migrate`                 | `Union[bool, str]`         | `True`  | Auto-migration mode. `True` (fail-fast on DDL failure, default since v2.4.0), `False` (no DDL execution), or `"warn"` (legacy log-and-continue escape hatch). See § 1.6 Auto-Migrate Semantics. Typo strings (`"WARN"`, `"warning"`, etc.) raise `DataFlowConfigurationError` at `__init__`. |
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

### 1.6 Auto-Migrate Semantics

Origin: GitHub issue #696 (per `workspaces/dataflow-prod-incident`, 2026-04-28). The JourneyMate (Azure FastAPI + DataFlow) production incident logged `Failed to execute DDL: CREATE TABLE IF NOT EXISTS "evaluation_dimensions" ...` every 30 seconds for the lifetime of the deployment. Root cause: under `auto_migrate=True`, the original DDL-failure path emitted an ERROR log and `continued`. The schema cache was never marked as ensured, so every subsequent model access re-entered `ensure_table_exists()` and re-fired the failing CREATE TABLE — saturating Azure PostgreSQL `max_connections` within minutes.

The `auto_migrate` parameter accepts three values, each with a distinct behavioural contract. Strings other than `"warn"` (case-sensitive) are rejected at `__init__` with `DataFlowConfigurationError` so a typo (`"WARN"`, `"warning"`, `"true"`) cannot silently degrade behavior at deploy time.

| Value     | DDL execution        | On DDL failure (e.g. invalid type, FK ordering, role permission)                                                                                                                                                                                                                       | Subsequent access to failed model                                                                                                                                              |
| --------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `True`    | Yes (default)        | Records the failure on `_failed_table_creations[model_name] = FailedDDLRecord(timestamp, error_message, statement_preview)`. Emits exactly ONE `engine.ddl_failed_recorded` ERROR log per `(model, DataFlow instance)` pair. Raises `DDLFailedError` to the caller of the first access. | Fail-fast: raises `DDLFailedError` from the head of `ensure_table_exists()` BEFORE re-entering the DDL path. NO connection acquired, NO DDL fired, NO additional log emitted. |
| `False`   | No (skip mode)       | N/A — DDL never runs. Schema is assumed managed externally (Alembic, Liquibase, dba-issued DDL).                                                                                                                                                                                       | Standard SQL-layer access. SELECT/INSERT errors surface from the database normally; no circuit-breaker engagement.                                                             |
| `"warn"`  | Yes (legacy)         | Records the failure on `_failed_table_creations` AND emits the `engine.ddl_failed_recorded` ERROR log (same as fail-fast). Returns `False` from `ensure_table_exists()`. **Does NOT raise.**                                                                                            | Legacy retry-on-access: `_check_failed_ddl()` is a no-op, the DDL path resumes pre-#696 semantics. Operators who explicitly opt in accept the pool-leak risk this entails.    |

#### 1.6.1 The `DDLFailedError` Typed Surface

`DDLFailedError` (`dataflow.core.exceptions.DDLFailedError`, also exported at `dataflow.DDLFailedError`) is the structured exception raised by the fail-fast circuit breaker. It subclasses `DataFlowError` so callers using `except DataFlowError` continue to catch the new type without explicit import.

| Attribute            | Type             | Description                                                                                                                                                              |
| -------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `model_name`         | `str`            | The model whose `CREATE TABLE` / `ALTER TABLE` failed.                                                                                                                   |
| `original_error`     | `BaseException`  | The underlying exception from the DDL execution (PostgreSQL `UndefinedObject`, MySQL `OperationalError`, etc.). Operators do not need to chain `__cause__` to diagnose. |
| `statement_preview`  | `str` (≤200 ch)  | First 200 characters of the failed DDL statement. Bounded to avoid leaking large schema bodies through error chains shipped to log aggregators.                          |

The `str(DDLFailedError)` rendering includes `model_name`, `original_error` type+message, optionally `statement_preview` (when non-empty), and inline operator guidance: "Subsequent access to this model will fail-fast without re-firing the DDL. Diagnose the root cause, then restart the application to retry. Use `auto_migrate='warn'` (legacy) to opt into log-and-continue behavior instead of fail-fast."

#### 1.6.2 Diagnostic Surface — `_failed_table_creations`

`DataFlow._failed_table_creations: Dict[str, FailedDDLRecord]` is a public-but-frozen diagnostic surface readable by support scripts. The leading underscore signals "internal state — do not mutate" while keeping the surface observable for incident response. The dictionary maps model names to `FailedDDLRecord` (a `collections.namedtuple` with fields `timestamp`, `error_message`, `statement_preview`). An empty dict means no DDL failures have been recorded; missing-key lookups return `None`.

```python
# Operator script: enumerate failed migrations on a running instance
for model_name, record in db._failed_table_creations.items():
    print(f"{model_name}: {record.error_message[:80]} (at {record.timestamp})")
```

State is per-`DataFlow` instance — one tenant's failed DDL cannot poison another tenant's framework. The dictionary is cleared on application restart (the canonical recovery path documented on `DDLFailedError`); operators who fix the root cause without restarting can clear individual entries via `_clear_failed_ddl(model_name)` for advanced workflows.

#### 1.6.3 Idempotency Invariant — One ERROR Log Per (Model, Process) Pair

A failed `CREATE TABLE` / `ALTER TABLE` under `auto_migrate=True` produces exactly ONE `engine.ddl_failed_recorded` ERROR log + ONE metric increment per `(model, DataFlow instance)` pair, NOT N per request. The `_record_failed_ddl()` helper checks `_failed_table_creations` membership before logging — every subsequent failure for the same model returns the existing record without re-emitting the log line. This is the structural defense against the JourneyMate retry storm manifesting as log spam (200,000 ERROR lines / hour) even when the DDL retry itself were somehow re-fired.

The log line is structured (per `rules/observability.md` Rule 1) and carries `model_name`, `error_type`, `error_message` (truncated to 500 chars), `statement_preview`, and `auto_migrate_mode` (`"warn"` or `"fail-fast"`) so operators see at a glance whether this run is the new fail-fast surface or the legacy log-and-continue escape hatch.

#### 1.6.4 Cross-Reference

- `rules/zero-tolerance.md` Rule 3 — silent fallbacks BLOCKED. The pre-#696 `except Exception: continue` pattern in `ensure_table_exists()` was the canonical instance of this anti-pattern; `DDLFailedError` is the typed surface that converts it into a loud, fail-fast error.
- `rules/observability.md` Rule 7 — bulk operations MUST log partial failures at WARN. Issue #696 surfaced the analogous gap for DDL operations: a per-model failure that re-fires every 30 seconds with no aggregation-pipeline visibility. The idempotent-once ERROR log + the `auto_migrate_mode` field together close that gap for the DDL surface.
- `rules/dataflow-pool.md` Rule 2 — fail-fast at startup. The DDL fail-fast circuit breaker is the model-access-time analogue of the pool-config validator: convert a silent degradation into a deployment-time failure that surfaces before users observe broken endpoints.

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

| Method                           | Purpose                                                                |
| -------------------------------- | ---------------------------------------------------------------------- |
| `.validation(layer)`             | Set a `ValidationLayer` protocol implementation                        |
| `.classification_policy(policy)` | Set a `DataClassificationPolicy`                                       |
| `.slow_query_threshold(seconds)` | Slow query detection threshold (default: 1.0s)                         |
| `.validate_on_write(enabled)`    | Enable auto-validation before writes                                   |
| `.source(name, config)`          | Register an external data source                                       |
| `.fabric(**kwargs)`              | Configure fabric runtime parameters                                    |
| `.config(**kwargs)`              | Pass additional kwargs to `DataFlow`                                   |
| `.build()`                       | Build the engine (async — preserved for cross-SDK parity)              |
| `.build_sync()`                  | Build the engine synchronously (module-import-time / lru_cache safe)   |

**`build()` vs `build_sync()`** — both surfaces produce identical
engine state. `build()` is `async def` for cross-SDK parity with
kailash-rs (where engine construction IS legitimately async due to
Tokio runtime initialization); the kailash-py body has no `await`s and
delegates to `build_sync()` so the two surfaces share a single body
and cannot drift.

| Caller context                                        | Use         |
| ----------------------------------------------------- | ----------- |
| Module-import-time (`@lru_cache` factory, top-level)  | `build_sync()` |
| Inside a running event loop (Nexus, FastAPI, Jupyter) | `build_sync()` (or `await build()`) |
| Cross-SDK polyglot code that awaits build everywhere  | `build()`   |

Per `rules/patterns.md` § "Paired Public Surface — Consistent
Async-ness", offering both shapes is permitted here because the
underlying body is genuinely sync (no `asyncio.run` wrap) — neither
surface raises `RuntimeError` under any caller context. Per
`rules/cross-sdk-inspection.md` § 3a, a structural invariant test
pins the `async def` signature on `build()` so a future refactor that
drops it fails loudly.

### 14.1.1 Model Registration — `DataFlowEngine.register_model`

`DataFlowEngine.register_model(registry, model)` registers a model
end-to-end through the engine surface:

```python
engine = DataFlowEngine.builder("sqlite:///app.db").build_sync()
engine.register_model(None, UserModel)            # ← model registered
report = engine.get_model_classification_report(UserModel)
```

The `registry` argument is kept for cross-SDK parity with kailash-rs
(where the equivalent method takes a model registry instance);
kailash-py threads model registration through the DataFlow primitive
itself, so callers pass `None`. Removing the parameter would break
the cross-SDK signature contract.

`DataFlowEngine.register_model` delegates to
`DataFlow.register_model` (§ 14.1.2 below), so the engine path and
the `@db.model` decorator path produce identical state — entries in
`_models` / `_registered_models` / `_model_fields`, CRUD/bulk node
generation, classification-policy registration, deferred relationship
detection. Additionally, when the engine has a
`DataClassificationPolicy` set via `.classification_policy(policy)`,
the model is also registered with the policy so per-field
classification metadata is available for
`get_model_classification_report`.

### 14.1.2 `DataFlow.register_model` — Underlying Mechanism

`DataFlow.register_model(model_cls, *, replace=False, force_drop=False)`
is the programmatic counterpart to the `@db.model` decorator. Both
paths share the same body — `db.register_model(Foo)` produces
identical state to `@db.model class Foo`.

| Call                                                    | Behaviour                                                          |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `db.register_model(Foo)`                                | Registers `Foo`; returns `Foo` for chaining.                       |
| `db.register_model(Foo)` again                          | Raises `ValueError("already registered")`.                         |
| `db.register_model(Foo, replace=True)`                  | Refused — raises `ValueError("force_drop=True required")`.         |
| `db.register_model(Foo, replace=True, force_drop=True)` | Tears down prior registration and re-registers. Destructive.       |

The `replace` + `force_drop` two-flag pattern follows the
destructive-confirmation discipline mandated by
`rules/dataflow-identifier-safety.md` Rule 4 — re-registration may
DROP and recreate the underlying table, which is irreversible.

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
- ~~`TenantTrustManager`~~: REMOVED on 2026-04-27 (W6-006, finding F-B-05 in Wave 5 audit). The class and its `CrossTenantDelegation` companion were preserved as a standalone import after the `db._tenant_trust_manager` facade was withdrawn on 2026-04-18, but no framework hot-path ever materialised. Per `rules/orphan-detection.md` § 3 ("Removed = Deleted, Not Deprecated"), the source + tests were deleted entirely. **Reason:** 1,599 LOC of class + 1,741 LOC of unit tests verified behaviour the framework never invoked once. **User impact:** consumers using `from dataflow.trust import TenantTrustManager` get `ImportError` after upgrade. **When a production cross-tenant delegation requirement lands**, design the new surface against the framework's hot path (express, query engine) in the SAME PR — do NOT resurrect the orphan from git history without a real call site. Regression test at `tests/regression/test_trust_manager_wiring.py` enforces both the absent-facade AND deleted-class invariants.

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

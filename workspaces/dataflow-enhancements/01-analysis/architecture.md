# DataFlow Enhancements — Architecture

## 1. DerivedModelEngine (TSG-100 + TSG-101)

### Current State

DataFlow models are registered via `@db.model`, which reads class annotations, extracts fields, reads `__dataflow__` config, generates 11 `AsyncNode` subclasses per model, and stores them in `DataFlow._nodes`. Models represent direct database tables — there is no concept of computed or derived data.

### What Is Missing

Application-layer materialized views. A way to define "CustomerStats is computed from Order data" and have DataFlow keep the derived data in sync.

### Design: `@db.derived_model` Decorator

```python
@db.model
class Order:
    id: str
    customer_id: str
    total: float
    status: str

@db.derived_model(
    sources=["Order"],
    refresh="on_source_change",  # or "scheduled" or "manual"
    schedule="0 */6 * * *",     # only for refresh="scheduled"
)
class CustomerStats:
    id: str                     # = customer_id (the grouping key)
    total_orders: int
    total_spent: float
    last_order_date: Optional[datetime]

    @staticmethod
    def compute(sources: Dict[str, List[Dict]]) -> List[Dict]:
        """Compute derived records from source data."""
        orders = sources["Order"]
        by_customer = {}
        for o in orders:
            cid = o["customer_id"]
            if cid not in by_customer:
                by_customer[cid] = {
                    "id": cid, "total_orders": 0,
                    "total_spent": 0.0, "last_order_date": None,
                }
            by_customer[cid]["total_orders"] += 1
            by_customer[cid]["total_spent"] += o["total"]
        return list(by_customer.values())
```

### Registration Flow

1. `@db.derived_model` calls `@db.model(cls)` first — full node generation, table creation, 11 CRUD nodes.
2. Registers derived metadata in `DataFlow._derived_models[model_name]` as `DerivedModelMeta`.
3. On `db.initialize()`, sets up refresh hooks based on strategy.

### DerivedModelMeta Dataclass

```python
@dataclass
class DerivedModelMeta:
    model_name: str
    sources: List[str]
    refresh: Literal["on_source_change", "scheduled", "manual"]
    schedule: Optional[str]  # cron string, only for scheduled
    compute_fn: Callable
    last_refreshed: Optional[datetime] = None
    next_scheduled: Optional[datetime] = None
```

### Refresh Strategies

**`scheduled`** (TSG-100): `DerivedModelRefreshScheduler` starts one `asyncio.create_task()` per derived model. Each task loops: parse next cron time, sleep until due, trigger refresh. Uses stdlib-compatible cron parsing (`croniter` as optional dependency, fallback to interval arithmetic).

**`manual`** (TSG-100): No automatic refresh. User calls `await db.refresh_derived("CustomerStats")`.

**`on_source_change`** (TSG-101): Uses Core SDK `EventBus` (`kailash.middleware.communication.event_bus`). DataFlow write nodes emit `DomainEvent(event_type="dataflow.Order.create")` after each write. `DerivedModelEngine` subscribes to source model events and triggers recompute.

### Compute Execution Pipeline

1. For each source: `source_data[src] = await db.express.list(src, limit=None)` (paginated for large datasets)
2. Call `meta.compute_fn(source_data)` — returns `List[Dict]`
3. Execute `BulkUpsertNode` on derived model table with computed records
4. Update `meta.last_refreshed = datetime.now(UTC)`
5. Emit `dataflow.derived.refreshed` event

### Dependency Graph

```
Order (source) --[write event]--> DerivedModelEngine --[compute]--> CustomerStats (derived)
                                          ^
                                          |
                              EventBus (Core SDK, in-memory or Redis)
```

### Key Decision: EventBus, Not Nexus

The `on_source_change` feature uses the Core SDK's `EventBus`, NOT Nexus's event system. This keeps DataFlow independent of Nexus. If Nexus is running, a separate bridge (TSG-250) translates DataFlow events into Nexus events. That is an integration concern, not a DataFlow concern.

---

## 2. FileSourceNode (TSG-102)

### Current State

DataFlow can create, read, update, delete records — but has no way to ingest data from files. Users must parse files manually and call bulk operations.

### What Is Missing

A node that reads tabular data from files and produces records compatible with existing bulk nodes.

### Design

```python
class FileSourceNode(AsyncNode):
    node_type = "FileSourceNode"

    async def async_run(self, file_path: str, format: str = "auto",
                        column_mapping: Dict[str, str] = None,
                        type_coercion: Dict[str, str] = None,
                        batch_size: int = 1000,
                        skip_rows: int = 0,
                        encoding: str = "utf-8") -> Dict:
        # Returns {"records": List[Dict], "count": int, "errors": List[str]}
        ...
```

### Format Detection

- `.csv`/`.tsv` -> Python `csv` module (stdlib)
- `.xlsx`/`.xls` -> `openpyxl` (optional, lazy import)
- `.parquet` -> `pyarrow` (optional, lazy import)
- `.json`/`.jsonl` -> Python `json` module (stdlib)
- Manual override via `format` parameter

Missing optional dependencies raise `DataFlowDependencyError` with install hint.

### Express Surface

```python
result = await db.express.import_file("User", "/data/users.csv", column_mapping={...})
```

Chains internally to `FileSourceNode` -> `BulkUpsertNode` (upsert semantics by default).

### Processing Order

1. Apply `column_mapping` (rename keys)
2. Apply `type_coercion` (coerce values: `int`, `float`, `str`, `bool`, `datetime`)
3. Failed coercion: append to `errors` list, keep raw value (fail-soft)

### Registration

`FileSourceNode` is a standalone utility node, NOT auto-generated per model. Registered globally in Kailash `NodeRegistry` on DataFlow import.

---

## 3. Declarative ValidationRules (TSG-103)

### Current State

Validation infrastructure exists: `field_validators.py` has email, url, uuid, length, range, pattern, phone validators as pure functions. `@field_validator` decorator attaches validators to classes. But there is no declarative dict syntax — users must stack decorators.

### What Is Missing

A `__validation__` dict on model classes that maps to existing validators without requiring decorator syntax.

### Design

```python
@db.model
class User:
    id: str
    name: str
    email: str
    age: Optional[int] = None
    status: str = "active"

    __validation__ = {
        "name": {"min_length": 1, "max_length": 100},
        "email": {"validators": ["email"]},
        "age": {"range": {"min": 0, "max": 150}},
        "status": {"one_of": ["active", "inactive", "suspended"]},
    }
```

### Parser Logic

```python
def _apply_validation_dict(cls: type, validation_dict: dict) -> None:
    if not hasattr(cls, '__field_validators__'):
        cls.__field_validators__ = {}
    for field_name, rules in validation_dict.items():
        if field_name.startswith('_'):  # config keys like _config
            continue
        validators = []
        if 'min_length' in rules or 'max_length' in rules:
            validators.append(length_validator(
                min_len=rules.get('min_length'),
                max_len=rules.get('max_length')
            ))
        if 'validators' in rules:
            for v_name in rules['validators']:
                validators.append(NAMED_VALIDATORS[v_name])
        if 'range' in rules:
            validators.append(range_validator(**rules['range']))
        if 'one_of' in rules:
            validators.append(one_of_validator(rules['one_of']))
        if 'pattern' in rules:
            validators.append(pattern_validator(rules['pattern']))
        if 'custom' in rules:
            validators.append(rules['custom'])
        cls.__field_validators__[field_name] = validators
```

### Integration Points

- `@db.model` decorator reads `__validation__` (same location as `__dataflow__` reading, ~line 1057 in `engine.py`)
- `validate_model(instance)` works identically for both declaration approaches
- Express `create()`, `update()`, `upsert()` call `validate_model()` before node execution
- `DataFlow(validate_on_write=False)` disables globally (default: `True`)
- `db.validate("User", data_dict)` for manual validation

### New Validator

`one_of_validator(allowed: List)` — trivial: check `value in allowed_values`. Added to `field_validators.py`.

---

## 4. Express Cache Wiring (TSG-104)

### Current State — Two Disconnected Cache Systems

**System 1: `ExpressQueryCache`** in `features/express.py`:
- Simple LRU + TTL, per-Express-instance
- Invalidation: `self._cache.clear()` on ANY write (clears everything, not model-scoped)
- Hand-rolled `_generate_key` for cache keys

**System 2: `cache/` module**:
- `RedisCacheManager` (distributed)
- `InMemoryCache` (local)
- `CacheKeyGenerator` (structured key generation)
- `CacheInvalidator` with `InvalidationPattern` (model-scoped invalidation)
- `ListNodeCacheIntegration`
- Complete but NOT wired to Express at all

### What Is Missing

The two halves need to be connected. The `cache/` module is comprehensive; the Express API is what users call. The bridge does not exist.

### Design

Replace `ExpressQueryCache` with a wrapper around the `cache/` module:

```python
# In DataFlowExpress.__init__:
from ..cache.auto_detection import detect_cache_backend
from ..cache.manager import RedisCacheManager, InMemoryCache
from ..cache.keys import CacheKeyGenerator
from ..cache.invalidation import CacheInvalidator, InvalidationPattern

backend = detect_cache_backend(redis_url=db.redis_url)
if backend == CacheBackend.REDIS:
    self._cache_manager = RedisCacheManager(db.redis_url, default_ttl=db.cache_ttl)
else:
    self._cache_manager = InMemoryCache(default_ttl=db.cache_ttl)
self._key_gen = CacheKeyGenerator()
self._invalidator = CacheInvalidator(self._cache_manager)
```

### API Surface

```python
# Implicit cache (uses default TTL from DataFlow config)
users = await db.express.list("User", {"active": True})

# Explicit TTL override
users = await db.express.list("User", {"active": True}, cache_ttl=300)

# Bypass cache for this call
users = await db.express.list("User", {"active": True}, cache_ttl=0)

# Cache stats
stats = db.express.cache_stats()  # {"hits": N, "misses": N, "size": N, "backend": "redis"|"memory"}
```

### Key Improvements Over Current State

| Aspect | Before (ExpressQueryCache) | After (cache/ module) |
|---|---|---|
| Backend | In-memory only | Redis or in-memory (auto-detected) |
| Invalidation | Clear ALL on any write | Model-scoped: User write clears only User cache |
| Key generation | Hand-rolled `_generate_key` | `CacheKeyGenerator` with structured keys |
| Per-call control | None | `cache_ttl` parameter on every read method |
| Stats | None | `cache_stats()` with hit/miss/size |

### Cache Key Format

`"dataflow:{model}:{operation}:{hash_of_params}"` — produced by `CacheKeyGenerator`.

### Invalidation on Write

```python
# In create(), update(), delete(), upsert():
await self._invalidator.invalidate(InvalidationPattern.model_writes("User"))
# Clears only keys matching "dataflow:User:*"
```

---

## 5. ReadReplicaSupport (TSG-105)

### Current State — Infrastructure 80% Built

| Component | Status |
|---|---|
| `DatabaseQueryRouter` | Has `QueryType.READ`/`WRITE`, `RoutingStrategy.READ_REPLICA` |
| `DatabaseRegistry` | Has `is_read_replica` flag on `DatabaseConfig` |
| `DatabaseAdapter.execute_query()` | Single execution point |
| `DataFlow.__init__` `read_url` parameter | MISSING |

### What Is Missing

A simple `DataFlow(read_url="...")` surface that wires everything up.

### Design

```python
db = DataFlow(
    database_url="postgresql://primary:5432/app",
    read_url="postgresql://replica:5432/app",  # NEW parameter
)

# Writes go to primary
await db.express.create("User", {"id": "u1", "name": "Alice"})

# Reads go to replica
users = await db.express.list("User", {"active": True})

# Force primary read (read-your-writes)
users = await db.express.list("User", {"active": True}, use_primary=True)
```

### Adapter Initialization

```python
# In DataFlow.__init__:
if read_url:
    self._write_adapter = create_adapter(database_url)
    self._read_adapter = create_adapter(read_url)
    self._registry.register(self._write_adapter, is_primary=True)
    self._registry.register(self._read_adapter, is_read_replica=True)
    self._query_router = DatabaseQueryRouter(
        registry=self._registry,
        strategy=RoutingStrategy.READ_REPLICA
    )
else:
    self._adapter = create_adapter(database_url)
    self._query_router = None
```

### Routing Logic

```python
def _get_adapter(self, operation: str) -> DatabaseAdapter:
    if self._query_router is None:
        return self._adapter
    query_type = QueryType.READ if operation in ("list", "read", "count", "find_one") else QueryType.WRITE
    return self._query_router.get_adapter(query_type)
```

### Critical Rule: Transactions Always Use Primary

`DataFlow.transaction()` context manager always yields `_write_adapter`. Inside the context, all nodes use write adapter regardless of operation type. Read-your-writes within a transaction must hit the primary.

---

## 6. RetentionEngine (TSG-106)

### Current State

No retention infrastructure exists. DataFlow models store data indefinitely. The `__dataflow__` config reading infrastructure exists but has no retention key.

### Design

```python
@db.model
class AuditLog:
    id: str
    action: str
    user_id: str
    timestamp: datetime

    __dataflow__ = {
        "retention": {
            "policy": "archive",      # "archive" | "delete" | "partition"
            "after_days": 365,
            "archive_table": "audit_log_archive",
        }
    }
```

### Three Policies

**Archive**: Move records older than `after_days` to archive table (same schema). Atomic transaction:
```sql
INSERT INTO {archive_table} SELECT * FROM {table} WHERE {cutoff_field} < $1;
DELETE FROM {table} WHERE {cutoff_field} < $1;
```

**Delete**: Hard delete records older than `after_days`:
```sql
DELETE FROM {table} WHERE {cutoff_field} < $1
```

**Partition** (PostgreSQL only): Monthly partitions via `PARTITION BY RANGE`. Auto-create new partitions, detach old ones.

### Cutoff Field Resolution

1. Explicit `cutoff_field` in config
2. `created_at` if exists in model fields
3. `updated_at` if exists
4. First `datetime`-typed field
5. Raise `DataFlowConfigError`

### Express Surface

```python
result = await db.retention.run()
# Returns: {"AuditLog": {"archived": 1523, "deleted": 0}}

result = await db.retention.run(dry_run=True)
# Returns counts without executing

status = db.retention.status()
# Returns policy config + last_run per model
```

---

## 7. DataFlowEventMixin (TSG-201)

### Current State

The Core SDK `EventBus` exists at `kailash/middleware/communication/event_bus.py` with `DomainEvent` and `InMemoryEventBus`. DataFlow does not use it.

### What Is Missing

DataFlow write nodes need to emit events after successful operations. This is required for `on_source_change` derived model refresh and the DataFlow-Nexus event bridge.

### Design

```python
from kailash.middleware.communication import EventBus, DomainEvent
from kailash.middleware.communication.backends.memory import InMemoryEventBus

class DataFlowEventMixin:
    """Mixin for DataFlow to emit write events."""

    def _init_events(self):
        self._event_bus: EventBus = InMemoryEventBus()

    def _emit_write_event(self, model_name: str, operation: str,
                           record_id: Optional[str] = None) -> None:
        event = DomainEvent(
            event_type=f"dataflow.{model_name}.{operation}",
            data={
                "model": model_name,
                "operation": operation,
                "record_id": record_id,
            },
        )
        self._event_bus.publish(event)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def on_model_change(self, model_name: str, handler: Callable) -> None:
        self._event_bus.subscribe(f"dataflow.{model_name}.*", handler)
```

### Write Node Instrumentation

All 8 write nodes get one line at the end of `async_run()`:
```python
if hasattr(self.dataflow_instance, '_emit_write_event'):
    self.dataflow_instance._emit_write_event(
        self._model_name, self._operation, record_id=result.get("id")
    )
```

The `hasattr` guard ensures backward compatibility.

### Integration Map

| Component | Emits | Subscribes |
|---|---|---|
| CreateNode, UpdateNode, DeleteNode, UpsertNode | `dataflow.{Model}.{operation}` | -- |
| BulkCreate/Update/Delete/Upsert | `dataflow.{Model}.bulk_{operation}` | -- |
| DerivedModelEngine | `dataflow.derived.refreshed` | `dataflow.{source}.create/update/delete` |
| CacheInvalidator | -- | `dataflow.{Model}.*` (for cache invalidation) |
| RetentionEngine | `dataflow.retention.executed` | -- |
| User code | -- | Any pattern via `db.on_model_change()` |

### This Is NOT Nexus EventBus

DataFlow uses Core SDK EventBus (`kailash.middleware.communication`), completely independent of Nexus. The DataFlow-Nexus event bridge (TSG-250, in the Nexus workspace) is a separate integration layer that translates DataFlow events into Nexus events. DataFlow has no knowledge of Nexus.

### Import Dependency

`kailash.middleware.communication` is in `kailash` (Core SDK), which `kailash-dataflow` already depends on. No new package dependency.

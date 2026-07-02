# Engine.py Audit

## Source

`packages/kailash-dataflow/src/dataflow/core/engine.py` (~6400 lines, 336K)

This is the largest file in the codebase and the central hub for DataFlow.

## DataFlow.**init** Signature

Current parameters (relevant subset):

```python
def __init__(
    self,
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
    pools: Optional[Dict] = None,
    max_overflow: Optional[int] = None,
    enable_caching: Optional[bool] = None,
    log_level: Optional[int] = None,
    log_config: Optional[LoggingConfig] = None,
    **kwargs,
)
```

**NOT present**: `read_url`, `redis_url`, `validate_on_write`, any retention config, any event config.

## Model Registration: `@db.model`

The `model()` method (line ~1005):

1. Reads class annotations for field types
2. Reads `__dataflow__` dict for model configuration (table name, indexes)
3. Determines table name from `__tablename__` or class name
4. Stores model info in `self._models[model_name]`
5. Sets `cls._dataflow_config = getattr(cls, "__dataflow__", {})`
6. Adds multi-tenant support if enabled
7. Generates 11 CRUD nodes per model

### `__dataflow__` Config Parsing

Currently reads:

- `indexes` -- custom index definitions (via `ensure_model_indexes`)
- No other config keys are consumed

**NOT read**: `retention`, `validation`, `derived`, `sources`, `refresh`, `schedule`.

## Node Generation

Engine generates these nodes per model (11 total):

- `{Model}CreateNode`, `{Model}ReadNode`, `{Model}UpdateNode`, `{Model}DeleteNode`
- `{Model}ListNode`, `{Model}CountNode`, `{Model}UpsertNode`
- `{Model}BulkCreateNode`, `{Model}BulkUpdateNode`, `{Model}BulkDeleteNode`, `{Model}BulkUpsertNode`

All stored in `self._nodes` dict. Express accesses them via `self._db._nodes[node_name]`.

## Properties (Feature Access)

- `db.express` -> `DataFlowExpress` (lazy init)
- `db.express_sync` -> `SyncExpress` (lazy init)
- `db.bulk` -> `BulkOperations`
- `db.transactions` -> `TransactionManager`
- `db.connection` -> `ConnectionManager`
- `db.tenants` -> `MultiTenantManager` (if enabled)
- `db.cache` -> cache integration (if enabled)

**NOT present**: `db.retention`, `db.event_bus`, `db.on_model_change()`, `db.refresh_derived()`, `db.derived_model_status()`, `db.validate()`.

## Key Observations for Enhancements

1. **File size concern**: At 336K (6400 lines), engine.py is already enormous. Adding DerivedModel, ReadReplica, Retention, EventMixin, and Validation directly will push it further. The brief's approach of creating separate modules (`features/derived.py`, `features/retention.py`, `core/events.py`) and using mixins/delegation is the right strategy.

2. **`@db.model` is the integration point**: All features that need to read class config (`__validation__`, `__dataflow__["retention"]`) or register derived models (`@db.derived_model`) must hook into the model registration flow.

3. **`DataFlow.__init__` needs expansion**: New parameters: `read_url`, `redis_url`, `validate_on_write`. Keep parameter count manageable -- consider moving to `DataFlowConfig` for new features.

4. **Adapter management**: Currently single adapter. ReadReplica requires dual adapter management. This is the most architecturally significant change.

# DataFlow Enhancements -- Gap Analysis

## Brief Claims vs Actual Codebase

### TSG-100: DerivedModelEngine

| Claim                                               | Verified | Notes                    |
| --------------------------------------------------- | -------- | ------------------------ |
| `@db.model` decorator exists and generates 11 nodes | TRUE     | Confirmed in engine.py   |
| `__dataflow__` config reading exists                | TRUE     | Reads `indexes` key only |
| No computed/derived models                          | TRUE     | Nothing related exists   |
| DataFlow uses `self._models` dict                   | TRUE     | Keyed by model name      |

**No discrepancies found.** The brief accurately describes what exists and what's missing.

### TSG-102: FileSourceNode

| Claim                         | Verified | Notes                           |
| ----------------------------- | -------- | ------------------------------- |
| No file ingestion in DataFlow | TRUE     | No FileSourceNode or equivalent |
| `nodes/` directory exists     | TRUE     | 27 specialized node files       |
| BulkUpsertNode exists         | TRUE     | In `nodes/bulk_upsert.py`       |

**No discrepancies found.**

### TSG-103: Declarative ValidationRules

| Claim                              | Verified | Notes                                           |
| ---------------------------------- | -------- | ----------------------------------------------- |
| Validator functions exist          | TRUE     | email, url, uuid, length, range, pattern, phone |
| `@field_validator` decorator works | TRUE     | Confirmed in decorators.py                      |
| No declarative dict syntax         | TRUE     |                                                 |
| `validate_model()` exists          | TRUE     | Returns ValidationResult                        |

**Minor discrepancy**: Brief mentions `__validation__` as a separate attribute from `__dataflow__`. This is a design choice, not a gap. But it means two class-level dicts (`__dataflow__` for DataFlow config, `__validation__` for validation rules). Consider whether `__dataflow__["validation"]` would be more consistent.

### TSG-104: Express Cache Wiring

| Claim                                       | Verified | Notes                              |
| ------------------------------------------- | -------- | ---------------------------------- |
| ExpressQueryCache exists with nuclear clear | TRUE     | `self._cache.clear()` on any write |
| cache/ module exists and is comprehensive   | TRUE     | 7 files, Redis + InMemory          |
| cache/ is NOT wired to Express              | TRUE     | Zero imports between them          |
| RedisCacheManager exists                    | TRUE     | Full implementation                |
| InMemoryCache exists                        | TRUE     | LRU + TTL                          |
| CacheKeyGenerator exists                    | TRUE     | Structured key generation          |
| CacheInvalidator with InvalidationPattern   | TRUE     | Model-scoped patterns              |

**Critical discrepancy**: The brief implies simple "wiring" between cache/ and Express. In reality, `CacheInvalidator` is typed to `RedisCacheManager`, not a generic interface. When Redis is unavailable and `InMemoryCache` is used, `CacheInvalidator` cannot be instantiated directly. This requires either refactoring `CacheInvalidator` or creating an adapter. The brief underestimates this friction.

**Also missing from brief**: The `CacheKeyGenerator` takes `(model_name, sql, params)` but Express doesn't generate SQL -- it calls nodes directly. The key generator needs a different input format for Express integration, or Express needs to produce cache keys differently than the SQL-based approach.

### TSG-105: ReadReplica Support

| Claim                                        | Verified   | Notes                                              |
| -------------------------------------------- | ---------- | -------------------------------------------------- |
| DatabaseQueryRouter exists                   | TRUE       | Full routing logic                                 |
| DatabaseRegistry exists with is_read_replica | TRUE       |                                                    |
| RoutingStrategy.READ_REPLICA exists          | TRUE       |                                                    |
| QueryType.READ/WRITE exists                  | TRUE       |                                                    |
| Infrastructure is "80% built"                | OVERSTATED | Routing logic: 100%. Integration with DataFlow: 0% |

**Significant discrepancy**: The brief claims "infrastructure is 80% built." The routing infrastructure is complete in isolation, but it has ZERO integration with DataFlow's adapter layer. DataFlow uses a single adapter/connection manager. Adding dual-adapter support requires modifying how DataFlow manages database connections, which is architecturally significant. "80% built" is more like "routing logic exists; integration is 0%."

Also: `DatabaseRegistry.get_connection()` is asyncpg-only. It won't work with SQLite replicas (not that SQLite replicas make sense, but the code path would fail).

### TSG-106: RetentionEngine

| Claim                                | Verified       | Notes                                                                |
| ------------------------------------ | -------------- | -------------------------------------------------------------------- |
| No retention infrastructure exists   | PARTIALLY TRUE | Python DataFlow has none. Rust has RetentionPolicy/RetentionEnforcer |
| `__dataflow__` config reading exists | TRUE           | Only `indexes` key read currently                                    |

**Minor discrepancy**: The brief says "no retention infrastructure exists" in Python. This is true for DataFlow-native retention. However, the Rust SDK already has `RetentionPolicy` and `DataRetentionEnforcer` exposed through Python bindings. The Python implementation should be aware of the Rust API shape for cross-SDK alignment.

### TSG-201: DataFlowEventMixin

| Claim                                     | Verified | Notes                             |
| ----------------------------------------- | -------- | --------------------------------- |
| Core SDK EventBus exists                  | TRUE     | Abstract + InMemoryEventBus       |
| DomainEvent exists                        | TRUE     | Full dataclass with serialization |
| InMemoryEventBus is in backends/memory.py | TRUE     | Thread-safe, bounded              |
| DataFlow does not use EventBus            | TRUE     | Zero references                   |

**Critical discrepancy**: The architecture doc proposes `self._event_bus.subscribe(f"dataflow.{model_name}.*", handler)` with wildcard patterns. The InMemoryEventBus does NOT support wildcard subscriptions -- it uses exact event_type matching only. This requires a workaround (multiple specific subscriptions per model) or Core SDK changes.

**Also missing from brief**: InMemoryEventBus handlers are invoked SYNCHRONOUSLY. Derived model recompute inside a write handler would block the write operation. The architecture must dispatch recompute asynchronously.

## Missing Pieces Not Mentioned in Brief

1. **CacheInvalidator type coupling** -- requires refactoring or adapter for InMemoryCache backend.
2. **CacheKeyGenerator input mismatch** -- designed for SQL queries, Express doesn't produce SQL.
3. **EventBus wildcard gap** -- no pattern matching in subscriptions.
4. **Synchronous event dispatch** -- handlers block publishers, problematic for derived model recompute.
5. **engine.py merge conflict risk** -- 6+ features all modifying the same 6400-line file.
6. **`DataFlowEngine.builder()` already has `validate_on_write()`** -- the new `DataFlow(validate_on_write=...)` parameter needs to align with the existing builder pattern.
7. **SyncExpress** needs updates too -- any new Express methods (import_file, use_primary) must have sync variants.

## Risk Assessment

| Feature | Risk        | Key Risk Factor                                                            |
| ------- | ----------- | -------------------------------------------------------------------------- |
| TSG-100 | Medium      | Large new feature, cron scheduling complexity, paginated source queries    |
| TSG-101 | High        | EventBus wildcard gap, synchronous dispatch, circular dependency detection |
| TSG-102 | Low         | Straightforward file parsing, no deep framework integration                |
| TSG-103 | Low         | Validators exist, parser is simple mapping                                 |
| TSG-104 | Medium      | CacheInvalidator type coupling, CacheKeyGenerator input mismatch           |
| TSG-105 | Medium-High | Adapter layer redesign, single-adapter assumption pervasive                |
| TSG-106 | Medium      | SQL generation across 3 dialects, partition policy PostgreSQL-only         |
| TSG-201 | Medium      | EventBus wildcard gap, async dispatch needed, 8 node modifications         |

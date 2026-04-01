# Cross-Dependencies Analysis

## Dependency Graph (Verified)

```
Independent (no dependencies):
  TSG-102 (FileSourceNode)     -- new node + Express method, standalone
  TSG-104 (Express Cache)      -- wires existing cache/ to Express
  TSG-105 (ReadReplica)        -- wires existing router to DataFlow
  TSG-106 (RetentionEngine)    -- new feature, reads __dataflow__["retention"]

Has soft dependency:
  TSG-103 (Validation)         -- standalone, but TSG-100 benefits from it

Sequential chain:
  TSG-100 (DerivedModel scheduled/manual) -- new decorator + engine
      |
      v
  TSG-201 (DataFlowEventMixin)           -- Core SDK EventBus integration
      |
      v
  TSG-101 (DerivedModel on_source_change) -- extends TSG-100 with events
      |
      v
  TSG-250 (DataFlow-Nexus bridge)         -- Nexus workspace, out of scope
```

## Brief's Dependency Graph -- Verification

The brief's graph is ACCURATE with one nuance:

- Brief shows TSG-103 -> TSG-100 (Validation blocks DerivedModel). This is a soft dependency -- derived models BENEFIT from source validation but don't REQUIRE it. DerivedModel can ship without validation and add the accuracy guarantee later. The brief acknowledges this by making both P0/P1 but recommending Validation first in sequential order.

## Cross-Feature Integration Points

### All features touch `engine.py`

Every feature modifies `DataFlow.__init__` or `@db.model` or adds properties:

| Feature | engine.py Changes                                                                                  |
| ------- | -------------------------------------------------------------------------------------------------- |
| TSG-100 | `derived_model()` decorator, `_derived_models` dict, `refresh_derived()`, `derived_model_status()` |
| TSG-102 | `import_file()` on Express (in express.py, not engine.py)                                          |
| TSG-103 | `__validation__` reading in `@db.model`, `validate_on_write` param, `db.validate()`                |
| TSG-104 | `redis_url` param, cache backend init                                                              |
| TSG-105 | `read_url` param, dual adapter init, query routing                                                 |
| TSG-106 | `__dataflow__["retention"]` reading, `db.retention` property                                       |
| TSG-201 | `DataFlowEventMixin` inheritance, `_init_events()` call                                            |

This is a merge conflict risk when working in parallel. engine.py is the bottleneck.

### Express touches (features adding Express methods)

| Feature | express.py Changes                                                   |
| ------- | -------------------------------------------------------------------- |
| TSG-102 | `import_file()` method                                               |
| TSG-103 | `validate_model()` calls in create/update/upsert                     |
| TSG-104 | Replace ExpressQueryCache, add cache_stats(), modify all cache calls |
| TSG-105 | `use_primary` parameter on read methods                              |

### Shared infrastructure

- **Core SDK EventBus**: Used by TSG-201 (directly), TSG-101 (subscribes), future TSG-104 (could use events for cache invalidation instead of direct calls).
- **`__dataflow__` dict**: Used by TSG-103 (if `__validation__` were inside `__dataflow__`), TSG-106 (retention config). Currently TSG-103 uses a separate `__validation__` attribute, which is a design choice to keep concerns separated.

## Parallelization Assessment

The brief claims "parallelizable to ~2 sessions wall clock." This is optimistic but feasible IF:

1. Features are developed on separate branches
2. engine.py changes are carefully coordinated (or each feature adds a single focused method/property)
3. Express.py changes don't conflict (different methods being modified)

In practice, with a single agent working sequentially, the recommended order in the implementation plan is sound.

## Cross-SDK Alignment (Verified)

### kailash-rs DataFlow status

Searched kailash-rs codebase:

- **QueryCache**: `query_cache.rs` exists with DashMap + TTL. Already wired to DataFlow. Python is behind.
- **RetentionPolicy/RetentionEnforcer**: Exists in `bindings/kailash-python/src/dataflow.rs` as Python bindings. Rust has data classification and retention enforcement already. Python is behind.
- **DerivedModel**: No evidence in kailash-rs. Neither SDK has this yet.
- **FileSourceNode**: No evidence in kailash-rs. Neither SDK has this yet.
- **ReadReplica/read_url**: No evidence of `read_url` parameter in kailash-rs DataFlow.
- **Validation**: Rust has `PyPatternValidator` in Python bindings. Rust approach may differ from Python's decorator-based system.

### Alignment Risk

The brief's cross-SDK alignment table claims Rust has certain features. Findings:

- "Rust is ahead" on cache wiring: **TRUE** -- Rust has `QueryCache` wired to DataFlow.
- Rust has `RetentionPolicy` and `DataRetentionEnforcer`: **TRUE** -- these exist in the Python bindings of the Rust SDK.
- Rust has `#[dataflow::derived_model]`: **NOT VERIFIED** -- no evidence found. The brief may be describing planned rather than implemented features.

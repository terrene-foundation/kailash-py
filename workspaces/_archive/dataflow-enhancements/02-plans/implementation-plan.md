# DataFlow Enhancements — Implementation Plan

## Phase Overview

```
Phase 1: Standalone Features (parallel)              Phase 2: Event-Driven Features (sequential)
────────────────────────────────────────              ──────────────────────────────────────────
TSG-100: DerivedModel (scheduled+manual)  ─────────> TSG-201: DataFlowEventMixin
TSG-102: FileSourceNode                               │
TSG-103: Validation DSL                               v
TSG-104: Express Cache Wiring                        TSG-101: DerivedModel (on_source_change)
TSG-105: ReadReplica Support                          │
TSG-106: RetentionEngine                              v
                                                     TSG-250: DataFlow-Nexus event bridge
                                                              (in Nexus workspace)
```

## Phase 1: Standalone Features (All Parallel)

All Phase 1 features have zero dependencies on each other. They can be implemented in any order or in parallel.

### TSG-100: DerivedModelEngine — Scheduled + Manual Modes

**Effort**: 1 session
**Dependencies**: None
**Blocks**: TSG-101 (on_source_change mode)

Implements `@db.derived_model` decorator with `refresh="scheduled"` and `refresh="manual"` modes. The `on_source_change` mode is deferred to TSG-101 because it requires Core SDK EventBus integration.

**Implementation steps**:
1. Create `packages/kailash-dataflow/src/dataflow/features/derived.py` with `DerivedModelEngine`, `DerivedModelRefreshScheduler`, `DerivedModelMeta`
2. Add `derived_model()` decorator to `DataFlow` class in `core/engine.py`
3. Implement refresh compute pipeline: query sources -> `compute()` -> `BulkUpsertNode`
4. Add `DerivedModelRefreshScheduler` for cron-based scheduling
5. Add `{Model}RefreshNode` generation in `NodeGenerator`
6. Add `db.refresh_derived("ModelName")` manual trigger
7. Add `db.derived_model_status()` status reporting

**New files**:
- `packages/kailash-dataflow/src/dataflow/features/derived.py`

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/core/engine.py`
- `packages/kailash-dataflow/src/dataflow/nodes/` (RefreshNode generation)

### TSG-102: FileSourceNode

**Effort**: 1 session
**Dependencies**: None
**Blocks**: Nothing directly (enables kailash-ml data ingestion)

Implements `FileSourceNode` for CSV, Excel, Parquet, JSON/JSONL ingestion. Plus Express `import_file()` one-liner.

**Implementation steps**:
1. Create `packages/kailash-dataflow/src/dataflow/nodes/file_source.py` with `FileSourceNode`
2. Implement format detection from file extension
3. Implement CSV reader (stdlib `csv.DictReader`)
4. Implement JSON/JSONL reader (stdlib `json`)
5. Implement Excel reader (lazy `openpyxl` import with `DataFlowDependencyError`)
6. Implement Parquet reader (lazy `pyarrow` import with `DataFlowDependencyError`)
7. Implement `column_mapping` and `type_coercion` processing
8. Add `import_file()` to `DataFlowExpress` in `features/express.py`
9. Update `pyproject.toml` with optional extras: `[excel]` = openpyxl, `[parquet]` = pyarrow

**New files**:
- `packages/kailash-dataflow/src/dataflow/nodes/file_source.py`

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/nodes/__init__.py`
- `packages/kailash-dataflow/src/dataflow/features/express.py`
- `packages/kailash-dataflow/pyproject.toml`

### TSG-103: Declarative ValidationRules

**Effort**: 0.5 sessions
**Dependencies**: None
**Blocks**: TSG-100 (accuracy guarantee)

Adds `__validation__` dict syntax to `@db.model`. Parses into existing `__field_validators__` format.

**Implementation steps**:
1. Create `packages/kailash-dataflow/src/dataflow/validation/dsl.py` with `_apply_validation_dict()` parser
2. Add `one_of_validator` to `field_validators.py`
3. In `@db.model` decorator (`engine.py`), read `__validation__` and call `_apply_validation_dict()`
4. Add `validate_model()` call in Express `create()`, `update()`, `upsert()`
5. Add `DataFlow(validate_on_write=False)` parameter
6. Add `db.validate("ModelName", data_dict)` manual validation

**New files**:
- `packages/kailash-dataflow/src/dataflow/validation/dsl.py`

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/core/engine.py`
- `packages/kailash-dataflow/src/dataflow/validation/field_validators.py`
- `packages/kailash-dataflow/src/dataflow/features/express.py`

### TSG-104: Express Cache Wiring

**Effort**: 1 session
**Dependencies**: None
**Blocks**: Nothing directly

Replaces `ExpressQueryCache` with the `cache/` module. Gives Express Redis-backed, model-scoped caching.

**Implementation steps**:
1. Replace `ExpressQueryCache` class in `features/express.py` with `_cache_manager` attribute
2. Add cache backend auto-detection (Redis or InMemory)
3. Replace `_generate_key` with `CacheKeyGenerator`
4. Replace `self._cache.clear()` with `CacheInvalidator.invalidate(InvalidationPattern.model_writes(...))`
5. Add `cache_ttl` parameter to `list()`, `read()`, `count()`, `find_one()`
6. Add `db.express.cache_stats()`
7. Add `redis_url` and `cache_ttl` to `DataFlow.__init__`

**New files**: None (wiring existing modules)

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/features/express.py`
- `packages/kailash-dataflow/src/dataflow/core/engine.py`

### TSG-105: ReadReplica Support

**Effort**: 1 session
**Dependencies**: None
**Blocks**: Nothing directly

Adds `read_url` parameter to `DataFlow.__init__`, wires to existing `DatabaseQueryRouter`.

**Implementation steps**:
1. Add `read_url` parameter to `DataFlow.__init__` in `engine.py`
2. When `read_url` provided, create two adapters: `_write_adapter` + `_read_adapter`
3. Register both in `DatabaseRegistry` with correct flags
4. Add `_get_adapter(operation)` routing method
5. Add `use_primary` parameter to Express read methods
6. Ensure transactions always use write adapter
7. Add `db.health_check()` dual-adapter reporting

**New files**: None (wiring existing infrastructure)

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/core/engine.py`
- `packages/kailash-dataflow/src/dataflow/core/query_router.py` (verify routing logic)
- `packages/kailash-dataflow/src/dataflow/features/express.py`

### TSG-106: RetentionEngine

**Effort**: 1 session
**Dependencies**: None
**Blocks**: Nothing directly

Implements data retention policies via `__dataflow__["retention"]` config.

**Implementation steps**:
1. Create `packages/kailash-dataflow/src/dataflow/features/retention.py` with `RetentionEngine`, `RetentionPolicy`, `RetentionResult`
2. Read `__dataflow__["retention"]` in `@db.model` decorator
3. Implement archive SQL generation (INSERT INTO archive + DELETE FROM main, in transaction)
4. Implement delete SQL generation
5. Implement partition policy (PostgreSQL only, with adapter check)
6. Implement cutoff field resolution order
7. Add `db.retention.run()` and `db.retention.run(dry_run=True)`
8. Add `db.retention.status()`
9. Auto-create archive table with same schema if not exists

**New files**:
- `packages/kailash-dataflow/src/dataflow/features/retention.py`

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/core/engine.py`

---

## Phase 2: Event-Driven Features (Sequential)

Phase 2 features depend on each other and on Phase 1 completion.

### TSG-201: DataFlowEventMixin

**Effort**: 0.5 sessions
**Dependencies**: None (uses existing Core SDK EventBus)
**Blocks**: TSG-101 (on_source_change), TSG-250 (DataFlow-Nexus bridge)

Adds event emission to DataFlow write nodes using the Core SDK `EventBus`.

**Implementation steps**:
1. Create `packages/kailash-dataflow/src/dataflow/core/events.py` with `DataFlowEventMixin`
2. Add `DataFlowEventMixin` to `DataFlow` class inheritance in `engine.py`
3. Call `_init_events()` in `DataFlow.__init__`
4. Add `_emit_write_event()` call to all 8 write node classes (CreateNode, UpdateNode, DeleteNode, UpsertNode, BulkCreate, BulkUpdate, BulkDelete, BulkUpsert)
5. Add `db.event_bus` property
6. Add `db.on_model_change()` convenience subscription

**New files**:
- `packages/kailash-dataflow/src/dataflow/core/events.py`

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/core/engine.py`
- `packages/kailash-dataflow/src/dataflow/nodes/` (all 8 write node classes)

### TSG-101: DerivedModel on_source_change Mode

**Effort**: 0.5 sessions
**Dependencies**: TSG-100 (DerivedModelEngine base), TSG-201 (DataFlowEventMixin)
**Blocks**: TSG-250 (DataFlow-Nexus event bridge)

Extends DerivedModelEngine with `refresh="on_source_change"` mode.

**Implementation steps**:
1. Add `_setup_event_subscriptions()` to `DerivedModelEngine` in `features/derived.py`
2. Subscribe to `dataflow.{source}.*` events for each derived model with `on_source_change`
3. Trigger recompute asynchronously when source events fire
4. Add circular dependency detection at `db.initialize()` time
5. Implement per-source subscription (only relevant derived models recompute)

**New files**: None

**Modified files**:
- `packages/kailash-dataflow/src/dataflow/features/derived.py`

---

## Session Effort Summary

| Todo | Description | Effort | Phase | Dependencies |
|---|---|---|---|---|
| TSG-100 | DerivedModel (scheduled + manual) | 1 session | 1 | None |
| TSG-102 | FileSourceNode | 1 session | 1 | None |
| TSG-103 | Validation DSL | 0.5 sessions | 1 | None |
| TSG-104 | Express Cache Wiring | 1 session | 1 | None |
| TSG-105 | ReadReplica Support | 1 session | 1 | None |
| TSG-106 | RetentionEngine | 1 session | 1 | None |
| TSG-201 | DataFlowEventMixin | 0.5 sessions | 2 | None |
| TSG-101 | DerivedModel on_source_change | 0.5 sessions | 2 | TSG-100, TSG-201 |

**Total**: ~6.5 autonomous sessions

**With parallelization**: Phase 1 (6 items, all parallel, ~1-2 sessions wall clock) + Phase 2 (sequential, ~1 session) = ~2-3 sessions wall clock.

## Implementation Order (Recommended)

If implementing sequentially (single agent):

1. **TSG-103** (Validation) — 0.5 sessions. Quick win, blocks TSG-100's accuracy guarantee.
2. **TSG-100** (DerivedModel scheduled/manual) — 1 session. P0, most consequential feature.
3. **TSG-102** (FileSourceNode) — 1 session. Standalone, high value.
4. **TSG-104** (Express Cache) — 1 session. Wires existing infrastructure.
5. **TSG-105** (ReadReplica) — 1 session. Wires existing infrastructure.
6. **TSG-106** (Retention) — 1 session. Standalone, lower urgency.
7. **TSG-201** (EventMixin) — 0.5 sessions. Prerequisite for on_source_change.
8. **TSG-101** (DerivedModel on_source_change) — 0.5 sessions. Completes DerivedModel.

Rationale: Validation first (quick, blocks DerivedModel), then DerivedModel (P0), then independent features by value, then event-driven features last (they depend on the most things).

## Cross-Package Dependency

TSG-250 (DataFlow-Nexus event bridge) lives in the Nexus workspace, not this workspace. It depends on:
- TSG-101 (this workspace — DataFlow on_source_change)
- TSG-201 (this workspace — DataFlow EventMixin)
- TSG-220 (Nexus workspace — EventBus handler triggering)

The DataFlow workspace delivers TSG-201 and TSG-101. The Nexus workspace delivers TSG-250.

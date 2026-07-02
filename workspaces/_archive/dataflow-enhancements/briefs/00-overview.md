# DataFlow Enhancements — Complete Brief

## What We Are Building

Six enhancements to the Kailash DataFlow framework that fill the gaps between "zero-config CRUD" and a production-grade data platform. These are not new frameworks — they wire existing infrastructure together, add missing features, and expose them through the `db.express` API surface that users already know.

## The Six Enhancements

| Priority | Feature | Description | Effort |
|---|---|---|---|
| **P0** | DerivedModelEngine | Application-layer materialized views. Compute derived data from source models via user-defined `compute()` function. Three refresh modes: scheduled, manual, on_source_change. | 1 session + 0.5 session |
| **P1** | FileSourceNode | Read CSV, Excel, Parquet, JSON files and produce records compatible with BulkCreate/BulkUpsert. Express one-liner: `db.express.import_file()`. | 1 session |
| **P2** | Declarative ValidationRules | `__validation__` dict on model classes. Maps to existing validator functions. Validates on write via Express. | 0.5 sessions |
| **P1** | Express Cache Wiring | Replace simplistic `ExpressQueryCache` (clears-all-on-write) with the existing comprehensive `cache/` module. Gives users Redis-backed, model-scoped caching for free. | 1 session |
| **P1** | ReadReplicaSupport | `DataFlow(read_url="...")` parameter. Reads go to replica, writes go to primary. Wires existing `DatabaseQueryRouter` infrastructure. | 1 session |
| **P2** | RetentionEngine | Data retention policies declared in `__dataflow__["retention"]`. Archive, delete, or partition old records. | 1 session |

**Total: ~5.5 autonomous sessions, parallelizable to ~2 sessions wall clock.**

## Priority Order and Rationale

### P0: DerivedModelEngine (TSG-100 + TSG-101)

DerivedModelEngine is the most consequential DataFlow enhancement. It enables application-layer materialized views — computed data that stays in sync with source models. It blocks:
- The DataFlow-Nexus event bridge (TSG-250) — events must exist for the bridge to translate
- kailash-ml FeatureStore — domain features that aggregate source data

DerivedModel is split into two todos:
- **TSG-100**: Scheduled and manual refresh modes (zero external dependencies, ships in M1)
- **TSG-101**: `on_source_change` mode (depends on Core SDK EventBus integration via TSG-201)

### P1: FileSourceNode, Express Cache, ReadReplica

These three are independent, parallelizable first-movers:
- **FileSourceNode** (TSG-102): Blocks kailash-ml data ingestion path. Uses stdlib csv/json + lazy openpyxl/pyarrow imports.
- **Express Cache** (TSG-104): Quality improvement replacing known weakness (nuclear-option cache clear). Both halves (Express + cache module) already exist — work is connecting them.
- **ReadReplica** (TSG-105): Infrastructure is 80% built (`DatabaseQueryRouter`, `DatabaseRegistry` exist). Work is adding `read_url` parameter and creating two adapters.

### P2: Validation, Retention

Lower urgency but high value:
- **Validation** (TSG-103): The validator functions already exist. Work is parsing `__validation__` dict syntax. 0.5 sessions.
- **Retention** (TSG-106): Straightforward SQL generation. No dependencies on other features.

## Dependencies Between Features

```
TSG-103 (Validation)     TSG-102 (FileSource)     TSG-104 (Cache)     TSG-105 (Replica)     TSG-106 (Retention)
     |                        (independent)         (independent)       (independent)          (independent)
     v
TSG-100 (DerivedModel - scheduled/manual)
     |
     v
TSG-201 (DataFlowEventMixin)  ← Core SDK EventBus integration
     |
     v
TSG-101 (DerivedModel - on_source_change)
     |
     v
TSG-250 (DataFlow-Nexus event bridge)  ← cross-package, lives in Nexus workspace
```

Key observation: TSG-102, TSG-104, TSG-105, TSG-106 have zero dependencies. They can all start immediately, in parallel.

## Red Team Findings That Shaped the Design

### Round 1
- Dependency analysis confirmed TSG-100 can ship in M1 without event dependencies by deferring `on_source_change` to TSG-101.
- Validation (TSG-103) blocks DerivedModel accuracy guarantees — derived models should validate source data.

### Round 2
- DataFlow events auto-enable per DerivedModel with `on_source_change`. When a DerivedModel is registered with `refresh="on_source_change"`, DataFlow auto-enables event emission for that model's sources. No global opt-in. Zero overhead when no derived models use events.
- DataFlow uses Core SDK EventBus (`kailash.middleware.communication`), NOT Nexus EventBus. This keeps DataFlow independent of Nexus. The DataFlow-Nexus event bridge is a separate integration layer.

### Round 3
- Convergence achieved. All findings resolved.
- BackgroundService pattern established for scheduled work (both in Nexus and DataFlow's `DerivedModelRefreshScheduler`).

## Current Codebase State

### What Already Exists

| Component | Location | Status |
|---|---|---|
| Express API (`db.express`) | `features/express.py` | Working, widely used |
| `ExpressQueryCache` | `features/express.py` | Working but crude (clears ALL on any write) |
| `cache/` module | `cache/` directory | Complete: `RedisCacheManager`, `InMemoryCache`, `CacheKeyGenerator`, `CacheInvalidator`, `InvalidationPattern` — NOT wired to Express |
| Validation functions | `validation/field_validators.py` | Complete: email, url, uuid, length, range, pattern, phone validators |
| `@field_validator` decorator | `validation/decorators.py` | Working decorator approach |
| `DatabaseQueryRouter` | `core/query_router.py` | Has `QueryType.READ`/`WRITE`, `RoutingStrategy.READ_REPLICA`, `DatabaseRegistry` with `is_read_replica` flag |
| Core SDK EventBus | `kailash/middleware/communication/event_bus.py` | Has `DomainEvent`, `InMemoryEventBus` |
| Node generation | `core/engine.py` + `nodes/` | 11 nodes per model (CRUD + bulk) |
| Adapter layer | `adapters/` | PostgreSQL, SQLite, MySQL — connection pooling |

### What Is Missing

| Gap | Enhancement | Work Required |
|---|---|---|
| No computed/derived models | DerivedModelEngine | New decorator + refresh engine |
| No file ingestion | FileSourceNode | New node + Express `import_file()` |
| No declarative validation syntax | `__validation__` DSL | Parser + wiring to Express writes |
| Express cache disconnected from cache module | Cache wiring | Replace glue layer in Express |
| `read_url` not exposed | ReadReplica | Parameter + dual adapter setup |
| No retention policies | RetentionEngine | New engine + SQL generation |
| No DataFlow event emission | EventMixin | Mixin + write node instrumentation |

## Key Files to Modify

- `packages/kailash-dataflow/src/dataflow/core/engine.py` — `@db.derived_model` decorator, `read_url` parameter, `__validation__` parsing, event emission, retention config reading
- `packages/kailash-dataflow/src/dataflow/features/express.py` — Cache wiring, `use_primary` parameter, `import_file()`, validation-on-write
- `packages/kailash-dataflow/src/dataflow/core/nodes.py` — Event emission after write operations
- `packages/kailash-dataflow/src/dataflow/nodes/` — New `FileSourceNode`, event instrumentation in write nodes

New modules:
- `packages/kailash-dataflow/src/dataflow/features/derived.py` — `DerivedModelEngine`, `DerivedModelRefreshScheduler`
- `packages/kailash-dataflow/src/dataflow/features/retention.py` — `RetentionEngine`, retention policies
- `packages/kailash-dataflow/src/dataflow/core/events.py` — `DataFlowEventMixin`
- `packages/kailash-dataflow/src/dataflow/nodes/file_source.py` — `FileSourceNode`
- `packages/kailash-dataflow/src/dataflow/validation/dsl.py` — `_apply_validation_dict()` parser

## Cross-SDK Alignment

| Feature | Python (kailash-py) | Rust (kailash-rs) | Alignment |
|---|---|---|---|
| DerivedModel | `@db.derived_model` + `compute()` static method | `#[dataflow::derived_model]` proc macro + `compute()` trait method | Same compute signature, same refresh strategies |
| FileSourceNode | `FileSourceNode` AsyncNode, csv/json/openpyxl/pyarrow | `FileSourceNode` Node impl, csv/json/calamine(xlsx)/arrow | Arrow as shared exchange format |
| Validation | `__validation__` dict DSL | `#[validate(min_length = 2, email)]` field attributes | Both map to same `ValidationRule` enum |
| Express Cache | `cache/` module wired to Express, Redis or InMemory | `query_cache.rs` with DashMap + TTL already wired | Rust is ahead; Python wiring catches up |
| ReadReplica | `read_url` parameter, adapter-level routing | `read_url` in `DataFlowConfig`, sqlx pool routing | Same API shape: `DataFlow(read_url="...")` |
| Retention | `__dataflow__["retention"]` dict config | `#[dataflow::retention(days = 365, policy = "archive")]` attribute | Same SQL generation, different declaration syntax |

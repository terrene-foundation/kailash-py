# DataFlow Primitive/Engine Audit — 2026-04-07

**Audit scope**: Verify whether DataFlowEngine composes DataFlow primitive or duplicates it.

## Verdict: PERFECT COMPOSITION — No Refactor Needed

DataFlow is the model of correct framework-first architecture. Every other framework should match this pattern.

## Primitive Layer: `DataFlow`

**Location**: `packages/kailash-dataflow/src/dataflow/core/engine.py` (~5000 lines)

**Responsibilities** (all in the primitive, not duplicated):

- Database connection pooling via `ConnectionManager`
- Model registration via `@db.model` decorator
- Auto-generated CRUD nodes (11 nodes per model)
- Query execution via SQLAlchemy
- Schema discovery/caching, auto-migration, audit logging
- Transaction management, bulk operations, multi-tenancy
- Express API (`db.express.*`) — 23x faster CRUD via direct node invocation
- Retention engine, derived models

**Cross-framework imports** (minimal, only Core SDK):

```python
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
```

**Does NOT import**: `kailash.trust.*`, `kailash.pact`, `kailash.mcp_server`. Self-contained.

**Audit integration** is implemented locally in `dataflow/audit_integration.py`, not via `kailash.trust`. This is **a minor duplication** (DataFlow has its own audit) but not architecturally broken — it's an isolated feature that could be migrated to `kailash.trust.AuditStore` in a future cleanup.

## Engine Layer: `DataFlowEngine`

**Location**: `packages/kailash-dataflow/src/dataflow/engine.py` (495 lines)

**Constructor** (the smoking gun for composition):

```python
class DataFlowEngine:
    def __init__(
        self,
        dataflow: DataFlow,  # ← REQUIRED, no default
        validation: Optional[ValidationLayer] = None,
        classification: Optional[DataClassificationPolicy] = None,
        query_engine: Optional[QueryEngine] = None,
        validate_on_write: bool = False,
    ) -> None:
        self._dataflow = dataflow  # stores reference
        ...
```

**DataFlowEngine CANNOT exist without DataFlow.** It takes a DataFlow instance as a required parameter.

**Builder pattern** (`DataFlowEngineBuilder`):

```python
# Line 242 — creates primitive first
dataflow = DataFlow(database_url=..., slow_query_threshold=..., **kwargs)

# Lines 254-260 — wraps primitive with engine
engine = DataFlowEngine(
    dataflow=dataflow,
    validation=self._validation,
    classification=self._classification,
    query_engine=query_engine,
    validate_on_write=self._validate_on_write,
)
```

**Delegation**:

- `engine.register_model(model)` → `self._dataflow.register_model(model)`
- `engine.close()` → `self._dataflow.close()`
- `engine.dataflow` property → read-only access to underlying primitive

**Engine-only features** (not in primitive):

- `QueryEngine` — slow query tracking, performance stats
- `ValidationLayer` protocol — per-field validation enforcement (`validate_on_write`)
- `DataClassificationPolicy` protocol — field classification + retention rules
- `validate_record()`, `validate_fields()`, `classify_field()`, `get_retention_days()`, `get_model_classification_report()`, `health_check()`

## Composition Verdict (Strict)

| Aspect                     | Primitive     | Engine                      | Verdict                   |
| -------------------------- | ------------- | --------------------------- | ------------------------- |
| Connection pooling         | ✅ Owns       | ❌ Delegates                | Composition               |
| Model registration         | ✅ Owns       | ❌ Delegates                | Composition               |
| CRUD node generation       | ✅ Owns       | ❌ Delegates                | Composition               |
| Query execution            | ✅ Owns       | ❌ Delegates                | Composition               |
| Schema cache               | ✅ Owns       | ❌ Uses primitive's         | Composition               |
| Auto-migration             | ✅ Owns       | ❌ Delegates                | Composition               |
| Field validation           | ❌            | ✅ NEW feature              | Additive                  |
| Classification policy      | ❌            | ✅ NEW feature              | Additive                  |
| Query performance tracking | ❌            | ✅ NEW feature              | Additive                  |
| Constructor                | Takes nothing | **Takes DataFlow instance** | **Composition confirmed** |

## Express API Positioning (Clarification)

**Express lives on the primitive, not the engine.** `db.express.*` bypasses BOTH the engine AND workflow layers for 23x speedup on simple CRUD.

**Trade-off**: Express is fast but does NOT go through validation/classification/query tracking. Users choosing audit/governance must use workflow-based CRUD or engine methods.

**This is a deliberate design decision**, not a primitive/engine violation. Express is documented as a "primitive convenience" for performance-critical CRUD.

## Data Fabric Engine

**Location**: `packages/kailash-dataflow/src/dataflow/fabric/` (22 files, ~23K LOC)

**Relationship to DataFlowEngine**: Separate orchestrator. Accessed via primitive (`db.source()`, `@db.product()`, `db.start()`), not via DataFlowEngine methods.

**Minor cleanup opportunity**: DataFlowEngine builder has `.source()` and `.fabric()` stubs that store config but never initialize FabricRuntime. Wiring FabricRuntime into engine `build()` would complete the engine as a unified entry point. Non-critical.

## Historical Context

**Key commit: 034bd3bb (March 26, 2026)** — "add NexusEngine and DataFlowEngine with builder pattern (#77, #78)"

Commit message explicitly states:

> "Both follow the same pattern as kaizen-agents: primitives (Nexus, DataFlow) stay as L1, engines provide developer-friendly unified entry points."

DataFlowEngine was designed as composition from day one, matching kailash-rs's DataFlowEngine for cross-SDK parity (#86, #99).

## Recommendations

### ✅ No refactor required.

Three non-critical optimizations:

1. **Wire FabricRuntime into engine builder** — `.source()` and `.fabric()` stubs should actually initialize FabricRuntime in `build()`. Currently they store config but never use it.

2. **Consider migrating DataFlow's local audit_integration.py to `kailash.trust.AuditStore`** — eliminates the one audit duplication. Low priority.

3. **Add top-level README clarifying entry points** — "Simple CRUD: `from dataflow import DataFlow`. Enterprise with validation/classification: `from dataflow import DataFlowEngine`."

**DataFlow is the reference architecture for the rest of the platform.** When refactoring Kaizen and Nexus, the goal is to match DataFlow's composition pattern exactly.

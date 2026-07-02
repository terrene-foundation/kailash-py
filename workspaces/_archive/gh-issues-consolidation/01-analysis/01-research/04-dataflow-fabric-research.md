# DataFlow + Fabric Research — Issues #242, #243, #244

## Issue #242: ProvenancedField — Field-Level Source Tracking

### Current State

**No provenance tracking exists.** Field system lives in:

- `packages/kailash-dataflow/src/dataflow/core/schema.py` — `FieldType` enum (16 types), `FieldMeta` dataclass
- Models use Python dataclasses with type hints via `@db.model`
- `to_dict()` / `from_dict()` serialization on models

### Design Integration Points

1. **New Generic Type**: `Provenance[T]` wrapping value + source_type + source_detail + confidence + previous_value + change_reason
2. **FieldMeta Extension**: `provenance_enabled: bool` flag
3. **Serialization**: Two strategies:
   - **Strategy A (JSON column)**: JSONB column per provenance field — no migration, queryable, but N+1 columns
   - **Strategy B (separate table)**: `field_provenance` table — single table for all, queryable history, but requires JOINs
4. **Integration with DataFlowEventMixin**: Emit provenance metadata in write events

### Complexity: LARGE

New generic type system, serialization layer, query/filter support, validation framework integration. Estimated 800-1200 lines.

### Key Decision

Serialization strategy (JSON column vs separate table) affects query performance and migration complexity. Recommend **Strategy A (JSON column)** for simplicity — each `Provenance[T]` field serializes to a JSONB column alongside the value column.

---

## Issue #243: Audit Trail Persistence

### Current State: In-Memory Only

**Event Emission** (`packages/kailash-dataflow/src/dataflow/core/events.py`):

- `DataFlowEventMixin` fires events to `InMemoryEventBus` after every write
- Fire-and-forget — logged failures never break writes
- 8 write operations tracked: create, update, delete, upsert, bulk_create/update/delete/upsert

**Audit Events** (`packages/kailash-dataflow/src/dataflow/core/audit_events.py`):

- `DataFlowAuditEvent` dataclass with `to_dict()` / `from_dict()`
- `DataFlowAuditEventType` enum — 14 types
- **No persistence mechanism**

**Audit Integration** (`packages/kailash-dataflow/src/dataflow/core/audit_integration.py`):

- Stores events in in-memory list
- Supports filtering by event_type/entity_type/timestamp
- **Lost on restart**

**Audit Trail Manager** (`packages/kailash-dataflow/src/dataflow/core/audit_trail_manager.py`):

- retention_days, max_events, storage_path
- Can export to JSON file only
- **No database persistence, no query API**

### EventStoreBackend Status

**Does NOT exist in kailash-core.** InMemoryEventBus is the only backend.

### Implementation Plan

1. Define `EventStoreBackend` ABC: `append(event)`, `query(filters)`
2. PostgreSQL adapter: `audit_events` table, indexed on (entity_type, entity_id, timestamp)
3. SQLite adapter: Same schema, WAL mode
4. Query API: `get_audit_trail(model_name, record_id, start_time, end_time, limit)`
5. Wire into `AuditIntegration` with backend injection

### Complexity: MEDIUM

Abstract backend + 2 adapters + query API + index strategy. Similar to existing database adapters. Estimated 1200-1800 lines.

### Provenance Enrichment

When #242 lands, audit events should include provenance metadata in `changes` dict:

```python
changes: {
    "user_email": {
        "old_value": "alice@old.com",
        "new_value": "alice@new.com",
        "provenance": {"source": "crm_sync", "confidence": 0.95}
    }
}
```

---

## Issue #244: Consumer Adapter Registry

### Current State

**Fabric Engine design is complete** (see `workspaces/data-fabric-engine/`).

**Existing infrastructure**:

- `ProductRegistration` dataclass (`packages/kailash-dataflow/src/dataflow/fabric/products.py`): name, fn, mode, depends_on, staleness, auth, rate_limit
- `FabricServingLayer` (`packages/kailash-dataflow/src/dataflow/fabric/serving.py`): Auto-generates REST endpoints per product with validation and fabric headers

**Consumer concept does NOT exist yet.** Products serve a single canonical output via REST.

### Design

Consumer adapters transform canonical product data into consumer-specific schemas:

```python
# Pure function adapters
db.fabric.register_consumer("maturity_report", to_maturity_report)
db.fabric.register_consumer("chat_summary", to_chat_summary)

# Product declares which consumers it supports
@db.product("portfolio", consumers=["maturity_report", "chat_summary"])
async def portfolio(ctx):
    return canonical_data

# Consumers access their specific view
data = await db.fabric.get("portfolio", consumer="maturity_report")
```

### Integration Points

1. **Consumer Registry** on DataFlow/Fabric: register_consumer(name, fn)
2. **ProductRegistration**: Add `consumers: list[str]` field
3. **Serving Layer**: Add `?consumer=` query param to product endpoints
4. **Pipeline Hook**: After product function returns, before caching — run consumer transforms

### Complexity: MEDIUM

Consumer base class + registry + pipeline hook + endpoint integration. Estimated 1000-1400 lines.

---

## Dependency Matrix

| Issue                  | Dependencies                | Blocks                     |
| ---------------------- | --------------------------- | -------------------------- |
| #242 ProvenancedField  | None                        | #243 (optional enrichment) |
| #243 Audit Persistence | None                        | Compliance queries         |
| #244 Consumer Adapters | Fabric Engine (design done) | None                       |

**Safe implementation order**: #243 → #242 → #244 (or all in parallel — they're independent)

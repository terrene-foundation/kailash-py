---
description: DataFlow Provenance[T] field tracking and audit trail persistence
---

# Provenance + Audit Trail

## Provenance[T] — Field-Level Source Tracking

```python
from dataflow.core.provenance import Provenance, ProvenanceMetadata, SourceType

# Create with provenance
metadata = ProvenanceMetadata(
    source_type=SourceType.API_QUERY,
    source_detail="CRM API /contacts endpoint",
    confidence=0.95,
    change_reason="Quarterly refresh",
)
field = Provenance(value=70_000_000.0, metadata=metadata)

# Validation enforced
# confidence must be 0.0-1.0 and math.isfinite()
# source_type must be valid SourceType enum
# extracted_at defaults to datetime.now(UTC)
```

### SourceType Enum

`EXCEL_CELL`, `API_QUERY`, `CALCULATED`, `AGENT_DERIVED`, `MANUAL`, `DATABASE`, `FILE`

### Serialization

```python
d = field.to_dict()   # {"value": 70000000.0, "source_type": "api_query", "confidence": 0.95, ...}
f = Provenance.from_dict(d)  # Round-trip
```

## Audit Trail Persistence

```python
# Enable audit persistence (auto-creates audit_events table)
db = DataFlow("sqlite:///app.db", audit=True)
await db.start()

# Query audit trail
events = await db.audit.query(
    entity_type="LoanEntry",
    entity_id="loan-001",
    start_time=datetime(2026, 3, 1, tzinfo=UTC),
    end_time=datetime(2026, 4, 1, tzinfo=UTC),
)

# Convenience method
trail = await db.audit.get_trail("LoanEntry", "loan-001")
```

### EventStoreBackend

- `SQLiteEventStore` — WAL mode, indexed on (entity_type, entity_id), (timestamp)
- `PostgreSQLEventStore` — JSONB columns, asyncpg (optional dependency)
- Both auto-created on `DataFlow.start(audit=True)`

### datetime Note

All audit code uses `datetime.now(UTC)` — NOT `datetime.utcnow()` (deprecated since Python 3.12).

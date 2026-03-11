# Bug Report: DataFlow CREATE Node Datetime Serialization Failure

**Date**: 2025-01-13
**Reporter**: Kaizen Team
**Severity**: Medium (Non-blocking, operations succeed but ERROR logs emitted)
**Component**: DataFlow Core Nodes
**Affected Versions**: DataFlow v0.7.x, Core SDK v0.10.x

---

## Executive Summary

DataFlow CREATE operations fail JSON serialization validation when model fields include `datetime` types. The database INSERT succeeds, but Core SDK runtime rejects node outputs containing datetime objects, causing ERROR logs on every CREATE operation.

**Impact**: Operations succeed and data persists correctly, but ERROR logs pollute output and workflow state cannot be serialized for checkpoints/debugging.

---

## Root Cause

**Location**: `kailash_python_sdk/packages/kailash-dataflow/src/dataflow/core/nodes.py`
**Lines**: 1296, 1309, 1327, 1355, 1369, 1455 (all CREATE/UPDATE operations)

DataFlow CREATE node returns `{**kwargs, **row}` which includes the original input parameters. When these parameters contain datetime objects (common for `created_at`, `updated_at` fields), Core SDK's output validation correctly rejects them as non-JSON-serializable.

```python
# Current broken code in DataFlow nodes.py (line ~1296)
return {
    "status": "success",
    "operation": "create",
    "record": {**kwargs, **row},  # ❌ Includes datetime objects from kwargs
}
```

**Why this happens**:
1. User passes `created_at: datetime.now()` as node parameter
2. DataFlow executes INSERT with datetime → SQL adapter converts to appropriate DB type
3. INSERT succeeds (row_count=1) ✅
4. Node returns `{**kwargs, **row}` with original datetime object
5. Core SDK runtime validates outputs → finds datetime object → ERROR ❌

---

## Evidence

### Error Message
```
ERROR kailash.runtime.base:local.py:1845 Node create_user failed: Node outputs must be JSON-serializable. Failed keys: ['created_at']
```

### Test Output
```
✅ SQLite INSERT result: {'result': {'data': [{'rows_affected': 1}], 'row_count': 1, ...}}
❌ ERROR: Node outputs must be JSON-serializable. Failed keys: ['created_at']
```

### Reproduction Code
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from datetime import datetime

# Setup DataFlow with datetime field
db = DataFlow(database_url="sqlite:///test.db", auto_migrate=True)

@db.model
class Message:
    id: str
    content: str
    created_at: datetime  # ← This causes the bug

# Execute CREATE with datetime
workflow = WorkflowBuilder()
workflow.add_node(
    "MessageCreateNode",
    "create",
    {
        "id": "msg_123",
        "content": "Hello",
        "created_at": datetime.now(),  # ← Datetime object
    },
)

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
# ✅ INSERT succeeds: data in database
# ❌ ERROR log: Node outputs must be JSON-serializable
```

---

## Impact Assessment

| Aspect | Status | Details |
|--------|--------|---------|
| Database operations | ✅ Work | INSERTs/UPDATEs succeed, data persisted |
| Data retrieval | ✅ Work | SELECT queries return correct data |
| Test suite | ✅ Pass | Data validation passes |
| Runtime logs | ❌ ERROR | Every CREATE emits "Node outputs must be JSON-serializable" |
| Workflow state | ❌ Fail | Cannot serialize state for checkpoints |
| Production monitoring | ❌ Noisy | False positive errors in logs |

### Affected Operations
- CREATE (most common)
- UPDATE (when updating datetime fields)
- BULK_CREATE (batch operations)
- READ operations (unaffected - ListNode handles datetime serialization correctly)

---

## Recommended Fix

Add a serialization helper in DataFlow nodes.py to convert datetime objects to ISO 8601 strings:

```python
def _serialize_datetime_fields(self, record: dict) -> dict:
    """
    Convert datetime objects to ISO 8601 strings for JSON serialization.

    Required for Core SDK runtime output validation which rejects datetime objects.
    Handles nested dicts and preserves None values.

    Args:
        record: Dict potentially containing datetime objects

    Returns:
        Dict with datetime objects converted to ISO strings
    """
    from datetime import datetime, date

    if not record or not isinstance(record, dict):
        return record

    serialized = {}
    for field_name, value in record.items():
        if isinstance(value, datetime):
            # Convert datetime to ISO 8601 with microseconds
            serialized[field_name] = value.isoformat()
        elif isinstance(value, date):
            # Convert date to ISO 8601
            serialized[field_name] = value.isoformat()
        elif isinstance(value, dict):
            # Recursively serialize nested dicts
            serialized[field_name] = self._serialize_datetime_fields(value)
        else:
            serialized[field_name] = value

    return serialized
```

**Apply to all return statements in CREATE/UPDATE operations**:

```python
# Line ~1296 (CREATE operation)
return {
    "status": "success",
    "operation": "create",
    "record": self._serialize_datetime_fields({**kwargs, **row}),  # ✅ Serialized
}

# Line ~1355 (UPDATE operation)
return {
    "status": "success",
    "operation": "update",
    "record": self._serialize_datetime_fields({**kwargs, **updated_row}),  # ✅ Serialized
}

# Similar changes for lines: 1309, 1327, 1369, 1455
```

---

## Workaround (User-Side, Temporary)

Until DataFlow is fixed, users can convert datetime to ISO strings before passing to nodes:

```python
from datetime import datetime

# ❌ Broken (current)
workflow.add_node("CreateNode", "create", {
    "created_at": datetime.now()
})

# ✅ Workaround (temporary)
workflow.add_node("CreateNode", "create", {
    "created_at": datetime.now().isoformat()
})
```

**Drawback**: Loses automatic SQL adapter datetime conversion, may cause type errors in strict databases.

---

## Testing Strategy

### Unit Tests (Add to DataFlow test suite)

```python
def test_create_node_datetime_serialization():
    """Test CREATE node properly serializes datetime fields."""
    from datetime import datetime
    from dataflow import DataFlow
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime import LocalRuntime
    import json

    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=True)

    @db.model
    class Event:
        id: str
        name: str
        created_at: datetime

    # Create with datetime
    workflow = WorkflowBuilder()
    workflow.add_node(
        "EventCreateNode",
        "create",
        {
            "id": "evt_123",
            "name": "Test Event",
            "created_at": datetime(2025, 1, 13, 10, 30, 0),
        },
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Verify no errors
    assert "create" in results
    record = results["create"]["record"]

    # Verify datetime serialized to ISO string
    assert isinstance(record["created_at"], str)
    assert record["created_at"] == "2025-01-13T10:30:00"

    # Verify JSON serializable
    json.dumps(results)  # Should not raise
```

---

## Precedent

Similar datetime serialization is already implemented in:

1. **DataFlow ListNode** (line ~1500+): Properly serializes datetime in SELECT results
2. **Core SDK JSONEncoder**: Has datetime → ISO string conversion for API responses
3. **Nexus API layer**: Converts datetime to ISO before JSON serialization

**Consistency**: All output paths should serialize datetime uniformly.

---

## Recommendations

1. **Implement the fix** (add `_serialize_datetime_fields()` helper in DataFlow nodes.py)
2. **Add unit tests** to DataFlow test suite
3. **Update documentation** to clarify datetime handling
4. **Consider backport** to DataFlow v0.6.x if widely used

**Priority**: Medium (non-blocking but impacts production observability)

---

## Related Files

- **Kaizen Implementation**: `packages/kailash-kaizen/src/kaizen/memory/backends/dataflow_backend.py`
- **Test Evidence**: `packages/kailash-kaizen/tests/e2e/autonomy/memory/test_cold_tier_e2e.py`
- **Investigation Reports** (from dataflow-specialist):
  - DATAFLOW_BUG_SUMMARY.md
  - DATAFLOW_DATETIME_BUG_ANALYSIS.md

---

## Contact

For questions or additional context, refer to the investigation session where this bug was discovered and documented with comprehensive root cause analysis using dataflow-specialist and kaizen-specialist subagents.

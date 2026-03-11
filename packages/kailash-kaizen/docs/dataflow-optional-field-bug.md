# DataFlow v0.7.4: Optional Field Type Normalization Bug

**Date**: 2025-10-29
**Severity**: HIGH (affects all Optional fields in DataFlow models)
**Status**: Workaround implemented, upstream fix pending

## Summary

DataFlow v0.7.4 has a type normalization bug where `Optional[T]` is incorrectly stripped to `T` during node generation, causing Core SDK to treat optional fields as required parameters.

## Root Cause

When DataFlow generates workflow nodes from `@db.model` classes, it normalizes type hints but loses the `Optional` wrapper:

```python
# Model definition
metadata: Optional[dict]

# DataFlow's type normalization (BUG)
original_type=typing.Optional[dict] -> normalized_type=<class 'dict'>
```

This causes Core SDK's parameter validation to treat the field as **required**, even when:
- You pass `metadata={}`
- You pass `metadata=None`
- You set a default value

## Error Symptoms

```
ERROR:kaizen.memory.backends.dataflow_backend:Failed to save turn:
Node 'create_user' missing required inputs: ['metadata'].
Provide these inputs via connections, node configuration, or runtime parameters
```

Even though `metadata` is clearly passed in the node configuration, Core SDK rejects it because DataFlow stripped the `Optional` wrapper.

## Evidence

From test execution logs:

```
WARNING:dataflow.core.nodes:PARAM metadata:
  original_type=typing.Optional[dict] -> normalized_type=<class 'dict'>
```

The normalization process explicitly strips `Optional`, converting optional fields to required.

## Workaround

Use **non-optional type with default value** instead of `Optional[T]`:

### Before (BROKEN in v0.7.4)

```python
from typing import Optional
from dataflow import DataFlow

db = DataFlow(db_url="sqlite:///db.db")

@db.model
class Message:
    id: str
    content: str
    metadata: Optional[dict]  # ❌ BROKEN - stripped to dict
    created_at: datetime
```

### After (WORKS in v0.7.4)

```python
from dataflow import DataFlow

db = DataFlow(db_url="sqlite:///db.db")

@db.model
class Message:
    id: str
    content: str
    metadata: dict  # ✅ Use dict (not Optional[dict])
    created_at: datetime

# Set default value at class level
Message.metadata = {}  # ✅ Required for default behavior
```

### Alternative: Dynamic Model Creation

```python
model_class = type(
    "Message",
    (),
    {
        "__annotations__": {
            "id": str,
            "content": str,
            "metadata": dict,  # NOT Optional[dict]
            "created_at": datetime,
        },
        "metadata": {},  # Default value inline
    },
)

db.model(model_class)
```

## Affected Code Locations

### Fixed Files

1. **tests/e2e/autonomy/test_memory_e2e.py** (lines 142-148)
   - Changed `Optional[dict]` → `dict` with `{}` default
   - Added explanatory comment

2. **src/kaizen/memory/backends/dataflow_backend.py**
   - Updated class docstring with workaround instructions
   - Added note in `save_turn()` method about metadata handling

## Testing

Minimal reproduction test confirms the bug and workaround:

```python
# Test 1: Optional[dict] - FAILS
metadata: Optional[dict]
metadata = None
# Error: Node 'create_msg' missing required inputs: ['metadata']

# Test 2: dict with default - WORKS
metadata: dict
metadata = {}
# Success: Parameter validation passes
```

## Impact Assessment

**High severity** - affects any DataFlow model with optional fields:
- Optional[dict]
- Optional[str]
- Optional[int]
- Any `Optional[T]` type

**Workaround severity**: Low - simple type change with default value

## Upstream Fix Required

DataFlow maintainers need to fix type normalization to preserve `Optional` wrapper:

```python
# Current (BROKEN)
if hasattr(field_type, '__origin__') and field_type.__origin__ is Union:
    normalized = get_args(field_type)[0]  # Strips Optional

# Proposed fix
if hasattr(field_type, '__origin__') and field_type.__origin__ is Union:
    # Preserve Optional for parameter generation
    if type(None) in get_args(field_type):
        normalized = field_type  # Keep Optional[T] intact
    else:
        normalized = get_args(field_type)[0]
```

## References

- **Kailash Core SDK**: Parameter validation in `kailash.workflow.builder`
- **DataFlow**: Type normalization in `dataflow.core.nodes`
- **Issue Tracking**: To be filed with DataFlow team

## Related Documentation

- DataFlowBackend class docstring (updated)
- E2E test fixture comments (updated)
- This document

---

**Last Updated**: 2025-10-29
**Author**: Claude Code (via investigation with dataflow-specialist)
**Status**: Workaround deployed, monitoring for upstream fix

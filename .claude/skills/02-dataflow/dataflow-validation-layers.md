---
name: dataflow-validation-layers
description: "4-layer validation system: Models -> Parameters -> Connections -> Workflows. Build-time only, zero runtime overhead."
---

# DataFlow Validation Layers

## Validation Flow

```
@db.model        --> Layer 1: Model (primary key, field types, reserved fields)
add_node()       --> Layer 2: Parameter (required params, types, reserved fields)
add_connection() --> Layer 3: Connection (node exists, param exists, type compat, cycles)
workflow.build() --> Layer 4: Workflow (reachability, orphans, execution order)
runtime.execute()--> NO validation (zero overhead)
```

Total build-time overhead: ~4ms. Zero runtime overhead.

## Layer 1: Model Validation

Validates at `@db.model` decoration time.

```python
# VALID
@db.model
class User:
    id: str          # Primary key MUST be named 'id'
    email: str
    __dataflow__ = {'strict_mode': True}

# INVALID: Missing 'id', reserved field 'created_at', unsupported type
```

### Supported Types

| Python Type                   | PostgreSQL              | SQLite | Notes       |
| ----------------------------- | ----------------------- | ------ | ----------- |
| `str`, `int`, `float`, `bool` | Native                  | Native | Basic types |
| `dict`                        | JSONB                   | TEXT   | JSON fields |
| `List[T]`                     | T[] (PG), JSON (others) | TEXT   | Arrays      |
| `Optional[T]`                 | T NULL                  | T NULL | Nullable    |

## Layer 2: Parameter Validation

Validates at `add_node()` time.

```python
# CreateNode: requires 'id', validates types, blocks reserved fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123", "email": "alice@example.com"
})

# UpdateNode: requires 'filter' + 'fields' structure
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})

# DeleteNode: requires 'filter' (prevents accidental delete-all)
workflow.add_node("UserDeleteNode", "delete", {"filter": {"id": "user-123"}})
```

## Layer 3: Connection Validation

Validates at `add_connection()` time.

```python
# VALID: 4-param connection between existing nodes
workflow.add_connection("create", "id", "read", "id")

# INVALID: nonexistent node, nonexistent param, type mismatch, circular dependency
```

## Layer 4: Workflow Validation

Validates at `workflow.build()` time. Checks reachability, orphaned nodes, execution order.

```python
# VALID: Linear or branching workflows with connected nodes
built = workflow.build()

# WARNING: Orphaned nodes (no connections), unreachable nodes
```

## Strict Mode Configuration

```python
from dataflow.validation.strict_mode import StrictModeConfig

config = StrictModeConfig(
    enabled=True,
    validate_models=True,       # Layer 1
    validate_parameters=True,   # Layer 2
    validate_connections=True,  # Layer 3
    validate_workflows=True,    # Layer 4
    fail_fast=True,
    verbose=True
)

db = DataFlow("postgresql://...", strict_mode_config=config)
```

Layers can be selectively enabled/disabled.

## Extending Validation

```python
from dataflow.validation.validators import BaseValidator

class CustomValidator(BaseValidator):
    def validate_custom_rule(self, model: type) -> None:
        if not hasattr(model, 'email'):
            raise ValidationError("Model must have 'email' field")

# Plugin validators run automatically during Layer 1
@db.register_validator
class EmailValidator:
    def validate(self, model: type) -> None:
        pass  # Custom validation logic
```

## Requirements

- Python 3.10+, `kailash>=0.10.0`

---
name: dataflow-validation-dsl
description: "Declarative validation rules for DataFlow models via __validation__ dict. Use when asking about 'model validation', 'validation DSL', '__validation__', 'field validators', 'email validator', 'one_of', 'length validation', or 'pattern validation'."
---

# DataFlow Validation DSL

Declarative `__validation__` dict on `@db.model` classes for field validation without stacking decorators.

## Quick Reference

```python
@db.model
class User:
    id: str
    name: str
    email: str
    status: str
    age: int

    __validation__ = {
        "name":   {"min_length": 1, "max_length": 100},
        "email":  {"validators": ["email"]},
        "status": {"one_of": ["active", "inactive", "pending"]},
        "age":    {"range": {"min": 0, "max": 150}},
    }
```

## Available Rules

| Rule             | Syntax                               | Example                                |
| ---------------- | ------------------------------------ | -------------------------------------- |
| Length           | `{"min_length": N, "max_length": N}` | `{"min_length": 1, "max_length": 255}` |
| Named validators | `{"validators": ["name", ...]}`      | `{"validators": ["email", "url"]}`     |
| One-of (enum)    | `{"one_of": [...]}`                  | `{"one_of": ["active", "inactive"]}`   |
| Range            | `{"range": {"min": N, "max": N}}`    | `{"range": {"min": 0, "max": 100}}`    |
| Pattern (regex)  | `{"pattern": "regex"}`               | `{"pattern": "^[A-Z]{2}\\d{4}$"}`      |
| Custom           | `{"custom": callable}`               | `{"custom": lambda v: v > 0}`          |

## Named Validators

| Name    | Validates           |
| ------- | ------------------- |
| `email` | Email format        |
| `url`   | URL format          |
| `uuid`  | UUID format         |
| `phone` | Phone number format |

## Combining Rules

Multiple rules on a single field are combined (all must pass):

```python
__validation__ = {
    "code": {
        "min_length": 3,
        "max_length": 10,
        "pattern": "^[A-Z0-9]+$",
    },
    "email": {
        "validators": ["email"],
        "max_length": 255,
    },
}
```

## How It Works

The `__validation__` dict is parsed at `@db.model` decoration time into the internal `__field_validators__` format (same as `@field_validator` decorators). This means validation runs at the same points as decorator-based validation -- on create and update operations.

Keys starting with `_` are reserved for config (e.g., `_config`).

## Source Code

- `packages/kailash-dataflow/src/dataflow/validation/dsl.py` -- Parser
- `packages/kailash-dataflow/tests/unit/test_validation_dsl.py` -- Unit tests

---
name: dataflow-strict-mode
description: "Strict mode validation for DataFlow with 4-layer validation system (models, parameters, connections, workflows). Use when building production applications that require enhanced validation, catching errors before runtime, or enforcing data integrity constraints."
---

# DataFlow Strict Mode

Opt-in 4-layer validation: Models, Parameters, Connections, Workflows. Catches errors at build time, zero runtime overhead.

## Enable Strict Mode (3 Ways)

### Per-Model (Recommended)

```python
from dataflow import DataFlow
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    email: str
    name: str
    __dataflow__ = {'strict_mode': True}
```

### Global

```python
db = DataFlow("postgresql://localhost/mydb", strict_mode=True)
```

### Environment Variable

```bash
DATAFLOW_STRICT_MODE=true
```

### Priority: Per-model > Global > Environment variable

## 4 Validation Layers

### Layer 1: Model Validation

- Primary key `id` exists
- Field types are valid Python types
- No reserved field conflicts

```python
# INVALID: Missing primary key
@db.model
class Bad:
    email: str  # No 'id' field
    __dataflow__ = {'strict_mode': True}
# ValidationError: Model 'Bad' must have 'id' field as primary key
```

### Layer 2: Parameter Validation

- Required parameters present
- Types match model fields
- No reserved fields (`created_at`, `updated_at`) in user params
- CreateNode vs UpdateNode structure correctness

```python
# INVALID: Missing required 'id'
workflow.add_node("UserCreateNode", "create", {"email": "a@ex.com"})
# ValidationError: Missing required parameter 'id'

# INVALID: Wrong UpdateNode structure
workflow.add_node("UserUpdateNode", "update", {"id": "123", "name": "Alice"})
# ValidationError: UpdateNode requires 'filter' and 'fields' structure

# VALID
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "123"}, "fields": {"name": "Alice"}
})
```

### Layer 3: Connection Validation

- Source/target nodes exist
- Parameter names valid
- Types compatible
- No circular dependencies

### Layer 4: Workflow Validation

- All nodes reachable
- No orphaned nodes (except terminal)
- Execution order valid
- No conflicting parameter sources

## StrictModeConfig

```python
from dataflow.validation.strict_mode import StrictModeConfig

# Production (recommended)
config = StrictModeConfig(
    enabled=True,
    validate_models=True,
    validate_parameters=True,
    validate_connections=True,
    validate_workflows=True,
    fail_fast=True,   # Stop on first error
    verbose=False
)

# Development
config = StrictModeConfig(
    enabled=True, fail_fast=False, verbose=True  # Collect all errors, detailed output
)

db = DataFlow("postgresql://...", strict_mode_config=config)
```

Selective layers: set any `validate_*` to `False` to skip that layer.

## Production Patterns

### Per-Environment

```python
# Critical models always strict
@db.model
class User:
    id: str
    email: str
    __dataflow__ = {'strict_mode': True}  # Always validate

# Logging models flexible (uses env var or global setting)
@db.model
class Log:
    id: str
    message: str
```

```bash
# .env.development
DATAFLOW_STRICT_MODE=false
# .env.production
DATAFLOW_STRICT_MODE=true
```

### CI/CD Fail-Fast

```python
config = StrictModeConfig(enabled=True, fail_fast=True, verbose=True)
db = DataFlow("postgresql://...", strict_mode_config=config)
```

## Performance

- **Build time**: +1-5ms (one-time validation at `workflow.build()`)
- **Execution time**: 0ms overhead
- **Memory**: <1KB per validated node

## When to Use

**Use**: Production apps, critical models, CI/CD pipelines, team coding standards.
**Skip**: Rapid prototyping, logging/temp models, legacy migration (enable gradually).

**Recommended**: Start global-off, enable per-model for critical models, expand as codebase matures.

---
name: dataflow-strict-mode
description: "Strict mode validation for DataFlow with 4-layer validation system (models, parameters, connections, workflows). Use when building production applications that require enhanced validation, catching errors before runtime, or enforcing data integrity constraints."
---

# DataFlow Strict Mode - Production-Ready Validation

Opt-in validation system with 4 validation layers providing enhanced error detection before workflow execution.

> **Skill Metadata**
> Category: `dataflow/validation`
> Priority: `HIGH`
> SDK Version: `0.8.0+ / DataFlow 0.8.0`

## Quick Reference

- **4 Validation Layers**: Models → Parameters → Connections → Workflows
- **3-Tier Configuration**: Per-model > Global > Environment variable
- **Fail-Fast Mode**: Stop on first validation error (production default)
- **Verbose Mode**: Detailed validation messages (development/debugging)
- **Zero Performance Impact**: Validation only at build time, not execution

## Enable Strict Mode (3 Ways)

### Method 1: Per-Model (Recommended)

```python
@db.model
class User:
    id: str
    email: str
    __dataflow__ = {'strict_mode': True}
```

### Method 2: Global Configuration

```python
db = DataFlow("postgresql://...", strict_mode=True)
```

### Method 3: Environment Variable

```bash
DATAFLOW_STRICT_MODE=true
```

## When to Use Strict Mode

**Use when**: Building production applications, CI/CD pipelines, critical models
**Don't use when**: Rapid prototyping, temporary data models, legacy migration

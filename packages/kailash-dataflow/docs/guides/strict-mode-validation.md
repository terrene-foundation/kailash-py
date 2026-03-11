# DataFlow Strict Mode Validation Guide

## Table of Contents
1. [What is Strict Mode](#what-is-strict-mode)
2. [Why Use Strict Mode](#why-use-strict-mode)
3. [Quick Start](#quick-start)
4. [Validation Layers](#validation-layers)
5. [Error Codes Reference](#error-codes-reference)
6. [Common Patterns](#common-patterns)
7. [Migration Guide](#migration-guide)
8. [Troubleshooting](#troubleshooting)

---

## What is Strict Mode

**Strict Mode** is an opt-in validation system for DataFlow that catches configuration errors at **definition time** rather than runtime, improving developer experience and preventing production issues.

### Key Features
- **Three Validation Layers**: Model, Parameter, and Connection validation
- **Opt-in Design**: Backward compatible - only validates when enabled
- **Rich Error Messages**: Detailed error messages with solutions and code examples
- **Zero Performance Impact**: Validation only runs at definition time, not during workflow execution

### Architecture
```
┌─────────────────────────────────────────────────────────┐
│                   DataFlow Application                  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Strict Mode Validation System              │
├─────────────────────────────────────────────────────────┤
│  Layer 1: Model Validation                              │
│  └─ Validates model definitions at registration time    │
│                                                          │
│  Layer 2: Parameter Validation                          │
│  └─ Validates node parameters at add_node() time        │
│                                                          │
│  Layer 3: Connection Validation                         │
│  └─ Validates workflow connections at add_connection()  │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              DataFlow Core Execution Engine             │
└─────────────────────────────────────────────────────────┘
```

---

## Why Use Strict Mode

### Problems Strict Mode Solves

#### Before Strict Mode ❌
```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    user_id: str  # ⚠️ DataFlow requires 'id' as primary key - only discovered at runtime!
    name: str
    created_at: datetime  # ⚠️ Conflicts with auto-managed field - only discovered at runtime!

# Workflow builds without errors
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice"  # ⚠️ Missing required 'id' parameter - only discovered at runtime!
})

# Errors only appear when executing the workflow
results, _ = runtime.execute(workflow.build())  # ❌ FAILS AT RUNTIME
```

#### After Strict Mode ✅
```python
from dataflow import DataFlow

db = DataFlow("postgresql://...", strict_mode=True)

@db.model
class User:
    user_id: str  # ❌ IMMEDIATE ERROR: Primary key must be named 'id'
    name: str
    created_at: datetime  # ❌ IMMEDIATE ERROR: Field 'created_at' conflicts with auto-managed field

# Corrected model
@db.model
class User:
    id: str  # ✅ Correct primary key
    name: str
    # created_at auto-managed by DataFlow

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice"  # ❌ IMMEDIATE ERROR: Missing required parameter 'id'
})

# Corrected workflow
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",  # ✅ All required parameters provided
    "name": "Alice"
})

# Executes successfully
results, _ = runtime.execute(workflow.build())  # ✅ SUCCESS
```

### Benefits
1. **Faster Development**: Catch errors immediately, not after minutes of execution
2. **Better Error Messages**: Rich error messages with solutions and code examples
3. **Prevent Production Issues**: Validate configurations before deployment
4. **Improved DX**: Clear, actionable feedback during development

---

## Quick Start

### Enable Strict Mode

```python
from dataflow import DataFlow

# Enable strict mode for immediate error detection
db = DataFlow("postgresql://...", strict_mode=True)
```

### Three Validation Levels

#### 1. Off Mode (Default)
```python
db = DataFlow("postgresql://...")  # No validation
```

#### 2. Warn Mode
```python
db = DataFlow("postgresql://...", validation_mode="warn")
# Logs warnings but allows execution
```

#### 3. Strict Mode (Recommended for Development)
```python
db = DataFlow("postgresql://...", strict_mode=True)
# Raises errors immediately on invalid configuration
```

---

## Validation Layers

### Layer 1: Model Validation

Validates model definitions at **registration time** (when using `@db.model` decorator).

#### Validation Rules

##### Rule 1: Primary Key Validation
```python
# ❌ WRONG: Missing primary key
@db.model
class User:
    name: str

# ERROR: STRICT_MODEL_101
# Model 'User' does not define a primary key field.
# Solution: Add 'id: <type>' field to your model

# ✅ CORRECT: Primary key defined
@db.model
class User:
    id: str  # Primary key must be named 'id'
    name: str
```

##### Rule 2: Auto-Managed Field Conflicts
```python
# ❌ WRONG: Manually defining auto-managed fields
@db.model
class User:
    id: str
    name: str
    created_at: datetime  # Conflicts with auto-managed field
    updated_at: datetime  # Conflicts with auto-managed field

# ERROR: STRICT_MODEL_102
# Field 'created_at' conflicts with auto-managed field.
# Solution: Remove 'created_at' from model - DataFlow manages it automatically

# ✅ CORRECT: Let DataFlow manage timestamps
@db.model
class User:
    id: str
    name: str
    # created_at and updated_at managed by DataFlow
```

##### Rule 3: Field Type Validation
```python
# ⚠️ WARNING: Datetime without timezone
@db.model
class User:
    id: str
    login_time: datetime  # Missing timezone awareness

# WARNING: STRICT_MODEL_103
# Field 'login_time' uses datetime without timezone awareness.
# Solution: Use timezone-aware datetime fields

# ✅ CORRECT: Timezone-aware datetime
from datetime import datetime

@db.model
class User:
    id: str
    login_time: datetime  # DataFlow handles timezone conversion
```

##### Rule 4: Naming Convention Validation
```python
# ⚠️ WARNING: CamelCase field names
@db.model
class User:
    id: str
    firstName: str  # CamelCase not recommended
    lastName: str   # CamelCase not recommended

# WARNING: STRICT_MODEL_104
# Field 'firstName' uses camelCase. Consider snake_case for consistency.
# Solution: Use snake_case naming convention

# ✅ CORRECT: Snake case naming
@db.model
class User:
    id: str
    first_name: str  # Snake case
    last_name: str   # Snake case
```

---

### Layer 2: Parameter Validation

Validates node parameters at **add_node() time** (when adding nodes to workflow).

#### Validation Rules

##### Rule 1: CreateNode Parameter Validation
```python
# ❌ WRONG: Missing required 'id' parameter
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# ERROR: STRICT_PARAM_101
# Missing required parameter 'id' for CreateNode.
# Solution: Provide 'id' parameter with valid value

# ✅ CORRECT: All required parameters provided
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",  # Required
    "name": "Alice",
    "email": "alice@example.com"
})
```

##### Rule 2: Auto-Managed Fields in CreateNode
```python
# ❌ WRONG: Manually setting auto-managed fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": "2025-01-01T00:00:00"  # Auto-managed, shouldn't be set manually
})

# ERROR: STRICT_PARAM_102
# Auto-managed field 'created_at' should not be set manually in CreateNode.
# Solution: Remove 'created_at' from parameters - DataFlow manages it automatically

# ✅ CORRECT: Let DataFlow manage timestamps
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # created_at managed by DataFlow
})
```

##### Rule 3: UpdateNode Parameter Validation
```python
# ❌ WRONG: Missing 'filter' and 'fields' structure
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "Alice Updated"
})

# ERROR: STRICT_PARAM_104
# UPDATE request must contain 'filter' field.
# Solution: Use {'filter': {...}, 'fields': {...}} structure

# ✅ CORRECT: Proper UPDATE structure
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

##### Rule 4: Type Validation
```python
# ❌ WRONG: Type mismatch
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "age": "twenty-five"  # Should be int, not str
})

# ERROR: STRICT_PARAM_103
# Type mismatch for field 'age': expected int, got str.
# Solution: Provide value of correct type: int

# ✅ CORRECT: Correct types
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "age": 25  # Correct type
})
```

---

### Layer 3: Connection Validation

Validates workflow connections at **add_connection() time** (when connecting nodes).

#### Validation Rules

##### Rule 1: Node Existence Validation
```python
# ❌ WRONG: Connecting to non-existent node
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_connection("create_user", "id", "read_user", "id")  # 'read_user' doesn't exist

# ERROR: STRICT_CONN_201
# Destination node 'read_user' not found in workflow.
# Solution: Add node 'read_user' before creating connection

# ✅ CORRECT: Both nodes exist
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("UserReadNode", "read_user", {...})
workflow.add_connection("create_user", "id", "read_user", "id")
```

##### Rule 2: Connection Parameter Validation
```python
# ❌ WRONG: Empty connection parameters
workflow.add_connection("create_user", "", "read_user", "id")  # Empty source_output

# ERROR: STRICT_CONN_202
# Source output parameter cannot be empty.
# Solution: Provide valid source output parameter

# ✅ CORRECT: Valid connection parameters
workflow.add_connection("create_user", "id", "read_user", "id")
```

##### Rule 3: Dot Notation Validation
```python
# ❌ WRONG: Invalid dot notation
workflow.add_connection("create_user", ".data.field", "read_user", "input")  # Leading dot

# ERROR: STRICT_CONN_204
# Invalid dot notation in source_output: '.data.field' has leading/trailing dot.
# Solution: Remove leading/trailing dots from parameter

# ✅ CORRECT: Valid dot notation
workflow.add_connection("create_user", "data.field", "read_user", "input")
```

##### Rule 4: Reserved Field Validation
```python
# ❌ WRONG: Using reserved field names
workflow.add_connection("create_user", "data.error.field", "read_user", "input")  # 'error' is reserved

# ERROR: STRICT_CONN_205
# Reserved field 'error' in source_output dot notation: 'data.error.field'.
# Solution: Avoid using reserved field name 'error'

# ✅ CORRECT: Avoid reserved fields
workflow.add_connection("create_user", "data.result.field", "read_user", "input")
```

##### Rule 5: Self-Connection Validation
```python
# ❌ WRONG: Node connecting to itself
workflow.add_connection("create_user", "output", "create_user", "input")  # Self-connection

# ERROR: STRICT_CONN_206
# Self-connection detected: node 'create_user' connects to itself.
# Solution: Connect to a different node

# ✅ CORRECT: Connect to different node
workflow.add_connection("create_user", "output", "read_user", "input")
```

##### Rule 6: Circular Dependency Detection
```python
# ❌ WRONG: Creating circular dependencies
workflow.add_connection("node1", "output", "node2", "input")
workflow.add_connection("node2", "output", "node3", "input")
workflow.add_connection("node3", "output", "node1", "input")  # Creates cycle

# ERROR: STRICT_CONN_207
# Circular dependency detected: adding connection from 'node3' to 'node1' would create cycle.
# Solution: Remove connections that create circular dependency

# ✅ CORRECT: Linear workflow
workflow.add_connection("node1", "output", "node2", "input")
workflow.add_connection("node2", "output", "node3", "input")
workflow.add_connection("node3", "output", "node4", "input")  # No cycle
```

---

## Error Codes Reference

### Model Validation Errors (STRICT_MODEL_1XX)

| Error Code | Description | Solution |
|------------|-------------|----------|
| **STRICT_MODEL_101** | Missing primary key | Add `id: <type>` field to model |
| **STRICT_MODEL_102** | Auto-managed field conflict | Remove `created_at`, `updated_at`, `created_by`, `updated_by` |
| **STRICT_MODEL_103** | Datetime without timezone | Use timezone-aware datetime fields |
| **STRICT_MODEL_104** | Invalid naming convention | Use snake_case for field names |
| **STRICT_MODEL_105** | Reserved field name | Avoid using SQL reserved keywords |

### Parameter Validation Errors (STRICT_PARAM_1XX)

| Error Code | Description | Solution |
|------------|-------------|----------|
| **STRICT_PARAM_101** | Missing required parameter | Provide required `id` parameter for CreateNode |
| **STRICT_PARAM_102** | Auto-managed field in CreateNode | Remove `created_at`, `updated_at` from parameters |
| **STRICT_PARAM_103** | Type mismatch | Provide value of correct type |
| **STRICT_PARAM_104** | Missing `filter` in UpdateNode | Use `{'filter': {...}, 'fields': {...}}` structure |
| **STRICT_PARAM_105** | Missing `fields` in UpdateNode | Use `{'filter': {...}, 'fields': {...}}` structure |
| **STRICT_PARAM_106** | Auto-managed field in UpdateNode fields | Remove `created_at`, `updated_at` from `fields` |
| **STRICT_PARAM_107** | Invalid filters type in ListNode | Provide `filters` as dict |
| **STRICT_PARAM_108** | Invalid limit in ListNode | Provide `limit >= 1` |
| **STRICT_PARAM_109** | Invalid offset in ListNode | Provide `offset >= 0` |

### Connection Validation Errors (STRICT_CONN_2XX)

| Error Code | Description | Solution |
|------------|-------------|----------|
| **STRICT_CONN_201** | Node not found | Add missing node before creating connection |
| **STRICT_CONN_202** | Empty connection parameter | Provide non-empty parameter names |
| **STRICT_CONN_204** | Invalid dot notation | Remove leading/trailing/consecutive dots |
| **STRICT_CONN_205** | Reserved field in dot notation | Avoid `error`, `success`, `metadata`, `_internal` |
| **STRICT_CONN_206** | Self-connection detected | Connect to different node |
| **STRICT_CONN_207** | Circular dependency detected | Remove connections creating cycles |

---

## Common Patterns

### Pattern 1: Development with Strict Mode

```python
from dataflow import DataFlow

# Development: Enable strict mode for immediate feedback
db = DataFlow("postgresql://localhost/dev_db", strict_mode=True)

@db.model
class User:
    id: str
    email: str
    name: str

# All validation errors caught immediately
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "email": "alice@example.com",
    "name": "Alice"
})
```

### Pattern 2: Production with Warn Mode

```python
import os

# Production: Use warn mode to log issues without breaking
validation_mode = "strict" if os.getenv("ENV") == "development" else "warn"
db = DataFlow("postgresql://prod/db", validation_mode=validation_mode)
```

### Pattern 3: Gradual Migration

```python
# Step 1: Enable warn mode to identify issues
db = DataFlow("postgresql://...", validation_mode="warn")

# Step 2: Fix warnings over time
# Review logs and fix reported issues

# Step 3: Enable strict mode once all warnings resolved
db = DataFlow("postgresql://...", strict_mode=True)
```

### Pattern 4: Per-Model Validation Control

```python
db = DataFlow("postgresql://...", strict_mode=True)

# Skip validation for specific models (backward compatibility)
@db.model
class LegacyModel:
    user_id: str  # Non-standard primary key

    __dataflow__ = {
        'skip_validation': True  # Disable validation for this model
    }

# Strict validation for new models
@db.model
class NewModel:
    id: str  # Standard primary key
    name: str
```

---

## Migration Guide

### Migrating Existing Projects to Strict Mode

#### Step 1: Enable Warn Mode
```python
# Before
db = DataFlow("postgresql://...")

# After
db = DataFlow("postgresql://...", validation_mode="warn")
```

#### Step 2: Review Warnings
```bash
# Run your application and review logs
python your_app.py 2>&1 | grep "STRICT_"
```

#### Step 3: Fix Common Issues

##### Issue 1: Primary Key Not Named 'id'
```python
# Before
@db.model
class User:
    user_id: str
    name: str

# After
@db.model
class User:
    id: str  # Renamed from user_id
    name: str

# Update existing data migration if needed
```

##### Issue 2: Manual Timestamp Fields
```python
# Before
@db.model
class User:
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

# After
@db.model
class User:
    id: str
    name: str
    # created_at and updated_at managed by DataFlow
```

##### Issue 3: Missing 'id' in CreateNode
```python
# Before
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
})

# After
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",  # Add required id
    "name": "Alice"
})
```

##### Issue 4: Wrong UpdateNode Structure
```python
# Before
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "Alice Updated"
})

# After
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

#### Step 4: Enable Strict Mode
```python
# After fixing all warnings
db = DataFlow("postgresql://...", strict_mode=True)
```

---

## Troubleshooting

### Issue 1: Too Many Validation Errors

**Problem**: Strict mode reports too many errors in existing codebase.

**Solution**: Use gradual migration approach:
```python
# Use warn mode first
db = DataFlow("postgresql://...", validation_mode="warn")

# Fix issues incrementally

# Enable strict mode when ready
db = DataFlow("postgresql://...", strict_mode=True)
```

### Issue 2: Need to Disable Validation for Specific Models

**Problem**: Some legacy models can't be updated to match strict mode requirements.

**Solution**: Use per-model validation control:
```python
@db.model
class LegacyModel:
    user_id: str  # Non-standard primary key

    __dataflow__ = {
        'skip_validation': True  # Disable validation
    }
```

### Issue 3: Validation Slowing Down Development

**Problem**: Validation errors interrupt rapid prototyping.

**Solution**: Temporarily disable strict mode:
```python
# Prototyping
db = DataFlow("postgresql://...", validation_mode="off")

# Before committing
db = DataFlow("postgresql://...", strict_mode=True)
```

### Issue 4: False Positive Validation Errors

**Problem**: Validation reports errors for valid configurations.

**Solution**: Please report the issue with:
1. Error code (STRICT_XXX_XXX)
2. Model/workflow definition
3. Expected behavior
4. Actual error message

Create an issue at: https://github.com/kailash-ai/kailash-dataflow/issues

---

## Best Practices

### 1. Always Use Strict Mode in Development
```python
# ✅ GOOD: Catch errors early
db = DataFlow("postgresql://...", strict_mode=True)
```

### 2. Use Warn Mode in Production
```python
# ✅ GOOD: Log issues without breaking production
db = DataFlow("postgresql://...", validation_mode="warn")
```

### 3. Fix Warnings Immediately
```python
# ⚠️ Don't ignore warnings - they indicate potential issues
# Fix them before they become production bugs
```

### 4. Test with Strict Mode Enabled
```python
# ✅ GOOD: Test suite with strict mode
import pytest

@pytest.fixture
def strict_db():
    return DataFlow("sqlite:///:memory:", strict_mode=True)

def test_user_creation(strict_db):
    # Strict mode ensures valid configuration
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",
        "name": "Alice"
    })
    # Test passes only if configuration is valid
```

### 5. Document Validation Exceptions
```python
# ✅ GOOD: Document why validation is disabled
@db.model
class LegacyModel:
    user_id: str

    __dataflow__ = {
        'skip_validation': True  # Legacy model from v1.0, migrating in Q2 2025
    }
```

---

## Summary

- **Strict Mode** catches configuration errors at definition time
- **Three validation layers**: Model, Parameter, Connection
- **Opt-in design**: Backward compatible, only validates when enabled
- **Rich error messages**: Detailed feedback with solutions
- **Gradual migration**: Use warn mode → fix issues → enable strict mode

### Recommended Configuration

**Development**:
```python
db = DataFlow("postgresql://...", strict_mode=True)
```

**Production**:
```python
db = DataFlow("postgresql://...", validation_mode="warn")
```

---

## Additional Resources

- **Architecture Decision Record**: See `docs/architecture/ADR-003-strict-mode-validation.md`
- **API Reference**: See `src/dataflow/validation/` module documentation
- **Test Examples**: See `tests/unit/test_*_validation.py` and `tests/integration/test_*_validation_integration.py`

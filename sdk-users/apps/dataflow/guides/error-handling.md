# DataFlow Error Handling Guide

## Overview

DataFlow includes **ErrorEnhancer**, a catalog-based error enhancement system that transforms standard Python exceptions into rich, actionable error messages. When an error occurs, ErrorEnhancer automatically provides:

- **Error codes** (DF-101 to DF-910) for quick identification
- **Contextual information** about what went wrong
- **Multiple possible causes** to help diagnose the issue
- **Actionable solutions** with code examples
- **Documentation links** for detailed explanations

This system covers 60+ common error patterns across 8 categories, providing sub-1ms performance through pattern caching.

---

## Understanding Enhanced Errors

### Error Structure

When an error occurs, DataFlow displays a structured message:

```
❌ DataFlow Error [DF-101]
Missing Required Parameter: 'data' in node 'user_create'

📍 Context:
  node_id: user_create
  node_type: UserCreateNode
  parameter: data

🔍 Possible Causes:
  1. Connection not established from previous node
  2. Parameter name mismatch in connection (using wrong name)
  3. Empty input passed to workflow

💡 Solutions:
  1. Add connection to provide parameter
     workflow.add_connection(
         "source_node", "output_field",
         "user_create", "data"
     )

📚 Documentation:
  https://docs.kailash.ai/dataflow/errors/df-101
```

### Error Components

1. **Error Code (DF-XXX)**: Unique identifier for the error type
2. **Message**: Concise description of what went wrong
3. **Context**: Relevant information (node ID, parameter name, etc.)
4. **Possible Causes**: List of reasons why this error might occur
5. **Solutions**: Step-by-step fixes with code examples
6. **Documentation Link**: Deep link to detailed error documentation

---

## Error Categories

### Parameter Errors (DF-101 to DF-110)

Issues with node parameters, missing values, type mismatches, and validation failures.

#### DF-101: Missing Required Parameter

**What it means**: A required parameter was not provided to a node.

**Common scenario**:
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow(":memory:")

@db.model
class User:
    id: str
    name: str
    email: str

# ❌ ERROR: Missing 'data' parameter
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {})  # No data provided

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

**Error message**:
```
❌ DataFlow Error [DF-101]
Missing Required Parameter: 'data' in node 'create'

📍 Context:
  node_id: create
  node_type: UserCreateNode
  parameter: data

🔍 Possible Causes:
  1. Connection not established from previous node
  2. Parameter name mismatch in connection
  3. Empty input passed to workflow

💡 Solutions:
  1. Add connection to provide parameter
     workflow.add_connection(
         "source_node", "output_field",
         "create", "data"
     )

  2. Provide parameter directly
     workflow.add_node("UserCreateNode", "create", {
         "id": "user-123",
         "name": "Alice",
         "email": "alice@example.com"
     })
```

**How to fix**:
```python
# ✅ CORRECT: Provide data parameter
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

---

#### DF-102: Parameter Type Mismatch

**What it means**: The parameter type doesn't match what the node expects.

**Common scenario**:
```python
# ❌ ERROR: Passing string instead of dict
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "data": "Alice"  # String, not dict!
})
```

**Error message**:
```
❌ DataFlow Error [DF-102]
Parameter Type Mismatch: 'data' in node 'create'

📍 Context:
  node_id: create
  node_type: UserCreateNode
  parameter: data
  expected_type: dict
  received_type: str

🔍 Possible Causes:
  1. Passing primitive value (str/int) instead of dict
  2. Passing list instead of dict for single create
  3. Previous node returned unexpected type

💡 Solutions:
  1. Wrap single value in dictionary
     workflow.add_node("UserCreateNode", "create", {
         "id": "user-123",
         "name": "Alice",
         "email": "alice@example.com"
     })
```

**How to fix**:
```python
# ✅ CORRECT: Pass dictionary
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

---

#### DF-104: Auto-Managed Field Conflict

**What it means**: You're trying to manually set fields that DataFlow manages automatically.

**Common scenario**:
```python
from datetime import datetime

# ❌ ERROR: Including created_at (auto-managed)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "created_at": datetime.now()  # ❌ Remove this!
})
```

**Error message**:
```
❌ DataFlow Error [DF-104]
Auto-Managed Field Conflict: 'created_at' in node 'create'

📍 Context:
  node_id: create
  node_type: UserCreateNode
  field: created_at

🔍 Possible Causes:
  1. Including 'created_at' in data dictionary
  2. Including 'updated_at' in data dictionary
  3. Not aware these fields are auto-managed by DataFlow

💡 Solutions:
  1. Remove auto-managed fields from data
     workflow.add_node("UserCreateNode", "create", {
         "id": "user-123",
         "name": "Alice",
         "email": "alice@example.com"
         # created_at/updated_at added automatically
     })
```

**How to fix**:
```python
# ✅ CORRECT: Omit created_at and updated_at
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
    # created_at/updated_at handled by DataFlow
})
```

**Auto-managed fields**:
- `created_at`: Automatically set on record creation
- `updated_at`: Automatically updated on record modification

---

#### DF-106: Wrong Primary Key Name

**What it means**: DataFlow requires the primary key field to be named `id`.

**Common scenario**:
```python
# ❌ ERROR: Using user_id instead of id
@db.model
class User:
    user_id: str  # ❌ Wrong! Must be 'id'
    name: str
    email: str
```

**Error message**:
```
❌ DataFlow Error [DF-106]
Wrong Primary Key Name: expected 'id', found 'user_id'

📍 Context:
  model_name: User
  field: user_id

🔍 Possible Causes:
  1. Using 'user_id' instead of 'id'
  2. Using 'model_id' instead of 'id'
  3. DataFlow requires exact field name 'id'

💡 Solutions:
  1. Use 'id' as primary key name
     @db.model
     class User:
         id: str  # ✅ Correct!
         name: str
```

**How to fix**:
```python
# ✅ CORRECT: Use 'id' as primary key
@db.model
class User:
    id: str  # Must be named 'id'
    name: str
    email: str
```

---

#### DF-107: UpdateNode Pattern Mismatch

**What it means**: UpdateNode requires a specific parameter structure (`filter` + `fields`), not flat fields.

**Common scenario**:
```python
# ❌ ERROR: Using flat pattern (CreateNode style) for UpdateNode
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "name": "Alice Updated"  # ❌ Wrong pattern!
})
```

**Error message**:
```
❌ DataFlow Error [DF-107]
UpdateNode Pattern Mismatch in node 'update'

📍 Context:
  node_id: update
  node_type: UserUpdateNode

🔍 Possible Causes:
  1. Using CreateNode flat pattern for UpdateNode
  2. Missing 'filter' and 'fields' structure

💡 Solutions:
  1. Use correct UpdateNode pattern
     workflow.add_node("UserUpdateNode", "update", {
         "filter": {"id": "user-123"},
         "fields": {"name": "Alice Updated"}
     })
```

**How to fix**:
```python
# ✅ CORRECT: UpdateNode requires filter + fields
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

**Pattern comparison**:

| Node Type | Pattern | Example |
|-----------|---------|---------|
| **CreateNode** | Flat fields | `{"id": "123", "name": "Alice"}` |
| **UpdateNode** | filter + fields | `{"filter": {"id": "123"}, "fields": {"name": "Alice"}}` |
| **ReadNode** | ID only | `{"id": "123"}` |
| **DeleteNode** | ID only | `{"id": "123"}` |

---

### Connection Errors (DF-201 to DF-210)

Issues with workflow connections between nodes.

#### DF-201: Invalid Connection

**What it means**: A connection references nodes or parameters that don't exist.

**Common scenario**:
```python
# ❌ ERROR: Connecting to non-existent node
workflow = WorkflowBuilder()
workflow.add_node("InputNode", "input", {})
workflow.add_connection("input", "data", "create", "data")  # 'create' doesn't exist!

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

**Error message**:
```
❌ DataFlow Error [DF-201]
Invalid Connection from 'input' to 'create'

📍 Context:
  source_node: input
  target_node: create
  source_param: data
  target_param: data

🔍 Possible Causes:
  1. Target node 'create' doesn't exist
  2. Typo in node ID
  3. Node added after connection

💡 Solutions:
  1. Add nodes before connections
     workflow.add_node("InputNode", "input", {})
     workflow.add_node("UserCreateNode", "create", {})
     workflow.add_connection("input", "data", "create", "data")
```

**How to fix**:
```python
# ✅ CORRECT: Add nodes before connections
workflow = WorkflowBuilder()
workflow.add_node("InputNode", "input", {})
workflow.add_node("UserCreateNode", "create", {})  # Add node first
workflow.add_connection("input", "data", "create", "data")
```

---

#### DF-205: Dot Notation Invalid

**What it means**: Using dot notation to access nested fields that don't exist or are null.

**Common scenario**:
```python
# ❌ ERROR: Accessing non-existent nested field
workflow = WorkflowBuilder()
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_node("InputNode", "input", {})
workflow.add_connection("read", "result.profile.avatar", "input", "image")
# Error if profile is None or doesn't have avatar field
```

**Error message**:
```
❌ DataFlow Error [DF-205]
Dot Notation Invalid: field 'profile.avatar' not found

📍 Context:
  source_node: read
  source_param: result.profile.avatar
  target_node: input

🔍 Possible Causes:
  1. Field doesn't exist in nested structure
  2. Null value in dot notation path
  3. Typo in field name

💡 Solutions:
  1. Verify nested structure exists
     workflow.add_connection("read", "result", "input", "user")
     # Handle null checks in code
```

**How to fix**:
```python
# ✅ CORRECT: Connect full result and handle nested access in code
workflow = WorkflowBuilder()
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_node("PythonCodeNode", "extract", {
    "code": """
# Safely access nested field
user = input_user
avatar = user.get('profile', {}).get('avatar') if user else None
return {'avatar': avatar}
"""
})
workflow.add_connection("read", "result", "extract", "input_user")
```

---

### Migration Errors (DF-301 to DF-308)

Issues with database schema migrations and table creation.

#### DF-301: Migration Failure

**What it means**: Database table creation or schema update failed.

**Common scenario**:
```python
# ❌ ERROR: Insufficient database permissions
db = DataFlow("postgresql://readonly_user:pass@localhost/mydb")

@db.model
class User:
    id: str
    name: str

# Error: User doesn't have CREATE TABLE permission
```

**Error message**:
```
❌ DataFlow Error [DF-301]
Migration Failure for model 'User'

📍 Context:
  model_name: User
  operation: create_table

🔍 Possible Causes:
  1. Database permissions insufficient
  2. Table already exists
  3. Invalid column type

💡 Solutions:
  1. Check database permissions
     # Ensure user has CREATE TABLE permission
     # Run: GRANT CREATE ON DATABASE mydb TO user;

  2. Enable auto_migrate
     db = DataFlow(url, auto_migrate=True)
```

**How to fix**:
```python
# ✅ CORRECT: Enable auto_migrate
db = DataFlow("postgresql://user:pass@localhost/mydb", auto_migrate=True)

@db.model
class User:
    id: str
    name: str
```

---

#### DF-302: Schema Mismatch

**What it means**: The model definition changed but database schema wasn't updated.

**Common scenario**:
```python
# Model definition changed (added email field)
@db.model
class User:
    id: str
    name: str
    email: str  # ← New field added

# ❌ ERROR: Database still has old schema without email column
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

**Error message**:
```
❌ DataFlow Error [DF-302]
Schema Mismatch for model 'User'

📍 Context:
  model_name: User
  operation: sync_schema

🔍 Possible Causes:
  1. Model definition changed
  2. Database schema out of sync

💡 Solutions:
  1. Enable auto_migrate to sync schema
     db = DataFlow(url, auto_migrate=True)
```

**How to fix**:
```python
# ✅ CORRECT: Enable auto_migrate for automatic schema updates
db = DataFlow("postgresql://user:pass@localhost/mydb", auto_migrate=True)

@db.model
class User:
    id: str
    name: str
    email: str  # New field automatically added to database
```

---

### Runtime Errors (DF-501 to DF-508)

Issues during workflow execution.

#### DF-501: Runtime Execution Error

**What it means**: A node failed during workflow execution.

**Common scenario**:
```python
# ❌ ERROR: Database connection lost during execution
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
# Database connection lost here
results, _ = runtime.execute(workflow.build())
```

**Error message**:
```
❌ DataFlow Error [DF-501]
Runtime Execution Error in node 'create'

📍 Context:
  node_id: create
  node_type: UserCreateNode
  operation: execute

🔍 Possible Causes:
  1. Node execution failed
  2. Database operation failed
  3. Connection lost during execution

💡 Solutions:
  1. Enable debug mode to see details
     runtime = LocalRuntime(debug=True)
     results, run_id = runtime.execute(workflow.build())
```

**How to fix**:
```python
# ✅ CORRECT: Enable debug mode and handle errors
runtime = LocalRuntime(debug=True)

try:
    results, run_id = runtime.execute(workflow.build())
except Exception as e:
    print(f"Workflow failed: {e}")
    # Handle error appropriately
```

---

### Workflow Errors (DF-801 to DF-805)

Issues with workflow structure and building.

#### DF-803: Missing Workflow Build

**What it means**: Forgot to call `.build()` before executing workflow.

**Common scenario**:
```python
# ❌ ERROR: Missing .build() call
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow)  # ❌ Missing .build()!
```

**Error message**:
```
❌ DataFlow Error [DF-803]
Missing Workflow Build

📍 Context:
  workflow_type: WorkflowBuilder

🔍 Possible Causes:
  1. Forgot to call .build() on WorkflowBuilder
  2. Passing WorkflowBuilder directly to runtime

💡 Solutions:
  1. Always call .build() before execution
     workflow = WorkflowBuilder()
     workflow.add_node("UserCreateNode", "create", {})
     runtime.execute(workflow.build())  # ← Add .build()
```

**How to fix**:
```python
# ✅ CORRECT: Always call .build()
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # ← .build() required
```

---

### Validation Errors (DF-901 to DF-910)

Issues with parameter validation and node-specific requirements.

#### DF-901: CreateNode Requires Flat Fields

**What it means**: CreateNode expects flat fields, not nested `filter`/`fields` structure.

**Common scenario**:
```python
# ❌ ERROR: Using UpdateNode pattern for CreateNode
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "filter": {"id": "user-123"},  # ❌ Wrong pattern!
    "fields": {"name": "Alice"}
})
```

**Error message**:
```
❌ DataFlow Error [DF-901]
CreateNode Requires Flat Fields in node 'create'

📍 Context:
  node_id: create
  node_type: UserCreateNode

🔍 Possible Causes:
  1. Using nested filter/fields structure in CreateNode
  2. Applying UpdateNode pattern to CreateNode

💡 Solutions:
  1. Use flat field structure for CreateNode
     workflow.add_node("UserCreateNode", "create", {
         "id": "user-123",
         "name": "Alice",
         "email": "alice@example.com"
     })
```

**How to fix**:
```python
# ✅ CORRECT: Use flat fields for CreateNode
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

---

#### DF-902: UpdateNode Requires filter + fields

**What it means**: UpdateNode expects nested `filter` + `fields` structure, not flat fields.

**Common scenario**:
```python
# ❌ ERROR: Using CreateNode pattern for UpdateNode
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "Alice Updated"  # ❌ Wrong pattern!
})
```

**Error message**:
```
❌ DataFlow Error [DF-902]
UpdateNode Requires filter + fields in node 'update'

📍 Context:
  node_id: update
  node_type: UserUpdateNode

🔍 Possible Causes:
  1. Using flat fields in UpdateNode
  2. Missing filter or fields structure

💡 Solutions:
  1. Use nested filter + fields structure
     workflow.add_node("UserUpdateNode", "update", {
         "filter": {"id": "user-123"},
         "fields": {"name": "Alice Updated"}
     })
```

**How to fix**:
```python
# ✅ CORRECT: Use filter + fields for UpdateNode
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

---

## Performance Modes

ErrorEnhancer supports three performance modes for different environments:

### FULL Mode (Default)

**When to use**: Development, debugging, testing

**Features**:
- Complete error context
- All possible causes listed
- Multiple solutions with code examples
- Full documentation links

**Performance**: ~5ms per error

```python
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

config = ErrorEnhancerConfig(mode=PerformanceMode.FULL)
db = DataFlow(url, error_config=config)
```

---

### MINIMAL Mode

**When to use**: Production environments, high-throughput systems

**Features**:
- Essential error context only
- Top cause only
- Top solution only
- Documentation link included

**Performance**: ~1ms per error

```python
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL)
db = DataFlow(url, error_config=config)
```

---

### DISABLED Mode

**When to use**: Performance-critical paths, bulk operations

**Features**:
- Generic error wrapper only
- Minimal overhead

**Performance**: ~0.1ms per error

```python
from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

config = ErrorEnhancerConfig(mode=PerformanceMode.DISABLED)
db = DataFlow(url, error_config=config)
```

---

## Reading Error Messages

### Error Code Format

DataFlow error codes follow the pattern `DF-XYY`:
- **DF**: DataFlow prefix
- **X**: Category (1=Parameter, 2=Connection, 3=Migration, etc.)
- **YY**: Specific error within category

**Examples**:
- `DF-101`: Parameter error #1 (Missing Required Parameter)
- `DF-201`: Connection error #1 (Invalid Connection)
- `DF-301`: Migration error #1 (Migration Failure)

### Context Fields

Common context fields you'll see:

| Field | Description |
|-------|-------------|
| `node_id` | ID of the node where error occurred |
| `node_type` | Type of node (UserCreateNode, etc.) |
| `parameter` | Name of the problematic parameter |
| `expected_type` | Expected parameter type |
| `received_type` | Actual parameter type received |
| `model_name` | Name of the model involved |
| `operation` | Operation being performed |

### Interpreting Solutions

Solutions are prioritized by likelihood:
1. **Priority 1**: Most common fix
2. **Priority 2**: Alternative approach
3. **Priority 3**: Advanced/rare case

**Auto-fixable solutions** are marked and may be applied automatically in future versions.

---

## Common Error Patterns

### Pattern 1: Wrong Node Pattern

```python
# ❌ COMMON MISTAKE: Mixing CreateNode and UpdateNode patterns

# CreateNode with nested structure (WRONG)
workflow.add_node("UserCreateNode", "create", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice"}
})

# UpdateNode with flat structure (WRONG)
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "Alice"
})

# ✅ CORRECT PATTERNS:

# CreateNode: Flat fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# UpdateNode: filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

---

### Pattern 2: Auto-Managed Fields

```python
# ❌ COMMON MISTAKE: Including created_at/updated_at

from datetime import datetime

workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": datetime.now(),  # ❌ Remove this
    "updated_at": datetime.now()   # ❌ Remove this
})

# ✅ CORRECT: Omit auto-managed fields

workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
    # created_at and updated_at added automatically
})
```

---

### Pattern 3: Primary Key Naming

```python
# ❌ COMMON MISTAKE: Using user_id or model_id

@db.model
class User:
    user_id: str  # ❌ Wrong! Must be 'id'
    name: str

# ✅ CORRECT: Always use 'id'

@db.model
class User:
    id: str  # ✅ Required name
    name: str
```

---

### Pattern 4: Missing .build()

```python
# ❌ COMMON MISTAKE: Forgetting .build()

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {})
runtime.execute(workflow)  # ❌ Missing .build()

# ✅ CORRECT: Always call .build()

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {})
runtime.execute(workflow.build())  # ✅ .build() required
```

---

### Pattern 5: BulkNode vs Single Node

```python
# ❌ COMMON MISTAKE: Wrong data structure

# BulkCreateNode with single dict (WRONG)
workflow.add_node("UserBulkCreateNode", "bulk", {
    "records": {"id": "user-1", "name": "Alice"}  # ❌ Should be list
})

# CreateNode with list (WRONG)
workflow.add_node("UserCreateNode", "create", {
    "data": [{"id": "user-1", "name": "Alice"}]  # ❌ Should be dict
})

# ✅ CORRECT USAGE:

# CreateNode: Single dict
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice"
})

# BulkCreateNode: List of dicts
workflow.add_node("UserBulkCreateNode", "bulk", {
    "records": [
        {"id": "user-1", "name": "Alice"},
        {"id": "user-2", "name": "Bob"}
    ]
})
```

---

## Debugging Workflow

When encountering errors, follow this systematic approach:

### Step 1: Read the Error Code

```
❌ DataFlow Error [DF-107]
```

Error code `DF-107` = UpdateNode Pattern Mismatch (Category 1 = Parameter, Error 07)

### Step 2: Check Context

```
📍 Context:
  node_id: update
  node_type: UserUpdateNode
```

This tells you exactly which node failed (`update`) and its type (`UserUpdateNode`).

### Step 3: Review Possible Causes

```
🔍 Possible Causes:
  1. Using CreateNode flat pattern for UpdateNode
  2. Missing 'filter' and 'fields' structure
```

Identify which cause matches your situation.

### Step 4: Apply Solution

```
💡 Solutions:
  1. Use correct UpdateNode pattern
     workflow.add_node("UserUpdateNode", "update", {
         "filter": {"id": "user-123"},
         "fields": {"name": "Alice Updated"}
     })
```

Copy the solution code and adapt to your use case.

### Step 5: Consult Documentation

```
📚 Documentation:
  https://docs.kailash.ai/dataflow/errors/df-107
```

Visit the docs link for detailed explanation and advanced scenarios.

---

## Error Catalog Reference

### Complete Error Code List

| Code Range | Category | Count | Examples |
|------------|----------|-------|----------|
| **DF-101 to DF-110** | Parameter Errors | 10 | Missing parameter, type mismatch, auto-managed fields |
| **DF-201 to DF-210** | Connection Errors | 10 | Invalid connection, missing output, type incompatibility |
| **DF-301 to DF-308** | Migration Errors | 8 | Migration failure, schema mismatch, constraint violation |
| **DF-401 to DF-408** | Configuration Errors | 8 | Invalid config, database connection, SSL errors |
| **DF-501 to DF-508** | Runtime Errors | 8 | Execution failure, timeout, resource exhaustion |
| **DF-601 to DF-606** | Model Errors | 6 | Invalid model, duplicate name, unsupported field type |
| **DF-701 to DF-705** | Node Errors | 5 | Node not found, generation failed, validation error |
| **DF-801 to DF-805** | Workflow Errors | 5 | Invalid structure, missing .build(), disconnected nodes |
| **DF-901 to DF-910** | Validation Errors | 10 | CreateNode pattern, UpdateNode pattern, filter validation |

**Total**: 60+ error patterns covered

---

## Best Practices

### 1. Always Call .build()

```python
# ✅ CORRECT
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {})
runtime.execute(workflow.build())  # Always .build()
```

### 2. Use Correct Node Patterns

```python
# CreateNode: Flat fields
workflow.add_node("UserCreateNode", "create", {
    "id": "123",
    "name": "Alice"
})

# UpdateNode: filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "123"},
    "fields": {"name": "Alice"}
})
```

### 3. Primary Key Must Be 'id'

```python
# ✅ CORRECT
@db.model
class User:
    id: str  # Must be named 'id'
    name: str
```

### 4. Omit Auto-Managed Fields

```python
# ✅ CORRECT
workflow.add_node("UserCreateNode", "create", {
    "id": "123",
    "name": "Alice"
    # created_at/updated_at handled automatically
})
```

### 5. Enable Debug Mode During Development

```python
# Get detailed error messages
runtime = LocalRuntime(debug=True)
```

### 6. Enable Auto-Migration

```python
# Automatically handle schema changes
db = DataFlow(url, auto_migrate=True)
```

### 7. Match Data Structure to Node Type

```python
# CreateNode: Single dict
workflow.add_node("UserCreateNode", "create", {"id": "1", "name": "Alice"})

# BulkCreateNode: List of dicts
workflow.add_node("UserBulkCreateNode", "bulk", {
    "records": [{"id": "1", "name": "Alice"}]
})
```

---

## Next Steps

- **Error Catalog**: Review complete error definitions in `src/dataflow/core/error_catalog.yaml`
- **Troubleshooting Guide**: See `sdk-users/apps/dataflow/troubleshooting/common-issues.md`
- **Pattern Guide**: Check `sdk-users/apps/dataflow/guides/create-vs-update-nodes.md`
- **Core Concepts**: Read `sdk-users/apps/dataflow/README.md`

---

## Summary

DataFlow's ErrorEnhancer provides:
- **60+ error patterns** across 8 categories
- **Actionable solutions** with code examples
- **Performance modes** for different environments (FULL/MINIMAL/DISABLED)
- **Sub-1ms overhead** through pattern caching
- **Automatic detection** via exception matching

When errors occur:
1. Read the error code and message
2. Check the context for specifics
3. Review possible causes
4. Apply the suggested solution
5. Consult documentation for details

Enhanced errors help you fix issues faster and learn DataFlow patterns through real examples.

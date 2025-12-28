# DataFlow Top 10 Errors - Quick Fix Guide

**Keep this handy!** These 10 errors account for 90% of DataFlow debugging sessions. Average time saved per error: **30-120 minutes**.

---

## 1. DF-101: Missing Required Parameter

**Symptom**: `KeyError: 'data'` or `Missing required parameter 'data'`

**Root Cause**: Connection not established to provide parameter, or parameter name mismatch

**Quick Fix**:
```python
# ❌ Error
workflow.add_node("UserCreateNode", "create", {})  # Missing 'id' parameter

# ✅ Fix 1: Provide parameter directly
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
})

# ✅ Fix 2: Connect from previous node
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'id': 'user-123'}"})
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
workflow.add_connection("input", "id", "create", "id")
```

**Time Saved**: 10-20 minutes
**See**: `sdk-users/apps/dataflow/guides/create-vs-update.md`

---

## 2. DF-102: Type Mismatch (Expected dict, got str)

**Symptom**: `TypeError: Expected dict but received str`

**Root Cause**: Parameter passed as wrong type, often from connection with wrong output

**Quick Fix**:
```python
# ❌ Error - Passing string instead of dict
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123"  # String, but CreateNode expects dict
})

# ✅ Fix - Provide complete dict with all fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# For connections with type mismatch:
# ✅ Use PythonCodeNode to transform types
workflow.add_node("PythonCodeNode", "transform", {
    "code": "result = {'data': {'id': input_id, 'name': input_name}}"
})
```

**Time Saved**: 15-30 minutes
**Inspector Command**: `inspector.trace_parameter("create", "id")` to see parameter flow

---

## 3. DF-201: Invalid Connection - Source Output Not Found

**Symptom**: `ConnectionError: Source node 'generate' does not have output 'user_id'`

**Root Cause**: Typo in output parameter name, or node doesn't produce that output

**Quick Fix**:
```python
# ❌ Error - Wrong output name
workflow.add_connection("generate", "user_id", "create", "id")
# But 'generate' node outputs 'id', not 'user_id'

# ✅ Fix 1: Use correct output name
workflow.add_connection("generate", "id", "create", "id")

# ✅ Fix 2: Check available outputs
inspector = Inspector()
info = inspector.node_schema("generate")
print(info['outputs'])  # See what's actually available
```

**Time Saved**: 20-40 minutes
**Inspector Command**: `inspector.connections()` to see all connection issues

---

## 4. DF-103: Auto-Managed Field Conflict

**Symptom**: `ValidationError: 'created_at' is auto-managed and should not be provided`

**Root Cause**: Manually providing `created_at`, `updated_at`, `created_by`, or `updated_by` fields

**Quick Fix**:
```python
# ❌ Error - Including auto-managed fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "created_at": datetime.now(),  # ❌ Auto-managed
    "updated_at": datetime.now()   # ❌ Auto-managed
})

# ✅ Fix - Remove auto-managed fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
    # created_at/updated_at added automatically by DataFlow
})
```

**Time Saved**: 10-15 minutes
**Note**: DataFlow automatically manages these fields with proper timezone handling

---

## 5. DF-104: Wrong Node Pattern (CreateNode vs UpdateNode)

**Symptom**: `Missing required parameter 'filter'` when using UpdateNode, or flat fields don't work

**Root Cause**: Applying CreateNode pattern to UpdateNode or vice versa

**Quick Fix**:
```python
# ❌ Error - Using flat fields in UpdateNode
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",      # ❌ Wrong: This is CreateNode pattern
    "name": "Alice"
})

# ✅ Fix - Use filter + fields structure for UpdateNode
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},  # Which record
    "fields": {"name": "Alice"}     # What to change
})

# For CreateNode, use flat fields:
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",  # Flat
    "name": "Alice"    # Flat
})
```

**Time Saved**: 60-120 minutes (most time-consuming error!)
**See**: `sdk-users/apps/dataflow/guides/create-vs-update.md` - Complete guide

---

## 6. DF-301: Migration Failed - Table Already Exists

**Symptom**: `MigrationError: Table 'users' already exists with different schema`

**Root Cause**: Model schema changed but migration system detected conflict

**Quick Fix**:
```python
# ✅ Fix 1: Drop and recreate (development only)
db = DataFlow("postgresql://...", drop_existing=True)

# ✅ Fix 2: Use existing schema mode
db = DataFlow("postgresql://...", existing_schema_mode=True)

# ✅ Fix 3: Manual migration
# 1. Backup data
# 2. Drop table
# 3. Recreate with new schema
# 4. Restore data
```

**Time Saved**: 30-60 minutes
**Note**: Always backup data before migrations in production!

---

## 7. DF-401: Runtime Error - Node Execution Failed

**Symptom**: `RuntimeError: Node 'create_user' execution failed: <specific error>`

**Root Cause**: Exception during node execution (database error, validation error, etc.)

**Quick Fix**:
```python
# ✅ Use Inspector to diagnose
inspector = Inspector()
report = inspector.workflow_validation_report()
print(report['errors'])

# ✅ Enable debug mode
runtime = LocalRuntime(debug=True)
results, _ = runtime.execute(workflow.build())

# ✅ Check ErrorEnhancer output
try:
    results, _ = runtime.execute(workflow.build())
except EnhancedDataFlowError as e:
    print(e.format_enhanced(color=True))
    # Shows causes, solutions, and relevant context
```

**Time Saved**: 20-40 minutes
**Inspector Commands**:
- `inspector.execution_order()` - See execution sequence
- `inspector.node_dependencies("create_user")` - Check dependencies

---

## 8. DF-202: Broken Connection - Type Contract Violation

**Symptom**: `ConnectionError: Type mismatch - expected 'dict' but connection provides 'str'`

**Root Cause**: Source output type doesn't match target input type

**Quick Fix**:
```python
# ❌ Error - Type mismatch in connection
workflow.add_node("PythonCodeNode", "gen", {"code": "result = 'user-123'"})  # Returns str
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})
workflow.add_connection("gen", "result", "create", "id")  # Expects str for 'id', OK
workflow.add_connection("gen", "result", "create", "data")  # ❌ Expects dict, got str

# ✅ Fix - Add transformation node
workflow.add_node("PythonCodeNode", "transform", {
    "code": "result = {'id': user_id, 'name': 'Alice'}"
})
workflow.add_connection("gen", "result", "transform", "user_id")
workflow.add_connection("transform", "result", "create", "data")
```

**Time Saved**: 25-45 minutes
**Inspector Command**: `inspector.validate_connections()` - Check all connection types

---

## 9. DF-105: Primary Key 'id' Missing or Wrong Name

**Symptom**: `ValidationError: Primary key 'id' is required` or `KeyError: 'id'`

**Root Cause**: Using custom primary key name like `user_id`, `pk`, or forgetting `id` entirely

**Quick Fix**:
```python
# ❌ Error - Wrong primary key name
@db.model
class User:
    user_id: str  # ❌ Wrong: Must be 'id'
    name: str

# ✅ Fix - Always use 'id' as primary key
@db.model
class User:
    id: str  # ✅ Correct
    name: str

# When creating records:
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",  # ✅ Primary key required
    "name": "Alice"
})
```

**Time Saved**: 10-20 minutes
**Note**: DataFlow requires `id` as the primary key name - this is not configurable

---

## 10. DF-302: Schema Mismatch - Field Type Changed

**Symptom**: `MigrationError: Field 'age' changed type from 'int' to 'str'`

**Root Cause**: Model field type changed incompatibly

**Quick Fix**:
```python
# ❌ Error - Changed field type
# Before:
@db.model
class User:
    id: str
    age: int  # Was int

# After:
@db.model
class User:
    id: str
    age: str  # Now str - incompatible change!

# ✅ Fix 1: Use compatible migration
# 1. Add new field with new type
@db.model
class User:
    id: str
    age: int       # Keep old field
    age_str: str   # Add new field

# 2. Migrate data
# 3. Remove old field

# ✅ Fix 2: Drop and recreate (development only)
db = DataFlow("postgresql://...", drop_existing=True)
```

**Time Saved**: 40-90 minutes
**Note**: For production, always use multi-step migrations for type changes

---

## Quick Diagnosis Decision Tree

```
Error occurred?
│
├─ "Missing parameter" → DF-101
│   └─ Check connections and parameter names
│
├─ "Type mismatch" → DF-102 or DF-202
│   └─ Check connection types with Inspector
│
├─ "Auto-managed field" → DF-103
│   └─ Remove created_at/updated_at from parameters
│
├─ "Missing 'filter'" or "Wrong structure" → DF-104
│   └─ Review CreateNode vs UpdateNode guide
│
├─ "Primary key" error → DF-105
│   └─ Ensure model has 'id' field
│
├─ "Connection error" → DF-201 or DF-202
│   └─ Run inspector.validate_connections()
│
├─ "Migration failed" → DF-301 or DF-302
│   └─ Check schema changes
│
└─ "Node execution failed" → DF-401
    └─ Enable debug mode and check logs
```

---

## Prevention Checklist

Before running your workflow, check:

- [ ] All CreateNodes use flat fields (not nested)
- [ ] All UpdateNodes use `filter`/`fields` structure
- [ ] No `created_at`/`updated_at` in CreateNode parameters
- [ ] Primary key is named `id` (not `user_id`, `pk`, etc.)
- [ ] All connections have matching source/target parameters
- [ ] Required parameters either provided or connected
- [ ] Model schema matches existing database (if using existing DB)

**Use Inspector to validate**:
```python
inspector = Inspector()
report = inspector.workflow_validation_report()
if not report['is_valid']:
    print("Errors:", report['errors'])
    print("Warnings:", report['warnings'])
    print("Suggestions:", report['suggestions'])
```

---

## Inspector Commands for Debugging

**Connection Issues**:
```python
inspector.connections()                      # List all connections
inspector.validate_connections()             # Check all connections valid
inspector.find_broken_connections()          # Find broken connections
```

**Parameter Issues**:
```python
inspector.trace_parameter("node_id", "param")  # Trace parameter source
inspector.parameter_dependencies("node_id")    # List all dependencies
inspector.find_parameter_source("node_id", "param")  # Find origin
```

**Node Issues**:
```python
inspector.node_schema("node_id")             # Get node input/output schema
inspector.node_dependencies("node_id")       # List upstream nodes
inspector.execution_order()                  # See execution sequence
```

**Workflow Issues**:
```python
inspector.workflow_validation_report()       # Full validation report
inspector.workflow_summary()                 # High-level overview
inspector.workflow_metrics()                 # Workflow statistics
```

---

## Error Code Reference

| Code | Category | Severity | Description |
|------|----------|----------|-------------|
| DF-101 | Parameter | High | Missing required parameter |
| DF-102 | Parameter | High | Type mismatch |
| DF-103 | Parameter | Medium | Auto-managed field conflict |
| DF-104 | Parameter | High | Wrong node pattern (Create vs Update) |
| DF-105 | Parameter | High | Primary key 'id' missing/wrong |
| DF-201 | Connection | High | Invalid connection - output not found |
| DF-202 | Connection | High | Type contract violation |
| DF-301 | Migration | Critical | Migration failed - table exists |
| DF-302 | Migration | Critical | Schema mismatch - incompatible change |
| DF-401 | Runtime | Critical | Node execution failed |

---

## Getting Help

1. **Check this guide first** - Covers 90% of issues
2. **Use Inspector** - `inspector.workflow_validation_report()`
3. **Enable ErrorEnhancer** - Enhanced error messages with solutions
4. **Read full guides**:
   - `sdk-users/apps/dataflow/guides/create-vs-update.md`
   - `sdk-users/apps/dataflow/conventions/primary-keys.md`
5. **Enable debug mode**: `LocalRuntime(debug=True)`

---

## Summary Statistics

**Total errors in catalog**: 50+
**Top 10 coverage**: 90% of user issues
**Average time saved per error**: 30-120 minutes
**Most common error**: DF-104 (CreateNode vs UpdateNode confusion)
**Most time-consuming error**: DF-104 (1-2 hours without guide)
**Most critical error**: DF-301 (Migration failures in production)

**Remember**: Most DataFlow errors are preventable with proper understanding of node patterns. When in doubt, consult the guides!

---

**Last Updated**: 2025-10-29
**Version**: 1.0
**Error Codes**: DF-101 through DF-805 (50+ errors cataloged)
**Inspector Version**: 1.0 (25 methods available)

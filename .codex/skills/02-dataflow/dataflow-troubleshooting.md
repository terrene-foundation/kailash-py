# DataFlow Troubleshooting Guide

## Overview

DataFlow v0.4.7+ provides diagnostic tools to resolve issues quickly.

## Troubleshooting Flowchart

1. **Start**: Is workflow executing at all?
   - NO -> Check error message for DF-XXX code
2. **Results empty?**
   - YES -> Use Inspector to validate connections
3. **Slow performance?**
   - YES -> Use `dataflow perf` to identify bottlenecks
4. **Type errors?**
   - YES -> Use Inspector to check connection types
5. **Event loop errors?**
   - YES -> Enable test_mode with cleanup

## Issue 1: Workflow Builds But Produces No Results

**Symptoms**: `runtime.execute(workflow.build())` succeeds but results are empty or None.

**Solution**:
```python
# Step 1: Use Inspector to validate connections
inspector = Inspector(workflow)
validation = inspector.validate_connections()

if not validation["is_valid"]:
    print("Connection errors found:")
    for error in validation["errors"]:
        print(f"  - {error}")

# Step 2: Use CLI validate command
# dataflow validate my_workflow.py --strict
```

## Issue 2: Missing Parameter Error (DF-101)

**Symptoms**: Error shows "DF-101: Missing Required Parameter"

**Solution**:
```python
# ErrorEnhancer shows exactly which parameter is missing
# Follow the 3 solutions provided in error message:

# Solution 1: Add missing parameter
data = {
    "id": "user-123",  # <- ADD THIS
    "name": "Alice",
    "email": "alice@example.com"
}

# Solution 2: Check model definition
# Verify all required fields are present

# Solution 3: Use Inspector to validate
inspector = Inspector(workflow)
trace = inspector.trace_parameter("create", "id")
```

## Issue 3: Slow First Operation

**Symptoms**: First database operation takes ~1500ms, subsequent operations are fast.

**Solution**:
```python
# This is expected behavior! Schema cache causes this pattern:
# - First operation: Cache miss (~1500ms) - includes migration checks
# - Subsequent operations: Cache hit (~1ms) - 99% faster

# To verify schema cache is working:
metrics = db._schema_cache.get_metrics()
print(f"Hit rate: {metrics['hit_rate']:.2%}")  # Should be >90% after warm-up
```

## Issue 4: Event Loop Closed Errors

**Symptoms**: "Event loop is closed" or "Pool attached to different loop"

**Solution**:
```python
# Use test mode with automatic cleanup
db = DataFlow("postgresql://...", test_mode=True)

# In pytest fixture:
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()  # Clean up after each test
```

## Issue 5: Connection Type Mismatch (DF-201)

**Symptoms**: Error shows "DF-201: Connection Type Mismatch"

**Solution**:
```python
# ErrorEnhancer shows expected vs actual types
# Use Inspector to trace the issue:

inspector = Inspector(workflow)
validation = inspector.validate_connections()

for error in validation["errors"]:
    if "type mismatch" in error["reason"].lower():
        print(f"Mismatch: {error['from_node']}.{error['from_param']}")
        print(f"Expected: {error['expected_type']}")
        print(f"Got: {error['actual_type']}")
        # Fix the type in the source node
```

## Quick Diagnostic Commands

```bash
# Full workflow validation
dataflow validate my_workflow.py --strict

# Debug specific node
dataflow debug my_workflow.py --node "problematic_node"

# Analyze performance
dataflow perf my_workflow.py --profile

# Check workflow structure
dataflow analyze my_workflow.py
```

## Debugging Steps (v0.4.7+)

**Step 1: Use Inspector First**
```python
from dataflow.platform.inspector import Inspector

# ALWAYS start with Inspector
inspector = Inspector(workflow)

# Quick health check
validation = inspector.validate_connections()
if not validation["is_valid"]:
    print(f"Found {len(validation['errors'])} errors")
    for error in validation["errors"]:
        print(f"  - {error}")
```

**Step 2: Check Error Codes**
```python
# Enhanced errors show DF-XXX codes
try:
    results = runtime.execute(workflow.build())
except Exception as e:
    if "DF-" in str(e):
        error_code = str(e).split(":")[0]
        print(f"Error code: {error_code}")
        print(f"Documentation: https://docs.kailash.dev/dataflow/errors/{error_code}")
```

**Step 3: Use CLI Commands**
```bash
dataflow validate my_workflow.py --strict
dataflow debug my_workflow.py --node "problematic_node"
dataflow perf my_workflow.py --profile
```

**Step 4: Verify Node-Instance Coupling**
```python
# Check node-instance coupling (rare issue)
node = db._nodes["UserCreateNode"]()
print(f"Bound to: {node.dataflow_instance}")
print(f"Correct: {node.dataflow_instance is db}")
```

**Step 5: Verify String ID Preservation**
```python
# Verify string ID preservation (rare issue)
results = runtime.execute(workflow.build())
print(f"ID type: {type(results['create_user']['id'])}")
print(f"ID value: {results['create_user']['id']}")
```

## Common Debugging Patterns

### Pattern 1: Connection Issues
```python
# Use Inspector to trace parameter flow
inspector = Inspector(workflow)
trace = inspector.trace_parameter("target_node", "missing_param")

if trace.source is None:
    print("Parameter not connected! Add connection:")
    print(f"  workflow.add_connection(source_node, 'param', 'target_node', 'missing_param')")
```

### Pattern 2: Type Mismatches
```python
# Inspector shows type mismatches in connections
validation = inspector.validate_connections()
for error in validation["errors"]:
    if "type mismatch" in error["reason"].lower():
        print(f"Type mismatch: {error['from_node']}.{error['from_param']} -> {error['to_node']}.{error['to_param']}")
        print(f"Expected: {error['expected_type']}, Got: {error['actual_type']}")
```

### Pattern 3: Performance Issues
```bash
# Use CLI perf command to identify bottlenecks
dataflow perf my_workflow.py --profile --output report.json

# Analyze report:
# - Long-running nodes
# - Network-bound operations
# - Database query optimization opportunities
```

## Common Error Codes Reference

| Code | Issue | Solution |
|------|-------|----------|
| DF-101 | Missing Required Parameter | Add missing field to data dictionary |
| DF-201 | Connection Type Mismatch | Check parameter types in connections |
| DF-301 | Migration Failed | Review schema changes and constraints |
| DF-401 | Database URL Invalid | Verify connection string format |
| DF-501 | Sync Method in Async Context | Use `create_tables_async()` instead |
| DF-601 | Primary Key Missing | Ensure model has 'id' field |
| DF-701 | Node Not Found | Check node name spelling and case |
| DF-801 | Workflow Build Failed | Validate all connections before .build() |

## Version Requirements

- DataFlow v0.4.7+ for enhanced debugging tools

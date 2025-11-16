# Inspector Debugging Guide

Comprehensive guide to debugging DataFlow workflows using the Inspector API.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Common Debugging Scenarios](#common-debugging-scenarios)
- [Inspector API Reference](#inspector-api-reference)
- [CLI Usage](#cli-usage)
- [Best Practices](#best-practices)

## Overview

**Inspector** is DataFlow's introspection API for debugging workflow structure, analyzing connections, and diagnosing errors without reading source code.

### Key Capabilities

- **Connection Analysis**: Inspect workflow connections and parameter flow
- **Parameter Tracing**: Trace parameters back to their source nodes
- **Model Introspection**: Examine model schemas, fields, and validation rules
- **Workflow Validation**: Detect broken connections and circular dependencies
- **Error Diagnosis**: Get actionable suggestions for DataFlow errors

### When to Use Inspector

✅ **Use Inspector when**:
- Debugging parameter flow issues ("where does this data come from?")
- Analyzing complex workflow structures
- Finding broken connections before runtime execution
- Understanding model schemas and relationships
- Diagnosing DataFlow errors with specific recommendations

❌ **Don't use Inspector for**:
- Workflow execution (use `LocalRuntime` or `AsyncLocalRuntime`)
- Data transformations (use `PythonCode` nodes)
- Production monitoring (use health checks and metrics)

---

## Quick Start

### Basic Usage

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder

# Initialize DataFlow
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str

# Create Inspector instance
inspector = Inspector(db)

# Inspect model
model_info = inspector.model("User")
print(model_info.show())

# Inspect workflow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user_123", "name": "Alice"})
workflow.add_node("UserReadNode", "read", {"id": "user_123"})
workflow.add_connection("create", "id", "read", "id")

workflow_inspector = Inspector(workflow)
connections = workflow_inspector.connections()
print(f"Found {len(connections)} connections")
```

### Output

```
Model: User
-----------
Fields:
  - id: str
  - name: str
  - email: str

Generated Nodes: 11
  - UserCreateNode
  - UserReadNode
  - UserUpdateNode
  - UserDeleteNode
  - UserListNode
  - UserUpsertNode
  - UserCountNode
  - UserBulkCreateNode
  - UserBulkUpdateNode
  - UserBulkDeleteNode
  - UserBulkUpsertNode

Found 1 connections
```

---

## Common Debugging Scenarios

### Scenario 1: Missing Data Parameter

**Problem**: Node receives `None` for a parameter that should have data.

**Solution**: Use `trace_parameter()` to find the source.

```python
from dataflow.platform.inspector import Inspector

# Create workflow with parameter flow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user_123", "name": "Alice", "email": "alice@example.com"})
workflow.add_node("UserReadNode", "read", {"id": "$param:user_id"})  # Where does user_id come from?
workflow.add_connection("create", "id", "read", "id")

# Inspect parameter flow
inspector = Inspector(workflow)
trace = inspector.trace_parameter("read", "id")

# Display trace
print(trace.show())
```

**Output**:

```
Parameter Trace: read.id
=======================
Source: create.id
Path: create.id → read.id (1 hop)

Transformation:
  - No transformation (direct connection)

Value Type: str
Expected Type: str
✓ Type match
```

**Diagnosis**: Parameter is correctly connected. Issue might be runtime data, not structure.

---

### Scenario 2: Broken Connection

**Problem**: Workflow fails with "parameter not found" error.

**Solution**: Use `find_broken_connections()` to detect structural issues.

```python
from dataflow.platform.inspector import Inspector

# Create workflow with broken connection
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user_123", "name": "Alice"})
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "$param:user_id"},  # Incorrect: user_id not defined
    "fields": {"name": "Alice Updated"}
})
workflow.add_connection("create", "id", "update", "user_id")  # Broken: update expects "filter.id"

# Find broken connections
inspector = Inspector(workflow)
broken = inspector.find_broken_connections()

for issue in broken:
    print(issue.show())
```

**Output**:

```
Broken Connection Detected
==========================
Source: create.id
Target: update.user_id

Issue: Target parameter 'user_id' not found in node definition
Expected: update.filter.id (nested parameter)

Suggestion:
  - Use dot notation for nested parameters:
    workflow.add_connection("create", "id", "update", "filter.id")
```

**Fix**:

```python
# Correct connection
workflow.add_connection("create", "id", "update", "filter.id")
```

---

### Scenario 3: Type Mismatch in Connection

**Problem**: Node expects integer but receives string.

**Solution**: Use `connections()` to verify type compatibility.

```python
from dataflow.platform.inspector import Inspector

# Create workflow with type mismatch
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user_123", "age": 30})
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = input_data * 2",  # Expects integer
    "input_data": "$param:age"
})
workflow.add_connection("create", "id", "process", "input_data")  # Type mismatch: str → int

# Inspect connections
inspector = Inspector(workflow)
connections = inspector.connections()

for conn in connections:
    print(conn.show())
```

**Output**:

```
Connection: create.id → process.input_data
==========================================
Source Type: str
Target Type: int

⚠ Type Mismatch Detected
Expected: int
Received: str

Suggestions:
  1. Add type conversion node:
     PythonCodeNode: user_id_int = int(user_id_str)

  2. Use correct source parameter:
     workflow.add_connection("create", "age", "process", "input_data")
```

**Fix**:

```python
# Correct connection using age (int) instead of id (str)
workflow.add_connection("create", "age", "process", "input_data")
```

---

### Scenario 4: Circular Dependency Detection

**Problem**: Workflow has circular dependency that causes infinite loops.

**Solution**: Use `validate_connections()` to detect cycles.

```python
from dataflow.platform.inspector import Inspector

# Create workflow with circular dependency
workflow = WorkflowBuilder()
workflow.add_node("NodeA", "a", {"data": "$param:b_output"})
workflow.add_node("NodeB", "b", {"data": "$param:a_output"})
workflow.add_connection("a", "output", "b", "b_output")
workflow.add_connection("b", "output", "a", "a_output")  # Circular!

# Validate connections
inspector = Inspector(workflow)
validation = inspector.validate_connections()

if not validation["is_valid"]:
    print(f"⚠ {len(validation['errors'])} validation errors found")
    for error in validation["errors"]:
        print(f"  - {error}")
```

**Output**:

```
⚠ 1 validation errors found
  - Circular dependency detected: a → b → a
```

**Fix**:

```python
# Remove circular connection
workflow = WorkflowBuilder()
workflow.add_node("NodeA", "a", {"data": "initial_value"})
workflow.add_node("NodeB", "b", {"data": "$param:a_output"})
workflow.add_connection("a", "output", "b", "data")  # One-way connection
```

---

### Scenario 5: Model Schema Comparison

**Problem**: Need to understand differences between two model versions.

**Solution**: Use `model_schema_diff()` to compare schemas.

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector

db = DataFlow(":memory:")

@db.model
class UserV1:
    id: str
    name: str

@db.model
class UserV2:
    id: str
    name: str
    email: str  # New field

# Compare schemas
inspector = Inspector(db)
diff = inspector.model_schema_diff("UserV1", "UserV2")

print(diff.show())
```

**Output**:

```
Schema Diff: UserV1 vs UserV2
==============================
Added Fields:
  - email: str

Removed Fields:
  (none)

Modified Fields:
  (none)

Migration Required: Yes
Suggested Migration:
  ALTER TABLE users_v1 ADD COLUMN email TEXT;
```

---

### Scenario 6: Understanding Model Validation Rules

**Problem**: Need to know which fields are required vs optional.

**Solution**: Use `model_validation_rules()` to extract validation metadata.

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector
from typing import Optional

db = DataFlow(":memory:")

@db.model
class Order:
    id: str
    customer_id: str  # Foreign key (detected by _id suffix)
    total: float
    notes: Optional[str] = None  # Nullable field

# Get validation rules
inspector = Inspector(db)
rules = inspector.model_validation_rules("Order")

print(rules.show())
```

**Output**:

```
Validation Rules: Order
=======================
Required Fields: 3
  - id (str)
  - customer_id (str)
  - total (float)

Nullable Fields: 1
  - notes (Optional[str])

Constraints:
  - Primary Key: id

Foreign Keys Detected: 1
  - customer_id → Customer model (inferred)

Validation Notes:
  - Foreign keys detected by _id suffix pattern
  - Add explicit foreign key constraints if needed
```

---

### Scenario 7: Migration Status Check

**Problem**: Need to verify if model schema matches database table.

**Solution**: Use `model_migration_status()` to check sync status.

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector

db = DataFlow("postgresql://localhost/mydb")

@db.model
class Product:
    id: str
    name: str
    price: float

# Check migration status
inspector = Inspector(db)
status = inspector.model_migration_status("Product")

print(status.show())
```

**Output**:

```
Migration Status: Product
=========================
Table Exists: Yes
Schema Match: No

Differences Detected:
  - Missing column: price (float)
  - Extra column: old_price (float) [in database, not in model]

Migration Required: Yes
Action: Run db.auto_migrate() or manually add 'price' column

Suggested Migration:
  ALTER TABLE products ADD COLUMN price REAL;
  ALTER TABLE products DROP COLUMN old_price;
```

---

### Scenario 8: Counting Model Instances

**Problem**: Need to verify how many records exist for a model.

**Solution**: Use `model_instances_count()`.

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

# Count instances (requires database query)
inspector = Inspector(db)
count = inspector.model_instances_count("User")

print(f"User instances: {count}")
```

**Output**:

```
User instances: 1247
```

**Note**: This performs an actual database query (`SELECT COUNT(*) FROM users`).

---

### Scenario 9: Error Diagnosis with Inspector Commands

**Problem**: DataFlow error occurs, need suggestions on how to debug.

**Solution**: Use `diagnose_error()` to get Inspector command suggestions.

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector
from dataflow.exceptions import EnhancedDataFlowError

db = DataFlow(":memory:")

@db.model
class User:
    id: str
    name: str

# Simulate error
error = EnhancedDataFlowError(
    error_code="DF-PARAM-001",
    message="Missing required parameter 'data'",
    context={"node_id": "user_create", "parameter_name": "data"}
)

# Diagnose error
inspector = Inspector(db)
diagnosis = inspector.diagnose_error(error)

print(diagnosis.show())
```

**Output**:

```
Error Diagnosis: DF-PARAM-001
==============================
Error Type: ParameterError
Affected Component: user_create

Inspector Commands to Run:
  $ inspector.node('user_create')
  $ inspector.trace_parameter('user_create', 'data')
  $ inspector.validate_connections()

Context Hints:
  - node_id: user_create
  - parameter_name: data

Recommended Actions:
  1. Verify 'data' parameter is defined in node
  2. Check if parameter is provided via connection
  3. Validate parameter is not None at runtime
  4. Review node signature for required parameters
```

---

### Scenario 10: Connection Chain Analysis

**Problem**: Complex workflow with multiple hops, need to see full data flow.

**Solution**: Use `trace_parameter()` for multi-hop analysis.

```python
from dataflow.platform.inspector import Inspector

# Create workflow with multi-hop parameter flow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user_123", "name": "Alice"})
workflow.add_node("PythonCodeNode", "transform", {
    "code": "result = {'transformed_id': input_id.upper()}",
    "input_id": "$param:user_id"
})
workflow.add_node("UserReadNode", "read", {"id": "$param:final_id"})

workflow.add_connection("create", "id", "transform", "user_id")
workflow.add_connection("transform", "result.transformed_id", "read", "final_id")

# Trace parameter through chain
inspector = Inspector(workflow)
trace = inspector.trace_parameter("read", "final_id")

print(trace.show())
```

**Output**:

```
Parameter Trace: read.final_id
===============================
Source: create.id
Path: create.id → transform.user_id → transform.result.transformed_id → read.final_id (3 hops)

Transformations:
  1. create.id → transform.user_id
     - Type: Direct connection
     - No transformation

  2. transform.user_id → transform.result.transformed_id
     - Type: PythonCode transformation
     - Code: result = {'transformed_id': input_id.upper()}
     - Output: Dict with 'transformed_id' key

  3. transform.result.transformed_id → read.final_id
     - Type: Dot notation extraction
     - Extracts 'transformed_id' from Dict

Value Type Chain:
  str → str → Dict → str

✓ All type transitions valid
```

---

### Scenario 11: Workflow Statistics Summary

**Problem**: Need overview of workflow complexity.

**Solution**: Use `workflow_summary()` for statistics.

```python
from dataflow.platform.inspector import Inspector

# Create complex workflow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_1", {"id": "user_1", "name": "Alice"})
workflow.add_node("UserCreateNode", "create_2", {"id": "user_2", "name": "Bob"})
workflow.add_node("UserListNode", "list", {"limit": 10})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(users)", "users": "$param:user_list"})
workflow.add_connection("list", "results", "process", "user_list")

# Get workflow summary
inspector = Inspector(workflow)
summary = inspector.workflow_summary()

print(summary.show())
```

**Output**:

```
Workflow Summary
================
Total Nodes: 4
Total Connections: 1

Node Types:
  - UserCreateNode: 2
  - UserListNode: 1
  - PythonCodeNode: 1

Connection Density: 0.25 (1 connection / 4 nodes)
Workflow Complexity: Low

Potential Issues:
  - create_1 and create_2 are isolated (no outgoing connections)
  - Consider connecting create nodes to downstream processing

Optimization Suggestions:
  - Isolated nodes may not contribute to workflow output
  - Review node dependency chain
```

---

### Scenario 12: CLI Quick Inspection

**Problem**: Need to quickly inspect workflow from command line.

**Solution**: Use Inspector CLI commands.

```bash
# Inspect model
python -m dataflow.cli.inspector_cli model User

# Inspect workflow from Python file
python -m dataflow.cli.inspector_cli workflow my_workflow.py

# List all connections
python -m dataflow.cli.inspector_cli connections my_workflow.py

# Trace specific parameter
python -m dataflow.cli.inspector_cli trace-parameter my_workflow.py read id

# Interactive debugging mode
python -m dataflow.cli.inspector_cli interactive my_workflow.py
```

**Interactive Mode Example**:

```
DataFlow Inspector (Interactive Mode)
======================================
Workflow: my_workflow.py
Nodes: 5
Connections: 4

Commands:
  nodes          - List all nodes
  connections    - List all connections
  trace <node> <param>  - Trace parameter
  validate       - Validate connections
  help           - Show help
  quit           - Exit

> nodes
1. UserCreateNode (id: create)
2. UserReadNode (id: read)
3. UserUpdateNode (id: update)
4. UserDeleteNode (id: delete)
5. PythonCodeNode (id: process)

> trace read id
Parameter Trace: read.id
Source: create.id
Path: create.id → read.id (1 hop)
✓ Valid connection

> quit
```

---

## Inspector API Reference

### Model Introspection

#### `model(model_name: str) -> ModelInfo`

Get comprehensive model information.

```python
model_info = inspector.model("User")
print(model_info.show())
```

**Returns**:
- Model name
- Fields with types
- Generated nodes (11 per model)

---

#### `model_schema_diff(model_name1: str, model_name2: str) -> ModelSchemaDiff`

Compare two model schemas.

```python
diff = inspector.model_schema_diff("UserV1", "UserV2")
print(diff.show())
```

**Returns**:
- Added fields
- Removed fields
- Modified fields
- Migration suggestions

---

#### `model_migration_status(model_name: str) -> ModelMigrationStatus`

Check if model schema matches database table.

```python
status = inspector.model_migration_status("User")
print(status.show())
```

**Returns**:
- Table exists
- Schema match status
- Detected differences
- Migration actions required

---

#### `model_validation_rules(model_name: str) -> ModelValidationRules`

Extract validation rules from model.

```python
rules = inspector.model_validation_rules("User")
print(rules.show())
```

**Returns**:
- Required fields
- Nullable fields
- Constraints
- Foreign key detection (by _id suffix)

---

#### `model_instances_count(model_name: str) -> int`

Count records in database table.

```python
count = inspector.model_instances_count("User")
print(f"Total users: {count}")
```

**Returns**: Integer count

**Note**: Performs database query.

---

### Workflow Analysis

#### `connections() -> List[ConnectionInfo]`

List all workflow connections.

```python
connections = inspector.connections()
for conn in connections:
    print(conn.show())
```

**Returns**: List of `ConnectionInfo` objects with:
- Source node and parameter
- Target node and parameter
- Type information
- Validation status

---

#### `trace_parameter(node_id: str, parameter_name: str) -> ParameterTrace`

Trace parameter back to source.

```python
trace = inspector.trace_parameter("read", "id")
print(trace.show())
```

**Returns**: `ParameterTrace` with:
- Source node
- Full path (all hops)
- Transformations
- Type transitions

---

#### `find_broken_connections() -> List[ConnectionIssue]`

Detect broken connections.

```python
broken = inspector.find_broken_connections()
for issue in broken:
    print(issue.show())
```

**Returns**: List of `ConnectionIssue` objects with:
- Connection details
- Issue description
- Suggestions for fixing

---

#### `validate_connections() -> Dict`

Validate all workflow connections.

```python
validation = inspector.validate_connections()
if not validation["is_valid"]:
    for error in validation["errors"]:
        print(error)
```

**Returns**: Dict with:
- `is_valid` (bool)
- `errors` (list of error messages)
- `warnings` (list of warnings)

---

#### `workflow_summary() -> WorkflowSummary`

Get workflow statistics.

```python
summary = inspector.workflow_summary()
print(summary.show())
```

**Returns**: `WorkflowSummary` with:
- Total nodes and connections
- Node type distribution
- Complexity metrics
- Optimization suggestions

---

### Error Diagnosis

#### `diagnose_error(error: Exception) -> ErrorDiagnosis`

Diagnose DataFlow error and suggest Inspector commands.

```python
from dataflow.exceptions import EnhancedDataFlowError

error = EnhancedDataFlowError(
    error_code="DF-101",
    message="Missing parameter",
    context={"node_id": "user_create"}
)

diagnosis = inspector.diagnose_error(error)
print(diagnosis.show())
```

**Returns**: `ErrorDiagnosis` with:
- Error code and type
- Affected component
- Suggested Inspector commands
- Context hints
- Recommended actions

---

## CLI Usage

### Installation

Inspector CLI is included with DataFlow. No additional installation required.

### Commands

#### Inspect Model

```bash
python -m dataflow.cli.inspector_cli model <model_name>
```

**Example**:
```bash
$ python -m dataflow.cli.inspector_cli model User

Model: User
-----------
Fields: id (str), name (str), email (str)
Generated Nodes: 11
```

---

#### Inspect Workflow

```bash
python -m dataflow.cli.inspector_cli workflow <workflow_file.py>
```

**Example**:
```bash
$ python -m dataflow.cli.inspector_cli workflow my_workflow.py

Workflow Summary
================
Total Nodes: 5
Total Connections: 4
Complexity: Medium
```

---

#### List Connections

```bash
python -m dataflow.cli.inspector_cli connections <workflow_file.py>
```

**Example**:
```bash
$ python -m dataflow.cli.inspector_cli connections my_workflow.py

Connections (4):
  1. create.id → read.id
  2. read.result → update.filter.id
  3. update.result → delete.id
  4. create.name → process.user_name
```

---

#### Trace Parameter

```bash
python -m dataflow.cli.inspector_cli trace-parameter <workflow_file.py> <node_id> <parameter_name>
```

**Example**:
```bash
$ python -m dataflow.cli.inspector_cli trace-parameter my_workflow.py read id

Parameter Trace: read.id
========================
Source: create.id
Path: create.id → read.id (1 hop)
✓ Valid connection
```

---

#### Interactive Mode

```bash
python -m dataflow.cli.inspector_cli interactive <workflow_file.py>
```

**Example**:
```bash
$ python -m dataflow.cli.inspector_cli interactive my_workflow.py

DataFlow Inspector (Interactive Mode)
======================================
Workflow: my_workflow.py
Nodes: 5

> help
Commands:
  nodes          - List all nodes
  connections    - List all connections
  trace <node> <param>  - Trace parameter
  validate       - Validate connections
  help           - Show help
  quit           - Exit

> nodes
1. UserCreateNode (id: create)
2. UserReadNode (id: read)
...

> quit
```

---

## Best Practices

### 1. Inspect Before Execution

Always validate workflow structure before runtime execution:

```python
# ✅ GOOD - Inspect first
inspector = Inspector(workflow)
validation = inspector.validate_connections()

if validation["is_valid"]:
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
else:
    print("Fix errors before execution:")
    for error in validation["errors"]:
        print(f"  - {error}")
```

---

### 2. Use Trace for Complex Workflows

For workflows with 3+ hops, always trace parameters:

```python
# ✅ GOOD - Trace multi-hop parameters
if workflow_has_complex_chain:
    trace = inspector.trace_parameter("final_node", "critical_param")
    print(trace.show())  # Verify all transformations are correct
```

---

### 3. Check Migration Status Before Deployment

Verify model-database sync before deploying:

```python
# ✅ GOOD - Check migration status
inspector = Inspector(db)

for model_name in db.get_models():
    status = inspector.model_migration_status(model_name)
    if not status.schema_match:
        print(f"⚠ Migration required for {model_name}")
        print(status.show())
```

---

### 4. Use Error Diagnosis in Exception Handlers

Integrate Inspector into error handling:

```python
# ✅ GOOD - Use Inspector for error diagnosis
try:
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
except EnhancedDataFlowError as e:
    inspector = Inspector(workflow)
    diagnosis = inspector.diagnose_error(e)
    print(diagnosis.show())  # Get actionable suggestions
```

---

### 5. Combine CLI and API

Use CLI for quick checks, API for automation:

```bash
# Quick check during development
$ python -m dataflow.cli.inspector_cli workflow my_workflow.py
```

```python
# Automated validation in CI/CD
def validate_workflow(workflow_path):
    workflow = load_workflow(workflow_path)
    inspector = Inspector(workflow)
    return inspector.validate_connections()
```

---

## Advanced Patterns

### Pattern 1: Workflow Health Check

```python
def check_workflow_health(workflow):
    """Comprehensive workflow validation."""
    inspector = Inspector(workflow)

    # 1. Validate connections
    validation = inspector.validate_connections()
    if not validation["is_valid"]:
        return {"healthy": False, "errors": validation["errors"]}

    # 2. Find broken connections
    broken = inspector.find_broken_connections()
    if broken:
        return {"healthy": False, "errors": [issue.message for issue in broken]}

    # 3. Check workflow complexity
    summary = inspector.workflow_summary()
    if summary.complexity == "High":
        return {"healthy": True, "warnings": ["High complexity workflow"]}

    return {"healthy": True, "errors": [], "warnings": []}
```

---

### Pattern 2: Pre-Deployment Checklist

```python
def pre_deployment_checklist(db):
    """Run before deploying to production."""
    inspector = Inspector(db)
    issues = []

    # Check all models
    for model_name in db.get_models():
        # 1. Verify migration status
        status = inspector.model_migration_status(model_name)
        if not status.schema_match:
            issues.append(f"Migration required for {model_name}")

        # 2. Check validation rules
        rules = inspector.model_validation_rules(model_name)
        if not rules.required_fields:
            issues.append(f"No required fields in {model_name}")

    return {"ready": len(issues) == 0, "issues": issues}
```

---

### Pattern 3: Automated Documentation Generation

```python
def generate_workflow_docs(workflow, output_file):
    """Generate documentation from workflow structure."""
    inspector = Inspector(workflow)

    with open(output_file, "w") as f:
        # Workflow summary
        summary = inspector.workflow_summary()
        f.write(summary.show())

        # All connections
        connections = inspector.connections()
        f.write("\n\nConnections:\n")
        for conn in connections:
            f.write(f"  - {conn.show()}\n")

        # Parameter traces for all nodes
        f.write("\n\nParameter Traces:\n")
        for node in workflow.nodes:
            for param in node.parameters:
                trace = inspector.trace_parameter(node.id, param)
                f.write(f"\n{trace.show()}\n")
```

---

## Troubleshooting

### Issue: Inspector returns empty connections

**Cause**: Workflow not built yet or connections not added.

**Solution**:
```python
# ❌ WRONG - Inspect before adding connections
inspector = Inspector(workflow)
connections = inspector.connections()  # Empty

# ✅ CORRECT - Add connections first
workflow.add_connection("create", "id", "read", "id")
inspector = Inspector(workflow)
connections = inspector.connections()  # Found
```

---

### Issue: trace_parameter() shows "no path found"

**Cause**: Parameter is not connected to any source.

**Solution**:
```python
# ❌ WRONG - Parameter not connected
workflow.add_node("UserReadNode", "read", {"id": "$param:user_id"})
# No connection providing user_id

trace = inspector.trace_parameter("read", "id")
# Output: "No path found - parameter not connected"

# ✅ CORRECT - Add connection
workflow.add_connection("create", "id", "read", "id")
trace = inspector.trace_parameter("read", "id")
# Output: Full trace from create.id to read.id
```

---

### Issue: model_migration_status() shows incorrect status

**Cause**: Database not initialized or model not registered.

**Solution**:
```python
# ❌ WRONG - Model not initialized
@db.model
class User:
    id: str

status = inspector.model_migration_status("User")
# Error: Table not found

# ✅ CORRECT - Initialize database first
await db.initialize()
status = inspector.model_migration_status("User")
# Output: Correct table status
```

---

## Summary

Inspector provides comprehensive workflow introspection:

✅ **Connection Analysis** - Trace parameters and detect broken connections
✅ **Model Introspection** - Compare schemas and check validation rules
✅ **Error Diagnosis** - Get actionable suggestions for errors
✅ **CLI Tools** - Quick command-line inspection
✅ **Workflow Validation** - Detect issues before runtime

**Next Steps**:
1. Try the [Quick Start](#quick-start) example
2. Practice with [Common Scenarios](#common-debugging-scenarios)
3. Integrate Inspector into your error handling
4. Use CLI tools for rapid debugging

**Related Documentation**:
- Error Handling Guide: `error-handling.md`
- DataFlow Architecture: `DATAFLOW_ARCHITECTURE.md`
- Testing Guide: `tests/CLAUDE.md`

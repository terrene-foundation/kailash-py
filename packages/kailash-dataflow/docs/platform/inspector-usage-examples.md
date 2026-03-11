# Inspector Connection Analysis - Usage Examples

**Practical examples for using the Inspector connection analysis methods.**

## Quick Start

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from src.dataflow.platform.inspector import Inspector

# Setup
db = DataFlow("postgresql://...")
workflow = WorkflowBuilder()

# Build a simple workflow
workflow.add_node("UserCreateNode", "create", {"id": "user_123"})
workflow.add_node("UserReadNode", "read", {})
workflow.add_connection("create", "id", "read", "id")

# Create inspector
inspector = Inspector(db, workflow=workflow)
```

## Example 1: List All Connections

**Use Case**: Quick overview of all workflow connections

```python
# Get all connections
connections = inspector.connections()

print(f"Workflow has {len(connections)} connection(s):")
for conn in connections:
    print(f"  {conn.show()}")
```

**Output**:
```
Workflow has 1 connection(s):
  ✓ create.id -> read.id
```

## Example 2: Debug Specific Node

**Use Case**: Find all connections involving a specific node

```python
# Get connections for "create" node
create_conns = inspector.connections("create")

print(f"Node 'create' has {len(create_conns)} connection(s):")
for conn in create_conns:
    direction = "outgoing" if conn.source_node == "create" else "incoming"
    print(f"  [{direction}] {conn.show()}")
```

**Output**:
```
Node 'create' has 1 connection(s):
  [outgoing] ✓ create.id -> read.id
```

## Example 3: Find Data Flow Path

**Use Case**: Trace how data flows from one node to another

```python
# Build workflow with multiple hops
workflow.add_node("UserCreateNode", "create", {})
workflow.add_node("UserUpdateNode", "update", {})
workflow.add_node("UserReadNode", "read", {})
workflow.add_connection("create", "id", "update", "id")
workflow.add_connection("update", "id", "read", "id")

inspector = Inspector(db, workflow=workflow)

# Find path from create to read
path = inspector.connection_chain("create", "read")

if path:
    print(f"Data flow from 'create' to 'read' ({len(path)} hop(s)):")
    for i, conn in enumerate(path, 1):
        print(f"  {i}. {conn.source_node}.{conn.source_parameter} "
              f"-> {conn.target_node}.{conn.target_parameter}")
else:
    print("No path found - nodes are disconnected")
```

**Output**:
```
Data flow from 'create' to 'read' (2 hop(s)):
  1. create.id -> update.id
  2. update.id -> read.id
```

## Example 4: Visualize Full Workflow

**Use Case**: Get complete workflow topology overview

```python
# Get connection graph
graph = inspector.connection_graph()

# Pretty print the graph
print(graph.show())

# Access graph properties
print(f"\nWorkflow Analysis:")
print(f"  - Total nodes: {len(graph.nodes)}")
print(f"  - Total connections: {len(graph.connections)}")
print(f"  - Entry points: {', '.join(graph.entry_points)}")
print(f"  - Exit points: {', '.join(graph.exit_points)}")
print(f"  - Cycles detected: {len(graph.cycles)}")
```

**Output**:
```
Connection Graph

Nodes (3):
  - create
  - read
  - update

Entry Points (1):
  - create

Exit Points (1):
  - read

Connections (2):
  ✓ create.id -> update.id
  ✓ update.id -> read.id

No Cycles Detected

Workflow Analysis:
  - Total nodes: 3
  - Total connections: 2
  - Entry points: create
  - Exit points: read
  - Cycles detected: 0
```

## Example 5: Detect Circular Dependencies

**Use Case**: Find cycles that could cause infinite loops

```python
# Build workflow with cycle
workflow.add_node("NodeA", "a", {})
workflow.add_node("NodeB", "b", {})
workflow.add_node("NodeC", "c", {})
workflow.add_connection("a", "out", "b", "in")
workflow.add_connection("b", "out", "c", "in")
workflow.add_connection("c", "out", "a", "in")  # Cycle!

inspector = Inspector(db, workflow=workflow)
graph = inspector.connection_graph()

if graph.cycles:
    print(f"⚠️ WARNING: {len(graph.cycles)} cycle(s) detected!")
    for i, cycle in enumerate(graph.cycles, 1):
        cycle_str = " -> ".join(cycle + [cycle[0]])
        print(f"  Cycle {i}: {cycle_str}")
    print("\nThis will cause infinite execution!")
else:
    print("✓ No cycles detected")
```

**Output**:
```
⚠️ WARNING: 1 cycle(s) detected!
  Cycle 1: a -> b -> c -> a

This will cause infinite execution!
```

## Example 6: Pre-Execution Validation

**Use Case**: Validate workflow before execution

```python
# Validate connections
invalid = inspector.validate_connections()

if invalid:
    print(f"⚠️ VALIDATION FAILED: {len(invalid)} invalid connection(s)")
    for conn in invalid:
        print(f"\n  Connection: {conn.show()}")
        print(f"  Issue: {conn.validation_message}")
    print("\n❌ DO NOT EXECUTE - Fix issues first!")
else:
    print("✓ All connections valid - safe to execute")
```

**Output (invalid)**:
```
⚠️ VALIDATION FAILED: 1 invalid connection(s)

  Connection: ✗ create.bad_param -> read.id
  Issue: Source parameter 'bad_param' not found in node 'create'

❌ DO NOT EXECUTE - Fix issues first!
```

**Output (valid)**:
```
✓ All connections valid - safe to execute
```

## Example 7: Find All Issues

**Use Case**: Comprehensive workflow health check

```python
# Find all broken connections
broken = inspector.find_broken_connections()

if broken:
    print(f"⚠️ WORKFLOW ISSUES DETECTED: {len(broken)} problem(s)\n")

    # Categorize issues
    invalid_conns = [b for b in broken if "not found" in b.validation_message]
    cycles = [b for b in broken if "Circular" in b.validation_message]
    isolated = [b for b in broken if "isolated" in b.validation_message]

    if invalid_conns:
        print(f"Invalid Connections ({len(invalid_conns)}):")
        for conn in invalid_conns:
            print(f"  - {conn.validation_message}")

    if cycles:
        print(f"\nCircular Dependencies ({len(cycles)}):")
        for conn in cycles:
            print(f"  - {conn.validation_message}")

    if isolated:
        print(f"\nIsolated Nodes ({len(isolated)}):")
        for conn in isolated:
            print(f"  - {conn.validation_message}")
else:
    print("✓ No issues found - workflow is healthy!")
```

**Output**:
```
⚠️ WORKFLOW ISSUES DETECTED: 3 problem(s)

Invalid Connections (1):
  - Source parameter 'wrong' not found in node 'create'

Circular Dependencies (1):
  - Circular dependency detected: a -> b -> c -> a

Isolated Nodes (1):
  - Node 'orphan_node' has no connections (isolated node)
```

## Example 8: Automated Workflow Report

**Use Case**: Generate comprehensive workflow health report

```python
def generate_workflow_report(inspector):
    """Generate comprehensive workflow health report."""
    print("=" * 60)
    print("WORKFLOW HEALTH REPORT")
    print("=" * 60)

    # 1. Connection Graph Overview
    graph = inspector.connection_graph()
    print(f"\n1. TOPOLOGY SUMMARY")
    print(f"   - Nodes: {len(graph.nodes)}")
    print(f"   - Connections: {len(graph.connections)}")
    print(f"   - Entry Points: {len(graph.entry_points)}")
    print(f"   - Exit Points: {len(graph.exit_points)}")

    # 2. Validation Status
    invalid = inspector.validate_connections()
    print(f"\n2. VALIDATION STATUS")
    if invalid:
        print(f"   ❌ FAILED: {len(invalid)} invalid connection(s)")
    else:
        print(f"   ✓ PASSED: All connections valid")

    # 3. Cycle Detection
    print(f"\n3. CYCLE DETECTION")
    if graph.cycles:
        print(f"   ⚠️ WARNING: {len(graph.cycles)} cycle(s) detected")
        for i, cycle in enumerate(graph.cycles, 1):
            print(f"      Cycle {i}: {' -> '.join(cycle + [cycle[0]])}")
    else:
        print(f"   ✓ PASSED: No cycles detected")

    # 4. Isolated Nodes
    broken = inspector.find_broken_connections()
    isolated = [b for b in broken if "isolated" in b.validation_message]
    print(f"\n4. CONNECTIVITY CHECK")
    if isolated:
        print(f"   ⚠️ WARNING: {len(isolated)} isolated node(s)")
        for conn in isolated:
            print(f"      - {conn.source_node}")
    else:
        print(f"   ✓ PASSED: All nodes connected")

    # 5. Overall Health
    print(f"\n5. OVERALL HEALTH")
    if not invalid and not graph.cycles and not isolated:
        print(f"   ✓ HEALTHY: Workflow is ready for execution")
    else:
        print(f"   ❌ UNHEALTHY: Fix issues before execution")

    print("=" * 60)

# Usage
generate_workflow_report(inspector)
```

**Output**:
```
============================================================
WORKFLOW HEALTH REPORT
============================================================

1. TOPOLOGY SUMMARY
   - Nodes: 3
   - Connections: 2
   - Entry Points: 1
   - Exit Points: 1

2. VALIDATION STATUS
   ✓ PASSED: All connections valid

3. CYCLE DETECTION
   ✓ PASSED: No cycles detected

4. CONNECTIVITY CHECK
   ✓ PASSED: All nodes connected

5. OVERALL HEALTH
   ✓ HEALTHY: Workflow is ready for execution
============================================================
```

## Example 9: Interactive Debugging Session

**Use Case**: Explore workflow interactively

```python
# Launch interactive mode
inspector.interactive()
```

**Interactive Session**:
```python
# Inside the interactive session
>>> # List all connections
>>> inspector.connections()
[ConnectionInfo(...), ConnectionInfo(...)]

>>> # Check specific node
>>> inspector.connections("create")
[ConnectionInfo(source_node='create', ...)]

>>> # Find path
>>> inspector.connection_chain("create", "read")
[ConnectionInfo(...), ConnectionInfo(...)]

>>> # Get graph
>>> graph = inspector.connection_graph()
>>> print(graph.show())
Connection Graph
...

>>> # Validate
>>> inspector.validate_connections()
[]  # Empty = all valid
```

## Example 10: Integration with Workflow Builder

**Use Case**: Validate workflow during construction

```python
from kailash.workflow.builder import WorkflowBuilder

class ValidatedWorkflowBuilder(WorkflowBuilder):
    """WorkflowBuilder with automatic validation."""

    def __init__(self, db):
        super().__init__()
        self.db = db

    def validate(self):
        """Validate workflow connections."""
        inspector = Inspector(self.db, workflow=self)

        # Check for issues
        broken = inspector.find_broken_connections()
        if broken:
            issues = "\n".join([f"  - {b.validation_message}" for b in broken])
            raise ValueError(f"Workflow validation failed:\n{issues}")

        return True

    def build_safe(self):
        """Build workflow with validation."""
        self.validate()
        return self.build()

# Usage
workflow = ValidatedWorkflowBuilder(db)
workflow.add_node("UserCreateNode", "create", {})
workflow.add_node("UserReadNode", "read", {})
workflow.add_connection("create", "id", "read", "id")

# Validate before building
built_workflow = workflow.build_safe()  # Raises ValueError if invalid
```

## Common Patterns

### Pattern: Connection Count Check
```python
connections = inspector.connections()
if len(connections) == 0:
    print("⚠️ Warning: Workflow has no connections")
```

### Pattern: Entry Point Detection
```python
graph = inspector.connection_graph()
if len(graph.entry_points) == 0:
    print("⚠️ Warning: No entry points - workflow may not start")
elif len(graph.entry_points) > 1:
    print(f"ℹ️ Info: Multiple entry points: {', '.join(graph.entry_points)}")
```

### Pattern: Exit Point Detection
```python
graph = inspector.connection_graph()
if len(graph.exit_points) == 0:
    print("⚠️ Warning: No exit points - workflow may not terminate")
```

### Pattern: Connection Density
```python
graph = inspector.connection_graph()
density = len(graph.connections) / max(len(graph.nodes), 1)
print(f"Connection density: {density:.2f} connections/node")
```

## Performance Tips

1. **Cache Inspector Instance**: Reuse for multiple calls
```python
# Good
inspector = Inspector(db, workflow=workflow)
conns = inspector.connections()
graph = inspector.connection_graph()

# Avoid
conns = Inspector(db, workflow=workflow).connections()
graph = Inspector(db, workflow=workflow).connection_graph()
```

2. **Filter Early**: Use node_id parameter to reduce processing
```python
# Good - filtered
inspector.connections("specific_node")

# Less efficient - filter after
[c for c in inspector.connections() if c.source_node == "specific_node"]
```

3. **Validation Before Execution**: Catch issues early
```python
# Validate once before multiple executions
invalid = inspector.validate_connections()
if not invalid:
    for i in range(100):
        runtime.execute(workflow.build())
```

## Error Handling

```python
try:
    # Connection operations
    connections = inspector.connections()
    graph = inspector.connection_graph()
    invalid = inspector.validate_connections()

except AttributeError as e:
    # Workflow not set or doesn't have required attributes
    print(f"Workflow error: {e}")
    print("Ensure Inspector was created with workflow parameter")

except Exception as e:
    # Unexpected error
    print(f"Unexpected error: {e}")
```

## Best Practices

1. **Always validate before execution**
```python
if not inspector.validate_connections():
    runtime.execute(workflow.build())
```

2. **Check for cycles in production**
```python
graph = inspector.connection_graph()
if graph.cycles:
    raise ValueError("Workflow contains cycles - execution aborted")
```

3. **Use descriptive node IDs**
```python
# Good
workflow.add_node("UserCreateNode", "create_user_for_signup", {})

# Less clear
workflow.add_node("UserCreateNode", "node1", {})
```

4. **Generate reports for complex workflows**
```python
generate_workflow_report(inspector)  # See Example 8
```

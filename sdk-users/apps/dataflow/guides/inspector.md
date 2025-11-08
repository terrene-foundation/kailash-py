# DataFlow Inspector - Workflow Introspection and Debugging

## What is Inspector?

Inspector is a powerful introspection tool for debugging DataFlow workflows without reading source code. It provides detailed information about:

- **Connection Analysis**: List connections, trace paths, analyze workflow topology
- **Parameter Tracing**: Track parameter flow, find sources, identify consumers
- **Workflow Validation**: Check connection validity, detect cycles, find broken connections
- **Node Inspection**: View node parameters, types, and connections

## Getting Started

### Basic Setup

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

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-1",
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserReadNode", "read_user", {"filter": {}})
workflow.add_connection("create_user", "id", "read_user", "filter.id")

# Initialize Inspector
inspector = Inspector(db)
inspector.workflow = workflow  # Attach workflow for connection analysis
```

## Connection Analysis

Inspector provides 5 methods for analyzing workflow connections:

### 1. connections() - List Workflow Connections

List all connections or filter by specific node.

**Signature**:
```python
def connections(node_id: Optional[str] = None) -> List[ConnectionInfo]
```

**Example: List All Connections**

```python
# Get all connections
all_conns = inspector.connections()

print(f"Workflow has {len(all_conns)} connections")
for conn in all_conns:
    print(conn.show())
```

**Output**:
```
✓ create_user.id -> read_user.filter.id
```

**Example: Filter by Node**

```python
# Get connections for specific node (incoming + outgoing)
user_conns = inspector.connections("create_user")

print(f"create_user has {len(user_conns)} connections")
for conn in user_conns:
    print(f"{conn.source_node}.{conn.source_parameter} -> {conn.target_node}.{conn.target_parameter}")
```

**Output**:
```
create_user has 1 connections
create_user.id -> read_user.filter.id
```

**ConnectionInfo Structure**:
```python
@dataclass
class ConnectionInfo:
    source_node: str              # Source node ID
    source_parameter: str         # Source output parameter
    target_node: str              # Target node ID
    target_parameter: str         # Target input parameter
    source_type: Optional[str]    # Source parameter type (if known)
    target_type: Optional[str]    # Target parameter type (if known)
    is_valid: bool                # Validation status
    validation_message: Optional[str]  # Validation error (if invalid)
```

---

### 2. connection_chain() - Trace Path Between Nodes

Find the shortest path of connections from one node to another using BFS.

**Signature**:
```python
def connection_chain(from_node: str, to_node: str) -> List[ConnectionInfo]
```

**Example: Simple Path**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {
    "code": "result = {'value': 10}"
})
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'result': data * 2}"
})
workflow.add_node("PythonCodeNode", "output", {
    "code": "result = {'final': result}"
})

workflow.add_connection("input", "value", "processor", "data")
workflow.add_connection("processor", "result", "output", "result")

inspector.workflow = workflow

# Find path from input to output
path = inspector.connection_chain("input", "output")

print(f"Path has {len(path)} connections:")
for conn in path:
    print(f"  {conn.show()}")
```

**Output**:
```
Path has 2 connections:
  ✓ input.value -> processor.data
  ✓ processor.result -> output.result
```

**Example: No Path**

```python
# Disconnected nodes
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "node_a", {"code": "result = {'x': 1}"})
workflow.add_node("PythonCodeNode", "node_b", {"code": "result = {'y': 2}"})

inspector.workflow = workflow

path = inspector.connection_chain("node_a", "node_b")
if not path:
    print("No path found between node_a and node_b")
```

---

### 3. connection_graph() - Analyze Workflow Topology

Get complete connection structure with entry/exit points and cycle detection.

**Signature**:
```python
def connection_graph() -> ConnectionGraph
```

**Example: Diamond Pattern**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'data': 100}"})
workflow.add_node("PythonCodeNode", "proc_a", {"code": "result = {'result': data * 2}"})
workflow.add_node("PythonCodeNode", "proc_b", {"code": "result = {'result': data * 3}"})
workflow.add_node("PythonCodeNode", "merger", {"code": "result = {'output': a + b}"})

workflow.add_connection("input", "data", "proc_a", "data")
workflow.add_connection("input", "data", "proc_b", "data")
workflow.add_connection("proc_a", "result", "merger", "a")
workflow.add_connection("proc_b", "result", "merger", "b")

inspector.workflow = workflow

# Analyze topology
graph = inspector.connection_graph()
print(graph.show())
```

**Output**:
```
Connection Graph

Nodes (4):
  - input
  - merger
  - proc_a
  - proc_b

Entry Points (1):
  - input

Exit Points (1):
  - merger

Connections (4):
  ✓ input.data -> proc_a.data
  ✓ input.data -> proc_b.data
  ✓ proc_a.result -> merger.a
  ✓ proc_b.result -> merger.b

No Cycles Detected
```

**Example: Detecting Cycles**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "a", {"code": "result = {'out': x}"})
workflow.add_node("PythonCodeNode", "b", {"code": "result = {'out': x}"})
workflow.add_node("PythonCodeNode", "c", {"code": "result = {'out': x}"})

# Create cycle: a -> b -> c -> a
workflow.add_connection("a", "out", "b", "x")
workflow.add_connection("b", "out", "c", "x")
workflow.add_connection("c", "out", "a", "x")

inspector.workflow = workflow

graph = inspector.connection_graph()

if graph.cycles:
    print(f"Warning: {len(graph.cycles)} cycle(s) detected!")
    for cycle in graph.cycles:
        cycle_str = " -> ".join(cycle + [cycle[0]])
        print(f"  {cycle_str}")
```

**Output**:
```
Warning: 1 cycle(s) detected!
  a -> b -> c -> a
```

**ConnectionGraph Structure**:
```python
@dataclass
class ConnectionGraph:
    nodes: List[str]              # All workflow nodes
    connections: List[ConnectionInfo]  # All connections
    entry_points: List[str]       # Nodes with no incoming connections
    exit_points: List[str]        # Nodes with no outgoing connections
    cycles: List[List[str]]       # Detected cycles (list of node paths)
```

---

### 4. validate_connections() - Check Connection Validity

Validate all connections and return invalid ones with error messages.

**Signature**:
```python
def validate_connections() -> List[ConnectionInfo]
```

**Example: Valid Workflow**

```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserReadNode", "read", {"filter": {}})
workflow.add_connection("create", "id", "read", "filter.id")

inspector.workflow = workflow

invalid = inspector.validate_connections()
if invalid:
    print(f"Found {len(invalid)} invalid connections:")
    for conn in invalid:
        print(conn.show())
else:
    print("All connections are valid!")
```

**Output**:
```
All connections are valid!
```

**Example: Invalid Connection**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = {'output': 'test'}"
})
workflow.add_node("PythonCodeNode", "target", {
    "code": "result = {'result': input_data}"
})

# Invalid: source outputs 'output', not 'missing_field'
workflow.add_connection("source", "missing_field", "target", "input_data")

inspector.workflow = workflow

invalid = inspector.validate_connections()
for conn in invalid:
    print(conn.show())
```

**Output**:
```
✗ source.missing_field -> target.input_data
  Issue: Source parameter 'missing_field' not found in node 'source'
```

---

### 5. find_broken_connections() - Identify All Connection Issues

Comprehensive check for invalid connections, cycles, and disconnected nodes.

**Signature**:
```python
def find_broken_connections() -> List[ConnectionInfo]
```

**Example: Complete Validation**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'value': 10}"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = {'result': data * 2}"})
workflow.add_node("PythonCodeNode", "isolated", {"code": "result = {'x': 1}"})

workflow.add_connection("input", "value", "processor", "data")

inspector.workflow = workflow

broken = inspector.find_broken_connections()

if broken:
    print(f"Found {len(broken)} issues:")
    for conn in broken:
        print(f"  {conn.show()}")
        if conn.validation_message:
            print(f"    Issue: {conn.validation_message}")
else:
    print("No broken connections found!")
```

**Output**:
```
Found 1 issues:
  ✗ isolated.(none) -> (none).(none)
    Issue: Node 'isolated' has no connections (isolated node)
```

---

## Parameter Tracing

Inspector provides 5 methods for tracing parameter flow through workflows:

### 1. trace_parameter() - Find Parameter Origin

Trace parameter back to its source node with complete transformation history.

**Signature**:
```python
def trace_parameter(node_id: str, parameter_name: str) -> ParameterTrace
```

**Example: Simple Trace**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {
    "code": "result = {'value': 10}"
})
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'result': data * 2}"
})
workflow.add_node("PythonCodeNode", "output", {
    "code": "result = {'final': result}"
})

workflow.add_connection("input", "value", "processor", "data")
workflow.add_connection("processor", "result", "output", "result")

inspector.workflow = workflow

# Trace 'result' parameter in output node
trace = inspector.trace_parameter("output", "result")
print(trace.show())
```

**Output**:
```
✓ Parameter Trace: result

Source:
  Node: input
  Parameter: value

Transformations (1):
  1. Mapping: value → data
  2. Mapping: result → result

Flow:
  input[value] → [data] → result → result
```

**Example: Dot Notation Trace**

```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserReadNode", "read", {"filter": {}})
workflow.add_connection("create", "record.name", "read", "filter.name")

inspector.workflow = workflow

trace = inspector.trace_parameter("read", "filter.name")
print(trace.show())
```

**Output**:
```
✓ Parameter Trace: filter.name

Source:
  Node: create
  Parameter: record.name

Transformations (1):
  1. Dot Notation: record.name → filter.name

Flow:
  create[record.name] → record.name → filter.name
```

**Example: Workflow Input (No Source)**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'result': input_data * 2}"
})

inspector.workflow = workflow

# Parameter has no upstream connection (workflow input)
trace = inspector.trace_parameter("processor", "input_data")
print(trace.show())
```

**Output**:
```
✓ Parameter Trace: input_data

Source: Workflow input (no upstream connection)

Flow:
  (workflow input) → input_data
```

**ParameterTrace Structure**:
```python
@dataclass
class ParameterTrace:
    parameter_name: str                   # Parameter being traced
    source_node: Optional[str]            # Source node ID (None if workflow input)
    source_parameter: Optional[str]       # Source parameter name
    transformations: List[Dict[str, Any]] # Transformations applied
    consumers: List[str]                  # Nodes consuming this parameter
    parameter_type: Optional[str]         # Parameter type (if known)
    is_complete: bool                     # Whether trace is complete
    missing_sources: List[str]            # Missing sources (if incomplete)
```

---

### 2. parameter_flow() - Track Parameter Forward

Follow parameter as it flows forward through workflow to downstream nodes.

**Signature**:
```python
def parameter_flow(from_node: str, parameter: str) -> List[ParameterTrace]
```

**Example: Single Path**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'value': 10}"})
workflow.add_node("PythonCodeNode", "proc", {"code": "result = {'result': data * 2}"})
workflow.add_node("PythonCodeNode", "output", {"code": "result = {'final': result}"})

workflow.add_connection("input", "value", "proc", "data")
workflow.add_connection("proc", "result", "output", "result")

inspector.workflow = workflow

# Track 'value' parameter forward from input node
flows = inspector.parameter_flow("input", "value")

print(f"Parameter flows to {len(flows)} downstream nodes:")
for flow in flows:
    print(f"  → {flow.parameter_name} (node: {flow.source_node})")
    print(f"    Transformations: {len(flow.transformations)}")
```

**Output**:
```
Parameter flows to 1 downstream nodes:
  → result (node: input)
    Transformations: 2
```

**Example: Multi-Path Flow**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "source", {"code": "result = {'data': 100}"})
workflow.add_node("PythonCodeNode", "proc_a", {"code": "result = {'x': data}"})
workflow.add_node("PythonCodeNode", "proc_b", {"code": "result = {'y': data}"})
workflow.add_node("PythonCodeNode", "proc_c", {"code": "result = {'z': data}"})

workflow.add_connection("source", "data", "proc_a", "data")
workflow.add_connection("source", "data", "proc_b", "data")
workflow.add_connection("source", "data", "proc_c", "data")

inspector.workflow = workflow

# Track 'data' parameter forward from source
flows = inspector.parameter_flow("source", "data")

print(f"Parameter flows to {len(flows)} downstream nodes:")
for flow in flows:
    print(f"  → {flow.parameter_name}")
    for transform in flow.transformations:
        print(f"      {transform['type']}: {transform['details']}")
```

**Output**:
```
Parameter flows to 3 downstream nodes:
  → data
      mapping: data → data
  → data
      mapping: data → data
  → data
      mapping: data → data
```

---

### 3. find_parameter_source() - Quick Source Lookup

Find source node for parameter without full trace information.

**Signature**:
```python
def find_parameter_source(node_id: str, parameter: str) -> Optional[str]
```

**Example: Find Source**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'value': 10}"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = {'result': data * 2}"})

workflow.add_connection("input", "value", "processor", "data")

inspector.workflow = workflow

# Quick source lookup
source = inspector.find_parameter_source("processor", "data")

if source:
    print(f"Parameter 'data' comes from node: {source}")
else:
    print("Parameter 'data' is a workflow input")
```

**Output**:
```
Parameter 'data' comes from node: input
```

**Example: Workflow Input**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'result': input_data * 2}"
})

inspector.workflow = workflow

source = inspector.find_parameter_source("processor", "input_data")

if source:
    print(f"Parameter 'input_data' comes from node: {source}")
else:
    print("Parameter 'input_data' is a workflow input")
```

**Output**:
```
Parameter 'input_data' is a workflow input
```

---

### 4. parameter_dependencies() - List All Dependencies

Get complete dependency map for a node with traces for each parameter.

**Signature**:
```python
def parameter_dependencies(node_id: str) -> Dict[str, ParameterTrace]
```

**Example: Node Dependencies**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'a': 1, 'b': 2}"})
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'result': x + y}"
})

workflow.add_connection("input", "a", "processor", "x")
workflow.add_connection("input", "b", "processor", "y")

inspector.workflow = workflow

# Get all dependencies for processor node
deps = inspector.parameter_dependencies("processor")

print(f"Node 'processor' has {len(deps)} parameter dependencies:")
for param_name, trace in deps.items():
    source = trace.source_node or "(workflow input)"
    print(f"  {param_name} ← {source}")
```

**Output**:
```
Node 'processor' has 2 parameter dependencies:
  x ← input
  y ← input
```

**Example: Complex Dependencies**

```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserUpdateNode", "update", {
    "filter": {},
    "fields": {"name": "Alice Updated"}
})

workflow.add_connection("create", "id", "update", "filter.id")
workflow.add_connection("create", "record.email", "update", "fields.email")

inspector.workflow = workflow

deps = inspector.parameter_dependencies("update")

print(f"Node 'update' has {len(deps)} parameter dependencies:")
for param_name, trace in deps.items():
    print(f"\n{param_name}:")
    print(f"  Source: {trace.source_node}.{trace.source_parameter}")
    if trace.transformations:
        print(f"  Transformations: {len(trace.transformations)}")
```

**Output**:
```
Node 'update' has 2 parameter dependencies:

filter.id:
  Source: create.id
  Transformations: 1

fields.email:
  Source: create.record.email
  Transformations: 1
```

---

### 5. parameter_consumers() - Find Parameter Consumers

List all nodes that consume a specific output parameter.

**Signature**:
```python
def parameter_consumers(node_id: str, output_param: str) -> List[str]
```

**Example: Single Consumer**

```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserReadNode", "read", {"filter": {}})

workflow.add_connection("create", "id", "read", "filter.id")

inspector.workflow = workflow

# Find consumers of 'id' output
consumers = inspector.parameter_consumers("create", "id")

print(f"Parameter 'id' is consumed by {len(consumers)} node(s):")
for consumer in consumers:
    print(f"  - {consumer}")
```

**Output**:
```
Parameter 'id' is consumed by 1 node(s):
  - read
```

**Example: Multiple Consumers**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "source", {"code": "result = {'data': 100}"})
workflow.add_node("PythonCodeNode", "proc_a", {"code": "result = {'x': data}"})
workflow.add_node("PythonCodeNode", "proc_b", {"code": "result = {'y': data}"})
workflow.add_node("PythonCodeNode", "proc_c", {"code": "result = {'z': data}"})

workflow.add_connection("source", "data", "proc_a", "data")
workflow.add_connection("source", "data", "proc_b", "data")
workflow.add_connection("source", "data", "proc_c", "data")

inspector.workflow = workflow

# Find consumers of 'data' output
consumers = inspector.parameter_consumers("source", "data")

print(f"Parameter 'data' is consumed by {len(consumers)} node(s):")
for consumer in consumers:
    print(f"  - {consumer}")
```

**Output**:
```
Parameter 'data' is consumed by 3 node(s):
  - proc_a
  - proc_b
  - proc_c
```

**Example: No Consumers**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "endpoint", {
    "code": "result = {'final_result': data}"
})

inspector.workflow = workflow

# Find consumers of 'final_result' (endpoint node)
consumers = inspector.parameter_consumers("endpoint", "final_result")

if not consumers:
    print("Parameter 'final_result' has no consumers (workflow output)")
```

**Output**:
```
Parameter 'final_result' has no consumers (workflow output)
```

---

## Common Debugging Scenarios

### Scenario 1: Debugging Missing Parameter Errors

**Problem**: Workflow fails with "missing parameter" error.

```python
# Error: Node 'update_user' missing required parameter 'filter.id'

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("UserUpdateNode", "update", {
    "filter": {},
    "fields": {"name": "Alice Updated"}
})

# Missing connection!
inspector.workflow = workflow

# Debug: Check dependencies
deps = inspector.parameter_dependencies("update")
print(f"Update node dependencies: {list(deps.keys())}")

# Debug: Find broken connections
broken = inspector.find_broken_connections()
if broken:
    print("\nBroken connections found:")
    for conn in broken:
        print(f"  {conn.show()}")
```

**Solution**: Add missing connection:
```python
workflow.add_connection("create", "id", "update", "filter.id")
```

---

### Scenario 2: Finding Circular Dependencies

**Problem**: Workflow hangs or fails with cycle error.

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "a", {"code": "result = {'out': x}"})
workflow.add_node("PythonCodeNode", "b", {"code": "result = {'out': x}"})
workflow.add_node("PythonCodeNode", "c", {"code": "result = {'out': x}"})

workflow.add_connection("a", "out", "b", "x")
workflow.add_connection("b", "out", "c", "x")
workflow.add_connection("c", "out", "a", "x")  # Creates cycle!

inspector.workflow = workflow

# Debug: Check for cycles
graph = inspector.connection_graph()

if graph.cycles:
    print(f"Found {len(graph.cycles)} cycle(s):")
    for cycle in graph.cycles:
        cycle_str = " -> ".join(cycle + [cycle[0]])
        print(f"  {cycle_str}")
```

**Output**:
```
Found 1 cycle(s):
  a -> b -> c -> a
```

---

### Scenario 3: Tracing Data Flow Through Workflow

**Problem**: Need to understand how data flows from input to output.

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input", {"code": "result = {'value': 10}"})
workflow.add_node("PythonCodeNode", "validate", {"code": "result = {'valid': data > 0}"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = {'result': data * 2}"})
workflow.add_node("PythonCodeNode", "output", {"code": "result = {'final': result}"})

workflow.add_connection("input", "value", "validate", "data")
workflow.add_connection("validate", "valid", "process", "should_process")
workflow.add_connection("input", "value", "process", "data")
workflow.add_connection("process", "result", "output", "result")

inspector.workflow = workflow

# Debug: Trace from input to output
path = inspector.connection_chain("input", "output")

print("Data flow path:")
for conn in path:
    print(f"  {conn.source_node}.{conn.source_parameter} -> {conn.target_node}.{conn.target_parameter}")

# Debug: Full trace for output parameter
trace = inspector.trace_parameter("output", "result")
print(f"\nFull trace:")
print(trace.show())
```

---

### Scenario 4: Validating Workflow Structure

**Problem**: Need to ensure workflow is correctly structured before execution.

```python
workflow = WorkflowBuilder()
# ... build complex workflow ...

inspector.workflow = workflow

# 1. Check for broken connections
print("=== Connection Validation ===")
broken = inspector.find_broken_connections()
if broken:
    print(f"Found {len(broken)} issues:")
    for conn in broken:
        print(f"  {conn.show()}")
        if conn.validation_message:
            print(f"    Issue: {conn.validation_message}")
else:
    print("✓ No broken connections")

# 2. Check topology
print("\n=== Topology Analysis ===")
graph = inspector.connection_graph()
print(f"Nodes: {len(graph.nodes)}")
print(f"Connections: {len(graph.connections)}")
print(f"Entry points: {', '.join(graph.entry_points)}")
print(f"Exit points: {', '.join(graph.exit_points)}")

if graph.cycles:
    print(f"⚠ Warning: {len(graph.cycles)} cycle(s) detected")
else:
    print("✓ No cycles detected")

# 3. Check for isolated nodes
if broken:
    isolated = [conn for conn in broken if "isolated" in conn.validation_message.lower()]
    if isolated:
        print(f"\n⚠ Warning: {len(isolated)} isolated node(s)")
```

---

## Advanced Usage

### Combining Methods for Comprehensive Analysis

```python
def analyze_workflow(inspector):
    """Comprehensive workflow analysis."""
    print("=" * 60)
    print("WORKFLOW ANALYSIS")
    print("=" * 60)

    # 1. Topology
    graph = inspector.connection_graph()
    print(f"\n📊 Topology:")
    print(f"  Nodes: {len(graph.nodes)}")
    print(f"  Connections: {len(graph.connections)}")
    print(f"  Entry points: {len(graph.entry_points)}")
    print(f"  Exit points: {len(graph.exit_points)}")

    # 2. Validation
    print(f"\n🔍 Validation:")
    broken = inspector.find_broken_connections()
    if broken:
        print(f"  ❌ Found {len(broken)} issue(s)")
        for conn in broken:
            print(f"    - {conn.validation_message}")
    else:
        print(f"  ✅ All connections valid")

    # 3. Cycles
    if graph.cycles:
        print(f"\n⚠️  Cycles:")
        for i, cycle in enumerate(graph.cycles, 1):
            cycle_str = " -> ".join(cycle + [cycle[0]])
            print(f"  {i}. {cycle_str}")
    else:
        print(f"\n✅ No cycles detected")

    # 4. Parameter flow for entry points
    if graph.entry_points:
        print(f"\n🔄 Parameter Flow from Entry Points:")
        for entry in graph.entry_points[:3]:  # Limit to 3 for brevity
            # Get outgoing connections
            outgoing = [conn for conn in graph.connections if conn.source_node == entry]
            if outgoing:
                print(f"\n  From '{entry}':")
                for conn in outgoing[:5]:  # Limit to 5
                    flows = inspector.parameter_flow(entry, conn.source_parameter)
                    print(f"    {conn.source_parameter} → {len(flows)} downstream node(s)")

# Use it
inspector.workflow = my_workflow
analyze_workflow(inspector)
```

---

### Interactive Debugging Session

```python
# Launch interactive session
inspector.interactive()
```

**Interactive Commands**:
```python
# Model & Node Inspection
inspector.model('User')                # Inspect model
inspector.node('create_user')          # Inspect node
inspector.instance()                   # Inspect DataFlow instance

# Connection Analysis
inspector.connections()                # List all connections
inspector.connections('create_user')   # List connections for node
inspector.connection_chain('A', 'B')   # Find path between nodes
inspector.connection_graph()           # Get full connection graph
inspector.validate_connections()       # Check connection validity
inspector.find_broken_connections()    # Find broken connections

# Parameter Tracing
inspector.trace_parameter('node_id', 'param_name')        # Trace to source
inspector.parameter_flow('node_id', 'param_name')         # Trace forward
inspector.find_parameter_source('node_id', 'param_name')  # Find source
inspector.parameter_dependencies('node_id')               # List dependencies
inspector.parameter_consumers('node_id', 'output_param')  # List consumers
```

---

## Best Practices

### 1. Always Attach Workflow Before Analysis

```python
# ✅ CORRECT
inspector = Inspector(db)
inspector.workflow = my_workflow  # Attach workflow first
connections = inspector.connections()

# ❌ WRONG - Returns empty list
inspector = Inspector(db)
connections = inspector.connections()  # No workflow attached!
```

### 2. Use .show() for Formatted Output

```python
# ✅ CORRECT - Formatted with colors
connections = inspector.connections()
for conn in connections:
    print(conn.show())  # Uses .show() for formatting

# ❌ WRONG - Raw dataclass output
connections = inspector.connections()
for conn in connections:
    print(conn)  # Raw output, hard to read
```

### 3. Check for Empty Results

```python
# ✅ CORRECT
path = inspector.connection_chain("node_a", "node_b")
if path:
    print(f"Found path with {len(path)} connections")
else:
    print("No path found between nodes")

# ❌ WRONG - Assumes path always exists
path = inspector.connection_chain("node_a", "node_b")
print(f"Path length: {len(path)}")  # May be 0!
```

### 4. Validate Before Execution

```python
# ✅ CORRECT - Validate first
inspector.workflow = workflow
broken = inspector.find_broken_connections()

if not broken:
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
else:
    print("Fix broken connections before executing")

# ❌ WRONG - Execute without validation
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())  # May fail!
```

### 5. Use Appropriate Method for Task

**Quick source lookup**:
```python
# ✅ Use find_parameter_source() - fast
source = inspector.find_parameter_source("node_id", "param")
```

**Full trace with transformations**:
```python
# ✅ Use trace_parameter() - detailed
trace = inspector.trace_parameter("node_id", "param")
print(trace.show())
```

**Forward flow analysis**:
```python
# ✅ Use parameter_flow() - tracks all paths
flows = inspector.parameter_flow("node_id", "param")
```

---

## Troubleshooting

### Issue: Empty connections list

**Cause**: Workflow not attached to inspector.

**Solution**:
```python
inspector = Inspector(db)
inspector.workflow = my_workflow  # Attach workflow
connections = inspector.connections()
```

---

### Issue: Trace shows incomplete

**Cause**: Parameter has no upstream connection (workflow input).

**Solution**: This is expected behavior. Check `trace.is_complete` and `trace.source_node`:
```python
trace = inspector.trace_parameter("node_id", "param")
if trace.source_node is None:
    print("Parameter is a workflow input")
```

---

### Issue: Cycle detection false positives

**Cause**: Workflow may have intentional cycles (enable_cycles=True).

**Solution**: Cycles are not always errors. Check runtime configuration:
```python
graph = inspector.connection_graph()
if graph.cycles:
    print("Cycles detected - ensure enable_cycles=True in runtime")
    runtime = LocalRuntime(enable_cycles=True)
```

---

## Performance Tips

1. **Reuse Inspector Instance**: Create once, attach different workflows as needed
2. **Filter Connections**: Use `connections(node_id)` instead of `connections()` for specific nodes
3. **Quick Lookups**: Use `find_parameter_source()` instead of `trace_parameter()` when full trace not needed
4. **Batch Validation**: Call `find_broken_connections()` once instead of multiple separate checks

---

## Summary

Inspector provides 10 essential methods for workflow debugging:

**Connection Analysis** (5 methods):
- `connections()` - List all connections or filter by node
- `connection_chain()` - Find path between two nodes
- `connection_graph()` - Analyze complete topology
- `validate_connections()` - Check connection validity
- `find_broken_connections()` - Identify all issues

**Parameter Tracing** (5 methods):
- `trace_parameter()` - Trace parameter to source with transformations
- `parameter_flow()` - Track parameter forward through workflow
- `find_parameter_source()` - Quick source node lookup
- `parameter_dependencies()` - List all node dependencies
- `parameter_consumers()` - Find nodes consuming output parameter

Use Inspector to:
- Debug missing parameter errors
- Find circular dependencies
- Trace data flow through workflows
- Validate workflow structure before execution
- Understand complex workflows without reading code

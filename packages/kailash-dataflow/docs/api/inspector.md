# Inspector API

## What Is This

Inspector provides introspection and debugging utilities for DataFlow models, nodes, workflows, and connections. Use it to understand model structure, trace parameter flows, validate connections, and debug workflow issues.

## When to Use

- **Development**: Explore model/node structure during development
- **Debugging**: Trace parameter flows and find broken connections
- **Validation**: Validate workflow connections before execution
- **Documentation**: Generate workflow documentation

## Basic Usage

### Initialize Inspector

```python
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector

db = DataFlow(":memory:")

@db.model
class User:
    id: str
    name: str
    email: str

# Create inspector
inspector = Inspector(db)
```

---

## Model Inspection

### model()

Get detailed information about a DataFlow model.

**Signature**:
```python
def model(model_name: str) -> ModelInfo
```

**Returns**: `ModelInfo` object with model details

**Example**:
```python
# Inspect User model
model_info = inspector.model("User")
print(model_info.show())
```

**Output**:
```
Model: User
Fields:
  - id: str (Required)
  - name: str (Required)
  - email: str (Required)
Auto-Managed Fields:
  - created_at: datetime
  - updated_at: datetime
Generated Nodes:
  - UserCreateNode
  - UserReadNode
  - UserUpdateNode
  - UserDeleteNode
  - UserListNode
  - UserBulkCreateNode
  - UserBulkUpdateNode
  - UserBulkDeleteNode
  - UserUpsertNode
  - UserBulkUpsertNode
```

**Use Case**: Understand model structure and generated nodes.

---

### node()

Get detailed information about a specific node.

**Signature**:
```python
def node(node_id: str) -> NodeInfo
```

**Returns**: `NodeInfo` object with node details

**Example**:
```python
# Inspect specific node in workflow
node_info = inspector.node("create_user")
print(node_info.show())
```

**Output**:
```
Node: create_user
Type: UserCreateNode
Parameters:
  Required:
    - id: str
    - name: str
    - email: str
  Optional:
    (none)
Connections:
  Inputs: (none)
  Outputs:
    - data → user_read.id
```

**Use Case**: Debug node configuration and connections.

---

## Instance Inspection

### instance()

Get DataFlow instance information.

**Signature**:
```python
def instance() -> InstanceInfo
```

**Returns**: `InstanceInfo` object with instance details

**Example**:
```python
instance_info = inspector.instance()
print(instance_info.show())
```

**Output**:
```
DataFlow Instance
Database: postgresql://localhost/mydb
Registered Models: 3
  - User
  - Organization
  - Product
Generated Nodes: 30 (10 per model)
Cache: Enabled (size: 100)
```

**Use Case**: Overview of DataFlow instance state.

---

## Workflow Inspection

### workflow()

Get workflow structure and statistics.

**Signature**:
```python
def workflow(workflow: Any) -> WorkflowInfo
```

**Returns**: `WorkflowInfo` object with workflow details

**Example**:
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
workflow.add_node("UserReadNode", "read", {...})

# Inspect workflow
workflow_info = inspector.workflow(workflow.build())
print(workflow_info.show())
```

**Output**:
```
Workflow Summary
Total Nodes: 2
Total Connections: 1
Node Types:
  - UserCreateNode: 1
  - UserReadNode: 1
Execution Order:
  1. create
  2. read
```

**Use Case**: Understand workflow structure before execution.

---

## Connection Analysis

### connections()

Get all connections in a workflow, optionally filtered by node.

**Signature**:
```python
def connections(node_id: Optional[str] = None) -> list[ConnectionInfo]
```

**Returns**: List of `ConnectionInfo` objects

**Example**:
```python
# Get all connections
all_connections = inspector.connections()

# Get connections for specific node
user_connections = inspector.connections(node_id="create")

for conn in user_connections:
    print(conn.show())
```

**Output**:
```
Connection: create → read
  Source: create.id
  Target: read.id
  Type: Direct
```

**Use Case**: Visualize workflow data flow.

---

### connection_chain()

Get connection chain between two nodes.

**Signature**:
```python
def connection_chain(from_node: str, to_node: str) -> list[ConnectionInfo]
```

**Returns**: List of `ConnectionInfo` objects representing the chain

**Example**:
```python
# Trace path from input to output
chain = inspector.connection_chain("input", "output")

print(f"Chain length: {len(chain)}")
for conn in chain:
    print(f"  {conn.source_node} → {conn.target_node}")
```

**Output**:
```
Chain length: 3
  input → transform
  transform → validate
  validate → output
```

**Use Case**: Debug multi-step workflows.

---

### connection_graph()

Get complete connection graph as adjacency list.

**Signature**:
```python
def connection_graph() -> dict[str, list[str]]
```

**Returns**: Dictionary mapping node_id → list of connected node_ids

**Example**:
```python
graph = inspector.connection_graph()

for node, targets in graph.items():
    print(f"{node} connects to: {', '.join(targets)}")
```

**Output**:
```
input connects to: transform, validate
transform connects to: output
validate connects to: output
```

**Use Case**: Generate workflow visualizations.

---

## Validation

### validate_connections()

Validate all workflow connections.

**Signature**:
```python
def validate_connections() -> tuple[bool, list[str]]
```

**Returns**: Tuple of (is_valid, list of error messages)

**Example**:
```python
is_valid, errors = inspector.validate_connections()

if not is_valid:
    print("Connection errors found:")
    for error in errors:
        print(f"  - {error}")
else:
    print("All connections are valid!")
```

**Output** (if errors):
```
Connection errors found:
  - Node 'create' output 'user_data' not found
  - Node 'read' missing required parameter 'id'
```

**Use Case**: Validate workflow before execution.

---

### find_broken_connections()

Find broken connections in workflow.

**Signature**:
```python
def find_broken_connections() -> list[ConnectionInfo]
```

**Returns**: List of `ConnectionInfo` objects for broken connections

**Example**:
```python
broken = inspector.find_broken_connections()

if broken:
    print(f"Found {len(broken)} broken connections:")
    for conn in broken:
        print(f"  {conn.source_node}.{conn.source_param} → {conn.target_node}.{conn.target_param}")
else:
    print("No broken connections!")
```

**Use Case**: Quick check for workflow issues.

---

## Parameter Tracing

### trace_parameter()

Trace a parameter's flow through the workflow.

**Signature**:
```python
def trace_parameter(node_id: str, parameter_name: str) -> ParameterTrace
```

**Returns**: `ParameterTrace` object with trace details

**Example**:
```python
# Trace where 'id' parameter comes from
trace = inspector.trace_parameter("read", "id")

print(f"Parameter: {trace.parameter}")
print(f"Node: {trace.node_id}")
print(f"Source: {trace.source}")
print(f"Hops: {trace.hops}")
```

**Output**:
```
Parameter: id
Node: read
Source: create
Hops: 1
```

**Use Case**: Debug parameter passing issues.

---

### parameter_flow()

Track parameter flow from a node downstream.

**Signature**:
```python
def parameter_flow(from_node: str, parameter: str) -> list[ParameterTrace]
```

**Returns**: List of `ParameterTrace` objects showing downstream flow

**Example**:
```python
# Track where 'id' flows after 'create'
flow = inspector.parameter_flow("create", "id")

print(f"Parameter 'id' flows to {len(flow)} nodes:")
for trace in flow:
    print(f"  → {trace.node_id} (as '{trace.parameter}')")
```

**Output**:
```
Parameter 'id' flows to 2 nodes:
  → read (as 'id')
  → update (as 'filter.id')
```

**Use Case**: Understand parameter propagation.

---

### find_parameter_source()

Find the source node of a parameter.

**Signature**:
```python
def find_parameter_source(node_id: str, parameter: str) -> Optional[str]
```

**Returns**: Source node ID or None if not found

**Example**:
```python
source = inspector.find_parameter_source("read", "id")
print(f"Parameter 'id' in 'read' comes from: {source}")
```

**Output**:
```
Parameter 'id' in 'read' comes from: create
```

**Use Case**: Quick source lookup.

---

### parameter_dependencies()

Get all parameter dependencies for a node.

**Signature**:
```python
def parameter_dependencies(node_id: str) -> dict[str, str]
```

**Returns**: Dictionary mapping parameter_name → source_node_id

**Example**:
```python
deps = inspector.parameter_dependencies("update")

print(f"Node 'update' depends on:")
for param, source in deps.items():
    print(f"  {param} ← {source}")
```

**Output**:
```
Node 'update' depends on:
  filter.id ← create
  fields.name ← input
```

**Use Case**: Understand node dependencies.

---

## Best Practices

### Pattern 1: Pre-Execution Validation

```python
# Validate workflow before execution
workflow = WorkflowBuilder()
# ... add nodes and connections ...

inspector = Inspector(db)
is_valid, errors = inspector.validate_connections()

if not is_valid:
    print("Workflow has errors:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)

# Execute if valid
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

---

### Pattern 2: Debug Parameter Flow

```python
# Find why parameter is missing
inspector = Inspector(db)

# Check if parameter has a source
source = inspector.find_parameter_source("read", "id")

if not source:
    print("Parameter 'id' has no source!")

    # Check all dependencies
    deps = inspector.parameter_dependencies("read")
    print(f"Available parameters: {list(deps.keys())}")
```

---

### Pattern 3: Generate Workflow Documentation

```python
def document_workflow(workflow, db):
    """Generate workflow documentation."""
    inspector = Inspector(db)

    # Workflow overview
    wf_info = inspector.workflow(workflow)
    print(wf_info.show())

    # Connection graph
    print("\nConnection Graph:")
    graph = inspector.connection_graph()
    for node, targets in graph.items():
        print(f"  {node} → {', '.join(targets)}")

    # Parameter flows
    print("\nParameter Flows:")
    connections = inspector.connections()
    for conn in connections:
        print(f"  {conn.source_node}.{conn.source_param} → {conn.target_node}.{conn.target_param}")
```

---

### Pattern 4: Find Broken Connections

```python
# Quick health check
inspector = Inspector(db)
broken = inspector.find_broken_connections()

if broken:
    print(f"WARNING: {len(broken)} broken connections found!")
    for conn in broken:
        print(f"  Fix: {conn.source_node}.{conn.source_param} → {conn.target_node}.{conn.target_param}")
```

---

### Pattern 5: Explore Models

```python
# Discover available models and nodes
inspector = Inspector(db)
instance_info = inspector.instance()

print(f"Available models ({len(instance_info.models)}):")
for model_name in instance_info.models:
    model_info = inspector.model(model_name)
    print(f"\n{model_name}:")
    print(f"  Fields: {len(model_info.fields)}")
    print(f"  Nodes: {len(model_info.generated_nodes)}")
```

---

## Info Classes

All Inspector methods return Info objects with a `show()` method for formatted output:

**ModelInfo**:
- `name`: Model name
- `fields`: List of field definitions
- `auto_managed_fields`: Auto-managed fields (created_at, updated_at)
- `generated_nodes`: List of generated node names

**NodeInfo**:
- `node_id`: Node identifier
- `node_type`: Node type (e.g., "UserCreateNode")
- `parameters`: Required and optional parameters
- `connections`: Input and output connections

**InstanceInfo**:
- `database_url`: Database connection string
- `models`: List of registered models
- `node_count`: Total generated nodes
- `cache_info`: Cache configuration

**WorkflowInfo**:
- `node_count`: Total nodes in workflow
- `connection_count`: Total connections
- `node_types`: Distribution of node types
- `execution_order`: Topological order of execution

**ConnectionInfo**:
- `source_node`: Source node ID
- `source_param`: Source parameter name
- `target_node`: Target node ID
- `target_param`: Target parameter name
- `connection_type`: Direct, indirect, or broken

**ParameterTrace**:
- `node_id`: Node being traced
- `parameter`: Parameter name
- `source`: Source node ID
- `hops`: Number of hops from source

---

## Related

- [ErrorEnhancer API](error-enhancer.md) - Error enhancement utilities
- [Common Patterns](../guides/common-patterns.md) - Best practices for DataFlow
- [Error Cheat Sheet](../guides/cheat-sheet-errors.md) - Common errors and solutions

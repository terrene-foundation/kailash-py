# Inspector Parameter Tracing API

Complete implementation of parameter tracing methods for debugging workflow parameter flows without reading source code.

## Overview

The Inspector class provides 5 parameter tracing methods for analyzing how parameters flow through workflows:

1. **trace_parameter()** - Trace parameter back to source (DFS)
2. **parameter_flow()** - Trace parameter forward through workflow (BFS)
3. **find_parameter_source()** - Quick source lookup
4. **parameter_dependencies()** - All dependencies for a node
5. **parameter_consumers()** - All consumers of an output parameter

## API Reference

### ParameterTrace Dataclass

Information about a parameter's trace through the workflow.

```python
@dataclass
class ParameterTrace:
    parameter_name: str                              # Parameter name
    source_node: Optional[str] = None                # Source node ID
    source_parameter: Optional[str] = None           # Source parameter name
    transformations: List[Dict[str, Any]] = []       # Parameter transformations
    consumers: List[str] = []                        # Consumer node IDs
    parameter_type: Optional[str] = None             # Parameter type (if known)
    is_complete: bool = True                         # Trace completeness
    missing_sources: List[str] = []                  # Missing sources (if incomplete)

    def show(self, color: bool = True) -> str:
        """Format parameter trace with flow visualization."""
```

**Transformation Types:**
- `dot_notation` - Dot notation navigation (e.g., `data.user.email → email`)
- `mapping` - Parameter renaming (e.g., `user_data → input_data`)
- `type_change` - Type conversion (if detectable)

**Example Output:**
```
✓ Parameter Trace: email

Source:
  Node: transform
  Parameter: data.email

Transformations (1):
  1. Dot Notation: data.email → email

Flow:
  transform [data.email] → data.email → email
```

---

## Method 1: trace_parameter()

Trace parameter back to its source using DFS.

**Signature:**
```python
def trace_parameter(self, node_id: str, parameter_name: str) -> ParameterTrace
```

**Parameters:**
- `node_id` - Node identifier
- `parameter_name` - Parameter name to trace

**Returns:**
- `ParameterTrace` with complete trace information

**Example:**
```python
from dataflow.platform.inspector import Inspector

inspector = Inspector(db, workflow)

# Trace 'email' parameter in create_record node
trace = inspector.trace_parameter("create_record", "email")

print(trace.show())
print(f"Source: {trace.source_node}.{trace.source_parameter}")
print(f"Transformations: {len(trace.transformations)}")
```

**Use Cases:**
- Find where a parameter value comes from
- Debug missing or incorrect parameter values
- Understand parameter transformations (dot notation, mapping)
- Identify workflow input parameters (no source)

---

## Method 2: parameter_flow()

Show how parameter flows forward through workflow using BFS.

**Signature:**
```python
def parameter_flow(self, from_node: str, parameter: str) -> List[ParameterTrace]
```

**Parameters:**
- `from_node` - Source node ID
- `parameter` - Parameter name to trace forward

**Returns:**
- List of `ParameterTrace` instances for all paths the parameter takes

**Example:**
```python
# Trace how 'user_data' flows from fetch_user node
traces = inspector.parameter_flow("fetch_user", "user_data")

print(f"Parameter flows to {len(traces)} downstream nodes:")
for trace in traces:
    print(f"  → {trace.parameter_name}")
    for transform in trace.transformations:
        print(f"    • {transform['type']}: {transform['details']}")
```

**Use Cases:**
- Find all consumers of an output parameter
- Understand how a parameter propagates through the workflow
- Identify parameter name changes across nodes
- Debug unexpected parameter usage

---

## Method 3: find_parameter_source()

Find original source node for a parameter (simple version of trace_parameter).

**Signature:**
```python
def find_parameter_source(self, node_id: str, parameter: str) -> Optional[str]
```

**Parameters:**
- `node_id` - Node identifier
- `parameter` - Parameter name

**Returns:**
- Source node ID, or `None` if parameter has no source (workflow input)

**Example:**
```python
# Quick source lookup
source = inspector.find_parameter_source("create_user", "email")

if source:
    print(f"Email comes from node: {source}")
else:
    print("Email is a workflow input")
```

**Use Cases:**
- Quick source lookup without needing full trace
- Determine if parameter is a workflow input
- Lightweight parameter dependency checking

---

## Method 4: parameter_dependencies()

List all parameters this node depends on with their traces.

**Signature:**
```python
def parameter_dependencies(self, node_id: str) -> Dict[str, ParameterTrace]
```

**Parameters:**
- `node_id` - Node identifier

**Returns:**
- Dict mapping parameter name to `ParameterTrace`

**Example:**
```python
# Get all dependencies for create_record node
deps = inspector.parameter_dependencies("create_record")

print(f"Node has {len(deps)} parameter dependencies:")
for param_name, trace in deps.items():
    source_info = f"{trace.source_node}.{trace.source_parameter}" if trace.source_node else "(workflow input)"
    print(f"  {param_name} ← {source_info}")
```

**Use Cases:**
- Understand all input requirements for a node
- Debug missing parameter connections
- Validate node has all required inputs
- Dependency analysis for workflow optimization

---

## Method 5: parameter_consumers()

List all nodes that consume this output parameter.

**Signature:**
```python
def parameter_consumers(self, node_id: str, output_param: str) -> List[str]
```

**Parameters:**
- `node_id` - Node identifier
- `output_param` - Output parameter name

**Returns:**
- List of consumer node IDs (sorted)

**Example:**
```python
# Find all consumers of transform.data.email
consumers = inspector.parameter_consumers("transform", "data.email")

print(f"data.email is consumed by {len(consumers)} nodes:")
for consumer in consumers:
    print(f"  → {consumer}")
```

**Use Cases:**
- Find all downstream nodes using an output
- Impact analysis for parameter changes
- Identify unused outputs
- Workflow refactoring

---

## Complete Workflow Analysis Example

```python
from dataflow.platform.inspector import Inspector

# Initialize inspector
inspector = Inspector(db, workflow)

# Analyze complete workflow
nodes = ["fetch_user", "transform", "create_record", "send_email"]

for node in nodes:
    print(f"\nNode: {node}")
    print("─" * 40)

    # Get all dependencies
    deps = inspector.parameter_dependencies(node)
    if deps:
        print(f"Dependencies ({len(deps)}):")
        for param_name, trace in deps.items():
            source_info = f"{trace.source_node}.{trace.source_parameter}" if trace.source_node else "(workflow input)"
            print(f"  • {param_name} ← {source_info}")
    else:
        print("Dependencies: (none - entry point)")

    # Check common outputs
    # In real usage, query node metadata for actual output parameters
    for output_param in ["user_data", "data.email", "record_id"]:
        consumers = inspector.parameter_consumers(node, output_param)
        if consumers:
            print(f"Consumers of '{output_param}' ({len(consumers)}):")
            for consumer in consumers:
                print(f"  → {consumer}")
```

**Output:**
```
Node: fetch_user
────────────────────────────────────────
Dependencies: (none - entry point)
Consumers of 'user_data' (1):
  → transform

Node: transform
────────────────────────────────────────
Dependencies (1):
  • input_data ← fetch_user.user_data
Consumers of 'data.email' (2):
  → create_record
  → send_email

Node: create_record
────────────────────────────────────────
Dependencies (1):
  • email ← transform.data.email
Consumers of 'record_id' (1):
  → log_activity
```

---

## Edge Cases

### 1. Parameters without sources (workflow inputs)

```python
trace = inspector.trace_parameter("fetch_user", "user_id")

assert trace.source_node is None
assert trace.is_complete is True  # Complete, but no source
```

### 2. Cycles in parameter dependencies

```python
# Workflow with cycle: node_a → node_b → node_c → node_a
trace = inspector.trace_parameter("node_b", "input")

# DFS prevents infinite loops with visited set
assert trace is not None
assert trace.source_node is not None
```

### 3. Multiple paths to same parameter

```python
# Parameter flows through multiple paths
traces = inspector.parameter_flow("node_a", "output")

# BFS finds all paths
assert len(traces) >= 2
```

### 4. Dot notation with missing intermediate fields

```python
# Connection: data.user.email → email
trace = inspector.trace_parameter("create_user", "email")

assert trace.transformations[0]["type"] == "dot_notation"
assert "data.user.email" in trace.transformations[0]["details"]
```

### 5. Disconnected nodes

```python
# Node with no connections
deps = inspector.parameter_dependencies("isolated_node")

assert len(deps) == 0
```

---

## Interactive Mode

All parameter tracing methods are available in interactive mode:

```python
inspector.interactive()

# Interactive shell opens with:
# - inspector.trace_parameter('node_id', 'param_name')
# - inspector.parameter_flow('node_id', 'param_name')
# - inspector.find_parameter_source('node_id', 'param_name')
# - inspector.parameter_dependencies('node_id')
# - inspector.parameter_consumers('node_id', 'output_param')
```

---

## Performance Characteristics

| Method | Algorithm | Time Complexity | Use Case |
|--------|-----------|----------------|----------|
| `trace_parameter()` | DFS | O(N) | Single parameter backward trace |
| `parameter_flow()` | BFS | O(N + E) | All forward paths from parameter |
| `find_parameter_source()` | DFS (delegated) | O(N) | Quick source lookup |
| `parameter_dependencies()` | Multiple DFS | O(N * D) | All dependencies for node |
| `parameter_consumers()` | Linear scan | O(C) | Direct consumers only |

Where:
- N = Number of nodes
- E = Number of connections
- D = Number of dependencies
- C = Number of connections

---

## Testing

Comprehensive unit tests cover:
- ParameterTrace dataclass and show() method
- All 5 parameter tracing methods
- Edge cases (cycles, missing sources, disconnected nodes)
- Integration tests for complex workflows

**Run tests:**
```bash
pytest tests/unit/test_inspector_parameter_tracing.py -v
```

**Test coverage:**
- 32 tests
- All passing
- 100% method coverage

---

## Demo

Complete demo showing all parameter tracing methods:

```bash
PYTHONPATH=src:$PYTHONPATH python examples/inspector_parameter_tracing_demo.py
```

---

## Implementation Details

### File Structure

```
src/dataflow/platform/inspector.py
├── ParameterTrace dataclass (lines 315-420)
│   ├── Fields: parameter_name, source_node, transformations, etc.
│   └── show() method with flow visualization
│
└── Inspector class parameter tracing methods (lines 1128-1429)
    ├── trace_parameter() - DFS backward tracing
    ├── parameter_flow() - BFS forward tracing
    ├── find_parameter_source() - Simple source lookup
    ├── parameter_dependencies() - All dependencies map
    └── parameter_consumers() - Direct consumers list
```

### Key Design Decisions

1. **DFS for trace_parameter()**: Follows connections backward to find source
2. **BFS for parameter_flow()**: Explores all forward paths in breadth-first order
3. **Depth tracking**: Prevents workflow inputs from being treated as sources
4. **Transformation ordering**: Transformations inserted at beginning for correct order
5. **Cycle detection**: Visited set prevents infinite loops
6. **Consumer sorting**: Results sorted alphabetically for consistency

---

## Related Documentation

- [Inspector Connection Analysis](./inspector-connection-analysis.md)
- [Inspector Model & Node Methods](./inspector-model-node-methods.md)
- [Inspector Interactive Mode](./inspector-interactive-mode.md)

---

## Implementation Status

**Status**: ✅ Complete

**Completed**:
- ParameterTrace dataclass with rich show() method
- All 5 parameter tracing methods
- Comprehensive unit tests (32 tests, all passing)
- Complete demo with example workflow
- Full documentation

**File**: `src/dataflow/platform/inspector.py` (1480 lines)

**Tests**: `tests/unit/test_inspector_parameter_tracing.py` (500+ lines)

**Demo**: `examples/inspector_parameter_tracing_demo.py` (200+ lines)

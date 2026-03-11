# Inspector API Structure

**Visual reference for Inspector API extensions**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Inspector Class                           │
│                                                                  │
│  Existing Methods (Unchanged)          New Methods (Extensions) │
│  ├─ model()                            ├─ Connection Analysis   │
│  ├─ node()                             │  ├─ connections()      │
│  ├─ instance()                         │  ├─ connection_chain() │
│  ├─ workflow()                         │  ├─ connection_graph() │
│  └─ interactive()                      │  ├─ validate_connections() │
│                                        │  └─ find_broken_connections() │
│                                        │                         │
│                                        └─ Parameter Tracing      │
│                                           ├─ trace_parameter()   │
│                                           ├─ parameter_flow()    │
│                                           ├─ find_parameter_source() │
│                                           ├─ parameter_dependencies() │
│                                           └─ parameter_consumers() │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dataclass Hierarchy

```
Existing Dataclasses              New Dataclasses
├─ ModelInfo                      ├─ ConnectionInfo
├─ NodeInfo (enhanced)            │  ├─ source_node
├─ InstanceInfo                   │  ├─ source_param
└─ WorkflowInfo                   │  ├─ target_node
                                  │  ├─ target_param
                                  │  ├─ type_compatible
                                  │  └─ validation_errors
                                  │
                                  ├─ ParameterTrace
                                  │  ├─ source_node
                                  │  ├─ transformations: list[ConnectionInfo]
                                  │  ├─ destination_nodes
                                  │  ├─ total_hops
                                  │  └─ type_changes
                                  │
                                  └─ ConnectionGraph
                                     ├─ nodes
                                     ├─ connections: list[ConnectionInfo]
                                     ├─ entry_points
                                     ├─ exit_points
                                     ├─ adjacency_list
                                     └─ cyclic
```

---

## Method Categories

### 1. Connection Analysis Methods

**Purpose**: Analyze workflow topology and connections

```
connections()
    │
    ├─ Input: node_id (optional), direction (optional)
    ├─ Returns: list[ConnectionInfo]
    └─ Use: List all connections or filter by node

connection_chain()
    │
    ├─ Input: from_node, to_node, max_depth
    ├─ Returns: list[ConnectionInfo]
    └─ Use: Find path between nodes (BFS)

connection_graph()
    │
    ├─ Input: workflow (optional)
    ├─ Returns: ConnectionGraph
    └─ Use: Complete topology analysis

validate_connections()
    │
    ├─ Input: workflow (optional)
    ├─ Returns: dict[str, Any]
    └─ Use: Comprehensive validation report

find_broken_connections()
    │
    ├─ Input: workflow (optional)
    ├─ Returns: list[ConnectionInfo]
    └─ Use: Quick health check
```

### 2. Parameter Tracing Methods

**Purpose**: Track parameter flow and dependencies

```
trace_parameter()
    │
    ├─ Input: node_id, parameter_name, direction
    ├─ Returns: ParameterTrace
    └─ Use: Complete parameter flow analysis

parameter_flow()
    │
    ├─ Input: from_node, parameter, max_depth
    ├─ Returns: list[dict[str, Any]]
    └─ Use: Step-by-step flow visualization

find_parameter_source()
    │
    ├─ Input: node_id, parameter
    ├─ Returns: dict[str, Any]
    └─ Use: Find parameter origin

parameter_dependencies()
    │
    ├─ Input: node_id, include_sources
    ├─ Returns: dict[str, list[str]]
    └─ Use: List all dependencies

parameter_consumers()
    │
    ├─ Input: node_id, output_param
    ├─ Returns: list[dict[str, str]]
    └─ Use: List all consumers
```

---

## Data Flow Diagram

### Connection Analysis Flow

```
WorkflowBuilder
    │
    ├─ .connections ────────┐
    │                       │
    ├─ .nodes ──────────────┤
    │                       ▼
    └─ .parameter_mappings  Inspector
                               │
                               ├─ Extract connections
                               ├─ Build graph structure
                               ├─ Validate connections
                               │
                               ▼
                        ConnectionInfo
                        ConnectionGraph
```

### Parameter Tracing Flow

```
Node
 ├─ .get_parameters() ────┐
 │                        │
 └─ outputs ──────────────┤
                          ▼
WorkflowBuilder          Inspector
 ├─ .connections ────┐      │
 │                   └─────►├─ Trace parameter
 └─ .nodes ─────────────────┤  flow (DFS/BFS)
                            │
                            ▼
                     ParameterTrace
```

---

## Algorithm Overview

### BFS for connection_chain()

```
Input: from_node, to_node
Output: list[ConnectionInfo] (shortest path)

1. Initialize queue with from_node
2. Track visited nodes
3. While queue not empty:
   a. Dequeue node
   b. If node == to_node: reconstruct path, return
   c. For each outgoing connection:
      - Enqueue target node
      - Track parent for path reconstruction
4. Return empty list (no path found)

Time: O(V + E)
Space: O(V)
```

### DFS for trace_parameter()

```
Input: node_id, parameter_name, direction
Output: ParameterTrace

Forward trace:
1. Find all outgoing connections from parameter
2. For each connection:
   a. Track transformation
   b. Recursively trace from target node
3. Collect all destinations

Backward trace:
1. Find all incoming connections to parameter
2. For each connection:
   a. Track transformation
   b. Recursively trace to source node
3. Find original source

Time: O(V + E)
Space: O(V) for visited tracking
```

### Topology Analysis for connection_graph()

```
Input: workflow
Output: ConnectionGraph

1. Build adjacency lists (forward + reverse)
2. Find entry points (no incoming)
3. Find exit points (no outgoing)
4. Find isolated nodes (no connections)
5. Calculate max depth (DFS from entry points)
6. Detect cycles (DFS with recursion stack)
7. Calculate statistics

Time: O(V + E)
Space: O(V + E) for adjacency lists
```

---

## Type Information Flow

```
Source Priority (highest to lowest):

1. Node.get_parameters()
   ├─ Explicitly declared types
   └─ Required/optional flags

2. Python Type Hints
   ├─ Function signatures
   └─ Class attributes

3. DataFlow Model Fields
   ├─ @db.model field types
   └─ SQLAlchemy column types

4. Runtime Inspection
   ├─ Value type at execution
   └─ Fallback when no static info

Type Compatibility Check:
├─ Exact match: str == str ✓
├─ Subtype match: dict ⊆ Mapping ✓
├─ Union types: str | None ⊇ str ✓
└─ Mismatch: str ≠ int ✗
```

---

## Error Handling Strategy

```
Method Behavior on Errors:

connections()
├─ Invalid node_id → return empty list
├─ Invalid direction → raise ValueError
└─ No connections → return empty list

connection_chain()
├─ Invalid from_node → raise ValueError
├─ Invalid to_node → raise ValueError
├─ No path exists → return empty list
└─ Cycle detected → enforce max_depth

trace_parameter()
├─ Invalid node_id → raise ValueError
├─ Invalid parameter → return ParameterTrace with is_complete=False
└─ Cycle detected → enforce max_depth

validate_connections()
├─ Always returns dict (never raises)
├─ Validation errors in 'issues' list
└─ Statistics always populated

find_broken_connections()
├─ Always returns list (never raises)
├─ Empty list if all valid
└─ ConnectionInfo.validation_errors populated
```

---

## Performance Characteristics

| Method | Time Complexity | Space Complexity | Notes |
|--------|----------------|------------------|-------|
| `connections()` | O(E) | O(E) | Linear scan of connections |
| `connection_chain()` | O(V + E) | O(V) | BFS traversal |
| `connection_graph()` | O(V + E) | O(V + E) | Full graph analysis |
| `validate_connections()` | O(V + E) | O(E) | Validate all connections |
| `find_broken_connections()` | O(V + E) | O(E) | Filter invalid connections |
| `trace_parameter()` | O(V + E) | O(V) | DFS traversal |
| `parameter_flow()` | O(V + E) | O(V) | Iterative path following |
| `find_parameter_source()` | O(V + E) | O(V) | Backward BFS |
| `parameter_dependencies()` | O(E) | O(E) | Filter incoming connections |
| `parameter_consumers()` | O(E) | O(E) | Filter outgoing connections |

**V** = Number of nodes
**E** = Number of connections

**Expected Performance**:
- Workflows with <50 nodes: <10ms per method
- Workflows with <100 nodes: <50ms per method
- Workflows with >100 nodes: May exceed 100ms for graph methods

---

## Integration Points

```
Inspector <─────> WorkflowBuilder
    │                  │
    │                  ├─ connections: list[dict]
    │                  ├─ nodes: dict[str, dict]
    │                  └─ parameter_mappings: dict
    │
    ├─────> Node
    │         ├─ get_parameters()
    │         └─ output declarations
    │
    ├─────> DataFlow
    │         ├─ _models
    │         └─ model schemas
    │
    └─────> Runtime (optional)
              └─ execution results
```

---

## Testing Strategy

### Unit Tests

```
Dataclasses
├─ ConnectionInfo
│  ├─ Creation with all fields
│  ├─ .show() formatting
│  └─ Serialization/deserialization
│
├─ ParameterTrace
│  ├─ Creation with transformations
│  ├─ .show() formatting
│  └─ Type change tracking
│
└─ ConnectionGraph
   ├─ Graph statistics
   ├─ .show() formatting
   └─ Cycle detection

Methods (each method)
├─ Normal operation
├─ Empty workflow
├─ Invalid inputs
├─ Edge cases
└─ Performance (large workflows)
```

### Integration Tests

```
Real Workflows
├─ Simple linear workflow (3 nodes)
├─ Branching workflow (5 nodes)
├─ Cyclic workflow (with cycles)
└─ Large workflow (50+ nodes)

Backward Compatibility
├─ Existing model() method
├─ Existing node() method
├─ Existing instance() method
└─ Existing workflow() method

Error Scenarios
├─ Broken connections
├─ Type mismatches
├─ Missing nodes
└─ Invalid parameters
```

---

## Usage Patterns

### Pattern 1: Pre-Execution Validation

```python
inspector = Inspector(studio)

# Quick validation
broken = inspector.find_broken_connections()
if broken:
    print(f"❌ {len(broken)} broken connections")
    sys.exit(1)

# Detailed validation
report = inspector.validate_connections()
if report['broken'] > 0:
    for issue in report['issues']:
        print(f"❌ {issue['message']}")
    sys.exit(1)

# Safe to execute
results = runtime.execute(workflow.build())
```

### Pattern 2: Debug Parameter Flow

```python
# Where does parameter go?
trace = inspector.trace_parameter("input", "user_id")
print(f"Flows to: {trace.destination_nodes}")

# Where does parameter come from?
source = inspector.find_parameter_source("output", "result")
print(f"Originates from: {source['node']}")

# Who depends on this node?
deps = inspector.parameter_dependencies("processor")
for param, sources in deps.items():
    print(f"{param}: {sources}")
```

### Pattern 3: Topology Analysis

```python
# Analyze structure
graph = inspector.connection_graph()
print(f"Cyclic: {graph.cyclic}")
print(f"Max depth: {graph.max_depth}")

# Find issues
if graph.isolated_nodes:
    print(f"Isolated: {graph.isolated_nodes}")

# Check connectivity
chain = inspector.connection_chain("input", "output")
if not chain:
    print("No connection path!")
```

---

## Visual Connection Example

```
Workflow:
    input_node
        │ user_id (str)
        ├──────────────┐
        ▼              ▼
    processor      logger
        │ processed_id (str)
        ▼
    formatter
        │ final_result (dict)
        ▼
    output_node

Inspector API:

1. connections("processor")
   Returns:
   - input_node.user_id → processor.user_id
   - processor.processed_id → formatter.input_data

2. connection_chain("input_node", "output_node")
   Returns:
   - input_node.user_id → processor.user_id
   - processor.processed_id → formatter.input_data
   - formatter.final_result → output_node.result

3. trace_parameter("input_node", "user_id")
   Returns:
   - Source: input_node.user_id
   - Destinations: [processor, logger]
   - Total hops: 2

4. parameter_consumers("input_node", "user_id")
   Returns:
   - processor.user_id
   - logger.id
```

---

**End of Visual Reference**

**Full Design**: [inspector-api-extensions-design.md](./inspector-api-extensions-design.md)
**Summary**: [inspector-api-design-summary.md](./inspector-api-design-summary.md)

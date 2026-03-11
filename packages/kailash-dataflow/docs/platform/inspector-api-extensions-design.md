# Inspector API Extensions - Design Document

**Version**: 1.0
**Date**: 2025-11-01
**Status**: Design Phase

## Executive Summary

This document specifies API extensions for the DataFlow Inspector to support **connection analysis** and **parameter tracing** capabilities. The extensions maintain backward compatibility while adding production-grade debugging features for workflow introspection.

---

## Design Goals

1. **Backward Compatibility**: All existing Inspector methods (`model()`, `node()`, `instance()`, `workflow()`) remain unchanged
2. **Consistent API**: New methods follow same patterns as existing methods (return dataclasses, support `.show()`)
3. **Production-Ready**: Designed for real-time debugging, not just static analysis
4. **Zero Dependencies**: Uses only stdlib and existing Kailash SDK infrastructure
5. **Type-Safe**: Full type hints with modern Python typing

---

## New Dataclasses

### ConnectionInfo

Represents a single connection between two nodes.

```python
from dataclasses import dataclass, field
from typing import Optional, Any

@dataclass
class ConnectionInfo:
    """Information about a workflow connection."""

    # Connection identity
    source_node: str              # Source node ID
    source_param: str             # Source parameter name
    target_node: str              # Target node ID
    target_param: str             # Target parameter name

    # Type information
    source_type: Optional[str] = None   # Inferred source type (e.g., "str", "dict", "List[str]")
    target_type: Optional[str] = None   # Expected target type
    type_compatible: bool = True        # Whether types are compatible

    # Connection metadata
    connection_id: str = field(default_factory=lambda: f"conn_{uuid.uuid4().hex[:8]}")
    is_valid: bool = True               # Whether connection exists and is valid
    validation_errors: list[str] = field(default_factory=list)

    # Navigation helpers
    chain_position: Optional[int] = None  # Position in connection chain (if part of trace)
    depth: int = 0                        # Depth from starting node (for graph traversal)

    def show(self, color: bool = True) -> str:
        """Format connection information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []

        # Connection path
        status_color = GREEN if self.is_valid else RED
        parts.append(f"{status_color}{BOLD}Connection: {self.connection_id}{RESET}")
        parts.append(f"{self.source_node}.{self.source_param} → {self.target_node}.{self.target_param}")
        parts.append("")

        # Type information
        if self.source_type or self.target_type:
            parts.append(f"{BLUE}Type Information:{RESET}")
            if self.source_type:
                parts.append(f"  Source type: {self.source_type}")
            if self.target_type:
                parts.append(f"  Target type: {self.target_type}")

            type_color = GREEN if self.type_compatible else RED
            parts.append(f"  Compatible: {type_color}{self.type_compatible}{RESET}")
            parts.append("")

        # Validation errors
        if self.validation_errors:
            parts.append(f"{YELLOW}Validation Issues:{RESET}")
            for error in self.validation_errors:
                parts.append(f"  - {error}")
            parts.append("")

        # Chain position (if part of trace)
        if self.chain_position is not None:
            parts.append(f"Chain Position: {self.chain_position}")
            parts.append(f"Depth: {self.depth}")

        return "\n".join(parts)
```

### ParameterTrace

Represents the complete flow of a parameter through the workflow.

```python
@dataclass
class ParameterTrace:
    """Trace of a parameter through the workflow."""

    # Trace identity
    parameter_name: str           # Original parameter name
    trace_id: str = field(default_factory=lambda: f"trace_{uuid.uuid4().hex[:8]}")

    # Source information
    source_node: str              # Node where parameter originates
    source_param: str             # Original output parameter name
    source_type: Optional[str] = None  # Original type

    # Flow path
    transformations: list[ConnectionInfo] = field(default_factory=list)
    intermediate_nodes: list[str] = field(default_factory=list)

    # Destination information
    destination_nodes: list[str] = field(default_factory=list)  # All nodes consuming this parameter
    destination_params: dict[str, str] = field(default_factory=dict)  # node_id -> param_name
    final_types: dict[str, str] = field(default_factory=dict)  # node_id -> expected_type

    # Trace metadata
    total_hops: int = 0           # Number of connections traversed
    type_changes: list[dict[str, Any]] = field(default_factory=list)  # Type transformations
    is_complete: bool = True      # Whether trace reached all destinations
    trace_errors: list[str] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format parameter trace for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Parameter Trace: {self.parameter_name}{RESET}")
        parts.append(f"Trace ID: {self.trace_id}")
        parts.append("")

        # Source
        parts.append(f"{GREEN}Source:{RESET}")
        parts.append(f"  Node: {self.source_node}")
        parts.append(f"  Parameter: {self.source_param}")
        if self.source_type:
            parts.append(f"  Type: {self.source_type}")
        parts.append("")

        # Flow path
        if self.transformations:
            parts.append(f"{GREEN}Flow Path ({self.total_hops} hops):{RESET}")
            for i, conn in enumerate(self.transformations, 1):
                parts.append(f"  {i}. {conn.source_node}.{conn.source_param} → {conn.target_node}.{conn.target_param}")
            parts.append("")

        # Destinations
        if self.destination_nodes:
            parts.append(f"{GREEN}Destinations ({len(self.destination_nodes)}):{RESET}")
            for node_id in self.destination_nodes:
                param_name = self.destination_params.get(node_id, "unknown")
                final_type = self.final_types.get(node_id, "unknown")
                parts.append(f"  - {node_id}.{param_name} ({final_type})")
            parts.append("")

        # Type changes
        if self.type_changes:
            parts.append(f"{YELLOW}Type Transformations:{RESET}")
            for change in self.type_changes:
                parts.append(f"  {change['from_type']} → {change['to_type']} at {change['node']}")
            parts.append("")

        # Errors
        if self.trace_errors:
            parts.append(f"{YELLOW}Trace Errors:{RESET}")
            for error in self.trace_errors:
                parts.append(f"  - {error}")

        return "\n".join(parts)
```

### ConnectionGraph

Represents the complete connection topology of a workflow.

```python
@dataclass
class ConnectionGraph:
    """Complete connection graph of a workflow."""

    # Graph identity
    workflow_id: str
    graph_id: str = field(default_factory=lambda: f"graph_{uuid.uuid4().hex[:8]}")

    # Graph structure
    nodes: list[str] = field(default_factory=list)  # All node IDs
    connections: list[ConnectionInfo] = field(default_factory=list)

    # Topology analysis
    entry_points: list[str] = field(default_factory=list)  # Nodes with no incoming connections
    exit_points: list[str] = field(default_factory=list)   # Nodes with no outgoing connections
    isolated_nodes: list[str] = field(default_factory=list)  # Nodes with no connections

    # Connection statistics
    total_connections: int = 0
    valid_connections: int = 0
    broken_connections: int = 0

    # Complexity metrics
    max_depth: int = 0            # Longest path from entry to exit
    avg_connections_per_node: float = 0.0
    cyclic: bool = False          # Whether graph contains cycles

    # Adjacency information
    adjacency_list: dict[str, list[str]] = field(default_factory=dict)  # node_id -> [connected_node_ids]
    reverse_adjacency: dict[str, list[str]] = field(default_factory=dict)  # node_id -> [nodes_that_connect_to_it]

    def show(self, color: bool = True) -> str:
        """Format connection graph for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Connection Graph: {self.workflow_id}{RESET}")
        parts.append(f"Graph ID: {self.graph_id}")
        parts.append("")

        # Statistics
        parts.append(f"{GREEN}Statistics:{RESET}")
        parts.append(f"  Total nodes: {len(self.nodes)}")
        parts.append(f"  Total connections: {self.total_connections}")
        parts.append(f"  Valid: {self.valid_connections}")
        parts.append(f"  Broken: {self.broken_connections}")
        parts.append(f"  Avg connections/node: {self.avg_connections_per_node:.2f}")
        parts.append(f"  Max depth: {self.max_depth}")
        parts.append(f"  Cyclic: {self.cyclic}")
        parts.append("")

        # Topology
        parts.append(f"{GREEN}Topology:{RESET}")
        if self.entry_points:
            parts.append(f"  Entry points ({len(self.entry_points)}): {', '.join(self.entry_points)}")
        if self.exit_points:
            parts.append(f"  Exit points ({len(self.exit_points)}): {', '.join(self.exit_points)}")
        if self.isolated_nodes:
            parts.append(f"  {YELLOW}Isolated nodes ({len(self.isolated_nodes)}): {', '.join(self.isolated_nodes)}{RESET}")
        parts.append("")

        # Connection summary
        if self.broken_connections > 0:
            parts.append(f"{RED}⚠️  {self.broken_connections} broken connections detected{RESET}")

        return "\n".join(parts)
```

---

## New Inspector Methods

### Connection Analysis Methods

#### 1. `connections(node_id: Optional[str] = None) -> list[ConnectionInfo]`

List all connections, optionally filtered by node.

```python
def connections(
    self,
    node_id: Optional[str] = None,
    direction: Optional[str] = None  # "incoming", "outgoing", or None (both)
) -> list[ConnectionInfo]:
    """
    Get connection information for workflow.

    Args:
        node_id: Optional node ID to filter connections
        direction: Optional direction filter ("incoming", "outgoing", None)

    Returns:
        List of ConnectionInfo instances

    Example:
        >>> # Get all connections
        >>> all_conns = inspector.connections()
        >>> print(f"Total connections: {len(all_conns)}")

        >>> # Get connections for specific node
        >>> user_conns = inspector.connections("user_create")
        >>> for conn in user_conns:
        >>>     print(conn.show())

        >>> # Get only incoming connections
        >>> incoming = inspector.connections("user_create", direction="incoming")
        >>> print(f"Incoming: {len(incoming)}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
- If `node_id=None`: Returns all connections in workflow
- If `node_id` specified: Returns connections where node is source or target
- If `direction` specified: Filters to only incoming/outgoing connections

**Use Cases**:
- Inspect all workflow connections
- Debug specific node's data flow
- Validate connection setup

---

#### 2. `connection_chain(from_node: str, to_node: str) -> list[ConnectionInfo]`

Trace connection path between two nodes.

```python
def connection_chain(
    self,
    from_node: str,
    to_node: str,
    max_depth: int = 10
) -> list[ConnectionInfo]:
    """
    Trace connection path from source node to target node.

    Args:
        from_node: Source node ID
        to_node: Target node ID
        max_depth: Maximum traversal depth (prevents infinite loops)

    Returns:
        List of ConnectionInfo instances representing the path
        Empty list if no path exists

    Example:
        >>> # Find path from input to output
        >>> chain = inspector.connection_chain("input_node", "output_node")
        >>> print(f"Path length: {len(chain)} hops")
        >>> for i, conn in enumerate(chain, 1):
        >>>     print(f"Hop {i}: {conn.source_node} → {conn.target_node}")

        >>> # Check if path exists
        >>> if not chain:
        >>>     print("No connection path found!")
    """
    pass  # Implementation in next phase
```

**Algorithm**:
- Breadth-first search (BFS) from `from_node` to `to_node`
- Returns shortest path if multiple paths exist
- Detects cycles and enforces `max_depth`

**Return Structure**:
- Ordered list of ConnectionInfo with `chain_position` set
- Each connection has `depth` indicating distance from `from_node`

**Use Cases**:
- Verify data flow path between nodes
- Debug broken connections
- Understand complex workflow topology

---

#### 3. `connection_graph() -> ConnectionGraph`

Get complete connection graph analysis.

```python
def connection_graph(
    self,
    workflow: Optional[Any] = None
) -> ConnectionGraph:
    """
    Get complete connection graph analysis for workflow.

    Args:
        workflow: Optional WorkflowBuilder instance. If None, analyzes current studio workflow.

    Returns:
        ConnectionGraph instance with topology analysis

    Example:
        >>> # Analyze workflow structure
        >>> graph = inspector.connection_graph()
        >>> print(graph.show())

        >>> # Check for isolated nodes
        >>> if graph.isolated_nodes:
        >>>     print(f"Warning: {len(graph.isolated_nodes)} isolated nodes")
        >>>     for node_id in graph.isolated_nodes:
        >>>         print(f"  - {node_id}")

        >>> # Check for cycles
        >>> if graph.cyclic:
        >>>     print("Workflow contains cycles")

        >>> # Find entry/exit points
        >>> print(f"Entry points: {graph.entry_points}")
        >>> print(f"Exit points: {graph.exit_points}")
    """
    pass  # Implementation in next phase
```

**Analysis Performed**:
1. Build adjacency lists (forward and reverse)
2. Identify entry points (no incoming connections)
3. Identify exit points (no outgoing connections)
4. Detect isolated nodes (no connections)
5. Calculate max depth (longest path)
6. Detect cycles using DFS
7. Calculate connection statistics

**Return Structure**:
- Complete `ConnectionGraph` with all topology analysis
- Adjacency lists for graph traversal algorithms
- Metrics for complexity assessment

**Use Cases**:
- Validate workflow structure
- Detect topology issues (isolated nodes, missing connections)
- Understand workflow complexity

---

#### 4. `validate_connections() -> dict[str, Any]`

Comprehensive connection validation.

```python
def validate_connections(
    self,
    workflow: Optional[Any] = None
) -> dict[str, Any]:
    """
    Validate all connections in workflow.

    Args:
        workflow: Optional WorkflowBuilder instance

    Returns:
        Validation report with issues and statistics

    Example:
        >>> # Validate all connections
        >>> report = inspector.validate_connections()
        >>> print(f"Total connections: {report['total']}")
        >>> print(f"Valid: {report['valid']}")
        >>> print(f"Broken: {report['broken']}")

        >>> # Show validation errors
        >>> for issue in report['issues']:
        >>>     print(f"❌ {issue['type']}: {issue['message']}")
        >>>     print(f"   Location: {issue['location']}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
```python
{
    "total": 15,           # Total connections
    "valid": 13,           # Valid connections
    "broken": 2,           # Broken connections
    "issues": [            # List of validation issues
        {
            "type": "missing_source_param",
            "severity": "error",
            "message": "Source parameter 'output' not found in node 'processor'",
            "location": "processor → formatter",
            "connection": ConnectionInfo(...)
        }
    ],
    "statistics": {
        "type_mismatches": 0,
        "missing_nodes": 0,
        "missing_params": 2,
        "circular_references": 0
    }
}
```

**Validation Checks**:
1. Source node exists
2. Target node exists
3. Source parameter exists in source node outputs
4. Target parameter exists in target node inputs
5. Type compatibility (if type info available)
6. Circular dependency detection

**Use Cases**:
- Pre-execution validation
- Debug workflow setup issues
- CI/CD validation

---

#### 5. `find_broken_connections() -> list[ConnectionInfo]`

Quickly identify invalid connections.

```python
def find_broken_connections(
    self,
    workflow: Optional[Any] = None
) -> list[ConnectionInfo]:
    """
    Find all broken or invalid connections.

    Args:
        workflow: Optional WorkflowBuilder instance

    Returns:
        List of ConnectionInfo instances for broken connections

    Example:
        >>> # Find broken connections
        >>> broken = inspector.find_broken_connections()
        >>> if broken:
        >>>     print(f"Found {len(broken)} broken connections:")
        >>>     for conn in broken:
        >>>         print(conn.show())
        >>>         for error in conn.validation_errors:
        >>>             print(f"  - {error}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
- List of `ConnectionInfo` with `is_valid=False`
- Each connection has `validation_errors` populated

**Use Cases**:
- Quick health check
- Debug broken workflows
- Pre-execution validation

---

### Parameter Tracing Methods

#### 1. `trace_parameter(node_id: str, parameter_name: str) -> ParameterTrace`

Trace a parameter's flow through the workflow.

```python
def trace_parameter(
    self,
    node_id: str,
    parameter_name: str,
    direction: str = "both"  # "forward", "backward", or "both"
) -> ParameterTrace:
    """
    Trace a parameter's flow through the workflow.

    Args:
        node_id: Node ID to start trace from
        parameter_name: Parameter name to trace
        direction: Trace direction ("forward", "backward", "both")

    Returns:
        ParameterTrace instance with complete flow path

    Example:
        >>> # Trace where user_id flows
        >>> trace = inspector.trace_parameter("user_create", "user_id")
        >>> print(trace.show())
        >>> print(f"Used by {len(trace.destination_nodes)} nodes")

        >>> # Backward trace to find source
        >>> trace = inspector.trace_parameter("final_node", "result", direction="backward")
        >>> print(f"Originates from: {trace.source_node}")
    """
    pass  # Implementation in next phase
```

**Algorithm**:
- **Forward trace**: Follow outgoing connections from parameter
- **Backward trace**: Follow incoming connections to find source
- **Both**: Combines forward and backward traces

**Return Structure**:
- Complete `ParameterTrace` with all flow information
- Includes type transformations if detectable
- Marks incomplete traces with `is_complete=False`

**Use Cases**:
- Debug parameter flow issues
- Understand data transformations
- Verify parameter propagation

---

#### 2. `parameter_flow(from_node: str, parameter: str) -> list[dict[str, Any]]`

Show parameter flow from a starting node.

```python
def parameter_flow(
    self,
    from_node: str,
    parameter: str,
    max_depth: int = 10
) -> list[dict[str, Any]]:
    """
    Show how a parameter flows through the workflow.

    Args:
        from_node: Starting node ID
        parameter: Parameter name
        max_depth: Maximum traversal depth

    Returns:
        List of flow steps with transformation information

    Example:
        >>> # Track user_id flow
        >>> flow = inspector.parameter_flow("input", "user_id")
        >>> for step in flow:
        >>>     print(f"{step['node']}: {step['param_in']} → {step['param_out']}")
        >>>     if step['transformed']:
        >>>         print(f"  Transformed: {step['transformation']}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
```python
[
    {
        "step": 1,
        "node": "input",
        "param_in": None,        # No incoming (source node)
        "param_out": "user_id",
        "type_in": None,
        "type_out": "str",
        "transformed": False,
        "transformation": None
    },
    {
        "step": 2,
        "node": "processor",
        "param_in": "user_id",
        "param_out": "processed_id",
        "type_in": "str",
        "type_out": "str",
        "transformed": True,
        "transformation": "renamed"
    }
]
```

**Use Cases**:
- Visual parameter flow tracking
- Debug transformations
- Documentation generation

---

#### 3. `find_parameter_source(node_id: str, parameter: str) -> dict[str, Any]`

Find the origin of a parameter.

```python
def find_parameter_source(
    self,
    node_id: str,
    parameter: str
) -> dict[str, Any]:
    """
    Find where a parameter originates from.

    Args:
        node_id: Node ID consuming the parameter
        parameter: Parameter name

    Returns:
        Source information dictionary

    Example:
        >>> # Find where 'result' comes from
        >>> source = inspector.find_parameter_source("output_node", "result")
        >>> print(f"Source: {source['node']}.{source['parameter']}")
        >>> print(f"Hops: {source['hops']}")
        >>> print(f"Path: {' → '.join(source['path'])}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
```python
{
    "found": True,
    "node": "processor",           # Source node ID
    "parameter": "output",         # Source parameter name
    "type": "dict",                # Source type (if known)
    "hops": 3,                     # Number of connections traversed
    "path": [                      # Full path
        "processor",
        "transformer",
        "formatter",
        "output_node"
    ],
    "connections": [               # Connection chain
        ConnectionInfo(...),
        ConnectionInfo(...),
        ConnectionInfo(...)
    ]
}
```

**Use Cases**:
- Debug missing parameters
- Understand parameter origins
- Validate data sources

---

#### 4. `parameter_dependencies(node_id: str) -> dict[str, list[str]]`

List all parameters a node depends on.

```python
def parameter_dependencies(
    self,
    node_id: str,
    include_sources: bool = True
) -> dict[str, list[str]]:
    """
    List all parameters a node depends on.

    Args:
        node_id: Node ID to analyze
        include_sources: Whether to include source node information

    Returns:
        Dictionary mapping parameter names to source information

    Example:
        >>> # Get all dependencies
        >>> deps = inspector.parameter_dependencies("formatter")
        >>> print(f"Node 'formatter' depends on:")
        >>> for param, sources in deps.items():
        >>>     print(f"  {param}: from {', '.join(sources)}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
```python
{
    "user_id": ["input.user_id"],              # Direct connection
    "user_data": [                             # Multiple sources
        "user_fetch.result",
        "cache.cached_data"
    ],
    "config": ["config_node.settings"]
}
```

**Use Cases**:
- Understand node dependencies
- Identify missing inputs
- Plan workflow modifications

---

#### 5. `parameter_consumers(node_id: str, output_param: str) -> list[dict[str, str]]`

List nodes consuming a parameter.

```python
def parameter_consumers(
    self,
    node_id: str,
    output_param: str
) -> list[dict[str, str]]:
    """
    List all nodes consuming an output parameter.

    Args:
        node_id: Source node ID
        output_param: Output parameter name

    Returns:
        List of consumer information dictionaries

    Example:
        >>> # Find who uses 'user_id'
        >>> consumers = inspector.parameter_consumers("input", "user_id")
        >>> print(f"Parameter 'user_id' consumed by:")
        >>> for consumer in consumers:
        >>>     print(f"  {consumer['node']}.{consumer['parameter']}")
    """
    pass  # Implementation in next phase
```

**Return Structure**:
```python
[
    {
        "node": "processor",
        "parameter": "user_id",
        "type": "str",
        "required": True
    },
    {
        "node": "logger",
        "parameter": "id",
        "type": "str",
        "required": False
    }
]
```

**Use Cases**:
- Impact analysis before changes
- Find unused outputs
- Validate parameter usage

---

## Integration with Existing Inspector

### Backward Compatibility

All existing methods remain unchanged:
- `model(model_name: str) -> ModelInfo`
- `node(node_id: str) -> NodeInfo`
- `instance() -> InstanceInfo`
- `workflow(workflow: Any) -> WorkflowInfo`
- `interactive()`

### Enhanced NodeInfo

Existing `NodeInfo` dataclass will be **extended** (not modified) to include connection information:

```python
@dataclass
class NodeInfo:
    """Information about a specific DataFlow node."""

    # EXISTING FIELDS (unchanged)
    node_id: str
    node_type: str
    model_name: str
    expected_params: dict[str, Any]
    output_params: dict[str, Any]
    connections_in: list[dict[str, str]] = field(default_factory=list)
    connections_out: list[dict[str, str]] = field(default_factory=list)
    usage_example: str = ""

    # NEW FIELDS (optional, default to empty)
    connection_details: list[ConnectionInfo] = field(default_factory=list)  # Full ConnectionInfo objects
    parameter_traces: dict[str, ParameterTrace] = field(default_factory=dict)  # param_name -> trace
```

This maintains backward compatibility while allowing richer information when needed.

---

## Usage Examples

### Example 1: Debug Broken Connection

```python
from dataflow.platform.inspector import Inspector

inspector = Inspector(studio)

# Find broken connections
broken = inspector.find_broken_connections()
if broken:
    print(f"❌ Found {len(broken)} broken connections:")
    for conn in broken:
        print(conn.show())
        print("Errors:")
        for error in conn.validation_errors:
            print(f"  - {error}")
```

### Example 2: Trace Parameter Flow

```python
# Trace where 'user_id' flows
trace = inspector.trace_parameter("input_node", "user_id")
print(trace.show())

# Check destinations
print(f"\nParameter 'user_id' flows to:")
for node_id in trace.destination_nodes:
    param = trace.destination_params[node_id]
    print(f"  - {node_id}.{param}")
```

### Example 3: Analyze Workflow Topology

```python
# Get connection graph
graph = inspector.connection_graph()
print(graph.show())

# Check for issues
if graph.isolated_nodes:
    print("\n⚠️  Warning: Isolated nodes detected:")
    for node_id in graph.isolated_nodes:
        print(f"  - {node_id}")

if graph.cyclic:
    print("\n⚠️  Warning: Workflow contains cycles")
```

### Example 4: Validate Before Execution

```python
# Comprehensive validation
report = inspector.validate_connections()

if report['broken'] > 0:
    print(f"❌ {report['broken']} broken connections - cannot execute")
    for issue in report['issues']:
        print(f"  {issue['type']}: {issue['message']}")
        print(f"  Location: {issue['location']}")
else:
    print(f"✅ All {report['total']} connections valid")
    # Safe to execute
    results = runtime.execute(workflow.build())
```

### Example 5: Find Connection Path

```python
# Find path between nodes
chain = inspector.connection_chain("input_node", "output_node")

if not chain:
    print("❌ No connection path found")
else:
    print(f"✅ Found path with {len(chain)} hops:")
    for i, conn in enumerate(chain, 1):
        print(f"  {i}. {conn.source_node}.{conn.source_param} → {conn.target_node}.{conn.target_param}")
```

---

## Implementation Notes

### Data Sources

Connection and parameter information will be extracted from:

1. **WorkflowBuilder.connections**: List of connection dictionaries
   ```python
   [
       {
           "source": "node1",
           "source_param": "output",
           "target": "node2",
           "target_param": "input"
       }
   ]
   ```

2. **WorkflowBuilder.nodes**: Node configuration dictionaries
   ```python
   {
       "node_id": {
           "type": "UserCreateNode",
           "config": {...},
           "instance": node_instance
       }
   }
   ```

3. **Node.get_parameters()**: Parameter declarations from nodes
   ```python
   {
       "user_id": {"required": True, "type": "str"},
       "name": {"required": True, "type": "str"}
   }
   ```

### Type Inference

Type information will be inferred from:
1. Node parameter declarations (`get_parameters()`)
2. Python type hints (if available)
3. DataFlow model field types (for DataFlow nodes)
4. Runtime value inspection (when instances available)

### Performance Considerations

- **Lazy evaluation**: Graph analysis performed on-demand, not cached
- **Memoization**: Results cached during inspector session for repeat queries
- **Max depth limits**: Prevent infinite loops in cyclic workflows
- **BFS for shortest paths**: Efficient pathfinding algorithm

---

## Testing Strategy

### Unit Tests

1. **Dataclass validation**
   - ConnectionInfo creation and serialization
   - ParameterTrace creation and serialization
   - ConnectionGraph creation and serialization

2. **Method signatures**
   - All new methods have correct signatures
   - Type hints are accurate
   - Default parameters work correctly

3. **Edge cases**
   - Empty workflows
   - Single-node workflows
   - Disconnected nodes
   - Cyclic workflows

### Integration Tests

1. **Real workflow analysis**
   - Test with actual DataFlow workflows
   - Validate connection detection
   - Verify parameter tracing

2. **Backward compatibility**
   - Existing Inspector methods still work
   - Enhanced NodeInfo compatible with old code

3. **Error handling**
   - Invalid node IDs
   - Missing connections
   - Type mismatches

---

## Documentation Requirements

1. **API Reference**: Complete docstrings for all methods
2. **User Guide**: Step-by-step examples for each use case
3. **Troubleshooting Guide**: Common issues and solutions
4. **Migration Guide**: How to use new features with existing code

---

## Next Steps

### Phase 1: Implementation (Task 1.2)
- Implement all 10 new methods
- Add comprehensive docstrings
- Handle edge cases

### Phase 2: Testing (Task 1.3)
- Write unit tests for all methods
- Integration tests with real workflows
- Performance benchmarks

### Phase 3: Documentation (Task 1.4)
- Complete API reference
- User guide with examples
- Update main Inspector README

---

## Appendix: Method Summary

| Method | Returns | Purpose |
|--------|---------|---------|
| `connections()` | `list[ConnectionInfo]` | List all/filtered connections |
| `connection_chain()` | `list[ConnectionInfo]` | Trace path between nodes |
| `connection_graph()` | `ConnectionGraph` | Complete topology analysis |
| `validate_connections()` | `dict[str, Any]` | Comprehensive validation |
| `find_broken_connections()` | `list[ConnectionInfo]` | Quick health check |
| `trace_parameter()` | `ParameterTrace` | Complete parameter flow |
| `parameter_flow()` | `list[dict]` | Step-by-step flow |
| `find_parameter_source()` | `dict[str, Any]` | Find parameter origin |
| `parameter_dependencies()` | `dict[str, list[str]]` | List dependencies |
| `parameter_consumers()` | `list[dict]` | List consumers |

---

**End of Design Document**

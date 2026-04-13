# Kailash Core SDK — Workflow Construction & Connections

Version: 2.8.5
Status: Authoritative domain truth document
Parent domain: Core SDK (split from `core-sdk.md` per specs-authority Rule 8)
Scope: WorkflowBuilder, Workflow, Connection, CyclicConnection, NodeInstance, ConnectionContract, data flow semantics, workflow validation

Sibling files: `core-nodes.md` (node architecture), `core-runtime.md` (execution + cycles + resilience + errors), `core-servers.md` (server variants + gateway)

---

## 2. Workflow Construction

### 2.1 WorkflowBuilder

**Module**: `kailash.workflow.builder`
**Import**: `from kailash import WorkflowBuilder`

Builder pattern for creating `Workflow` instances. The builder accumulates nodes and connections, then produces a validated `Workflow` when `build()` is called.

#### 2.1.1 Constructor

```python
class WorkflowBuilder:
    def __init__(self, edge_config: dict[str, Any] | None = None)
```

**Parameters**:

- `edge_config: dict[str, Any] | None` -- Optional edge infrastructure configuration for edge/IoT node support

**Internal state**:

- `self.nodes: dict[str, dict[str, Any]]` -- Accumulated node definitions (keyed by node_id)
- `self.connections: list[dict[str, str]]` -- Accumulated connections (dicts with `from_node`, `from_output`, `to_node`, `to_input`)
- `self._metadata: dict[str, Any]` -- Workflow-level metadata
- `self.workflow_parameters: dict[str, Any]` -- Workflow-level parameter values for injection
- `self.parameter_mappings: dict[str, dict[str, str]]` -- Per-node parameter mapping overrides
- `self.connection_contracts: dict[str, ConnectionContract]` -- Contract definitions for typed connections

#### 2.1.2 add_node

```python
def add_node(self, *args, **kwargs) -> str
```

Unified method supporting multiple API patterns. Returns the node ID (useful for chaining or reference).

**Supported patterns**:

| Pattern             | Example                                                   | Notes                                    |
| ------------------- | --------------------------------------------------------- | ---------------------------------------- |
| Current/Preferred   | `add_node("NodeType", "node_id", {"param": value})`       | String type name, string ID, dict config |
| Two strings         | `add_node("NodeType", "node_id")`                         | No config                                |
| Type only           | `add_node("NodeType")`                                    | Auto-generated ID                        |
| Type + dict         | `add_node("NodeType", {"param": value})`                  | Auto-generated ID                        |
| Alternative (class) | `add_node(NodeClass, "node_id", param=value)`             | Emits `UserWarning`                      |
| Instance            | `add_node(node_instance, "node_id")`                      | Emits `UserWarning`                      |
| Keyword-only        | `add_node(node_type="NodeType", node_id="id", config={})` | Full kwargs                              |

**Returns**: `str` -- The node ID (auto-generated as `f"node_{uuid.uuid4().hex[:8]}"` if not provided)

**Raises**:

- `WorkflowValidationError` -- If `node_id` already exists in the workflow, or if the pattern is unrecognized
- Legacy fluent API `add_node("node_id", NodeClass, ...)` raises `WorkflowValidationError` with migration guidance (removed in v1.0.0)

**Contracts**:

- Node IDs MUST be unique within a workflow
- When using class references for SDK-registered nodes, a `UserWarning` is emitted suggesting the string pattern
- When using class references for custom (unregistered) nodes, the warning confirms this is the correct pattern
- Node type is stored as a string name regardless of how it was provided

**Edge detection**: Node types starting with "Edge"/"edge" or ending with "EdgeNode" are flagged as edge nodes, triggering edge infrastructure initialization at build time.

#### 2.1.3 add_connection

```python
def add_connection(
    self,
    from_node: str,
    from_output: str,
    to_node: str,
    to_input: str,
) -> WorkflowBuilder
```

Connect two nodes by specifying source output port and target input port.

**Parameters**:

- `from_node` -- Source node ID
- `from_output` -- Output field name from source node
- `to_node` -- Target node ID
- `to_input` -- Input field name on target node

**Returns**: `self` for method chaining

**Raises**:

- `WorkflowValidationError` -- If `from_node` or `to_node` does not exist in the workflow. Error message includes available nodes and "did you mean?" suggestions.
- `ConnectionError` -- If `from_node == to_node` (self-connection), or if the exact same connection already exists (duplicate detection)

**Contracts**:

- Both nodes must exist before connecting (call `add_node` first)
- Duplicate connections (same from_node, from_output, to_node, to_input) are rejected
- Non-standard port names emit DEBUG-level log messages listing common port names

#### 2.1.4 connect (Convenience)

```python
def connect(
    self,
    from_node: str,
    to_node: str,
    mapping: dict | None = None,
    from_output: str | None = None,
    to_input: str | None = None,
) -> None
```

Higher-level connection method supporting multiple styles.

**Behavior**:

- If `mapping` provided: iterates over `{output: input}` pairs, calling `add_connection` for each
- If `from_output` and `to_input` provided: single explicit connection
- If neither: defaults to `add_connection(from_node, "data", to_node, "data")`

#### 2.1.5 add_typed_connection

```python
def add_typed_connection(
    self,
    from_node: str,
    from_output: str,
    to_node: str,
    to_input: str,
    contract: str | ConnectionContract,
    validate_immediately: bool = False,
) -> WorkflowBuilder
```

Adds a connection with contract-based validation using JSON Schema.

**Parameters**:

- `contract` -- Either a contract name (string, resolved from registry) or a `ConnectionContract` instance
- `validate_immediately` -- If `True`, validates contract schemas at build time using `Draft7Validator`

**Raises**:

- `WorkflowValidationError` -- If contract name is not found in registry, or if schema validation fails when `validate_immediately=True`

#### 2.1.6 set_metadata

```python
def set_metadata(self, **kwargs) -> WorkflowBuilder
```

Sets workflow-level metadata (key-value pairs). Returns `self` for chaining.

#### 2.1.7 validate_parameter_declarations

```python
def validate_parameter_declarations(self, warn_on_issues: bool = True) -> list[ValidationIssue]
```

Validates parameter declarations for all nodes. Detects common issues like undeclared parameters, type mismatches, and missing required parameters.

**Returns**: List of `ValidationIssue` objects with severity (`ERROR` or `WARNING`), category, error code, message, and suggestion.

#### 2.1.8 build

```python
def build(self, workflow_id: str | None = None, **kwargs) -> Workflow
```

Builds and returns a validated `Workflow` instance.

**Parameters**:

- `workflow_id: str | None` -- Workflow identifier. Auto-generated as `str(uuid.uuid4())` if not provided.
- `**kwargs` -- Additional metadata: `name`, `description`, `version`, `author`, etc.

**Returns**: `Workflow` -- Configured, validated workflow instance

**Build sequence**:

1. Generate workflow ID if not provided
2. Merge builder metadata with kwargs; default `name` to `f"Workflow-{workflow_id[:8]}"`
3. Initialize edge infrastructure if edge nodes were detected
4. Run `validate_parameter_declarations()` -- critical errors (severity `ERROR`) block the build with `WorkflowValidationError`
5. Add all nodes to the `Workflow` instance (resolving types from `NodeRegistry`, instantiating classes, or transferring instances)
6. Add all connections to the `Workflow` instance
7. Inject workflow parameters into nodes without incoming connections (parameter injection)

**Raises**:

- `WorkflowValidationError` -- If parameter declaration errors are found (severity ERROR), if any node fails to add, or if any connection fails

**Contracts**:

- `build()` MUST be called before passing to a runtime. Passing a `WorkflowBuilder` directly to `runtime.execute()` is a usage error.
- The returned `Workflow` is a fully instantiated DAG with real `Node` instances, ready for execution.

### 2.2 Workflow

**Module**: `kailash.workflow.graph`
**Import**: `from kailash import Workflow`

Represents a workflow as a directed graph of node instances and connections.

#### 2.2.1 Constructor

```python
class Workflow:
    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "",
        metadata: dict[str, Any] | None = None,
    )
```

**Internal state**:

- `self.graph` -- `WorkflowDAG` instance (directed graph)
- `self._node_instances: dict[str, Node]` -- Maps node_id to live Node instances
- `self.nodes: dict[str, NodeInstance]` -- Maps node_id to NodeInstance metadata
- `self.connections: list[Connection | CyclicConnection]` -- All connections
- `self._topo_cache: tuple[str, ...] | None` -- Cached topological sort (invalidated on mutation)
- `self._dag_cycle_cache` -- Cached DAG/cycle edge separation (invalidated on mutation)

#### 2.2.2 add_node (on Workflow)

```python
def add_node(self, node_id: str, node_or_type: Any, **config) -> None
```

Adds a node to the workflow graph. Called internally by `WorkflowBuilder.build()`.

**Accepts**:

- String type name (resolved via `NodeRegistry.get()`)
- Node class (instantiated with config)
- Node instance (assigned the given node_id)

**Raises**:

- `WorkflowValidationError` -- If `node_id` already exists
- `NodeConfigurationError` -- If node creation/configuration fails

#### 2.2.3 connect (on Workflow)

```python
def connect(
    self,
    source_node: str,
    target_node: str,
    mapping: dict[str, str] | None = None,
    cycle: bool = False,
    max_iterations: int | None = None,
    convergence_check: str | None = None,
    cycle_id: str | None = None,
    timeout: float | None = None,
    memory_limit: int | None = None,
    condition: str | None = None,
    parent_cycle: str | None = None,
) -> None
```

Connects two nodes with output-to-input mapping. Supports both DAG and cyclic connections.

**Cycle restrictions**:

- Direct `cycle=True` from external code raises `WorkflowValidationError` directing users to the `CycleBuilder` API (removed in v1.0.0)
- Only internal calls from `cycle_builder.py` are allowed to set `cycle=True`
- Cyclic connections require at least one of `max_iterations` or `convergence_check`
- `max_iterations`, `timeout`, `memory_limit` must be positive when provided

**Default mapping**: If `mapping` is `None`, defaults to `{"output": "input"}`

**Edge merging**: Multiple connections between the same node pair merge their mappings into the same graph edge.

#### 2.2.4 get_node

```python
def get_node(self, node_id: str) -> Node | None
```

Returns the live `Node` instance for the given ID, or `None` if not found.

#### 2.2.5 Graph Utilities

- `separate_dag_and_cycle_edges()` -- Returns `(dag_edges, cycle_edges)` as tuples of `(source, target, data)`. Cached; invalidated on mutation.
- `get_cycle_groups()` -- Returns `dict[str, list[tuple]]` mapping cycle IDs to their edges. Detects strongly connected components for multi-node cycles.
- `create_cycle(cycle_id: str | None = None)` -- Entry point to the CycleBuilder API. Returns a `CycleBuilder` instance.

---

## 3. Connection Model

### 3.1 Connection

**Module**: `kailash.workflow.graph`
**Import**: `from kailash import Connection`
**Base**: `pydantic.BaseModel`

```python
class Connection(BaseModel):
    source_node: str       # Source node ID
    source_output: str     # Output field from source
    target_node: str       # Target node ID
    target_input: str      # Input field on target
```

Data flows from `source_node.source_output` to `target_node.target_input`. The runtime reads the output dict from the source node and injects the value at key `source_output` into the target node's input as `target_input`.

### 3.2 CyclicConnection

**Module**: `kailash.workflow.graph`
**Extends**: `Connection`

```python
class CyclicConnection(Connection):
    cycle: bool = False                       # Whether this creates a cycle
    max_iterations: int | None = None         # Maximum cycle iterations
    convergence_check: str | None = None      # Convergence condition expression
    cycle_id: str | None = None               # Logical cycle group identifier
    timeout: float | None = None              # Cycle timeout in seconds
    memory_limit: int | None = None           # Memory limit in MB
    condition: str | None = None              # Conditional cycle routing expression
    parent_cycle: str | None = None           # Parent cycle for nested cycles
```

### 3.3 NodeInstance

**Module**: `kailash.workflow.graph`
**Import**: `from kailash import NodeInstance`
**Base**: `pydantic.BaseModel`

Metadata representation of a node instance within a workflow (distinct from the live `Node` instance).

```python
class NodeInstance(BaseModel):
    node_id: str                              # Unique identifier
    node_type: str                            # Type of node
    config: dict[str, Any] = {}               # Node configuration
    position: tuple[float, float] = (0, 0)    # Visual position
```

**Sensitive key redaction**: `model_dump()` is overridden to redact keys matching `_SENSITIVE_KEYS` (`api_key`, `api_secret`, `base_url`, `token`, `password`, `credential`, `auth`, `secret`) with `"***REDACTED***"`.

### 3.4 ConnectionContract

**Module**: `kailash.workflow.contracts`

Defines a contract for data flowing through a connection using JSON Schema.

```python
@dataclass
class ConnectionContract:
    name: str                                              # Human-readable name
    description: str = ""                                  # Description
    source_schema: dict[str, Any] | None = None            # JSON Schema for source output
    target_schema: dict[str, Any] | None = None            # JSON Schema for target input
    security_policies: list[SecurityPolicy] = []           # Security policies
    transformations: dict[str, Any] | None = None          # Optional type coercion rules
    audit_level: str = "normal"                            # 'none', 'normal', 'detailed'
    metadata: dict[str, Any] = {}                          # Additional metadata
```

**Security policies** (`SecurityPolicy` enum): `NONE`, `NO_PII`, `NO_CREDENTIALS`, `NO_SQL`, `SANITIZED`, `ENCRYPTED`

**Validation**: Schemas are validated against JSON Schema Draft 7 at construction time via `__post_init__`.

### 3.5 Data Flow Semantics

When the runtime executes a workflow:

1. Root nodes (no incoming connections) execute first with any injected parameters
2. For each connection `A.output_field -> B.input_field`: the value at key `output_field` in node A's result dict is passed as keyword argument `input_field` to node B's `run()` method
3. If a node has multiple incoming connections, all mapped values are merged into a single kwargs dict
4. If `mapping` is not specified, the default is `{"output": "input"}`
5. Multiple mappings between the same node pair are supported (e.g., `{"result": "data", "metadata": "context"}`)

---

## 8. Workflow Validation

### 8.1 Build-Time Validation (WorkflowBuilder.build)

The `build()` method performs:

1. **Parameter declaration validation** via `validate_parameter_declarations()`:
   - Detects undeclared parameters (parameters passed in config but not in `get_parameters()`)
   - Detects missing required parameters
   - Issues with severity `ERROR` block the build
   - Issues with severity `WARNING` are logged at DEBUG level
2. **Node instantiation**: Each node is resolved from the registry (or class/instance), constructed, and configured
3. **Connection validation**: Source and target nodes must exist; self-connections rejected for non-cycles

### 8.2 Runtime Validation

The runtime validates:

- **Connection parameter validation** (controlled by `connection_validation` setting):
  - `"off"` -- No validation
  - `"warn"` -- Log warnings for mismatched connections (default)
  - `"strict"` -- Raise `WorkflowValidationError` on mismatches
- **Contract validation**: When typed connections have contracts, data flowing through them is validated against JSON Schema
- **Cycle validation**: Cycles require at least one termination condition; `max_iterations` must be positive

### 8.3 ValidationIssue

```python
class ValidationIssue:
    severity: IssueSeverity    # ERROR or WARNING
    category: str              # e.g., "parameter_declaration"
    code: str                  # e.g., "PAR005", "PAR006"
    message: str               # Human-readable description
    suggestion: str            # Actionable fix suggestion
    node_id: str | None        # Affected node
```

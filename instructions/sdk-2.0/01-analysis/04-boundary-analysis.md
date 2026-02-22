# Boundary Analysis: Rust Core vs Language SDKs

## 1. Overview

This document defines the exact boundary between the shared Rust core and language-specific
SDK layers. The principle is: **Rust handles execution infrastructure; each language handles
domain logic and idiomatic APIs.**

## 2. What Goes in Rust Core (~15-20K LOC)

### 2.1 DAG Data Structure (Replace networkx)

**Current Python implementation**: `workflow/graph.py:122` uses `nx.DiGraph()`

**Rust replacement**:

```rust
// kailash-core/src/graph/mod.rs

/// Workflow DAG stored as adjacency list with node/edge metadata
pub struct WorkflowGraph {
    /// Node storage: node_id -> NodeInfo
    nodes: HashMap<NodeId, NodeInfo>,
    /// Forward adjacency: source -> [(target, ConnectionInfo)]
    forward_edges: HashMap<NodeId, Vec<(NodeId, ConnectionInfo)>>,
    /// Reverse adjacency: target -> [(source, ConnectionInfo)]
    reverse_edges: HashMap<NodeId, Vec<(NodeId, ConnectionInfo)>>,
    /// Cached topological order (invalidated on mutation)
    topo_cache: Option<Vec<NodeId>>,
    /// Cached level assignment (invalidated on mutation)
    level_cache: Option<Vec<Vec<NodeId>>>,
}

pub struct NodeInfo {
    pub node_id: NodeId,
    pub node_type: String,
    pub config: serde_json::Value,  // Opaque config blob
    pub metadata: NodeMetadata,
}

pub struct ConnectionInfo {
    pub source_output: String,
    pub target_input: String,
    pub is_cyclic: bool,
    pub cycle_config: Option<CycleConfig>,
}
```

**Operations implemented in Rust**:

- `add_node(id, type, config)` -> Result
- `add_edge(source, target, connection)` -> Result
- `remove_node(id)` -> Result
- `topological_sort()` -> Vec<NodeId>
- `detect_cycles()` -> Vec<Vec<NodeId>>
- `compute_levels()` -> Vec<Vec<NodeId>>
- `predecessors(id)` -> Vec<(NodeId, ConnectionInfo)>
- `successors(id)` -> Vec<(NodeId, ConnectionInfo)>
- `validate_structure()` -> ValidationResult

**Currently at**: `workflow/graph.py:81-250`, `runtime/local.py:1669`

### 2.2 Topological Sort & Scheduling

**Current**: `nx.topological_sort(workflow.graph)` at `runtime/local.py:1669`

**Rust replacement**: Kahn's algorithm with level computation for parallel scheduling:

```rust
// kailash-core/src/scheduler/mod.rs

pub struct ExecutionSchedule {
    /// Ordered list of execution levels
    pub levels: Vec<ExecutionLevel>,
    /// Total node count
    pub node_count: usize,
    /// Whether parallel execution is possible
    pub can_parallelize: bool,
}

pub struct ExecutionLevel {
    pub level: usize,
    pub node_ids: Vec<NodeId>,
    pub estimated_async_count: usize,
}

impl WorkflowGraph {
    /// Compute execution schedule with optional parallelism
    pub fn compute_schedule(&self) -> Result<ExecutionSchedule, ScheduleError> {
        // Kahn's algorithm with level tracking
        // O(V + E) time, O(V) space
    }
}
```

### 2.3 Cycle Detection & Management

**Current**: `workflow/cycle_analyzer.py`, `workflow/cyclic_runner.py` (1638 LOC)

**Rust handles**:

- Cycle detection (Tarjan's SCC algorithm)
- Cycle group identification
- Iteration counting and limit enforcement
- Convergence state tracking

**Python retains**:

- Convergence condition evaluation (user-defined expressions)
- Cycle state persistence between iterations
- Custom cycle callbacks

```rust
// kailash-core/src/cycles/mod.rs

pub struct CycleGroup {
    pub cycle_id: String,
    pub nodes: Vec<NodeId>,
    pub max_iterations: u32,
    pub timeout_ms: Option<u64>,
    pub convergence_check: Option<String>,  // Expression evaluated in Python
}

pub struct CycleState {
    pub iteration: u32,
    pub converged: bool,
    pub last_values: HashMap<String, serde_json::Value>,
}
```

### 2.4 Resource Lifecycle Management

**Current**: `resources/registry.py`, `runtime/resource_manager.py`

**Rust handles**:

- Resource tracking (creation, usage, destruction)
- Reference counting
- Memory limit enforcement
- Connection pool sizing
- Health check scheduling

```rust
// kailash-core/src/resources/mod.rs

pub struct ResourceManager {
    resources: HashMap<ResourceId, ResourceHandle>,
    limits: ResourceLimits,
    health_check_interval: Duration,
}

pub struct ResourceLimits {
    pub max_memory_mb: u64,
    pub max_cpu_percent: f64,
    pub max_connections: u32,
}
```

### 2.5 Trust Verification (CARE Framework)

**Current**: `runtime/trust/` directory

**Rust handles**:

- Cryptographic hash chain verification
- Trust posture computation
- Constraint dimension evaluation
- Audit trail integrity verification

```rust
// kailash-core/src/trust/mod.rs

pub struct TrustChain {
    entries: Vec<TrustEntry>,
    root_hash: [u8; 32],
}

pub struct TrustVerifier {
    mode: VerificationMode,  // Disabled, Permissive, Enforcing
    root_authority: Option<PublicKey>,
}
```

### 2.6 Workflow Validation

**Current**: `workflow/validation.py` (1027 LOC), `runtime/validation/` directory

**Rust handles**:

- Structure validation (orphan nodes, disconnected subgraphs)
- Connection type compatibility checking
- Parameter completeness verification
- Cyclic dependency detection in non-cycle-allowed workflows

```rust
// kailash-core/src/validation/mod.rs

pub struct ValidationResult {
    pub is_valid: bool,
    pub errors: Vec<ValidationError>,
    pub warnings: Vec<ValidationWarning>,
}

pub fn validate_workflow(graph: &WorkflowGraph) -> ValidationResult {
    let mut result = ValidationResult::default();
    validate_structure(graph, &mut result);
    validate_connections(graph, &mut result);
    validate_completeness(graph, &mut result);
    result
}
```

## 3. What Stays in Python/Go/Java

### 3.1 Node Implementations (ALL stay in language SDKs)

Every node is implemented in the target language. The Rust core never executes node logic;
it only schedules when nodes should run.

**Python**: All 142 node files in `src/kailash/nodes/` remain Python
**Go**: Node implementations wrap Go standard library and third-party packages
**Java**: Node implementations wrap Java ecosystem libraries

### 3.2 Framework Layers (ALWAYS native per language)

| Framework | Python                       | Go                      | Java              |
| --------- | ---------------------------- | ----------------------- | ----------------- |
| DataFlow  | Wraps SQLAlchemy, aiosqlite  | Wraps database/sql, pgx | Wraps JDBC, JPA   |
| Nexus     | Wraps FastAPI, Starlette     | Wraps net/http, Gin     | Wraps Spring Boot |
| Kaizen    | Wraps openai, anthropic SDKs | Wraps go-openai         | Wraps langchain4j |

### 3.3 User-Facing APIs

WorkflowBuilder, runtime constructors, and all public APIs are implemented in each language
idiomatically. They call into Rust core via FFI for graph/scheduling operations.

### 3.4 MCP Protocol Handling

MCP server/client stays in each language (Python uses `mcp` package, Go would use
go-mcp, Java would use mcp-java).

### 3.5 Channel Implementations

API, CLI, and MCP channels are language-specific wrappers around language-native frameworks.

## 4. FFI Data Structures

### 4.1 Core FFI Types

These types cross the FFI boundary and must be C-compatible:

```rust
// kailash-ffi/src/types.rs

/// Opaque handle to a workflow graph
#[repr(C)]
pub struct WorkflowHandle {
    ptr: *mut c_void,
}

/// Node identifier (string, owned by Rust)
#[repr(C)]
pub struct NodeId {
    ptr: *const c_char,
    len: usize,
}

/// Connection between nodes
#[repr(C)]
pub struct FfiConnection {
    source_node: NodeId,
    source_output: NodeId,
    target_node: NodeId,
    target_input: NodeId,
}

/// Execution result for a single node
#[repr(C)]
pub struct FfiNodeResult {
    node_id: NodeId,
    status: FfiResultStatus,
    /// JSON-serialized output (owned by Rust, read by language SDK)
    output_json: *const c_char,
    output_json_len: usize,
    duration_ns: u64,
    error_message: *const c_char,
}

#[repr(C)]
pub enum FfiResultStatus {
    Success = 0,
    Failed = 1,
    Skipped = 2,
    TimedOut = 3,
}

/// Validation result
#[repr(C)]
pub struct FfiValidationResult {
    is_valid: bool,
    errors: *const FfiValidationError,
    error_count: usize,
    warnings: *const FfiValidationWarning,
    warning_count: usize,
}
```

### 4.2 Callback Mechanism (Node Execution)

The Rust core schedules nodes but calls back into the language SDK for actual execution:

```rust
// kailash-ffi/src/callbacks.rs

/// Callback type for node execution
/// Called by Rust scheduler, implemented by language SDK
pub type NodeExecutionCallback = extern "C" fn(
    context: *mut c_void,       // Language-specific context
    node_id: *const c_char,     // Which node to execute
    node_type: *const c_char,   // Node type name
    inputs_json: *const c_char, // JSON-serialized inputs
    inputs_len: usize,
) -> FfiNodeResult;

/// Callback for convergence checking (cycles)
pub type ConvergenceCallback = extern "C" fn(
    context: *mut c_void,
    cycle_id: *const c_char,
    iteration: u32,
    state_json: *const c_char,
    state_len: usize,
) -> bool;

/// Register callbacks before execution
#[no_mangle]
pub extern "C" fn kailash_register_callbacks(
    handle: WorkflowHandle,
    execute_node: NodeExecutionCallback,
    check_convergence: Option<ConvergenceCallback>,
    context: *mut c_void,
) -> FfiResultStatus;
```

### 4.3 Data Flow Across FFI

```
Language SDK                    Rust Core
+------------------+          +-------------------+
| WorkflowBuilder  |  FFI     | WorkflowGraph     |
| .add_node()      | -------> | .add_node()       |
| .connect()       | -------> | .add_edge()       |
| .build()         | -------> | .validate()       |
|                  |          | .compute_schedule()|
|                  |          |                   |
| Runtime.execute  | -------> | .execute()        |
|                  |          |   for each level: |
|                  |          |     for each node:|
|                  | <------- |       CALLBACK    |
| node.execute()   |          |                   |
| return result    | -------> |     store result  |
|                  |          |   end loop        |
|                  | <------- | return all results|
| (dict, run_id)   |          |                   |
+------------------+          +-------------------+
```

## 5. PyO3 Bindings (Python-Specific)

For Python, we use PyO3 instead of raw C FFI for ergonomics:

```rust
// kailash-python/src/lib.rs
use pyo3::prelude::*;

#[pyclass]
struct PyWorkflowGraph {
    inner: WorkflowGraph,
}

#[pymethods]
impl PyWorkflowGraph {
    #[new]
    fn new() -> Self {
        Self { inner: WorkflowGraph::new() }
    }

    fn add_node(&mut self, node_id: &str, node_type: &str, config: &PyDict) -> PyResult<()> {
        let config_json = pythonize::depythonize(config)?;
        self.inner.add_node(node_id.into(), node_type.into(), config_json)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }

    fn topological_sort(&self) -> PyResult<Vec<String>> {
        self.inner.topological_sort()
            .map(|ids| ids.into_iter().map(|id| id.to_string()).collect())
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }

    fn execute(&self, py: Python, callback: PyObject) -> PyResult<PyObject> {
        let schedule = self.inner.compute_schedule()
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;

        let mut results = HashMap::new();
        for level in &schedule.levels {
            for node_id in &level.node_ids {
                let inputs = self.inner.prepare_inputs(node_id, &results);
                let inputs_py = pythonize::pythonize(py, &inputs)?;
                let result = callback.call1(py, (node_id.as_str(), inputs_py))?;
                results.insert(node_id.clone(), depythonize(result)?);
            }
        }
        Ok(pythonize::pythonize(py, &results)?)
    }
}
```

## 6. Memory Management

### 6.1 Ownership Rules

| Data                    | Owner        | Lifetime                                                    |
| ----------------------- | ------------ | ----------------------------------------------------------- |
| WorkflowGraph           | Rust         | Created by language SDK, freed by `kailash_free_workflow()` |
| Node configs (JSON)     | Rust         | Copied in during `add_node()`, freed with graph             |
| Node instances          | Language SDK | Language GC manages lifecycle                               |
| Execution inputs (JSON) | Rust         | Created per-callback, freed after callback returns          |
| Execution results       | Rust         | Stored in graph, returned to language SDK as JSON           |
| Connection info         | Rust         | Stored in graph edges                                       |
| Schedule/levels         | Rust         | Computed lazily, cached, invalidated on mutation            |

### 6.2 String Handling

All strings crossing FFI are UTF-8. Two patterns:

1. **Rust-owned strings**: Returned as `(*const c_char, len)` pairs. Language SDK must copy
   before Rust frees. PyO3 handles this automatically.

2. **Language-owned strings**: Passed as `(*const c_char, len)` pairs. Rust copies into
   owned String. PyO3 handles this automatically.

### 6.3 JSON Serialization for Complex Data

Node configs and execution inputs/outputs cross FFI as JSON:

- **Config**: Serialized once during `add_node()`, deserialized in language SDK for node creation
- **Inputs**: Serialized by Rust from stored results, deserialized by language SDK for callback
- **Outputs**: Serialized by language SDK after node execution, stored by Rust

This adds ~0.01-0.1ms per node for JSON ser/deser but avoids complex FFI struct mapping.

## 7. Error Handling Across FFI

```rust
// kailash-ffi/src/error.rs

#[repr(C)]
pub enum FfiErrorCode {
    Ok = 0,
    InvalidArgument = 1,
    NodeNotFound = 2,
    CycleDetected = 3,
    ValidationFailed = 4,
    ExecutionFailed = 5,
    ResourceExhausted = 6,
    TrustViolation = 7,
    InternalError = 99,
}

#[repr(C)]
pub struct FfiError {
    code: FfiErrorCode,
    message: *const c_char,
    message_len: usize,
}
```

Each language SDK maps these error codes to native exception types:

- Python: `WorkflowValidationError`, `RuntimeExecutionError`, etc.
- Go: `fmt.Errorf("kailash: %s", message)` or custom error types
- Java: `KailashException` hierarchy

## 8. Threading Model

### 8.1 Rust Core

- Workflow graph operations are **not thread-safe** (single-owner pattern)
- Execution scheduler can use Rayon for parallel level execution
- Callbacks into language SDK must respect language threading rules

### 8.2 Python

- GIL acquisition for all Python callbacks
- PyO3 handles GIL management automatically
- For CPU-bound Rust work, release GIL via `py.allow_threads()`
- Async execution: Rust schedules, Python awaits via `asyncio`

### 8.3 Go

- CGo callbacks run on Go goroutines
- Rust execution can use multiple OS threads
- Go scheduler handles goroutine multiplexing

### 8.4 Java

- JNI callbacks on Java threads
- Rust can use Rayon thread pool
- Java CompletableFuture integration for async

## 9. Boundary Decision Rationale

### 9.1 Why DAG in Rust (not just topological sort)

The DAG is the central data structure that everything else depends on. Moving just the
algorithms without the data structure would require constant FFI crossings to query graph
state, negating performance benefits.

### 9.2 Why Node Execution Stays in Language SDKs

Nodes perform domain-specific work (SQL queries, HTTP calls, LLM inference) that depends
on language-native libraries. Moving node execution to Rust would require FFI wrappers for
every library, which is impractical and slower.

### 9.3 Why Frameworks Stay Native

DataFlow wrapping Go's `database/sql` is idiomatic and performant. Wrapping it through Rust
FFI would add overhead and complexity. Same for Nexus wrapping `net/http` and Kaizen wrapping
LLM SDKs.

### 9.4 Why Validation in Rust

Validation operates purely on the graph structure (node types, connections, parameters).
It doesn't need language-specific runtime context. Moving it to Rust provides both speed
and consistency across all language SDKs.

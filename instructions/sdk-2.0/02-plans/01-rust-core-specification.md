# Rust Core Specification

## 1. Overview

The Rust core (`kailash-core`) is the shared execution engine for all Kailash language SDKs.
It handles workflow graph management, DAG scheduling, cycle detection, resource management,
trust verification, and validation. Estimated size: ~15-20K LOC of Rust.

## 2. Crate Structure

```
kailash-rust/
+-- Cargo.toml                  # Workspace root
+-- kailash-core/               # Core library (no FFI)
|   +-- Cargo.toml
|   +-- src/
|       +-- lib.rs
|       +-- graph/              # DAG data structure
|       |   +-- mod.rs
|       |   +-- node.rs
|       |   +-- edge.rs
|       |   +-- builder.rs
|       +-- scheduler/          # Execution scheduling
|       |   +-- mod.rs
|       |   +-- topological.rs
|       |   +-- levels.rs
|       |   +-- parallel.rs
|       +-- cycles/             # Cycle detection & management
|       |   +-- mod.rs
|       |   +-- detection.rs
|       |   +-- executor.rs
|       |   +-- state.rs
|       +-- validation/         # Workflow validation
|       |   +-- mod.rs
|       |   +-- structure.rs
|       |   +-- connections.rs
|       |   +-- parameters.rs
|       +-- resources/          # Resource lifecycle
|       |   +-- mod.rs
|       |   +-- manager.rs
|       |   +-- limits.rs
|       +-- trust/              # CARE trust framework
|       |   +-- mod.rs
|       |   +-- chain.rs
|       |   +-- verifier.rs
|       |   +-- posture.rs
|       +-- error.rs            # Error types
|       +-- types.rs            # Core type definitions
+-- kailash-ffi/                # C-compatible FFI layer
|   +-- Cargo.toml
|   +-- src/
|       +-- lib.rs
|       +-- types.rs            # FFI-safe types
|       +-- callbacks.rs        # Callback definitions
|       +-- error.rs            # FFI error handling
+-- kailash-python/             # PyO3 Python bindings
|   +-- Cargo.toml
|   +-- src/
|       +-- lib.rs
|       +-- workflow.rs         # Python workflow wrapper
|       +-- runtime.rs          # Python runtime wrapper
|       +-- types.rs            # Python type conversions
+-- kailash-go/                 # Go bindings (CGo header generation)
|   +-- Cargo.toml
|   +-- src/
|       +-- lib.rs
|       +-- bindings.rs
+-- kailash-java/               # JNI Java bindings
|   +-- Cargo.toml
|   +-- src/
|       +-- lib.rs
|       +-- bindings.rs
+-- kailash-bench/              # Benchmarks
    +-- Cargo.toml
    +-- benches/
        +-- graph_bench.rs
        +-- scheduler_bench.rs
        +-- validation_bench.rs
```

## 3. Core APIs

### 3.1 Workflow Graph API

```rust
// kailash-core/src/graph/mod.rs

use std::collections::HashMap;
use serde_json::Value;

/// Unique identifier for a node within a workflow
#[derive(Debug, Clone, Hash, Eq, PartialEq)]
pub struct NodeId(pub String);

/// Workflow graph - the central data structure
pub struct WorkflowGraph {
    id: String,
    name: String,
    nodes: HashMap<NodeId, NodeInfo>,
    forward_adj: HashMap<NodeId, Vec<Edge>>,
    reverse_adj: HashMap<NodeId, Vec<Edge>>,
    metadata: HashMap<String, Value>,
    // Cached computations (invalidated on mutation)
    topo_cache: Option<Vec<NodeId>>,
    level_cache: Option<Vec<Vec<NodeId>>>,
    cycle_cache: Option<Vec<CycleGroup>>,
}

pub struct NodeInfo {
    pub id: NodeId,
    pub node_type: String,
    pub config: Value,                    // JSON blob, opaque to Rust
    pub metadata: NodeMetadata,
    pub is_async: bool,                   // Hint for scheduler
}

pub struct NodeMetadata {
    pub description: String,
    pub version: String,
    pub tags: Vec<String>,
}

pub struct Edge {
    pub target: NodeId,
    pub connection: ConnectionInfo,
}

pub struct ConnectionInfo {
    pub source_output: String,
    pub target_input: String,
    pub is_cyclic: bool,
    pub cycle_config: Option<CycleConnectionConfig>,
}

pub struct CycleConnectionConfig {
    pub cycle_id: String,
    pub max_iterations: u32,
    pub timeout_ms: Option<u64>,
    pub convergence_check: Option<String>,
}
```

### 3.2 Graph Operations

```rust
impl WorkflowGraph {
    /// Create a new empty workflow graph
    pub fn new(id: &str, name: &str) -> Self;

    /// Add a node to the graph
    /// Returns error if node_id already exists
    pub fn add_node(
        &mut self,
        node_id: NodeId,
        node_type: &str,
        config: Value,
        is_async: bool,
    ) -> Result<(), GraphError>;

    /// Remove a node and all its edges
    pub fn remove_node(&mut self, node_id: &NodeId) -> Result<NodeInfo, GraphError>;

    /// Add a connection (edge) between two nodes
    pub fn connect(
        &mut self,
        source: &NodeId,
        target: &NodeId,
        connection: ConnectionInfo,
    ) -> Result<(), GraphError>;

    /// Remove a connection
    pub fn disconnect(
        &mut self,
        source: &NodeId,
        target: &NodeId,
    ) -> Result<(), GraphError>;

    /// Get all predecessors of a node with connection info
    pub fn predecessors(&self, node_id: &NodeId) -> Result<Vec<(&NodeId, &ConnectionInfo)>, GraphError>;

    /// Get all successors of a node with connection info
    pub fn successors(&self, node_id: &NodeId) -> Result<Vec<(&NodeId, &ConnectionInfo)>, GraphError>;

    /// Get node info
    pub fn get_node(&self, node_id: &NodeId) -> Option<&NodeInfo>;

    /// Get all node IDs
    pub fn node_ids(&self) -> Vec<&NodeId>;

    /// Get node count
    pub fn node_count(&self) -> usize;

    /// Get edge count
    pub fn edge_count(&self) -> usize;

    /// Check if graph has cycles (uses cached result)
    pub fn has_cycles(&self) -> bool;

    /// Invalidate all caches (called on mutation)
    fn invalidate_caches(&mut self);
}
```

### 3.3 Scheduler API

```rust
// kailash-core/src/scheduler/mod.rs

/// Execution schedule computed from workflow graph
pub struct ExecutionSchedule {
    pub levels: Vec<ExecutionLevel>,
    pub total_nodes: usize,
    pub async_node_count: usize,
    pub sync_node_count: usize,
    pub can_parallelize: bool,
    pub max_parallelism: usize,
}

pub struct ExecutionLevel {
    pub level_index: usize,
    pub node_ids: Vec<NodeId>,
    pub async_nodes: Vec<NodeId>,
    pub sync_nodes: Vec<NodeId>,
}

/// Input routing table: for each node, which outputs feed its inputs
pub struct InputRouting {
    /// node_id -> [(source_node, source_output, target_input)]
    pub routes: HashMap<NodeId, Vec<InputRoute>>,
}

pub struct InputRoute {
    pub source_node: NodeId,
    pub source_output: String,
    pub target_input: String,
}

impl WorkflowGraph {
    /// Compute topological sort (cached)
    pub fn topological_sort(&mut self) -> Result<&[NodeId], ScheduleError>;

    /// Compute execution schedule with level-based parallelism (cached)
    pub fn compute_schedule(&mut self) -> Result<ExecutionSchedule, ScheduleError>;

    /// Compute input routing table
    pub fn compute_input_routing(&self) -> Result<InputRouting, ScheduleError>;

    /// Get inputs for a specific node given current results
    pub fn prepare_inputs(
        &self,
        node_id: &NodeId,
        results: &HashMap<NodeId, Value>,
    ) -> Result<Value, ScheduleError>;
}
```

### 3.4 Execution API

```rust
// kailash-core/src/execution/mod.rs

/// Node execution callback - implemented by language SDK
pub trait NodeExecutor: Send {
    /// Execute a single node with given inputs
    /// Returns JSON-serialized output
    fn execute_node(
        &self,
        node_id: &NodeId,
        node_type: &str,
        inputs: &Value,
    ) -> Result<Value, ExecutionError>;
}

/// Execution configuration
pub struct ExecutionConfig {
    pub max_concurrent_nodes: usize,
    pub enable_cycles: bool,
    pub conditional_execution: ConditionalMode,
    pub resource_limits: Option<ResourceLimits>,
    pub trust_mode: TrustMode,
    pub timeout_ms: Option<u64>,
}

pub enum ConditionalMode {
    RouteData,
    SkipBranches,
}

pub enum TrustMode {
    Disabled,
    Permissive,
    Enforcing,
}

/// Execution result
pub struct ExecutionResult {
    pub results: HashMap<NodeId, Value>,
    pub run_id: String,
    pub duration_ms: u64,
    pub node_metrics: HashMap<NodeId, NodeMetrics>,
    pub skipped_nodes: Vec<NodeId>,
    pub failed_nodes: Vec<(NodeId, String)>,
}

pub struct NodeMetrics {
    pub duration_ms: u64,
    pub status: NodeStatus,
}

pub enum NodeStatus {
    Success,
    Failed,
    Skipped,
    TimedOut,
}

/// Execute a workflow
pub fn execute(
    graph: &mut WorkflowGraph,
    executor: &dyn NodeExecutor,
    config: &ExecutionConfig,
) -> Result<ExecutionResult, ExecutionError>;
```

### 3.5 Validation API

```rust
// kailash-core/src/validation/mod.rs

pub struct ValidationResult {
    pub is_valid: bool,
    pub errors: Vec<ValidationIssue>,
    pub warnings: Vec<ValidationIssue>,
}

pub struct ValidationIssue {
    pub code: String,           // e.g., "VAL001"
    pub severity: Severity,
    pub message: String,
    pub node_id: Option<NodeId>,
    pub suggestion: Option<String>,
}

pub enum Severity {
    Error,
    Warning,
    Info,
}

impl WorkflowGraph {
    /// Validate workflow structure
    pub fn validate(&self) -> ValidationResult;

    /// Validate with specific configuration
    pub fn validate_with_config(&self, config: &ValidationConfig) -> ValidationResult;
}

pub struct ValidationConfig {
    pub check_orphans: bool,
    pub check_connectivity: bool,
    pub check_cycles: bool,       // Only if cycles not explicitly enabled
    pub check_types: bool,
    pub strict_mode: bool,
}
```

### 3.6 Cycle Management API

```rust
// kailash-core/src/cycles/mod.rs

pub struct CycleGroup {
    pub cycle_id: String,
    pub nodes: Vec<NodeId>,
    pub entry_node: NodeId,
    pub exit_node: NodeId,
    pub max_iterations: u32,
    pub timeout_ms: Option<u64>,
}

pub struct CycleState {
    pub cycle_id: String,
    pub iteration: u32,
    pub converged: bool,
    pub node_values: HashMap<NodeId, Value>,
}

/// Convergence checker - implemented by language SDK
pub trait ConvergenceChecker: Send {
    fn check_convergence(
        &self,
        cycle_id: &str,
        iteration: u32,
        state: &CycleState,
    ) -> bool;
}

impl WorkflowGraph {
    /// Detect all cycle groups (cached, Tarjan's SCC)
    pub fn detect_cycles(&mut self) -> &[CycleGroup];

    /// Execute a cyclic workflow
    pub fn execute_cyclic(
        &mut self,
        executor: &dyn NodeExecutor,
        convergence: &dyn ConvergenceChecker,
        config: &ExecutionConfig,
    ) -> Result<ExecutionResult, ExecutionError>;
}
```

### 3.7 Resource Management API

```rust
// kailash-core/src/resources/mod.rs

pub struct ResourceLimits {
    pub max_memory_mb: Option<u64>,
    pub max_cpu_percent: Option<f64>,
    pub max_connections: Option<u32>,
    pub max_concurrent_workflows: Option<u32>,
}

pub struct ResourceStatus {
    pub memory_mb: u64,
    pub cpu_percent: f64,
    pub active_connections: u32,
    pub can_proceed: bool,
    pub violations: Vec<String>,
}

pub struct ResourceManager {
    limits: ResourceLimits,
}

impl ResourceManager {
    pub fn new(limits: ResourceLimits) -> Self;
    pub fn check_limits(&self) -> ResourceStatus;
    pub fn enforce(&self) -> Result<(), ResourceError>;
}
```

### 3.8 Trust Verification API

```rust
// kailash-core/src/trust/mod.rs

pub struct TrustChain {
    entries: Vec<TrustEntry>,
    root_hash: [u8; 32],
}

pub struct TrustEntry {
    pub timestamp: u64,
    pub agent_id: String,
    pub action: String,
    pub hash: [u8; 32],
    pub prev_hash: [u8; 32],
    pub signature: Option<Vec<u8>>,
}

pub struct TrustVerifier {
    mode: TrustMode,
}

impl TrustVerifier {
    pub fn new(mode: TrustMode) -> Self;
    pub fn verify_chain(&self, chain: &TrustChain) -> Result<bool, TrustError>;
    pub fn verify_node_trust(
        &self,
        node_id: &NodeId,
        node_type: &str,
    ) -> Result<bool, TrustError>;
}

pub struct TrustPosture {
    pub level: PostureLevel,
    pub score: f64,
    pub constraints_met: Vec<String>,
    pub constraints_violated: Vec<String>,
}

pub enum PostureLevel {
    Untrusted,
    Low,
    Medium,
    High,
    Full,
}
```

## 4. Dependency Selection

### 4.1 Core Dependencies

| Crate        | Version | Purpose                  | Justification                              |
| ------------ | ------- | ------------------------ | ------------------------------------------ |
| `serde`      | 1.x     | Serialization            | Industry standard                          |
| `serde_json` | 1.x     | JSON handling            | Node configs and results cross FFI as JSON |
| `thiserror`  | 2.x     | Error types              | Ergonomic error derivation                 |
| `sha2`       | 0.10    | Trust chain hashing      | SHA-256 for trust entries                  |
| `uuid`       | 1.x     | Run ID generation        | UUID v4 for execution runs                 |
| `sysinfo`    | 0.33    | Resource monitoring      | Replace Python psutil                      |
| `rayon`      | 1.x     | Parallel level execution | Data parallelism for independent nodes     |
| `log`        | 0.4     | Logging facade           | Standard Rust logging                      |

### 4.2 FFI Dependencies

| Crate      | Version | Purpose                       |
| ---------- | ------- | ----------------------------- |
| `pyo3`     | 0.22    | Python bindings               |
| `jni`      | 0.21    | Java bindings                 |
| `cbindgen` | 0.27    | C header generation (for CGo) |

### 4.3 Explicitly NOT Using

| Crate       | Reason                                                  |
| ----------- | ------------------------------------------------------- |
| `petgraph`  | Custom DAG is simpler and avoids unnecessary generality |
| `tokio`     | Core is sync; async is handled by language SDKs         |
| `async-std` | Same reason as tokio                                    |
| `reqwest`   | HTTP calls stay in language SDKs                        |
| `sqlx`      | Database stays in language SDKs                         |

## 5. Performance Targets

| Metric                              | Target    | Measurement       |
| ----------------------------------- | --------- | ----------------- |
| Graph creation (20 nodes, 19 edges) | < 0.05ms  | `criterion` bench |
| Topological sort (20 nodes)         | < 0.005ms | `criterion` bench |
| Topological sort (1000 nodes)       | < 0.1ms   | `criterion` bench |
| Level computation (20 nodes)        | < 0.01ms  | `criterion` bench |
| Cycle detection (20 nodes)          | < 0.01ms  | `criterion` bench |
| Validation (20 nodes)               | < 0.1ms   | `criterion` bench |
| Input preparation (per node)        | < 0.01ms  | `criterion` bench |
| Memory per node                     | < 1KB     | `criterion` bench |
| FFI crossing (PyO3)                 | < 0.05ms  | PyO3 bench        |
| FFI crossing (CGo)                  | < 0.1ms   | Go bench          |
| FFI crossing (JNI)                  | < 0.1ms   | Java bench        |

## 6. Error Handling Strategy

```rust
// kailash-core/src/error.rs

#[derive(Debug, thiserror::Error)]
pub enum KailashError {
    #[error("Graph error: {0}")]
    Graph(#[from] GraphError),

    #[error("Schedule error: {0}")]
    Schedule(#[from] ScheduleError),

    #[error("Validation error: {0}")]
    Validation(#[from] ValidationError),

    #[error("Execution error: {0}")]
    Execution(#[from] ExecutionError),

    #[error("Resource error: {0}")]
    Resource(#[from] ResourceError),

    #[error("Trust error: {0}")]
    Trust(#[from] TrustError),
}

#[derive(Debug, thiserror::Error)]
pub enum GraphError {
    #[error("Node '{0}' already exists")]
    DuplicateNode(String),

    #[error("Node '{0}' not found")]
    NodeNotFound(String),

    #[error("Connection creates invalid cycle between '{0}' and '{1}'")]
    InvalidCycle(String, String),

    #[error("Self-loop detected on node '{0}'")]
    SelfLoop(String),
}

#[derive(Debug, thiserror::Error)]
pub enum ScheduleError {
    #[error("Graph contains cycles (use enable_cycles=true for intentional cycles)")]
    UnexpectedCycles,

    #[error("Empty graph - no nodes to schedule")]
    EmptyGraph,
}

#[derive(Debug, thiserror::Error)]
pub enum ExecutionError {
    #[error("Node '{0}' execution failed: {1}")]
    NodeFailed(String, String),

    #[error("Execution timed out after {0}ms")]
    Timeout(u64),

    #[error("Resource limit exceeded: {0}")]
    ResourceExhausted(String),
}
```

## 7. Thread Safety Model

```rust
// WorkflowGraph is NOT Send/Sync by default
// It is single-threaded within one execution context
// Language SDK holds the reference and manages thread safety

// For parallel level execution, we use rayon scoped threads:
impl WorkflowGraph {
    fn execute_level_parallel(
        &self,
        level: &ExecutionLevel,
        executor: &dyn NodeExecutor,
        results: &Mutex<HashMap<NodeId, Value>>,
    ) -> Result<(), ExecutionError> {
        level.node_ids.par_iter().try_for_each(|node_id| {
            let inputs = self.prepare_inputs(node_id, &results.lock().unwrap())?;
            let output = executor.execute_node(node_id, &self.nodes[node_id].node_type, &inputs)?;
            results.lock().unwrap().insert(node_id.clone(), output);
            Ok(())
        })
    }
}
```

## 8. Build & Distribution

### 8.1 Build Targets

| Target                      | Platform    | Output                |
| --------------------------- | ----------- | --------------------- |
| `x86_64-unknown-linux-gnu`  | Linux x64   | `.so` / PyO3 wheel    |
| `aarch64-unknown-linux-gnu` | Linux ARM64 | `.so` / PyO3 wheel    |
| `x86_64-apple-darwin`       | macOS Intel | `.dylib` / PyO3 wheel |
| `aarch64-apple-darwin`      | macOS ARM   | `.dylib` / PyO3 wheel |
| `x86_64-pc-windows-msvc`    | Windows x64 | `.dll` / PyO3 wheel   |

### 8.2 CI Matrix

```yaml
# GitHub Actions matrix
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    rust: [stable, nightly]
    python: ["3.11", "3.12", "3.13"]
    include:
      - os: ubuntu-latest
        target: x86_64-unknown-linux-gnu
      - os: macos-latest
        target: aarch64-apple-darwin
```

### 8.3 Distribution

- **Python**: PyO3 wheel via `maturin build`, published to PyPI as `kailash-core`
- **Go**: Pre-built shared libraries bundled in Go module
- **Java**: JNI shared libraries bundled in Maven artifact
- **Standalone**: C header + shared library for other language bindings

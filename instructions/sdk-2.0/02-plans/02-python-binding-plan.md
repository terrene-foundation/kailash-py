# Python Binding Plan

## 1. Overview

The Python SDK is the reference implementation and the first language binding for the Rust core.
The migration must maintain **100% backward compatibility** with existing Python APIs while
switching the internal engine from pure Python (networkx) to Rust (PyO3 bindings).

## 2. PyO3 Integration

### 2.1 Module Structure

```
kailash-python/
+-- Cargo.toml
+-- src/
|   +-- lib.rs              # PyO3 module registration
|   +-- workflow.rs          # PyWorkflowGraph binding
|   +-- runtime.rs           # PyRuntime binding
|   +-- validation.rs        # PyValidation binding
|   +-- types.rs             # Python <-> Rust type conversions
|   +-- errors.rs            # Python exception mapping
+-- python/
    +-- kailash/
        +-- _rust/           # Rust extension module
        |   +-- __init__.pyi # Type stubs for IDE support
        +-- _compat.py       # Compatibility layer (networkx fallback)
```

### 2.2 PyO3 Module Definition

```rust
// kailash-python/src/lib.rs
use pyo3::prelude::*;

mod workflow;
mod runtime;
mod validation;
mod types;
mod errors;

/// Kailash Rust core extension module
#[pymodule]
fn _kailash_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<workflow::PyWorkflowGraph>()?;
    m.add_class::<runtime::PyExecutionResult>()?;
    m.add_class::<validation::PyValidationResult>()?;
    m.add_class::<runtime::PyNodeMetrics>()?;
    m.add_function(wrap_pyfunction!(runtime::execute_workflow, m)?)?;
    m.add_function(wrap_pyfunction!(validation::validate_workflow, m)?)?;
    Ok(())
}
```

### 2.3 Workflow Graph Binding

```rust
// kailash-python/src/workflow.rs
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use kailash_core::graph::{WorkflowGraph, NodeId, ConnectionInfo};

#[pyclass(name = "WorkflowGraph")]
pub struct PyWorkflowGraph {
    inner: WorkflowGraph,
}

#[pymethods]
impl PyWorkflowGraph {
    #[new]
    fn new(id: &str, name: &str) -> Self {
        Self {
            inner: WorkflowGraph::new(id, name),
        }
    }

    fn add_node(
        &mut self,
        node_id: &str,
        node_type: &str,
        config: &Bound<'_, PyAny>,
        is_async: bool,
    ) -> PyResult<()> {
        let config_json = pythonize::depythonize_bound(config.clone())?;
        self.inner
            .add_node(NodeId(node_id.to_string()), node_type, config_json, is_async)
            .map_err(|e| errors::to_py_error(e))
    }

    fn connect(
        &mut self,
        source_id: &str,
        source_output: &str,
        target_id: &str,
        target_input: &str,
    ) -> PyResult<()> {
        let conn = ConnectionInfo {
            source_output: source_output.to_string(),
            target_input: target_input.to_string(),
            is_cyclic: false,
            cycle_config: None,
        };
        self.inner
            .connect(
                &NodeId(source_id.to_string()),
                &NodeId(target_id.to_string()),
                conn,
            )
            .map_err(|e| errors::to_py_error(e))
    }

    fn topological_sort(&mut self) -> PyResult<Vec<String>> {
        self.inner
            .topological_sort()
            .map(|ids| ids.iter().map(|id| id.0.clone()).collect())
            .map_err(|e| errors::to_py_error(e))
    }

    fn compute_levels(&mut self, py: Python<'_>) -> PyResult<PyObject> {
        let schedule = self.inner
            .compute_schedule()
            .map_err(|e| errors::to_py_error(e))?;

        let result = PyList::empty(py);
        for level in &schedule.levels {
            let level_list = PyList::new(
                py,
                level.node_ids.iter().map(|id| id.0.as_str()),
            )?;
            result.append(level_list)?;
        }
        Ok(result.into())
    }

    fn has_cycles(&mut self) -> bool {
        self.inner.has_cycles()
    }

    fn node_count(&self) -> usize {
        self.inner.node_count()
    }

    fn validate(&self) -> PyResult<validation::PyValidationResult> {
        let result = self.inner.validate();
        Ok(validation::PyValidationResult::from(result))
    }

    fn predecessors(&self, node_id: &str) -> PyResult<Vec<(String, String, String)>> {
        self.inner
            .predecessors(&NodeId(node_id.to_string()))
            .map(|preds| {
                preds.iter().map(|(id, conn)| {
                    (id.0.clone(), conn.source_output.clone(), conn.target_input.clone())
                }).collect()
            })
            .map_err(|e| errors::to_py_error(e))
    }

    fn prepare_inputs(
        &self,
        py: Python<'_>,
        node_id: &str,
        results: &Bound<'_, PyDict>,
    ) -> PyResult<PyObject> {
        let results_json: serde_json::Value = pythonize::depythonize_bound(results.clone().into_any())?;
        let results_map = match results_json {
            serde_json::Value::Object(map) => {
                map.into_iter()
                    .map(|(k, v)| (NodeId(k), v))
                    .collect()
            }
            _ => HashMap::new(),
        };

        let inputs = self.inner
            .prepare_inputs(&NodeId(node_id.to_string()), &results_map)
            .map_err(|e| errors::to_py_error(e))?;

        pythonize::pythonize(py, &inputs)
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    }
}
```

## 3. Backward Compatibility

### 3.1 Strategy: Internal Swap, External Stability

The existing Python API surface (WorkflowBuilder, Workflow, LocalRuntime, AsyncLocalRuntime)
remains **unchanged**. Internally, these classes switch from networkx to Rust:

```python
# src/kailash/workflow/graph.py - MODIFIED

class Workflow:
    def __init__(self, workflow_id, name, ...):
        # BEFORE (v1.x):
        # self.graph = nx.DiGraph()

        # AFTER (v2.0):
        try:
            from kailash._rust import WorkflowGraph
            self._rust_graph = WorkflowGraph(workflow_id, name)
            self._use_rust = True
        except ImportError:
            # Fallback to networkx for development/debugging
            import networkx as nx
            self.graph = nx.DiGraph()
            self._use_rust = False
```

### 3.2 API Surface Preservation

Every method on these classes must continue to work identically:

| Class               | Method                     | Change Required                     |
| ------------------- | -------------------------- | ----------------------------------- |
| `WorkflowBuilder`   | `add_node()`               | Internal: route to Rust graph       |
| `WorkflowBuilder`   | `connect()`                | Internal: route to Rust graph       |
| `WorkflowBuilder`   | `build()`                  | Internal: build Rust graph          |
| `Workflow`          | `add_node()`               | Internal: delegate to `_rust_graph` |
| `Workflow`          | `connect()`                | Internal: delegate to `_rust_graph` |
| `Workflow`          | `validate()`               | Internal: use Rust validator        |
| `Workflow`          | `has_cycles()`             | Internal: use Rust cycle detection  |
| `LocalRuntime`      | `execute()`                | Internal: use Rust scheduler        |
| `AsyncLocalRuntime` | `execute_workflow_async()` | Internal: use Rust scheduler        |

### 3.3 networkx Compatibility Shim

For the transition period, we maintain a compatibility property:

```python
class Workflow:
    @property
    def graph(self):
        """Backward compatibility: return networkx-compatible view."""
        if self._use_rust:
            return _NetworkXCompat(self._rust_graph)
        return self._nx_graph

class _NetworkXCompat:
    """networkx-compatible read-only view over Rust graph."""

    def __init__(self, rust_graph):
        self._rust = rust_graph

    def predecessors(self, node_id):
        return [src for src, _, _ in self._rust.predecessors(node_id)]

    def successors(self, node_id):
        return [tgt for tgt, _, _ in self._rust.successors(node_id)]

    def __getitem__(self, node_id):
        # Return edge data dict for networkx compatibility
        return _EdgeDataView(self._rust, node_id)

    def nodes(self):
        return self._rust.node_ids()
```

## 4. Migration Phases

### 4.1 Phase A: Parallel Implementation (Month 1-2)

**Goal**: Rust core working alongside existing Python implementation.

**Tasks**:

1. Build `kailash-python` crate with PyO3 bindings
2. Create `kailash._rust` extension module
3. Implement `PyWorkflowGraph` with all graph operations
4. Add feature flag: `KAILASH_USE_RUST=1` to enable Rust backend
5. Write comparison tests: same workflow, both backends, same results

**Deliverable**: `pip install kailash[rust]` installs Rust extension

**Test criteria**:

```python
# Both backends must produce identical results
workflow_nx = build_test_workflow(backend="networkx")
workflow_rs = build_test_workflow(backend="rust")

results_nx, _ = runtime.execute(workflow_nx)
results_rs, _ = runtime.execute(workflow_rs)

assert results_nx == results_rs  # Exact match
```

### 4.2 Phase B: Feature Parity (Month 3-4)

**Goal**: Rust backend supports all features including cycles, conditional execution,
validation, and trust.

**Tasks**:

1. Implement cyclic workflow support in Rust
2. Implement conditional execution (skip_branches mode)
3. Implement connection validation (strict/warn/off)
4. Implement trust verification (CARE framework)
5. Implement resource limit checking
6. Port all validation rules to Rust

**Deliverable**: Feature flag can be enabled by default for CI

**Test criteria**:

```python
# Cyclic workflows produce same results
cyclic_wf_nx = build_cyclic_workflow(backend="networkx")
cyclic_wf_rs = build_cyclic_workflow(backend="rust")

# Conditional workflows produce same results
cond_wf_nx = build_conditional_workflow(backend="networkx")
cond_wf_rs = build_conditional_workflow(backend="rust")

# Validation produces same errors/warnings
assert validate(wf_nx) == validate(wf_rs)
```

### 4.3 Phase C: Switchover (Month 5)

**Goal**: Rust becomes the default backend. networkx becomes the fallback.

**Tasks**:

1. Set `KAILASH_USE_RUST=1` as default
2. Add deprecation warnings for networkx-specific usage
3. Update all documentation to reflect Rust backend
4. Remove networkx from required dependencies (move to optional)
5. Performance benchmarking and optimization

**Deliverable**: `pip install kailash` uses Rust by default

### 4.4 Phase D: Cleanup (Month 6)

**Goal**: Remove networkx dependency entirely.

**Tasks**:

1. Remove `_NetworkXCompat` shim
2. Remove all networkx imports and fallback code
3. Remove networkx from `pyproject.toml`
4. Final performance validation
5. SDK 2.0 release

**Deliverable**: kailash 2.0.0 release with pure Rust core

## 5. Performance Targets

### 5.1 Benchmark Suite

```python
# tests/benchmarks/test_rust_performance.py

import pytest
import time

@pytest.fixture(params=[10, 50, 100, 500, 1000])
def workflow_size(request):
    return request.param

def test_build_time(workflow_size, benchmark):
    """Build time should scale linearly with node count."""
    def build():
        wf = WorkflowBuilder()
        for i in range(workflow_size):
            wf.add_node("TestNode", f"node_{i}", {"value": i})
        for i in range(workflow_size - 1):
            wf.connect(f"node_{i}", "output", f"node_{i+1}", "input")
        return wf.build()

    benchmark(build)

def test_scheduling_time(workflow_size, benchmark):
    """Scheduling should be < 0.1ms for 20 nodes."""
    wf = build_linear_workflow(workflow_size)

    def schedule():
        runtime = LocalRuntime()
        return runtime._compute_execution_order(wf)

    benchmark(schedule)
```

### 5.2 Expected Improvements

| Metric                        | Python (v1.x) | Rust (v2.0)  | Improvement |
| ----------------------------- | ------------- | ------------ | ----------- |
| Build time (20 nodes)         | 20-60ms       | 2-5ms        | 10x         |
| Scheduling (20 nodes)         | 0.5-2ms       | 0.005-0.02ms | 100x        |
| Validation (20 nodes)         | 2-20ms        | 0.1-1ms      | 20x         |
| Cycle detection (20 nodes)    | 0.5-5ms       | 0.005-0.05ms | 100x        |
| Per-node overhead             | 1-3ms         | 0.3-1ms      | 3x          |
| Memory (20-node workflow)     | ~2MB          | ~200KB       | 10x         |
| Total SDK overhead (20 nodes) | 50-150ms      | 8-22ms       | 7x          |

### 5.3 Regression Prevention

```yaml
# .github/workflows/performance.yml
name: Performance Regression
on: [push, pull_request]
jobs:
  bench:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run benchmarks
        run: |
          cargo bench --package kailash-python -- --output-format bencher | tee output.txt
      - name: Compare with baseline
        uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: "cargo"
          output-file-path: output.txt
          alert-threshold: "120%" # Fail if 20% slower
          fail-on-alert: true
```

## 6. Framework Adaptation

### 6.1 DataFlow (No API Changes)

DataFlow uses `WorkflowBuilder` and `LocalRuntime`/`AsyncLocalRuntime`. Since these APIs
are preserved, DataFlow requires **zero code changes**:

```python
# DataFlow engine.py - UNCHANGED
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# This code works identically with both backends
workflow = WorkflowBuilder()
workflow.add_node("AsyncSQLDatabaseNode", "create_user", config)
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build())
```

### 6.2 Nexus (No API Changes)

Nexus uses `Workflow`, `WorkflowBuilder`, and gateway components. All preserved:

```python
# Nexus core.py - UNCHANGED
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.servers.gateway import create_gateway
```

### 6.3 Kaizen (No API Changes)

Kaizen agents inherit from `Node` and use `WorkflowBuilder`. All preserved:

```python
# Kaizen base_agent.py - UNCHANGED
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
```

## 7. Risk Mitigation

### 7.1 Risk: Behavior Differences

**Mitigation**: Extensive comparison test suite runs both backends on identical workflows
and asserts identical results. CI blocks merge if any difference detected.

### 7.2 Risk: PyO3 Build Failures on Some Platforms

**Mitigation**: Pre-built wheels for all major platforms (Linux x64/ARM64, macOS x64/ARM64,
Windows x64). Pure Python fallback if Rust extension can't be installed.

### 7.3 Risk: Performance Regression in Edge Cases

**Mitigation**: Criterion benchmarks in CI with 20% regression threshold. Profiling suite
covers all workflow patterns (linear, diamond, cyclic, conditional).

### 7.4 Risk: networkx Compatibility Breaking

**Mitigation**: Compatibility shim (`_NetworkXCompat`) maintained through Phase C.
Deprecation warnings guide users to updated APIs.

### 7.5 Risk: FFI Memory Leaks

**Mitigation**: PyO3 manages Python <-> Rust memory automatically. Integration tests with
`tracemalloc` verify no memory leaks over 10K workflow executions.

## 8. Testing Strategy

### 8.1 Test Categories

| Category      | Count | Purpose                      |
| ------------- | ----- | ---------------------------- |
| Unit (Rust)   | ~200  | Core algorithm correctness   |
| Unit (Python) | ~100  | Binding correctness          |
| Comparison    | ~50   | networkx vs Rust equivalence |
| Integration   | ~30   | Full workflow execution      |
| Performance   | ~20   | Regression detection         |
| Memory        | ~10   | Leak detection               |

### 8.2 Comparison Test Pattern

```python
@pytest.fixture(params=["networkx", "rust"])
def backend(request):
    if request.param == "rust":
        try:
            import kailash._rust
        except ImportError:
            pytest.skip("Rust extension not available")
    os.environ["KAILASH_BACKEND"] = request.param
    yield request.param

def test_linear_workflow(backend):
    wf = build_linear_workflow(20)
    runtime = LocalRuntime()
    results, run_id = runtime.execute(wf)
    assert len(results) == 20
    assert all(v is not None for v in results.values())
```

# Hot Path Analysis

## 1. Overview

This document profiles the per-workflow and per-node execution hot path in the Kailash Python
SDK. It identifies where CPU time is spent, estimates Python overhead, and quantifies what Rust
would improve.

## 2. Execution Hot Path

The critical path from `runtime.execute(workflow.build())` to completion:

```
WorkflowBuilder.build()          [PYTHON]  ~5-50ms
  +-- NodeRegistry.get()         [PYTHON]  ~0.1ms per node (dict lookup)
  +-- Node.__init__()            [PYTHON]  ~0.5-2ms per node (Pydantic + inspect)
  +-- nx.DiGraph.add_node()      [PYTHON/C] ~0.01ms per node
  +-- nx.DiGraph.add_edge()      [PYTHON/C] ~0.01ms per edge

LocalRuntime.execute()           [PYTHON]
  +-- _execute_async()           [PYTHON]  ~2ms overhead
  |   +-- resource_check()       [PYTHON]  ~1-5ms (psutil calls)
  |   +-- _check_workflow_access [PYTHON]  ~0.1ms
  |   +-- _process_params()      [PYTHON]  ~0.5ms
  |   +-- workflow.validate()    [PYTHON]  ~2-20ms (scales with nodes)
  |   +-- has_cycles()           [PYTHON]  ~0.5-5ms (networkx DFS)
  |
  +-- _execute_workflow_async()  [PYTHON]  ** HOT PATH **
      +-- nx.topological_sort()  [PYTHON/C] ~0.1-1ms
      +-- FOR EACH NODE:
          +-- _prepare_inputs()  [PYTHON]  ~0.5-2ms per node
          +-- DataTypeValidator  [PYTHON]  ~0.1ms per node
          +-- _verify_node_trust [PYTHON]  ~0.1ms per node
          +-- MetricsCollector   [PYTHON]  ~0.05ms per node
          +-- node.execute()     [VARIES]  1ms - 30sec (I/O bound)
          +-- detect_success()   [PYTHON]  ~0.05ms per node
          +-- result storage     [PYTHON]  ~0.01ms per node
```

## 3. Detailed Phase Analysis

### 3.1 Phase 1: Build Phase

**Source**: `workflow/builder.py:200-400` and `workflow/graph.py:81-250`

```python
# Hot spots in build phase:
# 1. Node class resolution via registry (dict lookup - fast)
node_class = NodeRegistry.get(node_type)  # graph.py:218

# 2. Node instance creation via reflection (SLOW)
sig = inspect.signature(node_class.__init__)  # graph.py:151
params = list(sig.parameters.keys())          # graph.py:152
node_instance = node_class(**config)          # graph.py:161

# 3. Pydantic validation in Node.__init__ (SLOW for complex nodes)
self._node_metadata = NodeMetadata(...)       # base.py:221-228
self._validate_config()                       # base.py (implicit)
```

**Estimated overhead per node**: 1-3ms

- `inspect.signature()`: ~0.3ms (cached after first call per class)
- `NodeMetadata` Pydantic construction: ~0.2ms
- Parameter filtering/validation: ~0.5ms
- Config dict operations: ~0.1ms

**For a 20-node workflow**: ~20-60ms in build phase

### 3.2 Phase 2: Pre-Execution Validation

**Source**: `runtime/local.py:1293-1435`

```python
# Resource limit checking (psutil calls are EXPENSIVE)
resource_check_results = self._resource_enforcer.check_all_limits()  # local.py:1330
# psutil.virtual_memory() + psutil.cpu_percent() = ~2-5ms

# Workflow validation
workflow.validate(runtime_parameters=processed_parameters)  # local.py:1400
# Iterates all nodes + connections, validates types = ~2-20ms

# Cycle detection
if self.enable_cycles and workflow.has_cycles():  # local.py:1434
# networkx DFS traversal = ~0.5-5ms depending on graph size
```

**Estimated overhead**: 5-30ms per execution

### 3.3 Phase 3: DAG Scheduling (Topological Sort)

**Source**: `runtime/local.py:1668-1674`

```python
execution_order = list(nx.topological_sort(workflow.graph))  # local.py:1669
```

This is networkx's Kahn's algorithm implementation. It operates on the networkx DiGraph
object which stores nodes and edges as Python dicts internally.

**Performance characteristics**:

- Time complexity: O(V + E) where V = nodes, E = edges
- For 20 nodes, 19 edges: ~0.1ms
- For 100 nodes, 200 edges: ~0.5ms
- For 1000 nodes, 2000 edges: ~5ms

The algorithm itself is fast, but the overhead is in Python dict iteration and object creation.
networkx stores everything as nested dicts (`{node: {neighbor: edge_data}}`).

### 3.4 Phase 4: Node Execution Loop (PRIMARY HOT PATH)

**Source**: `runtime/local.py:1692-1844`

This is where the SDK spends most of its time. For each node:

```python
for node_id in execution_order:                    # local.py:1692
    node_instance = workflow._node_instances.get(node_id)  # dict lookup

    # Input preparation (MOST OVERHEAD per iteration)
    inputs = self._prepare_node_inputs(...)         # local.py:1750
    # This involves:
    # - Iterating predecessor connections
    # - Extracting outputs from previous nodes
    # - Parameter mapping and injection
    # - Dict merging operations

    # Validation
    validated_inputs = DataTypeValidator.validate_node_input(node_id, inputs)

    # Trust verification
    node_trust_allowed = await self._verify_node_trust(...)

    # Metrics collection context manager
    with collector.collect(node_id=node_id) as metrics_context:
        # ACTUAL NODE EXECUTION
        if self.enable_async and hasattr(node_instance, "execute_async"):
            outputs = await node_instance.execute_async(**validated_inputs)
        else:
            outputs = node_instance.execute(**validated_inputs)

    # Result storage
    node_outputs[node_id] = outputs
    results[node_id] = outputs
```

**Per-node overhead breakdown** (excluding actual node execution):

| Operation                                 | Time       | Notes                             |
| ----------------------------------------- | ---------- | --------------------------------- |
| `_prepare_node_inputs()`                  | 0.5-2ms    | Dict iteration, parameter mapping |
| `DataTypeValidator.validate_node_input()` | 0.05-0.2ms | Type checking                     |
| `_verify_node_trust()`                    | 0.05-0.1ms | Trust context check               |
| `MetricsCollector.collect()`              | 0.05ms     | Context manager setup             |
| `detect_success()`                        | 0.05ms     | Result inspection                 |
| Dict storage                              | 0.01ms     | `node_outputs[id] = outputs`      |
| Task manager updates                      | 0.1-0.5ms  | Optional tracking                 |
| Logging                                   | 0.05ms     | Per-node log line                 |
| **Total per-node overhead**               | **~1-3ms** | **Without actual node work**      |

**For a 20-node workflow**: ~20-60ms overhead (not counting actual node execution)

### 3.5 Phase 5: Input Preparation Deep Dive

**Source**: `_prepare_node_inputs()` in `runtime/local.py`

This is the most expensive per-node operation:

```python
def _prepare_node_inputs(self, workflow, node_id, node_instance, node_outputs, parameters):
    inputs = {}

    # 1. Collect connected inputs (iterate predecessors)
    for pred in workflow.graph.predecessors(node_id):
        # Get edge data (connection mapping)
        edge_data = workflow.graph[pred][node_id]
        # Extract source output value
        source_output = node_outputs.get(pred, {})
        # Map source output field to target input field
        # ... dict operations ...

    # 2. Apply parameter overrides
    if parameters and node_id in parameters:
        node_params = parameters[node_id]
        inputs.update(node_params)

    # 3. Apply workflow-level parameters (WorkflowParameterInjector)
    # ... complex parameter resolution ...

    return inputs
```

**Key bottleneck**: `workflow.graph.predecessors(node_id)` returns a networkx iterator
over Python objects. Each predecessor lookup requires dict access into networkx's adjacency
structure.

## 4. AsyncLocalRuntime Parallel Execution Path

**Source**: `runtime/async_local.py`

AsyncLocalRuntime adds a workflow analysis phase before execution:

```python
# Analysis phase (additional overhead)
plan = self._analyze_workflow(workflow)        # ~1-5ms
# - Classify nodes as sync/async
# - Compute execution levels
# - Estimate parallelism potential

# Level-based execution
for level in plan.execution_levels:
    # Execute all nodes in level concurrently
    tasks = []
    for node_id in level.nodes:
        if node_id in plan.async_nodes:
            tasks.append(self._execute_node_async(node_id, ...))
        else:
            tasks.append(self._execute_node_in_thread(node_id, ...))
    await asyncio.gather(*tasks)
```

**Additional overhead**: 1-5ms for analysis, ~0.1ms per level for task creation.
**Benefit**: True parallelism for I/O-bound nodes.

## 5. What Rust Would Improve

### 5.1 DAG Data Structure (HIGH IMPACT)

Replace networkx DiGraph with a Rust DAG:

| Operation                     | Python (networkx) | Rust (petgraph) | Speedup |
| ----------------------------- | ----------------- | --------------- | ------- |
| Graph creation (20 nodes)     | ~2ms              | ~0.01ms         | 200x    |
| Topological sort (20 nodes)   | ~0.1ms            | ~0.001ms        | 100x    |
| Topological sort (1000 nodes) | ~5ms              | ~0.05ms         | 100x    |
| Cycle detection (20 nodes)    | ~0.5ms            | ~0.005ms        | 100x    |
| Predecessor lookup            | ~0.01ms           | ~0.001ms        | 10x     |
| Level computation             | ~0.5ms            | ~0.005ms        | 100x    |

**Total DAG improvement**: 10-100x for graph operations

### 5.2 Workflow Scheduling (HIGH IMPACT)

Replace Python execution loop scheduling with Rust:

| Operation                              | Python      | Rust          | Speedup |
| -------------------------------------- | ----------- | ------------- | ------- |
| Execution order computation            | ~0.5ms      | ~0.005ms      | 100x    |
| Level grouping (parallel)              | ~1ms        | ~0.01ms       | 100x    |
| Dependency checking                    | ~0.1ms/node | ~0.001ms/node | 100x    |
| Input routing (which outputs go where) | ~0.5ms/node | ~0.01ms/node  | 50x     |

### 5.3 Validation (MEDIUM IMPACT)

| Operation                      | Python      | Rust         | Speedup |
| ------------------------------ | ----------- | ------------ | ------- |
| Workflow structure validation  | ~2-20ms     | ~0.1-1ms     | 20x     |
| Connection contract validation | ~1-5ms      | ~0.1-0.5ms   | 10x     |
| Parameter type checking        | ~0.5ms/node | ~0.01ms/node | 50x     |

### 5.4 Resource Management (MEDIUM IMPACT)

| Operation          | Python (psutil) | Rust (sysinfo) | Speedup |
| ------------------ | --------------- | -------------- | ------- |
| Memory check       | ~2ms            | ~0.1ms         | 20x     |
| CPU check          | ~1ms            | ~0.05ms        | 20x     |
| Resource lifecycle | ~0.5ms          | ~0.05ms        | 10x     |

### 5.5 Trust Verification (LOW-MEDIUM IMPACT)

| Operation                  | Python | Rust       | Speedup |
| -------------------------- | ------ | ---------- | ------- |
| Cryptographic verification | ~1-5ms | ~0.1-0.5ms | 10x     |
| Trust chain traversal      | ~0.5ms | ~0.05ms    | 10x     |
| Posture calculation        | ~0.2ms | ~0.02ms    | 10x     |

## 6. Overhead Budget

### 6.1 Current Python Overhead (20-node workflow)

| Phase                        | Time          | % of Total |
| ---------------------------- | ------------- | ---------- |
| Build phase                  | 20-60ms       | 15-25%     |
| Pre-execution validation     | 5-30ms        | 5-15%      |
| DAG scheduling               | 0.5-2ms       | <1%        |
| Per-node overhead (20 nodes) | 20-60ms       | 15-25%     |
| Actual node execution        | 50ms-300sec   | 50-99%     |
| **Total Python overhead**    | **~50-150ms** |            |

### 6.2 Projected Rust Core Overhead (20-node workflow)

| Phase                                                | Time         | Improvement     |
| ---------------------------------------------------- | ------------ | --------------- |
| Build phase (FFI + Rust DAG)                         | 2-5ms        | 10-12x          |
| Pre-execution validation (Rust)                      | 0.5-2ms      | 10-15x          |
| DAG scheduling (Rust)                                | 0.005-0.02ms | 100x            |
| Per-node overhead (Rust scheduling, Python callback) | 5-15ms       | 4x              |
| Actual node execution                                | Same         | No change       |
| **Total Rust overhead**                              | **~8-22ms**  | **~7x overall** |

Note: The per-node overhead improvement is limited because each node execution still
crosses the FFI boundary (Rust -> Python callback -> Rust).

### 6.3 Where Rust Does NOT Help

1. **Actual node execution**: Nodes perform I/O (SQL queries, HTTP calls, LLM inference).
   This dominates total time and is unaffected by Rust.
2. **FFI crossing cost**: Each Python callback adds ~0.01-0.05ms overhead per call.
3. **Python object creation**: Input/output dicts must be created in Python for nodes.
4. **Framework-layer overhead**: DataFlow/Nexus/Kaizen logic stays in Python.

## 7. Profiling Recommendations for SDK 2.0

### 7.1 Benchmark Workflow Suite

Create standardized benchmark workflows:

1. **Linear-10**: 10 nodes in sequence (measures per-node overhead)
2. **Linear-100**: 100 nodes in sequence (measures scaling)
3. **Diamond-20**: 20 nodes with diamond patterns (measures parallel potential)
4. **Cyclic-5**: 5-node cycle with convergence (measures cycle overhead)
5. **DataFlow-CRUD**: Standard CRUD workflow (real-world baseline)
6. **Nexus-API**: Multi-channel API workflow (real-world baseline)

### 7.2 Key Metrics to Track

| Metric                        | Target   |
| ----------------------------- | -------- |
| Build time (20 nodes)         | < 5ms    |
| Scheduling time (20 nodes)    | < 0.1ms  |
| Per-node overhead             | < 0.5ms  |
| Total SDK overhead (20 nodes) | < 20ms   |
| FFI crossing cost             | < 0.05ms |
| Memory per workflow           | < 1MB    |
| Memory per 1000 nodes         | < 50MB   |

### 7.3 Profiling Tools

- **Python side**: `cProfile`, `line_profiler`, `py-spy` for flamegraphs
- **Rust side**: `criterion` for benchmarks, `perf` for system profiling
- **FFI boundary**: Custom timing instrumentation at PyO3 boundary
- **End-to-end**: `hyperfine` for CLI benchmarks

## 8. Optimization Priority Matrix

| Optimization                    | Impact     | Effort | Priority |
| ------------------------------- | ---------- | ------ | -------- |
| Rust DAG (replace networkx)     | High       | Medium | P0       |
| Rust scheduler                  | High       | Medium | P0       |
| Rust validation                 | Medium     | Low    | P1       |
| Rust resource management        | Medium     | Low    | P1       |
| Rust trust verification         | Low-Medium | Medium | P2       |
| Reduce per-node Python overhead | Medium     | High   | P2       |
| FFI-optimized data passing      | Medium     | High   | P2       |

The highest-impact, most tractable optimization is replacing networkx with a Rust DAG
and moving the scheduling loop to Rust. This addresses the primary overhead source while
keeping node execution in Python via callbacks.

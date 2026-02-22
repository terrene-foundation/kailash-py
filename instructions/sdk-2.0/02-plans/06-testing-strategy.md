# Testing Strategy

## 1. Overview

This document defines the comprehensive testing strategy for Kailash SDK 2.0 across all three
language SDKs (Python, Go, Java) and the shared Rust core. The strategy covers cross-language
equivalence testing, FFI boundary testing, performance benchmarks, property-based testing,
and CI integration.

The core principle: **the same workflow definition must produce the same execution results
regardless of which language SDK runs it.** The Rust core guarantees this for scheduling,
validation, and cycle detection. Each language SDK must prove equivalence through a shared
test corpus.

## 2. Test Architecture

### 2.1 Testing Layers

```
+-------------------------------------------------------------------+
|                    Layer 5: Cross-Language E2E                      |
|        Same workflow JSON -> Python/Go/Java -> same output         |
+-------------------------------------------------------------------+
|                    Layer 4: Framework Integration                   |
|   DataFlow CRUD, Nexus API, Kaizen Agent (per-language, real I/O) |
+-------------------------------------------------------------------+
|                    Layer 3: SDK Integration                         |
|      WorkflowBuilder -> Runtime -> Node callback -> Results        |
+-------------------------------------------------------------------+
|                    Layer 2: FFI Boundary                            |
|        PyO3 / CGo / JNI correctness, memory safety, errors        |
+-------------------------------------------------------------------+
|                    Layer 1: Rust Core Unit                          |
|      Graph, Scheduler, Validator, Cycles, Trust, Resources         |
+-------------------------------------------------------------------+
```

### 2.2 Test Volume Targets

| Layer                     | Rust | Python | Go   | Java | Total |
| ------------------------- | ---- | ------ | ---- | ---- | ----- |
| L1: Rust Core Unit        | 400+ | -      | -    | -    | 400+  |
| L2: FFI Boundary          | 50   | 100    | 100  | 100  | 350   |
| L3: SDK Integration       | -    | 150    | 150  | 150  | 450   |
| L4: Framework Integration | -    | 100    | 80   | 80   | 260   |
| L5: Cross-Language E2E    | -    | shared | test | pool | 100+  |
| **Total**                 | 450  | 350+   | 330+ | 330+ | ~1560 |

## 3. Layer 1: Rust Core Unit Tests

### 3.1 Graph Module Tests

```rust
// kailash-core/src/graph/tests.rs

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // -- Construction Tests --

    #[test]
    fn test_empty_graph() {
        let graph = WorkflowGraph::new("test", "Test Workflow");
        assert_eq!(graph.node_count(), 0);
        assert_eq!(graph.edge_count(), 0);
        assert!(!graph.has_cycles());
    }

    #[test]
    fn test_add_single_node() {
        let mut graph = WorkflowGraph::new("test", "Test");
        let result = graph.add_node(
            NodeId("n1".to_string()),
            "TestNode",
            json!({"value": 42}),
            false,
        );
        assert!(result.is_ok());
        assert_eq!(graph.node_count(), 1);
    }

    #[test]
    fn test_duplicate_node_id_returns_error() {
        let mut graph = WorkflowGraph::new("test", "Test");
        graph.add_node(NodeId("n1".into()), "TestNode", json!({}), false).unwrap();
        let result = graph.add_node(NodeId("n1".into()), "TestNode", json!({}), false);
        assert!(matches!(result, Err(GraphError::DuplicateNode(_))));
    }

    #[test]
    fn test_connect_nonexistent_source_returns_error() {
        let mut graph = WorkflowGraph::new("test", "Test");
        graph.add_node(NodeId("n1".into()), "TestNode", json!({}), false).unwrap();
        let result = graph.connect(
            &NodeId("missing".into()),
            &NodeId("n1".into()),
            ConnectionInfo::simple("output", "input"),
        );
        assert!(matches!(result, Err(GraphError::NodeNotFound(_))));
    }

    #[test]
    fn test_self_loop_returns_error() {
        let mut graph = WorkflowGraph::new("test", "Test");
        graph.add_node(NodeId("n1".into()), "TestNode", json!({}), false).unwrap();
        let result = graph.connect(
            &NodeId("n1".into()),
            &NodeId("n1".into()),
            ConnectionInfo::simple("output", "input"),
        );
        assert!(matches!(result, Err(GraphError::SelfLoop(_))));
    }

    // -- Topological Sort Tests --

    #[test]
    fn test_topological_sort_linear_chain() {
        let mut graph = build_linear_graph(5);
        let order = graph.topological_sort().unwrap();
        // Verify each node appears before its successors
        for i in 0..order.len() - 1 {
            let pos_current = order.iter().position(|id| id.0 == format!("n{}", i)).unwrap();
            let pos_next = order.iter().position(|id| id.0 == format!("n{}", i + 1)).unwrap();
            assert!(pos_current < pos_next);
        }
    }

    #[test]
    fn test_topological_sort_diamond() {
        // n0 -> n1, n0 -> n2, n1 -> n3, n2 -> n3
        let mut graph = build_diamond_graph();
        let order = graph.topological_sort().unwrap();
        assert_eq!(order.first().unwrap().0, "n0"); // n0 must be first
        assert_eq!(order.last().unwrap().0, "n3");  // n3 must be last
    }

    #[test]
    fn test_topological_sort_empty_graph_returns_error() {
        let mut graph = WorkflowGraph::new("test", "Test");
        let result = graph.topological_sort();
        assert!(matches!(result, Err(ScheduleError::EmptyGraph)));
    }

    // -- Cycle Detection Tests --

    #[test]
    fn test_acyclic_graph_has_no_cycles() {
        let mut graph = build_linear_graph(10);
        assert!(!graph.has_cycles());
    }

    #[test]
    fn test_cycle_detection_finds_simple_cycle() {
        let mut graph = build_cyclic_graph();
        assert!(graph.has_cycles());
        let cycles = graph.detect_cycles();
        assert!(!cycles.is_empty());
    }

    // -- Level Computation Tests --

    #[test]
    fn test_level_computation_linear() {
        let mut graph = build_linear_graph(5);
        let schedule = graph.compute_schedule().unwrap();
        // Linear graph: each node is its own level
        assert_eq!(schedule.levels.len(), 5);
        for level in &schedule.levels {
            assert_eq!(level.node_ids.len(), 1);
        }
    }

    #[test]
    fn test_level_computation_wide_graph() {
        // n0 -> [n1, n2, n3, n4] -> n5
        let mut graph = build_wide_graph(4);
        let schedule = graph.compute_schedule().unwrap();
        // Level 0: n0, Level 1: [n1,n2,n3,n4], Level 2: n5
        assert_eq!(schedule.levels.len(), 3);
        assert_eq!(schedule.levels[1].node_ids.len(), 4);
        assert!(schedule.can_parallelize);
    }

    // -- Cache Invalidation Tests --

    #[test]
    fn test_cache_invalidated_on_add_node() {
        let mut graph = build_linear_graph(3);
        let order1 = graph.topological_sort().unwrap().to_vec();

        graph.add_node(NodeId("new".into()), "TestNode", json!({}), false).unwrap();
        graph.connect(
            &NodeId("n2".into()),
            &NodeId("new".into()),
            ConnectionInfo::simple("out", "in"),
        ).unwrap();

        let order2 = graph.topological_sort().unwrap().to_vec();
        assert_eq!(order2.len(), order1.len() + 1);
        assert_eq!(order2.last().unwrap().0, "new");
    }

    #[test]
    fn test_cache_invalidated_on_remove_node() {
        let mut graph = build_linear_graph(5);
        let _ = graph.topological_sort().unwrap(); // prime cache

        graph.remove_node(&NodeId("n4".into())).unwrap();
        let order = graph.topological_sort().unwrap();
        assert_eq!(order.len(), 4);
    }
}
```

### 3.2 Validation Module Tests

```rust
// kailash-core/src/validation/tests.rs

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_workflow_passes() {
        let graph = build_valid_linear_graph(5);
        let result = graph.validate();
        assert!(result.is_valid);
        assert!(result.errors.is_empty());
    }

    #[test]
    fn test_orphan_node_detected() {
        let mut graph = WorkflowGraph::new("test", "Test");
        graph.add_node(NodeId("n1".into()), "TestNode", json!({}), false).unwrap();
        graph.add_node(NodeId("n2".into()), "TestNode", json!({}), false).unwrap();
        // n1 and n2 are not connected
        let result = graph.validate();
        assert!(!result.warnings.is_empty());
        assert!(result.warnings.iter().any(|w| w.code == "VAL_ORPHAN_NODE"));
    }

    #[test]
    fn test_disconnected_subgraph_warning() {
        let mut graph = WorkflowGraph::new("test", "Test");
        // Subgraph 1: n1 -> n2
        graph.add_node(NodeId("n1".into()), "A", json!({}), false).unwrap();
        graph.add_node(NodeId("n2".into()), "B", json!({}), false).unwrap();
        graph.connect(&NodeId("n1".into()), &NodeId("n2".into()),
            ConnectionInfo::simple("out", "in")).unwrap();
        // Subgraph 2: n3 -> n4
        graph.add_node(NodeId("n3".into()), "A", json!({}), false).unwrap();
        graph.add_node(NodeId("n4".into()), "B", json!({}), false).unwrap();
        graph.connect(&NodeId("n3".into()), &NodeId("n4".into()),
            ConnectionInfo::simple("out", "in")).unwrap();

        let result = graph.validate();
        assert!(result.warnings.iter().any(|w| w.code == "VAL_DISCONNECTED"));
    }

    #[test]
    fn test_strict_validation_rejects_cycles() {
        let mut graph = build_cyclic_graph();
        let config = ValidationConfig {
            check_cycles: true,
            strict_mode: true,
            ..Default::default()
        };
        let result = graph.validate_with_config(&config);
        assert!(!result.is_valid);
        assert!(result.errors.iter().any(|e| e.code == "VAL_UNEXPECTED_CYCLE"));
    }

    #[test]
    fn test_empty_graph_validation() {
        let graph = WorkflowGraph::new("test", "Test");
        let result = graph.validate();
        assert!(result.is_valid);
        assert!(result.warnings.iter().any(|w| w.code == "VAL_EMPTY_GRAPH"));
    }
}
```

### 3.3 Test Coverage Targets

| Rust Module | Target Coverage | Critical Paths                              |
| ----------- | --------------- | ------------------------------------------- |
| graph/      | 95%             | All mutation operations, cache invalidation |
| scheduler/  | 95%             | Topological sort, level computation         |
| cycles/     | 90%             | SCC detection, iteration limits             |
| validation/ | 90%             | All validation rules                        |
| resources/  | 85%             | Limit checking, lifecycle                   |
| trust/      | 90%             | Chain verification, posture computation     |
| error.rs    | 100%            | All error variants                          |
| types.rs    | 95%             | All type conversions                        |

## 4. Layer 2: FFI Boundary Tests

### 4.1 PyO3 Boundary Tests

```python
# tests/ffi/test_pyo3_boundary.py

import pytest
import tracemalloc
import gc


class TestPyO3GraphOperations:
    """Verify PyO3 bindings correctly translate Python calls to Rust."""

    def test_create_graph_returns_valid_handle(self):
        from kailash._rust import WorkflowGraph
        graph = WorkflowGraph("test", "Test")
        assert graph.node_count() == 0

    def test_add_node_with_complex_config(self):
        from kailash._rust import WorkflowGraph
        graph = WorkflowGraph("test", "Test")
        config = {
            "connection_string": "sqlite:///test.db",
            "query": "SELECT * FROM users",
            "nested": {"key": [1, 2, 3]},
            "null_value": None,
            "float_value": 3.14,
        }
        graph.add_node("n1", "SQLNode", config, False)
        assert graph.node_count() == 1

    def test_unicode_node_ids(self):
        from kailash._rust import WorkflowGraph
        graph = WorkflowGraph("test", "Test")
        graph.add_node("node_\u00e9\u00e8\u00ea", "TestNode", {}, False)
        assert graph.node_count() == 1

    def test_large_config_crossing_ffi(self):
        from kailash._rust import WorkflowGraph
        graph = WorkflowGraph("test", "Test")
        # 1MB JSON config
        large_config = {"data": "x" * (1024 * 1024)}
        graph.add_node("n1", "TestNode", large_config, False)
        assert graph.node_count() == 1

    def test_error_propagation_from_rust(self):
        from kailash._rust import WorkflowGraph
        graph = WorkflowGraph("test", "Test")
        graph.add_node("n1", "TestNode", {}, False)
        with pytest.raises(RuntimeError, match="already exists"):
            graph.add_node("n1", "TestNode", {}, False)

    def test_none_config_raises_type_error(self):
        from kailash._rust import WorkflowGraph
        graph = WorkflowGraph("test", "Test")
        with pytest.raises(TypeError):
            graph.add_node("n1", "TestNode", None, False)


class TestPyO3MemorySafety:
    """Verify no memory leaks across the PyO3 FFI boundary."""

    def test_graph_cleanup_on_del(self):
        tracemalloc.start()
        from kailash._rust import WorkflowGraph

        snapshot1 = tracemalloc.take_snapshot()
        for _ in range(1000):
            graph = WorkflowGraph("test", "Test")
            for j in range(100):
                graph.add_node(f"n{j}", "TestNode", {"v": j}, False)
            del graph

        gc.collect()
        snapshot2 = tracemalloc.take_snapshot()

        # Memory should not grow unboundedly
        stats = snapshot2.compare_to(snapshot1, "lineno")
        total_increase = sum(s.size_diff for s in stats if s.size_diff > 0)
        # Allow 10MB max growth for 1000 iterations of 100-node graphs
        assert total_increase < 10 * 1024 * 1024, (
            f"Potential memory leak: {total_increase / 1024 / 1024:.1f}MB growth"
        )
        tracemalloc.stop()

    def test_no_leak_across_10k_executions(self):
        tracemalloc.start()
        from kailash._rust import WorkflowGraph

        for i in range(10_000):
            graph = WorkflowGraph(f"run_{i}", "bench")
            graph.add_node("start", "TestNode", {}, False)
            graph.add_node("end", "TestNode", {}, False)
            graph.connect("start", "output", "end", "input")
            _ = graph.topological_sort()

        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        # Peak should not exceed 50MB for 10K simple workflows
        assert peak < 50 * 1024 * 1024


class TestPyO3CallbackSafety:
    """Verify callback mechanism handles edge cases safely."""

    def test_callback_exception_propagates(self):
        """Python exception in callback must propagate to Rust and back."""
        from kailash._rust import WorkflowGraph

        graph = WorkflowGraph("test", "Test")
        graph.add_node("n1", "TestNode", {}, False)

        def failing_callback(node_id, inputs):
            raise ValueError("intentional failure")

        with pytest.raises(ValueError, match="intentional failure"):
            graph.execute(failing_callback)

    def test_callback_with_large_return_value(self):
        """Callbacks returning large data must not corrupt memory."""
        from kailash._rust import WorkflowGraph

        graph = WorkflowGraph("test", "Test")
        graph.add_node("n1", "TestNode", {}, False)

        def large_output_callback(node_id, inputs):
            return {"data": list(range(100_000))}

        result = graph.execute(large_output_callback)
        assert len(result["n1"]["data"]) == 100_000

    def test_callback_returning_none(self):
        """Callback returning None must be handled gracefully."""
        from kailash._rust import WorkflowGraph

        graph = WorkflowGraph("test", "Test")
        graph.add_node("n1", "TestNode", {}, False)

        def none_callback(node_id, inputs):
            return None

        # Should either succeed with None result or raise a clear error
        try:
            result = graph.execute(none_callback)
            assert result["n1"] is None
        except RuntimeError as e:
            assert "null" in str(e).lower() or "none" in str(e).lower()
```

### 4.2 CGo Boundary Tests

```go
// internal/ffi/ffi_test.go

package ffi

import (
    "encoding/json"
    "fmt"
    "runtime"
    "sync"
    "testing"
)

func TestNewWorkflowReturnsValidHandle(t *testing.T) {
    h, err := NewWorkflow("test", "Test")
    if err != nil {
        t.Fatalf("NewWorkflow failed: %v", err)
    }
    defer h.Close()
}

func TestAddNodeWithComplexConfig(t *testing.T) {
    h, _ := NewWorkflow("test", "Test")
    defer h.Close()

    config, _ := json.Marshal(map[string]interface{}{
        "connection_string": "sqlite:///test.db",
        "nested":           map[string]interface{}{"key": []int{1, 2, 3}},
        "null_value":       nil,
    })

    err := h.AddNode("n1", "SQLNode", config, false)
    if err != nil {
        t.Fatalf("AddNode failed: %v", err)
    }
}

func TestDuplicateNodeReturnsError(t *testing.T) {
    h, _ := NewWorkflow("test", "Test")
    defer h.Close()

    h.AddNode("n1", "TestNode", []byte("{}"), false)
    err := h.AddNode("n1", "TestNode", []byte("{}"), false)
    if err == nil {
        t.Fatal("expected error for duplicate node")
    }
}

func TestTopologicalSortLinearChain(t *testing.T) {
    h, _ := NewWorkflow("test", "Test")
    defer h.Close()

    for i := 0; i < 5; i++ {
        h.AddNode(fmt.Sprintf("n%d", i), "TestNode", []byte("{}"), false)
    }
    for i := 0; i < 4; i++ {
        h.Connect(fmt.Sprintf("n%d", i), "out", fmt.Sprintf("n%d", i+1), "in")
    }

    order, err := h.TopologicalSort()
    if err != nil {
        t.Fatalf("TopologicalSort failed: %v", err)
    }
    if len(order) != 5 {
        t.Fatalf("expected 5 nodes, got %d", len(order))
    }
    if order[0] != "n0" || order[4] != "n4" {
        t.Fatalf("unexpected order: %v", order)
    }
}

func TestCGoMemorySafety(t *testing.T) {
    // Create and destroy many workflows to detect leaks
    var m1, m2 runtime.MemStats
    runtime.ReadMemStats(&m1)

    for i := 0; i < 10000; i++ {
        h, _ := NewWorkflow(fmt.Sprintf("test_%d", i), "Test")
        for j := 0; j < 10; j++ {
            h.AddNode(fmt.Sprintf("n%d", j), "TestNode", []byte("{}"), false)
        }
        h.Close()
    }

    runtime.GC()
    runtime.ReadMemStats(&m2)

    // Heap should not grow by more than 50MB
    growth := int64(m2.HeapAlloc) - int64(m1.HeapAlloc)
    if growth > 50*1024*1024 {
        t.Fatalf("potential memory leak: %dMB growth", growth/(1024*1024))
    }
}

func TestConcurrentCGoAccess(t *testing.T) {
    // Verify thread safety of CGo calls from multiple goroutines
    var wg sync.WaitGroup
    errors := make(chan error, 100)

    for i := 0; i < 100; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            h, err := NewWorkflow(fmt.Sprintf("test_%d", id), "Test")
            if err != nil {
                errors <- err
                return
            }
            defer h.Close()

            for j := 0; j < 10; j++ {
                err := h.AddNode(fmt.Sprintf("n%d", j), "TestNode", []byte("{}"), false)
                if err != nil {
                    errors <- err
                    return
                }
            }

            _, err = h.TopologicalSort()
            if err != nil {
                errors <- err
            }
        }(i)
    }

    wg.Wait()
    close(errors)

    for err := range errors {
        t.Errorf("concurrent access error: %v", err)
    }
}
```

### 4.3 JNI Boundary Tests

```java
// kailash-core/src/test/java/com/kailash/core/NativeLibTest.java

package com.kailash.core;

import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;

class NativeLibTest {

    @Test
    void createWorkflowReturnsNonZeroHandle() {
        long handle = NativeLib.createWorkflow("test", "Test");
        assertTrue(handle != 0, "Handle must be non-zero");
        NativeLib.freeWorkflow(handle);
    }

    @Test
    void addNodeSucceeds() {
        long handle = NativeLib.createWorkflow("test", "Test");
        int result = NativeLib.addNode(handle, "n1", "TestNode", "{}", false);
        assertEquals(0, result, "addNode should return 0 on success");
        NativeLib.freeWorkflow(handle);
    }

    @Test
    void duplicateNodeReturnsError() {
        long handle = NativeLib.createWorkflow("test", "Test");
        NativeLib.addNode(handle, "n1", "TestNode", "{}", false);
        int result = NativeLib.addNode(handle, "n1", "TestNode", "{}", false);
        assertNotEquals(0, result, "Duplicate node should return error code");
        NativeLib.freeWorkflow(handle);
    }

    @Test
    void topologicalSortLinearChain() {
        long handle = NativeLib.createWorkflow("test", "Test");
        for (int i = 0; i < 5; i++) {
            NativeLib.addNode(handle, "n" + i, "TestNode", "{}", false);
        }
        for (int i = 0; i < 4; i++) {
            NativeLib.connect(handle, "n" + i, "out", "n" + (i + 1), "in");
        }

        String orderJson = NativeLib.topologicalSort(handle);
        assertNotNull(orderJson);
        NativeLib.freeWorkflow(handle);
    }

    @Test
    void memoryCleanupUnderLoad() {
        // Create and destroy 10K workflows
        for (int i = 0; i < 10_000; i++) {
            long handle = NativeLib.createWorkflow("test_" + i, "Test");
            for (int j = 0; j < 10; j++) {
                NativeLib.addNode(handle, "n" + j, "TestNode", "{}", false);
            }
            NativeLib.freeWorkflow(handle);
        }
        // Reaching this point without SIGSEGV/OutOfMemoryError means success
    }

    @Test
    void concurrentJniAccess() throws InterruptedException {
        int threadCount = 50;
        Thread[] threads = new Thread[threadCount];
        boolean[] success = new boolean[threadCount];

        for (int i = 0; i < threadCount; i++) {
            final int id = i;
            threads[i] = new Thread(() -> {
                try {
                    long handle = NativeLib.createWorkflow("test_" + id, "Test");
                    for (int j = 0; j < 10; j++) {
                        NativeLib.addNode(handle, "n" + j, "TestNode", "{}", false);
                    }
                    String order = NativeLib.topologicalSort(handle);
                    NativeLib.freeWorkflow(handle);
                    success[id] = order != null;
                } catch (Exception e) {
                    success[id] = false;
                }
            });
            threads[i].start();
        }

        for (Thread t : threads) t.join();
        for (int i = 0; i < threadCount; i++) {
            assertTrue(success[i], "Thread " + i + " failed");
        }
    }
}
```

## 5. Layer 3: SDK Integration Tests

### 5.1 Python Integration Tests

```python
# tests/integration/test_rust_integration.py

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime, AsyncLocalRuntime


class TestWorkflowBuilderIntegration:
    """Verify WorkflowBuilder -> Rust graph -> Runtime pipeline."""

    def test_linear_workflow_execution(self):
        workflow = WorkflowBuilder()
        for i in range(5):
            workflow.add_node("PassthroughNode", f"node_{i}", {"value": i})
        for i in range(4):
            workflow.connect(f"node_{i}", "output", f"node_{i+1}", "input")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())
        assert len(results) == 5
        assert run_id is not None

    def test_diamond_workflow_execution(self):
        workflow = WorkflowBuilder()
        workflow.add_node("SplitNode", "start", {"data": "test"})
        workflow.add_node("TransformNode", "branch_a", {"transform": "upper"})
        workflow.add_node("TransformNode", "branch_b", {"transform": "lower"})
        workflow.add_node("MergeNode", "end", {})
        workflow.connect("start", "output_a", "branch_a", "input")
        workflow.connect("start", "output_b", "branch_b", "input")
        workflow.connect("branch_a", "output", "end", "input_a")
        workflow.connect("branch_b", "output", "end", "input_b")

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        assert "end" in results

    @pytest.mark.asyncio
    async def test_async_runtime_parallel_execution(self):
        workflow = WorkflowBuilder()
        workflow.add_node("SlowNode", "start", {"delay": 0.01})
        for i in range(4):
            workflow.add_node("SlowNode", f"parallel_{i}", {"delay": 0.01})
        workflow.add_node("MergeNode", "end", {})
        for i in range(4):
            workflow.connect("start", "output", f"parallel_{i}", "input")
            workflow.connect(f"parallel_{i}", "output", "end", f"input_{i}")

        runtime = AsyncLocalRuntime(max_concurrent_nodes=4)
        results, _ = await runtime.execute_workflow_async(workflow.build())
        assert len(results) == 6

    def test_validation_before_execution(self):
        workflow = WorkflowBuilder()
        workflow.add_node("TestNode", "n1", {})
        built = workflow.build()
        validation = built.validate()
        # Validation should complete without exceptions

    def test_cyclic_workflow_with_convergence(self):
        workflow = WorkflowBuilder()
        workflow.add_node("IncrementNode", "counter", {"initial": 0})
        workflow.add_node("CheckNode", "checker", {"threshold": 5})
        workflow.connect("counter", "value", "checker", "input")
        workflow.connect("checker", "loop_back", "counter", "input",
                        cyclic=True, max_iterations=10)

        runtime = LocalRuntime(enable_cycles=True)
        results, _ = runtime.execute(workflow.build())
        assert results["checker"]["converged"] is True
```

### 5.2 Go Integration Tests

```go
// runtime/runtime_test.go

func TestLinearWorkflowExecution(t *testing.T) {
    builder := workflow.NewBuilder("test", "Linear")
    for i := 0; i < 5; i++ {
        builder.AddNode("PassthroughNode", fmt.Sprintf("node_%d", i),
            map[string]interface{}{"value": i})
    }
    for i := 0; i < 4; i++ {
        builder.Connect(fmt.Sprintf("node_%d", i), "output",
            fmt.Sprintf("node_%d", i+1), "input")
    }

    wf, err := builder.Build()
    require.NoError(t, err)

    rt := runtime.NewLocalRuntime()
    result, err := rt.Execute(wf)
    require.NoError(t, err)
    assert.Len(t, result.Results, 5)
    assert.NotEmpty(t, result.RunID)
}

func TestAsyncRuntimeParallelExecution(t *testing.T) {
    builder := workflow.NewBuilder("test", "Parallel")
    builder.AddNode("StartNode", "start", nil)
    for i := 0; i < 4; i++ {
        builder.AddAsyncNode("SlowNode", fmt.Sprintf("p%d", i),
            map[string]interface{}{"delay_ms": 10})
    }
    builder.AddNode("MergeNode", "end", nil)
    for i := 0; i < 4; i++ {
        builder.Connect("start", "output", fmt.Sprintf("p%d", i), "input")
        builder.Connect(fmt.Sprintf("p%d", i), "output", "end", fmt.Sprintf("in_%d", i))
    }

    wf, err := builder.Build()
    require.NoError(t, err)

    rt := runtime.NewAsyncRuntime(runtime.WithMaxConcurrency(4))
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    result, err := rt.ExecuteCtx(ctx, wf)
    require.NoError(t, err)
    assert.Len(t, result.Results, 6)
}

func TestContextCancellationStopsExecution(t *testing.T) {
    builder := workflow.NewBuilder("test", "Cancellable")
    for i := 0; i < 10; i++ {
        builder.AddNode("SlowNode", fmt.Sprintf("n%d", i),
            map[string]interface{}{"delay_ms": 100})
        if i > 0 {
            builder.Connect(fmt.Sprintf("n%d", i-1), "out", fmt.Sprintf("n%d", i), "in")
        }
    }

    wf, _ := builder.Build()
    rt := runtime.NewLocalRuntime()

    ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
    defer cancel()

    _, err := rt.ExecuteCtx(ctx, wf)
    assert.ErrorIs(t, err, context.DeadlineExceeded)
}
```

## 6. Layer 5: Cross-Language Equivalence Tests

### 6.1 Shared Workflow Corpus

All language SDKs share a corpus of workflow definitions stored as JSON. Each SDK must
execute these workflows and produce identical results.

```
testdata/workflows/
+-- linear/
|   +-- linear_5.json             # 5-node linear chain
|   +-- linear_20.json            # 20-node linear chain
|   +-- linear_100.json           # 100-node linear chain
+-- diamond/
|   +-- diamond_basic.json        # 4-node diamond
|   +-- diamond_deep.json         # 8-node nested diamond
|   +-- diamond_wide.json         # 2-level, 10-wide diamond
+-- parallel/
|   +-- parallel_4.json           # 4 independent branches
|   +-- parallel_16.json          # 16 independent branches
+-- conditional/
|   +-- switch_basic.json         # Simple switch node
|   +-- conditional_nested.json   # Nested conditionals
+-- cyclic/
|   +-- cycle_simple.json         # 2-node cycle, max 5 iterations
|   +-- cycle_convergence.json    # Convergence-based termination
+-- complex/
|   +-- mixed_20.json             # Mix of patterns, 20 nodes
|   +-- enterprise_50.json        # Enterprise workflow, 50 nodes
+-- edge_cases/
|   +-- single_node.json          # Single-node workflow
|   +-- disconnected.json         # Two disconnected subgraphs
|   +-- maximum_width.json        # 1 start -> 100 parallel -> 1 end
|   +-- deep_chain.json           # 500-node linear chain
+-- expected_results/
    +-- linear_5_results.json     # Expected output for linear_5
    +-- linear_5_schedule.json    # Expected scheduling order
    +-- diamond_basic_results.json
    +-- ...
```

### 6.2 Workflow JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "id": { "type": "string" },
    "name": { "type": "string" },
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "type": { "type": "string" },
          "config": { "type": "object" },
          "is_async": { "type": "boolean", "default": false }
        },
        "required": ["id", "type"]
      }
    },
    "connections": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_id": { "type": "string" },
          "source_output": { "type": "string" },
          "target_id": { "type": "string" },
          "target_input": { "type": "string" },
          "cyclic": { "type": "boolean", "default": false }
        },
        "required": ["source_id", "source_output", "target_id", "target_input"]
      }
    },
    "inputs": { "type": "object" },
    "execution_config": {
      "type": "object",
      "properties": {
        "enable_cycles": { "type": "boolean" },
        "conditional_execution": {
          "type": "string",
          "enum": ["route_data", "skip_branches"]
        },
        "connection_validation": {
          "type": "string",
          "enum": ["off", "warn", "strict"]
        }
      }
    }
  },
  "required": ["id", "name", "nodes"]
}
```

### 6.3 Equivalence Test Runners

**Python runner:**

```python
# tests/cross_language/test_equivalence.py

import json
import pytest
from pathlib import Path

WORKFLOW_DIR = Path("testdata/workflows")
EXPECTED_DIR = WORKFLOW_DIR / "expected_results"


def load_workflow(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def build_and_execute(workflow_def: dict) -> dict:
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime import LocalRuntime

    builder = WorkflowBuilder()
    for node in workflow_def["nodes"]:
        builder.add_node(node["type"], node["id"], node.get("config", {}))
    for conn in workflow_def.get("connections", []):
        builder.connect(conn["source_id"], conn["source_output"],
                       conn["target_id"], conn["target_input"])

    config = workflow_def.get("execution_config", {})
    runtime = LocalRuntime(
        enable_cycles=config.get("enable_cycles", False),
        connection_validation=config.get("connection_validation", "warn"),
    )
    results, run_id = runtime.execute(
        builder.build(),
        inputs=workflow_def.get("inputs", {}),
    )
    return normalize_results(results)


def normalize_results(results: dict) -> dict:
    """Normalize results for cross-language comparison.

    - Sort dict keys
    - Round floats to 6 decimal places
    - Convert all numeric types to float
    """
    normalized = {}
    for key, value in sorted(results.items()):
        normalized[key] = normalize_value(value)
    return normalized


def normalize_value(value):
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [normalize_value(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, int):
        return float(value)
    return value


@pytest.mark.parametrize("workflow_path", sorted(WORKFLOW_DIR.rglob("*.json")))
def test_workflow_produces_expected_results(workflow_path):
    if "expected_results" in str(workflow_path):
        pytest.skip("Not a workflow file")

    workflow_def = load_workflow(workflow_path)
    results = build_and_execute(workflow_def)

    expected_path = EXPECTED_DIR / (workflow_path.stem + "_results.json")
    if expected_path.exists():
        with open(expected_path) as f:
            expected = json.load(f)
        assert results == normalize_results(expected), (
            f"Results mismatch for {workflow_path.name}"
        )
    else:
        # First run: save results as expected baseline
        with open(expected_path, "w") as f:
            json.dump(results, f, indent=2, sort_keys=True)
```

**Go runner:**

```go
// tests/cross_language/equivalence_test.go

func TestCrossLanguageEquivalence(t *testing.T) {
    workflowFiles, err := filepath.Glob("testdata/workflows/**/*.json")
    require.NoError(t, err)

    for _, wfPath := range workflowFiles {
        if strings.Contains(wfPath, "expected_results") {
            continue
        }

        t.Run(filepath.Base(wfPath), func(t *testing.T) {
            wfDef := loadWorkflowDef(t, wfPath)
            results := buildAndExecute(t, wfDef)
            normalized := normalizeResults(results)

            expectedPath := filepath.Join("testdata/workflows/expected_results",
                strings.TrimSuffix(filepath.Base(wfPath), ".json")+"_results.json")

            if _, err := os.Stat(expectedPath); err == nil {
                expected := loadExpectedResults(t, expectedPath)
                assert.Equal(t, expected, normalized,
                    "Results mismatch for %s", filepath.Base(wfPath))
            }
        })
    }
}
```

**Java runner:**

```java
// kailash-core/src/test/java/com/kailash/core/CrossLanguageEquivalenceTest.java

@TestFactory
Stream<DynamicTest> crossLanguageEquivalence() throws IOException {
    Path workflowDir = Paths.get("testdata/workflows");
    return Files.walk(workflowDir)
        .filter(p -> p.toString().endsWith(".json"))
        .filter(p -> !p.toString().contains("expected_results"))
        .map(path -> dynamicTest(path.getFileName().toString(), () -> {
            WorkflowDef def = loadWorkflowDef(path);
            Map<String, Object> results = buildAndExecute(def);
            Map<String, Object> normalized = normalizeResults(results);

            Path expectedPath = workflowDir.resolve("expected_results")
                .resolve(path.getFileName().toString()
                    .replace(".json", "_results.json"));

            if (Files.exists(expectedPath)) {
                Map<String, Object> expected = loadExpectedResults(expectedPath);
                assertEquals(expected, normalized,
                    "Results mismatch for " + path.getFileName());
            }
        }));
}
```

### 6.4 Scheduling Order Verification

Scheduling order is deterministic because it is computed by the Rust core. All SDKs
must produce the same topological sort and level assignment:

```python
# tests/cross_language/test_scheduling_equivalence.py

@pytest.mark.parametrize("workflow_path", sorted(WORKFLOW_DIR.rglob("*.json")))
def test_scheduling_order_matches(workflow_path):
    """Verify Rust core produces identical schedule across language bindings."""
    if "expected_results" in str(workflow_path):
        pytest.skip("Not a workflow file")

    workflow_def = load_workflow(workflow_path)

    # Get schedule from Python binding
    py_order = get_schedule_python(workflow_def)

    # Get schedule from expected baseline (generated by any SDK)
    expected_path = EXPECTED_DIR / (workflow_path.stem + "_schedule.json")
    if expected_path.exists():
        with open(expected_path) as f:
            expected_order = json.load(f)
        assert py_order == expected_order
    else:
        with open(expected_path, "w") as f:
            json.dump(py_order, f, indent=2)
```

### 6.5 Result Normalization Rules

For cross-language comparison, all results must be normalized:

| Data Type        | Normalization Rule                          |
| ---------------- | ------------------------------------------- |
| Float            | Round to 6 decimal places                   |
| Integer          | Convert to float for comparison             |
| String           | Exact match (UTF-8)                         |
| Null/None/nil    | Normalize to JSON `null`                    |
| Dict/Map         | Sort keys lexicographically                 |
| List/Array       | Preserve order (no sorting)                 |
| Boolean          | Exact match                                 |
| Timestamp        | Exclude from comparison (non-deterministic) |
| Run ID           | Exclude from comparison (non-deterministic) |
| Duration metrics | Exclude from comparison (non-deterministic) |

## 7. Performance Benchmarks

### 7.1 Benchmark Suite Design

Each language SDK maintains a benchmark suite that measures the same operations,
enabling cross-language performance comparison.

| Benchmark              | Description                          | Size Variants        |
| ---------------------- | ------------------------------------ | -------------------- |
| `bench_build`          | Workflow construction time           | 10, 50, 100, 500, 1K |
| `bench_schedule`       | Topological sort + level computation | 10, 50, 100, 500, 1K |
| `bench_validate`       | Full workflow validation             | 10, 50, 100, 500, 1K |
| `bench_cycle_detect`   | Cycle detection (Tarjan's SCC)       | 10, 50, 100, 500, 1K |
| `bench_prepare_inputs` | Input routing computation            | 10, 50, 100          |
| `bench_execute_noop`   | Full execution with no-op nodes      | 10, 20, 50, 100      |
| `bench_ffi_crossing`   | Single FFI call overhead             | N/A (micro)          |
| `bench_memory`         | Memory usage per workflow            | 10, 100, 1K, 10K     |

### 7.2 Rust Benchmarks (criterion)

```rust
// kailash-bench/benches/graph_bench.rs

use criterion::{criterion_group, criterion_main, Criterion, BenchmarkId};
use kailash_core::graph::*;
use serde_json::json;

fn bench_graph_build(c: &mut Criterion) {
    let mut group = c.benchmark_group("graph_build");

    for size in [10, 50, 100, 500, 1000] {
        group.bench_with_input(
            BenchmarkId::new("linear", size),
            &size,
            |b, &size| {
                b.iter(|| {
                    let mut graph = WorkflowGraph::new("bench", "Bench");
                    for i in 0..size {
                        graph.add_node(
                            NodeId(format!("n{}", i)),
                            "TestNode",
                            json!({"value": i}),
                            false,
                        ).unwrap();
                    }
                    for i in 0..size - 1 {
                        graph.connect(
                            &NodeId(format!("n{}", i)),
                            &NodeId(format!("n{}", i + 1)),
                            ConnectionInfo::simple("out", "in"),
                        ).unwrap();
                    }
                    graph
                });
            },
        );
    }
    group.finish();
}

fn bench_topological_sort(c: &mut Criterion) {
    let mut group = c.benchmark_group("topological_sort");

    for size in [10, 50, 100, 500, 1000] {
        let mut graph = build_linear_graph(size);

        group.bench_with_input(
            BenchmarkId::new("linear", size),
            &size,
            |b, _| {
                b.iter(|| {
                    graph.invalidate_caches();
                    graph.topological_sort().unwrap()
                });
            },
        );
    }
    group.finish();
}

fn bench_cycle_detection(c: &mut Criterion) {
    let mut group = c.benchmark_group("cycle_detection");

    for size in [10, 50, 100, 500] {
        let mut graph = build_complex_graph_with_potential_cycles(size);

        group.bench_with_input(
            BenchmarkId::new("complex", size),
            &size,
            |b, _| {
                b.iter(|| {
                    graph.invalidate_caches();
                    graph.detect_cycles()
                });
            },
        );
    }
    group.finish();
}

fn bench_validation(c: &mut Criterion) {
    let mut group = c.benchmark_group("validation");

    for size in [10, 20, 50, 100, 500] {
        let graph = build_diamond_graph(size);

        group.bench_with_input(
            BenchmarkId::new("full", size),
            &size,
            |b, _| {
                b.iter(|| graph.validate());
            },
        );
    }
    group.finish();
}

criterion_group!(benches, bench_graph_build, bench_topological_sort,
                 bench_cycle_detection, bench_validation);
criterion_main!(benches);
```

### 7.3 Python Benchmarks (pytest-benchmark)

```python
# tests/benchmarks/test_performance.py

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime


@pytest.mark.parametrize("size", [10, 50, 100, 500, 1000])
def test_bench_build(benchmark, size):
    """Measure workflow build time."""
    def build():
        wf = WorkflowBuilder()
        for i in range(size):
            wf.add_node("PassthroughNode", f"n{i}", {"value": i})
        for i in range(size - 1):
            wf.connect(f"n{i}", "output", f"n{i+1}", "input")
        return wf.build()

    benchmark(build)


@pytest.mark.parametrize("size", [10, 20, 50, 100])
def test_bench_execute_noop(benchmark, size):
    """Measure full execution overhead with no-op nodes."""
    wf = WorkflowBuilder()
    for i in range(size):
        wf.add_node("NoopNode", f"n{i}", {})
    for i in range(size - 1):
        wf.connect(f"n{i}", "output", f"n{i+1}", "input")
    built = wf.build()

    runtime = LocalRuntime()
    benchmark(lambda: runtime.execute(built))


def test_bench_ffi_crossing(benchmark):
    """Measure single FFI call overhead."""
    from kailash._rust import WorkflowGraph

    graph = WorkflowGraph("bench", "Bench")
    counter = [0]

    def single_add():
        graph.add_node(f"n{counter[0]}", "TestNode", {}, False)
        counter[0] += 1

    benchmark(single_add)
```

### 7.4 Go Benchmarks

```go
// workflow/builder_bench_test.go

func BenchmarkBuild(b *testing.B) {
    sizes := []int{10, 50, 100, 500, 1000}
    for _, size := range sizes {
        b.Run(fmt.Sprintf("linear_%d", size), func(b *testing.B) {
            b.ReportAllocs()
            for i := 0; i < b.N; i++ {
                builder := workflow.NewBuilder("bench", "Bench")
                for j := 0; j < size; j++ {
                    builder.AddNode("TestNode", fmt.Sprintf("n%d", j),
                        map[string]interface{}{"value": j})
                }
                for j := 0; j < size-1; j++ {
                    builder.Connect(fmt.Sprintf("n%d", j), "out",
                        fmt.Sprintf("n%d", j+1), "in")
                }
                builder.Build()
            }
        })
    }
}

func BenchmarkExecuteNoop(b *testing.B) {
    sizes := []int{10, 20, 50, 100}
    for _, size := range sizes {
        wf := buildLinearWorkflow(size)
        rt := runtime.NewLocalRuntime()

        b.Run(fmt.Sprintf("noop_%d", size), func(b *testing.B) {
            b.ReportAllocs()
            for i := 0; i < b.N; i++ {
                rt.Execute(wf)
            }
        })
    }
}

func BenchmarkFFICrossing(b *testing.B) {
    h, _ := ffi.NewWorkflow("bench", "Bench")
    defer h.Close()

    b.ResetTimer()
    b.ReportAllocs()
    for i := 0; i < b.N; i++ {
        h.AddNode(fmt.Sprintf("n%d", i), "TestNode", []byte("{}"), false)
    }
}
```

### 7.5 Performance Regression Detection

```yaml
# .github/workflows/performance.yml
name: Performance Regression Detection
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  rust-benchmarks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - name: Run benchmarks
        run: cargo bench --package kailash-bench -- --output-format bencher | tee rust-bench.txt
      - uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Rust Core Benchmarks
          tool: cargo
          output-file-path: rust-bench.txt
          alert-threshold: "120%"
          fail-on-alert: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: benchmarks/rust

  python-benchmarks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install -e ".[dev,rust]" pytest-benchmark
      - name: Run benchmarks
        run: pytest tests/benchmarks/ --benchmark-json=python-bench.json
      - uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Python SDK Benchmarks
          tool: pytest
          output-file-path: python-bench.json
          alert-threshold: "120%"
          fail-on-alert: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: benchmarks/python

  go-benchmarks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: "1.22"
      - name: Build Rust FFI
        run: cargo build --release --package kailash-ffi
      - name: Run benchmarks
        run: |
          cd kailash-go
          go test -bench=. -benchmem ./... | tee go-bench.txt
      - uses: benchmark-action/github-action-benchmark@v1
        with:
          name: Go SDK Benchmarks
          tool: go
          output-file-path: kailash-go/go-bench.txt
          alert-threshold: "120%"
          fail-on-alert: true
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          benchmark-data-dir-path: benchmarks/go
```

### 7.6 Performance Targets

| Metric                                    | Target    | Threshold (fail if exceeded) |
| ----------------------------------------- | --------- | ---------------------------- |
| Rust: graph build (20 nodes)              | < 0.05ms  | 0.1ms                        |
| Rust: topological sort (20 nodes)         | < 0.005ms | 0.01ms                       |
| Rust: topological sort (1000 nodes)       | < 0.1ms   | 0.2ms                        |
| Rust: cycle detection (20 nodes)          | < 0.01ms  | 0.02ms                       |
| Rust: validation (20 nodes)               | < 0.1ms   | 0.2ms                        |
| Python: FFI crossing (PyO3, single call)  | < 0.05ms  | 0.1ms                        |
| Python: full execution overhead (20 noop) | < 20ms    | 40ms                         |
| Go: FFI crossing (CGo, single call)       | < 0.1ms   | 0.2ms                        |
| Go: full execution overhead (20 noop)     | < 15ms    | 30ms                         |
| Java: FFI crossing (JNI, single call)     | < 0.1ms   | 0.2ms                        |
| Java: full execution overhead (20 noop)   | < 25ms    | 50ms                         |
| Memory: Rust graph (20 nodes)             | < 20KB    | 50KB                         |
| Memory: Rust graph (1000 nodes)           | < 1MB     | 5MB                          |

## 8. Property-Based Testing

### 8.1 Rust (proptest)

```rust
// kailash-core/src/graph/proptests.rs

use proptest::prelude::*;

proptest! {
    /// Any acyclic graph produced by adding nodes in order with forward-only edges
    /// must have a valid topological sort containing all nodes.
    #[test]
    fn topological_sort_is_complete(node_count in 1usize..100) {
        let mut graph = WorkflowGraph::new("prop", "Prop");
        for i in 0..node_count {
            graph.add_node(
                NodeId(format!("n{}", i)),
                "TestNode",
                serde_json::json!({}),
                false,
            ).unwrap();
        }
        // Only connect forward (i -> i+1), guaranteeing acyclicity
        for i in 0..node_count.saturating_sub(1) {
            graph.connect(
                &NodeId(format!("n{}", i)),
                &NodeId(format!("n{}", i + 1)),
                ConnectionInfo::simple("out", "in"),
            ).unwrap();
        }

        let order = graph.topological_sort().unwrap();
        assert_eq!(order.len(), node_count);

        // Verify ordering: for every edge (u, v), u appears before v
        let pos: HashMap<_, _> = order.iter().enumerate()
            .map(|(i, id)| (id.clone(), i))
            .collect();
        for i in 0..node_count.saturating_sub(1) {
            let u = &NodeId(format!("n{}", i));
            let v = &NodeId(format!("n{}", i + 1));
            assert!(pos[u] < pos[v],
                "Edge {}->{} violates topological order", i, i+1);
        }
    }

    /// Adding and removing a node should leave the graph in its original state.
    #[test]
    fn add_remove_is_identity(node_count in 1usize..50) {
        let mut graph = WorkflowGraph::new("prop", "Prop");
        for i in 0..node_count {
            graph.add_node(
                NodeId(format!("n{}", i)),
                "TestNode",
                serde_json::json!({}),
                false,
            ).unwrap();
        }

        let original_count = graph.node_count();
        graph.add_node(
            NodeId("extra".into()), "TestNode", serde_json::json!({}), false
        ).unwrap();
        assert_eq!(graph.node_count(), original_count + 1);

        graph.remove_node(&NodeId("extra".into())).unwrap();
        assert_eq!(graph.node_count(), original_count);
    }

    /// Validation should never panic regardless of graph structure.
    #[test]
    fn validation_never_panics(
        node_count in 0usize..50,
        edge_pairs in prop::collection::vec((0usize..50, 0usize..50), 0..100),
    ) {
        let mut graph = WorkflowGraph::new("prop", "Prop");
        for i in 0..node_count {
            let _ = graph.add_node(
                NodeId(format!("n{}", i)),
                "TestNode",
                serde_json::json!({}),
                false,
            );
        }
        for (src, tgt) in &edge_pairs {
            if src != tgt && *src < node_count && *tgt < node_count {
                let _ = graph.connect(
                    &NodeId(format!("n{}", src)),
                    &NodeId(format!("n{}", tgt)),
                    ConnectionInfo::simple("out", "in"),
                );
            }
        }

        // This should never panic
        let result = graph.validate();
        let _ = result.is_valid;
    }

    /// Level computation must assign every node exactly once.
    #[test]
    fn levels_contain_all_nodes(node_count in 2usize..50) {
        let mut graph = WorkflowGraph::new("prop", "Prop");
        for i in 0..node_count {
            graph.add_node(
                NodeId(format!("n{}", i)),
                "TestNode",
                serde_json::json!({}),
                false,
            ).unwrap();
        }
        for i in 0..node_count - 1 {
            graph.connect(
                &NodeId(format!("n{}", i)),
                &NodeId(format!("n{}", i + 1)),
                ConnectionInfo::simple("out", "in"),
            ).unwrap();
        }

        let schedule = graph.compute_schedule().unwrap();
        let total_nodes: usize = schedule.levels.iter()
            .map(|l| l.node_ids.len())
            .sum();
        assert_eq!(total_nodes, node_count);
    }
}
```

### 8.2 Python (Hypothesis)

```python
# tests/property/test_graph_properties.py

from hypothesis import given, strategies as st, settings
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime


@given(node_count=st.integers(min_value=1, max_value=100))
@settings(max_examples=200, deadline=5000)
def test_topological_sort_is_complete(node_count):
    """Topological sort must contain every node exactly once."""
    wf = WorkflowBuilder()
    for i in range(node_count):
        wf.add_node("PassthroughNode", f"n{i}", {"value": i})
    for i in range(node_count - 1):
        wf.connect(f"n{i}", "output", f"n{i+1}", "input")

    built = wf.build()
    runtime = LocalRuntime()
    results, _ = runtime.execute(built)
    assert len(results) == node_count


@given(
    node_count=st.integers(min_value=2, max_value=30),
    branch_count=st.integers(min_value=2, max_value=10),
)
@settings(max_examples=100, deadline=5000)
def test_diamond_pattern_all_nodes_execute(node_count, branch_count):
    """Diamond patterns must execute all branch nodes."""
    branch_count = min(branch_count, node_count - 1)

    wf = WorkflowBuilder()
    wf.add_node("SplitNode", "start", {})
    for i in range(branch_count):
        wf.add_node("PassthroughNode", f"branch_{i}", {})
        wf.connect("start", f"output_{i}", f"branch_{i}", "input")
    wf.add_node("MergeNode", "end", {})
    for i in range(branch_count):
        wf.connect(f"branch_{i}", "output", "end", f"input_{i}")

    built = wf.build()
    runtime = LocalRuntime()
    results, _ = runtime.execute(built)
    assert len(results) == branch_count + 2  # start + branches + end


@given(data=st.data())
@settings(max_examples=50, deadline=10000)
def test_validation_never_raises_unexpected_exception(data):
    """Validation should return a result, never raise unexpectedly."""
    node_count = data.draw(st.integers(min_value=0, max_value=20))
    wf = WorkflowBuilder()
    for i in range(node_count):
        wf.add_node("PassthroughNode", f"n{i}", {})

    edge_count = data.draw(st.integers(min_value=0, max_value=node_count * 2))
    for _ in range(edge_count):
        src = data.draw(st.integers(min_value=0, max_value=max(0, node_count - 1)))
        tgt = data.draw(st.integers(min_value=0, max_value=max(0, node_count - 1)))
        if src != tgt and node_count > 0:
            try:
                wf.connect(f"n{src}", "output", f"n{tgt}", "input")
            except Exception:
                pass  # Invalid connections are expected

    if node_count > 0:
        built = wf.build()
        result = built.validate()
        assert hasattr(result, "is_valid")
```

### 8.3 Go (gopter)

```go
// workflow/property_test.go

func TestTopologicalSortIsComplete(t *testing.T) {
    properties := gopter.NewProperties(gopter.DefaultTestParameters())

    properties.Property("sort contains all nodes", prop.ForAll(
        func(nodeCount int) bool {
            builder := workflow.NewBuilder("prop", "Prop")
            for i := 0; i < nodeCount; i++ {
                builder.AddNode("TestNode", fmt.Sprintf("n%d", i), nil)
            }
            for i := 0; i < nodeCount-1; i++ {
                builder.Connect(fmt.Sprintf("n%d", i), "out",
                    fmt.Sprintf("n%d", i+1), "in")
            }
            wf, err := builder.Build()
            if err != nil {
                return false
            }
            order, err := wf.TopologicalSort()
            return err == nil && len(order) == nodeCount
        },
        gen.IntRange(1, 100),
    ))

    properties.Property("add then remove preserves count", prop.ForAll(
        func(nodeCount int) bool {
            builder := workflow.NewBuilder("prop", "Prop")
            for i := 0; i < nodeCount; i++ {
                builder.AddNode("TestNode", fmt.Sprintf("n%d", i), nil)
            }
            wf, _ := builder.Build()
            original := wf.NodeCount()
            wf.AddNode("extra", "TestNode", nil)
            wf.RemoveNode("extra")
            return wf.NodeCount() == original
        },
        gen.IntRange(1, 50),
    ))

    properties.TestingRun(t)
}
```

## 9. CI Matrix

### 9.1 Test Matrix per Commit

Every commit to the `main` branch or any PR triggers the full test matrix:

```yaml
# .github/workflows/ci.yml
name: Full CI Matrix
on:
  push:
    branches: [main]
  pull_request:

jobs:
  rust-core:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        rust: [stable, nightly]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@${{ matrix.rust }}
      - run: cargo test --workspace --all-features
      - run: cargo clippy --workspace -- -D warnings
      - run: cargo fmt --all -- --check

  python-sdk:
    needs: rust-core
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python: ["3.11", "3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: Build Rust extension
        run: pip install maturin && maturin develop --release
      - name: Run tests
        run: pytest tests/ -x -v --tb=short
      - name: Run FFI boundary tests
        run: pytest tests/ffi/ -v
      - name: Run property tests
        run: pytest tests/property/ -v --hypothesis-seed=0

  go-sdk:
    needs: rust-core
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        go: ["1.21", "1.22", "1.23"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: ${{ matrix.go }}
      - name: Build Rust FFI
        run: cargo build --release --package kailash-ffi
      - name: Run tests
        run: cd kailash-go && CGO_ENABLED=1 go test -v -race ./...

  java-sdk:
    needs: rust-core
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        java: [17, 21]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: ${{ matrix.java }}
          distribution: temurin
      - name: Build Rust JNI
        run: cargo build --release --package kailash-java
      - name: Run tests
        run: cd kailash-java && mvn test

  cross-language:
    needs: [python-sdk, go-sdk, java-sdk]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup all languages
        run: |
          pip install maturin && maturin develop --release
          cd kailash-go && go build ./...
          cd ../kailash-java && mvn compile -DskipTests
      - name: Run equivalence tests
        run: |
          pytest tests/cross_language/ -v
          cd kailash-go && go test ./tests/cross_language/...
          cd ../kailash-java && mvn test -pl kailash-core -Dtest="CrossLanguage*"
      - name: Verify scheduling equivalence
        run: python scripts/verify_scheduling_equivalence.py
```

### 9.2 Test Pipeline Dependencies

```
rust-core (3 OS x 2 Rust versions = 6 jobs)
    |
    +---> python-sdk (3 OS x 3 Python versions = 9 jobs)
    +---> go-sdk (2 OS x 3 Go versions = 6 jobs)
    +---> java-sdk (2 OS x 2 Java versions = 4 jobs)
              |
              +---> cross-language (1 job, runs after all SDKs pass)
              +---> performance (1 job, runs on main only)
```

## 10. Regression Suite

### 10.1 Workflow Corpus Maintenance

The shared workflow corpus grows over time. Guidelines for adding new workflows:

1. Each workflow must have an `expected_results` file generated by the Python SDK
   (reference implementation)
2. All three SDK equivalence tests must pass before merging
3. Edge cases discovered during development are added to the corpus
4. Each release adds at least 10 new workflows covering new features

### 10.2 Corpus Categories and Counts

| Category     | Initial Target | Expanded Target (GA) | Purpose                       |
| ------------ | -------------- | -------------------- | ----------------------------- |
| Linear       | 10             | 20                   | Basic execution ordering      |
| Diamond      | 10             | 20                   | Parallel execution paths      |
| Wide/Fan-out | 5              | 15                   | Parallelism stress            |
| Conditional  | 10             | 30                   | Branch skipping, switch nodes |
| Cyclic       | 10             | 25                   | Cycle iteration, convergence  |
| Complex      | 15             | 50                   | Mixed patterns                |
| Edge cases   | 10             | 40                   | Empty, single-node, huge      |
| Real-world   | 30             | 100                  | DataFlow, Nexus, Kaizen       |
| **Total**    | **100**        | **300**              |                               |

### 10.3 Standard Test Node Types

Each language SDK implements these standard test nodes identically:

| Node Type         | Behavior                                           |
| ----------------- | -------------------------------------------------- |
| `PassthroughNode` | Returns input unchanged                            |
| `AddNode`         | Adds `addend` config value to input                |
| `MultiplyNode`    | Multiplies input by `factor` config value          |
| `ConditionalNode` | Routes data based on condition                     |
| `FailNode`        | Always throws error (for error handling tests)     |
| `SlowNode`        | Sleeps for configured duration (for timeout tests) |
| `StatefulNode`    | Tracks execution count (for cycle tests)           |
| `NoopNode`        | Executes instantly, returns empty output           |
| `AccumulatorNode` | Collects all inputs into a single output           |
| `SplitNode`       | Splits input into N outputs for fan-out patterns   |
| `MergeNode`       | Merges N inputs into a single output               |

These nodes are intentionally simple to isolate SDK behavior from domain logic.

### 10.4 Expected Results Generation

```python
# scripts/generate_expected_results.py
"""
Generate expected results for all workflow definitions using the Python SDK
(reference implementation). These results become the baseline for cross-language
equivalence testing.
"""

import json
from pathlib import Path
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime


def generate_all():
    workflow_dir = Path("testdata/workflows")
    results_dir = workflow_dir / "expected_results"
    results_dir.mkdir(exist_ok=True)

    count = 0
    for wf_path in sorted(workflow_dir.rglob("*.json")):
        if "expected_results" in str(wf_path):
            continue

        print(f"Generating results for {wf_path.name}...")
        wf_def = json.loads(wf_path.read_text())
        results = execute_workflow(wf_def)

        out_path = results_dir / (wf_path.stem + "_results.json")
        out_path.write_text(json.dumps(results, indent=2, sort_keys=True))

        schedule = compute_schedule(wf_def)
        sched_path = results_dir / (wf_path.stem + "_schedule.json")
        sched_path.write_text(json.dumps(schedule, indent=2))
        count += 1

    print(f"Generated results for {count} workflows")


if __name__ == "__main__":
    generate_all()
```

## 11. FFI Stress and Safety Testing

### 11.1 Memory Leak Detection

```python
# tests/stress/test_ffi_stress.py

import tracemalloc
import concurrent.futures


def test_no_memory_leak_10k_executions():
    """Verify no memory leaks after 10,000 workflow executions."""
    tracemalloc.start()

    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime import LocalRuntime

    runtime = LocalRuntime()

    initial_snapshot = tracemalloc.take_snapshot()

    for i in range(10_000):
        builder = WorkflowBuilder()
        builder.add_node("PassthroughNode", "node1", {"value": i})
        builder.add_node("PassthroughNode", "node2", {})
        builder.connect("node1", "value", "node2", "input")
        results, _ = runtime.execute(builder.build())

    final_snapshot = tracemalloc.take_snapshot()

    stats = final_snapshot.compare_to(initial_snapshot, "lineno")
    total_growth = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

    # Allow up to 10MB growth (for logging, caches, etc.)
    assert total_growth < 10 * 1024 * 1024, (
        f"Memory grew by {total_growth / 1024 / 1024:.1f}MB over 10K executions"
    )
    tracemalloc.stop()


def test_concurrent_workflow_execution():
    """Verify thread safety of Rust core under concurrent access."""
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime import LocalRuntime

    def execute_workflow(i):
        builder = WorkflowBuilder()
        builder.add_node("PassthroughNode", "node1", {"value": i})
        runtime = LocalRuntime()
        results, _ = runtime.execute(builder.build())
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(execute_workflow, i) for i in range(100)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 100
```

### 11.2 Sanitizer Integration

All Rust core tests are run under sanitizers in CI:

```yaml
# Part of CI matrix
- name: Test with AddressSanitizer
  env:
    RUSTFLAGS: "-Z sanitizer=address"
  run: cargo +nightly test --target x86_64-unknown-linux-gnu

- name: Test with MemorySanitizer
  env:
    RUSTFLAGS: "-Z sanitizer=memory"
  run: cargo +nightly test --target x86_64-unknown-linux-gnu

- name: Test with ThreadSanitizer
  env:
    RUSTFLAGS: "-Z sanitizer=thread"
  run: cargo +nightly test --target x86_64-unknown-linux-gnu
```

## 12. Summary

### 12.1 Key Principles

1. **Equivalence over independence**: The same workflow must produce the same results regardless
   of which language SDK runs it. The Rust core is the single source of truth for scheduling,
   validation, and graph operations.

2. **Property-based over example-based**: Property-based tests catch edge cases that hand-written
   examples miss. Every SDK includes property-based tests for core operations.

3. **FFI safety over FFI speed**: Memory safety across the FFI boundary is more important than
   micro-optimizing FFI call overhead. All boundary tests include leak detection and concurrency
   stress tests.

4. **Regression prevention over regression detection**: Performance benchmarks run on every commit
   with automatic regression alerts. A 20% regression blocks the merge.

5. **Shared corpus over separate suites**: The workflow test corpus is shared across all SDKs.
   Adding a workflow to the corpus automatically tests it in all three languages.

### 12.2 Tooling Summary

| Tool               | Language | Purpose                        |
| ------------------ | -------- | ------------------------------ |
| `cargo test`       | Rust     | Unit and integration tests     |
| `proptest`         | Rust     | Property-based testing         |
| `criterion`        | Rust     | Benchmarks                     |
| `pytest`           | Python   | All Python test layers         |
| `hypothesis`       | Python   | Property-based testing         |
| `pytest-benchmark` | Python   | Performance benchmarks         |
| `tracemalloc`      | Python   | Memory leak detection          |
| `go test`          | Go       | All Go test layers             |
| `gopter`           | Go       | Property-based testing         |
| `testing.B`        | Go       | Performance benchmarks         |
| `JUnit 5`          | Java     | All Java test layers           |
| `jqwik`            | Java     | Property-based testing         |
| `JMH`              | Java     | Performance benchmarks         |
| `benchmark-action` | CI       | Cross-commit regression alerts |
| `ASAN/MSAN/TSAN`   | Rust     | Memory and thread safety       |

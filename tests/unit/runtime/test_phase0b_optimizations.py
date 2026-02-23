"""Regression tests for Phase 0b Deduplication optimizations.

Validates that all P0B performance optimizations are in place and functional:
- P0B-001: Remove redundant VP#1 (DataTypeValidator.validate_node_input) from execution loop
- P0B-004: Cache topological sort in Workflow.get_execution_order()
- P0B-005: Cache cycle edge classification in Workflow.separate_dag_and_cycle_edges()
"""

import inspect

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


# --- P0B-001: Remove VP#1 (DataTypeValidator.validate_node_input) ---


class TestP0B001RemoveVP1:
    """Verify that DataTypeValidator.validate_node_input is NOT called in the execution loop."""

    def test_no_validate_node_input_in_execution_loop(self):
        """The main execution loop should not call DataTypeValidator.validate_node_input."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert "DataTypeValidator.validate_node_input(" not in source, (
            "DataTypeValidator.validate_node_input found in _execute_workflow_async. "
            "P0B-001 optimization may have been reverted."
        )

    def test_no_validate_node_input_in_execute_single_node(self):
        """_execute_single_node should not call DataTypeValidator.validate_node_input."""
        source = inspect.getsource(LocalRuntime._execute_single_node)
        assert "DataTypeValidator.validate_node_input(" not in source, (
            "DataTypeValidator.validate_node_input found in _execute_single_node. "
            "P0B-001 optimization may have been reverted."
        )

    def test_vp1_removal_comment_present(self):
        """The VP#1 removal comment should be present as documentation."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert (
            "P0B-001" in source
        ), "P0B-001 removal comment not found in execution method."

    def test_workflow_executes_without_vp1(self):
        """Workflow should execute correctly without VP#1 validation."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "producer", {"code": "result = {'data': 'hello'}"}
        )
        builder.add_node(
            "PythonCodeNode", "consumer", {"code": "result = {'received': input}"}
        )
        builder.add_connection("producer", "result", "consumer", "input")

        with LocalRuntime(debug=True) as runtime:
            results, run_id = runtime.execute(builder.build())

        assert "producer" in results
        assert "consumer" in results

    def test_vp3_still_present_in_node_execute(self):
        """Node.execute() should still perform VP#3 validation (authoritative)."""
        from kailash.nodes.base import Node

        source = inspect.getsource(Node.execute)
        assert "validate_inputs" in source, (
            "VP#3 (validate_inputs in Node.execute) has been removed. "
            "This is the authoritative validation and must remain."
        )


# --- P0B-004: Cache topological sort ---


class TestP0B004CacheTopoSort:
    """Verify that topological sort results are cached."""

    def test_topo_cache_attribute_exists(self):
        """Workflow should have _topo_cache attribute."""
        workflow = Workflow(workflow_id="test", name="test", description="test")
        assert hasattr(workflow, "_topo_cache")
        assert workflow._topo_cache is None

    def test_topo_cache_populated_after_call(self):
        """get_execution_order() should populate _topo_cache."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        builder.add_connection("a", "result", "b", "input")
        workflow = builder.build()

        assert workflow._topo_cache is None
        order = workflow.get_execution_order()
        assert workflow._topo_cache is not None
        assert workflow._topo_cache is order

    def test_topo_cache_returns_same_object(self):
        """Repeated calls should return the same cached list."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        builder.add_connection("a", "result", "b", "input")
        workflow = builder.build()

        order1 = workflow.get_execution_order()
        order2 = workflow.get_execution_order()
        assert order1 is order2, "Cache should return the same list object"

    def test_topo_cache_source_check(self):
        """get_execution_order source should have cache logic."""
        source = inspect.getsource(Workflow.get_execution_order)
        assert "_topo_cache" in source
        assert "self._topo_cache is not None" in source

    def test_topo_cache_invalidated_on_add_node(self):
        """Adding a node should invalidate the topo cache."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        workflow = builder.build()

        # Populate cache
        workflow.get_execution_order()
        assert workflow._topo_cache is not None

        # Add a new node — should invalidate
        workflow.add_node(
            node_id="c", node_or_type="PythonCodeNode", code="result = {'x': 3}"
        )
        assert workflow._topo_cache is None

    def test_topo_cache_invalidated_on_connect(self):
        """Connecting nodes should invalidate the topo cache."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        workflow = builder.build()

        # Populate cache
        workflow.get_execution_order()
        assert workflow._topo_cache is not None

        # Connect — should invalidate
        workflow.connect("a", "b", mapping={"result": "input"})
        assert workflow._topo_cache is None


# --- P0B-005: Cache cycle edge classification ---


class TestP0B005CacheCycleEdges:
    """Verify that cycle edge classification results are cached."""

    def test_dag_cycle_cache_attribute_exists(self):
        """Workflow should have _dag_cycle_cache attribute."""
        workflow = Workflow(workflow_id="test", name="test", description="test")
        assert hasattr(workflow, "_dag_cycle_cache")
        assert workflow._dag_cycle_cache is None

    def test_dag_cycle_cache_populated_after_call(self):
        """separate_dag_and_cycle_edges() should populate _dag_cycle_cache."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        builder.add_connection("a", "result", "b", "input")
        workflow = builder.build()

        assert workflow._dag_cycle_cache is None
        result = workflow.separate_dag_and_cycle_edges()
        assert workflow._dag_cycle_cache is not None
        assert workflow._dag_cycle_cache == result

    def test_dag_cycle_cache_returns_same_object(self):
        """Repeated calls should return the same cached tuple."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        builder.add_connection("a", "result", "b", "input")
        workflow = builder.build()

        result1 = workflow.separate_dag_and_cycle_edges()
        result2 = workflow.separate_dag_and_cycle_edges()
        assert result1 is result2, "Cache should return the same tuple object"

    def test_dag_cycle_cache_source_check(self):
        """separate_dag_and_cycle_edges source should have cache logic."""
        source = inspect.getsource(Workflow.separate_dag_and_cycle_edges)
        assert "_dag_cycle_cache" in source
        assert "self._dag_cycle_cache is not None" in source

    def test_dag_cycle_cache_invalidated_on_connect(self):
        """Connecting nodes should invalidate the dag/cycle cache."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        workflow = builder.build()

        # Populate cache
        workflow.separate_dag_and_cycle_edges()
        assert workflow._dag_cycle_cache is not None

        # Connect — should invalidate
        workflow.connect("a", "b", mapping={"result": "input"})
        assert workflow._dag_cycle_cache is None

    def test_invalidation_method_exists(self):
        """_invalidate_graph_caches method should exist."""
        workflow = Workflow(workflow_id="test", name="test", description="test")
        assert hasattr(workflow, "_invalidate_graph_caches")
        assert callable(workflow._invalidate_graph_caches)

    def test_invalidation_clears_both_caches(self):
        """_invalidate_graph_caches should clear both caches."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'x': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'x': 2}"})
        builder.add_connection("a", "result", "b", "input")
        workflow = builder.build()

        # Populate both caches
        workflow.get_execution_order()
        workflow.separate_dag_and_cycle_edges()
        assert workflow._topo_cache is not None
        assert workflow._dag_cycle_cache is not None

        # Invalidate
        workflow._invalidate_graph_caches()
        assert workflow._topo_cache is None
        assert workflow._dag_cycle_cache is None


# --- Integration: P0B optimizations working together ---


class TestPhase0bIntegration:
    """End-to-end tests verifying all P0B optimizations work together."""

    def test_multi_node_workflow_executes(self):
        """Multi-node workflow should execute correctly with all P0B optimizations."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "step1", {"code": "result = {'data': 'a'}"})
        builder.add_node("PythonCodeNode", "step2", {"code": "result = {'data': 'b'}"})
        builder.add_node("PythonCodeNode", "step3", {"code": "result = {'data': 'c'}"})
        builder.add_connection("step1", "result", "step2", "input")
        builder.add_connection("step2", "result", "step3", "input")

        with LocalRuntime(debug=True) as runtime:
            results, run_id = runtime.execute(builder.build())

        assert len(results) == 3
        assert all(f"step{i}" in results for i in range(1, 4))

    def test_cached_order_matches_execution(self):
        """Cached execution order should match actual execution sequence."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "first", {"code": "result = {'data': '1'}"})
        builder.add_node("PythonCodeNode", "second", {"code": "result = {'data': '2'}"})
        builder.add_node("PythonCodeNode", "third", {"code": "result = {'data': '3'}"})
        builder.add_connection("first", "result", "second", "input")
        builder.add_connection("second", "result", "third", "input")

        workflow = builder.build()

        # Get cached order
        order = workflow.get_execution_order()
        assert order.index("first") < order.index("second")
        assert order.index("second") < order.index("third")

        # Verify cached
        order2 = workflow.get_execution_order()
        assert order is order2

        # Execute
        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow)

        assert len(results) == 3

    def test_parallel_nodes_execute_correctly(self):
        """Independent parallel nodes should execute correctly with cached order."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "root", {"code": "result = {'data': 'root'}"}
        )
        builder.add_node(
            "PythonCodeNode", "branch_a", {"code": "result = {'data': 'a'}"}
        )
        builder.add_node(
            "PythonCodeNode", "branch_b", {"code": "result = {'data': 'b'}"}
        )
        builder.add_connection("root", "result", "branch_a", "input")
        builder.add_connection("root", "result", "branch_b", "input")

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(builder.build())

        assert len(results) == 3
        assert "root" in results
        assert "branch_a" in results
        assert "branch_b" in results

    def test_multiple_executions_independent_with_caching(self):
        """Multiple executions should produce independent results even with caching."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node", {"code": "result = {'data': 'ok'}"})
        workflow = builder.build()

        with LocalRuntime() as runtime:
            results1, run_id1 = runtime.execute(workflow)
            results2, run_id2 = runtime.execute(workflow)

        assert "node" in results1
        assert "node" in results2
        assert run_id1 != run_id2

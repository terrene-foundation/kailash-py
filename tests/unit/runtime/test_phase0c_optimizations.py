"""Regression tests for Phase 0c networkx hot-path replacement optimizations.

Validates that all P0C performance optimizations are in place and functional:
- P0C-001: Replace nx.topological_sort in _execute_workflow_async with cached get_execution_order
- P0C-002: Replace nx.topological_sort in switch/fallback paths with cached get_execution_order
- P0C-003: Replace nx.topological_sort in AsyncLocalRuntime with cached get_execution_order
- P0C-004: Replace nx.ancestors with pure-Python BFS predecessor traversal
- P0C-005: Remove unused networkx imports from local.py and async_local.py
"""

import inspect

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# --- P0C-001/002: Replace nx.topological_sort in local.py ---


class TestP0C001CachedTopoSortInLocalRuntime:
    """Verify that LocalRuntime uses workflow.get_execution_order() instead of nx.topological_sort."""

    def test_no_nx_topological_sort_in_execute_workflow_async(self):
        """_execute_workflow_async should not call nx.topological_sort."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert "nx.topological_sort" not in source, (
            "nx.topological_sort found in _execute_workflow_async. "
            "P0C-001 optimization may have been reverted."
        )

    def test_uses_get_execution_order_in_execute_workflow_async(self):
        """_execute_workflow_async should use workflow.get_execution_order()."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert (
            "get_execution_order()" in source
        ), "workflow.get_execution_order() not found in _execute_workflow_async."

    def test_p0c_comment_present(self):
        """P0C-001 optimization comment should be present."""
        source = inspect.getsource(LocalRuntime._execute_workflow_async)
        assert (
            "P0C-001" in source
        ), "P0C-001 comment not found in _execute_workflow_async."

    def test_workflow_executes_with_cached_topo_sort(self):
        """Workflow should execute correctly with cached topological sort."""
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "first", {"code": "result = {'data': 'hello'}"}
        )
        builder.add_node(
            "PythonCodeNode", "second", {"code": "result = {'data': 'world'}"}
        )
        builder.add_connection("first", "result", "second", "input")

        with LocalRuntime(debug=True) as runtime:
            results, run_id = runtime.execute(builder.build())

        assert "first" in results
        assert "second" in results


# --- P0C-003: Replace nx.topological_sort in AsyncLocalRuntime ---


class TestP0C003CachedTopoSortInAsyncRuntime:
    """Verify that AsyncLocalRuntime uses cached topological sort."""

    def test_no_nx_topological_sort_in_async_runtime(self):
        """AsyncLocalRuntime._execute_sync_workflow_internal should not call nx.topological_sort."""
        from kailash.runtime.async_local import AsyncLocalRuntime

        source = inspect.getsource(AsyncLocalRuntime._execute_sync_workflow_internal)
        assert "nx.topological_sort" not in source, (
            "nx.topological_sort found in AsyncLocalRuntime._execute_sync_workflow_internal. "
            "P0C-003 optimization may have been reverted."
        )

    def test_uses_get_execution_order_in_async_runtime(self):
        """AsyncLocalRuntime._execute_sync_workflow_internal should use get_execution_order()."""
        from kailash.runtime.async_local import AsyncLocalRuntime

        source = inspect.getsource(AsyncLocalRuntime._execute_sync_workflow_internal)
        assert "get_execution_order()" in source


# --- P0C-004: Replace nx.ancestors with pure-Python BFS ---


class TestP0C004PurePythonAncestors:
    """Verify that nx.ancestors is replaced with pure-Python BFS."""

    def test_no_nx_ancestors_in_local_runtime(self):
        """local.py should not use nx.ancestors."""
        import kailash.runtime.local as local_module

        source = inspect.getsource(local_module)
        assert "nx.ancestors(" not in source, (
            "nx.ancestors found in local.py. "
            "P0C-004 optimization may have been reverted."
        )

    def test_p0c_004_comment_present(self):
        """P0C-004 optimization comment should be present in local.py."""
        import kailash.runtime.local as local_module

        source = inspect.getsource(local_module)
        assert "P0C-004" in source


# --- P0C-005: Remove unused networkx imports ---


class TestP0C005RemovedNetworkxImports:
    """Verify that unused networkx imports are removed from hot-path files."""

    def test_no_networkx_import_in_local_runtime(self):
        """local.py should not import networkx."""
        import kailash.runtime.local as local_module

        source = inspect.getsource(local_module)
        # Check for top-level import (not in comments or strings)
        import_lines = [
            line.strip()
            for line in source.split("\n")
            if line.strip().startswith("import networkx")
            or line.strip().startswith("from networkx")
        ]
        assert len(import_lines) == 0, (
            f"networkx import found in local.py: {import_lines}. "
            "P0C-005 optimization may have been reverted."
        )

    def test_no_networkx_import_in_async_local(self):
        """async_local.py should not import networkx."""
        import kailash.runtime.async_local as async_module

        source = inspect.getsource(async_module)
        import_lines = [
            line.strip()
            for line in source.split("\n")
            if line.strip().startswith("import networkx")
            or line.strip().startswith("from networkx")
        ]
        assert len(import_lines) == 0, (
            f"networkx import found in async_local.py: {import_lines}. "
            "P0C-005 optimization may have been reverted."
        )


# --- Integration ---


class TestPhase0cIntegration:
    """End-to-end tests verifying all P0C optimizations work together."""

    def test_linear_workflow(self):
        """Linear 3-node workflow should execute with cached topo sort."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "a", {"code": "result = {'v': 1}"})
        builder.add_node("PythonCodeNode", "b", {"code": "result = {'v': 2}"})
        builder.add_node("PythonCodeNode", "c", {"code": "result = {'v': 3}"})
        builder.add_connection("a", "result", "b", "input")
        builder.add_connection("b", "result", "c", "input")

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(builder.build())

        assert len(results) == 3

    def test_diamond_workflow(self):
        """Diamond-shaped workflow (fan-out/fan-in) should execute correctly."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "root", {"code": "result = {'v': 0}"})
        builder.add_node("PythonCodeNode", "left", {"code": "result = {'v': 1}"})
        builder.add_node("PythonCodeNode", "right", {"code": "result = {'v': 2}"})
        builder.add_node("PythonCodeNode", "sink", {"code": "result = {'v': 3}"})
        builder.add_connection("root", "result", "left", "input")
        builder.add_connection("root", "result", "right", "input")
        builder.add_connection("left", "result", "sink", "left_input")
        builder.add_connection("right", "result", "sink", "right_input")

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(builder.build())

        assert len(results) == 4
        assert all(k in results for k in ["root", "left", "right", "sink"])

    def test_single_node_workflow(self):
        """Single-node workflow works without topological sort issues."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "solo", {"code": "result = {'v': 42}"})

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(builder.build())

        assert "solo" in results

    def test_repeated_executions(self):
        """Repeated executions should work with cached topo sort."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "node", {"code": "result = {'v': 1}"})
        workflow = builder.build()

        with LocalRuntime() as runtime:
            r1, id1 = runtime.execute(workflow)
            r2, id2 = runtime.execute(workflow)
            r3, id3 = runtime.execute(workflow)

        assert all("node" in r for r in [r1, r2, r3])
        assert len({id1, id2, id3}) == 3  # All unique run IDs

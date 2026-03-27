"""
Tier 2 edge case tests for LocalRuntime that require real threads or async event loops.

Extracted from tests/unit/runtime/test_local_runtime_edge_cases.py because these tests
either create real threads (cyclic executor) or trigger event loop conflicts on Python
3.13, which violates the Tier 1 contract (fast, isolated, deterministic).
"""

import pytest

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow


class TestLocalRuntimeEdgeCasesSlow:
    """Edge case tests that require real threads or async runtimes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.workflow = Workflow("test", "Test Workflow")
        self.runtime = LocalRuntime()

    @pytest.mark.asyncio
    async def test_execute_async_with_no_event_loop(self):
        """Test async execution when no event loop is running."""
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        self.workflow.add_node("node", node)

        # This should work even without explicit event loop
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        assert results["node"]["result"]["data"] == 1

    def test_cyclic_executor_failure(self):
        """Test handling of cyclic executor failure."""
        # Create cyclic workflow
        node1 = PythonCodeNode(name="node1", code="result = {'data': 1}")
        node2 = PythonCodeNode(name="node2", code="result = {'data': 2}")

        self.workflow.add_node("node1", node1)
        self.workflow.add_node("node2", node2)
        self.workflow.connect("node1", "node2", {"result": "input"})
        self.workflow.create_cycle("test_cycle").connect(
            "node2", "node1", {"result": "input"}
        ).max_iterations(2).build()

        # Execute - should handle cyclic workflow
        with LocalRuntime(enable_cycles=True) as runtime:
            results, run_id = runtime.execute(self.workflow)

        assert "node1" in results

    @pytest.mark.asyncio
    async def test_workflow_async_execution_with_node_errors(self):
        """Test workflow async execution with node execution errors."""
        # Create workflow with failing node
        good_node = PythonCodeNode(name="good", code="result = {'status': 'ok'}")
        bad_node = PythonCodeNode(
            name="bad", code="1/0"
        )  # Will raise ZeroDivisionError

        self.workflow.add_node("good", good_node)
        self.workflow.add_node("bad", bad_node)
        self.workflow.connect("good", "bad", {"result": "input"})

        # Execute - should handle node failure
        with self.runtime:
            results, run_id = self.runtime.execute(self.workflow)

        # Good node should have succeeded
        assert results["good"]["result"]["status"] == "ok"
        # Bad node result depends on error handling

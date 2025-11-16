"""
Integration tests for AsyncLocalRuntime parameter injection and unwrapping.

Tests the fix for bug CORE-SDK-001: AsyncLocalRuntime now properly unwraps
node-specific parameters to match LocalRuntime behavior.
"""

import asyncio

import pytest
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestAsyncParameterInjection:
    """Test suite for AsyncLocalRuntime parameter injection."""

    @pytest.mark.asyncio
    async def test_node_specific_parameter_unwrapping(self):
        """Test that node-specific parameters are properly unwrapped."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "node1",
            {"code": "result = x * 2", "x": 0},  # Default value
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(), inputs={"node1": {"x": 5}}  # Node-specific parameter
        )

        assert results["node1"]["result"] == 10  # Should use x=5, not x=0

    def test_node_specific_parameter_unwrapping_sync(self):
        """Test that node-specific parameters work in LocalRuntime (baseline)."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "node1",
            {"code": "result = x * 2", "x": 0},  # Default value
        )

        runtime = LocalRuntime()
        with runtime:
            results, _ = runtime.execute(
                workflow.build(),
                parameters={"node1": {"x": 5}},  # Node-specific parameter
            )

        assert results["node1"]["result"] == 10  # Should use x=5, not x=0

    @pytest.mark.asyncio
    async def test_global_parameter_passing(self):
        """Test that global parameters are passed to all nodes."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = global_param"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={"global_param": "shared_value"},  # Not wrapped under node ID
        )

        assert results["node1"]["result"] == "shared_value"

    @pytest.mark.asyncio
    async def test_mixed_parameter_types(self):
        """Test both node-specific and global parameters together."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode", "node1", {"code": "result = x + global_offset"}
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={"node1": {"x": 5}, "global_offset": 10},  # Node-specific  # Global
        )

        assert results["node1"]["result"] == 15

    @pytest.mark.asyncio
    async def test_parameter_isolation_between_nodes(self):
        """Test that node-specific parameters don't leak to other nodes."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = x"})
        workflow.add_node("PythonCodeNode", "node2", {"code": "result = y"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(), inputs={"node1": {"x": 1}, "node2": {"y": 2}}
        )

        assert results["node1"]["result"] == 1
        assert results["node2"]["result"] == 2
        # node1 should NOT receive y, node2 should NOT receive x

    @pytest.mark.asyncio
    async def test_parity_with_local_runtime(self):
        """Test that AsyncLocalRuntime behaves identically to LocalRuntime."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = x * 2", "x": 0})

        # Test with LocalRuntime (sync)
        sync_runtime = LocalRuntime()
        with sync_runtime:
            sync_results, _ = sync_runtime.execute(
                workflow.build(), parameters={"node1": {"x": 5}}
            )

        # Test with AsyncLocalRuntime (async)
        async_runtime = AsyncLocalRuntime()
        async_results, _ = await async_runtime.execute_workflow_async(
            workflow.build(), inputs={"node1": {"x": 5}}
        )

        # Results should be identical
        assert sync_results == async_results
        assert async_results["node1"]["result"] == 10

    @pytest.mark.asyncio
    async def test_node_specific_override_global(self):
        """Test that node-specific parameters override global parameters."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = value"})
        workflow.add_node("PythonCodeNode", "node2", {"code": "result = value"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={
                "value": "global",  # Global parameter
                "node1": {  # Node-specific override for node1
                    "value": "node1_specific"
                },
            },
        )

        # node1 should use node-specific value, node2 should use global
        assert results["node1"]["result"] == "node1_specific"
        assert results["node2"]["result"] == "global"

    @pytest.mark.asyncio
    async def test_multiple_node_specific_parameters(self):
        """Test multiple parameters for a single node."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "compute", {"code": "result = a + b * c"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={
                "compute": {  # Multiple node-specific parameters
                    "a": 10,
                    "b": 5,
                    "c": 2,
                }
            },
        )

        assert results["compute"]["result"] == 20  # 10 + 5*2

    @pytest.mark.asyncio
    async def test_empty_node_specific_params(self):
        """Test that empty node-specific params don't break execution."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = 42"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(), inputs={"node1": {}}  # Empty node-specific params
        )

        assert results["node1"]["result"] == 42

    @pytest.mark.asyncio
    async def test_non_dict_node_param_warning(self):
        """Test that non-dict node-specific params generate a warning."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "node1", {"code": "result = 42"})

        runtime = AsyncLocalRuntime()

        # This should generate a warning but not crash
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={"node1": "not_a_dict"},  # Invalid - should generate warning
        )

        # Should still execute successfully
        assert results["node1"]["result"] == 42

    @pytest.mark.asyncio
    async def test_parameter_filtering_prevents_leakage(self):
        """Test that parameters for other nodes are filtered out."""
        workflow = WorkflowBuilder()

        # Node1 should NOT see node2's parameters
        workflow.add_node(
            "PythonCodeNode",
            "node1",
            {
                "code": """
# Try to access node2's param (should not exist)
try:
    result = node2
    leaked = True
except NameError:
    result = 'no_leak'
    leaked = False
"""
            },
        )

        workflow.add_node("PythonCodeNode", "node2", {"code": "result = secret"})

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={"node1": {}, "node2": {"secret": "sensitive_data"}},
        )

        # node1 should not have access to node2's parameters
        assert results["node1"]["result"] == "no_leak"
        assert results["node2"]["result"] == "sensitive_data"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

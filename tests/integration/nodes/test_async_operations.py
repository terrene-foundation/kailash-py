"""Tests for asynchronous nodes in the Kailash SDK."""

import os
import sys

# Add the project root to the path to ensure imports work correctly in tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import asyncio
from typing import Any

import pytest
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.logic.async_operations import AsyncMergeNode, AsyncSwitchNode
from kailash.runtime.parallel import ParallelRuntime
from kailash.sdk_exceptions import RuntimeExecutionError
from kailash.workflow import Workflow


class SimpleAsyncNode(AsyncNode):
    """Simple async node for testing."""

    def get_parameters(self) -> dict[str, Any]:
        """Define parameters for the node."""
        from kailash.nodes.base import NodeParameter

        return {
            "value": NodeParameter(
                name="value",
                type=int,
                required=False,
                default=0,
                description="Input value to double",
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Synchronous fallback implementation."""
        value = kwargs.get("value", 0)
        return {"output": value * 2}

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Async run implementation."""
        await asyncio.sleep(0.1)
        value = kwargs.get("value", 0)
        return {"output": value * 2}


@pytest.mark.asyncio
async def test_async_merge_concat():
    """Test AsyncMerge with concat operation."""
    # Setup
    merge_node = AsyncMergeNode(merge_type="concat")

    # Execute
    result = await merge_node.execute_async(
        data1=[1, 2, 3], data2=[4, 5, 6], data3=[7, 8, 9]
    )

    # Assert
    assert "merged_data" in result
    assert result["merged_data"] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


@pytest.mark.asyncio
async def test_async_merge_dict():
    """Test AsyncMerge with merge_dict operation."""
    # Setup
    merge_node = AsyncMergeNode(merge_type="merge_dict")

    # Execute
    result = await merge_node.execute_async(
        data1={"a": 1, "b": 2},
        data2={"c": 3, "d": 4},
        data3={"e": 5, "b": 10},  # Overwrites b from data1
    )

    # Assert
    assert "merged_data" in result
    assert result["merged_data"] == {"a": 1, "b": 10, "c": 3, "d": 4, "e": 5}


@pytest.mark.asyncio
async def test_async_merge_with_lists_of_dicts():
    """Test AsyncMerge with lists of dictionaries."""
    # Setup
    merge_node = AsyncMergeNode(merge_type="merge_dict", key="id")

    # Execute
    result = await merge_node.execute_async(
        data1=[{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}],
        data2=[{"id": 1, "value": 100}, {"id": 3, "value": 300}],
    )

    # Assert
    assert "merged_data" in result
    merged = result["merged_data"]
    assert len(merged) == 3
    assert {"id": 1, "name": "Item 1", "value": 100} in merged
    assert {"id": 2, "name": "Item 2"} in merged
    assert {"id": 3, "value": 300} in merged


@pytest.mark.asyncio
async def test_async_switch_boolean_condition():
    """Test AsyncSwitch with boolean condition."""
    # Setup
    switch_node = AsyncSwitchNode()

    # Execute with true condition
    result1 = await switch_node.execute_async(
        input_data={"status": "success"},
        condition_field="status",
        operator="==",
        value="success",
    )

    # Execute with false condition
    result2 = await switch_node.execute_async(
        input_data={"status": "error"},
        condition_field="status",
        operator="==",
        value="success",
    )

    # Assert
    assert result1["true_output"] == {"status": "success"}
    assert result1["false_output"] is None
    assert result2["true_output"] is None
    assert result2["false_output"] == {"status": "error"}


@pytest.mark.asyncio
async def test_async_switch_multi_case():
    """Test AsyncSwitch with multiple cases."""
    # Setup
    switch_node = AsyncSwitchNode()

    # Execute
    result = await switch_node.execute_async(
        input_data={"status": "warning"},
        condition_field="status",
        cases=["success", "warning", "error"],
    )

    # Assert
    assert "case_warning" in result
    assert result["case_warning"] == {"status": "warning"}
    assert "default" in result
    assert result["default"] == {"status": "warning"}
    assert "condition_result" in result
    assert result["condition_result"] == "warning"


@pytest.mark.asyncio
async def test_parallel_runtime_execution():
    """Test ParallelRuntime with a simple workflow."""
    # Create a simple workflow
    workflow = Workflow(workflow_id="test_parallel", name="Test Parallel Workflow")

    # Add nodes
    workflow.add_node("source1", SimpleAsyncNode(value=5))
    workflow.add_node("source2", SimpleAsyncNode(value=10))
    workflow.add_node("merge", AsyncMergeNode())

    # Connect nodes
    workflow.connect("source1", "merge", {"output": "data1"})
    workflow.connect("source2", "merge", {"output": "data2"})

    # Create runtime
    runtime = ParallelRuntime(max_workers=2)

    # Execute
    results, run_id = await runtime.execute(workflow)

    # Assert
    assert "source1" in results
    assert "source2" in results
    assert "merge" in results

    assert results["source1"]["output"] == 10
    assert results["source2"]["output"] == 20
    assert results["merge"]["merged_data"] == [10, 20]


@pytest.mark.asyncio
async def test_parallel_execution_with_error_handling():
    """Test error handling in parallel execution."""

    # Create error node
    class ErrorNode(AsyncNode):
        def get_parameters(self) -> dict[str, Any]:
            """Define parameters for the node."""

            return {}

        def run(self, **kwargs) -> dict[str, Any]:
            """Synchronous fallback implementation."""
            raise ValueError("Simulated error in sync mode")

        async def async_run(self, **kwargs):
            """Async implementation that raises an error."""
            await asyncio.sleep(0.1)
            raise ValueError("Simulated error")

    # Create workflow
    workflow = Workflow(workflow_id="test_error", name="Test Error Handling")

    # Add nodes with dependencies between them to ensure error stops execution
    workflow.add_node("node1", SimpleAsyncNode(value=5))
    workflow.add_node("node2", ErrorNode())
    workflow.add_node("node3", SimpleAsyncNode(value=15))

    # Add dependency to ensure error propagation
    workflow.connect("node2", "node3", {"output": "value"})

    # Create runtime
    runtime = ParallelRuntime(max_workers=3)

    # Execute and expect exception
    with pytest.raises(RuntimeExecutionError):
        await runtime.execute(workflow)

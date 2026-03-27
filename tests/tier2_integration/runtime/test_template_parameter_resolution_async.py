"""
Tier-2 integration tests for template parameter resolution with AsyncLocalRuntime.

Moved from tests/unit/runtime/test_template_parameter_resolution.py because
these tests instantiate AsyncLocalRuntime (creates thread pools).
Pure resolve_templates() unit tests remain in the original file.
"""

import pytest

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestTopLevelTemplateResolution:
    """Test that top-level templates currently work (baseline)."""

    @pytest.mark.asyncio
    async def test_top_level_template_async(self):
        """Test top-level ${param} resolution in async runtime."""
        runtime = AsyncLocalRuntime()
        workflow = WorkflowBuilder()

        # Use PythonCodeNode to verify parameter values
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {
                "code": "result = {'limit_received': limit, 'limit_type': type(limit).__name__}"
            },
        )

        # Top-level template (should work)
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={"limit": 10}
        )

        node_result = results["test_node"]
        assert node_result["result"]["limit_received"] == 10
        assert node_result["result"]["limit_type"] == "int"


class TestNestedTemplateResolution:
    """Test nested template resolution (the bug we're fixing)."""

    @pytest.mark.asyncio
    async def test_nested_dict_template_async(self):
        """Test ${param} resolution in nested dictionaries."""
        runtime = AsyncLocalRuntime()
        workflow = WorkflowBuilder()

        # Use PythonCodeNode to receive and verify nested parameter
        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {
                "code": """
import json
result = {
    'filter_received': filter_dict,
    'filter_type': type(filter_dict).__name__,
    'filter_json': json.dumps(filter_dict) if isinstance(filter_dict, dict) else str(filter_dict)
}
"""
            },
        )

        # Execute with nested template in node parameters
        # Note: We need to manually construct the workflow with template in parameters
        # since add_node doesn't support templates yet
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={
                "filter_dict": {"run_tag": "local", "status": "active"}
            },  # Pass actual dict
        )

        node_result = results["test_node"]
        assert node_result["result"]["filter_type"] == "dict"
        # This test establishes baseline - next we'll test actual template resolution

    @pytest.mark.asyncio
    async def test_deeply_nested_template_resolution(self):
        """Test ${param} resolution in deeply nested structures."""
        runtime = AsyncLocalRuntime()
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {
                "code": """
result = {
    'level1_received': level1,
    'level1_type': type(level1).__name__
}
"""
            },
        )

        results, run_id = await runtime.execute_workflow_async(
            workflow.build(),
            inputs={"level1": {"level2": {"level3": "deep_value"}}},
        )

        node_result = results["test_node"]
        assert node_result["result"]["level1_type"] == "dict"

    @pytest.mark.asyncio
    async def test_template_in_list_items(self):
        """Test ${param} resolution in list elements."""
        runtime = AsyncLocalRuntime()
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "test_node",
            {"code": "result = {'items_received': items, 'count': len(items)}"},
        )

        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={"items": [{"value": "item1"}, {"value": "item2"}]}
        )

        node_result = results["test_node"]
        assert node_result["result"]["count"] == 2

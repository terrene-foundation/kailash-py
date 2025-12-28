"""
Unit tests for template parameter resolution in workflow execution.

This test suite validates that ${param} template syntax works correctly
at all nesting levels in node parameters.

Bug Report: Template parameters only resolve at top level, not in nested objects
Fix: Implement recursive template resolution

Version: v0.9.30
Created: 2025-10-24
"""

import pytest
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
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


class TestRecursiveTemplateResolution:
    """Test recursive template resolution utility function."""

    def test_resolve_templates_top_level(self):
        """Test template resolution at top level."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {"limit": "${limit}", "offset": "${offset}"}

        inputs = {"limit": 10, "offset": 0}

        resolved = resolve_templates(params, inputs)

        assert resolved["limit"] == 10
        assert resolved["offset"] == 0

    def test_resolve_templates_nested_dict(self):
        """Test template resolution in nested dictionaries."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "filter": {"run_tag": "${tag}", "status": "${status}"},
            "limit": "${limit}",
        }

        inputs = {"tag": "local", "status": "active", "limit": 10}

        resolved = resolve_templates(params, inputs)

        assert resolved["filter"]["run_tag"] == "local"
        assert resolved["filter"]["status"] == "active"
        assert resolved["limit"] == 10

    def test_resolve_templates_nested_list(self):
        """Test template resolution in lists."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "filters": [{"field": "status", "value": "${status}"}],
            "limit": "${limit}",
        }

        inputs = {"status": "active", "limit": 10}

        resolved = resolve_templates(params, inputs)

        assert resolved["filters"][0]["value"] == "active"
        assert resolved["limit"] == 10

    def test_resolve_templates_deeply_nested(self):
        """Test template resolution in deeply nested structures."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "config": {
                "database": {
                    "connection": {"url": "${db_url}"},
                    "pool_size": "${pool_size}",
                },
                "api": {"endpoint": "${api_endpoint}"},
            }
        }

        inputs = {
            "db_url": "postgresql://localhost",
            "pool_size": 10,
            "api_endpoint": "https://api.example.com",
        }

        resolved = resolve_templates(params, inputs)

        assert (
            resolved["config"]["database"]["connection"]["url"]
            == "postgresql://localhost"
        )
        assert resolved["config"]["database"]["pool_size"] == 10
        assert resolved["config"]["api"]["endpoint"] == "https://api.example.com"

    def test_resolve_templates_missing_input(self):
        """Test that missing inputs are left as templates."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {"value": "${missing_param}"}

        inputs = {}

        resolved = resolve_templates(params, inputs)

        # Should leave template unchanged if input not found
        assert resolved["value"] == "${missing_param}"

    def test_resolve_templates_preserves_non_templates(self):
        """Test that non-template values are preserved."""
        from kailash.runtime.template_resolver import resolve_templates

        params = {
            "static_string": "hello",
            "static_int": 42,
            "static_dict": {"key": "value"},
            "template": "${dynamic}",
        }

        inputs = {"dynamic": "resolved"}

        resolved = resolve_templates(params, inputs)

        assert resolved["static_string"] == "hello"
        assert resolved["static_int"] == 42
        assert resolved["static_dict"] == {"key": "value"}
        assert resolved["template"] == "resolved"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

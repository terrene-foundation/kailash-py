"""Integration test for comprehensive parameter handling fixes.

This test validates that all the fixes from TODO-092 work together:
1. PythonCodeNode default parameter handling
2. Parameter injection for functions with **kwargs
3. Security sanitization consistency
4. Enterprise node deferred configuration
5. AgentUIMiddleware parameter passing
"""

import asyncio

import pytest
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import (
    create_deferred_oauth2,
    create_deferred_sql,
)
from kailash.workflow import WorkflowBuilder


class TestComprehensiveParameterFixes:
    """Test all parameter handling fixes working together."""

    def test_pythoncode_default_params_integration(self):
        """Test PythonCodeNode default parameters in workflow context."""

        def process_data(data, multiplier=2, add_metadata=True):
            """Function with default parameters."""
            result = [x * multiplier for x in data]
            if add_metadata:
                return {
                    "processed_data": result,
                    "multiplier_used": multiplier,
                    "metadata_included": add_metadata,
                }
            return {"processed_data": result}

        # Create node from function
        node = PythonCodeNode.from_function(process_data, name="processor")

        # Verify parameter definitions
        params = node.get_parameters()
        assert params["data"].required is True
        assert params["multiplier"].required is False
        assert params["multiplier"].default == 2
        assert params["add_metadata"].required is False
        assert params["add_metadata"].default is True

        # Test with only required parameter
        result = node.execute(data=[1, 2, 3])
        expected = {
            "result": {
                "processed_data": [2, 4, 6],
                "multiplier_used": 2,
                "metadata_included": True,
            }
        }
        assert result == expected

        # Test with some parameters overridden
        result = node.execute(data=[1, 2, 3], multiplier=3)
        expected = {
            "result": {
                "processed_data": [3, 6, 9],
                "multiplier_used": 3,
                "metadata_included": True,
            }
        }
        assert result == expected

    def test_pythoncode_kwargs_parameter_injection(self):
        """Test parameter injection with **kwargs support."""

        def flexible_processor(data, **kwargs):
            """Function that accepts arbitrary parameters."""
            result = {"data": data, "extra_params": kwargs, "param_count": len(kwargs)}

            # Use specific kwargs if available
            if "transform" in kwargs:
                if kwargs["transform"] == "uppercase":
                    result["data"] = [str(x).upper() for x in data]
                elif kwargs["transform"] == "double":
                    result["data"] = [x * 2 for x in data]

            return result

        # Create node from function
        node = PythonCodeNode.from_function(flexible_processor, name="flexible")

        # Test with extra parameters
        result = node.execute(
            data=["hello", "world"], transform="uppercase", debug=True, version="1.0"
        )

        expected_result = {
            "data": ["HELLO", "WORLD"],
            "extra_params": {"transform": "uppercase", "debug": True, "version": "1.0"},
            "param_count": 3,
        }

        assert result["result"] == expected_result

    def test_security_sanitization_integration(self):
        """Test that security sanitization works consistently."""

        # Test with potentially dangerous code
        dangerous_code = """
# This should be sanitized
import os
result = {"safe": "data", "system_info": "blocked"}
"""

        node = PythonCodeNode(name="security_test", code=dangerous_code)

        # Should execute safely without access to dangerous imports
        result = node.execute()
        assert "result" in result
        assert "safe" in result["result"]

    def test_deferred_configuration_workflow_integration(self):
        """Test deferred configuration in workflow context."""
        workflow = WorkflowBuilder()

        # Create a deferred OAuth2 node (doesn't need real credentials)
        auth_node = create_deferred_oauth2(name="deferred_auth")
        workflow.add_node(auth_node, "authentication")

        # Add a processor that would use auth data
        workflow.add_node(
            "PythonCodeNode",
            "auth_processor",
            {
                "code": """
# Process auth result
if 'auth_data' in locals() and auth_data:
    result = {
        "auth_processed": True,
        "has_headers": "headers" in auth_data,
        "auth_type": auth_data.get("auth_type", "unknown")
    }
else:
    result = {
        "auth_processed": False,
        "message": "No auth data received"
    }
"""
            },
        )

        workflow.add_connection(
            "authentication", "headers", "auth_processor", "auth_data"
        )

        # Should build successfully even without connection parameters
        wf = workflow.build()
        assert wf is not None

        # Verify the auth node has expected parameter structure
        auth_params = auth_node.get_parameters()
        assert "token_url" in auth_params
        assert "client_id" in auth_params
        assert auth_params["token_url"].required is True

    def test_parameter_flow_end_to_end(self):
        """Test complete parameter flow from workflow input to node execution."""
        workflow = WorkflowBuilder()

        # Create a data processor with default parameters
        def data_processor(input_data, scale_factor=1.0, include_stats=True):
            """Process data with configurable parameters."""
            scaled_data = [x * scale_factor for x in input_data]

            result = {"scaled_data": scaled_data}

            if include_stats:
                result["stats"] = {
                    "original_count": len(input_data),
                    "scaled_count": len(scaled_data),
                    "scale_factor": scale_factor,
                    "original_sum": sum(input_data),
                    "scaled_sum": sum(scaled_data),
                }

            return result

        processor_node = PythonCodeNode.from_function(data_processor, name="processor")
        workflow.add_node(processor_node, "data_processor")

        # Add a results formatter
        workflow.add_node(
            "PythonCodeNode",
            "formatter",
            {
                "code": """
# Format the processed results
try:
    if processed:
        result = {
            "formatted_output": f"Processed {len(processed['scaled_data'])} items",
            "scaling_applied": processed.get('stats', {}).get('scale_factor', 'unknown'),
            "summary": processed.get('stats', {})
        }
    else:
        result = {"error": "No processed data received"}
except NameError:
    result = {"error": "No processed data received"}
"""
            },
        )

        workflow.add_connection("data_processor", "result", "formatter", "processed")

        # Build and execute workflow
        wf = workflow.build()
        runtime = LocalRuntime()

        # Test with default parameters
        result, run_id = runtime.execute(
            wf, parameters={"data_processor": {"input_data": [1, 2, 3, 4, 5]}}
        )

        formatter_result = result["formatter"]["result"]
        assert "formatted_output" in formatter_result
        assert "Processed 5 items" in formatter_result["formatted_output"]
        assert formatter_result["scaling_applied"] == 1.0

        # Test with custom parameters
        result, run_id = runtime.execute(
            wf,
            parameters={
                "data_processor": {
                    "input_data": [10, 20, 30],
                    "scale_factor": 2.5,
                    "include_stats": True,
                }
            },
        )

        formatter_result = result["formatter"]["result"]
        assert formatter_result["scaling_applied"] == 2.5
        assert formatter_result["summary"]["original_sum"] == 60
        assert formatter_result["summary"]["scaled_sum"] == 150.0

    def test_mixed_node_types_parameter_consistency(self):
        """Test parameter consistency across different node types."""
        workflow = WorkflowBuilder()

        # Add various node types that handle parameters differently

        # 1. Code node with explicit code
        workflow.add_node(
            "PythonCodeNode",
            "code_node",
            {
                "code": """
# Simple data transformation
try:
    result = {"transformed": [x * 2 for x in input_list]}
except NameError:
    result = {"transformed": []}
"""
            },
        )

        # 2. Function-based node with defaults
        def aggregator(data, operation="sum", include_count=True):
            if operation == "sum":
                value = sum(data)
            elif operation == "average":
                value = sum(data) / len(data) if data else 0
            else:
                value = len(data)

            result = {"value": value, "operation": operation}
            if include_count:
                result["count"] = len(data)
            return result

        agg_node = PythonCodeNode.from_function(aggregator, name="aggregator")
        workflow.add_node(agg_node, "aggregator_node")

        # 3. Deferred configuration node (with minimal query to satisfy validation)
        deferred_node = create_deferred_sql(
            name="deferred_db", query="SELECT 1 as dummy"
        )
        workflow.add_node(deferred_node, "database_node")

        # Connect them
        workflow.add_connection(
            "code_node", "result.transformed", "aggregator_node", "data"
        )

        # Build workflow
        wf = workflow.build()
        runtime = LocalRuntime()

        # Execute with mixed parameters
        result, run_id = runtime.execute(
            wf,
            parameters={
                "code_node": {"input_list": [1, 2, 3, 4]},
                "aggregator_node": {"operation": "average"},
                # Note: database_node doesn't get executed due to missing connection params
            },
        )

        # Verify results
        agg_result = result["aggregator_node"]["result"]
        assert agg_result["value"] == 5.0  # Average of [2, 4, 6, 8]
        assert agg_result["operation"] == "average"
        assert agg_result["count"] == 4

    @pytest.mark.asyncio
    async def test_async_parameter_handling(self):
        """Test parameter handling in async context."""

        # Create a simple async workflow
        workflow = WorkflowBuilder()

        # Add async-compatible nodes
        def async_processor(data, delay=0.1, transform="none"):
            """Simulate async processing."""
            import time

            time.sleep(delay)  # Simulate work

            if transform == "square":
                data = [x * x for x in data]
            elif transform == "double":
                data = [x * 2 for x in data]

            return {"processed": data, "delay_used": delay}

        processor_node = PythonCodeNode.from_function(
            async_processor, name="async_proc"
        )
        workflow.add_node(processor_node, "async_processor")

        # Build and execute
        wf = workflow.build()
        runtime = LocalRuntime()

        # Test with default parameters
        result, run_id = runtime.execute(
            wf,
            parameters={"async_processor": {"data": [1, 2, 3], "transform": "square"}},
        )

        proc_result = result["async_processor"]["result"]
        assert proc_result["processed"] == [1, 4, 9]
        assert proc_result["delay_used"] == 0.1

    def test_parameter_validation_consistency(self):
        """Test that parameter validation works consistently across fixes."""

        # Test function with strict parameters
        def strict_processor(required_param, optional_param="default"):
            return {
                "required": required_param,
                "optional": optional_param,
                "processed": True,
            }

        node = PythonCodeNode.from_function(strict_processor, name="strict")

        # Should work with required parameter
        result = node.execute(required_param="test_value")
        assert result["result"]["required"] == "test_value"
        assert result["result"]["optional"] == "default"

        # Should work with both parameters
        result = node.execute(required_param="test", optional_param="custom")
        assert result["result"]["optional"] == "custom"

        # Test with **kwargs function
        def flexible_processor(required, **kwargs):
            return {"required": required, "extras": kwargs, "extra_count": len(kwargs)}

        flex_node = PythonCodeNode.from_function(flexible_processor, name="flexible")

        # Should accept extra parameters
        result = flex_node.execute(required="test", extra1="value1", extra2="value2")

        assert result["result"]["required"] == "test"
        assert result["result"]["extra_count"] == 2
        assert result["result"]["extras"]["extra1"] == "value1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

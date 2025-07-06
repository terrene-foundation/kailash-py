#!/usr/bin/env python3
"""
Simple test for enterprise parameter injection.
"""

from typing import Any, Dict

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def test_parameter_injection():
    """Test enterprise parameter injection functionality."""

    def process_with_kwargs(data: str, **kwargs) -> Dict[str, Any]:
        """Function that accepts arbitrary parameters via **kwargs."""
        injected_params = {
            "tenant_id": kwargs.get("tenant_id", "default"),
            "processing_mode": kwargs.get("processing_mode", "standard"),
            "debug_enabled": kwargs.get("debug_enabled", False),
        }

        return {
            "processed_data": data.upper(),
            "injected_params": injected_params,
            "total_kwargs": len(kwargs),
        }

    # Create workflow
    workflow = WorkflowBuilder()
    node = PythonCodeNode.from_function(process_with_kwargs, name="processor")
    workflow.add_node_instance(node)

    # Execute with workflow-level parameters
    runtime = LocalRuntime()
    results, run_id = runtime.execute(
        workflow.build(),
        parameters={
            "processor": {"data": "test_input"},  # Required input for the function
            "tenant_id": "enterprise_tenant_123",
            "processing_mode": "enhanced",
            "debug_enabled": True,
            "audit_user": "test_user",
        },
    )

    # Validate results
    output = results["processor"]
    print(f"Results: {output}")

    # Test assertions
    assert (
        output["processed_data"] == "TEST_INPUT"
    )  # Function should uppercase the input
    assert output["injected_params"]["tenant_id"] == "enterprise_tenant_123"
    assert output["injected_params"]["processing_mode"] == "enhanced"
    assert output["injected_params"]["debug_enabled"] is True
    assert output["total_kwargs"] >= 3  # Should receive multiple workflow parameters

    print("✅ Enterprise parameter injection working correctly!")
    return True


if __name__ == "__main__":
    test_parameter_injection()

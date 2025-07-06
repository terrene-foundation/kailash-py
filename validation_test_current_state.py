#!/usr/bin/env python3
"""
Validation test for current enterprise parameter injection state.
This test validates the documentation against actual implementation.
"""

import os
import subprocess
import sys
import tempfile
from typing import Any, Dict


def test_enterprise_parameter_injection():
    """Test enterprise parameter injection as documented."""

    # Test 1: Basic PythonCodeNode with **kwargs
    print("Testing PythonCodeNode with **kwargs parameter injection...")

    test_code = '''
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code.python import PythonCodeNode

def process_with_kwargs(data: str, **kwargs) -> Dict[str, Any]:
    """Function that accepts arbitrary parameters via **kwargs."""
    injected_params = {
        "tenant_id": kwargs.get("tenant_id", "default"),
        "processing_mode": kwargs.get("processing_mode", "standard"),
        "debug_enabled": kwargs.get("debug_enabled", False)
    }

    return {
        "processed_data": data.upper(),
        "injected_params": injected_params,
        "total_kwargs": len(kwargs)
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
        "audit_user": "test_user"
    }
)

# Validate results
output = results["processor"]
print(f"Results: {output}")

# Test assertions
assert output["processed_data"] == "TEST_INPUT"  # Function should uppercase the input
assert output["injected_params"]["tenant_id"] == "enterprise_tenant_123"
assert output["injected_params"]["processing_mode"] == "enhanced"
assert output["injected_params"]["debug_enabled"] is True
assert output["total_kwargs"] >= 3  # Should receive multiple workflow parameters

print("✅ Test 1 PASSED: **kwargs parameter injection working")
'''

    # Test 2: Mixed parameter format handling
    print("\nTesting mixed parameter format handling...")

    test_code2 = """
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with multiple nodes
workflow = WorkflowBuilder()

def node1_func(data: str, **kwargs) -> Dict[str, Any]:
    return {"processed": data, "received_params": list(kwargs.keys())}

def node2_func(input_data: str, **kwargs) -> Dict[str, Any]:
    return {"final": input_data, "workflow_params": list(kwargs.keys())}

workflow.add_node("PythonCodeNode", "node1", function=node1_func)
workflow.add_node("PythonCodeNode", "node2", function=node2_func)
workflow.add_connection("node1", "node2", "processed", "input_data")

# Execute with MIXED format: both node-specific AND workflow-level parameters
runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        # Node-specific parameters (old format)
        "node1": {"data": "test_data"},
        # Workflow-level parameters (new enterprise format)
        "global_tenant": "enterprise_123",
        "processing_context": "production",
        "audit_enabled": True
    }
)

# Validate that both nodes received workflow-level parameters
node1_output = results["node1"]
node2_output = results["node2"]

print(f"Node1 received params: {node1_output['received_params']}")
print(f"Node2 received params: {node2_output['workflow_params']}")

# Both nodes should receive workflow-level parameters
assert "global_tenant" in node1_output["received_params"]
assert "processing_context" in node1_output["received_params"]
assert "global_tenant" in node2_output["workflow_params"]
assert "processing_context" in node2_output["workflow_params"]

print("✅ Test 2 PASSED: Mixed parameter format handling working")
"""

    # Test 3: Parameter precedence
    print("\nTesting parameter precedence...")

    test_code3 = """
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

def precedence_func(data: str, mode: str = "default", **kwargs) -> Dict[str, Any]:
    return {
        "data": data,
        "mode": mode,  # Should come from node-specific params
        "global_param": kwargs.get("global_param", "not_found")  # Should come from workflow-level
    }

workflow.add_node("PythonCodeNode", "precedence_test", function=precedence_func)

runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        # Node-specific parameters should take precedence
        "precedence_test": {"data": "test", "mode": "node_specific"},
        # Workflow-level parameters
        "global_param": "workflow_level",
        "mode": "workflow_level_mode"  # Should NOT override node-specific
    }
)

output = results["precedence_test"]
print(f"Precedence results: {output}")

# Node-specific "mode" should win over workflow-level "mode"
assert output["mode"] == "node_specific"
# Workflow-level parameters should still be injected
assert output["global_param"] == "workflow_level"

print("✅ Test 3 PASSED: Parameter precedence working correctly")
"""

    try:
        exec(test_code)
        exec(test_code2)
        exec(test_code3)
        print(
            "\n🎉 ALL TESTS PASSED - Enterprise parameter injection working correctly!"
        )
        return True
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_enterprise_parameter_injection()
    sys.exit(0 if success else 1)

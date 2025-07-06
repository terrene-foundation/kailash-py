#!/usr/bin/env python3
"""Debug script to understand parameter injection flow in the Kailash SDK."""

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.workflow.builder import WorkflowBuilder


def debug_parameter_injection():
    """Debug the parameter injection mechanism."""

    print("=" * 60)
    print("DEBUGGING PARAMETER INJECTION FLOW")
    print("=" * 60)

    # Create a simple function that accepts **kwargs
    def test_processor(data, **kwargs):
        """Test function that should receive workflow parameters via **kwargs."""
        print("test_processor called with:")
        print(f"  data: {data}")
        print(f"  kwargs: {kwargs}")
        return {
            "processed_data": data,
            "received_kwargs": dict(kwargs),
            "kwargs_keys": list(kwargs.keys()),
        }

    # Create node
    node = PythonCodeNode.from_function(test_processor, name="test_processor")

    print("\n1. DIRECT NODE EXECUTION:")
    print("-" * 30)

    # Test direct execution with extra parameters
    direct_inputs = {
        "data": [1, 2, 3],
        "tenant_id": "test_tenant",
        "processing_mode": "debug",
    }

    print(f"Direct inputs: {direct_inputs}")
    direct_result = node.execute_code(direct_inputs)
    print(f"Direct result: {direct_result}")

    print("\n2. WORKFLOW EXECUTION - NODE-SPECIFIC FORMAT:")
    print("-" * 50)

    # Create workflow
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "processor", {"function": test_processor})
    workflow = builder.build()

    # Test with node-specific parameters
    runtime = LocalRuntime(debug=True)

    node_specific_params = {
        "processor": {
            "data": [4, 5, 6],
            "tenant_id": "node_specific_tenant",
            "audit_mode": "enabled",
        }
    }

    print(f"Node-specific parameters: {node_specific_params}")
    result1 = runtime.execute(workflow, parameters=node_specific_params)
    if isinstance(result1, tuple):
        result1 = result1[0]
    print(f"Node-specific result: {result1['processor']['result']}")

    print("\n3. WORKFLOW EXECUTION - WORKFLOW-LEVEL FORMAT:")
    print("-" * 52)

    # Test with workflow-level parameters (should be injected)
    workflow_params = {
        "processor": {"data": [7, 8, 9]},  # Node-specific
        "tenant_id": "workflow_tenant",  # Should be injected
        "security_level": "high",  # Should be injected
    }

    print(f"Workflow parameters: {workflow_params}")

    # Check if parameters are detected as node-specific or workflow-level
    is_node_specific = runtime._is_node_specific_format(workflow_params, workflow)
    print(f"Detected as node-specific format: {is_node_specific}")

    # See what the parameter injector does
    if not is_node_specific:
        injector = WorkflowParameterInjector(workflow, debug=True)
        transformed = injector.transform_workflow_parameters(workflow_params)
        print(f"Transformed parameters: {transformed}")

    result2 = runtime.execute(workflow, parameters=workflow_params)
    if isinstance(result2, tuple):
        result2 = result2[0]
    print(f"Workflow-level result: {result2['processor']['result']}")

    print("\n4. PARAMETER INJECTOR ANALYSIS:")
    print("-" * 35)

    # Analyze the parameter injector behavior
    injector = WorkflowParameterInjector(workflow, debug=True)

    # Get entry nodes
    entry_nodes = injector._get_entry_nodes()
    print(f"Entry nodes found: {list(entry_nodes.keys())}")

    # Check parameter mapping for each entry node
    for node_id, node_instance in entry_nodes.items():
        print(f"\nNode '{node_id}' parameter analysis:")
        node_param_defs = node_instance.get_parameters()
        print(f"  Parameter definitions: {list(node_param_defs.keys())}")

        # Test parameter mapping
        test_params = ["tenant_id", "security_level", "data"]
        for param in test_params:
            mapped = injector._get_mapped_parameter_name(
                param, "test_value", node_param_defs
            )
            print(f"  '{param}' maps to: {mapped}")

    print("\n5. CRITICAL ISSUE ANALYSIS:")
    print("-" * 30)

    # The issue: workflow-level parameters like "tenant_id" don't have direct mappings
    # in PythonCodeNode parameter definitions, so they don't get injected

    print("Issue identified:")
    print(
        "- PythonCodeNode.get_parameters() only returns explicitly defined parameters"
    )
    print(
        "- Functions with **kwargs don't have 'tenant_id' in their parameter definitions"
    )
    print("- _get_mapped_parameter_name() can't find a mapping for 'tenant_id'")
    print("- Therefore, workflow-level parameters are not injected into **kwargs")

    print("\nTo fix this, we need to enhance _get_mapped_parameter_name() to:")
    print("1. Detect when a function accepts **kwargs")
    print("2. Allow any unmapped parameters to be passed through to **kwargs functions")


if __name__ == "__main__":
    debug_parameter_injection()

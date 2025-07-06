#!/usr/bin/env python3
"""Debug the complete parameter flow from runtime to PythonCodeNode execution."""

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.workflow.builder import WorkflowBuilder


def debug_complete_flow():
    """Debug the complete parameter injection flow."""

    print("=" * 80)
    print("COMPLETE PARAMETER INJECTION FLOW ANALYSIS")
    print("=" * 80)

    # Create a test function that accepts **kwargs
    def test_processor(data, **kwargs):
        """Test function that should receive workflow parameters."""
        print(f"  FUNCTION CALLED with data={data}, kwargs={kwargs}")
        return {"processed_data": data, "kwargs_received": dict(kwargs)}

    # Create workflow
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "processor", {"function": test_processor})
    workflow = builder.build()

    # Get the actual node instance
    processor_node = workflow._node_instances["processor"]
    print(f"Processor node type: {type(processor_node)}")
    print(f"Processor node function: {processor_node.function}")

    # Check if the function accepts **kwargs
    import inspect

    sig = inspect.signature(test_processor)
    accepts_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
    )
    print(f"Function accepts **kwargs: {accepts_kwargs}")

    # Test the node's parameter detection
    node_params = processor_node.get_parameters()
    print(f"Node parameter definitions: {list(node_params.keys())}")

    runtime = LocalRuntime(debug=True)

    print("\n" + "=" * 50)
    print("TEST CASE: Mixed parameters (the failing case)")
    print("=" * 50)

    # This is the problematic case - mixed parameters
    mixed_params = {
        "processor": {"data": [1, 2, 3]},  # Node-specific
        "tenant_id": "test_tenant",  # Should be injected
        "security_level": "high",  # Should be injected
    }

    print(f"Input parameters: {mixed_params}")

    # Step 1: Format detection
    is_node_specific = runtime._is_node_specific_format(mixed_params, workflow)
    print(
        f"1. Format detection: {'node-specific' if is_node_specific else 'workflow-level'}"
    )

    # Step 2: Parameter processing
    processed_params = runtime._process_workflow_parameters(workflow, mixed_params)
    print(f"2. Processed parameters: {processed_params}")

    # Step 3: Parameter extraction for the processor node
    node_id = "processor"
    node_specific_params = processed_params.get(node_id, {}) if processed_params else {}
    print(f"3. Parameters for node '{node_id}': {node_specific_params}")

    # Step 4: What the WorkflowParameterInjector should do (if it was called)
    print("\n4. What WorkflowParameterInjector SHOULD do:")
    injector = WorkflowParameterInjector(workflow, debug=True)

    # Extract non-node-specific parameters
    workflow_level_params = {
        k: v for k, v in mixed_params.items() if k not in workflow.graph.nodes()
    }
    print(f"   Workflow-level params to inject: {workflow_level_params}")

    if workflow_level_params:
        # This is where the issue is - these parameters should be injected
        transformed = injector.transform_workflow_parameters(workflow_level_params)
        print(f"   Injector transformation result: {transformed}")

        # The issue: transform_workflow_parameters doesn't find mappings for tenant_id
        # because _get_mapped_parameter_name doesn't handle **kwargs functions properly
        entry_nodes = injector._get_entry_nodes()
        for node_id, node_instance in entry_nodes.items():
            node_param_defs = node_instance.get_parameters()
            print(
                f"   Node '{node_id}' parameter definitions: {list(node_param_defs.keys())}"
            )

            for param_name in workflow_level_params:
                mapped = injector._get_mapped_parameter_name(
                    param_name, workflow_level_params[param_name], node_param_defs
                )
                print(
                    f"   '{param_name}' -> {mapped} (should be '{param_name}' for **kwargs functions)"
                )

    print("\n5. ACTUAL EXECUTION:")
    result = runtime.execute(workflow, parameters=mixed_params)
    if isinstance(result, tuple):
        result = result[0]

    print(f"Final result: {result['processor']['result']}")

    print("\n" + "=" * 60)
    print("ROOT CAUSE IDENTIFIED:")
    print("=" * 60)
    print("1. Mixed parameters are detected as 'node-specific' format")
    print("2. Non-node parameters (tenant_id, security_level) are IGNORED")
    print("3. WorkflowParameterInjector is NOT called for node-specific format")
    print("4. Therefore, workflow-level parameters are lost")
    print()
    print("SOLUTION:")
    print("- Enhance _process_workflow_parameters to handle mixed format")
    print("- Extract workflow-level parameters even from node-specific format")
    print("- Inject them into nodes that can accept them (**kwargs functions)")


if __name__ == "__main__":
    debug_complete_flow()

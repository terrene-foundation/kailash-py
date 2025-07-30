#!/usr/bin/env python3
"""
Debug script to trace data flow in the nested conditional execution workflow.
"""

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def create_debug_workflow():
    """Create the same workflow as the failing test with debug outputs."""
    workflow = WorkflowBuilder()

    # Data source
    workflow.add_node(
        "PythonCodeNode",
        "data_source",
        {"code": "result = {'user_type': 'premium', 'region': 'US', 'value': 1000}"},
    )

    # User type switch
    workflow.add_node(
        "SwitchNode",
        "user_type_switch",
        {"condition_field": "user_type", "operator": "==", "value": "premium"},
    )

    # Premium validator with debug output
    workflow.add_node(
        "PythonCodeNode",
        "premium_validator",
        {
            "code": """
print(f"premium_validator received: {input}")
result = {'validated': True, 'tier': 'premium'}
print(f"premium_validator output: {result}")
        """
        },
    )

    # Region switch (nested under premium branch)
    workflow.add_node(
        "SwitchNode",
        "region_switch",
        {"condition_field": "region", "operator": "==", "value": "US"},
    )

    # Connect the workflow - CRITICAL: Check these connections!
    workflow.add_connection("data_source", "result", "user_type_switch", "input")
    workflow.add_connection(
        "user_type_switch", "true_output", "premium_validator", "input"
    )
    workflow.add_connection("premium_validator", "result", "region_switch", "input")

    return workflow.build()


def test_data_flow():
    """Test the data flow to see what region_switch actually receives."""

    print("Testing data flow in nested conditional execution...")

    workflow = create_debug_workflow()

    # Use skip_branches mode to reproduce the bug
    runtime = LocalRuntime(conditional_execution="skip_branches", debug=True)

    try:
        results, run_id = runtime.execute(workflow)

        print("\n" + "=" * 60)
        print("EXECUTION RESULTS:")
        print("=" * 60)

        for node_id, result in results.items():
            if result is not None:
                print(f"\n{node_id}:")
                if isinstance(result, dict):
                    for key, value in result.items():
                        print(f"  {key}: {value}")
                else:
                    print(f"  {result}")
            else:
                print(f"\n{node_id}: None (skipped)")

    except Exception as e:
        print(f"Execution failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_data_flow()

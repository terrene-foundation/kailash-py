#!/usr/bin/env python3
"""Test script to verify workflow context functions work in actual workflow execution."""

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def test_workflow_context_in_workflow():
    print("Testing workflow context in actual workflow execution...")

    # Create a workflow with multiple PythonCodeNodes that share context
    workflow = WorkflowBuilder()

    # Node 1: Set context values
    setter_code = """
set_workflow_context('shared_value', 42)
set_workflow_context('message', 'Hello from node 1')

result = {'status': 'context_set', 'values_set': 2}
"""

    workflow.add_node("PythonCodeNode", "setter", {"code": setter_code})

    # Node 2: Read context values
    getter_code = """
shared_value = get_workflow_context('shared_value', 0)
message = get_workflow_context('message', 'default')
missing = get_workflow_context('missing_key', 'not_found')

result = {
    'shared_value': shared_value,
    'message': message, 
    'missing': missing,
    'status': 'context_read'
}
"""

    workflow.add_node("PythonCodeNode", "getter", {"code": getter_code})

    # Node 3: Modify context and use data paths
    modifier_code = """
# Modify existing context
current_value = get_workflow_context('shared_value', 0)
set_workflow_context('shared_value', current_value * 2)

# Test data path functions
input_path = get_input_data_path('test_file.csv')
output_path = get_output_data_path('workflow_results.json') 

result = {
    'new_shared_value': get_workflow_context('shared_value'),
    'input_path': input_path,
    'output_path': output_path,
    'status': 'context_modified'
}
"""

    workflow.add_node("PythonCodeNode", "modifier", {"code": modifier_code})

    # Connect the nodes
    workflow.connect("setter", "getter")
    workflow.connect("getter", "modifier")

    # Execute the workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    print(f"Workflow execution completed with run_id: {run_id}")
    print("Results:")
    for node_name, result in results.items():
        print(f"  {node_name}: {result}")

    return results


if __name__ == "__main__":
    try:
        print("=== Testing Workflow Context in Workflow Execution ===")
        results = test_workflow_context_in_workflow()
        print("\n=== Test completed successfully! ===")

        # Verify the context was shared correctly
        setter_result = results.get("setter", {})
        getter_result = results.get("getter", {})
        modifier_result = results.get("modifier", {})

        print("\n=== Verification ===")
        print(f"Setter status: {setter_result.get('status')}")
        print(f"Getter shared_value: {getter_result.get('shared_value')}")
        print(f"Getter message: {getter_result.get('message')}")
        print(f"Modified shared_value: {modifier_result.get('new_shared_value')}")
        print(f"Data paths working: {bool(modifier_result.get('input_path'))}")

    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback

        traceback.print_exc()

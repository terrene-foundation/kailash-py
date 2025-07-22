#!/usr/bin/env python3
"""
Investigation of very specific edge cases that might cause parameter injection to be skipped.

Based on the code analysis, I found these potential skip conditions:
1. Line 619: parameters.get(node_id, {}) returns empty dict
2. Line 628: injected_params is falsy
3. WorkflowParameterInjector.transform_workflow_parameters returns empty dict
4. _separate_parameter_formats incorrectly classifies parameters
"""

import logging
import sys

# Add src to Python path
sys.path.insert(0, "src")

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


def setup_logging():
    """Setup minimal logging."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')


def test_specific_bug_condition_1():
    """Test if parameters.get(node_id, {}) could return empty when it shouldn't."""
    print("=== Bug Condition 1: parameters.get(node_id, {}) Issue ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'input_value={input_value if \"input_value\" in globals() else \"MISSING\"}'}"
    })
    
    class BugTestRuntime(LocalRuntime):
        def _execute_workflow_async(self, workflow, task_manager, run_id, parameters, workflow_context=None):
            """Override to inspect parameters at the critical point."""
            print(f"  parameters dict structure: {parameters}")
            for node_id in workflow.graph.nodes():
                node_params = parameters.get(node_id, {})
                print(f"  parameters.get('{node_id}', {{}}) = {node_params}")
            return super()._execute_workflow_async(workflow, task_manager, run_id, parameters, workflow_context)
    
    runtime = BugTestRuntime(debug=False)
    
    # Test various parameter formats that might cause issues
    test_cases = [
        # Case 1: Workflow-level params should be injected
        {"input_value": "workflow_level"},
        # Case 2: Node-specific params  
        {"processor": {"input_value": "node_specific"}},
        # Case 3: Mixed format
        {"processor": {"input_value": "node_specific"}, "other_param": "workflow_level"},
        # Case 4: Empty node-specific dict
        {"processor": {}, "input_value": "workflow_level"},
    ]
    
    for i, params in enumerate(test_cases):
        print(f"\n--- Test Case {i+1}: {params} ---")
        try:
            results, run_id = runtime.execute(workflow.build(), parameters=params)
            success = "input_value=" in str(results) and "MISSING" not in str(results)
            print(f"RESULT: {'PASS' if success else 'FAIL'} - {results}")
        except Exception as e:
            print(f"ERROR: {e}")


def test_specific_bug_condition_2():
    """Test WorkflowParameterInjector edge cases."""
    print("\n=== Bug Condition 2: WorkflowParameterInjector Issues ===")
    
    from kailash.runtime.parameter_injector import WorkflowParameterInjector
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': 'executed'}"
    })
    built_workflow = workflow.build()
    
    # Test the injector directly
    injector = WorkflowParameterInjector(built_workflow, debug=True)
    
    test_params = [
        {"input_value": "test"},
        {"nonexistent_param": "value"},
        {},
        None,
        {"processor": "this_should_not_be_injected"},  # Node name as value
    ]
    
    for params in test_params:
        print(f"\n--- Testing injector with: {params} ---")
        try:
            if params is not None:
                transformed = injector.transform_workflow_parameters(params)
                print(f"  Transform result: {transformed}")
            else:
                print("  Skipping None parameters")
        except Exception as e:
            print(f"  Injector error: {e}")


def test_specific_bug_condition_3():
    """Test _separate_parameter_formats edge cases."""
    print("\n=== Bug Condition 3: Parameter Format Separation Issues ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {})
    built_workflow = workflow.build()
    
    runtime = LocalRuntime(debug=False)
    
    # Test edge cases in parameter separation
    test_cases = [
        # Case 1: Key matches node ID but value is not dict
        {"processor": "string_value", "input_value": "test"},
        # Case 2: Key doesn't match node ID but value is dict  
        {"not_a_node": {"param": "value"}, "input_value": "test"},
        # Case 3: Empty strings and special characters
        {"": {"param": "value"}, "input_value": "test"},
        {"processor": {}, "input_value": "test"},  # Empty dict for node
        # Case 4: All dict values but no node IDs
        {"config": {"setting": "value"}, "data": {"input": "test"}},
    ]
    
    for i, params in enumerate(test_cases):
        print(f"\n--- Separation Test {i+1}: {params} ---")
        try:
            node_specific, workflow_level = runtime._separate_parameter_formats(params, built_workflow)
            print(f"  Node-specific: {node_specific}")
            print(f"  Workflow-level: {workflow_level}")
        except Exception as e:
            print(f"  Separation error: {e}")


def test_specific_bug_condition_4():
    """Test the exact condition where injected_params might be empty."""
    print("\n=== Bug Condition 4: Empty injected_params ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'received_params': list(globals().keys())}"
    })
    
    class DebugRuntime(LocalRuntime):
        def _execute_workflow_async(self, workflow, task_manager, run_id, parameters, workflow_context=None):
            """Track the exact point where injection might fail."""
            print(f"  Processed parameters: {parameters}")
            return super()._execute_workflow_async(workflow, task_manager, run_id, parameters, workflow_context)
            
        def _prepare_node_inputs(self, workflow, node_id, node_instance, node_outputs, parameters):
            """Track parameter injection at node level."""
            print(f"  _prepare_node_inputs called with parameters: {parameters}")
            
            # This is the critical code from line 628-634 in local.py
            injected_params = parameters  # In the original code: parameters.get(node_id, {})
            print(f"  injected_params: {injected_params}")
            print(f"  injected_params is truthy: {bool(injected_params)}")
            
            return super()._prepare_node_inputs(workflow, node_id, node_instance, node_outputs, parameters)
    
    runtime = DebugRuntime(debug=False)
    
    # Test the specific scenario where parameters might be empty
    parameters = {"input_value": "test_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"RESULT: {results}")
    except Exception as e:
        print(f"ERROR: {e}")


def test_specific_bug_condition_5():
    """Test if there's a race condition or state issue."""
    print("\n=== Bug Condition 5: State/Timing Issues ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node1", {
        "code": "result = {'output': f'node1 got: {input_value if \"input_value\" in globals() else \"MISSING\"}'}"
    })
    workflow.add_node("PythonCodeNode", "node2", {
        "code": "result = {'output': f'node2 got: {input_value if \"input_value\" in globals() else \"MISSING\"}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    parameters = {"input_value": "shared_value"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        
        # Check if both nodes got the parameter
        node1_success = "shared_value" in str(results.get("node1", {}))
        node2_success = "shared_value" in str(results.get("node2", {}))
        
        print(f"Node1 success: {node1_success}")
        print(f"Node2 success: {node2_success}")
        print(f"Results: {results}")
        
        if not (node1_success and node2_success):
            print("POTENTIAL BUG: Not all nodes received parameters!")
        
    except Exception as e:
        print(f"ERROR: {e}")


def main():
    """Run specific bug condition tests."""
    print("Specific Edge Case Investigation for Parameter Injection Bug")
    print("=" * 65)
    
    setup_logging()
    
    test_specific_bug_condition_1()
    test_specific_bug_condition_2()
    test_specific_bug_condition_3()
    test_specific_bug_condition_4()
    test_specific_bug_condition_5()
    
    print("\n" + "=" * 65)
    print("Investigation complete.")


if __name__ == "__main__":
    main()
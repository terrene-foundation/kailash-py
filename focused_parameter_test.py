#!/usr/bin/env python3
"""
Focused investigation of the parameter injection bug.

Based on code analysis, I found several potential edge cases where parameters
might not be injected. This script tests the most likely scenarios.
"""

import logging
import sys

# Add src to Python path
sys.path.insert(0, "src")

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


def setup_logging():
    """Setup logging to see parameter flow."""
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')


def test_core_parameter_injection():
    """Test the basic parameter injection that should always work."""
    print("=== Basic Parameter Injection Test ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    parameters = {"input_value": "test_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_edge_case_workflow_context():
    """Test the workflow_context edge case that might affect parameter processing."""
    print("\n=== Workflow Context Edge Case ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    
    # This is the edge case from the code - workflow_context gets extracted in _execute_async
    parameters = {
        "workflow_context": {"session_id": "test"},  # This gets popped from parameters
        "input_value": "test_data"
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_edge_case_empty_workflow_level_params():
    """Test edge case where workflow-level parameters are empty after separation."""
    print("\n=== Empty Workflow-Level Parameters Edge Case ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    
    # Node-specific format only - workflow_level_params will be empty
    parameters = {
        "processor": {"input_value": "node_specific_data"}
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_edge_case_parameter_injection_skip():
    """Test the specific condition in _process_workflow_parameters that might skip injection."""
    print("\n=== Parameter Injection Skip Edge Case ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value}'}"
    })
    
    runtime = LocalRuntime(debug=True)
    
    # Create a scenario where workflow_level_params exists but injection might fail
    # According to the code analysis, this could happen if:
    # 1. WorkflowParameterInjector.transform_workflow_parameters returns empty
    # 2. Or if the injector fails internally
    
    parameters = {
        "input_value": "workflow_level_data",
        "unknown_param": "should_be_ignored"
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_edge_case_connection_validation_strict():
    """Test if strict connection validation affects parameter injection."""
    print("\n=== Strict Connection Validation Edge Case ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value}'}"
    })
    
    # Use strict connection validation
    runtime = LocalRuntime(debug=True, connection_validation="strict")
    parameters = {"input_value": "test_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_edge_case_secret_provider():
    """Test if secret provider affects parameter injection."""
    print("\n=== Secret Provider Edge Case ===")
    
    from kailash.runtime.secret_provider import EnvironmentSecretProvider
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value}'}"
    })
    
    secret_provider = EnvironmentSecretProvider()
    runtime = LocalRuntime(debug=True, secret_provider=secret_provider)
    parameters = {"input_value": "test_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_deep_dive_parameter_flow():
    """Deep dive into the parameter flow to see exactly what happens."""
    print("\n=== Deep Parameter Flow Analysis ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'output': f'Got input: {input_value if \"input_value\" in locals() else \"MISSING\"}'}"
    })
    
    # Create a custom runtime to intercept parameter processing
    class DeepDiveRuntime(LocalRuntime):
        def _process_workflow_parameters(self, workflow, parameters=None):
            print(f"  _process_workflow_parameters called with: {parameters}")
            result = super()._process_workflow_parameters(workflow, parameters)
            print(f"  _process_workflow_parameters returning: {result}")
            return result
            
        def _separate_parameter_formats(self, parameters, workflow):
            print(f"  _separate_parameter_formats called with: {parameters}")
            result = super()._separate_parameter_formats(parameters, workflow)
            print(f"  _separate_parameter_formats returning: {result}")
            return result
            
        def _prepare_node_inputs(self, workflow, node_id, node_instance, node_outputs, parameters):
            print(f"  _prepare_node_inputs for {node_id} with parameters: {parameters}")
            result = super()._prepare_node_inputs(workflow, node_id, node_instance, node_outputs, parameters)
            print(f"  _prepare_node_inputs returning: {result}")
            return result
    
    runtime = DeepDiveRuntime(debug=True)
    parameters = {"input_value": "deep_dive_data"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"SUCCESS: {results}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def main():
    """Run focused parameter injection tests."""
    print("Focused Parameter Injection Investigation")
    print("=" * 50)
    
    setup_logging()
    
    # Start with basic test to ensure it works
    if not test_core_parameter_injection():
        print("CRITICAL: Basic parameter injection is broken!")
        return
    
    # Test specific edge cases that might cause the bug
    tests = [
        test_edge_case_workflow_context,
        test_edge_case_empty_workflow_level_params,
        test_edge_case_parameter_injection_skip,
        test_edge_case_connection_validation_strict,
        test_edge_case_secret_provider,
        test_deep_dive_parameter_flow,
    ]
    
    for test in tests:
        test()
    
    print("\n" + "=" * 50)
    print("Investigation complete.")


if __name__ == "__main__":
    main()
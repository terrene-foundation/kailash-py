#!/usr/bin/env python3
"""
Comprehensive test to find the exact scenario where parameter injection fails.

After extensive code analysis, I believe the bug might be:
1. In a very specific workflow configuration
2. Related to connection validation strict mode
3. Related to async vs sync execution paths
4. Related to specific node types that don't accept parameters correctly
"""

import logging
import sys

# Add src to Python path
sys.path.insert(0, "src")

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


def setup_minimal_logging():
    """Setup minimal logging to see parameter injection logs."""
    logging.basicConfig(level=logging.DEBUG)


def create_test_workflow():
    """Create a simple test workflow."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test_node", {
        "code": """
# Simple test to see if we received parameters
received_params = []
for var_name in ['input_value', 'test_param', 'data']:
    if var_name in locals():
        received_params.append(f"{var_name}={locals()[var_name]}")

result = {
    'received_params': received_params,
    'total_params': len(received_params)
}
"""
    })
    return workflow


def test_scenario_1_basic():
    """Test basic parameter injection scenario."""
    print("=== Scenario 1: Basic Parameter Injection ===")
    
    workflow = create_test_workflow()
    runtime = LocalRuntime(debug=True)
    
    parameters = {"input_value": "test123"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        received = results.get("test_node", {}).get("result", {}).get("received_params", [])
        print(f"Received parameters: {received}")
        
        if "input_value=test123" in received:
            print("✅ PASS: Parameter injection worked")
        else:
            print("❌ FAIL: Parameter injection failed")
            print(f"Full results: {results}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")


def test_scenario_2_strict_validation():
    """Test with strict connection validation - potential bug source."""
    print("\n=== Scenario 2: Strict Connection Validation ===")
    
    workflow = create_test_workflow()
    runtime = LocalRuntime(debug=True, connection_validation="strict")
    
    parameters = {"input_value": "test456"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        received = results.get("test_node", {}).get("result", {}).get("received_params", [])
        print(f"Received parameters: {received}")
        
        if "input_value=test456" in received:
            print("✅ PASS: Parameter injection worked with strict validation")
        else:
            print("❌ FAIL: Parameter injection failed with strict validation")
            print(f"Full results: {results}")
        
    except Exception as e:
        print(f"❌ ERROR with strict validation: {e}")


def test_scenario_3_async_enabled():
    """Test with async execution enabled - potential race condition."""
    print("\n=== Scenario 3: Async Execution Enabled ===")
    
    workflow = create_test_workflow()
    runtime = LocalRuntime(debug=True, enable_async=True)
    
    parameters = {"input_value": "test789"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        received = results.get("test_node", {}).get("result", {}).get("received_params", [])
        print(f"Received parameters: {received}")
        
        if "input_value=test789" in received:
            print("✅ PASS: Parameter injection worked with async enabled")
        else:
            print("❌ FAIL: Parameter injection failed with async enabled")
            print(f"Full results: {results}")
        
    except Exception as e:
        print(f"❌ ERROR with async enabled: {e}")


def test_scenario_4_multiple_nodes():
    """Test with multiple nodes - potential parameter sharing issue."""
    print("\n=== Scenario 4: Multiple Nodes ===")
    
    workflow = WorkflowBuilder()
    
    # First node
    workflow.add_node("PythonCodeNode", "node1", {
        "code": """
received = 'input_value' in locals()
result = {'node1_received_param': received, 'value': input_value if received else 'NONE'}
"""
    })
    
    # Second node  
    workflow.add_node("PythonCodeNode", "node2", {
        "code": """
received = 'input_value' in locals()
result = {'node2_received_param': received, 'value': input_value if received else 'NONE'}
"""
    })
    
    runtime = LocalRuntime(debug=True)
    parameters = {"input_value": "shared_value"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        
        node1_received = results.get("node1", {}).get("result", {}).get("node1_received_param", False)
        node2_received = results.get("node2", {}).get("result", {}).get("node2_received_param", False)
        
        print(f"Node1 received parameter: {node1_received}")
        print(f"Node2 received parameter: {node2_received}")
        
        if node1_received and node2_received:
            print("✅ PASS: Both nodes received parameters")
        else:
            print("❌ FAIL: Not all nodes received parameters")
            print(f"Full results: {results}")
        
    except Exception as e:
        print(f"❌ ERROR with multiple nodes: {e}")


def test_scenario_5_enterprise_features():
    """Test with enterprise features enabled - potential parameter interference."""
    print("\n=== Scenario 5: Enterprise Features Enabled ===")
    
    workflow = create_test_workflow()
    runtime = LocalRuntime(
        debug=True,
        enable_security=True,
        enable_audit=True,
        enable_monitoring=True,
        connection_validation="strict"
    )
    
    parameters = {"input_value": "enterprise_test"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        received = results.get("test_node", {}).get("result", {}).get("received_params", [])
        print(f"Received parameters: {received}")
        
        if "input_value=enterprise_test" in received:
            print("✅ PASS: Parameter injection worked with enterprise features")
        else:
            print("❌ FAIL: Parameter injection failed with enterprise features")
            print(f"Full results: {results}")
        
    except Exception as e:
        print(f"❌ ERROR with enterprise features: {e}")


def test_scenario_6_inspect_parameter_flow():
    """Deep inspection of parameter flow to find where it might break."""
    print("\n=== Scenario 6: Deep Parameter Flow Inspection ===")
    
    class InspectionRuntime(LocalRuntime):
        def _process_workflow_parameters(self, workflow, parameters=None):
            print(f"🔍 _process_workflow_parameters INPUT: {parameters}")
            result = super()._process_workflow_parameters(workflow, parameters)
            print(f"🔍 _process_workflow_parameters OUTPUT: {result}")
            return result
        
        def _prepare_node_inputs(self, workflow, node_id, node_instance, node_outputs, parameters):
            print(f"🔍 _prepare_node_inputs for {node_id}: INPUT parameters={parameters}")
            result = super()._prepare_node_inputs(workflow, node_id, node_instance, node_outputs, parameters)
            print(f"🔍 _prepare_node_inputs for {node_id}: OUTPUT inputs={result}")
            return result
    
    workflow = create_test_workflow()
    runtime = InspectionRuntime(debug=False)  # Disable debug to reduce noise
    
    parameters = {"input_value": "inspection_test"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        print(f"🔍 FINAL RESULTS: {results}")
        
        # Check if parameter made it through
        received = results.get("test_node", {}).get("result", {}).get("received_params", [])
        if "input_value=inspection_test" in received:
            print("✅ PASS: Parameter flow inspection shows success")
        else:
            print("❌ FAIL: Parameter flow inspection shows failure")
            
    except Exception as e:
        print(f"❌ ERROR during inspection: {e}")


def test_scenario_7_reproducer_attempt():
    """Attempt to reproduce the exact conditions from the bug report."""
    print("\n=== Scenario 7: Bug Report Reproduction Attempt ===")
    
    # Try to recreate conditions where someone might report this bug
    # Could be related to:
    # - Specific node configurations
    # - Specific parameter names
    # - Workflow structure
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "data_processor", {
        "name": "data_processor",
        "code": """
# Check for common parameter names that might be expected
param_names = ['data', 'input', 'config', 'parameters', 'args']
found_params = []

for param_name in param_names:
    if param_name in locals():
        found_params.append(f"{param_name}={locals()[param_name]}")

result = {
    'found_parameters': found_params,
    'expected_but_missing': [p for p in param_names if p not in locals()],
    'all_locals': list(locals().keys())
}
"""
    })
    
    runtime = LocalRuntime(debug=True)
    
    # Try different parameter patterns that users might expect to work
    test_patterns = [
        {"data": "user_data"},
        {"input": "user_input"},
        {"config": {"setting": "value"}},
        {"parameters": {"key": "value"}},
        {"data_processor": {"data": "node_specific"}},  # Node-specific format
    ]
    
    for i, params in enumerate(test_patterns):
        print(f"\n--- Pattern {i+1}: {params} ---")
        try:
            results, run_id = runtime.execute(workflow.build(), parameters=params)
            found = results.get("data_processor", {}).get("result", {}).get("found_parameters", [])
            missing = results.get("data_processor", {}).get("result", {}).get("expected_but_missing", [])
            
            print(f"Found parameters: {found}")
            print(f"Missing parameters: {missing}")
            
            if found:
                print("✅ PASS: Some parameters were injected")
            else:
                print("❌ POTENTIAL BUG: No parameters were injected")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")


def main():
    """Run comprehensive bug investigation."""
    print("Comprehensive Parameter Injection Bug Investigation")
    print("=" * 60)
    
    setup_minimal_logging()
    
    # Run all test scenarios
    test_scenario_1_basic()
    test_scenario_2_strict_validation()  
    test_scenario_3_async_enabled()
    test_scenario_4_multiple_nodes()
    test_scenario_5_enterprise_features()
    test_scenario_6_inspect_parameter_flow()
    test_scenario_7_reproducer_attempt()
    
    print("\n" + "=" * 60)
    print("🔍 Investigation Summary:")
    print("If all tests PASS, the parameter injection is working correctly.")
    print("If any tests FAIL, we've identified the bug condition.")
    print("Check the debug logs above for detailed parameter flow analysis.")


if __name__ == "__main__":
    main()
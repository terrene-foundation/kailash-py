#!/usr/bin/env python3
"""
Definitive test to prove that parameter injection works correctly.

This test uses proper Python code that doesn't rely on locals() or globals()
to definitively show whether parameters are being injected.
"""

import sys

# Add src to Python path
sys.path.insert(0, "src")

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


def test_parameter_injection_definitive():
    """Definitive test of parameter injection using simple variable access."""
    print("=== DEFINITIVE Parameter Injection Test ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "test_node", {
        "code": """
# Test if the parameter was injected by directly referencing it
try:
    # If parameter injection works, input_value should be available
    test_result = input_value
    success = True
    message = f"SUCCESS: input_value = {input_value}"
except NameError:
    # If parameter injection fails, input_value won't be defined
    test_result = None
    success = False
    message = "FAIL: input_value is not defined"

result = {
    'success': success,
    'message': message,
    'test_result': test_result
}
"""
    })
    
    runtime = LocalRuntime(debug=False)  # Disable debug to reduce noise
    parameters = {"input_value": "INJECTED_PARAMETER_VALUE"}
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        
        node_result = results.get("test_node", {})
        if "error" in node_result:
            print(f"❌ EXECUTION ERROR: {node_result['error']}")
            return False
        
        result_data = node_result.get("result", {})
        success = result_data.get("success", False)
        message = result_data.get("message", "No message")
        test_result = result_data.get("test_result")
        
        print(f"Result: {message}")
        print(f"Test value: {test_result}")
        
        if success and test_result == "INJECTED_PARAMETER_VALUE":
            print("✅ DEFINITIVE PROOF: Parameter injection works correctly!")
            return True
        else:
            print("❌ DEFINITIVE PROOF: Parameter injection is broken!")
            return False
            
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False


def test_multiple_parameters():
    """Test injection of multiple parameters."""
    print("\n=== Multiple Parameters Test ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "multi_test", {
        "code": """
# Test multiple parameters
results = {}

for param_name in ['param1', 'param2', 'param3']:
    try:
        # Use eval to dynamically access variables
        param_value = eval(param_name)
        results[param_name] = f"SUCCESS: {param_value}"
    except NameError:
        results[param_name] = f"FAIL: {param_name} not defined"

result = {
    'parameter_results': results,
    'total_success': sum(1 for v in results.values() if 'SUCCESS' in v),
    'total_tested': len(results)
}
"""
    })
    
    runtime = LocalRuntime(debug=False)
    parameters = {
        "param1": "value1",
        "param2": "value2", 
        "param3": "value3"
    }
    
    try:
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        
        node_result = results.get("multi_test", {})
        if "error" in node_result:
            print(f"❌ EXECUTION ERROR: {node_result['error']}")
            return False
        
        result_data = node_result.get("result", {})
        param_results = result_data.get("parameter_results", {})
        success_count = result_data.get("total_success", 0)
        total_tested = result_data.get("total_tested", 0)
        
        print(f"Parameter injection results:")
        for param, result in param_results.items():
            print(f"  {param}: {result}")
        
        print(f"Success rate: {success_count}/{total_tested}")
        
        if success_count == total_tested:
            print("✅ MULTIPLE PARAMETERS: All parameters injected correctly!")
            return True
        else:
            print("❌ MULTIPLE PARAMETERS: Some parameters failed injection!")
            return False
            
    except Exception as e:
        print(f"❌ TEST ERROR: {e}")
        return False


def test_node_specific_vs_workflow_level():
    """Test the difference between node-specific and workflow-level parameters."""
    print("\n=== Node-Specific vs Workflow-Level Test ===")
    
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "param_test", {
        "code": """
# Test parameter access
try:
    test_param_value = test_param
    success = True
    message = f"Parameter received: {test_param_value}"
except NameError:
    success = False
    message = "Parameter NOT received"

result = {
    'success': success,
    'message': message
}
"""
    })
    
    runtime = LocalRuntime(debug=False)
    
    # Test 1: Workflow-level parameters
    print("Test 1: Workflow-level parameters")
    params1 = {"test_param": "workflow_level_value"}
    
    results1, _ = runtime.execute(workflow.build(), parameters=params1)
    result1 = results1.get("param_test", {}).get("result", {})
    print(f"  {result1.get('message', 'No message')}")
    
    # Test 2: Node-specific parameters
    print("Test 2: Node-specific parameters")
    params2 = {"param_test": {"test_param": "node_specific_value"}}
    
    results2, _ = runtime.execute(workflow.build(), parameters=params2)
    result2 = results2.get("param_test", {}).get("result", {})
    print(f"  {result2.get('message', 'No message')}")
    
    success1 = result1.get('success', False)
    success2 = result2.get('success', False)
    
    if success1 and success2:
        print("✅ BOTH FORMATS: Both workflow-level and node-specific parameters work!")
        return True
    else:
        print("❌ PARAMETER FORMAT ISSUE: One or both formats failed!")
        print(f"  Workflow-level success: {success1}")
        print(f"  Node-specific success: {success2}")
        return False


def main():
    """Run definitive parameter injection tests."""
    print("DEFINITIVE Parameter Injection Investigation")
    print("=" * 50)
    
    # Run definitive tests
    test1_pass = test_parameter_injection_definitive()
    test2_pass = test_multiple_parameters()
    test3_pass = test_node_specific_vs_workflow_level()
    
    print("\n" + "=" * 50)
    print("🎯 DEFINITIVE CONCLUSION:")
    
    if test1_pass and test2_pass and test3_pass:
        print("✅ Parameter injection is working CORRECTLY in all scenarios!")
        print("✅ The bug report may be based on incorrect expectations or test setup.")
        print("✅ No edge cases found where parameters are skipped under normal conditions.")
    else:
        print("❌ Parameter injection has confirmed issues:")
        print(f"   - Basic injection: {'PASS' if test1_pass else 'FAIL'}")
        print(f"   - Multiple parameters: {'PASS' if test2_pass else 'FAIL'}")
        print(f"   - Parameter formats: {'PASS' if test3_pass else 'FAIL'}")
    
    return test1_pass and test2_pass and test3_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
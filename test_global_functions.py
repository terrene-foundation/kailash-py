#!/usr/bin/env python3
"""Test script to verify global functions are available in PythonCodeNode."""

from kailash.nodes.code.python import PythonCodeNode

# Test 1: Data path functions
def test_data_path_functions():
    print("Testing data path functions...")
    
    code = """
# Test get_input_data_path
input_path = get_input_data_path('test.csv')
print(f"Input path: {input_path}")

# Test get_output_data_path  
output_path = get_output_data_path('results.json')
print(f"Output path: {output_path}")

# Test get_data_path
custom_path = get_data_path('templates', 'template.txt')
print(f"Custom path: {custom_path}")

result = {
    'input_path': input_path,
    'output_path': output_path,  
    'custom_path': custom_path
}
"""
    
    node = PythonCodeNode(name="test_data_paths", code=code)
    result = node.execute_code({})
    print("Data path functions test result:", result)
    return result

# Test 2: Workflow context functions
def test_workflow_context_functions():
    print("Testing workflow context functions...")
    
    code = """
# Test workflow context functions
set_workflow_context('test_key', 'test_value')
retrieved_value = get_workflow_context('test_key', 'default')
missing_value = get_workflow_context('missing_key', 'default_value')

result = {
    'retrieved_value': retrieved_value,
    'missing_value': missing_value
}
"""
    
    node = PythonCodeNode(name="test_context", code=code)
    result = node.execute_code({})
    print("Workflow context functions test result:", result)
    return result

if __name__ == "__main__":
    try:
        print("=== Testing Global Functions in PythonCodeNode ===")
        
        # Test data path functions
        data_result = test_data_path_functions()
        
        print()
        
        # Test workflow context functions  
        context_result = test_workflow_context_functions()
        
        print("\n=== Tests completed successfully! ===")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
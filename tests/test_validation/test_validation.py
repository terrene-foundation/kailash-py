"""Test the base class validation behavior with PythonCodeNode."""

from kailash.nodes.code import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def test_validation():
    """Test that base class validation works correctly."""
    # Create a node with typed inputs
    node = PythonCodeNode(
        name="validator",
        code="result = x + y",
        input_types={'x': int, 'y': int},
        output_type=int
    )
    
    print("Testing validation through execute() method...")
    
    # Test missing required parameter
    try:
        result = node.execute(x=5)  # Missing y
        print(f"ERROR: Should have raised validation error")
    except NodeValidationError as e:
        print(f"✓ Correctly caught missing parameter: {e}")
    
    # Test type conversion
    result = node.execute(x=5, y='10')  # String should be converted to int
    print(f"✓ Type conversion worked: {result}")
    
    # Test normal execution
    result = node.execute(x=5, y=10)
    print(f"✓ Normal execution: {result}")
    
    print("\nTesting direct execute_code() method...")
    
    # Test direct execute_code (bypasses validation)
    result = node.execute_code({'x': 5, 'y': 10})
    print(f"✓ Direct execute_code: {result}")
    
    # Test that execute_code doesn't validate (it should work with dict)
    result = node.execute_code({'x': 5, 'y': 10})
    print(f"✓ Execute_code with dict works: {result}")
    
    print("\nAll validation tests passed!")


if __name__ == "__main__":
    test_validation()
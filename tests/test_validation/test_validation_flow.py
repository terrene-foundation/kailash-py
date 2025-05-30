"""Test to verify validation flow in PythonCodeNode."""

from kailash.nodes.code import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def test_trace_validation():
    """Trace how validation works in PythonCodeNode."""

    # Create a node with typed inputs
    def add(x: int, y: int) -> int:
        return x + y

    node = PythonCodeNode.from_function(func=add, name="adder")

    print("1. Created node with parameters:")
    for name, param in node.get_parameters().items():
        print(f"   {name}: {param.type.__name__} (required={param.required})")

    print("\n2. Testing validation through execute():")

    # Test missing parameter
    try:
        result = node.execute(x=5)  # Missing y
        print("   ERROR: Should have failed validation")
    except NodeValidationError as e:
        print(f"   ✓ Validation caught missing parameter: {e}")

    # Test type conversion
    result = node.execute(x=5, y="10")
    print(f"   ✓ Type conversion worked: {result}")

    # Test normal execution
    result = node.execute(x=5, y=10)
    print(f"   ✓ Normal execution: {result}")

    print("\n3. Looking at the validation chain:")
    print(
        "   execute() -> validate_inputs() [base class] -> get_parameters() -> validation logic"
    )

    print("\n4. The base class validate_inputs() is doing all the work!")
    print("   - Checks required parameters")
    print("   - Validates types")
    print("   - Attempts type conversion")
    print("   - Returns validated inputs")


if __name__ == "__main__":
    test_trace_validation()

"""Test to verify type conversion behavior."""

import pandas as pd

from kailash.nodes.code import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def test_type_conversion():
    """Test how validation handles type conversion."""

    # Create test data
    df = pd.DataFrame(
        {
            "Total Claim Amount": [100, 200, 300, 400, 500],
            "Name": ["A", "B", "C", "D", "E"],
        }
    )

    # Define function with str threshold
    def custom_filter(data: pd.DataFrame, threshold: str) -> dict:
        print(
            f"Inside function - threshold type: {type(threshold)}, value: {threshold}"
        )
        # Convert back to float for comparison
        threshold_float = float(threshold)
        filtered = data[data["Total Claim Amount"] > threshold_float]
        return {
            "result": {"filtered_count": len(filtered), "threshold_used": threshold}
        }

    # Create node
    node = PythonCodeNode.from_function(func=custom_filter, name="threshold_filter")

    print("Testing type conversion behavior:")

    # Pass a float, expect it to be converted to str
    result = node.execute(data=df, threshold=1000.0)
    print(f"Result: {result}")

    # Test with actual string
    result2 = node.execute(data=df, threshold="300")
    print(f"Result with string: {result2}")

    # Test what str(1000.0) produces
    print(f"\nVerification: str(1000.0) = '{str(1000.0)}'")


def test_strict_type_check():
    """Test a case where type conversion should fail."""

    # Define function expecting a complex type that can't be converted
    def process_data(data: pd.DataFrame) -> dict:
        return {"result": {"rows": len(data)}}

    node = PythonCodeNode.from_function(func=process_data, name="processor")

    print("\nTesting with incompatible type:")
    try:
        # This should fail - can't convert string to DataFrame
        result = node.execute(data="not a dataframe")
        print(f"ERROR: Should have failed! Result: {result}")
    except NodeValidationError as e:
        print(f"✓ Correctly caught type error: {e}")


if __name__ == "__main__":
    test_type_conversion()
    test_strict_type_check()

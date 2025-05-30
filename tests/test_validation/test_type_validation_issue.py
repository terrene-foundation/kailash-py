"""Test to reproduce the type validation issue."""

import pandas as pd

from kailash.nodes.code import PythonCodeNode
from kailash.sdk_exceptions import NodeValidationError


def test_type_validation_issue():
    """Test that type validation correctly catches mismatches."""

    # Create test data
    df = pd.DataFrame(
        {
            "Total Claim Amount": [100, 200, 300, 400, 500],
            "Name": ["A", "B", "C", "D", "E"],
        }
    )

    # Define function with str threshold
    def custom_filter(data: pd.DataFrame, threshold: str) -> pd.DataFrame:
        # This will actually fail at runtime since we can't compare with string
        return data[data["Total Claim Amount"] > threshold].to_dict(orient="records")

    # Create node
    node = PythonCodeNode.from_function(func=custom_filter, name="threshold_filter")

    print("Function signature expects:")
    for name, param in node.get_parameters().items():
        print(f"  {name}: {param.type}")

    print("\nTrying to execute with wrong type (float instead of str):")
    try:
        # This should fail validation since we're passing a float but expect str
        result = node.execute(data=df, threshold=1000.0)
        print(f"ERROR: Validation passed when it should have failed! Result: {result}")
    except NodeValidationError as e:
        print(f"✓ Correctly caught type mismatch: {e}")
    except Exception as e:
        print(f"Got unexpected error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    test_type_validation_issue()

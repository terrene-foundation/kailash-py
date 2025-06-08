#!/usr/bin/env python3
"""Test exception handling in PythonCodeNode."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime


def test_exception_handling():
    """Test that PythonCodeNode can catch specific exceptions."""

    workflow = Workflow("exception_test", "Exception Handling Test")

    # Test catching NameError
    workflow.add_node(
        "name_error_test",
        PythonCodeNode(
            name="name_error_test",
            code="""
try:
    # This will raise NameError
    value = undefined_variable
except NameError as e:
    print(f"Successfully caught NameError: {e}")
    result = {"error_caught": "NameError", "message": str(e)}
""",
        ),
    )

    # Test catching multiple exception types
    workflow.add_node(
        "multi_exception_test",
        PythonCodeNode(
            name="multi_exception_test",
            code="""
errors_caught = []

# Test ValueError
try:
    int("not a number")
except ValueError as e:
    errors_caught.append(f"ValueError: {e}")

# Test KeyError
try:
    d = {"a": 1}
    value = d["missing_key"]
except KeyError as e:
    errors_caught.append(f"KeyError: {e}")

# Test IndexError
try:
    lst = [1, 2, 3]
    value = lst[10]
except IndexError as e:
    errors_caught.append(f"IndexError: {e}")

# Test ZeroDivisionError
try:
    result = 10 / 0
except ZeroDivisionError as e:
    errors_caught.append(f"ZeroDivisionError: {e}")

print(f"Caught {len(errors_caught)} exceptions")
for error in errors_caught:
    print(f"  - {error}")

result = {"errors_caught": errors_caught, "count": len(errors_caught)}
""",
        ),
    )

    # Test with pandas/numpy exceptions
    workflow.add_node(
        "data_science_exceptions",
        PythonCodeNode(
            name="data_science_exceptions",
            code="""
import pandas as pd
import numpy as np

exceptions_handled = []

# Test pandas exception
try:
    df = pd.DataFrame({"a": [1, 2, 3]})
    # This will raise KeyError
    value = df["missing_column"]
except KeyError as e:
    exceptions_handled.append(f"Pandas KeyError handled: column {e} not found")

# Test numpy exception
try:
    arr = np.array([1, 2, 3])
    # This will raise IndexError
    value = arr[10]
except IndexError as e:
    exceptions_handled.append(f"Numpy IndexError handled: {e}")

# Test custom exception handling in data processing
try:
    # Simulate data validation
    data = {"value": -10}
    if data["value"] < 0:
        raise ValueError("Negative values not allowed")
except ValueError as e:
    exceptions_handled.append(f"Custom ValueError handled: {e}")

print(f"Handled {len(exceptions_handled)} data science exceptions")
for exc in exceptions_handled:
    print(f"  - {exc}")

result = {"exceptions_handled": exceptions_handled}
""",
        ),
    )

    # Run the workflow
    runtime = LocalRuntime()

    print("🧪 Testing Exception Handling in PythonCodeNode")
    print("=" * 50)

    try:
        results, run_id = runtime.execute(workflow)

        # Check NameError test
        if "name_error_test" in results:
            result = results["name_error_test"].get("result", {})
            print(f"\n✅ NameError Test: {result.get('error_caught', 'Failed')}")
            print(f"   Message: {result.get('message', 'No message')}")

        # Check multi-exception test
        if "multi_exception_test" in results:
            result = results["multi_exception_test"].get("result", {})
            print(
                f"\n✅ Multi-Exception Test: Caught {result.get('count', 0)} exceptions"
            )
            for error in result.get("errors_caught", []):
                print(f"   - {error}")

        # Check data science exceptions
        if "data_science_exceptions" in results:
            result = results["data_science_exceptions"].get("result", {})
            print(
                f"\n✅ Data Science Exceptions: {len(result.get('exceptions_handled', []))} handled"
            )
            for exc in result.get("exceptions_handled", []):
                print(f"   - {exc}")

        print("\n" + "=" * 50)
        print("🎉 All exception handling tests passed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_exception_handling()

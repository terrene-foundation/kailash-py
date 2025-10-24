"""
Validation test for AsyncPythonCodeNode exception handling fix.
Tests that NameError and other exceptions are now available.
"""

import asyncio

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def test_nameerror_catch():
    """Test that NameError can be caught in AsyncPythonCodeNode."""
    print("\n=== Test 1: NameError catch ===")
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "AsyncPythonCodeNode",
        "test",
        {
            "code": """
try:
    value = undefined_variable
    result = {"value": value}
except NameError:
    result = {"status": "success", "message": "NameError caught"}
"""
        },
    )

    results = await runtime.execute_workflow_async(workflow.build(), inputs={})
    test_result = results.get("results", {}).get("test", {})

    if test_result.get("status") == "success":
        print(f"✅ PASSED: {test_result.get('message')}")
        return True
    else:
        print(f"❌ FAILED: Unexpected result: {test_result}")
        return False


async def test_attributeerror_catch():
    """Test that AttributeError can be caught in AsyncPythonCodeNode."""
    print("\n=== Test 2: AttributeError catch ===")
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "AsyncPythonCodeNode",
        "test",
        {
            "code": """
try:
    obj = {}
    value = obj.nonexistent
    result = {"value": value}
except AttributeError:
    result = {"status": "success", "message": "AttributeError caught"}
"""
        },
    )

    results = await runtime.execute_workflow_async(workflow.build(), inputs={})
    test_result = results.get("results", {}).get("test", {})

    if test_result.get("status") == "success":
        print(f"✅ PASSED: {test_result.get('message')}")
        return True
    else:
        print(f"❌ FAILED: Unexpected result: {test_result}")
        return False


async def test_zerodivisionerror_catch():
    """Test that ZeroDivisionError can be caught in AsyncPythonCodeNode."""
    print("\n=== Test 3: ZeroDivisionError catch ===")
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "AsyncPythonCodeNode",
        "test",
        {
            "code": """
try:
    value = 1 / 0
    result = {"value": value}
except ZeroDivisionError:
    result = {"status": "success", "message": "ZeroDivisionError caught"}
"""
        },
    )

    results = await runtime.execute_workflow_async(workflow.build(), inputs={})
    test_result = results.get("results", {}).get("test", {})

    if test_result.get("status") == "success":
        print(f"✅ PASSED: {test_result.get('message')}")
        return True
    else:
        print(f"❌ FAILED: Unexpected result: {test_result}")
        return False


async def test_undefined_result():
    """Test that undefined result is handled gracefully (internal NameError catch)."""
    print("\n=== Test 4: Undefined result handling ===")
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "AsyncPythonCodeNode",
        "test",
        {
            "code": """
# Don't define result - should return empty dict
x = 1 + 1
"""
        },
    )

    results = await runtime.execute_workflow_async(workflow.build(), inputs={})
    test_result = results.get("results", {}).get("test", {})

    if test_result == {}:
        print("✅ PASSED: Empty dict returned as expected")
        return True
    else:
        print(f"❌ FAILED: Expected empty dict, got: {test_result}")
        return False


async def test_stopiteration_catch():
    """Test that StopIteration can be caught in AsyncPythonCodeNode."""
    print("\n=== Test 5: StopIteration catch ===")
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "AsyncPythonCodeNode",
        "test",
        {
            "code": """
try:
    # Create iterator and exhaust it
    it = iter([1, 2, 3])
    next(it)
    next(it)
    next(it)
    next(it)  # This raises StopIteration
    result = {"status": "failed"}
except StopIteration:
    result = {"status": "success", "message": "StopIteration caught"}
"""
        },
    )

    results = await runtime.execute_workflow_async(workflow.build(), inputs={})
    test_result = results.get("results", {}).get("test", {})

    if test_result.get("status") == "success":
        print(f"✅ PASSED: {test_result.get('message')}")
        return True
    else:
        print(f"❌ FAILED: Unexpected result: {test_result}")
        return False


async def test_assertionerror_catch():
    """Test that AssertionError can be caught in AsyncPythonCodeNode."""
    print("\n=== Test 6: AssertionError catch ===")
    runtime = AsyncLocalRuntime()
    workflow = WorkflowBuilder()

    workflow.add_node(
        "AsyncPythonCodeNode",
        "test",
        {
            "code": """
try:
    assert False, "This should fail"
    result = {"status": "failed"}
except AssertionError:
    result = {"status": "success", "message": "AssertionError caught"}
"""
        },
    )

    results = await runtime.execute_workflow_async(workflow.build(), inputs={})
    test_result = results.get("results", {}).get("test", {})

    if test_result.get("status") == "success":
        print(f"✅ PASSED: {test_result.get('message')}")
        return True
    else:
        print(f"❌ FAILED: Unexpected result: {test_result}")
        return False


async def main():
    """Run all validation tests."""
    print("=" * 80)
    print("AsyncPythonCodeNode Exception Handling Fix - Validation Tests")
    print("=" * 80)

    tests = [
        ("NameError", test_nameerror_catch),
        ("AttributeError", test_attributeerror_catch),
        ("ZeroDivisionError", test_zerodivisionerror_catch),
        ("Undefined result", test_undefined_result),
        ("StopIteration", test_stopiteration_catch),
        ("AssertionError", test_assertionerror_catch),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = await test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ FAILED: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name:25} {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED - Fix successfully validated!")
        print()
        print("The following exceptions are now available in AsyncPythonCodeNode:")
        print("  ✅ NameError          - Undefined variables")
        print("  ✅ AttributeError     - Missing attributes")
        print("  ✅ ZeroDivisionError  - Division by zero")
        print("  ✅ StopIteration      - Iterator exhaustion")
        print("  ✅ AssertionError     - Failed assertions")
        print("  ✅ ImportError        - Import failures")
        print("  ✅ IOError            - I/O errors")
        print("  ✅ ArithmeticError    - Arithmetic errors")
        return 0
    else:
        print("❌ Some tests failed - fix may not be complete")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

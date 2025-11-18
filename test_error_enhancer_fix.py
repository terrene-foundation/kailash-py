"""
Test ErrorEnhancer API fix for enhance_missing_required_field().

This test verifies that the fix to nodes.py:1261 correctly passes
operation="CREATE" instead of expected_fields=field_names.

Bug Report: apps/kailash-dataflow/src/dataflow/core/nodes.py:1258-1263
Root Cause: Parameter name mismatch between method definition and call site
Fix: Changed `expected_fields=field_names` to `operation="CREATE"`
"""

import asyncio

from dataflow import DataFlow
from dataflow.exceptions import DataFlowError

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def test_error_enhancer_fix():
    """
    Test that missing required field raises proper DF-105 error with operation context.

    Before fix: TypeError: got an unexpected keyword argument 'expected_fields'
    After fix: DataFlowError with error_code='DF-105' and context containing 'operation'
    """
    print("=" * 80)
    print("TESTING: ErrorEnhancer Fix for enhance_missing_required_field()")
    print("=" * 80)

    # Step 1: Create DataFlow with SQLite
    print("\nStep 1: Creating DataFlow with SQLite...")
    db = DataFlow(":memory:")

    # Step 2: Define User model
    print("Step 2: Defining User model...")

    @db.model
    class User:
        id: str  # Required, no default
        name: str  # Required, no default
        email: str  # Required, no default

    # Step 3: Initialize DataFlow
    print("Step 3: Initializing DataFlow...")
    await db.initialize()

    # Step 4: Test missing 'id' field (most common case)
    print("\nStep 4: Testing missing 'id' field...")
    workflow_missing_id = WorkflowBuilder()
    workflow_missing_id.add_node(
        "UserCreateNode",
        "create",
        {
            "name": "Alice",
            "email": "alice@example.com",
            # Missing 'id' field
        },
    )

    runtime = AsyncLocalRuntime()

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_missing_id.build(), inputs={}
        )
        print("   ❌ FAILED - No error raised (expected DF-105)")
        return False
    except DataFlowError as e:
        # Expected: DataFlowError with DF-105
        print("   ✅ DataFlowError raised")
        print(f"      Error Code: {e.error_code}")
        print(f"      Message: {e.message}")
        print(f"      Context: {e.context}")

        # Verify error code
        if e.error_code != "DF-105":
            print(f"   ❌ FAILED - Wrong error code: {e.error_code} (expected DF-105)")
            return False

        # Verify 'operation' in context
        if "operation" not in e.context:
            print("   ❌ FAILED - 'operation' not in context")
            return False

        # Verify operation is 'CREATE'
        if e.context["operation"] != "CREATE":
            print(
                f"   ❌ FAILED - Wrong operation: {e.context['operation']} (expected CREATE)"
            )
            return False

        # Verify field_name is 'id'
        if e.context.get("field_name") != "id":
            print(
                f"   ❌ FAILED - Wrong field_name: {e.context.get('field_name')} (expected id)"
            )
            return False

        print("   ✅ PASSED - DF-105 error with correct operation context")
    except TypeError as e:
        # Before fix: TypeError about 'expected_fields'
        error_str = str(e)
        if "expected_fields" in error_str:
            print(f"   ❌ FAILED - Old bug still present: {error_str}")
        else:
            print(f"   ❌ FAILED - Unexpected TypeError: {error_str}")
        return False
    except Exception as e:
        print(f"   ❌ FAILED - Unexpected exception: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Step 5: Test missing other required field
    print("\nStep 5: Testing missing 'name' field...")
    workflow_missing_name = WorkflowBuilder()
    workflow_missing_name.add_node(
        "UserCreateNode",
        "create2",
        {
            "id": "user-123",
            "email": "alice@example.com",
            # Missing 'name' field
        },
    )

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_missing_name.build(), inputs={}
        )
        print("   ❌ FAILED - No error raised (expected DF-105)")
        return False
    except DataFlowError as e:
        print("   ✅ DataFlowError raised for 'name' field")
        print(f"      Error Code: {e.error_code}")
        print(f"      Field: {e.context.get('field_name')}")

        if e.error_code != "DF-105":
            print("   ❌ FAILED - Wrong error code")
            return False

        if e.context.get("field_name") != "name":
            print("   ❌ FAILED - Wrong field_name")
            return False

        print("   ✅ PASSED - DF-105 error for 'name' field")
    except TypeError as e:
        print(f"   ❌ FAILED - Old bug still present: {e}")
        return False
    except Exception as e:
        print(f"   ❌ FAILED - Unexpected exception: {type(e).__name__}: {e}")
        return False

    # Step 6: Test valid CREATE (regression test)
    print("\nStep 6: Testing valid CREATE (regression test)...")
    workflow_valid = WorkflowBuilder()
    workflow_valid.add_node(
        "UserCreateNode",
        "create_valid",
        {"id": "user-456", "name": "Bob", "email": "bob@example.com"},
    )

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_valid.build(), inputs={}
        )
        created_user = results.get("create_valid")

        if not created_user:
            print("   ❌ FAILED - No result returned")
            return False

        if created_user.get("id") != "user-456":
            print(f"   ❌ FAILED - Wrong ID: {created_user.get('id')}")
            return False

        print("   ✅ PASSED - Valid CREATE still works")
    except Exception as e:
        print(f"   ❌ FAILED - Valid CREATE broken: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED - ErrorEnhancer fix verified")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_error_enhancer_fix())
    exit(0 if success else 1)

"""
Test ErrorEnhancer API fix for enhance_auto_managed_field_conflict().

This test verifies that the fix to nodes.py:423-427 correctly passes
field_name instead of fields/model_name.

Bug Report: apps/kailash-dataflow/src/dataflow/core/nodes.py:423-428
Root Cause: Parameter name mismatch between method definition and call site
Fix: Changed `fields=auto_managed_fields, model_name=...` to `field_name=", ".join(auto_managed_fields)`
"""

import asyncio

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from dataflow.exceptions import DataFlowError


async def test_auto_managed_field_fix():
    """
    Test that auto-managed field raises proper DF-104 error.

    Before fix: TypeError: got unexpected keyword arguments 'fields', 'model_name'
    After fix: DataFlowError with error_code='DF-104' and context containing 'field_name'
    """
    print("=" * 80)
    print("TESTING: ErrorEnhancer Fix for enhance_auto_managed_field_conflict()")
    print("=" * 80)

    # Step 1: Create DataFlow with SQLite
    print("\nStep 1: Creating DataFlow with SQLite...")
    db = DataFlow(":memory:")

    # Step 2: Define User model
    print("Step 2: Defining User model...")

    @db.model
    class User:
        id: str
        name: str
        email: str

    # Step 3: Initialize DataFlow
    print("Step 3: Initializing DataFlow...")
    await db.initialize()

    # Step 4: Test auto-managed field conflict (created_at)
    print("\nStep 4: Testing auto-managed 'created_at' field...")
    workflow_created_at = WorkflowBuilder()
    workflow_created_at.add_node(
        "UserCreateNode",
        "create",
        {
            "id": "user-123",
            "name": "Alice",
            "email": "alice@example.com",
            "created_at": "2024-01-01T00:00:00",  # Auto-managed field
        },
    )

    runtime = AsyncLocalRuntime()

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_created_at.build(), inputs={}
        )
        print("   ❌ FAILED - No error raised (expected DF-104)")
        return False
    except DataFlowError as e:
        # Expected: DataFlowError with DF-104
        print("   ✅ DataFlowError raised")
        print(f"      Error Code: {e.error_code}")
        print(f"      Message: {e.message}")
        print(f"      Context: {e.context}")

        # Verify error code
        if e.error_code != "DF-104":
            print(f"   ❌ FAILED - Wrong error code: {e.error_code} (expected DF-104)")
            return False

        # Verify 'field_name' in context
        if "field_name" not in e.context:
            print("   ❌ FAILED - 'field_name' not in context")
            return False

        # Verify field_name contains 'created_at'
        if "created_at" not in e.context.get("field_name", ""):
            print(
                f"   ❌ FAILED - Wrong field_name: {e.context.get('field_name')} (expected 'created_at')"
            )
            return False

        print("   ✅ PASSED - DF-104 error with correct field_name context")
    except TypeError as e:
        # Before fix: TypeError about 'fields' or 'model_name'
        error_str = str(e)
        if "fields" in error_str or "model_name" in error_str:
            print(f"   ❌ FAILED - Old bug still present: {error_str}")
        else:
            print(f"   ❌ FAILED - Unexpected TypeError: {error_str}")
        return False
    except Exception as e:
        print(f"   ❌ FAILED - Unexpected exception: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Step 5: Test auto-managed field conflict (updated_at)
    print("\nStep 5: Testing auto-managed 'updated_at' field...")
    workflow_updated_at = WorkflowBuilder()
    workflow_updated_at.add_node(
        "UserCreateNode",
        "create2",
        {
            "id": "user-456",
            "name": "Bob",
            "email": "bob@example.com",
            "updated_at": "2024-01-01T00:00:00",  # Auto-managed field
        },
    )

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_updated_at.build(), inputs={}
        )
        print("   ❌ FAILED - No error raised (expected DF-104)")
        return False
    except DataFlowError as e:
        print("   ✅ DataFlowError raised for 'updated_at' field")
        print(f"      Error Code: {e.error_code}")
        print(f"      Field: {e.context.get('field_name')}")

        if e.error_code != "DF-104":
            print("   ❌ FAILED - Wrong error code")
            return False

        if "updated_at" not in e.context.get("field_name", ""):
            print("   ❌ FAILED - Wrong field_name")
            return False

        print("   ✅ PASSED - DF-104 error for 'updated_at' field")
    except TypeError as e:
        print(f"   ❌ FAILED - Old bug still present: {e}")
        return False
    except Exception as e:
        print(f"   ❌ FAILED - Unexpected exception: {type(e).__name__}: {e}")
        return False

    # Step 6: Test multiple auto-managed fields
    print("\nStep 6: Testing multiple auto-managed fields (created_at + updated_at)...")
    workflow_multiple = WorkflowBuilder()
    workflow_multiple.add_node(
        "UserCreateNode",
        "create3",
        {
            "id": "user-789",
            "name": "Charlie",
            "email": "charlie@example.com",
            "created_at": "2024-01-01T00:00:00",  # Auto-managed
            "updated_at": "2024-01-01T00:00:00",  # Auto-managed
        },
    )

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_multiple.build(), inputs={}
        )
        print("   ❌ FAILED - No error raised (expected DF-104)")
        return False
    except DataFlowError as e:
        print("   ✅ DataFlowError raised for multiple fields")
        print(f"      Error Code: {e.error_code}")
        print(f"      Field: {e.context.get('field_name')}")

        if e.error_code != "DF-104":
            print("   ❌ FAILED - Wrong error code")
            return False

        # Verify both fields are mentioned (joined by ", ")
        field_name = e.context.get("field_name", "")
        if "created_at" not in field_name or "updated_at" not in field_name:
            print(f"   ❌ FAILED - Not all fields mentioned: {field_name}")
            return False

        print("   ✅ PASSED - DF-104 error for multiple fields")
    except TypeError as e:
        print(f"   ❌ FAILED - Old bug still present: {e}")
        return False
    except Exception as e:
        print(f"   ❌ FAILED - Unexpected exception: {type(e).__name__}: {e}")
        return False

    # Step 7: Test valid CREATE (regression test)
    print(
        "\nStep 7: Testing valid CREATE without auto-managed fields (regression test)..."
    )
    workflow_valid = WorkflowBuilder()
    workflow_valid.add_node(
        "UserCreateNode",
        "create_valid",
        {
            "id": "user-valid",
            "name": "Valid User",
            "email": "valid@example.com",
            # No auto-managed fields
        },
    )

    try:
        results, _ = await runtime.execute_workflow_async(
            workflow_valid.build(), inputs={}
        )
        created_user = results.get("create_valid")

        if not created_user:
            print("   ❌ FAILED - No result returned")
            return False

        if created_user.get("id") != "user-valid":
            print(f"   ❌ FAILED - Wrong ID: {created_user.get('id')}")
            return False

        print("   ✅ PASSED - Valid CREATE still works")
    except Exception as e:
        print(f"   ❌ FAILED - Valid CREATE broken: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED - ErrorEnhancer auto-managed field fix verified")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_auto_managed_field_fix())
    exit(0 if success else 1)

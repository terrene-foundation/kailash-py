#!/usr/bin/env python3
"""
Simple test to prove ListNode filter bug and validate fix
Uses correct DataFlow node parameters (no db_instance, no model_name)
"""

import sqlite3
import sys

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def main():
    print("\n" + "=" * 70)
    print("SIMPLE ListNode Filter Test")
    print("=" * 70)

    # Step 1: Create DataFlow with SQLite
    print("\n1. Creating DataFlow with :memory: database...")
    db = DataFlow(":memory:")

    # Step 2: Define model
    print("2. Defining User model...")

    @db.model
    class User:
        id: str
        status: str
        name: str

    # Step 3: Create test data using CORRECT parameters
    # DataFlow nodes DON'T need db_instance or model_name
    # The node is already bound to the model
    print("3. Creating test data...")
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create1",
        {"id": "user1", "status": "active", "name": "Alice"},
    )
    workflow.add_node(
        "UserCreateNode",
        "create2",
        {"id": "user2", "status": "inactive", "name": "Bob"},
    )
    workflow.add_node(
        "UserCreateNode",
        "create3",
        {"id": "user3", "status": "active", "name": "Charlie"},
    )

    runtime = LocalRuntime()
    create_results, _ = runtime.execute(workflow.build())
    print(
        f"   Created {len([k for k in create_results.keys() if k.startswith('create')])} users"
    )

    # Step 4: Query ALL users (no filter) - ground truth
    print("\n4. Querying ALL users (no filter) - ground truth...")
    workflow2 = WorkflowBuilder()
    workflow2.add_node("UserListNode", "list_all", {})

    all_results, _ = runtime.execute(workflow2.build())
    all_users = all_results["list_all"]["records"]
    print(f"   Total users in database: {len(all_users)}")
    for user in all_users:
        print(f"     - {user['id']}: {user['status']} ({user['name']})")

    # Step 5: Query with $ne filter
    print("\n5. Testing $ne filter (status != 'inactive')...")
    print("   Expected: 2 users (user1=active, user3=active)")

    workflow3 = WorkflowBuilder()
    workflow3.add_node(
        "UserListNode", "list_filtered", {"filter": {"status": {"$ne": "inactive"}}}
    )

    filter_results, _ = runtime.execute(workflow3.build())
    filtered_users = filter_results["list_filtered"]["records"]

    print(f"   Actual: {len(filtered_users)} users")
    for user in filtered_users:
        print(f"     - {user['id']}: {user['status']} ({user['name']})")

    # Step 6: Validate result
    print("\n" + "=" * 70)
    expected_count = 2
    actual_count = len(filtered_users)

    if actual_count == expected_count:
        print(
            f"✅ TEST PASSED: Filter returned {actual_count} users (expected {expected_count})"
        )
        print("✅ FIX VERIFIED: $ne operator works correctly")
        return 0
    else:
        print(
            f"❌ TEST FAILED: Filter returned {actual_count} users (expected {expected_count})"
        )
        if actual_count == 3:
            print("❌ BUG DETECTED: Filter was ignored, returned ALL users")
        elif actual_count == 0:
            print("❌ BUG DETECTED: Query returned no results")
        print(
            "\nCheck WARNING logs above for SQL query path (QueryBuilder vs Unfiltered)"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

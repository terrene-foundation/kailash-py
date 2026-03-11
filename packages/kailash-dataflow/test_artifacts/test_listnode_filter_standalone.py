#!/usr/bin/env python3
"""
Standalone test for ListNode filter bug - NO pytest required.

Run as: python test_listnode_filter_standalone.py

Tests all filter operators ($ne, $nin, $in, $eq) against ground truth SQL queries.
Demonstrates that ListNode filters are broken.

This test uses DIRECT SQL to create test data, ensuring the data exists before testing.
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Add dataflow to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def setup_database_with_sql(db_path):
    """Create test database and data using DIRECT SQL."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create users table with direct SQL
    cursor.execute(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """
    )

    # Insert test data with direct SQL
    test_users = [
        ("user1", "Alice Smith", "alice@example.com", "active"),
        ("user2", "Bob Jones", "bob@example.com", "inactive"),
        ("user3", "Charlie Brown", "charlie@example.com", "active"),
        ("user4", "Diana Prince", "diana@example.com", "pending"),
        ("user5", "Eve Wilson", "eve@example.com", "active"),
    ]

    cursor.executemany(
        "INSERT INTO users (id, name, email, status) VALUES (?, ?, ?, ?)", test_users
    )

    conn.commit()

    # Verify data was inserted
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    print(f"✓ Created {count} test records with direct SQL")

    conn.close()
    return db_path


def get_ground_truth_count(db_path, condition):
    """Get count using raw SQL - this is the ground truth."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = f"SELECT COUNT(*) FROM users WHERE {condition}"
    cursor.execute(query)
    count = cursor.fetchone()[0]
    conn.close()

    print(f"  Ground Truth SQL: {query}")
    print(f"  Ground Truth Count: {count}")
    return count


def get_dataflow_count_direct(db_path, filter_dict):
    """Get count using DataFlow ListNode with filters."""
    # Create DataFlow instance pointing to existing database
    db_url = f"sqlite:///{db_path}"
    db = DataFlow(db_path=db_url, prefix="test")

    # Register existing table as a model
    @db.model
    class User:
        __tablename__ = "users"
        id: str
        name: str
        email: str
        status: str

    # Build workflow
    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list_users", {"filter": filter_dict})

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    users = results.get("list_users", {}).get("items", [])
    count = len(users)

    print(f"  DataFlow Filter: {filter_dict}")
    print(f"  DataFlow Count: {count}")

    if users:
        print(f"  Sample returned: {users[0]}")
    else:
        print("  ❌ No records returned (BUG!)")

    return count


def test_ne_operator(db_path):
    """Test $ne (not equal) operator."""
    print("\n" + "=" * 70)
    print("TEST: $ne operator (status != 'active')")
    print("=" * 70)

    # Ground truth: status != 'active'
    # Should return: inactive, pending (2 records)
    ground_truth = get_ground_truth_count(db_path, "status != 'active'")

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(db_path, {"status": {"$ne": "active"}})

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: $ne operator works correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def test_nin_operator(db_path):
    """Test $nin (not in) operator."""
    print("\n" + "=" * 70)
    print("TEST: $nin operator (status NOT IN ('active', 'inactive'))")
    print("=" * 70)

    # Ground truth: status NOT IN ('active', 'inactive')
    # Should return: pending (1 record)
    ground_truth = get_ground_truth_count(
        db_path, "status NOT IN ('active', 'inactive')"
    )

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(
        db_path, {"status": {"$nin": ["active", "inactive"]}}
    )

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: $nin operator works correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def test_in_operator(db_path):
    """Test $in operator."""
    print("\n" + "=" * 70)
    print("TEST: $in operator (status IN ('active', 'pending'))")
    print("=" * 70)

    # Ground truth: status IN ('active', 'pending')
    # Should return: active, active, active, pending (4 records)
    ground_truth = get_ground_truth_count(db_path, "status IN ('active', 'pending')")

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(
        db_path, {"status": {"$in": ["active", "pending"]}}
    )

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: $in operator works correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def test_eq_operator(db_path):
    """Test $eq operator (explicit equality)."""
    print("\n" + "=" * 70)
    print("TEST: $eq operator (status = 'inactive')")
    print("=" * 70)

    # Ground truth: status = 'inactive'
    # Should return: 1 record
    ground_truth = get_ground_truth_count(db_path, "status = 'inactive'")

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(db_path, {"status": {"$eq": "inactive"}})

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: $eq operator works correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def test_implicit_eq_operator(db_path):
    """Test implicit equality (no operator)."""
    print("\n" + "=" * 70)
    print("TEST: Implicit equality (status: 'active')")
    print("=" * 70)

    # Ground truth: status = 'active'
    # Should return: 3 records
    ground_truth = get_ground_truth_count(db_path, "status = 'active'")

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(db_path, {"status": "active"})

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: Implicit equality works correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def test_empty_filter(db_path):
    """Test empty filter (should return all records)."""
    print("\n" + "=" * 70)
    print("TEST: Empty filter (should return all records)")
    print("=" * 70)

    # Ground truth: all records
    ground_truth = get_ground_truth_count(db_path, "1=1")

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(db_path, {})

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: Empty filter works correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def test_multiple_conditions_and(db_path):
    """Test multiple conditions with AND logic."""
    print("\n" + "=" * 70)
    print("TEST: Multiple conditions (status = 'active' AND id > 'user2')")
    print("=" * 70)

    # Ground truth: status = 'active' AND id > 'user2'
    # Should return: user3, user5 (2 records)
    ground_truth = get_ground_truth_count(db_path, "status = 'active' AND id > 'user2'")

    # DataFlow query
    dataflow_count = get_dataflow_count_direct(
        db_path, {"status": "active", "id": {"$gt": "user2"}}
    )

    # Validation
    if dataflow_count == ground_truth:
        print("  ✅ PASS: Multiple conditions work correctly")
        return True
    else:
        print(f"  ❌ FAIL: Expected {ground_truth}, got {dataflow_count}")
        return False


def main():
    """Run all standalone tests."""
    print("\n" + "=" * 70)
    print("STANDALONE TEST: ListNode Filter Bug")
    print("=" * 70)
    print("Testing all filter operators against ground truth SQL queries")
    print("No pytest, no fixtures - just pure Python, SQLite, and DataFlow")
    print("=" * 70)

    # Setup - use temporary database file
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")

    print(f"\nTest Database: {db_path}")
    print("\nSetting up test data with DIRECT SQL...")
    setup_database_with_sql(db_path)
    print()

    # Run tests
    results = []
    results.append(("Empty Filter", test_empty_filter(db_path)))
    results.append(("Implicit Equality", test_implicit_eq_operator(db_path)))
    results.append(("$eq Operator", test_eq_operator(db_path)))
    results.append(("$in Operator", test_in_operator(db_path)))
    results.append(("$ne Operator", test_ne_operator(db_path)))
    results.append(("$nin Operator", test_nin_operator(db_path)))
    results.append(("Multiple Conditions", test_multiple_conditions_and(db_path)))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    # Cleanup
    try:
        os.remove(db_path)
        os.rmdir(temp_dir)
    except:
        pass

    # Exit with appropriate code
    if passed == total:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        print("\n" + "=" * 70)
        print("BUG DEMONSTRATED")
        print("=" * 70)
        print(
            "Expected behavior: DataFlow ListNode filters should match SQL WHERE clauses"
        )
        print(
            "Actual behavior: Filter operators ($ne, $nin, etc.) return incorrect results"
        )
        print("\nRoot cause analysis:")
        print("- Ground truth (raw SQL): Returns correct counts")
        print("- DataFlow ListNode: Returns 0 or all records (ignoring filters)")
        print("\nThis proves the ListNode filter bug exists and needs fixing.")
        sys.exit(1)


if __name__ == "__main__":
    main()

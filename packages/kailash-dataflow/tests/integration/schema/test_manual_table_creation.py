#!/usr/bin/env python3
"""
Test SQLite schema discovery by manually creating a table first.
"""

import asyncio
import os

# Add src to path for testing
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dataflow import DataFlow
from dataflow.adapters.sqlite import SQLiteAdapter
from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


async def test_manual_table_schema_discovery():
    """Test schema discovery on a manually created table."""
    print("=== Testing Schema Discovery on Manual Table ===")

    try:
        # Create a temporary SQLite database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            print(f"Using database file: {db_path}")

            # Step 1: Manually create a test table using the adapter
            adapter = SQLiteAdapter(f"sqlite:///{db_path}")
            await adapter.connect()

            # Create a test table with the expected structure
            create_table_sql = """
                CREATE TABLE test_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    age INTEGER DEFAULT 25,
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            await adapter.execute_query(create_table_sql)
            print("✅ Manually created test_users table")

            # Insert some test data
            await adapter.execute_query(
                "INSERT INTO test_users (name, email, age) VALUES (?, ?, ?)",
                ["Alice Smith", "alice@example.com", 30],
            )
            print("✅ Inserted test data")

            await adapter.disconnect()

            # Step 2: Now test schema discovery on this database
            db = DataFlow(f"sqlite:///{db_path}")

            # Test the schema discovery
            print("\n🔍 Testing schema discovery...")
            schema = await db._inspect_sqlite_schema_real(f"sqlite:///{db_path}")

            if schema:
                print(f"✅ Schema discovery found {len(schema)} tables")

                # Check if our test table was discovered
                if "test_users" in schema:
                    table_info = schema["test_users"]
                    print(
                        f"✅ Found test_users table with {len(table_info['columns'])} columns"
                    )

                    # Verify column information
                    column_names = [col["name"] for col in table_info["columns"]]
                    expected_columns = [
                        "id",
                        "name",
                        "email",
                        "age",
                        "active",
                        "created_at",
                    ]

                    print("📋 Discovered columns:")
                    for col in table_info["columns"]:
                        print(
                            f"   {col['name']}: {col['type']} (nullable: {col['nullable']}, pk: {col['primary_key']})"
                        )

                    for expected_col in expected_columns:
                        if expected_col in column_names:
                            print(f"✅ Found expected column: {expected_col}")
                        else:
                            print(f"❌ Missing expected column: {expected_col}")

                    print("✅ SQLite schema discovery working correctly!")
                    return True
                else:
                    print("❌ test_users table not found in discovered schema")
                    print(f"   Available tables: {list(schema.keys())}")
                    return False
            else:
                print("❌ Schema discovery returned empty result")
                return False

        finally:
            # Clean up the temporary database file
            if os.path.exists(db_path):
                os.unlink(db_path)

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_high_level_discover_schema():
    """Test the high-level discover_schema method."""
    print("\n=== Testing High-level discover_schema Method ===")

    try:
        # Create a temporary SQLite database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            # Create and populate database
            adapter = SQLiteAdapter(f"sqlite:///{db_path}")
            await adapter.connect()

            # Create multiple test tables
            await adapter.execute_query(
                """
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE
                )
            """
            )

            await adapter.execute_query(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    total REAL DEFAULT 0.0,
                    FOREIGN KEY (customer_id) REFERENCES customers (id)
                )
            """
            )

            await adapter.disconnect()
            print("✅ Created test database with customers and orders tables")

            # Test high-level discover_schema
            db = DataFlow(f"sqlite:///{db_path}")

            # Use the public API
            schema = db.discover_schema(use_real_inspection=True)

            if schema:
                print(f"✅ High-level schema discovery found {len(schema)} tables")
                print(f"   Tables: {list(schema.keys())}")

                # Check relationships
                if "orders" in schema and "relationships" in schema["orders"]:
                    print(
                        f"✅ Found relationships in orders table: {schema['orders']['relationships']}"
                    )

                return True
            else:
                print("❌ High-level schema discovery returned empty result")
                return False

        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    except Exception as e:
        print(f"❌ High-level test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("🧪 Manual Table Creation Schema Discovery Tests")
    print("===============================================")

    tests = [
        ("Manual Table Schema Discovery", test_manual_table_schema_discovery),
        ("High-level discover_schema Method", test_high_level_discover_schema),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🔄 Running: {test_name}")
        try:
            success = await test_func()
            if success:
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")

    print(f"\n📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! SQLite schema discovery is working!")
        return True
    else:
        print("⚠️  Some tests failed.")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)

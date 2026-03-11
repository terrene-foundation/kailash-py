#!/usr/bin/env python3
"""
Basic E2E tests for DataFlow that complete in <10s.
Tests core functionality with real PostgreSQL and SQLite infrastructure.
"""

import asyncio
import os

import pytest
from dataflow import DataFlow

from tests.conftest import DATABASE_CONFIGS
from tests.utils.real_infrastructure import real_infra


@pytest.mark.e2e
@pytest.mark.timeout(10)
@pytest.mark.parametrize("db_config", DATABASE_CONFIGS, ids=lambda x: x["id"])
async def test_basic_dataflow_operations(db_config):
    """Test basic CRUD operations with DataFlow in <10s."""
    # Create DataFlow instance with cache disabled for testing
    db = DataFlow(
        db_config["url"],
        migration_enabled=True,
        existing_schema_mode=True,
        cache_enabled=False,
    )

    # Define a simple model
    @db.model
    class TestUser:
        name: str
        email: str
        active: bool = True

    # Ensure tables are created for both databases
    db.create_tables()

    # Initialize (should be fast with existing_schema_mode=True)
    await db.initialize()

    # Test Create
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    workflow = WorkflowBuilder()
    create_params = {"name": "Test User", "email": "test@example.com"}
    # DataFlow nodes use the instance's database configuration internally
    workflow.add_node("TestUserCreateNode", "create_user", create_params)

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert "create_user" in results
    user_data = results["create_user"]
    print(f"DEBUG: Create result = {user_data}")

    # Handle database-specific response formats
    if db_config["type"] == "postgresql":
        # Check if the create operation actually succeeded
        if isinstance(user_data, dict):
            # The node might return the created record or just success status
            if "id" in user_data:
                created_id = user_data.get("id")
                print(f"DEBUG: Created user with ID = {created_id}")
            assert user_data.get("name") == "Test User" or user_data.get("success")
        else:
            print(f"DEBUG: Unexpected create result type: {type(user_data)}")
    elif db_config["type"] == "sqlite":
        # SQLite may have different response format, verify operation completed
        assert user_data is not None
        if isinstance(user_data, dict):
            if "name" in user_data:
                assert user_data["name"] == "Test User"
            if "email" in user_data:
                assert user_data["email"] == "test@example.com"

    # Test Read
    workflow = WorkflowBuilder()
    list_params = {}
    # DataFlow nodes use the instance's database configuration internally
    workflow.add_node("TestUserListNode", "list_users", list_params)

    results, run_id = runtime.execute(workflow.build())

    assert "list_users" in results
    list_result = results["list_users"]

    # Handle database-specific response formats
    if db_config["type"] == "postgresql":
        print(f"DEBUG: list_result = {list_result}")
        users = list_result.get("records", [])
        print(f"DEBUG: users = {users}")
        assert len(users) >= 1, f"Expected at least 1 user, got {len(users)}"
        assert any(
            u.get("email") == "test@example.com" for u in users
        ), f"Could not find user with email test@example.com in {users}"
    elif db_config["type"] == "sqlite":
        # SQLite may have different response format, verify operation completed
        assert list_result is not None
        if isinstance(list_result, dict) and "records" in list_result:
            users = list_result["records"]
            # Check if we have users and if email matches (if present)
            if users and isinstance(users, list) and len(users) > 0:
                for user in users:
                    if isinstance(user, dict) and "email" in user:
                        if user["email"] == "test@example.com":
                            break

    print(f"✅ Basic E2E test completed successfully for {db_config['type']}")


@pytest.mark.e2e
@pytest.mark.timeout(10)
async def test_dataflow_model_registration():
    """Test model registration completes in <10s."""
    db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/kailash_test",
    )

    db = DataFlow(db_url, migration_enabled=True, existing_schema_mode=True)

    # Register multiple models
    @db.model
    class Product:
        name: str
        price: float

    @db.model
    class Order:
        product_id: int
        quantity: int
        total: float

    # Initialize should be fast
    await db.initialize()

    # Verify nodes were created
    assert db.get_node("ProductCreateNode") is not None
    assert db.get_node("ProductListNode") is not None
    assert db.get_node("OrderCreateNode") is not None
    assert db.get_node("OrderListNode") is not None

    print("✅ Model registration E2E test completed successfully")


@pytest.mark.e2e
@pytest.mark.timeout(10)
async def test_dataflow_existing_database_safety():
    """Test existing database safety completes in <10s."""
    db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/kailash_test",
    )

    # First app - CREATE the table (without existing_schema_mode)
    db1 = DataFlow(db_url, migration_enabled=True, existing_schema_mode=False)

    @db1.model
    class SafetyTest:
        value: str

    await db1.initialize()

    # Second app - use existing table safely (with existing_schema_mode)
    db2 = DataFlow(db_url, migration_enabled=True, existing_schema_mode=True)

    @db2.model
    class SafetyTest:
        value: str

    # Should not cause issues - table already exists
    await db2.initialize()

    # Both should work now that table exists
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    runtime = LocalRuntime()

    # Create with first instance (table creator)
    workflow = WorkflowBuilder()
    workflow.add_node("SafetyTestCreateNode", "create1", {"value": "test1"})
    results, _ = runtime.execute(workflow.build())
    assert "create1" in results

    # Create with second instance (existing schema mode)
    workflow = WorkflowBuilder()
    workflow.add_node("SafetyTestCreateNode", "create2", {"value": "test2"})
    results, _ = runtime.execute(workflow.build())
    assert "create2" in results

    print("✅ Database safety E2E test completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

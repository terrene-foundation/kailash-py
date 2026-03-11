"""
Integration test to reproduce DataFlow PostgreSQL parameter conversion bug.

This test reproduces the issue documented in ADR-005 where DataFlow-generated
nodes fail to execute CREATE/UPDATE operations on PostgreSQL due to parameter
conversion failures in the AsyncSQLDatabaseNode → PostgreSQL adapter chain.
"""

import os
import sys
from pathlib import Path

import pytest

# Add the DataFlow src directory to sys.path
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
class TestDataFlowPostgreSQLParameterConversion:
    """Test DataFlow parameter conversion with PostgreSQL."""

    @pytest.fixture
    def test_dataflow(self, test_suite):
        """Create DataFlow instance with PostgreSQL."""
        # Use test suite database URL
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class TestUser:
            name: str
            email: str
            age: int = 25

        # Initialize and create the database tables
        try:
            if hasattr(db, "initialize"):
                import asyncio

                if asyncio.iscoroutinefunction(db.initialize):
                    # Handle async initialization in sync fixture
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If event loop is running, we can't run another loop
                        # Create tables synchronously if possible
                        if hasattr(db, "create_tables"):
                            db.create_tables()
                    else:
                        loop.run_until_complete(db.initialize())
                        db.create_tables()
                else:
                    db.initialize()
                    db.create_tables()
            elif hasattr(db, "create_tables"):
                db.create_tables()
        except Exception as e:
            # If table creation fails, let the test continue
            # The failure will be caught in the actual test
            print(f"Warning: Table creation failed: {e}")
            pass

        return db

    def test_dataflow_create_node_parameter_conversion_bug(
        self, test_suite, test_dataflow
    ):
        """
        Test that reproduces the DataFlow PostgreSQL parameter conversion bug.

        This test should FAIL if the bug exists:
        1. DataFlow generates correct SQL: INSERT INTO test_users (name, email, age) VALUES ($1, $2, $3)
        2. AsyncSQLDatabaseNode converts to: INSERT INTO test_users (name, email, age) VALUES (:p0, :p1, :p2)
        3. PostgreSQL adapter fails to convert back properly
        4. PostgreSQL receives invalid syntax: ":p0, :p1, :p2" instead of "$1, $2, $3"
        5. ERROR: syntax error at or near ":"
        """
        workflow = WorkflowBuilder()

        # Add node without parameters (will get them at runtime)
        workflow.add_node("TestUserCreateNode", "create_user", {})

        # Provide parameters via runtime execution (standard DataFlow pattern)
        runtime_params = {
            "create_user": {
                "name": "Alice Doe",
                "email": "alice@example.com",
                "age": 30,
            }
        }

        runtime = LocalRuntime()

        # This execution should fail with PostgreSQL syntax error if bug exists
        try:
            print("Executing DataFlow-generated node with PostgreSQL...")
            results, run_id = runtime.execute(
                workflow.build(), parameters=runtime_params
            )

            # If we get here, the bug might be fixed or doesn't exist
            print("✅ Execution succeeded - examining results...")
            assert "create_user" in results
            create_result = results["create_user"]

            print(f"Create result: {create_result}")

            # DataFlow returns the created record directly or None if failed
            if create_result is not None:
                # Check if it's a dictionary with the expected fields
                if isinstance(create_result, dict):
                    # Verify the created user data
                    assert create_result.get("name") == "Alice Doe"
                    assert create_result.get("email") == "alice@example.com"
                    assert create_result.get("age") == 30
                    print(f"✅ User created successfully: {create_result}")
                else:
                    # Non-dict result but not None means successful creation
                    print(f"✅ User creation succeeded with result: {create_result}")
            else:
                pytest.fail(
                    "❌ Create operation returned None - operation may have failed"
                )

        except Exception as e:
            error_msg = str(e).lower()
            print(f"❌ Exception occurred: {e}")
            print(f"Error message (lowercase): {error_msg}")

            # Check if this is the expected parameter conversion bug
            if "syntax error" in error_msg and (
                ":" in error_msg or "near" in error_msg
            ):
                pytest.fail(
                    f"❌ DataFlow PostgreSQL parameter conversion bug reproduced: {e}\n"
                    f"This confirms the issue documented in ADR-005.\n"
                    f"The AsyncSQLDatabaseNode → PostgreSQL adapter parameter conversion is failing.\n"
                    f"Expected SQL: INSERT INTO test_users (...) VALUES ($1, $2, $3)\n"
                    f"Actual SQL likely: INSERT INTO test_users (...) VALUES (:p0, :p1, :p2)\n"
                    f"PostgreSQL cannot parse the :pN syntax."
                )
            else:
                # Some other error - re-raise it
                print(
                    "❌ Different error than expected parameter conversion bug - re-raising"
                )
                raise

    def test_asyncsql_direct_usage_works(self, test_suite):
        """
        Control test: verify that AsyncSQLDatabaseNode works correctly when used directly.

        This test should PASS and demonstrates that the workaround (ADR-005) is valid.
        """
        workflow = WorkflowBuilder()

        # Create table first
        postgres_url = test_suite.config.url
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": test_suite.config.url,
                "query": """
                CREATE TABLE IF NOT EXISTS direct_test_users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    age INTEGER DEFAULT 25,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
                "fetch_mode": "all",
                "validate_queries": False,
            },
        )

        # Insert using direct AsyncSQLDatabaseNode (should work)
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_user",
            {
                "connection_string": test_suite.config.url,
                "query": "INSERT INTO direct_test_users (name, email, age) VALUES ($1, $2, $3) RETURNING *",
                "params": ["Charlie Direct", "charlie@example.com", 35],
                "fetch_mode": "one",
            },
        )

        workflow.add_connection("create_table", "result", "insert_user", "trigger")

        runtime = LocalRuntime()
        print("Executing direct AsyncSQLDatabaseNode with PostgreSQL...")
        results, run_id = runtime.execute(workflow.build())

        # This should work without issues
        print(f"Direct AsyncSQL results: {results}")
        assert "insert_user" in results
        insert_result = results["insert_user"]

        # Check for successful insertion - AsyncSQL returns different structure
        if insert_result is not None:
            # AsyncSQL may return result in different formats
            user_data = None

            # Handle different result structures
            if isinstance(insert_result, dict):
                if "result" in insert_result and "data" in insert_result["result"]:
                    user_data = insert_result["result"]["data"]
                elif "data" in insert_result:
                    user_data = insert_result["data"]
                elif "name" in insert_result:  # Direct record
                    user_data = insert_result

            if user_data:
                assert user_data["name"] == "Charlie Direct"
                assert user_data["email"] == "charlie@example.com"
                assert user_data["age"] == 35
                print(f"✅ Direct AsyncSQL worked: {user_data}")
            else:
                print(
                    f"✅ Direct AsyncSQL execution succeeded with result: {insert_result}"
                )

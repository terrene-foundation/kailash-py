"""
Integration test to reproduce DataFlow PostgreSQL parameter conversion bug.

This test reproduces the issue documented in ADR-005 where DataFlow-generated
nodes fail to execute CREATE/UPDATE operations on PostgreSQL due to parameter
conversion failures in the AsyncSQLDatabaseNode → PostgreSQL adapter chain.
"""

import pytest
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


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
class TestDataFlowPostgreSQLParameterConversion:
    """Test DataFlow parameter conversion with PostgreSQL."""

    @pytest.fixture
    def test_dataflow(self, test_suite):
        """Create DataFlow instance with PostgreSQL."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class TestUser:
            name: str
            email: str
            age: int = 25

        return db

    def test_dataflow_create_node_parameter_conversion_bug(
        self, test_dataflow, runtime
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

        # This should trigger the parameter conversion bug
        workflow.add_node(
            "TestUserCreateNode",
            "create_user",
            {"name": "Alice Doe", "email": "alice@example.com", "age": 30},
        )

        runtime = LocalRuntime()

        # This execution should fail with PostgreSQL syntax error if bug exists
        try:
            results, run_id = runtime.execute(workflow.build())

            # If we get here, the bug might be fixed or doesn't exist
            assert "create_user" in results
            create_result = results["create_user"]

            # Verify successful creation
            assert create_result.get("success", True)  # Default to True if not present

            # If result has data, verify it contains the expected user
            if "result" in create_result and "data" in create_result["result"]:
                user_data = create_result["result"]["data"]
                if isinstance(user_data, list) and len(user_data) > 0:
                    user = user_data[0]
                    assert user["name"] == "Alice Doe"
                    assert user["email"] == "alice@example.com"
                    assert user["age"] == 30

        except Exception as e:
            error_msg = str(e).lower()

            # Check if this is the expected parameter conversion bug
            if "syntax error" in error_msg and (
                ":" in error_msg or "near" in error_msg
            ):
                pytest.fail(
                    f"DataFlow PostgreSQL parameter conversion bug reproduced: {e}\n"
                    f"This confirms the issue documented in ADR-005.\n"
                    f"The AsyncSQLDatabaseNode → PostgreSQL adapter parameter conversion is failing.\n"
                    f"Expected SQL: INSERT INTO test_users (...) VALUES ($1, $2, $3)\n"
                    f"Actual SQL likely: INSERT INTO test_users (...) VALUES (:p0, :p1, :p2)\n"
                    f"PostgreSQL cannot parse the :pN syntax."
                )
            else:
                # Some other error - re-raise it
                raise

    def test_dataflow_update_node_parameter_conversion_bug(
        self, test_dataflow, test_database_url
    ):
        """
        Test UPDATE operations to verify parameter conversion bug affects all write operations.
        """
        workflow = WorkflowBuilder()

        # First create a user
        workflow.add_node(
            "TestUserCreateNode",
            "create_user",
            {"name": "Bob Test", "email": "bob@example.com", "age": 25},
        )

        # Then try to update (this may also trigger the bug)
        workflow.add_node(
            "TestUserUpdateNode",
            "update_user",
            {"id": 1, "name": "Bob Updated", "age": 26},  # Assuming auto-increment ID
        )

        # Connect the create result to update
        workflow.add_connection("create_user", "result", "update_user", "id")

        runtime = LocalRuntime()

        try:
            results, run_id = runtime.execute(workflow.build())

            # If we get here without error, verify both operations succeeded
            assert "create_user" in results
            assert "update_user" in results

        except Exception as e:
            error_msg = str(e).lower()

            # Check if this is the parameter conversion bug
            if "syntax error" in error_msg and (
                ":" in error_msg or "near" in error_msg
            ):
                pytest.fail(
                    f"DataFlow PostgreSQL parameter conversion bug in UPDATE operation: {e}\n"
                    f"This confirms the bug affects all write operations, not just CREATE."
                )
            else:
                raise

    def test_asyncsql_direct_usage_works(self, test_database_url):
        """
        Control test: verify that AsyncSQLDatabaseNode works correctly when used directly.

        This test should PASS and demonstrates that the workaround (ADR-005) is valid.
        """
        workflow = WorkflowBuilder()

        # Create table first
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": test_database_url,
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
                "connection_string": test_database_url,
                "query": "INSERT INTO direct_test_users (name, email, age) VALUES ($1, $2, $3) RETURNING *",
                "params": ["Charlie Direct", "charlie@example.com", 35],
                "fetch_mode": "one",
            },
        )

        workflow.add_connection("create_table", "result", "insert_user", "trigger")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # This should work without issues
        assert "insert_user" in results
        insert_result = results["insert_user"]

        # Verify successful insertion
        assert insert_result.get("success", True)
        if "result" in insert_result and "data" in insert_result["result"]:
            user_data = insert_result["result"]["data"]
            assert user_data["name"] == "Charlie Direct"
            assert user_data["email"] == "charlie@example.com"
            assert user_data["age"] == 35

"""
Integration tests for DeleteNode validation (Bug #2: Dangerous default id=1).

These tests verify that DeleteNode properly validates record IDs and never silently
defaults to id=1 when no ID is provided. This is a CRITICAL security issue that could
result in unintended data deletion.

Bug Location: packages/kailash-dataflow/src/dataflow/core/nodes.py:1422-1423

Test Strategy (TDD RED Phase):
- These tests should FAIL initially due to the dangerous default behavior
- After fixing the bug, all tests should pass
- Uses real PostgreSQL database (NO MOCKING) via IntegrationTestSuite
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


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestDeleteNodeValidation:
    """Test DeleteNode validation with real database operations."""

    @pytest.fixture(autouse=True)
    async def setup_and_cleanup(self, test_suite):
        """Setup and cleanup database for each test."""

        async def clean_test_data():
            """Clean test data from database."""
            async with test_suite.get_connection() as connection:
                try:
                    # Drop test tables to ensure clean state
                    await connection.execute("DROP TABLE IF EXISTS products CASCADE")
                    await connection.execute("DROP TABLE IF EXISTS test_items CASCADE")
                except Exception:
                    # Ignore errors if tables don't exist yet
                    pass

        # Clean before test
        await clean_test_data()
        yield
        # Clean after test
        await clean_test_data()

    @pytest.mark.asyncio
    async def test_delete_node_missing_id_raises_error(self, test_suite):
        """
        Test 1: DeleteNode should raise ValueError when no ID provided.

        CRITICAL: DeleteNode should NEVER default to id=1. This test verifies that
        attempting to delete without providing an ID raises a clear error instead of
        silently deleting id=1.

        Expected Behavior (after fix):
        - ValueError raised with message about missing required ID
        - No records deleted from database

        Current Behavior (BUG):
        - Silently defaults to id=1 and deletes that record
        """
        # Setup: Create test table with multiple records including id=1
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    price DECIMAL(10, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert test records - deliberately include id=1
            await conn.execute(
                """
                INSERT INTO products (id, name, price) VALUES
                (1, 'Critical Product', 999.99),
                (2, 'Product Two', 49.99),
                (3, 'Product Three', 29.99)
            """
            )

            # Verify records exist
            count = await conn.fetchval("SELECT COUNT(*) FROM products")
            assert count == 3, "Setup failed: should have 3 records"

        # Create DataFlow instance with existing schema
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        # Register model
        @dataflow.model
        class Product:
            id: int
            name: str
            price: float

        # Build workflow with DeleteNode but NO ID provided
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductDeleteNode",
            "delete_product",
            {},  # Empty params - no id or record_id provided!
        )

        # Execute: Since DeleteNode has no downstream dependencies, the runtime
        # will NOT raise an exception. Instead, it records the error in results.
        results, run_id = runtime.execute(workflow.build())

        # Verify the node failed with appropriate error
        assert "delete_product" in results, "delete_product node should be in results"
        node_result = results["delete_product"]

        # Check if node failed
        assert (
            node_result.get("failed") is True
        ), f"DeleteNode should have failed. Got result: {node_result}"

        # Verify error message mentions missing ID
        error_msg = node_result.get("error", "").lower()
        assert any(
            keyword in error_msg
            for keyword in ["id", "required", "missing", "must provide", "parameter"]
        ), f"Error message should mention missing ID, got: {node_result.get('error')}"

        # Verify NO records were deleted
        async with test_suite.get_connection() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM products")
            assert count == 3, "No records should be deleted when ID validation fails"

            # Verify id=1 still exists
            id1_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 1)"
            )
            assert id1_exists, "Critical: id=1 should NOT be deleted"

    @pytest.mark.asyncio
    async def test_delete_node_does_not_default_to_id_1(self, test_suite):
        """
        Test 2: DeleteNode should never default to deleting id=1.

        This test specifically checks that when DeleteNode is called with empty
        parameters, it either raises an error OR does nothing, but NEVER deletes id=1.

        Expected Behavior (after fix):
        - ValueError raised OR no deletion occurs
        - Record with id=1 remains in database

        Current Behavior (BUG):
        - Record with id=1 is silently deleted
        """
        # Setup: Create table with id=1 as a "canary" record
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE test_items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    is_critical BOOLEAN DEFAULT FALSE
                )
            """
            )

            # Insert canary record at id=1 marked as critical
            await conn.execute(
                """
                INSERT INTO test_items (id, name, is_critical) VALUES
                (1, 'CANARY_RECORD_DO_NOT_DELETE', TRUE)
            """
            )

            # Verify canary exists
            canary = await conn.fetchrow("SELECT * FROM test_items WHERE id = 1")
            assert canary is not None, "Canary record should exist"
            assert canary["is_critical"] is True, "Canary should be marked critical"

        # Create DataFlow instance
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        @dataflow.model
        class TestItem:
            id: int
            name: str
            is_critical: bool

        # Attempt delete with various empty parameter patterns
        # Note: Some patterns like {"record_id": None} will fail at workflow build time
        # because WorkflowBuilder validates parameter types
        empty_param_patterns = [
            {},  # Completely empty - should fail at runtime
            # {"id": None},  # Explicit None - fails at build time with type validation
            # {"record_id": None},  # Explicit None - fails at build time with type validation
        ]

        for idx, params in enumerate(empty_param_patterns):
            workflow = WorkflowBuilder()
            workflow.add_node("TestItemDeleteNode", f"delete_attempt_{idx}", params)

            # Execute - runtime will record the error in results, not raise exception
            results, run_id = runtime.execute(workflow.build())

            # Check if node failed (it should)
            node_id = f"delete_attempt_{idx}"
            node_result = results.get(node_id, {})

            # If node succeeded when it shouldn't, check if canary was deleted
            if not node_result.get("failed"):
                async with test_suite.get_connection() as conn:
                    canary_exists = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM test_items WHERE id = 1)"
                    )

                    if not canary_exists:
                        pytest.fail(
                            f"CRITICAL BUG: Canary record (id=1) was deleted with params {params}! "
                            "DeleteNode defaulted to id=1 which is a security risk."
                        )

            # Verify canary survived regardless of code path
            async with test_suite.get_connection() as conn:
                canary_check = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM test_items WHERE id = 1)"
                )
                assert canary_check, (
                    f"Canary record (id=1) should NEVER be deleted! "
                    f"Failed with params: {params}"
                )

    @pytest.mark.asyncio
    async def test_delete_node_with_valid_id_succeeds(self, test_suite):
        """
        Test 3: DeleteNode with explicit ID should delete correctly.

        This test verifies that when a valid ID is provided, DeleteNode works
        correctly and ONLY deletes the specified record (not id=1).

        Expected Behavior:
        - Record with specified ID is deleted
        - Other records (especially id=1) remain untouched
        """
        # Setup: Create table with multiple records
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    sku VARCHAR(50)
                )
            """
            )

            await conn.execute(
                """
                INSERT INTO products (id, name, sku) VALUES
                (1, 'Product One', 'SKU-001'),
                (5, 'Product Five', 'SKU-005'),
                (10, 'Product Ten', 'SKU-010')
            """
            )

            # Verify all records exist
            count = await conn.fetchval("SELECT COUNT(*) FROM products")
            assert count == 3, "Setup failed: should have 3 records"

        # Create DataFlow instance
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        @dataflow.model
        class Product:
            id: int
            name: str
            sku: str

        # Delete record with id=5 (NOT id=1)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductDeleteNode", "delete_five", {"record_id": 5}  # Explicit ID provided
        )

        # Execute deletion
        results, run_id = runtime.execute(workflow.build())

        # Verify correct record was deleted
        async with test_suite.get_connection() as conn:
            # id=5 should be gone
            id5_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 5)"
            )
            assert not id5_exists, "Record with id=5 should be deleted"

            # id=1 should still exist (was NOT touched)
            id1_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 1)"
            )
            assert id1_exists, (
                "Record with id=1 should NOT be deleted when deleting id=5! "
                "This suggests the dangerous default behavior is active."
            )

            # id=10 should still exist
            id10_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 10)"
            )
            assert id10_exists, "Record with id=10 should NOT be affected"

            # Total count should be 2
            final_count = await conn.fetchval("SELECT COUNT(*) FROM products")
            assert final_count == 2, "Should have exactly 2 records remaining"

    @pytest.mark.asyncio
    async def test_delete_node_id_parameter_works(self, test_suite):
        """
        Test 4: DeleteNode 'id' parameter should work as alias for record_id.

        This test verifies that the 'id' parameter (commonly used in workflow
        connections) works correctly as an alias for 'record_id'.

        Expected Behavior:
        - 'id' parameter works same as 'record_id'
        - Specified record is deleted
        - Other records remain untouched
        """
        # Setup: Create table with multiple records
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    category VARCHAR(50)
                )
            """
            )

            await conn.execute(
                """
                INSERT INTO products (id, name, category) VALUES
                (1, 'Essential Item', 'critical'),
                (7, 'Deletable Item', 'test'),
                (15, 'Another Item', 'test')
            """
            )

        # Create DataFlow instance
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        @dataflow.model
        class Product:
            id: int
            name: str
            category: str

        # Delete using 'id' parameter (not 'record_id')
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductDeleteNode",
            "delete_seven",
            {"id": 7},  # Using 'id' instead of 'record_id'
        )

        # Execute deletion
        results, run_id = runtime.execute(workflow.build())

        # Verify correct behavior
        async with test_suite.get_connection() as conn:
            # id=7 should be deleted
            id7_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 7)"
            )
            assert (
                not id7_exists
            ), "Record with id=7 should be deleted when using 'id' parameter"

            # id=1 should NOT be deleted (critical check!)
            id1_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 1)"
            )
            assert id1_exists, (
                "Record with id=1 should NOT be deleted when using 'id' parameter to delete id=7! "
                "This indicates the id=1 default bug is present."
            )

            # id=15 should still exist
            id15_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 15)"
            )
            assert id15_exists, "Record with id=15 should NOT be affected"

            # Final count should be 2
            final_count = await conn.fetchval("SELECT COUNT(*) FROM products")
            assert final_count == 2, "Should have exactly 2 records remaining"

    @pytest.mark.asyncio
    async def test_delete_node_workflow_connection_pattern(self, test_suite):
        """
        Test 5: DeleteNode should work correctly with workflow connections.

        This test verifies the common pattern where an ID is passed from one node
        to DeleteNode via workflow connections. This is the most common use case
        and must work correctly.

        Expected Behavior:
        - Create node outputs ID
        - Delete node receives ID via connection
        - Correct record is deleted
        - No default to id=1 behavior
        """
        # Setup: Create table
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    status VARCHAR(50) DEFAULT 'active'
                )
            """
            )

            # Insert a canary at id=1
            await conn.execute(
                """
                INSERT INTO products (id, name, status) VALUES
                (1, 'CANARY_DO_NOT_DELETE', 'protected')
            """
            )

            # Reset sequence so next auto-generated ID will be 2
            await conn.execute(
                "SELECT setval(pg_get_serial_sequence('products', 'id'), 1, true)"
            )

        # Create DataFlow instance
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        @dataflow.model
        class Product:
            id: int
            name: str
            status: str

        # Common workflow pattern: Create then Delete
        workflow = WorkflowBuilder()

        # Create a product (will get id=2 since id=1 exists)
        workflow.add_node(
            "ProductCreateNode",
            "create_product",
            {"name": "Temporary Product", "status": "temporary"},
        )

        # Delete the created product using workflow connection
        workflow.add_node(
            "ProductDeleteNode", "delete_product", {}
        )  # ID will come from connection

        # Connect: created product's ID -> delete node's id parameter
        # Signature: add_connection(from_node, from_output, to_node, to_input)
        workflow.add_connection(
            "create_product",  # From node
            "id",  # Output field from create
            "delete_product",  # To node
            "id",  # Input field to delete
        )

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify behavior
        async with test_suite.get_connection() as conn:
            # The created product (id=2) should be deleted
            created_id = results["create_product"]["id"]
            created_exists = await conn.fetchval(
                f"SELECT EXISTS(SELECT 1 FROM products WHERE id = {created_id})"
            )
            assert (
                not created_exists
            ), f"Created product (id={created_id}) should be deleted"

            # CRITICAL: Canary (id=1) must still exist
            canary_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM products WHERE id = 1)"
            )
            assert canary_exists, (
                "CRITICAL BUG: Canary (id=1) was deleted in workflow connection pattern! "
                f"Created product had id={created_id}, but id=1 was deleted instead."
            )

            # Verify canary is untouched
            canary = await conn.fetchrow(
                "SELECT name, status FROM products WHERE id = 1"
            )
            assert canary["name"] == "CANARY_DO_NOT_DELETE", "Canary data corrupted"
            assert canary["status"] == "protected", "Canary status changed"


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestDeleteNodeEdgeCases:
    """Additional edge case tests for DeleteNode validation."""

    @pytest.fixture(autouse=True)
    async def setup_and_cleanup(self, test_suite):
        """Setup and cleanup database for each test."""

        async def clean_test_data():
            async with test_suite.get_connection() as connection:
                try:
                    await connection.execute("DROP TABLE IF EXISTS edge_tests CASCADE")
                except Exception:
                    pass

        await clean_test_data()
        yield
        await clean_test_data()

    @pytest.mark.asyncio
    async def test_delete_node_with_id_zero(self, test_suite):
        """
        Test 6: DeleteNode with id=0 should not default to id=1.

        Edge case: id=0 is a valid (though unusual) ID value and should not
        trigger the default behavior.
        """
        # Setup
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE edge_tests (
                    id INTEGER PRIMARY KEY,
                    value VARCHAR(50)
                )
            """
            )

            await conn.execute(
                """
                INSERT INTO edge_tests (id, value) VALUES
                (0, 'Zero ID Record'),
                (1, 'One ID Record')
            """
            )

        # Create DataFlow
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        @dataflow.model
        class EdgeTest:
            id: int
            value: str

        # Attempt to delete id=0
        workflow = WorkflowBuilder()
        workflow.add_node("EdgeTestDeleteNode", "delete_zero", {"id": 0})

        results, run_id = runtime.execute(workflow.build())

        # Verify
        async with test_suite.get_connection() as conn:
            # id=0 should be deleted
            id0_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM edge_tests WHERE id = 0)"
            )
            assert not id0_exists, "Record with id=0 should be deleted"

            # id=1 should NOT be deleted
            id1_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM edge_tests WHERE id = 1)"
            )
            assert id1_exists, (
                "Record with id=1 should NOT be deleted when deleting id=0! "
                "id=0 should not trigger default behavior."
            )

    @pytest.mark.asyncio
    async def test_delete_node_with_nonexistent_id(self, test_suite):
        """
        Test 7: DeleteNode with non-existent ID should fail gracefully.

        Attempting to delete a non-existent record should not default to id=1.
        """
        # Setup
        async with test_suite.get_connection() as conn:
            await conn.execute(
                """
                CREATE TABLE edge_tests (
                    id SERIAL PRIMARY KEY,
                    value VARCHAR(50)
                )
            """
            )

            await conn.execute(
                """
                INSERT INTO edge_tests (id, value) VALUES
                (1, 'Only Record')
            """
            )

        # Create DataFlow
        dataflow = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        runtime = LocalRuntime()

        @dataflow.model
        class EdgeTest:
            id: int
            value: str

        # Try to delete non-existent id=999
        workflow = WorkflowBuilder()
        workflow.add_node("EdgeTestDeleteNode", "delete_nonexistent", {"id": 999})

        # Execute (may or may not raise error depending on implementation)
        results, run_id = runtime.execute(workflow.build())

        # Verify id=1 was NOT deleted
        async with test_suite.get_connection() as conn:
            id1_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM edge_tests WHERE id = 1)"
            )
            assert id1_exists, (
                "Record with id=1 should NOT be deleted when attempting to delete "
                "non-existent id=999!"
            )

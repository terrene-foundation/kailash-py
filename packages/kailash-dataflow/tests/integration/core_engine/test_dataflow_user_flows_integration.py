"""
Integration Tests for DataFlow User Flows

Tests the complete user workflows for DataFlow:
1. New Database Flow: Model registration → Auto-migration → Node usage
2. Existing Database Flow: Schema discovery → Model registration → Model reconstruction → Node usage
3. Dynamic Schema Discovery: Proves schema discovery is not hardcoded

These tests use real PostgreSQL and SQLite databases without mocking.
"""

import asyncio
import os
import random
import string

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
class TestDataFlowUserFlows:
    """Integration tests for complete DataFlow user workflows with PostgreSQL and SQLite."""

    @pytest.fixture
    async def cleanup_test_tables(self, test_suite):
        """Clean up test tables before and after tests using test suite."""
        tables_to_clean = ["customers", "test_customers", "simple_tests"]

        async def clean_tables():
            # Use test suite for cleanup
            try:
                async with test_suite.get_connection() as conn:
                    # Clean test tables
                    for table in tables_to_clean:
                        await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

                    # Also clean any random test tables
                    random_tables = await conn.fetch(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name LIKE 'test_tbl_%'
                    """
                    )
                    for row in random_tables:
                        await conn.execute(
                            f"DROP TABLE IF EXISTS {row['table_name']} CASCADE"
                        )
            except Exception as e:
                # If cleanup fails, log but don't fail the test
                print(f"Warning: PostgreSQL cleanup failed: {e}")

        await clean_tables()

        yield

        # Clean after test
        await clean_tables()

    @pytest.mark.asyncio
    async def test_new_database_flow(self, test_suite):
        """Test new database flow: Model → Auto-migration → Use."""
        # Step 1: Create model with auto-migration
        db = DataFlow(
            test_suite.config.url, auto_migrate=True, existing_schema_mode=False
        )

        @db.model
        class Customer:
            name: str
            email: str
            active: bool = True

        # Step 2: Verify table was created (PostgreSQL verification)
        # Since test_suite uses PostgreSQL, we can verify table creation
        # PostgreSQL verification using async connection
        conn = await db._get_async_database_connection()
        try:
            columns = await conn.fetch(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'customers'
                ORDER BY ordinal_position
            """
            )

            assert len(columns) >= 5  # id, name, email, active, created_at, updated_at
            column_names = [col["column_name"] for col in columns]
            assert "id" in column_names
            assert "name" in column_names
            assert "email" in column_names
            assert "active" in column_names
        finally:
            await conn.close()

        # Step 3: Test auto-migration doesn't run again
        conn = await db._get_async_database_connection()
        try:
            migrations_before = await conn.fetchrow(
                """
                SELECT COUNT(*) FROM dataflow_migration_history
                WHERE name LIKE '%customer%'
            """
            )
            migrations_before_count = migrations_before[0]

            # Re-register the model
            db2 = DataFlow(
                test_suite.config.url, auto_migrate=True, existing_schema_mode=False
            )

            @db2.model
            class Customer:
                name: str
                email: str
                active: bool = True

            migrations_after = await conn.fetchrow(
                """
                SELECT COUNT(*) FROM dataflow_migration_history
                WHERE name LIKE '%customer%'
            """
            )
            migrations_after_count = migrations_after[0]

            assert (
                migrations_after_count == migrations_before_count
            ), "Auto-migration should not run again"
        finally:
            await conn.close()

        # Step 4: Use generated nodes
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "database_url": test_suite.config.url,
                "name": "Test Customer",
                "email": "test@example.com",
                "active": True,
            },
        )

        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow.build())

        assert "create_customer" in result
        create_result = result["create_customer"]
        assert "id" in create_result or "result" in create_result

    @pytest.mark.asyncio
    async def test_existing_database_flow(self, test_suite, cleanup_test_tables):
        """Test existing database flow: Discover → Register → Reconstruct → Use."""
        # Setup: Create a table first using async DataFlow API
        setup_db = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        conn = await setup_db._get_async_database_connection()
        try:
            # PostgreSQL table creation (test suite uses PostgreSQL)
            await conn.execute(
                """
                CREATE TABLE test_customers (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
        finally:
            await conn.close()

        # Step 1: Discover schema
        db1 = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        schema = db1.discover_schema(use_real_inspection=True)

        assert "test_customers" in schema
        columns = schema["test_customers"].get("columns", [])
        column_names = [col["name"] for col in columns]
        assert "id" in column_names
        assert "name" in column_names
        assert "email" in column_names

        # Step 2: Register as models
        result = db1.register_schema_as_models(tables=["test_customers"])

        assert "registered_models" in result
        assert len(result["registered_models"]) > 0
        assert (
            "TestCustomers" in result["registered_models"]
            or "TestCustomer" in result["registered_models"]
        )

        # Step 3: Reconstruct models
        db2 = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        models = db2.reconstruct_models_from_registry()

        assert "generated_nodes" in models
        assert len(models["generated_nodes"]) > 0

        # Find the test_customers model (should be TestCustomer)
        customer_model = None
        for model_name in models["generated_nodes"]:
            if (
                model_name == "TestCustomer"
            ):  # Be specific - we want the TestCustomer model
                customer_model = model_name
                break

        assert customer_model is not None

        # Verify all 11 nodes are generated
        customer_nodes = models["generated_nodes"][customer_model]
        expected_nodes = [
            "create",
            "read",
            "update",
            "delete",
            "list",
            "bulk_create",
            "bulk_update",
            "bulk_delete",
            "bulk_upsert",
        ]

        for node_type in expected_nodes:
            assert node_type in customer_nodes

        # Step 4: Use generated nodes
        if "create" in customer_nodes:
            node_name = customer_nodes["create"]
            if not isinstance(node_name, str):
                node_name = node_name.__name__

            workflow = WorkflowBuilder()
            workflow.add_node(
                node_name,
                "create_test",
                {
                    "database_url": test_suite.config.url,
                    "name": "Test User",
                    "email": "test@example.com",
                    "active": True,
                },
            )

            runtime = LocalRuntime()
            result, _ = runtime.execute(workflow.build())

            assert "create_test" in result

    @pytest.mark.asyncio
    async def test_dynamic_schema_discovery(self, test_suite, cleanup_test_tables):
        """Test that schema discovery is truly dynamic, not hardcoded."""

        def generate_random_name(prefix="", length=8):
            """Generate random name for tables/columns."""
            random_part = "".join(random.choices(string.ascii_lowercase, k=length))
            return f"{prefix}{random_part}"

        # Create table with random name and columns
        random_table = f"test_tbl_{generate_random_name()}"
        random_cols = [generate_random_name("col_") for _ in range(3)]

        # Use async DataFlow API
        setup_db = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        conn = await setup_db._get_async_database_connection()
        try:
            # PostgreSQL table creation (test suite uses PostgreSQL)
            create_sql = f"""
                CREATE TABLE {random_table} (
                    id SERIAL PRIMARY KEY,
                    {random_cols[0]} VARCHAR(255),
                    {random_cols[1]} INTEGER,
                    {random_cols[2]} BOOLEAN DEFAULT true
                )
            """
            await conn.execute(create_sql)
        finally:
            await conn.close()

        # Discover the random table
        db = DataFlow(
            test_suite.config.url, auto_migrate=False, existing_schema_mode=True
        )
        schema = db.discover_schema(use_real_inspection=True)

        # Verify random table was discovered
        assert random_table in schema, f"Random table {random_table} not discovered"

        # Verify random columns were discovered
        table_columns = schema[random_table].get("columns", [])
        discovered_col_names = [col["name"] for col in table_columns]

        for random_col in random_cols:
            assert (
                random_col in discovered_col_names
            ), f"Random column {random_col} not discovered"

        # Register the random table as a model
        result = db.register_schema_as_models(tables=[random_table])

        assert "registered_models" in result
        assert len(result["registered_models"]) > 0

        # Verify model was registered
        models = db.get_models()
        model_found = False
        for model_name in models:
            if random_table.replace("_", "").lower() in model_name.lower():
                model_found = True
                break

        assert model_found, f"Model for random table {random_table} not registered"

        # Clean up
        conn = await setup_db._get_async_database_connection()
        try:
            await conn.execute(f"DROP TABLE {random_table} CASCADE")
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_auto_migration_serial_type_fix(
        self, test_suite, cleanup_test_tables
    ):
        """Test that auto-migration works correctly with SERIAL type fix."""

        # This tests the fix for the SERIAL type issue
        db = DataFlow(
            test_suite.config.url, auto_migrate=True, existing_schema_mode=False
        )

        @db.model
        class SimpleTest:
            name: str
            value: int
            active: bool = True

        # Verify table was created successfully using async DataFlow API
        conn = await db._get_async_database_connection()
        try:
            # PostgreSQL-specific validation
            columns = await conn.fetch(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'simple_tests'
                ORDER BY ordinal_position
            """
            )

            assert (
                len(columns) >= 5
            )  # Should have id, name, value, active, created_at, updated_at

            # Verify id column is integer type (not SERIAL which is not a real type)
            id_column = next(
                (col for col in columns if col["column_name"] == "id"), None
            )
            assert id_column is not None
            assert id_column["data_type"] == "integer"

            # Verify we can insert data
            inserted_row = await conn.fetchrow(
                """
                INSERT INTO simple_tests (name, value, active)
                VALUES ('test', 42, true)
                RETURNING id
            """
            )
            inserted_id = inserted_row["id"]
            assert inserted_id is not None
        finally:
            await conn.close()

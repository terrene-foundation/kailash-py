"""
End-to-end tests for BatchedMigrationExecutor with complete DataFlow workflows.

Tests complete user scenarios: DataFlow model changes → automatic migration with batching
→ real data operations using the full DataFlow stack.
"""

import asyncio
import time
from typing import Any, Dict, List

import pytest
from dataflow import DataFlow
from dataflow.migrations.auto_migration_system import AutoMigrationSystem
from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
class TestBatchedMigrationExecutorE2E:
    """End-to-end tests for BatchedMigrationExecutor with complete DataFlow workflows."""

    @pytest.fixture
    async def dataflow_instance(self, test_database_url):
        """Create DataFlow instance with PostgreSQL for E2E testing."""
        db = DataFlow(database_url=test_database_url)

        # Clean up any existing test tables
        async with db._get_connection() as conn:
            test_tables = [
                "e2e_users",
                "e2e_posts",
                "e2e_orders",
                "e2e_products",
                "e2e_categories",
                "e2e_inventory",
                "e2e_reviews",
            ]
            for table in test_tables:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                except:
                    pass

        yield db

        # Cleanup after test
        async with db._get_connection() as conn:
            for table in test_tables:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                except:
                    pass

    @pytest.mark.asyncio
    async def test_complete_ecommerce_schema_migration_with_batching(
        self, dataflow_instance
    ):
        """
        E2E test: Complete e-commerce schema creation with batched migrations.

        Tests the complete flow:
        1. Define complex DataFlow models
        2. Automatic migration generation with batching
        3. Efficient execution of batched DDL operations
        4. Verify data operations work correctly
        """
        db = dataflow_instance

        # Define comprehensive e-commerce models
        @db.model
        class E2EUser:
            """User model for e-commerce platform."""

            username: str
            email: str
            full_name: str
            is_active: bool = True
            created_at: str = "CURRENT_TIMESTAMP"

        @db.model
        class E2ECategory:
            """Product category model."""

            name: str
            description: str
            is_active: bool = True

        @db.model
        class E2EProduct:
            """Product model with category relationship."""

            name: str
            description: str
            price: float
            sku: str
            category_id: int
            stock_quantity: int = 0
            is_available: bool = True

        @db.model
        class E2EOrder:
            """Order model with user relationship."""

            user_id: int
            total_amount: float
            status: str = "pending"
            order_date: str = "CURRENT_TIMESTAMP"

        @db.model
        class E2EReview:
            """Review model with user and product relationships."""

            user_id: int
            product_id: int
            rating: int
            comment: str
            review_date: str = "CURRENT_TIMESTAMP"

        # Get the auto migration system
        auto_migration = db.auto_migration_system

        # Replace the standard executor with BatchedMigrationExecutor
        async with db._get_connection() as conn:
            batched_executor = BatchedMigrationExecutor(conn)

            # Get current and target schemas
            current_schema = await auto_migration.inspector.get_current_schema()
            target_schema = db._generate_target_schema()

            # Generate migration diff
            diff = auto_migration.inspector.compare_schemas(
                current_schema, target_schema
            )

            assert diff.has_changes()
            assert len(diff.tables_to_create) == 5  # All 5 models

            # Generate migration with operations
            migration = auto_migration.generator.generate_migration(
                diff, "e2e_ecommerce_schema"
            )

            # Test batched execution
            start_time = time.time()

            # Use our BatchedMigrationExecutor
            batches = batched_executor.batch_ddl_operations(migration.operations)
            result = await batched_executor.execute_batched_migrations(batches)

            execution_time = time.time() - start_time

            assert result
            assert execution_time < 10.0  # Must meet performance target
            print(f"E2E migration completed in {execution_time:.2f}s (target: <10s)")

            # Verify all tables were created correctly
            table_query = """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name LIKE 'e2e_%'
            ORDER BY table_name;
            """

            tables = await conn.fetch(table_query)
            table_names = [row["table_name"] for row in tables]

            expected_tables = [
                "e2e_users",
                "e2e_categories",
                "e2e_products",
                "e2e_orders",
                "e2e_reviews",
            ]
            for expected_table in expected_tables:
                assert expected_table in table_names

    @pytest.mark.asyncio
    async def test_dataflow_crud_operations_after_batched_migration(
        self, dataflow_instance
    ):
        """
        E2E test: Verify DataFlow CRUD operations work correctly after batched migration.
        """
        db = dataflow_instance

        # Define models
        @db.model
        class E2EUser:
            username: str
            email: str
            full_name: str

        @db.model
        class E2EPost:
            title: str
            content: str
            author_id: int
            published: bool = False

        # Perform migration with batching
        async with db._get_connection() as conn:
            auto_migration = db.auto_migration_system
            batched_executor = BatchedMigrationExecutor(conn)

            current_schema = await auto_migration.inspector.get_current_schema()
            target_schema = db._generate_target_schema()
            diff = auto_migration.inspector.compare_schemas(
                current_schema, target_schema
            )

            if diff.has_changes():
                migration = auto_migration.generator.generate_migration(
                    diff, "e2e_crud_test"
                )
                batches = batched_executor.batch_ddl_operations(migration.operations)
                result = await batched_executor.execute_batched_migrations(batches)
                assert result

        # Test CRUD operations using DataFlow-generated nodes
        workflow = WorkflowBuilder()
        runtime = LocalRuntime()

        # Test CREATE operation
        workflow.add_node(
            "E2EUserCreateNode",
            "create_user",
            {
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
            },
        )

        # Test READ operation (list all users)
        workflow.add_node("E2EUserListNode", "list_users", {})

        # Connect create to list to verify data persistence
        workflow.add_connection("create_user", "result", "list_users", "trigger")

        # Execute workflow
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        workflow_time = time.time() - start_time

        assert workflow_time < 5.0  # Fast execution after optimized migration

        # Verify CREATE worked
        assert "create_user" in results
        create_result = results["create_user"]
        assert create_result.get("success", True)

        # Verify READ worked
        assert "list_users" in results
        list_result = results["list_users"]
        assert list_result.get("success", True)

        # Verify data consistency
        if "result" in list_result and "data" in list_result["result"]:
            users = list_result["result"]["data"]
            assert len(users) >= 1  # At least our created user

            # Find our created user
            john_user = next((u for u in users if u["username"] == "john_doe"), None)
            assert john_user is not None
            assert john_user["email"] == "john@example.com"
            assert john_user["full_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_schema_evolution_with_batched_migrations(self, dataflow_instance):
        """
        E2E test: Schema evolution over time with batched migrations.

        Simulates real-world scenario where schema evolves incrementally.
        """
        db = dataflow_instance

        # Phase 1: Initial simple schema
        @db.model
        class E2EUser:
            username: str
            email: str

        # Apply initial migration
        await self._apply_batched_migration(db, "phase1_initial")

        # Verify initial tables exist
        async with db._get_connection() as conn:
            user_table_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'e2e_users')"
            )
            assert user_table_exists

        # Phase 2: Add more fields to existing model
        @db.model
        class E2EUser:
            username: str
            email: str
            full_name: str  # New field
            is_active: bool = True  # New field with default

        # Apply evolution migration
        start_time = time.time()
        await self._apply_batched_migration(db, "phase2_evolution")
        evolution_time = time.time() - start_time

        assert evolution_time < 5.0  # Fast schema evolution

        # Verify new columns exist
        async with db._get_connection() as conn:
            columns = await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'e2e_users'
                ORDER BY column_name;
            """
            )
            column_names = [row["column_name"] for row in columns]

            assert "username" in column_names
            assert "email" in column_names
            assert "full_name" in column_names
            assert "is_active" in column_names

        # Phase 3: Add completely new related model
        @db.model
        class E2EProfile:
            user_id: int
            bio: str
            avatar_url: str

        # Apply new model migration
        await self._apply_batched_migration(db, "phase3_new_model")

        # Verify new table exists
        async with db._get_connection() as conn:
            profile_table_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'e2e_profiles')"
            )
            assert profile_table_exists

    @pytest.mark.asyncio
    async def test_large_scale_migration_performance(self, dataflow_instance):
        """
        E2E test: Large-scale migration with many tables to test batching efficiency.
        """
        db = dataflow_instance

        # Define many models to test batching efficiency
        models = []
        for i in range(10):
            # Dynamically create model classes
            model_name = f"E2ETable{i}"

            @db.model
            class DynamicModel:
                name: str
                value: int
                description: str
                is_active: bool = True
                created_at: str = "CURRENT_TIMESTAMP"

            # Store reference to prevent garbage collection
            models.append(DynamicModel)
            # Change the table name
            DynamicModel.__name__ = model_name

        # Apply large migration with batching
        start_time = time.time()
        async with db._get_connection() as conn:
            batched_executor = BatchedMigrationExecutor(conn)
            auto_migration = db.auto_migration_system

            current_schema = await auto_migration.inspector.get_current_schema()
            target_schema = db._generate_target_schema()
            diff = auto_migration.inspector.compare_schemas(
                current_schema, target_schema
            )

            if diff.has_changes():
                migration = auto_migration.generator.generate_migration(
                    diff, "large_scale_test"
                )

                # Should efficiently batch many CREATE operations
                batches = batched_executor.batch_ddl_operations(migration.operations)
                print(f"Large migration batched into {len(batches)} batches")

                result = await batched_executor.execute_batched_migrations(batches)
                assert result

        total_time = time.time() - start_time

        # Even with 10 tables, should complete well under target
        assert total_time < 8.0  # Conservative target for large migration
        print(f"Large-scale migration ({10} tables) completed in {total_time:.2f}s")

        # Verify all tables were created
        async with db._get_connection() as conn:
            tables = await conn.fetch(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE 'e2e_table%'
                ORDER BY table_name;
            """
            )

            assert len(tables) == 10  # All tables created

    @pytest.mark.asyncio
    async def test_migration_rollback_compatibility(self, dataflow_instance):
        """
        E2E test: Verify rollback functionality works with batched migrations.
        """
        db = dataflow_instance

        # Define a simple model
        @db.model
        class E2EUser:
            username: str
            email: str
            test_field: str  # Field we'll remove in rollback test

        # Apply migration with BatchedMigrationExecutor
        async with db._get_connection() as conn:
            batched_executor = BatchedMigrationExecutor(conn)
            auto_migration = db.auto_migration_system

            current_schema = await auto_migration.inspector.get_current_schema()
            target_schema = db._generate_target_schema()
            diff = auto_migration.inspector.compare_schemas(
                current_schema, target_schema
            )

            if diff.has_changes():
                migration = auto_migration.generator.generate_migration(
                    diff, "rollback_test"
                )
                batches = batched_executor.batch_ddl_operations(migration.operations)
                result = await batched_executor.execute_batched_migrations(batches)
                assert result

                # Record the migration for rollback testing
                await auto_migration._record_migration(migration)

        # Verify table and columns exist
        async with db._get_connection() as conn:
            test_field_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'e2e_users' AND column_name = 'test_field'
                )
            """
            )
            assert test_field_exists

        # Test rollback (using standard AutoMigrationSystem rollback)
        rollback_success = await db.auto_migration_system.rollback_migration()
        assert rollback_success

        # Verify rollback worked (table should be gone)
        async with db._get_connection() as conn:
            table_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'e2e_users')"
            )
            # After rollback, table should not exist
            assert not table_exists

    async def _apply_batched_migration(self, db: DataFlow, migration_name: str) -> None:
        """Helper method to apply migration with BatchedMigrationExecutor."""
        async with db._get_connection() as conn:
            batched_executor = BatchedMigrationExecutor(conn)
            auto_migration = db.auto_migration_system

            current_schema = await auto_migration.inspector.get_current_schema()
            target_schema = db._generate_target_schema()
            diff = auto_migration.inspector.compare_schemas(
                current_schema, target_schema
            )

            if diff.has_changes():
                migration = auto_migration.generator.generate_migration(
                    diff, migration_name
                )
                batches = batched_executor.batch_ddl_operations(migration.operations)
                result = await batched_executor.execute_batched_migrations(batches)

                if not result:
                    raise Exception(f"Migration {migration_name} failed")

                # Record migration for tracking
                await auto_migration._record_migration(migration)

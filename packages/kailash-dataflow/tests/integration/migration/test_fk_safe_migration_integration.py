#!/usr/bin/env python3
"""
Integration Tests: FK-Safe Migration Operations - TODO-138 Phase 2

Tests FK-safe migration execution with real PostgreSQL on port 5434.
Validates complete referential integrity preservation and multi-table transaction coordination.

CRITICAL TEST SCENARIOS:
1. Primary Key Data Type Changes with FK Updates
2. FK Target Column Renaming with Constraint Recreation
3. FK Reference Chain Updates with Cascading Changes
4. Composite FK Management with Multi-column Operations

SAFETY VALIDATION:
- Zero Data Loss - All existing data relationships preserved
- Constraint Integrity - All FK constraints maintained or properly recreated
- Transaction Safety - Full rollback on any failure
- Cross-table ACID - Multi-table operations atomic
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, List
from unittest.mock import AsyncMock, Mock

import asyncpg
import asyncpg.exceptions
import pytest
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    ForeignKeyDependency,
)
from dataflow.migrations.fk_migration_operations import (
    CompositeFKOperation,
    FKChainUpdateOperation,
    FKMigrationOperations,
    FKOperationScenario,
    FKTargetRenameOperation,
    PKTypeChangeOperation,
)
from dataflow.migrations.fk_safe_migration_executor import (
    FKConstraintInfo,
    FKMigrationResult,
    FKMigrationStage,
    FKSafeMigrationExecutor,
    FKTransactionState,
)
from dataflow.migrations.foreign_key_analyzer import (
    FKImpactLevel,
    FKSafeMigrationPlan,
    ForeignKeyAnalyzer,
    MigrationStep,
)

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestFKSafeMigrationExecutor:
    """Test FK-Safe Migration Executor with real PostgreSQL."""

    @pytest.fixture
    async def postgres_connection(self, test_suite):
        """Create real PostgreSQL connection for testing."""
        conn = await asyncpg.connect(test_suite.config.url)

        # Setup test schema
        await conn.execute("DROP SCHEMA IF EXISTS test_fk_migration CASCADE")
        await conn.execute("CREATE SCHEMA test_fk_migration")
        await conn.execute("SET search_path TO test_fk_migration")

        # Create test tables with FK relationships
        await self._create_test_schema(conn)

        yield conn

        # Cleanup - handle aborted transactions
        try:
            await conn.execute("DROP SCHEMA IF EXISTS test_fk_migration CASCADE")
        except asyncpg.exceptions.InFailedSQLTransactionError:
            # Transaction was aborted, rollback and try again
            await conn.execute("ROLLBACK")
            await conn.execute("DROP SCHEMA IF EXISTS test_fk_migration CASCADE")
        await conn.close()

    async def _create_test_schema(self, conn: asyncpg.Connection):
        """Create test schema with FK relationships for testing."""
        # Parent table (PK will be modified)
        await conn.execute(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        """
        )

        # Child table with FK to customers
        await conn.execute(
            """
            CREATE TABLE orders (
                order_id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_date DATE DEFAULT CURRENT_DATE,
                total DECIMAL(10,2),
                CONSTRAINT fk_orders_customer
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
                    ON DELETE CASCADE ON UPDATE CASCADE
            )
        """
        )

        # Grandchild table with FK to orders
        await conn.execute(
            """
            CREATE TABLE order_items (
                item_id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_name VARCHAR(100),
                quantity INTEGER,
                price DECIMAL(10,2),
                CONSTRAINT fk_order_items_order
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                    ON DELETE CASCADE
            )
        """
        )

        # Add unique constraint on orders for composite FK BEFORE creating the composite FK table
        await conn.execute(
            """
            ALTER TABLE orders ADD CONSTRAINT unique_customer_order
            UNIQUE (customer_id, order_id)
        """
        )

        # Composite FK table
        await conn.execute(
            """
            CREATE TABLE order_tracking (
                tracking_id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_id INTEGER NOT NULL,
                status VARCHAR(50),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_tracking_composite
                    FOREIGN KEY (customer_id, order_id)
                    REFERENCES orders(customer_id, order_id)
                    MATCH FULL
            )
        """
        )

        # Insert test data
        await conn.execute(
            "INSERT INTO customers (customer_id, name, email) VALUES (1, 'Alice Smith', 'alice@example.com')"
        )
        await conn.execute(
            "INSERT INTO customers (customer_id, name, email) VALUES (2, 'Bob Jones', 'bob@example.com')"
        )

        await conn.execute(
            "INSERT INTO orders (order_id, customer_id, total) VALUES (101, 1, 250.00)"
        )
        await conn.execute(
            "INSERT INTO orders (order_id, customer_id, total) VALUES (102, 2, 180.00)"
        )

        await conn.execute(
            "INSERT INTO order_items (order_id, product_name, quantity, price) VALUES (101, 'Widget A', 2, 125.00)"
        )
        await conn.execute(
            "INSERT INTO order_items (order_id, product_name, quantity, price) VALUES (102, 'Widget B', 1, 180.00)"
        )

        await conn.execute(
            "INSERT INTO order_tracking (customer_id, order_id, status) VALUES (1, 101, 'shipped')"
        )
        await conn.execute(
            "INSERT INTO order_tracking (customer_id, order_id, status) VALUES (2, 102, 'processing')"
        )

    @pytest.fixture
    def connection_manager(self, postgres_connection):
        """Mock connection manager that returns real PostgreSQL connection."""
        manager = Mock()
        manager.get_connection = AsyncMock(return_value=postgres_connection)
        return manager

    @pytest.fixture
    def foreign_key_analyzer(self, connection_manager):
        """Create ForeignKeyAnalyzer with connection manager."""
        return ForeignKeyAnalyzer(connection_manager)

    @pytest.fixture
    def dependency_analyzer(self, connection_manager):
        """Create DependencyAnalyzer with connection manager."""
        analyzer = DependencyAnalyzer(connection_manager)

        # Mock the find_foreign_key_dependencies method to return test FK dependencies
        async def mock_find_fk_dependencies(table, column, connection):
            # Return mock FK dependencies for test scenario
            if table == "customers" and column == "customer_id":
                return [
                    ForeignKeyDependency(
                        constraint_name="fk_orders_customer",
                        source_table="orders",
                        source_column="customer_id",
                        target_table="customers",
                        target_column="customer_id",
                        on_delete="CASCADE",
                        on_update="CASCADE",
                    )
                ]
            elif table == "orders" and column == "order_id":
                return [
                    ForeignKeyDependency(
                        constraint_name="fk_order_items_order",
                        source_table="order_items",
                        source_column="order_id",
                        target_table="orders",
                        target_column="order_id",
                        on_delete="CASCADE",
                        on_update="RESTRICT",
                    )
                ]
            return []

        analyzer.find_foreign_key_dependencies = mock_find_fk_dependencies
        return analyzer

    @pytest.fixture
    def fk_executor(
        self, connection_manager, foreign_key_analyzer, dependency_analyzer
    ):
        """Create FKSafeMigrationExecutor with dependencies."""
        return FKSafeMigrationExecutor(
            connection_manager=connection_manager,
            foreign_key_analyzer=foreign_key_analyzer,
            dependency_analyzer=dependency_analyzer,
        )

    @pytest.fixture
    def fk_operations(self, fk_executor, foreign_key_analyzer, dependency_analyzer):
        """Create FKMigrationOperations with dependencies."""
        return FKMigrationOperations(
            executor=fk_executor,
            foreign_key_analyzer=foreign_key_analyzer,
            dependency_analyzer=dependency_analyzer,
        )

    @pytest.mark.asyncio
    async def test_fk_constraint_disable_enable_cycle(
        self, fk_executor, postgres_connection
    ):
        """Test that FK constraints can be safely disabled and re-enabled."""
        # Create a simple migration plan with FK constraint handling
        plan = FKSafeMigrationPlan(
            operation_id="test_constraint_cycle",
            steps=[
                MigrationStep(
                    step_type="drop_constraint",
                    description="Drop FK constraint for testing",
                    sql_command="ALTER TABLE orders DROP CONSTRAINT fk_orders_customer",
                    rollback_command="-- Restore FK constraint",
                ),
                MigrationStep(
                    step_type="add_constraint",
                    description="Restore FK constraint",
                    sql_command="ALTER TABLE orders ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE ON UPDATE CASCADE",
                ),
            ],
        )

        # Execute the migration
        result = await fk_executor.execute_fk_aware_column_modification(
            plan, postgres_connection
        )

        # Verify successful execution
        assert result.success
        assert FKMigrationStage.FK_CONSTRAINT_DISABLE in result.stage_results
        assert FKMigrationStage.FK_CONSTRAINT_RESTORE in result.stage_results
        assert result.stage_results[FKMigrationStage.FK_CONSTRAINT_DISABLE]
        assert result.stage_results[FKMigrationStage.FK_CONSTRAINT_RESTORE]

        # Verify FK constraint is working after restoration
        await postgres_connection.execute("SET search_path TO test_fk_migration")

        # This should fail due to FK constraint
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await postgres_connection.execute(
                "INSERT INTO orders (customer_id, total) VALUES (999, 100.00)"
            )

    @pytest.mark.asyncio
    async def test_multi_table_transaction_coordination(
        self, fk_executor, postgres_connection
    ):
        """Test multi-table transaction coordination with ACID compliance."""
        tables = ["customers", "orders", "order_items"]
        changes = {
            "customers": {
                "type": "column_add",
                "column": "updated_at",
                "data_type": "TIMESTAMP",
            },
            "orders": {
                "type": "column_add",
                "column": "updated_at",
                "data_type": "TIMESTAMP",
            },
            "order_items": {
                "type": "column_add",
                "column": "updated_at",
                "data_type": "TIMESTAMP",
            },
        }

        # Execute coordinated changes
        result = await fk_executor.coordinate_multi_table_changes(
            tables, changes, postgres_connection
        )

        # Verify successful coordination
        assert result.success
        assert len(result.tables_modified) == 3
        assert "customers" in result.tables_modified
        assert "orders" in result.tables_modified
        assert "order_items" in result.tables_modified

        # Verify savepoints were created
        assert len(result.transaction_savepoints) == 3

    @pytest.mark.asyncio
    async def test_referential_integrity_preservation(
        self, fk_executor, postgres_connection
    ):
        """Test that referential integrity is preserved during migrations."""
        # Create a mock operation that would affect FK relationships
        operation = Mock()
        operation.table = "customers"
        operation.column = "customer_id"
        operation.operation_type = "modify_column_type"

        # Test integrity preservation check
        result = await fk_executor.ensure_referential_integrity_preservation(
            operation, postgres_connection
        )

        # Should preserve integrity for a safe operation
        assert result.integrity_preserved
        assert not result.data_loss_detected
        assert len(result.orphaned_records) == 0

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self, fk_executor, postgres_connection):
        """Test that rollback properly restores FK constraints on failure."""
        # Create a plan that will fail during schema modification
        plan = FKSafeMigrationPlan(
            operation_id="test_rollback",
            steps=[
                MigrationStep(
                    step_type="drop_constraint",
                    description="Drop FK constraint",
                    sql_command="ALTER TABLE orders DROP CONSTRAINT fk_orders_customer",
                ),
                MigrationStep(
                    step_type="modify_column",
                    description="Invalid column modification that will fail",
                    sql_command="ALTER TABLE customers ALTER COLUMN customer_id TYPE VARCHAR(50) USING customer_id::VARCHAR",  # This will fail due to FK references
                ),
            ],
        )

        # Execute and expect failure
        result = await fk_executor.execute_fk_aware_column_modification(
            plan, postgres_connection
        )

        # Verify rollback was performed
        assert not result.success
        assert len(result.errors) > 0

        # Verify FK constraint still exists after rollback
        await postgres_connection.execute("SET search_path TO test_fk_migration")

        # FK constraint should still be enforced
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await postgres_connection.execute(
                "INSERT INTO orders (customer_id, total) VALUES (999, 100.00)"
            )


@pytest.mark.integration
@pytest.mark.requires_postgres
class TestFKMigrationOperations:
    """Test specialized FK migration operations with real PostgreSQL."""

    @pytest.fixture
    async def postgres_connection(self, test_suite):
        """Create real PostgreSQL connection for testing."""
        conn = await asyncpg.connect(test_suite.config.url)

        # Setup test schema
        await conn.execute("DROP SCHEMA IF EXISTS test_fk_ops CASCADE")
        await conn.execute("CREATE SCHEMA test_fk_ops")
        await conn.execute("SET search_path TO test_fk_ops")

        # Create test schema for operations
        await self._create_operations_test_schema(conn)

        yield conn

        # Cleanup
        await conn.execute("DROP SCHEMA IF EXISTS test_fk_ops CASCADE")
        await conn.close()

    async def _create_operations_test_schema(self, conn: asyncpg.Connection):
        """Create test schema for FK operations testing."""
        # Base tables for PK type change testing
        await conn.execute(
            """
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                name VARCHAR(100),
                price DECIMAL(10,2)
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE product_reviews (
                review_id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                rating INTEGER,
                comment TEXT,
                CONSTRAINT fk_reviews_product
                    FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """
        )

        # Tables for column rename testing
        await conn.execute(
            """
            CREATE TABLE categories (
                cat_id INTEGER PRIMARY KEY,
                category_name VARCHAR(50)
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE product_categories (
                id SERIAL PRIMARY KEY,
                product_id INTEGER,
                cat_id INTEGER NOT NULL,
                CONSTRAINT fk_product_cat_category
                    FOREIGN KEY (cat_id) REFERENCES categories(cat_id)
            )
        """
        )

        # Insert test data
        await conn.execute(
            "INSERT INTO products VALUES (1, 'Laptop', 999.99), (2, 'Mouse', 29.99)"
        )
        await conn.execute(
            "INSERT INTO product_reviews VALUES (1, 1, 5, 'Great laptop'), (2, 2, 4, 'Good mouse')"
        )
        await conn.execute(
            "INSERT INTO categories VALUES (1, 'Electronics'), (2, 'Accessories')"
        )
        await conn.execute("INSERT INTO product_categories VALUES (1, 1, 1), (2, 2, 2)")

    @pytest.fixture
    def connection_manager(self, postgres_connection):
        """Mock connection manager that returns real PostgreSQL connection."""
        manager = Mock()
        manager.get_connection = AsyncMock(return_value=postgres_connection)
        return manager

    @pytest.fixture
    def fk_operations(self, connection_manager):
        """Create FKMigrationOperations with mocked dependencies."""
        # Create dependency analyzer with mocked FK finding
        dependency_analyzer = DependencyAnalyzer(connection_manager)

        async def mock_find_fk_dependencies(table, column, connection):
            # Mock FK dependencies for operations tests
            if table == "products" and column == "product_id":
                return [
                    ForeignKeyDependency(
                        constraint_name="fk_reviews_product",
                        source_table="product_reviews",
                        source_column="product_id",
                        target_table="products",
                        target_column="product_id",
                        on_delete="RESTRICT",
                        on_update="RESTRICT",
                    )
                ]
            elif table == "categories" and column == "cat_id":
                return [
                    ForeignKeyDependency(
                        constraint_name="fk_product_cat_category",
                        source_table="product_categories",
                        source_column="cat_id",
                        target_table="categories",
                        target_column="cat_id",
                        on_delete="RESTRICT",
                        on_update="RESTRICT",
                    )
                ]
            return []

        dependency_analyzer.find_foreign_key_dependencies = mock_find_fk_dependencies

        fk_executor = FKSafeMigrationExecutor(
            connection_manager, dependency_analyzer=dependency_analyzer
        )
        foreign_key_analyzer = ForeignKeyAnalyzer(
            connection_manager, dependency_analyzer=dependency_analyzer
        )

        return FKMigrationOperations(
            executor=fk_executor,
            foreign_key_analyzer=foreign_key_analyzer,
            dependency_analyzer=dependency_analyzer,
        )

    @pytest.mark.asyncio
    async def test_primary_key_type_change_operation(
        self, fk_operations, postgres_connection
    ):
        """Test PK type change with FK reference updates."""
        await postgres_connection.execute("SET search_path TO test_fk_ops")

        # Create PK type change operation
        operation = PKTypeChangeOperation(
            table="products", column="product_id", old_type="INTEGER", new_type="BIGINT"
        )

        # Execute the operation
        result = await fk_operations.execute_primary_key_type_change(
            operation, postgres_connection
        )

        # Verify successful execution
        assert result.success
        assert result.rows_affected > 0

        # Verify data is preserved
        rows = await postgres_connection.fetch("SELECT * FROM products")
        assert len(rows) == 2

        # Verify FK relationships still work
        reviews = await postgres_connection.fetch(
            """
            SELECT r.*, p.name
            FROM product_reviews r
            JOIN products p ON r.product_id = p.product_id
        """
        )
        assert len(reviews) == 2

    @pytest.mark.asyncio
    async def test_fk_target_column_rename_operation(
        self, fk_operations, postgres_connection
    ):
        """Test FK target column rename with constraint recreation."""
        await postgres_connection.execute("SET search_path TO test_fk_ops")

        # Create FK target rename operation
        operation = FKTargetRenameOperation(
            table="categories", old_column_name="cat_id", new_column_name="category_id"
        )

        # Execute the operation
        result = await fk_operations.execute_fk_target_column_rename(
            operation, postgres_connection
        )

        # Verify successful execution
        assert result.success
        assert result.constraints_disabled > 0
        assert result.constraints_restored > 0

        # Verify column was renamed
        columns = await postgres_connection.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'categories'
            AND table_schema = 'test_fk_ops'
        """
        )
        column_names = [row["column_name"] for row in columns]
        assert "category_id" in column_names
        assert "cat_id" not in column_names

        # Verify FK relationships still work with new column name
        categories = await postgres_connection.fetch(
            """
            SELECT c.category_id, c.category_name, COUNT(pc.id) as product_count
            FROM categories c
            LEFT JOIN product_categories pc ON c.category_id = pc.cat_id
            GROUP BY c.category_id, c.category_name
        """
        )
        assert len(categories) == 2

    @pytest.mark.asyncio
    async def test_composite_fk_management_operation(
        self, fk_operations, postgres_connection
    ):
        """Test composite FK management operations."""
        await postgres_connection.execute("SET search_path TO test_fk_ops")

        # First add the unique constraint to support composite FK
        await postgres_connection.execute(
            """
            ALTER TABLE product_reviews
            ADD CONSTRAINT unique_product_review UNIQUE (product_id, review_id)
        """
        )

        # Now create the composite FK table
        await postgres_connection.execute(
            """
            CREATE TABLE order_summary (
                summary_id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                review_id INTEGER NOT NULL,
                summary_text TEXT,
                CONSTRAINT fk_summary_composite
                    FOREIGN KEY (product_id, review_id)
                    REFERENCES product_reviews(product_id, review_id)
            )
        """
        )

        # Insert test data
        await postgres_connection.execute(
            """
            INSERT INTO order_summary (product_id, review_id, summary_text)
            VALUES (1, 1, 'Excellent laptop review')
        """
        )

        # Create composite FK operation to modify constraint
        operation = CompositeFKOperation(
            source_table="order_summary",
            target_table="product_reviews",
            source_columns=["product_id", "review_id"],
            target_columns=["product_id", "review_id"],
            constraint_name="fk_summary_composite",
            operation_type="modify",
        )

        # Execute the operation
        result = await fk_operations.execute_composite_fk_management(
            operation, postgres_connection
        )

        # Verify successful execution
        assert result.success
        assert result.constraints_disabled == 1
        assert result.constraints_restored == 1

        # Verify composite FK constraint still works
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await postgres_connection.execute(
                """
                INSERT INTO order_summary (product_id, review_id, summary_text)
                VALUES (999, 999, 'Invalid reference')
            """
            )

    @pytest.mark.asyncio
    async def test_transaction_safety_across_operations(
        self, fk_operations, postgres_connection
    ):
        """Test that all operations maintain transaction safety."""
        await postgres_connection.execute("SET search_path TO test_fk_ops")

        # Start a transaction
        await postgres_connection.execute("BEGIN")

        # Create an operation that should succeed within transaction
        operation = FKTargetRenameOperation(
            table="categories", old_column_name="category_name", new_column_name="name"
        )

        # Execute within transaction
        result = await fk_operations.execute_fk_target_column_rename(
            operation, postgres_connection
        )

        # Rollback the transaction
        await postgres_connection.execute("ROLLBACK")

        # Verify original state is preserved after rollback
        columns = await postgres_connection.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'categories'
            AND table_schema = 'test_fk_ops'
        """
        )
        column_names = [row["column_name"] for row in columns]
        assert "category_name" in column_names  # Original name preserved
        assert "name" not in column_names  # New name not present

    @pytest.mark.asyncio
    async def test_data_preservation_during_complex_operations(
        self, fk_operations, postgres_connection
    ):
        """Test that all data is preserved during complex FK operations."""
        await postgres_connection.execute("SET search_path TO test_fk_ops")

        # Count original data
        original_products = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM products"
        )
        original_reviews = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM product_reviews"
        )
        original_categories = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM categories"
        )
        original_product_cats = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM product_categories"
        )

        # Execute a series of FK operations
        operations = [
            PKTypeChangeOperation(
                table="products",
                column="product_id",
                old_type="INTEGER",
                new_type="BIGINT",
            ),
            FKTargetRenameOperation(
                table="categories",
                old_column_name="cat_id",
                new_column_name="category_id",
            ),
        ]

        # Execute all operations
        for operation in operations:
            if isinstance(operation, PKTypeChangeOperation):
                result = await fk_operations.execute_primary_key_type_change(
                    operation, postgres_connection
                )
            else:
                result = await fk_operations.execute_fk_target_column_rename(
                    operation, postgres_connection
                )

            # Each operation should succeed
            assert result.success

        # Verify all data is preserved
        final_products = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM products"
        )
        final_reviews = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM product_reviews"
        )
        final_categories = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM categories"
        )
        final_product_cats = await postgres_connection.fetchval(
            "SELECT COUNT(*) FROM product_categories"
        )

        assert final_products == original_products
        assert final_reviews == original_reviews
        assert final_categories == original_categories
        assert final_product_cats == original_product_cats

        # Verify referential integrity is maintained
        # Note: After FK target column rename, categories.cat_id becomes categories.category_id
        join_results = await postgres_connection.fetch(
            """
            SELECT p.product_id, p.name, r.rating, c.category_name, pc.id
            FROM products p
            LEFT JOIN product_reviews r ON p.product_id = r.product_id
            LEFT JOIN product_categories pc ON p.product_id = pc.product_id
            LEFT JOIN categories c ON pc.cat_id = c.category_id
        """
        )

        # Should have meaningful join results proving FK relationships work
        assert len(join_results) > 0

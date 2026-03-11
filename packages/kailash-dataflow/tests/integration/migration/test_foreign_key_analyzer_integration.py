#!/usr/bin/env python3
"""
Tier 2 Integration Tests for Foreign Key Analysis Engine - TODO-138 Phase 1

Tests the ForeignKeyAnalyzer class with REAL PostgreSQL infrastructure on port 5433.
NO MOCKING - All tests use actual database connections and real FK relationships.

Following Tier 2 testing guidelines:
- Uses REAL PostgreSQL database on port 5433
- NO MOCKING of database connections or operations
- Fast execution (<5 seconds per test)
- Tests actual component interactions with real infrastructure
- CRITICAL PRIORITY: FK target analysis and referential integrity validation
"""

import asyncio
from typing import Any, Dict, List

import asyncpg
import pytest
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    ForeignKeyDependency,
    ImpactLevel,
)
from dataflow.migrations.foreign_key_analyzer import (
    FKChain,
    FKImpactLevel,
    FKImpactReport,
    FKOperationType,
    FKSafeMigrationPlan,
    ForeignKeyAnalyzer,
    IntegrityValidation,
)
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.mark.integration
class TestForeignKeyAnalyzerIntegration:
    """Tier 2 Integration Tests for ForeignKeyAnalyzer with REAL PostgreSQL."""

    @pytest.fixture
    async def test_suite(self):
        """Create complete integration test suite with infrastructure."""
        suite = IntegrationTestSuite()
        async with suite.session():
            yield suite

    @pytest.fixture
    async def real_connection(self, test_suite):
        """Create REAL PostgreSQL connection using test suite."""
        connection = await test_suite.infrastructure.get_connection()

        # Clean up any existing test tables
        await self._cleanup_test_tables(connection)

        yield connection

        # Clean up after test
        await self._cleanup_test_tables(connection)

        # Return connection to pool
        await test_suite.infrastructure._pool.release(connection)

    async def _cleanup_test_tables(self, connection: asyncpg.Connection):
        """Clean up test tables and foreign keys."""
        test_tables = [
            "fk_test_orders",
            "fk_test_users",
            "fk_test_categories",
            "fk_test_products",
            "fk_test_isolated",
            "fk_test_parent",
            "fk_test_child",
            "fk_test_source",
            "fk_test_target",
            "fk_test_account",
            "fk_test_transaction",
            "fk_test_hub",
            "fk_test_category_groups",
            "fk_test_department",
            "fk_test_employee",
        ]

        # Add dynamically created spoke tables
        for i in range(20):  # Cleanup spoke tables from performance test
            test_tables.append(f"fk_test_spoke_{i}")

        for table in test_tables:
            try:
                await connection.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            except Exception:
                pass  # Ignore errors during cleanup

    @pytest.fixture
    async def connection_manager(self, test_suite):
        """Create REAL connection manager using test suite."""
        # Create a simple DataFlow instance for the connection manager
        dataflow_instance = test_suite.dataflow_harness.create_dataflow(
            auto_migrate=False
        )
        manager = MigrationConnectionManager(dataflow_instance)
        yield manager
        # No close method needed for MigrationConnectionManager

    @pytest.fixture
    async def fk_analyzer(self, connection_manager):
        """Create FK analyzer with real infrastructure."""
        dependency_analyzer = DependencyAnalyzer(connection_manager)
        return ForeignKeyAnalyzer(connection_manager, dependency_analyzer)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_analyze_fk_impact_real_primary_key_modification(
        self, fk_analyzer, real_connection
    ):
        """CRITICAL TEST: Analyze FK impact on real primary key column modification."""
        # Set up REAL FK relationship: orders -> users
        await real_connection.execute(
            """
            CREATE TABLE fk_test_users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES fk_test_users(id) ON DELETE CASCADE,
                amount DECIMAL(10,2)
            )
        """
        )

        # Insert real test data
        await real_connection.execute(
            "INSERT INTO fk_test_users (email) VALUES ('test@example.com')"
        )
        await real_connection.execute(
            "INSERT INTO fk_test_orders (user_id, amount) VALUES (1, 100.00)"
        )

        # Analyze FK impact on primary key column
        result = await fk_analyzer.analyze_foreign_key_impact(
            table="fk_test_users",
            operation="modify_column_type",
            connection=real_connection,
        )

        assert isinstance(result, FKImpactReport)
        assert result.table_name == "fk_test_users"
        assert result.operation_type == "modify_column_type"
        assert result.impact_level in [FKImpactLevel.CRITICAL, FKImpactLevel.HIGH]
        assert len(result.affected_foreign_keys) >= 1
        assert result.cascade_risk_detected is True  # ON DELETE CASCADE detected

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_analyze_fk_impact_no_references_real(
        self, fk_analyzer, real_connection
    ):
        """Test FK impact analysis on isolated table with no FK references."""
        # Create isolated table with no FK relationships
        await real_connection.execute(
            """
            CREATE TABLE fk_test_isolated (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Analyze FK impact - should find no references
        result = await fk_analyzer.analyze_foreign_key_impact(
            table="fk_test_isolated",
            operation="drop_column",
            connection=real_connection,
        )

        assert result.impact_level == FKImpactLevel.SAFE
        assert len(result.affected_foreign_keys) == 0
        assert result.cascade_risk_detected is False
        assert result.requires_coordination is False

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_find_fk_chains_real_multi_level(self, fk_analyzer, real_connection):
        """Test detection of real multi-level FK dependency chains."""
        # Set up REAL chain: products -> categories -> category_groups
        await real_connection.execute(
            """
            CREATE TABLE fk_test_category_groups (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                group_id INTEGER REFERENCES fk_test_category_groups(id) ON DELETE RESTRICT
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                category_id INTEGER REFERENCES fk_test_categories(id) ON DELETE CASCADE
            )
        """
        )

        # Insert real test data to validate relationships
        await real_connection.execute(
            "INSERT INTO fk_test_category_groups (name) VALUES ('Electronics')"
        )
        await real_connection.execute(
            "INSERT INTO fk_test_categories (name, group_id) VALUES ('Laptops', 1)"
        )
        await real_connection.execute(
            "INSERT INTO fk_test_products (name, category_id) VALUES ('MacBook', 1)"
        )

        # Find FK chains starting from category_groups
        chains = await fk_analyzer.find_all_foreign_key_chains(
            table="fk_test_category_groups", connection=real_connection
        )

        assert len(chains) >= 1
        chain = chains[0]
        assert isinstance(chain, FKChain)
        assert chain.root_table == "fk_test_category_groups"
        assert len(chain.nodes) >= 1  # Should find at least categories referencing it
        assert chain.contains_cycles is False

        # Verify chain includes the expected FK relationships
        table_names_in_chain = {node.table_name for node in chain.nodes}
        assert "fk_test_categories" in table_names_in_chain

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_validate_referential_integrity_real_dangerous_operation(
        self, fk_analyzer, real_connection
    ):
        """CRITICAL TEST: Validate referential integrity with real FK constraints."""
        # Set up REAL FK relationship
        await real_connection.execute(
            """
            CREATE TABLE fk_test_parent (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_child (
                id SERIAL PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES fk_test_parent(id) ON DELETE RESTRICT,
                data TEXT
            )
        """
        )

        # Insert real test data
        await real_connection.execute(
            "INSERT INTO fk_test_parent (name) VALUES ('Test Parent')"
        )
        await real_connection.execute(
            "INSERT INTO fk_test_child (parent_id, data) VALUES (1, 'Test Data')"
        )

        # Mock operation that would violate referential integrity
        class MockOperation:
            def __init__(self):
                self.table = "fk_test_parent"
                self.column = "id"  # Primary key referenced by child
                self.operation_type = "drop_column"

        mock_operation = MockOperation()

        # Validate referential integrity
        result = await fk_analyzer.validate_referential_integrity(
            mock_operation, connection=real_connection
        )

        assert isinstance(result, IntegrityValidation)
        assert result.is_safe is False  # Operation would break referential integrity
        assert len(result.violations) >= 1
        assert len(result.recommended_actions) >= 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_validate_referential_integrity_real_safe_operation(
        self, fk_analyzer, real_connection
    ):
        """Test referential integrity validation for safe operations on real database."""
        # Create table without FK references
        await real_connection.execute(
            """
            CREATE TABLE fk_test_standalone (
                id SERIAL PRIMARY KEY,
                description TEXT,
                metadata JSONB
            )
        """
        )

        # Mock safe operation (adding index)
        class MockSafeOperation:
            def __init__(self):
                self.table = "fk_test_standalone"
                self.column = "description"
                self.operation_type = "add_index"

        mock_operation = MockSafeOperation()

        # Validate referential integrity
        result = await fk_analyzer.validate_referential_integrity(
            mock_operation, connection=real_connection
        )

        assert result.is_safe is True
        assert len(result.violations) == 0
        assert len(result.warnings) == 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_generate_fk_safe_migration_plan_real_database(
        self, fk_analyzer, real_connection
    ):
        """Test FK-safe migration plan generation with real database constraints."""
        # Set up REAL FK relationship
        await real_connection.execute(
            """
            CREATE TABLE fk_test_source (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_target (
                id SERIAL PRIMARY KEY,
                source_code VARCHAR(50) REFERENCES fk_test_source(code) ON UPDATE CASCADE,
                value INTEGER
            )
        """
        )

        # Mock operation to modify referenced column
        class MockModifyOperation:
            def __init__(self):
                self.table = "fk_test_source"
                self.column = "code"
                self.operation_type = "modify_column_type"
                self.new_type = "VARCHAR(100)"

        mock_operation = MockModifyOperation()

        # Generate FK-safe migration plan
        plan = await fk_analyzer.generate_fk_safe_migration_plan(
            mock_operation, connection=real_connection
        )

        assert isinstance(plan, FKSafeMigrationPlan)
        assert (
            len(plan.steps) >= 3
        )  # Should include: drop FK, modify column, recreate FK
        assert plan.requires_transaction is True
        assert plan.estimated_duration > 0
        assert plan.risk_level in [FKImpactLevel.HIGH, FKImpactLevel.MEDIUM]

        # Verify step types include FK constraint handling
        step_types = [step.step_type for step in plan.steps]
        assert "drop_constraint" in step_types or "modify_column" in step_types

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_cascade_risk_detection_real_database(
        self, fk_analyzer, real_connection
    ):
        """HIGH PRIORITY TEST: Detect CASCADE risk in real database scenario."""
        # Set up REAL CASCADE FK relationship - HIGH RISK
        await real_connection.execute(
            """
            CREATE TABLE fk_test_account (
                id SERIAL PRIMARY KEY,
                account_number VARCHAR(20) UNIQUE NOT NULL
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_transaction (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES fk_test_account(id) ON DELETE CASCADE,
                amount DECIMAL(15,2),
                transaction_date TIMESTAMP DEFAULT NOW()
            )
        """
        )

        # Insert critical business data
        await real_connection.execute(
            "INSERT INTO fk_test_account (account_number) VALUES ('ACC-001')"
        )
        await real_connection.execute(
            "INSERT INTO fk_test_transaction (account_id, amount) VALUES (1, 1000.00)"
        )

        # Analyze cascade risk for account deletion
        result = await fk_analyzer.analyze_foreign_key_impact(
            table="fk_test_account", operation="drop_column", connection=real_connection
        )

        assert result.cascade_risk_detected is True
        assert result.impact_level == FKImpactLevel.CRITICAL
        assert len(result.affected_foreign_keys) >= 1

        # Verify CASCADE constraint is detected
        cascade_fks = [
            fk for fk in result.affected_foreign_keys if fk.on_delete == "CASCADE"
        ]
        assert len(cascade_fks) >= 1

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_performance_with_real_large_fk_schema(
        self, fk_analyzer, real_connection
    ):
        """Test performance with realistic FK schema size."""
        # Create a moderately complex FK schema (50 relationships)
        await real_connection.execute(
            """
            CREATE TABLE fk_test_hub (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL
            )
        """
        )

        # Create multiple tables referencing the hub
        for i in range(10):
            await real_connection.execute(
                f"""
                CREATE TABLE fk_test_spoke_{i} (
                    id SERIAL PRIMARY KEY,
                    hub_id INTEGER REFERENCES fk_test_hub(id) ON DELETE RESTRICT,
                    data_{i} TEXT
                )
            """
            )

        # Insert some test data
        await real_connection.execute(
            "INSERT INTO fk_test_hub (name) VALUES ('Central Hub')"
        )

        import time

        start_time = time.time()

        # Analyze FK impact
        result = await fk_analyzer.analyze_foreign_key_impact(
            table="fk_test_hub",
            operation="modify_column_type",
            connection=real_connection,
        )

        execution_time = time.time() - start_time

        # Performance validation
        assert execution_time < 5.0  # Must complete within 5 seconds
        assert (
            len(result.affected_foreign_keys) == 10
        )  # All 10 spoke tables should be detected
        assert result.impact_level in [FKImpactLevel.CRITICAL, FKImpactLevel.HIGH]

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_real_database_error_handling(self, fk_analyzer, real_connection):
        """Test error handling with real database connection issues."""
        # Simulate analyzing non-existent table
        result = await fk_analyzer.analyze_foreign_key_impact(
            table="non_existent_table",
            operation="drop_column",
            connection=real_connection,
        )

        # Should handle gracefully without crashing
        assert isinstance(result, FKImpactReport)
        assert result.table_name == "nonexistenttable"  # Sanitized
        assert result.impact_level == FKImpactLevel.SAFE  # No FKs found
        assert len(result.affected_foreign_keys) == 0

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_integration_with_dependency_analyzer_real(
        self, fk_analyzer, real_connection
    ):
        """Test integration between FK analyzer and dependency analyzer with real database."""
        # Set up complex FK relationship for dependency analysis
        await real_connection.execute(
            """
            CREATE TABLE fk_test_department (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """
        )

        await real_connection.execute(
            """
            CREATE TABLE fk_test_employee (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                department_id INTEGER REFERENCES fk_test_department(id) ON DELETE SET NULL,
                manager_id INTEGER REFERENCES fk_test_employee(id) ON DELETE SET NULL
            )
        """
        )

        # Insert test data
        await real_connection.execute(
            "INSERT INTO fk_test_department (name) VALUES ('Engineering')"
        )
        await real_connection.execute(
            "INSERT INTO fk_test_employee (name, department_id) VALUES ('John Doe', 1)"
        )

        # Test that FK analyzer properly uses dependency analyzer
        result = await fk_analyzer.analyze_foreign_key_impact(
            table="fk_test_department",
            operation="drop_column",
            connection=real_connection,
        )

        # Verify that dependency analyzer found the FK relationship
        assert len(result.affected_foreign_keys) >= 1
        found_employee_fk = any(
            fk.source_table == "fk_test_employee"
            and fk.target_table == "fk_test_department"
            for fk in result.affected_foreign_keys
        )
        assert found_employee_fk is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=5"])
